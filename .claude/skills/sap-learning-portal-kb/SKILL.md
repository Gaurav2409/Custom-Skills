---
name: sap-learning-portal-kb
description: >
  Scrape any SAP Learning Portal learning journey or course into the consolidated sap-kb.
  Navigates learning.sap.com using browser-harness (requires active SAP SSO session in Chrome),
  clips all lesson content, stores raw articles under sap-kb/raw/articles/<course-slug>/web-sources/,
  and compiles wiki articles into the existing sap-kb wiki via llm-knowledge-base.
  Use when the user provides a learning.sap.com/learning-journeys/ or /courses/ URL.
---

# SAP Learning Portal → sap-kb

Scrapes an SAP Learning Portal learning journey or course and ingests it into the consolidated
`sap-kb`. Raw articles are stored neatly per-course under `sap-kb/raw/articles/<course-slug>/web-sources/`.
Wiki articles are compiled into the existing `sap-kb/wiki/` tree.

Requires the user's authenticated Chrome session (SAP SSO). Uses `browser-harness` for scraping
and `llm-knowledge-base` for compilation.

**Trigger:** `/sap-learning-portal-kb`

**Domain skill:** Read `agent-workspace/domain-skills/learning-sap-com/SKILL.md` in the browser-harness repo before making any browser calls.

---

## Invocation

```
/sap-learning-portal-kb <url>
```

Examples:
```
/sap-learning-portal-kb https://learning.sap.com/learning-journeys/becoming-an-sap-enterprise-architect
/sap-learning-portal-kb https://learning.sap.com/courses/intelligent-enterprise-architecture-fundamentals
```

**Arguments:**
- `<url>` — required. A `learning-journeys/` or `courses/` URL.

No `--kb-root` or `--kb-name` flags needed — output always goes to `sap-kb`.

---

## Constants

```
BROWSER_HARNESS_DOMAIN_SKILLS = "/Users/I321170/Documents/AI_Knowledge/browser-harness/agent-workspace/domain-skills/learning-sap-com/SKILL.md"
LLM_KB_SCRIPTS_TEMPLATE = "/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/llm-knowledge-base/templates/scripts/"
SAP_KB_ROOT = "/Users/I321170/Documents/LLM knowledge base/sap-kb"
```

The `<course-slug>` is derived from the course URL path segment, e.g.
`intelligent-enterprise-architecture-fundamentals` from `.../courses/intelligent-enterprise-architecture-fundamentals`.
Raw articles land at: `SAP_KB_ROOT/raw/articles/<course-slug>/web-sources/`

---

## Phase 0 — Parse and Validate

1. Extract `<url>` from invocation.
2. Determine URL type:
   - `learning-journeys/` → will discover courses first, then lessons.
   - `courses/` → navigate directly to course, discover lessons.
3. Derive `course-slug` from the URL for each course discovered. Rules:
   - For a journey URL the slug comes from each individual course URL discovered in Phase 2.
   - For a direct course URL the slug is the last path segment of that URL.
4. Confirm with user:
   ```
   KB root:    /Users/I321170/Documents/LLM knowledge base/sap-kb
   Source URL: <url>
   Raw output: sap-kb/raw/articles/<course-slug>/web-sources/  (one folder per course)
   Wiki target: sap-kb/wiki/
   Continue? (yes to proceed)
   ```

---

## Phase 1 — Ensure Course Raw Folder

`sap-kb` already exists — do NOT reinitialise it. For each course to be scraped, create its
dedicated raw folder if it doesn't exist:

```bash
SAP_KB_ROOT="/Users/I321170/Documents/LLM knowledge base/sap-kb"
COURSE_SLUG="<course-slug>"

mkdir -p "$SAP_KB_ROOT/raw/articles/$COURSE_SLUG/web-sources"
```

This mirrors the existing pattern:
```
sap-kb/raw/articles/sap-btp/web-sources/
sap-kb/raw/articles/sap-enterprise-arch/web-sources/
sap-kb/raw/articles/<course-slug>/web-sources/   ← new course goes here
```

