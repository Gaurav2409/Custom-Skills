---
name: sap-help-portal
description: >
  Search, browse, and retrieve documentation from SAP Help Portal (help.sap.com).
  Supports keyword search, product discovery, structured document navigation (TOC),
  URL resolution, and full page content retrieval — all without authentication.
triggers:
  - "SAP help"
  - "SAP doc / SAP documentation"
  - "search SAP"
  - "find in SAP help"
  - "SAP [product/module] how to / what is / explain"
  - "help.sap.com"
tool: web_fetch
base_url: https://help.sap.com
---

## Overview

This skill provides **six operations** for interacting with SAP Help Portal. Choose based on user intent:

| Operation | When to use |
|-----------|-------------|
| **Search Content** | User asks a question or wants to find pages by topic |
| **Find Product** | User mentions an SAP product name, wants to discover its documentation |
| **Get Deliverables** | User wants to see all available guides/documents for a product |
| **Get TOC** | User wants to browse the table of contents of a specific document |
| **Get Page** | User wants to read a specific documentation page |
| **Resolve URL** | User provides a `help.sap.com/docs/...` URL |

### Interaction Pattern

- **Ambiguous intent → default to Search Content** in list mode, then wait for user selection.
- **User provides a URL → always call Resolve URL first**, then proceed with Get Page or Get TOC.
- **User names a product → call Find Product** to get the `product_id`, then offer to list deliverables.

### No Authentication Required

All operations target PRODUCTION-state public documentation. No cookies or tokens are needed.

**IMPORTANT constraints:**
- Do NOT read any cookie files, call sap-authentication, or add Cookie/Authorization headers.
- Do NOT reference `AUTH_COOKIE_DIR`, `DECRYPT_KEY`, or any auth-related config from other skills.
- If an API call returns a login redirect, inform the user that the content may be internal-only — do NOT attempt authentication.

### Implementation Method

All API calls MUST be executed using `curl` with JSON parsing via `jq` (or inline shell tools). Do NOT use Python scripts for HTTP requests or JSON parsing. Keep the execution lightweight:

```bash
# Example pattern for all API calls in this skill:
curl -s "https://help.sap.com/http.svc/search?q=SSO&language=en-US&state=PRODUCTION&from=0&to=10" \
  -H "Accept: application/json" | jq '.data.results[] | {title, url, description}'
```

If `jq` is not available, fall back to `python3 -c "import sys,json; ..."` one-liners — but never use multi-line Python scripts or temp files for simple JSON extraction.

---

## Operation 1 — Search Content

Semantic search across all SAP Help Portal page content.

### API Call

```
GET https://help.sap.com/http.svc/search?q={query}&language=en-US&state=PRODUCTION&from=0&to={limit}
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | — | Natural language question or keywords |
| `product_id` | string | No | — | Scope results to a specific product (e.g., `IDENTITY_AUTHENTICATION`) |
| `limit` | number | No | 10 | Max results (max 20) |

When `product_id` is provided, add `&product={product_id}` to the URL.

### Response Parsing

From `data.results[]`, extract:

| Field | JSON key | Notes |
|-------|----------|-------|
| Product ID | `productId` | Use with Get Deliverables / Get Page |
| Product Name | `product` | Human-readable |
| Deliverable loio | Parse from `url`: 2nd segment after `/docs/` | 32-char hex |
| Page loio | Parse from `url`: 3rd segment (without `.html`) | 32-char hex |
| Title | `title` | Page title |
| Description | `description` | Short excerpt |

URL pattern: `/docs/{product_id}/{deliverable_loio}/{page_loio}.html?...`

### Output Format

```
Found {N} results for "{query}":

1. **{title}**
   Product: {product} | Document: {deliverableTitle}
   {description}
   → product_id: {productId}, deliverable: {deliverable_loio}, page: {page_loio}

2. ...

Which result would you like me to open?
```

→ Wait for user selection, then use **Get Page** with the extracted identifiers.

---

## Operation 2 — Find Product

Search for SAP products by name. Returns `product_id` values needed by other operations.

### API Call

```
GET https://help.sap.com/http.svc/elasticsearch?q={query}&language=en-US&state=PRODUCTION&transtype=standard,html,pdf,others&product=&area=topproducts&to={limit}&excludeNotSearchable=1
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | — | Product name to search (e.g., "Cloud Identity Services") |
| `limit` | number | No | 5 | Max results |

### Response Parsing

From `data.products[]`, extract:

| Field | JSON key |
|-------|----------|
| Product ID | `product` |
| Title | `title` |
| URL | `url` |

### Output Format

```
Found {N} SAP products matching "{query}":

1. **{title}**
   product_id: `{product}`
   🔗 https://help.sap.com{url}

2. ...

Would you like me to list available documents for one of these products?
```

