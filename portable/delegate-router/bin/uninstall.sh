#!/usr/bin/env bash
# Uninstall delegate-router symlinks and .clinerules shim.
# Does NOT touch the canonical source directory.

set -uo pipefail

NAME="delegate-router"

PROJECT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--project <path>]"; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

remove_link() {
  local path="$1"
  if [[ -L "$path" ]]; then
    rm "$path" && echo "  - removed symlink: $path"
  elif [[ -e "$path" ]]; then
    echo "  ⚠ not a symlink, leaving in place: $path" >&2
  fi
}

remove_link "$HOME/.claude/skills/$NAME"
remove_link "$HOME/.pi/agent/skills/$NAME"
remove_link "$HOME/.hermes/skills/multi-agent-orchestration/$NAME"

if [[ -n "$PROJECT" ]]; then
  remove_link "$PROJECT/.cline/skills/$NAME"
  local_rule="$PROJECT/.clinerules/00-delegate-router.md"
  if [[ -f "$local_rule" ]]; then
    rm "$local_rule" && echo "  - removed rule: $local_rule"
  fi
fi

echo "Uninstall complete. Canonical source untouched."
