#!/usr/bin/env python3
"""Validate normalized Bumpy frames: bbox, pivot, edge, blue residue, holes/fill."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".webp"}


def parse_hex(value: str) -> np.ndarray:
    value = value.strip().lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)


def hole_stats(alpha: np.ndarray, threshold: int) -> tuple[int, int, int]:
    """Return opaque, hole and filled-silhouette pixel counts.

    Transparent pixels connected to the canvas border are outside; transparent
    pixels enclosed by the silhouette are holes.
    """
    solid = alpha > threshold
    h, w = solid.shape
    outside = np.zeros_like(solid, dtype=bool)
    stack: list[tuple[int, int]] = []
    for x in range(w):
        if not solid[0, x]:
            stack.append((0, x))
        if not solid[h - 1, x]:
            stack.append((h - 1, x))
    for y in range(h):
        if not solid[y, 0]:
            stack.append((y, 0))
        if not solid[y, w - 1]:
            stack.append((y, w - 1))

    while stack:
        y, x = stack.pop()
        if outside[y, x] or solid[y, x]:
            continue
        outside[y, x] = True
        if y > 0:
            stack.append((y - 1, x))
        if y + 1 < h:
            stack.append((y + 1, x))
        if x > 0:
            stack.append((y, x - 1))
        if x + 1 < w:
            stack.append((y, x + 1))

    holes = (~solid) & (~outside)
    filled = solid | holes
    return int(solid.sum()), int(holes.sum()), int(filled.sum())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frames on the 208x208 pivot grid.")
    parser.add_argument("input", help="directory with PNG frames")
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--cx", type=float, default=104.0)
    parser.add_argument("--bottom", type=float, default=155.0)
    parser.add_argument("--tol", type=float, default=2.0, help="allowed pivot deviation, px")
    parser.add_argument("--alpha", type=int, default=10)
    parser.add_argument("--key", default="0000FF")
    parser.add_argument("--blue-max-pct", type=float, default=0.5, help="max blue residue, %% of opaque")
    parser.add_argument("--fill-min-pct", type=float, default=99.0, help="min opaque fill of silhouette, %%")
    parser.add_argument("--holes-max-pct", type=float, default=0.5, help="max enclosed transparent holes, %%")
    args = parser.parse_args()

    src_dir = Path(args.input)
    files = sorted(
        p for p in src_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTS
        and not p.stem.lower().startswith(("contact_sheet", "sheet"))
    )
    if not files:
        parser.error(f"no frame PNG/WebP in {src_dir}")

    key = parse_hex(args.key)
    rows = []
    failed = 0
    for src in files:
        img = np.array(Image.open(src).convert("RGBA"), dtype=np.int16)
        alpha = img[:, :, 3]
        ys, xs = np.nonzero(alpha > args.alpha)
        if len(xs) == 0:
            rows.append((src.name, "EMPTY", "-", "-", "-", "-", "-", "-", "FAIL"))
            failed += 1
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        cx = (x0 + x1 + 1) / 2.0
        bottom = y1 + 1
        edge = int(((alpha[0, :] > args.alpha).sum() + (alpha[-1, :] > args.alpha).sum()
                    + (alpha[:, 0] > args.alpha).sum() + (alpha[:, -1] > args.alpha).sum()))
        opaque, holes, filled = hole_stats(alpha, args.alpha)
        fill_pct = 100.0 * opaque / max(1, filled)
        hole_pct = 100.0 * holes / max(1, filled)
        r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
        blue = (alpha > 20) & (b > r + 30) & (b > g + 30) & (b > 100)
        blue_count = int(blue.sum())
        blue_pct = 100.0 * blue_count / max(1, opaque)
        ok = (
            abs(cx - args.cx) <= args.tol
            and abs(bottom - args.bottom) <= args.tol
            and edge == 0
            and x0 > 0 and y0 > 0 and x1 < args.size - 1 and y1 < args.size - 1
            and blue_pct <= args.blue_max_pct
            and fill_pct >= args.fill_min_pct
            and hole_pct <= args.holes_max_pct
        )
        if not ok:
            failed += 1
        rows.append((src.name, f"{x0},{y0},{x1},{y1}", f"{cx:.1f}", str(bottom),
                     str(edge), f"{fill_pct:.2f}%", f"{hole_pct:.2f}%",
                     f"{blue_pct:.2f}%", "OK" if ok else "FAIL"))

    headers = ("file", "bbox", "cx", "bottom", "edge", "fill", "holes", "blue", "verdict")
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))
    print(f"\n{len(rows) - failed}/{len(rows)} OK, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
