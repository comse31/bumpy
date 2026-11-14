"""Добавляет в main/controls/controls.gui два узла подсветки режима "тап по ячейкам":

  cell_highlight — рамка ячейки (текстура controls/hl_frame);
  wall_highlight — полоска боковой стенки (текстура controls/hl_pixel).

Узлы позиционируются и растягиваются из gui-скрипта, поэтому в файле у них
нулевые позиция/размер. Повторный запуск безопасен: старые узлы заменяются.

Запуск:  py tools/gen_controls_highlight.py
"""

import io
import re

GUI_PATH = 'main/controls/controls.gui'

NODE = '''nodes {{
  position {{
    x: 0.0
    y: 0.0
    z: 0.0
    w: 1.0
  }}
  size {{
    x: {w:.1f}
    y: {h:.1f}
    z: 0.0
    w: 1.0
  }}
  color {{
    x: 1.0
    y: 1.0
    z: 1.0
    w: 1.0
  }}
  type: TYPE_BOX
  blend_mode: BLEND_MODE_ALPHA
  texture: "{texture}"
  id: "{node_id}"
  pivot: PIVOT_CENTER
  adjust_mode: ADJUST_MODE_STRETCH
  inherit_alpha: true
  alpha: 0.9
  clipping_mode: CLIPPING_MODE_NONE
  clipping_visible: true
  clipping_inverted: false
}}
'''


def build():
    return (
        NODE.format(node_id='cell_highlight', texture='controls/hl_frame', w=160.0, h=106.7)
        + NODE.format(node_id='wall_highlight', texture='controls/hl_pixel', w=8.0, h=106.7)
    )


def main():
    with io.open(GUI_PATH, 'r', encoding='utf-8') as f:
        text = f.read()

    # убрать ранее добавленные узлы подсветки вместе с их блоками nodes { ... }
    blocks = re.split(r'(?m)^(?=nodes \{)', text)
    kept = []
    for block in blocks:
        if re.search(r'(?m)^\s*id: "(cell_highlight|wall_highlight)"', block):
            continue
        kept.append(block)
    text = ''.join(kept)

    m = re.search(r'(?m)^material:', text)
    if not m:
        raise SystemExit('не найден блок material: в %s' % GUI_PATH)

    text = text[:m.start()] + build() + '\n' + text[m.start():]
    text = re.sub(r'(?m)^max_nodes: \d+$', 'max_nodes: 16', text)

    with io.open(GUI_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)

    print('written %s' % GUI_PATH)


if __name__ == '__main__':
    main()
