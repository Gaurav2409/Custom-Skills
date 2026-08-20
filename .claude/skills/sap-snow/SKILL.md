---
name: sap-snow
description: Search, view, create, update, and comment on incidents and customer cases; search, view, update, and comment on change requests; read-only search and view of problems (PRB) and problem tasks (PTASK) on SAP's internal ServiceNow ITSM (itsm.services.sap). Supports encoded query search and personal ticket shortcuts. Use when user asks about ITSM tickets, incidents, ServiceNow, snow, customer cases, change requests, problems, problem tasks, or INC/CS/CHG/PRB/PTASK numbers.
---

# SAP ServiceNow ITSM Skill

You are a ServiceNow ITSM automation agent. Your job is to manage incidents, customer cases, and change requests on SAP's internal ServiceNow instance by running the `snow.py` CLI script. You MUST follow these instructions precisely and completely.

## Configuration

Before executing any operation, read the configuration file at `skills/sap-snow/config.yaml` (relative to this file). Copy from `config.example.yaml` if it does not exist. Parse the YAML and extract:

| Key | Required | Description |
|-----|----------|-------------|
| `SNOW_DOMAIN` | No | ServiceNow instance domain. Default: `itsm.services.sap` |
| `AUTH_COOKIE_DIR` | No | Directory containing `sap_cookies.txt`. Default: `~/.sap-mcp/cookies/sap-snow` |
| `DECRYPT_KEY` | No | AES-256-GCM decryption key (min 16 chars) for encrypted cookie files. Must match `ENCRYPT_KEY` in sap-authentication |

If a key is empty or not set, treat it as unset and use defaults.

---

## Authentication

### Cookie-based + g_ck CSRF token

This skill uses a two-layer authentication:
1. Standard SAP cookie authentication (same as Jira/Wiki)
2. A `g_ck` CSRF token extracted at runtime from ServiceNow HTML

**Cookie loading is handled by `scripts/snow.py` internally** — it shells out to `scripts/load-cookies.mjs` (which supports both plain text and AES-GCM encrypted `sap_cookies.txt`, honoring `DECRYPT_KEY`). You do NOT need to read the cookie file yourself; just run the `snow.py` commands below.

For the cookie file format and encryption details, see [`references/cookies-format.md`](references/cookies-format.md).

**g_ck CSRF token**: After loading cookies, the `snow.py` script automatically fetches a ServiceNow page and extracts the `g_ck` session token (regex: `g_ck = 'TOKEN'`). This token is required as `X-UserToken` header for all ServiceNow API calls. If extraction fails, re-authentication is needed.

### Authentication Error Recovery

When the script exits with an authentication error (exit code 1), the error message includes the `entry_url` and `store_path` needed for re-authentication.

**Recovery flow:**

1. Invoke the `sap-authentication` skill with:
   - `entry_url`: `https://itsm.services.sap/` (from error message)
   - `store_path`: `{AUTH_COOKIE_DIR}` (from error message)
2. Wait for authentication to complete
3. Reload cookies from `{store_path}/sap_cookies.txt`
4. Retry the original command

### Auth error reference

| Error message (stderr) | Cause |
|-------------------------|-------|
| `No cookie file found at ...` | Never authenticated |
| `Cookies expired (Xh old)` | Cookies older than 24h |
| `HTTP 401 — authentication failed` | Cookies invalid/revoked |
| `HTTP 403 — authentication failed` | Insufficient permissions |
| `Login redirect detected` | Server redirecting to SSO |
| `Could not extract g_ck token` | Session token extraction failed |

---

## Commands

Run commands using the `snow.py` script. Pass `--cookie-dir` with `AUTH_COOKIE_DIR` if configured:

```bash
python3 scripts/snow.py --cookie-dir "$AUTH_COOKIE_DIR" <command> [options]
```

### Query field choices

