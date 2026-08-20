# Create an OKF Bundle

Loaded when the user asks to create / scaffold / build a new OKF bundle.

## Procedure

### 1. Scaffold structure

```bash
BUNDLE_ROOT=<path>
mkdir -p "$BUNDLE_ROOT"/{datasets,tables,metrics,playbooks,apis,references}
```

Adjust subdirectories to match the domain — they're producer-defined, not specified.

### 2. Create root `index.md`

```markdown
# <Bundle Name> — Knowledge Bundle

> OKF v0.1 bundle. See [SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).

## Datasets
* [Sales](datasets/sales.md) — transactional sales data
* [Inventory](datasets/inventory.md) — current stock levels

## Tables
* [Orders](tables/orders.md) — completed orders
* [Customers](tables/customers.md) — customer records
```

`index.md` files have NO frontmatter. They are pure directory listings.

### 3. Concept document template

Every concept is one `.md` file:

```markdown
---
type: <Type>                  # REQUIRED — e.g. "BigQuery Table", "Metric", "Playbook"
title: <Display name>
description: <One-line summary>
resource: <Canonical URI>     # Optional — link to actual asset
tags: [<tag1>, <tag2>]
timestamp: <ISO 8601>         # e.g. 2026-06-17T00:00:00Z
---

# Schema

| Column | Type | Description |
|--------|------|-------------|

# Examples

```sql
SELECT ...
```

# Joins

Joined with [other-table](/tables/other.md) on `key_column`.

# Citations

[1] [Source title](https://url)
```

### 4. Cross-link concepts

Use **bundle-relative links** (start with `/`) for stability when files move:

```markdown
See the [orders table](/tables/orders.md) for transaction data.
See [neighbor](./other.md) for sibling-only references.
```

### 5. Add `log.md` for history

```markdown
# Bundle Update Log

## 2026-06-17
* **Initialization**: Created bundle structure.
* **Creation**: Added [orders table](/tables/orders.md).

## 2026-06-15
* **Update**: Schema change in [customers](/tables/customers.md) — added `region` column.
```

Date headings MUST be ISO 8601 `YYYY-MM-DD`. Bold prefixes (`**Update**`, `**Creation**`, `**Deprecation**`) are conventional, not required.

### 6. Validate before shipping

See `references/validate.md`.

## Type Conventions (not registered — just descriptive)

Common type values seen in the wild:
- `BigQuery Table` / `BigQuery Dataset` / `BigQuery View`
- `API Endpoint` / `REST API` / `GraphQL Schema`
- `Metric` / `KPI`
- `Playbook` / `Runbook`
- `Reference` / `Documentation`
- `Schema` / `Service` / `Component`

Pick descriptive, self-explanatory strings. Consumers won't reject unknown types.

## Distribution Options

A bundle MAY be distributed as:
- **Git repository** (recommended — provides history, attribution, diffs)
- **Tarball or zip** archive of the directory
- **Subdirectory** within a larger repo

## Tips for Agent-Friendly Bundles

- Favor structural markdown (headings, lists, tables, fenced code) over freeform prose — easier for agents to extract
- Use `index.md` files in every directory for progressive disclosure
- Keep concept files focused (one concept per file) — better than monolithic docs
- Use `tags:` consistently — they enable fast metadata filtering by consumer agents
