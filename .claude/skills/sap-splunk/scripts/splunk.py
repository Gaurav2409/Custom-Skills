#!/usr/bin/env python3
"""SuccessFactors Splunk search — stdlib only, cookie-based auth via sap-authentication skill.

Usage:
    python3 splunk.py search <SPL_QUERY> [--earliest -1h] [--latest now] [--limit 50] [--timeout 120] [--output /tmp/results.json] [--instance orf]
    python3 splunk.py jobs [--instance orf]
    python3 splunk.py results <SID> [--limit 100] [--offset 0] [--instance orf]
    python3 splunk.py status <SID> [--instance orf]
    python3 splunk.py cancel <SID> [--instance orf]
    python3 splunk.py open <SPL_QUERY> [--earliest -1h] [--latest now] [--instance orf]
    python3 splunk.py info [--instance orf]

Options:
    --cookie-dir DIR    — base cookie directory (default: ~/.sap-mcp/cookies/sap-splunk)
    SPLUNK_INSTANCE     — env var for default instance (default: orf)
    SPLUNK_TZ_OFFSET    — Splunk user timezone offset in hours from UTC (default: auto-detected)
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone

# ─── Configuration ───────────────────────────────────────────────────────────
DEFAULT_COOKIE_DIR = os.path.expanduser("~/.sap-mcp/cookies/sap-splunk")
COOKIE_DIR = None  # Set from --cookie-dir argument or default
HELPER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "load-cookies.mjs")

def _detect_system_tz_offset():
    """Auto-detect local timezone offset from UTC in hours."""
    now = datetime.now()
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    offset_seconds = (now - utc_now).total_seconds()
    return round(offset_seconds / 3600)

# Splunk user timezone offset: env var > auto-detect from system locale
_tz_env = os.environ.get("SPLUNK_TZ_OFFSET")
SPLUNK_TZ_OFFSET = int(_tz_env) if _tz_env is not None else _detect_system_tz_offset()

INSTANCES = {
    # Cross-DC — ORF connects to all DC indexers (2,200+ indexes, 37 DCs). Use for prod/cross-DC queries.
    "orf":    {"url": "https://orf.cld.ondemand.com"},
    # Americas
    "dc01": {"url": "https://cloudsearch-dc01.cld.ondemand.com"},  # QA
    "dc32": {"url": "https://cloudsearch-dc32.cld.ondemand.com"},
    "dc41": {"url": "https://cloudsearch-dc41.cld.ondemand.com"},
    "dc43": {"url": "https://cloudsearch-dc43.cld.ondemand.com"},
    "dc47": {"url": "https://cloudsearch-dc47.cld.ondemand.com"},
    "dc49": {"url": "https://cloudsearch-dc49.cld.ondemand.com"},
    "dc60": {"url": "https://cloudsearch-dc60.cld.ondemand.com"},  # OSK Target of DC17
    "dc61": {"url": "https://cloudsearch-dc61.cld.ondemand.com"},
    "dc62": {"url": "https://cloudsearch-dc62.cld.ondemand.com"},  # OSK Target of DC19
    "dc64": {"url": "https://cloudsearch-dc64.cld.ondemand.com"},  # OSK Target of DC14-NSQ
    "dc68": {"url": "https://cloudsearch-dc68.cld.ondemand.com"},  # OSK Target of DC04
    "dc70": {"url": "https://cloudsearch-dc70.cld.ondemand.com"},  # OSK Target of DC08
    "dc71": {"url": "https://cloudsearch-dc71.cld.ondemand.com"},
    # EMEA
    "dc22": {"url": "https://cloudsearch-dc22.cld.ondemand.com"},
    "dc23": {"url": "https://cloudsearch-dc23.cld.ondemand.com"},
    "dc25": {"url": "https://cloudsearch-dc25.cld.ondemand.com"},  # QA
    "dc33": {"url": "https://cloudsearch-dc33.cld.ondemand.com"},  # OSK Target of DC12
    "dc34": {"url": "https://cloudsearch-dc34.cld.ondemand.com"},
    "dc55": {"url": "https://cloudsearch-dc55.cld.ondemand.com"},
    "dc56": {"url": "https://cloudsearch-dc56.cld.ondemand.com"},
    "dc57": {"url": "https://cloudsearch-dc57.cld.ondemand.com"},  # OSK Target of DC02
    "dc58": {"url": "https://cloudsearch-dc58.cld.ondemand.com"},
    "dc74": {"url": "https://cloudsearch-dc74.cld.ondemand.com"},
    "dc75": {"url": "https://cloudsearch-dc75.cld.ondemand.com"},
    "dc82": {"url": "https://cloudsearch-dc82.cld.ondemand.com"},
    "dc83": {"url": "https://cloudsearch-dc83.cld.ondemand.com"},
    "dc84": {"url": "https://cloudsearch-dc84.cld.ondemand.com"},
    "dc85": {"url": "https://cloudsearch-dc85.cld.ondemand.com"},
    # APAC
    "dc30": {"url": "https://cloudsearch-dc30.cld.ondemand.com"},  # OSK Target of DC15
    "dc50": {"url": "https://cloudsearch-dc50.cld.ondemand.com"},
    "dc51": {"url": "https://cloudsearch-dc51.cld.ondemand.com"},
    "dc52": {"url": "https://cloudsearch-dc52.cld.ondemand.com"},  # OSK Target of DC44
    "dc66": {"url": "https://cloudsearch-dc66.cld.ondemand.com"},  # OSK Target of DC10
    "dc67": {"url": "https://cloudsearch-dc67.cld.ondemand.com"},
    "dc80": {"url": "https://cloudsearch-dc80.cld.ondemand.com"},
    "dc81": {"url": "https://cloudsearch-dc81.cld.ondemand.com"},
}
DEFAULT_INSTANCE = os.environ.get("SPLUNK_INSTANCE", "orf")

# DCs whose Splunk web frontend is misconfigured (Splunk listens on plain port 80
# behind an SSL-offloading LB and emits Location: http://... redirects with no
# X-Forwarded-Proto trust). The REST API itself works fine — but cookies cannot
# be obtained: SSO via the sap-authentication skill drives a Playwright browser
# whose Chromium has HttpsUpgrades disabled, so it follows the http:// downgrade
# into a firewalled port 80 and stalls. See references/known-issues.md.
UNSUPPORTED_INSTANCES = {
    "dc22", "dc25", "dc33", "dc34", "dc52",
    "dc55", "dc80", "dc81", "dc82", "dc84",
}

_warned_unsupported = set()

# ─── Time conversion ────────────────────────────────────────────────────────

def _convert_utc_to_splunk(time_str, tz_offset_hours=None):
    """Convert an absolute UTC time string to Splunk server local time.

    tz_offset_hours: offset from UTC (e.g. 8 for UTC+8). Defaults to SPLUNK_TZ_OFFSET.
    Handles formats (with or without trailing Z or +00:00):
      2026-04-08T13:39:20Z  → 2026-04-08T21:39:20
      2026-04-08T13:39:20   → 2026-04-08T21:39:20
      2026-04-08 13:39:20   → 2026-04-08 21:39:20
      2026-04-08T13:39      → 2026-04-08T21:39
    Relative times (-1h, -15m, now, @d) are returned unchanged.
    """
    s = time_str.strip()
    if tz_offset_hours is None:
        tz_offset_hours = SPLUNK_TZ_OFFSET
    # Relative times: pass through
    if s.startswith("-") or s.startswith("+") or s in ("now",) or s.startswith("@"):
        return s

    # Strip UTC markers (Z, +00:00, -00:00, +0000, -0000) — these all mean UTC
    # Do NOT strip non-zero offsets like +08:00 — that would silently discard timezone info
    s_clean = re.sub(r'[Zz]$', '', s)
    s_clean = re.sub(r'[+-]00:?00$', '', s_clean)
    # Also strip fractional seconds (.123456789)
    s_clean = re.sub(r'\.\d+', '', s_clean)

    offset = timedelta(hours=tz_offset_hours)

    # Try to parse absolute timestamps
    for fmt, out_fmt in [
        ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S"),
        ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"),
        ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M"),
        ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M"),
        ("%Y-%m-%d", "%Y-%m-%d"),
    ]:
        try:
            dt = datetime.strptime(s_clean, fmt)
            dt_local = dt + offset
            return dt_local.strftime(out_fmt)
        except ValueError:
            continue

    # Check if stripping failed because a non-UTC offset remained (e.g. +08:00)
    offset_match = re.search(r'[+-]\d{2}:?\d{2}$', s_clean)
    if offset_match:
        print(f"WARNING: --utc flag is for UTC timestamps, but '{time_str}' has offset {offset_match.group()}. "
              f"Stripping offset and treating as UTC.", file=sys.stderr)
        s_clean = s_clean[:offset_match.start()]
        s_clean = re.sub(r'\.\d+', '', s_clean)
        for fmt, out_fmt in [
            ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S"),
            ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"),
            ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M"),
            ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M"),
            ("%Y-%m-%d", "%Y-%m-%d"),
        ]:
            try:
                dt = datetime.strptime(s_clean, fmt)
                dt_local = dt + timedelta(hours=tz_offset_hours)
                return dt_local.strftime(out_fmt)
            except ValueError:
                continue

    # Not recognized — warn and return as-is
    print(f"WARNING: --utc could not parse timestamp '{time_str}', passing through unchanged.", file=sys.stderr)
    return s


def _resolve_time_args(args):
    """If --utc flag is set, convert earliest/latest from UTC to Splunk server time."""
    if getattr(args, "utc", False):
        args.earliest = _convert_utc_to_splunk(args.earliest, SPLUNK_TZ_OFFSET)
        args.latest = _convert_utc_to_splunk(args.latest, SPLUNK_TZ_OFFSET)
    return args

# ─── Cookie handling ─────────────────────────────────────────────────────────

def _get_cookie_dir(instance=None):
    """Return per-instance cookie directory: {base}-{instance}/"""
    base_dir = COOKIE_DIR or DEFAULT_COOKIE_DIR
    inst = instance or DEFAULT_INSTANCE
    return f"{base_dir}-{inst}"


def _print_auth_error(reason, instance=None):
    """Print structured auth error directing to sap-authentication skill."""
    cookie_dir = _get_cookie_dir(instance)
    base_url = get_base_url(instance) if instance else get_base_url(DEFAULT_INSTANCE)
    print(f"ERROR: {reason}.", file=sys.stderr)
    print(f"Invoke the sap-authentication skill with:", file=sys.stderr)
    print(f"  entry_url: {base_url}/", file=sys.stderr)
    print(f"  store_path: {cookie_dir}", file=sys.stderr)


def load_cookies(instance=None):
    """Load cookies via load-cookies.mjs helper.

    Helper handles plain text, AES-GCM encrypted files (DECRYPT_KEY env), and
    24h expiry checks. Each Splunk instance has its own cookie directory:
      - Default instance: {COOKIE_DIR}/sap_cookies.txt
      - Other instances: {COOKIE_DIR}-{instance}/sap_cookies.txt
    """
    cookie_dir = _get_cookie_dir(instance)
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
        base_url = get_base_url(instance or DEFAULT_INSTANCE)
        print("Invoke the sap-authentication skill with:", file=sys.stderr)
        print(f"  entry_url: {base_url}/", file=sys.stderr)
        print(f"  store_path: {cookie_dir}", file=sys.stderr)
        sys.exit(1)

    cookie_header = result.stdout.strip()
    if not cookie_header:
        print("ERROR: Cookie file is empty.", file=sys.stderr)
        sys.exit(1)

    return cookie_header


def _extract_csrf_token(cookie_header):
    """Extract the splunkweb_csrf_token from the Cookie header string.

    Splunk requires this token as X-Splunk-Form-Key header for POST requests.
    The cookie is named splunkweb_csrf_token_<port> (commonly splunkweb_csrf_token_80).
    """
    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if pair.startswith("splunkweb_csrf_token"):
            _, _, value = pair.partition("=")
            return value.strip()
    return None


def get_base_url(instance):
    """Resolve Splunk base URL from instance name."""
    inst = instance.lower()
    if inst in UNSUPPORTED_INSTANCES and inst not in _warned_unsupported:
        _warned_unsupported.add(inst)
        print(
            f"WARNING: Splunk instance '{inst}' is in the unsupported list.\n"
            f"  SSO authentication on this DC requires the opt-in HttpsUpgrades hack\n"
            f"  (see README → sap-splunk → 'Known Issue: Querying unsupported DCs directly').\n"
            f"  If the hack is not configured, this command will hang during authentication.\n"
            f"  Easiest path: re-run with '--instance orf' (cross-DC, indexes all 37+ DCs).",
            file=sys.stderr,
        )
    if inst in INSTANCES:
        return INSTANCES[inst]["url"]
    # Allow custom full URL
    if inst.startswith("https://"):
        return inst.rstrip("/")
    print(f"ERROR: Unknown instance '{instance}'. Use: {', '.join(INSTANCES.keys())} or a full URL.", file=sys.stderr)
    sys.exit(1)



# ─── HTTP helpers ────────────────────────────────────────────────────────────

class _HttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Force http:// redirects back to https:// — Splunk often issues http 303s."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl.startswith("http://"):
            newurl = "https://" + newurl[7:]
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener():
    ctx = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),  # bypass proxy — BigIP/F5 intercepts proxied requests
        _HttpsRedirectHandler,
        urllib.request.HTTPSHandler(context=ctx),
    )


def make_request(url, cookie_header, method="GET", data=None, accept="application/json", timeout=30, instance=None):
    """Make an authenticated HTTP request to Splunk."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Cookie", cookie_header)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    req.add_header("Accept", accept)

    # Always send CSRF + XMLHttpRequest headers (some instances like ORF require them for all requests)
    csrf = _extract_csrf_token(cookie_header)
    if csrf:
        req.add_header("X-Splunk-Form-Key", csrf)
        req.add_header("X-Requested-With", "XMLHttpRequest")

    if data is not None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.data = data

    reauth_url = (get_base_url(instance) + "/") if instance else None
    opener = _build_opener()
    try:
        resp = opener.open(req, timeout=timeout)
        # Detect auth redirects (SSO login page)
        if "login" in resp.url.lower() and "microsoftonline" not in url.lower():
            _print_auth_error("Login redirect detected", instance)
            sys.exit(1)
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code in (401, 403):
            _print_auth_error(f"HTTP {e.code} — authentication failed", instance)
            sys.exit(1)
        return e.code, body, {}
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def make_request_stream(url, cookie_header, timeout=120, instance=None):
    """Make an authenticated HTTP request and return the response object for streaming.

    Caller is responsible for reading and closing the response.
    Returns (status, response_obj) or exits on auth failure.
    """
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie_header)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    req.add_header("Accept", "application/json")
    # Always send CSRF + XMLHttpRequest headers (some instances like ORF require them)
    csrf = _extract_csrf_token(cookie_header)
    if csrf:
        req.add_header("X-Splunk-Form-Key", csrf)
        req.add_header("X-Requested-With", "XMLHttpRequest")

    reauth_url = (get_base_url(instance) + "/") if instance else None
    opener = _build_opener()
    try:
        resp = opener.open(req, timeout=timeout)
        if "login" in resp.url.lower() and "microsoftonline" not in url.lower():
            _print_auth_error("Login redirect detected", instance)
            sys.exit(1)
        return resp.status, resp
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _print_auth_error(f"HTTP {e.code} — authentication failed", instance)
            sys.exit(1)
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"ERROR: HTTP {e.code}", file=sys.stderr)
        _print_error_detail(body)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ─── Splunk API functions ────────────────────────────────────────────────────

