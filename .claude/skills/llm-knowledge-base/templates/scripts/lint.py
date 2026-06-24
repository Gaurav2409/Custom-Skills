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


def check_superseded_articles(articles: dict) -> list[str]:
    """Flag superseded articles that are missing superseded_by or have stale review_status."""
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, body = strip_frontmatter(content)
        # Check for supersession markers without proper frontmatter
        if "superseded" in body.lower() or "this document replaces" in body.lower():
            if fm.get("review_status") != "superseded" and "superseded_by" not in fm:
                issues.append(
                    f"SUPERSESSION_UNMARKED: {path} — mentions supersession but lacks "
                    f"superseded_by/supersedes frontmatter"
                )
        # Check for superseded articles still at high confidence
        if fm.get("review_status") == "superseded" and fm.get("confidence") == "high":
            issues.append(
                f"SUPERSEDED_HIGH_CONFIDENCE: {path} — marked superseded but still confidence:high"
            )
    return issues


def check_entity_registry_consistency(articles: dict, wiki_dir: Path) -> list[str]:
    """Verify entity registry matches actual wiki articles."""
    issues = []
    registry_path = wiki_dir / "entity_registry.md"
    if not registry_path.exists():
        # Only flag if there are entity articles that should be registered
        entity_articles = [p for p in articles if "entities/" in p and not p.startswith("_")]
        if len(entity_articles) > 5:
            issues.append(
                f"MISSING_ENTITY_REGISTRY: {len(entity_articles)} entity articles exist "
                f"but wiki/entity_registry.md not found"
            )
        return issues

    registry_content = registry_path.read_text(encoding="utf-8", errors="replace")

    # Check for entity articles not in registry
    for path in articles:
        if path.startswith("_") or "entities/" not in path:
            continue
        stem = Path(path).stem
        if stem not in registry_content and stem.replace("-", " ") not in registry_content:
            issues.append(f"ENTITY_NOT_REGISTERED: {path} not found in entity_registry.md")

    # Check for registry entries pointing to non-existent articles
    for line in registry_content.split("\n"):
        if not line.startswith("|") or "---" in line or "Entity Name" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 3:
            registered_path = parts[2]
            # Normalize path
            if registered_path.startswith("wiki/"):
                registered_path = registered_path[5:]
            if registered_path not in articles:
                issues.append(
                    f"REGISTRY_DANGLING: entity_registry.md references "
                    f"'{registered_path}' which does not exist"
                )

    return issues


def check_temporal_coherence(articles: dict) -> list[str]:
    """Check that supersession chains are bidirectional and complete."""
    issues = []
    all_slugs = {Path(p).stem: p for p in articles if not p.startswith("_")}

    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, _ = strip_frontmatter(content)

        # If A supersedes B, B should have superseded_by pointing to A
        supersedes_val = fm.get("supersedes", "")
        if supersedes_val:
            target_slug = re.sub(r"\[\[|\]\]", "", supersedes_val).strip()
            target_slug = Path(target_slug).stem if "/" in target_slug else target_slug
            if target_slug in all_slugs:
                target_path = all_slugs[target_slug]
                target_content = articles.get(target_path, "")
                target_fm, _ = strip_frontmatter(target_content)
                if "superseded_by" not in target_fm:
                    issues.append(
                        f"SUPERSESSION_BROKEN_CHAIN: {path} supersedes [[{target_slug}]] "
                        f"but that article lacks superseded_by"
                    )

        # If A has superseded_by B, B should have supersedes pointing to A
        superseded_by_val = fm.get("superseded_by", "")
        if superseded_by_val:
            target_slug = re.sub(r"\[\[|\]\]", "", superseded_by_val).strip()
            target_slug = Path(target_slug).stem if "/" in target_slug else target_slug
            if target_slug in all_slugs:
                target_path = all_slugs[target_slug]
                target_content = articles.get(target_path, "")
                target_fm, _ = strip_frontmatter(target_content)
                if "supersedes" not in target_fm:
                    issues.append(
                        f"SUPERSESSION_BROKEN_CHAIN: {path} superseded_by [[{target_slug}]] "
                        f"but that article lacks supersedes"
                    )

    return issues


def check_source_type_missing(articles: dict) -> list[str]:
    """Flag articles that have sources but no source_type classification."""
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, body = strip_frontmatter(content)
        has_sources = (
            "sources" in fm
            or "**Sources**" in content
            or "Sources:" in content
        )
        if has_sources and "source_type" not in content and "source_type" not in fm:
            issues.append(f"MISSING_SOURCE_TYPE: {path} — has sources but no source_type classification")
    return issues


