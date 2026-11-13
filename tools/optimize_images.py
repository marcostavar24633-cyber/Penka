#!/usr/bin/env python3
"""Create visually conservative WebP replacements in optimized/img without touching originals.

Usage:
  python -m pip install Pillow
  python tools/optimize_images.py
  python tools/optimize_images.py --quality 78 --max-width 1800
"""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "img"
OUTPUT = ROOT / "optimized" / "img"

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", type=int, default=80, choices=range(60, 96))
    parser.add_argument("--max-width", type=int, default=1800)
    parser.add_argument("--max-height", type=int, default=1800)
    args = parser.parse_args()

    files = sorted(SOURCE.glob("*.webp"))
    if not files:
        raise SystemExit(f"No WebP files found in {SOURCE}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    total_before = total_after = 0
    print(f"{'FILE':28} {'BEFORE':>10} {'AFTER':>10} {'SAVED':>9}")
    print("-" * 62)

    for source in files:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.thumbnail((args.max_width, args.max_height), Image.Resampling.LANCZOS)
            target = OUTPUT / source.name
            image.save(target, "WEBP", quality=args.quality, method=6)
        before, after = source.stat().st_size, target.stat().st_size
        total_before += before
        total_after += after
        saved = (1 - after / before) * 100 if before else 0
        print(f"{source.name:28} {before:9,} B {after:9,} B {saved:8.1f}%")

    print("-" * 62)
    saved_total = (1 - total_after / total_before) * 100 if total_before else 0
    print(f"{'TOTAL':28} {total_before:9,} B {total_after:9,} B {saved_total:8.1f}%")
    print(f"\nOptimized files are in: {OUTPUT}")
    print("Original images were not modified.")

if __name__ == "__main__":
    main()
