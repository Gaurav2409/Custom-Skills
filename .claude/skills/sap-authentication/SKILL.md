---
name: sap-authentication
description: Authenticates to SAP internal systems (SSO, IDP) using Playwright browser automation. Use when the user needs to log in to SAP services, obtain authentication cookies, or refresh expired sessions.
---

# SAP Authentication Skill

You are an authentication automation agent. Your job is to authenticate the user to SAP internal systems using the Playwright MCP browser tools. You MUST follow these instructions precisely and completely.

The browser may run in **headless** or **headed** mode (see **Browser Mode** section). In headless mode you are the user's eyes — read every page via `browser_snapshot` and relay prompts through chat. In headed mode the user can also see and interact with the browser directly, but you still drive the automation.

## Configuration

Before executing any authentication flow, read the configuration file at `~/.sap-auth/config.yaml` (or `skills/config.yaml` relative to this file as fallback). Copy from `config.example.yaml` if it does not exist. Parse the YAML and extract:

| Key | Required | Description |
|-----|----------|-------------|
| `SAP_AUTH_ACCOUNT` | Recommended | SAP email address for account selection (e.g., `first.last@sap.com`) |
| `ENCRYPT_KEY` | Optional | AES-256-GCM encryption key (min 16 chars) for cookie file encryption |
| `BROWSER_MODE` | Optional | `"headless"` (default) or `"headed"`. See **Browser Mode** section below |

If the config file does not exist or a key is empty, treat it as unset. If `SAP_AUTH_ACCOUNT` is not set, select the first available account tile on the login page.

## Browser Mode

Playwright MCP's headed/headless mode is fixed at startup and cannot be switched at runtime. To support both modes, the host client should configure **two Playwright MCP server instances**:

```json
{
  "mcpServers": {
    "playwright-headless": {
      "command": "npx",
      "args": ["-y", "@anthropic/playwright-mcp", "--browser", "chrome", "--headless"]
    },
    "playwright-headed": {
      "command": "npx",
      "args": ["-y", "@anthropic/playwright-mcp", "--browser", "chrome"]
    }
  }
}
```

### Mode Selection Rules

1. **Config default**: `BROWSER_MODE` in `config.yaml` determines which MCP instance to use initially.
   - `"headless"` → call tools from `playwright-headless`
   - `"headed"` → call tools from `playwright-headed`
2. **User override**: The user can request a mode switch at any time (e.g., "use a visible browser", "switch to headed"). Always honor the user's explicit request — it takes precedence over config.
3. **Stall suggestion**: If an OS-level dialog blocks headless mode and you cannot read its content via `browser_snapshot`, suggest switching to the headed instance. Do NOT switch automatically — ask the user first.

### How to Switch Mid-Flow

Since both MCP instances are always available:

1. Close the current browser session on the active instance: `browser_close` (on the current MCP)
2. Switch all subsequent Playwright tool calls to the other MCP instance
3. Resume the authentication flow from **Step 1** (navigate to entry URL again)

No server restart is needed — both instances are running in parallel.

### Behavior Differences

| Aspect | `playwright-headless` | `playwright-headed` |
|--------|----------------------|---------------------|
| Browser window | Not visible | Visible on screen |
| User can see page | No — you must describe everything via chat | Yes — user can observe directly |
| User can interact manually | No — you must mediate all input | Yes — user can type/click in the window |
| OS-level dialogs (certificates) | May not be accessible via snapshot | User can interact directly |
| Password entry | Must be relayed through chat | User can type directly in browser |
| Resource usage | Lower (no rendering) | Higher (full rendering) |

## Entry Parameters

This skill is invoked by downstream app MCPs (e.g., sap-jira-mcp, sap-wiki-mcp) when they encounter an authentication failure. They provide:

- **`entry_url`** (required): The SAP system URL to authenticate against (e.g., `https://jira.tools.sap/`, `https://wiki.one.int.sap/`)
- **`store_path`** (required): Directory path where `sap_cookies.txt` must be written after successful authentication

These values come from the `SAP_AUTH_REQUIRED` error payload returned by app MCPs:

