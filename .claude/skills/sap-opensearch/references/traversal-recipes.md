# Traversal recipes (copy-paste)

Each recipe runs as `browser-harness -c "$(cat <<'PY' ... PY)"`. They all start
with the **shared helper** below — prepend it to each recipe's Python. Fill the
`<TENANT_UUID>`, `<FROM>`, `<TO>` placeholders (`<FROM>`/`<TO>` accept `now-9h`
or ISO `2026-06-11T16:45:00Z`).

## Shared helper (prepend to every recipe)

```python
import json, re, datetime
TPL = r'''
return (async()=>{
  const body={params:{index:"application-*",body:__BODY__}};
  const r=await fetch("/internal/search/opensearch-with-long-numerals",
    {method:"POST",headers:{"content-type":"application/json","osd-xsrf":"true"},
     body:JSON.stringify(body)});
  const j=await r.json(); const h=j.rawResponse.hits;
  return JSON.stringify({total:h.total, aggs:j.rawResponse.aggregations||null,
    rows:h.hits.map(x=>({t:x._source["@timestamp"],l:x._source.level,
      loc:x._source.location||x._source.filePath||"",
      m:(x._source.message||"").replace(/\s+/g," ")}))});
})();
'''
def osq(body_json): return json.loads(js(TPL.replace("__BODY__", body_json)))
def P(t): return datetime.datetime.fromisoformat(t.replace("Z","+00:00"))
T='{match_phrase:{"tenantInfo.tenantId":"<TENANT_UUID>"}}'
W='{range:{"@timestamp":{gte:"<FROM>",lte:"<TO>"}}}'
```

## 1. Activity histogram — find the gaps first

```python
o=osq('{size:0,query:{bool:{must:[%s,%s]}},aggs:{tl:{date_histogram:{field:"@timestamp",fixed_interval:"1m",time_zone:"UTC",min_doc_count:1}}}}'%(T,W))
print("total:", o["total"])
for b in o["aggs"]["tl"]["buckets"]:
    c=b["doc_count"]; print(f'{b["key_as_string"][11:16]}  {"#"*min(c,60)} {c}')
```

Sparse "heartbeat" minutes between dense bursts = a long silent operation in
between. Widen `fixed_interval` to `5m` for long windows.

## 2. Level sweep + pod breakdown

```python
o=osq('{size:0,query:{bool:{must:[%s,%s]}},aggs:{lv:{terms:{field:"level",size:20}},pods:{terms:{field:"kubernetes.pod_name",size:30}}}}'%(T,W))
print("levels:", {b["key"]:b["doc_count"] for b in o["aggs"]["lv"]["buckets"]})
print("pods:  ", {b["key"].split("-")[-1]:b["doc_count"] for b in o["aggs"]["pods"]["buckets"]})
```

If `Performance`/`Debug` are present but you saw none, you were filtering them
out — add `{terms:{level:["Performance","Debug"]}}` to `must`.

## 3. Timeline → phases + largest silent gaps

```python
o=osq('{size:1500,sort:[{"@timestamp":{order:"asc"}}],_source:["@timestamp","level","location","filePath","message"],query:{bool:{must:[%s,%s]}}}'%(T,W))
docs=o["rows"]; docs.sort(key=lambda d:d["t"])
print("fetched:", len(docs), "of", o["total"])

# phases split on >60s gaps
from collections import Counter
phases=[]; cur=[]
for d in docs:
    if cur and (P(d["t"])-P(cur[-1]["t"])).total_seconds()>60: phases.append(cur); cur=[]
    cur.append(d)
if cur: phases.append(cur)
for p in phases:
    dur=(P(p[-1]["t"])-P(p[0]["t"])).total_seconds()
    files=Counter((d["loc"].split("/")[-1]) for d in p)
    print(f'\n{p[0]["t"][11:19]}->{p[-1]["t"][11:19]} ({len(p)} logs, {dur:.0f}s)  {dict(files.most_common(6))}')

# largest gaps + what brackets them
print("\n== largest gaps ==")
gaps=sorted(((P(docs[i]["t"])-P(docs[i-1]["t"])).total_seconds(), i) for i in range(1,len(docs)))[-8:]
for g,i in reversed(gaps):
    b,a=docs[i-1],docs[i]
    print(f'  {g/60:5.1f}min {b["t"][11:19]}->{a["t"][11:19]}')
    print(f'     BEFORE {b["loc"].split("/")[-1][:30]:30}| {b["m"][:90]}')
    print(f'     AFTER  {a["loc"].split("/")[-1][:30]:30}| {a["m"][:90]}')
```

A multi-minute gap with the connection held but **no SQL/HTTP/log** = blocking
in-memory (CPU) work; the BEFORE/AFTER lines name the operation around it.

## 4. Performance hotspots — rank + sum durations

```python
o=osq('{size:2000,sort:[{"@timestamp":{order:"asc"}}],_source:["@timestamp","location","message"],query:{bool:{must:[%s,%s,{match_phrase:{message:"Performance Time"}}]}}}'%(T,W))
from collections import defaultdict
durs=[]
for d in o["rows"]:
    mm=re.search(r'- ([\d.]+)ms', d["m"])
    if mm: durs.append((float(mm.group(1)), d))
print("== top single durations ==")
for ms,d in sorted(durs,reverse=True)[:15]:
    print(f'  {ms/1000:8.1f}s  {d["t"][11:19]} {d["loc"][:40]:40}| {d["m"][:70]}')
agg=defaultdict(lambda:[0.0,0])
for ms,d in durs: agg[d["loc"][:48]][0]+=ms; agg[d["loc"][:48]][1]+=1
print("== summed by location ==")
for loc,(tot,n) in sorted(agg.items(),key=lambda x:-x[1][0])[:12]:
    print(f'  {tot/1000:8.1f}s ({n:4} calls)  {loc}')
```

High *summed* time with many calls = an N+1 / hot loop. One huge *single*
duration = a slow query or step. A long operation with **no** perf line is
uninstrumented (e.g. a synchronous compute) — find it via recipe 3's gap.

## 5. Correlate to one job / pod / entity

```python
# by job run (framework + top-level job logs)
o=osq('{size:500,sort:[{"@timestamp":{order:"asc"}}],_source:["@timestamp","level","location","message","jobInfo"],query:{bool:{must:[{match_phrase:{"jobInfo.jobRunId":"<JOBRUN_UUID>"}}]}}}')
for d in o["rows"]: print(d["t"][11:23], d["l"][:5], d["loc"].split("/")[-1][:24], "|", d["m"][:120])
```

Caveat: deep application logs frequently **lack** `jobInfo`. To see what the app
actually did, correlate by `tenantInfo.tenantId` + time window, and isolate the
worker with a `kubernetes.pod_name` `match_phrase`. Other useful join keys:
`sapPassport.rootContextId`, and entity IDs (workspace/process/object) matched in
`message` via `{match_phrase:{message:"<ID>"}}`.

## Reporting

Lead with the timeline breakdown (phase durations), then the localized operation
(from the largest gap / hotspot), then the causal chain to the symptom. Prefer a
small table of attempts/phases over a wall of raw log lines.
