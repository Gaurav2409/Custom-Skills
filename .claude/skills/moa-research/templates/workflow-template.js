// workflow-template.js — copy-paste starting point for an MoA research workflow.
//
// This template implements the seven-step recipe from ../SKILL.md:
//   1. Enumerate corpus + artifact (constants at top)
//   2. Bump max_tokens beforehand (out-of-band, one-time)
//   3. Copy moa-call.sh into orchestration/ (out-of-band)
//   4. Chunked MoA with sequential emission (this file)
//   5. Adversarial multi-lens verify (this file)
//   6. Synthesis judge (this file)
//   7. Launch via Workflow tool with { args: { workdir: ... } }
//
// Replace the CONFIGURE ME blocks with your specific paths, sections, and lenses.
// Everything else should work as-is.

export const meta = {
  name: 'CHANGE-ME-workflow-name',
  description: 'CHANGE ME — one-line description shown in the permission dialog',
  phases: [
    { title: 'Scaffold' },
    { title: 'Chunked MoA' },
    { title: 'Stitch' },
    // Verify + Judge phases only appear in progress display when RUN_VERIFY /
    // RUN_JUDGE are flipped to true below. Leave these entries here as
    // documentation of the available shape.
    { title: 'Verify' },
    { title: 'Judge' },
  ],
}

// ===========================================================================
// CONFIGURE ME — paths
// ===========================================================================

// Where the corpus lives. Adjust for your project.
const KB          = '/absolute/path/to/your/knowledge-base'
const PROMPT_DIR  = `${KB}/prompts/your-protocol`
const CORPUS_DIR  = `${KB}/corpus`

// Where moa-call.sh was copied to.
const MOA_CALL    = `${PROMPT_DIR}/orchestration/moa-call.sh`

// Preset choice is PER CHUNK (see SKILL.md F8 + Cost optimisation section).
// The template default is `default` — the cheaper Opus+gpt-5.5 two-family MoA.
// Override per chunk by setting `preset: 'deep-research'` on the chunks that
// genuinely benefit from cross-family diversity (novel synthesis, red-teams,
// canonical extraction, adversarial verify). For structural chunks (matrix
// fills, table cells, verbatim extraction), consider skipping MoA entirely and
// using solo Opus at effort:high — 5-10x cheaper than any MoA.
const DEFAULT_PRESET = 'default'

// Verify + judgment phases default OFF (see SKILL.md F9). They cost ~1.5M
// input tokens for a 3-lens/2-artifact/solo-and-MoA pass — usually more
// expensive than a human read of the final artifact. Flip to true only when:
//   (a) the artifact will be adopted without a human read, or
//   (b) you have 20+ artifacts and can't read them all, or
//   (c) you need automated CI-style gating.
// When enabled: keep only identity-drift + layer-split lenses (drop the
// topic-specific third lens), run at effort:medium not high, and verify only
// the new artifact — never the solo baseline "for fair comparison".
const RUN_VERIFY = false
const RUN_JUDGE  = false

// Workdir passed in via args.
const workdir = (args && args.workdir) || null
if (!workdir) throw new Error('args.workdir is required (absolute path)')

const OUT_DIR     = workdir
const PROMPTS_DIR = `${workdir}/_prompts`
const LOGS_DIR    = `${workdir}/_logs`
const FINAL_ART   = `${workdir}/artifact.md`

// ===========================================================================
// CONFIGURE ME — shared prompt header
// ===========================================================================
// This block is prepended to every chunk's MoA prompt. Put hard rules, layer
// discipline, forbidden terms, and citation conventions here. Keep it under
// 2 KB so it doesn't crowd the chunk-specific instructions.

const PROMPT_HEADER = `
You are the MoA aggregator for the CHANGE-ME research protocol. Produce ONE
CHUNK only. Do not emit sections outside your chunk's scope.

Reference models cannot read files. Everything you need is INLINED below.
Do NOT try to read any file.

HARD RULES:
- CHANGE ME (e.g. "Never rename term X; extensions carry its name plus a qualifier.")
- CHANGE ME (e.g. "Cite by filename stem + line anchor: [name §7.1] or (name:1257).")
- Never fabricate a source. Mark [speculative] when unsupported.
- Do NOT summarize; EXTRACT mechanisms, definitions, assumptions, and evidence.
`

