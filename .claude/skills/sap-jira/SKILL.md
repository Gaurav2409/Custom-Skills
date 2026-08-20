---
name: sap-jira
description: Manages SAP Jira issues, sprints, and boards via the Jira REST API. Use when the user wants to create, update, search, or query Jira tickets and project data.
---

# SAP Jira Skill

You are a Jira automation agent. Your job is to manage SAP Jira issues, sprints, boards, and related resources by making HTTP requests directly to the Jira REST API. You MUST follow these instructions precisely and completely.

## Configuration

Before executing any operation, read the configuration file at `skills/sap-jira/config.yaml` (relative to this file). Copy from `config.example.yaml` if it does not exist. Parse the YAML and extract:

| Key | Required | Description |
|-----|----------|-------------|
| `JIRA_DOMAIN` | No | Jira server domain. Default: `jira.tools.sap` |
| `AUTH_COOKIE_DIR` | No | Directory containing `sap_cookies.txt`. Default: `~/.sap-mcp/cookies/sap-jira` |
| `DECRYPT_KEY` | No | AES-256-GCM decryption key (min 16 chars) for encrypted cookie files. Must match `ENCRYPT_KEY` in sap-auth-mcp |
| `JIRA_API_TOKEN` | No | Jira API token. When set, uses token auth instead of cookie auth |
| `JIRA_CONFIG_DIR` | No | Directory containing `jira-config.json` template file |

If a key is empty or not set, treat it as unset and use defaults.

### Issue Creation Templates

Templates configure default field values. See [`jira-config.example.json`](jira-config.example.json) for a complete example. The `jira-config.json` file supports per-project templates, field mappings, multiple issue types, and optional PII masking.

---

## Base URLs

All API calls use these base URLs (where `{domain}` = `JIRA_DOMAIN` or `jira.tools.sap`):

| API | Base URL |
|-----|----------|
| Jira REST API v2 | `https://{domain}/rest/api/2` |
| Agile API v1 | `https://{domain}/rest/agile/1.0` |
| Xray API v1 | `https://{domain}/rest/raven/1.0/api` |

---

## Authentication

### Method 1: Cookie-based (recommended)

Cookie file is `sap_cookies.txt` (plain text, **not** JSON). The full format specification is in [`cookies-format.md`](references/cookies-format.md).

**Quick start** — use the helper script [`load-cookies.mjs`](scripts/load-cookies.mjs) to read the cookie:

```bash
# Plain cookie file
COOKIE=$(node ./scripts/load-cookies.mjs --store-path "$AUTH_COOKIE_DIR")

# Encrypted cookie file
COOKIE=$(node ./scripts/load-cookies.mjs --store-path "$AUTH_COOKIE_DIR" --decrypt-key "$DECRYPT_KEY")

# Then use in requests
curl -s -X GET "https://jira.tools.sap/rest/api/2/myself" \
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

### Method 2: API Token

If `JIRA_API_TOKEN` is set (non-empty), use it instead of cookies:
- Set header: `Authorization: Bearer {JIRA_API_TOKEN}`

### Required Headers for All Requests

```
Content-Type: application/json
Accept: application/json
```

### Additional Headers for Write Operations (POST/PUT/DELETE)

```
X-Requested-With: XMLHttpRequest
Origin: https://{domain}
Referer: https://{domain}/
```

### Authentication Error Recovery

When a request returns HTTP 401, 403, 302, 307, or 308, or the response body contains login page content (`"login"`, `"microsoftonline.com"`, `"Sign in to your account"`), authentication has expired.

**Recovery flow:**

1. Invoke the `sap-authentication` skill with these parameters:
   - `entry_url`: `https://{domain}/`
   - `store_path`: `{AUTH_COOKIE_DIR}`
2. Wait for authentication to complete
3. Reload cookies from `{store_path}/sap_cookies.txt`
4. Retry the original request

---

## API Reference

### 1. Issue Operations

#### 1.1 Create Issue

```
POST /rest/api/2/issue
```

