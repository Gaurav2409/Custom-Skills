#!/usr/bin/env python3
"""
OKF Bundle Reader — efficient retrieval helper for OKF-conformant KBs.

Usage:
    python3 okf_read.py <kb_path>                          # show summary
    python3 okf_read.py <kb_path> --type concept           # filter by type
    python3 okf_read.py <kb_path> --tag joule              # filter by tag
    python3 okf_read.py <kb_path> --type entity --tag mcp  # combined
    python3 okf_read.py <kb_path> --search "auth"          # search title/desc
    python3 okf_read.py <kb_path> --get concepts/foo       # read full article
    python3 okf_read.py <kb_path> --graph                  # cross-link graph

Designed to be invoked by Claude/Hermes for fast metadata-driven retrieval.
"""

import argparse, re, sys, json
from pathlib import Path

RESERVED = {"_index.md","_summaries.md","log.md","_competency_questions.md",
            "entity_registry.md","_cluster_summaries.md",
            "_index-concepts.md","_index-entities.md","_index-topics.md"}


def parse_frontmatter(path: Path) -> dict | None:
    """Read first ~50 lines and return frontmatter dict (None if no fm)."""
    try:
        with open(path, errors='ignore') as f:
            head = "".join(f.readline() for _ in range(60))
    except Exception:
        return None
    if not head.startswith("---"):
        return None
    end = head.find("\n---", 3)
    if end < 0:
        return None
    fm_text = head[3:end]

    fm = {}
    # type
    m = re.search(r'^\s*type\s*:\s*(.+?)\s*$', fm_text, re.MULTILINE)
    if m: fm['type'] = m.group(1).strip().strip('"\'')
    # title
    m = re.search(r'^\s*title\s*:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if m: fm['title'] = m.group(1).strip()
    # description
    m = re.search(r'^\s*description\s*:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if m: fm['description'] = m.group(1).strip()
    # tags
    m = re.search(r'^\s*tags\s*:\s*\[(.+?)\]', fm_text, re.MULTILINE)
    if m:
        fm['tags'] = [t.strip().strip('"\'') for t in re.findall(r'["\']?([\w\-]+)["\']?', m.group(1))]
    # last_updated / timestamp
    m = re.search(r'^\s*(?:last_updated|timestamp)\s*:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if m: fm['updated'] = m.group(1).strip()
    return fm


def index_bundle(wiki: Path) -> list[dict]:
    """Return list of {path, type, title, description, tags, updated} for all articles."""
    articles = []
    for f in wiki.rglob("*.md"):
        if f.name in RESERVED:
            continue
        fm = parse_frontmatter(f)
        if not fm:
            continue
        articles.append({
            'path': str(f.relative_to(wiki)),
            'concept_id': str(f.relative_to(wiki))[:-3],
            **fm
        })
    return articles


def filter_articles(articles: list[dict], type_=None, tag=None, search=None,
                    fuzzy_tag=True, search_body_fallback=False, wiki=None,
                    body_recall=False) -> list[dict]:
    """Filter with quality safeguards.

    fuzzy_tag: match tag as substring case-insensitively (default True) so --tag mcp
               also matches articles tagged 'mcp-protocol', 'MCP', 'sap-mcp', etc.
    search_body_fallback: if --search returns 0 frontmatter hits, scan article bodies.
    body_recall: when filtering by tag, ALSO include articles whose bodies discuss
                 the term but aren't tagged. Trades speed for recall — recommended
                 default for research questions where missing 1 article is worse
                 than reading 5 extra.
    """
    out = articles
    if type_:
        out = [a for a in out if a.get('type') == type_]

    if tag:
        tl = tag.lower()
        # Step 1: metadata match (fast)
        if fuzzy_tag:
            metadata_hits = [a for a in out
                             if any(tl in t.lower() for t in a.get('tags', []))]
        else:
            metadata_hits = [a for a in out if tag in a.get('tags', [])]

        # Step 2: optional body recall pass (slower but higher recall)
        if body_recall and wiki:
            metadata_ids = {a['concept_id'] for a in metadata_hits}
            # Search both the literal tag and a "humanized" form (mcp-protocol -> mcp protocol)
            search_terms = {tl, tl.replace('-', ' '), tl.replace('_', ' ')}
            body_hits = []
            for a in out:
                if a['concept_id'] in metadata_ids:
                    continue
                p = wiki / f"{a['concept_id']}.md"
                try:
                    body = p.read_text(errors='ignore').lower()
                    if any(term in body for term in search_terms):
                        a = {**a, '_via_body': True}
                        body_hits.append(a)
                except Exception:
                    pass
            out = metadata_hits + body_hits
        else:
            out = metadata_hits

    if search:
        s = search.lower()
        fm_hits = [a for a in out
                   if s in a.get('title','').lower()
                   or s in a.get('description','').lower()
                   or s in a['concept_id'].lower()]
        if fm_hits or not search_body_fallback or not wiki:
            out = fm_hits
        else:
            body_hits = []
            for a in out:
                p = wiki / f"{a['concept_id']}.md"
                try:
                    if s in p.read_text(errors='ignore').lower():
                        a = {**a, '_via_body': True}
                        body_hits.append(a)
                except Exception:
                    pass
            out = body_hits
    return out


def show_summary(articles: list[dict]):
    print(f"# Bundle Summary\n")
    print(f"Total articles: {len(articles)}")
    types = {}
    tags = {}
    for a in articles:
        t = a.get('type', 'untyped')
        types[t] = types.get(t, 0) + 1
        for tag in a.get('tags', []):
            tags[tag] = tags.get(tag, 0) + 1
    print(f"\n## Types")
    for t, n in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  - {t}: {n}")
    print(f"\n## Top tags")
    for tag, n in sorted(tags.items(), key=lambda x: -x[1])[:15]:
        print(f"  - {tag}: {n}")


def show_list(articles: list[dict]):
    print(f"# {len(articles)} matching articles\n")
    via_body = sum(1 for a in articles if a.get('_via_body'))
    if via_body:
        print(f"  ({len(articles)-via_body} via metadata + {via_body} via body recall)\n")
    for a in articles:
        title = a.get('title', a['concept_id'])
        desc = a.get('description', '')
        tags = ', '.join(a.get('tags', [])[:5])
        marker = " [body]" if a.get('_via_body') else ""
        print(f"- [{a['concept_id']}]{marker} {title}")
        if desc: print(f"    {desc}")
        if tags: print(f"    tags: {tags}")


def get_article(wiki: Path, concept_id: str):
    path = wiki / f"{concept_id}.md"
    if not path.exists():
        print(f"NOT FOUND: {path}", file=sys.stderr)
        sys.exit(1)
    print(path.read_text())


def show_graph(wiki: Path, articles: list[dict]):
    """Build cross-link graph from [[wikilinks]] in bodies."""
    print("# Cross-link graph\n")
    graph = {}
    for a in articles:
        path = wiki / f"{a['concept_id']}.md"
        try:
            body = path.read_text(errors='ignore')
        except: continue
        links = set()
        for m in re.finditer(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', body):
            target = m.group(1).strip()
            links.add(target)
        if links:
            graph[a['concept_id']] = sorted(links)

    for src, tgts in sorted(graph.items()):
        for t in tgts:
            print(f"{src} -> {t}")


def main():
    ap = argparse.ArgumentParser(description="Read an OKF-conformant KB efficiently")
    ap.add_argument("kb_path", help="Path to KB root (containing wiki/) or to wiki/ itself")
    ap.add_argument("--type", dest="type_", help="Filter by type (concept|entity|topic|analysis)")
    ap.add_argument("--tag", help="Filter by tag")
    ap.add_argument("--search", help="Substring search in title/description/concept_id")
    ap.add_argument("--get", help="Read full markdown for concept_id (e.g. concepts/foo)")
    ap.add_argument("--graph", action="store_true", help="Print cross-link graph")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    ap.add_argument("--strict-tag", action="store_true",
                    help="Disable fuzzy tag matching (default: --tag mcp matches mcp-protocol, MCP, etc.)")
    ap.add_argument("--no-body-fallback", action="store_true",
                    help="Disable body-text fallback when --search returns 0 frontmatter hits")
    ap.add_argument("--show-coverage", action="store_true",
                    help="Show what fraction of total articles the filter retained (recall sanity check)")
    ap.add_argument("--high-recall", action="store_true",
                    help="When using --tag, also include articles whose bodies discuss the term "
                         "(slower but recommended for research questions; metadata-only misses ~60%% of relevant articles)")
    args = ap.parse_args()

    kb_path = Path(args.kb_path).expanduser().resolve()
    wiki = kb_path / "wiki" if (kb_path / "wiki").exists() else kb_path
    if not wiki.exists():
        print(f"No wiki/ at {kb_path}", file=sys.stderr); sys.exit(1)

    if args.get:
        get_article(wiki, args.get)
        return

    articles = index_bundle(wiki)
    filtered = filter_articles(
        articles, args.type_, args.tag, args.search,
        fuzzy_tag=not args.strict_tag,
        search_body_fallback=not args.no_body_fallback,
        wiki=wiki,
        body_recall=args.high_recall,
    )

    if args.show_coverage:
        pct = (len(filtered) / max(1, len(articles))) * 100
        print(f"# Coverage: {len(filtered)}/{len(articles)} articles ({pct:.0f}%)\n", file=sys.stderr)
        if len(filtered) == 0 and (args.type_ or args.tag or args.search):
            print(f"# WARNING: filter matched zero articles — consider broadening", file=sys.stderr)
        elif len(filtered) > 0 and len(filtered) < 3 and (args.type_ and args.tag):
            print(f"# NOTE: very narrow filter — re-running with type-only for comparison...", file=sys.stderr)
            broad = filter_articles(articles, args.type_, None, args.search,
                                    fuzzy_tag=not args.strict_tag,
                                    search_body_fallback=not args.no_body_fallback,
                                    wiki=wiki)
            print(f"# Broader (type only): {len(broad)} articles\n", file=sys.stderr)

    if args.graph:
        show_graph(wiki, filtered)
        return

    if args.json:
        print(json.dumps(filtered, indent=2))
        return

    if not (args.type_ or args.tag or args.search):
        show_summary(articles)
    else:
        show_list(filtered)


if __name__ == "__main__":
    main()