def cmd_info(args):
    """Show Splunk instance info and cookie status."""
    base = get_base_url(args.instance)
    cookie_dir = _get_cookie_dir(args.instance)
    cookie_file = os.path.join(cookie_dir, "sap_cookies.txt")
    print(f"Instance:   {args.instance} ({base})")
    print(f"Cookie dir: {cookie_dir}")
    print(f"Cookie file: {cookie_file}")

    # Check cookie status
    try:
        cookie_header = load_cookies(instance=args.instance)
        print(f"Cookies:    OK (loaded)")
    except SystemExit:
        print(f"Cookies:    MISSING or EXPIRED")
        return

    # Try to reach Splunk
    url = f"{base}/en-US/splunkd/__raw/services/server/info?output_mode=json"
    status, body, _ = make_request(url, cookie_header, instance=args.instance)
    if status == 200:
        try:
            info = json.loads(body)
            entry = info.get("entry", [{}])[0].get("content", {})
            print(f"Server:     {entry.get('serverName', 'unknown')}")
            print(f"Version:    {entry.get('version', 'unknown')}")
            print(f"Build:      {entry.get('build', 'unknown')}")
        except (json.JSONDecodeError, IndexError):
            print(f"Server:     reachable (status {status})")
    else:
        print(f"Server:     status {status} — may need re-auth")


