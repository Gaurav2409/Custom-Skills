---
name: moa-research
description: Run large-context, large-output research protocols through Hermes Mixture-of-Agents. Use when a research task needs (a) MoA aggregation for diversity, (b) inputs too big for one prompt, (c) outputs bigger than a single Opus response (>10 KB structured markdown). Handles inlining, output chunking, adversarial verification, and stitching. Trigger: `/moa-research`
---

# moa-research

Route knowledge work through **Hermes Mixture-of-Agents** (MoA): several reference models (different families) draft in parallel, an Opus aggregator synthesizes. Two ways to use this skill:

1. **Fire one MoA call** — a single adversarial review, synthesis, or red-team. Use the Quick Start below. This is most calls.
2. **Build a MoA workflow** — large corpora inlined, large outputs chunked, adversarial verify + stitch, resumable. Use the seven-step recipe further down.

Use when the user invokes `/moa-research`, asks to "run this through MoA / mixture-of-agents," or when a task needs cross-family diversity, an input too big for one prompt, or a structured artifact >10 KB.

---

## Quick Start — fire one MoA call

Any agent can do this. Four steps; do not skip step 1 or step 4.

```bash
# 0. One-time: the safe wrapper must exist (it usually does — it ships in this skill).
ls ~/.claude/skills/moa-research/lib/moa-call-safe.py

# 1. VERIFY REFS ARE LIVE (non-negotiable — see F12). If refs are dead, MoA silently
#    degrades to solo-Opus wearing a MoA costume. This 10-second check prevents that.
cd /Users/I321170/Documents/AI_Knowledge/hermes-agent
./venv/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from hermes_cli.config import load_config
from hermes_cli.moa_config import resolve_moa_preset
from agent.moa_loop import _run_reference
preset = resolve_moa_preset(load_config().get("moa") or {}, "deep-research")   # or your preset
refs = preset.get("reference_models") or []
msgs = [{"role":"user","content":"Reply with exactly: OK"}]
ok = sum("OK" in (t or "") and "failed" not in (t or "")
         for _,t,_ in (_run_reference(r, msgs, temperature=0.75, max_tokens=None) for r in refs))
print(f"{ok}/{len(refs)} reference models LIVE")
PY
# Require ok == len(refs). If fewer, STOP and debug (references/hermes-moa-config.md) —
# do NOT fire; you would get solo-Opus, not MoA.

# 2. Write your prompt to a file. Inline whole source files with a directive on its own line:
#      ===INLINE:/abs/path/to/source.md===
#    Reference models CANNOT read files (F1); the wrapper pastes the bytes in.

# 3. FIRE via the Python wrapper (never the bash one — F11). Background it if >10 min (F3).
python3 ~/.claude/skills/moa-research/lib/moa-call-safe.py deep-research \
  /abs/path/to/your.prompt  /abs/path/to/output.md
#   preset ∈ {default, deep-research, code, fast}. deep-research = 3 refs (max diversity).

# 4. VALIDATE the output before trusting it (F6):
#    - non-zero bytes (0-byte = silent ref failure, NOT success)
#    - if you asked for a self-audit HTML comment, it must be present (truncation evidence)
#    - if the first line says "reference models lacked context" / "N drafts: failed/abstaining",
#      the refs died mid-call → it was solo-Opus. Re-run step 1, then re-fire.
```

**That's the whole loop.** Everything below is for the workflow case (many calls, chunked output, verify/stitch) or for tuning cost. If you just need one MoA answer, you are done after step 4.

---

## Fundamental constraints (measured, not theoretical)

Before you design anything, internalize these hard limits. Fighting them costs tokens.

**F1. MoA reference models CANNOT read files.** They are LLM API calls, not tool-using agents. Any filepath you name in a prompt is invisible unless the file contents are inlined into the prompt text. Both wrappers ([lib/moa-call-safe.py](lib/moa-call-safe.py) preferred, [lib/moa-call.sh](lib/moa-call.sh) legacy) expand `===INLINE:<absolute-path>===` directives (each on its own line).

