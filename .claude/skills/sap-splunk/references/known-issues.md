# Known Issues — Unsupported DCs

## Affected DCs

```
dc22, dc25, dc33, dc34, dc52, dc55, dc80, dc81, dc82, dc84
```

These 10 Splunk DCs are recognized as instance names by `splunk.py` but the script will print a warning recommending `--instance orf` and still attempt the query. Without the opt-in HttpsUpgrades hack (see root README → sap-splunk → "Known Issue: Querying unsupported DCs directly"), the request will hang during SSO authentication.

## Workaround for users

Use ORF and scope your query with `host=...`, `index=...`, or other filters:

```bash
# Was: python3 scripts/splunk.py --instance dc25 search '...'
# Use:
python3 scripts/splunk.py --instance orf search 'host=*dc25* ...'
```

ORF is a cross-DC search head that indexes data from all 37+ DCs, so the data you need is reachable — just through a different entry point.

## Why these DCs are unsupported

The blocker is **not** in `splunk.py` itself. It is in the cookie acquisition step that runs in the `sap-authentication` skill (Playwright-driven SSO). The chain breaks like this:

1. **Splunk web frontend on these DCs is misconfigured.** Splunk listens on plain HTTP port 80 behind an SSL-offloading load balancer. Splunk has no `trustedIP` / `trustedSubnet` set in `server.conf`, so it does not honor the LB's `X-Forwarded-Proto: https` header. As a result, every redirect Splunk emits — including the root `303` to the login page, the post-login landing redirect, and the SAML assertion-consumer response — uses `Location: http://...`. Working DCs (e.g. dc60) emit `Location: https://...` and are unaffected.

2. **Port 80 is firewalled.** The LB only accepts traffic on 443. So once the browser obeys the `http://` Location, the connection hangs until timeout.

3. **Playwright disables Chromium's `HttpsUpgrades` feature.** `@playwright/mcp` ships Chromium with a hardcoded `--disable-features=...,HttpsUpgrades,...` (16 features total, in `chromiumSwitches.ts`). With `HttpsUpgrades` disabled, Chromium will *not* automatically upgrade `http://` URLs to `https://`, so it dutifully follows the broken Location into the firewalled port 80.

4. **The Playwright MCP CLI does not expose a way to re-enable `HttpsUpgrades`.** Adding `--browser-arg=--enable-features=HttpsUpgrades` does not work — Chromium's `FeatureList` rule is "first registration wins", and the disable is registered first. A workaround using Playwright's `ignoreDefaultArgs` exists but requires editing the plugin-level `.mcp.json` and a `playwright-mcp-config.json` that mirrors the full default disable-features string (fragile against Playwright upgrades).

5. **Net effect:** `sap-authentication` cannot complete SSO on these DCs → no fresh cookies → `splunk.py` has no credentials to call the REST API even though the API itself works.

## Why `splunk.py` REST works but is still useless without cookies

`splunk.py` already handles `Location: http://...` correctly via `_HttpsRedirectHandler` — it rewrites every `http://` redirect to `https://` before `urllib` follows it. Empirical test (no auth, just observing redirect chain) on dc25:

| Path | With handler (current) | Without handler |
|------|------------------------|-----------------|
| `/` | 200 in 4.0s | timeout in 16.4s |
| `/services/server/info` | 200 in 2.9s | timeout in 16.5s |
| `/services/search/jobs` | 200 in 6.7s | timeout in 16.5s |

So the REST path is healthy on broken DCs. The blocker is purely the missing cookies.

## What it would take to support these DCs again

Three orthogonal paths, in order of cleanliness:

1. **Splunk team fix.** Configure `trustedIP` / `trustedSubnet` in each broken DC's `server.conf` so Splunk honors `X-Forwarded-Proto: https` from the LB. This eliminates the `http://` Locations at the source. Tracked separately by Splunk Ops; ETA unknown.

2. **Playwright re-enables `HttpsUpgrades` by default or exposes it as a CLI flag.** Tracked upstream as Playwright PR #28439 (closed unmerged, 2023-12) and `@playwright/mcp` issue #1239 (closed as "unconventional", 2025-12). Not happening soon.

3. **Skill-side workaround (the `ignoreDefaultArgs` hack).** Override Chromium launch args via `--config <file>` with the full default disable-features string in `ignoreDefaultArgs` and a copy minus `HttpsUpgrades` in `args`. Works empirically (verified on dc22, dc25, dc52, dc84 — all loaded clean in <4s with hack vs timeout/error without). Fragile: a Playwright upgrade that adjusts the disable-features list silently breaks the exact-string match. Currently not enabled.

Until any of these lands, the supported workaround is `--instance orf`.
