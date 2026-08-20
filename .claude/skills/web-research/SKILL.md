---
name: web-research
description: Exhaustive web research — fetch, extract, and save full-text content from academic papers, vendor docs, and web pages into a KB raw directory. Handles JS-rendered sites, Cloudflare, PDFs, and paywall abstracts correctly.
---

# web-research

Exhaustive web research skill. Fetch full-text content from any source — academic papers, vendor docs, news, blogs — and save clean, usable files into a KB raw directory. Built from hard-won field observations across Google Scholar, arXiv, IEEE, SSRN, ResearchGate, Confluent, gRPC.io, Avalara, Microsoft Learn, and others.

## Core principle

**The goal is usable text, not downloaded bytes.** A 80KB HTML dump is worse than nothing — it wastes space and pollutes synthesis. Every file saved must contain extractable prose. Verify before saving.

---

## FIRST-CLASS RULE: Discover via the search ladder before fetching known URLs

**Always start research by running the search ladder (SearXNG → Tavily → DuckDuckGo) to discover current, credible sources. Do NOT jump straight to a hand-written list of URLs you already know.**

Why this is non-negotiable:

- **Your recalled URLs are dated and reflect your training priors.** The canonical primary you remember (a Fowler article, a vendor doc, a Wikipedia page) is often not the newest, best, or most independent source available now. Going straight to known URLs bakes staleness and confirmation bias into the corpus.
- **Discovery surfaces sources you don't know exist** — newer papers, updated official docs, primary authors' own writing, conference talks, competing implementations — which is the entire point of research.
- **SearXNG is local, free, and multi-engine.** There is no cost reason to skip it.

The correct default flow for every research task:

```bash
export TAVILY_API_KEY=$(security find-generic-password -a hermes-agent -s TAVILY_API_KEY -w 2>/dev/null)

# STEP 1 — DISCOVER (always first): run the search ladder to find current sources
fetch-sources --queries queries.txt --out ./web-sources/ --id my-topic --per-query 4

# STEP 2 — TARGETED TOP-UP (optional): add specific known-canonical URLs the
# search may have missed (a specific primary source, a spec, an author's page)
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic
```

Write 3–5 focused queries covering different angles (definition, primary author/originator, competing implementations, critiques/tradeoffs, recent developments). Known-URL fetching is a **top-up for gaps the search missed**, never the starting move. The only exception is when the user hands you an explicit URL to ingest — then fetch that URL directly, but still run a discovery pass for supporting/corroborating sources unless told otherwise.

---


## Tool decision tree

**For any batch of URLs or search queries — use `fetch-sources` first:**

```bash
# Known URLs
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic

# Search queries (search ladder: SearXNG → Tavily → DuckDuckGo)
fetch-sources --queries queries.txt --out ./web-sources/ --id my-topic --per-query 4

# Authenticated / SAP SSO pages (uses your running Chrome)
fetch-sources --urls urls.txt --out ./web-sources/ --id my-topic --browser-harness
```

`fetch-sources` runs the full fetch ladder automatically — no tool selection needed:

```
requests (static) → Jina Reader → Playwright headless → browser-harness
```

**Only reach for individual methods when:**

```
PDF file? (.pdf URL, arxiv.org/pdf/*)
  → curl + pdftotext  (fetch-sources doesn't handle PDFs)

Single URL quick check in an interactive session?
  → http_get(url) or goto_url() + innerText  (faster than the script)

Interactive multi-step flow (CAPTCHA, 2FA, wizard)?
  → browser-harness directly  (script can't handle interactive prompts)
```

---

## Method 0 — fetch-sources batch (DEFAULT for any multi-URL task)

```bash
export TAVILY_API_KEY=$(security find-generic-password -a hermes-agent -s TAVILY_API_KEY -w 2>/dev/null)
fetch-sources \
  --urls /path/to/urls.txt \
  --out /path/to/web-sources/ \
  --id my-topic \
  --delay 1.5
```

