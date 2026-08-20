# DC25 vs ORF Instance Comparison

Benchmarked April 2026 with identical SPL queries on `index="msc_worktech-teams"`.

## Performance

| Query type | DC25 | ORF | Notes |
|-----------|------|-----|-------|
| Simple count (dev, 1h) | ~2.4s | ~3.3s | Identical results when filtered to same environment |
| Stats by environment (1h) | ~2.8s | ~9.7s | DC25: 11 envs, 82K events; ORF: 19 envs, 3.4M events |
| Errors by logger (dev, 1h) | ~2.4s | ~7.9s | Identical results |
| Raw events (dev, 1h, limit 10) | ~2.5s | ~8.3s | Identical events |
| Stats by environment (24h) | ~4.9s | ~50.2s | DC25: 1.8M; ORF: 58.9M (33x more data) |
| Hosts by environment (4h) | ~3.6s | ~14.3s | DC25: 11 envs; ORF: 19 envs |

ORF is slower because it scans data across all 37+ DCs. For dev-only queries, the overhead is ~3x. For unfiltered queries over 24h, it can be 10x slower due to 33x more data.

## Environments Visible

**DC25** (11): dev, qa, perf, staging1, staging2, and 6 others

**ORF** (19): everything on DC25 **plus** prod (~48M events/day), stage, dr, sales, perfendtoend, earlypreview, devdemo, hanacloud

## When to Use Which

- **DC25**: Dev/QA debugging — faster, same dev data
- **ORF**: Prod investigation, cross-environment comparison, cross-DC search — only instance that sees prod
- When filtered to `environment=dev`, both return identical results
