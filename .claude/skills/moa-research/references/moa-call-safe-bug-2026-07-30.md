# MoA Silent Failure: Root Cause & Fix (2026-07-30)

## Two bugs, both silent

`moa-call-safe.py` produced 0-byte output with exit code 0. `hermes -z "/moa <prompt>"` hung for 5+ minutes and returned nothing. Both bugs had the same symptom but different causes.

---

## Bug 1 — Bare `/moa` string bypasses MoA entirely

### Symptom
Output produced but it is solo-Opus, not MoA. With large prompts: silent hang or 0-byte output.

### Root cause
`moa-call-safe.py` line 99 (original):
```python
proc = subprocess.run(["hermes", "-z", "/moa " + expanded], ...)
```

The oneshot path is: `hermes -z <msg>` → `run_oneshot(msg)` → `_run_agent(msg)` → `agent.run_conversation(msg)` → `conversation_loop(user_message=msg)`.

In `conversation_loop.py:623`, `decode_moa_turn(user_message)` checks:
```python
if not isinstance(message, str) or not message.startswith("__HERMES_MOA_TURN_V1__"):
    return message, None   # <-- always hits this branch for "/moa ..." strings
```

A bare `/moa <text>` string does NOT match. `moa_config` stays `None`. MoA never activates. The agent answers the literal `/moa <text>` as a normal chat message.

### Fix
Use `encode_moa_turn(prompt, config=moa_cfg, preset=preset)` from `hermes_cli.moa_config`. This builds the `__HERMES_MOA_TURN_V1__<base64>` encoded marker that `decode_moa_turn` recognises.

**Critical**: `encode_moa_turn(prompt, preset="deep-research")` alone raises `MoAPresetNotFoundError` — it resolves against an empty dict. Must pass the full moa config section:
```python
cfg = load_config()
moa_cfg = cfg.get("moa") or {}
marker = encode_moa_turn(prompt, config=moa_cfg, preset=preset)
```

---

## Bug 2 — Double MoA when default provider is `moa`

### Symptom
`hermes -z` hangs for 5+ minutes even on trivial prompts. Even baseline `hermes -z "Reply OK"` times out at 60s+.

### Root cause
`~/.hermes/config.yaml` has:
```yaml
model:
  default: deep-research
  provider: moa
```

When `hermes -z` runs without model override, `_run_agent` picks up `provider: moa` as the acting agent. The MoA facade runs 3 reference models on every call — including trivial ones.

With the Bug 1 fix applied, the flow becomes:
1. Marker decoded → `moa_config` set with 3 refs
2. `aggregate_moa_context()` fires → 3 refs run in parallel, aggregator synthesises → context prepended to user message ✓
3. Acting agent (provider: moa) now takes the turn → **runs 3 refs AGAIN** ✗

Double fan-out: 6 ref calls, 2 aggregator calls. With 15-30s per ref, total wall time exceeds any reasonable timeout.

### Fix
Extract the aggregator model/provider from the resolved preset dict and set them as env vars before the `hermes -z` subprocess call:
```python
preset_dict = resolve_moa_preset(moa_cfg, preset)
agg = preset_dict.get("aggregator") or {}
env["HERMES_INFERENCE_MODEL"] = agg.get("model")      # e.g. "claude-opus-latest"
env["HERMES_INFERENCE_PROVIDER"] = agg.get("provider") # e.g. "custom:hai-anthropic"
```

`_run_agent` in `oneshot.py` reads `HERMES_INFERENCE_MODEL` / `HERMES_INFERENCE_PROVIDER` and uses them as the acting model, overriding the `provider: moa` default. The acting agent is now the plain aggregator. The marker activates the reference fan-out inline via `aggregate_moa_context()`, then the aggregator acts on the synthesised context — correct single-pass MoA.

---

---

## Bug 3 — hermes -z cold-start hangs 30–90s (macOS .pyc stale cache)

### Symptom
Even after Bug 1 and Bug 2 fixes, `hermes -z` hangs for 30–90s on every call. Even `hermes -z "Reply OK"` times out.

