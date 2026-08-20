# SPL Query Templates for worktech-teams-svc

Primary index: `msc_worktech-teams`. Logs are structured JSON with fields: `level`, `logger`, `message`, `environment`, `host`, `app`, `datacenter`, `version`, `companyId`, `thread`.

**Note:** Templates below use `environment=dev` as an example filter. This field is optional — omit it to search across all environments. Common values by DC type:
- **Production DCs** (e.g. DC66): `prod`, `stage`
- **Dev/Preview DCs** (e.g. DC25): `dev`, `qa`, `perf`, `perfrelease`, `engcand`, `staging1`, `staging2`, and team-specific envs

Discover values for a specific DC: `index="msc_worktech-teams" | stats count by environment | sort -count`

## Contents
- [Anomaly Investigation](#anomaly-investigation)
- [Service Debugging](#service-debugging)
- [Request Tracing](#request-tracing)
- [Cron & Scheduling](#cron--scheduling)
- [Infrastructure](#infrastructure)
- [Performance Analysis](#performance-analysis)
- [tstats (Fast Mode)](#tstats-fast-mode)
- [SPL Tips](#spl-tips)

## Anomaly Investigation

### Error/warn summary (start here)
```spl
index="msc_worktech-teams" environment=dev (level=ERROR OR level=WARN)
| stats count by logger, level, message | sort -count | head 30
```

### Error rate over time
```spl
index="msc_worktech-teams" environment=dev level=ERROR
| timechart span=5m count by logger
```

### Top error sources by host
```spl
index="msc_worktech-teams" environment=dev level=ERROR
| stats count by host, logger | sort -count | head 20
```

## Service Debugging

### Errors for a specific logger
```spl
index="msc_worktech-teams" environment=dev logger="c.s.e.w.e.a.s.JobSchedulerService" level=ERROR
| table _time host message | sort -_time
```

### Specific tenant
```spl
index="msc_worktech-teams" environment=dev "CQABPGCEC"
| table _time host logger level message | sort -_time
```

### JDBC / DB connection failures
```spl
index="msc_worktech-teams" environment=dev ("JDBC" OR "Connection") level=ERROR
| stats count by logger, message | sort -count
```

### Stack traces / exceptions
```spl
index="msc_worktech-teams" environment=dev "Exception" level=ERROR
| rex field=message "(?P<exception>\w+Exception)"
| stats count by exception, logger | sort -count
```

### Null pointer errors
```spl
index="msc_worktech-teams" environment=dev ("NullPointerException" OR "message.*null")
| table _time host logger message | sort -_time
```

## Request Tracing

Trace a request across services using correlation IDs, request IDs, or trace IDs.

### Trace by correlation ID
```spl
index="msc_worktech-teams" environment=dev ("X-Correlation-Id" OR "correlationId")
| rex field=message "(?:X-Correlation-Id|correlationId)[=:]\\s*(?P<correlation_id>[a-f0-9\\-]+)"
| search correlation_id="<PASTE_CORRELATION_ID>"
| table _time host logger level message | sort _time
```

### Trace by request ID
```spl
index="msc_worktech-teams" environment=dev "<PASTE_REQUEST_ID>"
| table _time host logger level message | sort _time
```

### Extract correlation ID from a request ID (chained query)
Step 1 — Find the correlation ID from a request:
```spl
index="msc_worktech-teams" environment=dev "<PASTE_REQUEST_ID>"
| rex field=message "(?:X-Correlation-Id|correlationId)[=:]\\s*(?P<correlation_id>[a-f0-9\\-]+)"
| stats values(correlation_id) as correlation_ids
```
Step 2 — Use the extracted correlation ID to find all related events (substitute result from step 1):
```spl
index="msc_worktech-teams" environment=dev "<CORRELATION_ID_FROM_STEP_1>"
| table _time host logger level message | sort _time
```

### Trace by thread name (follow one execution thread)
```spl
index="msc_worktech-teams" environment=dev thread="<THREAD_NAME>"
| table _time logger level message | sort _time | head 100
```

### Cross-tenant request trace
```spl
index="msc_worktech-teams" environment=dev "CQABPGCEC" "<REQUEST_OR_CORRELATION_ID>"
| table _time host logger level message | sort _time
```

## Cron & Scheduling

### CRON-L1 scan activity
```spl
index="msc_worktech-teams" environment=dev "CRON-L1"
| table _time host level message | sort -_time
```

### CRON errors only
```spl
index="msc_worktech-teams" environment=dev ("CRON" OR "TenantScanScheduler") level=ERROR
| stats count by logger, message | sort -count
```

### Agent scheduler activity
```spl
index="msc_worktech-teams" environment=dev "AGENT-SCHEDULER"
| table _time host level message | sort -_time
```

### Scheduling task execution errors
```spl
index="msc_worktech-teams" environment=dev "SCHEDULING" level=ERROR
| table _time host message | sort -_time
```

### S3 / platform-job-scheduler events
```spl
index="msc_worktech-teams" environment=dev ("JobType" OR "platform-job-scheduler" OR "S3")
| table _time host logger message | sort -_time
```

## Infrastructure

### Events by host
```spl
index="msc_worktech-teams" environment=dev | stats count by host | sort -count
```

### Version distribution (which pods run which version)
```spl
index="msc_worktech-teams" environment=dev
| stats dc(host) as hosts, latest(version) as version by app | sort -hosts
```

### Upgrade pod activity
```spl
index="msc_worktech-teams" environment=dev host="*upgrade*"
| stats count by host, level | sort -count
```

### Kafka consumer issues
```spl
index="msc_worktech-teams" environment=dev logger="o.a.k.c.NetworkClient" level=WARN
| stats count by message | sort -count
```

## Performance Analysis

### Request latency distribution (if elapsed/duration fields present)
```spl
index="msc_worktech-teams" environment=dev ("elapsed" OR "duration")
| rex field=message "(?:elapsed|duration)[=:]\\s*(?P<latency_ms>\\d+)"
| where isnotnull(latency_ms)
| eval latency_ms=tonumber(latency_ms)
| stats avg(latency_ms) as avg_ms, perc90(latency_ms) as p90_ms, perc95(latency_ms) as p95_ms, perc99(latency_ms) as p99_ms, count by logger
| sort -avg_ms
```

### Slow requests (> 5s)
```spl
index="msc_worktech-teams" environment=dev ("elapsed" OR "duration")
| rex field=message "(?:elapsed|duration)[=:]\\s*(?P<latency_ms>\\d+)"
| where latency_ms > 5000
| table _time host logger message latency_ms | sort -latency_ms | head 20
```

### Error rate percentage over time
```spl
index="msc_worktech-teams" environment=dev
| eval is_error=if(level="ERROR", 1, 0)
| timechart span=5m count as total, sum(is_error) as errors
| eval error_pct=round(errors/total*100, 2)
| fields _time total errors error_pct
```

### Top N busiest tenants
```spl
index="msc_worktech-teams" environment=dev companyId=*
| stats count by companyId | sort -count | head 20
```

## tstats (Fast Mode)

`tstats` queries the tsidx index directly — 10-100x faster than regular search for large time ranges. Use for counting, time-series, and field discovery over days/weeks.

### Event count over time (fast overview)
```spl
| tstats count where index="msc_worktech-teams" by _time span=1h
```

### Event count by host
```spl
| tstats count where index="msc_worktech-teams" by host | sort -count | head 20
```

### Event count by source type
```spl
| tstats count where index="msc_worktech-teams" by sourcetype | sort -count
```

### Event volume trend over 7 days
```spl
| tstats count where index="msc_worktech-teams" by _time span=1d
```

### Discover available indexes on a DC
```spl
| tstats count where index=* by index | sort -count | head 30
```

**Note:** `tstats` only works with indexed fields (`host`, `source`, `sourcetype`, `_time`). For extracted fields like `level`, `logger`, `message`, use regular `search`.

## SPL Tips

- **Always use `=` syntax for negative time**: `--earliest='-1h'`
- **Start with stats**: `| stats count by logger, level, message | sort -count` gives the best overview
- **Filter by environment** (optional): Add `environment=dev` to narrow results. Omit it to search across all environments. Use `| stats count by environment` to discover valid values for the target DC
- **Time modifiers**: `-15m`, `-1h`, `-4h`, `-24h`, `-7d`, `@d` (midnight today)
- **Escape pipes**: Use `'| tstats ...'` (quote the whole query) for pipe-first queries
