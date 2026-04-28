#!/usr/bin/env python3
"""Web clipper: renders URLs with Playwright, downloads images locally, saves as Markdown.

Content extraction uses Mozilla Readability (via readability-lxml) to strip navigation,
sidebars, and boilerplate — the same algorithm browsers use for Reader Mode.
Site-specific CSS overrides handle GitHub and other structured pages.

urls.txt supports per-URL depth and path-scoped crawling:
    https://example.com/docs/intro              # uses global MAX_DEPTH, follows any same-domain link
    https://example.com/docs/intro  depth=1     # follows links only within /docs/ path prefix
"""

from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib
import re
import sys

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

CLIPS_DIR = Path("raw files")
IMAGES_DIR = CLIPS_DIR / "images"
MAX_DEPTH = 0  # global default; overridden per-URL with depth=N in urls.txt

JINA_THRESHOLD = 150  # fall back to Jina Reader if Playwright+Readability yields fewer words

# Hosts where Jina returns full page including heavy nav/sidebar before the article.
# For these, trim_jina_noise() cuts everything before the first H1/H2 that matches
# the page title, keeping only the article body.
JINA_NOISY_HOSTS = {
    "knowledge.avalara.com",
}

# Per-hostname CSS selectors for sites with known, stable content containers.
# Used instead of Readability when matched.
SITE_SELECTORS: dict[str, str] = {
    "github.com": ".markdown-body",
    "docs.anthropic.com": ".prose",
    "docs.claude.ai": ".prose",
    # Mintlify-based doc sites
    "modelcontextprotocol.io": "#content-area",
    "docs.langchain.com": "#content-area",
    "docs.smith.langchain.com": "#content-area",
    # VitePress-based doc sites
    "cap.cloud.sap": ".vp-doc",
    # Avalara developer portal — API reference pages
    "developer.avalara.com": "#contentLayout",
    # Zoomin Software knowledge base (Avalara, SAP help portal variants)
    "knowledge.avalara.com": ".conbody",
}

# Noise elements stripped before conversion regardless of extraction method
NOISE_TAGS = [
    "nav", "header", "footer", "aside",
    "script", "style", "noscript",
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
    ".sidebar", ".toc", ".breadcrumb", ".cookie-banner",
    "#cookie-banner", ".header", ".footer", ".nav",
]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 80) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-")


def normalise_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def url_to_filename(url: str) -> str:
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix or ".bin"
    ext = re.sub(r"[^\w.]", "", ext)[:6]
    return hashlib.sha1(url.encode()).hexdigest()[:12] + ext


def path_prefix_of(url: str) -> str:
    """Return the directory prefix of a URL's path, e.g.
    https://host/bundle/XYZ/page/ABC.html → 'https://host/bundle/XYZ/page/'
    """
    parsed = urlparse(url)
    parent = "/".join(parsed.path.split("/")[:-1])
    if not parent.endswith("/"):
        parent += "/"
    return f"{parsed.scheme}://{parsed.netloc}{parent}"


# ---------------------------------------------------------------------------
# urls.txt parsing
# ---------------------------------------------------------------------------

def parse_seed_urls(path: Path) -> list[tuple[str, int, str | None]]:
    """Parse urls.txt.

    Each non-comment line may be:
        <url>                → max_depth=MAX_DEPTH, path_prefix=None (hostname filter only)
        <url>  depth=N       → max_depth=N, path_prefix=auto-derived from seed URL's directory

    Returns list of (url, max_depth, path_prefix).
    """
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
# Content fetching
# ---------------------------------------------------------------------------

def fetch_via_jina(url: str) -> str | None:
    """Fetch clean markdown via Jina Reader API — bypasses bot protection."""
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            timeout=30,
            headers={
                "Accept": "text/plain",
                "User-Agent": "Mozilla/5.0",
                "X-Return-Format": "markdown",
            },
        )
        resp.raise_for_status()
        text = resp.text.strip()
        return text if len(text.split()) > 50 else None
    except Exception as exc:
        print(f"  [warn] Jina Reader failed: {exc}", file=sys.stderr)
        return None


