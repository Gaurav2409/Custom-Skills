# OKF Specification Overview

Loaded when the user asks "what is OKF", "how does the spec work", or wants details on the format itself.

## What OKF Is

Open Knowledge Format (OKF) v0.1 is a Google Cloud open specification (June 2026) representing knowledge as **a directory of markdown files with YAML frontmatter**. It formalizes the "LLM-wiki" pattern (Karpathy gist) into a vendor-neutral interoperable standard.

- **Repository:** https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
- **Spec:** https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md (single page, 451 lines)
- **License:** Apache 2.0

## Core Concepts

| Term | Definition |
|------|-----------|
| **Knowledge Bundle** | Self-contained directory of knowledge documents. Unit of distribution. |
| **Concept** | One markdown file. Can describe a tangible asset (table, API), abstract idea (metric, process), or anything in between. |
| **Concept ID** | The file path within the bundle, with `.md` removed. e.g. `tables/users.md` → `tables/users` |
| **Frontmatter** | YAML metadata block delimited by `---` at the top of the file |
| **Body** | Everything in the file after the frontmatter |
| **Link** | Standard markdown link from one concept to another |

## YAML Frontmatter Spec

```yaml
---
type: <Type name>           # REQUIRED — only mandatory field
title: <display name>       # Recommended
description: <one-liner>    # Recommended
resource: <canonical URI>   # Recommended — links to underlying asset
tags: [<tag>, <tag>]        # Optional
timestamp: <ISO 8601>       # Optional
# … any producer-defined extensions
---
```

**Only `type` is required.** Type values are not registered centrally — producers choose descriptive strings (`BigQuery Table`, `API Endpoint`, `Metric`, `Playbook`). Consumers MUST tolerate unknown types gracefully.

## Reserved Filenames

| File | Purpose |
|------|---------|
| `index.md` | Directory listing for progressive disclosure |
| `log.md` | Update history, newest first, ISO 8601 date headings |

All other `.md` files are concept documents.

## Cross-Linking

Two link forms supported:

```markdown
# Absolute (bundle-relative — recommended for stability)
See [customers](/tables/customers.md).

# Relative
See [neighbor](./other.md).
```

Links assert relationships — the kind is conveyed by surrounding prose, not the link itself. Consumers MUST tolerate broken links.

## Conformance Rules (v0.1)

A bundle is conformant if:
1. Every non-reserved `.md` file has a parseable YAML frontmatter block
2. Every frontmatter block has a non-empty `type:` field
3. Reserved filenames (`index.md`, `log.md`) follow their defined structure when present

Consumers MUST NOT reject a bundle for: missing optional fields, unknown types, unknown extra frontmatter keys, broken cross-links, missing `index.md`.

## Three Design Principles

1. **Minimally opinionated** — only `type` required; producers add any keys; consumers tolerate unknowns
2. **Producer/consumer independence** — humans, agents, export pipelines all produce; static servers, Obsidian, LLMs all consume
3. **Format, not platform** — no SDK, no proprietary account, no required runtime

## Comparison to Other Formats

| Format | Relation to OKF |
|--------|-----------------|
| **DCAT (W3C)** | RDF-based, complex, requires SPARQL. OKF can `resource:` link to a DCAT record. |
| **schema.org** | Web-page semantics via JSON-LD. Different problem space. |
| **Frictionless Data Package** | Older OKFN spec (2007). JSON descriptor + tabular focus. Different goal. |
| **OpenAPI / Protobuf / Avro** | OKF references these via `resource:`, doesn't replace them. |
| **Obsidian vaults** | Compatible — OKF bundles open as vaults directly. |
| **CLAUDE.md / AGENTS.md** | Same family; OKF extends to multi-file bundles. |
| **RAG (vector)** | Different use case. OKF stores *curated, cross-linked concepts*; RAG re-derives knowledge from chunks at query time. |

## Why OKF Succeeds Where RDF/DCAT Struggled

> "Less schema beats more." — OKF's architectural bet.

OWL/RDF required typed relationships, schema registries, and specialized tooling. The Semantic Web never achieved broad adoption because the producer burden was too high. OKF demands almost nothing from producers (one field) and rich tolerance from consumers.

## Versioning

`<major>.<minor>` semver:
- Minor bump: backward-compatible (new optional fields, new conventional headings)
- Major bump: may rename required fields, change reserved filenames

Bundles MAY declare `okf_version: "0.1"` in root `index.md` frontmatter.

## Karpathy LLM Wiki — The Precursor

Karpathy's April 2026 gist described a three-layer pattern OKF formalizes:

| Layer | Contents | Role |
|-------|----------|------|
| **Raw** | Original source docs | Immutable |
| **Wiki** | LLM-compiled interlinked markdown | Compiled, queryable |
| **Schema** | CLAUDE.md / AGENTS.md | Conventions |

Karpathy's insight: "LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass."

OKF adds: agreed YAML schema, reserved filenames, conformance rules, reference implementations.

## KB Articles in agentic-rag-and-memory-kb

For deeper detail and citations:
- `wiki/concepts/open-knowledge-format.md`
- `wiki/entities/google-okf-knowledge-catalog.md`
- `wiki/topics/knowledge-as-code-for-agents.md`