Re-fetch failures: `fetch-sources ... --refetch-failed --playwright`
Auth pages: `fetch-sources ... --browser-harness`

---

## Method 1 — PDF via curl + pdftotext (BEST for papers)

Use for: arXiv, ResearchGate open PDFs, IGC reports, LUT thesis, government PDFs, any `.pdf` URL.

```bash
tmpf=$(mktemp /tmp/paper_XXXXXX.pdf)
curl -sL --max-time 40 -A "Mozilla/5.0" -o "$tmpf" "$URL"
sz=$(stat -f%z "$tmpf")

if [ "$sz" -gt 2000 ]; then
    text=$(/opt/homebrew/bin/pdftotext -layout "$tmpf" - 2>/dev/null | head -c 80000)
    if [ -n "$text" ]; then
        printf "---\nsource_url: %s\nfetched_date: %s\ntopic: %s\nkb: %s\n---\n\n%s" \
            "$URL" "$(date +%Y-%m-%d)" "$LABEL" "$KB_NAME" "$text" > "$DEST"
        echo "OK: $(stat -f%z "$DEST") bytes"
    else
        echo "EMPTY: pdftotext got nothing (encrypted or image PDF)"
    fi
else
    echo "SMALL ($sz bytes): not a real PDF — likely a redirect or paywall"
fi
rm -f "$tmpf"
```

**Why `-layout`:** preserves column structure, making multi-column papers readable.  
**Cap at 80000 chars:** LLM context limit; first 80KB covers the full paper for most papers.  
**ResearchGate blocks curl:** 17-byte response = blocked. Fall back to Playwright.  
**arXiv PDFs:** always accessible. URL pattern: `https://arxiv.org/pdf/<id>` — no auth needed.

---

## Method 2 — http_get() in browser-harness (static pages)

Use for: static docs sites, GitHub raw, llms.txt feeds, OAuth spec pages, some AWS docs.

```python
content = http_get(url)
if content and len(content) > 800 and not content.strip().startswith("<!DOCTYPE"):
    header = f"---\nsource_url: {url}\nfetched_date: 2026-07-01\ntopic: {label}\nkb: {kb}\n---\n\n"
    with open(dest, "w") as f:
        f.write(header + content[:80000])
    print(f"OK: {len(content)} chars")
else:
    print(f"HTML DUMP or EMPTY — fall back to browser")
```

**Critical check:** always test `content.strip().startswith("<!DOCTYPE")` or `"<html"`. If true, the site is JS-rendered and `http_get` returned the shell, not the content. Do not save it.

**Sites that work:** `grpc.io` docs, `oauth.net`, `cloudevents.io`, `openid.net`, `docs.aws.amazon.com` (some), `developer.avalara.com/*.md` (the LLMs feed variants).  
**Sites that fail silently:** any Next.js/React SPA (Avalara developer portal, Confluent, Workday). Returns HTML shell that looks large but has no text.

---

## Method 3 — browser-harness goto_url() + innerText (JS-rendered)

Use for: Confluent courses, gRPC.io, developer portals, any SPA.

```python
goto_url(url)
time.sleep(3)           # wait for JS hydration — 2s minimum, 4s for heavy SPAs
content = js("document.body.innerText")

if content and len(content) > 500:
    # ... save
else:
    print(f"EMPTY ({len(content)} chars) — page may need more time or auth")
```

**Known limitation:** `innerText` only captures visible/rendered text. Tabs, accordions, lazy-loaded sections, and content below the fold are often missing. What you get is the above-the-fold text plus any statically-rendered sections. For docs sites this is typically 3–15KB, not 70KB.  
**When it's enough:** for overview/intro pages, Q&A pages, getting-started guides — the visible section has enough substance.  
**When it's not enough:** for full API reference docs. Those are paginated or tab-structured; scrape each sub-page individually.

**Delay guide:**
- Simple React pages: `time.sleep(2)`
- Confluent courses / heavy SPAs: `time.sleep(3.5)`
- Avalara developer portal: `time.sleep(4)` — still only renders nav + above-fold content

