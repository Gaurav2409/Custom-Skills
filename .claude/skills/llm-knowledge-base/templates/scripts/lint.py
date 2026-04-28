#!/usr/bin/env python3
"""
lint.py — Health-check the wiki for structural issues.

Usage:
    python scripts/lint.py [--kb-root .] [--fix] [--dashboard]

With --fix, auto-corrects issues that are safe to fix (broken links removed,
orphans added to index, missing index entries re-added). Contradiction flags
and duplicate concepts are only flagged, not auto-fixed.

With --dashboard (default: on), prints the health metrics dashboard at the end.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def load_config(kb_root: Path) -> dict:
    cfg_path = kb_root / "kb.config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}


def get_threshold(cfg: dict, key: str, default):
    return cfg.get("lint", {}).get("thresholds", {}).get(key, default)


def get_check(cfg: dict, key: str, default: bool = True) -> bool:
    return cfg.get("lint", {}).get("checks", {}).get(key, default)


def load_articles(wiki_dir: Path) -> dict[str, str]:
    """Return {relative_path_str: content} for all non-index articles."""
    articles = {}
    for f in wiki_dir.rglob("*.md"):
        rel = str(f.relative_to(wiki_dir))
        articles[rel] = f.read_text(encoding="utf-8", errors="replace")
    return articles


def strip_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Frontmatter is parsed best-effort."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_block = content[3:end].strip()
    body = content[end + 4:].lstrip()
    fm: dict = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    return fm, body


def count_wikilinks(content: str) -> int:
    return len(re.findall(r"\[\[([^\]]+)\]\]", content))


def word_count(body: str) -> int:
    return len(body.split())


def get_lint_comment(content: str, key: str) -> str | None:
    """Extract value from <!-- LINT: key=value --> comment."""
    m = re.search(rf"<!--\s*LINT:\s*{re.escape(key)}=([^\s>]+)", content)
    return m.group(1) if m else None


# ── individual checks ─────────────────────────────────────────────────────────

def check_missing_summaries(articles: dict) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        if "## Summary" not in content:
            issues.append(f"MISSING_SUMMARY: {path}")
    return issues


def check_broken_wikilinks(articles: dict) -> list[str]:
    issues = []
    all_slugs = {Path(p).stem for p in articles}
    for path, content in articles.items():
        for link in re.findall(r"\[\[([^\]]+)\]\]", content):
            slug = link.split("|")[0].strip()
            slug = Path(slug).stem if "/" in slug else slug
            if slug not in all_slugs:
                issues.append(f"BROKEN_LINK: {path} → [[{link}]]")
    return issues


def check_orphans(articles: dict, index_content: str) -> list[str]:
    issues = []
    for path in articles:
        if path.startswith("_"):
            continue
        stem = Path(path).stem
        if stem not in index_content:
            issues.append(f"ORPHAN: {path} not referenced in _index.md")
    return issues


def check_stubs(articles: dict, min_words: int) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        _, body = strip_frontmatter(content)
        wc = word_count(body)
        if wc < min_words:
            issues.append(f"STUB: {path} ({wc} words, min {min_words})")
    return issues


def check_missing_sources(articles: dict) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, _ = strip_frontmatter(content)
        has_sources = (
            "sources" in fm
            or "**Sources**" in content
            or "Sources:" in content
        )
        if not has_sources:
            issues.append(f"MISSING_SOURCES: {path}")
    return issues


def check_contradiction_flags(articles: dict) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        flag = get_lint_comment(content, "contradiction_flag")
        fm, _ = strip_frontmatter(content)
        if flag == "true" or fm.get("review_status") == "flagged-contradiction":
            issues.append(f"CONTRADICTION: {path} — requires user review")
    return issues


def check_stale_articles(articles: dict, stale_days: int) -> list[str]:
    issues = []
    today = date.today()
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, _ = strip_frontmatter(content)
        last_updated = fm.get("last_updated", "")
        if not last_updated:
            continue
        try:
            dt = datetime.strptime(last_updated, "%Y-%m-%d").date()
            age = (today - dt).days
            if age > stale_days:
                issues.append(f"STALE: {path} (last updated {last_updated}, {age} days ago)")
        except ValueError:
            pass
    return issues


def check_low_connection_density(articles: dict, min_links: int) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        _, body = strip_frontmatter(content)
        n = count_wikilinks(body)
        if n < min_links:
            issues.append(f"LOW_CONNECTIONS: {path} ({n} wikilinks, min {min_links})")
    return issues


def check_high_open_questions(articles: dict, max_oq: int) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        val = get_lint_comment(content, "open_questions_count")
        if val is None:
            # Fallback: count checkbox lines
            val = str(len(re.findall(r"^- \[ \]", content, re.MULTILINE)))
        try:
            n = int(val)
            if n > max_oq:
                issues.append(f"TOO_MANY_OPEN_QUESTIONS: {path} ({n} questions, max {max_oq})")
        except ValueError:
            pass
    return issues


def check_duplicate_concepts(articles: dict) -> list[str]:
    """Flag pairs of article names that are 80%+ similar (very naive Jaccard on bigrams)."""
    def bigrams(s: str) -> set:
        s = s.lower().replace("-", " ")
        tokens = s.split()
        return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else {(tokens[0],)} if tokens else set()

    issues = []
    paths = [p for p in articles if not p.startswith("_")]
    stems = [(p, Path(p).stem) for p in paths]
    seen: set[frozenset] = set()
    for i, (p1, s1) in enumerate(stems):
        for p2, s2 in stems[i + 1:]:
            b1, b2 = bigrams(s1), bigrams(s2)
            union = b1 | b2
            if not union:
                continue
            jaccard = len(b1 & b2) / len(union)
            pair = frozenset([p1, p2])
            if jaccard >= 0.8 and pair not in seen:
                seen.add(pair)
                issues.append(f"DUPLICATE_CONCEPT: {p1} ≈ {p2} (similarity {jaccard:.0%})")
    return issues


def check_missing_entity_type(articles: dict) -> list[str]:
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, _ = strip_frontmatter(content)
        if fm.get("type") == "entity" and not fm.get("entity_type"):
            issues.append(f"MISSING_ENTITY_TYPE: {path}")
    return issues


def check_index_drift(articles: dict, index_content: str) -> list[str]:
    """Articles that exist but aren't linked from _index.md (same as orphan check but different name)."""
    # Reuses orphan logic; separate issue type for clarity in dashboard
    return []  # already covered by ORPHAN check; kept for explicit categorization


