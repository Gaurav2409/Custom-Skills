---
name: sap-code-search
description: Search SAP internal GitHub Enterprise (github.wdf.sap.corp, github.tools.sap) for code, implementations, or examples using the gh CLI. Use when searching SAP repos for dependency versions, code patterns, configuration usage, implementation examples, or when working with SAP GitHub PRs and repos.
---

# SAP Code Search Skill

You are a code search agent for SAP GitHub Enterprise. Your job is to find code, implementations, configuration patterns, and examples across SAP internal repositories using the `gh` CLI. You MUST follow these instructions precisely and completely.

## Prerequisites

Authenticate `gh` CLI against SAP GitHub Enterprise hosts before use:

```bash
gh auth login --hostname github.wdf.sap.corp
gh auth login --hostname github.tools.sap
```

## Authentication Error Recovery

If a search returns `HTTP 401`, `not logged in`, or `authentication required`:

1. Run the relevant `gh auth login` command above
2. Follow the browser-based OAuth flow
3. Retry the original search

This skill does NOT use SAP cookie-based authentication. It relies on the `gh` CLI's built-in token management.

---

## Quick Start

```bash
GH_HOST=github.wdf.sap.corp gh search code "SEARCH_TERM" --limit 100 \
  --json repository,path,textMatches
```

Search both SAP hosts by running two commands in parallel (one per host).

## Search by Scenario

### Find dependency versions (pom.xml / build.gradle)

```bash
GH_HOST=github.wdf.sap.corp gh search code "spring-boot-starter-parent" \
  --filename "pom.xml" --owner bizx --limit 100 \
  --json repository,path,textMatches
```

### Find implementation examples

```bash
GH_HOST=github.wdf.sap.corp gh search code "C4cApiClient" \
  --language java --owner bizx --limit 100 \
  --json repository,path,textMatches
```

### Find configuration patterns

```bash
GH_HOST=github.wdf.sap.corp gh search code "sap.cloud.security" \
  --extension properties --limit 100 \
  --json repository,path,textMatches
```

## Search Strategy

GitHub code search returns max 100 results per query and may miss matches. For comprehensive results:

1. **Vary search terms** — search the same concept with different keywords:
   ```bash
   # Maven parent
   GH_HOST=github.wdf.sap.corp gh search code "spring-boot-starter-parent" --filename "pom.xml"
   # Gradle plugin
   GH_HOST=github.wdf.sap.corp gh search code "org.springframework.boot" --filename "build.gradle"
   # Properties
   GH_HOST=github.wdf.sap.corp gh search code "spring-boot.version" --extension properties
   ```

2. **Run searches in parallel** — make multiple independent Bash calls in one response

3. **Always use `--limit 100`** — default 30 is too low for broad searches

4. **Include version in search term** when looking for specific major versions:
   ```bash
   GH_HOST=github.wdf.sap.corp gh search code "spring-boot-starter-parent version 3" --extension xml
   ```

## Processing Results with Python

**NEVER** fetch files one-by-one in a loop. Use `textMatches` fragments directly.

### Standard template: extract and deduplicate

```bash
GH_HOST=github.wdf.sap.corp gh search code "SEARCH_TERM" --filename "pom.xml" --limit 100 \
  --json repository,path,textMatches 2>&1 | python3 -c "
import json, sys, re

data = json.load(sys.stdin)
results = {}
for item in data:
    repo = item['repository']['nameWithOwner']
    owner = repo.split('/')[0]
    # Skip personal repos (I/D/C + digits)
    if re.match(r'^[IDCidc]\d{5,}$', owner):
        continue
    for tm in item.get('textMatches', []):
        fragment = tm['fragment']
        # --- Customize extraction logic below ---
        for m in re.finditer(r'PATTERN_HERE', fragment):
            val = m.group(0)
            results.setdefault(repo, []).append(val)

for repo, vals in sorted(results.items()):
    print(f'{repo}: {vals}')
"
```

Adapt the `re.finditer` pattern per use case. For version comparison, sort by parsed version tuples.

## References

- **CLI flags, JSON fields, auth setup**: Read [references/gh-cli-reference.md](references/gh-cli-reference.md)
- **BizX repo naming and org conventions**: Read [references/bizx-repos.md](references/bizx-repos.md)
- **PR operations and file fetching**: Read [references/pr-operations.md](references/pr-operations.md)

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `textMatch` (singular) in `--json` | Use `textMatches` (plural, capital M) |
| `grep -P` on macOS | Use `python3` or `grep -E` |
| Fetching files one-by-one in a loop | Use `textMatches` fragments from search results |
| Not filtering personal repos | Add `re.match(r'^[IDCidc]\d{5,}$', owner)` check |
| Single query for broad questions | Use multiple varied search terms in parallel |
| Using default `--limit 30` | Always set `--limit 100` for broad searches |

## Important Constraints

1. **SAP network required.** Searches will fail if not connected to SAP internal network (VPN or enrolled device).
2. **Two hosts.** SAP has two GitHub Enterprise instances: `github.wdf.sap.corp` (legacy, most BizX repos) and `github.tools.sap` (newer). Always set `GH_HOST` explicitly.
3. **No file fetching loops.** Use `textMatches` from search results. If you must read a file, use `gh api` to fetch raw content — never in a loop over many files.
4. **100 result limit.** GitHub API caps at 100 results per query. Use varied search terms to get broader coverage.
5. **Personal repo filtering.** Repos owned by `I######`, `D######`, or `C######` are personal forks — filter them out unless specifically requested.
