# Judge prompt shape

The judge does not re-evaluate the artifact. It **reconciles the N lens reports** into a single verdict + actionable next step.

```
You are the SYNTHESIS JUDGE combining <N> adversarial lens reports on the artifact at <PATH>.

Lens reports:
  - <path to lens 1 report>   (Lens 1, <name>)
  - <path to lens 2 report>   (Lens 2, <name>)
  - <path to lens 3 report>   (Lens 3, <name>)

Their one-line return verdicts were:
  Lens 1: <verdict string>
  Lens 2: <verdict string>
  Lens 3: <verdict string>

Do NOT re-evaluate the artifact from scratch. Your job:

1. Read all lens reports.
2. Compute joint verdict:
   - NO-GO if ANY lens returned NO-GO
   - REVIEW if all lenses GO/REVIEW but ≥1 returned REVIEW
   - GO only if all lenses returned GO
3. Enumerate all FAILs and WARNs with lens attribution + evidence quoted from the lens report.
4. On NO-GO: produce "Suggested Prompt Patch" — the exact text to add to the failing chunk's MoA prompt on retry, keyed to each blocking FAIL.
5. On REVIEW: produce "Optional Tightenings" — non-blocking suggestions.
6. On GO: produce "Notes for Downstream Users" — anything the lenses noticed that downstream consumers should know when citing this artifact.

Write full synthesis to <validation report path>. Structure:

  # Validation Synthesis
  ## Joint Verdict: <GO | REVIEW | NO-GO>
  ## Summary
  <2-3 paragraphs of what the N lenses collectively found>
  ## Lens Verdicts
  - Lens 1 (<name>): <verdict + one-line summary>
  - Lens 2 (<name>): <same>
  - Lens 3 (<name>): <same>
  ## All FAILs (blocking)
  <list; each with lens attribution + check ID + quoted evidence>
  ## All WARNs (non-blocking)
  <list>
  ## Suggested Prompt Patch (NO-GO only) / Optional Tightenings (REVIEW only) / Notes for Downstream (GO only)
  <appropriate section>
  ## Individual Lens Reports (references)
  - [Lens 1](<path>)
  - [Lens 2](<path>)
  - [Lens 3](<path>)

Then respond with EXACTLY one line:
  "VERDICT: <GO|REVIEW|NO-GO> — <F> blocking fails, <W> warns — synthesis at <path>"
```

## Why the judge doesn't re-evaluate

Efficiency and honesty. If the judge re-reads the artifact and forms its own opinion, it becomes lens #4 — with the same blind spots as the others but presented with more authority. The verifiers already did the work; the judge's job is to **aggregate and act on** their findings, not to override them.

## The Suggested Prompt Patch is the load-bearing output

On NO-GO, this block is what makes the next iteration cheap. It should be:

- **Keyed to each blocking FAIL** — one patch per failure, not one generic wall of instructions.
- **Copy-pasteable** — the exact bytes to add to the failing chunk's MoA prompt, not a description of what to add.
- **Positional** — say where in the prompt to insert (e.g., "add this to the CRITICAL AGGREGATOR SYNTHESIS RULES block after rule 3").
- **Testable** — the patch must include a check that would have caught the failure on the previous run.

A NO-GO with no useful patch means the judge failed. A judge that produces a useful patch has done its job even if the artifact needs another round.

## GO verdicts are rare and valuable

Under adversarial verifiers with FAIL-on-ambiguity defaults, a clean GO across 3 lenses is a strong signal. Trust it. Move on to downstream work.

REVIEW verdicts are more common and usually mean "artifact is usable but tighten prompt on next iteration to reduce warns to zero."
