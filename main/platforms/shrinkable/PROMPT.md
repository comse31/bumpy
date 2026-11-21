# Промт для FLUX.2 — расходуемая платформа (shrinkable), 4 состояния

Платформа — горизонтальная балка из **сплетённых между собой лиан / бамбуковых
стеблей** в мультяшном стиле. Игровой объект
[`main/platforms/shrinkable/platform.go`](platform.go:1) использует собственный
меш [`platform.mesh`](platform.mesh:1) со своим буфером
[`platform.buffer`](platform.buffer:1), материалом
[`platform.material`](platform.material:1), фрагментным шейдером
[`platform.fp`](platform.fp:14) и общим вершинным шейдером
[`../platform.vp`](../platform.vp:25); логика — в скрипте
[`shrinkable.script`](shrinkable.script:5).

Скрипт сжимает платформу **только по горизонтали** (высота неизменна), коэффициент
берётся из `remaining / durability`. При `durability = 3` получается ровно
**4 состояния**:

| # | `remaining` | `shrink` | Что показываем |
|---|---|---|---|
| 1 | 3 | `1.00` | целые лианы, платформа нетронута |
| 2 | 2 | `0.66` | одно касание: одна жила надорвана, сок, волокна |
| 3 | 1 | `0.33` | два касания: балка разбита, торчат обрывки |
| 4 | 0 | `0.00` | обломок/пустота, коллизия отключена (`gone = 1`) |

> Важно: горизонтальное сжатие уже делает вершинный шейдер. Все 4 текстуры
> рисуются **на полную ширину полосы** (силуэт тянется от края до края), разница
> между состояниями — только в степени повреждения, а не в ширине. Иначе
> получится двойное сжатие.

---

## 1. Основной промт (общий стиль, копировать целиком, EN)

```
Cute 2D cartoon game asset, wide horizontal strip, flat side view, isolated on pure
white background, no perspective, no cast shadows. A platformer platform built from
three thick jungle vines and bamboo stalks braided and woven around each other into
one solid horizontal beam: glossy green vine ropes with a twisted spiral texture,
segmented yellow-green bamboo culms with visible nodes and small cut leaves, a couple
of tiny curly tendrils and one or two small buds tucked between the strands. All
strands interlace visibly — over, under, over — with clean colour separation where
they cross. Thick dark cartoon outline, flat cel shading with one light rim on top and
one darker shade on the underside, vibrant saturated greens and warm yellow-green
bamboo, crisp vector-like edges, mobile arcade platformer style, 8k game asset
```

## 2. Четыре состояния (каждое — отдельная генерация, EN)

Генерировать по одной полосе на состояние, сохраняя одну и ту же композицию
(те же три сплетённых стебля в той же позиции). Менять только «урон».

**Состояние 1 — целая:**

```
... three woven vine-and-bamboo strands, completely healthy and intact, full bright
green, fresh glossy leaves, tiny flower bud, no damage, no cracks, seamless repeating
pattern of 3 identical segments, even rhythm of the weave
```

**Состояние 2 — первое попадание:**

```
... the same braided vine-and-bamboo platform, one strand snapped and torn: a shallow
cut through the bamboo with pale splintered fibres and a few juice droplets, small
green leaf dangling loose, the weave slightly loosened, everything else still intact
and bright, seamless repeating pattern of 3 identical segments
```

**Состояние 3 — сильное повреждение:**

```
... the same braided vine-and-bamboo platform, badly broken: two of the three strands
are torn apart, frayed pale fibres and broken bamboo splinters sticking out, dark hollow
gaps between the strands, wilting yellowed leaves, drops of green sap, the beam looks
about to collapse, seamless repeating pattern of 3 identical segments
```

**Состояние 4 — почти исчезла:**

```
... the remains of the braided vine platform: only a thin tattered stump of vine across
the middle, a few loose hanging threads and one dry drooping leaf, mostly transparent
empty space, edges already fading out, very low visual mass, seamless repeating pattern
of 3 identical segments
```

## 3. Одна картинка-лист на все 4 состояния (если модель держит композицию)

FLUX.2 хорошо собирает сетку, поэтому можно заказать лист `2×2` — 4 полосы
одинакового размера, состояние читается слева-направо и сверху-вниз.

```
Game asset sheet, 2x2 grid of four identical-size horizontal platform strips separated
by thin pure white gutters, flat side view, isolated on pure white background. Each
strip is a horizontal beam of three interwoven jungle vines and bamboo stalks, cartoon
style, thick dark outline, flat cel shading, vibrant greens. Top-left strip: fully
intact and healthy. Top-right strip: one strand snapped with splintered fibres and a
loose leaf. Bottom-left strip: two strands torn, frayed fibres, darkened gaps, wilting
leaves. Bottom-right strip: only a thin tattered stump with hanging threads and one dry
leaf. Same composition in every cell, each strip is a seamless repeating pattern of 3
identical segments, no text, no characters, no perspective, 8k game asset
```