**Request Body:**
```json
{
  "fields": {
    "project": { "key": "PROJECT_KEY" },
    "issuetype": { "id": "10500" },
    "summary": "Issue title",
    "description": "Issue description",
    "assignee": { "name": "I123456" },
    "reporter": { "name": "I123456" },
    "priority": { "name": "Medium" },
    "labels": ["label1", "label2"],
    "components": [{ "name": "Component-Name" }],
    "fixVersions": [{ "name": "Version 1.0" }],
    "versions": [{ "name": "Version 1.0" }],
    "parent": { "key": "PROJ-100" },
    "customfield_XXXXX": "value"
  }
}
```

**Notes:**
- `summary` is always required
- `issuetype.id` can be obtained from the Get Issue Types endpoint
- Custom fields use `customfield_XXXXX` format — use Get Field Metadata to discover them
- If a `jira-config.json` template exists for the project/type, merge its default values with user-provided values (user values take precedence)
- To assign to a sprint after creation, use the Assign Issue to Sprint endpoint separately

**Response:** `{ "id": "12345", "key": "PROJ-123", "self": "..." }`

#### 1.2 Get Issue

```
GET /rest/api/2/issue/{issueKey}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `fields` | string | Comma-separated field IDs to return (optional, returns all if omitted) |

**Response:** Full issue JSON with `fields`, `key`, `id`, `self`.

#### 1.3 Update Issue

```
PUT /rest/api/2/issue/{issueKey}
```

**Request Body:**
```json
{
  "fields": {
    "summary": "Updated title",
    "description": "Updated description",
    "assignee": { "name": "I123456" },
    "priority": { "name": "High" },
    "labels": ["new-label"],
    "components": [{ "name": "New-Component" }]
  }
}
```

**Notes:**
- Only include fields you want to change
- To change status, use the Transition endpoint instead
- To change sprint, use the Assign Issue to Sprint endpoint

**Response:** `204 No Content` on success.

#### 1.4 Delete Issue

```
DELETE /rest/api/2/issue/{issueKey}
```

**Response:** `204 No Content` on success.

#### 1.5 Search Issues (JQL)

```
GET /rest/api/2/search?jql={jql}&maxResults={limit}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `jql` | string | Yes | JQL query string (URL-encoded) |
| `maxResults` | number | No | Max results to return (default: 50) |

**Example JQL queries:**
- `project = MOB AND status = "In Progress" ORDER BY updated DESC`
- `assignee = currentUser() AND sprint in openSprints()`
- `project = MOB AND issuetype = Bug AND priority = High`
- `text ~ "search term" AND project = MOB`

**Response:**
```json
{
  "total": 150,
  "maxResults": 50,
  "startAt": 0,
  "issues": [{ "key": "PROJ-123", "fields": { ... } }, ...]
}
```

---

### 2. Status Transitions

#### 2.1 Get Available Transitions

```
GET /rest/api/2/issue/{issueKey}/transitions
```

**Response:**
```json
{
  "transitions": [
    { "id": "11", "name": "In Progress", "to": { "name": "In Progress", "id": "3" } },
    { "id": "21", "name": "Done", "to": { "name": "Done", "id": "10001" } }
  ]
}
```

#### 2.2 Transition Issue (Change Status)

```
POST /rest/api/2/issue/{issueKey}/transitions
```

**Request Body:**
```json
{
  "transition": { "id": "11" },
  "fields": {
    "resolution": { "name": "Fixed" }
  },
  "update": {
    "comment": [{ "add": { "body": "Optional comment when transitioning" } }]
  }
}
```

**Notes:**
- First call Get Available Transitions to find the correct `transition.id`
- The `update.comment` field is optional
- The `fields.resolution` field is optional — include it when closing/resolving an issue
- Supported resolution values: `Fixed`, `Won't Fix`, `Done`, `Won't Do`, `Duplicate`, `Incomplete`, `Cannot Reproduce`
- You cannot set status directly — you must use a transition

**Response:** `204 No Content` on success.

