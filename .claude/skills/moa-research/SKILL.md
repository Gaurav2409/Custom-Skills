---
name: moa-research
description: Run large-context, large-output research protocols through Hermes Mixture-of-Agents. Use when a research task needs (a) MoA aggregation for diversity, (b) inputs too big for one prompt, (c) outputs bigger than a single Opus response (>10 KB structured markdown). Handles inlining, output chunking, adversarial verification, and stitching. Trigger: `/moa-research`
---

# moa-research

Skill for building research workflows that route through **Hermes Mixture-of-Agents** with:

- **Large inputs** (whole corpora inlined — 100s of KB, up to macOS ARG_MAX ~1 MB)
- **Large outputs** (chunked emission — MoA aggregator has a ~10 KB self-imposed ceiling per call on dense structured markdown, empirically confirmed even with max_tokens=32000)
- **Structural integrity** (adversarial multi-lens verify + stitcher)
- **Resumability** (Claude Code Workflow tool caches completed agents; re-runs are cheap)

Use this skill when the user asks for MoA-based research/analysis, or invokes `/moa-research`, or when a research protocol involves ingesting one or more large source documents and producing a structured multi-section artifact.

---

## Fundamental constraints (measured, not theoretical)

Before you design anything, internalize these hard limits. Fighting them costs tokens.

**F1. MoA reference models CANNOT read files.** They are LLM API calls, not tool-using agents. Any filepath you name in a prompt is invisible unless the file contents are inlined into the prompt text. The [lib/moa-call.sh](lib/moa-call.sh) wrapper handles this via `===INLINE:<absolute-path>===` directives.

**F2. Opus aggregator self-imposes ~10 KB output ceiling on dense structured markdown.** Not tunable by `max_tokens`. Empirically: an 800-line generic list generates cleanly at 43 KB / ~9700 tokens; a 50-70 KB dense multi-section research artifact truncates at ~10 KB every time even with `max_tokens: 32000`. Fix: chunk the output into 2-3 MoA calls, each producing 3-4 sections. Never demand a single MoA call produce >10 KB of dense structured content.

**F3. Claude Code Bash tool caps at 10 minutes.** A single `moa-call.sh` invocation can exceed 10 min for large-context calls. The [lib/moa-call.sh](lib/moa-call.sh) wrapper handles the wait; the workflow shepherd's Bash call may time out but the underlying `hermes -z /moa` process is properly parented and continues. Poll `pgrep -fa moa-call.sh` if you need to wait past 10 min.

**F4. Hermes MoA `deep-research` preset has `max_tokens: 8192` by default.** Bump to 32000 in `~/.hermes/config.yaml` before running anything substantial. See [references/hermes-moa-config.md](references/hermes-moa-config.md).

**F5. macOS argv ceiling: ~1 MB (ARG_MAX = 1,048,576).** The `moa-call.sh` wrapper passes the expanded prompt via argv. If your inlined prompt exceeds ~800 KB, split into two calls or switch to stdin piping.

**F6. Silent failures are common.** MoA can return 0-byte stdout with exit 0 or exit 3 and no stderr when a reference model errors upstream. The wrapper detects empty output and non-zero exit; the workflow should surface CHECKPOINT_FAILED rather than treat 0-byte as "still running".

**F7. Aggregator collapses top-level headings.** If asked for `## 1.`, `## 2.`, `## 3.` structure, Opus sometimes demotes `## 3.` to `### 3.1` under `## 2.` — content is present, heading level is wrong. Fix: chunked emission (one section family per call) makes each `##` heading load-bearing, not optional. Plus a stitcher that validates headings.

---

## The seven-step recipe

Every MoA research workflow built from this skill follows the same shape. Deviate only when a step doesn't apply.

### Step 1 — Enumerate the corpus and the artifact

Before writing any code, list:

| What | Where | Size estimate |
|---|---|---|
| Master prompt / role definitions | absolute path | KB |
| Grounding / authoritative anchors | absolute path | KB |
| Source corpus files (1..N) | absolute paths | total KB |
| Any phase-specific gate criteria | absolute paths | KB |

Then list the **artifact**:

- Number of top-level sections (each `## N. Title`)
- Estimated size per section (KB)
- Total artifact size (KB)
- Structural contracts: numbered lists ≥ K, verbatim quotes with anchors, forbidden terms, mandatory terms

Compute:
- Total inline size (must be < 800 KB for argv safety)
- Total output size / 10 KB per chunk → number of MoA calls

If inputs > 800 KB, split into multiple chunk families each seeing only the relevant subset. If output > 50 KB, use 3+ chunks minimum.

### Step 2 — Bump Hermes `max_tokens` for the preset you'll use

Verify current setting:

```bash
grep -B 1 -A 15 "deep-research:" ~/.hermes/config.yaml | grep max_tokens
```

If it says `max_tokens: 8192` (default for deep-research), bump it:

