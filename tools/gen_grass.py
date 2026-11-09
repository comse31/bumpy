"""Генератор текстуры платформы: мультяшная полянка с травой.

Пишет PNG размером 960x80 (RGBA) в main/platforms/default/platform.png.
Рисуется с 4x суперсэмплингом и уменьшается LANCZOS — получается гладкий
"мультяшный" контур.
"""

import math
import os
import random

from PIL import Image, ImageDraw

W, H = 960, 80
SS = 4
w, h = W * SS, H * SS

OUTLINE = (44, 62, 38, 255)

SOIL_L = (192, 146, 96, 255)
SOIL = (156, 108, 66, 255)
SOIL_D = (114, 74, 44, 255)
SOIL_DD = (84, 52, 30, 255)
PEBBLE = (206, 196, 178, 255)
PEBBLE_D = (152, 138, 118, 255)

GRASS_L = (172, 234, 110, 255)
GRASS = (120, 208, 78, 255)
GRASS_M = (88, 182, 66, 255)
GRASS_D = (62, 152, 56, 255)
GRASS_DD = (42, 118, 48, 255)

FLOWER_COLORS = [
    (255, 255, 255, 255),
    (255, 226, 104, 255),
    (255, 168, 196, 255),
    (255, 132, 112, 255),
    (196, 174, 255, 255),
    (255, 200, 90, 255),
]

random.seed(20260519)


def S(v):
    """Пиксели итогового размера -> пиксели суперсэмплинга."""
    return int(round(v * SS))


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))