### Root cause
Two compounding factors:
1. **Python version mismatch**: System Python is 3.14, venv Python is 3.11. `.pyc` files compiled by 3.14 are version-tagged and **ignored** by 3.11 — it regenerates them on every import.
2. **macOS Spotlight/privacy scanning**: macOS scans newly created `.pyc` files, blocking disk reads for 5–25s per file during indexing.

Measured: `from hermes_cli.config import load_config` alone: 17s. `from run_agent import AIAgent`: 29s. Total import chain for `run_oneshot`: 60–90s.

Running `compileall` with the venv Python helps (32,645 new `.pyc` files written) but macOS Spotlight scans those too — the improvement is slow and inconsistent.

### Fix — bypass hermes -z entirely (v2 architecture)

Instead of spawning a cold `hermes -z` subprocess, `moa-call-safe.py` v2 **calls `aggregate_moa_context()` directly** from the hermes Python package in-process:

```
old: hermes -z <encoded_marker>
     → run_oneshot() → AIAgent() → conversation_loop() → aggregate_moa_context()

new: import hermes libs directly
     → resolve_preset() → aggregate_moa_context() → write output
```

Benefits:
- No subprocess spawn overhead
- No AIAgent/conversation_loop/session_db construction
- Import happens once per wrapper invocation (~4s after pyc warmup, not 60–90s)
- No double-MoA risk (Bug 2 cannot recur — no provider:moa agent involved)
- No encode_moa_turn needed (Bug 1 cannot recur — no decode_moa_turn involved)

The `aggregate_moa_context()` function already does exactly what we need: fan-out refs in parallel, synthesise with aggregator, return text. The conversation-loop wrapper around it was adding complexity and startup cost for zero benefit in the headless case.

---

## Files changed

- `lib/moa-call-safe.py` v2 — calls `aggregate_moa_context()` directly, no `hermes -z` subprocess.
- `lib/moa-call.sh` — NOT fixed (legacy bash wrapper; use `moa-call-safe.py`).

---

## Why the live-refs probe appeared to hang (F12 note)

The SKILL.md Quick Start probe runs `_run_reference` directly in a standalone Python process (no hermes event loop). Valid but slow: ~20s hermes import overhead + ~15–30s per ref call × 3 serial = 65–110s total. The 120s bash timeout in the probe script falsely reports failure. Use `timeout 200 python3 ...` or run in background. The hanging was not ref model failure — it was a timeout on a valid slow call chain.

---

## Verify the fix

```bash
cat > /tmp/moa-probe.md << 'EOF'
Reply with exactly: PANEL_OK — [state how many reference drafts you received]
EOF
python3 ~/.claude/skills/moa-research/lib/moa-call-safe.py \
  deep-research /tmp/moa-probe.md /tmp/moa-probe.out
cat /tmp/moa-probe.out
# Expected: "PANEL_OK — 3 reference drafts" (or similar)
# If it says "0 drafts" or just "PANEL_OK" alone: Bug 2 not fixed (still double-MoA or no refs)
# If output is 0 bytes: check .log file for hermes errors
```

## Symptom

`moa-call-safe.py` produced 0-byte output with exit code 0. The `.log` file was
also 0 bytes. `hermes -z "/moa <prompt>"` would hang for 3+ minutes and then
return nothing, or return solo-Opus output with no MoA diversity.

## Investigation path

