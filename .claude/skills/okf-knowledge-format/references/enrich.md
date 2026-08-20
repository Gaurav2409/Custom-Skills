# Enrich an OKF Bundle from a Data Source

Loaded when the user wants to generate/enrich a bundle from BigQuery, a database, or an existing data catalog.

## Google's Reference Enrichment Agent (BigQuery)

Repository: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf

### Install

```bash
git clone https://github.com/GoogleCloudPlatform/knowledge-catalog
cd knowledge-catalog/okf
python3.13 -m venv .venv
.venv/bin/pip install -e .[dev]
```

### Credentials

- **BigQuery:** `gcloud auth application-default login` + `gcloud config set project <id>`
- **Gemini:** `GEMINI_API_KEY` env var (AI Studio) **OR** Vertex AI: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT=<id>`, `GOOGLE_CLOUD_LOCATION=<region>`

### Two-Pass Architecture

**Pass 1 — BQ pass:** Walks BigQuery dataset, drafts OKF concept doc per table/view from metadata alone.

**Pass 2 — Web pass:** LLM-as-crawler. Fetches seed URLs via `fetch_url`, decides which links to follow, enriches existing concepts with citations or mints `references/<slug>` docs.

### Run

```bash
# Minimum invocation
.venv/bin/python -m enrichment_agent enrich \
    --source bq \
    --dataset <project>.<dataset> \
    --web-seed-file seeds.txt \
    --out ./bundles/<name>

# BQ-only (skip web pass)
.venv/bin/python -m enrichment_agent enrich \
    --source bq \
    --dataset <project>.<dataset> \
    --no-web \
    --out ./bundles/<name>

# Iterate single concept
--concept tables/orders   # repeatable
```

Hard caps: `--web-max-pages` and `--web-allowed-host` prevent runaway crawling.

## Enriching from Any Database (Manual Pattern)

```python
import sqlalchemy, yaml
from pathlib import Path

def enrich_postgres_to_okf(conn_url, schema, bundle_dir):
    engine = sqlalchemy.create_engine(conn_url)
    inspector = sqlalchemy.inspect(engine)
    Path(bundle_dir, "tables").mkdir(parents=True, exist_ok=True)

    for table in inspector.get_table_names(schema=schema):
        cols = inspector.get_columns(table, schema=schema)
        fk = inspector.get_foreign_keys(table, schema=schema)

        fm = {
            "type": "PostgreSQL Table",
            "title": table,
            "description": f"Table {schema}.{table}",
            "resource": f"{conn_url}/{schema}/{table}",
            "tags": [schema, "postgres"],
        }

        body = "# Schema\n\n| Column | Type | Description |\n|---|---|---|\n"
        for c in cols:
            body += f"| `{c['name']}` | {c['type']} | |\n"

        if fk:
            body += "\n# Joins\n\n"
            for f in fk:
                target = f['referred_table']
                body += f"- Joins with [{target}](/tables/{target}.md) on `{f['constrained_columns'][0]}`\n"

        content = "---\n" + yaml.dump(fm, sort_keys=False) + "---\n\n" + body
        Path(bundle_dir, "tables", f"{table}.md").write_text(content)
```

## Enriching from an Existing Data Catalog

Map catalog fields to OKF frontmatter:

| Source catalog field | OKF field |
|---------------------|-----------|
| `display_name` / `label` | `title` |
| `description` | `description` |
| `fully_qualified_name` / browser URL | `resource` |
| `labels` / `tags` | `tags` |
| `modified_time` / `updated_at` | `timestamp` |
| `type` / `kind` / `entity_kind` | `type` |
| `schema_definition` | rendered as table in body |
| `lineage` / `relationships` | rendered as cross-links in body |

### Example: Dataplex export

```bash
gcloud dataplex entities list --location=us-central1 --lake=mylake \
  --project=$PROJECT --format=json > dataplex_entities.json

python3 dataplex_to_okf.py dataplex_entities.json ./bundles/dataplex/
```

```python
# dataplex_to_okf.py
import json, sys, yaml
from pathlib import Path

entities = json.load(open(sys.argv[1]))
out = Path(sys.argv[2])

for e in entities:
    fm = {
        "type": e.get("type", "Dataplex Entity"),
        "title": e["displayName"],
        "description": e.get("description", ""),
        "resource": e["dataPath"],
        "tags": list(e.get("labels", {}).keys()),
        "timestamp": e["updateTime"],
    }
    slug = e["id"].replace(":", "_")
    content = "---\n" + yaml.dump(fm, sort_keys=False) + "---\n\n# Schema\n\n" + e.get("schemaDescription", "")
    (out / "entities" / f"{slug}.md").parent.mkdir(parents=True, exist_ok=True)
    (out / "entities" / f"{slug}.md").write_text(content)
```

## Enriching from Code (dbt models, OpenAPI, Protobuf)

Treat the source schema as authoritative; generate OKF concepts that *reference* it via `resource:` rather than duplicate the schema:

```yaml
---
type: dbt Model
title: fct_orders
description: Fact table for completed orders, one row per order
resource: github.com/acme/dbt-warehouse/models/marts/fct_orders.sql
tags: [dbt, fact, sales]
timestamp: 2026-06-17T00:00:00Z
---

# Description

(Free-form prose explaining intent, business logic, common gotchas — content
that doesn't fit in dbt schema.yml but agents need to know.)

# Upstream

Built from [stg_orders](/staging/stg_orders.md) and [dim_customers](/marts/dim_customers.md).

# Citations

[1] [dbt model definition](github.com/acme/dbt-warehouse/models/marts/fct_orders.sql)
[2] [Business definition of "completed order"](https://wiki.acme.com/orders-spec)
```
