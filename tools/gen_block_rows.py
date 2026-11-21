"""Снимает с block.png реальные границы рядов кладки и печатает таблицу
локальных Y для шейдера block.fp / скрипта block.script.

Геометрия: текстура натянута на quad меша (block.buffer),
    v       = (H - y) / H                (0 внизу, 1 вверху)
    y_local = Y_MESH_MIN + v * (Y_MESH_MAX - Y_MESH_MIN)

Швы ищутся в нескольких X-окнах (правее лианы) и усредняются: на текстуре
ряды нарисованы с разной высотой, поэтому срез обязан идти по шву раствора,
а не по равномерной сетке.

Запуск:  py tools/gen_block_rows.py
"""
from PIL import Image, ImageDraw

TEX = 'main/walls/block/block.png'
Y_MESH_MIN = -50.0   # низ меша (block.buffer)
Y_MESH_MAX = 62.5    # верх меша (block.buffer)
ROWS = 8             # go.property("rows") в block.script

im = Image.open(TEX).convert('RGBA')
w, h = im.size
px = im.load()
H = h - 1
print('texture: %dx%d' % (w, h))

# X-окна правее лианы: лиана идёт по левому краю, но берём несколько окон,
# чтобы усреднить наклон шва
WINDOWS = [(360, 560), (600, 800), (820, 1020), (1000, 1150)]


def opaque_frac(y):
    c = n = 0
    for x in range(int(w * 0.35), int(w * 0.95), 2):
        if px[x, y][3] > 128:
            c += 1
        n += 1
    return c / float(n)


def mortar(y, xa, xb):
    """Доля «раствора» (светлые малонасыщенные пиксели) в окне xa..xb."""
    c = n = 0
    for x in range(xa, xb, 2):
        r, g, b, a = px[x, y]
        if a < 40:
            n += 1
            continue
        mx, mn = max(r, g, b), min(r, g, b)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum > 105 and (mx - mn) / mx < 0.50:
            c += 1
        n += 1
    return c / float(n)


# 1. вертикальные границы кладки
masonry_top = next(y for y in range(h) if opaque_frac(y) > 0.5)
masonry_bottom = next(y for y in range(h - 1, -1, -1) if opaque_frac(y) > 0.5)
print('masonry rows: %d..%d (height %d px)' % (
    masonry_top, masonry_bottom, masonry_bottom - masonry_top + 1))

# 2. ищем 7 внутренних швов: в каждом окне берём максимум раствора
#    в пределах +-55 px от равномерной сетки, затем усредняем по окнам
step = (masonry_bottom - masonry_top) / float(ROWS)
joints = []
for k in range(1, ROWS):
    pred = masonry_top + k * step
    found = []
    for xa, xb in WINDOWS:
        lo, hi = int(pred - 55), int(pred + 55)
        y = max(range(lo, hi + 1), key=lambda yy: mortar(yy, xa, xb))
        found.append(y)
    avg = sum(found) / float(len(found))
    joints.append(avg)
    print('joint %d: pred %7.1f  windows %s  -> %.1f' % (
        k, pred, found, avg))

# 3. последовательность срезов снизу вверх
pixel_cuts = [masonry_bottom] + joints[::-1] + [masonry_top]


def to_local(y):
    v = (H - y) / float(H)
    return Y_MESH_MIN + v * (Y_MESH_MAX - Y_MESH_MIN)


cuts = [to_local(y) for y in pixel_cuts]

print()
print('cuts in pixels (bottom -> top):', [round(y, 1) for y in pixel_cuts])
print('cuts local Y (broken = 0..%d):' % (len(cuts) - 1))
for i, c in enumerate(cuts):
    print('   broken=%d -> %8.3f' % (i, c))

print()
print('-- Lua, для block.script (низ -> верх) --')
print('local ROW_CUT = { %s }' % ', '.join('%.2f' % c for c in cuts))

# 4. оверлей для визуальной проверки
ov = im.copy()
d = ImageDraw.Draw(ov)
for i, (y, c) in enumerate(zip(pixel_cuts, cuts)):
    d.line([(0, int(y)), (w - 1, int(y))], fill=(0, 255, 255, 255), width=3)
    d.text((12, max(0, int(y) - 14)), 'b=%d %.1f' % (i, c), fill=(255, 0, 255, 255))
ov.convert('RGB').save('tools/_overlay_cuts.png')
print('overlay -> tools/_overlay_cuts.png')