def _cmd_search_async(args):
    """Run an SPL search via async job and wait for results."""
    _resolve_time_args(args)
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    # Create search job
    params = {
        "search": f"search {args.query}" if not args.query.strip().startswith("|") and not args.query.strip().lower().startswith("search ") else args.query,
        "earliest_time": args.earliest,
        "latest_time": args.latest,
        "max_count": str(args.limit),
        "output_mode": "json",
    }
    url = f"{base}/en-US/splunkd/__raw/services/search/jobs"
    data = urllib.parse.urlencode(params).encode("utf-8")

    timeout = getattr(args, "timeout", 120)
    status, body, _ = make_request(url, cookie_header, method="POST", data=data, timeout=timeout, instance=args.instance)
    if status not in (200, 201):
        print(f"ERROR: Failed to create search job (HTTP {status})", file=sys.stderr)
        _print_error_detail(body)
        sys.exit(1)

    # Extract SID
    sid = _extract_sid(body)
    if not sid:
        print(f"ERROR: Could not parse search job SID from response", file=sys.stderr)
        print(body[:500], file=sys.stderr)
        sys.exit(1)

    print(f"Search job created: {sid}")
    print(f"Query: {params['search']}")
    print(f"Time range: {args.earliest} to {args.latest}")
    print()

    # Poll for completion
    done = _wait_for_job(base, cookie_header, sid, timeout=timeout, instance=args.instance)

    if not done:
        print(f"SID: {sid}", file=sys.stderr)
        sys.exit(1)

    # Fetch results
    _fetch_and_print_results(base, cookie_header, sid, args.limit, timeout=timeout,
                             output_file=getattr(args, "output", None), instance=args.instance)


