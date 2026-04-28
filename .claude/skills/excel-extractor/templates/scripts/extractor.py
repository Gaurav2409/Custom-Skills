#!/usr/bin/env python3
"""
extractor.py — Extract data from .xlsx files using openpyxl + pandas.

Requires: pip install openpyxl pandas

CLI:
  python extractor.py <xlsx_path>
        [--op profile|extract|schema|sample|stream|summarize]
        [--sheet <name|all>]
        [--format csv|json|jsonl|markdown]
        [--out <dir>]                default: <basename>_extracted/
        [--chunk-size N]             default: 1000
        [--header-row 1|2|combined]  default: 1 (1-indexed; row 1 = header)
        [--max-rows N]               default: unlimited
        [--columns col1,col2,...]    filter to specific columns
        [--stream-threshold N]       default: 50 (MB of XML before auto-streaming)
        [--encoding utf-8|utf-8-sig] default: utf-8
        [--schema-fuzzy]             fuzzy FK matching across sheets

Examples:
  python extractor.py data.xlsx --op profile
  python extractor.py data.xlsx --op extract --sheet all --format csv
  python extractor.py data.xlsx --op extract --sheet "Business Areas" --format jsonl
  python extractor.py data.xlsx --op sample --sheet "Business Areas" --max-rows 20
  python extractor.py data.xlsx --op schema
  python extractor.py data.xlsx --op extract --sheet "Content Assignment" --chunk-size 500
"""

import sys
import json
import csv
import re
import argparse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Iterator, Optional

# ── dependency check ────────────────────────────────────────────────────────
_missing = []
try:
    import openpyxl
except ImportError:
    _missing.append("openpyxl")
try:
    import pandas as pd
except ImportError:
    _missing.append("pandas")

if _missing:
    print(f"ERROR: Missing required packages: {', '.join(_missing)}", file=sys.stderr)
    print(f"Fix: pip install {' '.join(_missing)}", file=sys.stderr)
    sys.exit(1)


# ── data classes ────────────────────────────────────────────────────────────

@dataclass
class SheetInfo:
    name: str
    xml_path: str        # e.g. "xl/worksheets/sheet1.xml"
    dim_rows: int        # from OOXML dimension attribute (unreliable)
    dim_cols: int
    xml_bytes: int       # uncompressed XML size
    xml_rows: int = 0    # actual <row> element count (populated during profile)
    headers: list = field(default_factory=list)
    has_multi_header: bool = False
    category: str = "SMALL"  # SMALL / MEDIUM / LARGE


@dataclass
class FileRecord:
    filename: str
    sheet: str
    rows: int
    columns: list
    format: str
    chunked: bool
    chunk_index: Optional[int] = None
    total_chunks: Optional[int] = None


# ── OOXML helpers ────────────────────────────────────────────────────────────

NS = {
    "ss":  "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "wb":  "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}

_COL_RE = re.compile(r"^([A-Z]+)")


def col_letter_to_index(col: str) -> int:
    """Convert column letter(s) to 0-based index.  A→0, Z→25, AA→26."""
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _col_from_ref(cell_ref: str) -> int:
    """Extract 0-based column index from cell reference like 'C5'."""
    m = _COL_RE.match(cell_ref)
    return col_letter_to_index(m.group(1)) if m else 0


def _row_from_ref(cell_ref: str) -> int:
    """Extract 1-based row number from cell reference like 'C5'."""
    return int(re.sub(r"[A-Z]+", "", cell_ref))


