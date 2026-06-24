---
name: sap-ai-kb-delta-update
description: Pull the latest commits from all repos (and sub-repos) in the sap-ai workspace, detect changed files since the last ingest, copy the delta into the sap-ai-northstar-arch-kb raw directory, and trigger a compile for only the affected clusters. Use when the user says "delta update the KB", "pull and update the knowledge base", "sync sap-ai repos to the KB", "refresh the northstar KB", or "run the delta update".
---

# SAP AI KB Delta Update

Pull all git repos in the `/Users/I321170/Documents/cbc-ai/sap-ai/` workspace, detect files changed since the last KB ingest, copy the delta into `sap-ai-northstar-arch-kb/raw/`, and trigger a targeted compile for only the affected clusters.

**Fixed paths (hard-coded — no prompting needed):**
- Source workspace: `/Users/I321170/Documents/cbc-ai/sap-ai/`
- KB root: `/Users/I321170/Documents/LLM knowledge base/sap-ai-northstar-arch-kb/`
- Delta state file: `<KB root>/.delta_state.json`
- Compile ticket dir: `<KB root>/.compile-tickets/`
- Auto-trigger wrapper: `~/.claude/sap-ai-kb-auto/auto_delta_update.sh` (LaunchAgent-driven; see `~/.claude/sap-ai-kb-auto/README.md`)

---

## Automation context

The non-LLM parts of this skill (pull, detect, sync, gate-check) run **automatically**
on a daily schedule via the macOS LaunchAgent
`com.user.sap-ai-kb-auto-update.plist`. When auto-update detects a delta, it:

1. Pulls all repos
2. Syncs changed files to `raw/`
3. Updates `.delta_state.json`
4. Runs `scripts/v1_gate_check.py` to detect regressions
5. Writes a JSON "compile pending" ticket to `<KB root>/.compile-tickets/`
6. Notifies the user via macOS notification

The **LLM compile step** is intentionally NOT auto-triggered — it consumes
tokens and makes content decisions. When the user runs this skill interactively,
check for pending tickets and offer to compile them.

---

## Phase 0: Understand the request

Determine which mode the user wants:

| Trigger | Mode | Behavior |
|---|---|---|
| "delta update the KB", "run the delta update" | **interactive** | Default: prompt before each phase, full reporting |
| "delta update --auto", "auto-compile the pending delta" | **auto-compile** | Skip confirmations; compile any pending tickets directly |
| "dry run", "preview" | **dry-run** | Phases 1–3 only (pull + detect + report) |
| "pull only" | **pull-only** | Phase 1 only |
| "detect only" | **detect-only** | Phase 2 only (no pull) |
| "v1.0 gate", "release gate" | **gate-only** | Run `v1_gate_check.py` and report; no pull/compile |
| "ingest quality", "audit ingestions" | **quality-only** | Run `ingest_quality_check.py --strictness strict` |

If pending compile tickets exist in `<KB root>/.compile-tickets/`, offer to consolidate
them: "Found N pending compile tickets from auto-update. Compile all together (recommended) or one at a time?"

If auto-generated stubs exist in `<KB root>/.compile-tickets/auto-stubs/`, offer to fill
them: "Found N auto-generated stubs from prior lazy ingestions. Fill them all into full
articles (recommended)?" Each stub is an ADR that was previously closed via a `covered-by`
shortcut where the parent article didn't actually contain the substance — the stub
preserves the ADR's decision sentences + decision-makers + date for the compiler.

---

## Critical: NO LAZY `covered-by` SHORTCUTS

The catalog at `wiki/topics/all-in-on-ai-decisions.md` accepts two valid forms for closing
an ADR-coverage gap:

1. **Dedicated article** — `wiki/concepts/<adr-slug>.md` exists with full content.
2. **`covered-by` line** — `covered-by: <adr-slug> -> [[parent-article]]` ONLY when the
   parent article's body contains:
   - The ADR's status + date
   - The ADR's decision sentences (paraphrased is fine; verbatim is better)
   - The ADR's named decision-makers
   - At least 3 of the ADR's distinguishing key terms