```json
{
  "error": "SAP_AUTH_REQUIRED",
  "details": "need call sap auth mcp to prepare cookie and redo function after",
  "data": {
    "store_path": "/tmp/cookies/jira",
    "entry_url": "https://jira.tools.sap/"
  }
}
```

---

## Authentication Flow

### Step 1: Navigate to Entry URL

```
Tool: browser_navigate
URL: {entry_url}
```

Wait for the page to fully load.

### Step 2: Detect Page State

```
Tool: browser_snapshot
```

Analyze the accessibility snapshot to determine which state you are in:

| State | Detection Criteria | Next Action |
|-------|-------------------|-------------|
| **Already Authenticated** | URL contains the target domain (extracted from `entry_url`) AND page content shows application UI (not a login form) | Go to Step 9 |
| **Account Picker** | Page shows a list of email accounts/tiles on `login.microsoftonline.com` | Go to Step 3 |
| **Email Input** | Page contains an email input field (`input[type="email"]`) | Go to Step 4 |
| **Password Input** | Page contains a password input field | Go to Step 5 |
| **MFA / Authenticator** | Page shows "Approve sign in", "Enter code", authenticator number, or "Verify your identity" | Go to Step 6 |
| **Certificate Selection** | Page shows "Choose a certificate" or "Pick a certificate" | Go to Step 7 |
| **"Stay Signed In" Prompt** | Page shows "Stay signed in?" with Yes/No buttons | Go to Step 8 |
| **Unknown / Stalled** | None of the above, or page has not changed after a previous action | Go to Stall Recovery |

### Step 3: Account Selection

If `SAP_AUTH_ACCOUNT` is set, locate and click the account tile matching that email address. Look for interactive elements (buttons, links, list items) containing the email text.

```
Tool: browser_click
element: [the element ref matching the SAP_AUTH_ACCOUNT email]
```

If `SAP_AUTH_ACCOUNT` is not set, click the first account tile that contains an `@` symbol in its text.

After clicking, wait 3 seconds, then return to **Step 2**.

### Step 4: Email Input

```
Tool: browser_fill_form
ref: [email input field ref]
value: {SAP_AUTH_ACCOUNT}
```

Then locate and click the submit/next button. Look for (in priority order):
1. Button with text "Next"
2. Button with text "Continue"
3. `input[type="submit"]`
4. `button[type="submit"]`

```
Tool: browser_click
element: [submit button ref]
```

Wait 3 seconds, then return to **Step 2**.

### Step 5: Password Input

**In headless mode** — the user cannot see the browser. You MUST mediate:

1. Take a `browser_snapshot` to confirm the password field
2. Tell the user:
   > "The SAP login page is asking for your password. Please type your password here in the chat — I will fill it into the browser and immediately discard it. Your password will NOT be stored anywhere."
3. Wait for the user to reply with their password
4. Fill the password field:
   ```
   Tool: browser_fill_form
   ref: [password input field ref]
   value: {user_provided_password}
   ```
5. Click the submit button
6. **Do NOT repeat or log the password in any subsequent message.**
7. Wait 3 seconds, then return to **Step 2**

**In headed mode** — the user can see the browser window. Tell the user:
> "The login page is asking for your password. You can type it directly into the browser window. Let me know when you are done."

Wait for the user to confirm, then return to **Step 2**.

### Step 6: MFA / Microsoft Authenticator

Take a `browser_snapshot` and analyze the MFA prompt type:

#### 6a: Authenticator Number Matching

If the page displays a prominent 2-3 digit number:

1. Extract the number from the snapshot
2. Tell the user:
   > "Microsoft Authenticator number matching required. Open the Authenticator app on your phone and enter: **{number}**"
3. Poll for up to 90 seconds:
   - Every 5 seconds, take a `browser_snapshot`
   - Check if the page has transitioned (URL changed or number display disappeared)
4. If approved (page changed): return to **Step 2**
5. If timeout: tell the user "MFA approval timed out. Would you like to retry?" and act on their response

#### 6b: Code Entry (TOTP / SMS)

If the page has a code input field:

