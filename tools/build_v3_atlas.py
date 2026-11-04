#!/usr/bin/env python3
"""Build the Bumpy v3 atlas (477 frames, 22 clips) + Lua clip manifest."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bumpy_anim_v3"
OUT = ROOT / "main" / "bumpy_v3"


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
            rel = f"/main/bumpy_v3/frames/{name}/{src.name}"
            images.append(rel)
            anim_images.append(rel)
        animations.append((name, anim_images))
        clip_lines.append(
            "    { name = \"%s\", frames = %d, duration_sec = %.6f, fps = %d, "
            "loop = %s, hold_last_frame = %s, physics_bound = %s, contact = \"%s\" },"
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
    (OUT / "bumpy_v3_clips.lua").write_text("\n".join(clip_lines) + "\n", encoding="utf-8")

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
    (OUT / "bumpy_v3.atlas").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"v3 atlas: {total} images, {len(animations)} animations, {len(data)} clips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