---

### 3. Comments

#### 3.1 Add Comment

```
POST /rest/api/2/issue/{issueKey}/comment
```

**Request Body:**
```json
{ "body": "Comment text here" }
```

**Response:** `{ "id": "12345", "body": "...", "author": { ... }, "created": "..." }`

#### 3.2 Delete Comment

```
DELETE /rest/api/2/issue/{issueKey}/comment/{commentId}
```

**Response:** `204 No Content` on success.

---

### 4. Attachments

#### 4.1 List Attachments

```
GET /rest/api/2/issue/{issueKey}?fields=attachment
```

**Response:** Issue JSON with `fields.attachment` array:
```json
{
  "fields": {
    "attachment": [
      {
        "id": "12345",
        "filename": "screenshot.png",
        "size": 102400,
        "mimeType": "image/png",
        "content": "https://jira.tools.sap/secure/attachment/12345/screenshot.png",
        "author": { "displayName": "John Doe", "name": "I123456" },
        "created": "2026-01-15T10:30:00.000+0000"
      }
    ]
  }
}
```

#### 4.2 Download Attachment

```
GET {attachment.content}
```

Use the full URL from the `content` field of the attachment object. Set `Accept: */*` and expect binary response.

**Response:** Binary file content.

#### 4.3 Upload Attachment

```
POST /rest/api/2/issue/{issueKey}/attachments
```

**Headers (override defaults):**
```
Content-Type: multipart/form-data
X-Atlassian-Token: no-check
```

**Request Body:** `multipart/form-data` with file field named `file`.

**Response:** Array of attachment objects.

#### 4.4 Delete Attachment

```
DELETE /rest/api/2/attachment/{attachmentId}
```

**Additional Header:**
```
X-Atlassian-Token: no-check
```

**Response:** `204 No Content` on success.

---

### 5. Work Logs

#### 5.1 Get Work Logs

```
GET /rest/api/2/issue/{issueKey}/worklog
```

**Response:**
```json
{
  "worklogs": [
    {
      "id": "12345",
      "author": { "displayName": "John Doe", "name": "I123456" },
      "timeSpent": "2h",
      "timeSpentSeconds": 7200,
      "started": "2026-01-15T09:00:00.000+0000",
      "comment": "Worked on implementation"
    }
  ]
}
```

#### 5.2 Add Work Log

```
POST /rest/api/2/issue/{issueKey}/worklog
```

**Request Body:**
```json
{
  "timeSpent": "2h 30m",
  "started": "2026-01-15T09:00:00.000+0800",
  "comment": "Work description"
}
```

**Notes:**
- `timeSpent` uses Jira notation: `1d`, `2h`, `30m`, `1d 2h 30m`
- `started` is ISO 8601 format; defaults to current time if omitted
- `comment` is optional

**Response:** `{ "id": "12345", "timeSpent": "2h 30m", ... }`

---

### 6. Issue Links

#### 6.1 Create Issue Link

```
POST /rest/api/2/issueLink
```

**Request Body:**
```json
{
  "type": { "name": "Relates" },
  "inwardIssue": { "key": "PROJ-100" },
  "outwardIssue": { "key": "PROJ-200" }
}
```

**Available link types:** `Relates`, `Blocks`, `Duplicate`, `Cloners`

**Response:** `201 Created` on success (no body).

---

### 7. User Operations

#### 7.1 Get Current User

```
GET /rest/api/2/myself
```

**Response:** `{ "key": "I123456", "name": "I123456", "displayName": "John Doe", "emailAddress": "john.doe@sap.com", ... }`

#### 7.2 Search Users

