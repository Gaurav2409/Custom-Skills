# Knowledge Base Patterns — Reference

Advanced patterns for operating and scaling LLM knowledge bases.

---

## 1. Multi-Source Ingest Strategies

### Web Articles (Obsidian Web Clipper)
The recommended workflow for web articles is to use the [Obsidian Web Clipper](https://obsidian.md/clipper) browser extension. It saves the page directly as a `.md` file into the vault with frontmatter (title, URL, date). Configure the clip destination to `raw/articles/`.

### PDFs and Papers
For PDFs, use `ingest.py --file paper.pdf --type paper`. The LLM reads PDFs natively during compile. For scanned PDFs, use an OCR tool first (e.g., `ocrmypdf`) before ingesting.

### GitHub Repositories
To index a repository, clone it into `raw/repos/<repo-name>/`. During compile, the LLM will read key files (README, docs/, key source files) and create a summary + entity article.

### Images
Download images to `raw/images/`. During compile, the LLM reads them with its vision capability. Name images descriptively (e.g., `transformer-architecture-diagram.png`). Enable `ingest.vision_pass.on_images: true` in `kb.config.json` to extract text, diagrams, and entities from each image automatically.

### Batch Directory Ingest
Pass a directory path directly to the skill: "ingest `data/articles/`". The skill walks the directory recursively, applies the quality filter, and batch-compiles all supported files. This is equivalent to dropping files into `raw/` and running compile, but in a single command.

---

## 2. Wiki Article Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Concept | lowercase-kebab | `attention-mechanism.md` |
| Entity (person) | firstname-lastname | `andrej-karpathy.md` |
| Entity (org) | org-name | `anthropic.md` |
| Entity (tool/model) | tool-name-version | `gpt-4o.md`, `llama-3.md` |
| Topic | topic-name | `scaling-laws.md` |
| Analysis (filed query) | query-slug-date | `gpt4-vs-claude-2025-04.md` |

---

## 3. Index Maintenance

The `_index.md` file is the entry point for LLM navigation. Keep it under 300 lines. For large wikis (> `wiki.split_index_at` articles), split the index by section:

```
wiki/
├── _index.md              # Top-level index (links to section indexes)
├── _index-concepts.md     # All concept articles
├── _index-entities.md     # All entity articles
├── _index-topics.md       # All topic articles
└── _index-analyses.md     # Filed query outputs
```

The LLM reads `_index.md` first, then navigates to section indexes as needed.

---

## 4. Incremental Compilation Strategy

To avoid reprocessing large wikis from scratch on every compile:

1. Run `python scripts/compile.py` to list only new/changed raw docs
2. For each new doc, run the LLM compile phase for that single doc
3. Update `_summaries.md`, `_index.md`, and the log incrementally

The `_summaries.md` file acts as the "processed" registry — a doc is considered compiled once its name appears there. Changed files are detected by comparing raw file modification time against the `last_updated` frontmatter of their corresponding wiki articles.

---

## 5. Q&A with Large Wikis

For wikis with 100+ articles and 400k+ words:

1. Use `scripts/search.py` or `qmd` to pre-filter to the top 5–10 relevant articles
2. Read those articles fully
3. Follow `## Connections` and `related` frontmatter links to discover adjacent articles (1 hop)
4. Answer based on the retrieved context, weighting by `confidence` frontmatter

The LLM does **not** need to read the entire wiki for most queries — the index + search + backlinks are sufficient for navigation.

---

## 6. qmd Search Integration

[qmd](https://github.com/tobi/qmd) is a local hybrid BM25/vector search engine for markdown files with LLM reranking, all on-device. It has both a CLI and an MCP server.

### Installation

```bash
npm install -g @tobilu/qmd
```

### Setup

```bash
# Add the wiki as a searchable collection
qmd collection add wiki/ --name <kb-name>
qmd context add qmd://<kb-name> "Wiki for <topic>"

# Re-embed after each compile
qmd embed
```

### Usage patterns

```bash
# Semantic search (vector)
qmd query "how does attention work" --files

# Exact match (BM25)
qmd query "RLHF" --bm25

# Hybrid with auto-expanded queries
qmd query "scaling laws neural networks" --expand

# JSON output for agentic pipelines
qmd query "transformer architecture" --json
```

### MCP daemon (for heavy-use wikis)

Running qmd as a persistent HTTP MCP server avoids model reload overhead for query-heavy workflows:

```bash
# Start daemon (survives session)
qmd mcp --http --daemon --port 8181

# Add to Claude Code MCP config (~/.claude/mcp_servers.json or settings.json):
{
  "qmd": {
    "type": "http",
    "url": "http://localhost:8181"
  }
}
```

Enable in `kb.config.json`: `"search": { "backend": "qmd", "qmd": { "mcp_http": true, "mcp_port": 8181 } }`

### When to use qmd vs naive search

| Condition | Recommendation |
|-----------|---------------|
| Semantic/conceptual queries | qmd (vector mode) |
| Exact term or keyword lookup | naive grep or qmd BM25 |
| Wiki > 100 articles | qmd (scales better) |
| No npm / offline | naive scripts/search.py |
| qmd daemon running | qmd (zero latency) |

---

## 7. Confidence Scoring Patterns

Every wiki article carries a `confidence` field (`high` | `medium` | `low`) derived from source quality and corroboration count. This enables precision-aware queries.

### Source weight reference

| Source type | Weight | Typical confidence |
|-------------|--------|-------------------|
| Peer-reviewed paper | 1.0 | high (if 1+) |
| Official documentation | 0.9 | high |
| News/journalism | 0.7 | medium |
| Blog post | 0.5 | medium (if 2+) |
| Social media | 0.3 | low |
| Inferred connection | 0.2 | low |

### Confidence assignment rules

- `high`: weight ≥ 0.9, or cumulative weight from multiple sources ≥ 1.5
- `medium`: single source with weight 0.5–0.8, or two sources with total ≥ 1.0
- `low`: single source with weight < 0.5, or purely inferred

### Using confidence in precision mode

Set `"mode": "precision"` in `kb.config.json` to:
- Skip claims with `confidence: low` during compile
- Set `review_status: needs-review` on articles sourced only from low-weight sources
- Raise `search.precision_score_threshold` (e.g., `0.6`) to filter low-scoring qmd results
- Use `output.file_back_to_wiki: "never"` (don't auto-file speculative outputs)

### Using confidence in recall mode

Set `"mode": "recall"` (default) to:
- Include all claims; mark speculative ones with `> **[Inferred]** ...`
- Use `output.file_back_to_wiki: "always"` to auto-file all query outputs
- Set `search.precision_score_threshold: 0.0` (retrieve all results)

---

## 8. Wiki Health Metrics

Track these metrics over time to measure KB quality (reported in the health dashboard during lint):

| Metric | Target | Needs work |
|--------|--------|-----------|
| Articles with summaries | > 95% | < 80% |
| Articles with sources | > 90% | < 70% |
| Confidence high/medium | > 80% | < 60% |
| Stub articles (< 120 words) | < 5% | > 15% |
| Orphan articles | 0 | > 3 |
| Broken wikilinks | 0 | > 5 |
| Open questions per article | 1–3 | 0 (stagnant) or > 5 (bloated) |
| Connection density (links/article) | ≥ 3 | < 2 |
| Contradiction flags | 0 | > 2 |

---

## 9. Synthetic Data Generation and Fine-tuning Prep

For advanced use: once your wiki reaches `training_data.min_wiki_words` words, you can generate training data.

### Q&A Pair Generation

The skill's Phase 11 handles this automatically. For manual generation:

> "Read `wiki/concepts/attention-mechanism.md` and generate 10 diverse Q&A pairs that test understanding of this concept. Format as JSONL with `prompt`, `completion`, and `reasoning` (chain-of-thought) fields."

Save to `outputs/training-data/<article-slug>-qa.jsonl`.

### Fine-tuning Considerations

- Use the wiki as the **knowledge source**, not the fine-tuning target
- Fine-tune on **reasoning patterns** (how to navigate and synthesize the KB), not raw facts
- Keep the wiki as the ground truth; fine-tuned models drift over time as the KB grows
- Include `confidence` metadata in training pairs so the model learns to qualify its answers

---

## 10. Multi-KB Federation

When you have multiple knowledge bases on related topics, link them:

1. Set `federation.enabled: true` and add peer KBs to `federation.peers` in `kb.config.json`
2. During Q&A, if the local wiki returns < 3 results, the LLM checks peer KB indexes automatically
3. Use `federation.cross_link_prefix` for cross-KB links: `[article](../other-kb/wiki/concepts/foo.md)`

Example config:
```json
"federation": {
  "enabled": true,
  "peers": [
    { "name": "policy-kb", "root": "/Users/me/research/policy-kb", "topic": "AI policy" }
  ],
  "cross_link_prefix": "../{peer-name}/wiki/",
  "query_peers_on_miss": true
}
```

---

## 11. Version Control

Keep the entire KB in a git repository for history and collaboration:

```bash
cd <kb-root>
git init
git add .
git commit -m "kb: init — <kb-name>"
```

Enable auto-commit in `kb.config.json`: `"git": { "enabled": true, "auto_commit": true }`. The skill will commit after each compile and lint run with a structured message.

Use the **Obsidian Git** plugin to also auto-commit from within Obsidian on a schedule (e.g., every 30 minutes).

Suggested `.gitignore`:
```
outputs/charts/*.png   # Regenerable from *.py scripts
__pycache__/
*.pyc
.DS_Store
scripts/__pycache__/
```

Commit messages from compile runs make the KB's evolution inspectable: `git log --oneline` shows when each concept was first added.

---

## 12. Semantic Pre-Clustering (NEW)

Before compiling 50+ documents, group them by topic similarity to enable cluster-aware compilation.

### Why Cluster?

- **Better cross-linking**: The LLM sees all related docs in a cluster, enabling richer wikilinks
- **Contradiction detection**: Contradictions only matter between topically-related docs
- **Model routing**: Large clusters with many cross-references get Opus; small factsheet clusters get Sonnet
- **RAPTOR-style summaries**: Cluster structure enables hierarchical summarization

### How It Works

```bash
python scripts/cluster.py --kb-root . --method tfidf --target-size 20
```

1. TF-IDF vectorization of all raw documents (first 3000 chars)
2. Agglomerative clustering with Ward linkage
3. Dynamic threshold to achieve target cluster size of 15-25 docs
4. Output: `cluster_manifest.json` with cluster labels, members, and top keywords

### Cluster Manifest Format

```json
{
  "created": "2025-05-02T15:30:00",
  "method": "tfidf_agglomerative",
  "num_clusters": 35,
  "clusters": [
    {
      "id": 0,
      "label": "joule-ai-assistant-configuration",
      "members": [
        {"path": "raw/articles/joule-setup.md", "title": "Joule Setup Guide"},
        ...
      ],
      "top_keywords": ["joule", "configuration", "assistant", "ai"],
      "size": 18
    }
  ]
}
```

### Fallback: Keyword Overlap

If TF-IDF dependencies (scikit-learn) are unavailable, `cluster.py` falls back to keyword overlap matching using only Python stdlib. Less precise but functional.

---

## 13. Two-Pass Compilation (NEW)

For large compile runs (50+ docs), a two-pass strategy dramatically improves quality:

### Pass 1 — Stub Generation (Fast/Sonnet)

- Model: Sonnet (fast, cheap)
- For each document: extract entities, create stub articles with frontmatter + summary + entity list
- No cross-linking, no contradiction detection, no synthesis
- Output: bare wiki articles with `review_status: stub`

### Pass 2 — Synthesis (Opus)

- Model: Opus (high quality)
- Read ALL stubs in a cluster (full context)
- Synthesize cross-references, detect contradictions, write full articles
- Build hierarchical summaries (RAPTOR-style L1/L2)
- Update entity registry

### Why Two Passes?

| | Single Pass | Two Pass |
|---|---|---|
| Quality | Good per-doc | Excellent cross-doc synthesis |
| Speed | Medium | Pass 1 fast, Pass 2 slower |
| Cost | All Opus = expensive | 70% Sonnet + 30% Opus = ~50% cheaper |
| Cross-linking | Limited (per-doc context) | Rich (full cluster context) |

### When to Use

- **Single pass**: < 20 docs, simple entity/factsheet compilation
- **Two pass**: 50+ docs, topics with heavy cross-references, ADR chains

---

## 14. Temporal Coherence & Supersession (NEW)

Knowledge bases with evolving documents (ADRs, versioned specs, policies) need temporal awareness.

### The Problem

ADR-042-v1 (2022) says "use REST". ADR-042-v2 (2024) says "use gRPC". Without temporal coherence, both claims co-exist at equal confidence, confusing queries.

### Supersession Chains

```
adr-042-v1.md (2022) ──superseded_by──► adr-042-v2.md (2024) ──superseded_by──► adr-042-v3.md (2026)
```

### Detection Signals

1. **Explicit**: "This document replaces ADR-042-v1"
2. **Version patterns**: `*-v1.md`, `*-v2.md` with same base
3. **Title matching**: Same title with different dates
4. **Deprecation markers**: "deprecated", "obsolete", "no longer applicable"

### Frontmatter Fields

```yaml
superseded_by: "[[adr-042-v2]]"   # On the older doc
supersedes: "[[adr-042-v1]]"       # On the newer doc
review_status: superseded           # Marks older as non-authoritative
```

### Impact on Queries

- Superseded articles are deprioritized in search results
- Claims from superseded articles get confidence downgrade
- Query responses cite the latest in a chain, noting the evolution

---

## 15. Hybrid Model Strategy (NEW)

Cost optimization without quality sacrifice.

### Routing Rules

| Document Type | Cluster Size | Model | Rationale |
|---|---|---|---|
| Simple entity/factsheet | Any | Sonnet | Extraction-only, no synthesis needed |
| Concept article | < 10 sources | Sonnet | Straightforward compilation |
| Topic with 10+ sources | ≥ 10 | Opus | Complex synthesis across many docs |
| Contradiction resolution | N/A | Opus | Nuanced judgment required |
| Pass 1 (stubs) | Any | Sonnet | Speed over quality for scaffolding |
| Pass 2 (synthesis) | Any | Opus | Quality for final output |
| RAPTOR L2 summaries | N/A | Opus | High-level abstraction needs top model |

### Cost Impact (estimated for 700-doc KB)

- All Opus: ~$45 (700 × ~$0.065/doc average)
- Hybrid: ~$22 (500 Sonnet × $0.01 + 200 Opus × $0.085)
- Savings: ~50% with minimal quality loss on entity/factsheet articles

### Configuration

```json
"compile": {
  "model_strategy": {
    "default": "sonnet",
    "synthesis_model": "opus",
    "opus_threshold_sources": 10,
    "always_opus_for": ["contradiction_resolution", "raptor_l2", "synthesis_pass"]
  }
}
```

---

## 16. Entity Registry Pattern (NEW)

A centralized entity lookup table prevents duplicate articles and enables consistent cross-linking.

### File: `wiki/entity_registry.md`

```markdown
# Entity Registry

| Entity Name | Type | Path | Aliases |
|---|---|---|---|
| SAP Joule | product | wiki/entities/sap-joule.md | Joule, SAP AI Assistant, Joule Copilot |
| ABAP Cloud | technology | wiki/concepts/abap-cloud.md | ABAP RESTful, RAP |
| SAP BTP | platform | wiki/entities/sap-btp.md | Business Technology Platform, BTP |
```

### How It's Used

1. **Before compile**: Load registry, pass to LLM as context
2. **During compile**: LLM checks if entity already exists before creating a new article
3. **After compile**: LLM appends new entities to registry
4. **During query**: Used for alias resolution ("What is BTP?" → reads `sap-btp.md`)

### Deduplication Rules

- If an entity name matches an existing entry's alias → link to existing, don't create new
- If two articles in the same cluster describe the same entity → merge into one
- Registry is the single source of truth for "what articles exist"

---

## 17. RAPTOR-Style Hierarchical Summaries (NEW)

For large wikis (200+ articles), flat search becomes unreliable. RAPTOR-inspired tree summaries enable multi-level retrieval.

### The Tree Structure

```
Level 2 (cluster overview)
  └── Level 1 (sub-topic syntheses, 3-5 articles each)
        └── Level 0 (individual article summaries)
```

### File: `wiki/_cluster_summaries.md`

Contains all L1 and L2 summaries, organized by cluster. The LLM reads this file FIRST during queries, then drills into specific articles.

### Query Strategy with Hierarchical Summaries

1. Read `_cluster_summaries.md` (all L2 overviews)
2. Identify 1-3 relevant clusters
3. Read L1 summaries for those clusters
4. Read full articles cited in relevant L1 sections
5. Synthesize answer

This replaces the naive "search → read top 5 → answer" pattern and dramatically improves recall for cross-cutting queries that span multiple articles.

### When to Build

- Automatically during Pass 2 of two-pass compilation
- Only for clusters with ≥ 8 articles (configurable via `hierarchical_summaries.min_cluster_size_for_tree`)
- Rebuild when > 20% of cluster articles change

---

## 18. Compile Priority Queue (NEW)

Not all documents are equally valuable. Compile high-impact documents first.

### Priority Formula

```
score = (cross_ref_count × 0.5) + (recency × 0.3) + (source_quality × 0.2)
```

### Factors

| Factor | Range | Calculation |
|---|---|---|
| cross_ref_count | 0–1 | How many other raw docs reference this one (normalized) |
| recency | 0–1 | Linear decay: 1.0 for today, 0.0 for >1 year old |
| source_quality | 0–1 | Source type weight from confidence calibration table |

### Impact

- Official documentation + recent + highly-referenced = compiled first
- Old blog posts with no cross-references = compiled last
- Interrupted compiles (via checkpoint) resume from highest-priority remaining

---

## 19. Expanded Contradiction Detection (NEW)

Beyond simple factual negation, detect 5 types of contradictions across full clusters.

### Contradiction Types

| Type | Example | Detection Difficulty |
|---|---|---|
| Factual negation | "X supports Y" vs "X does not support Y" | Easy |
| Numerical inconsistency | "max 100 users" vs "max 50 users" | Medium |
| Temporal conflict | "released 2023" vs "released 2024" | Medium |
| Causal reversal | "A causes B" vs "B causes A" | Hard |
| Conditional contradiction | Both true in isolation, mutually exclusive given constraints | Very Hard |

### Scope

- **Old (limited)**: Scan 3 most-linked articles
- **New (full_cluster)**: Scan ALL articles in the same semantic cluster

### Resolution Strategy

When contradictions are detected:
1. Check temporal ordering — newer source wins if confidence is equal
2. Check source type weights — official doc > blog post
3. If unresolvable → flag both, add to `## Open Questions`
4. If resolvable → mark older/weaker claim as `> **[Superseded]** ...`

---

## 20. Confidence Calibration with Recency Bonus (NEW)

Enhanced confidence scoring that accounts for source age.

### Formula

```
effective_weight = base_weight + recency_bonus
```

Where `recency_bonus = 0.1 × max(0, 1 - (days_old / half_life_days))`

### Example

- Official doc from 2025-01: base=0.95, recency_bonus=0.08 → effective=1.03
- Blog post from 2023-06: base=0.5, recency_bonus=0.0 → effective=0.5

This ensures that a recent official doc definitively outranks an old one, even when both are "official_documentation" type.

### Application

- During compile: set article confidence based on best source's effective weight
- During query: weight claims by effective weight when sources conflict
- During contradiction resolution: effective weight breaks ties

---

## 21. Karpathy-aligned conventions (v3)

The skill was re-aligned in v3 with [Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The gist's core thesis is that **the wiki is the synthesis, the LLM does the bookkeeping, and the schema (CLAUDE.md) is what co-evolves with the user — not a config file.** Five conventions operationalize that thesis without adding RAG machinery:

### Convention A — `## Questions This Page Answers` (compile-time HyDE/HyPE)

Every article carries 5–10 plain-English questions a future reader would phrase. Generated during Pass 2 from the cluster's actual content. Makes the wiki searchable in the user's vocabulary via `grep` and `_index.md`, with zero query-time embedding cost. Tracked in frontmatter as `cq_count: N`.

### Convention B — Inline footnote citations per factual sentence

Every sentence in `## Details` ends with `[^slug]`. Definitions live in `## Sources` at the bottom and resolve to a raw file path, optionally with `§"quoted span"` or line range. One footnote can be reused across many sentences. Renders as hover-cards in Obsidian. Lint check `UNFOOTED_FACTS` flags articles where `unfooted_pct > lint.thresholds.unfooted_pct_max` (default 0.10).

### Convention C — Four-verb revision (strengthen / update / contradict / add)

When a new source touches an existing article, every implied claim is classified into one verb before the body is edited. Verb counts go into `verbs_last_compile` frontmatter and per-article log entries. This is the Mem0-style consolidation step that keeps the wiki *compounding* rather than just *accreting* duplicate facts.

### Convention D — Single-shot self-critique before commit (Step 11.5)

After Pass 2 writes an article, the LLM re-reads it against the cluster sources **once** and fixes three failure modes: hallucinated claims (drop or cite), missing claims (add with citation), weak connections (insert wikilinks). One revision pass, then commit. Bounded Reflexion — ~1.3× Pass 2 tokens, prevents most lint-fix cycles. Sets `<!-- LINT: self_critique_applied=true -->`.

### Convention E — Active gap-filing on query miss (the compounding flywheel)

When a query can't be grounded ≥ 60% in retrieved articles, the LLM does **not** silently fabricate or just refuse. It answers what's grounded, files the user's question to the most relevant existing article's `## Open Questions`, proposes 2–3 ingest sources, and logs the entry with prefix `## [date] query-gap | ...`. Lint surfaces unfiled queries and gap-fills as top-line dashboard metrics — these are the leading indicators of whether the flywheel is turning.

### Why these and not others

The same v3 review considered query-time decomposition, small-to-big chunking, query-time HyDE, GraphRAG community detection, RAGAS dashboards, and token-budget context engineering. All were **declined** as drift toward RAG machinery the gist explicitly avoids. The wiki itself is the synthesis; you don't re-synthesize at query time. The wiki is read in Obsidian, not chunked. The Obsidian graph view is the human's tool for sense-making.

### What lives where (v3 split)

- **`kb.config.json`** (~30 lines) — data only: name, mode, search backend, git on/off, federation peers, lint thresholds.
- **`SKILL.md`** — the skill's universal workflow (Phase 0–12). Reads the config; describes the defaults. Updated once per skill release.
- **KB's `CLAUDE.md`** — the **schema**: KB-specific overrides, domain tags, ingest cadence, tuning journal. Co-evolves with the user, edited freely.

If a knob in this section needs to be tuned for a specific KB, edit that KB's CLAUDE.md — not the global skill, not `kb.config.json`.

---

## 22. Quality-mode additions (v3.1 — no-token-limit edition)

When the user has no cost constraint during wiki creation, the skill switches to **quality mode**: Opus everywhere, plus four compile-time additions that meaningfully raise wiki quality at the price of token spend. These are the right defaults for a one-shot durable artifact; they should NOT be used in always-on auto-compile loops.

### Why Opus on both passes (the cascade re-evaluation)

The original Sonnet-Pass-1 → Opus-Pass-2 cascade was a *cost device*, not a quality device. With no cost constraint, it is strictly worse than Opus-Pass-1 → Opus-Pass-2 because of well-documented weak-to-strong error propagation:

- **Missed claims propagate** — Sonnet's Pass 1 stubs frame the synthesis space. What Sonnet didn't extract, Opus is unlikely to re-discover in Pass 2 unless it re-reads the raw cluster fully (defeating the speedup).
- **Conflated entities propagate** — Sonnet's entity boundaries become Opus's starting vocabulary; cleaner entity resolution in Pass 1 produces a cleaner synthesis.
- **Verb decisions propagate** — strengthen / update / contradict / add classifications made in Pass 1 are inherited by Pass 2.
- **2026 model gap is non-trivial on the relevant tasks** — Opus 4.7 shows ~21% fewer factual errors than Opus 4.6 on enterprise document reasoning ([BenchLM](https://benchlm.ai/compare/claude-opus-4-7-vs-claude-sonnet-4-6)), and the gap to Sonnet 4.6 is wider. Long-context fidelity in the 200K–1M range — exactly where cluster compile lives — favors Opus.

The [SynthKG / Distill-SynthKG (arXiv 2410.16597)](https://arxiv.org/pdf/2410.16597) line of work makes the inverse point: cascade-then-distill works when the *strong model goes first* and produces training data for a smaller model. Cascade-as-speedup in *extraction* is much less supported.

The cascade remains documented as an explicit cost-mode opt-in for users who need it.

### Step 11.6 — Adversarial review pass

Self-critique (Step 11.5) catches its own mistakes but shares the original generation's blind spots. A **separately-prompted critic with no memory of how the article was written** catches a different distribution of errors. Per [MADR (arXiv 2402.07401)](https://arxiv.org/pdf/2402.07401), zero-shot fact explanations have ~80% hallucination rates that fresh-context critics dramatically reduce.

Implementation rules that matter:
- Fresh Opus instance, no shared context with the author
- Three inputs only: article body, cluster raw sources, entity registry
- **No author log entries** in the reviewer's context (biases toward agreement)
- One iteration; never loop (avoids the [confidence escalation effect](https://arxiv.org/html/2505.19184v2))
- Reviewer's findings applied silently — no defense of original choices

### Step 8.5 — Structured contradiction debate

Plain "two LLMs debate" converges on shared bias. The 2025 evidence supports **structured roles** ([PROClaim courtroom pattern, arXiv 2603.28488](https://arxiv.org/html/2603.28488v1)): advocate-A, advocate-B, judge — with the judge held out from author context and receiving only the advocate briefs plus raw sources.

Trigger only when Step 8's deterministic resolution rules fail (temporal tie AND source-weight tie AND debatable contradiction type). Otherwise the rules-based resolution is faster and more reliable. Run one round; multi-round debate amplifies overconfidence on both sides.

### Competency-question test suite (`wiki/_competency_questions.md`)

This is the wiki's executable test file — a living ⟨question, expected substance, status, answering articles⟩ table. After every compile, the LLM runs each CQ through Phase 4 and scores it. Coverage % is the wiki's single highest-information health metric (*"the KB answers 84% of its competency questions"*).

Three sources of CQs:
- **Seed** — written at init from user's topic
- **User** — auto-appended when queries are filed back to `wiki/analyses/`
- **Auto-derived** — every article's `## Questions This Page Answers` becomes a CQ

The user's actual exploration becomes the test suite over time — making the wiki *self-specifying*. This is the ontology-engineering tradition ([Bezerra et al.](https://link.springer.com/chapter/10.1007/978-3-031-77792-9_8); [VSPO 2511.07991](https://arxiv.org/pdf/2511.07991)) adapted to a personal LLM wiki.

### Phase 3.5 — Cross-cluster synthesis

Two-pass + clustering produces excellent intra-cluster synthesis but leaves inter-cluster connections to fire only when wikilinks happen to bridge two clusters. Phase 3.5 is a single global pass over L2 cluster summaries + entity registry + contradiction inventory + topic-article inventory, written to `wiki/topics/_cross-cluster-synthesis.md`.

This is [Microsoft GraphRAG's community sense-making benefit](https://medium.com/@yu-joshua/what-really-matters-to-better-graphrag-implementation-part-1-e02fff773c48) (86% accuracy vs 32% baseline on global queries) done at compile time as a static markdown artifact. Crucially **not** a query-time graph traversal — that's the RAG machinery Karpathy avoids. The synthesis is read at query time only for sense-making queries ("compare across", "big picture", "what's the field doing").

Runs only when ≥3 clusters changed, a new cluster formed, or registry gained ≥10 entries since last run. Skipped in cost/draft mode.

### When NOT to use quality mode

- Daily/auto-compile cycles where cost adds up
- Tiny ingest passes (<5 docs) where the two-pass structure itself is unnecessary
- Live agents where compile latency matters
- KBs with <50 articles where the additional structure is overkill

For those cases, the v3 baseline (single-pass Opus, no Step 8.5/11.6/3.5/CQ-run) is the right default.
