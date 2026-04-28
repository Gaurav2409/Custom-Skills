---
name: web-clipper
description: Clip web pages to local Markdown files with downloaded images. Use when the user wants to save web pages as Markdown, archive URLs locally, build an offline reading list, or convert documentation sites to local .md files. Handles JavaScript-rendered pages via Playwright headless browser. Trigger phrases include "clip this URL", "save page as markdown", "archive these links", "scrape to markdown".
---

# Web Clipper

Convert any list of URLs into clean, local Markdown files — with images downloaded and linked locally. Uses a real headless Chromium browser (Playwright) so JavaScript-rendered pages work correctly.

The clipper also **crawls**: it follows same-domain links discovered within each page up to **depth 2**, building a complete local mirror of reachable content.

```
urls.txt (seed URLs)
    │
    ├── depth 0: clip seed page → discover links
    ├── depth 1: clip each discovered link → discover more links
    └── depth 2: clip those links (stop here)

Output:
clips/
├── intro-guide.md
├── api-reference.md
├── tutorial-getting-started.md
└── images/
    ├── abc123def456.png
    └── 789xyz012ghi.jpg
```

---

## Phase 0: Determine What the User Needs

Before doing anything, clarify which operation is requested:

- **Setup** — user wants to install dependencies and get the script running
- **Clip** — user has `urls.txt` ready and wants to run the clipper
- **Troubleshoot** — something went wrong (Playwright error, missing images, empty output)
- **Customise** — user wants to change content selectors, output format, or concurrency

---

## Phase 1: Setup

### 1.1 Install dependencies

Run these commands in the project directory:

```bash
pip install playwright beautifulsoup4 markdownify requests
playwright install chromium
```

> **Note:** `playwright install chromium` downloads ~130MB. Only needed once per machine.

### 1.2 Copy the script

Copy `clipper.py` from the skill templates into your project root:

```bash
cp <skill-templates-dir>/scripts/clipper.py ./clipper.py
```

Or ask Claude to write it fresh from the template.

### 1.3 Create `urls.txt`

Create a `urls.txt` file in the same directory as `clipper.py`:

```
# One URL per line. Lines starting with # are ignored.
https://example.com
https://docs.python.org/3/library/pathlib.html
```

---

## Phase 2: Run the Clipper

```bash
python3 clipper.py
```

The script will:

1. Read every non-comment line from `urls.txt` as seed URLs
2. Launch a headless Chromium browser
3. Navigate to each URL and wait for JS to finish rendering
4. Extract the main article content (ignoring navbars and footers)
5. **Discover all same-domain links** in the content and add them to the crawl queue
6. Download all images to `clips/images/`
7. Rewrite image `src` attributes to local relative paths
8. Convert HTML → Markdown and save to `clips/<page-title>.md`
9. Repeat for discovered links up to **depth 2** (same hostname only)
10. Print `[depth N]` progress per page and a final summary

---

## Phase 3: Output Structure

After a successful run:

```
clips/
├── my-article-title.md          ← clean Markdown with frontmatter-style source URL
├── python-pathlib-docs.md
└── images/
    ├── abc123def456.png          ← image filename = SHA-1 hash of original URL
    └── 789xyz012ghi.jpg
```

Each `.md` file starts with:

```markdown
# Page Title

> Source: https://original-url.com/path

[article content here...]
```

---

## Phase 4: Customisation

### Change crawl depth

The default is `MAX_DEPTH = 2`. Set it to `0` to clip only the seed URLs with no crawling, or `1` for one hop:

```python
MAX_DEPTH = 0   # seed URLs only — no link following
MAX_DEPTH = 1   # seed + one level of links
MAX_DEPTH = 2   # seed + two levels (default)
```

> **Warning:** depth 2 on a large docs site can produce hundreds of files. Start with `MAX_DEPTH = 1` to preview the scope.

### Change the content selector

By default the script tries these selectors in order:

```python
CONTENT_SELECTORS = ["main", "article", '[role="main"]', ".content", "#content", ".post-content"]
```

Edit `CONTENT_SELECTORS` in `clipper.py` to add site-specific selectors (e.g., `".article-body"` for a specific news site).

### Adjust timeout

The default `networkidle` timeout is 20 seconds. For slow sites, increase it:

```python
page.goto(url, wait_until="networkidle", timeout=40_000)
```

### Skip image downloads

To skip downloading images and keep original URLs, remove the `for img in content.find_all("img"):` block in `clip_url()`.

---

## Phase 5: Troubleshooting

| Symptom | Fix |
|---------|-----|
| `playwright._impl._errors.Error: Executable doesn't exist` | Run `playwright install chromium` |
| Empty `.md` file | The page's content may use a non-standard selector — add it to `CONTENT_SELECTORS` |
| All images missing | Some sites block headless browsers; check the `[warn]` lines in stderr |
| `ModuleNotFoundError` | Run `pip install playwright beautifulsoup4 markdownify requests` |
| Timeout on JS-heavy SPA | Increase `timeout` in `page.goto()` or add `page.wait_for_selector(".your-content")` |
| SSL certificate errors | Pass `ignore_https_errors=True` to `browser.new_context()` |
