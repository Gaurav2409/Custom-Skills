# Research Task Template

This file is written by the sap-orchestrator and read by the Hermes sap-researcher skill.
Fill all sections before dispatching Hermes.

---

## Metadata

- topic: [The SAP technology subject]
- timestamp: [YYYYMMDD_HHMMSS]
- result_file: /tmp/sap_research_result_[TIMESTAMP].md
- kb_root: /Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb
- output_dir: /Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb/raw/articles/web-sources
- requested_by: sap-orchestrator

## Research Targets

### Subtopics to cover

[One subtopic per line. These drive the subtopic coverage check in the result file.]

### Coverage gaps from KB pre-scan

[List of specific KB gaps identified in Phase 1. "none" if this is a fresh topic.]

### Refresh targets (stale articles to update)

[List of wiki article slugs that are stale and need new source material. "none" if none.]

## Authenticated links (Browser Harness required)

[List of specific URLs provided by the user via -- links: argument]
[These must be crawled with Browser Harness. Never send to Firecrawl.]
[Write "none" if no authenticated links were provided.]

## Seed domains

### SAP-internal (Browser Harness only — never Firecrawl)

- pages.github.tools.sap (VPN required)
- *.launchpad.cfapps.*.hana.ondemand.com
- jam.sap.com

### Public (Firecrawl preferred, Browser Harness fallback)

[List inferred from topic keywords. The sap-researcher will expand these.]

## Quality requirements

- min_articles: 15
- min_word_count_per_article: 300
- required_official_docs_ratio: 0.30
- required_subtopics_covered: 0.80
- required_code_rich_articles: 5
- min_sap_internal_pages: [1 if authenticated links provided, else 0]

## Karpathy depth requirements

Each saved article should enable the wiki compile to produce:

- [ ] At least one code example per subtopic (real, runnable)
- [ ] API endpoint / CLI command reference for service entities
- [ ] Implementation pattern (how to wire it up end-to-end)
- [ ] Common pitfalls with error messages and fixes
- [ ] Links to related SAP services and dependencies

## Output instructions

Write result to: /tmp/sap_research_result_[TIMESTAMP].md
Articles saved to: /Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb/raw/articles/web-sources/
Skill invoked: /sap-researcher [this-task-file-path]

## Stop conditions for Hermes

- Stop if VPN is unavailable and internal links were provided — write FAIL result with VPN_REQUIRED flag
- Stop if Browser Harness fails to load any authenticated URL after 2 retries — write WARN result
- Stop if fewer than 5 articles are saved after crawling all seed domains — write FAIL result
- Do not infer subtopic coverage from unrelated articles

---

## Ground-Up Content Targets

The wiki articles compiled from this research must enable a developer to go from zero to
working code. Hermes should actively seek the following content types — they are not
optional extras, they are the primary research targets:

### Priority 1 — Runnable code examples

For each subtopic, find at least one source page that contains a **complete, runnable code
example** (not a fragment, not pseudocode). Preferred:

- TypeScript/JavaScript for CAP service definitions and handlers
- Python for AI Core / AI SDK usage
- Shell for BTP CLI, kubectl, cds, mbt commands
- YAML for Kubernetes/Kyma CRDs (Subscription, Function, APIRule)
- JSON for xs-security.json, mta.yaml, service bindings
- CDS for entity definitions, service annotations

A code block is "complete" if it can be copy-pasted and run with no modifications beyond
substituting realistic dummy values. Fragments like `// ... rest of code` are NOT complete.

### Priority 2 — Architecture and data-flow diagrams

Find sources that show, visually or textually, **how components connect**:

- What calls what (caller → callee)
- What owns what (owner → resource)
- What triggers what (event → handler)

If sources contain SVG or image diagrams, note them explicitly in the result file so the
Spec Writer knows the ASCII reconstruction must cover those flows.

### Priority 3 — "Why this exists" and mental model sources

Find at least one source per subtopic that answers: *what problem does this solve and why
was it built this way?* Developer guides, architecture decision records, conceptual overviews,
and "getting started" introductions all qualify. These feed the `## Why This Exists` and
`## Mental Model` sections and are the difference between a reference article and one that
builds genuine understanding.

### Priority 4 — Pitfall and error message sources

Find ≥2 sources that document **real errors, non-obvious behaviors, or known gotchas**.
Community posts, GitHub issues, and troubleshooting guides are valuable here. Capture the
exact error message string where possible (e.g. `Error: ECONNREFUSED 127.0.0.1:4004`).
These feed `## Common Pitfalls` and are often the highest-value content for coding agents.

### Priority 5 — End-to-end tutorials or deployment guides

Find at least one source that walks through the **full workflow from prerequisites to
deployed and verified** — including the BTP CLI commands, service instance creation, local
test command, and deploy + verify step. These feed `## Full Implementation Pattern`.
