#!/usr/bin/env python3
"""fetch-sources.py — raw KB-format web source fetcher.

Search ladder (cheapest → most capable):
  1. SearXNG   localhost:8888  — local, free, multi-engine aggregation
  2. Tavily    API             — structured web search + extract
  3. DuckDuckGo               — free, no key, last-resort search

Fetch ladder (cheapest → most capable):
  1. requests (static)  — instant, most news/blogs/docs/APIs
  2. Jina Reader        — free URL→markdown, handles many paywalls/SPAs
  3. Playwright         — headless Chromium, full JS rendering
  4. browser-harness    — authenticated sessions, SAP SSO, when all else fails

RAW STORAGE CONTRACT:
  Every saved file contains ONLY the source's content — no analysis,
  no synthesis, no "BlueSpan implications", no editorial framing.
  Contaminating a source file with derived content defeats the purpose
  of maintaining a re-synthesisable corpus.

Output format (KB frontmatter + raw content):
  ---
  url: <canonical URL>
  title: "<page title>"
  fetched_at: <ISO8601>
  source_id: "<brief_id or topic slug>"
  method: static|jina|playwright|browser-harness
  status: FETCHED | FAILED
  word_count: N
  ---
  <raw extracted content — prose only, no nav/sidebar/footer>

Usage:
  # Fetch a list of specific URLs:
  python3 fetch-sources.py --urls urls.txt --out /path/to/web-sources/ --id brief-2-6-moats

  # Search-then-fetch: give search queries, let the ladder find URLs:
  python3 fetch-sources.py --queries queries.txt --out /path/to/web-sources/ --id brief-2-6-moats --per-query 3

  # Mix: queries.txt lines starting with "http" treated as direct URLs
  python3 fetch-sources.py --queries queries.txt --out /path/to/web-sources/ --id brief-2-6-moats

  # Force browser-harness (authenticated / SAP SSO pages):
  python3 fetch-sources.py --urls urls.txt --out /path/to/web-sources/ --id my-topic --browser-harness

  # Re-fetch only failed files:
  python3 fetch-sources.py --urls urls.txt --out /path/to/web-sources/ --id brief-2-6-moats --refetch-failed
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEARXNG_URL = "http://localhost:8888/search"
JINA_BASE   = "https://r.jina.ai"
JINA_RATE   = 2.0   # seconds between Jina calls
JINA_BACKOFF = 30   # seconds to wait on 429

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

REQUEST_TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Per-hostname CSS selectors — match exact content containers
SITE_SELECTORS: dict[str, str] = {
    "github.com":                ".markdown-body",
    "docs.anthropic.com":        ".prose",
    "docs.claude.ai":            ".prose",
    "modelcontextprotocol.io":   "#content-area",
    "docs.langchain.com":        "#content-area",
    "cap.cloud.sap":             ".vp-doc",
    "developer.avalara.com":     "#contentLayout",
    "knowledge.avalara.com":     ".conbody",
    "sec.gov":                   "#formContent",
}

# Tags to strip before converting to markdown — nav, chrome, decoration
NOISE_TAGS = [
    "nav", "header", "footer", "aside",
    "script", "style", "noscript", "iframe",
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
    '[role="complementary"]',
    ".sidebar", ".toc", ".breadcrumb", ".cookie-banner",
    "#cookie-banner", ".header", ".footer", ".nav",
    ".advertisement", ".ad", ".social-share",
    ".related-articles", ".recommended",
]

# Page titles that indicate bot challenges — skip these
BOT_CHALLENGE_TITLES = {
    "human verification", "just a moment", "attention required",
    "access denied", "403 forbidden", "429 too many requests",
    "please wait", "ddos protection",
}

# Minimum word count to consider a fetch successful
MIN_WORD_COUNT = 80


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 90) -> str:
    text = re.sub(r"https?://", "", text).lower().strip()
    text = re.sub(r"[^\w\s-]", "-", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-")


def url_slug(url: str) -> str:
    """Stable filename slug from URL — domain + path, no query/fragment."""
    p = urlparse(url)
    base = (p.netloc + p.path).rstrip("/")
    slug = slugify(base, 90)
    return slug or hashlib.sha1(url.encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def word_count(text: str) -> int:
    return len(text.split())


def write_source(out_dir: Path, url: str, title: str, content: str,
                 source_id: str, method: str) -> Path:
    """Write a raw KB-format source file. Content must be prose only."""
    slug = url_slug(url)
    out_file = out_dir / f"{slug}.md"
    wc = word_count(content)
    frontmatter = (
        f"---\n"
        f"url: {url}\n"
        f'title: "{title}"\n'
        f"fetched_at: {now_iso()}\n"
        f"source_id: {source_id}\n"
        f"method: {method}\n"
        f"status: FETCHED\n"
        f"word_count: {wc}\n"
        f"---\n\n"
    )
    out_file.write_text(frontmatter + content.strip() + "\n", encoding="utf-8")
    return out_file


def write_failed(out_dir: Path, url: str, source_id: str, reason: str) -> Path:
    slug = url_slug(url)
    out_file = out_dir / f"{slug}.md"
    out_file.write_text(
        f"---\nurl: {url}\ntitle: \"\"\nfetched_at: {now_iso()}\n"
        f"source_id: {source_id}\nstatus: FAILED\nreason: {reason!r}\n---\n",
        encoding="utf-8",
    )
    return out_file


def is_already_fetched(out_dir: Path, url: str) -> bool:
    slug = url_slug(url)
    f = out_dir / f"{slug}.md"
    if not f.exists():
        return False
    text = f.read_text(encoding="utf-8", errors="replace")
    return "status: FETCHED" in text


def is_failed(out_dir: Path, url: str) -> bool:
    slug = url_slug(url)
    f = out_dir / f"{slug}.md"
    if not f.exists():
        return False
    return "status: FAILED" in f.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HTML → clean text
# ---------------------------------------------------------------------------

def strip_noise(soup) -> None:
    for sel in NOISE_TAGS:
        for tag in soup.select(sel):
            tag.decompose()


def html_to_text(html: str, url: str) -> tuple[str, str]:
    """Extract (title, prose_text) from raw HTML. No synthesis, no framing."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Bot challenge guard
    if title.lower().strip() in BOT_CHALLENGE_TITLES:
        return title, ""

    hostname = urlparse(url).netloc.lstrip("www.")

    # 1. Site-specific selector
    for host, sel in SITE_SELECTORS.items():
        if host in hostname:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                strip_noise(el)
                return title, _to_markdown(el)

    # 2. Readability (Mozilla algorithm)
    try:
        from readability import Document
        doc = Document(html)
        title = title or doc.title()
        clean_html = doc.summary(html_partial=True)
        content = BeautifulSoup(clean_html, "html.parser")
        body = content.find("div") or content
        if body and len(body.get_text(strip=True)) > 200:
            strip_noise(body)
            return title, _to_markdown(body)
    except Exception:
        pass

    # 3. Semantic fallbacks
    for sel in ["main", "article", '[role="main"]']:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 200:
            strip_noise(el)
            return title, _to_markdown(el)

    # 4. Full body
    body = soup.find("body") or soup
    strip_noise(body)
    return title, _to_markdown(body)


