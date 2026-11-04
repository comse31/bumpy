#!/usr/bin/env python3
"""Build the Bumpy v9 atlas (559 frames, 21 clips) + fx atlas + Lua clips."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bumpy_anim_v9"
OUT = ROOT / "main" / "bumpy_v9"


def main() -> int:
    data = json.loads((SRC / "animations.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    frames_root = OUT / "frames"
    if frames_root.exists():
        shutil.rmtree(frames_root)
    frames_root.mkdir()

    images = []
    animations = []
    clip_lines = ["return {"]
    total = 0
    for name, meta in data.items():
        frames = int(meta["frames"])
        src_dir = SRC / "frames" / name
        dst_dir = frames_root / name
        dst_dir.mkdir(parents=True)
        src_files = sorted(src_dir.glob(f"{name}_*.png"))
        if len(src_files) != frames:
            raise SystemExit(f"{name}: expected {frames}, found {len(src_files)}")
        anim_images = []
        for index, src in enumerate(src_files, start=1):
            expected = f"{name}_{index:02d}.png"
            if src.name != expected:
                raise SystemExit(f"{name}: unexpected {src.name}, expected {expected}")
            dst = dst_dir / src.name
            shutil.copyfile(src, dst)
            rel = f"/main/bumpy_v9/frames/{name}/{src.name}"
            images.append(rel)
            anim_images.append(rel)
        animations.append((name, anim_images))
        clip_lines.append(
            "    { name = \"%s\", frames = %d, duration_sec = %.6f, fps = %d, "
            "loop = %s, hold_last_frame = %s, physics_bound = %s, contact = \"%s\", "
            "frame_w = 144, frame_h = 144, pivot_x = 72.000, pivot_y = 107.300, "
            "ball_diameter = 72.000 },"
            % (
                name,
                int(meta["frames"]),
                float(meta["duration_sec"]),
                int(meta.get("fps", 30)),
                "true" if meta.get("loop") else "false",
                "true" if meta.get("hold_last_frame") else "false",
                "true" if meta.get("physics_bound") else "false",
                meta.get("contact", "bottom"),
            )
        )
        total += frames
    clip_lines.append("}")
    (OUT / "bumpy_v9_clips.lua").write_text("\n".join(clip_lines) + "\n", encoding="utf-8")

    lines = ["margin: 0", "extrude_borders: 2", "inner_padding: 0"]
    for path in images:
        lines.append(
            f'images {{\n  image: "{path}"\n  sprite_trim_mode: SPRITE_TRIM_MODE_OFF\n}}'
        )
    for name, paths in animations:
        lines.append(f'animations {{\n  id: "{name}"')
        for path in paths:
            lines.append(f'  images {{\n    image: "{path}"\n  }}')
        lines.append("}")
    (OUT / "bumpy_v9.atlas").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fx_src = SRC / "fx"
    fx_dst = OUT / "fx"
    if fx_dst.exists():
        shutil.rmtree(fx_dst)
    fx_dst.mkdir()
    fx_lines = ["margin: 0", "extrude_borders: 2", "inner_padding: 0"]
    for src in sorted(fx_src.glob("*.png")):
        shutil.copyfile(src, fx_dst / src.name)
        fx_lines.append(
            f'images {{\n  image: "/main/bumpy_v9/fx/{src.name}"\n'
            f"  sprite_trim_mode: SPRITE_TRIM_MODE_OFF\n}}"
        )
    (OUT / "bumpy_v9_fx.atlas").write_text("\n".join(fx_lines) + "\n", encoding="utf-8")

    print(f"v9 atlas: {total} images, {len(animations)} animations")
    print(f"fx atlas: {len(list(fx_src.glob('*.png')))} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