def make_gradient(stops):
    """Вертикальный градиент по всей высоте. stops: [(t, color), ...]."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        c = stops[-1][1]
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t <= t1 or i == len(stops) - 2:
                k = 0.0 if t1 <= t0 else max(0.0, min(1.0, (t - t0) / (t1 - t0)))
                c = lerp(c0, c1, k)
                break
        dr.line([0, y, w, y], fill=c)
    return img


def base_line(x):
    """Условная «почва» травяного ковра (низ травинок, верх земли)."""
    return 40.0 + 2.6 * math.sin(x * 0.017 + 0.6) + 1.3 * math.sin(x * 0.053 + 2.1)


def quad(p0, p1, p2, t):
    u = 1.0 - t
    return (
        u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
        u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
    )


def draw_blade(d, cx, base_y, tip_y, hw, lean, fill, edge):
    """Травинка: широкая у основания, сужается к округлому концу."""
    length = base_y - tip_y
    p0 = (cx, base_y)
    p1 = (cx + lean * 0.35, base_y - length * 0.55)
    p2 = (cx + lean, tip_y)

    steps = 16
    left = []
    right = []
    for i in range(steps + 1):
        t = i / steps
        sx, sy = quad(p0, p1, p2, t)
        wdt = hw * (1.0 - t ** 1.6) ** 0.5 + 0.9
        left.append((S(sx - wdt), S(sy)))
        right.append((S(sx + wdt), S(sy)))

    d.polygon(left + list(reversed(right)), fill=fill, outline=edge, width=S(0.8))
    # слегка скруглённый кончик
    d.ellipse(
        [S(p2[0] - hw * 0.42), S(p2[1] - hw * 0.42),
         S(p2[0] + hw * 0.42), S(p2[1] + hw * 0.42)],
        fill=fill,
        outline=edge,
        width=S(0.7),
    )
    # мягкий блик вдоль левого края травинки
    hl = []
    for t in (0.1, 0.28, 0.46, 0.64):
        hx, hy = quad(p0, p1, p2, t)
        hw_t = hw * (1.0 - t ** 1.6) ** 0.5
        hl.append((S(hx - hw_t * 0.42), S(hy)))
    d.line(hl, fill=(255, 255, 255, 70), width=S(1.3), joint="curve")


def draw_tuft(d, cx, base_y, height, halfw, lean, fill, edge):
    """Кустик: сплошная выпуклая «шапка» травы с округлой вершиной."""
    top_y = base_y - height
    steps = 18
    left = []
    right = []
    for i in range(steps + 1):
        t = i / steps  # 0 = левый край, 1 = правый
        xx = cx - halfw + 2.0 * halfw * t
        bump = (1.0 - (2.0 * t - 1.0) ** 2) ** 0.42
        yy = base_y - height * bump
        xx += lean * (1.0 - abs(2.0 * t - 1.0))
        left.append((S(xx), S(yy)))
    poly = left + [(S(cx + halfw), S(base_y + 2)), (S(cx - halfw), S(base_y + 2))]
    d.polygon(poly, fill=fill, outline=edge, width=S(0.9))
    # округлая вершина
    d.ellipse(
        [S(cx + lean - halfw * 0.30), S(top_y - halfw * 0.30),
         S(cx + lean + halfw * 0.30), S(top_y + halfw * 0.30)],
        fill=fill,
    )
    # блик сверху-слева
    d.arc(
        [S(cx - halfw * 0.7), S(top_y - halfw * 0.1),
         S(cx + halfw * 0.7), S(base_y - height * 0.35)],
        start=200, end=280,
        fill=(255, 255, 255, 90),
        width=S(1.6),
    )


def draw_pebble(d, cx, cy, rx, ry, tilt):
    d.ellipse(
        [S(cx - rx), S(cy - ry), S(cx + rx), S(cy + ry)],
        fill=PEBBLE,
        outline=PEBBLE_D,
        width=S(1.1),
    )
    d.ellipse(
        [S(cx - rx * 0.5 - tilt), S(cy - ry * 0.55), S(cx - rx * 0.05 - tilt), S(cy - ry * 0.1)],
        fill=(234, 228, 216, 255),
    )


def draw_flower(d, fx, base_y, tip_y, color):
    # стебелёк
    d.line([S(fx), S(base_y), S(fx), S(tip_y)], fill=GRASS_D, width=S(1.6))
    # два листика вдоль стебля
    for ly, side in ((0.35, -1), (0.62, 1)):
        yy = base_y + (tip_y - base_y) * ly
        xa, xb = sorted((fx + side * 5.0 - 2.4, fx + side * 0.4))
        d.ellipse(
            [S(xa), S(yy - 2.8), S(xb), S(yy + 1.2)],
            fill=GRASS_M,
            outline=GRASS_D,
            width=S(0.7),
        )
    # лепестки
    for k in range(5):
        a = 2.0 * math.pi * k / 5.0 - math.pi / 2.0
        px_ = fx + 4.0 * math.cos(a)
        py_ = tip_y + 4.0 * math.sin(a)
        d.ellipse(
            [S(px_ - 3.6), S(py_ - 3.6), S(px_ + 3.6), S(py_ + 3.6)],
            fill=color,
            outline=(150, 116, 76, 210),
            width=S(0.9),
        )
    # серединка
    d.ellipse(
        [S(fx - 2.4), S(tip_y - 2.4), S(fx + 2.4), S(tip_y + 2.4)],
        fill=(255, 214, 92, 255),
        outline=(198, 148, 40, 255),
        width=S(0.9),
    )


def main():
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # --- маска травы и земли ---
    grass_mask = Image.new("L", (w, h), 0)
    soil_mask = Image.new("L", (w, h), 0)
    gm = ImageDraw.Draw(grass_mask)
    sm = ImageDraw.Draw(soil_mask)

    top_pts = []
    bot_pts = []
    for i in range(w + 1):
        x = i / SS
        top_pts.append((i, S(base_line(x) - 9.0)))
        bot_pts.append((i, S(base_line(x))))

    gm.polygon(top_pts + list(reversed(bot_pts)) + [(w, h), (0, h)], fill=255)
    sm.polygon(bot_pts + [(w, h), (0, h)], fill=255)

    # --- заливка земли ---
    soil_grad = make_gradient([
        (0.50, SOIL_L),
        (0.72, SOIL),
        (0.92, SOIL_D),
        (1.0, SOIL_DD),
    ])
    layer.paste(soil_grad, (0, 0), soil_mask)

    # --- базовый слой травы (сплошной ковёр) ---
    grass_grad = make_gradient([
        (0.0, GRASS_L),
        (0.55, GRASS),
        (1.0, GRASS_M),
    ])
    layer.paste(grass_grad, (0, 0), grass_mask)

    # --- детали земли: крапинки ---
    for _ in range(750):
        x = random.uniform(0, W)
        y = random.uniform(base_line(x) + 1, H)
        r = random.uniform(0.6, 1.9)
        c = SOIL_D if random.random() < 0.55 else SOIL_L
        d.ellipse([S(x - r), S(y - r), S(x + r), S(y + r)], fill=c[:3] + (135,))

    # --- камешки ---
    for _ in range(15):
        x = random.uniform(14, W - 14)
        y = random.uniform(base_line(x) + 6, H - 6)
        draw_pebble(
            d, x, y,
            random.uniform(2.5, 5.5),
            random.uniform(2.0, 4.0),
            random.uniform(-1.0, 1.0),
        )

    # --- корешки ---
    for _ in range(9):
        x = random.uniform(20, W - 20)
        y0 = base_line(x) + 1
        d.line(
            [S(x), S(y0), S(x + random.uniform(-3, 3)), S(y0 + random.uniform(4, 9))],
            fill=SOIL_DD[:3] + (110,),
            width=S(0.8),
        )

    # --- кустики травы ---
    tufts = []
    cx = -12.0
    while cx < W + 12.0:
        halfw = random.uniform(9.0, 16.0)
        height = random.uniform(9.0, 24.0)
        tufts.append({
            "cx": cx,
            "base_y": base_line(cx) + random.uniform(-0.5, 1.5),
            "height": height,
            "halfw": halfw,
            "lean": random.uniform(-3.0, 3.0),
        })
        cx += halfw * random.uniform(0.9, 1.35)

    # высокие — позади, низкие — впереди
    tufts.sort(key=lambda t: t["height"], reverse=True)

    tuft_palette = [GRASS, GRASS_M, GRASS_D]
    for i, t in enumerate(tufts):
        fill = tuft_palette[i % len(tuft_palette)]
        draw_tuft(
            d,
            t["cx"], t["base_y"], t["height"], t["halfw"], t["lean"],
            fill, GRASS_DD,
        )

    # --- отдельные травинки поверх кустиков для детализации ---
    blades = []
    bx = -4.0
    while bx < W + 4.0:
        base_y = base_line(bx) + random.uniform(-1.0, 2.0)
        height = random.uniform(10.0, 26.0)
        blades.append({
            "cx": bx,
            "base_y": base_y,
            "tip_y": base_y - height,
            "hw": random.uniform(1.4, 2.8),
            "lean": random.uniform(-4.0, 4.0),
        })
        bx += random.uniform(9.0, 17.0)

    blade_palette = [GRASS_L, GRASS, GRASS_L, GRASS_M]
    for i, b in enumerate(blades):
        draw_blade(
            d,
            b["cx"], b["base_y"], b["tip_y"], b["hw"], b["lean"],
            blade_palette[i % len(blade_palette)], GRASS_DD,
        )

    # --- мягкая тень у основания травы ---
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(w + 1):
        x = i / SS
        y0 = base_line(x)
        for k in range(9):
            a = int(30 * (k / 8.0) ** 1.9)
            yy = y0 - 8 + k
            sd.line([i, S(yy), i, S(yy + 1)], fill=(30, 72, 36, a))
    layer.paste(shade, (0, 0), grass_mask)

    # --- цветочки ---
    flower_x = [random.uniform(40, W - 40) for _ in range(13)]
    flower_x.sort()
    for k, fx in enumerate(flower_x):
        tip_y = random.uniform(6.0, 20.0)
        draw_flower(
            d,
            fx,
            base_line(fx) - 3.0,
            tip_y,
            FLOWER_COLORS[k % len(FLOWER_COLORS)],
        )

    out = layer.resize((W, H), Image.LANCZOS)

    dst = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "main",
        "platforms",
        "default",
        "platform.png",
    )
    out.save(dst)
    print("saved", dst, out.size, out.mode)


if __name__ == "__main__":
    main()