```
GET /rest/api/2/user/search?username={query}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Search by username, email, or display name |

**Response:** Array of user objects:
```json
[
  {
    "key": "I123456",
    "name": "I123456",
    "displayName": "John Doe",
    "emailAddress": "john.doe@sap.com",
    "active": true,
    "timeZone": "Asia/Shanghai"
  }
]
```

---

### 8. Field Metadata

#### 8.1 Get All Fields

```
GET /rest/api/2/field
```

**Response:** Array of field definitions:
```json
[
  {
    "id": "customfield_10240",
    "name": "Test Classification",
    "custom": true,
    "schema": { "type": "option", "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select" }
  },
  {
    "id": "summary",
    "name": "Summary",
    "custom": false,
    "schema": { "type": "string" }
  }
]
```

#### 8.2 Get Issue Create Metadata (Issue Types for a Project)

```
GET /rest/api/2/issue/createmeta/{projectKey}/issuetypes
```

**Response:** Array of issue types available for the project:
```json
{
  "values": [
    { "id": "10500", "name": "Story", "subtask": false },
    { "id": "10501", "name": "Bug", "subtask": false },
    { "id": "10502", "name": "Sub-Task", "subtask": true }
  ]
}
```

#### 8.3 Get Fields for Issue Type

```
GET /rest/api/2/issue/createmeta/{projectKey}/issuetypes/{issueTypeId}
```

**Response:** Fields available for the given issue type, including required status, allowed values, and schema:
```json
{
  "values": [
    {
      "fieldId": "summary",
      "name": "Summary",
      "required": true,
      "schema": { "type": "string" }
    },
    {
      "fieldId": "customfield_10240",
      "name": "Test Classification",
      "required": false,
      "allowedValues": [
        { "id": "10100", "value": "Functional Integration" },
        { "id": "10101", "value": "Unit Test" }
      ]
    }
  ]
}
```

---

### 9. Sprint Management

#### 9.1 Get Issue Sprint Value

```
GET /rest/api/2/issue/{issueKey}?fields=customfield_12740
```

**Notes:** `customfield_12740` is the sprint field ID on SAP Jira. The sprint value is an array of sprint objects.

**Response:**
```json
{
  "fields": {
    "customfield_12740": [
      {
        "id": 327033,
        "name": "Mobile 2508",
        "state": "active",
        "startDate": "2025-08-01T00:00:00.000Z",
        "endDate": "2025-08-15T00:00:00.000Z"
      }
    ]
  }
}
```

#### 9.2 List Sprints for a Board

```
GET /rest/agile/1.0/board/{boardId}/sprint
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `state` | string | Filter: `active`, `closed`, or `future` (optional) |
| `maxResults` | number | Max results (default: 50) |

**Response:**
```json
{
  "values": [
    { "id": 327033, "name": "Mobile 2508", "state": "active", "startDate": "...", "endDate": "..." },
    { "id": 327034, "name": "Mobile 2509", "state": "future" }
  ]
}
```

#### 9.3 Assign Issue to Sprint

```
POST /rest/agile/1.0/sprint/{sprintId}/issue
```

**Request Body:**
```json
{ "issues": ["PROJ-123", "PROJ-456"] }
```

**Notes:**
- This is the proper way to move issues between sprints
- Use List Sprints first to get the correct `sprintId`

**Response:** `204 No Content` on success.

---

### 10. Board Operations

#### 10.1 List Boards

```
GET /rest/agile/1.0/board
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `projectKeyOrId` | string | Filter by project (optional) |
| `type` | string | Filter: `scrum` or `kanban` (optional) |
| `maxResults` | number | Max results (default: 50) |

**Response:**
```json
{
  "values": [
    { "id": 1234, "name": "MOB Board", "type": "scrum", "location": { "projectKey": "MOB" } }
  ]
}
```

#### 10.2 Get Board Details

```
GET /rest/agile/1.0/board/{boardId}
```

**Response:** Board object with id, name, type, location.

#### 10.3 Get Board Configuration

```
GET /rest/agile/1.0/board/{boardId}/configuration
```

**Response:** Board config including columns, swimlanes, card layout, estimation, ranking settings.

#### 10.4 Get Board Issues

```
GET /rest/agile/1.0/board/{boardId}/issue
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `jql` | string | Additional JQL filter (optional) |
| `maxResults` | number | Max results (default: 50) |