def trim_jina_noise(text: str, title: str) -> str:
    """Strip nav/sidebar preamble from Jina output for known noisy sites.

    Zoomin pages have this structure in Jina output:
      1. # Title  (Jina prepended metadata — skip)
      ...nav preamble (filter panel, breadcrumbs)...
      2. # Title  (second occurrence — start of article section)
      3. TOC sidebar (list of * links all pointing to the same Zoomin bundle)
      4. Actual article prose

    Strategy:
    - Skip first matching heading (Jina metadata)
    - Find second matching heading
    - From there, skip any contiguous list block where all links are on-domain
      (the TOC sidebar), then return remaining content
    """
    if not title:
        return text
    title_lower = title.lower().strip()
    lines = text.splitlines()

    # Find second occurrence of the title heading
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

    # From article_start, skip the Zoomin TOC block:
    # It's a run of lines that are either blank, list markers, or links
    # pointing back to the same Zoomin bundle host.
    # Use a simpler heuristic: skip lines until we hit a non-list, non-blank,
    # non-short-toolbar line that doesn't contain "knowledge.avalara.com"
    SKIP_TOKENS = {"watch", "save pdf", "share", "feedback", "expand", "collapse",
                   "table of contents"}
    prose_start = article_start
    for j in range(article_start, len(lines)):
        line = lines[j]
        stripped = line.strip()
        stripped_lower = stripped.lower()
        # Keep the heading
        if j == article_start:
            continue
        if not stripped:
            continue
        if stripped_lower in SKIP_TOKENS:
            continue
        # List items containing Zoomin/Avalara URLs → TOC, skip
        if (stripped.startswith(("*", "-", "!")) or stripped.startswith("[")) and \
                ("knowledge.avalara.com" in stripped or "zoominsoftware" in stripped or
                 "cdn.zoominsoftware" in stripped):
            continue
        # Tag labels like "External", "Integration guides" (appear right before prose)
        # — these are short lines without punctuation; skip them if we haven't hit prose
        if len(stripped.split()) <= 4 and not any(c in stripped for c in ".,:?") \
                and not stripped.startswith("#"):
            continue
        # This looks like real prose
        prose_start = j
        break

    result_lines = [lines[article_start]] + lines[prose_start:]
    trimmed = "\n".join(result_lines).strip()
    return trimmed if len(trimmed.split()) > 20 else text


def trim_zoomin_content(text: str, title: str) -> str:
    """Strip Zoomin chrome from Playwright-extracted .conbody content.

    knowledge.avalara.com .conbody structure:
      1. ## Title + full left-nav TOC list
      2. Breadcrumb + [Table of Contents] link
      3. # Title  (second occurrence — article start)
      4. prev/next nav arrows (empty markdown links)
      5. Watch / Save PDF / Share / Feedback toolbar lines
      6. Metadata: Last Updated, read time, tag labels (search?labelkey=...)
      7. ** ACTUAL ARTICLE CONTENT **  ← keep this
      8. © Avalara footer
      9. Duplicate Save PDF / feedback forms

    Strategy: find second title heading, skip toolbar/metadata, keep until footer.
    """
    if not title:
        return text
    title_lower = title.lower().strip()
    lines = text.splitlines()

    # Find second occurrence of the title heading
    match_count = 0
    article_h1 = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            if title_lower in heading or heading in title_lower:
                match_count += 1
                if match_count >= 2:
                    article_h1 = i
                    break

    if article_h1 < 0:
        return text

    # Skip toolbar/metadata lines after the article H1
    SKIP_EXACT = {"watch", "save pdf", "share", "feedback", "expand", "collapse",
                  "table of contents"}
    prose_start = article_h1 + 1
    for j in range(article_h1 + 1, len(lines)):
        line = lines[j]
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if not stripped:
            continue
        # Empty markdown links — prev/next nav arrows
        if re.match(r'^\[]\(https?://\S+\)$', stripped):
            continue
        if stripped_lower in SKIP_EXACT:
            continue
        # "Last Updated …" metadata
        if re.match(r'\*?\s*last updated', stripped_lower):
            continue
        # "N minute read"
        if re.match(r'\*?\s*\d+\s+minute\s+read', stripped_lower):
            continue
        # Tag label links (/search?labelkey=)
        if "search?labelkey=" in line:
            continue
        # Save PDF / Share compound action lines
        if any(t in stripped_lower for t in ("save selected topic", "copy topic url", "share to email")):
            continue
        # Short lines (≤4 words, no punctuation) before prose — tag labels like "External"
        if len(stripped.split()) <= 4 and not any(c in stripped for c in ".,:?") and not stripped.startswith("#"):
            continue
        prose_start = j
        break

    # Find end: stop at copyright footer or duplicate feedback form
    prose_end = len(lines)
    for j in range(prose_start, len(lines)):
        s = lines[j].strip()
        if "© Avalara" in s or "zoominsoftware.com" in s:
            prose_end = j
            break
        if s == "#### Save PDF":
            prose_end = j
            break

    result = "\n".join(lines[prose_start:prose_end]).strip()
    return result if len(result.split()) > 10 else text


