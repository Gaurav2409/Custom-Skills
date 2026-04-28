#!/usr/bin/env python3
"""
query.py — Run a Q&A query against the wiki via the search index.

This script is a CLI wrapper that finds the most relevant wiki articles
for a query and prints them, so the LLM can read them and compose an answer.

Usage:
    python scripts/query.py --question "<your question>" [--top 8] [--kb-root .]
"""
import argparse
import sys
from pathlib import Path

# Reuse search logic
sys.path.insert(0, str(Path(__file__).parent))
from search import search_wiki


def main():
    parser = argparse.ArgumentParser(description="Find wiki articles relevant to a question.")
    parser.add_argument("--question", required=True, help="The question to answer")
    parser.add_argument("--top", type=int, default=8, help="Number of articles to retrieve")
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    results = search_wiki(kb_root, args.question, args.top)

    if not results:
        print("No relevant articles found. The wiki may need more content on this topic.")
        return

    print(f"Top {len(results)} articles relevant to: '{args.question}'\n")
    print("=" * 60)
    for r in results:
        full_path = kb_root / r["path"]
        print(f"\n## {r['path']}  (relevance score: {r['score']})\n")
        content = full_path.read_text(encoding="utf-8", errors="replace")
        # Print first 600 chars of body as preview
        print(content[:600])
        if len(content) > 600:
            print(f"\n... [{len(content) - 600} more chars — read the full file for complete content]")
        print("\n" + "-" * 60)


if __name__ == "__main__":
    main()