def cmd_search(args):
    """Run an SPL query. Uses streaming export by default; --async for job-based search."""
    if getattr(args, "async_mode", False):
        return _cmd_search_async(args)

    # Default: streaming export (fast)
    _resolve_time_args(args)
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    query = args.query
    if not query.strip().startswith("|") and not query.strip().lower().startswith("search "):
        query = f"search {query}"

    output_mode = getattr(args, "output_mode", "json")
    print(f"Search: {query}")
    print(f"Time range: {args.earliest} to {args.latest}")
    print()

    timeout = getattr(args, "timeout", 120)
    output_file = getattr(args, "output", None)

    if output_mode == "json":
        results = _run_export_query(base, cookie_header, args.query, args.earliest, args.latest,
                                    limit=args.limit, timeout=timeout, instance=args.instance)

        if not results:
            print("No results.")
            return

        if output_file:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"{len(results)} result(s) written to {output_file}")
        else:
            print(f"--- {len(results)} result(s) ---\n")
            for i, r in enumerate(results[:args.limit]):
                _print_single_result(r, i)
    else:
        # CSV mode — build URL and stream to file or stdout
        params = {
            "search": query,
            "earliest_time": args.earliest,
            "latest_time": args.latest,
            "output_mode": output_mode,
            "count": str(args.limit),
        }
        url = f"{base}/en-US/splunkd/__raw/services/search/jobs/export?{urllib.parse.urlencode(params)}"
        status, resp = make_request_stream(url, cookie_header, timeout=timeout, instance=args.instance)
        try:
            if output_file:
                with open(output_file, "w") as f:
                    for raw_line in resp:
                        f.write(raw_line.decode("utf-8", errors="replace"))
                print(f"Results written to {output_file}")
            else:
                for raw_line in resp:
                    sys.stdout.write(raw_line.decode("utf-8", errors="replace"))
        finally:
            resp.close()



