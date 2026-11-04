#!/usr/bin/env python3
"""Export a PNG frame folder as 48 px and 96 px GIFs (composited on a neutral grey)."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".webp"}


def parse_rgb(value: str) -> tuple[int, int, int]:
    parts = [int(v.strip()) for v in value.split(",")]
    if len(parts) != 3:
        raise ValueError("bg must be R,G,B")
    return tuple(parts)


def composite(frame: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    rgba = frame.convert("RGBA")
    arr = np.array(rgba, dtype=np.float32)
    a = arr[:, :, 3:4] / 255.0
    rgb = arr[:, :, :3] * a + np.array(bg, dtype=np.float32) * (1.0 - a)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def export_gif(frames: list[Image.Image], output: Path, sizes: list[int],
               fps: int = 24, bg: tuple[int, int, int] = (200, 205, 215)) -> list[Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    duration = max(20, round(1000 / max(1, fps)))
    for size in sizes:
        prepared = []
        for frame in frames:
            prepared.append(composite(frame, bg).resize((size, size), Image.Resampling.LANCZOS))
        if not prepared:
            continue
        path = output.with_name(f"{output.stem}_{size}.gif")
        prepared[0].save(
            path,
            save_all=True,
            append_images=prepared[1:],
            duration=duration,
            loop=0,
            disposal=2,
            optimize=False,
        )
        made.append(path)
    return made


def main() -> int:
    parser = argparse.ArgumentParser(description="Export frame folder to 48/96 px GIFs.")
    parser.add_argument("input", help="directory with PNG frames")
    parser.add_argument("output", help="output directory")
    parser.add_argument("--name", help="base name (default: input directory name)")
    parser.add_argument("--sizes", default="48,96")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--bg", default="200,205,215")
    args = parser.parse_args()

    src = Path(args.input)
    files = sorted(
        p for p in src.iterdir()
        if p.suffix.lower() in IMAGE_EXTS and not p.stem.lower().startswith(("contact_sheet", "sheet"))
    )
    if not files:
        parser.error(f"no frames in {src}")
    frames = [Image.open(p).convert("RGBA") for p in files]
    sizes = [int(v.strip()) for v in args.sizes.split(",") if v.strip()]
    name = args.name or src.name
    made = export_gif(frames, Path(args.output) / name, sizes, args.fps, parse_rgb(args.bg))
    for path in made:
        print(f"gif: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