→ Wait for user selection, then use **Get Deliverables** with the `product_id`.

---

## Operation 3 — Get Deliverables

List all available HTML documents (guides, references) for a product.

### Step 1 · Resolve Product Version

```
GET https://help.sap.com/http.svc/productpagebyproduct?product={product_id}
```

Extract `version` from `data.redirect` using regex: `version=([^&]+)`

### Step 2 · Get Product Page

```
GET https://help.sap.com/http.svc/productpage?product={product_id}&version={version}&locale=en-US&state=PRODUCTION
```

### Response Parsing

Navigate: `data.kpTasks[] → contentCategories[] → links[]`

Filter for `link.format === "html5.uacp"` and extract:

| Field | How to extract |
|-------|----------------|
| Title | `link.title` |
| Deliverable loio | Regex on `link.href`: `/docs/[^/]+/([a-f0-9]{32})` |
| URL | `link.href` |

### Output Format

```
Documents for {product_id} (version: {version}):

1. **{title}**
   deliverable_loio: `{loio}`
   🔗 https://help.sap.com{href}

2. ...

Would you like me to show the table of contents for one of these?
```

→ Wait for user selection, then use **Get TOC** with `product_id` + `deliverable_loio`.

---

## Operation 4 — Get TOC (Table of Contents)

Fetch the full table of contents for a document, showing all sections and their page loios.

### Step 1 · Resolve Version + Metadata

First resolve the product version (same as Get Deliverables Step 1), then:

```
GET https://help.sap.com/http.svc/deliverableMetadata?product_url={product_id}&version={version}&deliverable_url={deliverable_loio}&language=en-US&state=PRODUCTION&deliverableInfo=1&toc=1
```

Extract from response:

| Variable | JSON path |
|----------|-----------|
| `deliverable_id` | `data.deliverable.id` |
| `build_no` | `data.deliverable.buildNo` |
| `landing_page_loio` | `data.topicLoio` |

### Step 2 · Fetch Landing Page (contains full TOC)

```
GET https://help.sap.com/http.svc/pagecontent?deliverableInfo=1&deliverable_id={deliverable_id}&buildNo={build_no}&file_path={landing_page_loio}.html
```

The full TOC is at: `data.deliverable.fullToc[]`

### TOC Structure

Each TOC node has:
- `t` — title
- `u` — page filename (remove `.html` suffix to get `page_loio`)
- `c` — array of child nodes (recursive)

### Output Format

Render as an indented tree:

```
Table of Contents: {deliverable_title}

1. {title} [loio: {page_loio}]
   1.1. {child_title} [loio: {child_loio}]
   1.2. {child_title} [loio: {child_loio}]
      1.2.1. {grandchild_title} [loio: {grandchild_loio}]
2. {title} [loio: {page_loio}]
...

Which section would you like me to open?
```

→ Wait for user selection, then use **Get Page** with the selected `page_loio`.

---

## Operation 5 — Get Page

Fetch and render the content of a specific documentation page.

### Prerequisites

You need three identifiers:
- `product_id` — from Find Product, Search Content, or Resolve URL
- `deliverable_loio` — from Get Deliverables, Search Content, or Resolve URL
- `page_loio` — from Get TOC, Search Content, or Resolve URL (omit to get landing page)

### Step 1 · Resolve Version + Metadata

```
GET https://help.sap.com/http.svc/productpagebyproduct?product={product_id}
```

Extract `version` from `data.redirect`.

```
GET https://help.sap.com/http.svc/deliverableMetadata?product_url={product_id}&version={version}&deliverable_url={deliverable_loio}&language=en-US&state=PRODUCTION&deliverableInfo=1&toc=0
```

Extract:

| Variable | JSON path |
|----------|-----------|
| `deliverable_id` | `data.deliverable.id` |
| `build_no` | `data.deliverable.buildNo` |
| `landing_page_loio` | `data.topicLoio` |

### Step 2 · Fetch Page Content

Use `page_loio` if provided, otherwise use `landing_page_loio`:

```
GET https://help.sap.com/http.svc/pagecontent?deliverableInfo=1&deliverable_id={deliverable_id}&buildNo={build_no}&file_path={target_loio}.html
```

The HTML content is at: `data.body`

### Step 3 · Render as Markdown

Convert `data.body` HTML to clean Markdown:

1. Strip `<!DOCTYPE>`, `<head>`, `<link>`, `<meta>` elements
2. Convert headings (`<h1>`–`<h6>`) to Markdown `#` syntax
3. Convert `<p>` to paragraphs with blank lines
4. Convert `<ul>/<ol>/<li>` to Markdown lists
5. Convert `<table>` to Markdown tables
6. Convert `<a href="...">` to Markdown links — if href contains a loio pattern (`[a-f0-9]{32}`), note it as a navigable page
7. Convert `<code>/<pre>` to code blocks
8. Strip all remaining HTML tags
9. Decode HTML entities

