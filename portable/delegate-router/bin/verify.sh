#!/usr/bin/env bash
# Verify delegate-router is installed in each harness location.

set -uo pipefail

CANONICAL="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
NAME="delegate-router"

check() {
  local label="$1" path="$2"
  if [[ ! -e "$path" ]]; then
    echo "  ✗ missing: $label  ($path)"
    return 1
  fi
  if [[ -L "$path" ]]; then
    local resolved
    resolved="$(readlink "$path")"
    if [[ "$resolved" == "$CANONICAL" ]]; then
      echo "  ✓ $label  (symlink → canonical)"
      return 0
    else
      echo "  ⚠ $label  points elsewhere: $resolved"
      return 1
    fi
  fi
  if [[ -f "$path/SKILL.md" ]]; then
    echo "  ✓ $label  (regular directory with SKILL.md)"
    return 0
  fi
  echo "  ✗ $label  exists but has no SKILL.md"
  return 1
}

fail=0
echo "Verifying $NAME (canonical: $CANONICAL)"

check "Claude Code" "$HOME/.claude/skills/$NAME"                            || fail=1
check "omp"         "$HOME/.pi/agent/skills/$NAME"                          || fail=1
check "Hermes"      "$HOME/.hermes/skills/multi-agent-orchestration/$NAME"  || fail=1

if [[ $# -gt 0 && "$1" == "--project" ]]; then
  proj="$2"
  check "Cline (project $proj)"   "$proj/.cline/skills/$NAME" || fail=1
  if [[ -f "$proj/.clinerules/00-delegate-router.md" ]]; then
    echo "  ✓ Cline rules shim present: $proj/.clinerules/00-delegate-router.md"
  else
    echo "  ⚠ Cline rules shim missing: $proj/.clinerules/00-delegate-router.md"
    fail=1
  fi
fi

if [[ $fail -eq 0 ]]; then
  echo "All checks passed."
else
  echo "One or more checks failed."
  exit 1
fi
