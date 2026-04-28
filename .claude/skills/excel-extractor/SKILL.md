---
name: excel-extractor
description: Extract content from large Excel (.xlsx) files for data analysis, agentic systems, and knowledge graphs. Use when the user wants to profile an xlsx file, extract sheets to CSV/JSON/JSONL, stream 100k+ row sheets without memory errors, generate entity-relationship schemas, or prepare data for ingestion into a knowledge base or agent pipeline. Trigger phrases include "extract from Excel", "profile xlsx", "convert Excel to CSV", "build schema from spreadsheet", "ingest Excel into KB", "Excel to knowledge graph".
---

# Excel Extractor

Read, profile, and extract data from `.xlsx` files — including files with millions of rows and dozens of sheets — into CSV, JSON, JSONL, or Markdown. Automatically streams large sheets using `openpyxl`'s `read_only` mode to avoid memory errors.

```
BAC_Mapping_Sheet.xlsx  (34 MB, 27 sheets)
        │
        ├── Phase 0: Understand request
        ├── Phase 1: Setup (install deps, copy script)
        ├── Phase 2: Profile (sheet inventory, row counts, header preview)
        ├── Phase 3: Extract (full / streaming / filtered)
        ├── Phase 4: Schema (entity map, FK detection, graph JSONL)
        ├── Phase 5: Output formats (CSV / JSON / JSONL / Markdown)
        ├── Phase 6: LLM-ready chunking + manifest.json
        ├── Phase 7: Troubleshooting
        ├── Phase 8: Sanitize (remove PII — names, employee IDs)
        └── Phase 9: Join (resolve FK relationships across sheets)
```

---

## Phase 0: Understand the Request

Determine which operation the user wants:

| Operation | When to use |
|-----------|-------------|
| **Profile** | First step — shows all sheet names, row counts, column counts, header preview, memory estimate |
| **Extract** | Pull one or more sheets to CSV/JSON/JSONL/Markdown |
| **Sample** | Pull first N rows (default 100) for fast exploration without full extraction |
| **Schema** | Generate entity-relationship map + FK graph for knowledge graph building |
| **Summarize** | LLM-friendly description of every sheet — what it contains, what the key columns are |

If ambiguous, ask:

> "What would you like to do with `<filename>.xlsx`?
> - **Profile**: Inventory all sheets — names, sizes, and column headers
> - **Extract**: Export sheets to CSV/JSON/JSONL files
> - **Schema**: Generate an entity-relationship map for knowledge graph building
> - **Sample**: Pull the first N rows for quick exploration"

---

## Phase 1: Setup

### 1.1 Install dependencies

Both `openpyxl` and `pandas` are required:

```bash
pip install openpyxl pandas
```

Verify:

```bash
python3 -c "import openpyxl, pandas; print('openpyxl', openpyxl.__version__, '| pandas', pandas.__version__)"
```

The script exits with a clear error and install hint if either is missing.

### 1.2 Copy the extractor script

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/skills-repo -type d -name "excel-extractor" 2>/dev/null | head -1)
cp "$SKILL_DIR/templates/scripts/extractor.py" ./extractor.py
```

Or ask Claude to write `extractor.py` from the template embedded in this skill.

### 1.3 Verify the Excel file

```bash
python3 -c "
from pathlib import Path
p = Path('<xlsx_path>')
print('Exists:', p.exists(), '| Size:', round(p.stat().st_size / 1024 / 1024, 1), 'MB')
"
```

---

## Phase 2: Profile the File

### 2.1 Run profile

```bash
python3 extractor.py "<xlsx_path>" --op profile
```

Expected output:

```
Excel File Profile
==================
File: BAC_Mapping_Sheet.xlsx  (34 MB)
Sheets: 27

Sheet                              rows    cols   xml_MB  category
------------------------------------------------------------------
Sanity Check Overview                88      17      0.0  SMALL
Target BAC                         2949      31     16.0  MEDIUM
BAC Element Definition             5534      79     44.5  MEDIUM
Technical Object Assignment       10052      23     22.1  MEDIUM
Content Assignment                 9996      69    114.6  LARGE
Business Areas                      900      28      0.1  SMALL
...

Categories:
  SMALL   (xml < 1 MB)   — safe to load fully
  MEDIUM  (1–50 MB)      — loads fine; streaming available via --op stream
  LARGE   (xml > 50 MB)  — streaming auto-enabled; never loads full sheet into RAM

⚠ Multi-row headers detected on: BAC Element Definition, Technical Object Assignment
  Row 1 = column names, Row 2 = lock annotations / sanity codes
  Use --header-row 2 to skip the annotation row, or leave at default (--header-row 1)
