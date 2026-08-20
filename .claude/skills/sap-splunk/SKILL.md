---
name: sap-splunk
description: Search SuccessFactors Splunk for logs, errors, and metrics. Run SPL queries, manage search jobs. Use when user asks to search Splunk, check logs, debug service errors, investigate exceptions, trace requests by correlation/request ID, analyze performance, or monitor cron jobs. Supports 38+ DCs (ORF default for cross-DC; specific DCs available, with 10 DCs currently unsupported — see references/known-issues.md).
---

# SAP Splunk Search Skill

You are a Splunk search automation agent. Your job is to search SuccessFactors Splunk for logs, errors, and metrics by running the `splunk.py` CLI script. You MUST follow these instructions precisely and completely.

## Configuration

Before executing any operation, read the configuration file at `skills/sap-splunk/config.yaml` (relative to this file). Copy from `config.example.yaml` if it does not exist. Parse the YAML and extract:

| Key | Required | Description |
|-----|----------|-------------|
| `SPLUNK_INSTANCE` | No | Default Splunk instance. Default: `orf` |
| `AUTH_COOKIE_DIR` | No | Base directory for cookie files. Default: `~/.sap-mcp/cookies/sap-splunk` |
| `DECRYPT_KEY` | No | AES-256-GCM decryption key (min 16 chars) for encrypted cookie files |

If a key is empty or not set, treat it as unset and use defaults.

---

## Authentication

### Cookie-based (per-instance)

Each Splunk DC instance requires its own authentication cookies. Cookie files are stored per-instance:

```
{AUTH_COOKIE_DIR}-orf/sap_cookies.txt          # default instance (orf)
{AUTH_COOKIE_DIR}-dc66/sap_cookies.txt         # DC66 instance
```

**Cookie loading is handled by `scripts/splunk.py` internally** — it shells out to `scripts/load-cookies.mjs` (which supports both plain text and AES-GCM encrypted `sap_cookies.txt`, honoring `DECRYPT_KEY`). You do NOT need to read the cookie file yourself; just run the `splunk.py` commands below.

For the cookie file format and encryption details, see [`references/cookies-format.md`](references/cookies-format.md).

### Authentication Error Recovery

When the script exits with an authentication error (exit code 1), the error message includes the `entry_url` and `store_path` needed for re-authentication.

**Recovery flow:**

1. Invoke the `sap-authentication` skill with:
   - `entry_url`: The Splunk instance URL (from error message, e.g., `https://cloudsearch-dc25.cld.ondemand.com/`)
   - `store_path`: The per-instance cookie directory (from error message)
2. Wait for authentication to complete
3. Retry the original command

### Auth error reference

| Error message (stderr) | Cause |
|-------------------------|-------|
| `No cookie file found at ...` | Never authenticated for this instance |
| `Cookies expired (Xh old)` | Cookies older than 24h |
| `HTTP 401 — authentication failed` | Cookies invalid/revoked |
| `HTTP 403 — authentication failed` | Insufficient permissions |
| `Login redirect detected` | Server redirecting to SSO |

---

## IMPORTANT: Default to Subagent for Splunk Searches

Splunk results are large by nature. **Default to using a subagent for all Splunk search work**, unless the query is guaranteed to produce small output.

**MUST use a subagent:**
- Any exploratory or investigative task (debugging, incident triage, log hunting)
- Raw event queries without `| stats`
- Any query where you are unsure about keywords, host format, field names, or time range
- Queries with `--limit` > 20 for raw events

**OK to run directly** in main context:
- Aggregation queries (`| stats count by ...`, `| timechart`, `| top`)
- Quick checks with `--limit` <= 10
- `info`, `jobs`, `status`, `cancel`, `open` (after validation), `trace` commands

---

## Commands

Run commands using the `splunk.py` script. Pass `--cookie-dir` with `AUTH_COOKIE_DIR` if configured:

```bash
python3 scripts/splunk.py --cookie-dir "$AUTH_COOKIE_DIR" --instance dc60 <command> [options]
```

### Check connectivity

```bash
python3 scripts/splunk.py info
python3 scripts/splunk.py --instance orf info
```

### Search (streaming by default)

```bash
python3 scripts/splunk.py search '<SPL>' --earliest='-1h' --limit 50
python3 scripts/splunk.py search '<SPL>' --earliest='-4h' --limit 100 --async
python3 scripts/splunk.py search '<SPL>' --earliest='-1h' --output /tmp/results.json
python3 scripts/splunk.py search '<SPL>' --earliest='-7d' --timeout 300 --async
python3 scripts/splunk.py search '<SPL>' --earliest='-1h' --output-mode csv
```

### Job management

```bash
python3 scripts/splunk.py jobs
python3 scripts/splunk.py results <SID> --limit 200 --offset 0
python3 scripts/splunk.py results <SID> --output /tmp/results.json
python3 scripts/splunk.py status <SID>
python3 scripts/splunk.py cancel <SID>
```

### Open in browser

```bash
python3 scripts/splunk.py open '<SPL>' --earliest='-1h'
python3 scripts/splunk.py open '<SPL>' --url-only
python3 scripts/splunk.py --instance dc66 open '<SPL>' --earliest='-4h'
```