def slugify(name: str) -> str:
    """Convert sheet name to safe filename: lowercase, underscores."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "sheet"


# ── shared strings ───────────────────────────────────────────────────────────

def load_shared_strings(z: zipfile.ZipFile) -> list:
    """Load xl/sharedStrings.xml into a list indexed by position."""
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    strings = []
    with z.open("xl/sharedStrings.xml") as f:
        tree = ET.parse(f)
        for si in tree.getroot().findall(f"{{{ns}}}si"):
            # Plain text: <t>
            t_plain = si.find(f"{{{ns}}}t")
            if t_plain is not None:
                strings.append(t_plain.text or "")
                continue
            # Rich text: <r><t>...</t></r>
            parts = [r.findtext(f"{{{ns}}}t", "") or "" for r in si.findall(f"{{{ns}}}r")]
            strings.append("".join(parts))
    return strings


# ── sheet manifest ───────────────────────────────────────────────────────────

def get_sheet_manifest(z: zipfile.ZipFile) -> list[SheetInfo]:
    """Parse workbook.xml + rels to return ordered list of SheetInfo."""
    ns_wb = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_r  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_rel = "http://schemas.openxmlformats.org/package/2006/relationships"

    # 1. Load relationships: rid → target path
    rels: dict[str, str] = {}
    with z.open("xl/_rels/workbook.xml.rels") as f:
        tree = ET.parse(f)
        for rel in tree.getroot():
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if not target.startswith("xl/"):
                target = "xl/" + target
            rels[rid] = target

    # 2. Load workbook.xml to get ordered sheet names + rIds
    sheets: list[SheetInfo] = []
    with z.open("xl/workbook.xml") as f:
        tree = ET.parse(f)
        root = tree.getroot()
        sheets_el = root.find(f"{{{ns_wb}}}sheets")
        if sheets_el is None:
            return []
        for sh in sheets_el.findall(f"{{{ns_wb}}}sheet"):
            name = sh.get("name", "")
            rid  = sh.get(f"{{{ns_r}}}id", "")
            xml_path = rels.get(rid, "")
            if not xml_path or xml_path not in z.namelist():
                continue

            # Parse dimension from sheet XML (fast — just read first few KB)
            dim_rows = dim_cols = 0
            with z.open(xml_path) as sf:
                content = sf.read(4096).decode("utf-8", errors="replace")
                m = re.search(r'<dimension\s+ref="([^"]+)"', content)
                if m:
                    ref = m.group(1)
                    if ":" in ref:
                        _, end = ref.split(":")
                        dim_cols = col_letter_to_index(_COL_RE.match(end).group(1)) + 1
                        dim_rows = _row_from_ref(end)

            xml_bytes = z.getinfo(xml_path).file_size
            sheets.append(SheetInfo(
                name=name,
                xml_path=xml_path,
                dim_rows=dim_rows,
                dim_cols=dim_cols,
                xml_bytes=xml_bytes,
            ))
    return sheets


# ── row streaming ────────────────────────────────────────────────────────────

def _cell_value(cell_el, ss: list, ns: str):
    """Extract typed value from a <c> element."""
    t = cell_el.get("t", "")  # type attribute
    v_el = cell_el.find(f"{{{ns}}}v")
    if v_el is None or v_el.text is None:
        return None
    raw = v_el.text
    if t == "s":
        try:
            return ss[int(raw)]
        except (IndexError, ValueError):
            return raw
    if t == "b":
        return raw == "1"
    if t in ("str", "inlineStr"):
        is_el = cell_el.find(f"{{{ns}}}is")
        if is_el is not None:
            t_el = is_el.find(f"{{{ns}}}t")
            return t_el.text if t_el is not None else raw
        return raw
    # numeric / date
    try:
        f = float(raw)
        return int(f) if f == int(f) else f
    except ValueError:
        return raw


def iter_raw_rows(
    z: zipfile.ZipFile,
    xml_path: str,
    ss: list,
    max_rows: Optional[int] = None,
) -> Iterator[dict[int, object]]:
    """Yield rows as {col_index: value} dicts (sparse — only non-empty cells)."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    row_count = 0
    with z.open(xml_path) as f:
        for event, el in ET.iterparse(f, events=("end",)):
            if el.tag == f"{{{ns}}}row":
                row: dict[int, object] = {}
                for c in el:
                    ref = c.get("r", "")
                    if ref:
                        col_idx = _col_from_ref(ref)
                    else:
                        col_idx = len(row)
                    val = _cell_value(c, ss, ns)
                    if val is not None:
                        row[col_idx] = val
                    c.clear()
                el.clear()
                yield row
                row_count += 1
                if max_rows and row_count >= max_rows:
                    break


def _build_header(row_dict: dict[int, object], n_cols: int) -> list[str]:
    """Turn a sparse row dict into a list of header strings."""
    headers = [""] * max(n_cols, max(row_dict.keys(), default=0) + 1)
    for idx, val in row_dict.items():
        headers[idx] = str(val) if val is not None else ""
    return headers


