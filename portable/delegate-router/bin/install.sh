#!/usr/bin/env bash
# Install delegate-router into every harness that lives on this box.
# Idempotent: safe to re-run. Uses symlinks so edits to the canonical source
# propagate everywhere.

set -euo pipefail

CANONICAL="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
NAME="delegate-router"

PROJECT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--project <path>]

  --project <path>   Also install into <path>/.cline/skills and drop a
                     <path>/.clinerules/00-delegate-router.md shim.
                     Cline skills are project-scoped, so this is how to
                     enable the skill for a specific repo.

Personal-scope targets (Claude Code, omp, Hermes) are always installed.
EOF
      exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

link() {
  local target="$1" linkname="$2"
  mkdir -p "$(dirname "$linkname")"
  if [[ -L "$linkname" ]]; then
    if [[ "$(readlink "$linkname")" == "$target" ]]; then
      echo "  ✓ already linked: $linkname"
      return
    fi
    echo "  ↻ updating symlink: $linkname"
    rm "$linkname"
  elif [[ -e "$linkname" ]]; then
    echo "  ⚠ path exists and is not a symlink, skipping: $linkname" >&2
    return
  fi
  ln -s "$target" "$linkname"
  echo "  + linked: $linkname -> $target"
}

echo "Installing $NAME from: $CANONICAL"

echo "[Claude Code]"
link "$CANONICAL" "$HOME/.claude/skills/$NAME"

echo "[omp / oh-my-pi]"
link "$CANONICAL" "$HOME/.pi/agent/skills/$NAME"

echo "[Hermes]"
link "$CANONICAL" "$HOME/.hermes/skills/multi-agent-orchestration/$NAME"

if [[ -n "$PROJECT" ]]; then
  if [[ ! -d "$PROJECT" ]]; then
    echo "  ✗ --project path does not exist: $PROJECT" >&2
    exit 1
  fi
  echo "[Cline] project: $PROJECT"
  link "$CANONICAL" "$PROJECT/.cline/skills/$NAME"

  RULE="$PROJECT/.clinerules/00-delegate-router.md"
  mkdir -p "$PROJECT/.clinerules"
  cat > "$RULE" <<'EOF'
# Delegate Router

When choosing between Claude Code, Cline, omp/oh-my-pi, and Hermes for
a task in this workspace, apply the `delegate-router` skill
(`.cline/skills/delegate-router/SKILL.md`).

Route by task shape, not by tool name:

- Claude Code — autonomous multi-file implementation.
- Cline       — IDE-supervised work, per-diff approval.
- omp         — terminal / LSP / DAP / harness-internal work.
- Hermes      — orchestration, research, scheduled/cross-repo work.

Before handing off between harnesses in the same repo: commit or stash,
name the branch, summarize state, don't let two harnesses edit the same
worktree at once.
EOF
  echo "  + wrote: $RULE"
fi

echo
echo "Done. Run bin/verify.sh to confirm."