```bash
BAK=~/.hermes/config.yaml.pre-moa-research.$(date +%Y%m%d%H%M%S).bak
cp ~/.hermes/config.yaml "$BAK"
python3 -c "
import pathlib
p = pathlib.Path.home() / '.hermes/config.yaml'
p.write_text(p.read_text().replace('max_tokens: 8192', 'max_tokens: 32000'))
print('bumped max_tokens to 32000')
"
```

The other presets (default, code, fast) already ship at 32000.

### Step 3 — Copy `moa-call.sh` into your workflow's orchestration/ dir

The `moa-call.sh` wrapper handles `===INLINE:<path>===` expansion, argv-safe prompt passing, preset detection, empty-output detection, and stderr capture.

```bash
mkdir -p <your-workdir>/orchestration
cp ~/.claude/skills/moa-research/lib/moa-call.sh <your-workdir>/orchestration/
chmod +x <your-workdir>/orchestration/moa-call.sh
```

**Smoke-test before wiring into a workflow:**

```bash
echo 'You are the MoA aggregator. Reply with the single word PONG.' > /tmp/probe.prompt
<your-workdir>/orchestration/moa-call.sh deep-research /tmp/probe.prompt /tmp/probe.out
cat /tmp/probe.out                                # should say PONG
```

If PONG doesn't come back in under 60 seconds, stop — MoA is broken, no workflow will help.

### Step 4 — Author the workflow using the chunked pattern

Use [templates/workflow-template.js](templates/workflow-template.js) as the starting shape. The critical structure:

```
export const meta = { name, description, phases: [...] }

phase('Scaffold')
// One agent creates the workdir tree.

phase('Chunked MoA')
// For each output-section family:
//   agent → Write chunk-prompt file → Bash moa-call.sh → validate → return
// Chunks run SEQUENTIALLY (not parallel), one MoA call at a time,
// because Hermes serializes /moa invocations client-side.

phase('Stitch')
// One agent reads all chunks, validates headings + SELF-AUDIT comments,
// concatenates into the final artifact, or writes CHECKPOINT_FAILED.

phase('Verify')  // OPTIONAL but strongly recommended when output correctness matters
// 3 parallel Claude Opus verifiers, each with a DISTINCT lens:
//   V1: identity / definitional integrity
//   V2: structural / layer discipline
//   V3: gate coverage / completeness
// Each writes its own report; each defaults to FAIL on ambiguity.

phase('Judge')  // OPTIONAL
// 1 Claude Opus judge reads the 3 lens reports, computes joint verdict,
// writes suggested prompt-patch on NO-GO.
```

**Each chunk's MoA prompt must:**

1. Begin with a shared `PROMPT_HEADER` block: hard rules, layer discipline reminders, forbidden terms.
2. Inline all needed source files via `===INLINE:<absolute-path>===` directives on their own lines.
3. Declare **exactly which sections** the chunk emits ("You emit §§4-6 only") — never "produce the whole artifact".
4. End with an explicit structural checklist and a `<!-- CHUNK-X SELF-AUDIT: ... -->` HTML comment the aggregator must emit at the end. The stitcher checks for this comment as truncation evidence.
5. Aim for 8-20 KB per chunk. Never exceed 25 KB. If your chunk plan exceeds 25 KB, split it further.

See [templates/chunk-prompt-shape.md](templates/chunk-prompt-shape.md) for the exact shape.

### Step 5 — Author adversarial multi-lens verifiers

Losing Fable through HAI, or when you need the highest confidence in output correctness, replace "one verifier who checks everything" with **N verifiers, each with one lens**. Each verifier:

- Reads the same input (the stitched artifact) + only the authoritative anchor doc for its lens
- Runs a bounded set of checks (5-10) — never "everything"
- Defaults to FAIL on ambiguity
- Writes its report to a lens-specific file
- Returns a one-line verdict

**Distinct lenses beat redundant verifiers.** Three verifiers with identical prompts catch the same failures. Three verifiers with orthogonal blind spots catch what redundancy can't.

See [templates/verifier-prompt-shape.md](templates/verifier-prompt-shape.md).

### Step 6 — Author the synthesis judge

One Claude Opus reads the N lens reports, computes joint verdict:

- **GO** = all lenses returned GO
- **REVIEW** = 0 lens FAIL but ≥1 REVIEW
- **NO-GO** = any lens FAIL

On NO-GO the judge produces a "Suggested Prompt Patch" block — the exact text to insert into the failing chunk's MoA prompt on retry. This is the fastest path to recovering from a failed run.

See [templates/judge-prompt-shape.md](templates/judge-prompt-shape.md).

### Step 7 — Launch, monitor, resume

**Launch:**

```
Workflow({
  scriptPath: "<absolute path to your workflow .js>",
  args: { workdir: "/absolute/path/runs/<timestamp>" }
})
```

**Monitor:**

