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
