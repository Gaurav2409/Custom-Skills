---
name: sap-wiki
description: Searches, reads, creates, and edits pages on SAP Confluence Wiki via the REST API. Use when the user wants to interact with wiki content, find documentation, or manage wiki pages.
---

# SAP Wiki Skill

You are a Wiki automation agent. Your job is to search, read, create, and edit pages on SAP's Confluence Wiki by making HTTP requests directly to the Confluence REST API. You MUST follow these instructions precisely and completely.

## Configuration

Before executing any operation, read the configuration file at `skills/sap-wiki/config.yaml` (relative to this file). Copy from `config.example.yaml` if it does not exist. Parse the YAML and extract:

| Key | Required | Description |
|-----|----------|-------------|
| `WIKI_DOMAIN` | No | Wiki server domain. Default: `wiki.one.int.sap` |
| `AUTH_COOKIE_DIR` | No | Directory containing `sap_cookies.txt`. Default: `~/.sap-mcp/cookies/sap-wiki` |
| `DECRYPT_KEY` | No | AES-256-GCM decryption key (min 16 chars) for encrypted cookie files. Must match `ENCRYPT_KEY` in sap-auth-mcp |
| `WIKI_API_TOKEN` | No | Wiki API token (PAT). When set, uses token auth instead of cookie auth |

If a key is empty or not set, treat it as unset and use defaults.

---

## Base URLs

All API calls use these base URLs (where `{domain}` = `WIKI_DOMAIN` or `wiki.one.int.sap`):

| Mode | Base URL |
|------|----------|
| Cookie auth (SAP Wiki) | `https://{domain}/wiki/rest/api` |
| PAT auth (custom domains) | `https://{domain}/rest/api` |

The SAP Wiki (`wiki.one.int.sap`) uses a `/wiki` context path. Custom domains with PAT authentication typically do not.

---

## Authentication

### Method 1: Cookie-based (recommended for SAP Wiki)

Cookie file is `sap_cookies.txt` (plain text, **not** JSON). The full format specification is in [`references/cookies-format.md`](references/cookies-format.md).

**Quick start** — use the helper script [`scripts/load-cookies.mjs`](scripts/load-cookies.mjs) to read the cookie:

```bash
# Plain cookie file
COOKIE=$(node ./scripts/load-cookies.mjs --store-path "$AUTH_COOKIE_DIR")

# Encrypted cookie file
COOKIE=$(node ./scripts/load-cookies.mjs --store-path "$AUTH_COOKIE_DIR" --decrypt-key "$DECRYPT_KEY")

# Then use in requests
curl -s -X GET "https://wiki.one.int.sap/wiki/rest/api/user/current" \
  -H "Content-Type: application/json" \
  -H "Cookie: $COOKIE"
```

**Manual loading** (without helper script):

1. Read `{AUTH_COOKIE_DIR}/sap_cookies.txt`
2. If `DECRYPT_KEY` is **not** set → read as UTF-8 text directly. The content is the Cookie header value: `name1=value1; name2=value2; ...`
3. If `DECRYPT_KEY` is set → read as binary and decrypt:
   - Derive key: `PBKDF2(DECRYPT_KEY, salt="sap-auth-mcp", iterations=100000, keylen=32, digest=sha256)`
   - Parse binary layout: `[IV 12 bytes][Auth Tag 16 bytes][Ciphertext]`
   - Decrypt with AES-256-GCM → plaintext is the Cookie header string
4. Set header: `Cookie: {cookie_string}`

**Expiry**: Cookies expire 24 hours after file mtime. Check file modification time before use.

### Method 2: API Token (PAT)

If `WIKI_API_TOKEN` is set (non-empty), use it instead of cookies:
- Set header: `Authorization: Bearer {WIKI_API_TOKEN}`

### Required Headers for All Requests

```
Content-Type: application/json
Accept: application/json
```

### Additional Headers for All Requests (recommended)

```
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
Cache-Control: no-cache, no-store, must-revalidate
```

For cookie-based auth, also add:
```
Referer: https://{domain}/wiki/
```

### Authentication Error Recovery

When a request returns HTTP 401, 403, 302, 307, or 308, or the response body contains login page content (`"login.action"`, `"accounts.sap.com/saml2/idp/sso"`, `"permissionViolation=true"`), or the response is a small HTML page with a `window.location.assign` JS redirect to SSO, authentication has expired.

**Recovery flow:**

1. Invoke the `sap-authenticate` skill with these parameters:
   - `entry_url`: `https://{domain}/`
   - `store_path`: `{AUTH_COOKIE_DIR}`