1. **HAI proxy up** — `curl http://localhost:6655/` returns `{"message":"Local Hai Proxy is running!"}`.
2. **Wire calls work** — `curl .../openai/v1/chat/completions` with `gpt-5.5` responds in <400ms when called directly with `max_completion_tokens`.
3. **Python timeout on `_run_reference`** — the `_run_reference` probe timed out after 120s even for a single ref. This was a red herring caused by the probe itself calling `_run_reference` outside the hermes event loop.
4. **`-z` oneshot path traced** — `hermes -z <prompt>` → `run_oneshot()` → `_run_agent()` → `agent.run_conversation(prompt)` → `conversation_loop()` → `decode_moa_turn(user_message)`.
5. **`decode_moa_turn` only recognises encoded marker** — it checks `message.startswith("__HERMES_MOA_TURN_V1__")`. A bare `/moa <text>` string does NOT match. `moa_config` stays `None`. MoA is never activated.
6. **Result** — hermes just runs the prompt as a normal user chat message. The agent answers the literal `/moa <text>` text. Output is solo-Opus, not MoA. With large prompts this can also hang because the agent tries to process the `/moa` prefix as a skill or slash command and gets confused.

## Root cause

`moa-call-safe.py` line 99 (original):

```python
proc = subprocess.run(
    ["hermes", "-z", "/moa " + expanded],   # <-- WRONG
    ...
)
```

The MoA conversation loop (`conversation_loop.py:623`) only activates MoA when
`decode_moa_turn()` returns a non-None config. That function only recognises the
`__HERMES_MOA_TURN_V1__<base64>` encoded format produced by `encode_moa_turn()`.
A raw `/moa <text>` string is treated as a plain chat message.

The same bug existed in the bash wrapper `moa-call.sh` — it too sends
`/moa <prompt>` as a bare string.

## Fix

Replace the raw `/moa <prompt>` string with the properly encoded marker:

```python
# NEW — in build_moa_marker():
sys.path.insert(0, HERMES_AGENT_DIR)
from hermes_cli.config import load_config
from hermes_cli.moa_config import encode_moa_turn
cfg = load_config()
moa_cfg = cfg.get("moa") or {}
result = encode_moa_turn(prompt, config=moa_cfg, preset=preset)
```

**Critical**: `encode_moa_turn(prompt, preset="deep-research")` alone fails with
`MoAPresetNotFoundError` because it calls `resolve_moa_preset({}, "deep-research")`
— resolving against an empty dict. You must pass the full `moa` config section
as the `config` argument: `encode_moa_turn(prompt, config=moa_cfg, preset=preset)`.

## Verify the fix works

```python
# Quick sanity — should decode back to 3 refs + correct aggregator
from hermes_cli.config import load_config
from hermes_cli.moa_config import encode_moa_turn, decode_moa_turn
cfg = load_config()
moa_cfg = cfg.get("moa") or {}
marker = encode_moa_turn("test", config=moa_cfg, preset="deep-research")
prompt, config = decode_moa_turn(marker)
assert len(config.get("reference_models", [])) == 3
assert config.get("aggregator", {}).get("model") == "claude-opus-latest"
print("OK")
```

## Files changed

- `lib/moa-call-safe.py` — replaced raw `/moa <prompt>` with `build_moa_marker()`
  which calls `encode_moa_turn(prompt, config=moa_cfg, preset=preset)`.
- `lib/moa-call.sh` — NOT fixed (legacy bash wrapper, still broken for this reason
  on top of the shell-escape issue; use `moa-call-safe.py` for all calls).

## Why the SKILL.md live-refs probe also appeared to hang

The probe runs `_run_reference` directly in a standalone Python process without
the hermes event loop. This works but is slow: hermes has a ~20s import/plugin
discovery overhead on cold start, and 3 serial ref calls at ~15s each = ~65s
total, exceeding the 120s bash timeout when run with surrounding overhead.
The probe is valid but needs a 180s+ timeout. The hanging was not a ref model
failure — it was a timeout on a valid (but slow) call chain.

## Update to SKILL.md F12

The live-refs probe step in the Quick Start now needs the corrected call
signature and a note that the probe requires ~90–180s to complete (3 refs
serial). See the updated F12 note below.

---

**F12 update (append):** The `_run_reference` probe requires ~90–180s for 3
serial refs due to hermes cold-start import overhead (~20s) + ref call latency
(~15–30s each). Run with a 180s+ timeout. A 120s bash timeout will falsely
report failure even when refs are live. Use `timeout 200 python3 ...` or run
in background and wait.
