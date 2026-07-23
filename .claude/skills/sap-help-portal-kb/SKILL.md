---
name: sap-help-portal-kb
description: >
  Scrape any SAP Help Portal deliverable (configuration guide, application help) into a KB.
  Uses the /http.svc/pagecontent API (no auth required) to extract the full TOC + per-topic
  HTML body without browser rendering. Stores raw articles under <kb-root>/raw/articles/<deliverable-slug>/
  and compiles wiki articles via llm-knowledge-base.
  Use when the user provides a help.sap.com/docs/ URL and wants to ingest it.
---

# SAP Help Portal → KB Ingestion

Scrapes a SAP Help Portal deliverable (configuration guide, app help, etc.) into a knowledge
base using the `http.svc/pagecontent` private API. No SAP SSO required — API is public.

**Trigger:** `/sap-help-portal-kb`

---

## Key APIs (all public, no auth)

### 1. Page navigation → deliverable_id + buildNo
When the user gives a help.sap.com URL, navigate to it in the browser and capture the pagecontent XHR:

```
GET https://help.sap.com/http.svc/pagecontent?deliverableInfo=1&deliverable_id=NUMERIC_ID&buildNo=BUILD&file_path=LOIO.html&locale=en-US
```

To discover `deliverable_id` and `buildNo` for any URL, navigate to the page in the browser and
intercept the network call (see Phase 0 below).

**Known canonical S/4HANA Finance deliverables (buildNo=1780 as of 2026-07-20):**

| deliverable_id | Slug | Title | Topics | buildNo |
|---|---|---|---|---|
| `40374856` | CO | Controlling (CO) | 3,243 topics, depth 10 | 1779 |
| `40374875` | FI-GL | General Ledger Accounting (FI-GL) | 1,383 topics, depth 9 | 1780 |
| `40374490` | FIN-ESM | Enterprise Services in Financials | 669 topics, low value | 1779 |
| `40374240` | FCC | SAP S/4HANA Financial Closing Cockpit | 82 topics | 1779 |
| `40374???` | FI-AA | Asset Accounting (FI-AA) — loio `67e323b7117e4c91869c...` | TBD | 1780 |
| `40374???` | GRP | Group Reporting (FIN-CS) — loio `4ebf1502064b406c964b...` | TBD | 1780 |
| `40374???` | CRED | SAP Credit Management — loio `0bfd0ef8ac604566b032...` | TBD | 1780 |
| `40374???` | TREAS | Treasury and Risk Management — loio `848f8ce21bcd4f67bce7...` | TBD | 1780 |

> **Note:** buildNo increments with SAP Help Portal deployments. Always capture fresh via browser XHR (Phase 0) if 500 errors appear. CO was scraped at buildNo=1779; FI-GL and later at buildNo=1780.

### 2. Full TOC (one call)
```
GET https://help.sap.com/http.svc/pagecontent?deliverableInfo=1&deliverable_id=ID&buildNo=BUILD&file_path=ANY_TOPIC.html&locale=en-US
```
Response: `data.deliverable.fullToc` — full tree, nodes have `{t: title, u: loio.html, c: children[], id: numeric}`

### 3. Per-topic content
```
GET https://help.sap.com/http.svc/pagecontent?deliverableInfo=0&deliverable_id=ID&buildNo=BUILD&file_path=LOIO.html&locale=en-US
```
Response: `data.body` — HTML string, clean with `.body` CSS selector or HTML parser.

### 4. Search (find deliverables by topic)
```
GET https://help.sap.com/http.svc/search?q=QUERY&locale=en-US&product=SAP_S4HANA_ON-PREMISE&limit=10
```
Response: `data.results[]` with `url` containing `/docs/PRODUCT/DELIVERABLE_LOIO/TOPIC_LOIO.html` — navigate to the result URL in browser to discover the numeric `deliverable_id` from the pagecontent XHR.

---

## Content Quality Assessment

| Guide type | Typical chars/topic | Value |
|---|---|---|
| Configuration guide (CO, FI-GL, FI-AA) | 200–1500 chars | **HIGH** — prerequisites, use, process steps, examples |
| Application help (FI-AA, Group Reporting) | 300–800 chars | **HIGH** — concept + config sequence |
| ESM Enterprise Services catalog | 300–700 chars | **LOW** — API metadata tables only |
| "What's New" delta docs | 50–300 chars | **SKIP** — version deltas, not reference |

**Recommended for sap-agentic-finance-kb:** CO, FI-GL, FI-AA, Group Reporting, Credit Mgmt, Treasury.

