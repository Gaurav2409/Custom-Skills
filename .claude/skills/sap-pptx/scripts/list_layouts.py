#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "python-pptx>=0.6.21",
# ]
# ///
"""
List all available slide layouts in the SAP PowerPoint template.

Usage:
    uv run scripts/list_layouts.py [OPTIONS]

Options:
    --format FORMAT       Output format: json, text, table (default: table)
    --category CATEGORY   Filter by category: cover, agenda, divider, content, closing, copilot
    --template PATH       Custom template path
    --help                Show this help message

Exit Codes:
    0 - Success
    1 - Invalid arguments
    2 - Template not found

Examples:
    uv run scripts/list_layouts.py
    uv run scripts/list_layouts.py --format json
    uv run scripts/list_layouts.py --category cover
"""

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation


# Layout definitions with categories
LAYOUTS = [
    {"index": 0, "name": "Cover A", "category": "cover", "description": "Title slide with SAP branding"},
    {"index": 1, "name": "Cover B", "category": "cover", "description": "Alternative cover layout"},
    {"index": 2, "name": "Cover C", "category": "cover", "description": "Cover with image area"},
    {"index": 3, "name": "Cover D", "category": "cover", "description": "Cover variant D"},
    {"index": 4, "name": "Cover E", "category": "cover", "description": "Cover variant E"},
    {"index": 5, "name": "Cover F", "category": "cover", "description": "Cover variant F"},
    {"index": 6, "name": "Cover G", "category": "cover", "description": "Cover variant G"},
    {"index": 7, "name": "Cover H", "category": "cover", "description": "Cover variant H"},
    {"index": 8, "name": "Cover I", "category": "cover", "description": "Cover variant I"},
    {"index": 9, "name": "Cover J", "category": "cover", "description": "Cover variant J"},
    {"index": 10, "name": "Cover K", "category": "cover", "description": "Cover variant K"},
    {"index": 11, "name": "Cover L", "category": "cover", "description": "Cover variant L"},
    {"index": 12, "name": "Agenda A", "category": "agenda", "description": "Agenda slide with bullet points"},
    {"index": 13, "name": "Agenda B", "category": "agenda", "description": "Alternative agenda layout"},
    {"index": 14, "name": "Divider Page A", "category": "divider", "description": "Section divider"},
    {"index": 15, "name": "Divider Page B", "category": "divider", "description": "Section divider variant B"},
    {"index": 16, "name": "Divider Page C", "category": "divider", "description": "Section divider variant C"},
    {"index": 17, "name": "Divider Page D", "category": "divider", "description": "Section divider variant D"},
    {"index": 18, "name": "Title Only", "category": "content", "description": "Title with empty content area"},
    {"index": 19, "name": "Title and Text", "category": "content", "description": "Title with text content"},
    {"index": 20, "name": "Title and Text: 2 Columns", "category": "content", "description": "Two-column text layout"},
    {"index": 21, "name": "Title and Text: 3 Columns", "category": "content", "description": "Three-column text layout"},
    {"index": 22, "name": "2 Columns - Text and Images", "category": "content", "description": "Two columns with text and image areas"},
    {"index": 23, "name": "3 Columns - Text and Images", "category": "content", "description": "Three columns with text and image areas"},
    {"index": 24, "name": "4 Columns - Text and Images", "category": "content", "description": "Four columns with text and image areas"},
    {"index": 25, "name": "Title and Text with Image 1/3", "category": "content", "description": "Text with side image (1/3 width)"},
    {"index": 26, "name": "Full Bleed Image", "category": "content", "description": "Full-slide image layout"},
    {"index": 27, "name": "Text and Screenshot", "category": "content", "description": "Text with screenshot area"},
    {"index": 28, "name": "Title and Content", "category": "content", "description": "Generic content layout"},
    {"index": 29, "name": "Quote", "category": "content", "description": "Quote/testimonial layout"},
    {"index": 30, "name": "Q & A", "category": "content", "description": "Questions and answers slide"},
    {"index": 31, "name": "Thank You A", "category": "closing", "description": "Closing slide variant A"},
    {"index": 32, "name": "Thank You B", "category": "closing", "description": "Closing slide variant B"},
    {"index": 33, "name": "Blank", "category": "closing", "description": "Blank slide for custom content"},
    {"index": 34, "name": "User guide TIPS & TRICKS", "category": "guide", "description": "Template usage tips"},
    {"index": 35, "name": "User guide SAP BRAND SITE", "category": "guide", "description": "SAP brand guidelines"},
    {"index": 36, "name": "User guide COLOR PALETTE", "category": "guide", "description": "SAP color palette reference"},
    {"index": 37, "name": ">Copilot layouts >", "category": "copilot", "description": "Copilot layout section marker"},
    {"index": 38, "name": "Title Photo", "category": "copilot", "description": "Copilot title with photo"},
    {"index": 39, "name": "Title", "category": "copilot", "description": "Copilot title slide"},
    {"index": 40, "name": "Content 1", "category": "copilot", "description": "Copilot content layout 1"},
    {"index": 41, "name": "Two Content", "category": "copilot", "description": "Copilot two content areas"},
    {"index": 42, "name": "Content Photo 1", "category": "copilot", "description": "Copilot content with photo 1"},
    {"index": 43, "name": "Content Photo 2", "category": "copilot", "description": "Copilot content with photo 2"},
    {"index": 44, "name": ">DO NOT USE>", "category": "internal", "description": "Reserved - do not use"},
]

