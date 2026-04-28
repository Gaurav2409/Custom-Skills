#!/usr/bin/env python3
"""
sanitize.py — Remove personally identifiable information (PII) from extracted Excel data.

Operates on CSV or JSONL files produced by extractor.py. Works in-place or writes
to a separate output directory.

PII removed:
  - Employee/user IDs: patterns like D045884, I321170 (letter + 5-7 digits)
  - Personal names: "Firstname Lastname", "Surname, Firstname", combined "ID, Name"
  - Free-text fields containing names/initials embedded in comments
  - Columns explicitly listed in --redact-columns (always fully redacted)
  - Auto-detected PII-bearing columns (owner, manager, architect, developer, contact, etc.)

CLI:
  python sanitize.py <input_path>
        [--out <dir>]              default: <input_dir>/sanitized/
        [--mode redact|drop]       redact=replace value, drop=remove column entirely
        [--redact-columns col,...] additional columns to always redact
        [--keep-columns col,...]   columns to skip PII detection on (never redact)
        [--placeholder TEXT]       replacement text (default: [REDACTED])
        [--dry-run]                print what would be redacted, don't write files
        [--report]                 write sanitize_report.json with stats

Examples:
  # Sanitize all JSONL files in a directory
  python sanitize.py ./BAC_Mapping_Sheet_extracted/ --out ./sanitized/

  # Drop PII columns entirely instead of redacting values
  python sanitize.py ./BAC_Mapping_Sheet_extracted/ --mode drop

  # Preview what would be redacted
  python sanitize.py bac_element_definition.jsonl --dry-run

  # Add extra columns to always redact
  python sanitize.py ./BAC_Mapping_Sheet_extracted/ \\
    --redact-columns "entered by  (Date/Name),Processing Comment"
"""

import sys
import json
import csv
import re
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ── dependency check ─────────────────────────────────────────────────────────

_missing = []
try:
    import openpyxl  # noqa: F401 — presence check only
except ImportError:
    _missing.append("openpyxl")
try:
    import pandas as pd  # noqa: F401
except ImportError:
    _missing.append("pandas")

if _missing:
    print(f"ERROR: Missing required packages: {', '.join(_missing)}", file=sys.stderr)
    print(f"Fix: pip install {' '.join(_missing)}", file=sys.stderr)
    sys.exit(1)


# ── PII detection patterns ────────────────────────────────────────────────────

# Employee/user IDs: one uppercase letter followed by 5–7 digits
# Covers: D045884, I321170, D063052, D070388
EMPLOYEE_ID_RE = re.compile(r'\b[A-Z]\d{5,7}\b')

# Short SAP user codes: 3–5 uppercase letters that are the ENTIRE cell value
# (e.g. ".ANJ", "ANJ" as standalone user codes in Object Owner columns).
# NOT used on free-text comment fields — too many false positives with business
# acronyms like RO (Receivables), DW (Data Warehouse), BCM, SSCUI, etc.
SHORT_CODE_RE = re.compile(r'^\.?[A-Z]{3,5}$')

# Names: "Firstname Lastname" or "Firstname Middle Lastname"
# Requires capital first letters, at least 2 parts, each ≥ 2 chars, no underscores
# Negative lookahead avoids matching BA_X4_MARKETING-style technical IDs
NAME_FL_RE = re.compile(
    r'\b([A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30}){1,4})\b'
)

# "Surname, Firstname" format: "Herold, Robert" / "Kohlmaier, Klaus"
NAME_SURNF_RE = re.compile(
    r'\b([A-Z][a-z]{1,30}),\s+([A-Z][a-z]{1,30})\b'
)

# Combined "ID, Name": "D045884, Arti Shah"
COMBINED_ID_NAME_RE = re.compile(
    r'\b[A-Z]\d{5,7},\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
)

# Column names that always contain PII — matched case-insensitively as substrings
PII_COLUMN_KEYWORDS = [
    "owner",
    "manager",
    "architect",
    "developer",
    "author",
    "contact",
    "assignee",
    "reviewer",
    "approver",
    "responsible",
    "created by",
    "modified by",
    "product owner",
    "ua dev",
    "entered by",
    "delivery manager",
    "bb owner",
    "content architect",
    "person responsible",
    "owner (name",
    "sub-application area owner",
]

