---
name: sap-codemeta
description: Search and browse the SAP SuccessFactors CodeMeta API catalog. Use when the user asks about SAP SF APIs, wants to find API documentation, search for endpoints, or view OpenAPI specs from codemeta.sapsf.com.
---

# SAP CodeMeta API Catalog Skill

You are an API catalog assistant. Your job is to help users search, browse, and retrieve information from the SAP SuccessFactors CodeMeta API catalog (codemeta.sapsf.com) — a registry of 1800+ internal APIs across 16 modules.

## Configuration

Before executing any operation, read the configuration file at `skills/sap-codemeta/config.yaml` (relative to the project root). If it does not exist, fall back to `skills/sap-codemeta/config.example.yaml`. Parse the YAML and extract:

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `AUTH_COOKIE_DIR` | No | `~/.sap-auth/codemeta` | Directory containing `sap_cookies.txt` |
| `DECRYPT_KEY` | No | _(empty)_ | AES-256-GCM key for decrypting encrypted cookie files. Must match `ENCRYPT_KEY` in sap-authentication. Leave empty if cookies are plain text. |

---

## Network Prerequisite

Before making any API call or authentication attempt, verify SAP internal network connectivity:

```bash
curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "https://codemeta.sapsf.com"
```

- **If the command returns a status code (200, 301, 302, etc.)**: Network is reachable, proceed normally.
- **If it fails (exit code non-zero, e.g., 6=DNS failure, 7=connection refused, 28=timeout, 35=SSL error)**: The user is NOT on SAP internal network.

**When network is unreachable, stop immediately and tell the user:**

> "Cannot reach codemeta.sapsf.com — you are not connected to the SAP internal network. Please connect to SAP VPN or ensure your device is on the corporate network, then try again."

Do NOT proceed with authentication or API calls if this check fails.

---

## Authentication

All CodeMeta API calls require a `DHUBTOKEN` cookie (HS256 JWT, ~20 day expiry).

**Important**: CodeMeta uses single-active-token semantics — each new login invalidates all previous tokens. If the user also uses CodeMeta in a browser, their browser login will invalidate the CLI token (and vice versa).

### Cookie Storage

- **File**: `{AUTH_COOKIE_DIR}/sap_cookies.txt`
- **Format**: `DHUBTOKEN=<jwt_value>` (single line, plain text)

### Reading the Token

Before every API call, load the stored cookie via the helper script (handles both plain-text and encrypted files):

```bash
COOKIE=$(node skills/sap-codemeta/scripts/load-cookies.mjs --store-path {AUTH_COOKIE_DIR} ${DECRYPT_KEY:+--decrypt-key "$DECRYPT_KEY"} --max-age 480)
```

- `--max-age 480` (20 days) reflects the DHUBTOKEN's ~20-day expiry; downstream requests still rely on the server returning 401 to trigger re-auth.
- If `DECRYPT_KEY` is empty, omit the `--decrypt-key` flag.
- For plain-text inspection (debug only), `cat {AUTH_COOKIE_DIR}/sap_cookies.txt` works when the file is unencrypted.

If the file does not exist, the script exits non-zero, or the API returns HTTP 401, perform **Token Acquisition** below.

### Token Acquisition (Playwright — Automated)

CodeMeta authenticates via SAP IAS with client certificate auto-authentication. No user interaction is required — the flow completes automatically.

**Steps:**

1. Navigate to the OAuth entry point:
   ```
   Tool: browser_navigate (playwright-headless)
   URL: https://codemeta.sapsf.com/api/login/github
   ```

2. Wait for the redirect chain to complete (client cert auto-authenticates with SAP IAS):
   ```
   Tool: browser_wait_for
   time: 10
   ```

3. Verify the page has returned to CodeMeta (not stuck on IAS):
   ```
   Tool: browser_snapshot
   ```
   The URL should contain `codemeta.sapsf.com` and NOT contain `accounts` or `authorize`.
   If still on IAS after 10 seconds, wait another 5 seconds and check again.

4. Extract cookies:
   ```
   Tool: browser_cookie_list
   domain: codemeta.sapsf.com
   ```

5. Find the cookie named `DHUBTOKEN` in the response. Extract its `value` field.