```

**NOTE:** `rows` is the actual count of `<row>` elements in the XML — NOT the OOXML `dimension` attribute, which can report `A1:W1045675` for a sparse sheet with only 10,052 actual rows.

### 2.2 Multi-row header detection

The profiler flags sheets where row 2 looks like annotation codes rather than data (short codes, lock phrases, status strings). You can:

- `--header-row 1` (default): row 1 is the header, row 2 is treated as data
- `--header-row 2`: row 2 is the header, row 1 is discarded, data starts at row 3
- `--header-row combined`: rows 1+2 merged as `"Row1: Row2"` compound headers

---

## Phase 3: Extract Operations

### 3.1 Extract all sheets

```bash
python3 extractor.py "<xlsx_path>" --op extract --sheet all --format csv
```

### 3.2 Extract a specific sheet

```bash
python3 extractor.py "<xlsx_path>" --op extract --sheet "BAC Element Definition" --format jsonl
```

### 3.3 Sample N rows (fast exploration)

```bash
python3 extractor.py "<xlsx_path>" --op sample --sheet "Business Areas" --max-rows 50
```

Prints a markdown table to stdout — no files written.

### 3.4 Column filter

```bash
python3 extractor.py "<xlsx_path>" --op extract --sheet "BAC Element Definition" \
  --columns "BAC Element ID,Title,BAC Element Type,Business Area,Business Package,Business Topic"
```

### 3.5 Multi-row header handling

```bash
# Skip annotation row — treat row 1 as headers, data from row 2 (default):
python3 extractor.py "<xlsx_path>" --op extract --sheet "BAC Element Definition" --header-row 1

# Use row 2 as header, skip row 1, data from row 3:
python3 extractor.py "<xlsx_path>" --op extract --sheet "BAC Element Definition" --header-row 2

# Combine both rows into compound "Row1: Row2" headers:
python3 extractor.py "<xlsx_path>" --op extract --sheet "BAC Element Definition" --header-row combined
```

### 3.6 Streaming (auto-triggered for large XML)

Streaming is automatically activated for sheets whose XML exceeds `--stream-threshold` (default 50 MB). Rows are written incrementally in chunks — only `--chunk-size` rows are in memory at a time.

Force streaming explicitly:

```bash
python3 extractor.py "<xlsx_path>" --op stream --sheet "Content Assignment" --chunk-size 1000
```

Output during streaming:

```
[stream] Content Assignment: writing chunk 1 (rows 1–1000) → content_assignment_chunk_001.csv
[stream] Content Assignment: writing chunk 2 (rows 1001–2000) → content_assignment_chunk_002.csv
...
[stream] Content Assignment: done — 9996 rows, 10 chunks (1.4s)
```

---

## Phase 4: Schema / Knowledge Graph Mode

### 4.1 Generate entity-relationship schema

```bash
python3 extractor.py "<xlsx_path>" --op schema
```

The schema extractor:
1. Scans all sheet headers for ID columns (ending in `ID`, matching patterns like `BA_X4_*`, `BP_X4_*`, `BE-NNNN`)
2. Finds FK relationships: sheets sharing the same column name with ID-like values
3. Detects hierarchical patterns: `Business Area` → `Business Package` → `Business Topic` → `BAC Element`
4. Writes `schema.md` (human-readable ER map) and `schema_graph.jsonl` (node/edge JSONL)

Expected `schema.md` output:

```markdown
# Entity Schema: BAC_Mapping_Sheet.xlsx

## Entities

### BusinessArea
- Source: Business Areas
- Key: BA ID  (pattern: BA_X4_*)
- Fields: BA ID, Description, Technical Name, Component, ...
- Rows: 900

### BusinessPackage
- Source: Business Packages
- Key: BP ID  (pattern: BP_X4_*)
- FK → BusinessArea: Business Area column

### BACElement
- Source: BAC Element Definition
- Key: BAC Element ID  (pattern: BE-NNNN)
- FK → BusinessArea, BusinessPackage, BusinessTopic via shared column names

### TechnicalObject
- Source: Technical Object Assignment
- FK → BACElement: BAC Element ID column

## Relationships

