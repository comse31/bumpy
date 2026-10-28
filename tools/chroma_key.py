#!/usr/bin/env python3
"""Remove a flat chroma-key background (default pure blue #0000FF) with soft edge and despill."""
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


def key_image(image: Image.Image, key: np.ndarray, tol: float, soft: float, despill: bool) -> Image.Image:
    rgba = np.array(image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[:, :, :3]
    src_alpha = rgba[:, :, 3] / 255.0
    dist = np.sqrt(((rgb - key) ** 2).sum(axis=2))
    if soft <= 0:
        alpha = (dist > tol).astype(np.float32)
    else:
        alpha = np.clip((dist - tol) / soft, 0.0, 1.0)
    alpha = np.minimum(alpha, src_alpha)

    if despill:
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        # Despill all visible blue-dominant pixels, including a blue rim that is
        # already fully opaque in the source. Green eyes/brown hair are unaffected.
        spill = (alpha > 0.05) & (b > r + 5) & (b > g + 5)
        rgb[:, :, 2] = np.where(spill, np.maximum(r, g), b)

    rgba[:, :, :3] = np.clip(rgb, 0, 255)
    rgba[:, :, 3] = np.clip(alpha * 255.0, 0, 255)
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def process_file(src: Path, dst: Path, key: np.ndarray, tol: float, soft: float, despill: bool) -> None:
    image = Image.open(src)
    result = key_image(image, key, tol, soft, despill)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result.save(dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chroma key PNG/JPG to transparent RGBA.")
    parser.add_argument("inputs", nargs="+", help="files or directories")
    parser.add_argument("-o", "--out", help="output directory (or file for one input)")
    parser.add_argument("--key", default="0000FF", help="RRGGBB key color, default 0000FF")
    parser.add_argument("--tol", type=float, default=40.0, help="fully transparent distance")
    parser.add_argument("--soft", type=float, default=40.0, help="soft edge width in RGB distance")
    parser.add_argument("--no-despill", action="store_true", help="disable edge despill")
    args = parser.parse_args()

    key = parse_hex(args.key)
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
        process_file(inputs[0], out, key, args.tol, args.soft, not args.no_despill)
        print(f"keyed: {inputs[0]} -> {out}")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for src in inputs:
        dst = out / (src.stem + ".png")
        process_file(src, dst, key, args.tol, args.soft, not args.no_despill)
    print(f"keyed {len(inputs)} image(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