// ===========================================================================
// CONFIGURE ME — chunk plan
// ===========================================================================
// Each chunk emits 2-4 sections and produces 8-20 KB of markdown. Never
// exceed 25 KB per chunk. Total artifact = sum of chunk sizes.
//
// For each chunk, define:
//   id             — short identifier (A, B, C, ...)
//   sections       — array of section headings this chunk emits
//   preset         — OPTIONAL: 'default' (cheap, 2-family) or 'deep-research'
//                    (expensive, 3-family). Omit to use DEFAULT_PRESET above.
//                    Use 'deep-research' only on chunks that benefit from
//                    cross-family diversity (novel synthesis, red-teams,
//                    canonical extraction, adversarial framing). Use 'default'
//                    or omit for structural / mid-density chunks. Consider
//                    NOT using MoA at all (solo Opus effort:high) for
//                    structural table-fill / verbatim-extraction chunks.
//   inlines        — array of absolute paths inlined into the prompt via
//                    ===INLINE:<path>=== directives (order preserved).
//                    Prefer PER-CHUNK CORPUS SLICES over the full corpus —
//                    inlining only what the chunk needs saves 40-60% of
//                    input tokens. Prep slices in the Scaffold phase.
//   prompt         — chunk-specific instructions (what to emit, structural
//                    contracts, target size). Do NOT include PROMPT_HEADER
//                    or ===INLINE=== directives here — those are assembled
//                    by the chunk builder below.
//   auditPhrase    — literal string the aggregator must emit as
//                    `<!-- ${auditPhrase}: ... -->` at the end. Stitcher
//                    checks this as truncation evidence.

const CHUNKS = [
  {
    id: 'A',
    sections: ['## 1. CHANGE-ME-Section-1', '## 2. CHANGE-ME-Section-2'],
    inlines: [
      `${PROMPT_DIR}/master-prompt.md`,
      `${PROMPT_DIR}/grounding.md`,
      `${CORPUS_DIR}/source-1.md`,
    ],
    prompt: `YOUR CHUNK: §§1-2.

## 1. CHANGE-ME-Section-1

<CHANGE ME: describe what content goes here. Include structural requirements:
verbatim quotes, minimum enumerations, layer attribution, etc.>

## 2. CHANGE-ME-Section-2

<CHANGE ME: same>

At the very end, on a line by itself, emit:
<!-- CHUNK-A SELF-AUDIT: 2/2 sections emitted; no truncation; <other invariants> -->

Aim for 12-20 KB.`,
    auditPhrase: 'CHUNK-A SELF-AUDIT',
  },
  {
    id: 'B',
    sections: ['## 3. CHANGE-ME-Section-3', '## 4. CHANGE-ME-Section-4'],
    inlines: [
      `${PROMPT_DIR}/master-prompt.md`,
      `${PROMPT_DIR}/grounding.md`,
      `${CORPUS_DIR}/source-2.md`,
    ],
    prompt: `YOUR CHUNK: §§3-4.

## 3. CHANGE-ME-Section-3

<CHANGE ME>

## 4. CHANGE-ME-Section-4

<CHANGE ME>

At the very end, on a line by itself, emit:
<!-- CHUNK-B SELF-AUDIT: 2/2 sections emitted; no truncation -->

Aim for 12-20 KB.`,
    auditPhrase: 'CHUNK-B SELF-AUDIT',
  },
  // Add more chunks as needed. Aim for 3-4 chunks total.
]

// ===========================================================================
// CONFIGURE ME — verifier lenses
// ===========================================================================
// Each verifier gets exactly one lens with 5-10 bounded checks. Distinct
// lenses beat redundant verifiers. Each defaults to FAIL on ambiguity.

const LENSES = [
  {
    id: 'V1',
    label: 'identity',
    focus: 'CHANGE ME: e.g. "term X definition and non-rename"',
    checks: [
      // Each check: { id, question, failCondition, warnCondition? }
      {
        id: 'L1',
        question: 'Is term X ever renamed to X-2, extended-X, or a similar variant?',
        failCondition: 'any rename detected',
      },
      // Add 4-9 more.
    ],
    anchorFile: `${PROMPT_DIR}/grounding.md`,   // the authoritative source for THIS lens
  },
  {
    id: 'V2',
    label: 'structure',
    focus: 'CHANGE ME: e.g. "eight top-level sections in exact order"',
    checks: [
      // ...
    ],
    anchorFile: `${PROMPT_DIR}/master-prompt.md`,
  },
  {
    id: 'V3',
    label: 'coverage',
    focus: 'CHANGE ME: e.g. "gate criteria and mandatory enumerations"',
    checks: [
      // ...
    ],
    anchorFile: `${PROMPT_DIR}/gate-criteria.md`,
  },
]

