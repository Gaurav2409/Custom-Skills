# learn.chatgpt.com — Scraping Notes

## Site structure

- **JS-rendered SPA** — `http_get` returns HTML shell, 0 usable content. Must use browser navigation.
- **Content selector**: `main article` — clean prose, no nav noise. Falls back to `main`.
- **Nav sections**: Docs (Overview/Features/Configuration/Developers/Security/Administration), Use cases, Resources.
- **Sidebar links**: extracted via `nav a, aside a, [role=navigation] a` — returns ~40–50 links per section page.

## URL patterns

- Docs: `https://learn.chatgpt.com/docs/<slug>` and `https://learn.chatgpt.com/docs/<section>/<slug>`
- Use cases: `https://learn.chatgpt.com/use-cases` (+ `?category=`, `?team=`, `?task_type=` query params — same JS-filtered page, skip)
- Use cases collections: `https://learn.chatgpt.com/use-cases/collections`
- Resources / Learn: `https://learn.chatgpt.com/resources`, `/learn`

## Discovery pattern

1. `goto_url("https://learn.chatgpt.com/docs")` → `wait_for_load()`
2. Extract links: `js("Array.from(document.querySelectorAll('nav a, aside a')).map(a=>({text:a.innerText.trim(),href:a.href})).filter(a=>a.href.startsWith('https://learn.chatgpt.com'))")`
3. Repeat for each top-level section URL to collect sub-page links
4. Deduplicate; skip query-param filter URLs (`?category=`, `?team=`, `?task_type=`)

## Extraction pattern

```python
goto_url(url)
wait_for_load()
content = js("""
(function() {
  const el = document.querySelector("main article") || document.querySelector("main");
  return el ? el.innerText : "";
})()
""")
# Quality gate: len > 300 and sentences > 5
```

## Thin pages (known)

- `/docs/open-source` — 1252 chars, mostly links, not worth saving
- `/docs/developer-commands` — 346 chars on static load; may need extra wait

## Notes

- 84 content pages scraped 2026-07-11; total ~796 KB
- `main article` consistently returns clean content without sidebar noise
- No auth required for any docs page
- GPT-5.6 Sol is the current default model referenced in CLI examples (`gpt-5.6-sol`)