### Output Format

```
# {page_title}

**Document:** {deliverable_title}
**Product:** {product_name}
**Source:** https://help.sap.com/docs/{product_readable_url}/{deliverable_readable_url}/{page_loio}

---

{rendered_markdown_content}

---

**Navigation:**
- Related pages found in links: {list of page_loios mentioned in the content}
- To browse other sections: ask for the TOC
```

---

## Operation 6 — Resolve URL

Parse a `help.sap.com/docs/...` URL into identifiers usable with other operations.

**Always call this first when the user provides a URL.**

### URL Pattern

```
https://help.sap.com/docs/{product_url}[/{deliverable_url}[/{topic_url}]][?state=...&version=...]
```

Accepts partial URLs:
- Product only: `https://help.sap.com/docs/green-ledger`
- Product + deliverable: `https://help.sap.com/docs/green-ledger/use`
- Full: `https://help.sap.com/docs/green-ledger/use/overview`

### Step 1 · Parse URL Segments

Extract from the URL path:
- `product_url` — 1st segment after `/docs/`
- `deliverable_url` — 2nd segment (optional)
- `topic_url` — 3rd segment (optional)

Extract from query params:
- `state` — default `PRODUCTION`
- `version` — default `LATEST`

### Step 2 · Resolve Identifiers

**If only product_url is present:**

```
GET https://help.sap.com/http.svc/productpagebyproduct?product={product_url}
```

Then:

```
GET https://help.sap.com/http.svc/productpage?product={product_url}&version={version}&locale=en-US&state={state}
```

Extract `product_id` from `data.productId`, `product_name` from `data.productName`.

**If deliverable_url is present (with or without topic_url):**

```
GET https://help.sap.com/http.svc/deliverableMetadata?product_url={product_url}&deliverable_url={deliverable_url}&topic_url={topic_url}&version={version}&state={state}&deliverableInfo=1&toc=0&loadlandingpageontopicnotfound=true
```

Extract:

| Field | JSON path |
|-------|-----------|
| `product_id` | `data.deliverable.product` |
| `product_name` | `data.deliverable.productName` |
| `deliverable_loio` | `data.deliverableLoio` |
| `deliverable_id` | `data.deliverable.id` |
| `build_no` | `data.deliverable.buildNo` |
| `page_loio` | `data.topicLoio` |

### Output Format

```
Resolved URL: {original_url}

- product_id: `{product_id}`
- product_name: {product_name}
- deliverable_loio: `{deliverable_loio}` (if resolved)
- page_loio: `{page_loio}` (if resolved)

Next steps:
- To read this page → Get Page with the above identifiers
- To browse the document → Get TOC
- To see other documents → Get Deliverables
```

→ Then proceed based on user intent.

---

## Alternative Search — Semantic Search API (POST)

For richer semantic search with more filtering options, use this POST endpoint instead of the GET-based Operation 1:

```
POST https://help.sap.com/http.svc/semanticsearch
Content-Type: application/json
```

Payload:

```json
{
  "to": 10,
  "isExactMatch": false,
  "query": "<keywords>",
  "searchType": "SEMANTIC",
  "keywordHighlight": false,
  "semanticHighlight": false,
  "transTypes": ["standard", "html", "pdf", "others"],
  "states": ["PRODUCTION"]
}
```

Notes:
- Increase `"to"` up to 20 for broader results.
- Add `"TEST"` / `"DRAFT"` to `"states"` only if user explicitly wants pre-release content.
- This endpoint may return slightly different ranking than the GET `/http.svc/search` endpoint.

Response parsing is the same as Operation 1.

---

## Error Handling

| Situation | Action |
|-----------|--------|
| Search returns 0 results | Suggest broader or alternative keywords, offer to retry |
| Product not found | Suggest alternative product names, try partial match |
| `deliverableMetadata` call fails | Fall back: use `web_fetch` directly on the full URL |
| `pagecontent` returns empty body | Fall back: use `web_fetch` directly on the full URL |
| Version resolution fails | Try `version=LATEST` as fallback |
| Any API call fails | Inform user, suggest retrying or opening the URL manually |

---

## Quick Reference — API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/http.svc/search` | GET | Search page content by topic |
| `/http.svc/elasticsearch` | GET | Search products by name |
| `/http.svc/productpagebyproduct` | GET | Resolve product → version |
| `/http.svc/productpage` | GET | List deliverables for a product |
| `/http.svc/deliverableMetadata` | GET | Get document metadata (ID, buildNo) |
| `/http.svc/pagecontent` | GET | Fetch page HTML content + TOC |
| `/http.svc/semanticsearch` | POST | Alternative semantic search |
