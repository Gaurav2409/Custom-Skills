#!/usr/bin/env python3
"""moa-call-safe.py — invoke Hermes MoA headlessly, shell-escape-safe.

Usage:
    moa-call-safe.py <preset> <prompt-file> <output-file>

IMPORTANT: Must be run with the hermes venv Python, NOT system python3:
    /Users/I321170/Documents/AI_Knowledge/hermes-agent/venv/bin/python3 \
        ~/.claude/skills/moa-research/lib/moa-call-safe.py <preset> <prompt> <out>

    Running with system Python 3.14 against a venv built for Python 3.11
    causes silent import crashes (.pyc version mismatch).

    The moa-call-safe.py wrapper detects this and re-execs itself with the
    venv Python automatically if needed.

ARCHITECTURE (v2 — direct MoA, no hermes -z subprocess):
    This wrapper calls aggregate_moa_context() directly from the hermes
    Python package rather than spawning a cold `hermes -z` subprocess.

    Why direct call:
    - `hermes -z` cold-start takes 30-90s on macOS when .pyc files are
      stale (Spotlight scanning, dyld cache miss, Python version mismatch
      between system 3.14 and venv 3.11 regenerating .pycs).
    - The `hermes -z` path also requires a full AIAgent construction and
      conversation loop just to run a single MoA synthesis call.
    - Direct call: import hermes libs once (~4s after pyc warmup), run
      refs in parallel, synthesise, write output. Total: refs latency + 4s.

    What it does:
    1. Resolves the preset from ~/.hermes/config.yaml
    2. Expands ===INLINE:<path>=== directives in the prompt file
    3. Calls _run_references_parallel() for the ref fan-out
    4. Calls call_llm() for the aggregator synthesis
    5. Writes the final synthesis to <output-file>

    This bypasses the conversation loop entirely — correct for headless
    one-shot synthesis where no tool use, memory, or session state is needed.

ROOT CAUSE HISTORY (bugs fixed in previous versions):
    Bug 1: bare `/moa <prompt>` string bypasses decode_moa_turn() — fixed
    Bug 2: default provider:moa causes double MoA fan-out — fixed
    Bug 3: hermes -z cold-start 30-90s on macOS stale .pyc — fixed HERE
      by calling aggregate_moa_context directly, no subprocess spawn.

Behavior:
- Expands ===INLINE:<absolute-path>=== directives (must be on their own line).
- Writes aggregator synthesis to <output-file>.
- Also writes <output-file>.expanded (the sent prompt) and <output-file>.log.
- Exits non-zero on: missing INLINE target, empty output, argv over ceiling,
  ref/aggregator failure.
"""
import os
import re
import sys
import time

ARGV_MAX_BYTES = 800_000  # macOS ARG_MAX ~1MB; leave headroom for env
INLINE_RE = re.compile(r'^===INLINE:(?P<path>[^=]+?)===\s*$', re.MULTILINE)

HERMES_AGENT_DIR = os.path.expanduser("~/Documents/AI_Knowledge/hermes-agent")
HERMES_VENV_PYTHON = os.path.join(HERMES_AGENT_DIR, "venv/bin/python3")
_REEXEC_ENV_VAR = "_MOA_REEXECED"

# Re-exec with venv Python immediately at module load — before any hermes imports.
# System Python (3.14) cannot use venv packages built for Python 3.11.
# IMPORTANT: Use the venv symlink path directly (not os.path.realpath).
# os.execve with the realpath bypasses pyvenv.cfg and lands on the system
# Homebrew Python without venv site-packages. The symlink path triggers
# Python's venv detection via pyvenv.cfg, giving the correct sys.path.
if not os.environ.get(_REEXEC_ENV_VAR):
    _venv_python = HERMES_VENV_PYTHON  # symlink — do NOT realpath
    _current_real = os.path.realpath(sys.executable)
    _venv_real = os.path.realpath(_venv_python)
    if _current_real != _venv_real and os.path.isfile(_venv_python):
        _env = dict(os.environ)
        _env[_REEXEC_ENV_VAR] = "1"
        _env["VIRTUAL_ENV"] = HERMES_AGENT_DIR + "/venv"
        os.execve(_venv_python, [_venv_python] + sys.argv, _env)


def _ensure_venv_python():
    """Re-exec this script with the hermes venv Python if we're not already using it.

    System Python (3.14) cannot import hermes venv packages built for Python
    3.11 — .pyc files are version-tagged and get regenerated on every import,
    causing 30-90s startup hangs and silent crashes. Re-execing with the venv
    Python ensures .pyc files are compatible and imports are fast.
    """
    if os.environ.get(_REEXEC_ENV_VAR):
        return  # already re-execed, don't loop
    if not os.path.isfile(HERMES_VENV_PYTHON):
        return  # venv not found, proceed with current Python and hope for the best
    current = os.path.realpath(sys.executable)
    target = os.path.realpath(HERMES_VENV_PYTHON)
    if current == target:
        return  # already the venv Python
    # Re-exec with venv Python
    env = dict(os.environ)
    env[_REEXEC_ENV_VAR] = "1"
    os.execve(target, [target] + sys.argv, env)  # replaces current process


