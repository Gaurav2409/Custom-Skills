# Compile Directive Template (Build Spec for llm-knowledge-base)

This template is filled by the Spec Writer and passed to the llm-knowledge-base skill
as the compilation instruction. It replaces the generic compile prompt with SAP-specific
depth requirements.

---

## Objective

Compile [N] raw articles covering "[topic]" into wiki articles with deep implementation
depth: problem motivation, core abstraction, runnable code, API references, and real pitfalls.

**This is an incremental wiki update, not a fresh build.** The wiki already contains existing
articles. For every new article produced:

1. Check `_index.md` — if an article on this subtopic already exists, UPDATE it (revise
   `## Details`, extend `## Connections`, add any new pitfalls found). Do not create a
   duplicate page.
2. Scan existing wiki articles for any that should now link to the new content — update
   their `## Connections` sections with the new wikilink. A single new article may touch
   5–15 existing pages.
3. If multiple new articles cover related subtopics, produce a synthesis page
   (e.g. "How [subtopic-A] and [subtopic-B] compose") — file it as `type: topic`.

## Background

[2-3 sentences from the research result file about what was found and why it matters for
coding agents working with this SAP technology.]

## Source-grounded findings for compile context

[Key facts (with source citations) that the compile LLM should know when writing articles.
These are the "research briefing" — not the full articles, just the key architectural facts.]

Example format:
> Kyma eventing uses NATS JetStream under the hood and exposes Kubernetes CRDs (Subscription,
> EventingBackend). Source: kyma-project.io/docs/main/05-technical-reference/eventing/

## Functional requirements (must-have sections)

Article sections are governed by the Ground-Up Article Structure defined at the end of this
directive. Required sections by article type:

| Type            | Required sections                                                                          |
| --------------- | ------------------------------------------------------------------------------------------ |
| Every article   | Why This Exists, Mental Model, Architecture Overview, Minimal Working Example, Connections |
| `type: concept` | + Full Implementation Pattern, Common Pitfalls                                             |
| `type: entity`  | + API Reference (≥3 rows), Common Pitfalls                                                 |
| `type: topic`   | + Full Implementation Pattern, Connections                                                 |

Pending placeholder when code is unavailable:
`> [Implementation pattern pending — no code example found in sources. Add from: <url>]`

## Non-functional requirements

- Minimum article length: 400 words (hard cutoff for stubs)
- Every article with a `Has-Code: true` source must have at least one fenced code block
- Code blocks must be labeled with the language: ` ```typescript `, ` ```yaml `, etc.
- Wikilinks must use `[[slug|Display Name]]` syntax (not markdown links)
- Source paths must use `../../raw/` prefix (two levels deep from `wiki/concepts/` etc.)

## SAP entity types to extract

service, runtime, protocol, cli_tool, sdk, btp_service

## Source confidence weights

```text
help.sap.com:              official_documentation (0.95)
kyma-project.io:           official_documentation (0.95)
cap.cloud.sap:             official_documentation (0.95)
pages.github.tools.sap:    internal_design_doc    (0.90)
developers.sap.com:        tutorial               (0.65)
community.sap.com:         community_forum        (0.40)
*.launchpad.cfapps.*:      internal_design_doc    (0.85)
```

## Out of scope

[Subtopics from the task file that had zero source coverage. These need a follow-up pass.]

## Acceptance criteria

- [ ] Every requested subtopic has at least one wiki article
- [ ] Every article ≥400 words
- [ ] Implementation Pattern sections use numbered steps, not prose
- [ ] API Reference tables have ≥3 rows for SAP service entities
- [ ] No article cites only `community_forum` sources without a `confidence: low` frontmatter
- [ ] Entity registry updated with new SAP service/entity entries
- [ ] `_summaries.md` updated with one-paragraph summary per raw article compiled

## Assumptions

[List any `[ASSUMPTION]` items from the Research Critic that were carried into this directive.]

## Stop conditions for llm-knowledge-base