def _to_markdown(el) -> str:
    try:
        from markdownify import markdownify as md
        return md(str(el), heading_style="ATX", bullets="-").strip()
    except ImportError:
        # Fallback: plain text extraction
        return el.get_text(separator="\n", strip=True)


# ---------------------------------------------------------------------------
# Fetch methods (ladder rungs)
# ---------------------------------------------------------------------------

def fetch_static(url: str) -> tuple[str, str, str]:
    """Rung 0: plain curl-equivalent requests fetch. Fast, no JS."""
    resp = requests.get(
        url, timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    resp.raise_for_status()
    title, text = html_to_text(resp.text, resp.url)
    return title, text, "static"


_jina_last_call = 0.0

def fetch_jina(url: str) -> tuple[str, str, str]:
    """Rung 2: Jina Reader — free URL→markdown. Rate-limited."""
    global _jina_last_call
    elapsed = time.time() - _jina_last_call
    if elapsed < JINA_RATE:
        time.sleep(JINA_RATE - elapsed)

    resp = requests.get(
        f"{JINA_BASE}/{url}",
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "text/plain",
            "User-Agent": USER_AGENT,
            "X-Return-Format": "markdown",
        },
    )
    _jina_last_call = time.time()

    if resp.status_code == 429:
        print(f"  [jina] 429 rate limit — backing off {JINA_BACKOFF}s", file=sys.stderr)
        time.sleep(JINA_BACKOFF)
        return fetch_jina(url)  # single retry

    if "RateLimitTriggeredError" in resp.text:
        raise RuntimeError("Jina per-IP rate limit")

    resp.raise_for_status()
    text = resp.text.strip()
    if not text or word_count(text) < MIN_WORD_COUNT:
        raise RuntimeError(f"Jina returned thin content ({word_count(text)} words)")

    # Extract title from Jina's markdown header (first H1/H2 line)
    title = ""
    for line in text.splitlines():
        m = re.match(r"^#{1,2}\s+(.+)", line.strip())
        if m:
            title = m.group(1).strip()
            break

    return title, text, "jina"


