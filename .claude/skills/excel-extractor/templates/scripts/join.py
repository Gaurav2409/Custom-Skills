#!/usr/bin/env python3
"""
join.py — Resolve cross-sheet relationships in extracted Excel data.

Reads the schema_graph.jsonl produced by extractor.py --op schema, then
joins related sheets together via their detected FK columns. Outputs
enriched JSONL/CSV where each row carries denormalised fields from its
parent entities.

CLI:
  python join.py <extracted_dir>
        [--schema schema_graph.jsonl]  default: <dir>/schema_graph.jsonl
        [--sheets sheet_a,sheet_b,...] sheets to join (default: all)
        [--anchor <sheet>]             the "fact" table to start from
        [--format csv|jsonl]           output format (default: jsonl)
        [--out <dir>]                  default: <extracted_dir>/joined/
        [--depth N]                    max join hops from anchor (default: 3)
        [--prefix]                     prefix imported columns with source sheet name
        [--dry-run]                    show join plan without writing files

Examples:
  # Join all sheets using auto-detected FKs from schema
  python join.py ./BAC_Mapping_Sheet_extracted/

  # Join anchored on BAC Element Definition outward to Technical Objects
  python join.py ./BAC_Mapping_Sheet_extracted/ \\
    --anchor "BAC Element Definition" --depth 2

  # Join specific sheets only
  python join.py ./BAC_Mapping_Sheet_extracted/ \\
    --sheets "BAC Element Definition,Business Areas,Business Packages,Business Topics"

  # Produce a flat CSV per join path
  python join.py ./BAC_Mapping_Sheet_extracted/ --format csv --anchor "Technical Object Assignment"
"""

import sys
import json
import csv
import argparse
from pathlib import Path
from collections import defaultdict


# ── dependency check ──────────────────────────────────────────────────────────

_missing = []
try:
    import openpyxl  # noqa: F401
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


# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "sheet"