def cmd_jobs(args):
    """List recent search jobs."""
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    url = f"{base}/en-US/splunkd/__raw/services/search/jobs?output_mode=json&count=20"
    status, body, _ = make_request(url, cookie_header, instance=args.instance)
    if status != 200:
        print(f"ERROR: Failed to list jobs (HTTP {status})", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(body)
        entries = data.get("entry", [])
        if not entries:
            print("No recent search jobs found.")
            return
        print(f"{'SID':<50} {'Status':<12} {'Events':<10} {'Created'}")
        print("-" * 100)
        for e in entries:
            c = e.get("content", {})
            sid = c.get("sid", e.get("name", "?"))
            state = c.get("dispatchState", "?")
            events = c.get("eventCount", "?")
            created = e.get("published", "?")
            print(f"{sid:<50} {state:<12} {str(events):<10} {created}")
    except json.JSONDecodeError:
        print("Failed to parse jobs response.", file=sys.stderr)
        print(body[:500])


def cmd_results(args):
    """Fetch results from an existing search job."""
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)
    _fetch_and_print_results(base, cookie_header, args.sid, args.limit, args.offset,
                             output_file=getattr(args, "output", None), instance=args.instance)


def cmd_status(args):
    """Check status of a search job."""
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    url = f"{base}/en-US/splunkd/__raw/services/search/jobs/{urllib.parse.quote(args.sid, safe='')}?output_mode=json"
    status, body, _ = make_request(url, cookie_header, instance=args.instance)
    if status != 200:
        print(f"ERROR: Failed to get job status (HTTP {status})", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(body)
        entry = data.get("entry", [{}])[0]
        c = entry.get("content", {})
        print(f"SID:          {c.get('sid', args.sid)}")
        print(f"State:        {c.get('dispatchState', '?')}")
        print(f"Done:         {c.get('isDone', '?')}")
        print(f"Event count:  {c.get('eventCount', '?')}")
        print(f"Result count: {c.get('resultCount', '?')}")
        print(f"Scan count:   {c.get('scanCount', '?')}")
        print(f"Run duration: {c.get('runDuration', '?')}s")
        print(f"Search:       {c.get('search', '?')}")
    except (json.JSONDecodeError, IndexError):
        print(body[:500])


def cmd_cancel(args):
    """Cancel a running search job."""
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    url = f"{base}/en-US/splunkd/__raw/services/search/jobs/{urllib.parse.quote(args.sid, safe='')}/control"
    data = urllib.parse.urlencode({"action": "cancel"}).encode("utf-8")
    status, body, _ = make_request(url, cookie_header, method="POST", data=data, instance=args.instance)
    if status == 200:
        print(f"Job {args.sid} cancelled.")
    else:
        print(f"ERROR: Failed to cancel (HTTP {status})", file=sys.stderr)
        print(body[:300], file=sys.stderr)
        sys.exit(1)


def cmd_open(args):
    """Generate a Splunk search URL and open it in the default browser."""
    import webbrowser

    _resolve_time_args(args)
    base = get_base_url(args.instance)

    query = args.query
    if not query.strip().startswith("|") and not query.strip().lower().startswith("search "):
        query = f"search {query}"

    params = urllib.parse.urlencode({
        "q": query,
        "earliest": args.earliest,
        "latest": args.latest,
    })
    url = f"{base}/en-US/app/search/search?{params}"

    if getattr(args, "url_only", False):
        print(url)
        return

    print(f"Opening Splunk search in browser...")
    print(f"Instance: {args.instance} ({base})")
    print(f"Query: {query}")
    print(f"Time range: {args.earliest} to {args.latest}")
    print(f"URL: {url}")

    if not webbrowser.open(url):
        print("ERROR: Failed to open browser.", file=sys.stderr)
        sys.exit(1)


def cmd_trace(args):
    """Trace a request by ID — auto-discovers correlation chain and shows full timeline."""
    _resolve_time_args(args)
    base = get_base_url(args.instance)
    cookie_header = load_cookies(instance=args.instance)

    input_id = args.id
    index = getattr(args, "index", "msc_worktech-teams")
    env = getattr(args, "environment", None)
    env_filter = f" environment={env}" if env else ""
    timeout = getattr(args, "timeout", 120)
    output_file = getattr(args, "output", None)
    max_corr_ids = 10

    # ── Phase 1: Discovery — find all related IDs ──
    print(f"Tracing ID: {input_id}")
    print(f"Time range: {args.earliest} to {args.latest}")
    if env:
        print(f"Environment: {env}")
    print(flush=True)

    discovery_spl = (
        f'index="{index}"{env_filter} "{input_id}"'
        f' | rex field=_raw max_match=0 "(?i)(?:x-request-id|requestId|x-sf-request-id)[=:\\"\\s]+(?P<req_id>[A-Za-z0-9-]{{8,}})"'
        f' | rex field=_raw max_match=0 "(?i)(?:x-correlation-id|correlationId|x-sf-correlation-id)[=:\\"\\s]+(?P<corr_id>[A-Za-z0-9-]{{8,}})"'
        f' | stats values(req_id) as request_ids values(corr_id) as correlation_ids count as seed_events'
    )

    print("Phase 1: Discovering related IDs...", file=sys.stderr)
    seed_results = _run_export_query(base, cookie_header, discovery_spl, args.earliest, args.latest,
                                     limit=10, timeout=min(timeout, 60), instance=args.instance)

    if not seed_results:
        print(f"No events found for ID: {input_id}")
        sys.exit(0)

    seed = seed_results[0]
    seed_events = int(seed.get("seed_events", 0))
    if seed_events == 0:
        print(f"No events found for ID: {input_id}")
        sys.exit(0)

    # Parse discovered IDs (Splunk returns multivalue fields as space-separated or lists)
    def _parse_mv(val):
        """Parse a Splunk multivalue field into a set of strings."""
        if not val:
            return set()
        if isinstance(val, list):
            return set(val)
        return set(val.split())

    request_ids = _parse_mv(seed.get("request_ids"))
    correlation_ids = _parse_mv(seed.get("correlation_ids"))

    print(f"  Seed events: {seed_events}", file=sys.stderr)
    if request_ids:
        print(f"  Request IDs: {', '.join(sorted(request_ids))}", file=sys.stderr)
    if correlation_ids:
        print(f"  Correlation IDs: {', '.join(sorted(correlation_ids))}", file=sys.stderr)

    # ── Build trace ID set ──
    all_ids = {input_id}
    all_ids.update(request_ids)
    all_ids.update(correlation_ids)

    if not correlation_ids:
        print("\n  WARNING: No correlation ID found — showing request-scoped events only.", file=sys.stderr)

    if len(correlation_ids) > max_corr_ids:
        print(f"\n  WARNING: {len(correlation_ids)} correlation IDs found, capping at {max_corr_ids}.", file=sys.stderr)
        trimmed = sorted(correlation_ids)[:max_corr_ids]
        all_ids = {input_id} | set(trimmed) | request_ids

    # ── Phase 2: Full trace query ──
    terms = " OR ".join(f'"{v}"' for v in sorted(all_ids))
    trace_spl = (
        f'index="{index}"{env_filter} ({terms})'
        f' | table _time host logger level message'
        f' | sort 0 _time'
    )

    print(f"\nPhase 2: Fetching full trace ({len(all_ids)} ID(s), limit {args.limit})...", file=sys.stderr)
    results = _run_export_query(base, cookie_header, trace_spl, args.earliest, args.latest,
                                limit=args.limit, timeout=timeout, instance=args.instance)

    if not results:
        print("No trace events found.")
        return

    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"{len(results)} trace event(s) written to {output_file}")
    else:
        print(f"\n--- Trace: {len(results)} event(s) ---\n")
        for i, r in enumerate(results[:args.limit]):
            _print_single_result(r, i)


