#!/usr/bin/env python3
"""Deterministic Bumpy deformation renderer with face crossfades and GIF export.

Reads animations.json, maps key indices to an output frame timeline, interpolates
numeric parameters with smoothstep, crossfades face textures over two frames, and
renders 208x208 premultiplied RGBA frames at 2x before downsampling.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chroma_key import key_sheet  # noqa: E402
from export_gif import export_gif, parse_rgb  # noqa: E402

NUM_KEYS = ("phi", "psi", "k", "wmin", "tip", "a0", "sy", "sytop", "pa", "bulge", "shear")


def sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Renderer:
    def __init__(self, base_path: Path, scale: int, size: int, content: int, bottom: int):
        self.scale = scale
        self.size = size
        self.content = content
        self.bottom = bottom
        self.cw = size * scale
        self.ch = size * scale
        self.yb = bottom * scale
        self.xc = self.cw // 2
        self.base = self._load_base(base_path)

    def _load_base(self, path: Path) -> np.ndarray:
        image = Image.open(path)
        image = key_sheet(image, 1, 1, "auto", 30.0, 45.0, True)
        rgba = np.array(image, dtype=np.float32)
        a = rgba[:, :, 3]
        ys, xs = np.nonzero(a > 8)
        if len(xs) == 0:
            raise SystemExit(f"base has no alpha: {path}")
        crop = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = crop.shape[:2]
        target_h = self.content * self.scale
        sc = target_h / max(1, h)
        nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
        crop = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((self.ch, self.cw, 4), dtype=np.float32)
        x, y = self.xc - nw // 2, self.yb - nh
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.cw, x + nw), min(self.ch, y + nh)
        sx0, sy0 = max(0, -x), max(0, -y)
        canvas[y0:y1, x0:x1] = crop[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        alpha = canvas[:, :, 3:4] / 255.0
        return np.dstack([canvas[:, :, :3] * alpha, alpha])

    def warp(self, src: np.ndarray, sy: float = 1.0, k: float = 1.0, wmin: float = 1.0,
             a: float = 0.72, bulge: float = 0.0, shear: float = 0.0) -> np.ndarray:
        h, w = src.shape[:2]
        xx, yy = np.meshgrid(np.arange(self.cw, dtype=np.float32),
                             np.arange(self.ch, dtype=np.float32))
        vp = (self.yb - yy) / h
        up = xx - self.xc
        lowlen = a * sy
        toplen = (1.0 - a) * sy * k
        v = np.where(vp <= lowlen, vp / sy, a + (vp - lowlen) / (sy * k))
        t = (vp - lowlen) / max(toplen, 1e-6)
        wf = 1.0 - (1.0 - wmin) * sstep(t)
        wf = wf * (1.0 / np.sqrt(max(sy, 1e-6)))
        wf = wf * (1.0 + bulge * np.clip(1.0 - vp / max(lowlen + toplen, 1e-6), 0.0, 1.0))
        xs = (w - 1) / 2.0 + up / np.maximum(wf, 1e-6) + shear * self.cw * np.power(np.clip(t, 0, 1), 1.5)
        ys = (h - 1) - v * h
        out = cv2.remap(src, xs.astype(np.float32), ys.astype(np.float32),
                        cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out[..., 3] = np.clip(out[..., 3], 0.0, 1.0)
        return out

    def rotate(self, src: np.ndarray, angle: float, anchor: bool = True) -> np.ndarray:
        if abs(angle) < 1e-6:
            return src
        m = cv2.getRotationMatrix2D((self.cw / 2.0, self.ch / 2.0), angle, 1.0)
        out = cv2.warpAffine(src, m, (self.cw, self.ch), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out[..., 3] = np.clip(out[..., 3], 0.0, 1.0)
        return self.anchor_bottom(out) if anchor else out

    def anchor_bottom(self, src: np.ndarray) -> np.ndarray:
        ys, xs = np.nonzero(src[:, :, 3] > 0.02)
        if len(ys) == 0:
            return src
        dy = self.yb - (int(ys.max()) + 1)
        dx = self.xc - ((int(xs.min()) + int(xs.max()) + 1) / 2.0)
        if abs(dy) < 1e-6 and abs(dx) < 1e-6:
            return src
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        return cv2.warpAffine(src, m, (self.cw, self.ch), flags=cv2.INTER_NEAREST,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def frame(self, phi: float, psi: float, mode: str, k: float, wmin: float,
              tip: float, a0: float, sy: float, sytop: float, pa: float,
              bulge: float, shear: float) -> np.ndarray:
        if mode == "rest":
            sy = k = wmin = 1.0
            a0 = 0.72
        elif mode == "squash":
            k = 1.0
            wmin = 1.0
            a0 = pa if pa else a0
        else:
            k = max(0.2, k * (sytop if sytop else 1.0))
        pm = self.base
        if abs(psi) > 1e-6:
            pm = self.rotate(pm, -psi, anchor=False)
        pm = self.warp(pm, sy=sy, k=k, wmin=wmin, a=a0, bulge=bulge, shear=shear)
        if abs(psi) > 1e-6:
            pm = self.rotate(pm, psi, anchor=False)
        if abs(phi) > 1e-6:
            pm = self.rotate(pm, phi, anchor=True)
        else:
            pm = self.anchor_bottom(pm)
        return pm

    def save(self, pm: np.ndarray, path: Path) -> None:
        a = np.clip(pm[..., 3:4], 1e-4, 1.0)
        rgb = np.clip(pm[..., :3] / a, 0, 255)
        img = Image.fromarray(np.dstack([rgb, pm[..., 3:4] * 255.0]).astype(np.uint8), "RGBA")
        img.resize((self.size, self.size), Image.Resampling.LANCZOS).save(path)


def interp_keys(keys: list[dict], pos: float, defaults: dict) -> dict:
    if not keys:
        return dict(defaults)
    keys = sorted(keys, key=lambda x: float(x.get("i", 1)))
    prev = keys[0]
    nxt = keys[-1]
    for i, key in enumerate(keys):
        if float(key.get("i", 1)) <= pos:
            prev = key
            nxt = keys[i + 1] if i + 1 < len(keys) else key
        else:
            break
    out = dict(defaults)
    out["mode"] = prev.get("mode", defaults["mode"])
    for name in NUM_KEYS:
        if name in prev:
            out[name] = prev[name]
    if nxt is not prev:
        i0, i1 = float(prev.get("i", 1)), float(nxt.get("i", 1))
        t = sstep((pos - i0) / max(1e-6, i1 - i0))
        for name in NUM_KEYS:
            if name in prev or name in nxt:
                a = float(prev.get(name, defaults[name]))
                b = float(nxt.get(name, defaults[name]))
                out[name] = a + (b - a) * t
    return out


def face_for_keys(keys: list[dict], pos: float, index: int, frames: int) -> tuple[str, str, float]:
    keys = sorted(keys, key=lambda x: float(x.get("i", 1)))
    prev = keys[0]
    nxt = keys[-1]
    for i, key in enumerate(keys):
        if float(key.get("i", 1)) <= pos:
            prev = key
            nxt = keys[i + 1] if i + 1 < len(keys) else key
        else:
            break
    fa = str(prev.get("face", "happy"))
    fb = str(nxt.get("face", fa))
    if fa == fb:
        return fa, fa, 0.0
    i_min = float(keys[0].get("i", 1))
    i_max = float(keys[-1].get("i", 1))
    p_next = 1.0 + (float(nxt.get("i", 1)) - i_min) / max(1e-6, i_max - i_min) * (frames - 1)
    full = int(round(p_next))
    if index >= full:
        return fb, fb, 0.0
    if index == full - 1:
        return fa, fb, 0.5
    return fa, fa, 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Bumpy animations from animations.json.")
    parser.add_argument("--base", help="single approved cutout PNG/JPG")
    parser.add_argument("--faces", help="directory with named face PNGs (happy.png, etc.)")
    parser.add_argument("--animations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only")
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--size", type=int, default=208)
    parser.add_argument("--content", type=int, default=104)
    parser.add_argument("--bottom", type=int, default=155)
    parser.add_argument("--gif-sizes", default="48,96")
    parser.add_argument("--gif-fps", type=int, default=24)
    parser.add_argument("--gif-bg", default="200,205,215")
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()
    if not args.base and not args.faces:
        parser.error("give --base or --faces")

    data = json.loads(Path(args.animations).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("animations.json must be an object")
    only = {v.strip() for v in args.only.split(",")} if args.only else None
    face_dir = Path(args.faces) if args.faces else None
    renderers: dict[str, Renderer] = {}

    def renderer(face: str) -> Renderer:
        if face not in renderers:
            path = None
            if face_dir:
                for ext in (".png", ".webp", ".jpg", ".jpeg"):
                    candidate = face_dir / (face + ext)
                    if candidate.exists():
                        path = candidate
                        break
            if path is None and args.base:
                path = Path(args.base)
            if path is None:
                raise SystemExit(f"face not found: {face}")
            renderers[face] = Renderer(path, args.scale, args.size, args.content, args.bottom)
        return renderers[face]

    out_root = Path(args.out)
    gif_sizes = [int(v.strip()) for v in args.gif_sizes.split(",") if v.strip()]
    gif_bg = parse_rgb(args.gif_bg)

    for name, anim in data.items():
        if only and name not in only:
            continue
        frames = int(anim.get("frames", 0))
        keys = anim.get("keys", [])
        if frames <= 0:
            print(f"SKIP {name}: frames=0")
            continue
        defaults = {
            "mode": anim.get("mode", "rest"),
            "phi": 0.0, "psi": 0.0, "k": 1.0, "wmin": 1.0, "tip": 1.0,
            "a0": 0.72, "sy": 1.0, "sytop": 1.0, "pa": 0.72,
            "bulge": 0.0, "shear": 0.0,
        }
        for key in NUM_KEYS:
            if key in anim:
                defaults[key] = anim[key]
        i_min = float(keys[0].get("i", 1)) if keys else 1.0
        i_max = float(keys[-1].get("i", 1)) if keys else 1.0
        anim_dir = out_root / name
        anim_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        for index in range(1, frames + 1):
            pos = i_min if frames == 1 else i_min + (i_max - i_min) * (index - 1) / (frames - 1)
            p = interp_keys(keys, pos, defaults)
            fa, fb, w = face_for_keys(keys, pos, index, frames)
            pm_a = renderer(fa).frame(
                float(p["phi"]), float(p["psi"]), str(p["mode"]),
                float(p["k"]), float(p["wmin"]), float(p["tip"]),
                float(p["a0"]), float(p["sy"]), float(p["sytop"]),
                float(p["pa"]), float(p["bulge"]), float(p["shear"]),
            )
            if w > 0.0 and fb != fa:
                pm_b = renderer(fb).frame(
                    float(p["phi"]), float(p["psi"]), str(p["mode"]),
                    float(p["k"]), float(p["wmin"]), float(p["tip"]),
                    float(p["a0"]), float(p["sy"]), float(p["sytop"]),
                    float(p["pa"]), float(p["bulge"]), float(p["shear"]),
                )
                pm = pm_a * (1.0 - w) + pm_b * w
            else:
                pm = pm_a
            path = anim_dir / f"{name}_{index:03d}.png"
            renderer(fa).save(pm, path)
            rendered.append(Image.open(path).convert("RGBA"))
        if not args.no_gif:
            export_gif(rendered, anim_dir / name, gif_sizes, args.gif_fps, gif_bg)
        print(f"{name}: {frames} frames -> {anim_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