// ===========================================================================
// End of CONFIGURE ME. The rest of the file is boilerplate that assembles
// prompts and orchestrates agents. Read it once; you usually won't edit it.
// ===========================================================================

// ---------------------------------------------------------------------------
// Chunk-prompt assembly
// ---------------------------------------------------------------------------

function buildChunkPrompt(chunk) {
  const inlineDirectives = chunk.inlines
    .map(p => `===INLINE:${p}===`)
    .join('\n\n')
  return `${PROMPT_HEADER.trim()}

${inlineDirectives}

=== END INLINED SOURCES ===

${chunk.prompt.trim()}
`
}

// ---------------------------------------------------------------------------
// Phase 1: Scaffold
// ---------------------------------------------------------------------------

phase('Scaffold')

await agent(
  `Create workdir tree using Write. Create these files (parent dirs implicit):
  - ${workdir}/README.md    → "MoA research run. Do not edit files under phaseN/ manually."
  - ${PROMPTS_DIR}/.gitkeep → ""
  - ${LOGS_DIR}/.gitkeep    → ""

Then respond with exactly: "SCAFFOLD OK".`,
  { label: 'scaffold', phase: 'Scaffold' },
)

// ---------------------------------------------------------------------------
// Phase 2: Chunked MoA emission (SEQUENTIAL — Hermes serializes /moa)
// ---------------------------------------------------------------------------

phase('Chunked MoA')

for (const chunk of CHUNKS) {
  const promptFile = `${PROMPTS_DIR}/chunk-${chunk.id}.prompt.md`
  const rawFile    = `${LOGS_DIR}/chunk-${chunk.id}-raw.md`
  const fullPrompt = buildChunkPrompt(chunk)

  await agent(
    `Three steps in order:

STEP 1. Write the MoA prompt to ${promptFile}:
<<<PROMPT
${fullPrompt}
PROMPT

STEP 2. Run Bash. moa-call.sh will expand ===INLINE:<path>=== directives:
  ${MOA_CALL.replace(/ /g, '\\ ')} ${chunk.preset || DEFAULT_PRESET} ${promptFile} ${rawFile}

  NOTE: MoA calls of ~200 KB inlined input take 3-10 min. If Bash times out
  at 10 min, poll \`pgrep -fa moa-call.sh\` and wait a further 10 min before
  declaring failure.

STEP 3. Validate ${rawFile}:
  - Non-empty (≥ 5 KB)
  - Contains each of these headings: ${JSON.stringify(chunk.sections)}
  - Contains the audit phrase "${chunk.auditPhrase}"

If valid: respond "CHUNK ${chunk.id} OK — <bytes> bytes".
If invalid: respond "CHUNK ${chunk.id} FAILED — <reason>".`,
    { label: `chunk-${chunk.id} MoA`, phase: 'Chunked MoA' },
  )
}

// ---------------------------------------------------------------------------
// Phase 3: Stitch chunks into final artifact
// ---------------------------------------------------------------------------

phase('Stitch')

const chunkFiles = CHUNKS.map(c => ({
  id: c.id,
  file: `${LOGS_DIR}/chunk-${c.id}-raw.md`,
  audit: c.auditPhrase,
  headings: c.sections,
})).map(c => `  - ${c.file}   (chunk ${c.id}, expects headings ${JSON.stringify(c.headings)} and audit "${c.audit}")`).join('\n')

await agent(
  `Combine chunk raw outputs into the final artifact at ${FINAL_ART}.

STEP 1. Read all chunks:
${chunkFiles}

STEP 2. For each chunk: verify expected headings + audit phrase are present.
If any chunk is malformed, Write "CHECKPOINT_FAILED: chunk X malformed — <reason>" to ${FINAL_ART} and stop.

STEP 3. Concatenate chunks in order (A, B, C, ...), stripping any preamble
before the first "## N." heading in each. Prepend a top-of-artifact H1
title. Write the combined content to ${FINAL_ART}. Append a final SELF-AUDIT
HTML comment listing all chunks stitched.

STEP 4. Final validation on the stitched artifact:
  - Contains every heading from every chunk
  - Total size ≥ 20 KB (adjust if your target is different)
  - Contains at least one SELF-AUDIT comment per chunk

Respond: "WROTE ${FINAL_ART} — <bytes> bytes" or "CHECKPOINT_FAILED — <reason>".`,
  { label: 'stitcher', phase: 'Stitch' },
)

// ---------------------------------------------------------------------------
// Phase 4: Adversarial multi-lens verify (parallel) — OPTIONAL
// ---------------------------------------------------------------------------