6. Save the token — **use the exact value from step 5, never re-type it**:
   ```bash
   mkdir -p {AUTH_COOKIE_DIR}
   ```
   Then write the file using the Write tool with content: `DHUBTOKEN=<exact_value_from_step_5>`
   
   Do NOT manually type or reconstruct the token string. Copy it programmatically.

7. Verify the token works — call the userInfo endpoint immediately after saving:
   ```bash
   COOKIE=$(cat {AUTH_COOKIE_DIR}/sap_cookies.txt)
   curl -s 'https://codemeta.sapsf.com/admin/user/userInfo' \
     -H 'accept: application/json, text/plain, */*' \
     -H 'accept-language: en-US,en;q=0.9' \
     -b "$COOKIE" \
     -H 'dnt: 1' \
     -H 'priority: u=1, i' \
     -H 'referer: https://codemeta.sapsf.com/home' \
     -H 'sec-ch-ua: "Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"' \
     -H 'sec-ch-ua-mobile: ?0' \
     -H 'sec-ch-ua-platform: "macOS"' \
     -H 'sec-fetch-dest: empty' \
     -H 'sec-fetch-mode: cors' \
     -H 'sec-fetch-site: same-origin' \
     -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0'
   ```
   - If the response `code` is 200 and `data.name` is NOT "Guest", the token is valid.
   - If `data.name` is "Guest" or the response is 401, the token is invalid — re-run the login flow (do NOT close the browser yet, navigate to `/api/login/github` again).

8. Close the browser:
   ```
   Tool: browser_close (playwright-headless)
   ```

### Auth Failure Recovery

CodeMeta does **not** return a clean 401 when the cookie is missing or expired. Instead it returns **HTTP 200** with a guest user payload. Detect auth failure by checking BOTH conditions on every API response:

| Signal | Auth state |
|------|------|
| HTTP 401 | Token rejected — re-auth |
| HTTP 200 **and** response `data.name == "Guest"` (on userInfo) | No valid session — re-auth |
| HTTP 200 **and** response indicates guest/empty data on other endpoints | Cookie invalid — re-auth |

When any of the above triggers:

1. Run the **Token Acquisition** flow above
2. Retry the original request with the new token
3. If the failure persists after retry, report the error to the user

### Auth Failure

If the Playwright login flow does not produce a `DHUBTOKEN` cookie (e.g., client cert not available, network issue):

> "CodeMeta authentication failed — no DHUBTOKEN cookie received after login. Possible causes:
> - Client certificate not available (check system keychain)
> - Not connected to SAP network
> - SAP IAS session issue
>
> Try opening https://codemeta.sapsf.com in your browser to verify access."

---

## Making API Calls

All API calls **must** include browser-like headers. The server validates `sec-fetch-*` headers and rejects bare curl requests.

**IMPORTANT**: Never manually re-type tokens. Always read them from the cookie file or Playwright output programmatically.

**GET requests:**
```bash
COOKIE=$(cat {AUTH_COOKIE_DIR}/sap_cookies.txt)
curl -s 'https://codemeta.sapsf.com{endpoint}' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'referer: https://codemeta.sapsf.com/' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0' \
  -b "originalPage=/; $COOKIE"
```

**POST requests:**
```bash
COOKIE=$(cat {AUTH_COOKIE_DIR}/sap_cookies.txt)
curl -s -X POST 'https://codemeta.sapsf.com{endpoint}' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'content-type: application/json' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'referer: https://codemeta.sapsf.com/' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0' \
  -b "originalPage=/; $COOKIE" \
  -d '{json_body}'
```

Check the HTTP status. **CodeMeta returns 200 even when unauthenticated** — also verify the response is not a guest-user payload before treating it as success. If 401, or the body indicates a guest session, run **Auth Failure Recovery**.

---

## API Reference

### 1. Search/List APIs

```
POST /api/doc/page/list
```

**Request Body:**
```json
{
  "search": "<keyword>",
  "admins": "",
  "favorite": false,
  "moduleNames": "",
  "apiTypes": "",
  "release": "",
  "lifecycles": "",
  "categories": "",
  "pageSize": 20,
  "pageNo": 1,
  "sortDirection": "desc",
  "sortField": "updateTime"
}
```

