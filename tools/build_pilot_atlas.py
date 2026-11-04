#!/usr/bin/env python3
"""Build the Bumpy pilot atlas + clip manifest from bumpy_anim_pilot/animations.json."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bumpy_anim_pilot"
OUT = ROOT / "main" / "bumpy_pilot"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-page", type=int, default=4096)
    args = parser.parse_args()
    data = json.loads((SRC / "animations.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    frames_root = OUT / "frames"
    if frames_root.exists():
        shutil.rmtree(frames_root)
    frames_root.mkdir()

    images = []
    animations = []
    clips = []
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
                raise SystemExit(f"{name}: unexpected frame {src.name}, expected {expected}")
            dst = dst_dir / src.name
            shutil.copyfile(src, dst)
            rel = f"/main/bumpy_pilot/frames/{name}/{src.name}"
            images.append(rel)
            anim_images.append(rel)
        animations.append((name, anim_images))
        clips.append({
            "name": name,
            "frames": frames,
            "fps": int(meta["fps"]),
            "loop": bool(meta["loop"]),
            "pivot_x": 104,
            "pivot_y": 155,
        })
        total += frames

    lines = [
        f'margin: 0',
        f'extrude_borders: 2',
        f'inner_padding: 0',
    ]
    for path in images:
        lines.append(f'images {{\n  image: "{path}"\n  sprite_trim_mode: SPRITE_TRIM_MODE_OFF\n}}')
    for name, paths in animations:
        lines.append(f'animations {{\n  id: "{name}"')
        for path in paths:
            lines.append(f'  images {{\n    image: "{path}"\n  }}')
        lines.append('}')
    (OUT / "bumpy_pilot.atlas").write_text("\n".join(lines) + "\n", encoding="utf-8")

    clip_lines = ["return {"]
    for c in clips:
        loop = "true" if c["loop"] else "false"
        clip_lines.append(
            '    { name = "%s", frames = %d, fps = %d, loop = %s, pivot_x = %d, pivot_y = %d },'
            % (c["name"], c["frames"], c["fps"], loop, c["pivot_x"], c["pivot_y"])
        )
    clip_lines.append("}")
    (OUT / "pilot_clips.lua").write_text("\n".join(clip_lines) + "\n", encoding="utf-8")
    print(f"pilot atlas: {total} images, {len(animations)} animations, max_page={args.max_page}")
    for name, paths in animations:
        print(f"  {name}: {len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