The audit script `scripts/ingest_quality_check.py --strictness strict` enforces this
rule with a fingerprint-coverage threshold of 0.60. Lazy covered-by entries (where the
parent doesn't actually contain the substance) are auto-flagged and a stub is written
to `.compile-tickets/auto-stubs/<adr>.md`.

When you write a `covered-by` entry, the **same compile pass MUST also strengthen the
parent article** with the ADR's substance — quote the decision text, name the
decision-makers, footnote to the raw ADR. Otherwise the next ingestion-quality run
will flip the gate to FAIL.

---

## Phase 1: Pull all repos

---

## Cluster → Repo Map

This is the authoritative mapping used for routing delta files to the right cluster raw directory and compile scope.

| Cluster | Label | Repos |
|---------|-------|-------|
| A | Architecture Vision & Strategy | ai-native-northstar-arch, durable-ai-agents, ai-golden-path, TechnologyGuidelines |
| B | Protocols & Standards | a2a-protocol, a2a-agent-template, mcp-protocol, mcp-translation-specification, open-resource-discovery-specification, api-guidelines, namespace-registry, api-metadata-validator |
| C | Gateway & Integration | agent-gateway, integration-layer, agent-connector, agent-gateway-documentation, fx-engagement-layer-docs |
| D | MCP Platform | mcp-hub, sdk, btp-service-metadata-mcp, mcp-hub-documentation, docs |
| E | BAF & Joule | baf-commons, baf-documentation, baf-examples, joule-function-toolkit, joule-functions-example, joule-baf-dev-patterns, joule-capability, architecture |
| F | Identity & Security | iam-for-agents, all-in-identity |
| G | Metadata & Discovery | open-resource-discovery-reference-application, crawler, agent-registry-catalog, unified-landscape-model, ums, unified-ai-agent, apis-and-events-portal |
| H | Agent Frameworks, Eval & Observability | agent-evaluation, agent-skills, agent-extensibility-documentation, agent-runtime-domains, agent-documentation, agent-onboarding, agent-mcp-hub-sample, appfnd-bat, document-grounding-toolkit |
| I | SDKs & Developer Tools | cloud-sdk-python, common-lib, spring-boot-starter-ord, euporie-dwc-integration-js, sdk-demo |
| J | Docs & Onboarding | atom-docs, sirius, urm-docs, stakeholders-documentation, user-documentation, intapp-guide, ucl-onboarding-guide, pab-integration, unified-agent-runtime-documentation, landing-page-content, landing-page, documentation, n8n-ord-service |

Any repo in the workspace **not** in the map above is unassigned. The skill will report unassigned repos but will not fail.

---

## File-type filter

Only ingest files that contribute knowledge. Skip binary blobs, lock files, and build artifacts.

**Include:**
- `*.md`, `*.txt`, `*.rst`
- `*.py`, `*.ts`, `*.js`, `*.java`, `*.go`, `*.yaml`, `*.yml`, `*.json`, `*.toml`, `*.xml`
- `*.png`, `*.jpg`, `*.svg` (diagrams — vision pass during compile)
- `*.pdf`

**Exclude (never copy to raw/):**
- `node_modules/`, `__pycache__/`, `.git/`, `dist/`, `build/`, `target/`, `.nyc_output/`
- `*.lock`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`
- `*.min.js`, `*.min.css`, `*.map`, `*.d.ts`
- `*.jar`, `*.war`, `*.class`, `*.pyc`, `*.so`, `*.dylib`, `*.exe`
- Files >500 KB (flag, do not copy)

---

## Phase 0: Understand the request

Confirm the user wants a delta update (pull + detect + ingest + compile).

If the user says "dry run" or "preview", run Phases 1–3 only (pull, detect, report diff) and stop before copying or compiling. Ask: "Found N changed files across M clusters. Proceed with ingest and compile?"

If the user says "pull only", run Phase 1 only and stop.

If the user says "detect only" (no pull), skip Phase 1 and run Phase 2 only.

Default (no qualifier): run all phases (1–5).

---

## Phase 1: Pull all repos

**Goal:** Bring every git repo in the workspace up to date with its remote.

### 1a. Run `pull_all.py`

```bash
cd "/Users/I321170/Documents/cbc-ai/sap-ai"
python3 "/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/sap-ai-kb-delta-update/templates/scripts/pull_all.py" \
  --workspace "/Users/I321170/Documents/cbc-ai/sap-ai" \
  --output "/tmp/sap-ai-pull-report.json"
```

The script walks every immediate subdirectory of `--workspace`. For each directory that contains a `.git` folder, it runs `git fetch --all --prune` followed by `git pull --ff-only`. Repos where `git pull` would require a merge (non-fast-forward) are logged as `SKIPPED_MERGE_REQUIRED` — the pull is not forced. Repos with no remote are logged as `LOCAL_ONLY`.

### 1b. Read and summarise the pull report

Read `/tmp/sap-ai-pull-report.json`. Report to the user:

```
Pull summary
  Repos scanned:    <N>
  Updated:          <N> (list repo names)
  Already current:  <N>
  Skipped (merge):  <N> (list repo names + reason)
  Local only:       <N>
  Errors:           <N> (list repo names + error)
```

If any repo has errors or requires a merge, report them clearly. Continue unless the user says to abort.

---

## Phase 2: Detect delta

**Goal:** For each repo, find all files that changed since the commit SHA recorded in the delta state file. For repos that were not previously tracked (or have no state entry), treat all files as new.

### 2a. Load delta state

Read `<KB root>/.delta_state.json`. It has this shape:

```json
{
  "schema": 1,
  "last_run": "2026-05-27T00:00:00Z",
  "repos": {
    "a2a-protocol": {
      "last_commit": "abc123",
      "last_run": "2026-05-27T00:00:00Z"
    }
  }
}
```

If the file does not exist, treat every repo as new (full ingest of all qualifying files).

### 2b. Run `detect_delta.py`

```bash
python3 "/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/sap-ai-kb-delta-update/templates/scripts/detect_delta.py" \
  --workspace "/Users/I321170/Documents/cbc-ai/sap-ai" \
  --state "/Users/I321170/Documents/LLM knowledge base/sap-ai-northstar-arch-kb/.delta_state.json" \
  --output "/tmp/sap-ai-delta-report.json"
```

The script reads the state file, gets the current HEAD SHA for each repo, diffs it against the last recorded SHA (`git diff --name-status <last_commit>..HEAD -- <qualified files>`), and writes a structured report.

### 2c. Read and summarise the delta report

`/tmp/sap-ai-delta-report.json` has this shape:

```json
{
  "generated_at": "<ISO timestamp>",
  "clusters_affected": ["A", "E"],
  "repos": {
    "a2a-protocol": {
      "cluster": "B",
      "last_commit": "abc123",
      "current_commit": "def456",
      "changed_files": ["docs/spec.md", "README.md"],
      "deleted_files": [],
      "status": "updated"
    },
    "new-repo": {
      "cluster": null,
      "last_commit": null,
      "current_commit": "xyz789",
      "changed_files": ["README.md"],
      "deleted_files": [],
      "status": "new_untracked"
    }
  }
}
```

Report to the user:

```
Delta summary
  Clusters affected:  <list>
  Repos with changes: <N>
  Total changed files: <N>
  Deleted files:       <N>
  Unassigned repos:    <N> (list names)

Per-cluster breakdown:
  Cluster A: <repo1> (+3 files), <repo2> (+1 file)
  Cluster E: <repo1> (+7 files), <repo2> (2 deleted)
```

If zero changes detected, log a no-op entry in `wiki/log.md` and stop:
```
## [YYYY-MM-DD] delta-update | no changes detected
- All repos at last-ingested SHA. Nothing to ingest.
```

---

## Phase 3: Copy delta to raw/

**Goal:** Copy changed files from the workspace into the KB's `raw/repos/<cluster-<letter>>/` directories, mirroring the source structure. Delete KB raw copies of deleted source files.

### 3a. Run `sync_repos.py`

```bash
python3 "/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/sap-ai-kb-delta-update/templates/scripts/sync_repos.py" \
  --workspace "/Users/I321170/Documents/cbc-ai/sap-ai" \
  --kb-root "/Users/I321170/Documents/LLM knowledge base/sap-ai-northstar-arch-kb" \
  --delta-report "/tmp/sap-ai-delta-report.json" \
  --cluster-map-builtin
```

The script reads the delta report, uses the built-in cluster map (defined inside the script), and for each changed file:
- Copies `<workspace>/<repo>/<file>` → `<kb-root>/raw/repos/cluster-<letter>/<repo>/<file>`, creating intermediate directories.
- For deleted files: removes the corresponding file from `raw/repos/cluster-<letter>/<repo>/` if it exists.
- Skips files matching the exclude list (node_modules, lock files, binaries, >500 KB).
- Writes a copy report to `/tmp/sap-ai-sync-report.json`.

For repos with `cluster: null` (unassigned): skip copy, log as `UNASSIGNED_SKIPPED`.

### 3b. Update delta state

After sync completes, update `.delta_state.json`:
- Set `last_run` to current ISO timestamp.
- For each repo that was processed, update `repos.<name>.last_commit` to `current_commit` from the delta report.
- Do not touch entries for repos with no changes.

Write the updated state back to `<KB root>/.delta_state.json`.

### 3c. Report

```
Sync complete
  Files copied:   <N> across <M> clusters
  Files deleted:  <N>
  Skipped (filter): <N>
  Unassigned:     <N>
```

---

## Phase 4: Ingest into KB

**Goal:** Register the newly copied files with the KB's ingest system.

### 4a. For each affected cluster, run `ingest.py`

Use the KB's existing `scripts/ingest.py`:

```bash
KB_ROOT="/Users/I321170/Documents/LLM knowledge base/sap-ai-northstar-arch-kb"
for CLUSTER in <affected clusters>; do
  CLUSTER_LOWER=$(echo "$CLUSTER" | tr '[:upper:]' '[:lower:]')
  python3 "$KB_ROOT/scripts/ingest.py" \
    --source "$KB_ROOT/raw/repos/cluster-$CLUSTER_LOWER" \
    --kb-root "$KB_ROOT" \
    --batch-label "delta-$(date +%Y%m%d)-cluster-$CLUSTER"
done
```

`ingest.py` scans the directory, registers new/modified files in `wiki/_summaries.md`, and queues them for the next compile.

### 4b. Log ingest

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] ingest | delta update — clusters <list>
- Trigger: delta-update skill (pull + detect + sync)
- Pull report: /tmp/sap-ai-pull-report.json
- Delta report: /tmp/sap-ai-delta-report.json
- Clusters affected: <list>
- Files ingested: <N>
- Files deleted: <N>
- Repos updated: <list of repo names>
```

---

## Phase 5: Compile affected clusters

**Goal:** Re-compile only the clusters that received new or changed files.

### 5a. Confirm before compiling

Always confirm with the user before starting a compile:

> "Delta ingested. Ready to compile **clusters <list>** (N files changed). This will use Opus quality-mode two-pass as configured in the KB's CLAUDE.md. Proceed?"

### 5b. Hand off to llm-knowledge-base skill for each affected cluster

For each affected cluster, invoke the llm-knowledge-base skill in Compile mode, scoped to that cluster. Pass context:
- KB root path
- Cluster label and letter (e.g., "Cluster A — Architecture Vision & Strategy")
- "Delta compile — only files changed since last ingest. Existing articles may need verb-logic updates (strengthen / update / contradict / add) rather than full rewrites."
- Quality mode: Opus, two-pass (as per KB CLAUDE.md — non-negotiable)
- After compile: run `scripts/lint.py --run-cqs touched` for the affected cluster
- RAPTOR summaries: rebuild L0/L1/L2 for the cluster if ≥8 articles changed

### 5c. Verb logic for delta compiles

When updating articles in response to changed source files, follow the KB's compile verb logic:

| Signal | Action |
|--------|--------|
| Source file has new content not in article | `add` — append to `## Details` with new footnote |
| Source file updates an existing claim with compatible new info | `strengthen` — increase confidence score if evidence is stronger |
| Source file revises a claim (same topic, new value/conclusion) | `update` — replace old claim, note supersession, update footnote |
| Source file contradicts an existing article claim | `contradict` — flag in `## Open Questions`, trigger Step 8.5 debate if irresolvable |

Do NOT rewrite the entire article on a delta compile unless >50% of the article's source files changed. Surgical updates are preferred.

### 5d. Post-compile log

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] compile | delta compile — clusters <list>
- Source: delta-update skill
- Clusters compiled: <list>
- Articles updated: <N>
- Articles created: <N>
- Verb actions: add=<N>, strengthen=<N>, update=<N>, contradict=<N>
- Lint CQ coverage: <N>% (target ≥80%)
- Open questions raised: <N>
- Compile mode: quality (Opus, two-pass)
```

### 5e. Git commit

After compile and lint, commit:

```bash
cd "/Users/I321170/Documents/LLM knowledge base/sap-ai-northstar-arch-kb"
git add wiki/ .delta_state.json
git commit -m "delta update $(date +%Y-%m-%d): clusters <list>, <N> articles updated"
```

---

## Phase 6: Summary report

After all phases complete, output a concise summary:

```
Delta update complete — YYYY-MM-DD

