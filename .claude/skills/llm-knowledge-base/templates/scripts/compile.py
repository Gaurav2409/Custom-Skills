#!/usr/bin/env python3
"""
compile.py — List raw/ documents not yet compiled into the wiki.

This script identifies new and changed raw documents so the LLM knows exactly
what needs to be processed in a compile run. It also reports confidence
distribution across existing wiki articles and writes a log entry.

Usage:
    python scripts/compile.py [--kb-root .] [--all] [--log]

With --all, lists every raw document regardless of whether it's been summarized.
With --log, appends a compile-start entry to wiki/log.md.
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".md", ".txt", ".html", ".htm", ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
}


# ── config ────────────────────────────────────────────────────────────────────

def load_config(kb_root: Path) -> dict:
    cfg_path = kb_root / "kb.config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}


def get_skip_patterns(cfg: dict) -> list[str]:
    return cfg.get("ingest", {}).get("quality_filter", {}).get("skip_patterns", [])


def matches_skip_pattern(name: str, patterns: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


# ── raw document discovery ────────────────────────────────────────────────────

def list_raw_docs(kb_root: Path, skip_patterns: list[str]) -> list[Path]:
    raw_dir = kb_root / "raw"
    docs = []
    if not raw_dir.exists():
        return docs
    for f in raw_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            if not matches_skip_pattern(f.name, skip_patterns):
                docs.append(f)
    return sorted(docs)


def load_summarized_names(summaries_path: Path) -> set[str]:
    if not summaries_path.exists():
        return set()
    content = summaries_path.read_text(encoding="utf-8", errors="replace")
    # Match **filename** entries in the summaries file
    return set(re.findall(r"\*\*([\w\-. ]+\.\w+)\*\*", content))


# ── change detection via frontmatter last_updated ────────────────────────────

def get_article_last_updated(wiki_dir: Path, doc_name: str) -> date | None:
    """Search wiki/ for an article whose sources reference doc_name, return its last_updated."""
    stem = Path(doc_name).stem
    for f in wiki_dir.rglob("*.md"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if doc_name in content or stem in content:
            m = re.search(r"last_updated:\s*[\"']?(\d{4}-\d{2}-\d{2})", content)
            if m:
                try:
                    from datetime import datetime
                    return datetime.strptime(m.group(1), "%Y-%m-%d").date()
                except ValueError:
                    pass
    return None


def is_changed(doc: Path, wiki_dir: Path) -> bool:
    """Return True if the raw doc's mtime is newer than the article's last_updated date."""
    last_updated = get_article_last_updated(wiki_dir, doc.name)
    if last_updated is None:
        return False  # Not yet compiled — covered by "new" check
    doc_mtime = date.fromtimestamp(doc.stat().st_mtime)
    return doc_mtime > last_updated


# ── confidence distribution from wiki frontmatter ────────────────────────────

def confidence_distribution(wiki_dir: Path) -> dict[str, int]:
    dist = {"high": 0, "medium": 0, "low": 0, "unset": 0}
    for f in wiki_dir.rglob("*.md"):
        if f.name.startswith("_"):
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^confidence:\s*(\w+)", content, re.MULTILINE)
        val = m.group(1) if m else "unset"
        key = val if val in dist else "unset"
        dist[key] += 1
    return dist


# ── log entry ─────────────────────────────────────────────────────────────────

def append_log_entry(log_path: Path, new_docs: list[Path], changed_docs: list[Path]):
    today = date.today().isoformat()
    total = len(new_docs) + len(changed_docs)
    title = f"{total} doc(s) queued" if total else "no new docs"
    lines = [
        f"\n## [{today}] compile | {title}",
    ]
    if new_docs:
        lines.append(f"- New: {', '.join(d.name for d in new_docs[:10])}"
                     + (f" (+{len(new_docs)-10} more)" if len(new_docs) > 10 else ""))
    if changed_docs:
        lines.append(f"- Changed: {', '.join(d.name for d in changed_docs[:5])}"
                     + (f" (+{len(changed_docs)-5} more)" if len(changed_docs) > 5 else ""))
    if not new_docs and not changed_docs:
        lines.append("- All raw documents are already compiled and up-to-date.")

    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="List raw documents not yet compiled into the wiki."
    )
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory")
    parser.add_argument("--all", action="store_true",
                        help="List all raw docs, not just new/changed ones")
    parser.add_argument("--log", action="store_true",
                        help="Append a compile-start entry to wiki/log.md")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    wiki_dir = kb_root / "wiki"
    summaries_path = wiki_dir / "_summaries.md"
    log_path = wiki_dir / "log.md"

    cfg = load_config(kb_root)
    skip_patterns = get_skip_patterns(cfg)

    raw_docs = list_raw_docs(kb_root, skip_patterns)
    summarized = load_summarized_names(summaries_path)

    print(f"Knowledge base: {kb_root}")
    print(f"Total raw documents: {len(raw_docs)}")
    print(f"Already summarized:  {len(summarized)}")

    new_docs = [d for d in raw_docs if d.name not in summarized]
    changed_docs = [
        d for d in raw_docs
        if d.name in summarized and wiki_dir.exists() and is_changed(d, wiki_dir)
    ]

    # Confidence distribution
    if wiki_dir.exists():
        dist = confidence_distribution(wiki_dir)
        total_articles = sum(dist.values())
        if total_articles > 0:
            print(f"\nWiki confidence distribution ({total_articles} articles):")
            print(f"  high: {dist['high']}  medium: {dist['medium']}  "
                  f"low: {dist['low']}  unset: {dist['unset']}")

    print()

    if args.all:
        print("All raw documents:")
        for doc in raw_docs:
            if doc.name not in summarized:
                marker = "○ NEW    "
            elif any(d.name == doc.name for d in changed_docs):
                marker = "↻ CHANGED"
            else:
                marker = "✓ done   "
            print(f"  {marker}  {doc.relative_to(kb_root)}")
    else:
        if not new_docs and not changed_docs:
            print("✓ All raw documents are already compiled and up-to-date.")
        else:
            if new_docs:
                print(f"New documents to compile ({len(new_docs)}):")
                for doc in new_docs:
                    print(f"  ○  {doc.relative_to(kb_root)}")
            if changed_docs:
                print(f"\nChanged documents to recompile ({len(changed_docs)}):")
                for doc in changed_docs:
                    print(f"  ↻  {doc.relative_to(kb_root)}")

    if args.log and wiki_dir.exists():
        append_log_entry(log_path, new_docs, changed_docs)
        print(f"\nLog entry appended to {log_path.relative_to(kb_root)}")


if __name__ == "__main__":
    main()
