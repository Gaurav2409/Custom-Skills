---
name: sap-pptx
description: Create, edit, and read PowerPoint pptx files. Use when working with PowerPoint files, creating SAP-branded presentations, or manipulating slides with SAP color themes and fonts (72 Brand font family).
license: MIT
compatibility: Requires Python 3.9+ with uv or pip. The "72 Brand" font family should be installed for proper rendering.
metadata:
  version: "1.0.0"
  author: "SAP"
  category: "document-processing"
  template: "SAP_Corp_2026.potx"
---

# SAP PowerPoint Skill

Create, edit, and read PowerPoint presentations with SAP corporate branding.

## Prerequisites

- Python 3.9 or higher
- `uv` (recommended) or `pip`
- For proper font rendering: "72 Brand" and "72 Brand Medium" fonts installed

## Quick Start

1. Create a new SAP presentation: `uv run scripts/create_presentation.py --output my_presentation.pptx --title "My Title"`
2. Create from JSON file: `uv run scripts/create_presentation.py --output my_presentation.pptx --slides-json-file slides.json`
3. Export slides as images: `uv run scripts/export_slides_as_png.py my_presentation.pptx --resolution 4k`
4. Read presentation info: `uv run scripts/read_presentation.py my_presentation.pptx`
5. Edit a presentation: `uv run scripts/edit_presentation.py my_presentation.pptx --add-slide "Title and Text" --title "My Title"`

## Available Scripts

| Script | Purpose |
|--------|---------|
| `scripts/create_presentation.py` | Create new SAP-branded presentations |
| `scripts/export_slides_as_png.py` | Export slides as PNG/JPG images (Full HD, 4K) |
| `scripts/read_presentation.py` | Read and extract information from presentations |
| `scripts/edit_presentation.py` | Modify existing presentations |
| `scripts/list_layouts.py` | List all available SAP template layouts |

## SAP Template Information

### Color Theme (SAP Colors 2023)

| Color Name | Hex Code | Usage |
|------------|----------|-------|
| SAP Blue (Dark 2) | `#1B90FF` | Primary brand color |
| Light Blue (Light 2) | `#89D1FF` | Secondary blue |
| Mango (Accent 1) | `#E76500` | Highlights, CTAs |
| Teal (Accent 2) | `#049F9A` | Supporting color |
| Green (Accent 3) | `#36A41D` | Success, positive |
| Raspberry (Accent 4) | `#FA4F96` | Accent color |
| Pink (Accent 5) | `#F31DED` | Accent color |
| Indigo (Accent 6) | `#7858FF` | Accent color |
| Black (Dark 1) | `#000000` | Text |
| White (Light 1) | `#FFFFFF` | Backgrounds |
| Link Blue | `#0070F2` | Hyperlinks |

### Font Theme (SAP 2023)

- **Headings**: 72 Brand Medium
- **Body Text**: 72 Brand

### Available Slide Layouts

The SAP template includes 45 layouts organized by category:

**Cover Slides (1-12)**
- Cover A, B, C, D, E, F, G, H, I, J, K, L

**Agenda Slides (13-14)**
- Agenda A, Agenda B

**Divider Pages (15-18)**
- Divider Page A, B, C, D

**Content Slides (19-31)**
- Title Only
- Title and Text
- Title and Text: 2 Columns
- Title and Text: 3 Columns
- 2 Columns - Text and Images
- 3 Columns - Text and Images
- 4 Columns - Text and Images
- Title and Text with Image 1/3
- Full Bleed Image
- Text and Screenshot
- Title and Content
- Quote
- Q & A

**Closing Slides (32-34)**
- Thank You A, Thank You B
- Blank

See [references/LAYOUTS.md](references/LAYOUTS.md) for detailed layout descriptions.

## Usage

### Create a New Presentation

```bash
# Create empty presentation with SAP template
uv run scripts/create_presentation.py --output presentation.pptx

# Create with a title slide (default layout is Cover K)
uv run scripts/create_presentation.py --output presentation.pptx \
  --title "My Presentation" \
  --subtitle "Subtitle Here"

# Create with multiple slides from JSON file (RECOMMENDED)
uv run scripts/create_presentation.py --output presentation.pptx \
  --slides-json-file slides.json

# Read JSON from stdin
cat slides.json | uv run scripts/create_presentation.py --output presentation.pptx --slides-json -

# Inline JSON (only for simple cases without special characters)
uv run scripts/create_presentation.py --output presentation.pptx \
  --slides-json '[{"layout": "Cover K", "title": "Welcome"}]'
```

### JSON Slide Format

For multi-slide presentations, create a JSON file with an array of slide definitions:

```json
[
  {
    "layout": "Cover K",
    "title": "SAP Innovation Summit 2026",
    "subtitle": "Transforming Business with Intelligent Technology"
  },
  {
    "layout": "Agenda A",
    "title": "Agenda",
    "body": "1. Introduction to SAP Solutions\n2. Digital Transformation Strategy\n3. Customer Success Stories\n4. Next Steps"
  },
  {
    "layout": "Title and Text",
    "title": "Introduction to SAP Solutions",
    "body": "SAP provides enterprise software to manage business operations:\n\n• Enterprise Resource Planning (ERP)\n• Customer Relationship Management (CRM)\n• Supply Chain Management (SCM)"
  },
  {
    "layout": "Thank You A",
    "title": "Thank You",
    "body": "Contact us at: info@sap.com\nwww.sap.com"
  }
]
```

**Important**: For presentations with multiple slides or content containing special characters (newlines, quotes, bullet points), always use `--slides-json-file` instead of inline `--slides-json`. This avoids shell escaping issues that can corrupt the JSON.

### Read Presentation Information

