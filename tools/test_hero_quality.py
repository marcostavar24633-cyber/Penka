#!/usr/bin/env python3
"""Compare WebP quality candidates for the PENKA hero without changing production assets."""
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "img" / "penka-hero.webp"
OUT = ROOT / "hero-quality-report"
WIDTH = 768
QUALITIES = (70, 74, 78, 82)

def metrics(reference: np.ndarray, candidate: np.ndarray):
    x = reference.astype(np.float64)
    y = candidate.astype(np.float64)
    mse = float(np.mean((x - y) ** 2))
    psnr = float("inf") if mse == 0 else 10 * np.log10((255.0 ** 2) / mse)
    # Global SSIM per RGB channel, averaged; useful for a consistent candidate comparison.
    c1, c2 = 6.5025, 58.5225
    scores = []
    for channel in range(3):
        a, b = x[..., channel], y[..., channel]
        ma, mb = a.mean(), b.mean()
        va, vb = a.var(), b.var()
        cov = ((a - ma) * (b - mb)).mean()
        scores.append(((2 * ma * mb + c1) * (2 * cov + c2)) /
                      ((ma * ma + mb * mb + c1) * (va + vb + c2)))
    return psnr, float(np.mean(scores))

def main():
    OUT.mkdir(exist_ok=True)
    with Image.open(SOURCE) as im:
        reference = ImageOps.exif_transpose(im).convert("RGB")
        reference.thumbnail((WIDTH, WIDTH * 2), Image.Resampling.LANCZOS)
        ref = np.asarray(reference)
        print(f"Reference: {reference.width}x{reference.height}")
        print("quality | bytes | PSNR dB | global SSIM")
        print("-" * 48)
        for quality in QUALITIES:
            target = OUT / f"penka-hero-{WIDTH}-q{quality}.webp"
            reference.save(target, "WEBP", quality=quality, method=6)
            with Image.open(target) as encoded:
                candidate = np.asarray(encoded.convert("RGB"))
            psnr, ssim = metrics(ref, candidate)
            print(f"{quality:>7} | {target.stat().st_size:>5} | {psnr:>7.2f} | {ssim:.6f}")
    print("Report-only test: img/ and img/responsive/ were not modified.")

if __name__ == "__main__":
    main()