Filter options for `moduleNames`, `lifecycles`, `apiTypes`, `release` can be obtained from the dictionary endpoint.

**Response:**
```json
{
  "code": 200,
  "data": {
    "totalCount": 1819,
    "totalPage": 182,
    "currentPage": 1,
    "list": [
      {
        "id": "<apiId>",
        "apiName": "...",
        "apiType": "REST|OData|SOAP|Event",
        "moduleName": "...",
        "uriAccessMode": "...",
        "contents": [{"apiVersion": "v1", "lifecycle": "Production", "path": "/rest/..."}]
      }
    ]
  }
}
```

### 2. Get API Detail

```
GET /api/doc/<apiId>/<version>
```

Returns full API metadata including team members, description, path, lifecycle.

### 3. Get Operation Detail

```
GET /api/doc/operations/<contentId>?apiOperation=<method>$$<urlEncodedPath>
```

Returns full operation-level detail including description, parameters, request/response examples, and schemas.

- `contentId`: The content ID from the `contents` array in search results
- `apiOperation`: Format is `<httpMethod>$$<url-encoded-path>` (e.g., `get$$%2Frest%2Fecosystem%2Fwholeself%2Fv1%2FcertificateAssetExports`)

**Response:**
```json
{
  "code": 200,
  "data": {
    "operationId": "...",
    "method": "get",
    "path": "/rest/ecosystem/wholeself/v1/certificateAssetExports",
    "summary": "...",
    "description": "...",
    "parameters": [...],
    "responses": {...},
    "examples": [...]
  }
}
```

### 4. Get OpenAPI Specification

```
GET /api/doc/spec/<apiId>?version=<version>
```

Returns an array with the OpenAPI/Swagger spec as a JSON string in `swaggerJson` field:
```json
[{
  "id": "...",
  "swaggerJson": "{\"openapi\":\"3.0.3\",\"info\":{...},\"paths\":{...}}",
  "category": "default",
  "apiVersion": "v1"
}]
```

Parse `swaggerJson` (JSON.parse) to get the full OpenAPI 3.0 specification with paths, schemas, etc.

### 5. Get Filter Options (Dictionary)

```
GET /api/dict/dictData?type=apiModule,apiLifecycle,apiRelease,apiProtocol
```

Returns available filter values:
- `apiModule`: 16 modules (Analytics, Employee Central, Recruiting, etc.)
- `apiLifecycle`: Production, Development, Deprecated, etc.
- `apiRelease`: Version milestones (2111, 2205, 2305, etc.)
- `apiProtocol`: REST, OData, SOAP, Event, GraphQL

### 6. Get Tools/Utilities

```
GET /api/getTools
```

### 6. Get Register Centers

```
GET /api/registerCenters
```

---

## Usage Patterns

### Finding an API by keyword
1. Search with `POST /api/doc/page/list` using the keyword
2. Get details with `GET /api/doc/<id>/<version>` for interesting results
3. Get the OpenAPI spec with `GET /api/doc/spec/<id>?version=<version>` for full endpoint details

### Browsing by module
1. Get module list from `GET /api/dict/dictData?type=apiModule`
2. Search with `moduleNames` filter set to the desired module

### Getting endpoint documentation
1. Get the OpenAPI spec
2. Parse the `swaggerJson` field (it's a JSON string, needs double-parse)
3. Extract paths, parameters, request/response schemas

---

## Important Notes

- **Browser is for authentication only.** All data retrieval (search, detail, spec, operation info, etc.) must go through the REST API endpoints documented above using `curl`/`fetch`. Do NOT use Playwright tools (`browser_navigate`, `browser_evaluate`, `browser_snapshot`, etc.) to scrape the CodeMeta UI for data.
- CodeMeta has ~1819 APIs across 16 modules and 19 tools
- Each login invalidates the previous token — if the user logs in via browser, the CLI token is invalidated
- The API uses standard REST conventions with JSON request/response bodies
- OpenAPI specs are stored as stringified JSON within the response (need double-parse)
- Token has ~20 day JWT expiry but can be invalidated at any time by another login