```bash
# Context-aware choices for a specific record (recommended — matches UI exactly)
python3 scripts/snow.py choices incident close_code --record INC16970266
python3 scripts/snow.py choices incident u_symptom --record INC16970266 --depends-on configuration_change
python3 scripts/snow.py choices incident u_affected_area --record INC16970266

# Generic choices without record context (returns more values than UI shows)
python3 scripts/snow.py choices incident state
python3 scripts/snow.py choices sn_customerservice_case state
```

Use `--record` to get the exact choices shown on the UI for that specific record.

### Identity

```bash
python3 scripts/snow.py myself
python3 scripts/snow.py myself --json
```

### View incident

```bash
python3 scripts/snow.py incident-get INC16970266
python3 scripts/snow.py incident-get INC16970266 --full    # full description (no truncation)
python3 scripts/snow.py incident-get INC16970266 --json    # raw API JSON
python3 scripts/snow.py incident-get INC16970266 --field sys_id          # extract single field
python3 scripts/snow.py incident-get INC16970266 --field assigned_to.display_value  # dot notation
python3 scripts/snow.py incident-get INC16970266 --related  # also show linked parent case
python3 scripts/snow.py incident-get INC16970266 --escalations  # show ESC references in history
```

### Search incidents

```bash
# Encoded query
python3 scripts/snow.py incident-search 'assignment_group=SF Ops QA Support^stateIN1,2^ORDERBYDESCsys_updated_on' --limit 20

# Shortcuts
python3 scripts/snow.py incident-search --my-open
python3 scripts/snow.py incident-search --my-assigned

# Convenience filters (combinable)
python3 scripts/snow.py incident-search --component LOD-SF-INT-AHR --priority 1 --since 2026-04-25
python3 scripts/snow.py incident-search --group "SF Ops QA Support" --since 2026-04-01 --limit 50

# Raw JSON output
python3 scripts/snow.py incident-search 'priority=1' --json
```

Filters: `--component` (u_app_component), `--priority` (1-5), `--since` (opened after YYYY-MM-DD), `--group` (assignment_group).

For query syntax, see [references/snow_query_examples.md](references/snow_query_examples.md).

### Create incident

```bash
python3 scripts/snow.py incident-create --short-description "Login service down" --category "Software" --priority 2 --assignment-group "SF Ops QA Support" --description "Full details..."
```

### Update incident

```bash
python3 scripts/snow.py incident-update INC16970266 --state 2 --priority 3
python3 scripts/snow.py incident-update INC16970266 --state "In Progress"
python3 scripts/snow.py incident-update INC16970266 --assigned-to "I575297" --assignment-group "My Team"
```

State values: `1`/`New`, `2`/`In Progress`, `3`/`On Hold`, `-3`/`Awaiting Info`, `6`/`Resolved`, `7`/`Closed`, `8`/`Canceled`.

#### Resolve workflow (IMPORTANT)

Resolving an incident requires multiple fields. Follow this workflow:

**Step 1:** Fetch context-aware choices:
```bash
python3 scripts/snow.py choices incident close_code --record INC16970266
```

**Step 2:** Use `AskUserQuestion` to let the user pick Resolution Category.

**Step 3:** Fetch Resolution Subcategory filtered by the chosen close_code:
```bash
python3 scripts/snow.py choices incident u_symptom --record INC16970266 --depends-on configuration_change
```

**Step 4:** Use `AskUserQuestion` for Resolution Subcategory and Affected area.

**Step 5:** Execute after explicit user confirmation:
```bash
python3 scripts/snow.py incident-update INC16970266 --state 6 --close-code configuration_change --resolution-subcategory configuration_issue_documented_in_guide --affected-area application --close-notes "Resolution details..."
```

### Add comment to incident (IMPORTANT — confirm before posting)

```bash
# Internal work note (default)
python3 scripts/snow.py incident-comment INC16970266 "Investigated — root cause is Redis connection timeout"
# Customer-visible comment
python3 scripts/snow.py incident-comment INC16970266 "Customer-visible update" --public
```