---

## Method 4 — Playwright for Cloudflare-protected pages (SSRN, some IEEE)

Use for: `papers.ssrn.com`, sites with "Just a moment..." Cloudflare challenge.

```python
# Via mcp__playwright-headed__ tools:
# 1. Navigate
mcp__playwright-headed__browser_navigate(url=url)
# 2. Wait 4–5 seconds for CF to resolve
# 3. Extract
result = mcp__playwright-headed__browser_evaluate(
    function="() => document.body.innerText.substring(0, 8000)"
)
```

Or via browser-harness (same Chrome session, CF already solved):
```python
goto_url(url)
time.sleep(5)   # CF challenge takes 3–4s
content = js("document.body.innerText")
```

**SSRN pages:** full abstract + authors + keywords + citation — that's all you'll get without login. The abstract is usually 300–500 words and contains the key claim, method, and results. That's useful.  
**IEEE Xplore abstract pages:** same — abstract + section outline + DOI. Enough to cite and summarize. Full text requires institutional access.  
**After CF resolves:** subsequent `goto_url()` calls in the same browser session don't hit CF again for that domain.

---

## Quality gate — before saving any file

```python
def is_usable(content, min_sentences=8):
    """True if content is worth saving."""
    if not content or len(content) < 500:
        return False
    # Reject raw HTML
    if content.strip().startswith(("<!DOCTYPE", "<html", "<!doctype", "<meta")):
        return False
    # Reject Cloudflare spinners that weren't given enough time
    if "Just a moment" in content[:200] or "Checking your browser" in content[:200]:
        return False
    # Reject nav-only dumps (no sentences)
    sentences = [s for s in content.split('.') if len(s.strip()) > 30]
    return len(sentences) >= min_sentences
```

**Rule of thumb:** fewer than 10 meaningful sentences = not worth saving. This catches nav shells, 404 pages, login redirects, and JS spinners that got saved accidentally.

---

## Content quality tiers

Label every saved file with `content_quality` in frontmatter so downstream ingestion can filter:

| Tier | When | What to save |
|---|---|---|
| `full-text` | PDF extracted or long article | Full text, cap at 80KB |
| `abstract-only` | IEEE/SSRN paywall | Clean abstract + DOI + keywords — strip all nav noise |
| `summary` | Thin page but has substance | Keep it, mark it |

For `abstract-only` files: **strip the nav noise before saving.** The IEEE/SSRN abstract pages have 3KB of real content surrounded by 50KB of nav, cookie banners, and related articles. Save only the meaningful parts:

```python
# For SSRN: extract just title, authors, abstract, keywords, citation
# For IEEE: extract title, authors, abstract, section outline, DOI, conference
# Reject: everything after "Sign in to Continue Reading" or "References is not available"
```

---

## Bulk fetch pattern (parallel, with fallback)

For scraping a list of URLs — always probe first, batch second:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_one(url):
    content = http_get(url)
    if content and len(content) > 800 and not content.strip().startswith("<!"):
        return url, content, "http_get"
    return url, None, "needs_browser"

# Phase 1: fast static fetch
results = {}
browser_queue = []

with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(fetch_one, url): url for url in urls}
    for f in as_completed(futures):
        url, content, method = f.result()
        if content:
            results[url] = content
        else:
            browser_queue.append(url)

# Phase 2: browser fetch for what failed
for url in browser_queue:
    goto_url(url)
    time.sleep(3)
    content = js("document.body.innerText")
    if is_usable(content):
        results[url] = content
```

---

## Google Scholar scraping

Scholar is the best discovery source for 2026 research. Always use `as_ylo=YYYY` to filter by year.

```python
goto_url(f"https://scholar.google.com/scholar?q={query}&as_ylo=2026")
time.sleep(2.5)

