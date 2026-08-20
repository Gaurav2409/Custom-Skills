---
name: okf-knowledge-format
description: Read OKF-conformant LLM knowledge bases efficiently and without quality loss, or create/validate/migrate OKF bundles. Use when (a) the user asks a research question against any KB under ~/Documents/LLM knowledge base/ — invoke the read protocol below; (b) the user wants to create a new OKF bundle, validate one, enrich from BigQuery, visualize, or migrate existing KBs to OKF — read the relevant reference file. Also triggers on "OKF spec", "knowledge-as-code", "agent-readable knowledge format".
version: 1.2.0
author: Gaurav2409
---

# OKF Knowledge Format Skill

OKF (Open Knowledge Format, Google 2026) represents knowledge as markdown + YAML frontmatter. All 8 LLM KBs under `~/Documents/LLM knowledge base/` are OKF v0.1 conformant.

**Core fact:** Every wiki article has `type:` in its frontmatter (concept | entity | topic | analysis). This enables fast metadata-driven retrieval — but **metadata-only filtering loses 60–70% recall**, so always pair it with a body-grep pass for research questions.

## Decision Tree

| User intent | Action |
|-------------|--------|
| Research question against a KB | **Read protocol below** (this file) |
| "Create an OKF bundle for X" | Read `references/create-bundle.md` |
| "Validate this bundle" | Read `references/validate.md` |
| "Enrich from BigQuery / a database" | Read `references/enrich.md` |
| "Visualize this bundle" | Read `references/visualize.md` |
| "Migrate existing KBs to OKF" | Read `references/migrate.md` |
| "What is OKF / how does it work?" | Read `references/spec-overview.md` |

## KB Catalog (all OKF v0.1 conformant)

| KB | Articles | Topics |
|----|---------|--------|
| `agentic-rag-and-memory-kb` | 80 | RAG, agent memory, OKF, knowledge-as-code |
| `sap-ai-practices-kb` | 200 | Joule, AI Core, agent frameworks, eval-driven dev |
| `sap-ai-northstar-arch-kb` | 262 | A2A, MCP, ORD, agent gateway, BAF |
| `sap-btp-solution-architect-kb` | 63 | BTP services, CF, Kyma, Integration Suite |
| `sap-enterprise-architect-kb` | 18 | TOGAF, EA frameworks, LeanIX |
| `knowledge-graph-design-kb` | 45 | Graph theory, ontology, EKG, GraphRAG |
| `avalara-avatax-kb` | 33 | AvaTax API, Avalara MCP, ERP tax |
| `cbc-onboarding-kb` | 28 | UCL, SPII, URM, ORD, webhooks |

KB root template: `/Users/I321170/Documents/LLM knowledge base/<kb-name>`

## Read Protocol — The Load-Bearing Section

For any research question, follow this 4-step flow. Use the helper `okf_read.py` in this skill's directory.

```bash
OKF_READ=/Users/I321170/.claude/skills/okf-knowledge-format/okf_read.py
KB="/Users/I321170/Documents/LLM knowledge base/<kb-name>"
```

**Step 1 — Orient (always run first on unfamiliar KBs):**
```bash
python3 $OKF_READ "$KB"
```
~50ms. Shows type counts and top tags so you pick filter terms that exist.

**Step 2 — Filter with `--high-recall` (mandatory for research):**
```bash
python3 $OKF_READ "$KB" --tag <topic> --high-recall
python3 $OKF_READ "$KB" --type concept --tag <topic> --high-recall
```
~60–80ms. Combines metadata match with body grep. Articles found via body recall are marked `[body]`.

> **Why `--high-recall`?** Tag-only filter has 27–38% recall (measured). Articles often discuss a topic without being tagged for it. The recall flag adds a body-grep pass that pushes recall to 98–100% at <80ms cost.

**Step 3 — Read top 3–5 full articles:**
```bash
python3 $OKF_READ "$KB" --get concepts/<id>
# or
cat "$KB/wiki/concepts/<id>.md"
```

**Step 4 — Follow `[[wikilinks]]` one hop** for transitive context, then synthesize with citations.

## Other Modes

```bash
# Substring search with body fallback (default — disable with --no-body-fallback)
python3 $OKF_READ "$KB" --search "authentication"

# Cross-link graph (when relationships matter)
python3 $OKF_READ "$KB" --tag <topic> --high-recall --graph

# Coverage sanity check (warns on overly narrow filters)
python3 $OKF_READ "$KB" --tag <topic> --high-recall --show-coverage

# JSON output (for scripting)
python3 $OKF_READ "$KB" --type entity --json
```

## Anti-patterns

| ❌ Don't | ✅ Do |
|---------|-------|
| `--tag X` for research questions | `--tag X --high-recall` |
| Read every article in `wiki/` | Filter first, then read 3–5 |
| Skip Step 1 on unfamiliar KBs | Always orient — saves dead-end filters |
| Use this skill to ingest sources | Use `llm-knowledge-base` skill instead |

## When to Defer to llm-knowledge-base Skill

| Question | Use |
|----------|-----|
| "What is X?" / "How does Y work?" / focused factual | This skill (read protocol above) |
| "Compare X across KBs" / multi-KB synthesis | `llm-knowledge-base` query |
| "Add this source to the wiki" | `llm-knowledge-base` ingest |
| "Find gaps in coverage of Z" | `llm-knowledge-base` lint |

## Hermes Integration

```bash
~/.hermes/hermes-secure.sh -z "Use OKF read protocol to find Joule architecture docs:
python3 /Users/I321170/.claude/skills/okf-knowledge-format/okf_read.py \
  '/Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb' \
  --tag joule --high-recall
Then read the top 5 results and summarize."
```

## Recall Benchmark (measured 2026-06-17)

| Filter | Body grep truth | OKF naive | OKF `--high-recall` | Time |
|--------|----------------|-----------|---------------------|------|
| `--tag joule` | 101 | 27 (27%) ❌ | 101 (100%) ✅ | 76ms |
| `--tag mcp` | 87 | 33 (38%) ❌ | 85 (98%) ✅ | 56ms |
| `--tag agent-gateway` | 56 | 18 (30%) ❌ | 58 (100%) ✅ | 60ms |

**`--high-recall` is essentially lossless at <100ms.** Use it as the default.

## Files in This Skill

- `SKILL.md` — this file (trigger guide + read protocol, ~1.2k tokens)
- `okf_read.py` — retrieval helper (the workhorse)
- `references/` — load these on-demand only when the user requests that specific action:
  - `spec-overview.md` — what OKF is, frontmatter spec, conformance rules, comparison to DCAT/RAG
  - `create-bundle.md` — scaffold a new OKF bundle (templates, structure, cross-linking)
  - `validate.md` — conformance validation script (Python, stdlib only)
  - `enrich.md` — BigQuery / database enrichment patterns + Google's reference agent
  - `visualize.md` — graph viewer patterns (Cytoscape.js, custom D3)
  - `migrate.md` — migrating existing KBs (the 2026-06-17 procedure + okf_migrate.py)