def iter_sheet_rows(
    z: zipfile.ZipFile,
    xml_path: str,
    ss: list,
    header_row: str = "1",
    columns_filter: Optional[set] = None,
    max_rows: Optional[int] = None,
) -> tuple[list[str], Iterator[dict]]:
    """
    Return (headers, row_iterator) where each row is {col_name: value}.

    header_row:
      "1"        — row 1 is header (default)
      "2"        — row 2 is header; row 1 discarded
      "combined" — rows 1+2 merged as "Row1: Row2"
    """
    raw = iter_raw_rows(z, xml_path, ss)

    try:
        row1 = next(raw)
    except StopIteration:
        return [], iter([])

    if header_row == "1":
        n_cols = max(row1.keys(), default=0) + 1
        headers = _build_header(row1, n_cols)
        data_iter = raw
    elif header_row == "2":
        try:
            row2 = next(raw)
        except StopIteration:
            row2 = {}
        n_cols = max((max(row1.keys(), default=0), max(row2.keys(), default=0))) + 1
        headers = _build_header(row2, n_cols)
        data_iter = raw
    elif header_row == "combined":
        try:
            row2 = next(raw)
        except StopIteration:
            row2 = {}
        n_cols = max((max(row1.keys(), default=0), max(row2.keys(), default=0))) + 1
        h1 = _build_header(row1, n_cols)
        h2 = _build_header(row2, n_cols)
        headers = [
            f"{a}: {b}" if a and b else (a or b)
            for a, b in zip(h1, h2)
        ]
        data_iter = raw
    else:
        headers = []
        data_iter = raw

    # Deduplicate blank/duplicate headers
    seen: dict[str, int] = {}
    clean_headers = []
    for h in headers:
        h = h.strip() if h else ""
        if not h:
            h = f"col_{len(clean_headers)}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        clean_headers.append(h)

    # Build column filter indices
    if columns_filter:
        allowed_idx = {i for i, h in enumerate(clean_headers) if h in columns_filter}
    else:
        allowed_idx = None

    def _gen():
        count = 0
        for raw_row in data_iter:
            if max_rows and count >= max_rows:
                break
            row_out = {}
            for idx, val in raw_row.items():
                if idx < len(clean_headers):
                    col_name = clean_headers[idx]
                else:
                    col_name = f"col_{idx}"
                if allowed_idx is None or idx in allowed_idx:
                    row_out[col_name] = val
            yield row_out
            count += 1

    return clean_headers, _gen()


# ── profile ──────────────────────────────────────────────────────────────────

def profile_file(z: zipfile.ZipFile, ss: list, sheets: list[SheetInfo]) -> list[SheetInfo]:
    """Populate xml_rows, headers, has_multi_header, category for each sheet."""
    stream_threshold = 50 * 1024 * 1024  # 50 MB

    for sh in sheets:
        mb = sh.xml_bytes / 1024 / 1024
        if mb < 1:
            sh.category = "SMALL"
        elif mb < 50:
            sh.category = "MEDIUM"
        else:
            sh.category = "LARGE"

        # Count rows and grab first 3 rows for header analysis
        sample_rows = []
        row_count = 0
        for r in iter_raw_rows(z, sh.xml_path, ss):
            if len(sample_rows) < 3:
                sample_rows.append(r)
            row_count += 1
        sh.xml_rows = row_count

        if sample_rows:
            n_cols = max(
                (max(r.keys(), default=0) for r in sample_rows),
                default=0
            ) + 1
            sh.headers = _build_header(sample_rows[0], n_cols)

            # Detect multi-row header: row 2 looks like annotations
            if len(sample_rows) >= 2:
                row2_vals = [str(v) for v in sample_rows[1].values() if v]
                if row2_vals:
                    # Heuristic: row 2 is an annotation if most values are short
                    avg_len = sum(len(v) for v in row2_vals) / len(row2_vals)
                    lock_keywords = {"locked", "central", "only", "mandatory", "optional"}
                    has_lock = any(
                        any(kw in v.lower() for kw in lock_keywords)
                        for v in row2_vals
                    )
                    sh.has_multi_header = avg_len < 20 or has_lock

    return sheets


