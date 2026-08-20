#!/usr/bin/env python3
"""SAP ServiceNow ITSM client — stdlib only, cookie-based auth via sap-authentication skill.

Usage:
    python3 snow.py myself
    python3 snow.py incident-get <number> [--field F] [--related] [--escalations]
    python3 snow.py incident-search <query> [--limit N] [--json]
    python3 snow.py incident-search --my-open [--limit N]
    python3 snow.py incident-search --component C --priority P --since DATE --group G
    python3 snow.py incident-create --short-description "..." [--category C] [--priority P] [--assignment-group G]
    python3 snow.py incident-update <number> [--state S] [--priority P] [--assigned-to U]
    python3 snow.py incident-comment <number> "text"
    python3 snow.py case-get <number> [--field F] [--incidents]
    python3 snow.py case-search <query> [--limit N]
    python3 snow.py case-create --short-description "..." [--contact C] [--category C]
    python3 snow.py case-update <number> [--state S] [--priority P]
    python3 snow.py case-comment <number> "text"
    python3 snow.py change-get <number> [--field F]
    python3 snow.py change-search <query> [--limit N]
    python3 snow.py change-update <number> [--state S] [--priority P]
    python3 snow.py change-comment <number> "text"
    python3 snow.py attachments <number> [--download-all --output-dir <dir>]
    python3 snow.py attachment-download <sys_id> [--output-dir <dir>]
    python3 snow.py attachment-upload <number> <file> [--name N]
    python3 snow.py activities <number> [--limit N] [--since DATE] [--type external|internal|all]

Options:
    --cookie-dir DIR  — cookie directory (default: ~/.sap-mcp/cookies/sap-snow)
"""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

# ─── Configuration ───────────────────────────────────────────────────────────
DEFAULT_COOKIE_DIR = os.path.expanduser("~/.sap-mcp/cookies/sap-snow")
COOKIE_DIR = None  # Set from --cookie-dir argument or default
SNOW_DOMAIN = os.environ.get("SNOW_DOMAIN", "itsm.services.sap")
SNOW_BASE = f"https://{SNOW_DOMAIN}"
API_BASE = f"{SNOW_BASE}/api/now/table"
ATTACHMENT_API = f"{SNOW_BASE}/api/now/attachment"
HELPER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "load-cookies.mjs")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

TABLE_INCIDENT = "incident"
TABLE_CASE = "sn_customerservice_case"
TABLE_CHANGE = "change_request"
TABLE_PROBLEM = "problem"
TABLE_PROBLEM_TASK = "problem_task"
TABLE_USER = "sys_user"
TABLE_JOURNAL = "sys_journal_field"

INCIDENT_STATES = {
    "new": "1", "in progress": "2", "on hold": "3",
    "awaiting info": "-3", "resolved": "6", "closed": "7", "canceled": "8",
}
CASE_STATES = {
    "new": "1", "in progress": "10", "awaiting info": "18",
    "resolved": "6", "closed": "3", "cancelled": "7",
}
CHANGE_STATES = {
    "new": "-5", "assess": "-4", "authorize": "-3", "scheduled": "-2",
    "implement": "-1", "review": "0", "closed": "3", "canceled": "4",
}
PROBLEM_STATES = {
    "new": "1", "assess": "2", "root cause analysis": "3",
    "fix in progress": "4", "resolved": "6", "closed": "7", "canceled": "8",
}
PROBLEM_TASK_STATES = {
    "open": "1", "pending": "2", "work in progress": "3",
    "closed complete": "4", "closed incomplete": "7", "closed skipped": "8",
}

MIME_TYPES = {
    ".txt": "text/plain", ".csv": "text/csv", ".json": "application/json",
    ".xml": "application/xml", ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".bmp": "image/bmp", ".svg": "image/svg+xml",
    ".zip": "application/zip", ".gz": "application/gzip",
    ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html", ".log": "text/plain", ".md": "text/markdown",
}

INCIDENT_LIST_FIELDS = "sys_id,number,short_description,state,priority,assignment_group,assigned_to,opened_at,sys_updated_on"
INCIDENT_DETAIL_FIELDS = "sys_id,number,short_description,description,state,incident_state,priority,impact,urgency,category,subcategory,assignment_group,assigned_to,caller_id,opened_by,opened_at,resolved_at,closed_at,close_code,close_notes,u_app_component,u_task_component,cmdb_ci,parent,comments_and_work_notes,sys_updated_on"

CASE_LIST_FIELDS = "sys_id,number,short_description,state,priority,assignment_group,assigned_to,opened_at,sys_updated_on"
CASE_DETAIL_FIELDS = "sys_id,number,short_description,description,state,priority,impact,urgency,category,subcategory,assignment_group,assigned_to,contact,opened_by,opened_at,resolved_at,closed_at,close_notes,resolution_code,u_app_component,u_task_component,u_case_number,correlation_display,comments_and_work_notes,sys_updated_on"

CHANGE_LIST_FIELDS = "sys_id,number,short_description,state,priority,type,risk,assignment_group,assigned_to,start_date,end_date"
CHANGE_DETAIL_FIELDS = "sys_id,number,short_description,description,state,priority,type,category,risk,impact,assignment_group,assigned_to,requested_by,opened_by,opened_at,start_date,end_date,close_code,close_notes,comments_and_work_notes,sys_updated_on"

PROBLEM_LIST_FIELDS = "sys_id,number,short_description,state,priority,assignment_group,assigned_to,opened_at,sys_updated_on"
PROBLEM_DETAIL_FIELDS = "sys_id,number,short_description,description,state,problem_state,priority,impact,urgency,category,subcategory,assignment_group,assigned_to,opened_by,opened_at,resolved_at,closed_at,close_code,cause_notes,fix_notes,workaround,known_error,major_problem,u_app_component,u_task_component,u_error_category,u_affected_area,u_sub_affected_area,u_responsible_party,u_cause_note_status,u_problem_coordinator,u_record_audience,u_work_notes_incident,u_work_notes_problem_task,cmdb_ci,first_reported_by_task,comments_and_work_notes,sys_updated_on"

PROBLEM_TASK_LIST_FIELDS = "sys_id,number,short_description,state,priority,problem,problem_task_type,assignment_group,assigned_to,opened_at,sys_updated_on"
PROBLEM_TASK_DETAIL_FIELDS = "sys_id,number,short_description,description,state,priority,impact,urgency,problem,parent,assignment_group,assigned_to,opened_by,opened_at,due_date,closed_at,close_code,close_notes,work_notes,cause_notes,fix_notes,problem_task_type,u_root_cause,u_affected_area,u_affected_sub_area,u_responsible_party,u_component,u_task_component,u_record_audience,comments_and_work_notes,sys_updated_on"

# Cached session info
_g_ck_token = None
_current_user = None
_current_user_sysid = None


# ─── Cookie handling ─────────────────────────────────────────────────────────
def _get_cookie_dir():
    """Return the cookie directory (from --cookie-dir or default)."""
    return COOKIE_DIR or DEFAULT_COOKIE_DIR


