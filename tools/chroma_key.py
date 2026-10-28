#!/usr/bin/env python3
"""Remove a per-cell chroma background sampled from the four cell corners.

The default key is auto: each grid cell gets its own background model (bilinear
between corner medians), so different blue shades in one sheet are handled.
Soft alpha edge + un-premultiply despill are applied per pixel.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def parse_hex(value: str) -> np.ndarray:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("key must be RRGGBB")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _cell_bounds(width: int, height: int, cols: int, rows: int, col: int, row: int):
    x0 = round(col * width / cols)
    x1 = round((col + 1) * width / cols)
    y0 = round(row * height / rows)
    y1 = round((row + 1) * height / rows)
    return x0, y0, x1, y1


def _corner_color(cell: np.ndarray, x: int, y: int, patch: int) -> np.ndarray:
    h, w = cell.shape[:2]
    x0 = max(0, min(w - patch, x))
    y0 = max(0, min(h - patch, y))
    patch_px = cell[y0:y0 + patch, x0:x0 + patch, :3].reshape(-1, 3)
    return np.median(patch_px, axis=0)


def cell_background(cell: np.ndarray) -> np.ndarray:
    """Bilinear background from four robust corner colors."""
    h, w = cell.shape[:2]
    inset = max(2, int(min(h, w) * 0.05))
    patch = max(2, int(min(h, w) * 0.05))
    corners = np.stack([
        _corner_color(cell, inset, inset, patch),
        _corner_color(cell, w - inset - patch, inset, patch),
        _corner_color(cell, inset, h - inset - patch, patch),
        _corner_color(cell, w - inset - patch, h - inset - patch, patch),
    ])
    med = np.median(corners, axis=0)
    # If a corner is the character, replace it by the robust median.
    for i in range(4):
        if np.linalg.norm(corners[i] - med) > 80:
            corners[i] = med
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx + 0.5) / max(1, w)
    v = (yy + 0.5) / max(1, h)
    top = corners[0][None, None, :] * (1 - u[..., None]) + corners[1][None, None, :] * u[..., None]
    bot = corners[2][None, None, :] * (1 - u[..., None]) + corners[3][None, None, :] * u[..., None]
    return top * (1 - v[..., None]) + bot * v[..., None]


def key_cell(cell: np.ndarray, key: np.ndarray | None, tol: float, soft: float,
             despill: bool) -> np.ndarray:
    rgb = cell[:, :, :3].astype(np.float32)
    src_a = cell[:, :, 3].astype(np.float32) / 255.0
    bg = cell_background(cell) if key is None else np.broadcast_to(key, rgb.shape)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    alpha = np.clip((dist - tol) / max(soft, 1.0), 0.0, 1.0)
    alpha = np.minimum(alpha, src_a)

    if despill:
        # Un-premultiply the key contribution on soft edges.
        a = np.maximum(alpha, 0.03)[..., None]
        fg = (rgb - (1.0 - alpha[..., None]) * bg) / a
        edge = (alpha > 0.03) & (alpha < 0.995)
        rgb = np.where(edge[..., None], fg, rgb)
        # Remove a blue rim when the cell key itself is blue-dominant.
        key_blue = (bg[:, :, 2] > bg[:, :, 0] + 20) & (bg[:, :, 2] > bg[:, :, 1] + 20)
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        spill = key_blue & (alpha > 0.05) & (b > r + 5) & (b > g + 5)
        rgb[:, :, 2] = np.where(spill, np.maximum(r, g), b)

    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255.0, 0, 255)])
    return out.astype(np.uint8)


def key_sheet(image: Image.Image, cols: int = 1, rows: int = 1,
              key_mode: str = "auto", tol: float = 30.0, soft: float = 45.0,
              despill: bool = True) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    if key_mode == "none":
        return image.convert("RGBA")
    # A PNG/WebP with a real alpha channel is treated as already cut out.
    if key_mode == "auto" and rgba[:, :, 3].min() < 250:
        return image.convert("RGBA")
    key = None if key_mode == "auto" else parse_hex(key_mode)
    h, w = rgba.shape[:2]
    out = rgba.copy()
    for r in range(rows):
        for c in range(cols):
            x0, y0, x1, y1 = _cell_bounds(w, h, cols, rows, c, r)
            cell = rgba[y0:y1, x0:x1]
            out[y0:y1, x0:x1] = key_cell(cell, key, tol, soft, despill)
    return Image.fromarray(out, "RGBA")


def process_file(src: Path, dst: Path, cols: int, rows: int, key_mode: str,
                 tol: float, soft: float, despill: bool) -> None:
    image = Image.open(src)
    result = key_sheet(image, cols, rows, key_mode, tol, soft, despill)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result.save(dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-cell chroma key with corner background sampling.")
    parser.add_argument("inputs", nargs="+", help="files or directories")
    parser.add_argument("-o", "--out", help="output directory (or file for one input)")
    parser.add_argument("--cols", type=int, default=1, help="grid columns (1 for a single image)")
    parser.add_argument("--rows", type=int, default=1, help="grid rows")
    parser.add_argument("--key", default="auto", help="auto or RRGGBB (fixed key)")
    parser.add_argument("--tol", type=float, default=30.0, help="fully transparent distance")
    parser.add_argument("--soft", type=float, default=45.0, help="soft edge width")
    parser.add_argument("--no-despill", action="store_true")
    args = parser.parse_args()
    if args.cols < 1 or args.rows < 1:
        parser.error("--cols/--rows must be >= 1")

    inputs: list[Path] = []
    for raw in args.inputs:
        path = Path(raw)
        if path.is_dir():
            inputs.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS))
        elif path.is_file():
            inputs.append(path)
        else:
            parser.error(f"not found: {path}")
    if not inputs:
        parser.error("no input images")

    out = Path(args.out) if args.out else None
    if out is None:
        if len(inputs) == 1:
            out = inputs[0].with_name(inputs[0].stem + "_keyed.png")
        else:
            out = inputs[0].parent.with_name(inputs[0].parent.name + "_keyed")

    if len(inputs) == 1 and out.suffix.lower() in IMAGE_EXTS:
        process_file(inputs[0], out, args.cols, args.rows, args.key, args.tol, args.soft, not args.no_despill)
        print(f"keyed: {inputs[0]} -> {out}")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for src in inputs:
        process_file(src, out / (src.stem + ".png"), args.cols, args.rows, args.key,
                     args.tol, args.soft, not args.no_despill)
    print(f"keyed {len(inputs)} image(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