If the folder already exists (resume scenario), skip creation and proceed to Phase 3.

---

## Phase 2 — Discover Content Structure

Read the domain skill first: `BROWSER_HARNESS_DOMAIN_SKILLS`.

### 2a. If URL is a learning journey

```python
browser-harness -c '
import time
new_tab("<journey-url>")
wait_for_load()
time.sleep(3)

links = js("""
  Array.from(document.querySelectorAll("a")).filter(a =>
    a.href.includes("/courses/") && !a.href.split("/courses/")[1].includes("/")
  ).map(a => ({text: a.textContent.trim().slice(0,100), href: a.href}))
""")
seen = set()
courses = [l for l in links if l["href"] not in seen and not seen.add(l["href"])]
for c in courses:
    print(c)
'
```

Report discovered courses to user:
```
Discovered N course(s):
  1. Course Title → https://learning.sap.com/courses/<slug>
  ...
```

### 2b. For each course — discover lessons

```python
browser-harness -c '
import time
new_tab("<course-url>")
wait_for_load()
time.sleep(2)

lessons = js("""
  Array.from(document.querySelectorAll("nav a, aside a, [class*=sidebar] a, [class*=nav] a")).filter(a =>
    a.href.includes("/courses/") && a.href.split("/courses/")[1].includes("/")
  ).map(a => ({text: a.textContent.trim().replace(/\\s+/g," ").slice(0,100), href: a.href}))
""")
seen = set()
unique = [l for l in lessons if l["href"] not in seen and not seen.add(l["href"])]
for l in unique:
    print(l)
'
```

Assign each lesson a `unit_key` based on the sidebar grouping (group by the unit heading above each batch of lessons). The unit heading is visible in the sidebar above the lesson links — extract it with:

```python
# Extract unit → lesson groupings from sidebar
groups = js("""
  var items = [];
  var currentUnit = "unit-unknown";
  document.querySelectorAll("nav li, aside li, [class*=nav] li, [class*=sidebar] li").forEach(function(li) {
    var a = li.querySelector("a");
    if (a && a.href.includes("/courses/") && a.href.split("/courses/")[1].includes("/")) {
      items.push({unit: currentUnit, text: a.textContent.trim().replace(/\\s+/g," "), href: a.href});
    } else if (!a && li.textContent.trim()) {
      currentUnit = li.textContent.trim().replace(/\\s+/g," ").slice(0, 60);
    }
  });
  return items;
""")
```

Report total lesson count:
```
Course: <title>
  Unit 1 — <unit-title>: N lessons
  Unit 2 — <unit-title>: N lessons
  ...
  Total: N lessons
```

---

## Phase 3 — Scrape All Lessons (Progressive)

For each lesson URL, print progress immediately before fetching and after saving. This is the progressive output the user sees.

```
[1/N] Fetching: <lesson-title> ...
  ✓ Saved: <filename>.md (W words)
[2/N] Fetching: ...
```

### Scraping code per lesson