titles   = js("Array.from(document.querySelectorAll('.gs_rt')).map(e=>e.innerText).join('|||')")
links    = js("Array.from(document.querySelectorAll('.gs_rt a')).map(e=>e.href).join('|||')")
authors  = js("Array.from(document.querySelectorAll('.gs_a')).map(e=>e.innerText).join('|||')")
snippets = js("Array.from(document.querySelectorAll('.gs_rs')).map(e=>e.innerText).join('|||')")
```

**Stable selectors:** `.gs_rt` (title), `.gs_a` (authors/venue), `.gs_rs` (snippet), `.gs_or_ggsm a` (PDF link).  
**Extract arXiv IDs from links:** `re.findall(r'arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+)', all_links_text)` — then fetch via PDF pipeline.  
**Rate:** 1 query per 1.5s minimum. Scholar doesn't rate-limit harshly but 12 rapid queries will trigger CAPTCHA.  
**Year filter is critical:** without `as_ylo`, you get 2015 papers for most engineering queries.

---

## arXiv — best source for CS/AI papers

arXiv PDFs are always free, no auth, no Cloudflare. The Atom API works for known IDs; full-text search is unreliable for engineering/enterprise topics (they don't publish there).

```bash
# Fetch known IDs via Atom API
curl -s "https://export.arxiv.org/api/query?id_list=2601.20112,2602.14871&max_results=10" | \
  grep -oP '(?<=<title>)[^<]+' 

# Download PDF
curl -sL --max-time 30 -o /tmp/paper.pdf "https://arxiv.org/pdf/2601.20112"
/opt/homebrew/bin/pdftotext -layout /tmp/paper.pdf - | head -c 80000
```

**arXiv field search:** `ti:` (title), `abs:` (abstract). Example: `ti:agentic+AND+abs:ERP`. BUT: enterprise/connector/ERP topics are not well-indexed on arXiv — Scholar → SSRN/IEEE/ResearchGate is the better path for those.

---

## Site-specific notes (field-tested)

### Avalara developer portal (developer.avalara.com)
- **`*.md` feeds work via http_get:** `https://developer.avalara.com/products/e-invoicing.md` returns clean markdown. Always try the `.md` variant first.
- **Main pages are Next.js SPA:** `http_get` returns HTML shell. Use `goto_url()` + `innerText`.
- **ELR guide sub-pages** contain content in embedded JSON (`"content":"<html>..."` inside `__NEXT_DATA__`). Strip HTML tags after extraction.
- **API reference pages** are useless via scraping — JSON schema rendered in a UI. Ignore.

### Google Scholar
- Works via `goto_url()` — no auth needed, no CF.
- If the page shows 0 results, the Chrome tab might be on a previous Scholar page that didn't navigate cleanly. Add `ensure_real_tab()` before the first `goto_url()`.

### SSRN (papers.ssrn.com)
- Cloudflare: use `goto_url()` + 5s sleep. Once CF resolves, subsequent pages in the same session load immediately.
- Abstract is full and valuable — 300–500 words with method, findings, keywords.
- "Download This Paper" button requires login. Don't try.

### IEEE Xplore
- Abstract page accessible without login. "Sign in to Continue Reading" cuts off after the intro paragraph.
- Abstract + section outline + DOI + conference = enough to assess relevance.
- Clean by removing everything after "Sign in to Continue Reading".

### ResearchGate
- Direct PDF links (`/publication/.../links/.../file.pdf`) blocked by curl (17-byte response).
- Use `goto_url()` to get the landing page (abstract + metadata) — full PDF requires login.

### gRPC.io, Confluent, AsyncAPI
- JS-rendered. `goto_url()` + `innerText` gets the above-the-fold text (3–7KB typically).
- Full course content on Confluent is in transcript format — use `View Transcript` link if available.
- For comprehensive coverage, scrape each sub-page individually rather than the top-level guide page.

### Microsoft Learn (learn.microsoft.com)
- Mostly static, `http_get` works on most pages.
- Some pages redirect to a JS shell — check with `content.startswith("<!DOCTYPE")`.

### Oracle docs (docs.oracle.com)
- Mix of static and JS. Try `http_get` first; fall back to browser.

---

## File naming convention