1. Tell the user:
   > "The login page requires an MFA code. Please enter the code from your authenticator app (or SMS):"
2. Wait for the user to reply with the code
3. Fill the code input field:
   ```
   Tool: browser_fill_form
   ref: [code input field ref]
   value: {user_provided_code}
   ```
4. Click the submit/verify button
5. Wait 3 seconds, return to **Step 2**

#### 6c: Push Notification (no number)

If the page says "Approve sign in" without a visible number:

1. Tell the user:
   > "A push notification has been sent to your Microsoft Authenticator app. Please approve the sign-in request."
2. Poll for 90 seconds (same as 6a step 3)
3. If approved: return to **Step 2**
4. If timeout: ask user if they want to retry

### Step 7: Certificate Selection

**In headless mode** — the user cannot see the certificate picker. You MUST mediate:

1. Take a `browser_snapshot` to read the list of available certificates
2. Present the options to the user:
   > "The login page requires a client certificate. Available certificates:
   > 1. {cert_name_1}
   > 2. {cert_name_2}
   > ...
   > Which one should I select?"
3. Wait for the user to choose
4. Click the selected certificate:
   ```
   Tool: browser_click
   element: [the element ref for the chosen certificate]
   ```
5. If there is a confirmation/OK button, click it
6. Wait 3 seconds, return to **Step 2**

If the snapshot does not show individual certificate options (some OS-level dialogs are not accessible via the accessibility tree), suggest switching to headed mode:
> "A system certificate dialog appeared but I cannot read its contents in headless mode. Would you like me to restart the browser in headed (visible) mode so you can select the certificate directly?"

**In headed mode** — the user can see the certificate dialog. Tell the user:
> "A certificate selection dialog is displayed. Please select the correct certificate in the browser window and let me know when you are done."

Wait for the user to confirm, then return to **Step 2**.

### Step 8: "Stay Signed In" Prompt

Click "Yes" to stay signed in:

```
Tool: browser_click
element: [Yes button ref]
```

Wait 3 seconds, return to **Step 2**.

### Step 9: Extract Cookies

Once authenticated (URL is on the target domain and shows application content):

```
Tool: browser_cookie_list
```

Collect ALL cookies returned.

If the target is a Microsoft service (Teams, Outlook), also note that cookies from related domains (`teams.microsoft.com`, `outlook.office.com`, `login.microsoftonline.com`) should be included.

### Step 10: Extract Tokens (Microsoft Services Only)

If the `entry_url` targets a Microsoft service (Teams, Outlook):

```
Tool: browser_localstorage_list
```

Scan all localStorage entries for JWT tokens (strings matching pattern `eyJ...`). For each JWT found:
1. Decode the payload (base64url decode the middle segment)
2. Check the `aud` (audience) field for these targets:
   - `https://graph.microsoft.com`
   - `ic3.teams.office.com`
   - `teams.office.com`
   - `api.spaces.skype.com`
   - `https://outlook.office.com`
   - `https://substrate.office.com`
3. Check `exp` (expiration) is in the future
4. Collect valid tokens with their audience and expiry metadata

### Step 11: Save Cookies to File

Use the `save-cookies.mjs` utility script to extract `name=value` pairs and write a plain-text cookie header file. This script handles format normalization, filtering, and optional encryption.

**Script location**: `scripts/save-cookies.mjs` (relative to this skill directory)

**Output file**: `{store_path}/sap_cookies.txt` — a single line containing `name1=value1; name2=value2; ...`

Downstream app MCPs consume this directly:
```javascript
const cookie = fs.readFileSync(path, 'utf8');
fetch(url, { headers: { Cookie: cookie } });
```

**Usage** — pipe the raw `browser_cookie_list` JSON output into the script:

```bash
echo '<browser_cookie_list_output_json>' | node /path/to/skills/sap-authentication/scripts/save-cookies.mjs \
  --store-path "{store_path}"
```

If `ENCRYPT_KEY` is configured:

```bash
echo '...' | ENCRYPT_KEY="{key}" node /path/to/skills/sap-authentication/scripts/save-cookies.mjs \
  --store-path "{store_path}"
```