BusinessArea (1) ──< BusinessPackage (many)
BusinessPackage (1) ──< BusinessTopic (many)
BusinessTopic (1) ──< BACElement (many)
BACElement (1) ──< TechnicalObject (many)
```

### 4.2 JSONL for graph ingestion

Each entity type becomes nodes; FK references become edges:

```json
{"type":"node","label":"BusinessArea","id":"BA_X4_MARKETING","props":{"description":"Marketing","component":"CBC-BOS-BAC-STR"}}
{"type":"edge","from":"BA_X4_MARKETING","to":"BP_X4_MKT_DEVELOPMENT","rel":"HAS_PACKAGE"}
```

Output: `<out_dir>/schema_graph.jsonl`

Use `--schema-fuzzy` to enable fuzzy FK matching when column names differ slightly between sheets.

---

## Phase 5: Output Formats

| Format | Flag | Best for |
|--------|------|----------|
| CSV | `--format csv` | Data analysis, pandas, SQL import |
| JSON | `--format json` | API payloads, small sheets (<5k rows) |
| JSONL | `--format jsonl` | LLM ingestion, streaming, large sheets, agentic pipelines |
| Markdown | `--format markdown` | Human-readable preview, small sheets only (<200 rows) |

Output directory defaults to `<xlsx_basename>_extracted/`. Override with `--out <dir>`.

A `manifest.json` is always written at the end of every run:

```json
{
  "source": "BAC_Mapping_Sheet.xlsx",
  "extracted_at": "2026-04-17T14:23:00Z",
  "output_dir": "BAC_Mapping_Sheet_extracted",
  "files": [
    {
      "filename": "business_areas.csv",
      "sheet": "Business Areas",
      "rows": 900,
      "columns": ["BA ID", "Description", "Technical Name"],
      "format": "csv",
      "chunked": false
    },
    {
      "filename": "content_assignment_chunk_001.csv",
      "sheet": "Content Assignment",
      "rows": 1000,
      "chunk_index": 1,
      "total_chunks": 10,
      "format": "csv",
      "chunked": true
    }
  ]
}
```

---

## Phase 6: LLM-Ready Chunking

For feeding extracted data into an agentic system or knowledge base pipeline:

```bash
python3 extractor.py "<xlsx_path>" --op extract --sheet all \
  --format jsonl --chunk-size 500 --out ./kb_data/
```

Each JSONL line includes `_sheet` and `_row` metadata for source traceability:

```json
{"_sheet":"Business Areas","_row":2,"BA ID":"BA_X4_MARKETING","Description":"Marketing","Component":"CBC-BOS-BAC-STR"}
```

### 6.1 Knowledge base integration

To feed extracted data into a `llm-knowledge-base` KB:

```bash
# 1. Extract key sheets to JSONL, drop into KB raw/
python3 extractor.py "BAC_Mapping_Sheet.xlsx" --op extract \
  --sheet "BAC Element Definition,Business Areas,Business Packages,Business Topics" \
  --format jsonl --out ./my-kb/raw/articles/excel-data/

# 2. Add the schema as a raw document (gives Claude structural context):
python3 extractor.py "BAC_Mapping_Sheet.xlsx" --op schema --out /tmp/schema_out/
cp /tmp/schema_out/schema.md ./my-kb/raw/articles/bac-mapping-schema.md

# 3. Run KB compile — Claude reads the schema first, then individual JSONL files:
#    /llm-knowledge-base → compile
```

**Important:** For sheets with >1,000 rows, use `--chunk-size 500` to split into multiple files. The KB compile processes each chunk as a separate raw document, creating focused wiki articles rather than one massive article.

---

---

## Phase 8: Sanitize — Remove PII

### 8.1 Copy the sanitize script

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/skills-repo -type d -name "excel-extractor" 2>/dev/null | head -1)
cp "$SKILL_DIR/templates/scripts/sanitize.py" ./sanitize.py
```

### 8.2 Preview what would be redacted (no files written)

```bash
python3 sanitize.py "<extracted_dir>/" --dry-run
```

### 8.3 Sanitize all files (default: redact mode)

```bash
python3 sanitize.py "<extracted_dir>/" --out "<extracted_dir>/sanitized/"
```

Output is written to `sanitized/` — originals are never modified.

### 8.4 Drop PII columns entirely instead of replacing values

```bash
python3 sanitize.py "<extracted_dir>/" --mode drop
```

### 8.5 Add extra columns to always redact

```bash
python3 sanitize.py "<extracted_dir>/" \
  --redact-columns "entered by  (Date/Name),Processing Comment"
```

### 8.6 Protect specific columns from auto-detection

```bash
# e.g. "Object Owner" in your data is an app ID, not a person
python3 sanitize.py "<extracted_dir>/" --keep-columns "Object Owner"
```

### 8.7 Get a full redaction report

```bash
python3 sanitize.py "<extracted_dir>/" --report
```

Writes `sanitized/sanitize_report.json` with per-file PII hit counts and which columns were affected.

### What gets redacted

