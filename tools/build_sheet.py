#!/usr/bin/env python3
"""Pack normalized frames into a sprite sheet and a JSON manifest."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {".png", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack frames into a sprite sheet + JSON.")
    parser.add_argument("input", help="directory with normalized frames")
    parser.add_argument("output", help="output sprite sheet PNG")
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--frame-size", type=int, default=208)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--pivot", default="104,155", help="pivot x,y inside a frame")
    parser.add_argument("--json", help="manifest path (default: output with .json)")
    args = parser.parse_args()

    src_dir = Path(args.input)
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        parser.error(f"no PNG/WebP in {src_dir}")

    size = args.frame_size
    cols = max(1, args.cols)
    rows = math.ceil(len(files) / cols)
    sheet = Image.new("RGBA", (cols * size, rows * size), (0, 0, 0, 0))

    for i, path in enumerate(files):
        img = Image.open(path).convert("RGBA")
        if img.size != (size, size):
            print(f"WARN resize {path.name}: {img.size} -> {(size, size)}")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
        x = (i % cols) * size
        y = (i // cols) * size
        sheet.alpha_composite(img, (x, y))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)

    pivot = [int(v.strip()) for v in args.pivot.split(",")]
    manifest = {
        "sheet": out.name,
        "frame_width": size,
        "frame_height": size,
        "columns": cols,
        "rows": rows,
        "count": len(files),
        "fps": args.fps,
        "pivot": {"x": pivot[0], "y": pivot[1]},
        "frames": [
            {"index": i, "name": p.stem, "file": p.name}
            for i, p in enumerate(files)
        ],
    }
    json_path = Path(args.json) if args.json else out.with_suffix(".json")
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sheet: {out} ({cols}x{rows}, {len(files)} frames)\nmanifest: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
