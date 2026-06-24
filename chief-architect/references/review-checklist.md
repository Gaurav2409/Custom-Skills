# Architecture Review Checklist

Used in Phase 7 — reviewing code changes, PRs, or existing systems against
the recorded architecture. Judge by the record (ADRs, ledger, diagrams),
not by taste. Use the verdict vocabulary from reasoning-protocols.md
Stage 6: VIOLATION (ADR-NNNN) | DRIFT (update ADR-NNNN) | GAP (new ADR
needed) | CONFORMS.

## 0. Preparation
- [ ] Read the ADR index and the definitions ledger before reading code.
- [ ] Identify which ADRs the change plausibly touches.

## 1. Boundaries & dependencies
- [ ] Dependency direction: domain core imports no infrastructure,
      framework, or transport code.
- [ ] No module/service reaches into another's database tables or private
      internals.
- [ ] New external dependency? It needs an ADR (GAP if missing).
- [ ] Circular dependencies between modules/services — automatic VIOLATION.

## 2. Contracts
- [ ] API/event schema changes are backward compatible or versioned.
- [ ] Every cross-boundary call has timeout, retry policy, and failure
      behavior defined.
- [ ] Every cross-boundary write is idempotent or carries an idempotency key.
- [ ] Error contracts: callers can distinguish retryable from terminal.

## 3. SOLID / coupling (component scale)
- [ ] Single responsibility at the module level: can you state each
      module's job in one sentence without "and"?
- [ ] Interfaces owned by consumers (ports), implementations by adapters.
- [ ] Shared "utils/common" growth — flag as coupling smell; propose a home.

## 4. Data
- [ ] Exactly one source of truth per entity; derived copies are labeled
      as derived with a staleness bound.
- [ ] Migrations are reversible or have a tested rollback note.
- [ ] PII/regulated data placement matches the ADR'd classification.

## 5. Failure & operations
- [ ] New failure modes introduced? Each is observable (metric/alert named).
- [ ] Blast radius of the change: what else can this take down?
- [ ] Degradation behavior matches the recorded plan.

## 6. Drift handling
- [ ] Code contradicts an ADR but the code is right → propose ADR update
      in the same review (DRIFT), don't just flag the code.
- [ ] Repeated drift in the same area → escalate: the boundary itself may
      be wrong; schedule a Phase 1–4 redesign of that boundary.

## Output format

```
## Architecture Review — <scope> — <date>
Verdict summary: N conforms / N violations / N drift / N gaps

1. [VIOLATION — ADR-0007] OrderService writes directly to inventory.items.
   ADR-0007 mandates event-based inventory updates. Fix: publish
   order.allocated; consume in inventory worker.
2. [GAP] New Redis dependency has no ADR. Drafted stub: docs/adr/0012-*.md
3. [DRIFT — ADR-0003] ...
```

Every finding: verdict tag, evidence (file/line or component), the recorded
decision it relates to, and a concrete fix or next step. No untagged
opinions.