def load_cookies():
    """Load cookies via load-cookies.mjs helper.

    Helper handles plain text, AES-GCM encrypted files (DECRYPT_KEY env), and
    24h expiry checks. We delegate so encryption stays in one place — see
    sap-authentication/scripts/save-cookies.mjs for the writer side.
    """
    cookie_dir = _get_cookie_dir()
    try:
        result = subprocess.run(
            ["node", HELPER_SCRIPT, "--store-path", cookie_dir],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("ERROR: 'node' executable not found — required to read cookies.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
            if not result.stderr.endswith("\n"):
                sys.stderr.write("\n")
        print("Invoke the sap-authentication skill with:", file=sys.stderr)
        print(f"  entry_url: {SNOW_BASE}/", file=sys.stderr)
        print(f"  store_path: {cookie_dir}", file=sys.stderr)
        sys.exit(1)

    cookie_header = result.stdout.strip()
    if not cookie_header:
        print("ERROR: Cookie file is empty.", file=sys.stderr)
        sys.exit(1)

    return cookie_header


def _print_auth_error(reason):
    """Print structured auth error directing to sap-authentication skill."""
    cookie_dir = _get_cookie_dir()
    print(f"ERROR: {reason}.", file=sys.stderr)
    print(f"Invoke the sap-authentication skill with:", file=sys.stderr)
    print(f"  entry_url: {SNOW_BASE}/", file=sys.stderr)
    print(f"  store_path: {cookie_dir}", file=sys.stderr)


# ─── Session info & g_ck token ──────────────────────────────────────────────
def _fetch_session_info(cookie_header):
    """Fetch g_ck CSRF token from a ServiceNow page, then resolve current username via API."""
    global _g_ck_token, _current_user

    if _g_ck_token is not None:
        return _g_ck_token

    for page in ["/nav_to.do", "/"]:
        url = f"{SNOW_BASE}{page}"
        req = urllib.request.Request(url)
        req.add_header("Cookie", cookie_header)
        req.add_header("User-Agent", USER_AGENT)

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            final_url = resp.url
            if "accounts.sap.com" in final_url or "login" in final_url.split("?")[0].lower():
                _print_auth_error("Login redirect detected")
                sys.exit(1)
            body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                _print_auth_error(f"HTTP {e.code} — authentication failed")
                sys.exit(1)
            continue
        except urllib.error.URLError as e:
            print(f"ERROR: Connection failed — {e.reason}", file=sys.stderr)
            sys.exit(1)

        g_ck_match = re.search(r"""g_ck\s*=\s*['"]([^'"]+)['"]""", body)
        if g_ck_match:
            token = g_ck_match.group(1)
            if token and token != "undefined":
                _g_ck_token = token
                break

    if _g_ck_token is None:
        _print_auth_error(f"Could not extract g_ck token from {SNOW_BASE}")
        sys.exit(1)

    _fetch_current_user(cookie_header)
    return _g_ck_token


def _fetch_current_user(cookie_header):
    """Resolve current username via the session API."""
    global _current_user
    if _current_user is not None:
        return

    url = f"{SNOW_BASE}/api/now/ui/user/current_user"
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie_header)
    req.add_header("X-UserToken", _g_ck_token)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        _current_user = data.get("result", {}).get("user_name", "")
    except Exception:
        pass


def _invalidate_session():
    global _g_ck_token
    _g_ck_token = None


# ─── HTTP helpers ────────────────────────────────────────────────────────────
def make_request(url, cookie_header, g_ck, method="GET", data=None, _retried=False):
    """Send HTTP request to ServiceNow. Returns (status_code: int, body: str)."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Cookie", cookie_header)
    req.add_header("X-UserToken", g_ck)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    if method in ("POST", "PUT", "PATCH", "DELETE"):
        req.add_header("Content-Type", "application/json")

    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data)
        req.data = data.encode("utf-8") if isinstance(data, str) else data

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        final_url = resp.url
        if "accounts.sap.com" in final_url or "login" in final_url.split("?")[0].lower():
            _print_auth_error("Login redirect detected")
            sys.exit(1)
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "") == "gzip":
            raw = gzip.decompress(raw)
        body = raw.decode("utf-8")
        return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code in (401, 403):
            if not _retried:
                _invalidate_session()
                new_g_ck = _fetch_session_info(cookie_header)
                return make_request(url, cookie_header, new_g_ck, method=method, data=data, _retried=True)
            _print_auth_error(f"HTTP {e.code} — authentication failed")
            sys.exit(1)
        return e.code, body
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed — {e.reason}", file=sys.stderr)
        sys.exit(1)


def _safe_json(body):
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        _print_auth_error("Expected JSON but got non-JSON response")
        print(f"  Response (truncated): {body[:300]}", file=sys.stderr)
        sys.exit(1)


def api_get(table, cookie_header, g_ck, params=None):
    url = f"{API_BASE}/{table}"
    if params is None:
        params = {}
    params.setdefault("sysparm_display_value", "true")
    url += "?" + urllib.parse.urlencode(params)
    code, body = make_request(url, cookie_header, g_ck)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    return _safe_json(body)


def api_post(table, cookie_header, g_ck, data=None):
    url = f"{API_BASE}/{table}?sysparm_display_value=true"
    code, body = make_request(url, cookie_header, g_ck, method="POST", data=data)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    return _safe_json(body)


def api_patch(table, sys_id, cookie_header, g_ck, data=None):
    url = f"{API_BASE}/{table}/{sys_id}"
    code, body = make_request(url, cookie_header, g_ck, method="PATCH", data=data)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    return _safe_json(body)


# ─── Form POST for state transitions (triggers UI Actions / SLA workflows) ────

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)
    http_error_301 = http_error_303 = http_error_307 = http_error_302


_INCIDENT_SYS_ACTIONS = {
    "-3": "awaiting_requestor",
    "2": "retrieve_incident",
    "6": "resolve_incident",
}
_CASE_SYS_ACTIONS = {
    "18": "awaiting_requestor",
    "10": "retrieve_case",
    "6": "resolve_case",
}
_CHANGE_SYS_ACTIONS = {
    "-3": "awaiting_requestor",
    "-1": "retrieve_change",
    "3": "resolve_change",
}


def form_post(table, sys_id, cookie_header, g_ck, sys_action, extra_fields=None, sys_mod_count="0"):
    url = f"{SNOW_BASE}/{table}.do"
    payload = {
        "sys_action": sys_action,
        "sysparm_ck": g_ck,
        "sys_uniqueValue": sys_id,
        "sys_target": table,
        "sys_mod_count": str(sys_mod_count),
        "sys_base_uri": f"{SNOW_BASE}/",
    }
    if extra_fields:
        payload.update(extra_fields)

    form_data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, method="POST", data=form_data)
    req.add_header("Cookie", cookie_header)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        opener.open(req, timeout=30)
        print("ERROR: Form POST did not receive expected redirect.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307):
            return
        if e.code in (401, 403):
            _print_auth_error(f"HTTP {e.code} during form POST")
            sys.exit(1)
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"ERROR: Form POST failed — HTTP {e.code}", file=sys.stderr)
        if body:
            print(f"  {body[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed — {e.reason}", file=sys.stderr)
        sys.exit(1)


def _print_api_error(code, body):
    print(f"ERROR: HTTP {code}", file=sys.stderr)
    try:
        err = json.loads(body)
        error_obj = err.get("error", {})
        msg = error_obj.get("message", "")
        detail = error_obj.get("detail", "")
        if msg:
            print(f"  {msg}", file=sys.stderr)
        if detail:
            print(f"  {detail}", file=sys.stderr)
    except (json.JSONDecodeError, AttributeError):
        if body:
            print(f"  {body[:500]}", file=sys.stderr)


# ─── Record helpers ──────────────────────────────────────────────────────────
def _display(record, field):
    """Extract display value from a record field. Handles both plain strings and reference objects."""
    val = record.get(field, "")
    if isinstance(val, dict):
        return val.get("display_value", val.get("value", ""))
    return val or ""


def _extract_field(record, field_path):
    """Extract a field value using dot notation (e.g., 'assigned_to.display_value')."""
    parts = field_path.split(".")
    val = record
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part, "")
        else:
            return ""
    if val is None:
        return ""
    return val if isinstance(val, str) else json.dumps(val)


def _resolve_table_from_number(number):
    upper = number.upper()
    if upper.startswith("INC"):
        return TABLE_INCIDENT
    elif upper.startswith("CS"):
        return TABLE_CASE
    elif upper.startswith("CHG"):
        return TABLE_CHANGE
    elif upper.startswith("PTASK"):
        return TABLE_PROBLEM_TASK
    elif upper.startswith("PRB"):
        return TABLE_PROBLEM
    else:
        print(f"ERROR: Cannot determine table for '{number}'. Expected INC/CS/CHG/PRB/PTASK prefix.", file=sys.stderr)
        sys.exit(1)


def _resolve_state(value, state_map):
    """Resolve a state value: pass through numeric codes, map names to values."""
    if not value:
        return value
    stripped = value.strip()
    if stripped.lstrip("-").isdigit():
        return stripped
    key = stripped.lower()
    if key in state_map:
        return state_map[key]
    names = ", ".join(f'"{k}"' for k in state_map)
    print(f"ERROR: Unknown state '{value}'. Valid names: {names}", file=sys.stderr)
    sys.exit(1)


def _get_by_number(table, number, cookie_header, g_ck, fields=None, display_value="true"):
    params = {
        "sysparm_query": f"number={number}",
        "sysparm_limit": "1",
        "sysparm_display_value": display_value,
    }
    if fields:
        params["sysparm_fields"] = fields
    data = api_get(table, cookie_header, g_ck, params=params)
    results = data.get("result", [])
    if not results:
        print(f"ERROR: No record found with number {number}", file=sys.stderr)
        sys.exit(1)
    return results[0]


def _search(table, query, cookie_header, g_ck, limit=20, offset=0, fields=None):
    params = {
        "sysparm_query": query,
        "sysparm_limit": str(limit),
        "sysparm_offset": str(offset),
    }
    if fields:
        params["sysparm_fields"] = fields
    data = api_get(table, cookie_header, g_ck, params=params)
    return data.get("result", [])


# ─── User resolution ────────────────────────────────────────────────────────
def _get_current_user_sysid(cookie_header, g_ck):
    global _current_user_sysid
    if _current_user_sysid:
        return _current_user_sysid

    if not _current_user:
        print("ERROR: Could not determine current username from session.", file=sys.stderr)
        sys.exit(1)

    data = api_get(TABLE_USER, cookie_header, g_ck, params={
        "sysparm_query": f"user_name={_current_user}",
        "sysparm_limit": "1",
        "sysparm_fields": "sys_id,user_name,name,email",
        "sysparm_display_value": "false",
    })
    results = data.get("result", [])
    if not results:
        print(f"ERROR: User '{_current_user}' not found in sys_user table.", file=sys.stderr)
        sys.exit(1)

    _current_user_sysid = results[0].get("sys_id", "") or None
    if not _current_user_sysid:
        print(f"ERROR: User '{_current_user}' has no sys_id.", file=sys.stderr)
        sys.exit(1)
    return _current_user_sysid


# ─── Formatting helpers ─────────────────────────────────────────────────────
def _strip_html(text):
    """Strip HTML tags and decode common entities for cleaner text output."""
    if not text:
        return text
    text = re.sub(r"\[code\]|\[/code\]", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li>", "  - ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<a\s+[^>]*href=['\"]([^'\"]*)['\"][^>]*>([^<]*)</a>", r"\2 (\1)", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#64;", "@").replace("&quot;", '"')
    text = text.replace("&rarr;", "→").replace("&mdash;", "—")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_lines(text, max_lines, full=False):
    if not text:
        return []
    lines = text.split("\n")
    if full or len(lines) <= max_lines:
        return [f"    {l}" for l in lines]
    result = [f"    {l}" for l in lines[:max_lines]]
    result.append(f"    ... ({len(lines) - max_lines} more lines)")
    return result


def _format_incident_row(r):
    num = _display(r, "number")
    state = _display(r, "state")
    priority = _display(r, "priority")
    group = _display(r, "assignment_group")[:20]
    assigned = _display(r, "assigned_to")[:18]
    desc = _display(r, "short_description")[:55]
    return f"{num:<16} {state:<16} {priority:<12} {group:<20} {assigned:<18} {desc}"


def _format_incident_detail(r, full=False):
    num = _display(r, "number")
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {num}: {_display(r, 'short_description')}")
    lines.append(f"{'='*70}")
    lines.append(f"  URL:              {SNOW_BASE}/incident.do?sysparm_query=number={num}")
    lines.append(f"  State:            {_display(r, 'state')}")
    lines.append(f"  Priority:         {_display(r, 'priority')}")
    lines.append(f"  Impact:           {_display(r, 'impact')}")
    lines.append(f"  Urgency:          {_display(r, 'urgency')}")
    lines.append(f"  Category:         {_display(r, 'category')}")
    lines.append(f"  Subcategory:      {_display(r, 'subcategory')}")
    lines.append(f"  Assignment Group: {_display(r, 'assignment_group')}")
    lines.append(f"  Assigned To:      {_display(r, 'assigned_to')}")
    lines.append(f"  Caller:           {_display(r, 'caller_id')}")
    lines.append(f"  Opened By:        {_display(r, 'opened_by')}")
    lines.append(f"  Opened At:        {_display(r, 'opened_at')}")
    resolved = _display(r, "resolved_at")
    if resolved:
        lines.append(f"  Resolved At:      {resolved}")
    closed = _display(r, "closed_at")
    if closed:
        lines.append(f"  Closed At:        {closed}")
        lines.append(f"  Close Code:       {_display(r, 'close_code')}")
    parent = _display(r, "parent")
    if parent:
        lines.append(f"  Parent Case:      {parent}")
    app_comp = _display(r, "u_app_component")
    if app_comp:
        lines.append(f"  App Component:    {app_comp}")
    cmdb_ci = _display(r, "cmdb_ci")
    if cmdb_ci:
        lines.append(f"  CI:               {cmdb_ci}")

    desc = _display(r, "description")
    if desc:
        lines.append(f"\n  Description:")
        lines.extend(_truncate_lines(_strip_html(desc), 20, full=full))

    close_notes = _display(r, "close_notes")
    if close_notes:
        lines.append(f"\n  Close Notes:")
        lines.extend(_truncate_lines(_strip_html(close_notes), 10, full=full))

    case_notes = _display(r, "comments_and_work_notes")
    if case_notes:
        lines.append(f"\n  Activities:")
        lines.extend(_truncate_lines(_strip_html(case_notes), 20, full=full))

    return "\n".join(lines)


def _format_case_row(r):
    num = _display(r, "number")
    state = _display(r, "state")
    priority = _display(r, "priority")
    group = _display(r, "assignment_group")[:20]
    assigned = _display(r, "assigned_to")[:18]
    desc = _display(r, "short_description")[:55]
    return f"{num:<24} {state:<16} {priority:<12} {group:<20} {assigned:<18} {desc}"


def _format_case_detail(r, full=False):
    num = _display(r, "number")
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {num}: {_display(r, 'short_description')}")
    lines.append(f"{'='*70}")
    lines.append(f"  URL:              {SNOW_BASE}/sn_customerservice_case.do?sysparm_query=number={num}")
    lines.append(f"  State:            {_display(r, 'state')}")
    lines.append(f"  Priority:         {_display(r, 'priority')}")
    lines.append(f"  Impact:           {_display(r, 'impact')}")
    lines.append(f"  Urgency:          {_display(r, 'urgency')}")
    lines.append(f"  Category:         {_display(r, 'category')}")
    lines.append(f"  Subcategory:      {_display(r, 'subcategory')}")
    lines.append(f"  Assignment Group: {_display(r, 'assignment_group')}")
    lines.append(f"  Assigned To:      {_display(r, 'assigned_to')}")
    lines.append(f"  Contact:          {_display(r, 'contact')}")
    lines.append(f"  Opened By:        {_display(r, 'opened_by')}")
    lines.append(f"  Opened At:        {_display(r, 'opened_at')}")
    case_num = _display(r, "u_case_number")
    if case_num:
        lines.append(f"  Case Number:      {case_num}")
    correlation = _display(r, "correlation_display")
    if correlation:
        lines.append(f"  Correlation:      {correlation}")
    resolved = _display(r, "resolved_at")
    if resolved:
        lines.append(f"  Resolved At:      {resolved}")
    closed = _display(r, "closed_at")
    if closed:
        lines.append(f"  Closed At:        {closed}")
    resolution = _display(r, "resolution_code")
    if resolution:
        lines.append(f"  Resolution Code:  {resolution}")
    app_comp = _display(r, "u_app_component")
    if app_comp:
        lines.append(f"  App Component:    {app_comp}")

    desc = _display(r, "description")
    if desc:
        lines.append(f"\n  Description:")
        lines.extend(_truncate_lines(_strip_html(desc), 20, full=full))

    close_notes = _display(r, "close_notes")
    if close_notes:
        lines.append(f"\n  Close Notes:")
        lines.extend(_truncate_lines(_strip_html(close_notes), 10, full=full))

    activities = _display(r, "comments_and_work_notes")
    if activities:
        lines.append(f"\n  Activities:")
        lines.extend(_truncate_lines(_strip_html(activities), 20, full=full))

    return "\n".join(lines)


def _format_change_row(r):
    num = _display(r, "number")
    state = _display(r, "state")
    priority = _display(r, "priority")
    chg_type = _display(r, "type")[:10]
    risk = _display(r, "risk")[:10]
    assigned = _display(r, "assigned_to")[:18]
    desc = _display(r, "short_description")[:50]
    return f"{num:<16} {state:<14} {priority:<12} {chg_type:<10} {risk:<10} {assigned:<18} {desc}"


def _format_change_detail(r, full=False):
    num = _display(r, "number")
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {num}: {_display(r, 'short_description')}")
    lines.append(f"{'='*70}")
    lines.append(f"  URL:              {SNOW_BASE}/change_request.do?sysparm_query=number={num}")
    lines.append(f"  State:            {_display(r, 'state')}")
    lines.append(f"  Priority:         {_display(r, 'priority')}")
    lines.append(f"  Type:             {_display(r, 'type')}")
    lines.append(f"  Category:         {_display(r, 'category')}")
    lines.append(f"  Risk:             {_display(r, 'risk')}")
    lines.append(f"  Impact:           {_display(r, 'impact')}")
    lines.append(f"  Assignment Group: {_display(r, 'assignment_group')}")
    lines.append(f"  Assigned To:      {_display(r, 'assigned_to')}")
    lines.append(f"  Requested By:     {_display(r, 'requested_by')}")
    lines.append(f"  Opened By:        {_display(r, 'opened_by')}")
    lines.append(f"  Opened At:        {_display(r, 'opened_at')}")
    start = _display(r, "start_date")
    if start:
        lines.append(f"  Start Date:       {start}")
    end = _display(r, "end_date")
    if end:
        lines.append(f"  End Date:         {end}")
    close_code = _display(r, "close_code")
    if close_code:
        lines.append(f"  Close Code:       {close_code}")

    desc = _display(r, "description")
    if desc:
        lines.append(f"\n  Description:")
        lines.extend(_truncate_lines(_strip_html(desc), 20, full=full))

    close_notes = _display(r, "close_notes")
    if close_notes:
        lines.append(f"\n  Close Notes:")
        lines.extend(_truncate_lines(_strip_html(close_notes), 10, full=full))

    activities = _display(r, "comments_and_work_notes")
    if activities:
        lines.append(f"\n  Activities:")
        lines.extend(_truncate_lines(_strip_html(activities), 20, full=full))

    return "\n".join(lines)


def _format_problem_row(r):
    num = _display(r, "number")
    state = _display(r, "state")
    priority = _display(r, "priority")
    group = _display(r, "assignment_group")[:20]
    assigned = _display(r, "assigned_to")[:18]
    desc = _display(r, "short_description")[:55]
    return f"{num:<16} {state:<22} {priority:<12} {group:<20} {assigned:<18} {desc}"


def _format_problem_detail(r, full=False):
    num = _display(r, "number")
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {num}: {_display(r, 'short_description')}")
    lines.append(f"{'='*70}")
    lines.append(f"  URL:              {SNOW_BASE}/problem.do?sysparm_query=number={num}")
    lines.append(f"  State:            {_display(r, 'state')}")
    lines.append(f"  Problem State:    {_display(r, 'problem_state')}")
    lines.append(f"  Priority:         {_display(r, 'priority')}")
    lines.append(f"  Impact:           {_display(r, 'impact')}")
    lines.append(f"  Urgency:          {_display(r, 'urgency')}")
    lines.append(f"  Category:         {_display(r, 'category')}")
    lines.append(f"  Subcategory:      {_display(r, 'subcategory')}")
    lines.append(f"  Assignment Group: {_display(r, 'assignment_group')}")
    lines.append(f"  Assigned To:      {_display(r, 'assigned_to')}")
    lines.append(f"  Opened By:        {_display(r, 'opened_by')}")
    lines.append(f"  Opened At:        {_display(r, 'opened_at')}")
    resolved = _display(r, "resolved_at")
    if resolved:
        lines.append(f"  Resolved At:      {resolved}")
    closed = _display(r, "closed_at")
    if closed:
        lines.append(f"  Closed At:        {closed}")
        lines.append(f"  Close Code:       {_display(r, 'close_code')}")
    major = _display(r, "major_problem")
    if major:
        lines.append(f"  Major Problem:    {major}")
    known = _display(r, "known_error")
    if known:
        lines.append(f"  Known Error:      {known}")
    first = _display(r, "first_reported_by_task")
    if first:
        lines.append(f"  First Reported:   {first}")
    app_comp = _display(r, "u_app_component")
    if app_comp:
        lines.append(f"  App Component:    {app_comp}")
    cmdb_ci = _display(r, "cmdb_ci")
    if cmdb_ci:
        lines.append(f"  CI:               {cmdb_ci}")

    desc = _display(r, "description")
    if desc:
        lines.append(f"\n  Description:")
        lines.extend(_truncate_lines(_strip_html(desc), 20, full=full))

    workaround = _display(r, "workaround")
    if workaround:
        lines.append(f"\n  Workaround:")
        lines.extend(_truncate_lines(_strip_html(workaround), 15, full=full))

    cause = _display(r, "cause_notes")
    if cause:
        lines.append(f"\n  Cause Notes:")
        lines.extend(_truncate_lines(_strip_html(cause), 15, full=full))

    fix = _display(r, "fix_notes")
    if fix:
        lines.append(f"\n  Fix Notes:")
        lines.extend(_truncate_lines(_strip_html(fix), 15, full=full))

    activities = _display(r, "comments_and_work_notes")
    if activities:
        lines.append(f"\n  Activities:")
        lines.extend(_truncate_lines(_strip_html(activities), 20, full=full))

    return "\n".join(lines)


def _format_problem_task_row(r):
    num = _display(r, "number")
    state = _display(r, "state")
    priority = _display(r, "priority")
    problem = _display(r, "problem")[:14]
    group = _display(r, "assignment_group")[:18]
    assigned = _display(r, "assigned_to")[:18]
    desc = _display(r, "short_description")[:50]
    return f"{num:<16} {state:<20} {priority:<12} {problem:<14} {group:<18} {assigned:<18} {desc}"


def _format_problem_task_detail(r, full=False):
    num = _display(r, "number")
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  {num}: {_display(r, 'short_description')}")
    lines.append(f"{'='*70}")
    lines.append(f"  URL:              {SNOW_BASE}/problem_task.do?sysparm_query=number={num}")
    lines.append(f"  State:            {_display(r, 'state')}")
    lines.append(f"  Priority:         {_display(r, 'priority')}")
    lines.append(f"  Impact:           {_display(r, 'impact')}")
    lines.append(f"  Urgency:          {_display(r, 'urgency')}")
    parent_problem = _display(r, "problem")
    if parent_problem:
        lines.append(f"  Problem:          {parent_problem}")
    parent = _display(r, "parent")
    if parent and parent != parent_problem:
        lines.append(f"  Parent:           {parent}")
    lines.append(f"  Assignment Group: {_display(r, 'assignment_group')}")
    lines.append(f"  Assigned To:      {_display(r, 'assigned_to')}")
    lines.append(f"  Opened By:        {_display(r, 'opened_by')}")
    lines.append(f"  Opened At:        {_display(r, 'opened_at')}")
    due = _display(r, "due_date")
    if due:
        lines.append(f"  Due Date:         {due}")
    closed = _display(r, "closed_at")
    if closed:
        lines.append(f"  Closed At:        {closed}")
        lines.append(f"  Close Code:       {_display(r, 'close_code')}")

    desc = _display(r, "description")
    if desc:
        lines.append(f"\n  Description:")
        lines.extend(_truncate_lines(_strip_html(desc), 20, full=full))

    close_notes = _display(r, "close_notes")
    if close_notes:
        lines.append(f"\n  Close Notes:")
        lines.extend(_truncate_lines(_strip_html(close_notes), 10, full=full))

    activities = _display(r, "comments_and_work_notes")
    if activities:
        lines.append(f"\n  Activities:")
        lines.extend(_truncate_lines(_strip_html(activities), 20, full=full))

    return "\n".join(lines)


# ─── Commands ────────────────────────────────────────────────────────────────
def cmd_myself(args, cookie_header, g_ck):
    if not _current_user:
        print("ERROR: Could not determine current username from session.", file=sys.stderr)
        sys.exit(1)

    data = api_get(TABLE_USER, cookie_header, g_ck, params={
        "sysparm_query": f"user_name={_current_user}",
        "sysparm_limit": "1",
        "sysparm_fields": "sys_id,user_name,name,email,title,department,location,manager",
    })
    results = data.get("result", [])
    if not results:
        print(f"ERROR: User '{_current_user}' not found.", file=sys.stderr)
        sys.exit(1)

    user = results[0]
    if args.json:
        print(json.dumps(user, indent=2))
        return

    print(f"User Name:  {_display(user, 'user_name')}")
    print(f"Full Name:  {_display(user, 'name')}")
    print(f"Email:      {_display(user, 'email')}")
    print(f"Title:      {_display(user, 'title')}")
    print(f"Department: {_display(user, 'department')}")
    print(f"Location:   {_display(user, 'location')}")
    print(f"Manager:    {_display(user, 'manager')}")
    print(f"Sys ID:     {_display(user, 'sys_id')}")


def cmd_incident_get(args, cookie_header, g_ck):
    dv = "all" if args.field else "true"
    r = _get_by_number(TABLE_INCIDENT, args.number.upper(), cookie_header, g_ck, fields=INCIDENT_DETAIL_FIELDS, display_value=dv)
    if args.field:
        print(_extract_field(r, args.field))
        return
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(_format_incident_detail(r, full=args.full))
    if args.related:
        parent = _display(r, "parent")
        if parent and parent.upper().startswith("CS"):
            print(f"\n{'─'*70}")
            print(f"  Related Case:")
            print(f"{'─'*70}")
            case = _get_by_number(TABLE_CASE, parent.upper(), cookie_header, g_ck, fields=CASE_DETAIL_FIELDS)
            if args.json:
                print(json.dumps(case, indent=2))
            else:
                print(_format_case_detail(case, full=args.full))
        else:
            print("\n  No parent case linked to this incident.")
    if args.escalations:
        sys_id = r.get("sys_id", "")
        query = f"element_id={sys_id}^valueLIKEESC^ORDERBYDESCsys_created_on"
        params = urllib.parse.urlencode({
            "sysparm_query": query,
            "sysparm_limit": "20",
            "sysparm_fields": "sys_created_on,value,sys_created_by,element",
        })
        url = f"{API_BASE}/{TABLE_JOURNAL}?{params}"
        code, body = make_request(url, cookie_header, g_ck)
        print(f"\n{'─'*70}")
        print(f"  Escalations:")
        print(f"{'─'*70}")
        if code >= 400:
            print("  Could not retrieve escalation info.")
        else:
            entries = _safe_json(body).get("result", [])
            if not entries:
                print("  No escalation references found in activity history.")
            else:
                esc_seen = set()
                for e in entries:
                    content = e.get("value", "")
                    esc_numbers = re.findall(r"ESC\d+", content)
                    for esc in esc_numbers:
                        if esc not in esc_seen:
                            esc_seen.add(esc)
                    ts = e.get("sys_created_on", "")
                    author = e.get("sys_created_by", "")
                    snippet = _strip_html(content)[:120]
                    print(f"  [{ts}] by {author}")
                    print(f"    {snippet}")
                    print()
                if esc_seen:
                    print(f"  Referenced escalations: {', '.join(sorted(esc_seen))}")


def cmd_incident_search(args, cookie_header, g_ck):
    if args.my_open:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^stateIN1,2,3,-3^ORDERBYDESCsys_updated_on"
    elif args.my_assigned:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^ORDERBYDESCsys_updated_on"
    else:
        parts = []
        if args.query:
            parts.append(args.query)
        if args.component:
            parts.append(f"u_app_component={args.component}")
        if args.priority_filter:
            parts.append(f"priority={args.priority_filter}")
        if args.since:
            parts.append(f"opened_at>={args.since}")
        if args.group:
            parts.append(f"assignment_group={args.group}")
        if not parts:
            print("ERROR: Provide a query, shortcuts (--component, --priority, --since, --group), or use --my-open / --my-assigned", file=sys.stderr)
            sys.exit(1)
        query = "^".join(parts) + "^ORDERBYDESCsys_updated_on"

    results = _search(TABLE_INCIDENT, query, cookie_header, g_ck, limit=args.limit, fields=INCIDENT_LIST_FIELDS)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Results: {len(results)}")
    if not results:
        return
    print(f"\n{'Number':<16} {'State':<16} {'Priority':<12} {'Assignment Group':<20} {'Assigned To':<18} Short Description")
    print("-" * 120)
    for r in results:
        print(_format_incident_row(r))


def cmd_incident_create(args, cookie_header, g_ck):
    fields = {"short_description": args.short_description}
    if args.description:
        fields["description"] = args.description
    if args.category:
        fields["category"] = args.category
    if args.subcategory:
        fields["subcategory"] = args.subcategory
    if args.assignment_group:
        fields["assignment_group"] = args.assignment_group
    if args.assigned_to:
        fields["assigned_to"] = args.assigned_to
    if args.priority:
        fields["priority"] = args.priority
    if args.impact:
        fields["impact"] = args.impact
    if args.urgency:
        fields["urgency"] = args.urgency
    if args.caller:
        fields["caller_id"] = args.caller

    data = api_post(TABLE_INCIDENT, cookie_header, g_ck, data=fields)
    result = data.get("result", {})
    num = _display(result, "number")
    print(f"Created: {num}")
    print(f"URL:     {SNOW_BASE}/incident.do?sysparm_query=number={num}")


def cmd_incident_update(args, cookie_header, g_ck):
    fields = {}
    state_value = None
    if args.state:
        state_value = _resolve_state(args.state, INCIDENT_STATES)
    if args.priority:
        fields["priority"] = args.priority
    if args.impact:
        fields["impact"] = args.impact
    if args.urgency:
        fields["urgency"] = args.urgency
    if args.assignment_group:
        fields["assignment_group"] = args.assignment_group
    if args.assigned_to:
        fields["assigned_to"] = args.assigned_to
    if args.category:
        fields["category"] = args.category
    if args.close_code:
        fields["close_code"] = args.close_code
    if args.close_notes:
        fields["close_notes"] = args.close_notes
    if args.resolution_subcategory:
        fields["u_symptom"] = args.resolution_subcategory
    if args.affected_area:
        fields["u_affected_area"] = args.affected_area

    if not state_value and not fields:
        print("ERROR: No fields to update. Use --state, --priority, --assignment-group, --assigned-to, etc.", file=sys.stderr)
        sys.exit(1)

    fetch_fields = "sys_id,number,sys_mod_count" if state_value else "sys_id,number"
    record = _get_by_number(TABLE_INCIDENT, args.number.upper(), cookie_header, g_ck,
                            fields=fetch_fields, display_value="false")
    sys_id = record.get("sys_id", "")
    num = args.number.upper()

    if state_value:
        sys_action = _INCIDENT_SYS_ACTIONS.get(state_value, "sysverb_update")
        extra = {}

        if sys_action in ("awaiting_requestor", "retrieve_incident"):
            comment = getattr(args, "comment", None)
            if not comment:
                label = "Awaiting Info" if state_value == "-3" else "In Progress"
                print(f"ERROR: --comment is required when transitioning to {label}.", file=sys.stderr)
                sys.exit(1)
            extra["incident.comments"] = comment

        if sys_action == "resolve_incident":
            extra["incident.close_code"] = args.close_code or ""
            extra["incident.u_resolution_subcategory"] = args.resolution_subcategory or ""
            extra["incident.u_affected_area"] = args.affected_area or ""
            extra["incident.close_notes"] = args.close_notes or ""

        if sys_action == "sysverb_update":
            extra["incident.incident_state"] = state_value

        mod_count = record.get("sys_mod_count", "0")
        form_post(TABLE_INCIDENT, sys_id, cookie_header, g_ck, sys_action,
                  extra_fields=extra, sys_mod_count=mod_count)
        print(f"State updated: {num}")

    if fields:
        if state_value == "6":
            fields.pop("close_code", None)
            fields.pop("close_notes", None)
            fields.pop("u_symptom", None)
            fields.pop("u_affected_area", None)
        if fields:
            api_patch(TABLE_INCIDENT, sys_id, cookie_header, g_ck, data=fields)
            if not state_value:
                print(f"Updated: {num}")
            else:
                print(f"Additional fields updated: {num}")


def cmd_incident_comment(args, cookie_header, g_ck):
    record = _get_by_number(TABLE_INCIDENT, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    field = "comments" if args.public else "work_notes"
    api_patch(TABLE_INCIDENT, sys_id, cookie_header, g_ck, data={field: args.text})
    label = "Public comment" if args.public else "Work note"
    print(f"{label} added to {args.number.upper()}")
    _echo_comment(sys_id, field, cookie_header, g_ck)


def cmd_case_get(args, cookie_header, g_ck):
    dv = "all" if args.field else "true"
    r = _get_by_number(TABLE_CASE, args.number.upper(), cookie_header, g_ck, fields=CASE_DETAIL_FIELDS, display_value=dv)
    if args.field:
        print(_extract_field(r, args.field))
        return
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(_format_case_detail(r, full=args.full))
    if args.incidents:
        case_sys_id = r.get("sys_id", "")
        if not case_sys_id:
            print("\n  ERROR: Cannot determine case sys_id for incident lookup.", file=sys.stderr)
            return
        query = f"parent={case_sys_id}^ORDERBYDESCsys_updated_on"
        incidents = _search(TABLE_INCIDENT, query, cookie_header, g_ck, limit=50, fields=INCIDENT_LIST_FIELDS)
        print(f"\n{'─'*70}")
        print(f"  Child Incidents: {len(incidents)}")
        print(f"{'─'*70}")
        if incidents:
            if args.json:
                print(json.dumps(incidents, indent=2))
            else:
                print(f"\n  {'Number':<16} {'State':<16} {'Priority':<12} {'Assigned To':<18} Short Description")
                print(f"  {'-'*100}")
                for inc in incidents:
                    num = _display(inc, "number")
                    state = _display(inc, "state")
                    priority = _display(inc, "priority")
                    assigned = _display(inc, "assigned_to")[:18]
                    desc = _display(inc, "short_description")[:50]
                    print(f"  {num:<16} {state:<16} {priority:<12} {assigned:<18} {desc}")


def cmd_case_search(args, cookie_header, g_ck):
    if args.my_open:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^stateIN1,10,18^ORDERBYDESCsys_updated_on"
    elif args.my_assigned:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^ORDERBYDESCsys_updated_on"
    else:
        query = args.query
        if not query:
            print("ERROR: Provide a query or use --my-open / --my-assigned", file=sys.stderr)
            sys.exit(1)

    results = _search(TABLE_CASE, query, cookie_header, g_ck, limit=args.limit, fields=CASE_LIST_FIELDS)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Results: {len(results)}")
    if not results:
        return
    print(f"\n{'Number':<24} {'State':<16} {'Priority':<12} {'Assignment Group':<20} {'Assigned To':<18} Short Description")
    print("-" * 130)
    for r in results:
        print(_format_case_row(r))


def cmd_case_create(args, cookie_header, g_ck):
    fields = {"short_description": args.short_description}
    if args.description:
        fields["description"] = args.description
    if args.category:
        fields["category"] = args.category
    if args.subcategory:
        fields["subcategory"] = args.subcategory
    if args.assignment_group:
        fields["assignment_group"] = args.assignment_group
    if args.assigned_to:
        fields["assigned_to"] = args.assigned_to
    if args.priority:
        fields["priority"] = args.priority
    if args.contact:
        fields["contact"] = args.contact

    data = api_post(TABLE_CASE, cookie_header, g_ck, data=fields)
    result = data.get("result", {})
    num = _display(result, "number")
    print(f"Created: {num}")
    print(f"URL:     {SNOW_BASE}/sn_customerservice_case.do?sysparm_query=number={num}")


def cmd_case_update(args, cookie_header, g_ck):
    fields = {}
    state_value = None
    if args.state:
        state_value = _resolve_state(args.state, CASE_STATES)
    if args.priority:
        fields["priority"] = args.priority
    if args.impact:
        fields["impact"] = args.impact
    if args.urgency:
        fields["urgency"] = args.urgency
    if args.assignment_group:
        fields["assignment_group"] = args.assignment_group
    if args.assigned_to:
        fields["assigned_to"] = args.assigned_to
    if args.category:
        fields["category"] = args.category

    if not state_value and not fields:
        print("ERROR: No fields to update. Use --state, --priority, --assignment-group, --assigned-to, etc.", file=sys.stderr)
        sys.exit(1)

    fetch_fields = "sys_id,number,sys_mod_count" if state_value else "sys_id,number"
    record = _get_by_number(TABLE_CASE, args.number.upper(), cookie_header, g_ck,
                            fields=fetch_fields, display_value="false")
    sys_id = record.get("sys_id", "")
    num = args.number.upper()

    if state_value:
        sys_action = _CASE_SYS_ACTIONS.get(state_value, "sysverb_update")
        extra = {}

        if sys_action in ("awaiting_requestor", "retrieve_case"):
            comment = getattr(args, "comment", None)
            if not comment:
                label = "Awaiting Info" if state_value == "18" else "In Progress"
                print(f"ERROR: --comment is required when transitioning to {label}.", file=sys.stderr)
                sys.exit(1)
            extra[f"{TABLE_CASE}.comments"] = comment

        if sys_action == "resolve_case":
            extra[f"{TABLE_CASE}.state"] = state_value

        if sys_action == "sysverb_update":
            extra[f"{TABLE_CASE}.state"] = state_value

        mod_count = record.get("sys_mod_count", "0")
        form_post(TABLE_CASE, sys_id, cookie_header, g_ck, sys_action,
                  extra_fields=extra, sys_mod_count=mod_count)
        print(f"State updated: {num}")

    if fields:
        api_patch(TABLE_CASE, sys_id, cookie_header, g_ck, data=fields)
        if not state_value:
            print(f"Updated: {num}")
        else:
            print(f"Additional fields updated: {num}")


def cmd_case_comment(args, cookie_header, g_ck):
    record = _get_by_number(TABLE_CASE, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    field = "comments" if args.public else "work_notes"
    api_patch(TABLE_CASE, sys_id, cookie_header, g_ck, data={field: args.text})
    label = "Public comment" if args.public else "Work note"
    print(f"{label} added to {args.number.upper()}")
    _echo_comment(sys_id, field, cookie_header, g_ck)


def cmd_change_get(args, cookie_header, g_ck):
    dv = "all" if args.field else "true"
    r = _get_by_number(TABLE_CHANGE, args.number.upper(), cookie_header, g_ck, fields=CHANGE_DETAIL_FIELDS, display_value=dv)
    if args.field:
        print(_extract_field(r, args.field))
        return
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(_format_change_detail(r, full=args.full))


def cmd_change_search(args, cookie_header, g_ck):
    if args.my_open:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^stateNOT IN3,4,7^ORDERBYDESCsys_updated_on"
    elif args.my_assigned:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^ORDERBYDESCsys_updated_on"
    else:
        query = args.query
        if not query:
            print("ERROR: Provide a query or use --my-open / --my-assigned", file=sys.stderr)
            sys.exit(1)

    results = _search(TABLE_CHANGE, query, cookie_header, g_ck, limit=args.limit, fields=CHANGE_LIST_FIELDS)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Results: {len(results)}")
    if not results:
        return
    print(f"\n{'Number':<16} {'State':<14} {'Priority':<12} {'Type':<10} {'Risk':<10} {'Assigned To':<18} Short Description")
    print("-" * 130)
    for r in results:
        print(_format_change_row(r))


def cmd_change_update(args, cookie_header, g_ck):
    fields = {}
    state_value = None
    if args.state:
        state_value = _resolve_state(args.state, CHANGE_STATES)
    if args.priority:
        fields["priority"] = args.priority
    if args.risk:
        fields["risk"] = args.risk
    if args.impact:
        fields["impact"] = args.impact
    if args.assignment_group:
        fields["assignment_group"] = args.assignment_group
    if args.assigned_to:
        fields["assigned_to"] = args.assigned_to
    if args.category:
        fields["category"] = args.category

    if not state_value and not fields:
        print("ERROR: No fields to update. Use --state, --priority, --risk, --assignment-group, --assigned-to, etc.", file=sys.stderr)
        sys.exit(1)

    fetch_fields = "sys_id,number,sys_mod_count" if state_value else "sys_id,number"
    record = _get_by_number(TABLE_CHANGE, args.number.upper(), cookie_header, g_ck,
                            fields=fetch_fields, display_value="false")
    sys_id = record.get("sys_id", "")
    num = args.number.upper()

    if state_value:
        sys_action = _CHANGE_SYS_ACTIONS.get(state_value, "sysverb_update")
        extra = {}

        if sys_action in ("awaiting_requestor", "retrieve_change"):
            comment = getattr(args, "comment", None)
            if not comment:
                label = "Awaiting Info" if state_value == "-3" else "In Progress"
                print(f"ERROR: --comment is required when transitioning to {label}.", file=sys.stderr)
                sys.exit(1)
            extra[f"{TABLE_CHANGE}.comments"] = comment

        if sys_action == "resolve_change":
            extra[f"{TABLE_CHANGE}.state"] = state_value

        if sys_action == "sysverb_update":
            extra[f"{TABLE_CHANGE}.state"] = state_value

        mod_count = record.get("sys_mod_count", "0")
        form_post(TABLE_CHANGE, sys_id, cookie_header, g_ck, sys_action,
                  extra_fields=extra, sys_mod_count=mod_count)
        print(f"State updated: {num}")

    if fields:
        api_patch(TABLE_CHANGE, sys_id, cookie_header, g_ck, data=fields)
        if not state_value:
            print(f"Updated: {num}")
        else:
            print(f"Additional fields updated: {num}")


def cmd_change_comment(args, cookie_header, g_ck):
    record = _get_by_number(TABLE_CHANGE, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    field = "comments" if args.public else "work_notes"
    api_patch(TABLE_CHANGE, sys_id, cookie_header, g_ck, data={field: args.text})
    label = "Public comment" if args.public else "Work note"
    print(f"{label} added to {args.number.upper()}")
    _echo_comment(sys_id, field, cookie_header, g_ck)


# ─── Problem (PRB) commands — read-only ────────────────────────────────────
def cmd_problem_get(args, cookie_header, g_ck):
    dv = "all" if args.field else "true"
    r = _get_by_number(TABLE_PROBLEM, args.number.upper(), cookie_header, g_ck,
                       fields=PROBLEM_DETAIL_FIELDS, display_value=dv)
    if args.field:
        print(_extract_field(r, args.field))
        return
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(_format_problem_detail(r, full=args.full))

    if args.tasks:
        sys_id = r.get("sys_id", "")
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")
        query = f"problem={sys_id}^ORDERBYDESCsys_updated_on"
        children = _search(TABLE_PROBLEM_TASK, query, cookie_header, g_ck,
                           limit=20, fields=PROBLEM_TASK_LIST_FIELDS)
        print(f"\n{'─'*70}")
        print(f"  Problem Tasks ({len(children)}):")
        print(f"{'─'*70}")
        if not children:
            print("  (none)")
        else:
            for c in children:
                print(_format_problem_task_row(c))


def cmd_problem_search(args, cookie_header, g_ck):
    if args.my_open:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^stateIN1,2,3,4^ORDERBYDESCsys_updated_on"
    elif args.my_assigned:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^ORDERBYDESCsys_updated_on"
    else:
        parts = []
        if args.query:
            parts.append(args.query)
        if args.component:
            parts.append(f"u_app_component={args.component}")
        if args.priority_filter:
            parts.append(f"priority={args.priority_filter}")
        if args.since:
            parts.append(f"opened_at>={args.since}")
        if args.group:
            parts.append(f"assignment_group={args.group}")
        if not parts:
            print("ERROR: Provide a query, shortcuts (--component, --priority, --since, --group), or use --my-open / --my-assigned", file=sys.stderr)
            sys.exit(1)
        query = "^".join(parts) + "^ORDERBYDESCsys_updated_on"

    results = _search(TABLE_PROBLEM, query, cookie_header, g_ck,
                      limit=args.limit, fields=PROBLEM_LIST_FIELDS)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Results: {len(results)}")
    if not results:
        return
    print(f"\n{'Number':<16} {'State':<22} {'Priority':<12} {'Assignment Group':<20} {'Assigned To':<18} Short Description")
    print("-" * 125)
    for r in results:
        print(_format_problem_row(r))


# ─── Problem Task (PTASK) commands — read-only ─────────────────────────────
def cmd_problem_task_get(args, cookie_header, g_ck):
    dv = "all" if args.field else "true"
    r = _get_by_number(TABLE_PROBLEM_TASK, args.number.upper(), cookie_header, g_ck,
                       fields=PROBLEM_TASK_DETAIL_FIELDS, display_value=dv)
    if args.field:
        print(_extract_field(r, args.field))
        return
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(_format_problem_task_detail(r, full=args.full))

    if args.related:
        problem = _display(r, "problem")
        if problem and problem.upper().startswith("PRB"):
            print(f"\n{'─'*70}")
            print(f"  Parent Problem:")
            print(f"{'─'*70}")
            prb = _get_by_number(TABLE_PROBLEM, problem.upper(), cookie_header, g_ck,
                                 fields=PROBLEM_DETAIL_FIELDS)
            if args.json:
                print(json.dumps(prb, indent=2))
            else:
                print(_format_problem_detail(prb, full=args.full))
        else:
            print("\n  No parent problem linked to this task.")


def cmd_problem_task_search(args, cookie_header, g_ck):
    if args.my_open:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^stateIN1,2,3^ORDERBYDESCsys_updated_on"
    elif args.my_assigned:
        sysid = _get_current_user_sysid(cookie_header, g_ck)
        query = f"assigned_to={sysid}^ORDERBYDESCsys_updated_on"
    else:
        parts = []
        if args.query:
            parts.append(args.query)
        if args.problem:
            parts.append(f"problem.number={args.problem.upper()}")
        if args.priority_filter:
            parts.append(f"priority={args.priority_filter}")
        if args.since:
            parts.append(f"opened_at>={args.since}")
        if args.group:
            parts.append(f"assignment_group={args.group}")
        if not parts:
            print("ERROR: Provide a query, shortcuts (--problem, --priority, --since, --group), or use --my-open / --my-assigned", file=sys.stderr)
            sys.exit(1)
        query = "^".join(parts) + "^ORDERBYDESCsys_updated_on"

    results = _search(TABLE_PROBLEM_TASK, query, cookie_header, g_ck,
                      limit=args.limit, fields=PROBLEM_TASK_LIST_FIELDS)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Results: {len(results)}")
    if not results:
        return
    print(f"\n{'Number':<16} {'State':<20} {'Priority':<12} {'Problem':<14} {'Group':<18} {'Assigned To':<18} Short Description")
    print("-" * 130)
    for r in results:
        print(_format_problem_task_row(r))


# ─── Generic API access ────────────────────────────────────────────────────
def cmd_api_get(args, cookie_header, g_ck):
    params = {
        "sysparm_limit": str(args.limit),
        "sysparm_display_value": "true",
    }
    if args.query:
        params["sysparm_query"] = args.query
    if args.fields:
        params["sysparm_fields"] = args.fields

    data = api_get(args.table, cookie_header, g_ck, params=params)
    results = data.get("result", [])
    if not results:
        print("No records found.")
        return

    print(f"Found {len(results)} record(s):\n")
    for i, rec in enumerate(results, 1):
        print(f"--- Record {i} ---")
        for k, v in rec.items():
            if isinstance(v, dict):
                v = v.get("display_value", v.get("value", ""))
            if v:
                print(f"  {k}: {v}")
        print()


# ─── Attachment commands ────────────────────────────────────────────────────
def _list_attachments(record_sys_id, cookie_header, g_ck):
    url = f"{ATTACHMENT_API}?sysparm_query=table_sys_id={record_sys_id}"
    code, body = make_request(url, cookie_header, g_ck)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    return _safe_json(body).get("result", [])


def _download_attachment(attachment_sys_id, cookie_header, g_ck):
    """Download attachment content. Returns (filename, content_bytes)."""
    meta_url = f"{ATTACHMENT_API}/{attachment_sys_id}"
    code, body = make_request(meta_url, cookie_header, g_ck)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    meta = _safe_json(body).get("result", {})
    filename = meta.get("file_name", attachment_sys_id)

    file_url = f"{ATTACHMENT_API}/{attachment_sys_id}/file"
    req = urllib.request.Request(file_url)
    req.add_header("Cookie", cookie_header)
    req.add_header("X-UserToken", g_ck)
    req.add_header("User-Agent", USER_AGENT)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        content = resp.read()
    except urllib.error.HTTPError as e:
        print(f"ERROR: Failed to download attachment {attachment_sys_id}: HTTP {e.code}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed — {e.reason}", file=sys.stderr)
        sys.exit(1)
    return filename, content


def cmd_attachments(args, cookie_header, g_ck):
    table = _resolve_table_from_number(args.number)
    record = _get_by_number(table, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    attachments = _list_attachments(sys_id, cookie_header, g_ck)

    if args.json:
        print(json.dumps(attachments, indent=2))
        return

    if not attachments:
        print(f"No attachments found for {args.number.upper()}")
        return

    print(f"Attachments for {args.number.upper()}: {len(attachments)}\n")
    print(f"{'File Name':<40} {'Size':<12} {'Content Type':<30} {'Created':<20} Sys ID")
    print("-" * 135)
    for a in attachments:
        fname = a.get("file_name", "")[:39]
        size = a.get("size_bytes", "")
        ctype = a.get("content_type", "")[:29]
        created = a.get("sys_created_on", "")[:19]
        aid = a.get("sys_id", "")
        print(f"{fname:<40} {size:<12} {ctype:<30} {created:<20} {aid}")

    if args.download_all:
        output_dir = args.output_dir or "."
        os.makedirs(output_dir, exist_ok=True)
        for a in attachments:
            aid = a.get("sys_id", "")
            filename, content = _download_attachment(aid, cookie_header, g_ck)
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(content)
            print(f"  Downloaded: {filepath} ({len(content)} bytes)")


def cmd_attachment_download(args, cookie_header, g_ck):
    output_dir = args.output_dir or "."
    os.makedirs(output_dir, exist_ok=True)
    filename, content = _download_attachment(args.sys_id, cookie_header, g_ck)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    print(f"Downloaded: {filepath} ({len(content)} bytes)")


def cmd_attachment_upload(args, cookie_header, g_ck):
    table = _resolve_table_from_number(args.number)
    record = _get_by_number(table, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    file_path = os.path.expanduser(args.file)
    if not os.path.isfile(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    file_name = args.name or os.path.basename(file_path)
    ext = os.path.splitext(file_name)[1].lower()
    content_type = MIME_TYPES.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        file_data = f.read()

    params = urllib.parse.urlencode({
        "table_name": table,
        "table_sys_id": sys_id,
        "file_name": file_name,
    })
    url = f"{ATTACHMENT_API}/file?{params}"
    req = urllib.request.Request(url, method="POST", data=file_data)
    req.add_header("Cookie", cookie_header)
    req.add_header("X-UserToken", g_ck)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", content_type)
    req.add_header("Accept", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"ERROR: Upload failed — HTTP {e.code}", file=sys.stderr)
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if err_body:
            print(f"  {err_body[:300]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed — {e.reason}", file=sys.stderr)
        sys.exit(1)

    result = _safe_json(body).get("result", {})
    att_id = result.get("sys_id", "")
    att_size = result.get("size_bytes", len(file_data))
    print(f"Uploaded: {file_name} ({att_size} bytes)")
    print(f"  Record:  {args.number.upper()}")
    print(f"  Sys ID:  {att_id}")


# ─── Activity / comment history ────────────────────────────────────────────
def _echo_comment(sys_id, element, cookie_header, g_ck):
    """Fetch and display the latest posted comment for confirmation."""
    params = urllib.parse.urlencode({
        "sysparm_query": f"element_id={sys_id}^element={element}^ORDERBYDESCsys_created_on",
        "sysparm_limit": "1",
        "sysparm_fields": "sys_created_on,value,sys_created_by",
    })
    url = f"{API_BASE}/{TABLE_JOURNAL}?{params}"
    code, body = make_request(url, cookie_header, g_ck)
    if code >= 400:
        return
    entries = _safe_json(body).get("result", [])
    if entries:
        e = entries[0]
        ts = e.get("sys_created_on", "")
        author = e.get("sys_created_by", "")
        content = _strip_html(e.get("value", ""))
        preview = content[:200] + ("..." if len(content) > 200 else "")
        print(f"  Posted at: {ts}")
        print(f"  By:        {author}")
        print(f"  Content:   {preview}")


def cmd_activities(args, cookie_header, g_ck):
    table = _resolve_table_from_number(args.number)
    record = _get_by_number(table, args.number.upper(), cookie_header, g_ck, fields="sys_id,number")
    sys_id = record.get("sys_id", "")

    query_parts = [f"element_id={sys_id}"]
    if args.type == "external":
        query_parts.append("element=comments")
    elif args.type == "internal":
        query_parts.append("element=work_notes")
    else:
        query_parts.append("elementINcomments,work_notes")
    if args.since:
        query_parts.append(f"sys_created_on>={args.since}")
    query_parts.append("ORDERBYDESCsys_created_on")
    query = "^".join(query_parts)

    params = urllib.parse.urlencode({
        "sysparm_query": query,
        "sysparm_limit": str(args.limit),
        "sysparm_fields": "sys_created_on,element,value,sys_created_by",
    })
    url = f"{API_BASE}/{TABLE_JOURNAL}?{params}"
    code, body = make_request(url, cookie_header, g_ck)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    entries = _safe_json(body).get("result", [])

    if args.json:
        print(json.dumps(entries, indent=2))
        return

    print(f"Activities for {args.number.upper()}: {len(entries)}\n")
    if not entries:
        return

    for e in entries:
        ts = e.get("sys_created_on", "")
        element = e.get("element", "")
        label = "Comment" if element == "comments" else "Work Note"
        author = e.get("sys_created_by", "")
        content = _strip_html(e.get("value", ""))
        preview = content[:150] + ("..." if len(content) > 150 else "")
        print(f"  [{ts}] {label} by {author}")
        print(f"    {preview}")
        print()


TABLE_SYS_CHOICE = "sys_choice"

FIELD_LABEL_MAP = {
    "close_code": "Resolution Category",
    "u_symptom": "Resolution Subcategory",
    "u_affected_area": "Affected area",
    "u_error_subcategory": "Affected sub-area",
    "state": "State",
    "category": "Category",
    "subcategory": "Subcategory",
    "priority": "Priority",
    "impact": "Impact",
    "urgency": "Urgency",
}

FORM_URL_TEMPLATES = {
    TABLE_INCIDENT: "{base}/incident.do?sys_id={sys_id}",
    TABLE_CASE: "{base}/sn_customerservice_case.do?sys_id={sys_id}",
    TABLE_CHANGE: "{base}/change_request.do?sys_id={sys_id}",
}


def _fetch_ui_meta(table, cookie_header, g_ck):
    url = f"{SNOW_BASE}/api/now/ui/meta/{table}"
    code, body = make_request(url, cookie_header, g_ck)
    if code >= 400:
        _print_api_error(code, body)
        sys.exit(1)
    return _safe_json(body)


def _fetch_scratchpad(table, sys_id, cookie_header):
    tpl = FORM_URL_TEMPLATES.get(table)
    if not tpl:
        return None
    url = tpl.format(base=SNOW_BASE, sys_id=sys_id)
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie_header)
    req.add_header("User-Agent", USER_AGENT)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        final_url = resp.url
        if "accounts.sap.com" in final_url or "login" in final_url.split("?")[0].lower():
            return None
        html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None
    m = re.search(r"var g_scratchpad\s*=\s*JSON\.parse\('(.+?)'\);", html, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).replace("\\'", "'").replace("\\\\", "\\").replace('\\"', '"')
    try:
        return json.loads(raw)
    except Exception:
        return None


def _resolve_choices_from_scratchpad(sp, field, depends_on=None):
    if not sp:
        return None

    active_map = {}
    for key in ("activeResolCategory", "activeResolSubCategory", "activeAffected_area", "activeAffected_subarea"):
        try:
            for item in json.loads(sp.get(key, "[]")):
                active_map[item["value"]] = item["label"]
        except (json.JSONDecodeError, KeyError):
            pass

    if field == "close_code":
        allowed = [v for v in sp.get("ResolCategory_str", "").split(",") if v and v != "none"]
        return [{"label": active_map.get(v, v), "value": v} for v in allowed]

    if field == "u_symptom":
        wcc = sp.get("wrapedCategoryChoices", "")
        if sp.get("dependentCategory") == "true" and wcc:
            data = json.loads(wcc).get("data", [])
            if depends_on:
                for item in data:
                    if item["parent_value"] == depends_on:
                        return [{"label": c["label"], "value": c["value"]} for c in item.get("Child_set", [])]
                return []
            result = []
            for item in data:
                parent_label = active_map.get(item["parent_value"], item["parent_value"])
                for c in item.get("Child_set", []):
                    result.append({"label": c["label"], "value": c["value"], "parent": parent_label})
            return result
        allowed = [v for v in sp.get("ResolSubCategory_str", "").split(",") if v]
        return [{"label": active_map.get(v, v), "value": v} for v in allowed]

    if field == "u_affected_area":
        allowed = [v for v in sp.get("affected_area_str", "").split(",") if v and v != "none"]
        return [{"label": active_map.get(v, v), "value": v} for v in allowed]

    if field == "u_error_subcategory":
        allowed = [v for v in sp.get("affected_subarea_str", "").split(",") if v and v != "none"]
        return [{"label": active_map.get(v, v), "value": v} for v in allowed]

    return None


def cmd_choices(args, cookie_header, g_ck):
    table = args.table
    field = args.field

    if args.record:
        record = _get_by_number(table, args.record.upper(), cookie_header, g_ck, fields="sys_id,number")
        sys_id = record.get("sys_id", "")
        sp = _fetch_scratchpad(table, sys_id, cookie_header)
        choices = _resolve_choices_from_scratchpad(sp, field, depends_on=args.depends_on)
        if choices is not None:
            if args.json:
                print(json.dumps(choices, indent=2))
                return
            label = FIELD_LABEL_MAP.get(field, field)
            record_num = args.record.upper()
            dep_note = f" for {args.depends_on}" if args.depends_on else ""
            print(f"{label}{dep_note} ({record_num}): {len(choices)} values\n")
            for c in choices:
                parent = c.get("parent", "")
                parent_str = f"  ({parent})" if parent else ""
                print(f"  {c['label']:<50} [{c['value']}]{parent_str}")
            return

    meta = _fetch_ui_meta(table, cookie_header, g_ck)
    columns = meta.get("result", {}).get("columns", {})

    if field not in columns:
        print(f"ERROR: Field '{field}' not found in {table} metadata.", file=sys.stderr)
        available = [k for k, v in columns.items() if v.get("type") == "choice" or "choices" in v or "choiceList" in v]
        if available:
            print(f"Choice fields: {', '.join(sorted(available)[:20])}", file=sys.stderr)
        sys.exit(1)

    col = columns[field]
    choices = col.get("choices", col.get("choiceList", []))
    if not isinstance(choices, list):
        choices = []

    if args.depends_on:
        dep_val = args.depends_on
        choices = [c for c in choices if dep_val in c.get("parameters", {}).get("dependent_values", [])]

    choices = [c for c in choices if c.get("value") != ""]

    if args.json:
        print(json.dumps(choices, indent=2))
        return

    label = FIELD_LABEL_MAP.get(field, field)
    dep_note = f" (filtered by depends_on={args.depends_on})" if args.depends_on else ""
    print(f"Choices for {table}.{field} ({label}){dep_note}: {len(choices)} values\n")
    for c in choices:
        dep_vals = c.get("parameters", {}).get("dependent_values", [])
        dep_str = f"  (depends on: {', '.join(dep_vals)})" if dep_vals and dep_vals != [""] else ""
        print(f"  {c['label']:<50} [{c['value']}]{dep_str}")


# ─── Argument parser ─────────────────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(description="SAP ServiceNow ITSM CLI", prog="snow.py")
    parser.add_argument("--cookie-dir", help="Cookie directory containing sap_cookies.txt (default: ~/.sap-mcp/cookies/sap-snow)")
    sub = parser.add_subparsers(dest="command")

    # myself
    p = sub.add_parser("myself", help="Show current user info")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # choices
    p = sub.add_parser("choices", help="List allowed values for a field")
    p.add_argument("table", help="Table name (e.g., incident, sn_customerservice_case, change_request)")
    p.add_argument("field", help="Field name (e.g., close_code, u_symptom, u_affected_area, state)")
    p.add_argument("--record", help="Record number (e.g., INC25205115) for context-aware filtering")
    p.add_argument("--depends-on", help="Filter by dependent value (e.g., close_code value to filter u_symptom)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # incident-get
    p = sub.add_parser("incident-get", help="Get incident details")
    p.add_argument("number", help="Incident number (e.g., INC16970266)")
    p.add_argument("--full", action="store_true", help="Show full description without truncation")
    p.add_argument("--json", action="store_true", help="Output raw API JSON")
    p.add_argument("--field", help="Extract a single field value (dot notation for nested, e.g., assigned_to.display_value)")
    p.add_argument("--related", action="store_true", help="Also show linked parent case details")
    p.add_argument("--escalations", action="store_true", help="Show escalation references from activity history")

    # incident-search
    p = sub.add_parser("incident-search", help="Search incidents")
    p.add_argument("query", nargs="?", help="ServiceNow encoded query")
    p.add_argument("--my-open", action="store_true", help="My open incidents (New, In Progress, On Hold, Awaiting Info)")
    p.add_argument("--my-assigned", action="store_true", help="All incidents assigned to me")
    p.add_argument("--component", help="Filter by app component (u_app_component)")
    p.add_argument("--priority", dest="priority_filter", help="Filter by priority (1-5)")
    p.add_argument("--since", help="Opened after date (YYYY-MM-DD)")
    p.add_argument("--group", help="Filter by assignment group")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # incident-create
    p = sub.add_parser("incident-create", help="Create an incident")
    p.add_argument("--short-description", required=True, help="Short description (required)")
    p.add_argument("--description", help="Full description")
    p.add_argument("--category", help="Category")
    p.add_argument("--subcategory", help="Subcategory")
    p.add_argument("--assignment-group", help="Assignment group name")
    p.add_argument("--assigned-to", help="Assigned to (username or display name)")
    p.add_argument("--priority", help="Priority (1-5)")
    p.add_argument("--impact", help="Impact (1-3)")
    p.add_argument("--urgency", help="Urgency (1-3)")
    p.add_argument("--caller", help="Caller (username or display name)")

    # incident-update
    p = sub.add_parser("incident-update", help="Update an incident")
    p.add_argument("number", help="Incident number")
    p.add_argument("--state", help="New state (-3=Awaiting Info, 1=New, 2=In Progress, 3=On Hold, 6=Resolved, 7=Closed, 8=Canceled)")
    p.add_argument("--priority", help="Priority (1-5)")
    p.add_argument("--impact", help="Impact (1-3)")
    p.add_argument("--urgency", help="Urgency (1-3)")
    p.add_argument("--assignment-group", help="Assignment group")
    p.add_argument("--assigned-to", help="Assigned to")
    p.add_argument("--category", help="Category")
    p.add_argument("--close-code", help="Resolution category (required for resolve)")
    p.add_argument("--close-notes", help="Resolution notes (required for resolve)")
    p.add_argument("--resolution-subcategory", help="Resolution subcategory / u_symptom (required for resolve)")
    p.add_argument("--affected-area", help="Affected area / u_affected_area (required for resolve)")
    p.add_argument("--comment", help="Comment (required for Awaiting Info / In Progress transitions)")

    # incident-comment
    p = sub.add_parser("incident-comment", help="Add a work note to an incident")
    p.add_argument("number", help="Incident number")
    p.add_argument("text", help="Work note text")
    p.add_argument("--public", action="store_true", help="Post as customer-visible comment instead of internal work note")

    # case-get
    p = sub.add_parser("case-get", help="Get case details")
    p.add_argument("number", help="Case number (e.g., CS20230005856530)")
    p.add_argument("--full", action="store_true", help="Show full description without truncation")
    p.add_argument("--json", action="store_true", help="Output raw API JSON")
    p.add_argument("--field", help="Extract a single field value (dot notation for nested, e.g., assigned_to.display_value)")
    p.add_argument("--incidents", action="store_true", help="Also show child incidents linked to this case")

    # case-search
    p = sub.add_parser("case-search", help="Search cases")
    p.add_argument("query", nargs="?", help="ServiceNow encoded query")
    p.add_argument("--my-open", action="store_true", help="My open cases (New, In Progress, Awaiting Info)")
    p.add_argument("--my-assigned", action="store_true", help="All cases assigned to me")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # case-create
    p = sub.add_parser("case-create", help="Create a case")
    p.add_argument("--short-description", required=True, help="Short description (required)")
    p.add_argument("--description", help="Full description")
    p.add_argument("--category", help="Category")
    p.add_argument("--subcategory", help="Subcategory")
    p.add_argument("--assignment-group", help="Assignment group name")
    p.add_argument("--assigned-to", help="Assigned to")
    p.add_argument("--priority", help="Priority (1-5)")
    p.add_argument("--contact", help="Contact (username or display name)")

    # case-update
    p = sub.add_parser("case-update", help="Update a case")
    p.add_argument("number", help="Case number")
    p.add_argument("--state", help="New state (1=New, 10=In Progress, 18=Awaiting Info, 6=Resolved, 3=Closed)")
    p.add_argument("--priority", help="Priority (1-5)")
    p.add_argument("--impact", help="Impact (1-3)")
    p.add_argument("--urgency", help="Urgency (1-3)")
    p.add_argument("--assignment-group", help="Assignment group")
    p.add_argument("--assigned-to", help="Assigned to")
    p.add_argument("--category", help="Category")
    p.add_argument("--comment", help="Comment (required for Awaiting Info / In Progress transitions)")

    # case-comment
    p = sub.add_parser("case-comment", help="Add a work note to a case")
    p.add_argument("number", help="Case number")
    p.add_argument("text", help="Work note text")
    p.add_argument("--public", action="store_true", help="Post as customer-visible comment instead of internal work note")

    # change-get
    p = sub.add_parser("change-get", help="Get change request details")
    p.add_argument("number", help="Change request number (e.g., CHG13854754)")
    p.add_argument("--full", action="store_true", help="Show full description without truncation")
    p.add_argument("--json", action="store_true", help="Output raw API JSON")
    p.add_argument("--field", help="Extract a single field value (dot notation for nested, e.g., assigned_to.display_value)")

    # change-search
    p = sub.add_parser("change-search", help="Search change requests")
    p.add_argument("query", nargs="?", help="ServiceNow encoded query")
    p.add_argument("--my-open", action="store_true", help="My open change requests")
    p.add_argument("--my-assigned", action="store_true", help="All change requests assigned to me")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # change-update
    p = sub.add_parser("change-update", help="Update a change request")
    p.add_argument("number", help="Change request number")
    p.add_argument("--state", help="New state")
    p.add_argument("--priority", help="Priority (1-5)")
    p.add_argument("--risk", help="Risk level")
    p.add_argument("--impact", help="Impact (1-3)")
    p.add_argument("--assignment-group", help="Assignment group")
    p.add_argument("--assigned-to", help="Assigned to")
    p.add_argument("--category", help="Category")
    p.add_argument("--comment", help="Comment (required for Awaiting Info / In Progress transitions)")

    # change-comment
    p = sub.add_parser("change-comment", help="Add a work note to a change request")
    p.add_argument("number", help="Change request number")
    p.add_argument("text", help="Work note text")
    p.add_argument("--public", action="store_true", help="Post as customer-visible comment instead of internal work note")

    # prb-get (problem)
    p = sub.add_parser("prb-get", help="Get problem (PRB) details")
    p.add_argument("number", help="Problem number (e.g., PRB0040123)")
    p.add_argument("--full", action="store_true", help="Show full description without truncation")
    p.add_argument("--json", action="store_true", help="Output raw API JSON")
    p.add_argument("--field", help="Extract a single field value (dot notation for nested)")
    p.add_argument("--tasks", action="store_true", help="Also list child problem tasks (PTASK)")

    # prb-search
    p = sub.add_parser("prb-search", help="Search problems")
    p.add_argument("query", nargs="?", help="ServiceNow encoded query")
    p.add_argument("--my-open", action="store_true", help="My open problems")
    p.add_argument("--my-assigned", action="store_true", help="All problems assigned to me")
    p.add_argument("--component", help="Filter by app component (u_app_component)")
    p.add_argument("--priority", dest="priority_filter", help="Filter by priority (1-5)")
    p.add_argument("--since", help="Opened after date (YYYY-MM-DD)")
    p.add_argument("--group", help="Filter by assignment group")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # ptask-get (problem_task)
    p = sub.add_parser("ptask-get", help="Get problem task (PTASK) details")
    p.add_argument("number", help="Problem task number (e.g., PTASK0040123)")
    p.add_argument("--full", action="store_true", help="Show full description without truncation")
    p.add_argument("--json", action="store_true", help="Output raw API JSON")
    p.add_argument("--field", help="Extract a single field value (dot notation for nested)")
    p.add_argument("--related", action="store_true", help="Also show parent problem (PRB) details")

    # ptask-search
    p = sub.add_parser("ptask-search", help="Search problem tasks")
    p.add_argument("query", nargs="?", help="ServiceNow encoded query")
    p.add_argument("--my-open", action="store_true", help="My open problem tasks")
    p.add_argument("--my-assigned", action="store_true", help="All problem tasks assigned to me")
    p.add_argument("--problem", help="Filter by parent problem number (e.g., PRB0040123)")
    p.add_argument("--priority", dest="priority_filter", help="Filter by priority (1-5)")
    p.add_argument("--since", help="Opened after date (YYYY-MM-DD)")
    p.add_argument("--group", help="Filter by assignment group")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # attachments
    p = sub.add_parser("attachments", help="List attachments for a record")
    p.add_argument("number", help="Record number (INC/CS/CHG prefix)")
    p.add_argument("--download-all", action="store_true", help="Download all attachments")
    p.add_argument("--output-dir", help="Directory for downloads (default: current dir)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # attachment-download
    p = sub.add_parser("attachment-download", help="Download a single attachment by sys_id")
    p.add_argument("sys_id", help="Attachment sys_id")
    p.add_argument("--output-dir", help="Directory for download (default: current dir)")

    # attachment-upload
    p = sub.add_parser("attachment-upload", help="Upload a file attachment to a record")
    p.add_argument("number", help="Record number (INC/CS/CHG prefix)")
    p.add_argument("file", help="Path to file to upload")
    p.add_argument("--name", help="Override filename (default: basename of path)")

    # activities
    p = sub.add_parser("activities", help="View activity/comment history for a record")
    p.add_argument("number", help="Record number (INC/CS/CHG prefix)")
    p.add_argument("--limit", type=int, default=10, help="Max entries (default 10)")
    p.add_argument("--since", help="Only entries after this date (YYYY-MM-DD)")
    p.add_argument("--type", choices=["external", "internal", "all"], default="all", help="Filter by comment type")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # api-get
    p = sub.add_parser("api-get", help="Query any ServiceNow table directly")
    p.add_argument("table", help="Table name (e.g., task_sla, sys_ui_action, cmdb_ci)")
    p.add_argument("--query", help="Encoded query string (e.g., 'task.number=INC26089000')")
    p.add_argument("--fields", help="Comma-separated field list")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")

    return parser


def main():
    global COOKIE_DIR
    parser = build_parser()
    args = parser.parse_args()

    if args.cookie_dir:
        COOKIE_DIR = os.path.expanduser(args.cookie_dir)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cookie_header = load_cookies()
    g_ck = _fetch_session_info(cookie_header)

    dispatch = {
        "myself": cmd_myself,
        "choices": cmd_choices,
        "incident-get": cmd_incident_get,
        "incident-search": cmd_incident_search,
        "incident-create": cmd_incident_create,
        "incident-update": cmd_incident_update,
        "incident-comment": cmd_incident_comment,
        "case-get": cmd_case_get,
        "case-search": cmd_case_search,
        "case-create": cmd_case_create,
        "case-update": cmd_case_update,
        "case-comment": cmd_case_comment,
        "change-get": cmd_change_get,
        "change-search": cmd_change_search,
        "change-update": cmd_change_update,
        "change-comment": cmd_change_comment,
        "prb-get": cmd_problem_get,
        "prb-search": cmd_problem_search,
        "ptask-get": cmd_problem_task_get,
        "ptask-search": cmd_problem_task_search,
        "attachments": cmd_attachments,
        "attachment-download": cmd_attachment_download,
        "attachment-upload": cmd_attachment_upload,
        "activities": cmd_activities,
        "api-get": cmd_api_get,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args, cookie_header, g_ck)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