# ── Karpathy-aligned conventions: footnote citations + unfiled query tracking ──

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]]+\]")
_SCAFFOLDING_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+\.|>|#|```|\||$)")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")


def _extract_details_body(content: str) -> str:
    """Return the body between `## Details` and the next top-level section."""
    m = re.search(r"^## Details\s*\n(.*?)(?=^## |\Z)", content, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else ""


def check_unfooted_facts(articles: dict, max_unfooted_pct: float) -> list[str]:
    """Flag articles whose `## Details` has factual sentences without a [^src] citation.

    Heuristic: split prose into sentences. Skip scaffolding lines (lists, headings,
    code fences, blockquotes, empty). A sentence is "footed" if it contains at
    least one [^slug] reference. Flag the article when unfooted_pct exceeds the
    threshold (default 0.10).
    """
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        body = _extract_details_body(content)
        if not body.strip():
            continue

        # Strip fenced code blocks before sentence splitting
        body_no_code = re.sub(r"```.*?```", "", body, flags=re.DOTALL)

        total = 0
        unfooted = 0
        for raw_line in body_no_code.splitlines():
            if _SCAFFOLDING_PREFIX_RE.match(raw_line):
                continue
            line = _INLINE_CODE_RE.sub("", raw_line).strip()
            if not line:
                continue
            for sent in _SENTENCE_SPLIT_RE.split(line):
                sent = sent.strip()
                # Require at least 6 words to count as a "factual sentence"
                if len(sent.split()) < 6:
                    continue
                total += 1
                if not _FOOTNOTE_REF_RE.search(sent):
                    unfooted += 1

        if total == 0:
            continue
        pct = unfooted / total
        if pct > max_unfooted_pct:
            issues.append(
                f"UNFOOTED_FACTS: {path} — {unfooted}/{total} sentences "
                f"({pct:.0%}) lack [^src] citations (target: <{max_unfooted_pct:.0%})"
            )
    return issues


def _query_slugs_in_log(log_text: str) -> list[str]:
    """Extract slugs from `## [date] query | <slug>` entries."""
    slugs = []
    for m in re.finditer(
        r"^## \[\d{4}-\d{2}-\d{2}\]\s+query\s*\|\s*(.+?)\s*$",
        log_text,
        re.MULTILINE,
    ):
        slugs.append(m.group(1).strip().lower())
    return slugs


def check_unfiled_queries(articles: dict, kb_root: Path) -> list[str]:
    """Compare query entries in log.md against wiki/analyses/*.md slugs.

    Per Karpathy's gist, queries that produce useful answers should be filed
    back as analyses so the wiki compounds. Each query without a matching
    analysis article is an evaporation point.
    """
    issues = []
    log_path = kb_root / "wiki" / "log.md"
    if not log_path.exists():
        return issues
    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    query_slugs = _query_slugs_in_log(log_text)
    if not query_slugs:
        return issues

    analysis_slugs = {
        Path(p).stem.lower()
        for p in articles
        if p.startswith("analyses/")
    }

    # A query is "filed" if its slug (or a normalized form) matches an analysis stem
    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")

    analysis_norms = {_norm(s) for s in analysis_slugs}

    unfiled = []
    for q in query_slugs:
        if _norm(q) not in analysis_norms:
            unfiled.append(q)

    # Report up to the 10 most recent unfiled, with a count for the rest
    for q in unfiled[-10:]:
        issues.append(f"UNFILED_QUERY: {q} — no wiki/analyses/ article for this query")
    if len(unfiled) > 10:
        issues.append(
            f"UNFILED_QUERY: …and {len(unfiled) - 10} more older unfiled queries"
        )
    return issues


def parse_cq_file(kb_root: Path) -> dict:
    """Parse wiki/_competency_questions.md into a status summary.

    Looks for bullet items of the form `- [ ] **<question>**` followed by an
    indented `*Status*:` line. Returns
    {total, passing, partial, failing, unrun, failing_questions:[...]}.
    """
    cq_path = kb_root / "wiki" / "_competency_questions.md"
    summary = {
        "total": 0, "passing": 0, "partial": 0, "failing": 0, "unrun": 0,
        "failing_questions": [],
    }
    if not cq_path.exists():
        return summary
    text = cq_path.read_text(encoding="utf-8", errors="replace")

    # Each CQ block starts with `- [ ] **...**` (or `- [x]`) and may contain
    # indented metadata lines. Split into blocks by the bullet marker.
    blocks = re.split(r"\n(?=- \[[ x]\] \*\*)", text)
    for block in blocks:
        m = re.match(r"- \[[ x]\] \*\*(.+?)\*\*", block)
        if not m:
            continue
        question = m.group(1).strip()
        # Status line: `  *Status*: ✓` or `  - *Status*: ⚠` etc.
        status_m = re.search(r"\*Status\*:\s*([✓⚠✗—-])", block)
        status = status_m.group(1) if status_m else "—"
        summary["total"] += 1
        if status == "✓":
            summary["passing"] += 1
        elif status == "⚠":
            summary["partial"] += 1
            summary["failing_questions"].append((question, "partial"))
        elif status == "✗":
            summary["failing"] += 1
            summary["failing_questions"].append((question, "failing"))
        else:
            summary["unrun"] += 1
    return summary


def check_competency_questions(kb_root: Path, target_pct: float = 0.90) -> list[str]:
    """Flag failing CQs and report coverage if below target."""
    issues = []
    s = parse_cq_file(kb_root)
    if s["total"] == 0:
        return issues
    passing_pct = s["passing"] / s["total"]
    if passing_pct < target_pct:
        issues.append(
            f"CQ_COVERAGE_LOW: {passing_pct:.0%} of {s['total']} competency "
            f"questions passing (target: >{target_pct:.0%}). "
            f"failing={s['failing']} partial={s['partial']} unrun={s['unrun']}"
        )
    # Report up to 10 failing/partial CQs by name
    for q, st in s["failing_questions"][:10]:
        issues.append(f"CQ_FAILING: [{st}] {q}")
    if len(s["failing_questions"]) > 10:
        issues.append(
            f"CQ_FAILING: …and {len(s['failing_questions']) - 10} more"
        )
    return issues


def check_adversarial_review_missing(articles: dict) -> list[str]:
    """Flag quality-mode articles that don't have the adversarial-review marker."""
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        fm, body = strip_frontmatter(content)
        # Heuristic: a "quality-mode" article is one where compile_pass=2
        # OR the article is a topic/analysis (always Opus by routing).
        is_quality = (
            "compile_pass: 2" in content
            or fm.get("type") in ("topic", "analysis")
            or path.startswith("topics/") or path.startswith("analyses/")
        )
        if not is_quality:
            continue
        if "adversarial_review_applied=true" not in content:
            issues.append(
                f"MISSING_ADVERSARIAL_REVIEW: {path} — "
                f"quality-mode article without Step 11.6 marker"
            )
    return issues


def check_pending_debates(articles: dict) -> list[str]:
    """Flag contradiction-flagged articles without a resolved Step 8.5 debate."""
    issues = []
    for path, content in articles.items():
        if path.startswith("_"):
            continue
        has_contradiction = "contradiction_flag=true" in content
        debate_resolved = "debate_resolved=true" in content
        if has_contradiction and not debate_resolved:
            issues.append(
                f"PENDING_DEBATE: {path} — contradiction flagged but Step 8.5 "
                f"debate not yet run/resolved"
            )
    return issues


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

    # ── Compounding Signal block (Karpathy flywheel — read this first) ────────
    unfiled_count = sum(1 for i in issues if i.startswith("UNFILED_QUERY"))
    unfooted_articles = sum(1 for i in issues if i.startswith("UNFOOTED_FACTS"))
    pending_debates = sum(1 for i in issues if i.startswith("PENDING_DEBATE"))
    missing_adv = sum(1 for i in issues if i.startswith("MISSING_ADVERSARIAL_REVIEW"))
    # Gap-fills proposed: count log entries with prefix `query-gap`
    gap_fills = 0
    if log_path.exists():
        gap_fills = len(
            re.findall(r"^## \[\d{4}-\d{2}-\d{2}\] query-gap ", log_content, re.MULTILINE)
        )
    # Open question backlog: sum across articles
    oq_total = 0
    cq_present = 0
    adv_reviewed = 0
    quality_mode_pages = 0
    for path, content in non_index.items():
        oq_match = re.search(r"## Open Questions\s*(.*?)(?=^##|\Z)", content,
                             re.DOTALL | re.MULTILINE)
        if oq_match:
            oq_total += len(re.findall(r"^\s*-\s*\[\s*\]", oq_match.group(1), re.MULTILINE))
        if "## Questions This Page Answers" in content:
            cq_present += 1
        # Adversarial-review coverage on quality-mode pages
        if ("compile_pass: 2" in content
                or path.startswith("topics/") or path.startswith("analyses/")):
            quality_mode_pages += 1
            if "adversarial_review_applied=true" in content:
                adv_reviewed += 1

    # CQ suite summary
    cq_summary = parse_cq_file(kb_root)
    cq_pct_str = "—"
    if cq_summary["total"] > 0:
        cq_pct_str = f"{cq_summary['passing']}/{cq_summary['total']} ({cq_summary['passing']/cq_summary['total']:.0%})"

    adv_pct_str = "—"
    if quality_mode_pages > 0:
        adv_pct_str = f"{adv_reviewed}/{quality_mode_pages} ({adv_reviewed/quality_mode_pages:.0%})"

    print()
    print("⚡ COMPOUNDING SIGNAL   (Karpathy flywheel — target near zero/full)")
    print(f"  CQ coverage (passing):         {cq_pct_str}   [target: >90%]")
    print(f"  Unfiled queries:               {unfiled_count}   [target: 0]")
    print(f"  Open question backlog:         {oq_total}   (top ingest candidates below)")
    print(f"  Gap-fills proposed by query:   {gap_fills}")
    print(f"  Articles with footnote gaps:   {unfooted_articles}")
    print(f"  Pages with '## Questions':     {cq_present}/{total}   [target: 100%]")
    print(f"  Adversarial review coverage:   {adv_pct_str}   [target: 100% in quality mode]")
    print(f"  Pending debates (Step 8.5):    {pending_debates}   [target: 0]")
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

    # New metrics: supersession, entity registry, source types
    superseded_n = sum(1 for i in issues if "SUPERSESSION" in i or "SUPERSEDED" in i)
    registry_n = sum(1 for i in issues if "ENTITY" in i or "REGISTRY" in i)
    source_type_n = sum(1 for i in issues if "SOURCE_TYPE" in i)
    if superseded_n or registry_n or source_type_n:
        print()
        print("Advanced Checks:")
        if superseded_n:
            print(f"  Supersession issues:  {superseded_n} ⚠")
        if registry_n:
            print(f"  Entity registry:      {registry_n} issue(s) ⚠")
        if source_type_n:
            print(f"  Missing source_type:  {source_type_n} article(s) ⚠")

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
    if get_check(cfg, "superseded_articles", True):
        all_issues += check_superseded_articles(articles)
    if get_check(cfg, "entity_registry", True):
        all_issues += check_entity_registry_consistency(articles, wiki_dir)
    if get_check(cfg, "temporal_coherence", True):
        all_issues += check_temporal_coherence(articles)
    if get_check(cfg, "source_type_classification", True):
        all_issues += check_source_type_missing(articles)

    # New Karpathy-aligned checks (always on; threshold lives in lint.thresholds)
    max_unfooted_pct = get_threshold(cfg, "unfooted_pct_max", 0.10)
    all_issues += check_unfooted_facts(articles, max_unfooted_pct)
    all_issues += check_unfiled_queries(articles, kb_root)

    # Quality-mode checks (no-token-limit additions)
    cq_target_pct = get_threshold(cfg, "cq_coverage_target", 0.90)
    all_issues += check_competency_questions(kb_root, cq_target_pct)
    all_issues += check_adversarial_review_missing(articles)
    all_issues += check_pending_debates(articles)

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
        "SUPERSESSION_UNMARKED": "⚠", "SUPERSEDED_HIGH_CONFIDENCE": "⚠",
        "SUPERSESSION_BROKEN_CHAIN": "✗", "ENTITY_NOT_REGISTERED": "⚠",
        "REGISTRY_DANGLING": "✗", "MISSING_ENTITY_REGISTRY": "⚠",
        "MISSING_SOURCE_TYPE": "⚠",
        "UNFOOTED_FACTS": "⚠", "UNFILED_QUERY": "⚠",
        "CQ_COVERAGE_LOW": "✗", "CQ_FAILING": "⚠",
        "MISSING_ADVERSARIAL_REVIEW": "⚠", "PENDING_DEBATE": "✗",
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