---

## Constants

```
SAP_HELP_BASE       = "https://help.sap.com"
SAP_HELP_PAGECONTENT = "/http.svc/pagecontent"
SAP_HELP_SEARCH     = "/http.svc/search"
DEFAULT_BUILD_NO    = "1779"   # valid as of 2026-07-19; re-capture if 500 errors
DEFAULT_LOCALE      = "en-US"
DEFAULT_PRODUCT     = "SAP_S4HANA_ON-PREMISE"
```

---

## Phase 0 — Discover deliverable_id for a URL

Given a URL like `https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/<DELIV_LOIO>/<TOPIC_LOIO>.html`:

```python
browser-harness -c '
import json, time
js("performance.clearResourceTimings()")
goto_url("<help.sap.com URL>")
wait_for_load()
time.sleep(4)
xhrs = js("""
  return performance.getEntriesByType("resource")
    .filter(e => e.name.includes("pagecontent"))
    .map(e => e.name.substring(0, 250));
""")
for x in xhrs:
    print(x)
'
```

Extract `deliverable_id=NNNNN&buildNo=BBBB` from the captured URL.
Save as: `DELIVERABLE_ID=NNNNN`, `BUILD_NO=BBBB`.

---

## Phase 1 — Fetch Full TOC

```python
#!/usr/bin/env python3
# fetch_toc.py — dump full TOC for a deliverable to JSON
import urllib.request, json, sys

BASE = "https://help.sap.com"
DELIVERABLE_ID = sys.argv[1]   # e.g. "40374856"
BUILD_NO = sys.argv[2]          # e.g. "1779"
ROOT_TOPIC = sys.argv[3]        # any topic loio.html from this deliverable
OUT_FILE = sys.argv[4]          # e.g. /tmp/co_toc.json

headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0", "Referer": BASE+"/"}
url = f"{BASE}/http.svc/pagecontent?deliverableInfo=1&deliverable_id={DELIVERABLE_ID}&buildNo={BUILD_NO}&file_path={ROOT_TOPIC}&locale=en-US"
r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20)
d = json.loads(r.read())
deliv = d["data"]["deliverable"]

def walk_toc(nodes, depth=0, results=None):
    if results is None: results = []
    for n in nodes:
        u = str(n.get("u",""))
        results.append({"depth": depth, "title": str(n.get("t","")), "loio_html": u, "children": len(n.get("c",[]))})
        walk_toc(n.get("c",[]), depth+1, results)
    return results

all_nodes = walk_toc(deliv.get("fullToc",[]))
output = {
    "deliverable_id": DELIVERABLE_ID,
    "build_no": BUILD_NO,
    "title": deliv.get("title",""),
    "version": deliv.get("version",""),
    "total_nodes": len(all_nodes),
    "nodes": all_nodes,
}
with open(OUT_FILE, "w") as f:
    json.dump(output, f, indent=2)
print(f"Saved {len(all_nodes)} nodes to {OUT_FILE}")
print(f"Title: {deliv.get('title','')}  Version: {deliv.get('version','')}")
depths = {}
for n in all_nodes: depths[n["depth"]] = depths.get(n["depth"],0)+1
print(f"Depth distribution: {depths}")
```

---

## Phase 2 — Scrape All Topics to Raw Files