def die(msg, code=1):
    print(f"moa-call-safe.py: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg):
    print(f"moa-call-safe.py: {msg}", file=sys.stderr, flush=True)


def expand_inlines(text, prompt_file):
    """Expand ===INLINE:<path>=== directives."""
    def _expand(m):
        path = m.group("path").strip()
        if not os.path.isabs(path):
            die(f"INLINE path must be absolute: {path}", 2)
        if not os.path.isfile(path):
            die(f"INLINE target does not exist: {path}", 2)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        return f"=== BEGIN FILE: {path} ===\n{body}\n=== END FILE ==="
    return INLINE_RE.sub(_expand, text)


def run_moa_direct(prompt: str, preset: str, log_file: str) -> str:
    """Call MoA directly via hermes Python package — no subprocess spawn.

    Imports hermes libs, resolves preset, fans out refs in parallel,
    synthesises with aggregator, returns the synthesis text.
    """
    t_start = time.time()

    sys.path.insert(0, HERMES_AGENT_DIR)

    log("importing hermes libs...")
    log(f"python: {sys.executable} {sys.version[:6]}")
    t0 = time.time()
    try:
        from hermes_cli.config import load_config
        from hermes_cli.moa_config import resolve_moa_preset
        from agent.moa_loop import (
            aggregate_moa_context,
            _preset_temperature,
        )
    except Exception as e:
        die(f"failed to import hermes libs from {HERMES_AGENT_DIR}: {e}", 2)
    log(f"hermes libs imported in {time.time()-t0:.1f}s")

    log("loading config and resolving preset...")
    try:
        cfg = load_config()
        moa_cfg = cfg.get("moa") or {}
        preset_dict = resolve_moa_preset(moa_cfg, preset)
    except Exception as e:
        die(f"failed to resolve preset '{preset}': {e}", 2)

    refs = preset_dict.get("reference_models") or []
    agg = preset_dict.get("aggregator") or {}
    log(f"preset={preset} refs={len(refs)} aggregator={agg.get('model')}")

    log(f"running MoA ({len(refs)} refs in parallel + aggregator)...")
    t0 = time.time()
    try:
        synthesis = aggregate_moa_context(
            user_prompt=prompt,
            api_messages=[{"role": "user", "content": prompt}],
            reference_models=refs,
            aggregator=agg,
            temperature=_preset_temperature(preset_dict, "reference_temperature"),
            aggregator_temperature=_preset_temperature(preset_dict, "aggregator_temperature"),
            reference_max_tokens=preset_dict.get("reference_max_tokens"),
        )
    except Exception as e:
        die(f"aggregate_moa_context failed: {e}", 3)

    log(f"MoA completed in {time.time()-t0:.1f}s (total {time.time()-t_start:.1f}s)")

    # aggregate_moa_context returns the "[Mixture of Agents context — ...]" wrapper.
    # For headless synthesis we want the raw synthesis, not the internal-guidance wrapper.
    # Strip the internal guidance header if present so output is the clean synthesis.
    GUIDANCE_PREFIX = "[Mixture of Agents context"
    if synthesis.startswith(GUIDANCE_PREFIX):
        # Find the double-newline after the header block
        parts = synthesis.split("\n\n", 2)
        if len(parts) >= 3:
            synthesis = parts[2].strip()
        elif len(parts) == 2:
            synthesis = parts[1].strip()

    return synthesis


def main():
    _ensure_venv_python()  # re-exec with venv Python 3.11 if running under system Python
    if len(sys.argv) != 4:
        die("usage: moa-call-safe.py <preset> <prompt-file> <output-file>", 2)
    preset, prompt_file, out_file = sys.argv[1], sys.argv[2], sys.argv[3]
    log_file = out_file + ".log"
    expanded_file = out_file + ".expanded"

    if not os.access(prompt_file, os.R_OK):
        die(f"prompt file not readable: {prompt_file}", 2)
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)

    with open(prompt_file, encoding="utf-8") as f:
        text = f.read()

    expanded = expand_inlines(text, prompt_file)

    n_inlines = expanded.count("BEGIN FILE:")
    log(f"expanded {len(text)}B -> {len(expanded)}B ({n_inlines} inlines)")

    b = len(expanded.encode("utf-8"))
    if b > ARGV_MAX_BYTES:
        die(f"expanded prompt exceeds ceiling ({b} > {ARGV_MAX_BYTES}); "
            f"split into multiple calls", 5)

    with open(expanded_file, "w", encoding="utf-8") as f:
        f.write(expanded)

    # Tee stderr to log file during MoA run so hermes internal logs are captured
    # but our progress messages still reach the caller's stderr.
    import io

    class _TeeStderr:
        def __init__(self, real, buf):
            self._real = real
            self._buf = buf
        def write(self, s):
            self._real.write(s)
            self._buf.write(s)
        def flush(self):
            self._real.flush()
            self._buf.flush()
        def fileno(self):
            return self._real.fileno()

    log_buf = io.StringIO()
    _real_stderr = sys.stderr
    sys.stderr = _TeeStderr(_real_stderr, log_buf)

    try:
        synthesis = run_moa_direct(expanded, preset, log_file)
    finally:
        sys.stderr = _real_stderr
        with open(log_file, "w", encoding="utf-8") as lf:
            lf.write(log_buf.getvalue())

    if not (synthesis or "").strip():
        die(f"empty synthesis; see {log_file}", 4)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(synthesis)
        if not synthesis.endswith("\n"):
            f.write("\n")

    log(f"wrote {out_file} ({os.path.getsize(out_file)} bytes)")


if __name__ == "__main__":
    main()