| Pattern | Example | Action |
|---------|---------|--------|
| Employee IDs | `D045884`, `I321170` | Always redacted in PII columns |
| Combined ID + name | `D045884, Arti Shah` | Replaced as a unit |
| `Surname, Firstname` | `Herold, Robert` | Replaced in PII columns |
| `Firstname Lastname` | `Karen Feng` | Replaced in PII columns |
| Short user codes | `.ANJ` (whole cell = code) | Replaced in PII columns |
| Employee IDs in comments | `added by D036458` | Replaced in comment fields |
| `Surname, Firstname` in comments | `Kohlmaier, Klaus approved` | Replaced in comment fields |

### What is NOT redacted

- Business acronyms in free text: `RO Inventory Account`, `BCM decision`, `DW` (Data Warehouse) — 2-3 letter codes in prose are too ambiguous to redact without removing business data
- Technical IDs: `BA_X4_MARKETING`, `SAP_BR_GL_ACCOUNTANT`, `BE-0001`, `FI-GL`
- Placeholder/status values: `TBD`, `N/A`, `harmonized`, `#N/A`
- Any column listed in `--keep-columns`

### Auto-detected PII columns

The script auto-flags any column whose name contains: `owner`, `manager`, `architect`, `developer`, `author`, `contact`, `assignee`, `reviewer`, `approver`, `responsible`, `created by`, `modified by`, `product owner`, `ua dev`, `entered by`, `delivery manager`, `bb owner`, `content architect`.

---

## Phase 9: Join — Resolve Cross-Sheet Relationships

### 9.1 Copy the join script

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/skills-repo -type d -name "excel-extractor" 2>/dev/null | head -1)
cp "$SKILL_DIR/templates/scripts/join.py" ./join.py
```

### 9.2 Preview the join plan (no files written)

```bash
python3 join.py "<extracted_dir>/" --dry-run
```

Shows which sheets will be joined and in what order based on the auto-detected FK relationships in `schema_graph.jsonl`.

### 9.3 Auto-join all related sheets

```bash
python3 join.py "<extracted_dir>/"
```

Uses BFS from the most-connected sheet. Outputs to `<extracted_dir>/joined/`.

### 9.4 Join anchored on a specific fact table

```bash
# Start from Technical Object Assignment → enrich with BAC Element → Business hierarchy
python3 join.py "<extracted_dir>/" --anchor "Technical Object Assignment" --depth 3
```

### 9.5 Join a specific subset of sheets

```bash
python3 join.py "<extracted_dir>/" \
  --sheets "BAC Element Definition,Business Areas,Business Packages,Business Topics" \
  --anchor "BAC Element Definition"
```

### 9.6 Prefix imported columns with source sheet name

```bash
# Avoids column name collisions; produces e.g. "Business Areas.Description"
python3 join.py "<extracted_dir>/" --prefix --anchor "BAC Element Definition"
```

### 9.7 Output as CSV

```bash
python3 join.py "<extracted_dir>/" --format csv --anchor "BAC Element Definition"
```

### How it works

1. Reads `schema_graph.jsonl` (produced by `--op schema`) for FK relationships
2. Performs BFS from the anchor sheet, collecting join steps up to `--depth` hops
3. Left-joins each related sheet on the shared key column — unmatched anchor rows are kept with null foreign fields
4. Writes one enriched output file per anchor + a `join_manifest.json`

### Example: BAC hierarchy joined

```
Anchor: BAC Element Definition  (5,534 rows)
  + Business Areas via Area ID         → adds BA-level fields
  + Business Packages via Package ID   → adds BP-level fields
  + Business Topics via Topic ID       → adds BT-level fields
  + Technical Object Assignment via BAC Element ID → adds TO-level fields

Result: bac_element_definition_joined.jsonl
  5,534 rows × ~120 columns (each row has full hierarchy context)
```

### Output files

```
<extracted_dir>/joined/
├── <anchor_slug>_joined.jsonl     (or .csv)
└── <anchor_slug>_join_manifest.json
```

`join_manifest.json` records the exact join steps, output row count, and column count for reproducibility.

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: openpyxl` | `pip install openpyxl pandas` |
| `MemoryError` on large sheet | Should auto-stream. Force it: `--op stream --sheet "<name>"` |
| Column headers wrong (annotation row in data) | Use `--header-row 2` or `--header-row combined` |
| `rows` count looks wrong (much higher than actual data) | Normal — OOXML `dimension` is unreliable. The script counts real `<row>` XML elements. |
| Encoding errors in CSV (Excel shows ??? for special chars) | Use `--encoding utf-8-sig` (adds BOM) |
| Schema shows no FK relationships | Column names may differ slightly — use `--schema-fuzzy` |
| Chunked output splits rows at wrong boundaries | Adjust `--chunk-size N` to a smaller value |
| Empty rows included in output | Normal for sheets with sparse data. Filter in pandas downstream. |
| `calcChain.xml` warning in output | Safe to ignore — it's the formula recalculation cache, not data |