Pull
  Updated:     <N> repos
  Skipped:     <N>

Delta
  Changed files:   <N> across <M> repos
  Deleted files:   <N>

Sync
  Copied to raw/:  <N> files
  Removed:         <N>

Ingest
  Registered:  <N> files

Compile
  Clusters:     <list>
  Articles updated: <N>
  Articles created: <N>
  CQ coverage:  <N>%

State saved to: <KB root>/.delta_state.json
Wiki committed: yes
```

---

## Error handling

| Situation | Action |
|-----------|--------|
| `git pull` fails (network/auth) | Log error, skip repo, continue with others. Report at end. |
| `git pull` non-fast-forward | Log as SKIPPED_MERGE_REQUIRED, skip, report to user. |
| Repo has no remote | Log as LOCAL_ONLY. Delta detect still runs against working tree. |
| File >500 KB | Log as OVERSIZED_SKIPPED, do not copy. |
| `ingest.py` not found | Abort Phase 4 with: "ingest.py not found at <path>. Run the llm-knowledge-base skill to re-scaffold scripts." |
| Delta state missing | Treat all files as new (full baseline ingest). Log: "No prior delta state — performing full baseline scan." |
| Unassigned repo | Skip copy phase for that repo, log as UNASSIGNED_SKIPPED. Do not fail. |
| Zero changes after pull | Skip Phases 3–5, log no-op entry, report to user. |

---

## Registering the skill in Claude Code settings

To make this skill available as `/sap-ai-kb-delta-update` in Claude Code, add it to your project or global settings:

```json
{
  "skills": [
    "/Users/I321170/Documents/cbc-ai/skills-repo/.claude/skills/sap-ai-kb-delta-update"
  ]
}
```

Or run `/update-config` and ask Claude to add the skill path.
