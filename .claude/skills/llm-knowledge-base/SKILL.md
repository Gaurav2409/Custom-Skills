---
name: llm-knowledge-base
description: Build and maintain a personal LLM-powered knowledge base. Use when the user wants to ingest raw documents (articles, papers, repos, images) into a structured Obsidian-compatible markdown wiki, run Q&A against it, generate visual outputs, or perform health-check linting over the wiki. Also triggers when the user asks a question and a CLAUDE.md or kb.config.json exists nearby — query the wiki first before generating from scratch.
---

# LLM Knowledge Base

Build and maintain a **personal knowledge base** powered by an LLM. Raw source documents are compiled by the LLM into an Obsidian-compatible markdown wiki that acts as **long-term agent memory** — once initialized, Claude automatically queries it before answering research questions, without the user needing to specify a path. You rarely edit the wiki directly; the LLM owns it.

## Directory Layout

```
<kb-root>/
├── CLAUDE.md                   # Auto-generated — tells Claude to query this KB
├── kb.config.json              # Knowledge base configuration (v2)
├── raw/                        # Source documents (articles, papers, repos, images, PDFs)
│   ├── articles/
│   ├── papers/
│   ├── images/
│   └── repos/
├── wiki/                       # LLM-compiled wiki (markdown articles)
│   ├── _index.md               # Master index — auto-maintained by LLM
│   ├── _summaries.md           # One-paragraph summary of every raw doc
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
│   ├── compile.py              # List new/changed raw docs for the LLM to process
│   ├── query.py                # Q&A against the wiki
│   ├── lint.py                 # Health-check the wiki
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

### 1d. Create `kb.config.json`

```json
{
  "name": "<kb-name>",
  "root": "<absolute-path>",
  "topic": "<research topic or empty string>",
  "created": "<ISO date>",
  "version": "2",
  "mode": "recall",

  "wiki": {
    "index_file": "wiki/_index.md",
    "summaries_file": "wiki/_summaries.md",
    "log_file": "wiki/log.md",
    "split_index_at": 300,
    "subdirectories": ["concepts", "entities", "topics", "analyses"],
    "article_min_words": 120,
    "article_max_open_questions": 5,
    "connection_density_target": 3
  },

  "ingest": {
    "auto_compile": true,
    "quality_filter": {
      "enabled": true,
      "min_word_count": 200,
      "require_readable_text": true,
      "skip_patterns": ["draft-*", "temp-*"],
      "duplicate_detection": true
    },
    "vision_pass": {
      "enabled": true,
      "on_images": true,
      "on_pdfs": false
    }
  },

  "compile": {
    "entity_extraction": {
      "enabled": true,
      "types": ["person", "organization", "tool", "dataset", "model", "concept"],
      "min_mention_count": 2
    },
    "contradiction_detection": {
      "enabled": true,
      "sensitivity": "medium",
      "flag_in_article": true
    },
    "confidence_scoring": {
      "enabled": true,
      "scale": "three-point",
      "min_confidence_to_include": "low",
      "source_weight": {
        "peer_reviewed": 1.0,
        "news_article": 0.7,
        "blog_post": 0.5,
        "social_media": 0.3,
        "inferred": 0.2
      }
    },
    "cross_references": {
      "auto_link": true,
      "max_links_per_article": 30,
      "bidirectional": true
    }
  },

  "search": {
    "backend": "naive",
    "qmd": {
      "collection_name": "<kb-name>",
      "mcp_http": false,
      "mcp_port": 8181,
      "embed_on_compile": true
    },
    "query_top_k": 8,
    "precision_score_threshold": 0.0
  },

  "lint": {
    "auto_fix_safe": true,
    "thresholds": {
      "stub_words": 120,
      "open_questions_max": 5,
      "broken_links_max": 0,
      "orphan_articles_max": 0,
      "articles_without_sources_pct": 0.05,
      "confidence_low_pct": 0.20
    },
    "checks": {
      "missing_summary": true,
      "broken_backlinks": true,
      "orphan_articles": true,
      "stub_articles": true,
      "missing_sources": true,
      "duplicate_concepts": true,
      "contradiction_flags": true,
      "stale_articles": true,
      "stale_days": 180,
      "open_questions_to_ingest": true,
      "connection_density": true
    },
    "health_dashboard": true
  },

  "log": {
    "enabled": true,
    "file": "wiki/log.md",
    "prefix_format": "## [YYYY-MM-DD] {operation} | {title}",
    "operations_to_log": ["ingest", "compile", "query", "lint", "output", "git-commit"],
    "max_entries": 1000
  },

  "git": {
    "enabled": false,
    "auto_commit": true,
    "commit_message_template": "kb: {operation} — {summary}"
  },

  "output": {
    "default_format": "markdown",
    "file_back_to_wiki": "ask",
    "report_subdirectory": "outputs/reports",
    "slides_subdirectory": "outputs/slides",
    "charts_subdirectory": "outputs/charts",
    "training_data_subdirectory": "outputs/training-data"
  },

  "federation": {
    "enabled": false,
    "peers": [],
    "cross_link_prefix": "../{peer-name}/wiki/",
    "query_peers_on_miss": true
  },

  "tags": {
    "taxonomy": [],
    "require_taxonomy": false
  },

  "training_data": {
    "enabled": false,
    "min_wiki_words": 50000,
    "format": "jsonl",
    "qa_pairs_per_article": 10,
    "include_cot": true
  }
}
```

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

### 1j. Set up qmd collection (if `search.backend == "qmd"`)

```bash
npm install -g @tobilu/qmd   # one-time global install
qmd collection add wiki/ --name <collection_name>
qmd context add qmd://<collection_name> "Wiki for <kb-name>: <topic>"
```

### 1j. Write `CLAUDE.md` — long-term memory registration

Write a `CLAUDE.md` file in `<kb-root>/`:

```markdown
# Knowledge Base: <kb-name>