def fetch_playwright(url: str) -> tuple[str, str, str]:
    """Rung 3: Playwright headless — JS-heavy / Cloudflare-protected pages."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=20_000)
        except PWTimeout:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        html = page.content()
        final_url = page.url
        browser.close()

    title, text = html_to_text(html, final_url)
    return title, text, "playwright"


def fetch_browser_harness(url: str) -> tuple[str, str, str]:
    """Rung 4: browser-harness — authenticated sessions, SAP SSO, when all else fails.

    Attaches to the user's running Chrome via CDP. Requires browser-harness daemon
    to be running (auto-starts on first use). Used for:
    - Pages requiring login (SAP internal, portals with SSO)
    - Sites that block all headless browsers (Cloudflare JS challenge)
    - Multi-step navigation (login → navigate → extract)
    """
    import subprocess, json as _json, textwrap

    script = textwrap.dedent(f"""
        new_tab({url!r})
        wait_for_load()
        import time; time.sleep(3)
        html = js("document.documentElement.outerHTML")
        print(html[:500000])
    """)
    result = subprocess.run(
        ["browser-harness", "-c", script],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"browser-harness failed (rc={result.returncode}): {result.stderr[:200]}"
        )
    html = result.stdout
    # Use a dummy final_url since browser-harness doesn't report redirects easily
    title, text = html_to_text(html, url)
    return title, text, "browser-harness"


# ---------------------------------------------------------------------------
# Search (returns list of URLs)
# ---------------------------------------------------------------------------

def search_searxng(query: str, limit: int = 5) -> list[str]:
    """SearXNG local instance — cheapest search, no API key."""
    try:
        resp = requests.get(
            SEARXNG_URL,
            params={"q": query, "format": "json", "categories": "general", "count": limit},
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        return [r["url"] for r in data.get("results", [])[:limit]]
    except Exception as e:
        print(f"  [searxng] failed: {e}", file=sys.stderr)
        return []


def search_tavily(query: str, limit: int = 5) -> list[str]:
    """Tavily search API — paid but reliable."""
    if not TAVILY_API_KEY:
        print("  [tavily] no TAVILY_API_KEY set", file=sys.stderr)
        return []
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_API_KEY, "query": query, "max_results": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [r["url"] for r in data.get("results", [])[:limit]]
    except Exception as e:
        print(f"  [tavily] failed: {e}", file=sys.stderr)
        return []


def search_duckduckgo(query: str, limit: int = 5) -> list[str]:
    """DuckDuckGo HTML scrape — no key, last-resort search."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=limit):
                results.append(r["href"])
        return results
    except Exception as e:
        print(f"  [ddgs] failed: {e}", file=sys.stderr)
        return []