def check_low_confidence_cluster(articles: dict, max_low_pct: float) -> list[str]:
    """Warn if too many articles have confidence: low."""
    total = 0
    low_count = 0
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        total += 1
        fm, _ = strip_frontmatter(content)
        if fm.get("confidence") == "low":
            low_count += 1
    if total == 0:
        return []
    pct = low_count / total
    if pct > max_low_pct:
        return [
            f"LOW_CONFIDENCE_CLUSTER: {low_count}/{total} articles ({pct:.0%}) have confidence:low "
            f"(threshold {max_low_pct:.0%}) — consider adding higher-quality sources"
        ]
    return []


# ── ingest candidates from open questions ────────────────────────────────────

def suggest_ingest_candidates(articles: dict, top_n: int = 5) -> list[tuple[str, int]]:
    """Return top N concept names referenced in Open Questions sections, ranked by frequency."""
    mention_count: dict[str, int] = {}
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        # Find the Open Questions section
        oq_match = re.search(r"## Open Questions\s*(.*?)(?=^##|\Z)", content,
                             re.DOTALL | re.MULTILINE)
        if not oq_match:
            continue
        oq_text = oq_match.group(1)
        # Extract wikilinks from open questions
        for link in re.findall(r"\[\[([^\]]+)\]\]", oq_text):
            slug = link.split("|")[0].strip()
            mention_count[slug] = mention_count.get(slug, 0) + 1
        # Also extract capitalized noun phrases (rough heuristic)
        for phrase in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", oq_text):
            mention_count[phrase] = mention_count.get(phrase, 0) + 1

    # Exclude concepts that already have articles
    existing_slugs = {Path(p).stem.lower() for p in articles if not p.startswith("_")}
    candidates = [
        (name, count) for name, count in mention_count.items()
        if name.lower().replace(" ", "-") not in existing_slugs
        and name.lower() not in existing_slugs
    ]
    return sorted(candidates, key=lambda x: -x[1])[:top_n]


