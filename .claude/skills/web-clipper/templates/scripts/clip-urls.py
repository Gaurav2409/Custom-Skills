#!/usr/bin/env python3
"""clip-urls.py — Playwright-based web clipper with KB-format output.

Renders each URL with headless Chromium, extracts main content using
Mozilla Readability, strips all nav/sidebar/footer noise, and saves
clean markdown with YAML frontmatter.

RAW STORAGE CONTRACT:
  Saved files contain ONLY the source page's content.
  No synthesis, no analysis, no "implications for X", no editorial framing.
  The content must be what the page says, not what you think about it.

Output format (KB frontmatter + raw content):
  ---
  url: <canonical URL>
  title: "<page title>"
  fetched_at: <ISO8601>
  source_id: "<topic slug>"
  method: playwright | jina | static
  status: FETCHED | FAILED
  word_count: N
  ---
  <raw extracted prose — heading structure preserved, no images>

urls.txt format:
  https://example.com/page          # fetched at depth 0
  https://example.com/docs  depth=2 # crawl links within /docs/ up to depth 2
  # comment lines ignored

Usage:
  python3 clip-urls.py [--id SOURCE_ID] [--out DIR] [--depth N] [urls.txt]
  python3 clip-urls.py --id bluespan-moats --out /path/to/web-sources/
"""

import argparse
import hashlib
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from readability import Document

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLIPS_DIR      = Path("raw files")
MAX_DEPTH      = 0
JINA_BASE      = "https://r.jina.ai"
JINA_THRESHOLD = 120   # fall back to Jina if Playwright yields fewer words
JINA_RATE      = 2.0   # seconds between Jina calls
REQUEST_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Per-hostname CSS selectors for stable content containers
SITE_SELECTORS: dict[str, str] = {
    "github.com":                ".markdown-body",
    "docs.anthropic.com":        ".prose",
    "docs.claude.ai":            ".prose",
    "modelcontextprotocol.io":   "#content-area",
    "docs.langchain.com":        "#content-area",
    "docs.smith.langchain.com":  "#content-area",
    "cap.cloud.sap":             ".vp-doc",
    "developer.avalara.com":     "#contentLayout",
    "knowledge.avalara.com":     ".conbody",
    "sec.gov":                   "#formContent",
}

# Tags stripped before markdown conversion
NOISE_TAGS = [
    "nav", "header", "footer", "aside",
    "script", "style", "noscript", "iframe",
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
    '[role="complementary"]',
    ".sidebar", ".toc", ".breadcrumb", ".cookie-banner",
    "#cookie-banner", ".header", ".footer", ".nav",
    ".advertisement", ".ad", ".social-share",
    ".related-articles", ".recommended", ".print-header",
]

BOT_CHALLENGE_TITLES = {
    "human verification", "just a moment", "attention required",
    "access denied", "403 forbidden", "ddos protection",
}

# Hosts where Jina output includes noisy preamble before article
JINA_NOISY_HOSTS = {"knowledge.avalara.com"}