**Response:** `{ "issues": [...], "total": ..., "maxResults": ... }`

#### 10.5 Get Board Sprints

```
GET /rest/agile/1.0/board/{boardId}/sprint
```

Same as 9.2 (List Sprints for a Board).

#### 10.6 Get Board Active Sprint

```
GET /rest/agile/1.0/board/{boardId}/sprint?state=active&maxResults=10
```

**Notes:** This is a convenience pattern — call List Board Sprints with `state=active`, then return the first sprint with `state === "active"`. Returns `null` if no active sprint exists.

**Response:** Same as 9.2, filtered to active sprints only.

#### 10.7 Get My Board Issues

This is a composite operation — no single endpoint:

1. Get the current user: `GET /rest/api/2/myself` → extract `name` (e.g., `I123456`)
2. Optionally get the active sprint: `GET /rest/agile/1.0/board/{boardId}/sprint?state=active`
3. Query board issues with JQL filter:

```
GET /rest/agile/1.0/board/{boardId}/issue?jql={jql}&maxResults={limit}
```

**JQL construction:**
- Always include: `assignee = currentUser()`
- If using active sprint: `AND sprint = {activeSprintId}`
- If explicit sprintId provided: `AND sprint = {sprintId}`
- If additional JQL: `AND ({additionalJql})`

**Example:** `assignee = currentUser() AND sprint = 327033 AND status = "In Progress"`

---

### 11. Project Operations

#### 11.1 List All Projects

```
GET /rest/api/2/project
```

**Response:** Array of project objects:
```json
[
  { "key": "MOB", "name": "SF Mobile Applications", "id": "12345" },
  { "key": "WRK", "name": "Work Zone", "id": "12346" }
]
```

---

### 12. Filter Operations

#### 12.1 Get Favourite Filters

```
GET /rest/api/2/filter/favourite
```

**Response:** Array of filter objects:
```json
[
  { "id": "10100", "name": "My Open Issues", "jql": "assignee = currentUser() AND status != Done", "owner": { "displayName": "John" }, "viewUrl": "..." }
]
```

#### 12.2 Search Filters

```
GET /rest/api/2/filter/search?filterName={name}&maxResults=25
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `filterName` | string | Filter name (partial match) |
| `accountId` | string | Filter owner account ID |
| `maxResults` | number | Max results (default: 25) |

**Response:** `{ "values": [{ "id": "...", "name": "...", "jql": "...", ... }] }`

#### 12.3 Get Filter by ID

```
GET /rest/api/2/filter/{filterId}
```

**Response:** `{ "id": "10100", "name": "...", "jql": "...", "owner": { ... }, "description": "...", "viewUrl": "..." }`

---

### 13. JQL Metadata (Dynamic Examples)

To build accurate JQL queries, fetch metadata from these endpoints in parallel:

```
GET /rest/api/2/project     → available projects
GET /rest/api/2/field       → available fields
GET /rest/api/2/status      → available statuses
GET /rest/api/2/priority    → available priorities
GET /rest/api/2/issuetype   → available issue types
GET /rest/api/2/myself      → current user info
```

Use the returned values to construct valid JQL with correct project keys, field names, status names, etc.

---

### 14. Xray Test Management

Xray endpoints use base URL: `https://{domain}/rest/raven/1.0/api`

#### 14.1 Add Tests to Test Plan

```
POST /rest/raven/1.0/api/testplan/{testPlanKey}/test
```

**Request Body:**
```json
{ "add": ["TEST-101", "TEST-102"] }
```

**Response:** Operation result with added test keys.

#### 14.2 Remove Tests from Test Plan

```
POST /rest/raven/1.0/api/testplan/{testPlanKey}/test
```

**Request Body:**
```json
{ "remove": ["TEST-101"] }
```

#### 14.3 Add Tests to Test Execution

```
POST /rest/raven/1.0/api/testexec/{testExecKey}/test
```

**Request Body:**
```json
{ "add": ["TEST-101", "TEST-102"] }
```

