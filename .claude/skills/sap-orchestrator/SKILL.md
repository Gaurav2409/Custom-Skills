# SAP Orchestrator Skill

Stage-gated multi-agent pipeline for building and enriching the SAP LLM knowledge graph.
Orchestrates Hermes (deep researcher) and the llm-knowledge-base skill to produce
Karpathy-depth wiki articles for non-open-source SAP technologies.

**Trigger:** `/sap-orchestrator`

## Invocation

```
/sap-orchestrator "<topic>" [-- links: <url1> <url2> ...]
```

Examples:

```
/sap-orchestrator "Kyma Runtime: service mesh, eventing, serverless functions"
/sap-orchestrator "SAP Joule: tool-use, agent API, MCP integration" -- links: https://help.sap.com/docs/joule
/sap-orchestrator "BTP AppFoundation: agent bootstrap, ORD, A2A protocol"
/sap-orchestrator "CAP: Node.js CDS, service bindings, hybrid testing, event-driven"
```

---

## Constants

```
KB_ROOT="/Users/I321170/Documents/LLM knowledge base/sap-ai-practices-kb"
HERMES_BIN="$HOME/.hermes/hermes-secure.sh"
AGENTS_DIR="$HOME/Documents/cbc-ai/skills-repo/.claude/skills/sap-orchestrator/.agents"
```

---

## Operating Model (from multi_agent_rd_prompt_pack)

```
User target
  → Orchestrator (Claude Code) — this skill
  → Internal + Public Researcher (Hermes /sap-researcher) — parallel
  → Research Critic (Claude Code, automated gate)
  → Spec Writer (Claude Code) — compile directive
  → Builder (llm-knowledge-base skill) — wiki compilation
  → Requirement Reviewer (lint health check)
  → Release Summarizer (Claude Code)
```

**Core rule:** Raw research output NEVER directly drives compilation. It must pass the
Research Critic gate and become a source-grounded compile directive first.

---

## Phase 0 — Parse Request

Extract from the invocation:
- **Topic**: the SAP technology subject (required, everything before `-- links:`)
- **Authenticated links**: URLs after `-- links:` (optional, Browser Harness targets)
- **Subtopics**: comma-separated terms in the topic string (e.g. "service mesh, eventing")

If topic is missing or vague, ask one clarifying question:
> "What specific aspect of `<tech>` should I research? E.g. `<tech>: <subtopic1>, <subtopic2>`"

---

## Phase 1 — KB Pre-Scan (Gate 1 Check)

Before dispatching research, scan what the KB already covers.

```bash
python3 "$KB_ROOT/scripts/search.py" --query "<topic>" --top 5
```

Identify:
- Articles already high-confidence for this topic → skip or target gaps only
- Articles with `review_status: stale` or `confidence: low` → mark as refresh targets
- Subtopics with zero coverage → primary research targets