**F2. Opus aggregator self-imposes ~10 KB output ceiling on dense structured markdown.** Not tunable by `max_tokens`. Empirically: an 800-line generic list generates cleanly at 43 KB / ~9700 tokens; a 50-70 KB dense multi-section research artifact truncates at ~10 KB every time even with `max_tokens: 32000`. Fix: chunk the output into 2-3 MoA calls, each producing 3-4 sections. Never demand a single MoA call produce >10 KB of dense structured content. (A single review/synthesis can run ~20-30% over an 8 KB ask before it truncates — treat the ceiling as a soft ~10 KB, not the number you write in the prompt.)

**F3. Claude Code Bash tool caps at 10 minutes.** A single wrapper invocation can exceed 10 min for large-context calls. Fire it with `run_in_background: true` and wait for the completion notification, or poll `pgrep -fa moa-call-safe` (alive = still working) and `wc -c <output-file>` (bytes = real progress). The underlying `hermes -z /moa` is properly parented and continues even if a foreground Bash call times out — do NOT kill and retry, you will double-bill.

**F4. Verify `max_tokens` for your preset.** `deep-research` historically shipped at `max_tokens: 8192`, which truncates dense markdown at ~10 KB; the other presets ship at 32000. Check and bump if needed. See [references/hermes-moa-config.md](references/hermes-moa-config.md). (Note: MoA does NOT cap reference-model output by default — `reference_max_tokens` is unset — so a stray `max_tokens: 8192` mainly bites the aggregator, not the refs.)

**F5. macOS argv ceiling: ~1 MB (ARG_MAX = 1,048,576).** The wrapper passes the expanded prompt via argv. If the expanded prompt exceeds ~800 KB it errors out rather than truncating — split into multiple calls each seeing only the relevant corpus slice.

**F6. Silent failures are common; a 0-byte or degraded output is NOT success.** MoA can return 0-byte stdout with exit 0/3 and no stderr when a reference model errors upstream. The wrapper detects empty output and non-zero exit. Beyond that, ALWAYS read the first line of the output: if it says "reference models lacked context" or "N drafts: failed/abstaining," the refs died and you got solo-Opus — re-verify refs (F12) and re-fire. Never adopt a MoA artifact without this glance.

**F7. Aggregator collapses top-level headings.** If asked for `## 1.`, `## 2.`, `## 3.` structure, Opus sometimes demotes `## 3.` to `### 3.1` under `## 2.` — content is present, heading level wrong. Fix: chunked emission (one section family per call) makes each `##` load-bearing; add a `<!-- SELF-AUDIT: ... -->` HTML comment at the tail the stitcher checks for.

**F8. Preset choice is per-chunk, not per-workflow.** `deep-research` (3 refs: gpt-5.5 + 4.7-opus + sonnet → Opus aggregator) is ~1.5-2× the input-token cost of `default` (2 refs: gpt-5.5 + 4.7-opus → Opus aggregator). Cross-family diversity earns its cost on generative/adversarial work (novel synthesis, taxonomies, red-teams, canonical extraction). On structural work (matrix rows, table cells, verbatim extraction, schema-driven fills), the third family adds cost without adding angles — use `default`, or skip MoA and use solo Opus at `effort:high` (5-10× cheaper). Confirmed 2026-07-03: A4/A8 re-pass produced 82 KB / 118 KB artifacts on `default`, quality comparable to `deep-research`.

**F9. Verify + judgment scaffolding is expensive and often unnecessary.** A 3-lens × 2-artifact × solo-and-MoA verify pass costs ~1.5M input tokens. If a human reads the artifact before adoption, verify+judgment is waste. Enable it only when (a) artifacts adopted without human read, (b) 20+ artifacts to compare, or (c) automated CI-style gating. Otherwise default OFF.

