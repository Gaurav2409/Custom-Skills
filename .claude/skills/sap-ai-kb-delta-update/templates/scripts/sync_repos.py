#!/usr/bin/env python3
"""
sync_repos.py — Copy delta files from the sap-ai workspace into the KB's raw/ directory.

Reads the delta report produced by detect_delta.py and for each changed file:
  - Copies <workspace>/<repo>/<file> -> <kb-root>/raw/repos/cluster-<letter>/<repo>/<file>
  - Removes KB raw copies of deleted source files
  - Skips oversized files (>500 KB)
  - Skips repos with no cluster assignment

Also updates .delta_state.json with the current HEAD SHA for each processed repo.
Writes a sync report to /tmp/sap-ai-sync-report.json.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_FILE_SIZE = 500 * 1024  # 500 KB

# Extensions with no LLM-readable value in a documentation KB
EXCLUDED_EXTENSIONS = {
    # Raster images — binary, not LLM-readable text
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    # Binary diagram source files (not text-readable)
    ".vsdx",
    # Binary office files
    ".pptx", ".docx",
    # PDFs — binary; not directly processable in the raw pipeline
    ".pdf",
    # Code files — no architecture doc value in this KB
    ".ts", ".js", ".groovy", ".css",
    # Build/deploy config
    ".npmrc", ".lock",
    # NOTE: .puml, .plantuml, .svg, .drawio, .mmd are KEPT — they are
    # text-based architecture diagram sources with LLM-readable content.
}

# Specific filenames to exclude regardless of extension
EXCLUDED_FILENAMES = {
    "Dockerfile", ".dockerignore", ".gitignore", ".gitmodules",
    "pytest.ini", ".webmanifest", "package-lock.json", "yarn.lock",
}

# Path segment prefixes — skip any file whose relative path starts with these
EXCLUDED_PATH_PREFIXES = (
    ".github/",          # CI/CD workflows
    "components/",       # Helm charts and Kubernetes deployment manifests
    ".pipeline/",        # SAP pipeline configs
    ".registry/",        # Agent onboarding registry tickets (ephemeral)
    "test/fixtures/",    # Test fixture data
    "test/",             # Test files generally
    "kyma/deployment-resources/",  # Kubernetes deployment values
)

# Built-in cluster map (same as detect_delta.py — kept in sync manually)
CLUSTER_MAP = {
    "ai-native-northstar-arch": "a", "durable-ai-agents": "a",
    "ai-golden-path": "a", "TechnologyGuidelines": "a",
    "a2a-protocol": "b", "a2a-agent-template": "b", "mcp-protocol": "b",
    "mcp-translation-specification": "b", "open-resource-discovery-specification": "b",
    "api-guidelines": "b", "namespace-registry": "b", "api-metadata-validator": "b",
    "agent-gateway": "c", "integration-layer": "c", "agent-connector": "c",
    "agent-gateway-documentation": "c", "fx-engagement-layer-docs": "c",
    "mcp-hub": "d", "sdk": "d", "btp-service-metadata-mcp": "d",
    "mcp-hub-documentation": "d", "docs": "d",
    "baf-commons": "e", "baf-documentation": "e", "baf-examples": "e",
    "joule-function-toolkit": "e", "joule-functions-example": "e",
    "joule-baf-dev-patterns": "e", "joule-capability": "e", "architecture": "e",
    "iam-for-agents": "f", "all-in-identity": "f",
    "open-resource-discovery-reference-application": "g", "crawler": "g",
    "agent-registry-catalog": "g", "unified-landscape-model": "g",
    "ums": "g", "unified-ai-agent": "g", "apis-and-events-portal": "g",
    "agent-evaluation": "h", "agent-skills": "h",
    "agent-extensibility-documentation": "h", "agent-runtime-domains": "h",
    "agent-documentation": "h", "agent-onboarding": "h",
    "agent-mcp-hub-sample": "h", "appfnd-bat": "h", "document-grounding-toolkit": "h",
    "cloud-sdk-python": "i", "common-lib": "i", "spring-boot-starter-ord": "i",
    "euporie-dwc-integration-js": "i", "sdk-demo": "i",
    "atom-docs": "j", "sirius": "j", "urm-docs": "j",
    "stakeholders-documentation": "j", "user-documentation": "j",
    "intapp-guide": "j", "ucl-onboarding-guide": "j", "pab-integration": "j",
    "unified-agent-runtime-documentation": "j", "landing-page-content": "j",
    "landing-page": "j", "documentation": "j", "n8n-ord-service": "j",
}


def load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text())
    return None


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main():
    parser = argparse.ArgumentParser(description="Sync delta files to KB raw/")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--kb-root", required=True)
    parser.add_argument("--delta-report", required=True)
    parser.add_argument("--state", default=None,
                        help="Path to .delta_state.json (default: <kb-root>/.delta_state.json)")
    parser.add_argument("--cluster-map-builtin", action="store_true",
                        help="Use built-in cluster map (default behaviour)")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    kb_root = Path(args.kb_root).expanduser().resolve()
    raw_repos = kb_root / "raw" / "repos"
    state_path = Path(args.state) if args.state else kb_root / ".delta_state.json"

    delta = load_json(Path(args.delta_report))
    if delta is None:
        print(f"ERROR: delta report not found: {args.delta_report}", file=sys.stderr)
        sys.exit(1)

    state = load_json(state_path) or {"schema": 1, "repos": {}}
    repos_state = state.setdefault("repos", {})

    copied = []
    deleted_from_raw = []
    skipped_oversized = []
    skipped_unassigned = []
    errors = []

    for repo_name, info in delta.get("repos", {}).items():
        cluster = info.get("cluster") or CLUSTER_MAP.get(repo_name)
        if not cluster:
            skipped_unassigned.append(repo_name)
            print(f"  ○ {repo_name:45s} UNASSIGNED — skipped")
            continue

        cluster_dir = raw_repos / f"cluster-{cluster}"
        repo_src = workspace / repo_name
        repo_dst = cluster_dir / repo_name

        changed_files = info.get("changed_files", [])
        deleted_files = info.get("deleted_files", [])
        current_commit = info.get("current_commit")
        status = info.get("status", "")

        if status == "no_change":
            continue

        # Copy changed/added files
        for rel in changed_files:
            src = repo_src / rel
            dst = repo_dst / rel
            try:
                if not src.exists():
                    errors.append({"repo": repo_name, "file": rel, "error": "src not found"})
                    continue
                if src.suffix.lower() in EXCLUDED_EXTENSIONS or src.name in EXCLUDED_FILENAMES:
                    continue
                if any(rel.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
                    continue
                size = src.stat().st_size
                if size > MAX_FILE_SIZE:
                    skipped_oversized.append({"repo": repo_name, "file": rel, "size_kb": size // 1024})
                    continue
                copy_file(src, dst)
                copied.append({"repo": repo_name, "cluster": cluster, "file": rel})
            except Exception as e:
                errors.append({"repo": repo_name, "file": rel, "error": str(e)})

        # Remove deleted files from raw/
        for rel in deleted_files:
            dst = repo_dst / rel
            try:
                if dst.exists():
                    dst.unlink()
                    deleted_from_raw.append({"repo": repo_name, "cluster": cluster, "file": rel})
                    # Remove empty parent dirs up to cluster_dir
                    parent = dst.parent
                    while parent != repo_dst and parent != cluster_dir:
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            except Exception as e:
                errors.append({"repo": repo_name, "file": rel, "error": f"delete: {e}"})

        # Update state
        if current_commit:
            repos_state[repo_name] = {
                "last_commit": current_commit,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "cluster": cluster,
            }

        n_c = len(changed_files)
        n_d = len(deleted_files)
        print(f"  ✓ {repo_name:45s} cluster-{cluster}: +{n_c} copied, -{n_d} deleted")

    # Save updated state
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state_path.write_text(json.dumps(state, indent=2))
    print(f"\nDelta state saved to {state_path}")

    # Write sync report
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "files_copied": len(copied),
            "files_deleted": len(deleted_from_raw),
            "skipped_oversized": len(skipped_oversized),
            "skipped_unassigned": len(skipped_unassigned),
            "errors": len(errors),
        },
        "copied": copied,
        "deleted": deleted_from_raw,
        "skipped_oversized": skipped_oversized,
        "skipped_unassigned": skipped_unassigned,
        "errors": errors,
    }

    report_path = Path("/tmp/sap-ai-sync-report.json")
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Sync report written to {report_path}")

    print(f"\nSync complete:")
    print(f"  Files copied:            {len(copied)}")
    print(f"  Files deleted from raw:  {len(deleted_from_raw)}")
    print(f"  Skipped (oversized):     {len(skipped_oversized)}")
    print(f"  Skipped (unassigned):    {len(skipped_unassigned)}")
    print(f"  Errors:                  {len(errors)}")

    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  {e['repo']}/{e['file']}: {e['error']}")

    if skipped_oversized:
        print(f"\nOversized files (not copied):")
        for f in skipped_oversized:
            print(f"  {f['repo']}/{f['file']} ({f['size_kb']} KB)")

    if skipped_unassigned:
        print(f"\nUnassigned repos (not synced):")
        for r in skipped_unassigned:
            print(f"  {r}")


if __name__ == "__main__":
    main()