# ─── Internal helpers ────────────────────────────────────────────────────────


def _run_export_query(base, cookie_header, query, earliest, latest, limit=10000, timeout=120, instance=None):
    """Run an export query and return parsed results as list[dict]."""
    if not query.strip().startswith("|") and not query.strip().lower().startswith("search "):
        query = f"search {query}"
    params = {
        "search": query,
        "earliest_time": earliest,
        "latest_time": latest,
        "output_mode": "json",
        "count": str(limit),
    }
    url = f"{base}/en-US/splunkd/__raw/services/search/jobs/export?{urllib.parse.urlencode(params)}"
    status, resp = make_request_stream(url, cookie_header, timeout=timeout, instance=instance)
    results = []
    dropped_lines = 0
    try:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("preview") is True:
                    continue
                if "result" in obj:
                    results.append(obj["result"])
                elif "results" in obj:
                    results.extend(obj["results"])
                else:
                    results.append(obj)
            except json.JSONDecodeError:
                dropped_lines += 1
                continue
    finally:
        resp.close()
    if dropped_lines:
        print(f"WARNING: {dropped_lines} line(s) could not be parsed as JSON and were skipped.", file=sys.stderr)
    return results


def _extract_sid(body):
    """Extract SID from Splunk job creation response (JSON or XML)."""
    # Try JSON first
    try:
        data = json.loads(body)
        return data.get("sid") or data.get("entry", [{}])[0].get("content", {}).get("sid")
    except (json.JSONDecodeError, IndexError, KeyError):
        pass
    # Fallback: XML <sid>...</sid>
    m = re.search(r"<sid>(.*?)</sid>", body)
    if m:
        return m.group(1)
    return None


