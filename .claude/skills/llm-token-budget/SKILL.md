---
name: llm-token-budget
description: Declare an explicit token budget before any expensive LLM operation — MoA workflows, multi-agent Workflow runs, large-context synthesis. Enforces a kill-at-2× gate. Prevents runaway spending from misconfigured presets, verify/judge left ON, shell-escape retry loops, and oversized corpora. Trigger: `/token-budget`
---

# llm-token-budget

Before launching any expensive LLM operation, state the expected cost and time explicitly, then enforce a hard kill at 2× the declared upper bound.

## Why this exists

Expensive operations spiral silently. None of these announce themselves until the bill arrives:
- MoA preset misconfigured as `deep-research` instead of `default` → 2× per chunk
- Verify+judge left ON by accident → 1.5M extra input tokens per phase
- Shell-escape bug causes 3–4 full MoA retries before diagnosis (see moa-research F11)
- Workflow loop condition bug spawns 30 agents instead of 3
- Oversized inlined corpus across every chunk → 2–3× input cost with no quality gain

**Empirical baseline:** a 3-chunk MoA research protocol with no verify/judge costs ~$3–10 and runs in 30–45 min. If you're at $20 and still running, something is wrong.

## When to invoke

- Before any MoA workflow launch (use alongside `moa-research` skill)
- Before any `Workflow(...)` call expected to spawn >5 subagents
- Before any large-context synthesis task (inline corpus >200 KB)
- When resuming a failed workflow run — re-declare the budget for the remaining work
- Trigger: `/token-budget`

---

## The budget declaration

State this before launching — in the conversation, or as a `log()` line in the Workflow script:

```
Budget declaration:
  Expected cost:   $X–Y     (e.g., $5–8)
  Expected time:   N min    (e.g., 30–45 min)
  Kill threshold:  $2Y      (hard stop: cost > 2× upper bound → stop and diagnose)
  Basis:           [what you're doing — chunks, preset, verify ON/OFF, corpus size]
```

You don't need precision — a factor-of-2 estimate is fine. The purpose is a kill threshold, not accounting.

In a Workflow script:
```javascript
phase('Budget')
log('Budget: $5-8 expected, kill at $16. 3 chunks, default preset, no verify. Corpus: 200 KB.')
```

---

## Reference costs (empirical, HAI proxy, 2026-07)

| Operation | Preset / config | Expected cost | Expected time |
|---|---|---|---|
| Single MoA chunk, ~50 KB inline | `default` | $0.50–1.50 | 3–8 min |
| Single MoA chunk, ~50 KB inline | `deep-research` | $1.00–3.00 | 5–12 min |
| 3-chunk MoA protocol, no verify | `default` | $3–8 | 25–40 min |
| 3-chunk MoA + 3-lens verify + judge | `deep-research` | $15–25 | 45–75 min |
| Claude Workflow, ~10 subagents | Sonnet, effort:medium | $2–5 | 10–20 min |
| Claude Workflow, ~30 subagents | Sonnet, effort:high | $10–20 | 20–45 min |
| Solo Opus, effort:high, 100 KB context | — | $0.10–0.30 | 1–3 min |

---

## Cost multiplier quick reference

| Change | Cost multiplier |
|---|---|
| `default` → `deep-research` preset | ~1.5–2× |
| Verify+judge OFF → ON | ~3–5× |
| Full corpus inline → per-chunk pruned slice | ~0.4–0.6× (savings) |
| 3 chunks → 5 chunks | ~1.7× |
| bash wrapper → Python wrapper (F11) | no cost change — but bash may silently retry 3–4× = 3–4× cost |

The two biggest levers: **(1) preset selection** and **(2) verify/judge toggle**. Fix those before anything else.

---

## Kill gate protocol

### Soft kill (time > 2× expected, cost still in range)

Check: is the workflow actually progressing?
```bash
pgrep -fa moa-call.sh           # alive = MoA still running
wc -c <workdir>/_logs/*.raw.md  # bytes increasing = output flowing
```
If stalled (no byte growth in 5 min), kill and diagnose. If progressing, note the overrun and continue with monitoring.

### Hard kill (cost > 2× upper bound)

**Stop immediately. Do not retry without diagnosis.**

Diagnose in this order:

1. **Preset misconfigured?**
   ```bash
   grep -A5 "deep-research:" ~/.hermes/config.yaml | grep max_tokens
   grep -A5 "default:" ~/.hermes/config.yaml | grep max_tokens
   ```
   Is `deep-research` being used where `default` was intended?

2. **Verify+judge accidentally ON?**
   Check the workflow script for `RUN_VERIFY=true` or `RUN_JUDGE=true`. Both default to OFF per moa-research skill.

3. **Retry loop?**
   ```bash
   pgrep -c moa-call.sh   # run twice, 30s apart — if count stays ≥1, something is looping
   ```

4. **Shell-escape bug?** (F11 in moa-research)
   Is MoA returning 0-byte output every call? If yes, switch to the Python wrapper — do not retry with bash.

5. **Corpus too large?**
   ```bash
   wc -c <workdir>/chunk*.prompt   # any single prompt file >800 KB?
   ```
   If yes, prune to per-chunk corpus slices.

---

## Applies to non-MoA workflows too

Any Claude Code `Workflow(...)` call that fans out to many agents needs a budget declaration:

```javascript
export const meta = {
  name: 'my-workflow',
  description: 'Does X',
  phases: [{ title: 'Budget' }, { title: 'Work' }]
}

phase('Budget')
log('Budget: $8-12 expected, kill at $24. 20 agents × Sonnet effort:medium.')

// KILL GATE: if budget.total set and remaining < threshold, abort
if (budget.total && budget.remaining() < 20_000) {
  log('Budget exhausted before work complete — stopping.')
  return { status: 'budget-exhausted' }
}
```

---

## Relation to other skills

- **moa-research**: The detailed preset/verify levers are in that skill's "Cost optimisation" section and F8/F9/F11 constraints. This skill adds the upfront declaration discipline and the kill gate protocol.
- **web-fetch-guardrail**: Fetch costs are separate from LLM costs — that guardrail handles the fetch budget (4× cost of using `hermes chat -s browser-harness` for fetching vs `fetch-sources`).
