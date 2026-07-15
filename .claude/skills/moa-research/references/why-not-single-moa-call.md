# Why not a single MoA call?

Because the aggregator (Claude Opus, in the deep-research preset) self-imposes a ~10 KB output ceiling on dense structured markdown. This is not a `max_tokens` cap. It is model behavior. Chunking is the mitigation.

## Empirical evidence

Three probes, run on 2026-07-02/03, `deep-research` preset (Sonnet + Opus + gpt-5.5 refs → Opus aggregator), `max_tokens: 32000`.

### Probe 1: `PONG` sanity check

Prompt: 55 bytes.
```
Reply with the single word PONG and nothing else.
```
Result: `PONG`, 5 bytes, 41 seconds. MoA works.

### Probe 2: 800-line generic list

Prompt: 200 bytes, "emit exactly 800 numbered lines, ~60 chars each."
Result: **800 lines, 43,790 bytes, 9,718 tokens estimated. No truncation.** 4:20 wall-clock.

Signal: MoA CAN emit ~9.7k tokens cleanly when the content is simple and repetitive.

### Probe 3: 1500-line generic list

Prompt: same shape, ask for 1500 lines.
Result: **259 tokens.** The aggregator refused the task and returned a clarifying question ("what do you actually want?"). Not a truncation — a **semantic refusal**.

Signal: Opus has a heuristic that treats implausibly-long requests as suspect. There's a soft limit around 1000 lines / ~10k tokens where "just emit this" transitions to "wait, this feels wrong".

### Probe 4: Structured research artifact, single call

Prompt: 272 KB inlined (whole corpus + Grounding + master prompt), asked for 8-section base-theory map, aim 40-70 KB.
Result across three attempts:
- Attempt 1 (max_tokens=8192): 57 KB, truncated mid-§6, ~10k output tokens.
- Attempt 2 (max_tokens=32000): 58 KB, truncated in §8 Steelman mid-sentence, ~10k output tokens.
- Attempt 3 (max_tokens=32000, explicit structural check, self-audit comment): 58 KB, §8 truncated again, `## 3.` heading missing (demoted to `### 3.x`), ~10k output tokens.

**Consistent output ceiling of ~10k tokens.** Independent of `max_tokens`. Present across three iterations with progressively stronger prompts.

### Probe 5: Multi-section chunks (2026-07-03 P1 smoke)

Prompt: 272 KB inlined, chunked into **3 chunks of 3, 3, 2 sections each** (§§1-3, §§4-6, §§7-8), each aimed at 25-35 KB, 12-20 KB, 8-14 KB respectively.

Results:
- Chunk A (§§1-3, dense definitions + mechanisms + verbatim quotes) — **truncated mid-§2 at 26 KB, ~10k output tokens. §3 never started.** SELF-AUDIT marker missing (proof of truncation).
- Chunk B (§§4-6, definitions + numbered assumptions + numbered dependencies) — clean at 36 KB with SELF-AUDIT marker.
- Chunk C (§§7-8, verbatim question list + steelman paragraph) — clean at 16 KB with SELF-AUDIT marker.

Signal: **the ~10 KB ceiling fires per multi-section chunk when content is dense.** Chunk B's 36 KB worked because it's list-heavy (24 numbered assumptions + 7 numbered dependencies = repetitive shape). Chunk A's 26 KB failed because §§1-3 are the densest sections — full mechanism enumerations + verbatim quotes + no repetitive structure.

Fix that worked: split chunk A into **three one-section chunks** (A1=§1, A2=§2, A3=§3). Each stays 10-15 KB well under ceiling.

**The rule refined:** target ≤ 1 dense section per chunk. List-heavy or repetitive-structure chunks tolerate 2-3 sections. When in doubt, default to one section per chunk — the extra wall-clock is cheap insurance.

