#!/usr/bin/env python3
"""Cut an equal grid sheet into normalized 208x208 frames with one common scale.

Background is keyed per cell from its corners (different blue shades are allowed).
The common scale comes from the rest cell (cell 1 by default); every cell keeps
the same pixels-per-unit scale, so stretch/squash is preserved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chroma_key import key_sheet  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def alpha_bbox(image: Image.Image, threshold: int = 8):
    a = np.array(image.convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(a > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def cell_bounds(width: int, height: int, cols: int, rows: int, index: int):
    c = index % cols
    r = index // cols
    x0 = round(c * width / cols)
    x1 = round((c + 1) * width / cols)
    y0 = round(r * height / rows)
    y1 = round((r + 1) * height / rows)
    return x0, y0, x1, y1


def load_names(path: str | None, names_arg: str | None, count: int) -> list[str]:
    names: list[str] | None = None

    if path:
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            data = json.loads(text)
            if isinstance(data, dict):
                names = [str(data.get(str(i), data.get(i, f"cell_{i:02d}"))) for i in range(1, count + 1)]
            elif isinstance(data, list):
                names = [str(v) for v in data]
            else:
                raise SystemExit("mapping JSON must be an object or a list")
        else:
            names = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^(\d+)\s*[=,;:]\s*(.+)$", line)
                if m:
                    idx = int(m.group(1))
                    while len(names) < idx:
                        names.append(f"cell_{len(names) + 1:02d}")
                    names[idx - 1] = m.group(2).strip()
                else:
                    names.append(line)

    if names_arg:
        names = [v.strip() for v in names_arg.split(",") if v.strip()]

    if not names:
        names = [f"cell_{i:02d}" for i in range(1, count + 1)]
    if len(names) < count:
        names += [f"cell_{i:02d}" for i in range(len(names) + 1, count + 1)]
    return names[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description="Cut and normalize a grid sprite sheet.")
    parser.add_argument("input", help="sheet image (JPG/PNG)")
    parser.add_argument("output", help="output directory for frames")
    parser.add_argument("--cols", type=int, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--names", help="comma-separated names in row-major order")
    parser.add_argument("--mapping", help="JSON object/list or index=name text file")
    parser.add_argument("--key", default="auto", help="auto, none or RRGGBB")
    parser.add_argument("--tol", type=float, default=30.0)
    parser.add_argument("--soft", type=float, default=45.0)
    parser.add_argument("--no-despill", action="store_true")
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--content", type=int, default=104)
    parser.add_argument("--cx", type=int, default=104)
    parser.add_argument("--bottom", type=int, default=155)
    parser.add_argument("--ref-cell", type=int, default=1, help="1-based rest cell for common scale")
    args = parser.parse_args()
    if args.cols < 1 or args.rows < 1:
        parser.error("--cols/--rows must be >= 1")

    image = Image.open(args.input)
    sheet = key_sheet(image, args.cols, args.rows, args.key, args.tol, args.soft,
                      not args.no_despill)
    w, h = sheet.size
    count = args.cols * args.rows
    names = load_names(args.mapping, args.names, count)

    cells = []
    for i in range(count):
        x0, y0, x1, y1 = cell_bounds(w, h, args.cols, args.rows, i)
        cells.append(sheet.crop((x0, y0, x1, y1)))

    ref_index = max(1, min(count, args.ref_cell)) - 1
    ref_box = alpha_bbox(cells[ref_index])
    if ref_box is None:
        raise SystemExit(f"reference cell {ref_index + 1} is empty after keying")
    ref_h = ref_box[3] - ref_box[1]
    scale = args.content / max(1, ref_h)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    warnings = 0
    for i, cell in enumerate(cells):
        box = alpha_bbox(cell)
        if box is None:
            print(f"WARN empty cell {i + 1}: {names[i]}")
            warnings += 1
            continue
        crop = cell.crop(box)
        cw = max(1, round(crop.width * scale))
        ch = max(1, round(crop.height * scale))
        resized = crop.resize((cw, ch), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (args.size, args.size), (0, 0, 0, 0))
        x = args.cx - cw // 2
        y = args.bottom - ch
        if x < 0 or y < 0 or x + cw > args.size or y + ch > args.size:
            warnings += 1
            print(f"WARN clipping {names[i]}: x={x} y={y} w={cw} h={ch}")
        canvas.alpha_composite(resized, (x, y))
        canvas.save(out / f"{names[i]}.png")

    print(f"cut {count} cells -> {out}")
    print(f"grid={args.cols}x{args.rows}, ref_cell={ref_index + 1}, scale={scale:.6f}, warnings={warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
