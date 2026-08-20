---
name: sap-opensearch
description: >-
  Query and traverse SAP internal OpenSearch / OpenSearch Dashboards application
  logs through the user's authenticated browser session (via browser-harness),
  by replaying the Dashboards internal search API instead of scraping the
  Discover grid. Use when the user wants to investigate OpenSearch logs, debug a
  job/service failure from cluster logs, trace a tenant/jobRun/pod over a time
  window, find where time goes in a long operation, or shares an
  opensearch.*.clusters.*.cloud.sap (data-explorer/discover) link.
---

# SAP OpenSearch log traversal

Investigate SAP internal OpenSearch application logs by driving the user's
already-authenticated OpenSearch Dashboards tab with `browser-harness` and
calling the Dashboards **internal search API** with same-origin `fetch`. This
gets the *complete* result set (all levels, aggregations, 1000s of docs) — the
`/app/data-explorer/discover` grid is virtualized, so DOM scraping only returns
the few visible rows and is a dead end.

## Prerequisites

- `browser-harness` on `$PATH` (see `/Users/I321170/Documents/AI_Knowledge/browser-harness`).
- The user's Chrome has an **OpenSearch Dashboards tab open and logged in** (SAP SSO). The `fetch` runs in that page's origin, so auth cookies and XSRF work automatically. If redirected to login, stop and ask the user to authenticate.
- Each `browser-harness -c '<python>'` is a **fresh process** (no state carries over). Do the fetch *and* the analysis in one call.

## Core technique: replay the internal search API

```bash
browser-harness -c "$(cat <<'PY'
import json
Q = r'''
return (async()=>{
  const body={params:{index:"application-*",body:{
    size:500,
    sort:[{"@timestamp":{order:"asc"}}],
    _source:["@timestamp","level","location","filePath","message"],
    query:{bool:{must:[
      {match_phrase:{"tenantInfo.tenantId":"<TENANT_UUID>"}},
      {range:{"@timestamp":{gte:"now-1h",lte:"now"}}}
    ]}}
  }}};
  const r=await fetch("/internal/search/opensearch-with-long-numerals",
    {method:"POST",headers:{"content-type":"application/json","osd-xsrf":"true"},
     body:JSON.stringify(body)});
  const j=await r.json();
  const h=j.rawResponse.hits;
  return JSON.stringify({total:h.total,
    rows:h.hits.map(x=>({t:x._source["@timestamp"],l:x._source.level,
      loc:x._source.location||x._source.filePath||"",
      m:(x._source.message||"").replace(/\s+/g," ").slice(0,220)}))});
})();
'''
o=json.loads(js(Q))
print("total:", o["total"], " fetched:", len(o["rows"]))
for d in o["rows"]:
    print(d["t"][11:23], d["l"][:5], (d["loc"] or "").split("/")[-1][:26], "|", d["m"][:140])
PY
)"
```

Two things that make or break this:

1. **`js()` wraps your code in a non-async function**, so a bare top-level
   `await` throws `await is only valid in async functions`. Always wrap the body
   in an async IIFE and return it: `return (async()=>{ ... })();`.
2. **Response shape**: `j.rawResponse.hits.total`, `j.rawResponse.hits.hits[]._source`,
   and `j.rawResponse.aggregations.<name>` for aggs.

`_source` top-level fields typically include: `@timestamp`, `level`, `location`,
`filePath`, `message`, `kubernetes.*` (e.g. `pod_name`, `namespace_name`,
`labels.version`), `tenantInfo.tenantId`, `jobInfo.*` (`implementationId`,
`jobRunId`, `mode`), `sapPassport.*`. Use `_source: [...]` to keep payloads small.

If the endpoint 404s (Dashboards version drift), discover the real one via CDP —
see [references/query-dsl.md](references/query-dsl.md#discover-the-endpoint).

## Traversal playbook (where does the time/problem go?)

Work top-down; each step narrows the next query. Templates in
[references/traversal-recipes.md](references/traversal-recipes.md).

1. **Histogram first.** A `date_histogram` (1m/5m) over the window shows *when*
   activity happens. A long quiet gap between bursts = one long silent operation
   (CPU-bound or blocking); dense uniform logs = continuous work. This single
   query usually localizes the problem.
2. **Level sweep.** A `terms` agg on `level` reveals what exists. `Performance`
   and `Debug` logs are retained but absent from default Info views — query them
   explicitly with `{terms:{level:["Performance","Debug"]}}`. They carry per-step
   timings (`... Performance Time - 1234.5ms`) and progress markers.
3. **Phase split.** Pull the window sorted ascending, split into phases wherever
   consecutive logs are >N seconds apart, and summarize each phase by `filePath`
   and top repeated messages.
4. **Largest silent gap.** The biggest inter-log gap localizes a silent op. Read
   the *last* log before it and *first* after it — that brackets the operation.
   No SQL/HTTP/log during a gap while a connection is held = blocking in-memory work.
5. **Duration ranking.** Parse `- <N>ms` out of `Performance Time` messages; rank
   single durations and sum by `location` to find the hotspot / N+1 loops.
6. **Correlate.** Filter by `jobInfo.jobRunId`, `kubernetes.pod_name`,
   `sapPassport.rootContextId`, or an entity ID (workspace/process). Caveat: deep
   application logs often **don't** carry `jobInfo`; correlate those by
   `tenantInfo.tenantId` + time window + pod instead.

## Pitfalls

| Pitfall | Fix |
|---|---|
| Discover grid scrape returns ~4 of N rows | It's virtualized — use the search API, never DOM `innerText`. |
| Bare `await` in `js()` errors | Wrap in `return (async()=>{...})();`. |
| Quoted-UUID kuery inflates hit count | DQL `field:"uuid"` can match partial hex tokens across many docs. Use `match_phrase` in the API for exact counts. |
| "Performance"/"Debug" logs seem missing | They're below Info. Query `{terms:{level:[...]}}` explicitly. |
| Wrong time results | Timestamps are **UTC**. Use `now-Xh` or ISO `...Z`. |
| `size` too small / >10000 | Default `index.max_result_window` is 10000. For more, paginate with `search_after` (see references). |
| Mixed tenant noise in a window | Add a `kubernetes.pod_name` `match_phrase` to isolate one pod/worker. |
| Trying to escape `$state` in a shared URL | Not needed — the API approach uses no Dashboards URL state. |

## References

- Query DSL, aggregations, pagination, endpoint discovery: [references/query-dsl.md](references/query-dsl.md)
- Copy-paste analysis recipes (histogram, phase split, gap, duration ranking, correlation): [references/traversal-recipes.md](references/traversal-recipes.md)
