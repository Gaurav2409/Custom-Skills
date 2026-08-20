# OpenSearch query DSL, aggregations, pagination

All snippets go inside the `js()` async IIFE from `SKILL.md`. The request body is
always `{params:{index:"<index>", body:{ <DSL below> }}}` and the useful response
paths are `j.rawResponse.hits.{total,hits}` and `j.rawResponse.aggregations`.

Common indices: `application-*` (app logs). Confirm by reading the index pattern
in the Dashboards URL or via the captured request (below).

## Discover the endpoint

The internal search endpoint observed is
`POST /internal/search/opensearch-with-long-numerals`. If it 404s after a
Dashboards upgrade, capture the real one with CDP: enable Network, run any
Discover search, then read the request the app made.

```bash
browser-harness -c "$(cat <<'PY'
import time
cdp("Network.enable"); drain_events()
# trigger a search in the open Discover tab (or new_tab to the discover URL), then:
time.sleep(5)
for e in drain_events():
    if e.get("method")=="Network.requestWillBeSent":
        u=e["params"]["request"]["url"]
        if "search" in u:
            print(e["params"]["request"]["method"], u[:120])
            pd=e["params"]["request"].get("postData")
            if pd: print("  BODY:", pd[:400])
PY
)"
```

## Query clauses (inside `query.bool`)

```js
// exact field value (use for IDs, levels, tenants — avoids partial-token matches)
{match_phrase:{"tenantInfo.tenantId":"<uuid>"}}
{match_phrase:{"jobInfo.implementationId":"DEPLOY_TRIGGER"}}

// time window (UTC). relative or ISO both work
{range:{"@timestamp":{gte:"now-9h",lte:"now"}}}
{range:{"@timestamp":{gte:"2026-06-11T16:45:00Z",lte:"2026-06-11T18:14:00Z"}}}

// set membership (great for levels)
{terms:{level:["Performance","Debug"]}}

// full-text (analyzed) — matches a token anywhere in message
{match_phrase:{message:"Connection terminated unexpectedly"}}

// existence / wildcard
{exists:{field:"jobInfo.jobRunId"}}
{wildcard:{"location":"*ContentRetriever*"}}
```

Combine with `bool`:

```js
query:{bool:{
  must:[ {match_phrase:{"tenantInfo.tenantId":"<uuid>"}},
         {range:{"@timestamp":{gte:"now-9h",lte:"now"}}} ],
  should:[ {match_phrase:{message:"failed on the application side"}},
           {match_phrase:{message:"DEPLOYMENT in error"}},
           {match_phrase:{message:"JOB_ERROR_100"}} ],
  minimum_should_match:1,
  must_not:[ {match_phrase:{message:"Cannot find source key"}} ]  // drop known noise
}}
```

`level` values are exact-cased: `Info`, `Debug`, `Performance`, `Warning`, `Error`.

## Sort, source filtering, size

```js
sort:[{"@timestamp":{order:"asc"}}],   // asc = oldest first (timeline); desc = latest
_source:["@timestamp","level","location","message","kubernetes.pod_name","jobInfo"],
size:1000                               // pull only what you need
```

## Aggregations (set `size:0` to skip hits)

```js
aggs:{
  tl:{date_histogram:{field:"@timestamp",fixed_interval:"1m",time_zone:"UTC",min_doc_count:1}},
  lv:{terms:{field:"level",size:20}},                 // counts by level
  pods:{terms:{field:"kubernetes.pod_name",size:30}}, // counts by pod
  uniq:{cardinality:{field:"jobInfo.jobRunId"}}
}
```

Read back: `j.rawResponse.aggregations.tl.buckets` →
`[{key_as_string, doc_count}, ...]`; `...lv.buckets` → `[{key, doc_count}, ...]`.

`terms` aggs require an aggregatable (keyword) field. `level`,
`kubernetes.pod_name`, `tenantInfo.tenantId` work. If a `terms` agg returns
empty on a text field, aggregate on its `.keyword` subfield instead.

## Pagination beyond 10000

`size` is capped by `index.max_result_window` (default 10000). For more, sort by
a tiebreaker and page with `search_after`:

```js
sort:[{"@timestamp":{order:"asc"}},{"_doc":{order:"asc"}}],
// page 1: omit search_after; page N+1: search_after = last hit's `sort` array
search_after:[<lastTsEpochMillis>, <lastDoc>]
```

In practice, prefer narrowing the time window or filtering by pod/level so a
single `size<=2000` query suffices — it's faster and simpler than paging.

## kuery vs DSL (counts)

The Discover search bar uses DQL/kuery. `jobInfo.jobRunId:"<uuid>"` there can
match *partial* hyphen-delimited hex tokens (e.g. `1211`, `bea7`) across unrelated
docs and massively inflate the hit count. For trustworthy counts and correlation
use `match_phrase` (exact) in the API, as shown above.