**Gate 1 (Research Readiness) — proceed only if:**
- Target is specific enough to research (not "everything about SAP")
- Internal and public domains are identifiable
- No conflicting confidentiality rules (don't mix internal and public researchers)

**Escalate if:** Target is too broad → ask user to narrow scope.

Report pre-scan to user:
```
KB Pre-Scan: "<topic>"
  Existing articles (high): N
  Stale/low-confidence:     N → will refresh
  Coverage gaps:            [subtopics not covered]
  Research scope:           [gap-fill | full coverage]
  Proceeding automatically if 0 high-confidence articles exist for topic.
```

---

## Phase 2 — Write Research Task File

Generate a timestamp and paths:
```bash
TS=$(date +%Y%m%d_%H%M%S)
TASK_FILE="/tmp/sap_research_task_${TS}.md"
RESULT_FILE="/tmp/sap_research_result_${TS}.md"
COMPILE_SUMMARY="/tmp/sap_compile_summary_${TS}.md"
```

Write the task file using the `.agents/templates/research-task.md` template, populated with:
- `topic`, `TS`, `RESULT_FILE`, `KB_ROOT`, output directory
- Subtopics extracted from Phase 0 + gaps from Phase 1
- Authenticated links from invocation (or "none")
- Quality requirements (≥15 articles, ≥300 words avg, ≥80% subtopics covered)
- Ground-up content targets (runnable code examples, architecture sources, pitfall sources)

For complex or multi-team topics, use `.agents/templates/intake.md` as a richer intake
form (adds business context, definition of done, approval requirements). The quick
invocation format is sufficient for focused single-topic research.

---

## Phase 3 — Dispatch Hermes

Launch Hermes with the sap-researcher skill:
```bash
$HERMES_BIN /sap-researcher "$TASK_FILE"
```

If Hermes supports non-interactive single-turn mode:
```bash
$HERMES_BIN --message "/sap-researcher $TASK_FILE" &
```

If neither works, show the user:
```
Action required: Run this in a terminal →
  ~/.hermes/hermes-secure.sh /sap-researcher /tmp/sap_research_task_<TS>.md

Then continue this conversation when Hermes finishes.
Expected result file: /tmp/sap_research_result_<TS>.md
```

Poll for the result file (check every 30s, timeout 30 min):
```bash
while [ ! -f "$RESULT_FILE" ] && [ $ELAPSED -lt 1800 ]; do
    sleep 30; ELAPSED=$((ELAPSED + 30))
    echo "Waiting for Hermes... (${ELAPSED}s / 1800s)"
done
```

---

## Phase 4 — Research Critic Gate (Gate 2)

Read the result file and run the Research Critic check. Load the full instructions from
`.agents/research-critic.md`.

**Gate 2 (Spec Readiness) — automated checks:**

| Check | Threshold | Gate |
|-------|-----------|------|
| Articles saved | ≥ 15 | WARN if <15, FAIL if <5 |
| Official docs ratio | ≥ 30% | WARN |
| Avg word count | ≥ 300 | FAIL if <200 |
| Subtopics covered | ≥ 80% of requested | WARN |
| Code-rich articles (`Has-Code: true`) | ≥ 5 | WARN |
| SAP-internal pages (if auth links provided) | ≥ 1 | FAIL if 0 and links were given |
| Coverage gaps | Documented | Required |
| Source citations present | Yes | Required |

**Gate 2 output:**
```
Research Critic Report
======================
Articles:          N  (target: ≥15)   [PASS/WARN/FAIL]
Official docs:     N% (target: ≥30%)  [PASS/WARN/FAIL]
Avg word count:    N  (target: ≥300)  [PASS/WARN/FAIL]
Subtopics:         N/M covered        [PASS/WARN/FAIL]
Code-rich:         N  (target: ≥5)    [PASS/WARN/FAIL]
SAP-internal:      N pages            [PASS/FAIL]
Contradictions:    N flagged

Gate 2: PASS | WARN (N issues) | FAIL
```

**On FAIL:** Describe exactly what is missing. Offer to re-dispatch Hermes with a broader
scope or ask user whether to proceed anyway.

**On PASS/WARN:** Proceed. Append any warnings to the KB log entry.

---

## Phase 5 — Spec Writer: Compile Directive (Gate 3 Check)

Generate the compile directive — the "build spec" that tells llm-knowledge-base what to
produce. Load the full instructions from `.agents/spec-writer.md`.

The compile directive instructs the KB compile to produce for every SAP article:

**Compile directive (Spec Writer output, Karpathy depth):**
Instructs llm-knowledge-base compile to emit for every SAP article:
- `## Implementation Pattern` — numbered steps, real runnable code
- `## Common Pitfalls` — error messages + fixes
- `## API Reference` — endpoint/CLI table (for entity articles)

**For `type: concept` articles:**
- `## Summary` — 2-3 sentence overview
- `## Details` — full explanation with subsections
- `## Implementation Pattern` — numbered steps, real runnable code
- `## Common Pitfalls` — 3-5 gotchas with error messages + fixes
- `## Connections` — wikilinks with relationship descriptions

**For `type: entity` articles (SAP services, tools, runtimes):**
- `## Summary` — what it is and when to use it
- `## Details` — full explanation
- `## API Reference` — table: `| Endpoint/Command | Purpose | Auth | Notes |`
- `## Common Pitfalls` — 3-5 gotchas
- `## Connections` — wikilinks

**Source confidence weights for SAP domains:**
```
help.sap.com           → official_documentation (0.95)
kyma-project.io        → official_documentation (0.95)
cap.cloud.sap          → official_documentation (0.95)
pages.github.tools.sap → internal_design_doc (0.90)
developers.sap.com     → tutorial (0.65)
community.sap.com      → community_forum (0.40)
*.launchpad.cfapps.*   → internal_design_doc (0.85)
```

**SAP entity types to extract:**
service, runtime, protocol, cli_tool, sdk, btp_service

**Gate 3 (Implementation Readiness) — proceed only if:**
- Compile directive is specific enough (subtopics, section requirements)
- New raw articles are on disk (`ls $KB_ROOT/raw/articles/web-sources/ | wc -l > 0`)
- Stop conditions are explicit (what to do if a subtopic has no source material)

---

## Phase 6 — Builder: KB Compilation

Drive the llm-knowledge-base skill compile pipeline.

### Step 6a — Cluster

```bash
cd "$KB_ROOT"
python3 scripts/cluster.py --kb-root .
```

Regenerates `scripts/clusters.json`. The new SAP articles will form or join a cluster.

### Step 6b — Dry Run

```bash
python3 scripts/compile.py --kb-root . --dry-run
```

Lists pending (uncompiled) raw articles. Confirm the new articles appear.

### Step 6c — Compile (invoke llm-knowledge-base skill)

Invoke the llm-knowledge-base compile following its SKILL.md protocol, passing the
compile directive from Phase 5 as the compilation instruction.

Key compile settings:
- Two-pass strategy: Sonnet stubs (Pass 1) → Opus synthesis (Pass 2)
- Batch size: 20 documents
- Resume on failure: `--resume` flag
- Priority sort: high cross-references first

**Save the compilation output** to `$COMPILE_SUMMARY` so Phase 8 can read it:
```bash
# Pipe or tee llm-knowledge-base compile output to the summary file
# The exact mechanism depends on how llm-knowledge-base outputs its summary.
# At minimum, manually write to $COMPILE_SUMMARY:
#   articles_created, articles_updated, entities_extracted, contradictions_flagged
```

### Step 6d — Post-compile

After compile, run:
```bash
python3 scripts/compile.py --kb-root . --dry-run
```

Verify the pending list is empty (or reduced to known gaps).

---

## Phase 7 — Requirement Reviewer: Lint (Gate 4)

```bash
cd "$KB_ROOT"
python3 scripts/lint.py --kb-root . --fix
```

**Gate 4 (Review Readiness) — pass only if:**
- Compilation summary exists (from llm-knowledge-base output)
- New wiki articles are on disk
- Lint ran (even if it found issues)

Parse the health dashboard:
- Health score < 70% → flag specific failing checks
- Stub articles > 5% → note for follow-up
- Contradiction flags > 0 → list affected articles

---

## Phase 8 — Release Summarizer

Load `.agents/release-summarizer.md` for the output format. Report:

```
SAP Orchestrator Complete
=========================
Topic:     <topic>
Pipeline:  KB Pre-Scan → Research → Critic Gate → Spec → Compile → Lint

Research (Hermes):
  Pages crawled:          N
  Articles saved:         N  → KB/raw/articles/web-sources/
  SAP internal (Browser Harness):  N
  Public (Firecrawl):              N

Compilation (llm-knowledge-base):
  Wiki articles created:  N
  Wiki articles updated:  N
  Entities extracted:     [entity names]
  Confidence — high: X | medium: Y | low: Z
  Contradictions flagged: N

KB Health (post-lint):
  Score:         N%
  Stubs:         N%
  Open questions: N
  Orphans:       N

New articles:
  - [[<slug>|<title>]] — <one-line summary>
  ...

Next:
  - Query: ask "how does <concept> work in <topic>?"
  - Deepen: /sap-orchestrator "<topic> advanced patterns"
  - Export: /llm-knowledge-base export training data
```

---

## Error Handling

| Error | Action |
|-------|--------|
| Hermes timeout (>30 min) | Report partial result if articles exist; skip Research Critic and ask user |
| Gate 2 FAIL | Describe gap precisely; offer re-dispatch or proceed with warning |
| Gate 2 WARN | Proceed; append warning to KB log |
| Gate 3: no articles on disk | Stop; something went wrong with Hermes — show last known error |
| Compile checkpoint exists | Resume from checkpoint automatically |
| Lint score < 70% | Flag; offer targeted re-compile for specific failed articles |
| VPN required but no internal pages | Warn in final summary; note which subtopics need VPN |

---

## Anti-Patterns (from prompt pack — enforced here)

- Never let Hermes output directly drive compilation — always pass Research Critic first
- Never assume blog posts or community posts are authoritative without citation
- Never mark compilation done without lint results
- Never ask Hermes to "research everything and build it" — scope must be specific
- Never mix SAP-internal URL handling with public researchers (different confidentiality)
- Never skip the gate checks to speed up the pipeline

---

## Agent Role Files

The `.agents/` directory alongside this SKILL.md contains the full system prompts for
each role in the pipeline, adapted from the multi-agent R&D prompt pack:

```
.agents/
  orchestrator.md          — this skill's operating instructions (reference)
  internal-researcher.md   — Hermes sap-researcher internal role
  public-researcher.md     — Hermes sap-researcher public role
  research-critic.md       — Research Critic gate instructions
  spec-writer.md           — Compile directive generator
  release-summarizer.md    — Final report format
  templates/
    intake.md              — User target intake form
    research-task.md       — Hermes task file template
    build-spec.md          — Compile directive template
    review-handoff.md      — Lint/quality review template

---

## KB Purpose and Article Quality Standards

**Why this KB exists:** Coding agents have no training data for non-open-source SAP
technologies (Kyma, Joule, BTP AppFoundation, CAP CDS, etc.). Every article must answer:
*"What does a developer need to produce working code with this today?"*

**Article structure, code completeness, and visualization standards** are defined in full in
`.agents/spec-writer.md`. Those requirements are read and applied in Phase 5 and flow
through the compile directive into the llm-knowledge-base compile step. Do not duplicate
them here — treat `.agents/spec-writer.md` as the single source of truth for article format.

**LLM Wiki pattern:** The KB is a persistent, compounding artifact — not a RAG index.
Every compile run should:
- Create new wiki articles for new subtopics
- Update existing wiki articles whose `## Connections` or `## Details` now have new
  information from the current research batch ("a single source may touch 10–15 pages")
- Produce synthesis pages when research spans multiple clusters (e.g. "How Kyma eventing
  and CAP event handlers compose")

**Query → File Back:** Valuable query answers (comparisons, analyses, discovered patterns)
should be filed back into the wiki as new pages — explorations compound just like ingested
sources do. Prompt the user at the end of Phase 8 with suggested follow-up queries that
would produce fileable synthesis pages.

### Article structure reference

Full section-order template, code completeness standard, and visualization rules:
→ `.agents/spec-writer.md` § Ground-Up Article Structure
