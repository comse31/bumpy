#!/usr/bin/env python3
"""Build Bumpy v8 atlas (519 frames, 23 clips) + Lua clip manifest."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bumpy_anim_v8"
OUT = ROOT / "main" / "bumpy_v8"


def main() -> int:
    data = json.loads((SRC / "animations.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    frames_root = OUT / "frames"
    if frames_root.exists():
        shutil.rmtree(frames_root)
    frames_root.mkdir()
    images, animations = [], []
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
            rel = f"/main/bumpy_v8/frames/{name}/{src.name}"
            images.append(rel)
            anim_images.append(rel)
        animations.append((name, anim_images))
        total += frames

    lines = ["margin: 0", "extrude_borders: 2", "inner_padding: 0"]
    for path in images:
        lines.append(f'images {{\n  image: "{path}"\n  sprite_trim_mode: SPRITE_TRIM_MODE_OFF\n}}')
    for name, paths in animations:
        lines.append(f'animations {{\n  id: "{name}"')
        for path in paths:
            lines.append(f'  images {{\n    image: "{path}"\n  }}')
        lines.append('}')
    (OUT / "bumpy_v8.atlas").write_text("\n".join(lines) + "\n", encoding="utf-8")

    clip_lines = ["return {"]
    for name, meta in data.items():
        fs = meta.get("frame_size", [160, 160])
        pivot = meta.get("pivot", [80.0, 119.2])
        clip_lines.append(
            '    { name = "%s", frames = %d, duration_sec = %.6f, loop = %s, hold_last_frame = %s, contact = "%s", frame_w = %d, frame_h = %d, pivot_x = %.3f, pivot_y = %.3f, ball_diameter = %.3f },'
            % (
                name, int(meta["frames"]), float(meta["duration_sec"]),
                "true" if meta.get("loop") else "false",
                "true" if meta.get("hold_last_frame") else "false",
                meta.get("contact", "bottom"), int(fs[0]), int(fs[1]),
                float(pivot[0]), float(pivot[1]), float(meta.get("ball_diameter_px", 80.0)),
            )
        )
    clip_lines.append("}")
    (OUT / "bumpy_v8_clips.lua").write_text("\n".join(clip_lines) + "\n", encoding="utf-8")
    print(f"v8 atlas: {total} images, {len(animations)} animations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
