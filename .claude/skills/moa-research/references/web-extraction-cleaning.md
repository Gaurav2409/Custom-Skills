# Web Extraction Cleaning — ROBUST FETCH PROTOCOL

Every URL fetched and saved as a raw source file must be cleaned before writing.
This is mandatory. Raw markdown from `web_extract` / browser-harness / crawl4ai /
`r.jina.ai` contains high-noise boilerplate that inflates file size, pollutes KB
embeddings, and wastes MoA reference-model context.

---

## What the noise looks like (empirically observed in bluespan-kb raw files)

| Noise type | Example | Typical size |
|---|---|---|
| Cookie consent banner | "We use essential cookies… Accept / Decline / Customize …" | 400-800 words |
| Navigation menus | `* [Products](…) * [Solutions](…) * [Pricing]` | 50-200 lines |
| Site header / hero with no text | `![Image 1](cdn.prod.website-files.com/…)` | 1 line per image |
| Logo carousels repeated | Same 8 logos repeated twice (Abridge customer carousel) | 16+ image lines |
| Footer / site-map links | "Learn / What Is AWS? / What Is Cloud Computing? / …" | 50-150 lines |
| CTA boilerplate | "Get started now » / Learn more in the FAQs »" | 10-30 lines |
| 404 page body | Full nav + "Page Not Found" site chrome | 200-400 lines |
| Privacy/GDPR overlays | "Your privacy choices … Opt out of cross-context behavioral ads" | 200-400 words |

These noise types contribute zero information to research synthesis. A 12 KB raw file
may contain only 2-3 KB of actual content.

---

## Detection and rejection rules (check BEFORE writing any file)

**Hard reject — do not save, log as FAILED:**

1. **404 / error page** — detected by any of:
   - HTTP status 404 or 410 from HEAD request
   - `<title>` containing "404", "Page Not Found", "Not Found", "Error"
   - Body text under 400 characters after stripping HTML
   - Markdown content starting with "Skip to main content" + nav links with no substantive text

2. **Cookie banner intercept** — detected by:
   - First 500 chars of body contain "we use cookies" / "essential cookies" / "accept or decline"
   - Body is >80% cookie/consent language with no product content

3. **Login / paywall wall** — detected by:
   - HTTP 401/403
   - Body contains "Sign in to continue", "Create an account to read", "Subscribe to access"
   - Body under 300 chars after stripping

**Soft reject — attempt alternate extraction, then fall back:**

4. **SPA skeleton** — `document.body.innerText.length < 300` after 4s hydration wait → use site-specific selector or `document.body.innerText` fallback → fail if still under 400 chars

---

## Cleaning function (Python — embed in every Hermes brief prompt)

```python
import re

def clean_web_content(raw_markdown: str, url: str = "") -> str:
    """
    Remove structural noise from web-extracted markdown before saving as raw source.
    Returns cleaned text, or empty string if content is below minimum quality threshold.
    """
    text = raw_markdown

    # 1. Strip cookie consent blocks (common patterns from AWS, Google, EU sites)
    text = re.sub(
        r'(?is)(we use (essential )?cookies.*?)(save preferences|dismiss|cancel|accept cookies)',
        '', text
    )
    text = re.sub(
        r'(?is)(select your cookie preferences.*?)(save preferences|dismiss)',
        '', text
    )
    text = re.sub(
        r'(?is)(your privacy choices.*?)(cancel save preferences|dismiss)',
        '', text
    )

    # 2. Strip image markdown references — ![Image N](cdn...) lines
    # Keep images that have meaningful alt text (not "Image 1", "Image 2", etc.)
    text = re.sub(r'!\[Image \d+\]\([^)]+\)\n?', '', text)
    # Also strip bare image lines with no alt text
    text = re.sub(r'!\[\]\([^)]+\)\n?', '', text)

    # 3. Strip navigation menu blocks
    # Pattern: 3+ consecutive markdown list items that are all links
    def strip_nav_blocks(t):
        lines = t.split('\n')
        out = []
        link_run = 0
        for line in lines:
            stripped = line.strip()
            is_link_item = bool(re.match(r'^[\*\-\+]\s+\[', stripped))
            if is_link_item:
                link_run += 1
            else:
                if link_run >= 4:
                    # Was a nav block — discard
                    pass
                else:
                    # Short list — keep
                    for _ in range(link_run):
                        out.append('')  # preserve spacing
                link_run = 0
                out.append(line)
        return '\n'.join(out)
    text = strip_nav_blocks(text)

    # 4. Strip footer boilerplate patterns
    # Common footer start markers
    footer_markers = [
        r'\n#+\s+Learn\b',
        r'\n#+\s+Resources\b',
        r'\n#+\s+About AWS\b',
        r'\n#+\s+Contact us\b',
        r'\n\*\s+\[What Is ',        # AWS footer links
        r'\nCreate an AWS account',
        r'\n#+\s+Follow us',
        r'\n#+\s+Legal\b',
        r'\nCopyright ©',
        r'\n©\s+\d{4}',
    ]
    for marker in footer_markers:
        m = re.search(marker, text)
        if m:
            text = text[:m.start()]

    # 5. Strip repeated carousel / logo blocks
    # Detect and deduplicate runs of 3+ identical lines
    lines = text.split('\n')
    seen_recently = {}
    out_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) > 10:
            if stripped in seen_recently and (i - seen_recently[stripped]) < 30:
                continue  # duplicate within a 30-line window
            seen_recently[stripped] = i
        out_lines.append(line)
    text = '\n'.join(out_lines)

    # 6. Strip CTA / "get started" boilerplate lines
    cta_patterns = [
        r'^\[Get started now',
        r'^\[Learn more(?: in the| »)',
        r'^\[Contact us\b',
        r'^\[Sign up\b',
        r'^\[Create an? account\b',
        r'^\[Start free\b',
        r'^\s*\[?\s*Skip to (main )?content\s*\]?',
    ]
    text = '\n'.join(
        line for line in text.split('\n')
        if not any(re.match(pat, line.strip(), re.IGNORECASE) for pat in cta_patterns)
    )

    # 7. Collapse excessive blank lines (3+ → 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 8. Minimum content check
    content_chars = len(re.sub(r'\s+', '', text))
    if content_chars < 400:
        return ''  # caller should treat as fetch failure

    return text.strip()
```