```python
#!/usr/bin/env python3
# scrape_deliverable.py — fetch all topics and save as markdown
import urllib.request, json, sys, os, re, time
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://help.sap.com"
TOC_FILE = sys.argv[1]         # JSON from fetch_toc.py
KB_ROOT = sys.argv[2]          # e.g. /path/to/sap-agentic-finance-kb
DELIVERABLE_SLUG = sys.argv[3] # e.g. "controlling-co"
CONCURRENCY = int(sys.argv[4]) if len(sys.argv)>4 else 8

with open(TOC_FILE) as f:
    toc_data = json.load(f)

DELIVERABLE_ID = toc_data["deliverable_id"]
BUILD_NO = toc_data["build_no"]
DELIV_TITLE = toc_data["title"]
NODES = toc_data["nodes"]

OUT_DIR = os.path.join(KB_ROOT, "raw", "articles", DELIVERABLE_SLUG, "web-sources")
os.makedirs(OUT_DIR, exist_ok=True)

headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0", "Referer": BASE+"/"}

class TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.text=[]; self.skip=False; self.in_table=False
    def handle_starttag(self, tag, attrs):
        if tag in ('head','style','script','button','nav','footer'): self.skip=True
        if tag=='tr': self.text.append('\n')
        if tag=='td': self.text.append(' | ')
    def handle_endtag(self, tag):
        if tag in ('head','style','script','button','nav','footer'): self.skip=False
        if tag in ('p','h1','h2','h3','h4','li','tr','th'): self.text.append('\n')
    def handle_data(self, data):
        if not self.skip and data.strip(): self.text.append(data.strip())
    def get_text(self): return re.sub(r'\n{3,}', '\n\n', '\n'.join(self.text)).strip()

def fetch_topic(node):
    loio_html = node["loio_html"]
    if not loio_html or loio_html == "None": return None
    
    # Skip-if-exists
    safe_title = re.sub(r'[^a-z0-9]+', '-', node["title"].lower()).strip('-')[:60]
    loio = loio_html.replace(".html","")
    filename = f"{safe_title}_{loio[:16]}.md"
    filepath = os.path.join(OUT_DIR, filename)
    if os.path.exists(filepath):
        return {"status": "skip", "title": node["title"]}
    
    url = f"{BASE}/http.svc/pagecontent?deliverableInfo=0&deliverable_id={DELIVERABLE_ID}&buildNo={BUILD_NO}&file_path={loio_html}&locale=en-US"
    try:
        req = urllib.request.Request(url, headers=headers)
        r = urllib.request.urlopen(req, timeout=15)
        d = json.loads(r.read())
        body = d["data"].get("body","")
        if not body: return {"status": "empty", "title": node["title"]}
        
        p = TextExtractor(); p.feed(body)
        text = p.get_text()
        # Strip icon characters (SAP uses private-use Unicode)
        text = re.sub(r'[-]', '', text)
        word_count = len(text.split())
        
        # Build path breadcrumb from depth
        indent = "  " * node["depth"]
        
        md = f"""---
source_url: {BASE}/docs/SAP_S4HANA_ON-PREMISE/{loio}.html?locale=en-US
deliverable: {DELIV_TITLE}
deliverable_id: {DELIVERABLE_ID}
topic_title: {node["title"]}
topic_loio: {loio}
depth: {node["depth"]}
source_type: sap_help_portal
confidence_weight: 0.90
word_count: {word_count}
---

# {node["title"]}

**Guide:** {DELIV_TITLE}
**Source:** {BASE}/docs/SAP_S4HANA_ON-PREMISE/{loio}.html?locale=en-US

---

{text}
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return {"status": "ok", "title": node["title"], "words": word_count, "file": filename}
    except Exception as e:
        return {"status": "error", "title": node["title"], "error": str(e)}

# Filter: only fetch leaf nodes + section headers with content (depth <= 3)
# Skip pure container nodes that have children but no own content
fetchable = [n for n in NODES if n["loio_html"] and n["loio_html"] != "None"]
print(f"Fetching {len(fetchable)} topics from '{DELIV_TITLE}' with concurrency={CONCURRENCY}")
print(f"Output: {OUT_DIR}")

stats = {"ok": 0, "skip": 0, "empty": 0, "error": 0}
with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
    futures = {ex.submit(fetch_topic, n): n for n in fetchable}
    for i, fut in enumerate(as_completed(futures), 1):
        result = fut.result()
        if result:
            status = result.get("status","?")
            stats[status] = stats.get(status,0) + 1
            if i % 50 == 0 or status == "error":
                print(f"  [{i}/{len(fetchable)}] {status}: {result.get('title','')[:50]} words:{result.get('words','-')}")

print(f"\nDone: {stats}")
print(f"Raw files in: {OUT_DIR}")
```

---

## Phase 3 — Compile Wiki Articles

Use the `llm-knowledge-base` compile script or invoke the skill directly.

```bash
KB_ROOT="/path/to/target-kb"
DELIVERABLE_SLUG="controlling-co"
SOURCE_DIR="$KB_ROOT/raw/articles/$DELIVERABLE_SLUG/web-sources"

python3 "$KB_ROOT/scripts/compile.py" \
  --source-dir "$SOURCE_DIR" \
  --wiki-dir "$KB_ROOT/wiki" \
  --deliverable-title "Controlling (CO)" \
  --domain "CO"
```

If the KB doesn't have a compile.py, use the llm-knowledge-base skill's compile workflow
and point it at `$SOURCE_DIR`.

---

## Phase 4 — Lint

```bash
cd "$KB_ROOT" && python3 scripts/lint.py
```

---

## Finding Good Deliverables via Search