2. Wait for authentication to complete
3. Reload cookies from `{store_path}/sap_cookies.txt`
4. Retry the original request

---

## API Reference

### 1. General Search (keyword search)

```
GET {base}/search?cql={encoded_cql}&start={start}&limit={limit}&excerpt=highlight&expand=space.icon&includeArchivedSpaces=false&src=next.ui.search
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `keyword` | string | Yes | Search keyword or phrase |
| `start` | number | No | Pagination offset (default: 0) |
| `limit` | number | No | Max results (default: 20, max: 100) |

**CQL constructed from keyword:**
```
siteSearch ~ "{keyword}" AND type in ("space","user","com.atlassian.confluence.extra.team-calendars:calendar-content-type","attachment","page","com.atlassian.confluence.extra.team-calendars:space-calendars-view-content-type","blogpost")
```

URL-encode the entire CQL string for the `cql` query parameter.

**Response:**
```json
{
  "totalSize": 150,
  "results": [
    {
      "title": "Page Title",
      "url": "/wiki/spaces/SPACE/pages/123456/Page+Title",
      "excerpt": "...matching text excerpt...",
      "type": "page",
      "space": { "name": "Space Name", "key": "SPACE" },
      "_links": { "webui": "/wiki/spaces/SPACE/pages/123456/Page+Title" }
    }
  ]
}
```

**Output formatting:**
- Strip highlight markers: replace `@@@hl@@@(text)@@@endhl@@@` with just `text`
- Prefix relative URLs with `https://{domain}`
- Display as numbered list with title, URL, and excerpt

---

### 2. CQL Search (advanced query)

```
GET {base}/search?cql={encoded_cql}&start={start}&limit={limit}&excerpt=highlight&expand=space.icon&includeArchivedSpaces=false&src=next.ui.search
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cql` | string | Yes | Full CQL query string |
| `start` | number | No | Pagination offset (default: 0) |
| `limit` | number | No | Max results (default: 20, max: 100) |

The `cql` parameter is the raw CQL query provided by the user, URL-encoded.

**Response:** Same structure as General Search.

**CQL errors** (HTTP 400): The response body contains `message` field with syntax error details. Report it clearly and suggest using `cql_examples` for correct syntax.

---

### 3. CQL Examples (syntax reference)

This is a local operation — no HTTP request needed. Return the CQL syntax reference below:

#### Basic Search Examples

| # | CQL Query | Description |
|---|-----------|-------------|
| 1 | `siteSearch ~ "API"` | Search for pages containing "API" |
| 2 | `siteSearch ~ "Business Process"` | Exact phrase search |
| 3 | `siteSearch ~ "SAP" AND siteSearch ~ "Integration"` | Multiple keywords with AND |
| 4 | `siteSearch ~ "documentation" AND type = page` | Search only pages |
| 5 | `siteSearch ~ "announcement" AND type = blogpost` | Search only blog posts |
| 6 | `siteSearch ~ "release" AND lastModified > "2024-12-01" ORDER BY lastModified DESC` | Recent content |
| 7 | `siteSearch ~ "deployment" AND lastModified > "2024-11-01" AND lastModified < "2024-12-31"` | Date range |
| 8 | `siteSearch ~ "configuration" ORDER BY lastModified DESC` | Sort by date |
| 9 | `title ~ "Getting Started"` | Title search |
| 10 | `title ~ "API" OR siteSearch ~ "REST endpoint"` | Combined title and content |

#### Syntax Rules

- **Operators:** `~` (contains), `=` (equals), `>` / `<` (dates), `AND`, `OR`
- **Fields:** `siteSearch` (full-text), `title`, `type` (page/blogpost), `lastModified`
- **Date format:** `"YYYY-MM-DD"` — relative dates like `-30d` are NOT supported
- **Quoting:** Always use double quotes for text values
- **Case:** Field names are case-sensitive

---

### 4. Fetch Page Content (by URL)

```
GET {page_url}
```

Fetches the full HTML of a wiki page and extracts the main content. Supports **chunked reading** for large pages.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | Complete wiki page URL |
| `raw` | boolean | No | Return raw HTML without cleaning (default: false) |
| `chunk` | number | No | Chunk number to return (1-based). Default: 1 |
| `chunk_size` | number | No | Characters per chunk (default: 5000, max: 20000) |

**URL validation:** The URL must contain the configured `{domain}`. Reject URLs from other domains.

**Request headers** (override defaults for this endpoint):
```
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Upgrade-Insecure-Requests: 1
```

**Timeout:** Use `--max-time 90` for curl requests to accommodate large pages that may take 30-60 seconds to load.

**Content extraction (when `raw` = false):**

