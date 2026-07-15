# Chunk-prompt shape

Every chunk-prompt fed to `hermes -z /moa` follows this exact structure. Deviations bite.

```
<shared PROMPT_HEADER — hard rules, forbidden terms, citation conventions>

===INLINE:/absolute/path/to/source-1.md===

===INLINE:/absolute/path/to/source-2.md===

===INLINE:/absolute/path/to/anchor-doc.md===

=== END INLINED SOURCES ===

YOUR CHUNK: §§N-M (name them explicitly — never "all sections")

## N. Section-N-Title

<Structural requirements for this section:
 - Verbatim quotes of X with anchor
 - Numbered list ≥ K items
 - Layer attribution on every mechanism claim
 - No summarization — extract mechanisms/assumptions/threat-models>

## M. Section-M-Title

<Same shape>

At the very end, on a line by itself, emit:
<!-- CHUNK-X SELF-AUDIT: <count>/<total> sections emitted; <specific invariants met>; no truncation -->

Output ONLY the sections + self-audit comment. No preamble, no meta-commentary.
Aim for 12-20 KB. Never exceed 25 KB.
```

## Rules that matter more than they look

**Every chunk emits a fresh copy of the PROMPT_HEADER.** Don't try to save tokens by omitting it — reference models see one chunk at a time and have no memory of previous chunks. The header is what enforces hard rules per call.

**Every source file is inlined via `===INLINE:` on its own line.** Not `===INLINE: /path===` (spaces break the regex). Not multiple directives on one line. Not relative paths.

**The chunk's section list is enumerated explicitly.** "YOUR CHUNK: §§4-6" beats "YOUR CHUNK: middle three sections" every time. LLMs count better when the count is spelled out.

**Structural requirements go inside each section's placeholder**, not at the top of the chunk. Aggregators forget top-of-prompt structural rules by the time they're generating §6. Recency bias favors the rules right next to where they apply.

**The SELF-AUDIT HTML comment is mandatory.** The stitcher checks for it as evidence the aggregator finished cleanly. A missing SELF-AUDIT is treated as truncation. Make the audit content substantive — "3/3 sections emitted, ≥12 assumptions in §5, ≥5 dependencies in §6, all seven Q-XXIV questions verbatim" — so the aggregator has to actually check its work to emit it.

**Aim for 12-20 KB per chunk, hard-cap at 25 KB.** Above 25 KB you hit Opus's self-imposed length limit and truncate. Below 8 KB you're wasting the fixed setup cost of a MoA call — combine two small sections into one chunk instead.

## Anti-patterns

- **"Produce all 8 sections"** — will truncate at ~10 KB, sections 3+ will be broken.
- **"Read the files at /path/to/..."** — ref models can't read files, they'll hallucinate or hang.
- **`===INLINE: /path ===`** with spaces — regex won't match, file won't inline.
- **Relative paths in INLINE** — wrapper enforces absolute paths; will exit 2.
- **No SELF-AUDIT phrase** — stitcher has no truncation detector; downstream corruption goes unnoticed.
- **Duplicated content between chunks** — if §3 references §1 material, add a one-paragraph recap inside §3, don't ask the aggregator to reference "as noted in chunk A" (the ref models never saw chunk A).