# Column names that look PII-bearing but whose values are technical (never redact)
TECHNICAL_COLUMN_KEYWORDS = [
    "ba id",
    "bp id",
    "bt id",
    "bac element id",
    "constraint id",
    "object id",
    "component",
    "application component",
    "area id",
    "package  id",
    "topic  id",
    "technical name",
    "first release",
]

# Values that look like names but are actually technical placeholders — skip these
SAFE_VALUES = {
    "TBD", "N/A", "#N/A", "#NAME?", "harmonized", "?", "??", "???",
    "0", "", "-1", "-", "–",
}


# ── column classification ─────────────────────────────────────────────────────

def _col_lower(col: str) -> str:
    return col.lower().strip()


def is_pii_column(col: str, extra_redact: set[str], keep: set[str]) -> bool:
    """Return True if this column should have PII detection applied."""
    if col in keep:
        return False
    if col in extra_redact:
        return True
    cl = _col_lower(col)
    if any(kw in cl for kw in TECHNICAL_COLUMN_KEYWORDS):
        return False
    if any(kw in cl for kw in PII_COLUMN_KEYWORDS):
        return True
    return False


def is_comment_column(col: str) -> bool:
    """Free-text columns where names/initials appear inline in prose."""
    cl = _col_lower(col)
    return any(kw in cl for kw in ["comment", "processing comment", "comments"])


# ── value sanitization ────────────────────────────────────────────────────────

def contains_pii(value: str, is_comment: bool = False) -> bool:
    """Return True if the string contains a recognisable PII pattern."""
    if not value or value in SAFE_VALUES:
        return False
    v = str(value).strip()
    if EMPLOYEE_ID_RE.search(v):
        return True
    if COMBINED_ID_NAME_RE.search(v):
        return True
    if NAME_SURNF_RE.search(v):
        return True
    # Name detection: require at least 2 capitalised words, both ≥ 3 chars
    names = NAME_FL_RE.findall(v)
    for name in names:
        parts = name.split()
        if len(parts) >= 2 and all(len(p) >= 3 for p in parts):
            # Avoid matching technical tokens like "BAC Element", "Business Area"
            if not any(p.lower() in {
                "bac", "area", "business", "package", "topic", "element",
                "check", "status", "type", "standard", "extended", "scope",
                "country", "sector", "object", "content", "setup", "guide",
            } for p in parts):
                return True
    # Short user codes only in non-comment, non-prose columns (e.g. Object Owner = ".ANJ")
    if not is_comment and len(v) <= 6 and SHORT_CODE_RE.match(v):
        return True
    return False


def redact_value(value: str, placeholder: str) -> str:
    """Replace PII patterns in a string with placeholder."""
    if not value or value in SAFE_VALUES:
        return value
    v = str(value)
    # Combined "ID, Name" first (most specific)
    v = COMBINED_ID_NAME_RE.sub(placeholder, v)
    # Employee IDs
    v = EMPLOYEE_ID_RE.sub(placeholder, v)
    # "Surname, Firstname"
    v = NAME_SURNF_RE.sub(placeholder, v)
    # "Firstname Lastname" — only in PII columns, not free-text (too risky)
    return v


def sanitize_comment(value: str, placeholder: str) -> str:
    """
    Sanitize a free-text comment column.
    Replaces employee IDs and "Surname, Firstname" patterns but leaves
    general prose intact — avoids false-positive name detection in prose.
    """
    if not value:
        return value
    v = str(value)
    v = COMBINED_ID_NAME_RE.sub(placeholder, v)
    v = EMPLOYEE_ID_RE.sub(placeholder, v)
    v = NAME_SURNF_RE.sub(placeholder, v)
    return v


def sanitize_row(
    row: dict,
    mode: str,
    placeholder: str,
    extra_redact: set[str],
    keep: set[str],
) -> tuple[dict, int]:
    """
    Sanitize one row dict. Returns (sanitized_row, pii_hit_count).
    mode: "redact" replaces values; "drop" removes the column key entirely.
    """
    out = {}
    hits = 0

    for col, val in row.items():
        # Skip metadata fields
        if col in ("_sheet", "_row"):
            out[col] = val
            continue

        str_val = str(val) if val is not None else ""

        if col in extra_redact or is_pii_column(col, extra_redact, keep):
            if mode == "drop":
                hits += 1
                continue  # omit column
            else:
                new_val = redact_value(str_val, placeholder) if str_val else val
                if new_val != str_val:
                    hits += 1
                out[col] = new_val if str_val else val

        elif is_comment_column(col):
            new_val = sanitize_comment(str_val, placeholder)
            if new_val != str_val:
                hits += 1
            out[col] = new_val if str_val else val

        else:
            out[col] = val

    return out, hits