**F10. Raw web sources contain 40–60% structural noise that wastes MoA context.** `web_extract` / browser-harness / jina keep cookie banners, nav menus, image refs, carousel repetition, footer/CTA boilerplate. Inlined via `===INLINE:===`, this noise burns reference-model context for nothing. Run the CLEAN-BEFORE-SAVE protocol on every fetched URL before writing it to disk. See [references/web-extraction-cleaning.md](references/web-extraction-cleaning.md).
- **Reject/log FAILED** (don't save): 404/error pages, cookie-banner intercepts, content <400 chars after cleaning.
- **Strip before saving**: cookie banners, image markdown lines, nav menus (4+ consecutive link-list items), footer boilerplate (stop at `## Learn`, `## Resources`, `© YEAR`, `Create an account`), carousel duplicates (same line within 30 lines), CTA lines.
- **Do not strip**: tables, numbered lists, inline code, headers, quoted text.

**F11 (shell-escape). ALWAYS use the Python wrapper; the bash wrapper breaks silently on prompts containing code.** `moa-call.sh` passes the expanded prompt to `hermes -z "/moa ..."` via double-quoted bash argv. Prose-only prompts survive. Prompts that inline TypeScript/JS/Python/bash source — or markdown dense with backtick code-spans and `${...}` (e.g. rule IDs like `` `HC_i` ``, `` `radius(a, ρ, κ)` ``) — trigger shell command-substitution that mutilates the argv before hermes runs. Result: exit 0, 0-byte or corrupted output, no stderr. `lib/moa-call-safe.py` fires `subprocess.run([argv], ...)` with no shell, so bytes reach hermes verbatim. Confirmed twice: 2026-07-09 (138 KB TS inline → 0 bytes on bash, 42 KB on Python) and 2026-07-14 (108 KB backtick-dense markdown → clean on Python). **Default to `moa-call-safe.py` for every call.** The bash wrapper is retained only for legacy prose-only pipelines.

**F13 (macOS Spotlight venv scan). Add the hermes venv to Spotlight Privacy or every cold-start subprocess takes 60-100s.** On macOS, Spotlight indexes `.pyc` files as they are created/modified. When the venv's Python version (3.11) differs from the system Python (3.14), `.pyc` files are version-tagged and regenerated on every import — and each regeneration triggers Spotlight scanning that blocks disk reads for 5-25s per file. Measured: `import openai` alone takes 68s cold. Fix: **System Settings → Siri & Spotlight → Spotlight Privacy → add `/Users/I321170/Documents/AI_Knowledge/hermes-agent/venv`**. After adding, the next cold import takes <5s. This is a one-time manual step — no programmatic fix works from a subprocess. The `moa-call-safe.py` wrapper auto-re-execs with the venv Python (to ensure correct site-packages), but the Spotlight exclusion must be done manually first. Verify the fix: `time /Users/I321170/Documents/AI_Knowledge/hermes-agent/venv/bin/python3 -c "import sys,os; sys.path.insert(0,os.path.expanduser('~/Documents/AI_Knowledge/hermes-agent')); import openai; print('OK')"` — should be <5s, not 60-100s. Do NOT run `compileall` to work around this — it writes more `.pyc` files, triggering more Spotlight scanning, making things worse.

**F12 (live-refs). Verify reference models respond BEFORE every substantive fire — MoA degrades to solo-Opus silently.** When reference models error or abstain (HAI proxy load, transient upstream 5xx, rate-limit on the concurrent fan-out, a stale provider config), the Opus aggregator proceeds ALONE and synthesizes from the prompt — you get a valid Opus answer with zero cross-family diversity, and nothing fails loudly. The only tell is the aggregator's own preamble ("N drafts: failed/abstaining"). This wasted a full session (2026-07-16): a VA-1 review and a peer's fable run both silently ran solo-Opus. **Fix:** run the Quick-Start step-1 live-refs probe (`_run_reference` on each slot, require all return non-"failed") immediately before firing. The probe needs a **180s+ timeout** (each ref takes 30-40s cold — see F13). If it's a transient dip, the probe catches it and you retry; if a ref is genuinely misconfigured, debug per [references/hermes-moa-config.md](references/hermes-moa-config.md). A PONG probe is NOT sufficient — it exercises the aggregator, not the refs.

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

### Step 2b — Ensure raw source files are clean before inlining (F10)

If your workflow inlines raw web-sourced files via `===INLINE:===`, run the cleaning pass first. Dirty files waste ~40-60% of reference-model context on cookie banners, nav menus, and image refs.

Quick pre-inline clean (run once per source directory or per file before launching the workflow):

```bash
python3 ~/.claude/skills/moa-research/lib/clean_sources.py \
  /path/to/raw/articles/<brief-slug>/web-sources/
```

Or per-file inside the workflow script before building the prompt:

```python
# In a scaffold agent — clean all raw sources before prompt construction
import pathlib, re

def clean_web_content(raw, url=""):
    # Cookie banners
    raw = re.sub(r'(?is)(we use (essential )?cookies.*?)(save preferences|dismiss|cancel|accept cookies)', '', raw)
    raw = re.sub(r'(?is)(select your cookie preferences.*?)(save preferences|dismiss)', '', raw)
    # Image markdown refs with no useful alt text
    raw = re.sub(r'!\[Image \d+\]\([^)]+\)\n?', '', raw)
    raw = re.sub(r'!\[\]\([^)]+\)\n?', '', raw)
    # Footer boilerplate — stop at first footer marker
    for marker in [r'\n#+\s+Learn\b', r'\n#+\s+Resources\b', r'\nCopyright ©', r'\n©\s+\d{4}', r'\nCreate an AWS account']:
        m = re.search(marker, raw)
        if m: raw = raw[:m.start()]
    # Deduplicate carousel lines (same line twice within 30 lines)
    lines, seen, out = raw.split('\n'), {}, []
    for i, line in enumerate(lines):
        s = line.strip()
        if len(s) > 10 and s in seen and i - seen[s] < 30:
            continue
        if len(s) > 10: seen[s] = i
        out.append(line)
    raw = '\n'.join(out)
    # Collapse blank lines
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    return raw.strip() if len(re.sub(r'\s+', '', raw)) >= 400 else ''

for f in pathlib.Path('/path/to/web-sources').glob('*.md'):
    cleaned = clean_web_content(f.read_text())
    if cleaned:
        f.write_text(cleaned)
    else:
        print(f"WARN: {f.name} below minimum after cleaning — check manually")
```

See [references/web-extraction-cleaning.md](references/web-extraction-cleaning.md) for the full function, detection rules, and expected size reductions.

**Also: include the RAW SOURCE SAVE PROTOCOL block in every Hermes brief prompt** so newly fetched files arrive clean. See the same reference for the exact instruction block to copy-paste.

### Step 3 — Copy the wrapper into your workflow's orchestration/ dir

Use `moa-call-safe.py` (F11 — the Python wrapper is shell-escape-safe and the default for everything). It handles `===INLINE:<path>===` expansion, argv-safe prompt passing, preset hinting, empty-output detection, and stderr capture. It writes `<out>`, `<out>.expanded` (the sent prompt), and `<out>.log`.

```bash
mkdir -p <your-workdir>/orchestration
cp ~/.claude/skills/moa-research/lib/moa-call-safe.py <your-workdir>/orchestration/
```

**Preflight before wiring into a workflow — run both, in order:**

**Preflight A — refs are live (F12, non-negotiable):** run the Quick-Start step-1 probe. Require all reference models return non-"failed". If any is down, STOP — the whole workflow would silently produce solo-Opus.

**Preflight B — end-to-end fire (F11 safety is built in):**
```bash
python3 <your-workdir>/orchestration/moa-call-safe.py deep-research /tmp/probe.prompt /tmp/probe.out
cat /tmp/probe.out
# Prompt: 'You are the MoA aggregator. In your FIRST line state how many reference-model
#          drafts you received (a number), then reply PONG.'
# The number MUST equal your preset's ref count (deep-research = 3). If it is lower,
# refs are dropping mid-call → F12 → debug before building the workflow.
```

A bare PONG probe confirms only the aggregator. The ref-count question is what proves you have real MoA diversity, not solo-Opus.

### Step 4 — Author the workflow using the chunked pattern

Use [templates/workflow-template.js](templates/workflow-template.js) as the starting shape. The critical structure:

```
export const meta = { name, description, phases: [...] }

phase('Scaffold')
// One agent creates the workdir tree.

phase('Chunked MoA')
// For each output-section family:
//   agent → Write chunk-prompt file → Bash moa-call-safe.py → validate → return
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
- Check MoA progress: `pgrep -fa moa-call-safe` (alive = still working) and `wc -c <workdir>/_logs/*.raw.md` (bytes = actual output)
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

## Cost optimisation — read this before every run

Token cost inflates fast on this pattern. The four biggest levers, ranked by impact:

**1. Corpus pruning per chunk (~40-60% input savings).** The inlined corpus goes to every MoA call. Most chunks only need a slice of it. Instead of `===INLINE:full-corpus.md===` on every chunk, prep per-chunk slices in the Scaffold phase and inline only what each chunk needs. Rule: a chunk emitting §§4-6 doesn't need §7's grounding, §1's mechanism definitions, or unrelated substrate quotes. Zero quality cost if slices are chosen carefully.

**2. Preset selection per chunk (~33% savings on structural work).** Follow F8 above. Use `default` for structural chunks (matrix fills, table cells, verbatim extraction, section skeletons). Reserve `deep-research` for the ≤2 genuinely novel-synthesis or adversarial chunks per phase. Concrete decision matrix:

| Chunk type | Preset | Rationale |
|---|---|---|
| Novel-theory synthesis, taxonomy invention, red-team, canonical-extraction, adversarial verify | `deep-research` | Cross-family diversity is the point |
| Comparative analysis, categorisation, mid-density skeletons | `default` | Two-family MoA sufficient |
| Matrix rows, table cells, schema fills, verbatim extraction | **Solo Opus effort:high** (skip MoA) | 5-10× cheaper; no diversity benefit |

**3. Verify + judgment default OFF (~1.5M tokens saved per phase when skipped).** See F9. Only enable when the artifact will be adopted without a human read. When you do enable it: run only identity-drift + layer-split lenses (drop topic-specific third lens), only against the new MoA artifact (never against the solo baseline for "fair comparison" — that's 2× redundant cost), and at `effort:medium` not `high` (verifiers pattern-match on specific failure signatures; deep reasoning wasted).

**4. Trim `PROMPT_HEADER` on later chunks (~10-15% input on chunks 2+).** After chunk 1 has established framing, later chunks in the same artifact can use a compressed header ("LIMF/STAMINA/SCIF-Mem invariants apply, see G.1") — the reference models have seen the full one for the same run.

**Not worth the complexity:** prompt caching (HAI doesn't expose it reliably), cheaper reference models (quality matters for MoA to work), fewer chunks per artifact (see F2 ceiling).

**Expected impact of applying levers 1-3:** roughly **60-75% token reduction** vs a full-scaffolding run with hardcoded `deep-research` on every call, with no quality loss on finished artifacts.

---

## Budget declaration + kill gate — estimate always, gate is OPTIONAL

State the expected cost upfront (this forces the right preset/verify decisions before launch). The **kill gate is OFF by default** — quality-first. Turn it ON only when the user asks for a cost ceiling, or for unattended/CI runs where a runaway can't be caught by a human.

```
Budget declaration (always state these two):
  Expected cost:   $X–Y     (e.g., $5–8)
  Expected time:   N min    (e.g., 30–45 min)
  Basis:           [chunks, preset, verify ON/OFF]

Kill gate:         OFF   (default — run to completion, quality-first)
                   ON at $Z / T min   (only if the user set a ceiling or it's unattended)
```

**The kill gate is a switch, not a mandate.** Default OFF: let MoA finish even if it runs long or over the estimate — a truncated or aborted synthesis wastes the whole spend. Only set it ON when explicitly directed (e.g. "hard kill at $6 / 25 min"). When ON, honor exactly the numbers given; when OFF, the estimate is informational only and you never auto-abort.

**Reference costs (empirical, HAI proxy):**

| Operation | Preset | Expected cost | Time |
|---|---|---|---|
| Single MoA chunk, ~50 KB inline | `default` | $0.50–1.50 | 3–8 min |
| Single MoA chunk, ~50 KB inline | `deep-research` | $1.00–3.00 | 5–12 min |
| 3-chunk protocol, no verify | `default` | $3–8 | 25–40 min |
| 3-chunk + 3-lens verify + judge | `deep-research` | $15–25 | 45–75 min |
| Solo Opus effort:high, 100 KB context | — | $0.10–0.30 | 1–3 min |

**If a run genuinely looks runaway** (whether or not a gate is set), diagnose in this order before killing:
1. Preset misconfigured? (`grep max_tokens ~/.hermes/config.yaml` — is `deep-research` where `default` was intended?)
2. Verify+judge accidentally ON? (check workflow script for `RUN_VERIFY=true`)
3. Retry loop? (`pgrep -c moa-call-safe` over 30s — is the same chunk looping?)
4. Shell-escape bug? (0-byte output on every call — see F11, switch to Python wrapper)
5. Corpus too large? (inlined prompt >800 KB — check scaffold agent output)

In Workflow scripts, add the declaration as a log line:
```javascript
log(`Budget: $5-8 expected, kill at $16. 3 chunks, default preset, no verify.`)
```
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

- [lib/moa-call-safe.py](lib/moa-call-safe.py) — **the wrapper (default).** `<preset> <prompt-file> <output-file>`. Shell-escape-safe (F11); handles inlining, argv-safe passing via `subprocess.run([argv])`, empty-output detection. Writes `<out>`, `<out>.expanded`, `<out>.log`.
- [lib/moa-call.sh](lib/moa-call.sh) — legacy bash wrapper, same CLI. Prose-only; breaks silently on code/backtick-dense prompts (F11). Prefer the Python one.
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

Every constraint in this skill (F1–F13) is empirically validated. Not theoretical. If you find one to be wrong on your setup, update this SKILL.md and the affected reference — don't just work around it.

---

## Project continuity — for multi-session research

MoA research protocols routinely span 5–15+ sessions. Without deliberate continuity hygiene, each session burns 300–600K input tokens just re-reading source documents to re-orient.

### Session startup file

For any project with ≥3 prior sessions, maintain a **`session-start.md`** file (<3 KB) at the project root. Claude reads this *instead of* re-reading 5–6 source documents at session start.

**Format (hard limit: 3 KB):**

```markdown
---
project: <name>
last_updated: YYYY-MM-DD
current_phase: <one phrase>
next_action: <one sentence — the single most important next thing>
---

## Status in one sentence
<Current phase + last thing completed + what's blocked.>

## 3 rules in force
1. <Most important binding constraint — verbatim if it has a canonical form>
2. <Second>
3. <Third>

## Active files (read if you need depth)
| File | Why you'd read it |
|---|---|
| `path/to/file.md` | <one-line reason> |

## Do NOT do this
- <Top 2–3 traps that have burned prior sessions>
```

**Update discipline:** update `current_phase` and `next_action` whenever the phase or next action changes. Do NOT let it grow — it is a current-state snapshot, not a history log. If it exceeds 3 KB, it has become a status doc and should be split.

**Handoff prompts are the first draft.** When writing a handoff prompt at session end, the same content goes into `session-start.md` for the next session.

### Plan scoping — housekeeping vs research

File reorganisation, artifact consolidation, and provenance cleanup are **housekeeping**. They do not deserve the same planning infrastructure as the research itself.

| Task type | Right artifact | Wrong artifact |
|---|---|---|
| Research phases, theorem work, benchmarks | Full plan with phases, gates, verification | One-page checklist |
| File reorganisation, `cp`/`mv`, YAML banners | One-page checklist | 700-line plan with 6 phases and 9 verification checks |
| Single MoA run | Budget declaration + chunk design | Full plan-mode session |

A consolidation/reorganisation job that gets a 700-line plan with phases and verification gates will consume 1–3 plan-authoring sessions (100–150K tokens each) for work that could have been a 20-line checklist. Rule of thumb: if the task is "move files and add headers", write a checklist in a comment, not a plan file.
