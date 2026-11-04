#!/usr/bin/env python3
"""Check P1 pilot assets: 180 PNG frames and 15 atlas animations."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", default=str(ROOT / "main" / "bumpy_pilot" / "frames"))
    parser.add_argument("--atlas", default=str(ROOT / "main" / "bumpy_pilot" / "bumpy_pilot.atlas"))
    args = parser.parse_args()

    frames = sorted(Path(args.frames).rglob("*.png"))
    atlas = Path(args.atlas).read_text(encoding="utf-8")
    anims = re.findall(r'animations \{\s*id:\s*"([^"]+)"', atlas)
    print(f"frames: {len(frames)}")
    print(f"animations: {len(anims)}")
    print("ids:", ", ".join(anims))
    ok = len(frames) == 180 and len(anims) == 15 and len(set(anims)) == 15
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
