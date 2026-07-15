# Hermes MoA config

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
- Reliable: edit `~/.hermes/config.yaml` directly:

```yaml
moa:
  default_preset: deep-research
  active_preset: <target>
```

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
