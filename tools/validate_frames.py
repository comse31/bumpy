#!/usr/bin/env python3
"""Validate Bumpy frames: pivot/edge, holes/fill, bottom span, repeated neighbours."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".webp"}
BG = np.array([200, 205, 215], dtype=np.float32)


def parse_hex(value: str) -> np.ndarray:
    value = value.strip().lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)


def hole_stats(alpha: np.ndarray, threshold: int) -> tuple[int, int, int]:
    """Opaque, enclosed-hole and filled-silhouette pixel counts."""
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


def composite(img: np.ndarray) -> np.ndarray:
    a = img[:, :, 3:4].astype(np.float32) / 255.0
    return img[:, :, :3].astype(np.float32) * a + BG * (1.0 - a)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frames on the 208x208 pivot grid.")
    parser.add_argument("input", help="directory with PNG frames")
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--cx", type=float, default=104.0)
    parser.add_argument("--bottom", type=float, default=155.0)
    parser.add_argument("--tol", type=float, default=2.0, help="allowed pivot deviation, px")
    parser.add_argument("--bottom-span-max", type=float, default=1.0,
                        help="max difference between lowest and highest bottom across frames")
    parser.add_argument("--alpha", type=int, default=10)
    parser.add_argument("--key", default="0000FF")
    parser.add_argument("--blue-max-pct", type=float, default=0.5)
    parser.add_argument("--fill-min-pct", type=float, default=99.0)
    parser.add_argument("--holes-max-pct", type=float, default=0.5)
    parser.add_argument("--repeat-diff-pct", type=float, default=0.5,
                        help="neighbour mean RGB difference below this = repeated frame")
    parser.add_argument("--skip-bottom", action="store_true",
                        help="skip per-frame bottom and bottom-span checks for airborne runs")
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
    bottoms: list[float] = []
    prev_comp = None
    prev_area = 0

    for src in files:
        img = np.array(Image.open(src).convert("RGBA"), dtype=np.int16)
        if img.shape[0] != args.size or img.shape[1] != args.size:
            rows.append((src.name, f"size={img.shape[1]}x{img.shape[0]}", "-", "-", "-", "-", "-", "-", "-", "-", "-", "FAIL"))
            failed += 1
            prev_comp = None
            prev_area = 0
            continue
        alpha = img[:, :, 3]
        ys, xs = np.nonzero(alpha > args.alpha)
        if len(xs) == 0:
            rows.append((src.name, "EMPTY", "-", "-", "-", "-", "-", "-", "-", "-", "-", "FAIL"))
            failed += 1
            prev_comp = None
            prev_area = 0
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        cx = (x0 + x1 + 1) / 2.0
        bottom = y1 + 1
        bottoms.append(bottom)
        edge = int(((alpha[0, :] > args.alpha).sum() + (alpha[-1, :] > args.alpha).sum()
                    + (alpha[:, 0] > args.alpha).sum() + (alpha[:, -1] > args.alpha).sum()))
        opaque, holes, filled = hole_stats(alpha, args.alpha)
        fill_pct = 100.0 * opaque / max(1, filled)
        hole_pct = 100.0 * holes / max(1, filled)
        area = opaque
        area_delta = 100.0 * abs(area - prev_area) / max(1, prev_area) if prev_area else float("nan")
        comp = composite(img)
        diff_pct = 100.0 * float(np.abs(comp - prev_comp).mean()) / 255.0 if prev_comp is not None else float("nan")
        repeat = prev_comp is not None and diff_pct < args.repeat_diff_pct
        r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
        blue = (alpha > 20) & (b > r + 30) & (b > g + 30) & (b > 100)
        blue_pct = 100.0 * int(blue.sum()) / max(1, opaque)
        other_ok = (
            abs(cx - args.cx) <= args.tol
            and (args.skip_bottom or abs(bottom - args.bottom) <= args.tol)
            and edge == 0
            and x0 > 0 and y0 > 0 and x1 < args.size - 1 and y1 < args.size - 1
            and blue_pct <= args.blue_max_pct
            and fill_pct >= args.fill_min_pct
            and hole_pct <= args.holes_max_pct
        )
        if not other_ok or repeat:
            failed += 1
        verdict = "FAIL" if not other_ok else ("REPEAT" if repeat else "OK")
        rows.append((
            src.name,
            f"{x0},{y0},{x1},{y1}",
            f"{cx:.1f}",
            str(bottom),
            str(edge),
            f"{fill_pct:.2f}%",
            f"{hole_pct:.2f}%",
            str(area),
            "-" if np.isnan(area_delta) else f"{area_delta:.1f}%",
            "-" if np.isnan(diff_pct) else f"{diff_pct:.2f}%",
            f"{blue_pct:.2f}%",
            verdict,
        ))
        prev_comp = comp
        prev_area = area

    headers = ("file", "bbox", "cx", "bottom", "edge", "fill", "holes",
               "area", "dArea", "diff", "blue", "verdict")
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))

    span = (max(bottoms) - min(bottoms)) if bottoms else 0.0
    span_ok = args.skip_bottom or span <= args.bottom_span_max
    if not span_ok:
        failed += 1
    if args.skip_bottom:
        print("\nbottom span: skipped (airborne run)")
    else:
        print(f"\nbottom span: {span:.0f} px (max {args.bottom_span_max:g}) {'OK' if span_ok else 'FAIL'}")
    print(f"{len(rows) - failed}/{len(rows)} OK, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
