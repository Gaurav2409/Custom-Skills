# ServiceNow Encoded Query Quick Reference

## Basic syntax

```
field=value^field2=value2^ORDERBYDESCfield3
```

Use `^` for AND, `^OR` for OR. No spaces around operators.

## Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Equals | `state=1` |
| `!=` | Not equals | `state!=7` |
| `IN` | In set | `stateIN1,2,3` |
| `NOT IN` | Not in set | `stateNOT IN6,7` |
| `LIKE` | Contains | `short_descriptionLIKElogin` |
| `NOT LIKE` | Not contains | `short_descriptionNOT LIKEtest` |
| `STARTSWITH` | Starts with | `numberSTARTSWITHINC` |
| `ENDSWITH` | Ends with | `numberENDSWITH266` |
| `ISEMPTY` | Is empty | `assigned_toISEMPTY` |
| `ISNOTEMPTY` | Is not empty | `assigned_toISNOTEMPTY` |
| `>` | Greater than | `opened_at>2026-01-01` |
| `<` | Less than | `opened_at<2026-04-01` |
| `>=` | Greater or equal | `priority>=2` |
| `<=` | Less or equal | `priority<=3` |

## Sorting

| Syntax | Meaning |
|--------|---------|
| `^ORDERBY field` | Ascending |
| `^ORDERBYDESC field` | Descending |

## Incident state values

| Value | State |
|-------|-------|
| `1` | New |
| `2` | In Progress |
| `3` | On Hold |
| `-3` | Awaiting Info |
| `6` | Resolved |
| `7` | Closed |
| `8` | Canceled |

## Case state values

| Value | State |
|-------|-------|
| `1` | New |
| `10` | In Progress |
| `18` | Awaiting Info |
| `6` | Resolved |
| `3` | Closed |
| `7` | Cancelled |

## Common incident queries

```
-- Open P1/P2 incidents
priority<=2^stateIN1,2,3^ORDERBYDESCsys_updated_on

-- Incidents assigned to a group
assignment_group=SF Ops QA Support^stateIN1,2^ORDERBYDESCsys_updated_on

-- Unassigned open incidents
assigned_toISEMPTY^stateIN1,2^ORDERBYDESCopened_at

-- Keyword search in short description
short_descriptionLIKEredis^stateIN1,2,3^ORDERBYDESCopened_at

-- Recently opened (last 7 days)
opened_at>javascript:gs.daysAgoStart(7)^ORDERBYDESCopened_at

-- Incidents opened today
opened_at>=javascript:gs.beginningOfToday()^ORDERBYDESCopened_at

-- Resolved in last 24 hours
state=6^resolved_at>javascript:gs.hoursAgoStart(24)^ORDERBYDESCresolved_at
```

## Common case queries

```
-- Open cases by assignment group
assignment_group=My Team^stateIN1,10^ORDERBYDESCsys_updated_on

-- Cases with keyword
short_descriptionLIKElogin^ORDERBYDESCopened_at

-- High priority open cases
priority<=2^stateIN1,10,18^ORDERBYDESCsys_updated_on

-- Cases opened in the last 30 days
opened_at>javascript:gs.daysAgoStart(30)^ORDERBYDESCopened_at
```

## Date functions

| Function | Meaning |
|----------|---------|
| `javascript:gs.daysAgoStart(N)` | N days ago (start of day) |
| `javascript:gs.hoursAgoStart(N)` | N hours ago |
| `javascript:gs.beginningOfToday()` | Today 00:00 |
| `javascript:gs.beginningOfThisWeek()` | Start of this week |
| `javascript:gs.beginningOfThisMonth()` | Start of this month |
| `YYYY-MM-DD` | Absolute date |
| `YYYY-MM-DD HH:MM:SS` | Absolute datetime |
