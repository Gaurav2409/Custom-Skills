# Hermes MoA config

## Verify reference models are actually LIVE (do this before every substantive call)

**The single most important check in this skill.** When reference models error or abstain, the Opus aggregator proceeds ALONE — you get a valid solo-Opus answer with zero cross-family diversity, and nothing fails loudly. The only surface tell is a preamble like "N drafts: failed/abstaining" in the output. This has silently degraded whole sessions. A PONG probe does NOT catch it (PONG exercises the aggregator, not the refs).

Run this against your target preset and require `ok == len(refs)`:

```bash
cd /Users/I321170/Documents/AI_Knowledge/hermes-agent
./venv/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from hermes_cli.config import load_config
from hermes_cli.moa_config import resolve_moa_preset
from agent.moa_loop import _run_reference
preset = resolve_moa_preset(load_config().get("moa") or {}, "deep-research")   # your preset
refs = preset.get("reference_models") or []
msgs = [{"role":"user","content":"Reply with exactly: OK"}]
for r in refs:
    label, text, _ = _run_reference(r, msgs, temperature=0.75, max_tokens=None)
    good = "OK" in (text or "") and "failed" not in (text or "")
    print(f"{'✓' if good else '✗'} {label}: {(text or '')[:80]!r}")
PY
```

If a ref shows `✗ ... [failed: ...]`, read the error:
- **`unsupported_parameter ... max_tokens ... use max_completion_tokens`** → an OpenAI-family model (gpt-5/o-series) got sent `max_tokens`. Hermes' `utils.model_forces_max_completion_tokens()` already remaps the known families; if a NEW family 400s, add its name prefix there. Note: MoA's own reference path sends `max_tokens=None` (no cap) so this usually only bites if a `reference_max_tokens` is set on the preset or you curl by hand.
- **transient (proxy 5xx, rate-limit, timeout)** → just re-run the probe; refs recover on their own. Only debug config if it fails repeatedly.

Confirm the HAI proxy and each model endpoint directly if the probe is ambiguous:

```bash
# proxy up?
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $HAI_PROXY_TOKEN" \
  http://localhost:6655/openai/v1/models
# gpt-5.5 present?
curl -s -H "Authorization: Bearer $HAI_PROXY_TOKEN" http://localhost:6655/openai/v1/models \
  | python3 -c "import sys,json;print('gpt-5.5' in [m['id'] for m in json.load(sys.stdin)['data']])"
```

## Presets

```
$ hermes moa list
Mixture of Agents presets
Default: deep-research
Active in config: deep-research

  default
    Reference models: gpt-5.5, claude-4.7-opus
    Aggregator: claude-opus-latest
    reference_temperature: 0.6
    aggregator_temperature: 0.4
    max_tokens: 32000

  code
    Reference models: gpt-5.5, claude-4.7-opus, claude-sonnet-latest
    Aggregator: gpt-5.5
    max_tokens: 32000

  fast
    Reference models: gpt-5.5, claude-4.7-opus
    Aggregator: claude-opus-latest
    max_tokens: 32000

  deep-research
    Reference models: gpt-5.5, claude-4.7-opus, claude-sonnet-latest
    Aggregator: claude-opus-latest
    reference_temperature: 0.75
    aggregator_temperature: 0.25
    max_tokens: 32000   ← check yours; ships at 8192 by default
```

## Bump `deep-research` max_tokens to 32000

The shipping default is 8192, which truncates dense multi-section markdown around ~10 KB. Bump it before running anything substantial:

```bash
BAK=~/.hermes/config.yaml.pre-max-tokens-bump.$(date +%Y%m%d%H%M%S).bak
cp ~/.hermes/config.yaml "$BAK"

python3 -c "
import pathlib
p = pathlib.Path.home() / '.hermes/config.yaml'
p.write_text(p.read_text().replace('max_tokens: 8192', 'max_tokens: 32000'))
"

grep -B 1 -A 3 'deep-research:' ~/.hermes/config.yaml | grep max_tokens
# expected: max_tokens: 32000
```

Bumping max_tokens is necessary but not sufficient. **Opus self-imposes a ~10 KB output ceiling on dense structured markdown regardless of max_tokens.** The chunked-emission pattern in this skill is what actually gets you past that. See [why-not-single-moa-call.md](why-not-single-moa-call.md).

## Switching the active preset

`hermes moa configure` is interactive and cannot be scripted headlessly. To switch presets from a script:

- Manual: `hermes moa configure` at a prompt, pick preset, save.
- Automated (best-effort): set `HERMES_MOA_PRESET=<name>` env var; Hermes may honor it depending on version.
- Reliable: edit `~/.hermes/config.yaml` directly. There are **three** selectors — set all three (verified 2026-07-16), then restore them when done:

```yaml
model:
  default: <target>          # top-level model.default
moa:
  default_preset: <target>
  active_preset: <target>
```

`hermes moa list` prints `Active in config: <name>` — use it to confirm the switch and to confirm the restore afterwards.

## Which preset when

| Task | Preset | Why |
|---|---|---|
| Deep research synthesis, cross-source triangulation | `deep-research` | 3 refs (Sonnet + Opus + gpt-5.5) → Opus aggregator. Highest diversity + best synthesis. Slower. |
| Fast iteration, red-team, taxonomy | `default` | 2 refs + Opus aggregator. Faster, cheaper, still good. |
| Code review, mechanical decomposition | `code` | 3 refs → gpt-5.5 aggregator. Better structural output. |
| Prototyping the workflow | `fast` | Same as default but with cache-friendly settings. |

## Reference-model quirks

Every MoA call retries reference models once without `temperature` because HAI providers occasionally reject temperature. This shows up in `~/.hermes/logs/agent.log` as `Auxiliary moa_reference: provider rejected temperature; retrying once without it`. It's normal, not an error.

## Debugging a MoA call

```bash
# What was the exact API call?
grep "deep-research.*provider=moa" ~/.hermes/logs/agent.log | tail -3

# Any upstream errors around the call time?
tail -100 ~/.hermes/logs/errors.log | grep -E "moa|aggregator|Streaming failed"

# Did a reference model hang or upstream 5xx?
tail -100 ~/.hermes/logs/gateway.log
```

Silent failures (0-byte output, exit 3 with no stderr) usually mean an upstream 5xx that Hermes didn't surface. Retry once; if it repeats, check HAI proxy status.