```python
#!/usr/bin/env python3
# search_help_portal.py — find canonical SAP Help Portal guides
import urllib.request, json, urllib.parse, re, sys

BASE = "https://help.sap.com"
headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0", "Referer": BASE+"/"}

def search(query, product="SAP_S4HANA_ON-PREMISE", limit=10):
    url = f"{BASE}/http.svc/search?q={urllib.parse.quote(query)}&locale=en-US&product={product}&limit={limit}"
    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15)
    return json.loads(r.read())["data"]["results"]

# Run queries and collect unique canonical deliverables (skip "What's New")
SKIP_TITLES = ["What's New", "HCM Local", "Payroll Processing", "Portfolio", "Insurance",
               "Security Guide", "Administration Guide", "Release"]
seen = {}
queries = sys.argv[1:] if len(sys.argv)>1 else ["financial accounting configuration S4HANA"]

for q in queries:
    for res in search(q):
        deliv_title = res.get("deliverableTitle","")
        url_path = res.get("url","")
        m = re.search(r'/docs/[^/]+/([0-9a-f]{32})/', url_path)
        if not m: continue
        loio = m.group(1)
        if any(s in deliv_title for s in SKIP_TITLES): continue
        if loio not in seen:
            seen[loio] = {"title": deliv_title, "hits": 0, "sample_url": url_path}
        seen[loio]["hits"] += 1

ranked = sorted(seen.items(), key=lambda x: x[1]["hits"], reverse=True)
print(f"{'Hits':>4}  {'Deliverable LOIO':<34}  Title")
print("-"*90)
for loio, info in ranked[:20]:
    print(f"  {info['hits']:>2}  {loio}  {info['title'][:50]}")
    print(f"      Navigate to: https://help.sap.com{info['sample_url'][:80]}")
```

---

## SAP Learning Portal Search API

(Cross-reference: discovered while building this skill)

```python
# Search the SAP Learning Portal for courses by topic
import urllib.request, json, urllib.parse

BASE_LP = "https://learning.sap.com"
headers_lp = {"Accept": "application/json", "User-Agent": "Mozilla/5.0", "Referer": BASE_LP+"/"}

def lp_search(query, limit=15, page=1):
    """Search SAP Learning Portal for courses matching a query."""
    filters = json.dumps({"content": query, "locale": "en-US"})
    raw = f"getCards(types='[\"search-page\"]',filters='{filters}',sort='',limit={limit},page={page})"
    url = f"{BASE_LP}/service/learning/search/{urllib.parse.quote(raw, safe='()')}"
    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers_lp), timeout=12)
    return json.loads(r.read()).get("value", {})

# Usage:
# result = lp_search("financial accounting S/4HANA FI", limit=20)
# courses = result["results"]   # list of {title, slug, type, subtype, level, ...}
# total = result["totalCount"]
#
# Filter to standalone-course only:
# courses = [c for c in result["results"] if c.get("subtype") == "Standalone-Course"]
#
# Notes:
# - types='["search-page"]' is required (NOT "standalone-course" — that returns 400)
# - The query goes in filters.content, not as a URL param
# - Results include certifications, journeys, courses — filter by subtype
# - Returns up to 15 results per page; paginate with page=2, 3, ...
# - For full catalog dump (no search), use the getCards API with types='["standalone-course"]'
#   without a content filter (returns all ~3900 courses, paginated)
```

---

## Ingestion Decision Guide

| Source | Use for | Skip for |
|---|---|---|
| SAP Help Portal config guides | Configuration reference, prerequisites, process steps, IMG settings | ESM Enterprise Services (API catalog), "What's New", delta docs |
| SAP Learning Portal courses | Conceptual understanding, hands-on exercises, scenario walkthroughs | Pure video/SCORM lessons (body is empty — correct, not a bug) |
| Combination | Best coverage: Learning Portal → "why/what", Help Portal → "how/config" | |

---

## Error Handling

| Error | Cause | Fix |
|---|---|---|
| HTTP 500 on pagecontent | Wrong file_path format — must end in `.html` | Append `.html` to loio |
| HTTP 500 on deliverableMetadata | truncated loio or wrong product_url | Use browser to capture live XHR instead |
| HTTP 400 on getCards | Wrong URL encoding or types param | Use `types='["search-page"]'` for search, `types='["standalone-course"]'` for catalog |
| Empty body in topic | Container node with no own content, or ESM metadata-only topic | Skip if word_count < 30 |
| buildNo stale (500 on pagecontent) | buildNo is periodically updated (currently 1779) | Navigate to any help.sap.com page and re-capture XHR for current buildNo |
