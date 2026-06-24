---
name: llm-knowledge-base
description: Build and maintain a personal LLM-powered knowledge base. Use when the user wants to ingest raw documents (articles, papers, repos, images) into a structured Obsidian-compatible markdown wiki, run Q&A against it, generate visual outputs, or perform health-check linting over the wiki. Also triggers when the user asks a question and a CLAUDE.md or kb.config.json exists nearby — query the wiki first before generating from scratch.
version: 1.0.0
author: Gaurav2409
metadata:
  hermes:
    tags: [Knowledge, Memory, Research, Wiki]
    requires_toolsets: [terminal, file]
---

# LLM Knowledge Base

Build and maintain a **personal knowledge base** powered by an LLM. Raw source documents are compiled by the LLM into an Obsidian-compatible markdown wiki that acts as **long-term agent memory** — once initialized, Claude automatically queries it before answering research questions, without the user needing to specify a path. You rarely edit the wiki directly; the LLM owns it.

## Directory Layout

```
<kb-root>/
├── CLAUDE.md                   # Auto-generated — tells Claude to query this KB
├── kb.config.json              # Knowledge base configuration (v2)
├── cluster_manifest.json       # Output of cluster.py — groups raw docs by topic
├── .compile_checkpoint.json    # Compile progress checkpoint (resume support)
├── raw/                        # Source documents (articles, papers, repos, images, PDFs)
│   ├── articles/
│   ├── papers/
│   ├── images/
│   └── repos/
├── wiki/                       # LLM-compiled wiki (markdown articles)
│   ├── _index.md               # Master index — auto-maintained by LLM
│   ├── _summaries.md           # One-paragraph summary of every raw doc
│   ├── _cluster_summaries.md   # RAPTOR-style hierarchical summaries per cluster
│   ├── entity_registry.md      # Centralized entity lookup (prevents duplicates)
│   ├── log.md                  # Chronological operation log (parseable prefix)
│   ├── concepts/               # Concept articles
│   ├── entities/               # People, orgs, tools, datasets
│   ├── topics/                 # Thematic groupings
│   └── analyses/               # Filed query outputs and derived analyses
├── outputs/                    # Generated outputs (slides, images, reports)
│   ├── slides/                 # Marp markdown slide decks
│   ├── charts/                 # matplotlib Python scripts + PNG outputs
│   ├── reports/                # Long-form markdown reports
│   └── training-data/          # Q&A pairs for fine-tuning
├── scripts/                    # Helper CLI tools
│   ├── ingest.py               # Ingest a new raw document or directory
│   ├── compile.py              # Orchestrate compilation (clustering, batching, checkpoints)
│   ├── cluster.py              # Semantic pre-clustering of raw docs
│   ├── query.py                # Q&A against the wiki
│   ├── lint.py                 # Health-check the wiki (incl. temporal/registry checks)
│   └── search.py               # Full-text search over the wiki
└── .gitignore
```

---

## Phase 0: Understand the Request

Before doing anything, determine which operation the user wants:

| Operation | Trigger keywords |
|-----------|-----------------|
| **Init** | "create", "initialize", "start", "new knowledge base" |
| **Ingest** | "add", "ingest", "index", "import" + a file/URL/directory path |
| **Compile** | "compile", "update wiki", "refresh", "rebuild" |
| **Query** | "ask", "what is", "summarize", "find", "explain", "compare", "what do you know about", "look it up", "check the KB" |
| **Output** | "generate", "create slides", "make a chart", "write a report" |
| **Lint** | "lint", "health check", "find gaps", "fix inconsistencies" |
| **Search** | "search for", "find articles about" |
| **Log** | "show log", "what did we do", "history", "recent changes", "activity" |
| **Git** | "commit", "save version", "checkpoint" |
| **Federation** | "check other KB", "ask sister KB", "multi-KB query" |
| **Export** | "export training data", "generate Q&A pairs", "fine-tuning data" |
| **Image** | "download images", "process images", "vision pass" |

**Auto-query check:** If a `kb.config.json` or `CLAUDE.md` (with KB reference) exists in the current directory or a nearby parent, and the user asks a research question, go to Phase 4 (Query) automatically before answering.

If the operation is ambiguous, ask:

> "What would you like to do with your knowledge base?
> - **Init**: Create a new knowledge base
> - **Ingest**: Add source documents (file, URL, or directory)
> - **Compile**: Update the wiki from raw sources
> - **Query**: Ask a question against the wiki
> - **Output**: Generate slides, charts, or a report
> - **Lint**: Health-check the wiki"

---

## Phase 1: Init — Create a New Knowledge Base

### 1a. Confirm location

Ask the user:
> "Where should the knowledge base be created? Provide a directory path (e.g. `~/research/ai-safety-kb`)."

### 1b. Scaffold structure

```bash
KB_ROOT=<path-from-user>
mkdir -p "$KB_ROOT"/{raw/{articles,papers,images,repos},wiki/{concepts,entities,topics,analyses},outputs/{slides,charts,reports,training-data},scripts}
```

### 1c. Copy helper scripts from the skill templates

```bash
SKILL_PATH=$(find . -type d -name "llm-knowledge-base" -path "*/skills/*" 2>/dev/null | head -1)
cp "$SKILL_PATH/templates/scripts/"*.py "$KB_ROOT/scripts/"
```

### 1d. Create `kb.config.json` (data-only — workflow lives in CLAUDE.md)

Keep the config minimal. Per Karpathy's gist, *the schema (CLAUDE.md) is what co-evolves with the user, not a config file.* Workflow knobs (model routing, two-pass, clustering, contradiction sensitivity, source weights) belong in prose the LLM reads — they are **defaults the skill follows**, documented in this SKILL.md and copied into the KB's CLAUDE.md. The config file is just data: paths, the mode toggle, the search backend choice, git on/off, federation peers.

```json
{
  "name": "<kb-name>",
  "mode": "recall",
  "version": "3.0",

  "wiki": {
    "split_index_at": 80
  },

  "search": {
    "backend": "naive",
    "qmd": {
      "mcp_http": false,
      "mcp_port": 8181
    }
  },

  "lint": {
    "thresholds": {
      "stub_words": 120,
      "stale_days": 180,
      "open_questions_max": 5,
      "confidence_low_pct": 0.20,
      "unfooted_pct_max": 0.10
    }
  },

  "git": {
    "enabled": true,
    "auto_commit": true
  },

  "federation": {
    "enabled": false,
    "peers": []
  }
}
```

**Modes:**
- `"recall"` (default) — include all claims; mark speculative ones inline with `> **[Inferred]**`. Auto-file query outputs to `wiki/analyses/`.
- `"precision"` — skip `confidence: low` claims during compile; require explicit confirmation before filing query outputs; raise `search.precision_score_threshold` to 0.6 if using qmd.

### 1j. Schema defaults (the workflow knobs that *used* to be in config)

These are defaults the LLM follows when compiling, querying, and linting. They are described here once and copied verbatim into the KB's CLAUDE.md so the user can tune them per-KB. **Treat each as a sensible default, not a hard rule.**

**Model routing (default: quality mode)** — Use **Opus for every compile step**: Pass 1 extraction, Pass 2 synthesis, contradiction resolution, RAPTOR L2 summaries, self-critique, adversarial review. The cascade from Sonnet → Opus is a *cost optimization*, not a quality device, and the 2025 weak-to-strong literature shows the strong model inherits the weak model's missed claims, conflated entities, and verb decisions rather than re-discovering them in Pass 2. With Opus 4.7's measured advantages on multi-source synthesis (~21% fewer factual errors than Opus 4.6 on enterprise document reasoning) and long-context fidelity in the 200K–1M range, the marginal token spend pays off in fewer lint cycles and lower revision rates over the life of the wiki. Wiki creation is a one-shot durable artifact — favor quality.

**Model routing (opt-in: cost mode)** — When the user explicitly says "compile cheap", sets `mode: "draft"`, or signals a cost constraint, fall back to the cascade: Sonnet for entity articles, concept articles with <10 sources, Pass 1 stubs, routine lint fixes; Opus for topic articles, any article synthesizing 10+ sources, Pass 2 synthesis, contradiction resolution, RAPTOR L2, self-critique, adversarial review. Document this fallback in the KB's CLAUDE.md if it becomes the standing default for a given KB.