def load_schema(schema_path: Path) -> tuple[list[dict], list[dict]]:
    """Load schema_graph.jsonl → (nodes, edges)."""
    nodes, edges = [], []
    with open(schema_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "node":
                nodes.append(obj)
            elif obj.get("type") == "edge":
                edges.append(obj)
    return nodes, edges


def load_jsonl(path: Path) -> list[dict]:
    """Load a .jsonl file; handles chunked files by globbing."""
    rows = []
    stem = path.stem
    parent = path.parent

    # If the direct file exists, use it; otherwise try chunks
    candidates = [path] if path.exists() else sorted(
        parent.glob(f"{stem}_chunk_*.jsonl")
    )
    for f in candidates:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return rows


def load_csv(path: Path) -> list[dict]:
    """Load a .csv file; handles chunked files by globbing."""
    rows = []
    stem = path.stem
    parent = path.parent

    candidates = [path] if path.exists() else sorted(
        parent.glob(f"{stem}_chunk_*.csv")
    )
    for f in candidates:
        with open(f, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(dict(row))
    return rows


def find_sheet_file(extracted_dir: Path, sheet_name: str) -> Path | None:
    """Find the JSONL or CSV file for a given sheet name."""
    slug = slugify(sheet_name)
    for ext in (".jsonl", ".csv"):
        p = extracted_dir / (slug + ext)
        if p.exists():
            return p
        # Check for chunked version
        chunks = sorted(extracted_dir.glob(f"{slug}_chunk_001{ext}"))
        if chunks:
            return chunks[0].parent / (slug + ext)  # virtual base path
    return None


def load_sheet(extracted_dir: Path, sheet_name: str) -> list[dict]:
    """Load all rows for a sheet by name."""
    slug = slugify(sheet_name)

    # Try JSONL first
    jsonl = extracted_dir / (slug + ".jsonl")
    chunks_jsonl = sorted(extracted_dir.glob(f"{slug}_chunk_*.jsonl"))
    if jsonl.exists():
        return load_jsonl(jsonl)
    if chunks_jsonl:
        rows = []
        for f in chunks_jsonl:
            rows.extend(load_jsonl(f))
        return rows

    # Fall back to CSV
    csv_path = extracted_dir / (slug + ".csv")
    chunks_csv = sorted(extracted_dir.glob(f"{slug}_chunk_*.csv"))
    if csv_path.exists():
        return load_csv(csv_path)
    if chunks_csv:
        rows = []
        for f in chunks_csv:
            rows.extend(load_csv(f))
        return rows

    return []


# ── join logic ────────────────────────────────────────────────────────────────

def build_lookup(rows: list[dict], key_col: str) -> dict[str, dict]:
    """Build a {key_value: row} lookup dict for fast FK resolution."""
    lookup = {}
    for row in rows:
        val = row.get(key_col)
        if val is not None and str(val).strip():
            lookup[str(val).strip()] = row
    return lookup


def find_shared_columns(rows_a: list[dict], rows_b: list[dict]) -> list[str]:
    """Find column names present in both datasets (excluding metadata cols)."""
    if not rows_a or not rows_b:
        return []
    meta = {"_sheet", "_row"}
    cols_a = set(rows_a[0].keys()) - meta
    cols_b = set(rows_b[0].keys()) - meta
    return sorted(cols_a & cols_b)


def join_sheets(
    anchor_rows: list[dict],
    anchor_name: str,
    target_rows: list[dict],
    target_name: str,
    join_col: str,
    prefix: bool = False,
    depth: int = 0,
) -> list[dict]:
    """
    Left-join anchor_rows with target_rows on join_col.
    Adds target columns to each anchor row (prefixed with target_name if --prefix).
    Unmatched anchor rows are kept with null target fields.
    """
    target_lookup = build_lookup(target_rows, join_col)
    target_cols = (
        set(target_rows[0].keys()) - {"_sheet", "_row", join_col}
        if target_rows else set()
    )

    result = []
    for row in anchor_rows:
        key = str(row.get(join_col, "")).strip()
        match = target_lookup.get(key, {})

        enriched = dict(row)
        for col in sorted(target_cols):
            dest_col = f"{target_name}.{col}" if prefix else col
            # Don't overwrite existing columns unless prefixed
            if prefix or dest_col not in enriched:
                enriched[dest_col] = match.get(col)

        result.append(enriched)

    return result


def plan_joins(
    nodes: list[dict],
    edges: list[dict],
    anchor: str | None,
    sheet_filter: set[str] | None,
    depth: int,
) -> list[tuple[str, str, str]]:
    """
    Return ordered list of (sheet_a, sheet_b, join_col) join steps.
    BFS from anchor (or most-connected node if no anchor).
    """
    # Build adjacency: sheet_name → [(other_sheet, via_col)]
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in edges:
        # Labels in schema_graph use CamelCase; map back via source_sheet
        # Edges store the label (CamelCase), nodes store source_sheet (original)
        label_to_sheet = {n["label"]: n["source_sheet"] for n in nodes}
        sa = label_to_sheet.get(edge["from"], edge["from"])
        sb = label_to_sheet.get(edge["to"], edge["to"])
        col = edge["via"]
        if sheet_filter and (sa not in sheet_filter or sb not in sheet_filter):
            continue
        adj[sa].append((sb, col))
        adj[sb].append((sa, col))

    if not adj:
        return []

    # Choose anchor: most-connected node if not specified
    if anchor is None:
        anchor = max(adj, key=lambda s: len(adj[s]))

    # BFS to build join order
    visited = {anchor}
    queue = [(anchor, 0)]
    steps: list[tuple[str, str, str]] = []

    while queue:
        current, d = queue.pop(0)
        if d >= depth:
            continue
        for neighbor, col in adj.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                steps.append((current, neighbor, col))
                queue.append((neighbor, d + 1))

    return steps


# ── output ────────────────────────────────────────────────────────────────────

def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Join extracted Excel sheets via FK relationships",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("extracted_dir",
                   help="Directory of extracted JSONL/CSV files from extractor.py")
    p.add_argument("--schema", default=None,
                   help="Path to schema_graph.jsonl (default: <extracted_dir>/schema_graph.jsonl)")
    p.add_argument("--sheets", default=None,
                   help="Comma-separated sheet names to include (default: all)")
    p.add_argument("--anchor", default=None,
                   help="Starting 'fact' table for join BFS (default: most-connected sheet)")
    p.add_argument("--format", default="jsonl", choices=["jsonl", "csv"],
                   help="Output format (default: jsonl)")
    p.add_argument("--out", default=None,
                   help="Output directory (default: <extracted_dir>/joined/)")
    p.add_argument("--depth", type=int, default=3,
                   help="Max join hops from anchor (default: 3)")
    p.add_argument("--prefix", action="store_true",
                   help="Prefix imported columns with source sheet name (e.g. 'Business Areas.Description')")
    p.add_argument("--dry-run", action="store_true",
                   help="Show join plan without writing files")
    return p.parse_args()


def main():
    args = parse_args()
    extracted_dir = Path(args.extracted_dir).expanduser().resolve()
    out_dir = Path(args.out) if args.out else extracted_dir / "joined"

    schema_path = Path(args.schema) if args.schema else extracted_dir / "schema_graph.jsonl"
    if not schema_path.exists():
        print(f"ERROR: schema_graph.jsonl not found at {schema_path}", file=sys.stderr)
        print("Run extractor.py with --op schema first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading schema from {schema_path.name} ...")
    nodes, edges = load_schema(schema_path)

    sheet_filter: set[str] | None = None
    if args.sheets:
        sheet_filter = {s.strip() for s in args.sheets.split(",")}

    # Plan join order
    steps = plan_joins(nodes, edges, args.anchor, sheet_filter, args.depth)

    if not steps:
        print("No join relationships found for the given sheets/anchor.", file=sys.stderr)
        print("Available edges in schema:")
        label_to_sheet = {n["label"]: n["source_sheet"] for n in nodes}
        for e in edges:
            sa = label_to_sheet.get(e["from"], e["from"])
            sb = label_to_sheet.get(e["to"], e["to"])
            print(f"  {sa}  ↔  {sb}  via  '{e['via']}'")
        sys.exit(1)

    print(f"\nJoin plan ({len(steps)} step(s), anchor={args.anchor or 'auto'}, depth={args.depth}):")
    for i, (sa, sb, col) in enumerate(steps, 1):
        print(f"  {i}. {sa}  ──[{col}]──>  {sb}")

    if args.dry_run:
        print("\n(dry-run: no files written)")
        return

    # Load anchor sheet
    anchor_name = steps[0][0]
    print(f"\nLoading anchor: {anchor_name} ...")
    result_rows = load_sheet(extracted_dir, anchor_name)
    if not result_rows:
        print(f"ERROR: No rows loaded for anchor sheet '{anchor_name}'", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(result_rows):,} rows")

    # Perform joins in BFS order
    loaded_sheets: dict[str, list[dict]] = {anchor_name: result_rows}

    for sheet_a, sheet_b, join_col in steps:
        # Ensure sheet_a rows are in result (may already be from prior join)
        if sheet_a not in loaded_sheets:
            print(f"Loading: {sheet_a} ...")
            loaded_sheets[sheet_a] = load_sheet(extracted_dir, sheet_a)

        # Load sheet_b
        print(f"Joining: {sheet_a}  +  {sheet_b}  on '{join_col}' ...")
        target_rows = load_sheet(extracted_dir, sheet_b)
        if not target_rows:
            print(f"  WARNING: No rows for '{sheet_b}' — skipping this join step")
            continue

        loaded_sheets[sheet_b] = target_rows

        # Join into the running result (always left-join from anchor perspective)
        # We join onto result_rows if sheet_a == anchor, otherwise build a
        # separate enriched table for this sub-relationship
        if sheet_a == anchor_name or join_col in (result_rows[0] if result_rows else {}):
            result_rows = join_sheets(
                result_rows, sheet_a,
                target_rows, sheet_b,
                join_col,
                prefix=args.prefix,
            )
            print(f"  → {len(result_rows):,} rows  ({len(result_rows[0]) if result_rows else 0} cols)")
        else:
            print(f"  (skipping — '{join_col}' not present in current result set; use --anchor to start from this sheet)")

    # Write output
    out_dir.mkdir(parents=True, exist_ok=True)
    anchor_slug = slugify(anchor_name)
    out_path = out_dir / f"{anchor_slug}_joined.{args.format}"

    print(f"\nWriting {len(result_rows):,} rows → {out_path}")
    if args.format == "jsonl":
        write_jsonl(out_path, result_rows)
    else:
        write_csv(out_path, result_rows)

    # Also write a manifest
    manifest = {
        "anchor": anchor_name,
        "join_steps": [
            {"from": sa, "to": sb, "on": col}
            for sa, sb, col in steps
        ],
        "output_rows": len(result_rows),
        "output_columns": len(result_rows[0]) if result_rows else 0,
        "output_file": str(out_path),
    }
    manifest_path = out_dir / f"{anchor_slug}_join_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Done.")
    print(f"  Output rows    : {len(result_rows):,}")
    print(f"  Output columns : {len(result_rows[0]) if result_rows else 0}")
    print(f"  File           : {out_path}")
    print(f"  Manifest       : {manifest_path}")


if __name__ == "__main__":
    main()
