"""Генератор вспомогательных текстур для сенсорного управления.

Пишет:
  main/controls/white.png      — сплошной белый квадрат 8x8 (заливка узлов:
                                 полоска боковой стенки, тонируется цветом узла);
  main/controls/cell_frame.png — тонкая белая рамка 96x96 с прозрачным центром
                                 (подсветка игровой ячейки при тапе).

Цвет и прозрачность задаются самим GUI-узлом, текстуры служат только формой.

Запуск:  py tools/gen_controls_ui.py
"""

import os

from PIL import Image, ImageDraw

WHITE_W, WHITE_H = 8, 8
FRAME_W, FRAME_H = 96, 96
FRAME_BORDER = 2

OUT_DIR = 'main/controls'
WHITE_OUT = os.path.join(OUT_DIR, 'white.png')
FRAME_OUT = os.path.join(OUT_DIR, 'cell_frame.png')

os.makedirs(OUT_DIR, exist_ok=True)

# сплошная белая заливка
white = Image.new('RGBA', (WHITE_W, WHITE_H), (255, 255, 255, 255))
white.save(WHITE_OUT)
print('written %s (%dx%d)' % (WHITE_OUT, WHITE_W, WHITE_H))

# тонкая рамка: белые пиксели по периметру, центр прозрачный
frame = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
d = ImageDraw.Draw(frame)
d.rectangle(
    [0, 0, FRAME_W - 1, FRAME_H - 1],
    outline=(255, 255, 255, 255),
    width=FRAME_BORDER,
)
frame.save(FRAME_OUT)
print('written %s (%dx%d, border %d)' % (FRAME_OUT, FRAME_W, FRAME_H, FRAME_BORDER))
