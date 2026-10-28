#!/usr/bin/env python3
"""Build a numbered contact sheet from a folder of PNG frames."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTS = {".png", ".webp"}


def load_font(size: int = 14):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description="Contact sheet with frame names and numbers.")
    parser.add_argument("input", help="directory with PNG frames")
    parser.add_argument("output", help="output PNG")
    parser.add_argument("--cols", type=int, default=6)
    parser.add_argument("--cell", type=int, default=208)
    parser.add_argument("--label", type=int, default=22)
    parser.add_argument("--pad", type=int, default=6)
    args = parser.parse_args()

    src_dir = Path(args.input)
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        parser.error(f"no PNG/WebP in {src_dir}")

    font = load_font(14)
    cols = max(1, args.cols)
    rows = math.ceil(len(files) / cols)
    cell_w = args.cell + args.pad * 2
    cell_h = args.cell + args.label + args.pad * 2
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (245, 245, 245, 255))
    draw = ImageDraw.Draw(sheet)

    for i, path in enumerate(files):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((args.cell, args.cell), Image.Resampling.LANCZOS)
        col = i % cols
        row = i // cols
        x = col * cell_w + args.pad + (args.cell - image.width) // 2
        y = row * cell_h + args.pad + args.label + (args.cell - image.height) // 2
        sheet.alpha_composite(image, (x, y))
        label = f"{i + 1:02d} {path.stem}"
        draw.text((col * cell_w + args.pad, row * cell_h + 3), label, fill=(20, 20, 20, 255), font=font)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out)
    print(f"contact sheet: {out} ({len(files)} frames, {cols}x{rows})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
