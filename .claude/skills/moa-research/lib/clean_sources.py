#!/usr/bin/env python3
"""
clean_sources.py — strip structural noise from web-extracted raw source files.

Usage:
  python3 clean_sources.py <directory-of-md-files>
  python3 clean_sources.py <single-file.md>

Cleans in place. Prints a summary: kept / shrunk / rejected (below minimum).
See: ~/.claude/skills/moa-research/references/web-extraction-cleaning.md
"""

import sys
import re
import pathlib


def clean_web_content(raw: str, filename: str = "") -> str:
    """
    Remove structural noise. Returns cleaned text, or empty string if below
    minimum quality threshold (< 400 non-whitespace chars after cleaning).
    """
    text = raw

    # --- Frontmatter passthrough ---
    # Preserve YAML frontmatter block unchanged; clean only the body
    frontmatter = ""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            frontmatter = text[:end + 4]  # includes closing ---
            body = text[end + 4:]

    # --- 1. Cookie consent banners ---
    body = re.sub(
        r'(?is)## (Select your cookie preferences|Customize cookie preferences).*?'
        r'(## Your privacy choices|## Unable to save|## (?!Select|Customize))',
        r'\2', body
    )
    body = re.sub(
        r'(?is)(## Your privacy choices.*?)(## (?!Your privacy)|\Z)',
        r'\2', body
    )
    # Generic cookie consent block (Amazon, GDPR overlays)
    body = re.sub(
        r'(?is)(we use essential cookies and similar tools.*?)'
        r'(save preferences|dismiss|cancel\s+save preferences)',
        '', body
    )
    body = re.sub(
        r'(?is)(we and our advertising partners.*?)'
        r'(cancel save preferences|dismiss)',
        '', body
    )

    # --- 2. Image markdown refs with no useful alt text ---
    # Remove: ![Image 1](url), ![](url), [![Image 1: text](url)](link)
    body = re.sub(r'!\[Image \d+[^\]]*\]\([^)]+\)', '', body)
    body = re.sub(r'!\[\]\([^)]+\)', '', body)
    # Remove image-only lines (just an image ref with optional link wrapper)
    body = re.sub(r'^\[?!\[[^\]]*\]\([^)]+\)\]?(?:\([^)]*\))?\s*$', '', body, flags=re.MULTILINE)

    # --- 3. Footer boilerplate — stop at first footer marker ---
    footer_markers = [
        r'\n## Learn\b',
        r'\n## Resources\b',
        r'\n## About AWS\b',
        r'\n## Follow',
        r'\n## Legal\b',
        r'\nCopyright ©',
        r'\n©\s+\d{4}',
        r'\n\[Create an AWS account\]',
        r'\nCreate an AWS account',
        r'\n\*\s+\[What Is AWS',
        r'\n## Get Started with AWS',
    ]
    for marker in footer_markers:
        m = re.search(marker, body)
        if m:
            body = body[:m.start()]

    # --- 4. Navigation menu blocks (4+ consecutive link-list lines) ---
    lines = body.split('\n')
    out = []
    link_run_start = None
    link_run_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_link_item = bool(re.match(r'^[\*\-\+]\s+\[.+\]\(', stripped))
        if is_link_item:
            if link_run_start is None:
                link_run_start = i
            link_run_lines.append(line)
        else:
            if link_run_start is not None:
                if len(link_run_lines) >= 4:
                    pass  # drop nav block
                else:
                    out.extend(link_run_lines)  # short list, keep
                link_run_start = None
                link_run_lines = []
            out.append(line)

    if link_run_start is not None and len(link_run_lines) < 4:
        out.extend(link_run_lines)

    body = '\n'.join(out)

    # --- 5. CTA / boilerplate single lines ---
    cta_patterns = [
        r'^\[Get started now',
        r'^\[Learn more(?: in the| »|$)',
        r'^\[Learn more»',
        r'^\[Contact us\b',
        r'^\[Sign up\b',
        r'^\[Create an? account\b',
        r'^\[Start free\b',
        r'^\s*\[?\s*Skip to (main )?content\s*\]?',
        r'^Get started now\b',
        r'^Learn more »',
    ]
    body = '\n'.join(
        line for line in body.split('\n')
        if not any(re.match(pat, line.strip(), re.IGNORECASE) for pat in cta_patterns)
    )

    # --- 6. Deduplicate carousel / repeated lines ---
    lines = body.split('\n')
    seen_recently: dict[str, int] = {}
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        if len(s) > 15:
            if s in seen_recently and (i - seen_recently[s]) < 30:
                continue  # duplicate within 30-line window — skip
            seen_recently[s] = i
        out.append(line)
    body = '\n'.join(out)

    # --- 7. Collapse excessive blank lines ---
    body = re.sub(r'\n{3,}', '\n\n', body)

    # --- Reassemble ---
    if frontmatter:
        result = frontmatter + '\n' + body.strip()
    else:
        result = body.strip()

    # --- 8. Minimum content check (non-whitespace chars in body) ---
    body_content = len(re.sub(r'\s+', '', body))
    if body_content < 400:
        return ''

    return result


def process_path(target: pathlib.Path) -> None:
    if target.is_file():
        files = [target]
    else:
        files = sorted(target.glob('*.md'))

    total = len(files)
    kept = 0
    shrunk = 0
    rejected = 0

    for f in files:
        original = f.read_text(encoding='utf-8', errors='replace')
        original_size = len(original)

        cleaned = clean_web_content(original, filename=f.name)

        if not cleaned:
            print(f"  REJECTED  {f.name} (below 400 chars after cleaning)")
            rejected += 1
            continue

        cleaned_size = len(cleaned)
        reduction = (1 - cleaned_size / original_size) * 100 if original_size > 0 else 0

        if cleaned_size < original_size:
            f.write_text(cleaned, encoding='utf-8')
            print(f"  CLEANED   {f.name}: {original_size:,} → {cleaned_size:,} chars ({reduction:.0f}% reduction)")
            shrunk += 1
        else:
            kept += 1
            # Don't rewrite if no change

    print(f"\nDone: {total} files — {shrunk} cleaned, {kept} already clean, {rejected} rejected (below minimum)")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: clean_sources.py <directory-or-file.md>")
        sys.exit(1)

    target = pathlib.Path(sys.argv[1]).expanduser()
    if not target.exists():
        print(f"Error: path not found: {target}")
        sys.exit(1)

    process_path(target)