---

## Integration points — where to call this

### In Hermes brief prompts (Phases 1–2)

Every brief prompt must include these instructions in the **RAW SOURCE SAVE PROTOCOL** block:

```
RAW SOURCE SAVE PROTOCOL (mandatory for every URL you fetch):

1. Fetch the page content (browser-harness: new_tab → wait_for_load → 4s JS wait →
   document.body.innerText or site-specific selector).

2. Before saving, clean the content:
   - Remove all cookie consent banners (detect: "we use cookies", "accept/decline",
     "your privacy choices" — strip from start of body)
   - Remove all image markdown lines: `![Image N](url)` → delete
   - Remove navigation menus (3+ consecutive link-list items → delete the block)
   - Remove footer boilerplate (stop at first of: "## Learn", "## Resources",
     "© 2024", "Create an account", "Follow us", "Legal")
   - Remove duplicate carousel lines (same line repeated within 30 lines → keep first only)
   - Remove CTA lines ("Get started now »", "Learn more »", "Skip to content")
   - Collapse 3+ blank lines → 2

3. After cleaning: if content is under 400 chars, do NOT save. Log as FAILED.

4. If content is 404 / "Page Not Found" / error page, do NOT save. Log as FAILED.

5. Save the CLEANED content with this frontmatter:
   ---
   url: <original URL>
   title: <page title>
   fetched_at: <YYYY-MM-DD>
   content_chars: <character count of cleaned content>
   brief: <brief number>
   ---
```

### In the `revisit_failed_urls.sh` pipeline

The `try_wayback` and `try_alternate` functions already do basic HTML stripping.
Extend the Python snippet in each to call the full cleaning function above:
- Add image-markdown removal
- Add footer-stop heuristics
- Add cookie-banner strip
- Add 400-char minimum check (already present but tighten to cleaned-char count)

### In the moa-call.sh + `===INLINE:===` pipeline (Phases 0, 3–7)

Before inlining a raw source file, run it through the cleaner to avoid wasting
MoA reference model context on cookie banners and nav menus. Add a pre-inline
clean step in the workflow:

```python
# Pre-inline cleaner — run before ===INLINE:=== on any raw source
cleaned = clean_web_content(open(path).read(), url=path)
if cleaned:
    open(path, 'w').write(cleaned)  # overwrite in place
```

---

## Size reduction expected

Based on empirically measured noise ratios in bluespan-kb/raw/articles/:

| File type | Typical raw size | Expected clean size | Reduction |
|---|---|---|---|
| AWS/Google product pages | 12–20 KB | 4–8 KB | ~50-60% |
| News/funding articles | 5–8 KB | 4–6 KB | ~20-30% |
| SPA homepage (vendor) | 8–14 KB | 3–6 KB | ~50-60% |
| Research/academic pages | 10–30 KB | 8–25 KB | ~15-20% |
| 404 / error pages | 3–10 KB | REJECTED | 100% |
| Cookie-banner intercepts | 5–15 KB | REJECTED | 100% |

Across a 100-file brief corpus, cleaning typically saves 20-40% total size, which
directly reduces MoA reference-model context use when files are inlined via `===INLINE:===`.

---

## What NOT to strip

- Structured data (tables, numbered lists of features/pricing)
- Inline code blocks and technical specifications
- Quoted text and verbatim references
- Short link references where the link text is informative
- Headers (`#`, `##`) that introduce content sections

The goal is to remove structural chrome, not to summarize the content. The MoA
reference models should receive the actual page content, just without the noise.
