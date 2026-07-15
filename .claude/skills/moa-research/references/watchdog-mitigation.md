# Watchdog mitigation

Two watchdogs kill Claude Code Workflow agents. Both are load-bearing to work around.

## Watchdog 1: 180s no-tool-call stall detector

**Symptom:** subagent generating a large artifact (>15 KB dense markdown) gets killed mid-stream. Journal shows retry-until-exhausted. Zero bytes on disk.

**Cause:** the Workflow harness kills an agent that goes 180 seconds without a tool call. Writing a large artifact in one Write call takes 3-5 minutes of streaming text with no intermediate tool activity.

**Fix — sectioned writes:**

Ask the agent to write the artifact in sections. First section: Write. Subsequent sections: Edit. Each individual call stays under 180s of streaming, keeping the watchdog fed.

```
Write the artifact in sections:
1. **Write** — Header + Section 1 to <path>
2. **Edit** — Append Section 2 to <path>
3. **Edit** — Append Section 3 to <path>
... etc.

Between sections you may do additional Read/grep calls to confirm anchors before
appending. Every 60-120 seconds should see at least one tool call.
```

Bonus: sectioned writes give partial-progress artifacts if the agent dies partway. Not zero bytes on disk.

## Watchdog 2: 600s Bash tool timeout

**Symptom:** a shepherd agent's Bash call to `moa-call.sh` returns "timed out after 10 min". The `hermes -z /moa` process may or may not still be alive.

**Cause:** Claude Code's Bash tool has a hard 10-minute ceiling. Large-context MoA calls (200-300 KB inlined) legitimately take 10-25 min.

**Fixes (pick one):**

### Fix A: Tell the shepherd to poll externally

```
STEP 2. Run Bash. If it times out at 10 min, the moa-call.sh script may still
be running. Poll `pgrep -fa moa-call.sh` to check, and wait a further 10 min
via subsequent Bash calls before declaring failure.
```

This is what the skill's workflow template uses. Simple, works.

### Fix B: Detach with Python double-fork (macOS-safe)

If the shepherd absolutely can't wait, spawn `hermes` detached so it survives Bash timeout:

```python
python3 -c "
import os, sys
if os.fork() != 0: sys.exit(0)
os.setsid()
if os.fork() != 0: sys.exit(0)
os.close(0); os.close(1); os.close(2)
os.open('/dev/null', os.O_RDONLY)
os.open('/tmp/output.md', os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
os.open('/tmp/output.md.err', os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
with open('/tmp/output.pid', 'w') as f: f.write(str(os.getpid()))
os.execvp('hermes', ['hermes', '-z', '/moa ' + '<prompt>'])
"
```

macOS lacks `setsid` in `/usr/bin`; the Python fallback is necessary. Note that `nohup` alone is not enough — the subshell process group gets reaped when Bash returns.

### Fix C (NOT RECOMMENDED): `run_in_background: true`

Backgrounded Bash calls do survive parent turn boundaries, BUT the Workflow tool doesn't natively support this. It requires manual polling from subsequent turns and adds fragility. Only use if A and B fail.

## Watchdog 3 (Hermes-side): reference model timeout

**Symptom:** one of the 3 HAI connections goes to CLOSED early, the other two hang forever. Hermes eventually gives up and exits with 0 bytes.

**Cause:** an HAI upstream 5xx or timeout on one reference model. The MoA aggregator waits for all references before synthesizing.

**Fix:** retry once. If retry also fails, check `~/.hermes/logs/gateway.log` and `errors.log` around the call time. Common causes:

- `Streaming failed after partial delivery` — upstream cut the connection mid-response. Usually transient.
- `HTTP 401: Jwt is expired` — reauth via `hermes auth login`.
- `provider rejected temperature; retrying once without it` — normal, not a real error.

If reference-model failures are persistent across retries, one of the HAI providers is down. Switch to a preset with different refs (e.g. `default` uses only gpt-5.5 + opus, no sonnet).

## Post-mortem checklist when a workflow dies

When a workflow reports failure, in this order:

1. **Journal**: `cat ~/.claude/projects/.../subagents/workflows/wf_<id>/journal.jsonl`. Which agents `started` but never `result`?
2. **Agent transcript**: `agent-<id>.jsonl` for the failed agent — last 20 tool calls tell you where it got stuck.
3. **Hermes agent.log**: activity in the timing window of the failed call. `provider=moa` entries show input/output token counts and latency.
4. **On-disk artifacts**: `wc -c` on every file the workflow writes. Zero bytes = watchdog kill. Partial = truncation. CHECKPOINT_FAILED marker = shepherd caught a problem.
5. **Running procs**: `pgrep -fa moa-call.sh` — still alive means the underlying call is fine, the shepherd's Bash just timed out.