The script will:
- Accept any Playwright cookie format (array or `{cookies: [...]}`)
- Extract `name=value` pairs, skip cookies with empty values
- Join with `; ` to form a valid HTTP Cookie header string
- Create the `store_path` directory if it does not exist
- Encrypt if a key is provided (AES-256-GCM, matching `src/secure-store.ts`)
- Write to `{store_path}/sap_cookies.txt`

**Cookie age**: determined by file modification time (mtime). Cookies are considered expired after 24 hours.

**Verify** the script prints: `Saved N cookies to {store_path}/sap_cookies.txt`

### Step 12: Save Tokens (if extracted)

If tokens were collected in Step 10 (Microsoft services), write them to a temp file and pass to the same script:

```bash
cat > /tmp/_sap_tokens_tmp.json << 'TOKENS_EOF'
{
  "tokens": [...collected tokens...],
  "timestamp": <Date.now()>,
  "source": "localStorage"
}
TOKENS_EOF

node /path/to/skills/sap-authentication/scripts/save-cookies.mjs \
  --store-path "{store_path}" \
  --input /dev/null \
  --tokens /tmp/_sap_tokens_tmp.json

rm -f /tmp/_sap_tokens_tmp.json
```

The tokens file will be saved as `{store_path}/sap_tokens.json` with the same encryption applied if configured.

Note: tokens remain in JSON format since they contain structured metadata (audience, expiry, scopes) needed by consuming services.

### Step 13: Close Browser and Report Success

```
Tool: browser_close
```

Return to the calling context:

```
Authentication successful.
- Target: {entry_url}
- Cookies saved: {store_path}/sap_cookies.txt ({cookie_count} cookies)
- Tokens saved: {store_path}/sap_tokens.json ({token_count} tokens) [if applicable]
- Domain: {target_domain}
```

---

## Stall Recovery

If after any action the page state does not change (same URL, same content) for two consecutive `browser_snapshot` checks (10 seconds apart), the flow is stalled. Execute the following recovery procedure:

### 1. Read the Page

```
Tool: browser_snapshot
```

### 2. Classify the Stall

Analyze the snapshot content and match against these patterns:

| Pattern Found in Snapshot | Stall Type | Recovery Action |
|--------------------------|------------|-----------------|
| Password input field visible | Needs password | Go to Step 5 |
| Text: "Approve sign in", "Verify your identity" | Needs MFA approval | Go to Step 6 |
| Text: "Enter code", code input field | Needs MFA code | Go to Step 6b |
| 2-3 digit number prominently displayed | Needs Authenticator number matching | Go to Step 6a |
| Text: "Choose a certificate", "Pick a certificate" | Needs certificate selection | Go to Step 7 |
| Text: "Stay signed in" | Needs confirmation | Go to Step 8 |
| Text: "Your account is locked", "account has been blocked" | Account locked | Report to user and abort |
| Text: "Something went wrong", "error" | Server error | Report to user, suggest retry |
| Empty or minimal content | Page still loading | Wait 5 more seconds, snapshot again |
| URL is on target domain | Actually authenticated | Go to Step 9 |

### 3. Unrecognized Stall

If none of the above patterns match after 3 consecutive snapshots:

1. Report to the user with full details:
   > "Authentication appears to be stuck. Here is what I see on the page:
   > - **Current URL**: {url}
   > - **Page content summary**: {brief description of visible elements}
   > - **Interactive elements**: {list of buttons, inputs, links visible}
   >
   > What would you like me to do? Options:
   > 1. Click a specific element (tell me which one)
   > 2. Type text into a field (tell me which field and what to type)
   > 3. Retry navigation from the beginning
   > 4. Abort authentication"

2. Wait for user instruction and execute accordingly
3. After executing user instruction, return to **Step 2**

---

## Error Handling

### Retry Logic

- If account click does not cause a page transition within 10 seconds, retry the click once
- If the page redirects back to the SSO page after reaching the target domain (double-redirect), wait 5 seconds and attempt account selection again on the new SSO page
- Maximum 3 SSO retry attempts before entering Stall Recovery

### Timeout Boundaries

