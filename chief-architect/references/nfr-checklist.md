# NFR Checklist (Quality Attributes)

Walk this in Phase 3 for every candidate architecture. For each attribute:
either record an atomic target in the definitions ledger, or explicitly mark
it "not a driver" — silence is not allowed. An NFR without a number is a
wish.

## Performance & scale
- [ ] Peak and sustained request rate (rps) — now and at 10x
- [ ] p50 / p99 latency budgets per critical path (end-to-end, not per hop)
- [ ] Data volume: current, growth rate, retention requirement
- [ ] Read/write ratio and hot-spot expectations
- [ ] Batch vs interactive workloads and their isolation

## Availability & reliability
- [ ] Availability target per component (99.9%? 99.99%?) and the REAL cost
      of each extra nine
- [ ] RTO / RPO for each data store
- [ ] Failure domains: what fails together? blast radius of each dependency
- [ ] Degradation plan: what still works when dependency X is down
- [ ] Idempotency and retry semantics for every cross-boundary write

## Consistency & data
- [ ] Where is strong consistency genuinely required (money, inventory,
      auth) vs where is eventual acceptable
- [ ] Source of truth per entity — exactly one
- [ ] Migration/backfill strategy for schema evolution

## Security & compliance
- [ ] AuthN/AuthZ model; tenant isolation mechanism if multi-tenant
- [ ] Data classification: PII/PHI/payment data, where it lives, encryption
      at rest and in transit
- [ ] Regulatory constraints (GDPR, DPDP, HIPAA, PCI, SOC2) and data
      residency requirements
- [ ] Secrets management and rotation
- [ ] Audit trail requirements

## Cost
- [ ] Build cost (team-months) and run cost ($/month) per candidate —
      order-of-magnitude estimates are fine, absence is not
- [ ] Cost cliffs: what gets 10x more expensive at 10x load
- [ ] Vendor lock-in: exit cost in team-months

## Operability
- [ ] Observability: metrics, traces, logs — what question must each answer
- [ ] Deployment: rollout strategy, rollback time
- [ ] On-call surface: how many distinct things can page a human
- [ ] Local development story: can one engineer run it on a laptop

## Team & evolution (Conway check)
- [ ] Component boundaries vs team boundaries — do they match?
- [ ] Skills required vs skills present
- [ ] What is most likely to change in 6–18 months — is it isolated behind
      a boundary?
- [ ] Reversibility: which decisions are one-way doors? (Those get the full
      reasoning protocol.)

## Verdict format

For each candidate, output a table: attribute → meets / risks / fails,
with one-line justification tied to the ledger numbers. Candidates that
fail a hard driver are pruned with that reason recorded.