You MUST use `AskUserQuestion` before posting any comment. Present target, visibility (internal/external), and content for user confirmation.

### View case

```bash
python3 scripts/snow.py case-get CS20230005856530
python3 scripts/snow.py case-get CS20230005856530 --full
python3 scripts/snow.py case-get CS20230005856530 --json
python3 scripts/snow.py case-get CS20230005856530 --field sys_id
python3 scripts/snow.py case-get CS20230005856530 --incidents  # show child incidents
```

### Search cases

```bash
python3 scripts/snow.py case-search 'assignment_group=My Team^stateIN1,10' --limit 20
python3 scripts/snow.py case-search --my-open
python3 scripts/snow.py case-search --my-assigned
```

### Create case

```bash
python3 scripts/snow.py case-create --short-description "Customer reports login issue" --category "1" --priority 3 --contact "customer.name"
```

### Update case

```bash
python3 scripts/snow.py case-update CS20230005856530 --state 10 --priority 2
python3 scripts/snow.py case-update CS20230005856530 --state "In Progress"
```

State values: `1`/`New`, `10`/`In Progress`, `18`/`Awaiting Info`, `6`/`Resolved`, `3`/`Closed`, `7`/`Cancelled`.

### Add comment to case (IMPORTANT — confirm before posting)

```bash
python3 scripts/snow.py case-comment CS20230005856530 "Escalated to engineering team"
python3 scripts/snow.py case-comment CS20230005856530 "Customer update" --public
```

Same confirmation workflow as incident comments.

### View change request

```bash
python3 scripts/snow.py change-get CHG13854754
python3 scripts/snow.py change-get CHG13854754 --full
python3 scripts/snow.py change-get CHG13854754 --json
python3 scripts/snow.py change-get CHG13854754 --field sys_id
```

### Search change requests

```bash
python3 scripts/snow.py change-search 'assignment_group=My Team^stateNOT IN3,4,7' --limit 20
python3 scripts/snow.py change-search --my-open
python3 scripts/snow.py change-search --my-assigned
```

### Update change request

```bash
python3 scripts/snow.py change-update CHG13854754 --state "Implement" --priority 3
python3 scripts/snow.py change-update CHG13854754 --assigned-to "I575297" --risk "High"
```

### Add comment to change request (IMPORTANT — confirm before posting)

```bash
python3 scripts/snow.py change-comment CHG13854754 "Implementation completed successfully"
python3 scripts/snow.py change-comment CHG13854754 "Visible update" --public
```

### List attachments

```bash
python3 scripts/snow.py attachments INC16970266
python3 scripts/snow.py attachments CS20230005856530 --json
python3 scripts/snow.py attachments CHG13854754 --download-all --output-dir /tmp/attachments
```

### Download / Upload attachments

```bash
python3 scripts/snow.py attachment-download <sys_id> --output-dir /tmp
python3 scripts/snow.py attachment-upload INC16970266 /path/to/screenshot.png
python3 scripts/snow.py attachment-upload CS20230005856530 /tmp/analysis.pdf --name "Root Cause Analysis.pdf"
```

### View problem (PRB)

```bash
python3 scripts/snow.py prb-get PRB0123456
python3 scripts/snow.py prb-get PRB0123456 --full
python3 scripts/snow.py prb-get PRB0123456 --json
python3 scripts/snow.py prb-get PRB0123456 --field sys_id
python3 scripts/snow.py prb-get PRB0123456 --tasks  # also list child PTASKs
```

### Search problems

```bash
# Encoded query
python3 scripts/snow.py prb-search 'assignment_group=My Team^stateIN1,2^ORDERBYDESCsys_updated_on' --limit 20

# Shortcuts
python3 scripts/snow.py prb-search --my-open
python3 scripts/snow.py prb-search --my-assigned

# Convenience filters (combinable)
python3 scripts/snow.py prb-search --component LOD-SF-INT-AHR --priority 1 --since 2026-04-25
python3 scripts/snow.py prb-search --group "My Team" --since 2026-04-01 --limit 50
```