def print_profile(sheets: list[SheetInfo], xlsx_path: Path):
    mb = xlsx_path.stat().st_size / 1024 / 1024
    print(f"\nExcel File Profile")
    print(f"==================")
    print(f"File: {xlsx_path.name}  ({mb:.1f} MB)")
    print(f"Sheets: {len(sheets)}\n")

    w_name = max(len(s.name) for s in sheets)
    print(f"{'Sheet':<{w_name}}  {'rows':>8}  {'cols':>5}  {'xml_MB':>7}  category")
    print("-" * (w_name + 35))
    multi_header_sheets = []
    for s in sheets:
        xml_mb = s.xml_bytes / 1024 / 1024
        print(f"{s.name:<{w_name}}  {s.xml_rows:>8,}  {s.dim_cols:>5}  {xml_mb:>6.1f}  {s.category}")
        if s.has_multi_header:
            multi_header_sheets.append(s.name)

    print(f"""
Categories:
  SMALL   (xml < 1 MB)   — safe to load fully
  MEDIUM  (1–50 MB)      — loads fine; use --op stream to force chunking
  LARGE   (xml > 50 MB)  — streaming auto-enabled""")

    if multi_header_sheets:
        print(f"\n⚠  Multi-row headers likely on: {', '.join(multi_header_sheets)}")
        print("   Use --header-row 2 to use row 2 as header, or --header-row combined")

    print()


# ── extract ──────────────────────────────────────────────────────────────────

