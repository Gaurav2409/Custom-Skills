#!/usr/bin/env python3
"""
compile.py — Orchestrate compilation of raw/ documents into the wiki.

Enhanced features:
- Semantic cluster-aware batching (reads cluster_manifest.json from cluster.py)
- Two-pass compilation support (stub pass + synthesis pass)
- Hybrid model routing (Sonnet for entities, Opus for synthesis)
- Compile checkpointing (resume interrupted compiles)
- Priority queue ordering (cross-ref count, recency, source quality)
- Entity registry management
- Temporal coherence detection

Usage:
    python scripts/compile.py [--kb-root .] [--all] [--log] [--batch-size 20]
                              [--resume] [--pass 1|2|both] [--cluster LABEL]
                              [--priority-sort] [--dry-run]

With --all, lists every raw document regardless of whether it's been summarized.
With --log, appends a compile-start entry to wiki/log.md.
With --resume, continues from the last checkpoint.
With --pass, runs only the specified pass (1=stubs, 2=synthesis, both=default).
With --cluster, compiles only documents in the named cluster.
With --priority-sort, orders compilation by priority score.
With --dry-run, shows what would be compiled without making changes.
"""
import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional


SUPPORTED_EXTENSIONS = {
    ".md", ".txt", ".html", ".htm", ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
}

# Source type detection patterns for confidence calibration
SOURCE_TYPE_PATTERNS = {
    "peer_reviewed": {
        "signals": ["doi.org", "arxiv.org", "journal", "proceedings", "IEEE", "ACM"],
        "weight": 1.0
    },
    "official_documentation": {
        "signals": ["help.sap.com", "docs.", "developer.", "documentation", "api-reference"],
        "weight": 0.95
    },
    "internal_adr": {
        "signals": ["ADR-", "Architecture Decision Record", "decision-record"],
        "weight": 0.9
    },
    "internal_design_doc": {
        "signals": ["Design Document", "Technical Specification", "RFC-", "design-doc"],
        "weight": 0.85
    },
    "news_article": {
        "signals": ["news.", "press-release", "announcement"],
        "weight": 0.7
    },
    "tutorial": {
        "signals": ["tutorial", "how-to", "step-by-step", "getting-started", "quickstart"],
        "weight": 0.65
    },
    "blog_post": {
        "signals": ["blog", "medium.com", "dev.to", "hashnode"],
        "weight": 0.5
    },
    "community_forum": {
        "signals": ["stackoverflow", "reddit.com", "community.", "forum", "answers.sap.com"],
        "weight": 0.4
    },
    "social_media": {
        "signals": ["twitter.com", "x.com", "linkedin.com"],
        "weight": 0.3
    },
}


# ── config ────────────────────────────────────────────────────────────────────

def load_config(kb_root: Path) -> dict:
    cfg_path = kb_root / "kb.config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}


def get_skip_patterns(cfg: dict) -> list[str]:
    return cfg.get("ingest", {}).get("quality_filter", {}).get("skip_patterns", [])


def get_compile_config(cfg: dict) -> dict:
    return cfg.get("compile", {})