## 4. Короткая версия (если модель режет длинный промт)

```
2D cartoon platformer platform made of three braided jungle vines and bamboo stalks,
thick dark outline, flat cel shading, vibrant green, wide horizontal strip, seamless
3-segment repeat, white background, game asset — four states: intact, one strand broken,
two strands torn and frayed, only a thin tattered stump
```

## 5. Что писать в negative prompt

```
text, watermark, logo, letters, numbers, ui, characters, faces, hands, 3d render,
realistic photo, soft blurry edges, gradients, drop shadow, background scenery, ground,
soil, grass field, perspective, isometric, tilted camera, vertical platform, diagonal,
cropped strands, strands sticking out at the ends, different composition between states
```

## 6. Технические требования к результату

| Параметр | Значение |
|---|---|
| Соотношение сторон | ~4.8:1 на каждое состояние (`1440×300` или `1408×288`) |
| Итоговая ширина после обработки | `960` px — 1 px текстуры = 1 игровая единица, как у `default` |
| Итоговая высота | производная от картинки (`960×H`), буфер считается по ней |
| Лист `2×2` (опция) | ~4.8:1 общий (`2048×448`…`2816×600`), 4 равных ячейки |
| Повторов сегмента в полосе | ровно 3, стыки незаметны |
| Фон | чистый белый (`#FFFFFF`); альфу FLUX не отдаёт — вырезать пост-обработкой |
| Контур | толстый, тёмный, замкнутый по силуэту всей сплетённой балки |
| Композиция | одинаковая во всех 4 состояниях (те же 3 стебля в тех же местах) |
| Ширина силуэта | одинаковая во всех состояниях — сжимает движок, не картинка |
| Прозрачность | не просить у модели, только пост-обработкой |

## 7. Ограничения движка (учесть при вырезании)

1. Фрагментный шейдер [`platform.fp`](platform.fp:14) SDF-обрезки **не делает**:
   форма целиком берётся из текстуры, как у `default`, `burning` и `sticky`.
   Поэтому листья и усики можно рисовать где угодно — они не отсекаются.
   Важно лишь, чтобы фон вокруг рисунка был прозрачным.
2. Меш [`platform.buffer`](platform.buffer:1) построен строго по размерам
   картинки (`tools/gen_platform_buffer.py`): ширина `960` единиц при ширине
   текстуры `960` px, высота — по высоте картинки, масштаб 1:1. Поэтому
   текстуру не нужно подгонять под `960×80` — рисуйте в тех пропорциях,
   которые нужны, а буфер пересоберите.
3. Семплер в [`platform.material`](platform.material:53) — `CLAMP_TO_EDGE`,
   тайлинг не используется: за пределы quad'а лиана не выйдет, это нормально.
4. Меш [`platform.mesh`](platform.mesh:1) указывает на одну текстуру. Для 4 состояний
   либо собрать атлас `2×2` и брать `uv`-смещение в шейдере, либо держать 4 меша /
   4 текстуры и переключать их из [`shrinkable.script`](shrinkable.script:22) в
   `start_spring()` по `self.remaining` (3 → 2 → 1 → 0).
5. Состояние 4 совпадает с `gone = 1`: коллизия уже отключена, поэтому текстуру
   можно не делать вовсе либо оставить почти пустую (лучше — пустую, чтобы
   платформа «проваливалась» без визуального обломка).
6. Пересборка текстуры и меша из исходника с белым фоном:
   `python tools/build_shrinkable_platform.py` (см. раздел 8).

## 8. Порядок работы

1. Сгенерировать 1 сегмент (~`1024×1024`): три сплетённых стебля, читаемый
   «over-under» рисунок плетения.
2. Сгенерировать полосу из 3 сегментов, проверить бесшовность стыка и ритм плетения.
3. Сгенерировать/собрать все 4 состояния с **одинаковой** композицией и шириной.
4. Сохранить сгенерированную полосу с белым фоном как
   `tools/shrinkable_platform_src.png` и выполнить
   `python tools/build_shrinkable_platform.py`. Скрипт сам:
   - вырежет белый фон (`tools/remove_white_bg.py`),
   - обрежет прозрачные поля,
   - приведёт ширину к `960` px (1 px = 1 игровая единица, как у `default`),
   - пересоберёт [`platform.buffer`](platform.buffer:1) по фактическим размерам
     картинки (`tools/gen_platform_buffer.py`): ширина `±480`, низ картинки на
     `y = -40`, верх — по высоте картинки.
5. Для 4 состояний повторить шаги 3–4 и сохранить получившиеся текстуры как
   `shrink_3.png`, `shrink_2.png`, `shrink_1.png` (и опционально `shrink_0.png`)
   рядом с [`platform.png`](platform.png).
6. Проверить в игре: при каждом касании текстура меняется вместе с пружинным
   сжатием, белого фона и обрезанных стеблей нет.
