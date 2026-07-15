---
name: web-clipper
description: >
  Fetch and save web pages as raw KB-format markdown — no synthesis, no contamination.
  Two scripts: fetch-sources.py (search-then-fetch via search ladder) and clip-urls.py
  (Playwright deep crawl). Use when saving web research corpora, archiving URLs, or
  building a re-synthesisable source corpus for MoA research.
  Trigger: "clip this URL", "save page as markdown", "archive these links",
  "fetch these sources", "scrape to KB", "save web resources".
---

# Web Clipper

Two tools for saving web content as raw, clean, re-synthesisable markdown:

| Script | Use when |
|---|---|
| `fetch-sources.py` | You have a list of URLs or search queries; want the cheapest fetch path per URL |
| `clip-urls.py` | You want Playwright rendering + optional crawling of discovered links |

---

## THE RAW STORAGE CONTRACT

**Saved files must contain only the source page's content.**

Never inject:
- Analysis of what the page means for your project
- "Implications for X", "BlueSpan analog", editorial framing
- Summaries or synthesis of multiple pages
- LLM-generated content of any kind

The reason: source files are a re-synthesisable corpus. If a model writes
"The BlueSpan analog here is…" into a source file, every future synthesis
built on that file inherits that framing. The ground truth is gone.

A contaminated corpus produces biased synthesis. Raw files produce honest synthesis.

---

## Search Ladder (fetch-sources.py)

fetch-sources.py uses a cost/capability ladder — cheapest method first:

```
1. SearXNG   localhost:8888     free, local, multi-engine — for search queries
2. Tavily    api.tavily.com     paid, reliable — search fallback when SearXNG fails
3. DuckDuckGo duckduckgo-search  free, no key — search fallback of last resort
   ↓
4. requests (static)            instant, works for most news/blogs/docs
5. Jina Reader r.jina.ai        free, handles many paywalls/SPAs, rate-limited 1req/s
6. Playwright headless          JS-heavy pages, Cloudflare-protected — slowest
```

Each fetch rung is tried only if the previous returned thin content (< 80 words).
Search rungs are separate from fetch rungs — search finds URLs, then a fetch rung gets content.

---

## Phase 0: Setup

```bash
pip install playwright beautifulsoup4 markdownify requests readability-lxml duckduckgo-search
playwright install chromium
```

Copy scripts from the skill templates:

```bash
SKILL_DIR="/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/web-clipper/templates/scripts"
cp "$SKILL_DIR/fetch-sources.py" ./fetch-sources.py
cp "$SKILL_DIR/clip-urls.py"     ./clip-urls.py
```

---

## Phase 1: fetch-sources.py — Search ladder + batch fetch

### Fetch a list of known URLs

```bash
# urls.txt: one URL or search query per line (# = comment)
python3 fetch-sources.py \
  --urls urls.txt \
  --out /path/to/web-sources/ \
  --id brief-2-6-moats
```

Lines starting with `http` are fetched directly. Other lines are treated as search queries.

### Search then fetch

```bash
# queries.txt: one search query per line
python3 fetch-sources.py \
  --queries queries.txt \
  --out /path/to/web-sources/ \
  --id my-topic \
  --per-query 4
```

### Re-fetch failed files only

```bash
python3 fetch-sources.py --urls urls.txt --out ./web-sources/ --id my-topic --refetch-failed
```

### Force Playwright (Cloudflare-heavy batch)

```bash
python3 fetch-sources.py --urls urls.txt --out ./web-sources/ --id my-topic --playwright
```

### Output format

Each saved file:

```markdown
---
url: https://example.com/article
title: "Article Title"
fetched_at: 2026-07-11T12:00:00+00:00
source_id: brief-2-6-moats
method: static | jina | playwright
status: FETCHED
word_count: 1247
---

[raw page content — prose only, no nav/sidebar/footer]
```

Failed fetches get `status: FAILED` with a `reason:` field. They are skipped on re-run unless `--refetch-failed` is passed.

---

## Phase 2: clip-urls.py — Playwright deep crawl

Use when you need JS rendering for all pages or want to crawl discovered links.

```bash
# urls.txt with optional depth= annotation
python3 clip-urls.py urls.txt \
  --out /path/to/web-sources/ \
  --id my-topic
```

### urls.txt format

```
# Static depth (no crawling)
https://example.com/article

# Crawl links within /docs/ up to depth 2
https://example.com/docs/intro  depth=2
```

### Options

```
--out DIR      Output directory (default: ./raw files/)
--id STRING    source_id in frontmatter
--depth N      Override global MAX_DEPTH (default 0)
```

---

## Phase 3: Output structure

```
web-sources/
├── example-com-article-title.md        ← slug = domain + path
├── a16z-com-data-moats-healthcare.md
├── sec-gov-tempus-ai-s1-filing.md
└── ...
```

Filename is `slugify(domain + path)` — stable, human-readable, no hash collisions.

---

## Phase 3.5: MCP Playwright Recovery (Claude tool loop only)