let lensVerdicts = []
if (RUN_VERIFY) {
  phase('Verify')

  function buildVerifierPrompt(lens) {
    const checksList = lens.checks
      .map(c => `- **${c.id}. ${c.question}** FAIL if: ${c.failCondition}${c.warnCondition ? ` | WARN if: ${c.warnCondition}` : ''}`)
      .join('\n')

    return `You are an ADVERSARIAL verifier for the artifact at ${FINAL_ART}. Your job is to CATCH drift. Default to FAIL when ambiguous.

YOUR LENS: **${lens.label}** — ${lens.focus}
Do NOT run checks outside this lens. Other lenses cover them.

BEFORE JUDGING, read in full:
1. ${lens.anchorFile}   (authoritative anchor for this lens)
2. ${FINAL_ART}         (artifact under test)

Run these checks. For each: verdict (PASS/WARN/FAIL) + quoted evidence with line numbers from the artifact.

${checksList}

Write your report to ${OUT_DIR}/verify-${lens.id}-${lens.label}.md as markdown:

  # Verify ${lens.id} — ${lens.label}
  ## Verdict: <GO | REVIEW | NO-GO>
  ## Summary
  <one paragraph>
  ## Check details
  <each check with verdict + evidence>

Lens verdict rule:
  - GO   = 0 FAIL, ≤1 WARN
  - REVIEW = 0 FAIL, ≥2 WARN
  - NO-GO = ≥1 FAIL

Then respond with ONE line:
  "LENS ${lens.id} VERDICT: <GO|REVIEW|NO-GO> — <F> fails, <W> warns"`
  }

  lensVerdicts = await parallel(
    LENSES.map(lens => () =>
      agent(buildVerifierPrompt(lens), {
        label: `verify:${lens.label}`,
        phase: 'Verify',
        effort: 'medium',   // pattern-matching, not deep reasoning — see SKILL.md Cost optimisation
      })
    )
  )
}

// ---------------------------------------------------------------------------
// Phase 5: Synthesis judge — OPTIONAL (requires RUN_VERIFY)
// ---------------------------------------------------------------------------

let verdict = null
const validationReport = `${OUT_DIR}/validation.md`
if (RUN_JUDGE && RUN_VERIFY) {
  phase('Judge')

  const survived = lensVerdicts.filter(Boolean)

  const judgePrompt = `You are the SYNTHESIS JUDGE combining ${LENSES.length} adversarial lens reports on the artifact at ${FINAL_ART}.

Lens reports:
${LENSES.map(l => `  - ${OUT_DIR}/verify-${l.id}-${l.label}.md   (Lens ${l.id}, ${l.label})`).join('\n')}

Their one-line return verdicts were:
${survived.map((v, i) => `  Lens ${i + 1}: ${v}`).join('\n')}

Do NOT re-evaluate the artifact from scratch. Your job:

1. Read all lens reports.
2. Compute joint verdict:
   - NO-GO if ANY lens returned NO-GO
   - REVIEW if all lenses GO/REVIEW but ≥1 returned REVIEW
   - GO only if all lenses returned GO
3. Enumerate all FAILs and WARNs with lens attribution + evidence quoted from the lens report.
4. On NO-GO: produce "Suggested Prompt Patch" — exact text to add to the failing chunk's MoA prompt on retry.
5. On REVIEW: produce "Optional Tightenings".
6. On GO: produce "Notes for Downstream Users".

Write full synthesis to ${validationReport}. Structure:
  # Validation Synthesis
  ## Joint Verdict: <GO | REVIEW | NO-GO>
  ## Summary
  ## Lens Verdicts
  ## All FAILs (blocking)
  ## All WARNs (non-blocking)
  ## Suggested Prompt Patch / Optional Tightenings / Notes
  ## Individual Lens Reports (references)

Then respond with EXACTLY one line:
  "VERDICT: <GO|REVIEW|NO-GO> — <F> blocking fails, <W> warns — synthesis at ${validationReport}"`

  verdict = await agent(judgePrompt, {
    label: 'synthesis judge',
    phase: 'Judge',
    effort: 'high',
  })
}

return {
  workdir,
  artifact: FINAL_ART,
  ...(RUN_VERIFY && { lensReports: LENSES.map(l => `${OUT_DIR}/verify-${l.id}-${l.label}.md`), lensVerdicts: lensVerdicts.filter(Boolean) }),
  ...(RUN_JUDGE  && RUN_VERIFY && { validationReport, verdict }),
}
