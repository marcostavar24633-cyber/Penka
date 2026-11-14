#!/usr/bin/env python3
"""Generate responsive WebP image variants without modifying source assets."""
from pathlib import Path
from PIL import Image, ImageOps
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "img"
OUTPUT = SOURCE / "responsive"
WIDTHS = (480, 768, 1200, 1800)
def main():
    files = sorted(p for p in SOURCE.glob("*.webp") if p.is_file())
    if not files:
        raise SystemExit(f"No WebP files found in {SOURCE}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for source in files:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            for width in WIDTHS:
                if image.width < width:
                    continue
                variant = image.copy()
                variant.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
                target = OUTPUT / f"{source.stem}-{width}.webp"
                quality = 70 if width <= 768 else 76
                variant.save(target, "WEBP", quality=quality, method=6)
                total += target.stat().st_size
                print(f"{target.relative_to(ROOT)}: {target.stat().st_size:,} bytes ({variant.width}x{variant.height}, q={quality})")
    print(f"Responsive assets generated: {total:,} bytes")
if __name__ == "__main__":
    main()