def search_ladder(query: str, limit: int = 5) -> list[str]:
    """Search ladder: SearXNG → Tavily → DuckDuckGo."""
    urls = search_searxng(query, limit)
    if urls:
        print(f"  [search] searxng: {len(urls)} results", file=sys.stderr)
        return urls

    urls = search_tavily(query, limit)
    if urls:
        print(f"  [search] tavily: {len(urls)} results", file=sys.stderr)
        return urls

    urls = search_duckduckgo(query, limit)
    if urls:
        print(f"  [search] ddgs: {len(urls)} results", file=sys.stderr)
        return urls

    print(f"  [search] all engines failed for: {query!r}", file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# Fetch ladder: tries cheapest method first
# ---------------------------------------------------------------------------

def fetch_url(
    url: str,
    force_playwright: bool = False,
    force_browser_harness: bool = False,
) -> tuple[str, str, str]:
    """
    Fetch a URL through the ladder. Returns (title, content, method).

    Fetch ladder:
      1. static requests   — instant, most news/blogs/docs
      2. Jina Reader       — free, handles many paywalls/SPAs, rate-limited
      3. Playwright        — full JS rendering, headless Chromium
      4. browser-harness   — authenticated sessions, real Chrome, last resort

    Each rung is attempted only if the previous returned thin content or failed.
    Use force_browser_harness=True for SAP SSO / auth-gated pages directly.
    Use force_playwright=True for known Cloudflare-protected pages.
    """
    if force_browser_harness:
        return fetch_browser_harness(url)

    if force_playwright:
        try:
            return fetch_playwright(url)
        except Exception as e:
            print(f"  [playwright] failed: {e}, trying browser-harness", file=sys.stderr)
            return fetch_browser_harness(url)

    # Rung 1: static
    try:
        title, text, method = fetch_static(url)
        if word_count(text) >= MIN_WORD_COUNT:
            return title, text, method
        print(f"  [static] thin ({word_count(text)}w), trying jina", file=sys.stderr)
    except Exception as e:
        print(f"  [static] failed: {e}, trying jina", file=sys.stderr)

    # Rung 2: Jina
    try:
        title, text, method = fetch_jina(url)
        if word_count(text) >= MIN_WORD_COUNT:
            return title, text, method
        print(f"  [jina] thin ({word_count(text)}w), trying playwright", file=sys.stderr)
    except Exception as e:
        print(f"  [jina] failed: {e}, trying playwright", file=sys.stderr)

    # Rung 3: Playwright
    try:
        title, text, method = fetch_playwright(url)
        if word_count(text) >= MIN_WORD_COUNT:
            return title, text, method
        print(f"  [playwright] thin ({word_count(text)}w), trying browser-harness", file=sys.stderr)
    except ImportError:
        print(f"  [playwright] not installed, trying browser-harness", file=sys.stderr)
    except Exception as e:
        print(f"  [playwright] failed: {e}, trying browser-harness", file=sys.stderr)

    # Rung 4: browser-harness (requires running Chrome + daemon)
    return fetch_browser_harness(url)


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------

def fetch_batch(
    urls: list[str],
    out_dir: Path,
    source_id: str,
    skip_existing: bool = True,
    refetch_failed: bool = False,
    force_playwright: bool = False,
    force_browser_harness: bool = False,
    delay: float = 1.0,
) -> dict[str, str]:
    """
    Fetch a list of URLs and save to out_dir. Returns {url: status} map.

    Args:
        urls:                  List of URLs to fetch.
        out_dir:               Directory to save .md files.
        source_id:             Brief/topic identifier stored in frontmatter.
        skip_existing:         Skip URLs that already have a FETCHED file.
        refetch_failed:        Re-attempt URLs that previously failed.
        force_playwright:      Use Playwright for all URLs.
        force_browser_harness: Use browser-harness for all URLs (auth/SSO pages).
        delay:                 Seconds between fetches.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    for i, url in enumerate(urls, 1):
        if skip_existing and is_already_fetched(out_dir, url):
            print(f"[{i}/{len(urls)}] SKIP (exists): {url}")
            results[url] = "skipped"
            continue

        if is_failed(out_dir, url) and not refetch_failed:
            print(f"[{i}/{len(urls)}] SKIP (prev failed): {url}")
            results[url] = "prev_failed"
            continue

        print(f"[{i}/{len(urls)}] Fetching: {url}")
        try:
            title, text, method = fetch_url(
                url,
                force_playwright=force_playwright,
                force_browser_harness=force_browser_harness,
            )
            wc = word_count(text)
            if wc < MIN_WORD_COUNT:
                reason = f"thin content: {wc} words"
                write_failed(out_dir, url, source_id, reason)
                print(f"  -> FAILED ({reason})")
                results[url] = "failed"
            else:
                out_file = write_source(out_dir, url, title, text, source_id, method)
                print(f"  -> SAVED [{method}] {wc}w → {out_file.name}")
                results[url] = "ok"
        except Exception as e:
            write_failed(out_dir, url, source_id, str(e))
            print(f"  -> FAILED: {e}")
            results[url] = "failed"

        if i < len(urls):
            time.sleep(delay)

    ok = sum(1 for v in results.values() if v == "ok")
    failed = sum(1 for v in results.values() if v == "failed")
    skipped = sum(1 for v in results.values() if v in ("skipped", "prev_failed"))
    print(f"\nDone: {ok} saved, {failed} failed, {skipped} skipped → {out_dir}")
    return results


def search_and_fetch(
    queries: list[str],
    out_dir: Path,
    source_id: str,
    per_query: int = 3,
    delay: float = 1.5,
) -> dict[str, str]:
    """Search each query through the search ladder, then fetch found URLs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    all_urls: list[str] = []
    seen: set[str] = set()

    for q in queries:
        print(f"\n[search] {q!r}")
        urls = search_ladder(q, per_query)
        for u in urls:
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

    print(f"\nFound {len(all_urls)} unique URLs across {len(queries)} queries")
    return fetch_batch(all_urls, out_dir, source_id, delay=delay)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_lines(path: Path) -> list[str]:
    return [
        l.strip() for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]


def list_failed(out_dir: Path) -> list[dict]:
    """Return list of {url, reason, file} for all FAILED files in out_dir.

    Used to generate a recovery list for Claude to re-fetch via mcp__playwright-headed__.
    PDFs and 404s are excluded (not recoverable by headed browser).
    """
    recoverable = []
    skip_reasons = {"404", "not found", "page not found"}
    for f in sorted(out_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "status: FAILED" not in text:
            continue
        url = next((l.split(":",1)[1].strip() for l in text.splitlines() if l.startswith("url:")), "")
        reason = next((l.split(":",1)[1].strip() for l in text.splitlines() if l.startswith("reason:")), "unknown")
        # Skip PDFs (need pdftotext, not browser) and confirmed 404s
        if url.lower().endswith(".pdf") or any(s in reason.lower() for s in skip_reasons):
            continue
        recoverable.append({"url": url, "reason": reason, "file": str(f)})
    return recoverable


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fetch web sources into KB-format .md files. No synthesis, no contamination."
    )
    ap.add_argument("--urls",    type=Path, help="File with one URL per line")
    ap.add_argument("--queries", type=Path, help="File with one search query (or URL) per line")
    ap.add_argument("--out",     type=Path, required=True, help="Output directory")
    ap.add_argument("--id",      default="unknown", help="source_id stored in frontmatter (e.g. brief-2-6-moats)")
    ap.add_argument("--per-query", type=int, default=3, help="Results per search query (default 3)")
    ap.add_argument("--delay",   type=float, default=1.0, help="Seconds between fetches")
    ap.add_argument("--refetch-failed", action="store_true", help="Re-attempt previously failed URLs")
    ap.add_argument("--playwright",     action="store_true", help="Force Playwright for all URLs (Cloudflare-heavy batches)")
    ap.add_argument("--browser-harness", dest="browser_harness", action="store_true",
                    help="Force browser-harness for all URLs (authenticated / SAP SSO pages)")
    ap.add_argument("--list-failed", action="store_true",
                    help="Print JSON list of recoverable FAILED files (for Claude mcp__playwright-headed__ recovery)")
    args = ap.parse_args()

    # --list-failed: print recoverable failures as JSON for Claude to act on
    if args.list_failed:
        items = list_failed(args.out)
        print(json.dumps(items, indent=2))
        print(f"\n# {len(items)} recoverable failures in {args.out}", file=sys.stderr)
        print("# Re-fetch these via: mcp__playwright-headed__ (Claude tool call)", file=sys.stderr)
        return

    if not args.urls and not args.queries:
        ap.error("Provide --urls and/or --queries")

    if args.urls:
        lines = load_lines(args.urls)
        # Split lines into direct URLs vs search queries
        direct_urls = [l for l in lines if l.startswith("http")]
        queries     = [l for l in lines if not l.startswith("http")]

        if direct_urls:
            print(f"Fetching {len(direct_urls)} direct URLs...")
            fetch_batch(
                direct_urls, args.out, args.id,
                refetch_failed=args.refetch_failed,
                force_playwright=args.playwright,
                force_browser_harness=args.browser_harness,
                delay=args.delay,
            )
        if queries:
            print(f"Searching {len(queries)} queries...")
            search_and_fetch(queries, args.out, args.id, args.per_query, args.delay)

    if args.queries:
        lines = load_lines(args.queries)
        direct_urls = [l for l in lines if l.startswith("http")]
        queries     = [l for l in lines if not l.startswith("http")]

        if direct_urls:
            fetch_batch(
                direct_urls, args.out, args.id,
                refetch_failed=args.refetch_failed,
                force_playwright=args.playwright,
                force_browser_harness=args.browser_harness,
                delay=args.delay,
            )
        if queries:
            search_and_fetch(queries, args.out, args.id, args.per_query, args.delay)


if __name__ == "__main__":
    main()
