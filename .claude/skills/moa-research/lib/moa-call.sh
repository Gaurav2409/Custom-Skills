#!/usr/bin/env bash
# moa-call.sh — invoke Hermes MoA headlessly with an inlined prompt.
#
# Usage:
#   moa-call.sh <preset> <prompt-file> <output-file>
#
# Behavior:
# - Expands ===INLINE:<absolute-path>=== directives in the prompt before firing
#   Hermes. This exists because MoA reference models CANNOT read files — they
#   are LLM API calls, not tool-using agents. Any file referenced by path in
#   the prompt is invisible unless its contents are pasted inline.
#
# - Writes the aggregator's final response to <output-file>.
#
# - Also writes:
#     <output-file>.expanded  — the fully-expanded prompt actually sent
#     <output-file>.log       — Hermes stderr
#
# - Exits non-zero on: missing INLINE target, empty stdout, non-zero Hermes exit.
#
# Expansion directive syntax:
#   ===INLINE:<absolute-path>===
# must appear on its own line. Multiple directives in one prompt are all
# expanded independently. Replacement:
#   === BEGIN FILE: <path> ===
#   <file contents verbatim>
#   === END FILE ===
#
# Argv safety: macOS ARG_MAX is ~1 MB. After expansion the prompt is passed
# via argv to `hermes -z`. If expanded prompt > 800 KB this script errors out
# rather than silently truncating. Split into multiple calls in that case.
#
# Timeout: this script does NOT impose a wall-clock ceiling. Large-context
# MoA calls can legitimately run 10-25 min. If you need a ceiling, wrap this
# script with a caller-side timeout. See references/watchdog-mitigation.md
# for the Claude Code Workflow implications.

set -euo pipefail

# ARG_MAX safety threshold (macOS default 1048576). Leave headroom for env vars.
readonly ARGV_MAX_BYTES=800000

preset="${1:?preset required (e.g. deep-research, default, code, fast)}"
prompt_file="${2:?prompt file required}"
out_file="${3:?output file required}"
log_file="${out_file}.log"
expanded_prompt_file="${out_file}.expanded"

if [[ ! -r "$prompt_file" ]]; then
  echo "moa-call.sh: prompt file not readable: $prompt_file" >&2
  exit 2
fi

mkdir -p "$(dirname "$out_file")"

# ---------------------------------------------------------------------------
# Expand ===INLINE:<absolute-path>=== directives.
# ---------------------------------------------------------------------------

python3 - "$prompt_file" "$expanded_prompt_file" <<'PYEOF'
import sys, re, os

src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    text = f.read()

# Directive must be on its own line, absolute path only.
INLINE_RE = re.compile(r'^===INLINE:(?P<path>[^=]+?)===\s*$', re.MULTILINE)

def expand(match):
    path = match.group('path').strip()
    if not os.path.isabs(path):
        raise SystemExit(f"moa-call.sh: INLINE path must be absolute: {path}")
    if not os.path.isfile(path):
        raise SystemExit(f"moa-call.sh: INLINE target does not exist: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        body = f.read()
    return f"=== BEGIN FILE: {path} ===\n{body}\n=== END FILE ==="

expanded = INLINE_RE.sub(expand, text)

with open(dst, 'w', encoding='utf-8') as f:
    f.write(expanded)

inlines = expanded.count('BEGIN FILE:')
print(f"expanded {len(text)}B -> {len(expanded)}B ({inlines} inlines)", file=sys.stderr)
PYEOF

if [[ ! -s "$expanded_prompt_file" ]]; then
  echo "moa-call.sh: expansion produced empty file" >&2
  exit 2
fi

expanded_bytes=$(wc -c < "$expanded_prompt_file")
echo "moa-call.sh: expanded prompt is ${expanded_bytes} bytes" >&2

if (( expanded_bytes > ARGV_MAX_BYTES )); then
  echo "moa-call.sh: expanded prompt exceeds argv safety ceiling (${expanded_bytes} > ${ARGV_MAX_BYTES}). Split into multiple calls." >&2
  exit 5
fi

# ---------------------------------------------------------------------------
# Preset switch (best-effort). Hermes /moa uses the ACTIVE preset from
# ~/.hermes/config.yaml. `hermes moa configure` is interactive and cannot be
# scripted. If a caller specifies a preset that differs from the active one,
# we set HERMES_MOA_PRESET as a hint; Hermes may or may not honor it depending
# on version. Callers who need a specific preset should switch it manually
# via `hermes moa configure` before running.
# ---------------------------------------------------------------------------

active_preset="$(hermes moa list 2>/dev/null | awk '/Active in config:/ {print $NF; exit}')"
switched=0
if [[ -n "$preset" && "$preset" != "$active_preset" ]]; then
  export HERMES_MOA_PRESET="$preset"
  switched=1
  echo "moa-call.sh: requested preset=${preset} differs from active=${active_preset}; set HERMES_MOA_PRESET (best-effort)." >&2
fi

# ---------------------------------------------------------------------------
# Fire the MoA call.
# ---------------------------------------------------------------------------

prompt_content="$(cat "$expanded_prompt_file")"
if ! hermes -z "/moa ${prompt_content}" >"$out_file" 2>"$log_file"; then
  echo "moa-call.sh: hermes exited non-zero; see $log_file" >&2
  [[ "$switched" == "1" ]] && unset HERMES_MOA_PRESET
  exit 3
fi

[[ "$switched" == "1" ]] && unset HERMES_MOA_PRESET

# ---------------------------------------------------------------------------
# Empty-output detection. MoA can return "" with exit 0 when a reference
# model times out and the aggregator refuses to synthesize a single-draft
# answer. Callers must not treat exit 0 as success without checking bytes.
# ---------------------------------------------------------------------------

if [[ ! -s "$out_file" ]]; then
  echo "moa-call.sh: empty MoA output; see $log_file" >&2
  exit 4
fi

output_bytes=$(wc -c < "$out_file")
echo "moa-call.sh: wrote $out_file (${output_bytes} bytes)" >&2
