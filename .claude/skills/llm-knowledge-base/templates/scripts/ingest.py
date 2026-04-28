#!/usr/bin/env python3
"""
ingest.py — Add a source document to the knowledge base raw/ directory.

Usage:
    python scripts/ingest.py --url <url> [--type article|paper]
    python scripts/ingest.py --file <path> [--type article|paper|image|repo]
    python scripts/ingest.py --text "<pasted text>" --title "<title>" [--type article]
"""
import argparse
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SUBDIR_MAP = {
    "article": "articles",
    "paper": "papers",
    "image": "images",
    "repo": "repos",
}

EXT_TO_TYPE = {
    ".md": "article",
    ".txt": "article",
    ".html": "article",
    ".htm": "article",
    ".pdf": "paper",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:80]


def load_config(kb_root: Path) -> dict:
    config_path = kb_root / "kb.config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def fetch_url(url: str) -> str:
    """Fetch a URL and return its content as plain text/markdown."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    # Strip HTML tags for a naive markdown conversion
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def ingest_url(kb_root: Path, url: str, doc_type: str) -> Path:
    print(f"Fetching {url} ...")
    content = fetch_url(url)
    title = slugify(url.split("/")[-1] or url.split("/")[-2] or "article")
    subdir = SUBDIR_MAP.get(doc_type, "articles")
    dest = kb_root / "raw" / subdir / f"{title}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"---\nsource_url: {url}\ntype: {doc_type}\n"
        f"ingested: {datetime.now(timezone.utc).isoformat()}\n---\n\n"
    )
    dest.write_text(header + content, encoding="utf-8")
    print(f"Saved → {dest}")
    return dest


def ingest_file(kb_root: Path, src: Path, doc_type: str) -> Path:
    ext = src.suffix.lower()
    if doc_type is None:
        doc_type = EXT_TO_TYPE.get(ext, "article")
    subdir = SUBDIR_MAP.get(doc_type, "articles")
    dest = kb_root / "raw" / subdir / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"Copied → {dest}")
    return dest


def ingest_text(kb_root: Path, text: str, title: str, doc_type: str) -> Path:
    subdir = SUBDIR_MAP.get(doc_type, "articles")
    slug = slugify(title)
    dest = kb_root / "raw" / subdir / f"{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"---\ntitle: {title}\ntype: {doc_type}\n"
        f"ingested: {datetime.now(timezone.utc).isoformat()}\n---\n\n"
    )
    dest.write_text(header + text, encoding="utf-8")
    print(f"Saved → {dest}")
    return dest


def main():
    parser = argparse.ArgumentParser(description="Ingest a source document into the knowledge base.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="URL to fetch and ingest")
    group.add_argument("--file", help="Local file path to ingest")
    group.add_argument("--text", help="Text content to ingest (requires --title)")
    parser.add_argument("--type", choices=list(SUBDIR_MAP.keys()), help="Document type")
    parser.add_argument("--title", help="Title for --text ingestion")
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory (default: .)")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    if not (kb_root / "kb.config.json").exists():
        print(f"Warning: No kb.config.json found in {kb_root}. Continuing anyway.", file=sys.stderr)

    doc_type = args.type or "article"

    if args.url:
        ingest_url(kb_root, args.url, doc_type)
    elif args.file:
        ingest_file(kb_root, Path(args.file).resolve(), args.type)
    elif args.text:
        if not args.title:
            parser.error("--text requires --title")
        ingest_text(kb_root, args.text, args.title, doc_type)


if __name__ == "__main__":
    main()
