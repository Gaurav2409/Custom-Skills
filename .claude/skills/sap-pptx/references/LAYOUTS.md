# SAP PowerPoint Template Layouts

This document provides detailed information about all 45 slide layouts available in the SAP Corp 2026 PowerPoint template.

## Layout Index Reference

The layouts are organized by category and can be referenced by either name or index (0-based).

## Cover Slides (Index 0-11)

Cover slides are used for the opening of your presentation. They feature SAP branding elements and are designed for high visual impact.

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 0 | Cover A | Standard title slide with SAP branding | Title, Picture |
| 1 | Cover B | Alternative cover with different image placement | Title, Subtitle |
| 2 | Cover C | Cover with larger image area | Title, Picture |
| 3 | Cover D | Cover variant D | Title |
| 4 | Cover E | Cover variant E | Title |
| 5 | Cover F | Cover variant F | Title |
| 6 | Cover G | Cover variant G | Title |
| 7 | Cover H | Cover variant H | Title |
| 8 | Cover I | Cover variant I | Title |
| 9 | Cover J | Cover variant J | Title |
| 10 | Cover K | Cover variant K | Title |
| 11 | Cover L | Cover variant L | Title |

**Recommended Usage:**
- Use **Cover A** for standard external presentations
- Use **Cover B** for internal presentations
- Choose variants based on image requirements and visual preference

## Agenda Slides (Index 12-13)

Agenda slides help structure your presentation and set expectations.

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 12 | Agenda A | Standard agenda with bullet points | Title, Body |
| 13 | Agenda B | Alternative agenda layout | Title, Body |

**Recommended Usage:**
- Use at the beginning of presentations to outline topics
- Use to show progress through sections (highlight current topic)

## Divider Pages (Index 14-17)

Section dividers visually separate major topics within your presentation.

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 14 | Divider Page A | Standard section divider | Title |
| 15 | Divider Page B | Section divider variant B | Title |
| 16 | Divider Page C | Section divider variant C | Title |
| 17 | Divider Page D | Section divider variant D | Title |

**Recommended Usage:**
- Insert between major sections of your presentation
- Keep text minimal - typically just the section name
- Choose variant based on color scheme preference

## Content Slides (Index 18-30)

The main content slides for presenting information, data, and visuals.

### Text-Focused Layouts

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 18 | Title Only | Title with empty content area | Title |
| 19 | Title and Text | Standard content slide | Title, Body |
| 20 | Title and Text: 2 Columns | Two-column text layout | Title, Body (2x) |
| 21 | Title and Text: 3 Columns | Three-column text layout | Title, Body (3x) |

### Image-Focused Layouts

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 22 | 2 Columns - Text and Images | Two columns with text and images | Title, Body, Picture |
| 23 | 3 Columns - Text and Images | Three columns with text and images | Title, Body, Picture |
| 24 | 4 Columns - Text and Images | Four columns with text and images | Title, Body, Picture |
| 25 | Title and Text with Image 1/3 | Text with side image (1/3 width) | Title, Body, Picture |
| 26 | Full Bleed Image | Full-slide image layout | Picture |
| 27 | Text and Screenshot | Text with screenshot area | Title, Body, Picture |

### Special Content Layouts

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 28 | Title and Content | Generic content layout | Title, Content |
| 29 | Quote | Quote/testimonial layout | Title, Body |
| 30 | Q & A | Questions and answers slide | Title |

**Recommended Usage:**
- **Title and Text**: Most versatile, use for general content
- **2/3/4 Columns**: Comparing items, listing features
- **Full Bleed Image**: Visual impact, minimal text
- **Quote**: Customer testimonials, key messages
- **Q & A**: Session breaks, audience interaction

## Closing Slides (Index 31-33)

End your presentation professionally with these closing layouts.

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 31 | Thank You A | Standard closing slide | Title |
| 32 | Thank You B | Alternative closing with contact info | Title, Body |
| 33 | Blank | Empty slide for custom content | None |

**Recommended Usage:**
- **Thank You A**: Standard external presentations
- **Thank You B**: When including contact details
- **Blank**: Custom graphics or special endings

## User Guide Slides (Index 34-36)

These slides provide guidance on using the template. Generally not included in final presentations.

| Index | Name | Description |
|-------|------|-------------|
| 34 | User guide TIPS & TRICKS | Template usage tips |
| 35 | User guide SAP BRAND SITE | SAP brand guidelines reference |
| 36 | User guide COLOR PALETTE | Color palette reference |

**Note:** These are reference slides - delete before finalizing your presentation.

## Copilot Layouts (Index 37-43)

These layouts are optimized for Microsoft Copilot integration.

| Index | Name | Description | Placeholders |
|-------|------|-------------|--------------|
| 37 | >Copilot layouts > | Section marker (do not use) | - |
| 38 | Title Photo | Copilot title with photo | Title, Picture |
| 39 | Title | Copilot title slide | Title |
| 40 | Content 1 | Copilot content layout | Title, Body |
| 41 | Two Content | Two content areas | Title, Body (2x) |
| 42 | Content Photo 1 | Content with photo | Title, Body, Picture |
| 43 | Content Photo 2 | Alternative content with photo | Title, Body, Picture |

**Recommended Usage:**
- Use when creating presentations with Microsoft Copilot
- These layouts are optimized for AI-assisted content generation

## Internal/Reserved (Index 44)

| Index | Name | Description |
|-------|------|-------------|
| 44 | >DO NOT USE> | Reserved - do not use in presentations |

## Layout Selection Guide

### By Presentation Type

| Presentation Type | Recommended Layouts |
|-------------------|---------------------|
| Executive Summary | Cover A, Agenda A, Title and Text, Thank You A |
| Technical Deep-Dive | Cover B, Title and Text, Title and Text: 2 Columns, Q & A |
| Sales Pitch | Cover A, Agenda A, Quote, Thank You B |
| Training Material | Cover A, Agenda A, Title and Text, Q & A |
| Product Demo | Cover A, Full Bleed Image, Text and Screenshot |

### By Content Type

| Content Type | Best Layout |
|--------------|-------------|
| Bullet points | Title and Text |
| Comparison | Title and Text: 2 Columns |
| Feature list | 3 Columns - Text and Images |
| Screenshot walkthrough | Text and Screenshot |
| Customer quote | Quote |
| Visual emphasis | Full Bleed Image |

## Programmatic Layout Access

Use the layout name or index when creating slides programmatically:

```python
# By name (recommended)
add_slide(prs, "Title and Text", title="My Slide")

# By index (advanced)
slide_layout = prs.slide_layouts[19]  # Title and Text
```

## Layout Naming Conventions

- **Standard names** use spaces and proper capitalization: "Title and Text"
- **Multi-column layouts** include the number: "2 Columns - Text and Images"
- **Variants** use letter suffixes: "Cover A", "Cover B"
- **Special layouts** use prefixes: ">Copilot layouts >"