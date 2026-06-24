#!/usr/bin/env python3
"""
pull_all.py — Pull all git repos in the sap-ai workspace.

For each immediate subdirectory containing a .git folder:
  1. git fetch --all --prune
  2. git pull --ff-only

Skips repos that would require a merge. Reports local-only repos.
Writes a JSON report to --output.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(cmd, cwd):
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=60
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def has_remote(repo_path):
    rc, out, _ = run(["git", "remote"], repo_path)
    return rc == 0 and bool(out.strip())


def pull_repo(repo_path: Path):
    name = repo_path.name

    if not (repo_path / ".git").exists():
        return {"name": name, "status": "NOT_A_GIT_REPO", "detail": ""}

    if not has_remote(repo_path):
        rc, sha, _ = run(["git", "rev-parse", "HEAD"], repo_path)
        return {
            "name": name,
            "status": "LOCAL_ONLY",
            "current_commit": sha if rc == 0 else "unknown",
            "detail": "No remote configured",
        }

    # fetch
    rc, _, err = run(["git", "fetch", "--all", "--prune"], repo_path)
    if rc != 0:
        return {
            "name": name,
            "status": "FETCH_ERROR",
            "detail": err[:300],
        }

    # check if ahead of remote (nothing to pull)
    rc_branch, branch, _ = run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_path
    )
    if rc_branch != 0:
        return {"name": name, "status": "ERROR", "detail": "Cannot determine branch"}

    branch = branch.strip()

    # get remote tracking branch
    rc_upstream, upstream, _ = run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        repo_path,
    )
    if rc_upstream != 0:
        # no upstream — local branch only
        rc, sha, _ = run(["git", "rev-parse", "HEAD"], repo_path)
        return {
            "name": name,
            "status": "LOCAL_ONLY",
            "current_commit": sha if rc == 0 else "unknown",
            "detail": f"Branch '{branch}' has no upstream",
        }

    # compare local vs remote
    rc_rev, remote_sha, _ = run(["git", "rev-parse", upstream.strip()], repo_path)
    rc_loc, local_sha, _ = run(["git", "rev-parse", "HEAD"], repo_path)

    if rc_rev == 0 and rc_loc == 0 and remote_sha == local_sha:
        return {
            "name": name,
            "status": "ALREADY_CURRENT",
            "current_commit": local_sha,
            "detail": "",
        }

    # attempt pull --ff-only
    rc, out, err = run(["git", "pull", "--ff-only"], repo_path)
    if rc == 0:
        rc2, new_sha, _ = run(["git", "rev-parse", "HEAD"], repo_path)
        return {
            "name": name,
            "status": "UPDATED",
            "previous_commit": local_sha if rc_loc == 0 else "unknown",
            "current_commit": new_sha if rc2 == 0 else "unknown",
            "detail": out[:200],
        }

    # non-fast-forward
    if "Not possible to fast-forward" in err or "diverged" in err or rc == 128:
        return {
            "name": name,
            "status": "SKIPPED_MERGE_REQUIRED",
            "current_commit": local_sha if rc_loc == 0 else "unknown",
            "detail": err[:300],
        }

    return {
        "name": name,
        "status": "PULL_ERROR",
        "detail": err[:300],
    }


def main():
    parser = argparse.ArgumentParser(description="Pull all git repos in a workspace")
    parser.add_argument("--workspace", required=True, help="Path to workspace directory")
    parser.add_argument("--output", required=True, help="Path to write JSON report")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"ERROR: workspace not found: {workspace}", file=sys.stderr)
        sys.exit(1)

    results = []
    for entry in sorted(workspace.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            result = pull_repo(entry)
            results.append(result)
            status = result["status"]
            sym = {"UPDATED": "↑", "ALREADY_CURRENT": "✓", "LOCAL_ONLY": "○",
                   "SKIPPED_MERGE_REQUIRED": "⚠", "FETCH_ERROR": "✗",
                   "PULL_ERROR": "✗", "NOT_A_GIT_REPO": "-"}.get(status, "?")
            print(f"  {sym} {entry.name:45s} {status}")

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "summary": counts,
        "repos": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {args.output}")

    errors = [r for r in results if r["status"] in ("FETCH_ERROR", "PULL_ERROR")]
    if errors:
        print(f"\nWARNING: {len(errors)} repos had errors:")
        for e in errors:
            print(f"  {e['name']}: {e['detail'][:120]}")


if __name__ == "__main__":
    main()