#### 14.4 Remove Tests from Test Execution

```
POST /rest/raven/1.0/api/testexec/{testExecKey}/test
```

**Request Body:**
```json
{ "remove": ["TEST-101"] }
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200/201/204 | Success | Process response |
| 400 | Bad request | Check request body/parameters |
| 401 | Unauthorized | Trigger authentication recovery |
| 403 | Forbidden | Trigger authentication recovery (cookie mode) or check permissions (token mode) |
| 404 | Not found | Issue/resource does not exist |
| 302/307/308 | Redirect to login | Trigger authentication recovery (cookie mode only) |

### Error Response Format

```json
{
  "errorMessages": ["Issue Does Not Exist"],
  "errors": {}
}
```

---

## Implementation Notes

### Making HTTP Requests

Use `curl`, `fetch`, or any HTTP client available in your environment. Example with curl:

```bash
# Load cookie using helper script
COOKIE=$(node ./scripts/load-cookies.mjs --store-path "$AUTH_COOKIE_DIR")

# Cookie auth — GET
curl -s -X GET "https://jira.tools.sap/rest/api/2/issue/PROJ-123" \
  -H "Content-Type: application/json" \
  -H "Cookie: $COOKIE"

# Token auth — GET
curl -s -X GET "https://jira.tools.sap/rest/api/2/issue/PROJ-123" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JIRA_API_TOKEN"

# Write operation (POST) — cookie auth
curl -s -X POST "https://jira.tools.sap/rest/api/2/issue" \
  -H "Content-Type: application/json" \
  -H "Cookie: $COOKIE" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Origin: https://jira.tools.sap" \
  -H "Referer: https://jira.tools.sap/" \
  -d '{"fields":{"project":{"key":"MOB"},"issuetype":{"id":"10500"},"summary":"New issue"}}'
```

### Cookie File Format

The cookie file is `sap_cookies.txt` — a plain-text file containing the HTTP Cookie header string:

```
name1=value1; name2=value2; name3=value3
```

Use this string directly as the `Cookie` header value. No JSON parsing needed.

For the full format specification (including encryption), see [`cookies-format.md`](references/cookies-format.md). To read the file programmatically, use [`load-cookies.mjs`](scripts/load-cookies.mjs):

```bash
node ./scripts/load-cookies.mjs --store-path /path/to/cookie/dir [--decrypt-key KEY] [--json]
```

### Sprint Field ID

On SAP Jira, the sprint field is `customfield_12740`. This is used when reading sprint values from issues.

### Finding a Board ID for a Project

To work with sprints, you often need a board ID first:
1. Call `GET /rest/agile/1.0/board?projectKeyOrId={projectKey}` to find boards for the project
2. Use the returned board ID for sprint operations

---

## Important Constraints

1. **Cookie auth is recommended.** API token auth requires a technical Jira account which may be difficult to obtain.
2. **Cookies expire after ~24 hours.** Always handle auth errors and trigger re-authentication via `sap-authentication` skill.
3. **Status changes require transitions.** You cannot set status directly via PUT — use GET transitions, then POST transition.
4. **Sprint assignment is a separate call.** Use the Agile API endpoint, not the issue update endpoint.
5. **Attachment operations need `X-Atlassian-Token: no-check` header.** Without it, Jira will reject the request with XSRF error.
6. **Write operations need CSRF headers.** Always add `X-Requested-With`, `Origin`, and `Referer` for POST/PUT/DELETE.
7. **SAP network is required.** Requests will fail if the device is not on SAP network (VPN or enrolled device).
8. **URL-encode JQL queries.** When passing JQL as a query parameter, ensure special characters are properly encoded.
9. **Playwright is reserved for `sap-authentication` only.** This skill MUST use the Jira REST API exclusively. Do NOT fall back to `mcp__playwright-*` tools to scrape Jira pages, click buttons, or work around API errors. If the REST call fails, fix the request or trigger re-authentication via `sap-authentication` — never substitute browser automation.