def _wait_for_job(base, cookie_header, sid, timeout=300, instance=None):
    """Poll until a search job completes. Returns True if done, False if timed out.

    Re-reads cookies from disk each iteration so that if an external process
    (e.g. sap-auth) refreshes them during a long poll, the next request uses
    the fresh ones.
    """
    url = f"{base}/en-US/splunkd/__raw/services/search/jobs/{urllib.parse.quote(sid, safe='')}?output_mode=json"
    start = time.time()
    dots = 0
    current_cookies = cookie_header
    while time.time() - start < timeout:
        status, body, _ = make_request(url, current_cookies, timeout=min(timeout, 30), instance=instance)
        # Reload cookies in case they were refreshed externally
        try:
            current_cookies = load_cookies(instance=instance)
        except SystemExit:
            # Cookie file is missing or expired — re-raise so the caller
            # sees the auth error instead of silently polling with stale cookies.
            raise
        if status != 200:
            print(f"\nERROR: Job status check failed (HTTP {status})", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(body)
            content = data.get("entry", [{}])[0].get("content", {})
            if content.get("isDone"):
                elapsed = time.time() - start
                event_count = content.get("eventCount", 0)
                result_count = content.get("resultCount", 0)
                print(f"\nCompleted in {elapsed:.1f}s — {event_count} events, {result_count} results")
                return True
        except (json.JSONDecodeError, IndexError):
            pass
        # Progress indicator
        dots += 1
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(2)

    print(f"\nWARNING: Job timed out after {timeout}s. Use 'status {sid}' to check later.", file=sys.stderr)
    return False


def _fetch_and_print_results(base, cookie_header, sid, limit=100, offset=0, timeout=30, output_file=None, instance=None):
    """Fetch and display results from a completed search job."""
    params = {
        "output_mode": "json",
        "count": str(limit),
        "offset": str(offset),
    }
    url = f"{base}/en-US/splunkd/__raw/services/search/jobs/{urllib.parse.quote(sid, safe='')}/results?{urllib.parse.urlencode(params)}"

    status, body, _ = make_request(url, cookie_header, timeout=timeout, instance=instance)
    if status != 200:
        print(f"ERROR: Failed to fetch results (HTTP {status})", file=sys.stderr)
        _print_error_detail(body)
        sys.exit(1)

    _print_json_results(body, limit, output_file=output_file)


def _print_single_result(r, index):
    """Pretty-print one Splunk result, preferring structured fields over _raw."""
    # For stats/aggregation results (no _raw), show all non-internal fields
    if "_raw" not in r:
        print(f"--- Result {index+1} ---")
        for k, v in sorted(r.items()):
            if not k.startswith("_") or k in ("_time", "_sourcetype"):
                val = v if isinstance(v, str) else json.dumps(v)
                print(f"  {k}: {val}")
        print()
        return

    # For raw event results, try to extract structured fields
    ts = r.get("_time", "")
    prefix = f"[{ts}] " if ts else ""

    # Merge top-level fields with parsed _raw JSON (top-level wins)
    raw_str = r.get("_raw", "")
    parsed = {}
    if raw_str.strip().startswith("{"):
        try:
            parsed = json.loads(raw_str)
        except json.JSONDecodeError:
            pass

    level = r.get("level") or parsed.get("level", "")
    logger = r.get("logger") or parsed.get("logger", "")
    message = r.get("message") or parsed.get("message", "")
    host = r.get("host") or parsed.get("host", "")

    if level and message:
        # Structured log — show parsed fields for clarity
        logger_part = f" {logger}" if logger else ""
        sep = " — " if logger else " "
        print(f"{prefix}{level:5s}{logger_part}{sep}{message}")
        # Collect all non-internal fields dynamically from both top-level and parsed _raw
        _skip_keys = {"_raw", "_time", "_indextime", "_serial", "_si", "_cd", "_kv",
                      "_bkt", "_sourcetype", "_subsecond", "_pre_msg", "_fulllinecount",
                      "level", "logger", "message", "host", "source", "sourcetype",
                      "index", "linecount", "splunk_server", "splunk_server_group",
                      "punct", "eventtype", "tag", "tag::eventtype", "timestartpos",
                      "timeendpos"}
        extra = {}
        # Merge parsed _raw fields first, then top-level (top-level wins)
        for k, v in parsed.items():
            if k not in _skip_keys and not k.startswith("_") and v:
                extra[k] = v
        for k, v in r.items():
            if k not in _skip_keys and not k.startswith("_") and v:
                extra[k] = v
        if host:
            extra["host"] = host
        if extra:
            parts = [f"{k}={v}" for k, v in sorted(extra.items())]
            # Use " | " separator so values containing commas don't cause confusion
            print(f"         {' | '.join(parts)}")
        print()
    else:
        # Unstructured — fall back to _raw
        src = r.get("source", host)
        suffix = f" ({src})" if src else ""
        print(f"{prefix}{raw_str}{suffix}")


def _print_json_results(body, limit, output_file=None):
    """Parse and pretty-print Splunk JSON results."""
    # Splunk export can return newline-delimited JSON objects
    results = []
    dropped_lines = 0
    for line in body.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # Export format: each line is {"preview":..., "result":...}
            if "result" in obj:
                results.append(obj["result"])
            elif "results" in obj:
                results.extend(obj["results"])
            else:
                results.append(obj)
        except json.JSONDecodeError:
            dropped_lines += 1
            continue

    if dropped_lines:
        print(f"WARNING: {dropped_lines} line(s) could not be parsed as JSON and were skipped.", file=sys.stderr)

    if not results:
        print("No results.")
        return

    # Write to file if --output specified
    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"{len(results)} result(s) written to {output_file}")
        return

    print(f"--- {len(results)} result(s) ---\n")

    for i, r in enumerate(results[:limit]):
        _print_single_result(r, i)


