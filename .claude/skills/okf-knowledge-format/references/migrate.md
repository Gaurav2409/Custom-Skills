# Migrate Existing KBs to OKF Conformance

Loaded when the user wants to migrate / make conformant / OKF-ify an existing knowledge base.

## Status as of 2026-06-27

All 10 LLM KBs under `~/Documents/LLM knowledge base/` are OKF v0.1 conformant:

| KB | Articles | Status |
|----|---------|--------|
| agentic-rag-and-memory-kb | 80 | ✅ |
| sap-ai-practices-kb | 200 | ✅ |
| sap-ai-northstar-arch-kb | 262 | ✅ |
| sap-btp-solution-architect-kb | 63 | ✅ |
| sap-enterprise-architect-kb | 18 | ✅ |
| knowledge-graph-design-kb | 45 | ✅ |
| avalara-avatax-kb | 33 | ✅ |
| cbc-onboarding-kb | 28 | ✅ |
| principal-se-prep | 0 (empty) | ✅ |
| bluespan-kb | 19 | ✅ |

**Migration was done with:**
```bash
python3 "/Users/I321170/Documents/LLM knowledge base/agentic-rag-and-memory-kb/scripts/okf_migrate.py" --all
```

20 articles needed `type:` added; all inferred correctly from directory (concepts/entities/topics/analyses).

## When to Run This Migration

Run when:
- Adding a brand-new KB and you want to ensure conformance from day one
- After bulk-importing articles from another tool that don't have `type:` in frontmatter
- After a periodic audit catches drift

## Migration Script

Located at: `/Users/I321170/Documents/LLM knowledge base/agentic-rag-and-memory-kb/scripts/okf_migrate.py`

### Usage

```bash
# Single KB (recommended pattern)
python3 ~/Documents/LLM\ knowledge\ base/agentic-rag-and-memory-kb/scripts/okf_migrate.py \
    /path/to/kb --dry-run

# All KBs under ~/Documents/LLM knowledge base/
python3 ~/Documents/LLM\ knowledge\ base/agentic-rag-and-memory-kb/scripts/okf_migrate.py \
    --all --dry-run

# Apply for real (drop --dry-run)
python3 ~/Documents/LLM\ knowledge\ base/agentic-rag-and-memory-kb/scripts/okf_migrate.py --all
```

### What it does

1. Walks `<kb>/wiki/` recursively
2. Skips reserved files: `_index.md`, `_summaries.md`, `log.md`, `_competency_questions.md`, `entity_registry.md`, `_cluster_summaries.md`, `_index-concepts.md`, `_index-entities.md`, `_index-topics.md`
3. For each non-reserved `.md` file:
   - If frontmatter exists and has `type:` — leaves it alone (`ok`)
   - If frontmatter exists but no `type:` — inserts `type: <inferred>` as the first frontmatter field
   - If no frontmatter at all — creates one with `type: <inferred>` and `title: <stem>`
4. Reports `manual` for any file the directory can't infer (rare)

### Type Inference

| Directory | Inferred `type:` |
|-----------|-----------------|
| `wiki/concepts/` | `concept` |
| `wiki/entities/` | `entity` |
| `wiki/topics/` | `topic` |
| `wiki/analyses/` | `analysis` |

If the file isn't under any of these subdirectories, the script reports `manual` and you must edit the file directly.

## What `raw/` Should Look Like

**`raw/` is exempt from OKF conformance.** Raw source documents are immutable inputs, not curated knowledge concepts. Don't try to add `type:` to articles in `raw/articles/`, papers in `raw/papers/`, or images in `raw/images/`.

The migration script only touches `<kb>/wiki/`.

## Verification Checklist (post-migration)

```bash
# 1. Confirm every non-reserved article has type:
KB=/path/to/kb
find $KB/wiki -name "*.md" \
  ! -name "_*" ! -name "log.md" ! -name "entity_registry.md" \
  | while read f; do
      head -10 "$f" | grep -q "^type:" || echo "MISSING TYPE: $f"
    done

# 2. Confirm wiki/_index.md still uses [[wikilinks]] not markdown links
grep -c "^- \[\[" $KB/wiki/_index.md   # should be > 0
grep -c "\](" $KB/wiki/_index.md       # markdown link count — should be 0 in body

# 3. Smoke-test the read protocol
python3 /Users/I321170/.claude/skills/okf-knowledge-format/okf_read.py $KB

# 4. Sanity-check sample of migrated files
for f in $(find $KB/wiki -name "*.md" -newer /tmp/before-migration -mmin -60); do
    echo "=== $f ==="
    head -15 "$f"
done
```

## Rollback (if something goes wrong)

The migration only inserts a single line per file. To roll back:

```bash
# If KB is git-versioned (recommended):
cd $KB && git checkout -- wiki/

# Otherwise, manually remove the inserted 'type:' line per file:
sed -i.bak '/^type: \(concept\|entity\|topic\|analysis\)$/d' $KB/wiki/**/*.md
```

## Common Gotchas

- **Plural `type:` values.** Some articles ended up with `type: topics` (plural) after migration if they had inherited from a parent. The script's helper run on 2026-06-17 normalized 12 articles in `sap-ai-practices-kb` to singular form. If you see `type: concepts/topics/entities/analyses` (plural) after migration, normalize to singular for consistency.
- **`raw/` modification.** Don't run this script with `raw/` as input. It will fail conformance checks because raw articles legitimately shouldn't have `type:`.
- **Existing `type:` with non-OKF values.** If frontmatter already had `type:` with a different meaning (e.g., `type: blog-post` from an Obsidian Web Clipper), the script preserves it — that's still OKF-conformant since any string is valid.

## After Migration: Update CLAUDE.md

Add to each KB's `CLAUDE.md`:

```markdown
## OKF Conformance
This KB is OKF v0.1 conformant.
Type taxonomy: concept | entity | topic | analysis
Migration script: scripts/okf_migrate.py
Conformed: <date>
```