This directory is an LLM knowledge base managed by the llm-knowledge-base skill.

- **Config**: kb.config.json
- **Wiki index**: wiki/_index.md
- **Activity log**: wiki/log.md
- **Topic**: <topic>

## Instructions for Claude

When the user asks any research question or says "query", "what do you know about",
"check the KB", or "look it up" — use the llm-knowledge-base skill to query this
wiki BEFORE generating an answer from scratch. The wiki is the accumulated source
of truth for this project.

To query: read wiki/_index.md, identify relevant articles, read them, synthesize
an answer with citations. Follow wikilinks one hop for transitive knowledge.
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

This is the core LLM operation. Read new/changed raw documents and incrementally update the wiki.

### 3a. Read the current wiki state

```bash
cat wiki/_index.md
cat wiki/_summaries.md
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

### 3c. For each new or changed raw document — 11-step pipeline

**Step 1 — Read the file**

```bash
cat "<raw-file>"
```

For images: view them directly (multimodal). If `ingest.vision_pass.on_images` is true, extract: (a) description, (b) any text/diagrams visible, (c) entities depicted.

**Step 2 — Quality filter**

Apply the `ingest.quality_filter` checks from 2e. Skip and log if the document fails.

**Step 3 — Write/update summary**

Append a one-paragraph summary to `wiki/_summaries.md`:
```
**<filename>** — <one-paragraph summary. Source type: <article|paper|image|repo>.>
```

**Step 4 — Extract entities**

From the document, extract all entities matching `compile.entity_extraction.types` (person, organization, tool, dataset, model, concept). Only entities appearing at least `min_mention_count` times warrant their own article.

**Step 5 — Entity resolution**

Before creating a new entity article, search existing `wiki/entities/` for articles with similar names (e.g., "GPT-4" and "GPT4", "OpenAI" and "Open AI"). If a near-duplicate exists, merge the new content into the existing article instead of creating a new file.

**Step 6 — Create or update articles**

Create or update concept/entity/topic articles using the article template (see §Article Format below). For each article:
- If the file doesn't exist: create it
- If it exists: update `## Details`, `## Connections`, `## Open Questions`, and frontmatter fields (`last_updated`, `claim_count`, `sources`, `image_refs`)

**Step 7 — Assign confidence**

Based on source type and number of corroborating sources:
- `high`: peer-reviewed paper, or claim appears in 3+ independent sources
- `medium`: single credible source (news, book, official docs)
- `low`: single blog post, inferred connection, or social media

In `"mode": "precision"`: skip claims with `confidence: low` entirely; mark article `review_status: needs-review` if any source weight < 0.5.

In `"mode": "recall"`: include all claims; mark speculative content inline:
> **[Inferred]** <speculative claim>

**Step 8 — Contradiction scan**

After writing/updating an article, cross-check its factual claims against the 3 most-linked related articles. If a direct contradiction is found:
- Add `<!-- LINT: contradiction_flag=true -->` at the bottom of both articles
- Set `review_status: flagged-contradiction` in frontmatter
- Note the contradiction explicitly in the `## Open Questions` section