# Category descriptions
CATEGORIES = {
    "cover": "Title/cover slides for presentation start",
    "agenda": "Agenda and overview slides",
    "divider": "Section divider pages",
    "content": "Main content slides",
    "closing": "Thank you and closing slides",
    "guide": "Template user guide slides",
    "copilot": "Microsoft Copilot compatible layouts",
    "internal": "Internal use only - do not use",
}


def get_script_dir() -> Path:
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def get_template_path(custom_path: str | None = None) -> Path:
    """Get the path to the SAP template file."""
    if custom_path:
        return Path(custom_path)
    script_dir = get_script_dir()
    return script_dir.parent / "assets" / "SAP_Corp_2026.potx"


def filter_layouts(category: str | None = None) -> list[dict]:
    """Filter layouts by category."""
    if not category:
        return LAYOUTS
    
    category_lower = category.lower()
    return [l for l in LAYOUTS if l["category"] == category_lower]


def format_as_table(layouts: list[dict]) -> str:
    """Format layouts as a table."""
    lines = []
    lines.append(f"{'Index':<6} {'Name':<35} {'Category':<10} {'Description':<40}")
    lines.append("-" * 95)
    
    for layout in layouts:
        index = str(layout["index"])
        name = layout["name"][:33] if len(layout["name"]) > 33 else layout["name"]
        category = layout["category"][:8] if len(layout["category"]) > 8 else layout["category"]
        desc = layout["description"][:38] if len(layout["description"]) > 38 else layout["description"]
        lines.append(f"{index:<6} {name:<35} {category:<10} {desc:<40}")
    
    return "\n".join(lines)


def format_as_text(layouts: list[dict]) -> str:
    """Format layouts as plain text."""
    lines = []
    current_category = None
    
    for layout in layouts:
        if layout["category"] != current_category:
            current_category = layout["category"]
            if lines:
                lines.append("")
            cat_desc = CATEGORIES.get(current_category, current_category.title())
            lines.append(f"== {current_category.upper()} - {cat_desc} ==")
            lines.append("")
        
        lines.append(f"  [{layout['index']:2}] {layout['name']}")
        lines.append(f"       {layout['description']}")
    
    return "\n".join(lines)


def get_layouts_from_template(template_path: Path) -> list[dict]:
    """Get layout information directly from the template file."""
    if not template_path.exists():
        return []
    
    try:
        prs = Presentation(str(template_path))
        layouts = []
        for i, layout in enumerate(prs.slide_layouts):
            layouts.append({
                "index": i,
                "name": layout.name,
                "category": "unknown",
                "description": f"Layout from template",
            })
        return layouts
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="List all available slide layouts in the SAP PowerPoint template.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --format json
  %(prog)s --category cover
  %(prog)s --category content --format text

Categories:
  cover    - Title/cover slides
  agenda   - Agenda and overview slides
  divider  - Section divider pages
  content  - Main content slides
  closing  - Thank you and closing slides
  copilot  - Microsoft Copilot compatible layouts
        """,
    )
    parser.add_argument(
        "--format",
        choices=["json", "text", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--category",
        choices=["cover", "agenda", "divider", "content", "closing", "guide", "copilot"],
        help="Filter by category",
    )
    parser.add_argument(
        "--template",
        help="Custom template path (for verification)",
    )
    parser.add_argument(
        "--from-template",
        action="store_true",
        help="Read layouts directly from template file",
    )
    
    args = parser.parse_args()
    
    # Get layouts
    if args.from_template:
        template_path = get_template_path(args.template)
        if not template_path.exists():
            print(f"Error: Template not found: {template_path}", file=sys.stderr)
            sys.exit(2)
        layouts = get_layouts_from_template(template_path)
        if not layouts:
            print(f"Error: Could not read layouts from template", file=sys.stderr)
            sys.exit(2)
    else:
        layouts = filter_layouts(args.category)
    
    # Format output
    if args.format == "json":
        output = json.dumps(layouts, indent=2)
    elif args.format == "text":
        output = format_as_text(layouts)
    else:  # table
        output = format_as_table(layouts)
    
    print(output)
    
    # Print summary
    if args.format != "json":
        print(f"\nTotal layouts: {len(layouts)}")
        if args.category:
            print(f"Filtered by: {args.category}")


if __name__ == "__main__":
    main()