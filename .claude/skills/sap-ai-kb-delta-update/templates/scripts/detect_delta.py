#!/usr/bin/env python3
"""
detect_delta.py — Detect changed files in sap-ai repos since last KB ingest.

For each repo in the workspace:
  - Reads the last-ingested commit SHA from .delta_state.json
  - Runs git diff --name-status <last_commit>..HEAD to find changed files
  - Applies the include/exclude filter (same rules as sync_repos.py)
  - Writes a structured report to --output

If a repo has no state entry, all qualifying files are treated as new.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Built-in cluster map: repo name -> cluster letter
CLUSTER_MAP = {
    # Cluster A — Architecture Vision & Strategy
    "ai-native-northstar-arch": "a",
    "durable-ai-agents": "a",
    "ai-golden-path": "a",
    "TechnologyGuidelines": "a",
    # Cluster B — Protocols & Standards
    "a2a-protocol": "b",
    "a2a-agent-template": "b",
    "mcp-protocol": "b",
    "mcp-translation-specification": "b",
    "open-resource-discovery-specification": "b",
    "api-guidelines": "b",
    "namespace-registry": "b",
    "api-metadata-validator": "b",
    # Cluster C — Gateway & Integration
    "agent-gateway": "c",
    "integration-layer": "c",
    "agent-connector": "c",
    "agent-gateway-documentation": "c",
    "fx-engagement-layer-docs": "c",
    # Cluster D — MCP Platform
    "mcp-hub": "d",
    "sdk": "d",
    "btp-service-metadata-mcp": "d",
    "mcp-hub-documentation": "d",
    "docs": "d",
    # Cluster E — BAF & Joule
    "baf-commons": "e",
    "baf-documentation": "e",
    "baf-examples": "e",
    "joule-function-toolkit": "e",
    "joule-functions-example": "e",
    "joule-baf-dev-patterns": "e",
    "joule-capability": "e",
    "architecture": "e",
    # Cluster F — Identity & Security
    "iam-for-agents": "f",
    "all-in-identity": "f",
    # Cluster G — Metadata & Discovery
    "open-resource-discovery-reference-application": "g",
    "crawler": "g",
    "agent-registry-catalog": "g",
    "unified-landscape-model": "g",
    "ums": "g",
    "unified-ai-agent": "g",
    "apis-and-events-portal": "g",
    # Cluster H — Agent Frameworks, Eval & Observability
    "agent-evaluation": "h",
    "agent-skills": "h",
    "agent-extensibility-documentation": "h",
    "agent-runtime-domains": "h",
    "agent-documentation": "h",
    "agent-onboarding": "h",
    "agent-mcp-hub-sample": "h",
    "appfnd-bat": "h",
    "document-grounding-toolkit": "h",
    # Cluster I — SDKs & Developer Tools
    "cloud-sdk-python": "i",
    "common-lib": "i",
    "spring-boot-starter-ord": "i",
    "euporie-dwc-integration-js": "i",
    "sdk-demo": "i",
    # Cluster J — Docs & Onboarding
    "atom-docs": "j",
    "sirius": "j",
    "urm-docs": "j",
    "stakeholders-documentation": "j",
    "user-documentation": "j",
    "intapp-guide": "j",
    "ucl-onboarding-guide": "j",
    "pab-integration": "j",
    "unified-agent-runtime-documentation": "j",
    "landing-page-content": "j",
    "landing-page": "j",
    "documentation": "j",
    "n8n-ord-service": "j",
}

# Include extensions
INCLUDE_EXTENSIONS = {
    ".md", ".txt", ".rst",
    ".py", ".ts", ".js", ".java", ".go",
    ".yaml", ".yml", ".json", ".toml", ".xml",
    ".png", ".jpg", ".jpeg", ".svg",
    ".pdf",
}

# Exclude directory name segments (any path component matching these is skipped)
EXCLUDE_DIR_SEGMENTS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    "target", ".nyc_output", ".gradle", ".mvn", "vendor",
}

# Exclude filename patterns
EXCLUDE_FILE_PATTERNS = [
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "*.min.js", "*.min.css", "*.map", "*.d.ts",
    "*.jar", "*.war", "*.class", "*.pyc", "*.so", "*.dylib", "*.exe",
]

MAX_FILE_SIZE = 500 * 1024  # 500 KB


def is_excluded_path(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    for part in parts[:-1]:  # directory components
        if part in EXCLUDE_DIR_SEGMENTS:
            return True
    filename = parts[-1]
    for pattern in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def is_included_extension(rel_path: str) -> bool:
    return Path(rel_path).suffix.lower() in INCLUDE_EXTENSIONS


def qualifies(rel_path: str) -> bool:
    return is_included_extension(rel_path) and not is_excluded_path(rel_path)


def run(cmd, cwd):
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=60
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_head_sha(repo_path: Path):
    rc, sha, _ = run(["git", "rev-parse", "HEAD"], repo_path)
    return sha if rc == 0 else None


def get_changed_files_since(repo_path: Path, last_commit: str):
    """Return (changed_files, deleted_files) relative paths since last_commit."""
    rc, out, err = run(
        ["git", "diff", "--name-status", f"{last_commit}..HEAD"],
        repo_path,
    )
    if rc != 0:
        return None, None, err

    changed = []
    deleted = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status, filepath = parts[0][0], parts[1]  # first char: M/A/D/R/C/T
        if not qualifies(filepath):
            continue
        if status == "D":
            deleted.append(filepath)
        else:
            changed.append(filepath)

    return changed, deleted, None


def get_all_qualifying_files(repo_path: Path):
    """Return all qualifying files (for new/untracked repos)."""
    rc, out, _ = run(["git", "ls-files"], repo_path)
    if rc != 0:
        # fallback: walk the directory
        files = []
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_SEGMENTS]
            for f in filenames:
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                if qualifies(rel):
                    full = repo_path / rel
                    if full.stat().st_size <= MAX_FILE_SIZE:
                        files.append(rel)
        return files, []

    files = []
    for line in out.splitlines():
        line = line.strip()
        if line and qualifies(line):
            full = repo_path / line
            try:
                if full.exists() and full.stat().st_size <= MAX_FILE_SIZE:
                    files.append(line)
            except OSError:
                pass
    return files, []


def main():
    parser = argparse.ArgumentParser(description="Detect delta changes in sap-ai repos")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--state", required=True, help="Path to .delta_state.json")
    parser.add_argument("--output", required=True, help="Path to write delta report JSON")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    state_path = Path(args.state).expanduser()

    # Load state
    state = {"schema": 1, "repos": {}}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception as e:
            print(f"WARNING: Could not load state file: {e}. Treating all repos as new.")

    repos_state = state.get("repos", {})

    repos_result = {}
    clusters_affected = set()

    for entry in sorted(workspace.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        # skip non-git dirs
        if not (entry / ".git").exists():
            continue

        repo_name = entry.name
        cluster = CLUSTER_MAP.get(repo_name)
        current_commit = get_head_sha(entry)
        prior = repos_state.get(repo_name, {})
        last_commit = prior.get("last_commit")

        if current_commit is None:
            repos_result[repo_name] = {
                "cluster": cluster,
                "last_commit": last_commit,
                "current_commit": None,
                "changed_files": [],
                "deleted_files": [],
                "status": "ERROR_NO_HEAD",
            }
            continue

        if last_commit is None:
            # New/untracked repo — full scan
            changed, deleted = get_all_qualifying_files(entry)
            status = "new_untracked"
        elif last_commit == current_commit:
            # No changes
            repos_result[repo_name] = {
                "cluster": cluster,
                "last_commit": last_commit,
                "current_commit": current_commit,
                "changed_files": [],
                "deleted_files": [],
                "status": "no_change",
            }
            continue
        else:
            changed, deleted, err = get_changed_files_since(entry, last_commit)
            if changed is None:
                repos_result[repo_name] = {
                    "cluster": cluster,
                    "last_commit": last_commit,
                    "current_commit": current_commit,
                    "changed_files": [],
                    "deleted_files": [],
                    "status": f"DIFF_ERROR: {err[:200]}",
                }
                continue
            status = "updated"

        if cluster and (changed or deleted):
            clusters_affected.add(cluster.upper())

        repos_result[repo_name] = {
            "cluster": cluster,
            "last_commit": last_commit,
            "current_commit": current_commit,
            "changed_files": changed,
            "deleted_files": deleted,
            "status": status,
        }

        sym = "+" if status == "new_untracked" else "↑"
        if changed or deleted:
            print(f"  {sym} {repo_name:45s} +{len(changed)} changed, -{len(deleted)} deleted")
        else:
            print(f"  ✓ {repo_name:45s} no qualifying changes")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "clusters_affected": sorted(clusters_affected),
        "repos": repos_result,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nDelta report written to {args.output}")

    total_changed = sum(len(v["changed_files"]) for v in repos_result.values())
    total_deleted = sum(len(v["deleted_files"]) for v in repos_result.values())
    repos_with_changes = sum(
        1 for v in repos_result.values() if v["changed_files"] or v["deleted_files"]
    )
    print(f"Clusters affected: {sorted(clusters_affected)}")
    print(f"Repos with changes: {repos_with_changes}")
    print(f"Total changed files: {total_changed}")
    print(f"Total deleted files: {total_deleted}")


if __name__ == "__main__":
    main()
