# Verifier prompt shape

One lens, one verifier. Never combine lenses.

```
You are an ADVERSARIAL verifier for the artifact at <PATH>. Your job is to CATCH drift. Default to FAIL when ambiguous.

YOUR LENS: **<lens name>** — <one-sentence focus>
Do NOT run checks outside this lens. Other lenses cover them.

BEFORE JUDGING, read in full:
1. <path to authoritative anchor for THIS lens ONLY>
2. <path to artifact under test>

Run these checks. For each: verdict (PASS/WARN/FAIL) + quoted evidence with line numbers from the artifact.

- **C1. <question>** FAIL if: <condition> | WARN if: <condition>
- **C2. <question>** FAIL if: <condition>
- ... (5-10 checks total; more than 10 dilutes the lens)

Write your report to <report path> as markdown:

  # Verify <ID> — <lens name>
  ## Verdict: <GO | REVIEW | NO-GO>
  ## Summary
  <one paragraph>
  ## <each check heading>
  <verdict + quoted evidence with line numbers>

Lens verdict rule:
  - GO     = 0 FAIL, ≤1 WARN
  - REVIEW = 0 FAIL, ≥2 WARN
  - NO-GO  = ≥1 FAIL

Then respond with ONE line:
  "LENS <ID> VERDICT: <GO|REVIEW|NO-GO> — <F> fails, <W> warns"
```

## Lens design

Distinct lenses catch what redundancy can't. Pick lenses so that a single failure surfaces on **exactly one** lens — not none, not all. Overlap is a smell.

**Good lens split for research protocols:**

| Lens | Focus | Typical checks |
|---|---|---|
| **identity** | key term definitions, no renames, no parallel mechanisms | term X quoted verbatim; no X-2 / extended-X variants; correct family (release-property vs labels vs access control) |
| **structure** | layer discipline, section ordering, cross-layer attribution | N sections in order; no mechanism attributed to wrong layer; forbidden merges |
| **coverage** | gate criteria, enumerations, verbatim quotes with anchors | ≥K assumptions, ≥M dependencies, all N open questions verbatim, ≥P citations per section |

**Bad lens split (redundant):**

| Lens | Focus |
|---|---|
| overall correctness | everything |
| adversarial | everything, but with skepticism |
| detailed | everything, but slowly |

Same failures caught 3 times. No new information.

## Rules

**Every check has a machine-actionable FAIL condition.** Not "consider whether the artifact adequately addresses X". A verifier reading a fuzzy check will default to PASS. Adversarial framing + FAIL-on-ambiguity + machine-actionable conditions = failure detection.

**Line-number evidence is mandatory.** A verdict without a line reference is untrustworthy. If the check is "does the artifact quote definition D verbatim?", the verifier must quote the specific line range.

**Each verifier reads only its own anchor doc.** If your lens is "term X definition integrity", the verifier reads the anchor file that defines X and the artifact. Not the entire master prompt. Reading extra material adds noise; sticking to one anchor per lens forces the verifier to check what matters.

**5-10 checks per lens.** More than 10 and the verifier starts skimming. Fewer than 5 and the lens isn't earning its slot.

**Verifiers are cheap; the judge is where diverse signals converge.** Don't try to make one verifier smart — make three verifiers each dumb but focused.

## When one lens returns NO-GO and others return GO

Read the failing lens's report. Two cases:

- **Verifier miscalibrated** (e.g., picky regex): loosen the check, re-run only the verifier via `resumeFromRunId`.
- **Real defect detected**: read the judge's Suggested Prompt Patch, apply to the failing chunk, re-run from that chunk.

Never override a lens's NO-GO verdict without a documented reason. That's how drift gets in.
