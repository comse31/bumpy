#!/usr/bin/env python3
"""Generate 12 world prompt files (P4-P7) from the pipeline world table."""
from __future__ import annotations

import argparse
from pathlib import Path

ENV_STYLE = """Smooth glossy 2.5D cartoon mobile game art, thin dark outline, soft top-left light, saturated but balanced colors, big simple readable shapes (the asset is shown very small in game), consistent with a bright casual mobile platformer. No text, no characters."""

WORLDS = [
    ("sunny", "Солнечный день", "blue sky, white clouds, rolling green hills, round trees, flowers",
     "bright green grass", "warm brown soil with stones and roots", "grey metal", "roots, stones, flowers, grass tufts"),
    ("rainy", "Дождь и гроза", "dark rain clouds, puddles, wet trees, rain",
     "dark wet grass", "wet soil, wet stone, wooden planks", "dark wet metal", "puddles, wet stones, wet roots"),
    ("night", "Ночь", "stars, big moon, fireflies, tree silhouettes",
     "dark grass", "dark soil and bluish stones with cold highlights", "dark steel with cold blue highlights",
     "glowing mushrooms, bluish stones, roots"),
    ("winter", "Зима", "snowy hills, fir trees, snowdrifts, snowflakes",
     "snow on top", "frozen soil, ice, frozen stones", "ice crystal", "snow lumps, icicles, frozen stones"),
    ("christmas", "Рождество", "christmas trees, garlands, gifts, snowy houses",
     "snow ledges", "wooden planks, ice, warm lights", "candy-cane striped", "gift boxes, lights, snow lumps"),
    ("halloween", "Хэллоуин", "purple sky, pumpkins, fog, moon, bare trees",
     "dark soil with dry roots", "stone, mystic flame", "bone-like dark", "pumpkins, dry roots, small mystic flames"),
    ("japan", "Япония", "Mount Fuji, pagodas, sakura, lanterns, small bridges",
     "wooden planks", "stone base, bamboo, petals", "stone / bamboo", "lanterns, petals, bamboo, stones"),
    ("desert", "Пустыня", "dunes, rock formations, cacti, dry plants",
     "sand", "sandstone, rock ledges, cracks", "bone / stone", "cacti, dry bushes, cracked stones"),
    ("space", "Космос", "planets, stars, nebulae, asteroids, space stations",
     "metal panel with glowing energy strip", "asteroid rock", "metal / energy", "crystals, antenna, small asteroids"),
    ("industrial", "Индустриальный", "factories, pipes, tanks, steam",
     "metal grate", "rusty beams, concrete", "rusty metal", "gears, pipes, rivet plates"),
    ("autumn", "Осень", "golden trees, red leaves, mushrooms",
     "dry grass and leaves", "roots, moss", "dry wood / metal", "leaves, mushrooms, mossy roots"),
    ("tropical", "Тропики", "palm trees, jungle, islands, waterfalls",
     "sand and jungle plants", "wet soil, roots, mossy stones", "thorny plant / stone",
     "palm leaves, roots, mossy stones, shells"),
]


def platform_prompt(w):
    _, _, _, top, side, _, _ = w
    return f"""2D platformer platform sprites, side view, flat pure blue background #0000FF, each piece separate with wide spacing, all the same wide rectangular proportion (about 2.8 : 1, width to height), equal size:
1) normal platform: {top} on top, {side} underneath;
2) sticky platform: same shape, covered with glossy sticky goo, slightly gummy look;
3) shrinkable platform: same shape, made of fragile segmented material, looks like it can wear away;
4) burning platform: same shape with glowing cracks, charred, ready for flames on top;
5) burning sticky platform: sticky goo mixed with ember glow.
The top surface is clearly lighter than the side so the standing surface reads at small size.
{ENV_STYLE}"""


def hazard_prompt(w):
    _, _, _, top, side, spikes, _ = w
    return f"""2D platformer hazards and slopes on a flat pure blue background #0000FF, separate pieces with wide spacing:
1) spike platform: a wide base strip with a row of sharp {spikes} on top, aspect about 2.2 : 1;
2) the same spike platform with fewer, larger spikes;
3) slope platform rising to the right, same material as the normal platform: {top} on top, {side} underneath;
4) the mirrored slope falling to the right.
Sharp triangular silhouettes that are clearly dangerous and different in shape from every platform.
{ENV_STYLE}"""


def background_prompt(w):
    _, _, bg, _, _, _, _ = w
    return f"""Horizontal 16:9 background for a 2D mobile platformer, {bg}. Layered depth: distant sky, soft mid-ground shapes, calm composition. Gentle soft focus and low contrast everywhere gameplay happens: the whole central area and lower two thirds; the main interest and brighter details only near the left and right edges. No characters, no platforms, no UI, no text, nothing sharp or high-contrast in the middle.
{ENV_STYLE}"""


def decor_prompt(w):
    _, _, _, _, _, _, decor = w
    return f"""Decor set on a flat pure blue background #0000FF: separate small items with wide spacing, same style and scale: {decor}.
{ENV_STYLE}"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate P4-P7 prompt files for 12 worlds.")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "prompts"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for i, w in enumerate(WORLDS, start=1):
        slug, title, *_ = w
        body = (
            f"# World {i:02d} — {title}\n\n"
            f"Подстановка из таблицы миров pipeline. Ключ: синий #0000FF. "
            f"Герой не нужен; окружение — Phoenix/SeaArt.\n\n"
            f"## P4. Платформы мира\n\n```text\n{platform_prompt(w)}\n```\n\n"
            f"## P5. Шипы и склоны мира\n\n```text\n{hazard_prompt(w)}\n```\n\n"
            f"## P6. Фон мира\n\n```text\n{background_prompt(w)}\n```\n\n"
            f"## P7. Декор мира\n\n```text\n{decor_prompt(w)}\n```\n"
        )
        (out / f"world_{i:02d}_{slug}.md").write_text(body, encoding="utf-8")
    print(f"prompts: {len(WORLDS)} files -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