```python
browser-harness -c '
import time, os, re

# One folder per course under sap-kb/raw/articles/
OUTPUT_DIR = "/Users/I321170/Documents/LLM knowledge base/sap-kb/raw/articles/<course-slug>/web-sources"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- lesson loop (inline all lessons as a list) ---
LESSONS = [
    ("<lesson-slug>", "<lesson-title>", "<unit-key>", "<unit-title>", "<course-title>"),
    ...
]
BASE = "https://learning.sap.com/courses/<course-slug>"
CONTENT_SEL = "[class*=CourseContentLayout_content]"

for lesson_slug, lesson_title, unit_key, unit_title, course_title in LESSONS:
    url = f"{BASE}/{lesson_slug}"
    filename = f"{unit_key}--{lesson_slug}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        print(f"SKIP (exists): {lesson_title}", flush=True)
        continue

    print(f"Fetching: {lesson_title}", flush=True)
    new_tab(url)
    wait_for_load()
    time.sleep(2.5)

    # Auth check
    info = page_info()
    if "accounts.sap" in info.get("url","") or "sign" in info.get("title","").lower():
        print(f"AUTH_REQUIRED — SAP session expired. Stop.", flush=True)
        break

    content = js(f"""
      var el = document.querySelector("{CONTENT_SEL}");
      el ? el.innerText : document.querySelector("main").innerText;
    """)

    # Strip noise
    content = re.sub(
        r"\n+Was this lesson helpful\?\s*\n+Yes\s*\n+No\s*\n+(Next lesson|Continue to quiz)\s*$",
        "", content, flags=re.IGNORECASE
    )
    content = re.sub(r"^\s*" + re.escape(lesson_title) + r"\s*\n+", "", content)
    content = content.strip()
    word_count = len(content.split())

    md = f"""---
source_url: {url}
course_title: {course_title}
unit_title: {unit_title}
lesson_title: {lesson_title}
unit_key: {unit_key}
lesson_slug: {lesson_slug}
ingested: 2026-05-16
source_type: learning_portal
confidence_weight: 0.85
word_count: {word_count}
---

# {lesson_title}

**Course:** {course_title}
**Unit:** {unit_title}
**Source:** {url}

---

{content}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  ✓ Saved: {filename} ({word_count} words)", flush=True)
'
```

**Skip files that already exist** — this makes the scraper resumable. If scraping is interrupted, rerun and it continues from where it left off.

---

## Phase 4 — Cluster

```bash
cd "/Users/I321170/Documents/LLM knowledge base/sap-kb" && python3 scripts/cluster.py --kb-root .
```

Report cluster result to user.

---

## Phase 5 — Compile Wiki Articles

This is the substantive synthesis step. Read all raw lesson files from
`sap-kb/raw/articles/<course-slug>/web-sources/` and write wiki articles into
`sap-kb/wiki/` following the format below.

**Check for existing wiki articles first** — if an article with the same slug already
exists in `sap-kb/wiki/`, ask the user whether to skip or update (overwrite) it.
Do not silently overwrite existing sap-kb content.

### Determine article set from content

After reading the raw files, group them by topic and decide which wiki articles to write:
- **Concepts** — one article per distinct architectural concept or framework (EA fundamentals, TOGAF ADM, each architecture domain, governance, roadmaps, etc.)
- **Entities** — one article per named SAP tool, product, or standard (SAP LeanIX, TOGAF, SAP EA Framework, etc.)
- **Topics** — one article per thematic cross-cutting concern (stakeholder management, EA maturity, etc.)

Aim for Karpathy depth: each article should let an architect understand and apply the topic with zero external lookup.

### Required article sections

```markdown
---
title: "Article Title"
type: concept | entity | topic
domain: [enterprise-architecture, sap]
tags: [tag1, tag2]
sources:
  - file: "../../raw/articles/<course-slug>/web-sources/<filename>.md"
    type: learning_portal
    confidence_weight: 0.85
confidence: high | medium | low
review_status: current
last_updated: "<date>"
first_created: "<date>"
---

## Summary
2–3 sentence overview.

## Why This Exists
What problem does this concept solve? Why was it created?

## Mental Model
Core intuition — how an architect thinks about this.

## Architecture Overview
ASCII diagram or structured prose showing how components/phases/artifacts relate.

## Key Principles
3–7 principles with explanations.

## SAP-Specific Application
How SAP implements this: tool names, artifact names, methodology steps.

## Worked Example / Case Study
Concrete scenario from source material. For non-coding topics, use architecture examples.

## Common Pitfalls
3–5 failure modes with specific descriptions.

## Connections
[[wikilinks]] to related wiki articles.

## Open Questions
Gaps not answered by available sources (drives future ingests).
```

### After writing all articles, update index files

1. **`wiki/_summaries.md`** — append one entry per raw source file:
   ```
   ## [<date>] <filename>
   <one-paragraph summary of what the source covers>
   ```

2. **`wiki/_index.md`** — add every article under Concepts/Entities/Topics using `[[slug|Display Name]]` wikilinks. Update the All Articles table.

