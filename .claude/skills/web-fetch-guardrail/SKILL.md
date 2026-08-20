---
name: web-fetch-guardrail
description: "Guardrail for all web fetch and search tasks. Use fetch-sources — not raw hermes agent sessions — to avoid cost multiplication and source contamination."
metadata:
  type: guardrail
  always_active: true
---

# Web Fetch Guardrail

## Hard Rule

**Use `fetch-sources` for all web fetch and search tasks. Never use a raw `hermes chat -s browser-harness` session for fetching.**

```bash
# Standard batch fetch (static → Jina → Playwright → browser-harness fallback)
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic

# Auth/SSO pages (uses your running Chrome session)
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic --browser-harness

# Search queries (SearXNG → Tavily → DuckDuckGo, then fetch)
TAVILY_API_KEY=$(security find-generic-password -a hermes-agent -s TAVILY_API_KEY -w) \
fetch-sources --queries queries.txt --out ./web-sources/ --id my-topic --per-query 4

# Re-fetch failed files
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic --refetch-failed --playwright
```

Script: `~/.local/bin/fetch-sources`
Source: `~/.claude/skills/web-clipper/templates/scripts/fetch-sources.py`

## Why hermes agent sessions are banned for web fetch

Two compounding problems:

**1. Cost:** `hermes chat` invokes an LLM on every turn. Even with `--provider custom:hai-anthropic -m claude-sonnet-latest` (Sonnet-only), a 40-turn fetch session = 40 LLM calls × 150K tokens = ~$5-25. With the default `deep-research` MoA preset it's 4× worse (~$110 for 4 briefs, as happened on 2026-07-09).

**2. Source contamination:** The hermes agent synthesizes and injects editorial framing ("BlueSpan analog", "implications for X") into saved files, destroying the raw source corpus. `fetch-sources` never calls an LLM — it only HTTP-fetches and strips HTML noise.

## CRITICAL: `--preset` is NOT a valid `hermes chat` flag

`hermes chat --preset web-fetch` is silently ignored. config.yaml swapping also does not work reliably (MoA gateway caches presets at startup).

If you must use `hermes chat` for some non-fetch reason, bypass MoA with:
```bash
~/.hermes/hermes-secure.sh chat -q "..." \
  --provider custom:hai-anthropic -m claude-sonnet-latest ...
```

## When MoA IS appropriate

- `moa-call.sh deep-research` for Phase B synthesis from saved local files (no web fetch)
- Any hermes task that reads local documents and synthesizes them

## Exceptions (use individual tools, not fetch-sources)

| Case | Tool |
|------|------|
| PDF files (arxiv, egazette) | `curl` + `pdftotext` |
| Single URL quick check | `http_get(url)` in browser-harness |
| Interactive CAPTCHA/2FA | `browser-harness` directly |