1. Find `<div id="main-content"` in the HTML
2. Extract content between that div and `<div id="likes-and-labels-container"`
3. Remove `<script>` and `<style>` tags
4. Convert block HTML to newlines: `<br>`, `<div>`, `<p>`, `<h1>`–`<h6>`, `<li>`, `<ul>`, `<ol>`, `<table>`, `<tr>`, `<td>`, `<th>`
5. Strip remaining HTML tags
6. Decode HTML entities: `&lt;`, `&gt;`, `&amp;`, `&quot;`, `&#39;`, `&nbsp;`, `&hellip;`, `&ndash;`, `&mdash;`, `&apos;`
7. Collapse whitespace: multiple spaces → single space, 3+ newlines → 2 newlines
8. Trim

If `<div id="main-content"` is not found, return an error message.

**Chunked output (when content exceeds `chunk_size`):**

After extracting and cleaning the full content, apply chunked delivery:

1. Calculate `total_chars` = length of cleaned content
2. Calculate `total_chunks` = ceil(total_chars / chunk_size)
3. If `total_chunks` > 1 (content is large), slice the content:
   - `start` = (chunk - 1) * chunk_size
   - `end` = min(chunk * chunk_size, total_chars)
   - Return the substring from `start` to `end`
4. If `total_chunks` == 1, return full content as-is

**Output header for chunked responses:**

Always prepend the following metadata block before the content when `total_chunks` > 1:

```
--- Page Content (Chunked) ---
Title: {page_title}
URL: {page_url}
Total characters: {total_chars}
Chunk: {chunk}/{total_chunks}
Characters in this chunk: {end - start}
Range: {start+1}-{end} of {total_chars}
---
To read the next chunk, repeat this request with chunk={chunk+1}.
To read a specific section, adjust the chunk number (1 to {total_chunks}).
---

{chunk_content}
```

When `total_chunks` == 1 (short page), output content directly without the metadata header.

**Implementation notes:**
- The curl request fetches the entire page once. Chunking happens locally after content extraction.
- For very large pages, save the cleaned content to a temp file and use `cut -c` or similar to extract the chunk range, avoiding loading the full content into a shell variable.
- If the user asks to "read the whole page" or "get all content", iterate through all chunks automatically.

---

### 5. Create Page

```
POST {base}/content?expand=space,version
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `spaceKey` | string | Yes | Confluence space key (e.g., `TEAM`) |
| `title` | string | Yes | Page title |
| `body` | string | Yes | Page body in Confluence storage format (XHTML) |
| `parentId` | string | No | Parent page ID (creates at space root if omitted) |
| `status` | string | No | `"current"` (default) = publish immediately; `"draft"` = create as personal draft (only visible to creator until published) |

**Request Body:**
```json
{
  "type": "page",
  "title": "{title}",
  "space": { "key": "{spaceKey}" },
  "status": "{status}",
  "body": {
    "storage": {
      "value": "{body}",
      "representation": "storage"
    }
  },
  "ancestors": [{ "id": "{parentId}" }]
}
```

Omit `ancestors` if `parentId` is not provided. Omit `status` (or set to `"current"`) for immediate publishing.

**Response:** Returns page object with `id`, `title`, `version.number`, `_links.webui`, `_links.edit`.

**Output:**
```json
{
  "success": true,
  "id": "123456",
  "title": "Page Title",
  "version": 1,
  "status": "current",
  "url": "https://{domain}/wiki/spaces/SPACE/pages/123456/Page+Title"
}
```

**Output for drafts** (when `status` = `"draft"`):
```json
{
  "success": true,
  "id": "123456",
  "title": "Page Title",
  "version": 1,
  "status": "draft",
  "url": "https://{domain}/wiki/spaces/SPACE/pages/123456/Page+Title",
  "editUrl": "https://{domain}/wiki/pages/resumedraft.action?draftId=123456&draftShareId=..."
}
```

The `editUrl` is extracted from `_links.edit` in the response. Share it with reviewers so they can edit and publish the draft from the Confluence UI.

**Error codes:**
- 404: Space not found
- 409: Page with this title already exists in the space

---

### 6. Get Page for Edit

```
GET {base}/content/{pageId}?expand=body.storage,version,space
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pageId` | string | Yes | The wiki page ID |

**Response:**
```json
{
  "id": "123456",
  "title": "Page Title",
  "version": { "number": 5 },
  "body": {
    "storage": {
      "value": "<p>Page content in XHTML...</p>"
    }
  },
  "space": { "key": "SPACE" },
  "_links": { "webui": "/wiki/spaces/SPACE/pages/123456/Page+Title", "base": "https://wiki.one.int.sap" }
}
```

**Output:** Return all fields needed for editing:
```json
{
  "id": "123456",
  "title": "Page Title",
  "version": 5,
  "body": "<p>Page content in XHTML...</p>",
  "spaceKey": "SPACE",
  "url": "https://{domain}/wiki/spaces/SPACE/pages/123456/Page+Title"
}
```

**Error codes:**
- 404: Page not found

---

### 7. Update Page

```
PUT {base}/content/{pageId}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pageId` | string | Yes | The wiki page ID |
| `title` | string | Yes | Page title (use current unless changing) |
| `body` | string | Yes | Updated page body in Confluence storage format (XHTML) |
| `version` | number | Yes | Current version number (from Get Page for Edit). The skill increments by 1 |
| `message` | string | No | Version comment describing the change |

**Request Body:**
```json
{
  "type": "page",
  "title": "{title}",
  "body": {
    "storage": {
      "value": "{body}",
      "representation": "storage"
    }
  },
  "version": {
    "number": {version + 1},
    "message": "{message}"
  }
}
```

Omit `version.message` if `message` is not provided.

**Response:** Returns updated page object with `id`, `title`, `version.number`, `_links.webui`.

**Output:**
```json
{
  "success": true,
  "id": "123456",
  "title": "Page Title",
  "version": 6,
  "url": "https://{domain}/wiki/spaces/SPACE/pages/123456/Page+Title"
}
```

**Error codes:**
- 404: Page not found
- 409: Version conflict — page was modified by someone else. Fetch latest version and retry.

---

## Edit Workflow

The standard page editing workflow is:

1. **Get current content**: Call "Get Page for Edit" with the page ID → receive `body`, `version`, `title`
2. **Modify content**: Edit the body XHTML as needed
3. **Save changes**: Call "Update Page" with the page ID, modified body, original `version` number (skill auto-increments), and optionally a version `message`

If a version conflict (409) occurs, repeat from step 1.

---

## URL Formats

The skill supports these standard Confluence URL formats:
- `https://{domain}/wiki/pages/viewpage.action?pageId=123456`
- `https://{domain}/wiki/spaces/SPACE/pages/123456/Page+Title`
- `https://{domain}/wiki/display/SPACE/Page+Title`