After `fetch-sources` completes, some files may have `status: FAILED`. The `mcp__playwright-headed__` MCP tool — which uses your real Chrome with existing cookies/session — can recover many of these failures that headless methods cannot (Cloudflare JS challenges, soft paywalls, JS-heavy SPAs).

**This step runs in Claude's tool loop, not in the shell.** Claude calls the MCP tools directly.

### Step 1 — identify recoverable failures

```bash
fetch-sources --out /path/to/web-sources/ --list-failed
```

Prints a JSON list of `{url, reason, file}` for all non-PDF, non-404 failures.

### Step 2 — Claude recovers each URL via mcp__playwright-headed__

For each URL in the list, Claude:

1. Navigates with `mcp__playwright-headed__browser_navigate(url=url)`
2. Waits: `mcp__playwright-headed__browser_wait_for(state="networkidle")`
3. Extracts text: `mcp__playwright-headed__browser_evaluate(function="() => document.body.innerText")`
4. Saves with KB-format frontmatter to the same directory, overwriting the FAILED stub

```python
# Claude writes this after getting the text content:
from datetime import datetime, timezone
from pathlib import Path
import re, hashlib

def url_slug(url):
    p = url.split("://",1)[-1].rstrip("/")
    s = re.sub(r"[^\w\s-]", "-", p).lower()
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-{2,}", "-", s)[:90].strip("-")

def save_recovered(url, title, content, out_dir, source_id):
    slug = url_slug(url)
    out_file = Path(out_dir) / f"{slug}.md"
    wc = len(content.split())
    ts = datetime.now(timezone.utc).isoformat()
    out_file.write_text(
        f"---\nurl: {url}\ntitle: \"{title}\"\nfetched_at: {ts}\n"
        f"source_id: {source_id}\nmethod: mcp-playwright-headed\n"
        f"status: FETCHED\nword_count: {wc}\n---\n\n{content.strip()}\n"
    )
    return out_file
```

### When to use MCP Playwright recovery

| Failure reason | Worth trying? |
|---|---|
| `Failed to fetch url` / generic error | Yes — usually JS-rendered |
| `thin content` / `<80 words` | Yes — JS not rendered |
| `Request timed out` | Yes — retry with real browser |
| `404 page not found` | No — dead link |
| `.pdf` URL | No — use `curl` + `pdftotext` |
| `status: FAILED` with no reason | Yes |

---

### Add a site-specific content selector

Both scripts have a `SITE_SELECTORS` dict. Add entries for sites with known stable containers:

```python
SITE_SELECTORS = {
    "github.com": ".markdown-body",
    "docs.mysite.com": "#article-content",   # ← add here
}
```

### Increase Jina rate

If you have a Jina API key, set `JINA_RATE = 0.5` and add the key header:

```python
headers={"Authorization": f"Bearer {os.environ['JINA_API_KEY']}", ...}
```

### Add SearXNG engines

The SearXNG call uses `categories=general`. Add `&engines=google,bing,brave` to pin specific engines.

---

## Phase 5: Known failure modes

| Site | Failure mode | Workaround |
|---|---|---|
| Cloudflare JS challenge | Playwright shows blank / challenge page | Use `--playwright` flag; some sites still block headless |
| SSRN / IEEE | Paywalled abstracts only | Use Jina — it bypasses many academic soft-paywalls |
| web.archive.org | Permanently blocked by Jina | `--playwright` directly |
| abdm.gov.in | Full React SPA, static returns nav shell | Use NHA press releases (pib.gov.in) instead |
| nmc.org.in | Jina timeout >15s | Skip; use regulatory KB |
| indiankanoon.org | CAPTCHA | Use livelaw.in or taxguru.in for case summaries |
| cdsco.gov.in | Download links are base64 IDs | Listing page works; individual doc URLs blocked |
| ModuleNotFoundError | Missing dep | `pip install readability-lxml duckduckgo-search` |
| Thin output (<80w) after all rungs | Bot block or genuine short page | Note as FAILED; accept coverage gap |

---

## Phase 6: Checking for contamination

After a fetch run, verify files are raw:

```bash
python3 - << 'EOF'
import pathlib
d = pathlib.Path("web-sources/")
INJECTED = ["BlueSpan", "implications for", "analog here", "this means for", "our product"]
for f in sorted(d.glob("*.md")):
    text = f.read_text()
    body_start = text.find("---\n", 3)
    body = text[body_start+4:] if body_start > 0 else text
    hits = [kw for kw in INJECTED if kw.lower() in body.lower()]
    if hits:
        print(f"CONTAMINATED {f.name}: {hits}")
EOF
```

If contamination is found: delete the file and re-fetch with `--refetch-failed`.

---

## Phase 7: Using the corpus for MoA synthesis

Once source files are clean, run Phase B synthesis with `moa-call.sh`:

```bash
# The synthesis prompt inlines source files via ===INLINE:<path>=== directives
# moa-call.sh handles the inlining — it does NOT contaminate source files
moa-call.sh deep-research synthesis-prompt.txt output.md
```

The synthesis step is where analysis and framing belong — not in the source files.
