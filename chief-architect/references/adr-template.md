# ADR Template (MADR-style, extended)

File: `docs/adr/NNNN-short-kebab-title.md`. Number sequentially. Never delete
an ADR — supersede it (set status and link both ways).

```markdown
# ADR-NNNN: <Short decision title in imperative form>

- Status: proposed | accepted | superseded by ADR-MMMM | deprecated
- Date: YYYY-MM-DD
- Deciders: <people/agents involved>
- Tags: <e.g., data, messaging, security>

## Context

What is the issue, in 3–6 sentences. Include:
- The governing principles from Stage 2 that apply (verbatim).
- The relevant atomic definitions from the definitions ledger.
- The constraint that forces a decision now.

## Decision drivers

- <driver 1, tied to an NFR or constraint, e.g., "p99 < 200ms (ledger)">
- <driver 2>
- <driver 3>

## Considered options

1. <Option A — one-line summary>
2. <Option B — one-line summary>
3. <Option C — one-line summary>

## Decision

Chosen option: <Option X>, because <single strongest reason tied to a
decision driver>.

## Trade-off analysis

| Driver | Option A | Option B | Option C |
|---|---|---|---|
| <driver 1> | good/bad + why | … | … |
| <driver 2> | … | … | … |
| Operational complexity | … | … | … |
| Cost (build + run) | … | … | … |
| Reversibility | … | … | … |

## Rejected alternatives

For each non-chosen option, one or two sentences: why it was pruned
(from Stage 4 convergence notes).

## Consequences and risks

- Positive: <what becomes easier>
- Negative: <what becomes harder — be honest>
- Premortem risks (from Stage 5): for each — risk, likelihood, and whether
  it is mitigated / mitigable / accepted.

## What would change this decision

Explicit triggers for revisiting: <e.g., "sustained load exceeds 5k rps",
"team grows past 3 squads", "vendor pricing changes >2x">.
```

## Rules

- One decision per ADR. If you are writing "and" in the title, split it.
- Trade-off rows must reference decision drivers, not generic virtues.
- The "What would change this decision" section is mandatory — an ADR
  without falsification conditions is an opinion, not a decision.
- Mini-ADR (for lightweight decisions): Context (2 sentences), Decision,
  one-line rejected alternatives, change triggers. Still numbered and filed.
