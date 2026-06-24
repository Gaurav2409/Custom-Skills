# Review Handoff Template

This template defines the format for the Hermes research result file and the lint review
handoff. The sap-orchestrator reads both using this structure.

---

## Research Result File (written by Hermes sap-researcher)

File path: `/tmp/sap_research_result_<TIMESTAMP>.md`

### Required sections

```
# SAP Research Result

## Status
PASS | WARN | FAIL

## Task
- topic: "<topic>"
- task_file: "<path to task file>"
- completed: "<ISO 8601 timestamp>"
- hermes_session: "<session ID if available>"

## Statistics
- pages_crawled: N
- articles_saved: N
- articles_skipped: N (already indexed)
- errors: N (fetch failed, too short, etc.)
- browser_harness_pages: N
- firecrawl_pages: N
- code_rich_articles: N
- avg_word_count: N
- official_docs_count: N
- tutorial_count: N
- community_forum_count: N
- internal_design_doc_count: N

## Subtopics Covered
- [x] <subtopic 1> — covered by: <slug>, <slug>
- [x] <subtopic 2> — covered by: <slug>
- [ ] <subtopic 3> — NOT covered (no sources found)

## Articles Saved
| Slug | Source Type | Words | Has Code | Has Diagram | URL |
|------|-------------|-------|----------|-------------|-----|
| <slug> | official_documentation | N | yes | no | <url> |

## Coverage Gaps
- <gap>: no sources found
- <gap>: only community_forum sources available

## Recommendations
- [VPN issues, auth failures, quality warnings, version notes]

## Output Path
/Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb/raw/articles/web-sources/
```

---

## Lint Review Handoff (written by sap-orchestrator after lint runs)

```
# Lint Review Handoff

## Compilation summary
- articles_created: N
- articles_updated: N
- entities_extracted: [list]
- confidence_high: N | confidence_medium: N | confidence_low: N
- contradictions_flagged: N

## Changed files
[List of wiki article paths created or updated]

## Lint results
[Paste health dashboard output from lint.py]

## Validation commands run
- python3 scripts/lint.py --kb-root . --fix
  Result: [paste output summary]
- python3 scripts/compile.py --kb-root . --dry-run
  Result: [paste output — should show 0 pending articles]

## Review focus
- Correctness: do articles accurately reflect source material?
- Requirement alignment: are all compile directive must-haves satisfied?
- Security/privacy: no SAP-internal content in public-confidence articles
- Tests: lint health score ≥70%, 0 broken wikilinks, 0 orphan articles
- Maintainability: are wikilinks bidirectional? entity registry updated?

## Output required
- blocking_issues: [list or "none"]
- non_blocking_suggestions: [list or "none"]
- recommendation: accept | revise | escalate
```