When constructing URLs from API responses:
- If `_links.webui` is present: `{_links.base}{_links.webui}`
- Fallback: `https://{domain}/wiki/spaces/{spaceKey}/pages/{id}`

---

## Error Handling

### HTTP Error Classification

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request (CQL syntax error) | Report error message to user |
| 401 | Unauthorized | Trigger auth recovery |
| 403 | Forbidden | Report access denied |
| 404 | Not found | Report page/space not found |
| 409 | Conflict | Report version conflict or duplicate page |
| 302/307/308 | Redirect to login | Trigger auth recovery |

### Auth Redirect Detection

In addition to HTTP status codes, detect these auth redirect patterns:
- Final response URL contains `login.action` or `permissionViolation=true`
- Final response URL contains `accounts.sap.com/saml2/idp/sso`
- Response body is small HTML (< 5KB) with `window.location.assign` pointing to SSO

### Network Errors

If the request fails with `ECONNREFUSED` or `ETIMEDOUT`, report:
> "Cannot connect to Wiki. Check network connectivity and VPN."

---

## Important Constraints

1. **Cookie files are per-app.** The `AUTH_COOKIE_DIR` is unique to this skill. Never reuse paths with other app skills.
2. **24-hour cookie validity.** Cookies expire when `sap_cookies.txt` mtime is older than 24 hours.
3. **Encryption is optional but symmetric.** If `DECRYPT_KEY` is set, both writing (sap-authenticate skill) and reading (this skill) must use the same key.
4. **SAP network required.** Operations will fail if not connected to SAP internal network (VPN or enrolled device).
5. **Version control.** Always fetch the current version before updating a page. Never guess version numbers.
6. **Storage format.** Page body must be valid Confluence storage format (XHTML). For simple text, wrap in `<p>` tags.
7. **URL domain validation.** Only accept URLs matching the configured `WIKI_DOMAIN`. Reject URLs from other domains.
8. **Highlight markers.** Strip `@@@hl@@@` and `@@@endhl@@@` markers from search result titles and excerpts before displaying.
9. **Playwright is reserved for `sap-authentication` only.** This skill MUST use the Confluence REST API exclusively. Do NOT fall back to `mcp__playwright-*` tools to scrape wiki pages, click buttons, or work around API errors. If the REST call fails, fix the request or trigger re-authentication via `sap-authentication` — never substitute browser automation.