```bash
# Get presentation summary
uv run scripts/read_presentation.py presentation.pptx

# Output as JSON
uv run scripts/read_presentation.py presentation.pptx --format json

# Extract text content only
uv run scripts/read_presentation.py presentation.pptx --text-only

# Get specific slide info
uv run scripts/read_presentation.py presentation.pptx --slide 2
```

### Edit an Existing Presentation

```bash
# Add a new slide
uv run scripts/edit_presentation.py presentation.pptx \
  --add-slide "Title and Text" \
  --title "New Slide Title" \
  --body "Slide content here"

# Update slide content
uv run scripts/edit_presentation.py presentation.pptx \
  --slide 2 \
  --title "Updated Title"

# Delete a slide
uv run scripts/edit_presentation.py presentation.pptx \
  --delete-slide 3

# Reorder slides
uv run scripts/edit_presentation.py presentation.pptx \
  --move-slide 3 --to-position 1

# Add image to slide
uv run scripts/edit_presentation.py presentation.pptx \
  --slide 2 \
  --add-image path/to/image.png \
  --image-position "center"

# Preview changes without saving
uv run scripts/edit_presentation.py presentation.pptx \
  --add-slide "Blank" \
  --dry-run
```

### Export Slides as PNG/JPG Images

Export slides as high-resolution images for use in videos, social media, or other applications.

**Prerequisites for export:**
- LibreOffice (for direct PPTX to image conversion)

```bash
# macOS installation
brew install --cask libreoffice

# Ubuntu/Debian installation
sudo apt-get install libreoffice

# Windows installation
# Download from https://www.libreoffice.org/
```

**Resolution Presets:**
| Preset | Resolution | Use Case |
|--------|------------|----------|
| `fullhd` / `1080p` | 1920×1080 | Standard HD displays, YouTube |
| `4k` / `uhd` / `2160p` | 3840×2160 | 4K displays, high-quality video |
| `hd` / `720p` | 1280×720 | Smaller file sizes, web use |

```bash
# Export all slides as Full HD PNGs (default)
uv run scripts/export_slides_as_png.py presentation.pptx

# Export as 4K resolution
uv run scripts/export_slides_as_png.py presentation.pptx --resolution 4k

# Export specific slides to a custom directory
uv run scripts/export_slides_as_png.py presentation.pptx \
  --output-dir ./images \
  --slides 1-5

# Export only specific slides (comma-separated)
uv run scripts/export_slides_as_png.py presentation.pptx --slides 1,3,5,10

# Export with custom resolution (e.g., 2K/QHD)
uv run scripts/export_slides_as_png.py presentation.pptx --resolution 2560x1440

# Export as JPEG with custom quality (smaller files)
uv run scripts/export_slides_as_png.py presentation.pptx \
  --format jpg \
  --quality 85

# Export with custom filename prefix
uv run scripts/export_slides_as_png.py presentation.pptx \
  --prefix "sap_summit" \
  --resolution 4k
```

**Output:** The script creates numbered image files (e.g., `presentation_001.png`, `presentation_002.png`) and outputs JSON with export details:

```json
{
  "input_file": "presentation.pptx",
  "output_directory": "./images",
  "resolution": "1920x1080",
  "total_slides": 10,
  "exported_count": 5,
  "format": "png",
  "files": [
    {"slide_number": 1, "filename": "presentation_001.png", "path": "./images/presentation_001.png"}
  ]
}
```

### List Available Layouts

```bash
# List all layouts
uv run scripts/list_layouts.py

# List layouts in JSON format
uv run scripts/list_layouts.py --format json

# Filter by category
uv run scripts/list_layouts.py --category cover
```

## Working with SAP Colors Programmatically

When adding custom elements, use the SAP color values:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RgbColor

# SAP Colors
SAP_BLUE = RgbColor(0x1B, 0x90, 0xFF)
SAP_MANGO = RgbColor(0xE7, 0x65, 0x00)
SAP_TEAL = RgbColor(0x04, 0x9F, 0x9A)
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `FileNotFoundError` | Input file doesn't exist | Check the file path |
| `InvalidLayoutError` | Layout name not found | Use `list_layouts.py` to see available layouts |
| `TemplateNotFoundError` | SAP template missing | Ensure template is in assets folder |
| `PackageNotFoundError` | python-pptx not installed | Run with `uv run` or install dependencies |
| `Invalid JSON` | JSON parsing failed | Use `--slides-json-file` instead of inline JSON |
| `LibreOffice not found` | LibreOffice not installed | Install LibreOffice for PNG export |

### Common JSON Issues

If you see `Invalid JSON` errors when using `--slides-json`, the cause is usually shell escaping problems with special characters. **Solution**: Save your JSON to a file and use `--slides-json-file`:

```bash
# Instead of this (error-prone):
uv run scripts/create_presentation.py --output out.pptx --slides-json '[{"title": "Hello\nWorld"}]'

# Do this (reliable):
echo '[{"title": "Hello\nWorld"}]' > slides.json
uv run scripts/create_presentation.py --output out.pptx --slides-json-file slides.json
```

## Limitations

- Font rendering depends on having "72 Brand" fonts installed on the system
- Some complex template features (animations, transitions) may not be fully preserved
- Images in slides are referenced, not embedded when using edit operations
- Maximum recommended file size: 100MB
- PNG export requires LibreOffice to be installed
- Export resolution is limited by available system memory for very large presentations

## Additional Resources

- [SAP Brand Portal](https://brand.sap.com) - Official SAP branding guidelines
- [references/LAYOUTS.md](references/LAYOUTS.md) - Detailed layout documentation
- [references/COLORS.md](references/COLORS.md) - Complete SAP color palette