**Two-pass compile** — When the pending queue has 15+ documents, cluster them first (Phase 3-pre Step 0a) then run two passes. In *quality mode* both passes use Opus — the two-pass *structure* still earns its keep (Pass 1 isolates extraction from synthesis so Pass 2 sees coherent stubs, not raw clusters; Pass 2 sees the full cluster's stubs together for cross-doc reasoning), independently of which model runs each pass. Below 15 documents, single-pass Opus is fine.

**Clustering** — TF-IDF + agglomerative (Ward linkage) targeting 15–25 docs per cluster; fall back to keyword-overlap if scikit-learn is unavailable. Cluster manifest at `cluster_manifest.json`.

**Batching & checkpoints** — Process 20 docs per batch. After each batch write progress to `.compile_checkpoint.json`. On interruption, resume from the checkpoint.

**Priority queue** — Within a batch, order by `0.5 × cross_reference_count + 0.3 × recency + 0.2 × source_quality`. Compile high-impact docs first so downstream articles can link to them.

**Entity registry** — Maintain `wiki/entity_registry.md` as the canonical lookup. Feed it to every compile call. Append after creating any new entity. Deduplicate on alias.

**Temporal coherence** — Detect supersession via the signals: `replaces`, `supersedes`, `deprecates`, `updates`, `superseded by`, `obsoletes`, `revision of`, `v2`, `v3`, identical title with later date, same ADR-N base with version suffix. Chain via `superseded_by` / `supersedes` frontmatter fields; mark older as `review_status: superseded`; downgrade old conflicting claims by one confidence level.

**Contradiction detection** — Scope = full cluster (not just top-3-linked). Types to detect: factual negation, numerical inconsistency, temporal conflict, causal reversal, conditional contradiction. Resolution priority: newer source > higher source-type weight > flag both in `## Open Questions` if unresolvable.

**Source-type weights** (used for confidence scoring; recency bonus up to +0.1, half-life 365 days):

| Source type | Weight |
|---|---|
| peer-reviewed | 1.0 |
| official documentation | 0.95 |
| internal ADR | 0.9 |
| internal design doc | 0.85 |
| news article | 0.7 |
| tutorial | 0.65 |
| blog post | 0.5 |
| community forum | 0.4 |
| social media | 0.3 |
| inferred | 0.2 |

**Connection density target** — At least 3 wikilinks per article. Auto-insert during compile when below target.

**Cross-references** — Bidirectional. Cap at 30 wikilinks per article to keep pages readable.

**Hierarchical (RAPTOR) summaries** — Build for clusters with 8+ articles. Three levels: L0 article summaries, L1 sub-group syntheses (3–5 articles each), L2 single-paragraph cluster overview. Rebuild when >20% of cluster articles change.

**Output default** — In `recall` mode, file query outputs back to `wiki/analyses/` automatically. In `precision` mode, ask first.

**Article subdirectories** — `wiki/concepts/`, `wiki/entities/`, `wiki/topics/`, `wiki/analyses/`.

**Log retention** — Keep last 1000 entries in `wiki/log.md`. Older entries archive to `wiki/log-archive-YYYY.md`.

**Tuning policy** — If any default doesn't fit a KB's domain, the user (with the LLM) edits the KB's CLAUDE.md to override it. Don't add a config flag.

### 1e. Bootstrap `wiki/_index.md`

> **CRITICAL — Obsidian graph rule:** Every article entry in `_index.md` MUST use `[[wikilink|Display Name]]` syntax, NOT markdown `[text](path)` links. Obsidian's graph view only draws edges from `[[wikilinks]]`. Using markdown links makes every article appear as a disconnected node in the graph. This applies to both the section lists and the All Articles table.

```markdown
# Knowledge Base Index

> Auto-maintained by LLM. Do not edit manually.
> IMPORTANT: All article links MUST use [[wikilink|Display Name]] syntax. Never use [text](path) markdown links here.

## Concepts
<!-- auto-populated — format: - [[article-slug|Display Name]] — one-line description -->

## Entities
<!-- auto-populated — format: - [[article-slug|Display Name]] — one-line description -->

## Topics
<!-- auto-populated — format: - [[article-slug|Display Name]] — one-line description -->

## Analyses
<!-- auto-populated — format: - [[article-slug|Display Name]] — one-line description -->

## All Articles

| Article | Type | Confidence | Last Updated |
|---------|------|-----------|--------------|
<!-- auto-populated — format: | [[article-slug\|Display Name]] | concept/entity/topic | high/medium/low | YYYY-MM-DD | -->
```

### 1f. Bootstrap `wiki/_summaries.md`

```markdown
# Document Summaries

> One-paragraph summary of every document in raw/. Auto-maintained by LLM.

<!-- auto-populated -->
```

### 1g. Bootstrap `wiki/log.md`

```markdown
# Knowledge Base Log

> Auto-maintained. Each entry uses a parseable prefix: `## [YYYY-MM-DD] operation | title`
> Grep pattern for all entries: `grep "^## \[20" wiki/log.md`
> Grep by operation: `grep "^## \[20.*\] compile" wiki/log.md`

<!-- entries appended below -->

## [<ISO date>] init | <kb-name>
- KB initialized at: <absolute-path>
- Mode: <mode>
- Topic: <topic>
```

### 1g-bis. Bootstrap `wiki/_competency_questions.md`

The competency-question suite is the KB's **executable test file** — a living list of questions the KB *should be able to answer*. Each question carries an expected substance (what a good answer must contain), a status, and the article(s) that currently answer it. After every compile, the LLM runs each question through Phase 4 and scores whether the wiki's answer matches. Coverage % becomes a top-line health metric — *"the KB answers 84% of its competency questions"* is a far more meaningful signal than article count.

This pattern is the ontology-engineering tradition ([Bezerra et al., CQs as test cases](https://link.springer.com/chapter/10.1007/978-3-031-77792-9_8); [VSPO arXiv 2511.07991](https://arxiv.org/pdf/2511.07991)) adapted to a personal LLM wiki.

```markdown
# Competency Questions

> Auto-maintained. The KB should be able to answer every question below.
> Run via `python scripts/lint.py --kb-root . --run-cqs` (or by query phase).
>
> Status legend:
>   ✓ passing       — wiki answer matches expected substance
>   ⚠ partial       — wiki answers part but misses key substance
>   ✗ failing       — wiki cannot answer; gap exists
>   — unrun         — not yet evaluated this compile cycle
>
> Coverage target: 90% passing. Failing questions auto-promote to ingest candidates.

## Seed questions

<!-- The LLM seeds this list during init from the user's stated topic.
     Each entry has: question | expected substance (1-2 sentences) | status | answering articles -->

- [ ] **What is <core topic>?**
  - *Expected*: <core definition with 2-3 distinguishing properties>
  - *Status*: —
  - *Answered by*: <none yet>

## User questions (from queries)

<!-- Appended by Phase 4 §4f when the user files an analysis.
     The original query becomes a CQ; its expected substance is the analysis answer. -->

## Auto-derived questions (from compile)

<!-- Appended during Step 4-bis. Each article's "## Questions This Page Answers"
     becomes a CQ here, with the article itself as the expected answer source. -->
```

The file's three sections have distinct ownership:
- **Seed questions** — written at init from the user's topic; edited by the user over time as scope clarifies
- **User questions** — appended automatically when a query is filed back to `wiki/analyses/` (§4f) or when a gap-fill is logged (§4e-bis). The user's actual exploration becomes the test suite.
- **Auto-derived questions** — appended during Step 4-bis. Every article's `## Questions This Page Answers` flows into here so coverage is computable. The expected substance for these is *"a coherent answer from the named article"*.

Run cadence: full CQ suite runs as part of every `lint` operation. Individual CQs re-run during query phase to verify the relevant ones still pass after a compile.

### 1h. Bootstrap `.gitignore`

```
outputs/charts/*.png
__pycache__/
*.pyc
.DS_Store
scripts/__pycache__/
```

If `git.enabled` is true:
```bash
cd <kb-root>
git init
git add .
git commit -m "kb: init — <kb-name>"
```

### 1i. Create `.obsidian/app.json` — Obsidian vault scope

**REQUIRED.** Without this file, Obsidian scans `raw/`, `outputs/`, and `scripts/` and renders every raw source file as a node in the graph view — resulting in dozens of disconnected nodes from files that are not wiki articles.

Create `.obsidian/app.json` in `<kb-root>`:

```json
{
  "userIgnoreFilters": [
    "raw/",
    "outputs/",
    "scripts/",
    "kb.config.json",
    ".gitignore"
  ]
}
```

This restricts Obsidian's graph, search, and link resolution to the `wiki/` directory only. Without it the graph is unreadable on any KB with more than ~10 raw sources.

### 1k. Set up qmd collection (if `search.backend == "qmd"`)

```bash
npm install -g @tobilu/qmd   # one-time global install
qmd collection add wiki/ --name <collection_name>
qmd context add qmd://<collection_name> "Wiki for <kb-name>: <topic>"
```

### 1l. Write `CLAUDE.md` — **the schema** (this is what co-evolves with the user)

Per Karpathy's gist, the CLAUDE.md (a.k.a. AGENTS.md) inside the KB **is the schema**: it tells the LLM how this specific wiki is structured, what conventions to follow, and what workflow defaults apply. It is intentionally rich — far richer than the slim `kb.config.json` — because it's prose the LLM reads and the user edits. **This file is the load-bearing artifact for KB-specific tuning, not the config.**

Write the following starter template into `<kb-root>/CLAUDE.md`. The user (with the LLM) will edit it over time to fit their domain.

```markdown
# Knowledge Base: <kb-name>

This directory is an LLM knowledge base managed by the llm-knowledge-base skill.
The wiki/ directory is the accumulated synthesis. Raw sources in raw/ are
immutable. The LLM owns wiki/ entirely — humans read it; the LLM writes it.

- **Topic**: <topic>
- **Mode**: <recall | precision>
- **Config (data only)**: kb.config.json
- **Wiki index**: wiki/_index.md
- **Activity log**: wiki/log.md

## When to query this KB

Whenever the user asks a research question, says "query", "what do you know about",
"check the KB", "look it up", or asks anything in the topic area above — use the
llm-knowledge-base skill to query this wiki BEFORE generating an answer from
scratch. The wiki is the accumulated source of truth.

To query: read wiki/_cluster_summaries.md (if present) and wiki/_index.md, search
for relevant articles, read them, follow [[wikilinks]] one hop for transitive
knowledge, then synthesize with inline citations.

## Conventions this KB follows

### Article structure
Every article has: `## Summary` → `## Questions This Page Answers` →
`## Details` → `## Connections` → `## Open Questions` → `## Sources`.
The `## Questions` section lists 5–10 questions a future reader would phrase —
this is what makes the wiki searchable in plain English without embedding
infrastructure.

### Citation convention
Every factual sentence in `## Details` ends with an inline footnote `[^slug]`.
Footnote definitions live in `## Sources` at the bottom and resolve to a raw
file path, optionally with `§"quoted span"` or line range.

Example: `SAP Joule launched in late 2023 [^joule-launch].`

This replaces opaque `claim_count` counters with provenance a human can verify
in Obsidian (footnotes render as hover-cards) and lint can check programmatically.

### Pass 2 verbs (how the LLM revises existing pages)
When a new source touches an existing article, every implied claim falls under
one of four verbs:
- **strengthen** — same claim, new corroborating source → append footnote, raise confidence if applicable
- **update** — claim has changed → replace text, mark prior as `> **[Superseded by [^new]]** <old>`, footnote both
- **contradict** — irreconcilable → keep both, append conflict to `## Open Questions`, flag `review_status: flagged-contradiction`
- **add** — genuinely new claim → append with footnote

Verb counts go into per-article frontmatter (`verbs_last_compile`) and the
compile log entry.

### Self-critique before commit
After writing or updating an article, re-read it against the cluster sources
**one** more time. Check: (1) hallucinated claims (drop or cite), (2) missing
claims (add with citation), (3) weak connections (add wikilinks to meet density
target). Apply one revision pass, then commit. Do not loop. Set
`<!-- LINT: self_critique_applied=true -->`.

### Ingest cadence
<TODO — user fills in>: prefer one-at-a-time with discussion, or batch ingest
with less supervision? Default: one-at-a-time for the first 20 sources, then
batch as patterns stabilize.

### Article naming
- Concepts: `lowercase-kebab.md` (e.g. `attention-mechanism.md`)
- Entities: `firstname-lastname.md` / `org-name.md` / `tool-name-version.md`
- Topics: `topic-name.md`
- Analyses (filed queries): `query-slug-YYYY-MM.md`

### Workflow defaults (override here, not in kb.config.json)
- Model routing: Opus for 10+ sources, contradictions, Pass 2 synthesis, self-critique. Sonnet otherwise.
- Two-pass compile triggered when 15+ docs are pending.
- Cluster size target: 15–25 docs.
- Connection density target: 3+ wikilinks per article.
- Contradiction scope: full cluster.
- Hierarchical (RAPTOR) summaries built for clusters ≥ 8 articles.

### Active gap-filing on query miss
When a query can't be grounded ≥ 60% in retrieved articles, do **not** silently
fabricate. Answer what's grounded, file the user's question as an
`## Open Questions` entry on the closest existing article, propose 2–3 ingest
sources, and log the entry with prefix `## [date] query-gap | ...`. The lint
dashboard tracks unfiled queries and gap-fills as the leading indicators of
the compounding flywheel.

## Domain-specific tags & entity types

<TODO — user fills in over time. Example for a SAP KB:
- tags: `btp`, `joule`, `abap-cloud`, `integration`, `analytics`, `ai-foundation`
- entity_types: `sap-product`, `bapi`, `cds-view`, `cap-service`
- preferred source types: SAP Help Portal (official_documentation), SAP TechEd talks (official_documentation), community blogs on community.sap.com (community_forum)
>

## Tuning notes (append over time)

<This is the running journal where you and the LLM record what's working and
what isn't. Examples:
- "2025-04-10: For ABAP-related ingests, prefer extracting code examples into
  fenced ``` blocks with the file:line origin in the language tag."
- "2025-05-02: Switched contradiction sensitivity to high after missing two
  spec conflicts in cluster-007."
>
```

Then ask the user:
> "Would you like me to also register this KB in your global `~/.claude/CLAUDE.md`? This lets Claude discover it from any working directory."

If yes, append to `~/.claude/CLAUDE.md`:

```markdown

## Knowledge Base: <kb-name>
- **Root**: <absolute-path>
- **Topic**: <topic>
- When the user asks research questions related to <topic>, query this KB first using the llm-knowledge-base skill.
```

Confirm to the user:
> "Knowledge base initialized at `<path>`. Claude will now automatically query it when you ask research questions. Add source documents to `raw/` then run compile to build the wiki."

---

## Phase 2: Ingest — Add Source Documents

### 2a. Identify the source

The user provides one of:
- A **local file path**
- A **directory path** (batch ingest all files inside)
- A **URL** (web article, paper, repo)
- A **pasted text block**

### 2b. For directory paths — batch ingest

If the source is a directory:
```bash
find "<source-dir>" -type f | sort
```
Collect all files with supported extensions (`.md`, `.txt`, `.html`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`). Report:
> "Found N files in `<path>` — ingesting: [list]. Starting batch compile..."

Process each file through steps 2c–2f below. After all are done, compile once (not once per file, to avoid redundant index rewrites).

### 2c. For URLs — convert to markdown

> **REQUIRED — Raw file must exist on disk before compiling.** When ingesting from a URL (via WebFetch), you MUST write the raw markdown content to a file in `raw/articles/web-sources/<slug>.md` BEFORE running compile. The raw file is the source of truth: wiki article frontmatter cites it, and lint verifies it exists. If the raw file is missing, lint will report 100% of web-sourced articles as having broken source paths.

Steps for URL ingestion:
1. Fetch the URL content using WebFetch
2. Write the content to `raw/articles/web-sources/<slug>.md` (use `raw/articles/web-sources/` for external web articles to keep them separate from local/internal content)
3. Add a header block at the top: `# <Title>\n\nSource: <url>\nOriginally published: <date-if-known>`
4. Proceed to compile

If the URL is unavailable (404, paywall, redirect), reconstruct the content from the document's title/summary/known facts and still write it to `raw/articles/web-sources/<slug>.md` — mark it with `> Note: Content reconstructed from summaries — original URL unavailable.`

Alternatively, use the **Obsidian Web Clipper** browser extension to save the page as a `.md` file directly into `raw/articles/`, or use `scripts/ingest.py`:

```bash
python scripts/ingest.py --url "<url>" --type article
```

### 2d. For local files — copy to raw/

| Extension | Directory |
|-----------|-----------|
| `.md`, `.txt`, `.html`, `.htm` | `raw/articles/` |
| `.pdf` | `raw/papers/` |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg` | `raw/images/` |
| Directory or `.zip` | `raw/repos/` |
| Other | `raw/articles/` |

```bash
cp "<source>" "$KB_ROOT/raw/<subdir>/<filename>"
```

### 2e. Quality filter check

Before processing, apply `ingest.quality_filter` rules:
- Skip files matching any pattern in `skip_patterns` (e.g. `draft-*`, `temp-*`)
- If `duplicate_detection` is true: check `_summaries.md` for an existing entry with the same filename or source URL — skip if found
- If `min_word_count > 0`: skip text files below the threshold (report as skipped, not error)

### 2f. Append log entry

```
## [YYYY-MM-DD] ingest | <filename-or-url-title>
- Source: raw/<subdir>/<filename>
- Type: <article|paper|image|repo>
- Auto-compile: <true|false>
```

### 2g. Auto-compile

If `ingest.auto_compile` is `true`, proceed immediately to Phase 3 (Compile).

---

## Phase 3: Compile — Update the Wiki

> **SYNTHESIS PRINCIPLE:** A wiki article represents a **concept, entity, or topic** — not a raw file.
> - One raw file may contribute to multiple wiki articles (if it covers several concepts)
> - Multiple raw files may contribute to one wiki article (if they all cover the same concept)
> - The number of wiki articles is determined by the semantic content, not by the number of raw files
> - What matters is correct topic distribution: every distinct concept/entity/topic gets its own article, duplicates are merged, and every raw file's knowledge is captured somewhere

This is the core LLM operation. Read clusters of raw documents and write synthesized wiki articles.

### 3-pre. Pre-compile Setup (NEW — run before 3a)

**Step 0a — Semantic Pre-Clustering**

If `compile.clustering.enabled` is true and there are 15+ pending documents:

```bash
python scripts/cluster.py --kb-root .
```

This groups pending raw docs into topically coherent clusters of 10-25 documents. The cluster manifest (`scripts/clusters.json`) drives the batch order and enables cross-document synthesis within each cluster. The LLM processes one cluster at a time, giving it topical context for better wikilink generation and contradiction detection.

**Step 0b — Model Strategy Selection**

Per §1j, the default is **quality mode: Opus on every step.** Wiki creation is a one-shot durable artifact; the Sonnet-then-Opus cascade saves cost but imports Sonnet's missed claims, conflated entities, and verb decisions into Pass 2 (well-documented weak-to-strong error propagation). Use the cascade only when the user has explicitly opted into cost mode (`mode: "draft"` or "compile cheap"); in that case the rules are:

- **Sonnet (cost mode only):** Entity articles, concept articles with < 10 sources, Pass 1 stubs, routine lint fixes
- **Opus (always in quality mode; selectively in cost mode):** Topic articles, any article synthesizing 10+ sources, Pass 2 synthesis, contradiction resolution, Step 8.5 debate, RAPTOR L2 summaries, Step 11.5 self-critique, Step 11.6 adversarial review, analysis articles, cross-cluster synthesis (Phase 3.5)

In Claude Code: in quality mode run the entire compile with `--model opus`. In cost mode, switch `--model` between batches per the rules above (or let the skill route automatically if your harness supports per-call model selection).

**Step 0c — Two-Pass Compile Strategy**

If `compile.two_pass.enabled` is true:
- **Pass 1 (Opus by default; Sonnet only in cost mode):** For each raw doc in the cluster, create stub articles with: title, type, entity extraction, key claims list, initial wikilinks.
- **Pass 2 (Opus, always):** Read ALL stubs in the cluster together + the entity registry. Perform synthesis: merge related stubs, write full `## Details` sections, detect contradictions across the cluster, assign final confidence scores, and generate the `## Open Questions` that connect articles.

The two-pass *structure* is a quality device (Pass 1 isolates extraction from synthesis; Pass 2 sees the full cluster context), independent of which model runs each pass.

**Step 0d — Compile Batching & Checkpointing**

If `compile.batching.enabled` is true:
1. Group pending docs by cluster (from `scripts/clusters.json`)
2. Within each cluster, order by priority score (see §Priority Queue below)
3. Process in batches of `compile.batching.batch_size` (default: 20)
4. After each batch, write progress to `compile.batching.checkpoint_file`:
   ```json
   {
     "started": "2025-05-02T15:00:00Z",
     "last_batch_completed": "2025-05-02T15:30:00Z",
     "current_cluster": "cluster-003",
     "docs_completed": ["raw/articles/foo.md", ...],
     "docs_remaining": ["raw/articles/bar.md", ...],
     "articles_created": 45,
     "articles_updated": 12,
     "errors": []
   }
   ```
5. If a compile run is interrupted, the next `compile` command reads the checkpoint and resumes from where it left off (skipping already-completed docs).

**Step 0e — Priority Queue**

If `compile.priority_queue.enabled` is true, order documents within each batch by priority score:
- `cross_reference_count` (0.5 weight): How many other pending docs reference this one? Compile high-reference docs first so downstream articles can link to them.
- `recency` (0.3 weight): More recent docs first (for temporal coherence — newer docs may supersede older ones).
- `source_quality` (0.2 weight): Higher-quality source types first (official docs before blog posts).

**Step 0f — Load Entity Registry**

If `compile.entity_registry.enabled` is true:
```bash
cat wiki/entity_registry.md
```

Feed the entity registry to every compile call. This ensures consistent entity naming, prevents duplicate articles, and provides context for cross-linking. The registry format:

```markdown
# Entity Registry
> Auto-maintained. Maps entity names to their wiki article paths.

| Entity | Type | Article Path | Aliases |
|--------|------|-------------|---------|
| SAP Joule | tool | entities/sap-joule | Joule, SAP AI Copilot |
| ABAP Cloud | concept | concepts/abap-cloud | ABAP RESTful, RAP |
```

### 3a. Read the current wiki state

```bash
cat wiki/_index.md
cat wiki/_summaries.md
cat wiki/entity_registry.md    # NEW — feed to compile context
```

Also list all existing wiki articles:
```bash
find wiki/ -name "*.md" ! -name "_*" | sort
```

### 3b. Identify new or changed raw documents

```bash
python scripts/compile.py --kb-root .
```

The script compares `raw/` filenames against `_summaries.md` entries. Files not yet summarized are new. Also flag files whose raw content modification time is newer than their `last_updated` frontmatter date in the wiki.

If clustering is enabled and `scripts/clusters.json` exists, also report which cluster each pending doc belongs to.

### 3c. SYNTHESIS LOOP — For each cluster, identify concepts/entities/topics and write articles

> **The unit of compilation is a concept/entity/topic — not a raw file.**
> Read a cluster of related docs, identify all distinct concepts/entities/topics within them, and write one well-structured article per distinct concept. A single raw file may spawn multiple articles (if it covers multiple topics); multiple raw files may merge into one article (if they all cover the same topic). Let semantic content determine the article count — do not impose a ratio.

---

**Step 1 — Read the entire cluster**

Read ALL raw files in the current cluster before writing anything:

```bash
cat "<raw-file-1>"
cat "<raw-file-2>"
# ... all files in this cluster
```

Hold them all in context. Do not write any article yet.

**Step 2 — Map concepts/entities/topics across the cluster**

After reading all files, identify every distinct thing worth an article:
- **Named things** (specific services, tools, components, people) → `wiki/entities/`
- **Ideas, patterns, mechanisms** (streaming architecture, multi-tenancy, auth patterns) → `wiki/concepts/`
- **Thematic overviews** spanning multiple entities/concepts → `wiki/topics/`

Then apply **entity resolution**: check `wiki/entity_registry.md` and existing `wiki/` for anything already covered. If a concept already has an article, plan to update it — do not create a duplicate.

**Step 3 — Quality filter**

Apply `ingest.quality_filter` checks. Skip files below `min_word_count`. Log skipped files.

**Step 4 — Write or update each article**

For each identified concept/entity/topic:

1. If the article already exists: UPDATE it — merge new information into `## Details`, append footnote definitions to `## Sources`, regenerate `## Questions This Page Answers` if the new content meaningfully expands scope.
2. If it's new: create it using the article template (§3d). Every article must have:
   - `stub: false` — fully written, minimum 400 words
   - **Every factual sentence ending with a `[^src1]` footnote** that resolves to a definition in `## Sources` pointing to the raw file
   - At least 3 `[[wikilinks]]` to related articles
   - A `## Questions This Page Answers` section with 5–10 questions a future reader would phrase (see Step 4-bis below)
   - Rich `## Details` with subheadings covering all key content from contributing files

**Step 4-bis — Generate "Questions This Page Answers"**

Before committing the article, derive 5–10 plain-English questions the page can answer. Source them from the cluster's actual content, not from a generic template. Phrase them the way a future reader would search:

- Mix factual recall (*"What is X?"*), comparison (*"How does X differ from Y?"*), application (*"When would you use X?"*), and limitation (*"What are the failure modes of X?"*).
- Avoid yes/no questions.
- One question per likely retrieval intent — if two questions would land a reader on the same paragraph, merge them.

This section is the compile-time equivalent of HyDE/HyPE — it makes the page discoverable in the user's own vocabulary via `_index.md` and `grep`, with zero query-time embedding cost. Update `cq_count` in frontmatter to match the bullet count.

**Step 5 — Mark ALL contributing raw files as compiled in _summaries.md**

After writing articles for this cluster, add a `_summaries.md` entry for EVERY raw file processed — even if it contributed to an existing article rather than creating a new one:

```
**<raw-filename.md>** — <one-sentence description. Compiled into: [[article-slug]].>
```

This is how `compile.py` knows a file has been processed. A file that contributed to 3 different articles gets one summary entry pointing to all 3.

**Step 6 — Assign confidence**

Based on source type (per the weights table in §1j) and number of corroborating sources:

- `high` — peer-reviewed paper, or claim appears in 3+ independent sources, or best source weight ≥ 0.9 with recency bonus
- `medium` — single credible source (news, official docs without corroboration), or two sources totaling ≥ 1.0
- `low` — single blog post, inferred connection, social media, or weight < 0.5

In `"mode": "precision"`: skip claims with `confidence: low` entirely; mark article `review_status: needs-review` if any source weight < 0.5.

In `"mode": "recall"`: include all claims; mark speculative content inline:
> **[Inferred]** <speculative claim>

**Step 7 — Decide the verb (per-claim revision)**

When a new source touches an article that already exists, every claim it implies belongs to one of four verbs. Decide the verb explicitly before editing the body — this is what keeps the wiki *compounding* rather than just accreting:

| Verb | Trigger | Action |
|---|---|---|
| **strengthen** | New source asserts the same claim that's already on the page | Append the new footnote alongside the existing one on the affected sentence(s). If confidence was `medium` and now there are 3+ independent sources, promote to `high`. |
| **update** | Claim has changed (newer facts, corrected numbers, version bump) | Replace the sentence. Mark the prior version inline: `> **[Superseded by [^new-src]]** <old text>`. Footnote both old and new. |
| **contradict** | New source asserts a claim irreconcilable with what's on the page (and not just an update) | Keep both claims. Append the conflict to `## Open Questions` with both footnotes. Set `review_status: flagged-contradiction`. Apply Step 8 (contradiction scan) rules to pick a winner only if resolvable by recency + source weight. |
| **add** | Genuinely new claim not previously on the page | Append a new sentence in the appropriate subsection with its footnote. |

After processing all claims from new sources for this article, record the verb counts in frontmatter:

```yaml
verbs_last_compile: {strengthen: 4, update: 1, contradict: 0, add: 7}
```

And in the per-article log entry (Step 11). The verb log is what a future maintainer reads to understand *what changed* about a page, not just *that it changed*.

**Step 8 — Expanded Contradiction Scan (IMPROVED)**

After writing/updating an article, cross-check its factual claims against **ALL articles in the same cluster** (not just 3 most-linked). If `compile.contradiction_detection.scope` is `"full_cluster"`, the scan covers every article in the current compile batch/cluster.

Contradiction types to detect (from `compile.contradiction_detection.types`):
- **factual_negation**: X is Y vs X is not Y
- **numerical_inconsistency**: "supports 100 users" vs "supports 50 users"
- **temporal_conflict**: "released in 2023" vs "released in 2024" (check which is superseded)
- **causal_reversal**: "A causes B" vs "B causes A"
- **conditional_contradiction**: Two claims that are both true in isolation but mutually exclusive given a third constraint (per RAPTOR research)

If a contradiction is found:
- Add `<!-- LINT: contradiction_flag=true -->` at the bottom of both articles
- Set `review_status: flagged-contradiction` in frontmatter
- Note the contradiction explicitly in the `## Open Questions` section with both claims cited
- If one source is newer AND has higher confidence weight, mark the older claim as `> **[Superseded]** ...`

Sensitivity levels (from `compile.contradiction_detection.sensitivity`):
- `low`: only factual_negation
- `medium`: factual_negation + numerical_inconsistency + temporal_conflict
- `high`: all types including conditional_contradiction

**Step 8.5 — Structured contradiction debate (quality mode, irreconcilable only)**

For each contradiction Step 8 flagged that the resolution rules *could not* break (temporal ordering inconclusive AND source-type weights tied AND recency bonuses near-equal), run a structured 3-role debate before falling back to "flag both in Open Questions". This is **not** unstructured chat between two Opus instances — that escalates confidence on both sides and converges to bias ([When Two LLMs Debate, Both Think They'll Win, arXiv 2505.19184](https://arxiv.org/html/2505.19184v2)). It is courtroom-style with explicit roles ([PROClaim, arXiv 2603.28488](https://arxiv.org/html/2603.28488v1); [MADR, arXiv 2402.07401](https://arxiv.org/pdf/2402.07401)).

Trigger conditions (all must hold):
- Step 8 detected a contradiction
- Temporal resolution failed (dates unknown, equal, or within 30 days)
- Source-weight resolution failed (both sources within 0.1 weight)
- The contradiction is `factual_negation`, `numerical_inconsistency`, or `conditional_contradiction` (skip debate for `causal_reversal` and `temporal_conflict` — those need human review, not more LLM reasoning)

Three roles, three fresh Opus instances:

| Role | Inputs | Prompt frame |
|---|---|---|
| **Advocate-A** | Source A + cluster sources that support A | *"Build the strongest case that A is correct. Quote evidence. Identify the weakest part of B's case."* |
| **Advocate-B** | Source B + cluster sources that support B | *"Build the strongest case that B is correct. Quote evidence. Identify the weakest part of A's case."* |
| **Judge** | Both advocate briefs + raw cluster sources + entity registry. Receives NO author's-page context. | *"Decide: A, B, both-valid-under-different-conditions, or insufficient-evidence. Cite the deciding evidence verbatim. Do not invoke evidence neither advocate raised."* |

One round only. Apply the judge's verdict:

- **A wins / B wins** — keep winning claim; mark loser inline `> **[Disputed — see Open Questions]** <text>`; both footnoted; add to `## Open Questions` with full debate citation
- **Both-valid-under-different-conditions** — keep both claims, add the conditional that distinguishes them, footnote each; this resolves what Step 8 typed as `conditional_contradiction`
- **Insufficient evidence** — fall back to Step 8's default (flag both, no resolution); the debate output is logged for the human

Record in the per-article log entry: `Debate: <A_wins|B_wins|both_conditional|insufficient> | rounds: 1 | judge: opus`. Set `<!-- LINT: debate_resolved=true -->` if a verdict was reached.

Skip this step entirely in cost/draft mode — fall back to the Step 8 default flag-both behavior.

**Step 9 — Auto-insert wikilinks**

Scan the article body for names/titles of existing wiki articles. Where found, wrap with `[[article-title]]`. Cap total links at `compile.cross_references.max_links_per_article`.

If `compile.cross_references.bidirectional` is true: when adding a link to article B in article A, also add a `## Connections` entry in B pointing back to A.

**Step 10 — Check cross-reference density**

Count `[[wikilinks]]` in the article. If below `wiki.connection_density_target`:
- Scan body text for any concept or entity names present in the wiki that weren't auto-linked
- Insert the missing links

**Step 11 — Write log entry**

```
## [YYYY-MM-DD] compile | <document-title>
- Source: raw/<subdir>/<filename>
- Articles created: <list or "none">
- Articles updated: <list or "none">
- Verbs (per updated article): <slug>: {strengthen: N, update: N, contradict: N, add: N}
- Entities extracted: <list>
- Confidence: <high/medium/low counts>
- Open questions added: N
- Contradictions flagged: N
- Cluster: <cluster-id or "unclustered">
- Model used: <sonnet|opus>
- Pass: <1|2>
- Self-critique applied: <yes|no>
```

**Step 11.5 — Self-critique pass (single iteration, before commit)**

Before committing the article (whether new or updated), re-read it against the cluster's raw sources one more time. Run **one** revision pass — do not loop — looking for three failure modes:

1. **Hallucinated claims** — any sentence in `## Details` that isn't supported by a source in `## Sources`. Either drop the sentence or add the missing footnote with citation.
2. **Missing claims** — anything load-bearing in the sources that didn't make the page. Add it with its footnote.
3. **Weak connections** — fewer than the connection density target (default 3) wikilinks, or no entry in `## Connections`. Find natural insertion points and add them.

If `mode == "precision"`, also: drop or downgrade any sentence whose only supporting source has weight < 0.5.

Apply all fixes in **one** revision, then commit. Set `<!-- LINT: self_critique_applied=true -->` at the bottom of the article. This is bounded Reflexion: it catches in ~1.3× Pass 2 tokens what lint would otherwise catch days later across many articles.

**Step 11.6 — Adversarial review pass (fresh-context critic, quality mode only)**

Self-critique systematically misses the same blind spots the original generation had, because both reasoning passes share the same context and reasoning chain. The fix is a **separately-prompted critic with no memory of how the article was written** — a held-out reviewer that comes to the page cold and looks for what slipped through.

Run this step in **quality mode only** (skip in cost/draft mode). For each article touched by this compile:

1. **Start a fresh Opus instance** — new system prompt, no memory of Pass 1, Pass 2, or Step 11.5. The reviewer must approach the article without the author's framing.
2. **Give the reviewer exactly three inputs**: the article body, the cluster's raw sources, and the entity registry. Do not include the per-article log entry or the verb counts — those bias the reviewer toward agreement with the author's decisions.
3. **Use this exact prompt frame** (paraphrase if needed, but keep the adversarial tone):
   > *You are a hostile reviewer of this wiki article. The author claims every factual sentence is supported by a footnoted source. Find every claim that isn't. Find every important fact in the cluster sources that the article omits. Find every wikilink that doesn't justify itself in context. Find every entity referenced by an unregistered name. Be specific and quote line numbers.*
4. **Apply the reviewer's findings** in one revision. Add missing footnotes, drop unsupported claims, insert missing facts with citations, remove or replace weak wikilinks. Do not argue with the reviewer — if a finding is wrong, drop it silently rather than defending the original.
5. **One iteration only.** Do not run the reviewer on the revised article. Multi-round adversarial loops [escalate confidence in both sides](https://arxiv.org/html/2505.19184v2) and converge on bias rather than truth.

Set `<!-- LINT: adversarial_review_applied=true -->` and record the reviewer's finding count in the per-article log entry: `Adversarial findings: {hallucinated: N, missing: N, weak_links: N, unregistered_entities: N}`.

This step is the single highest-yield no-cost-constraint addition. Empirically (per [MADR 2024](https://arxiv.org/pdf/2402.07401)), fresh-context critics catch up to 80% of the unfaithful claims that author-self-critique leaves in place. Cost: ~1× Pass 2 tokens per article; in a quality-mode wiki creation that's a worthwhile spend.

**Step 12 — Temporal Coherence Check (NEW)**

If `compile.temporal_coherence.enabled` is true:

1. **Date extraction:** Parse document dates from frontmatter (`date:`, `published:`, `created:`), filename patterns (YYYY-MM-DD), and content ("as of January 2024", "updated March 2025").

2. **Supersession detection:** Scan for signals in `compile.temporal_coherence.supersession_signals`:
   - If the current document explicitly states it "replaces", "supersedes", or "updates" another document
   - If two documents share the same ADR number pattern (e.g., `ADR-042` in both `adr-042-v1.md` and `adr-042-v2.md`)
   - If the title is identical/near-identical but with a version suffix or later date

3. **Chain linking:** When supersession is detected:
   - Set `superseded_by: "[[newer-article]]"` in the older article's frontmatter
   - Set `supersedes: "[[older-article]]"` in the newer article's frontmatter
   - Mark the older article `review_status: superseded`
   - Add a notice at the top of the older article: `> ⚠️ **Superseded** — see [[newer-article]] for the current version.`

4. **Temporal confidence adjustment:** If a claim exists in both an old and new version of a document, and the new version changes it, the old claim's confidence is downgraded by one level (high→medium, medium→low).

**Step 13 — Update Entity Registry (NEW)**

If `compile.entity_registry.enabled` is true:

After creating or updating any entity/concept article, update `wiki/entity_registry.md`:

```markdown
| <Entity Name> | <type> | <article-path> | <comma-separated aliases> |
```

The registry serves as a lookup table fed to subsequent compile calls. It prevents:
- Creating duplicate articles for the same entity under different names
- Inconsistent naming across the wiki
- Missing cross-links when documents reference an entity by an alias

**Step 14 — Hierarchical Summary Tree (NEW — RAPTOR-inspired)**

If `compile.hierarchical_summaries.enabled` is true and the current cluster has ≥ `min_cluster_size_for_tree` articles:

Build a RAPTOR-style summary tree for the cluster:
1. **Level 0 (leaves):** Individual article summaries (from `## Summary`)
2. **Level 1 (groups):** Group 3-5 related articles, write a 2-paragraph synthesis summary
3. **Level 2 (cluster):** Single paragraph summarizing the entire cluster's knowledge

Write the tree to `wiki/_cluster_summaries.md`:
```markdown
## Cluster: <cluster-label>
### Overview (L2)
<cluster-level summary>

### Sub-topics (L1)
#### <sub-group-1-label>
<synthesis of 3-5 articles>
Articles: [[art-1]], [[art-2]], [[art-3]]

#### <sub-group-2-label>
<synthesis of 3-5 articles>
Articles: [[art-4]], [[art-5]], [[art-6]]
```

This tree enables multi-level retrieval during queries: the LLM reads cluster summaries first to identify relevant clusters, then drills into specific articles. Dramatically improves query performance on large wikis (200+ articles).

**Step 15 — Confidence Calibration with Source Types (NEW)**

If `compile.confidence_scoring.enabled` is true, apply the expanded source weight table:

| Source Type | Weight | Auto-detection Signal |
|-------------|--------|----------------------|
| `peer_reviewed` | 1.0 | DOI link, arxiv ID, "journal", "proceedings" |
| `official_documentation` | 0.95 | help.sap.com, docs.*, official SDK docs |
| `internal_adr` | 0.9 | "ADR-", "Architecture Decision Record", internal decision doc |
| `internal_design_doc` | 0.85 | "Design Document", "Technical Specification" |
| `news_article` | 0.7 | News domains, press releases |
| `tutorial` | 0.65 | "tutorial", "how-to", "step-by-step" |
| `blog_post` | 0.5 | "blog", medium.com, personal sites |
| `community_forum` | 0.4 | Stack Overflow, Reddit, forum posts |
| `social_media` | 0.3 | Twitter/X, LinkedIn posts |
| `inferred` | 0.2 | No explicit source, derived from context |

**Recency bonus** (`compile.confidence_scoring.recency_bonus`): If a source is < 1 year old, add up to +0.1 to its weight (linear decay with `half_life_days`). This ensures recent official docs outrank older ones for the same topic.

**Source type auto-detection:** The LLM should infer `source_type` from the raw document's URL, frontmatter, content patterns, and filename. Set in article frontmatter:
```yaml
sources:
  - file: "../../raw/articles/sap-joule-api.md"
    type: official_documentation
    source_type: official_documentation
    confidence_weight: 0.95
    date: "2025-03-15"
```

### 3d. Article format

Every wiki article must use this template. **Two conventions are load-bearing** and they are what make the wiki a compounding asset rather than a pile of notes:

1. **`## Questions This Page Answers`** — a list of 5–10 plain-English questions a future reader (or LLM) would phrase. Generated during Pass 2 from the cluster's actual content. This is the compile-time equivalent of HyDE/HyPE: the index becomes searchable in the user's own vocabulary without any embedding infrastructure. Grep `wiki/**/*.md` for "how to X" and you land on the right page.
2. **Inline footnote citations** — every factual sentence ends with `[^src1]`. Definitions live in a `## Sources` section at the bottom, each pointing to the raw file (and optionally a `§"quoted span"` or line range). One footnote is reusable across many sentences. This replaces opaque `claim_count` counters with provenance a human can verify in Obsidian and lint can check programmatically.

```markdown
---
title: "<Article Title>"
type: concept          # concept | entity | topic | analysis
entity_type: null      # person | organization | tool | dataset | model (for type: entity)
domain: []             # e.g. ["ml", "nlp"] — domain tags from CLAUDE.md
tags: []               # free-form supplementary tags
related: []            # ["[[concept-a]]", "[[entity-b]]"]
confidence: medium     # high | medium | low (overall article confidence)
review_status: current # current | needs-review | stale | flagged-contradiction | superseded | stub
last_updated: "YYYY-MM-DD"
first_created: "YYYY-MM-DD"
cq_count: 0            # number of "Questions This Page Answers" — updated by compile
image_refs: []         # ["../../raw/images/diagram.png"] — use ../../raw/ for subdirectory articles
cross_kb_links: []     # ["../sister-kb/wiki/concepts/foo.md"] — federation links
stub: false            # true if article is below wiki.article_min_words
supersedes: null       # "[[older-article]]" — if this article replaces a previous version
superseded_by: null    # "[[newer-article]]" — if this article is replaced by a newer version
cluster: null          # cluster label from cluster_manifest.json (for traceability)
compile_pass: null     # 1 | 2 — which pass created/last-updated this article
verbs_last_compile: null  # {strengthen: N, update: N, contradict: N, add: N} — from Pass 2 verb log
---

# <Article Title>

## Summary

<2–3 sentence summary.>

## Questions This Page Answers

- What is <thing>?
- How does <thing> differ from <related thing>?
- When would you use <thing> over <alternative>?
- What are the limitations of <thing>?
- <5–10 questions total — phrased as a future reader would search>

## Details

<Main content — structured with ### subheadings as needed.
Every factual sentence carries an inline footnote citation [^src1].
One footnote can be reused across sentences.>

### Example paragraph

SAP Joule is SAP's generative AI copilot [^joule-launch]. It launched in late 2023 and shipped first inside SAP SuccessFactors [^joule-launch][^sf-rollout]. Joule is positioned as a natural-language interface across SAP applications, not a standalone product [^joule-launch].

## Connections

- [[linked-article]] — <one sentence explaining the relationship>

## Open Questions

- [ ] <unresolved question 1>
- [ ] <unresolved question 2>

## Sources

[^joule-launch]: ../../raw/articles/sap-joule-announcement.md
[^sf-rollout]: ../../raw/articles/sf-2024-release-notes.md §"Joule integration"

<!-- Frontmatter `sources` block (legacy, optional) — for tooling that hasn't migrated to footnotes -->
<!-- LINT: open_questions_count=N -->
<!-- LINT: cq_count=N -->
<!-- LINT: footnoted_pct=0.NN -->
<!-- LINT: contradiction_flag=false -->
```

**Source metadata**: when a footnote needs more than a raw path, embed it inline: `[^joule-launch]: ../../raw/articles/sap-joule-announcement.md (official_documentation, 2023-09-12)`. The source-type and date are optional but enable the recency-bonus and confidence weighting described in §1j.

**Obsidian note:** YAML frontmatter is queryable with the Dataview plugin. Footnote definitions render as hover-cards in reading mode. Use `![[image.png]]` syntax for images to get native Obsidian inline rendering.

### 3e. Update `wiki/_index.md`

After processing all new documents, update the index. **ALWAYS use `[[wikilink|Display Name]]` syntax — never markdown `[text](path)` links.** Obsidian's graph only draws edges from wikilinks.

```markdown
## Concepts
- [[transformer-architecture|Transformer Architecture]] — self-attention based model architecture
- [[attention-mechanism|Attention Mechanism]] — weighted context aggregation

## Entities
- [[anthropic|Anthropic]] — AI safety company, creator of Claude
- [[gpt-4|GPT-4]] — OpenAI large language model

## Analyses
- [[gpt4-vs-claude|Comparison: GPT-4 vs Claude]] — filed query output

## All Articles

| Article | Type | Confidence | Last Updated |
|---------|------|-----------|--------------|
| [[transformer-architecture\|Transformer Architecture]] | concept | high | 2025-01-01 |
| [[anthropic\|Anthropic]] | entity | high | 2025-01-01 |
```

For large wikis (total articles > `wiki.split_index_at`): create per-section indexes (`_index-concepts.md`, `_index-entities.md`, etc.) and link to them from the master `_index.md`.

### 3f. Re-embed for qmd (if configured)

```bash
qmd embed
```

### 3g. Git auto-commit (if `git.enabled` and `git.auto_commit`)

```bash
git add wiki/ && git commit -m "kb: compile — <N> new articles, <M> updated"
```

### 3h. Report to user

```
Compile complete
================
Raw docs processed: N (M new, K updated)
Articles created: N
Articles updated: N
Entities extracted: [list]
Confidence distribution: high: N | medium: N | low: N
Contradictions flagged: N
Open questions added: N
Wiki size: ~N words across N articles
```

---

## Phase 3.5: Cross-Cluster Synthesis (quality mode, post-compile)

Two-pass clustering produces excellent *intra-cluster* synthesis but leaves *inter-cluster* connections to fire only when wikilinks happen to bridge two clusters. Concepts that span clusters, contradictions between clusters, and missing articles that would tie cluster-A to cluster-B all go undetected. This phase closes that gap with a single global pass over the cluster-level summaries.

This is **GraphRAG's community sense-making benefit** ([Microsoft GraphRAG](https://medium.com/@yu-joshua/what-really-matters-to-better-graphrag-implementation-part-1-e02fff773c48) reports 86% accuracy vs 32% baseline on global queries) done at compile time as a static markdown artifact, **not** as a query-time graph traversal — which keeps it Karpathy-shaped.

### 3.5a. When to run

Run after Phase 3 finishes and any of the following holds:
- ≥3 clusters changed in this compile cycle
- A new cluster was created or an existing cluster split
- Entity registry gained ≥10 new entries since the last Phase 3.5
- The user explicitly asks ("global sweep", "cross-cluster pass")

Skip in cost/draft mode. Skip if fewer than 2 clusters exist.

### 3.5b. Inputs

Feed Opus the following bounded context (typically 30–80k tokens, well within the 200k window):

1. **`wiki/_cluster_summaries.md`** — all L2 cluster overviews (one paragraph each)
2. **`wiki/_cluster_summaries.md` L1 sub-syntheses** — for clusters that changed in this cycle
3. **`wiki/entity_registry.md`** — full registry
4. **Contradiction inventory** — grep `<!-- LINT: contradiction_flag=true -->` across the wiki; list the flagged articles with the contradiction summary from each `## Open Questions`
5. **Topic-article inventory** — list of all `wiki/topics/*.md` with their `## Summary` content
6. **The cluster manifest** (`cluster_manifest.json`) for cluster labels and sizes

Do NOT feed full article bodies — that defeats the purpose. Cross-cluster synthesis works on the *abstractions*, not the *primary sources*.

### 3.5c. Output: `wiki/topics/_cross-cluster-synthesis.md`

Write (or overwrite) a single canonical synthesis article structured as:

```markdown
---
title: "Cross-Cluster Synthesis"
type: topic
review_status: current
last_updated: "YYYY-MM-DD"
clusters_in_scope: [<list of cluster IDs>]
generated_by: phase-3.5
---

# Cross-Cluster Synthesis

## Summary

<2–3 sentence overview of the wiki's current shape across clusters.>

## Bridging Concepts

<Concepts/entities that appear meaningfully in 2+ clusters. For each:
- name (with wikilink to canonical article)
- clusters it bridges
- the cross-cluster insight: "in cluster-A this is treated as X; in cluster-B it shows up as Y; together they imply Z"
- footnote citations to the articles>

## Inter-Cluster Contradictions

<Contradictions that span clusters — different from Step 8's intra-cluster
contradictions. Each entry:
- the contradicting claims, footnoted
- which clusters they live in
- a resolution proposal (or "needs human" if irreconcilable)
- an `## Open Questions` entry on each side's article (added by this phase)>

## Missing Bridge Articles

<Concepts referenced in 2+ clusters that have no dedicated article. Each entry
becomes a priority-1 ingest candidate. Format:
- candidate slug
- clusters referencing it
- the bridging value: what synthesis it would enable
- minimum sources needed (list types: "1 official doc + 2 corroborating")>

## Evolution Notes

<What has changed in the wiki's overall shape since the last Phase 3.5 run?
New clusters formed? Old clusters merged? Entity-registry growth pattern?
This is the meta-narrative of the KB's intellectual evolution.>

## Sources

<Cited articles, by cluster. Use [^cluster-N-art-slug] footnote pattern.>
```

### 3.5d. Side effects on per-article wikis

When Phase 3.5 identifies a bridging concept whose canonical article exists, append a new entry to that article's `## Connections`:

```markdown
- [[other-cluster-article]] — *(cross-cluster: identified by Phase 3.5 on <date>)*
```

Bidirectional. The cross-cluster bridges become first-class wikilinks visible in Obsidian's graph view.

### 3.5e. Log entry

```
## [YYYY-MM-DD] phase-3.5 | cross-cluster synthesis
- Clusters in scope: <list>
- Bridging concepts found: N
- Inter-cluster contradictions: N (resolved: M)
- Missing bridge articles: N (added to ingest queue)
- Cross-cluster wikilinks added: N
- Model: opus
```

### 3.5f. Query-time effect

When a query is ambiguous about scope (e.g., "compare X across the field" or "what's the big picture"), Phase 4 reads `wiki/topics/_cross-cluster-synthesis.md` *first* before drilling into individual articles. It functions as the wiki's executive summary for sense-making queries.

---

## Phase 4: Query — Ask a Question Against the Wiki

### 4a. Read hierarchical summaries first (if available)

**For broad / sense-making queries** (signals: "compare across", "big picture", "evolution of", "what's the field doing", "summarize what you know") — read the cross-cluster synthesis first if it exists:

```bash
cat wiki/topics/_cross-cluster-synthesis.md
```

This is the wiki's executive summary, written by Phase 3.5. It surfaces bridging concepts, inter-cluster contradictions, and the meta-narrative of the KB's evolution. For these queries, the cross-cluster synthesis often answers more directly than any individual article.

**For narrower queries** — read the RAPTOR-style cluster summaries:

```bash
cat wiki/_cluster_summaries.md
```

Scan L2 (cluster-level) summaries to identify 1-3 relevant clusters. Then read the L1 sub-topic summaries for those clusters to narrow to specific articles.

If no cluster summaries exist, fall back to:
```bash
cat wiki/_index.md
cat wiki/_summaries.md
```

### 4b. Search for relevant articles

**If `search.backend == "qmd"`:**
```bash
qmd query "<user question>" --json
# or for file paths only:
qmd query "<user question>" --files
# for automatic query expansion:
qmd query "<user question>" --expand
```

**If `search.backend == "naive"`:**
```bash
python scripts/search.py --query "<user question>" --top <query_top_k>
```

Retrieve the top `query_top_k` articles.

**Entity registry resolution:** If the query mentions an entity by alias (e.g., "BTP"), check `wiki/entity_registry.md` to resolve to the canonical article before searching.

### 4c. Multi-hop reasoning (follow the links)

Read the retrieved articles. Collect all `[[wikilinks]]` from their `## Connections` sections. Retrieve any linked articles not yet in the result set (1 additional hop). Cap total articles at `query_top_k * 2`.

This handles transitive knowledge: if the user asks about X and the answer lives in Y (which X links to), the skill finds it without the user needing to know Y exists.

**Supersession awareness:** If a retrieved article has `review_status: superseded`, follow `superseded_by` to read the latest version instead. Note the evolution in the answer.

### 4d. Read relevant articles

```bash
cat wiki/concepts/<relevant>.md
cat wiki/entities/<relevant>.md
```

Flag if any retrieved article has `review_status: flagged-contradiction` — call this out in the answer.
Skip articles with `review_status: superseded` unless the user specifically asks about historical decisions.

### 4e. Synthesize a confidence-weighted answer

Structure the response as:

- **Direct answer** (1–3 sentences)
- **Supporting details** (from wiki articles, with inline citations: `[source: wiki/concepts/foo.md]`)
- **Confidence note** (if any source articles have `confidence: low` or `flagged-contradiction`)
- **Related topics** (links to related wiki articles not yet consulted)
- **Open questions** (what the wiki doesn't yet cover)

In `"mode": "precision"`: only cite `high` or `medium` confidence sources; explicitly say "the wiki has low-confidence information on X — I'd recommend adding a high-quality source."

### 4e-bis. Groundedness check + active gap-filing

After drafting the answer, check **groundedness**: what fraction of the factual claims in your answer can be traced to a footnote in a retrieved article? Compute it directly: count the answer's distinct claims, count how many resolve to a wiki `[^src]` footnote.

- **Groundedness ≥ 60% AND retrieved ≥ 2 articles for a multi-hop question** → return the answer normally (§4e structure).
- **Groundedness < 60% OR the query implies coverage the wiki doesn't have** → switch to the **gap-filing protocol** below. Do not silently fabricate. Do not just say "I don't know."

**Gap-filing protocol** (the compounding flywheel made explicit — per Karpathy, *queries that hit gaps should feed the wiki rather than evaporate*):

1. **Answer what you can** from grounded content. Be explicit about which parts are partial:
   > *"Partial answer based on the wiki: <grounded sentences with citations>. The wiki doesn't yet cover <gap>."*
2. **Identify the natural home** for the gap. This is usually one of the articles you just retrieved — pick the one whose topic is closest to the gap. If none fits, propose a new article slug.
3. **Append the user's question** to that article's `## Open Questions` section:
   ```markdown
   - [ ] <user's question, verbatim or lightly paraphrased> (asked 2025-05-27)
   ```
4. **Propose 2–3 ingest sources** to close the gap. Web-search if available; otherwise suggest source types the user likely has access to (specific docs sites, papers, internal repos).
5. **Log it** with prefix `## [YYYY-MM-DD] query-gap | <question-slug>` so lint counts it separately from satisfied queries:
   ```
   - Question: "<user question>"
   - Groundedness: 0.NN
   - Filed open question to: [[article-slug]]
   - Recommended ingest: <list>
   ```

Return the partial answer plus the gap-filing summary in this shape:

> *"<grounded partial answer>. Filed your question as an open question on [[article-slug]]. To close the gap, recommend ingesting: <source 1>, <source 2>."*

This is what makes the KB compound through use, not just through ingest.

### 4f. File answer back into wiki (optional)

If `output.file_back_to_wiki == "always"` (recall mode default) or the user says "save this":

1. Create `wiki/analyses/<slug>.md` using the article template with `type: analysis`
2. Set `sources` to the wiki articles consulted
3. Set `confidence` to the minimum confidence among all sources used
4. Update `_index.md` under `## Analyses`
5. Append a log entry:
   ```
   ## [YYYY-MM-DD] query | <question-slug>
   - Question: "<user question>"
   - Articles consulted: <list>
   - Filed back as: wiki/analyses/<slug>.md
   ```

If `output.file_back_to_wiki == "ask"`: offer to file it back.

---

## Phase 5: Output Generation

Generate a structured output from a query result or from the wiki directly.

### 5a. Determine output format

Ask if not specified:
> "What format would you like?
> - **Markdown report** — a long-form `.md` file
> - **Marp slides** — a slide deck viewable in Obsidian with the Marp plugin
> - **Matplotlib chart** — a Python script that generates a `.png` visualization
> - **Summary table** — a markdown table comparing concepts or entities"

### 5b. Markdown report

Write to `outputs/reports/<slug>.md`:

```markdown
---
title: <title>
date: <ISO date>
query: "<original question>"
sources:
  - wiki/concepts/foo.md
  - wiki/entities/bar.md
confidence: <min confidence of all sources>
---
```

### 5c. Marp slides

Write to `outputs/slides/<slug>.md`:

```markdown
---
marp: true
theme: default
paginate: true
---

# <Title>

---

## Slide 1 Title

- Bullet 1
- Bullet 2

---
```

Keep each slide to 4–6 bullet points. Include a title slide and a sources slide at the end.

Export to PDF: `npx @marp-team/marp-cli outputs/slides/<slug>.md --pdf`

### 5d. Matplotlib chart

Write to `outputs/charts/<slug>.py`:

```python
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# Data derived from wiki
fig, ax = plt.subplots(figsize=(10, 6))
# ... chart code ...
plt.title('<Chart Title>')
plt.tight_layout()
plt.savefig('outputs/charts/<slug>.png', dpi=150, bbox_inches='tight')
print("Saved: outputs/charts/<slug>.png")
```

Then run: `python outputs/charts/<slug>.py`

### 5e. File output back into wiki (optional)

Ask:
> "Would you like to file this output back into the wiki as a new analysis article? This enriches the knowledge base for future queries."

If yes, copy to `wiki/analyses/<slug>.md` and update `_index.md`.

---

## Phase 6: Lint — Health Check the Wiki

### 6a. Read all wiki articles

```bash
find wiki/ -name "*.md" | sort
```

Use `scripts/lint.py` to batch-detect structural issues:
```bash
python scripts/lint.py --kb-root . [--fix]
```

### 6b. Full check list

| Issue | Detection | Auto-fix? |
|-------|-----------|-----------|
| **Missing summary** | No `## Summary` section | Add stub summary |
| **Broken wikilinks** | `[[article]]` references a non-existent file | Remove link |
| **Orphan articles** | Article not referenced in `_index.md` | Add to index |
| **Conflicting facts** | `<!-- LINT: contradiction_flag=true -->` | Flag for user review only |
| **Missing sources** | No `sources:` in frontmatter | Mark as `[inferred]` |
| **Stub articles** | Word count < `lint.thresholds.stub_words` | Flag; offer to expand |
| **Duplicate concepts** | Two articles with 80%+ name similarity | Flag for merge |
| **Stale articles** | `last_updated` > `stale_days` days ago | Flag; offer web search update |
| **Low connection density** | `[[wikilinks]]` count < `connection_density_target` | Auto-insert missing links |
| **High open question count** | `open_questions_count` > `open_questions_max` | Convert oldest to ingest candidates |
| **Low-confidence cluster** | > `confidence_low_pct` of articles at `confidence: low` | Report; suggest ingestion |
| **Index drift** | Article exists in `wiki/` but not in `_index.md` | Re-add to index |
| **Missing entity_type** | `type: entity` article with no `entity_type` | Infer and set |
| **Unfiled analyses** | Query entries in `log.md` with no corresponding analysis article | Offer to file |
| **Wrong source path depth** | Articles in `wiki/concepts/`, `wiki/entities/`, `wiki/topics/` using `../raw/` instead of `../../raw/` | Auto-fix: replace `../raw/` → `../../raw/` |
| **Index uses markdown links** | `_index.md` contains `[text](path)` links instead of `[[wikilinks]]` | Auto-fix: convert to `[[slug\|Display Name]]` syntax |
| **Missing .obsidian/app.json** | File `<kb-root>/.obsidian/app.json` does not exist | Auto-create with `userIgnoreFilters` for raw/, outputs/, scripts/ |
| **Missing web-source raw files** | Wiki article `sources:` cites a file in `raw/articles/web-sources/` that does not exist on disk | Report; offer to re-fetch or reconstruct |
| **Unfooted factual sentences** | Sentences in `## Details` that don't end with `[^src]` and aren't headings/list scaffolding. Per-article `unfooted_pct > lint.thresholds.unfooted_pct_max` flags the article. | Flag for user; do not auto-add citations |
| **Unfiled queries** | `## [date] query \| ...` entries in `log.md` with no corresponding `wiki/analyses/<slug>.md`. Promoted to a top-line dashboard metric because Karpathy's compounding flywheel depends on it. | Offer to file each unfiled query as an analysis article |
| **Missing CQ section** | Article has no `## Questions This Page Answers` section or `cq_count: 0` | Flag; offer to regenerate via a small compile run on that article alone |
| **Failing competency questions** | CQs in `wiki/_competency_questions.md` with `status: ✗` or `⚠`. Surfaced as top-line **CQ coverage %** in the dashboard. | Auto-promote to ingest candidates ranked by referencing-article count |
| **Stale CQ status** | CQs marked `—` (unrun) or whose `Answered by` articles have changed since the last status update | Re-run the CQ via Phase 4 |
| **Missing adversarial review** | Article body lacks `<!-- LINT: adversarial_review_applied=true -->` and was last touched in quality mode | Flag; offer to run Step 11.6 on it standalone |
| **Pending debates** | `<!-- LINT: debate_resolved=false -->` on a contradiction-flagged article | Flag; offer to run Step 8.5 |

### 6c. Web-search to fill gaps (if web search available)

For `## Open Questions` items flagged across multiple articles, use web search to find additional sources and update the articles.

### 6d. Suggest new article candidates

Scan `## Open Questions` and `## Connections` sections across all articles. Identify concept/entity names that are referenced in 2+ articles but have no wiki article:

> "These new articles would fill important gaps:
> - `concepts/chain-of-thought.md` — referenced in 4 articles but not yet defined
> - `entities/mistral-ai.md` — mentioned in 2 papers
> - `topics/scaling-laws.md` — central theme with no dedicated article"

### 6e. Health dashboard

```
KB Health Dashboard
===================
Wiki: <kb-name> | Mode: <mode> | Last compile: <date>

⚡ COMPOUNDING SIGNAL   (the Karpathy flywheel — keep these near zero/full)
  CQ coverage (passing):        X%  [target: >90%]   ✓/⚠/✗
  Unfiled queries (last 30d):   N   [target: 0]
  Open question backlog:        N   (top 5 shown below)
  Gap-fills proposed by lint:   N
  Footnoted sentences:          X%  [target: >90%]   ✓/⚠/✗
  Adversarial-reviewed pages:   X%  [target: 100% in quality mode]   ✓/⚠/✗

Articles: N total | concepts: X | entities: Y | topics: Z | analyses: W
Words: ~N | avg per article: N

Quality Scores:
  Summaries present:    X%  (N/N)  [target: >95%]  ✓/⚠/✗
  Questions-this-page:  X%  (N/N)  [target: >90%]  ✓/⚠/✗
  Footnoted facts:      X%  (N/N)  [target: >90%]  ✓/⚠/✗
  Confidence high/med:  X%  (N/N)  [target: >80%]  ✓/⚠/✗
  Stubs (< N words):    X%  (N/N)  [target: <5%]   ✓/⚠/✗
  Connection density:   X%  (N/N)  [target: >75%]  ✓/⚠/✗
  Contradiction flags:  N articles              [target: 0]   ✓/✗

Activity (last 30 days, from log.md):
  Ingests: N | Compiles: N | Queries: N | Lint runs: N
  Verbs across compiles: strengthen=N | update=N | contradict=N | add=N

Open Questions backlog:
  Total: N | Top ingest candidates:
  1. <topic> (referenced in N articles, M open questions)
  2. <topic> (referenced in N articles)
  3. <topic> (referenced in N articles)
```

The **COMPOUNDING SIGNAL** block goes at the top deliberately. Per Karpathy, a wiki is only valuable if synthesis accumulates — these four metrics are the leading indicators of whether the flywheel is turning. Unfiled queries that pile up mean the user's exploration isn't being captured. A growing open-question backlog with no proposed gap-fills means the LLM is failing to surface ingest candidates. Footnote coverage below 90% means future queries can't be groundedness-checked. Treat any ⚠ or ✗ here as **higher priority than the structural quality scores below it.**

### 6f. Convert open questions to ingest candidates

Present the user with a ranked list of topics to ingest next, ordered by the number of articles referencing them. Offer to search the web for sources on each.

### 6f-bis. Run the competency-question suite

This is the wiki's executable test pass. Read `wiki/_competency_questions.md`. For each question:

1. **Run the question through Phase 4** (full retrieval + synthesis pipeline)
2. **Compare the answer to the question's expected substance** (a separate Opus call — short prompt: *"Question: X. Expected substance: Y. Wiki's answer: Z. Score: passing | partial | failing. One-line reason."*)
3. **Update the question's status** in `_competency_questions.md` (✓ / ⚠ / ✗) and the `Answered by:` line with the articles consulted
4. **Failing CQs become priority-1 ingest candidates** — surfaced in the dashboard's COMPOUNDING SIGNAL block and in §6f's ranked list

Coverage % = `passing / total`. This is the wiki's single highest-information health number — it measures whether the KB actually *delivers* on its stated scope, not just whether it has well-formed articles.

For wikis with 100+ CQs, run on a schedule (e.g., only the CQs related to articles that changed in the last compile cycle, full suite weekly). The lint script supports `--run-cqs all` (full) and `--run-cqs touched` (only CQs whose `Answered by` articles changed since last lint).

Skip in cost/draft mode — CQ runs are full-pipeline queries and cost adds up. In quality mode this is exactly what no-token-limit affords you.

### 6g. Git auto-commit (if `git.enabled`)

```bash
git add wiki/ && git commit -m "kb: lint — <N> issues fixed, <M> flagged"
```

---

## Phase 7: Search — Find Articles in the Wiki

### When to use qmd vs naive search

| Condition | Use |
|-----------|-----|
| Semantic / conceptual query ("how does attention work") | qmd (vector mode) |
| Exact term lookup ("find all mentions of RLHF") | naive search or qmd BM25 |
| Large wiki (100+ articles, 200k+ words) | qmd (scales better) |
| Offline / no npm | naive search |
| qmd MCP HTTP server running (`mcp_http: true`) | qmd (zero latency) |

### qmd usage

```bash
# Hybrid BM25 + vector search (recommended)
qmd query "<search terms>" --json

# Return only file paths for the LLM to read
qmd query "<search terms>" --files

# Automatic sub-query expansion
qmd query "<search terms>" --expand

# Start persistent MCP server (for heavy-use wikis)
qmd mcp --http --daemon
# Add to Claude Code MCP config: { "type": "http", "url": "http://localhost:8181" }
```

### Naive search

```bash
python scripts/search.py --query "<search terms>" --top 10
# or
grep -r "<search terms>" wiki/ -l
```

Return matching articles with a one-line description from their `## Summary` section.

---

## Phase 8: Image Handling

### 8a. Configure Obsidian for local image storage

In Obsidian: Settings > Files & Links > Default location for new attachments → set to `raw/images/`

Bind a hotkey (e.g. `Cmd+Shift+D`) to "Download attachments for current file" — this downloads all linked images in the current note to `raw/images/`.

### 8b. Download images during ingestion

When a web article references images important for understanding the content:
```bash
python scripts/ingest.py --url "<image-url>" --type image
```

### 8c. Vision pass during compile

For each image in `raw/images/` not yet in `_summaries.md` (and `ingest.vision_pass.on_images` is true):

1. Read the image (LLM multimodal input)
2. Extract: (a) one-paragraph description, (b) any visible text or diagram labels, (c) entities/concepts depicted
3. Create or update relevant wiki articles with an `image_refs` frontmatter entry
4. Reference in article body using relative path:
   ```markdown
   ![description](../raw/images/name.png)
   ```
   Or Obsidian native syntax: `![[name.png]]`
5. Append to `_summaries.md`

**Note:** LLMs cannot read markdown with inline images in one pass. Workaround: read the article text first, then load the referenced images separately for additional context.

---

## Phase 9: Log Operations

### 9a. Log structure

Every entry follows the parseable prefix from `log.prefix_format`:

```
## [YYYY-MM-DD] ingest | article-title
## [YYYY-MM-DD] compile | 3 new articles, 2 updated
## [YYYY-MM-DD] query | how-does-moe-routing-work
## [YYYY-MM-DD] lint | 47 articles checked, 2 issues fixed
## [YYYY-MM-DD] output | slides-transformer-overview
## [YYYY-MM-DD] git-commit | compile — 5 new articles
```

### 9b. Reading the log

```bash
# All recent entries
grep "^## \[20" wiki/log.md | tail -20

# Filter by operation
grep "^## \[20.*\] compile" wiki/log.md
grep "^## \[20.*\] query" wiki/log.md

# Date range
grep "^## \[2025-0[3-4]" wiki/log.md
```

### 9c. Log-driven workflows

When the user asks "what have we added recently?" or "show me the history":

1. Run the grep commands above (last 30 entries)
2. Summarize: N ingests, M compiles, K queries, J lint runs
3. If there are unfiled query entries (queries in the log without a corresponding `wiki/analyses/` article), offer to file them

Trim the log when it exceeds `log.max_entries`: keep the most recent N entries, archive older entries to `wiki/log-archive-YYYY.md`.

---

## Phase 10: Federation Queries (requires `federation.enabled: true`)

### 10a. When federation triggers

If a query returns fewer than 3 relevant results from the local wiki, and `federation.query_peers_on_miss` is true, automatically check peer KBs.

### 10b. Multi-KB query process

1. Read `wiki/_index.md` of each peer KB in `federation.peers`
2. Run the same search against each peer wiki
3. Synthesize a cross-KB answer, clearly attributing which KB each piece came from:
   > "From the `ai-safety-kb`: ... [wiki/concepts/foo.md]
   > From the `policy-kb`: ... [../policy-kb/wiki/concepts/bar.md]"
4. Insert cross-KB links using `federation.cross_link_prefix`: `[article](../peer-kb/wiki/concepts/article.md)`

### 10c. Cross-KB article stubs

If a synthesis draws heavily from a peer KB, create a stub article in `wiki/analyses/` with `cross_kb_links` pointing to the source articles, and a `## Summary` noting the cross-KB context.

---

## Phase 11: Training Data Export (requires `training_data.enabled: true`)

### 11a. Eligibility check

Only offer export when total wiki word count exceeds `training_data.min_wiki_words`. Check:
```bash
find wiki/ -name "*.md" ! -name "_*" | xargs wc -w | tail -1
```

### 11b. Generate Q&A pairs per article

For each wiki article, generate `training_data.qa_pairs_per_article` diverse Q&A pairs:

| Type | Template |
|------|----------|
| Factual recall | "What is X?" → answer from `## Summary` |
| Synthesis | "How does X relate to Y?" → answer from `## Connections` |
| Application | "When would you use X instead of Y?" → from `## Details` |
| Open-ended | "What are the open questions around X?" → from `## Open Questions` |

If `training_data.include_cot` is true, add a `reasoning` field with step-by-step thought.

Save to `outputs/training-data/<article-slug>-qa.jsonl`:
```json
{"prompt": "...", "completion": "...", "reasoning": "...", "source": "wiki/concepts/foo.md", "confidence": "high"}
```

### 11c. Manifest

Write `outputs/training-data/_manifest.jsonl` with one entry per export file (date, source article, pair count, confidence distribution).

---

## Phase 12: Git Version Control (requires `git.enabled: true`)

### 12a. Initialize

Done in Phase 1h. If not yet initialized:
```bash
cd <kb-root>
git init
git add .
git commit -m "kb: init — <kb-name>"
```

### 12b. Auto-commit hooks

After each compile and lint run, the skill issues:
```bash
git add wiki/
git commit -m "kb: <operation> — <summary>"
```

### 12c. Obsidian Git plugin

Install **Obsidian Git** in the vault. Configure to auto-commit on a schedule (e.g. every 30 minutes). Commit messages from compile runs make it easy to trace when a concept was first added: `git log --oneline`.

### 12d. Gitignore

The `.gitignore` created in Phase 1h excludes regenerable outputs. To track chart scripts but not PNG artifacts:
```
outputs/charts/*.png  # Regenerable from *.py scripts
```

---

## Key Principles

1. **LLM owns the wiki** — never prompt the user to manually edit wiki files. The LLM writes and maintains them.
2. **Incremental compilation** — only process new or changed raw documents; preserve existing wiki articles.
3. **Backlinks everywhere** — every wiki article links to its source documents and to related articles.
4. **Index is always current** — `_index.md` is updated as part of every compile and lint operation.
5. **Outputs are filed back** — useful query outputs are offered for filing back into the wiki under `wiki/analyses/`.
6. **Open Questions drive growth** — unanswered questions in articles are the fuel for future ingests and linting. Lint converts them into ranked ingest candidates.
7. **The log is the audit trail** — every operation appends a parseable entry to `wiki/log.md`. The log drives the health dashboard and surfaces unfiled queries.
8. **Search backend is configurable** — `search.backend: naive` for zero-dependency simplicity; `qmd` for semantic power on large wikis. Switch via config without changing workflow steps.
9. **Confidence is first-class** — every article carries a confidence level. Query synthesis weights answers by confidence. Lint enforces the confidence health threshold.
10. **Git is native** — the wiki is a git repo. Compile and lint auto-commit when `git.enabled`. This makes the KB's evolution inspectable and recoverable.
11. **The KB is long-term memory** — Init writes a `CLAUDE.md` inside the KB root and optionally into the global `~/.claude/CLAUDE.md`. Future Claude sessions auto-discover the KB and query it before generating answers from scratch.

---

## Obsidian Setup Tips

1. Open `<kb-root>` as an Obsidian vault
2. Install plugins: **Marp** (slides), **Dataview** (dynamic tables), **Obsidian Git** (auto-commit)
3. Enable **Wikilinks** in Settings so `[[article]]` syntax works
4. Use the **Obsidian Web Clipper** browser extension to clip web articles directly to `raw/articles/`
5. Set Settings > Files & Links > Default attachment folder to `raw/images/`
6. Bind `Cmd+Shift+D` (Mac) or `Ctrl+Shift+D` (Windows/Linux) to "Download attachments for current file" — this pulls all linked images to `raw/images/` for local LLM vision access
7. Open `wiki/log.md` as a sidebar panel for a live activity feed
8. Example Dataview query to audit confidence across concepts:
   ```dataview
   TABLE confidence, last_updated, claim_count
   FROM "wiki/concepts"
   SORT confidence ASC, last_updated ASC
   ```
9. Use the graph view to spot poorly-connected orphan articles (nodes with few edges)

---

## Reference

See [references/knowledge-base-patterns.md](references/knowledge-base-patterns.md) for advanced patterns: qmd integration, confidence scoring, multi-KB federation, synthetic data generation, and version control.