# ── file processing ───────────────────────────────────────────────────────────

@dataclass
class FileStats:
    filename: str
    rows_processed: int = 0
    pii_hits: int = 0
    pii_columns_detected: set = field(default_factory=set)


def process_jsonl(
    src: Path,
    dst: Path,
    args,
    extra_redact: set[str],
    keep: set[str],
) -> FileStats:
    stats = FileStats(filename=src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)

    lines_out = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                lines_out.append(line)
                continue

            clean_row, hits = sanitize_row(row, args.mode, args.placeholder, extra_redact, keep)
            stats.rows_processed += 1
            stats.pii_hits += hits

            if hits > 0:
                for col in row:
                    if col in ("_sheet", "_row"):
                        continue
                    if is_pii_column(col, extra_redact, keep) or is_comment_column(col):
                        if str(row.get(col, "")) != str(clean_row.get(col, "")):
                            stats.pii_columns_detected.add(col)

            lines_out.append(json.dumps(clean_row, ensure_ascii=False, default=str))

    if not args.dry_run:
        dst.write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    return stats


def process_csv(
    src: Path,
    dst: Path,
    args,
    extra_redact: set[str],
    keep: set[str],
) -> FileStats:
    stats = FileStats(filename=src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with open(src, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return stats
        fieldnames = list(reader.fieldnames)

        rows_clean = []
        for row in reader:
            clean_row, hits = sanitize_row(dict(row), args.mode, args.placeholder, extra_redact, keep)
            stats.rows_processed += 1
            stats.pii_hits += hits
            if hits > 0:
                for col in row:
                    if is_pii_column(col, extra_redact, keep) or is_comment_column(col):
                        if row.get(col, "") != clean_row.get(col, ""):
                            stats.pii_columns_detected.add(col)
            rows_clean.append(clean_row)

    if args.mode == "drop":
        fieldnames = [c for c in fieldnames if not is_pii_column(c, extra_redact, keep)]

    if not args.dry_run:
        with open(dst, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows_clean)

    return stats


def process_file(src: Path, out_dir: Path, args, extra_redact: set, keep: set) -> FileStats:
    dst = out_dir / src.name
    ext = src.suffix.lower()

    if ext == ".jsonl":
        return process_jsonl(src, dst, args, extra_redact, keep)
    elif ext == ".csv":
        return process_csv(src, dst, args, extra_redact, keep)
    else:
        return FileStats(filename=src.name)


# ── report ────────────────────────────────────────────────────────────────────

def write_report(out_dir: Path, all_stats: list[FileStats], args):
    total_rows = sum(s.rows_processed for s in all_stats)
    total_hits = sum(s.pii_hits for s in all_stats)
    all_cols: set[str] = set()
    for s in all_stats:
        all_cols.update(s.pii_columns_detected)

    report = {
        "mode": args.mode,
        "placeholder": args.placeholder,
        "total_files": len(all_stats),
        "total_rows": total_rows,
        "total_pii_hits": total_hits,
        "pii_columns_found": sorted(all_cols),
        "files": [
            {
                "filename": s.filename,
                "rows": s.rows_processed,
                "pii_hits": s.pii_hits,
                "pii_columns": sorted(s.pii_columns_detected),
            }
            for s in all_stats
        ],
    }
    rp = out_dir / "sanitize_report.json"
    rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  sanitize_report.json → {rp}")
    return report


# ── dry-run preview ───────────────────────────────────────────────────────────

def dry_run_preview(src: Path, args, extra_redact: set, keep: set):
    """Print the first 10 PII hits from a file to stdout."""
    ext = src.suffix.lower()
    hits_shown = 0
    print(f"\n[dry-run] {src.name}")

    def _show_hit(col, original, redacted):
        nonlocal hits_shown
        if hits_shown >= 10:
            return
        print(f"  col={col!r}")
        print(f"    before: {original!r}")
        print(f"    after:  {redacted!r}")
        hits_shown += 1

    if ext == ".jsonl":
        with open(src, encoding="utf-8") as f:
            for line in f:
                if hits_shown >= 10:
                    break
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                for col, val in row.items():
                    if col in ("_sheet", "_row"):
                        continue
                    str_val = str(val) if val is not None else ""
                    if is_pii_column(col, extra_redact, keep) or is_comment_column(col):
                        if is_comment_column(col):
                            new_val = sanitize_comment(str_val, args.placeholder)
                        else:
                            new_val = redact_value(str_val, args.placeholder)
                        if new_val != str_val:
                            _show_hit(col, str_val, new_val)

    elif ext == ".csv":
        with open(src, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if hits_shown >= 10:
                    break
                for col, val in row.items():
                    str_val = str(val) if val else ""
                    if is_pii_column(col, extra_redact, keep) or is_comment_column(col):
                        if is_comment_column(col):
                            new_val = sanitize_comment(str_val, args.placeholder)
                        else:
                            new_val = redact_value(str_val, args.placeholder)
                        if new_val != str_val:
                            _show_hit(col, str_val, new_val)

    if hits_shown == 0:
        print("  (no PII detected)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Remove PII from extracted Excel CSV/JSONL files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input_path",
                   help="Path to a .csv/.jsonl file OR a directory of such files")
    p.add_argument("--out", default=None,
                   help="Output directory (default: <input_dir>/sanitized/)")
    p.add_argument("--mode", default="redact", choices=["redact", "drop"],
                   help="redact=replace PII values with placeholder; drop=remove column entirely (default: redact)")
    p.add_argument("--redact-columns", default=None,
                   help="Comma-separated extra column names to always redact")
    p.add_argument("--keep-columns", default=None,
                   help="Comma-separated column names to never redact (override auto-detection)")
    p.add_argument("--placeholder", default="[REDACTED]",
                   help="Replacement text for redacted values (default: [REDACTED])")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be redacted, write no files")
    p.add_argument("--report", action="store_true",
                   help="Write sanitize_report.json with per-file stats")
    return p.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input_path).expanduser().resolve()

    extra_redact: set[str] = set()
    if args.redact_columns:
        extra_redact = {c.strip() for c in args.redact_columns.split(",")}

    keep: set[str] = set()
    if args.keep_columns:
        keep = {c.strip() for c in args.keep_columns.split(",")}

    # Collect input files
    if input_path.is_dir():
        files = sorted(
            list(input_path.glob("*.jsonl")) + list(input_path.glob("*.csv"))
        )
        # Skip manifest and report files
        files = [f for f in files if f.name not in ("manifest.json",) and "sanitize_report" not in f.name]
        out_dir = Path(args.out) if args.out else input_path / "sanitized"
    elif input_path.is_file():
        files = [input_path]
        out_dir = Path(args.out) if args.out else input_path.parent / "sanitized"
    else:
        print(f"ERROR: Path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("No .csv or .jsonl files found.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"[dry-run] Scanning {len(files)} file(s) — no files will be written\n")
        for f in files[:5]:  # Preview first 5 files
            dry_run_preview(f, args, extra_redact, keep)
        if len(files) > 5:
            print(f"\n... and {len(files) - 5} more files (run without --dry-run to process all)")
        return

    print(f"Sanitizing {len(files)} file(s) → {out_dir}/")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_stats: list[FileStats] = []
    for f in files:
        stats = process_file(f, out_dir, args, extra_redact, keep)
        all_stats.append(stats)
        pii_pct = (stats.pii_hits / stats.rows_processed * 100) if stats.rows_processed else 0
        flag = "  ⚠" if stats.pii_hits > 0 else ""
        print(f"  {f.name:<55}  {stats.rows_processed:>6,} rows  {stats.pii_hits:>5,} hits ({pii_pct:.0f}%){flag}")

    total_rows = sum(s.rows_processed for s in all_stats)
    total_hits = sum(s.pii_hits for s in all_stats)
    all_cols: set[str] = set()
    for s in all_stats:
        all_cols.update(s.pii_columns_detected)

    print(f"\nDone.")
    print(f"  Files processed : {len(all_stats)}")
    print(f"  Rows processed  : {total_rows:,}")
    print(f"  PII hits        : {total_hits:,}")
    if all_cols:
        print(f"  PII columns     : {', '.join(sorted(all_cols))}")
    print(f"  Output          : {out_dir}/")

    if args.report or total_hits > 0:
        report = write_report(out_dir, all_stats, args)
        if total_hits > 0 and not args.report:
            print(f"\n  Tip: run with --report to save full stats to sanitize_report.json")


if __name__ == "__main__":
    main()