| Operation | Maximum Wait |
|-----------|-------------|
| Page navigation | 45 seconds |
| Account tile appearance | 15 seconds |
| Post-click redirect | 15 seconds |
| MFA approval | 90 seconds |
| Stall detection | 10 seconds (2 snapshots) |
| Overall authentication | 6 minutes |

### Failure Reporting

When authentication fails and cannot be recovered, report clearly:

```
Authentication failed.
- Target: {entry_url}
- Reason: {specific reason}
- Current URL: {current page URL}
- Last page content: {summary}
- Suggestion: {actionable next step}
```

Common failure reasons:
- "Account tile not found" — `SAP_AUTH_ACCOUNT` does not match any listed account
- "MFA approval timed out" — User did not approve within 90 seconds
- "Password not provided" — User declined to provide password
- "Certificate dialog not accessible" — OS-level dialog cannot be operated in headless mode
- "Unexpected page state" — Page does not match any known auth flow state
- "Navigation timeout" — Target URL did not respond within 45 seconds
- "SSO retries exhausted" — Auth page keeps redirecting after 3 attempts
- "Account locked" — SAP account is locked or blocked

---

## Cookie Inspection Tool

When asked to check cookie status (equivalent to `sap_get_cookie_info`):

1. Check if `{store_path}/sap_cookies.txt` exists
2. If encrypted (file content is binary/non-ASCII), decrypt using `ENCRYPT_KEY`
3. Report:
   - File exists: yes/no
   - Cookie count: number of `name=value` pairs (split by `; `)
   - Age: hours since file modification time (mtime)
   - Expired: whether mtime is older than 24 hours
   - Preview: first 3 cookie names (without values) for verification

---

## Cookie Clearing Tool

When asked to clear cookies (equivalent to `sap_clear_cookies`):

1. Delete `{store_path}/sap_cookies.txt` if it exists
2. Delete `{store_path}/sap_tokens.json` if it exists
3. Confirm deletion

---

## Domain Classification

### SAP Systems

URLs matching these patterns are SAP internal systems:
- `*.tools.sap` (Jira, Git, etc.)
- `*.one.int.sap` (Wiki, Confluence)
- `*.wdf.sap.corp` (internal services)
- `*.sap.com` (external SAP services)

### Microsoft Services

URLs matching these patterns are Microsoft services requiring extended cookie/token extraction:
- `teams.microsoft.com`, `teams.cloud.microsoft`, `teams.live.com`, `teams.office.com`
- `outlook.office.com`, `outlook.office365.com`, `outlook.cloud.microsoft`

### SSO/Login Pages (NOT target pages)

These URLs indicate authentication is still in progress:
- `login.microsoftonline.com`
- `accounts.sap.com`
- Any URL containing `/login`, `/auth`, `/oauth2/`

---

## Important Constraints

1. **NEVER store, repeat, or log passwords.** Fill them into the browser field and forget immediately.
2. **NEVER skip MFA.** Always wait for user approval or code entry.
3. **Cookie files are per-app-MCP.** The `store_path` is unique to each calling app MCP. Never reuse or share paths between apps.
4. **24-hour cookie validity.** Cookies are expired when `sap_cookies.txt` file mtime is older than 24 hours.
5. **Encryption is optional but symmetric.** If `ENCRYPT_KEY` is set, both writing (this skill) and reading (app MCPs) must use the same key.
6. **Close browser after authentication.** Once cookies are extracted and saved, call `browser_close` to free resources.
7. **SAP network required.** Authentication will fail if the device is not connected to SAP internal network (VPN or enrolled device).
8. **Respect the user's mode preference.** Default to `BROWSER_MODE` from config, but always honor an explicit user request to switch between headless and headed. Never switch automatically without asking.
9. **Adapt your behavior to the current mode.**
   - **Headless**: You are the user's eyes. Always describe what you see on the page before asking the user to act. Never ask the user to "look at the browser" — they cannot see it.
   - **Headed**: The user can see the browser. For steps that require direct user interaction (password, certificate), you may defer to the user instead of mediating through chat. Still drive automation for all other steps.