Sensitivity levels (from `compile.contradiction_detection.sensitivity`):
- `low`: only direct factual negations (X is Y vs X is not Y)
- `medium`: numerical inconsistencies, reversed causal claims
- `high`: any claim that appears in tension with another

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
- Entities extracted: <list>
- Confidence: <high/medium/low counts>
- Open questions added: N
- Contradictions flagged: N
```

### 3d. Article format

Every wiki article must use this template:

```markdown
---
title: "<Article Title>"
type: concept          # concept | entity | topic | analysis
entity_type: null      # person | organization | tool | dataset | model (for type: entity)
domain: []             # e.g. ["ml", "nlp"] — from kb.config.json tags.taxonomy
tags: []               # free-form supplementary tags
sources:
  - file: "../../raw/articles/example.md"   # CRITICAL: articles in wiki/concepts/, wiki/entities/, wiki/topics/ are TWO levels deep from KB root — always use ../../raw/ NOT ../raw/
    type: article      # article | paper | image | repo | inferred
    confidence_weight: 0.7
related: []            # ["[[concept-a]]", "[[entity-b]]"]
confidence: medium     # high | medium | low (overall article confidence)
review_status: current # current | needs-review | stale | flagged-contradiction
last_updated: "YYYY-MM-DD"
first_created: "YYYY-MM-DD"
claim_count: 0         # number of distinct factual claims — updated by compile
image_refs: []         # ["../../raw/images/diagram.png"] — use ../../raw/ for subdirectory articles
cross_kb_links: []     # ["../sister-kb/wiki/concepts/foo.md"] — federation links
stub: false            # true if article is below wiki.article_min_words
---

# <Article Title>

## Summary

<2–3 sentence summary.>

## Details

<Main content — structured with ### subheadings as needed.>

## Connections

- [[linked-article]] — <one sentence explaining the relationship>

## Open Questions

- [ ] <unresolved question 1>
- [ ] <unresolved question 2>

<!-- LINT: open_questions_count=N -->
<!-- LINT: claim_count=N -->
<!-- LINT: contradiction_flag=false -->
```

**Obsidian note:** YAML frontmatter is queryable with the Dataview plugin. Use `![[image.png]]` syntax for images to get native Obsidian inline rendering.

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

## Phase 4: Query — Ask a Question Against the Wiki

### 4a. Read the index and summaries first

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

### 4c. Multi-hop reasoning (follow the links)

Read the retrieved articles. Collect all `[[wikilinks]]` from their `## Connections` sections. Retrieve any linked articles not yet in the result set (1 additional hop). Cap total articles at `query_top_k * 2`.

This handles transitive knowledge: if the user asks about X and the answer lives in Y (which X links to), the skill finds it without the user needing to know Y exists.

### 4d. Read relevant articles

```bash
cat wiki/concepts/<relevant>.md
cat wiki/entities/<relevant>.md
```

Flag if any retrieved article has `review_status: flagged-contradiction` — call this out in the answer.

### 4e. Synthesize a confidence-weighted answer

Structure the response as:

- **Direct answer** (1–3 sentences)
- **Supporting details** (from wiki articles, with inline citations: `[source: wiki/concepts/foo.md]`)
- **Confidence note** (if any source articles have `confidence: low` or `flagged-contradiction`)
- **Related topics** (links to related wiki articles not yet consulted)
- **Open questions** (what the wiki doesn't yet cover)

In `"mode": "precision"`: only cite `high` or `medium` confidence sources; explicitly say "the wiki has low-confidence information on X — I'd recommend adding a high-quality source."

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

Articles: N total | concepts: X | entities: Y | topics: Z | analyses: W
Words: ~N | avg per article: N

Quality Scores:
  Summaries present:    X%  (N/N)  [target: >95%]  ✓/⚠/✗
  Sources present:      X%  (N/N)  [target: >90%]  ✓/⚠/✗
  Confidence high/med:  X%  (N/N)  [target: >80%]  ✓/⚠/✗
  Stubs (< N words):    X%  (N/N)  [target: <5%]   ✓/⚠/✗
  Connection density:   X%  (N/N)  [target: >75%]  ✓/⚠/✗
  Contradiction flags:  N articles              [target: 0]   ✓/✗

Activity (last 30 days, from log.md):
  Ingests: N | Compiles: N | Queries: N | Lint runs: N
  Unfiled queries: N

Open Questions backlog:
  Total: N | Top ingest candidates:
  1. <topic> (referenced in N articles, M open questions)
  2. <topic> (referenced in N articles)
  3. <topic> (referenced in N articles)
```

### 6f. Convert open questions to ingest candidates

Present the user with a ranked list of topics to ingest next, ordered by the number of articles referencing them. Offer to search the web for sources on each.

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
