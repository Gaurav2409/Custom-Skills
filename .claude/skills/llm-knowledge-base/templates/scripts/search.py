#!/usr/bin/env python3
"""
search.py — Naive full-text search over the wiki.

Usage:
    python scripts/search.py --query "<search terms>" [--top 10] [--kb-root .]
    python scripts/search.py --query "transformer attention" --top 5
"""
import argparse
import re
from pathlib import Path


def score(query_terms: list[str], text: str) -> int:
    text_lower = text.lower()
    score = 0
    for term in query_terms:
        # Title match (first 3 lines) = 10 pts, body match = 1 pt each
        lines = text_lower.splitlines()
        title_text = " ".join(lines[:3])
        score += title_text.count(term.lower()) * 10
        score += text_lower.count(term.lower())
    return score


def extract_summary(text: str) -> str:
    """Extract the ## Summary section or first non-frontmatter paragraph."""
    # Try to find ## Summary
    m = re.search(r"## Summary\s*\n+(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if m:
        return m.group(1).strip()[:200]
    # Skip frontmatter
    lines = text.splitlines()
    in_frontmatter = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter and line.strip() and not line.startswith("#"):
            return line.strip()[:200]
    return ""


def search_wiki(kb_root: Path, query: str, top_n: int) -> list[dict]:
    query_terms = query.lower().split()
    wiki_dir = kb_root / "wiki"
    results = []

    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue
        text = md_file.read_text(encoding="utf-8", errors="replace")
        s = score(query_terms, text)
        if s > 0:
            results.append({
                "path": md_file.relative_to(kb_root),
                "score": s,
                "summary": extract_summary(text),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


def main():
    parser = argparse.ArgumentParser(description="Search the wiki for relevant articles.")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--top", type=int, default=10, help="Number of results to return")
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    results = search_wiki(kb_root, args.query, args.top)

    if not results:
        print(f"No results found for: {args.query}")
        return

    print(f"\nSearch results for '{args.query}':\n")
    for i, r in enumerate(results, 1):
        print(f"{i:2}. [{r['path']}]  (score: {r['score']})")
        if r["summary"]:
            print(f"    {r['summary'][:120]}...")
        print()


if __name__ == "__main__":
    main()