def matches_skip_pattern(name: str, patterns: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


# ── cluster manifest loading ─────────────────────────────────────────────────

def load_cluster_manifest(kb_root: Path) -> dict:
    """Load cluster_manifest.json produced by cluster.py."""
    manifest_path = kb_root / "cluster_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def get_cluster_for_doc(manifest: dict, doc_path: Path) -> Optional[str]:
    """Return the cluster label for a given document path."""
    clusters = manifest.get("clusters", [])
    doc_str = str(doc_path)
    for cluster in clusters:
        for member in cluster.get("members", []):
            if member.get("path", "") in doc_str or doc_str.endswith(member.get("path", "")):
                return cluster.get("label", "unclustered")
    return "unclustered"


def get_docs_in_cluster(manifest: dict, cluster_label: str) -> list[str]:
    """Return all document paths in a specific cluster."""
    clusters = manifest.get("clusters", [])
    for cluster in clusters:
        if cluster.get("label") == cluster_label:
            return [m.get("path", "") for m in cluster.get("members", [])]
    return []


# ── checkpoint management ────────────────────────────────────────────────────

CHECKPOINT_FILE = ".compile_checkpoint.json"


def load_checkpoint(kb_root: Path) -> dict:
    """Load checkpoint for resume support."""
    cp_path = kb_root / CHECKPOINT_FILE
    if cp_path.exists():
        return json.loads(cp_path.read_text(encoding="utf-8"))
    return {"completed": [], "current_batch": None, "pass": None, "timestamp": None}


def save_checkpoint(kb_root: Path, checkpoint: dict):
    """Save checkpoint after each document is compiled."""
    cp_path = kb_root / CHECKPOINT_FILE
    checkpoint["timestamp"] = datetime.now().isoformat()
    cp_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def clear_checkpoint(kb_root: Path):
    """Remove checkpoint file after successful full compile."""
    cp_path = kb_root / CHECKPOINT_FILE
    if cp_path.exists():
        cp_path.unlink()


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
                    return datetime.strptime(m.group(1), "%Y-%m-%d").date()
                except ValueError:
                    pass
    return None


def is_changed(doc: Path, wiki_dir: Path) -> bool:
    """Return True if the raw doc's mtime is newer than the article's last_updated date."""
    last_updated = get_article_last_updated(wiki_dir, doc.name)
    if last_updated is None:
        return False
    doc_mtime = date.fromtimestamp(doc.stat().st_mtime)
    return doc_mtime > last_updated


# ── source type detection ────────────────────────────────────────────────────

def detect_source_type(doc: Path) -> tuple[str, float]:
    """Detect source type from filename and content. Returns (type, weight)."""
    content = ""
    try:
        if doc.suffix.lower() in (".md", ".txt", ".html", ".htm"):
            content = doc.read_text(encoding="utf-8", errors="replace")[:2000]
    except (OSError, UnicodeDecodeError):
        pass

    combined = f"{doc.name} {content}".lower()

    for source_type, info in SOURCE_TYPE_PATTERNS.items():
        for signal in info["signals"]:
            if signal.lower() in combined:
                return source_type, info["weight"]

    return "blog_post", 0.5  # default


# ── priority scoring ─────────────────────────────────────────────────────────

def compute_priority_score(
    doc: Path,
    manifest: dict,
    wiki_dir: Path,
    compile_cfg: dict
) -> float:
    """
    Compute priority score for a document.
    Formula: cross_ref_count * 0.5 + recency * 0.3 + source_quality * 0.2
    """
    weights = compile_cfg.get("priority_queue", {}).get("weights", {})
    w_xref = weights.get("cross_reference_count", 0.5)
    w_recency = weights.get("recency", 0.3)
    w_quality = weights.get("source_quality", 0.2)

    # Cross-reference count: how many other docs in the cluster reference this one
    xref_score = 0.0
    cluster_label = get_cluster_for_doc(manifest, doc)
    if cluster_label != "unclustered":
        cluster_docs = get_docs_in_cluster(manifest, cluster_label)
        doc_stem = doc.stem.lower()
        for other_path in cluster_docs:
            if other_path == str(doc):
                continue
            try:
                other = Path(other_path)
                if other.exists() and other.suffix.lower() in (".md", ".txt", ".html"):
                    other_content = other.read_text(encoding="utf-8", errors="replace")[:5000].lower()
                    if doc_stem in other_content:
                        xref_score += 1.0
            except (OSError, UnicodeDecodeError):
                pass
        # Normalize to 0-1 (assume max 10 cross-refs)
        xref_score = min(xref_score / 10.0, 1.0)

    # Recency: newer docs get higher scores
    try:
        mtime = doc.stat().st_mtime
        days_old = (datetime.now().timestamp() - mtime) / 86400
        recency_score = max(0, 1.0 - (days_old / 365.0))  # Linear decay over 1 year
    except OSError:
        recency_score = 0.5

    # Source quality
    _, quality_weight = detect_source_type(doc)
    quality_score = quality_weight

    return (w_xref * xref_score) + (w_recency * recency_score) + (w_quality * quality_score)


# ── model routing ────────────────────────────────────────────────────────────

def select_model(doc: Path, manifest: dict, compile_cfg: dict) -> str:
    """
    Select model based on hybrid strategy.
    - Opus for synthesis topics (10+ sources in cluster or cross-ref heavy)
    - Sonnet for entity/factsheet articles
    """
    strategy = compile_cfg.get("model_strategy", {})
    opus_threshold = strategy.get("opus_threshold_sources", 10)
    default_model = strategy.get("default", "sonnet")
    synthesis_model = strategy.get("synthesis_model", "opus")

    cluster_label = get_cluster_for_doc(manifest, doc)
    if cluster_label != "unclustered":
        cluster_docs = get_docs_in_cluster(manifest, cluster_label)
        if len(cluster_docs) >= opus_threshold:
            return synthesis_model

    return default_model


# ── temporal coherence ───────────────────────────────────────────────────────

SUPERSESSION_SIGNALS = [
    "replaces", "supersedes", "deprecates", "updates",
    "this document replaces", "superseded by", "obsoletes",
    "new version of", "revision of", "amended version"
]


def detect_supersession(doc: Path, raw_docs: list[Path]) -> list[dict]:
    """Detect if this document supersedes or is superseded by others."""
    chains = []
    try:
        content = doc.read_text(encoding="utf-8", errors="replace")[:3000].lower()
    except (OSError, UnicodeDecodeError):
        return chains

    # Check for explicit supersession signals
    for signal in SUPERSESSION_SIGNALS:
        if signal in content:
            # Try to identify the referenced document
            for other in raw_docs:
                if other == doc:
                    continue
                other_stem = other.stem.lower().replace("-", " ").replace("_", " ")
                if other_stem in content:
                    chains.append({
                        "newer": str(doc),
                        "older": str(other),
                        "signal": signal
                    })

    # ADR version detection: adr-042-v1 vs adr-042-v2
    adr_match = re.match(r"(adr[_-]?\d+)[_-]v(\d+)", doc.stem.lower())
    if adr_match:
        adr_base = adr_match.group(1)
        adr_version = int(adr_match.group(2))
        for other in raw_docs:
            if other == doc:
                continue
            other_match = re.match(r"(adr[_-]?\d+)[_-]v(\d+)", other.stem.lower())
            if other_match and other_match.group(1) == adr_base:
                other_version = int(other_match.group(2))
                if adr_version > other_version:
                    chains.append({
                        "newer": str(doc),
                        "older": str(other),
                        "signal": f"ADR version {other_version} → {adr_version}"
                    })
                elif other_version > adr_version:
                    chains.append({
                        "newer": str(other),
                        "older": str(doc),
                        "signal": f"ADR version {adr_version} → {other_version}"
                    })

    return chains


# ── entity registry ──────────────────────────────────────────────────────────

def load_entity_registry(wiki_dir: Path) -> dict[str, dict]:
    """Load entity registry as {name: {type, path, aliases}}."""
    registry_path = wiki_dir / "entity_registry.md"
    registry = {}
    if not registry_path.exists():
        return registry

    content = registry_path.read_text(encoding="utf-8", errors="replace")
    for line in content.split("\n"):
        # Parse table rows: | Name | Type | Path | Aliases |
        if line.startswith("|") and not line.startswith("| Entity") and "---" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                name = parts[0]
                registry[name.lower()] = {
                    "name": name,
                    "type": parts[1],
                    "path": parts[2],
                    "aliases": [a.strip() for a in parts[3].split(",") if a.strip()]
                }
    return registry


def entity_exists(name: str, registry: dict[str, dict]) -> Optional[str]:
    """Check if entity exists by name or alias. Returns canonical name or None."""
    name_lower = name.lower()
    if name_lower in registry:
        return registry[name_lower]["name"]
    for entry in registry.values():
        if name_lower in [a.lower() for a in entry.get("aliases", [])]:
            return entry["name"]
    return None


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


# ── batch management ─────────────────────────────────────────────────────────

def create_batches(docs: list[Path], manifest: dict, batch_size: int = 20) -> list[list[Path]]:
    """
    Group documents into batches by cluster.
    Documents in the same cluster are kept together in a batch.
    """
    clusters = manifest.get("clusters", [])
    cluster_doc_map: dict[str, list[Path]] = {}

    for doc in docs:
        cluster_label = get_cluster_for_doc(manifest, doc)
        cluster_doc_map.setdefault(cluster_label, []).append(doc)

    batches = []
    current_batch: list[Path] = []

    for cluster_label, cluster_docs in sorted(cluster_doc_map.items()):
        # If adding this cluster exceeds batch_size, start a new batch
        # (unless the cluster itself is larger than batch_size)
        if len(current_batch) + len(cluster_docs) > batch_size and current_batch:
            batches.append(current_batch)
            current_batch = []

        if len(cluster_docs) > batch_size:
            # Split large clusters into sub-batches
            for i in range(0, len(cluster_docs), batch_size):
                batches.append(cluster_docs[i:i + batch_size])
        else:
            current_batch.extend(cluster_docs)

    if current_batch:
        batches.append(current_batch)

    return batches


# ── log entry ─────────────────────────────────────────────────────────────────

def append_log_entry(
    log_path: Path,
    new_docs: list[Path],
    changed_docs: list[Path],
    batches: list[list[Path]],
    compile_pass: str = "both"
):
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
    if batches:
        lines.append(f"- Batches: {len(batches)} (batch_size≤20)")
    lines.append(f"- Pass: {compile_pass}")
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
        description="Orchestrate compilation of raw documents into the wiki."
    )
    parser.add_argument("--kb-root", default=".", help="Knowledge base root directory")
    parser.add_argument("--all", action="store_true",
                        help="List all raw docs, not just new/changed ones")
    parser.add_argument("--log", action="store_true",
                        help="Append a compile-start entry to wiki/log.md")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="Max documents per compile batch (default: 20)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint")
    parser.add_argument("--pass", dest="compile_pass", choices=["1", "2", "both"],
                        default="both", help="Which compile pass to run")
    parser.add_argument("--cluster", type=str, default=None,
                        help="Only compile documents in this cluster")
    parser.add_argument("--priority-sort", action="store_true",
                        help="Order documents by priority score")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show compile plan without executing")
    args = parser.parse_args()

    kb_root = Path(args.kb_root).resolve()
    wiki_dir = kb_root / "wiki"
    summaries_path = wiki_dir / "_summaries.md"
    log_path = wiki_dir / "log.md"

    cfg = load_config(kb_root)
    compile_cfg = get_compile_config(cfg)
    skip_patterns = get_skip_patterns(cfg)

    # Load cluster manifest
    manifest = load_cluster_manifest(kb_root)
    has_clusters = bool(manifest.get("clusters"))

    # Load checkpoint if resuming
    checkpoint = load_checkpoint(kb_root) if args.resume else {"completed": []}
    completed_set = set(checkpoint.get("completed", []))

    raw_docs = list_raw_docs(kb_root, skip_patterns)
    summarized = load_summarized_names(summaries_path)

    print(f"Knowledge base: {kb_root}")
    print(f"Total raw documents: {len(raw_docs)}")
    print(f"Already summarized:  {len(summarized)}")
    if has_clusters:
        print(f"Clusters loaded:     {len(manifest['clusters'])}")
    if completed_set:
        print(f"Checkpoint (done):   {len(completed_set)}")

    new_docs = [d for d in raw_docs if d.name not in summarized]
    changed_docs = [
        d for d in raw_docs
        if d.name in summarized and wiki_dir.exists() and is_changed(d, wiki_dir)
    ]

    # Filter by cluster if requested
    if args.cluster:
        cluster_paths = set(get_docs_in_cluster(manifest, args.cluster))
        new_docs = [d for d in new_docs if str(d) in cluster_paths or
                    any(str(d).endswith(p) for p in cluster_paths)]
        changed_docs = [d for d in changed_docs if str(d) in cluster_paths or
                        any(str(d).endswith(p) for p in cluster_paths)]

    # Filter out already-checkpointed docs
    if completed_set:
        new_docs = [d for d in new_docs if d.name not in completed_set]
        changed_docs = [d for d in changed_docs if d.name not in completed_set]

    # Priority sorting
    all_to_compile = new_docs + changed_docs
    if args.priority_sort and all_to_compile:
        scored = [(doc, compute_priority_score(doc, manifest, wiki_dir, compile_cfg))
                  for doc in all_to_compile]
        scored.sort(key=lambda x: x[1], reverse=True)
        all_to_compile = [doc for doc, _ in scored]
        # Re-split for display
        new_names = {d.name for d in new_docs}
        new_docs = [d for d in all_to_compile if d.name in new_names]
        changed_docs = [d for d in all_to_compile if d.name not in new_names]

    # Create batches
    batches = create_batches(all_to_compile, manifest, args.batch_size)

    # Confidence distribution
    if wiki_dir.exists():
        dist = confidence_distribution(wiki_dir)
        total_articles = sum(dist.values())
        if total_articles > 0:
            print(f"\nWiki confidence distribution ({total_articles} articles):")
            print(f"  high: {dist['high']}  medium: {dist['medium']}  "
                  f"low: {dist['low']}  unset: {dist['unset']}")

    # Entity registry stats
    if wiki_dir.exists():
        registry = load_entity_registry(wiki_dir)
        if registry:
            print(f"  Entity registry: {len(registry)} entities tracked")

    print()

    # ── Display compile plan ──────────────────────────────────────────────────

    if args.all:
        print("All raw documents:")
        for doc in raw_docs:
            if doc.name not in summarized:
                marker = "○ NEW    "
            elif any(d.name == doc.name for d in changed_docs):
                marker = "↻ CHANGED"
            else:
                marker = "✓ done   "
            cluster = get_cluster_for_doc(manifest, doc) if has_clusters else ""
            model = select_model(doc, manifest, compile_cfg) if has_clusters else ""
            suffix = f"  [{cluster}|{model}]" if cluster else ""
            print(f"  {marker}  {doc.relative_to(kb_root)}{suffix}")
    else:
        if not new_docs and not changed_docs:
            print("✓ All raw documents are already compiled and up-to-date.")
        else:
            if new_docs:
                print(f"New documents to compile ({len(new_docs)}):")
                for doc in new_docs[:30]:
                    model = select_model(doc, manifest, compile_cfg)
                    source_type, weight = detect_source_type(doc)
                    cluster = get_cluster_for_doc(manifest, doc) if has_clusters else ""
                    info = f"[{model}|{source_type}:{weight}]"
                    if cluster and cluster != "unclustered":
                        info += f" cluster:{cluster}"
                    print(f"  ○  {doc.relative_to(kb_root)}  {info}")
                if len(new_docs) > 30:
                    print(f"  ... and {len(new_docs) - 30} more")
            if changed_docs:
                print(f"\nChanged documents to recompile ({len(changed_docs)}):")
                for doc in changed_docs[:10]:
                    print(f"  ↻  {doc.relative_to(kb_root)}")
                if len(changed_docs) > 10:
                    print(f"  ... and {len(changed_docs) - 10} more")

    # ── Batch summary ─────────────────────────────────────────────────────────

    if batches:
        print(f"\nCompile plan: {len(batches)} batch(es), pass={args.compile_pass}")
        for i, batch in enumerate(batches):
            cluster_label = get_cluster_for_doc(manifest, batch[0]) if has_clusters else "mixed"
            print(f"  Batch {i+1}: {len(batch)} docs (cluster: {cluster_label})")

    # ── Two-pass info ─────────────────────────────────────────────────────────

    if compile_cfg.get("two_pass", {}).get("enabled"):
        print(f"\nTwo-pass mode: {'ENABLED' if compile_cfg['two_pass']['enabled'] else 'disabled'}")
        if args.compile_pass in ("1", "both"):
            print(f"  Pass 1 (stubs): {compile_cfg['two_pass'].get('pass_1_model', 'sonnet')}")
        if args.compile_pass in ("2", "both"):
            print(f"  Pass 2 (synthesis): {compile_cfg['two_pass'].get('pass_2_model', 'opus')}")

    # ── Temporal coherence report ─────────────────────────────────────────────

    if compile_cfg.get("temporal_coherence", {}).get("enabled") and all_to_compile:
        supersession_chains = []
        for doc in all_to_compile[:50]:  # Limit scan for performance
            chains = detect_supersession(doc, raw_docs)
            supersession_chains.extend(chains)
        if supersession_chains:
            print(f"\nTemporal coherence: {len(supersession_chains)} supersession chain(s) detected:")
            for chain in supersession_chains[:5]:
                newer = Path(chain["newer"]).name
                older = Path(chain["older"]).name
                print(f"  {older} → {newer} ({chain['signal']})")
            if len(supersession_chains) > 5:
                print(f"  ... and {len(supersession_chains) - 5} more")

    # ── Dry run exit ──────────────────────────────────────────────────────────

    if args.dry_run:
        print("\n[DRY RUN] No changes made. Use without --dry-run to compile.")
        return

    # ── Log entry ─────────────────────────────────────────────────────────────

    if args.log and wiki_dir.exists():
        append_log_entry(log_path, new_docs, changed_docs, batches, args.compile_pass)
        print(f"\nLog entry appended to {log_path.relative_to(kb_root)}")

    # ── Instructions for LLM compile ─────────────────────────────────────────

    if all_to_compile:
        print("\n" + "=" * 70)
        print("COMPILE INSTRUCTIONS FOR LLM")
        print("=" * 70)
        print(f"""
To compile these documents, the LLM should:

1. Load entity registry: wiki/entity_registry.md
2. For each batch (in order):
   a. Read all raw docs in the batch
   b. Pass 1 (if enabled): Create stub articles with entity extraction
      Model: {compile_cfg.get('two_pass', {}).get('pass_1_model', 'sonnet')}
   c. Pass 2 (if enabled): Synthesize across cluster context
      Model: {compile_cfg.get('two_pass', {}).get('pass_2_model', 'opus')}
   d. Run contradiction scan across cluster
   e. Check temporal coherence / supersession
   f. Update entity registry
   g. Save checkpoint after each document

Checkpoint file: {CHECKPOINT_FILE}
Resume with: python scripts/compile.py --resume
""")


if __name__ == "__main__":
    main()
