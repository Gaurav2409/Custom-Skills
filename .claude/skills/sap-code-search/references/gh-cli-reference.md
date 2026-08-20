# gh CLI Reference for SAP GitHub Enterprise

## Authentication

```bash
gh auth login --hostname github.wdf.sap.corp
gh auth login --hostname github.tools.sap
```

## Targeting SAP Hosts

Every `gh` command defaults to `github.com`. Prefix with `GH_HOST` to target SAP:

```bash
GH_HOST=github.wdf.sap.corp gh <command>
GH_HOST=github.tools.sap gh <command>
```

SAP has two enterprise hosts:
- `github.wdf.sap.corp` — legacy SAP GitHub Enterprise
- `github.tools.sap` — newer SAP GitHub instance

## Code Search Flags

```bash
GH_HOST=github.wdf.sap.corp gh search code "TERM" --limit 100 --json repository,path,textMatches
```

| Flag | Example | Notes |
|------|---------|-------|
| `--language` | `--language java` | Filter by programming language |
| `--repo` / `-R` | `--repo bizx/au-recruiting` | Search within a specific repo |
| `--owner` | `--owner bizx` | Search within an org |
| `--filename` | `--filename "build.gradle"` | Filter by exact filename |
| `--extension` | `--extension java` | Filter by file extension |
| `--match` | `--match path` | Restrict to `file` contents or `path` |
| `--limit` / `-L` | `--limit 100` | Max results (default 30, max 100) |
| `--json` | `--json repository,path,textMatches` | JSON output |
| `--web` / `-w` | `--web` | Open results in browser |

## JSON Output Fields

Available fields for `--json`: `repository`, `path`, `sha`, `textMatches`, `url`

**IMPORTANT:** The field is `textMatches` (plural, capital M), NOT `textMatch`.

`textMatches` contains matched text fragments — no need to fetch full files in most cases.
