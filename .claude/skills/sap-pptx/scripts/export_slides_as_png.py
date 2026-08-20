#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "Pillow>=9.0.0",
# ]
# ///
"""
Export PowerPoint slides as PNG images in Full HD or 4K resolution.

This script converts PPTX presentations directly to high-resolution PNG images
using LibreOffice's native image export capabilities (no PDF intermediate step).

Prerequisites:
    - LibreOffice installed (with UNO Python bindings)
    
    macOS:
        brew install --cask libreoffice
    
    Ubuntu/Debian:
        sudo apt-get install libreoffice
    
    Windows:
        Install LibreOffice from https://www.libreoffice.org/

Usage:
    uv run scripts/export_slides_as_png.py INPUT_FILE [OPTIONS]

Options:
    INPUT_FILE              Input PPTX file path (required)
    --output-dir DIR        Output directory for PNG files (default: same as input)
    --resolution RES        Resolution: "fullhd", "4k", or "WIDTHxHEIGHT" (default: fullhd)
    --slides RANGE          Slide range to export: "all", "1", "1-3", "1,3,5" (default: all)
    --prefix PREFIX         Filename prefix for output files (default: input filename)
    --format FORMAT         Output format: "png" or "jpg" (default: png)
    --quality QUALITY       JPEG quality 1-100 (default: 95, only for jpg format)
    --help                  Show this help message

Exit Codes:
    0 - Success
    1 - Invalid arguments
    2 - Input file not found
    3 - LibreOffice not found
    5 - Conversion error

Examples:
    # Export all slides as Full HD PNGs
    uv run scripts/export_slides_as_png.py presentation.pptx
    
    # Export as 4K resolution
    uv run scripts/export_slides_as_png.py presentation.pptx --resolution 4k
    
    # Export specific slides to a directory
    uv run scripts/export_slides_as_png.py presentation.pptx --output-dir ./images --slides 1-5
    
    # Export with custom resolution
    uv run scripts/export_slides_as_png.py presentation.pptx --resolution 2560x1440
    
    # Export as JPEG with custom quality
    uv run scripts/export_slides_as_png.py presentation.pptx --format jpg --quality 90
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image


# Resolution presets (width x height)
RESOLUTION_PRESETS = {
    "fullhd": (1920, 1080),
    "full_hd": (1920, 1080),
    "1080p": (1920, 1080),
    "4k": (3840, 2160),
    "uhd": (3840, 2160),
    "2160p": (3840, 2160),
    "hd": (1280, 720),
    "720p": (1280, 720),
}

# Standard PowerPoint slide aspect ratio (16:9)
SLIDE_ASPECT_RATIO = 16 / 9


def parse_resolution(resolution_str: str) -> tuple[int, int]:
    """Parse resolution string into width and height tuple."""
    resolution_lower = resolution_str.lower().strip()
    
    # Check presets first
    if resolution_lower in RESOLUTION_PRESETS:
        return RESOLUTION_PRESETS[resolution_lower]
    
    # Try to parse WIDTHxHEIGHT format
    if "x" in resolution_lower:
        try:
            parts = resolution_lower.split("x")
            width = int(parts[0].strip())
            height = int(parts[1].strip())
            if width > 0 and height > 0:
                return (width, height)
        except (ValueError, IndexError):
            pass
    
    raise ValueError(
        f"Invalid resolution: {resolution_str}. "
        f"Use 'fullhd', '4k', or 'WIDTHxHEIGHT' format (e.g., '2560x1440')"
    )


def parse_slide_range(range_str: str, total_slides: int) -> list[int]:
    """Parse slide range string into list of slide numbers (1-based)."""
    if range_str.lower() == "all":
        return list(range(1, total_slides + 1))
    
    slides = set()
    parts = range_str.split(",")
    
    for part in parts:
        part = part.strip()
        if "-" in part:
            # Range: "1-5"
            try:
                start, end = part.split("-")
                start = int(start.strip())
                end = int(end.strip())
                for i in range(start, end + 1):
                    if 1 <= i <= total_slides:
                        slides.add(i)
            except ValueError:
                raise ValueError(f"Invalid slide range: {part}")
        else:
            # Single slide: "3"
            try:
                slide_num = int(part)
                if 1 <= slide_num <= total_slides:
                    slides.add(slide_num)
            except ValueError:
                raise ValueError(f"Invalid slide number: {part}")
    
    return sorted(slides)


def find_libreoffice() -> Optional[str]:
    """Find LibreOffice executable path."""
    # Common executable names
    executables = ["soffice", "libreoffice", "libreoffice7.0"]
    
    # macOS specific paths
    mac_paths = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/libreoffice",
    ]
    
    # Windows specific paths
    win_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    
    # Check PATH first
    for exe in executables:
        path = shutil.which(exe)
        if path:
            return path
    
    # Check platform-specific paths
    if sys.platform == "darwin":
        for path in mac_paths:
            if os.path.exists(path):
                return path
    elif sys.platform == "win32":
        for path in win_paths:
            if os.path.exists(path):
                return path
    
    return None


def export_slides_directly(
    pptx_path: Path,
    output_dir: Path,
    libreoffice_path: str,
    output_format: str = "png",
) -> list[Path]:
    """
    Export PPTX slides directly to images using LibreOffice.
    
    This uses LibreOffice's native image export filter which directly
    converts each slide to an image file without intermediate PDF conversion.
    """
    # Determine the export filter based on format
    if output_format == "jpg":
        filter_name = "impress_jpg_Export"
    else:
        filter_name = "impress_png_Export"
    
    # LibreOffice command to convert directly to images
    # The filter exports each slide as a separate image file
    cmd = [
        libreoffice_path,
        "--headless",
        "--convert-to", f"{output_format}:{filter_name}",
        "--outdir", str(output_dir),
        str(pptx_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for large presentations
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreOffice conversion timed out (300s)")
    
    # Find all exported image files
    # LibreOffice exports as: filename.png (single) or filename-1.png, filename-2.png, etc. (multiple)
    stem = pptx_path.stem
    ext = output_format
    
    # Check for single file first (presentations with 1 slide)
    single_file = output_dir / f"{stem}.{ext}"
    if single_file.exists():
        return [single_file]
    
    # Look for numbered files (multi-slide presentations)
    pattern = str(output_dir / f"{stem}*.{ext}")
    files = sorted(glob.glob(pattern))
    
    if not files:
        raise RuntimeError(
            f"No image files were created. Expected pattern: {pattern}"
        )
    
    return [Path(f) for f in files]


def count_slides_in_pptx(pptx_path: Path) -> int:
    """Count the number of slides in a PPTX file without external dependencies."""
    import zipfile
    import xml.etree.ElementTree as ET
    
    try:
        with zipfile.ZipFile(pptx_path, 'r') as z:
            # The presentation.xml.rels file contains references to all slides
            rels_path = 'ppt/_rels/presentation.xml.rels'
            if rels_path not in z.namelist():
                # Fallback: count slide files directly
                slide_files = [f for f in z.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')]
                return len(slide_files)
            
            with z.open(rels_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                # Count relationships that point to slides
                slide_count = 0
                for rel in root.iter():
                    target = rel.get('Target', '')
                    if 'slides/slide' in target:
                        slide_count += 1
                return slide_count
    except Exception:
        # If we can't count slides, return 0 and let the export handle it
        return 0


def resize_and_save_images(
    image_paths: list[Path],
    output_dir: Path,
    resolution: tuple[int, int],
    slides: Optional[list[int]],
    prefix: str,
    output_format: str,
    jpeg_quality: int,
) -> list[dict]:
    """Resize exported images to target resolution and save with proper naming."""
    exported_files = []
    total_slides = len(image_paths)
    
    # If no specific slides requested, export all
    if slides is None:
        slides = list(range(1, total_slides + 1))
    
    for slide_num in slides:
        if slide_num < 1 or slide_num > total_slides:
            continue
        
        img_path = image_paths[slide_num - 1]  # 0-based index
        
        # Open and resize image
        with Image.open(img_path) as img:
            img_resized = img.resize(resolution, Image.Resampling.LANCZOS)
            
            # Generate output filename
            ext = "jpg" if output_format == "jpg" else "png"
            filename = f"{prefix}_{slide_num:03d}.{ext}"
            output_path = output_dir / filename
            
            # Save image
            if output_format == "jpg":
                # Convert to RGB if necessary (PNG might have alpha channel)
                if img_resized.mode in ('RGBA', 'LA', 'P'):
                    img_resized = img_resized.convert('RGB')
                img_resized.save(output_path, "JPEG", quality=jpeg_quality)
            else:
                img_resized.save(output_path, "PNG")
            
            exported_files.append({
                "slide_number": slide_num,
                "filename": filename,
                "path": str(output_path),
                "width": resolution[0],
                "height": resolution[1],
                "format": output_format,
            })
    
    return exported_files


def export_slides_as_png(
    input_path: Path,
    output_dir: Path,
    resolution: tuple[int, int],
    slides: Optional[str] = None,
    prefix: Optional[str] = None,
    output_format: str = "png",
    jpeg_quality: int = 95,
) -> dict:
    """Export slides from PPTX as PNG/JPG images."""
    
    # Validate input file
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if not input_path.suffix.lower() in [".pptx", ".ppt", ".odp"]:
        raise ValueError(f"Unsupported file format: {input_path.suffix}")
    
    # Find LibreOffice
    libreoffice_path = find_libreoffice()
    if not libreoffice_path:
        raise RuntimeError(
            "LibreOffice not found. Install with:\n"
            "  macOS: brew install --cask libreoffice\n"
            "  Ubuntu: sudo apt-get install libreoffice\n"
            "  Windows: Download from https://www.libreoffice.org/"
        )
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use input filename as prefix if not specified
    if prefix is None:
        prefix = input_path.stem
    
    # Create temporary directory for LibreOffice's raw export
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Export slides directly to images using LibreOffice
        raw_images = export_slides_directly(
            pptx_path=input_path,
            output_dir=temp_path,
            libreoffice_path=libreoffice_path,
            output_format=output_format,
        )
        
        total_slides = len(raw_images)
        
        # Parse slide range
        if slides:
            slide_list = parse_slide_range(slides, total_slides)
        else:
            slide_list = None  # All slides
        
        # Resize and save images with proper naming
        exported_files = resize_and_save_images(
            image_paths=raw_images,
            output_dir=output_dir,
            resolution=resolution,
            slides=slide_list,
            prefix=prefix,
            output_format=output_format,
            jpeg_quality=jpeg_quality,
        )
    
    return {
        "input_file": str(input_path),
        "output_directory": str(output_dir),
        "resolution": f"{resolution[0]}x{resolution[1]}",
        "total_slides": total_slides,
        "exported_count": len(exported_files),
        "format": output_format,
        "files": exported_files,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export PowerPoint slides as PNG/JPG images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Resolution Presets:
  fullhd, 1080p    1920x1080 (Full HD)
  4k, uhd, 2160p   3840x2160 (4K Ultra HD)
  hd, 720p         1280x720 (HD)

Examples:
  %(prog)s presentation.pptx
  %(prog)s presentation.pptx --resolution 4k
  %(prog)s presentation.pptx --output-dir ./images --slides 1-5
  %(prog)s presentation.pptx --resolution 2560x1440
  %(prog)s presentation.pptx --format jpg --quality 90
        """,
    )
    
    parser.add_argument(
        "input",
        help="Input PPTX file path",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory for PNG files (default: same as input file)",
    )
    parser.add_argument(
        "--resolution", "-r",
        default="fullhd",
        help="Resolution: 'fullhd', '4k', or 'WIDTHxHEIGHT' (default: fullhd)",
    )
    parser.add_argument(
        "--slides", "-s",
        help="Slide range: 'all', '1', '1-3', '1,3,5' (default: all)",
    )
    parser.add_argument(
        "--prefix", "-p",
        help="Filename prefix for output files (default: input filename)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["png", "jpg"],
        default="png",
        help="Output format: 'png' or 'jpg' (default: png)",
    )
    parser.add_argument(
        "--quality", "-q",
        type=int,
        default=95,
        help="JPEG quality 1-100 (default: 95, only for jpg format)",
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(2)
    
    # Parse resolution
    try:
        resolution = parse_resolution(args.resolution)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = input_path.parent
    
    # Validate quality
    if args.quality < 1 or args.quality > 100:
        print("Error: Quality must be between 1 and 100", file=sys.stderr)
        sys.exit(1)
    
    # Check dependencies
    if not find_libreoffice():
        print("Error: LibreOffice not found.", file=sys.stderr)
        print("Install with:", file=sys.stderr)
        print("  macOS: brew install --cask libreoffice", file=sys.stderr)
        print("  Ubuntu: sudo apt-get install libreoffice", file=sys.stderr)
        print("  Windows: Download from https://www.libreoffice.org/", file=sys.stderr)
        sys.exit(3)
    
    try:
        result = export_slides_as_png(
            input_path=input_path,
            output_dir=output_dir,
            resolution=resolution,
            slides=args.slides,
            prefix=args.prefix,
            output_format=args.format,
            jpeg_quality=args.quality,
        )
        
        print(json.dumps(result, indent=2))
        print(f"\nExported {result['exported_count']} slides to: {result['output_directory']}", file=sys.stderr)
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(5)
    except Exception as e:
        print(f"Error: Failed to export slides: {e}", file=sys.stderr)
        sys.exit(5)


if __name__ == "__main__":
    main()