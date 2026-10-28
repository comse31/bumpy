#!/usr/bin/env python3
"""Normalize cut-out frames onto a common 208x208 canvas with one pivot/scale."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".webp"}


def alpha_bbox(image: Image.Image, threshold: int = 8):
    a = np.array(image.convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(a > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def reference_file(files: list[Path], explicit: Path | None) -> Path:
    if explicit:
        return explicit
    rest = [p for p in files if "rest" in p.stem.lower()]
    if rest:
        return sorted(rest)[0]
    return files[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Place frames on 208x208, feet y=155, center x=104.")
    parser.add_argument("input", help="input directory with transparent frames")
    parser.add_argument("output", help="output directory")
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--content", type=int, default=104, help="reference rest-frame height in px")
    parser.add_argument("--cx", type=int, default=104)
    parser.add_argument("--bottom", type=int, default=155)
    parser.add_argument("--ref", help="reference frame for common scale (default: *rest*)")
    parser.add_argument("--threshold", type=int, default=8)
    args = parser.parse_args()

    src_dir = Path(args.input)
    out_dir = Path(args.output)
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        parser.error(f"no PNG/WebP in {src_dir}")

    ref = reference_file(files, Path(args.ref) if args.ref else None)
    ref_img = Image.open(ref).convert("RGBA")
    ref_box = alpha_bbox(ref_img, args.threshold)
    if ref_box is None:
        parser.error(f"reference has no alpha content: {ref}")
    ref_h = ref_box[3] - ref_box[1]
    if ref_h <= 0:
        parser.error(f"bad reference bbox: {ref}")
    scale = args.content / ref_h

    out_dir.mkdir(parents=True, exist_ok=True)
    warnings = 0
    for src in files:
        img = Image.open(src).convert("RGBA")
        box = alpha_bbox(img, args.threshold)
        if box is None:
            print(f"WARN empty alpha: {src.name}")
            warnings += 1
            continue
        crop = img.crop(box)
        w = max(1, int(round(crop.width * scale)))
        h = max(1, int(round(crop.height * scale)))
        resized = crop.resize((w, h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (args.size, args.size), (0, 0, 0, 0))
        x = args.cx - w // 2
        y = args.bottom - h
        if x < 0 or y < 0 or x + w > args.size or y + h > args.size:
            warnings += 1
            print(f"WARN clipping: {src.name} at x={x} y={y} w={w} h={h}")
        canvas.alpha_composite(resized, (x, y))
        canvas.save(out_dir / (src.stem + ".png"))

    print(f"normalized {len(files)} frame(s), scale={scale:.6f}, ref={ref.name}, warnings={warnings} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