(src: str, base_url: str) -> str | None:
    try:
        abs_src = urljoin(base_url, src)
        filename = url_to_filename(abs_src)
        dest = IMAGES_DIR / filename
        if dest.exists():
            return f"images/{filename}"
        resp = requests.get(abs_src, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return f"images/{filename}"
    except Exception as exc:
        print(f"  [warn] image {src}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def extract_content_soup(html: str, url: str) -> BeautifulSoup:
    """Extract main article content from raw HTML.

    Priority:
    1. Site-specific CSS selector (most precise for known sites)
    2. Mozilla Readability (content-density scoring, generic)
    3. <main> / <article> fallback
    """
    hostname = urlparse(url).netloc.lstrip("www.")
    full_soup = BeautifulSoup(html, "html.parser")

    # 1. Site-specific override
    for host, selector in SITE_SELECTORS.items():
        if host in hostname:
            el = full_soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 200:
                return _strip_noise(el)

    # 2. Readability
    try:
        doc = Document(html)
        clean_html = doc.summary(html_partial=True)
        content = BeautifulSoup(clean_html, "html.parser")
        body = content.find("div") or content
        if body and len(body.get_text(strip=True)) > 200:
            return _strip_noise(body)
    except Exception as exc:
        print(f"  [warn] readability failed: {exc}", file=sys.stderr)

    # 3. Generic fallback
    for selector in ["main", "article", '[role="main"]']:
        el = full_soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 200:
            return _strip_noise(el)

    return _strip_noise(full_soup.find("body") or full_soup)


def _strip_noise(el) -> BeautifulSoup:
    for selector in NOISE_TAGS:
        for tag in el.select(selector):
            tag.decompose()
    return el


def extract_links(content, base_url: str) -> set[str]:
    """Return all same-domain absolute HTTP(S) links found in content."""
    base_host = urlparse(base_url).netloc
    links: set[str] = set()
    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base_host:
            continue
        clean = normalise_url(abs_url)
        if clean:
            links.add(clean)
    return links


# ---------------------------------------------------------------------------
# Core clip function
# ---------------------------------------------------------------------------

def clip_url(page, url: str, depth: int, slug_registry: set[str]) -> set[str]:
    """Navigate, extract clean content, download images, save as Markdown.
    Returns set of discovered same-domain links.
    """
    print(f"[depth {depth}] Clipping: {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        print(f"  [warn] networkidle timed out, retrying with domcontentloaded")
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)

    final_url = page.url
    html = page.content()

    full_soup = BeautifulSoup(html, "html.parser")
    title_tag = full_soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else ""

    # Skip bot-challenge / CAPTCHA pages
    BOT_CHALLENGE_TITLES = {"human verification", "just a moment", "attention required", "access denied", "403 forbidden"}
    if raw_title.lower().strip() in BOT_CHALLENGE_TITLES:
        print(f"  [skip] bot-challenge page (title: {raw_title!r})")
        return set()

    base_slug = slugify(raw_title) if raw_title else slugify(urlparse(final_url).netloc + urlparse(final_url).path)
    if not base_slug:
        base_slug = hashlib.sha1(final_url.encode()).hexdigest()[:12]
    slug = base_slug
    if slug in slug_registry:
        slug = f"{base_slug}-{hashlib.sha1(final_url.encode()).hexdigest()[:6]}"
    slug_registry.add(slug)

    content = extract_content_soup(html, final_url)
    # Discover links from the full Playwright page (not just the readability subset),
    # so path-scoped crawling works even when Jina is used for content.
    full_body = full_soup.find("body") or full_soup
    discovered = extract_links(full_body, final_url)

    for img in content.find_all("img"):
        src = img.get("src") or img.get("data-src", "")
        if not src or src.startswith("data:"):
            continue
        local_path = download_image(src, final_url)
        if local_path:
            img["src"] = local_path

    markdown_text = md(str(content), heading_style="ATX", bullets="-")

    # Strip Zoomin chrome from knowledge.avalara.com Playwright output
    if "knowledge.avalara.com" in urlparse(final_url).netloc:
        markdown_text = trim_zoomin_content(markdown_text, raw_title)

    # Fall back to Jina Reader if content is thin — but skip for known-selector hosts.
    # Those sites have precise selectors; sparse output means the page is genuinely short
    # (e.g. a DELETE endpoint). Jina would return full nav dump which is worse.
    word_count = len(markdown_text.split())
    hostname = urlparse(final_url).netloc.lstrip("www.")
    has_site_selector = any(h in hostname for h in SITE_SELECTORS)
    if word_count < JINA_THRESHOLD and not has_site_selector:
        print(f"  [info] thin content ({word_count} words), trying Jina Reader...")
        jina_text = fetch_via_jina(final_url)
        if jina_text and len(jina_text.split()) > word_count:
            hostname = urlparse(final_url).netloc
            if hostname in JINA_NOISY_HOSTS:
                jina_text = trim_jina_noise(jina_text, raw_title)
                print(f"  [info] trimmed Jina noise for {hostname}")
            markdown_text = jina_text
            word_count = len(markdown_text.split())
            print(f"  [info] Jina improved to {word_count} words")
        else:
            print(f"  [warn] Jina also thin — site likely blocks all scrapers")

    output = f"# {raw_title or slug}\n\n> Source: {final_url}\n\n{markdown_text.strip()}\n"
    out_file = CLIPS_DIR / f"{slug}.md"
    out_file.write_text(output, encoding="utf-8")
    print(f"  -> saved {out_file}  ({word_count} words, {len(discovered)} links)")

    return discovered


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    urls_file = Path("urls.txt")
    if not urls_file.exists():
        print("ERROR: urls.txt not found.", file=sys.stderr)
        sys.exit(1)

    seed_entries = parse_seed_urls(urls_file)
    if not seed_entries:
        print("No URLs found in urls.txt.")
        return

    CLIPS_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)

    # Queue entries: (url, current_depth, max_depth, path_prefix)
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        while queue:
            url, current_depth, max_depth, path_prefix = queue.popleft()
            try:
                discovered = clip_url(page, url, current_depth, slug_registry)
                clipped += 1
                visited.add(normalise_url(page.url))
            except Exception as exc:
                print(f"  ERROR {url}: {exc}", file=sys.stderr)
                errors.append(url)
                continue

            if current_depth < max_depth:
                for link in discovered:
                    if link in visited:
                        continue
                    # Path-scoped seeds: only follow links within the same path prefix
                    if path_prefix and not link.startswith(path_prefix):
                        continue
                    visited.add(link)
                    queue.append((link, current_depth + 1, max_depth, path_prefix))

        browser.close()

    print(f"\nDone. {clipped} pages clipped to {CLIPS_DIR}/  ({len(errors)} errors)")
    if errors:
        print("Failed:")
        for u in errors:
            print(f"  {u}")


if __name__ == "__main__":
    main()
