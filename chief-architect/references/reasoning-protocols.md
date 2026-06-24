# Reasoning Protocols

Six stages mapped to the operating loop. Each stage gives the exact internal
prompt to execute. Run all six for ADR-worthy decisions; run Stages 2 and 5
only for lightweight decisions.

---

## Stage 1 — Socratic Intake (Definition + missing-information check)

Before designing, execute:

> List every load-bearing term in the request that is undefined or vague.
> For each, either (a) reduce it to an atomic, measurable claim from context,
> or (b) add it to the clarifying-questions batch. A term is "load-bearing"
> if the design would change depending on its meaning.
>
> Then ask: What information is missing that would change the design?
> What am I assuming that the user has not actually said?

Ledger entry format:

| Term | Atomic definition | Source |
|---|---|---|
| "real-time" | p99 end-to-end latency < 200ms | user, 2026-06-10 |
| "scalable" | 10x current load (→ 5k rps) with < 2x cost | assumption — CONFIRM |

Rules:
- Mark assumptions explicitly and get them confirmed before the ADR is final.
- Never let an undefined term survive into Phase 3.

---

## Stage 2 — Step-Back Abstraction

Before proposing any structure, execute:

> Take a step back. Step 1: Abstract the key concepts, governing principles,
> and physical/organizational constraints relevant to this problem
> (consistency vs availability trade-offs, failure domains, data gravity,
> Conway's law given the team structure, cost of coordination, latency
> budgets, regulatory boundaries). Step 2: Only then reason from those
> principles toward concrete designs.

Output: a "Governing principles" list of 3–5 items, each one sentence,
each tied to a fact from intake. These reappear verbatim in the ADR's
Context section.

---

## Stage 3 — Analogical Recall

Before generating candidates, execute:

> Recall 2–3 known systems or published architectures that solved a
> structurally similar problem. For each: name it, state the structural
> similarity in one sentence, state what transfers, and state what does
> NOT transfer and why (scale, team, domain, or constraint mismatch).

The "what does NOT transfer" clause is mandatory — it is the guard against
cargo-culting Google-scale solutions onto five-person teams.

---

## Stage 4 — Branch and Converge (Tree-of-Thought + self-consistency)

Generate candidates:

> Produce 2–3 candidate architectures, each derived from a DIFFERENT
> starting principle (e.g., minimize cost; minimize p99 latency; minimize
> coordination across teams). Do not let candidates converge prematurely —
> derive each independently before comparing.

Then converge:

> Compare the candidates. Elements present in all independently derived
> candidates form the stable core — adopt them with high confidence.
> Elements where candidates diverge are the genuine decisions — these are
> what the ADR must argue. For each pruned branch, record in one sentence
> why it was pruned (this becomes the ADR's "Alternatives considered").

---

## Stage 5 — Reflect–Critique–Refine + Premortem

Run on the leading candidate before writing the ADR:

> REFLECT: State three specific ways this design could be wrong. For each,
> name the exact assumption the failure depends on.
>
> CRITIQUE: Examine each major design element and identify any errors —
> logical flaws, unverified claims, scaling cliffs, single points of
> failure, or steps you cannot verify from the intake facts.
>
> PREMORTEM: Assume it is 18 months from now and this architecture has
> failed in production. Write the three most plausible postmortem
> summaries (one sentence each). For each: is the cause already mitigated,
> mitigable cheaply now, or accepted as a recorded risk?
>
> REFINE: Modify the design only where the critique produced a new reasoning
> step — do not churn. Conclude with an explicit verdict: SOUND or REVISE.

The premortem outputs go into the ADR's Consequences/Risks section verbatim.

---

## Stage 6 — Review Elenchus (cross-examination of implementations)

When reviewing code or designs against the recorded architecture:

> For each structural element under review, ask: Which ADR or governing
> principle does this conform to or violate? Do not judge by taste —
> judge by the record. If the code violates an ADR, flag it with the ADR
> number. If the code is right and the ADR is wrong, say so and propose
> the ADR update. If neither covers the situation, that is a missing
> decision — draft the new ADR stub.
>
> Conclude each finding with: VIOLATION (ADR-NNNN) | DRIFT (update
> ADR-NNNN) | GAP (new ADR needed) | CONFORMS.

---

## Anti-patterns (do not do these)

- Running all six stages on trivial decisions — gate by stakes (see SKILL.md).
- Letting Stage 4 candidates share a starting principle — that fakes
  convergence and destroys the signal.
- Writing "could be wrong if requirements change" as a Stage 5 reflection —
  reflections must name a specific assumption and failure mode.
- Skipping the definitions ledger because the terms "seem obvious."