# ---------------------------------------------------------------------------
# Slug / filename utilities
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 90) -> str:
    text = re.sub(r"https?://", "", text).lower().strip()
    text = re.sub(r"[^\w\s-]", "-", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-")


def url_slug(url: str) -> str:
    p = urlparse(url)
    base = (p.netloc + p.path).rstrip("/")
    slug = slugify(base, 90)
    return slug or hashlib.sha1(url.encode()).hexdigest()[:16]


def normalise_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def path_prefix_of(url: str) -> str:
    p = urlparse(url)
    parent = "/".join(p.path.split("/")[:-1])
    if not parent.endswith("/"):
        parent += "/"
    return f"{p.scheme}://{p.netloc}{parent}"


# ---------------------------------------------------------------------------
# urls.txt parsing
# ---------------------------------------------------------------------------

def parse_seed_urls(path: Path) -> list[tuple[str, int, str | None]]:
    """Parse urls.txt → list of (url, max_depth, path_prefix)."""
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        url = parts[0]
        depth = MAX_DEPTH
        path_prefix: str | None = None
        for token in parts[1:]:
            if token.startswith("depth="):
                depth = int(token.split("=", 1)[1])
                path_prefix = path_prefix_of(url)
        entries.append((url, depth, path_prefix))
    return entries


# ---------------------------------------------------------------------------
# Noise stripping
# ---------------------------------------------------------------------------

def strip_noise(el) -> None:
    for sel in NOISE_TAGS:
        for tag in el.select(sel):
            tag.decompose()


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def extract_content(html: str, url: str) -> tuple[str, str]:
    """Return (title, clean_markdown). No synthesis, no framing — raw page prose only."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    hostname = urlparse(url).netloc.lstrip("www.")

    def to_md(el) -> str:
        strip_noise(el)
        return md(str(el), heading_style="ATX", bullets="-").strip()

    # 1. Site-specific selector
    for host, sel in SITE_SELECTORS.items():
        if host in hostname:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                return title, to_md(el)

    # 2. Readability
    try:
        doc = Document(html)
        title = title or doc.title()
        clean_html = doc.summary(html_partial=True)
        content = BeautifulSoup(clean_html, "html.parser")
        body = content.find("div") or content
        if body and len(body.get_text(strip=True)) > 200:
            return title, to_md(body)
    except Exception as e:
        print(f"  [readability] {e}", file=sys.stderr)

    # 3. Semantic fallbacks
    for sel in ["main", "article", '[role="main"]']:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 200:
            return title, to_md(el)

    # 4. Full body
    body = soup.find("body") or soup
    return title, to_md(body)


# ---------------------------------------------------------------------------
# Jina Reader
# ---------------------------------------------------------------------------

_jina_last = 0.0

def fetch_jina(url: str) -> str | None:
    global _jina_last
    gap = time.time() - _jina_last
    if gap < JINA_RATE:
        time.sleep(JINA_RATE - gap)
    try:
        resp = requests.get(
            f"{JINA_BASE}/{url}",
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "text/plain", "User-Agent": USER_AGENT,
                     "X-Return-Format": "markdown"},
        )
        _jina_last = time.time()
        if resp.status_code == 429:
            print("  [jina] 429 — sleeping 30s", file=sys.stderr)
            time.sleep(30)
            return fetch_jina(url)
        if "RateLimitTriggeredError" in resp.text:
            print("  [jina] per-IP rate limit", file=sys.stderr)
            return None
        resp.raise_for_status()
        text = resp.text.strip()
        return text if len(text.split()) > 50 else None
    except Exception as e:
        print(f"  [jina] failed: {e}", file=sys.stderr)
        return None


def trim_jina_noise(text: str, title: str) -> str:
    """Strip nav/sidebar preamble from Jina output on known noisy hosts."""
    if not title:
        return text
    title_lower = title.lower().strip()
    lines = text.splitlines()
    match_count = 0
    article_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip().lower()
            if title_lower in heading_text or heading_text in title_lower:
                match_count += 1
                if match_count >= 2:
                    article_start = i
                    break
    if article_start == 0:
        return text
    SKIP_TOKENS = {"watch", "save pdf", "share", "feedback", "expand", "collapse",
                   "table of contents"}
    prose_start = article_start
    for j in range(article_start, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if j == article_start:
            continue
        if not stripped or stripped.lower() in SKIP_TOKENS:
            continue
        if (stripped.startswith(("*", "-", "!")) or stripped.startswith("[")) and \
                ("knowledge.avalara.com" in stripped or "zoominsoftware" in stripped):
            continue
        if len(stripped.split()) <= 4 and not any(c in stripped for c in ".,:?") \
                and not stripped.startswith("#"):
            continue
        prose_start = j
        break
    result = "\n".join([lines[article_start]] + lines[prose_start:]).strip()
    return result if len(result.split()) > 20 else text


# ---------------------------------------------------------------------------
# Link extraction (for crawling)
# ---------------------------------------------------------------------------

def extract_links(soup, base_url: str) -> set[str]:
    base_host = urlparse(base_url).netloc
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
            continue
        abs_url = urljoin(base_url, href)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https") or p.netloc != base_host:
            continue
        links.add(normalise_url(abs_url))
    return links


# ---------------------------------------------------------------------------
# KB-format write
# ---------------------------------------------------------------------------

def write_source(out_dir: Path, url: str, title: str, content: str,
                 source_id: str, method: str) -> Path:
    slug = url_slug(url)
    out_file = out_dir / f"{slug}.md"
    wc = len(content.split())
    ts = datetime.now(timezone.utc).isoformat()
    out_file.write_text(
        f"---\n"
        f"url: {url}\n"
        f'title: "{title}"\n'
        f"fetched_at: {ts}\n"
        f"source_id: {source_id}\n"
        f"method: {method}\n"
        f"status: FETCHED\n"
        f"word_count: {wc}\n"
        f"---\n\n"
        f"{content.strip()}\n",
        encoding="utf-8",
    )
    return out_file


def write_failed(out_dir: Path, url: str, source_id: str, reason: str) -> Path:
    slug = url_slug(url)
    out_file = out_dir / f"{slug}.md"
    ts = datetime.now(timezone.utc).isoformat()
    out_file.write_text(
        f"---\nurl: {url}\ntitle: \"\"\nfetched_at: {ts}\n"
        f"source_id: {source_id}\nstatus: FAILED\nreason: {reason!r}\n---\n",
        encoding="utf-8",
    )
    return out_file


# ---------------------------------------------------------------------------
# Core clip function
# ---------------------------------------------------------------------------

def clip_url(
    page,
    url: str,
    depth: int,
    slug_registry: set[str],
    out_dir: Path,
    source_id: str,
) -> set[str]:
    """Clip one URL: render → extract → save KB-format. Returns discovered links."""
    print(f"[depth {depth}] {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        print("  [warn] networkidle timeout, retrying domcontentloaded", file=sys.stderr)
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)

    final_url = page.url
    html = page.content()

    full_soup = BeautifulSoup(html, "html.parser")
    title_tag = full_soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else ""

    if raw_title.lower().strip() in BOT_CHALLENGE_TITLES:
        print(f"  [skip] bot challenge: {raw_title!r}", file=sys.stderr)
        return set()

    discovered = extract_links(full_soup.find("body") or full_soup, final_url)

    title, markdown_text = extract_content(html, final_url)
    title = title or raw_title
    wc = len(markdown_text.split())

    # Jina fallback for thin content (skip known-selector hosts — thin means genuinely short)
    hostname = urlparse(final_url).netloc.lstrip("www.")
    has_site_selector = any(h in hostname for h in SITE_SELECTORS)
    if wc < JINA_THRESHOLD and not has_site_selector:
        print(f"  [info] thin ({wc}w), trying jina", file=sys.stderr)
        jina_text = fetch_jina(final_url)
        if jina_text and len(jina_text.split()) > wc:
            if hostname in JINA_NOISY_HOSTS:
                jina_text = trim_jina_noise(jina_text, title)
            markdown_text = jina_text
            wc = len(markdown_text.split())
            print(f"  [info] jina: {wc}w", file=sys.stderr)

    if wc < 50:
        write_failed(out_dir, final_url, source_id, f"thin: {wc} words")
        print(f"  -> FAILED (thin: {wc}w)")
        return discovered

    out_file = write_source(out_dir, final_url, title, markdown_text, source_id, "playwright")
    print(f"  -> SAVED {wc}w → {out_file.name}")
    return discovered


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Clip URLs to raw KB-format markdown. No synthesis, no contamination."
    )
    ap.add_argument("urls_file", nargs="?", default="urls.txt",
                    type=Path, help="urls.txt path (default: ./urls.txt)")
    ap.add_argument("--out",   type=Path, default=None,
                    help="Output directory (default: ./raw files/)")
    ap.add_argument("--id",    default="clipped",
                    help="source_id stored in frontmatter")
    ap.add_argument("--depth", type=int, default=None,
                    help="Override global MAX_DEPTH")
    args = ap.parse_args()

    global CLIPS_DIR, MAX_DEPTH
    if args.out:
        CLIPS_DIR = args.out
    if args.depth is not None:
        MAX_DEPTH = args.depth

    urls_file = args.urls_file
    if not urls_file.exists():
        print(f"ERROR: {urls_file} not found", file=sys.stderr)
        sys.exit(1)

    seed_entries = parse_seed_urls(urls_file)
    if not seed_entries:
        print("No URLs in urls.txt", file=sys.stderr)
        sys.exit(1)

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    visited: set[str] = set()
    queue: deque[tuple[str, int, int, str | None]] = deque()
    for url, max_depth, path_prefix in seed_entries:
        clean = normalise_url(url)
        if clean not in visited:
            visited.add(clean)
            queue.append((clean, 0, max_depth, path_prefix))

    errors: list[str] = []
    clipped = 0
    slug_registry: set[str] = set()
    source_id = args.id

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()

        while queue:
            url, current_depth, max_depth, path_prefix = queue.popleft()
            try:
                discovered = clip_url(
                    page, url, current_depth, slug_registry,
                    CLIPS_DIR, source_id,
                )
                clipped += 1
                visited.add(normalise_url(page.url))
            except Exception as e:
                print(f"  ERROR {url}: {e}", file=sys.stderr)
                errors.append(url)
                write_failed(CLIPS_DIR, url, source_id, str(e))
                continue

            if current_depth < max_depth:
                for link in discovered:
                    if link in visited:
                        continue
                    if path_prefix and not link.startswith(path_prefix):
                        continue
                    visited.add(link)
                    queue.append((link, current_depth + 1, max_depth, path_prefix))

        browser.close()

    print(f"\nDone: {clipped} clipped to {CLIPS_DIR}/ ({len(errors)} errors)")
    if errors:
        print("Failed:")
        for u in errors:
            print(f"  {u}")


if __name__ == "__main__":
    main()
