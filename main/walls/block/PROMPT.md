# Промт для FLUX.2 — кирпичная стена (block, lo = 10)

Разрушаемая кирпичная кладка: мяч бьёт снизу и сносит **один ряд за удар**, снизу
вверх ([`block.script`](block.script:26)). Ряды не нарисованы на состояния — их
отсекает шейдер [`block.fp`](block.fp:24), поэтому важна только «идеальная»
текстура с ровной сеткой кладки.

Геометрия блока: quad `140 × 112.5` локальных единиц, Y от `-50` до `+62.5`
([`block.buffer`](block.buffer:7)), текстура растягивается на всю площадь.
Всего рядов по умолчанию `rows = 8` ([`block.script`](block.script:15)).

Срез разбитых рядов задаётся не формулой, а таблицей `ROW_CUT` в
[`block.script`](block.script:24) — она снята с готовой текстуры скриптом
[`tools/gen_block_rows.py`](../../../tools/gen_block_rows.py). Поэтому ряды
не обязаны быть идеально равными: после замены `block.png` достаточно
перегенерировать таблицу. Важно только, чтобы каждый ряд был отделён
видимым швом раствора — по нему и проходит срез.

Стиль серии — как у остальных ассетов игры: 2D-спрайт, плоский cel-shading,
толстый тёмный контур, яркие насыщенные цвета, чистые векторные формы.

---

## 1. Основной промт (копировать целиком, EN)

```
Cute cartoon 2D game asset, flat front view, isolated on pure white background, no
perspective, no cast shadows. A rectangular red brick wall block, almost square (thin
vertical wall), built of warm red bricks (#C0392B, #B03A2E, #A93226 randomly varied)
with pale sandy-grey mortar joints. Exactly eight horizontal courses of equal height,
four bricks per course, every second course offset by half a brick, thin dark outlines
around each brick, flat cel shading with one soft light highlight on the top edge of
each brick and one darker shade on the bottom edge, a few tiny chips, cracks and
speckles for a hand-drawn cartoon look, crisp vector-like edges. A single thin green
jungle vine wraps the wall very sparsely: a slim glossy stem with a twisted spiral
texture climbing up the left edge in a loose S-curve, only three or four small cartoon
leaves, one curly tendril at the top — mostly bare brick is still visible, the vine
covers only a small part of the wall. Vibrant saturated colors, thick cartoon outline,
mobile arcade platformer style, 8k game asset
```

## 2. Короткая версия (если модель режет длинный промт)

```
2D cartoon platformer brick wall, red bricks with grey mortar, exactly 8 equal rows,
4 bricks per row, half-brick offset, thick dark outlines, flat cel shading, one thin
green vine with 3-4 small leaves climbing sparsely up the left edge, white background,
flat front view, game asset
```

## 3. Вариант для длинной стены из нескольких блоков (тайлится по горизонтали)

Длинная стена в игре собирается из нескольких блоков подряд, поэтому лиана
должна стыковаться: у левого края — поднимающийся стебель, у правого — его
продолжение с листом. Тогда повторы читаются как одна непрерывная лиана.

```
... the same red brick wall block, seamless horizontal tiling: the green vine enters
at the bottom-left corner, climbs up along the left edge, its stem leaves the frame at
the top-right corner and a matching stem stub with one leaf returns at the same height
on the right edge, so the pattern repeats continuously; thin sandy mortar joints align
across the left and right borders, brick courses cut exactly at the frame edges,
seamless repeating pattern, no visible seam ...
```

## 4. Вариант без лианы (базовая кладка, если лиана мешает читаемости)

```
... the same red brick wall block, clean bare masonry, exactly 8 equal courses, thick
dark cartoon outline, flat cel shading, small chips and speckles only, no plants, no
vine, no moss ...
```

## 5. Что писать в negative prompt

```
text, watermark, logo, letters, numbers, ui, characters, faces, hands, 3d render,
realistic photo, photorealistic brick texture, mortar haze, soft blurry edges, heavy
gradients, drop shadow, ambient occlusion, background scenery, ground, grass, sky,
perspective, isometric, tilted camera, side view with visible depth, diagonal wall,
rounded corners, uneven brick rows, more than 8 rows, ivy covering the whole wall, dense
foliage, moss everywhere, flowers, broken hole, missing bricks, fire, damage
```

## 6. Технические требования к результату

| Параметр | Значение |
|---|---|
| Соотношение сторон | `140 : 112.5` ≈ 1.244:1 (например `1120×900` или `1400×1125`) |
| Ряды кладки | **ровно 8**, каждый отделён швом раствора |
| Кирпичей в ряду | 3–4, чётные ряды смещены на полкирпича |
| Ориентация | плоский вид спереди, строго вертикальная стена, без наклона |
| Края | кирпичи обрезаны рамкой ровно по шву, кладка уходит за край (нужно для стыковки блоков в длинную стену) |
| Лиана | одна, тонкая, занимает не более ~15 % площади, у левого края |
| Фон | чистый белый (`#FFFFFF`), альфу FLUX не отдаёт — вырезать пост-обработкой |
| Контур | толстый, тёмный, замкнутый по силуэту блока и по каждой лиане |
| Прозрачность | у модели не просить, только пост-обработкой |

## 7. Важное ограничение движка (учесть при подготовке PNG)

Шейдер [`block.fp`](block.fp:26) отбрасывает всё, что **ниже** локального Y
`brick_break.x`, а значение среза берётся из таблицы `ROW_CUT` в
[`block.script`](block.script:24) (локальные координаты `-50..+62.5`).
Значит:

1. Таблица `ROW_CUT` должна соответствовать новой текстуре — после замены
   `block.png` запустить `py tools/gen_block_rows.py` и перенести полученный
   список в [`block.script`](block.script:24).
2. Разбитые ряды исчезают **без** анимации и без обломков — не рисовать на
   текстуре осыпающиеся кирпичи, крошку у нижнего края и «дыры»: они будут
   висеть в воздухе.
3. Текстура не тайлится по вертикали: низ и верх должны быть разными
   (низ — обычный ряд, верх — обычный ряд, без обрезки «на половину» по
   горизонтали).

## 8. Порядок работы

1. Сгенерировать квадрат ~`1024×1024` — так модель лучше держит пропорции
   кирпичей и лианы.
2. Проверить, что рядов ровно 8 и каждый отделён швом раствора.
3. Вписать в `1400×1125` (или сразу уменьшить до целевого `140×112.5` с
   nearest-neighbour, чтобы контур остался резким).
4. Вырезать белый фон, сохранить как [`block.png`](block.png).
5. Перегенерировать таблицу срезов: `py tools/gen_block_rows.py`, перенести
   `ROW_CUT` в [`block.script`](block.script:24) и стартовое значение
   `brick_break.x` в [`block.material`](block.material:24).
6. Проверить в игре: после 1–7 ударов срез должен идти строго по шву между
   рядами, а лиана не должна «висеть» после разрушения нижних рядов —
   если она доходит до низа, укоротить её до верхней половины стены.