Opus has an internal "length feels excessive" heuristic that fires when it's generating dense, structured, mostly-non-repeating text. On repetitive content (probe 2, 800 numbered lines) the heuristic tolerates 9.7k tokens because the pattern is trivial. On dense multi-section research writing, it stops around the same token count because the content complexity per token is much higher.

`max_tokens` sets the API cap. Opus's own generation policy sets the effective ceiling. When they differ, the tighter one wins.

### Probe 6: Verbatim-quote-heavy §§7-8 chunk (2026-07-03 P1P3 real run)

Prompt: same corpus + grounding inline, asked for §7 (all 7 Part XXIV questions verbatim + 3 LIMF scope limits verbatim + 3-6 additional draft question markers) + §8 (400-600 word steelman paragraph) in a single chunk.

Result: **truncated at 10.3 KB with §8 never started.** The aggregator got through §7's three subsections of verbatim quotes but hit ceiling before §8's steelman.

Signal: **verbatim-quote-heavy content is DENSE even though it looks list-shaped.** Chunk B (24 numbered assumptions + 7 numbered dependencies) was list-shaped AND repetitive-structure → 36 KB clean. Chunk C's §7 was list-shaped BUT each item was a verbatim multi-line quote with anchor → still dense → truncated.

Fix that worked: split §7 and §8 into separate chunks C1 and C2. §7 alone lands cleanly at 10-15 KB; §8 alone at 4-8 KB.

**The rule refined again:** density is measured by "content complexity per token", not by list-vs-prose surface shape. Long verbatim quotes count as dense. Numbered lists of paragraph-length statements count as dense. Only truly repetitive content (e.g., numbered lines of similar shape and length) can safely occupy 30+ KB in a single chunk.

**Working heuristic:** unless you know the chunk is repetitive-shape, **target ≤ 1 top-level section per chunk**. Two-section chunks are only safe when both sections have simple structure and no verbatim quotes.

## Corollary: split by output family, not by prompt length

The fix is not to trim the input. The 272 KB input is fine — reference models handle it. The fix is to split the **output** across multiple aggregator calls, each producing 8-20 KB.

For an 8-section artifact of ~50 KB:
- 3 chunks × ~15 KB each = 45 KB across 3 sequential MoA calls
- Each chunk's aggregator invocation stays well under the 10 KB dense-structure ceiling
- Each chunk emits a SELF-AUDIT comment as evidence of completion
- Stitcher concatenates + validates + writes final artifact

Cost: 3× the wall-clock of a single call (Hermes serializes `/moa` invocations). Reliability: from ~0% success (0 of 3 attempts) to consistently getting all sections.

## What doesn't work

- **Bump `max_tokens` higher** — doesn't help past 32000; ceiling is model-internal.
- **Beg the model to emit longer output** — Opus interprets "aim for 50-70 KB" as a soft hint and still stops at ~10 KB when the content gets dense.
- **Front-load structural rules** — recency bias means top-of-prompt rules get forgotten by section 6.
- **Extract more compact drafts** — helps a little (each section is smaller) but structural collapse still hits.
- **Different aggregator model** — gpt-5.5 has similar limits, sometimes worse.

## What does work

- **Chunked emission** — 3-4 sequential MoA calls, each producing 2-3 sections. Ceiling doesn't matter because each chunk fits under it.
- **SELF-AUDIT HTML comment** — mandatory tail marker that the aggregator has to compose. Missing SELF-AUDIT is truncation evidence for the stitcher.
- **Per-section structural checks inline** — put "verbatim quote required with anchor" inside the section placeholder, not at the top of the prompt.
- **Adversarial multi-lens verify** — three focused verifiers catch what a single overall check misses. Combined with chunking they yield a reliable pipeline.

## The lesson

MoA's cost model is "N reference models + 1 aggregator per call". If you try to make one call produce a large structured artifact, you eat the aggregator's length ceiling and pay full price for a truncated result. If you break the artifact into 3 chunks, you pay 3× the wall-clock but you get a complete artifact and can retry any single chunk cheaply on failure.

The right shape is chunked-and-serialized.