def _print_error_detail(body):
    """Try to extract a useful error message from Splunk response."""
    try:
        data = json.loads(body)
        msgs = data.get("messages", [])
        for m in msgs:
            print(f"  [{m.get('type', 'ERROR')}] {m.get('text', '')}", file=sys.stderr)
        return
    except json.JSONDecodeError:
        pass
    # XML fallback
    m = re.search(r"<msg[^>]*>(.*?)</msg>", body, re.DOTALL)
    if m:
        print(f"  {m.group(1).strip()}", file=sys.stderr)
    elif body.strip():
        print(f"  {body[:300]}", file=sys.stderr)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _fix_negative_args(argv):
    """Rewrite '--earliest -1h' → '--earliest=-1h' so argparse doesn't choke.

    argparse treats '-1h' as an unknown flag. This pre-processes sys.argv to
    join --earliest/--latest with their next token when it starts with '-'.
    """
    fixed = []
    i = 0
    merge_flags = {"--earliest", "--latest"}
    while i < len(argv):
        if argv[i] in merge_flags and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            fixed.append(f"{argv[i]}={argv[i + 1]}")
            i += 2
        else:
            fixed.append(argv[i])
            i += 1
    return fixed


def main():
    parser = argparse.ArgumentParser(description="SuccessFactors Splunk search (cookie-based auth)")
    parser.add_argument("--instance", default=DEFAULT_INSTANCE,
                        help=f"Splunk instance: {', '.join(INSTANCES.keys())} or full URL (default: {DEFAULT_INSTANCE})")
    parser.add_argument("--cookie-dir", help="Base cookie directory containing sap_cookies.txt (default: ~/.sap-mcp/cookies/sap-splunk)")
    sub = parser.add_subparsers(dest="command", required=True)

    # info
    sub.add_parser("info", help="Show instance info and cookie status")

    # search
    p_search = sub.add_parser("search", help="Run an SPL query")
    p_search.add_argument("query", help="SPL query string")
    p_search.add_argument("--earliest", default="-1h", help="Earliest time (default: -1h)")
    p_search.add_argument("--latest", default="now", help="Latest time (default: now)")
    p_search.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p_search.add_argument("--output-mode", default="json", choices=["json", "csv"], help="Output format (default: json)")
    p_search.add_argument("--async", dest="async_mode", action="store_true", help="Use async job instead of streaming (for large/long queries)")
    p_search.add_argument("--utc", action="store_true", help="Treat --earliest/--latest absolute times as UTC (auto-converts to Splunk server timezone)")
    p_search.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds (default: 120)")
    p_search.add_argument("--output", help="Write results to file instead of stdout")

    # jobs
    sub.add_parser("jobs", help="List recent search jobs")

    # results
    p_results = sub.add_parser("results", help="Fetch results from an existing search job")
    p_results.add_argument("sid", help="Search job SID")
    p_results.add_argument("--limit", type=int, default=100, help="Max results")
    p_results.add_argument("--offset", type=int, default=0, help="Result offset")
    p_results.add_argument("--output", help="Write results to file instead of stdout")

    # status
    p_status = sub.add_parser("status", help="Check search job status")
    p_status.add_argument("sid", help="Search job SID")

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a running search job")
    p_cancel.add_argument("sid", help="Search job SID")

    # open
    p_open = sub.add_parser("open", help="Open a Splunk search in the browser")
    p_open.add_argument("query", help="SPL query string")
    p_open.add_argument("--earliest", default="-24h", help="Earliest time (default: -24h)")
    p_open.add_argument("--latest", default="now", help="Latest time (default: now)")
    p_open.add_argument("--utc", action="store_true", help="Treat --earliest/--latest absolute times as UTC")
    p_open.add_argument("--url-only", action="store_true", help="Print URL only, don't open browser (for agent chaining)")

    # trace
    p_trace = sub.add_parser("trace", help="Trace a request by ID (auto-discovers correlation chain)")
    p_trace.add_argument("id", help="Request ID, correlation ID, or any traceable identifier")
    p_trace.add_argument("--earliest", default="-4h", help="Earliest time (default: -4h)")
    p_trace.add_argument("--latest", default="now", help="Latest time (default: now)")
    p_trace.add_argument("--utc", action="store_true", help="Treat absolute times as UTC")
    p_trace.add_argument("--timeout", type=int, default=120, help="Timeout in seconds (default: 120)")
    p_trace.add_argument("--limit", type=int, default=200, help="Max trace events (default: 200)")
    p_trace.add_argument("--output", help="Save trace results to JSON file")
    p_trace.add_argument("--index", default="msc_worktech-teams", help="Splunk index (default: msc_worktech-teams)")
    p_trace.add_argument("--environment", help="Filter by environment (e.g., dev, prod)")

    args = parser.parse_args(_fix_negative_args(sys.argv[1:]))

    global COOKIE_DIR
    if args.cookie_dir:
        COOKIE_DIR = os.path.expanduser(args.cookie_dir)

    cmds = {
        "info": cmd_info,
        "search": cmd_search,
        "jobs": cmd_jobs,
        "results": cmd_results,
        "status": cmd_status,
        "cancel": cmd_cancel,
        "open": cmd_open,
        "trace": cmd_trace,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