```
YYYY-MM-DD-<slug>-<first-author>-<year>.md
```

Examples:
- `2026-07-01-ai-native-erp-trivedi-2026.md`
- `2026-07-01-grpc-vs-rest-ramadan-2026.md`
- `2026-07-01-elr-guide-authentication.md`

---

## Frontmatter template

```markdown
---
source_url: <original URL>
fetched_date: YYYY-MM-DD
topic: <descriptive label — what the paper/page is about>
kb: <which KB this belongs to>
content_quality: full-text | abstract-only | summary
---

<extracted text>
```

Always include `content_quality`. It lets ingestion pipelines, LightRAG, and wiki synthesis agents know what they're working with without reading the body.

---

## Post-download audit (always run this)

After any bulk fetch, audit before declaring done:

```python
import os, re

for root, dirs, fnames in os.walk(KB_RAW):
    for fn in fnames:
        if not fn.endswith(".md"): continue
        path = os.path.join(root, fn)
        content = open(path).read()
        fm = re.match(r'^---.*?---\n', content, re.DOTALL)
        body = content[fm.end():].strip() if fm else content.strip()
        sz = os.path.getsize(path)
        sentences = [s for s in re.split(r'[.!?]', body) if len(s.strip()) > 30]
        
        is_html  = body.startswith(("<!DOCTYPE", "<html", "<!doctype"))
        is_thin  = len(sentences) < 8 and sz < 4000
        is_dupe  = False  # check manually or by content hash
        
        if is_html:   print(f"DELETE (HTML dump):  {fn}")
        elif is_thin: print(f"REVIEW (thin):       {fn}  [{len(sentences)} sentences]")
        else:         print(f"OK:                  {fn}  [{sz} bytes, {len(sentences)} sentences]")
```

Delete HTML dumps immediately. Review thin files — some are legitimately short (glossaries, LLM feeds); others are nav noise.

---

## What to do with abstract-only files

They're still useful — don't delete them reflexively:
- Full abstract contains the key claim, method, and results
- DOI + authors enables manual full-text retrieval later
- Good enough for Hermes to cite and summarize accurately

Strip all nav/cookie/footer noise. Keep only: title, authors, abstract, section outline, keywords, DOI, citation. Mark `content_quality: abstract-only`.

Full text upgrade path: the `source_url` is in the frontmatter. Open it, log in with institutional access, download PDF, run through pdftotext pipeline, overwrite the file.

---

## What NOT to do

- **Do not skip the search ladder and jump to known URLs.** Starting from a hand-written list of URLs you already know bakes in staleness and confirmation bias — your recalled sources are dated. Run `--queries` (SearXNG → Tavily → DuckDuckGo) FIRST to discover current, credible sources; use `--urls` only as a targeted top-up. See the first-class rule near the top of this file.
- **Do not save raw HTML.** `http_get` on a JS-rendered page returns the HTML shell. It looks big (80KB) but contains zero prose. Always check `content.startswith("<!DOCTYPE")`.
- **Do not use `http_get` for ResearchGate, SSRN, IEEE, or Cloudflare-protected sites.** You'll get a 17-byte block response or an HTML spinner.
- **Do not save navigation dumps.** If `document.body.innerText` returns "Sign In | Products | Solutions | About..." for the first 500 chars, the page didn't render its content. Add more sleep or use a different method.
- **Do not save duplicate files.** If two URLs return the same content (common with Avalara's mirror paths), keep one and delete the other.
- **Do not use arXiv full-text search for enterprise/connector topics.** Enterprise SaaS, ERP connectors, tax compliance — these don't get published on arXiv. Use Scholar → SSRN/IEEE/ResearchGate instead.
- **Do not scrape top-level course pages expecting full course content.** Confluent courses, gRPC guides — the top-level page has 2KB of intro. Each lesson is a separate URL. Scrape sub-pages if you need depth.

---

## Trigger

`/web-research` — or when the user asks to research a topic, collect papers, scrape vendor docs, or build a raw KB from web sources.
