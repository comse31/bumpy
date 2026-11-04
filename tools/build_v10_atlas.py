#!/usr/bin/env python3
"""Build the Bumpy v10 atlas (607 frames, 25 clips, phi per frame) + fx atlas."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bumpy_anim_v10"
OUT = ROOT / "main" / "bumpy_v10"


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
        phi = meta.get("phi_deg") or []
        if len(phi) != frames:
            raise SystemExit(f"{name}: phi len {len(phi)} != frames {frames}")
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
            rel = f"/main/bumpy_v10/frames/{name}/{src.name}"
            images.append(rel)
            anim_images.append(rel)
        animations.append((name, anim_images))
        phi_text = ", ".join("%.1f" % float(v) for v in phi)
        clip_lines.append(
            "    { name = \"%s\", frames = %d, duration_sec = %.6f, fps = %d, "
            "loop = %s, hold_last_frame = %s, physics_bound = %s, contact = \"%s\", "
            "phi = { %s } },"
            % (
                name,
                int(meta["frames"]),
                float(meta["duration_sec"]),
                int(meta.get("fps", 30)),
                "true" if meta.get("loop") else "false",
                "true" if meta.get("hold_last_frame") else "false",
                "true" if meta.get("physics_bound") else "false",
                meta.get("contact", "bottom"),
                phi_text,
            )
        )
        total += frames
    clip_lines.append("}")
    (OUT / "bumpy_v10_clips.lua").write_text("\n".join(clip_lines) + "\n", encoding="utf-8")

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
    (OUT / "bumpy_v10.atlas").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fx_src = SRC / "fx"
    fx_dst = OUT / "fx"
    if fx_dst.exists():
        shutil.rmtree(fx_dst)
    fx_dst.mkdir()
    fx_files = sorted(fx_src.glob("shadow_*.png"), key=lambda p: int(p.stem.split("_")[1]))
    fx_lines = ["margin: 0", "extrude_borders: 2", "inner_padding: 0"]
    for src in fx_files:
        shutil.copyfile(src, fx_dst / src.name)
        fx_lines.append(
            f'images {{\n  image: "/main/bumpy_v10/fx/{src.name}"\n'
            f"  sprite_trim_mode: SPRITE_TRIM_MODE_OFF\n}}"
        )
    (OUT / "bumpy_v10_fx.atlas").write_text("\n".join(fx_lines) + "\n", encoding="utf-8")

    print(f"v10 atlas: {total} images, {len(animations)} animations, phi per frame")
    print(f"fx atlas: {len(fx_files)} levels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