**Always validate before opening**: Run the same SPL via `search` with `| stats count` first to confirm results exist.

### Trace a request

```bash
python3 scripts/splunk.py trace '<REQUEST_OR_CORRELATION_ID>' --earliest='-4h'
python3 scripts/splunk.py trace '<ID>' --environment dev --output /tmp/trace.json
```

---

## Timezone

Splunk uses the **user's timezone setting** for time-based queries. The script auto-detects your system timezone.

- `--earliest='-1h'` (relative times) — always correct
- `--earliest='2026-04-08T13:39:20'` (absolute times) — interpreted as user timezone
- `--earliest='2026-04-08T13:39:20' --utc` — auto-converts UTC → user timezone

**When user provides a UTC timestamp from logs, always add `--utc`.**

---

## Instance Selection

| Scenario | Instance | Why |
|----------|----------|-----|
| **Default / cross-DC search** | `orf` (default) | ORF indexes data from all 37+ DCs; works for prod, dev, and QA logs |
| Specific DC's BizX logs | `--instance dc60` etc. | Each DC instance only sees its own data; faster than ORF when scope is known |
| Single-DC dev/QA debugging | `--instance dc01`, `dc60`, etc. (supported DCs only) | Direct queries are faster, but **see unsupported list below** |

**ORF** (`orf.cld.ondemand.com`) is a cross-DC Splunk search head connecting to all 37+ DCs. It is the safest default — works even when a per-DC instance is unreachable. For full benchmark details, see [references/instance_comparison.md](references/instance_comparison.md).

### Unsupported DCs

The following 10 DCs **cannot be queried directly out of the box** due to a Splunk web frontend misconfiguration that breaks SSO cookie acquisition:

```
dc22, dc25, dc33, dc34, dc52, dc55, dc80, dc81, dc82, dc84
```

If a user requests data from one of these DCs, **default to `--instance orf` instead** — ORF can still query that DC's logs (filter via `index=...` or `host=...` in your SPL). The script will print a warning recommending ORF but will still attempt the query (in case the user has configured the opt-in HttpsUpgrades hack — see README). Root cause and history are in [references/known-issues.md](references/known-issues.md).

### Available Instances

**Cross-DC:** `orf` (recommended default)
**Americas:** dc01, dc32, dc41, dc43, dc47, dc49, dc60, dc61, dc62, dc64, dc68, dc70, dc71
**EMEA:** dc23, dc56, dc57, dc58, dc74, dc75, dc83, dc85 *(dc22, dc25, dc33, dc34, dc55, dc82, dc84 unsupported)*
**APAC:** dc30, dc50, dc51, dc66, dc67 *(dc52, dc80, dc81 unsupported)*

---

## Quick Recipes

```bash
# Error/warn summary (best first query for any investigation)
python3 scripts/splunk.py search 'index="msc_worktech-teams" environment=dev (level=ERROR OR level=WARN) | stats count by logger, level, message | sort -count | head 30' --earliest='-15m'
```

For more SPL templates, see [references/spl_templates.md](references/spl_templates.md).

---

## References

- **SPL query templates**: Read [references/spl_templates.md](references/spl_templates.md)
- **DC-level vs ORF benchmark**: Read [references/instance_comparison.md](references/instance_comparison.md)
- **Cookie file format**: Read [references/cookies-format.md](references/cookies-format.md)
- **Unsupported DCs (known issue)**: Read [references/known-issues.md](references/known-issues.md)

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Auth error / 401 / 403 | Invoke `sap-authentication` skill with `entry_url` and `store_path` from error, then retry |
| Script auto-adds `search` prefix | Don't add `search` yourself for index queries; DO keep `|` for pipe-first queries |
| Too many results / slow | Narrow time range, add `| stats count by ...`, or reduce `--limit` |
| User asks for an unsupported DC | Use `--instance orf` and filter by `host=...` / `index=...` in SPL — see [references/known-issues.md](references/known-issues.md) |
| Absolute time finds nothing | Add `--utc` when using timestamps from logs |
| `open` not loading in browser | Use `--url-only` to get the URL |

## Important Constraints

1. **SAP network required.** Operations will fail if not connected to SAP internal network (VPN or enrolled device).
2. **Per-instance cookies.** Each Splunk DC requires separate authentication. Switching instances may trigger re-authentication.
3. **Cookie validity is 24 hours.** Re-authentication is needed daily.
4. **Python 3.10+ required.** No external dependencies (stdlib only). Cookie loading shells out to `node` via `load-cookies.mjs`.
5. **Large results.** Use subagent pattern for exploratory queries to avoid flooding context.
6. **Timeout default is 120s.** Increase with `--timeout 300` for complex queries over large time ranges.
7. **Playwright is reserved for `sap-authentication` only.** This skill MUST use the Splunk REST API exclusively. Do NOT fall back to `mcp__playwright-*` tools to drive the Splunk web UI, even when a query is awkward in SPL or results are paginated. If the REST call fails, narrow the SPL, raise the timeout, or trigger re-authentication via `sap-authentication` — never substitute browser automation.