- Stop if a required subtopic has no raw article covering it — write a stub with
  `review_status: stub` and `## Open Questions: source material needed`
- Stop if contradiction detection flags a factual conflict — flag the article with
  `review_status: flagged-contradiction`, do not guess which source is correct
- Stop if an Implementation Pattern requires code but no source has code — use the
  pending placeholder and mark `Has-Code: false`

---

## Ground-Up Article Structure

**Purpose:** Articles must enable a developer to produce working code immediately after
reading — with no gaps requiring external lookup. Every article follows this section order
so the reader builds understanding progressively.

### Required section order

```text
1. ## Why This Exists
   One paragraph. The problem this technology solves.
   No jargon. Written for a senior engineer from a non-SAP background.
   Example: "Before Kyma eventing existed, wiring SAP S/4HANA events to a handler
   required a custom polling loop or an expensive middleware layer..."

2. ## Mental Model
   The core abstraction in plain language. One analogy that makes it click.
   Example: "A Kyma API Rule is like an nginx ingress annotation, but declarative
   and enforced by Istio — you describe the route and auth policy, Kyma wires it."

3. ## Architecture Overview
   ASCII diagram. Mandatory. Every article, no exceptions.
   Show: components, data flow, where the developer's code plugs in.

   Box-and-arrow format:
   ┌─────────────┐       ┌──────────────┐       ┌─────────────┐
   │  Component A │──▶   │  Component B  │──▶   │  Component C │
   └─────────────┘       └──────────────┘       └─────────────┘

   Sequence format (for multi-step flows):
   1. Developer code ──▶ CAP service  (OData PATCH /Orders(1))
   2. CAP service    ──▶ HANA Cloud   (@cds.on.UPDATE handler fires)
   3. CAP service    ──▶ Kyma broker  (emit OrderUpdated CloudEvent)

4. ## Minimal Working Example
   Smallest complete snippet that works end-to-end.
   - Copy-paste runnable. No abstract placeholders.
   - Complete file, not a fragment. All imports included.
   - Under 30 lines. Labeled language. One comment line saying what it does.
   - Use realistic dummy values: "my-kyma-ns", "my-cap-srv", "order-handler".

5. ## Full Implementation Pattern  (concept articles)
   Numbered walkthrough from prerequisites to deployed and verified:
   - Prerequisite: BTP entitlements, CLI tools, service instances needed
   - Config file: full minimal mta.yaml / xs-security.json / subscription.yaml
   - Core code: complete file with all imports and error handling
   - Local test command (cds bind --exec, kubectl port-forward, etc.)
   - Deploy command and how to verify it worked

6. ## API Reference  (entity articles — SAP services, runtimes, CLI tools)
   Table: | Endpoint / Command | Purpose | Auth Required | Notes |
   Minimum 3 rows. Include both REST endpoint and equivalent CLI command where both exist.

7. ## Common Pitfalls
   3–5 items from real source material (not invented).
   Format: **Pitfall**: `exact error message` → Fix: concrete solution.
   Include the exact error string a developer would see in their terminal or logs.

8. ## Connections
   [[wikilink|Display Name]] — one sentence on the relationship.
```

### Code completeness standard

- Minimal Working Example must run without modification. Realistic dummy values only.
- Full Implementation Pattern: complete file — not a fragment, not `// ... rest of code`.
- Every YAML/JSON config: show the complete minimal file.
- Every code block: labeled language, one descriptive comment at the top.
- Both happy path AND error handling shown in Full Implementation Pattern.
- Preferred languages: TypeScript/JS for CAP, Python for AI Core, shell for CLI, YAML for CRDs.

### Visualization standard

- Architecture Overview uses Unicode box-drawing: `┌ ─ ┐ └ ┘ │ ──▶`
- If source has an image/SVG diagram, reconstruct its structure in ASCII.
  Never skip the diagram section because the original was not text.
- State machines: use a State | Event → Next State table.
- Layered architectures: stack boxes vertically with labels on each layer.
