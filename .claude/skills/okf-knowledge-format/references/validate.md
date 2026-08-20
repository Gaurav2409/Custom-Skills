# Validate an OKF Bundle

Loaded when the user asks to validate, check conformance, or audit a bundle.

## Conformance Rules (v0.1)

A bundle is **conformant** if ALL of:
1. Every non-reserved `.md` file has a parseable YAML frontmatter block
2. Every frontmatter block contains a non-empty `type:` field
3. Reserved filenames follow their defined structure when present

**Reserved filenames** (exempt): `index.md`, `log.md`

## Hard Conformance Check (stdlib only)

```python
#!/usr/bin/env python3
"""OKF v0.1 conformance validator. No dependencies."""
import os, re, sys

RESERVED = {"index.md", "log.md"}

def validate(bundle_root):
    errors = []
    for root, dirs, files in os.walk(bundle_root):
        for fname in files:
            if not fname.endswith(".md") or fname in RESERVED:
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, errors='ignore') as f:
                content = f.read()
            if not content.startswith("---"):
                errors.append(f"MISSING_FRONTMATTER: {fpath}")
                continue
            fm_end = content.find("---", 3)
            if fm_end < 0:
                errors.append(f"UNCLOSED_FRONTMATTER: {fpath}")
                continue
            fm = content[3:fm_end]
            if not re.search(r"^\s*type\s*:\s*\S+", fm, re.MULTILINE):
                errors.append(f"MISSING_TYPE: {fpath}")
    return errors

if __name__ == "__main__":
    bundle = sys.argv[1] if len(sys.argv) > 1 else "."
    errs = validate(bundle)
    if errs:
        print(f"INVALID: {len(errs)} conformance errors")
        for e in errs:
            print(f"  {e}")
        sys.exit(1)
    print("VALID: OKF v0.1 conformant")
```

## Soft Guidance Checks (warnings, not failures)

These are quality indicators, not conformance failures:

```python
import os, re, yaml  # PyYAML for proper parsing

RESERVED = {"index.md", "log.md"}

def soft_audit(bundle_root):
    warnings = []
    for root, _, files in os.walk(bundle_root):
        for fname in files:
            if not fname.endswith(".md") or fname in RESERVED:
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, bundle_root)
            with open(fpath, errors='ignore') as f:
                content = f.read()
            fm_end = content.find("---", 3)
            try:
                fm = yaml.safe_load(content[3:fm_end]) or {}
            except yaml.YAMLError:
                fm = {}
            if not fm.get("title"):
                warnings.append(f"MISSING_TITLE: {rel}")
            if not fm.get("description"):
                warnings.append(f"MISSING_DESCRIPTION: {rel}")
            body = content[fm_end+3:]
            if len(re.findall(r'\[.+?\]\(.*?\.md\)', body)) < 1:
                warnings.append(f"NO_CROSS_LINKS: {rel}")
            if len(body.split()) < 100:
                warnings.append(f"STUB_ARTICLE: {rel}")
    return warnings
```

## Quick Bash One-liner

```bash
# Find all non-conformant files in a bundle
find <bundle> -name "*.md" ! -name "index.md" ! -name "log.md" | while read f; do
    head -20 "$f" | grep -q "^type:" || echo "MISSING_TYPE: $f"
done
```

## Validating LLM KBs (your local KBs)

For your own KBs, additional reserved files apply:

```python
RESERVED_LLM_KB = {
    "index.md", "log.md",
    "_index.md", "_summaries.md", "_competency_questions.md",
    "entity_registry.md", "_cluster_summaries.md",
    "_index-concepts.md", "_index-entities.md", "_index-topics.md",
}
```

The migration script at `references/migrate.md` (or `<kb>/scripts/okf_migrate.py`) uses this expanded list.