def _flush_csv(path: Path, headers: list[str], rows: list[dict], encoding: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def extract_sheet(
    z: zipfile.ZipFile,
    sh: SheetInfo,
    ss: list,
    out_dir: Path,
    args,
) -> list[FileRecord]:
    """Extract one sheet; returns list of FileRecord (one per chunk file)."""
    columns_filter = set(args.columns.split(",")) if args.columns else None
    stream_bytes = args.stream_threshold * 1024 * 1024
    force_stream = args.op == "stream"
    auto_stream  = sh.xml_bytes >= stream_bytes

    headers, row_iter = iter_sheet_rows(
        z, sh.xml_path, ss,
        header_row=args.header_row,
        columns_filter=columns_filter,
        max_rows=args.max_rows if args.op == "sample" else None,
    )

    if columns_filter:
        headers = [h for h in headers if h in columns_filter]

    slug = slugify(sh.name)
    fmt  = args.format
    records: list[FileRecord] = []

    if force_stream or auto_stream:
        # Streaming / chunked write
        chunk_size  = args.chunk_size
        chunk_num   = 0
        buffer: list[dict] = []
        total_rows  = 0
        chunk_paths: list[Path] = []

        for row in row_iter:
            buffer.append(row)
            if len(buffer) >= chunk_size:
                chunk_num += 1
                chunk_path = out_dir / f"{slug}_chunk_{chunk_num:03d}.{fmt}"
                _write_rows(chunk_path, headers, buffer, fmt, args.encoding, sh.name)
                print(f"[stream] {sh.name}: chunk {chunk_num} ({total_rows + 1}–{total_rows + len(buffer)}) → {chunk_path.name}")
                total_rows += len(buffer)
                chunk_paths.append(chunk_path)
                records.append(FileRecord(
                    filename=chunk_path.name, sheet=sh.name,
                    rows=len(buffer), columns=headers, format=fmt,
                    chunked=True, chunk_index=chunk_num,
                ))
                buffer = []

        if buffer:
            chunk_num += 1
            if chunk_num == 1:
                # Only one chunk — write without chunk suffix
                out_path = out_dir / f"{slug}.{fmt}"
                _write_rows(out_path, headers, buffer, fmt, args.encoding, sh.name)
                total_rows += len(buffer)
                records.append(FileRecord(
                    filename=out_path.name, sheet=sh.name,
                    rows=total_rows, columns=headers, format=fmt, chunked=False,
                ))
            else:
                chunk_path = out_dir / f"{slug}_chunk_{chunk_num:03d}.{fmt}"
                _write_rows(chunk_path, headers, buffer, fmt, args.encoding, sh.name)
                total_rows += len(buffer)
                chunk_paths.append(chunk_path)
                records.append(FileRecord(
                    filename=chunk_path.name, sheet=sh.name,
                    rows=len(buffer), columns=headers, format=fmt,
                    chunked=True, chunk_index=chunk_num,
                ))

        # Update total_chunks now that we know it
        for rec in records:
            if rec.chunked:
                rec.total_chunks = chunk_num

        if force_stream or (auto_stream and chunk_num > 1):
            print(f"[stream] {sh.name}: done — {total_rows:,} rows, {chunk_num} chunk(s)")

    else:
        # Full load
        all_rows = list(row_iter)
        out_path  = out_dir / f"{slug}.{fmt}"
        _write_rows(out_path, headers, all_rows, fmt, args.encoding, sh.name)
        records.append(FileRecord(
            filename=out_path.name, sheet=sh.name,
            rows=len(all_rows), columns=headers, format=fmt, chunked=False,
        ))
        print(f"  {sh.name} → {out_path.name}  ({len(all_rows):,} rows)")

    return records


def _write_rows(path: Path, headers: list[str], rows: list[dict], fmt: str, encoding: str, sheet_name: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        _flush_csv(path, headers, rows, encoding)
    elif fmt == "json":
        with open(path, "w", encoding=encoding) as f:
            json.dump(rows, f, ensure_ascii=False, default=str, indent=2)
    elif fmt == "jsonl":
        with open(path, "w", encoding=encoding) as f:
            for i, row in enumerate(rows, start=1):
                obj = {"_sheet": sheet_name, "_row": i}
                obj.update(row)
                f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    elif fmt == "markdown":
        if not rows:
            path.write_text("*(empty)*\n", encoding=encoding)
            return
        with open(path, "w", encoding=encoding) as f:
            f.write("| " + " | ".join(headers) + " |\n")
            f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
            for row in rows:
                vals = [str(row.get(h, "")).replace("|", "\\|") for h in headers]
                f.write("| " + " | ".join(vals) + " |\n")


# ── sample ───────────────────────────────────────────────────────────────────

def sample_sheet(z: zipfile.ZipFile, sh: SheetInfo, ss: list, args):
    """Print a markdown table of the first N rows to stdout."""
    n = args.max_rows or 20
    headers, row_iter = iter_sheet_rows(
        z, sh.xml_path, ss,
        header_row=args.header_row,
        max_rows=n,
    )
    rows = list(row_iter)
    print(f"\n## {sh.name}  (first {len(rows)} rows)\n")
    if not rows:
        print("*(empty)*\n")
        return
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        vals = [str(row.get(h, "")).replace("|", "\\|") for h in headers]
        print("| " + " | ".join(vals) + " |")
    print()


# ── schema ───────────────────────────────────────────────────────────────────

_ID_PATTERNS = re.compile(
    r"(^.+\s+ID$|^.+_id$|[A-Z]{2}_X\d+_|BE-\d{4})",
    re.IGNORECASE,
)

def detect_fk_relationships(sheets: list[SheetInfo], fuzzy: bool = False) -> list[dict]:
    """
    Find FK relationships: sheets sharing the same ID-like column names.
    Returns list of {"from_sheet", "to_sheet", "column"} dicts.
    """
    # Map column_name → list of sheet names that have it
    col_to_sheets: dict[str, list[str]] = {}
    for sh in sheets:
        for h in sh.headers:
            if not h:
                continue
            if _ID_PATTERNS.search(h):
                col_to_sheets.setdefault(h, []).append(sh.name)

    relationships = []
    for col, sheet_names in col_to_sheets.items():
        if len(sheet_names) < 2:
            continue
        # All pairs
        for i in range(len(sheet_names)):
            for j in range(i + 1, len(sheet_names)):
                relationships.append({
                    "column": col,
                    "sheet_a": sheet_names[i],
                    "sheet_b": sheet_names[j],
                })

    return relationships


def generate_schema(
    z: zipfile.ZipFile,
    sheets: list[SheetInfo],
    ss: list,
    out_dir: Path,
    fuzzy: bool = False,
) -> tuple[Path, Path]:
    """Write schema.md and schema_graph.jsonl; return (schema_md, graph_jsonl)."""
    fk_rels = detect_fk_relationships(sheets, fuzzy)

    # ── schema.md ──────────────────────────────────────────────────────────
    md_lines = [
        "# Entity Schema\n",
        f"> Auto-generated by excel-extractor from {sheets[0].xml_path.split('/')[0] if sheets else 'workbook'}\n",
        "\n## Entities\n",
    ]
    for sh in sheets:
        id_cols = [h for h in sh.headers if h and _ID_PATTERNS.search(h)]
        pk = id_cols[0] if id_cols else "(none detected)"
        fk_lines = [
            f"  - FK ↔ {r['sheet_b'] if r['sheet_a'] == sh.name else r['sheet_a']}: `{r['column']}`"
            for r in fk_rels
            if sh.name in (r["sheet_a"], r["sheet_b"])
        ]
        md_lines.append(f"### {sh.name}\n")
        md_lines.append(f"- Source sheet: `{sh.name}`\n")
        md_lines.append(f"- Primary key candidate: `{pk}`\n")
        md_lines.append(f"- Rows: {sh.xml_rows:,}\n")
        md_lines.append(f"- Columns: {sh.dim_cols}\n")
        if sh.headers:
            preview = ", ".join(sh.headers[:6])
            if len(sh.headers) > 6:
                preview += f", ... (+{len(sh.headers) - 6} more)"
            md_lines.append(f"- Fields: {preview}\n")
        for fk in fk_lines:
            md_lines.append(fk + "\n")
        md_lines.append("\n")

    if fk_rels:
        md_lines.append("## Relationships\n\n")
        for r in fk_rels:
            md_lines.append(f"- `{r['sheet_a']}` ↔ `{r['sheet_b']}` via `{r['column']}`\n")

    schema_path = out_dir / "schema.md"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text("".join(md_lines), encoding="utf-8")
    print(f"  schema.md → {schema_path}")

    # ── schema_graph.jsonl ─────────────────────────────────────────────────
    graph_path = out_dir / "schema_graph.jsonl"
    with open(graph_path, "w", encoding="utf-8") as gf:
        # Node: one per sheet
        for sh in sheets:
            id_cols = [h for h in sh.headers if h and _ID_PATTERNS.search(h)]
            node = {
                "type": "node",
                "label": sh.name.replace(" ", ""),
                "source_sheet": sh.name,
                "rows": sh.xml_rows,
                "columns": sh.dim_cols,
                "key_column": id_cols[0] if id_cols else None,
                "fields": sh.headers[:20],
            }
            gf.write(json.dumps(node, ensure_ascii=False) + "\n")

        # Edge: one per FK relationship
        for r in fk_rels:
            edge = {
                "type": "edge",
                "from": r["sheet_a"].replace(" ", ""),
                "to":   r["sheet_b"].replace(" ", ""),
                "rel":  "SHARES_KEY",
                "via":  r["column"],
            }
            gf.write(json.dumps(edge, ensure_ascii=False) + "\n")

    print(f"  schema_graph.jsonl → {graph_path}")
    return schema_path, graph_path


# ── manifest ─────────────────────────────────────────────────────────────────

def write_manifest(out_dir: Path, source_path: Path, files: list[FileRecord]):
    manifest = {
        "source": source_path.name,
        "source_path": str(source_path),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out_dir),
        "files": [
            {k: v for k, v in vars(f).items() if v is not None}
            for f in files
        ],
    }
    mp = out_dir / "manifest.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"\n  manifest.json → {mp}")


# ── summarize ────────────────────────────────────────────────────────────────

def summarize_file(sheets: list[SheetInfo], xlsx_path: Path):
    """Print an LLM-friendly summary of every sheet."""
    print(f"\n# Summary: {xlsx_path.name}\n")
    print(f"**{len(sheets)} sheets**, {xlsx_path.stat().st_size // 1024 // 1024} MB total\n")
    for sh in sheets:
        id_cols = [h for h in sh.headers if h and _ID_PATTERNS.search(h)]
        print(f"## {sh.name}")
        print(f"- {sh.xml_rows:,} rows × {sh.dim_cols} columns  |  {sh.category}")
        if sh.headers:
            print(f"- Key columns: {', '.join(sh.headers[:8])}")
        if id_cols:
            print(f"- ID columns: {', '.join(id_cols[:4])}")
        if sh.has_multi_header:
            print("- ⚠ Multi-row header detected")
        print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Extract data from .xlsx files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("xlsx_path", help="Path to the .xlsx file")
    p.add_argument("--op", default="profile",
                   choices=["profile", "extract", "schema", "sample", "stream", "summarize"],
                   help="Operation to perform (default: profile)")
    p.add_argument("--sheet", default="all",
                   help="Sheet name or 'all' (default: all)")
    p.add_argument("--format", default="csv",
                   choices=["csv", "json", "jsonl", "markdown"],
                   help="Output format (default: csv)")
    p.add_argument("--out", default=None,
                   help="Output directory (default: <basename>_extracted/)")
    p.add_argument("--chunk-size", type=int, default=1000,
                   help="Rows per chunk file for streaming (default: 1000)")
    p.add_argument("--header-row", default="1",
                   choices=["1", "2", "combined"],
                   help="Which row(s) to use as column headers (default: 1)")
    p.add_argument("--max-rows", type=int, default=None,
                   help="Max rows to extract per sheet (useful with --op sample)")
    p.add_argument("--columns", default=None,
                   help="Comma-separated list of column names to include")
    p.add_argument("--stream-threshold", type=int, default=50,
                   help="Auto-stream sheets whose XML exceeds this many MB (default: 50)")
    p.add_argument("--encoding", default="utf-8",
                   choices=["utf-8", "utf-8-sig"],
                   help="Output file encoding (default: utf-8; use utf-8-sig for Excel BOM)")
    p.add_argument("--schema-fuzzy", action="store_true",
                   help="Enable fuzzy FK matching in schema mode")
    return p.parse_args()


def main():
    args = parse_args()
    xlsx_path = Path(args.xlsx_path).expanduser().resolve()

    if not xlsx_path.exists():
        print(f"ERROR: File not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out) if args.out else xlsx_path.parent / f"{xlsx_path.stem}_extracted"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Opening {xlsx_path.name} ...")
    with zipfile.ZipFile(xlsx_path, "r") as z:
        print("Loading shared strings ...")
        ss = load_shared_strings(z)

        print("Reading sheet manifest ...")
        sheets = get_sheet_manifest(z)

        if not sheets:
            print("ERROR: No sheets found in workbook.", file=sys.stderr)
            sys.exit(1)

        # Filter to requested sheet(s)
        if args.sheet.lower() != "all":
            target = args.sheet
            sheets_filtered = [s for s in sheets if s.name == target]
            if not sheets_filtered:
                # Try by index
                try:
                    idx = int(target) - 1
                    sheets_filtered = [sheets[idx]]
                except (ValueError, IndexError):
                    print(f"ERROR: Sheet '{target}' not found.", file=sys.stderr)
                    print(f"Available sheets: {[s.name for s in sheets]}", file=sys.stderr)
                    sys.exit(1)
            sheets = sheets_filtered

        # ── operations ──────────────────────────────────────────────────────
        if args.op == "summarize":
            # Summarize doesn't need full profile
            for sh in sheets:
                # Quick row count
                row_count = 0
                for _ in iter_raw_rows(z, sh.xml_path, ss, max_rows=5):
                    pass
                sample = list(iter_raw_rows(z, sh.xml_path, ss, max_rows=2))
                if sample:
                    n_cols = max((max(r.keys(), default=0) for r in sample), default=0) + 1
                    sh.headers = _build_header(sample[0], n_cols)
                # Full row count
                sh.xml_rows = sum(1 for _ in iter_raw_rows(z, sh.xml_path, ss))
                xml_mb = z.getinfo(sh.xml_path).file_size / 1024 / 1024
                sh.category = "SMALL" if xml_mb < 1 else ("MEDIUM" if xml_mb < 50 else "LARGE")
            summarize_file(sheets, xlsx_path)
            return

        # Profile all sheets (needed for all other ops)
        print("Profiling sheets ...")
        sheets = profile_file(z, ss, sheets)

        if args.op == "profile":
            print_profile(sheets, xlsx_path)
            return

        if args.op == "summarize":
            summarize_file(sheets, xlsx_path)
            return

        if args.op == "schema":
            print(f"\nGenerating schema → {out_dir}/")
            schema_path, graph_path = generate_schema(
                z, sheets, ss, out_dir, fuzzy=args.schema_fuzzy
            )
            print(f"\nDone. Files written to {out_dir}/")
            return

        if args.op == "sample":
            target_sheets = sheets
            for sh in target_sheets:
                sample_sheet(z, sh, ss, args)
            return

        # extract / stream
        all_records: list[FileRecord] = []
        print(f"\nExtracting {len(sheets)} sheet(s) → {out_dir}/")
        for sh in sheets:
            records = extract_sheet(z, sh, ss, out_dir, args)
            all_records.extend(records)

        write_manifest(out_dir, xlsx_path, all_records)
        total_rows = sum(r.rows for r in all_records)
        print(f"\nDone. {total_rows:,} rows across {len(all_records)} file(s) in {out_dir}/")


if __name__ == "__main__":
    main()