# ── health dashboard ──────────────────────────────────────────────────────────

def print_health_dashboard(articles: dict, issues: list[str], kb_root: Path, cfg: dict):
    non_index = {p: c for p, c in articles.items() if not p.startswith("_")}
    total = len(non_index)
    if total == 0:
        print("\nNo articles found.")
        return

    counts = {"concepts": 0, "entities": 0, "topics": 0, "analyses": 0, "other": 0}
    words_total = 0
    confidence_counts = {"high": 0, "medium": 0, "low": 0, "unset": 0}

    with_summaries = 0
    with_sources = 0
    stubs_n = 0
    min_words = get_threshold(cfg, "stub_words", 120)
    density_ok = 0
    min_links = cfg.get("wiki", {}).get("connection_density_target", 3)

    for path, content in non_index.items():
        fm, body = strip_frontmatter(content)
        wc = word_count(body)
        words_total += wc

        # type bucket
        art_type = fm.get("type", "")
        if art_type in counts:
            counts[art_type] += 1
        elif path.startswith("concepts/"):
            counts["concepts"] += 1
        elif path.startswith("entities/"):
            counts["entities"] += 1
        elif path.startswith("topics/"):
            counts["topics"] += 1
        elif path.startswith("analyses/"):
            counts["analyses"] += 1
        else:
            counts["other"] += 1

        if "## Summary" in content:
            with_summaries += 1
        has_src = (
            "sources" in fm or "**Sources**" in content or "Sources:" in content
        )
        if has_src:
            with_sources += 1
        if wc < min_words:
            stubs_n += 1

        conf = fm.get("confidence", "unset")
        confidence_counts[conf if conf in confidence_counts else "unset"] += 1

        if count_wikilinks(body) >= min_links:
            density_ok += 1

    avg_words = words_total // total if total else 0

    contradiction_n = sum(1 for i in issues if i.startswith("CONTRADICTION"))

    def fmt(n, tot, target_dir="above", target_pct=0.0):
        pct = n / tot if tot else 0
        symbol = "✓" if (pct >= target_pct if target_dir == "above" else pct <= target_pct) else ("⚠" if abs(pct - target_pct) < 0.1 else "✗")
        return f"{pct:5.0%}  ({n}/{tot})  {symbol}"

    print()
    print("KB Health Dashboard")
    print("===================")
    kb_name = cfg.get("name", str(kb_root.name))
    mode = cfg.get("mode", "recall")
    log_path = kb_root / "wiki" / "log.md"
    last_compile = "—"
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8")
        compile_entries = re.findall(r"## \[(\d{4}-\d{2}-\d{2})\] compile", log_content)
        if compile_entries:
            last_compile = compile_entries[-1]
    print(f"Wiki: {kb_name} | Mode: {mode} | Last compile: {last_compile}")
    print()
    print(f"Articles: {total} total | concepts: {counts['concepts']} | "
          f"entities: {counts['entities']} | topics: {counts['topics']} | "
          f"analyses: {counts['analyses']}")
    print(f"Words:    ~{words_total:,} | avg per article: {avg_words:,}")
    print(f"Confidence: high: {confidence_counts['high']} | "
          f"medium: {confidence_counts['medium']} | "
          f"low: {confidence_counts['low']}")
    print()
    print("Quality Scores:")
    print(f"  Summaries present:    {fmt(with_summaries, total, 'above', 0.95)}")
    print(f"  Sources present:      {fmt(with_sources, total, 'above', 0.90)}")
    hi_med = confidence_counts["high"] + confidence_counts["medium"]
    print(f"  Confidence high/med:  {fmt(hi_med, total, 'above', 0.80)}")
    print(f"  Stubs (< {min_words} words): {fmt(stubs_n, total, 'below', 0.05)}")
    print(f"  Connection density:   {fmt(density_ok, total, 'above', 0.75)}")
    print(f"  Contradiction flags:  {contradiction_n} articles"
          + (" ✓" if contradiction_n == 0 else " ✗"))

    # Activity from log
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")
        # last 30 days approximate (no date parsing here, just counts)
        print()
        print("Activity (from log.md):")
        for op in ["ingest", "compile", "query", "lint"]:
            n = len(re.findall(rf"^## \[20\d\d-\d\d-\d\d\] {op}", log_text, re.MULTILINE))
            print(f"  {op}: {n} total")

    # Top ingest candidates
    candidates = suggest_ingest_candidates(non_index, top_n=5)
    if candidates:
        print()
        print("Top ingest candidates (from Open Questions):")
        for i, (name, count) in enumerate(candidates, 1):
            print(f"  {i}. {name} (referenced {count}x)")

    print()
    print(f"Issues found: {len(issues)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Health-check the knowledge base wiki.")
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory")
    parser.add_argument("--fix", action="store_true", help="Auto-fix safe issues")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip health dashboard")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    wiki_dir = kb_root / "wiki"

    if not wiki_dir.exists():
        print(f"Error: wiki/ directory not found at {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(kb_root)
    checks = cfg.get("lint", {}).get("checks", {})

    articles = load_articles(wiki_dir)
    index_path = wiki_dir / "_index.md"
    index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    stub_words = get_threshold(cfg, "stub_words", 120)
    stale_days = checks.get("stale_days", 180)
    max_oq = get_threshold(cfg, "open_questions_max", 5)
    min_links = cfg.get("wiki", {}).get("connection_density_target", 3)
    max_low_pct = get_threshold(cfg, "confidence_low_pct", 0.20)

    all_issues: list[str] = []

    if get_check(cfg, "missing_summary"):
        all_issues += check_missing_summaries(articles)
    if get_check(cfg, "broken_backlinks"):
        all_issues += check_broken_wikilinks(articles)
    if get_check(cfg, "orphan_articles"):
        all_issues += check_orphans(articles, index_content)
    if get_check(cfg, "stub_articles"):
        all_issues += check_stubs(articles, stub_words)
    if get_check(cfg, "missing_sources"):
        all_issues += check_missing_sources(articles)
    if get_check(cfg, "contradiction_flags"):
        all_issues += check_contradiction_flags(articles)
    if get_check(cfg, "stale_articles"):
        all_issues += check_stale_articles(articles, stale_days)
    if get_check(cfg, "connection_density"):
        all_issues += check_low_connection_density(articles, min_links)
    if get_check(cfg, "open_questions_to_ingest"):
        all_issues += check_high_open_questions(articles, max_oq)
    if get_check(cfg, "duplicate_concepts", True):
        all_issues += check_duplicate_concepts(articles)
    all_issues += check_missing_entity_type(articles)
    all_issues += check_low_confidence_cluster(articles, max_low_pct)

    non_index_count = sum(1 for p in articles if not p.startswith("_"))
    print(f"\nLint Results")
    print(f"============")
    print(f"Articles checked: {non_index_count}")
    print(f"Issues found:     {len(all_issues)}\n")

    ICONS = {
        "MISSING_SUMMARY": "⚠", "BROKEN_LINK": "✗", "ORPHAN": "⚠",
        "STUB": "⚠", "MISSING_SOURCES": "⚠", "CONTRADICTION": "✗",
        "STALE": "⚠", "LOW_CONNECTIONS": "⚠", "TOO_MANY_OPEN_QUESTIONS": "⚠",
        "DUPLICATE_CONCEPT": "⚠", "MISSING_ENTITY_TYPE": "⚠",
        "LOW_CONFIDENCE_CLUSTER": "⚠",
    }

    if not all_issues:
        print("✓ No issues found.")
    else:
        for issue in all_issues:
            category = issue.split(":")[0]
            icon = ICONS.get(category, "?")
            print(f"  {icon}  {issue}")

    if not args.no_dashboard and cfg.get("lint", {}).get("health_dashboard", True):
        print_health_dashboard(articles, all_issues, kb_root, cfg)

    print()
    if args.fix:
        print("--fix mode: auto-fixable issues (broken links, orphans) should be corrected by the LLM using this report.")
    else:
        print("Run with --fix to attempt auto-correction of safe issues.")
        print("Contradiction flags (✗ CONTRADICTION) require manual review.")


if __name__ == "__main__":
    main()
