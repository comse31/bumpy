#!/usr/bin/env python3
"""Method A: build procedural pose ladders (rise/fall/sq/tm/wl/wr) from one approved Bumpy image."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chroma_key import key_image, parse_hex  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
NAMES = (["rest"] + [f"rise{i}" for i in range(1, 4)] + [f"fall{i}" for i in range(1, 5)]
         + [f"sq{i}" for i in range(1, 7)] + [f"tm{i}" for i in range(1, 3)]
         + [f"wl{i}" for i in range(1, 5)] + [f"wr{i}" for i in range(1, 5)])


def alpha_bbox(image: Image.Image, threshold: int = 8):
    a = np.array(image.convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(a > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def prepare_base(source: Image.Image, size: int, content: int, cx: int, bottom: int) -> Image.Image:
    img = source.convert("RGBA")
    a = np.array(img)[:, :, 3]
    if a.max() <= 8:
        raise SystemExit("source is fully transparent")
    if a.min() > 250:  # RGB/JPG with no real alpha
        img = key_image(img, parse_hex("0000FF"), 40.0, 40.0, True)
    box = alpha_bbox(img)
    if box is None:
        raise SystemExit("source has no opaque content")
    crop = img.crop(box)
    scale = content / max(1, crop.height)
    w = max(1, round(crop.width * scale))
    h = max(1, round(crop.height * scale))
    crop = crop.resize((w, h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(crop, (cx - w // 2, bottom - h))
    return canvas


def bilinear(image: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x0 = np.floor(u).astype(np.int32)
    y0 = np.floor(v).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    wx = (u - x0)[..., None]
    wy = (v - y0)[..., None]
    valid = (x0 >= 0) & (y0 >= 0) & (x1 < w) & (y1 < h)
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x1, 0, w - 1)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y1, 0, h - 1)
    top = image[y0c, x0c] * (1 - wx) + image[y0c, x1c] * wx
    bot = image[y1c, x0c] * (1 - wx) + image[y1c, x1c] * wx
    out = top * (1 - wy) + bot * wy
    out[~valid] = 0
    return out


def warp(base: Image.Image, sy: float, sx: float = 1.0, taper: float = 0.0,
         cx: int = 104, bottom: int = 155, content: int = 104) -> Image.Image:
    src = np.array(base, dtype=np.float32)
    size = base.width
    yy, xx = np.mgrid[0:size, 0:size]
    v = bottom + (yy - bottom) / max(sy, 1e-6)
    t = np.clip((bottom - yy) / max(1.0, content * sy), 0.0, 1.0)
    fx = 1.0 - taper * np.power(t, 1.3)
    u = cx + (xx - cx) / np.maximum(sx * fx, 1e-6)
    out = bilinear(src, u.astype(np.float32), v.astype(np.float32))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def rotate_frame(base: Image.Image, angle: float) -> Image.Image:
    return base.rotate(angle, resample=Image.Resampling.BICUBIC, center=(base.width / 2, base.height / 2))


def anchor_bottom(image: Image.Image, bottom: int = 155) -> Image.Image:
    """Shift a frame vertically so its alpha bbox bottom lands on the pivot line."""
    a = np.array(image)[:, :, 3]
    ys, _ = np.nonzero(a > 8)
    if len(ys) == 0:
        return image
    dy = bottom - (int(ys.max()) + 1)
    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    canvas.alpha_composite(image, (0, dy))
    return canvas


def build_set(base: Image.Image, flipped: bool = False) -> dict[str, Image.Image]:
    frames: dict[str, Image.Image] = {"rest": base}

    for i, (sy, sx) in enumerate([(1.12, 0.97), (1.25, 0.92), (1.38, 0.86)], start=1):
        frames[f"rise{i}"] = warp(base, sy, sx, taper=0.45)
    for i, (sy, sx) in enumerate([(1.10, 0.97), (1.22, 0.92), (1.34, 0.86), (1.46, 0.80)], start=1):
        frames[f"fall{i}"] = warp(base, sy, sx, taper=0.55)
    for i, (sy, sx) in enumerate([(0.85, 1.12), (0.76, 1.20), (0.67, 1.28),
                                  (0.58, 1.36), (0.50, 1.44), (0.44, 1.52)], start=1):
        frames[f"sq{i}"] = warp(base, sy, sx, taper=0.0)
    for i, angle in enumerate((-35.0, -75.0), start=1):
        frames[f"tm{i}"] = rotate_frame(base, angle)
    for i, angle in enumerate((-20.0, -40.0, -60.0, -80.0), start=1):
        frames[f"wl{i}"] = rotate_frame(base, angle)
    for i, angle in enumerate((20.0, 40.0, 60.0, 80.0), start=1):
        frames[f"wr{i}"] = rotate_frame(base, angle)

    if flipped:
        # Placeholder: geometric 180-degree turn. A true f-set needs a separate
        # upside-down face source; the pilot will show if this is acceptable.
        # Anchor the bbox bottom to the same pivot line so validation/pivots match.
        frames = {name: anchor_bottom(img.rotate(180), 155) for name, img in frames.items()}
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description="Build method A pose ladders from one image.")
    parser.add_argument("source", help="bumpy_clean.png/jpg")
    parser.add_argument("output", help="output directory, e.g. art_inbox/03_hero_anim/A")
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--content", type=int, default=104)
    parser.add_argument("--cx", type=int, default=104)
    parser.add_argument("--bottom", type=int, default=155)
    parser.add_argument("--sets", default="u,f", help="u, f or u,f")
    args = parser.parse_args()

    source = Image.open(args.source)
    base = prepare_base(source, args.size, args.content, args.cx, args.bottom)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    sets = {s.strip().lower() for s in args.sets.split(",") if s.strip()}
    count = 0
    for set_name in ("u", "f"):
        if set_name not in sets:
            continue
        frames = build_set(base, flipped=(set_name == "f"))
        for name in NAMES:
            frames[name].save(out / f"{set_name}_{name}.png")
            count += 1
    print(f"built {count} frames -> {out}")
    if "f" in sets:
        print("NOTE: f_* is a geometric 180-turn placeholder until an upside-down face source exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