### View problem task (PTASK)

```bash
python3 scripts/snow.py ptask-get PTASK0123456
python3 scripts/snow.py ptask-get PTASK0123456 --full
python3 scripts/snow.py ptask-get PTASK0123456 --json
python3 scripts/snow.py ptask-get PTASK0123456 --field sys_id
python3 scripts/snow.py ptask-get PTASK0123456 --related  # show parent PRB
```

### Search problem tasks

```bash
# Encoded query
python3 scripts/snow.py ptask-search 'assignment_group=My Team^stateIN1,2' --limit 20

# Shortcuts
python3 scripts/snow.py ptask-search --my-open
python3 scripts/snow.py ptask-search --my-assigned

# Filter by parent problem
python3 scripts/snow.py ptask-search --problem PRB0123456
```

PRB and PTASK support is **read-only** — there are no create/update/comment commands by design.

### View activity history

```bash
python3 scripts/snow.py activities INC16970266
python3 scripts/snow.py activities INC16970266 --limit 5 --type external
python3 scripts/snow.py activities INC16970266 --since 2026-04-29 --type internal
python3 scripts/snow.py activities CS20230005856530 --json
```

---

## Key Notes

- Number formats: incidents use `INC` prefix, cases use `CS` prefix, change requests use `CHG` prefix, problems use `PRB` prefix, problem tasks use `PTASK` prefix
- All output uses display values (human-readable names, not sys_id UUIDs)
- `--json` outputs raw API JSON (available on `get`, `search`, `myself`, `attachments`, `activities`)
- `--full` disables truncation (available on `get` commands)
- `--field` extracts a single value (supports dot notation for nested fields)
- State names are accepted case-insensitively (e.g., `--state "Awaiting Info"` or `--state -3`)
- Comment commands echo the posted content with timestamp for verification
- Queries use ServiceNow encoded query syntax (`^` for AND, `^OR` for OR), not SQL

## References

- **Encoded query syntax and examples**: Read [references/snow_query_examples.md](references/snow_query_examples.md)
- **Cookie file format specification**: Read [references/cookies-format.md](references/cookies-format.md)

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Auth error / 401 / 403 | Invoke `sap-authentication` skill with `entry_url` and `store_path` from error, then retry |
| No results for valid number | Number is case-sensitive: use exact format (INC/CS prefix in uppercase) |
| Encoded query syntax error | Use `^` for AND, not `&&`; check references/snow_query_examples.md |
| Description truncated | Use `--full` flag to see everything |
| g_ck token error | Session may be stale; re-authenticate |
| Resolve state not changing | All four resolve fields required: `--close-code`, `--resolution-subcategory`, `--affected-area`, `--close-notes` |
| Choices don't match UI | Use `--record` flag with `choices` command for context-aware filtering |
| Comment posted as wrong type | Default is internal work note; use `--public` for customer-visible |

## Important Constraints

1. **SAP network required.** Operations will fail if not connected to SAP internal network (VPN or enrolled device).
2. **Cookie validity is 24 hours.** Re-authentication is needed daily.
3. **g_ck token is session-bound.** If the script detects a stale token, it retries once with a fresh token before failing.
4. **Comments require user confirmation.** NEVER post comments without explicit user approval via `AskUserQuestion`.
5. **Resolve workflow is multi-step.** All four fields (close_code, resolution_subcategory, affected_area, close_notes) are required for resolution.
6. **Python 3.10+ required.** No external dependencies (stdlib only). Cookie loading shells out to `node` via `load-cookies.mjs`.
7. **Playwright is reserved for `sap-authentication` only.** This skill MUST use the ServiceNow REST API exclusively. Do NOT fall back to `mcp__playwright-*` tools to scrape the UI, click buttons, or work around API errors. If the REST call fails, fix the request, query field metadata via `choices`, or trigger re-authentication via `sap-authentication` — never substitute browser automation.