- `/workflows` shows live agent tree
- Check MoA progress: `pgrep -fa moa-call.sh` (alive = still working) and `wc -c <workdir>/_logs/*.raw.md` (bytes = actual output)
- If a shepherd's Bash call times out at 10 min but the underlying `hermes -z /moa` is still alive, do NOT kill — wait it out or the workflow will burn tokens on retry

**Resume:**

If any agent fails, edit the workflow script (fix the prompt, tune the validator), then:

```
Workflow({
  scriptPath: "...same path...",
  resumeFromRunId: "wf_...previous_id...",
  args: { workdir: "...same workdir..." }
})
```

Completed agents replay from cache instantly. Only the edited/failed agents re-run.

---

## Cost expectations

For a research protocol with:

- Inputs: 200-300 KB total (whole corpus inlined)
- Output: 40-70 KB structured markdown across 8 sections
- Verification: 3-lens adversarial verify + 1 judge

Expect:

- **MoA calls**: 3 chunked calls × 3-10 min wall-clock each = 15-30 min sequential
- **Verifier + judge**: 4 Claude Opus subagents ≈ 5-10 min parallel
- **Tokens**: ~200-400k output tokens for the whole workflow
- **Dollar cost via HAI**: single-digit dollars typically
- **Wall-clock**: 30-45 min end-to-end

If your run costs materially more than this, something is looping — kill and diagnose before spending more.

---

## Failure playbook

When something goes wrong, consult in this order:

1. **0-byte MoA output** → check `hermes moa list` shows the expected preset, check `~/.hermes/logs/agent.log` tail for provider errors. Most often: reference model timeout or upstream 5xx.
2. **Truncated MoA output** (ends mid-sentence, missing self-audit comment) → chunk was too big. Split further.
3. **Wrong heading levels** (`### 3.1` where `## 3.` was demanded) → aggregator collapsed headings. Push structural check to the tail of the chunk prompt, add the SELF-AUDIT comment as evidence of full emission.
4. **Content is right but structural checks fail** → validator was too picky (e.g., hyphenation check). Loosen to substring `in` rather than regex-exact.
5. **All 3 lens verifiers agree on NO-GO** → the artifact is genuinely broken. Read the judge's suggested prompt patch and iterate the chunk prompt.
6. **1 of 3 lens verifiers NO-GO, other 2 GO** → the failing verifier is likely miscalibrated. Read its lens report and decide whether to adjust its threshold or accept the finding.
7. **Watchdog kills the workflow subagent mid-generation** → the shepherd is writing a large artifact in one Write call. Break into sectioned Write + Edit calls (each < 180s of streaming). See [references/watchdog-mitigation.md](references/watchdog-mitigation.md).

---

## Key references

- [lib/moa-call.sh](lib/moa-call.sh) — the wrapper. `<preset> <prompt-file> <output-file>`. Handles inlining, argv-safe passing, empty-output detection.
- [templates/workflow-template.js](templates/workflow-template.js) — copy-paste starting point for a 3-chunk MoA workflow with adversarial verify.
- [templates/chunk-prompt-shape.md](templates/chunk-prompt-shape.md) — the exact prompt shape each chunk uses.
- [templates/verifier-prompt-shape.md](templates/verifier-prompt-shape.md) — adversarial verifier prompt template.
- [templates/judge-prompt-shape.md](templates/judge-prompt-shape.md) — synthesis-judge prompt template.
- [references/hermes-moa-config.md](references/hermes-moa-config.md) — MoA preset definitions, active-preset switching (`hermes moa configure` is interactive; `~/.hermes/config.yaml` is authoritative).
- [references/watchdog-mitigation.md](references/watchdog-mitigation.md) — how to keep Claude Code Workflow's 180s stall-watchdog fed during large artifact writes.
- [references/why-not-single-moa-call.md](references/why-not-single-moa-call.md) — the empirical evidence for chunking, the 800-line probe, the ~10 KB ceiling.

---

## When NOT to use this skill

- **Single small MoA call is enough.** If your input fits in 5 KB and output fits in 5 KB, just use `hermes -z "/moa <prompt>"` directly. Don't spin up a workflow.
- **You need Fable-tier intelligence.** HAI proxy does not route Fable. This skill uses Sonnet + Opus refs + Opus aggregator (deep-research preset). If Fable becomes available, revisit — but as of 2026-07-03 it's not reachable via HAI/Hermes.
- **You need real streaming output.** MoA aggregator emits final response only; there is no incremental delivery. If a user wants to watch output stream, don't use MoA — use `hermes` in interactive mode.
- **The task is extraction, not synthesis.** If the task is "read this doc and extract a table", single-Claude-Opus is faster, cheaper, and more reliable than MoA. MoA earns its cost on judgment tasks (taxonomies, red-team invention, benchmark design, cross-source triangulation) where cross-family diversity actually helps.

---

## Attribution note

Every constraint in this skill (F1-F7) is empirically validated. Not theoretical. If you find one to be wrong on your setup, update this SKILL.md and the affected reference — don't just work around it.