3. **`wiki/entity_registry.md`** — add each entity to the registry table.

4. **`wiki/log.md`** — append a compile log entry.

---

## Phase 6 — Lint

```bash
cd "/Users/I321170/Documents/LLM knowledge base/sap-kb" && python3 scripts/lint.py --kb-root . --fix 2>&1
```

Fix any broken wikilinks (remove placeholder template links). Report the health dashboard to user.

---

## Phase 7 — Update sap-kb Log

Do NOT add a new entry to `~/.claude/CLAUDE.md` — `sap-kb` is already registered there.

Instead, append a compile log entry to `sap-kb/wiki/log.md`:

```markdown
## [<date>] Learning Portal ingest: <course-slug>

- Source: <url>
- Raw files: sap-kb/raw/articles/<course-slug>/web-sources/ (N files, ~W words)
- Wiki articles added/updated: N
- Phase 6 lint: X% health
```

---

## Resumability

The skill is fully resumable at each phase:
- **Phase 3 skips existing files** — rerun after interruption, scraping continues from last saved lesson.
- **Phase 4–6 are idempotent** — cluster and lint are safe to rerun.
- **Phase 5 checks existing wiki articles** — if an article already exists, skip or ask whether to update.

---

## Error Handling

| Error | Action |
|-------|---------|
| `AUTH_REQUIRED` in Phase 3 | Stop immediately. Tell user: "SAP session expired — log in to learning.sap.com in Chrome, then re-run." |
| Lesson content < 50 words | Add `[SHORT_CONTENT]` note; still save the file. Quiz pages are commonly short. |
| Course cards not found on journey page | Take screenshot, scroll down, retry after `time.sleep(5)`. Some journeys render slowly. |
| browser-harness not responding | Run `browser-harness -c 'print(page_info())'` to test connectivity. |

---

## Karpathy Depth Checklist

Before marking compile complete, verify each article has:

- [ ] A concrete "why this exists" (not just what it is)
- [ ] A mental model that would survive being explained verbally
- [ ] At least one worked scenario (not hypothetical — use specifics from source)
- [ ] Named SAP artifacts, tools, or methodology steps (not generic)
- [ ] `[[wikilinks]]` to at least 2 other articles
- [ ] `## Common Pitfalls` with specific failure descriptions

---

## Example Run

```
User: /sap-learning-portal-kb https://learning.sap.com/learning-journeys/becoming-an-sap-enterprise-architect

[Phase 0] Parsed: journey URL
          KB root:    sap-kb
          Raw output: sap-kb/raw/articles/intelligent-enterprise-architecture-fundamentals/web-sources/
          Wiki target: sap-kb/wiki/
[Phase 1] Created: sap-kb/raw/articles/intelligent-enterprise-architecture-fundamentals/web-sources/
[Phase 2] Discovered 1 course: Intelligent Enterprise - Architecture Fundamentals
          Discovered 25 lessons across 7 units
[Phase 3] Scraping 25 lessons...
  [1/25] Fetching: Examining Enterprise Architecture ... ✓ (679 words)
  [2/25] Fetching: Tailoring the TOGAF ADM ...          ✓ (996 words)
  ...
  [25/25] Fetching: Quiz: Opportunities & Solutions ...  ✓ (81 words)
  Total: 33,391 words → sap-kb/raw/articles/intelligent-enterprise-architecture-fundamentals/web-sources/
[Phase 4] Clustering: 1 cluster (25 docs, coherence 0.163)
[Phase 5] Compiling 18 wiki articles into sap-kb/wiki/...
  concepts/ (10): enterprise-architecture-fundamentals, togaf-adm, ...
  entities/ (4):  sap-enterprise-architecture-framework, sap-leanix, ...
  topics/   (4):  intelligent-enterprise-architecture, ea-practice-maturity, ...
[Phase 6] Lint: 90% health, 0 errors, 18 warnings (cosmetic)
[Phase 7] Log entry appended to sap-kb/wiki/log.md
Done. New content ingested into sap-kb.
```
