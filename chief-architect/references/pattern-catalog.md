# Pattern Catalog — When and When NOT

Patterns are trade-offs, not virtues. Every "use when" has a "do NOT use
when" — cite both in ADRs. Default bias: the simplest structure that meets
the ledger numbers.

## System shape

### Modular monolith (default starting point)
- Use when: single team or few teams, unproven domain boundaries, need speed.
- Do NOT split into services because "we might scale" — split when a ledger
  number or team boundary demands it.
- Discipline required: enforce module boundaries (no cross-module imports
  except via public interfaces) so future extraction is cheap.

### Microservices
- Use when: multiple teams need independent deploy cadence; components have
  genuinely different scaling/availability profiles; boundary is stable.
- Do NOT use when: team < ~3 squads, domain boundaries still shifting, or
  ops maturity (CI/CD, observability, on-call) is absent. Distributed
  systems convert design problems into operational problems.

### Event-driven architecture
- Use when: natural domain events exist, consumers evolve independently,
  spikes need absorbing, audit trail is a requirement.
- Do NOT use for request/response flows that need an answer now; beware
  hidden coupling via event schemas — version them from day one.
- Always decide: at-least-once + idempotent consumers (default) vs
  effectively-once machinery (expensive).

### Serverless / FaaS
- Use when: spiky or low baseline traffic, event-glue workloads, small team.
- Do NOT use when: p99 latency budget is tight (cold starts), long-running
  work, or heavy sustained load (cost cliff).

## Internal structure

### Layered / Clean Architecture / Hexagonal (ports & adapters)
- Core rule: dependencies point inward; the domain core imports no
  framework, no database, no transport.
- Use when: the domain has real logic worth protecting from infrastructure
  churn.
- Do NOT impose four layers on a CRUD service — that is ceremony, not
  architecture. CRUD earns transaction-script simplicity.

### Domain-Driven Design (strategic)
- Use bounded contexts to slice large domains; the context map IS the
  service map candidate.
- Ubiquitous language feeds the definitions ledger directly.
- Do NOT apply tactical DDD (aggregates, repositories everywhere) to
  simple domains — strategic DDD scales down, tactical mostly doesn't.

### CQRS
- Use when: read and write shapes/loads differ by an order of magnitude.
- Do NOT pair with event sourcing by default. CQRS without ES is common
  and fine.

### Event sourcing
- Use when: the history IS the requirement (ledgers, compliance, temporal
  queries).
- Do NOT use as a generic persistence choice — replay, versioning, and
  GDPR-deletion complexity are permanent taxes.

## Data

### One database per service (when split)
- Services share data via APIs/events, never via reaching into each other's
  tables. A shared database between "services" means you built a
  distributed monolith.

### Caching
- Decide explicitly: TTL vs invalidation; cache-aside (default) vs
  write-through; stampede protection at high fan-out.
- Every cache is a consistency decision — record staleness tolerance in
  the ledger.

### Saga / outbox
- Cross-service writes need either an orchestrated saga or
  choreography + outbox pattern. "We'll call both and hope" fails review.

## Integration

### Synchronous REST/gRPC
- Default for query paths and low fan-out commands. Set timeouts, retries
  with backoff + jitter, and circuit breakers at every boundary — these are
  not optional extras, they are part of the call.

### API gateway / BFF
- Use BFF when client shapes diverge (mobile vs web). Do NOT put business
  logic in the gateway.

## Selection procedure

1. Start from the modular monolith; demand a ledger-backed reason to depart.
2. For each departure, name the pattern, the driver, and the tax you accept.
3. Check the combination against the NFR checklist — patterns interact
   (e.g., microservices + strong consistency across services = pain you
   must explicitly accept or design away).
