# Промт для FLUX.2 — платформа с шипами (spike)

Базовая платформа: `main/platforms/default/platform.png` — широкая горизонтальная полоса
из 3 повторяющихся сегментов: сверху яркая трава с мелкими мультяшными цветочками
(жёлтые, розовые, фиолетовые, оранжевые), снизу — коричневая земля с камешками и
тёмным контуром. Стиль: 2D-спрайт, плоский cel-shading, толстый контур, яркие цвета.

Задача: тот же стиль, но с шипами, торчащими **и вверх, и вниз**, в мультяшном стиле.

---

## 1. Основной промт (копировать целиком, EN)

```
Cute cartoon game-asset texture, wide horizontal strip, flat side view, isolated on pure
white background. A grassy platform block: warm brown soil body (#8B5A2B) with a darker
brown outline, small pebbles and dirt speckles, the top edge covered by a bright green
grass layer with sharp grass blades and tiny cartoon flowers in yellow, pink, purple and
orange. Cartoon spikes sticking out of the platform: a row of chunky light-grey steel
cones with dark outlines, glossy highlights and rivets at the base, pointing UP out of the
grass, and a mirrored row of the same spikes pointing DOWN out of the bottom of the soil.
Spikes alternate in size — one big spike with two smaller ones between — evenly spaced,
slightly tilted for a playful look. Thick cartoon outline, flat cel shading, vibrant
saturated colors, clean vector-like shapes, crispy edges, 2D platformer sprite sheet,
seamless repeating pattern of 3 identical segments, no perspective, no cast shadows,
no text, no characters, mobile arcade platformer art, 8k game asset
```

## 2. Короткая версия (если модель режет длинный промт)

```
2D cartoon platformer platform, green grass on brown soil with pebbles, chunky grey steel
spikes sticking UP from the grass and DOWN from the bottom, thick outlines, flat cel
shading, vibrant colors, seamless 3-segment horizontal strip, white background, game asset
```

## 3. Вариант со «злыми» каменными шипами (если металл выглядит слишком «техно»)

```
... the same grassy-soil platform, but the spikes are cartoon stone spikes: light warm-grey
rock cones with rough facets, darker grey outline, tiny cracks, chipped tips, with a few
short stubby spikes mixed between the tall ones ...
```

## 4. Что писать в «избегать» (для моделей с negative prompt)

```
text, watermark, logo, letters, characters, faces, perspective, 3d render, realistic photo,
soft blurry edges, gradient background, drop shadow, isometric, tilted camera, extra limbs,
cropped spikes, busy background
```

---

## 5. Технические требования к результату

| Параметр | Значение |
|---|---|
| Соотношение сторон | ~4.8:1 (например `1408×288` или `1536×320`) |
| Повторов сегмента в полосе | ровно 3, стыки незаметны |
| Фон | чистый белый (`#FFFFFF`), альфу FLUX не отдаёт — вырезать потом |
| Контур | толстый, тёмный, замкнутый по силуэту (трава + шипы + земля) |
| Шипы | сверху **и** снизу, одинаковый ритм, симметрично относительно центра |
| Прозрачность | не просить у модели, только пост-обработкой |

## 6. Важное ограничение движка (учесть при ресайзе)

Шейдер [`main/platforms/platform.fp`](../platform.fp:37) отбрасывает всё, что выходит за
скруглённый прямоугольник `±480 × ±40` локальных единиц, а меш
[`main/platforms/platform.buffer`](../platform.buffer:7) — это quad `960×80`.
Значит, шипы, нарисованные за пределами полосы, будут **обрезаны**.

Варианты, как сохранить торчащие шипы:

1. Сгенерировать картинку с запасом по высоте и потом вписать шипы **внутрь** полосы
   (визуально короче, но безопасно) — самый быстрый путь.
2. Сделать для spike отдельный меш выше (`±480 × ±120`) и в `platform.fp` передавать
   полувысоту как uniform вместо константы `40.0`.
3. Оставить шипы отдельным спрайтом/сценой поверх платформы.

## 7. Порядок работы

1. Сгенерировать 1 сегмент (квадрат ~`1024×1024`) — так модель лучше держит детализацию.
2. Сгенерировать/собрать полосу из 3 сегментов и проверить бесшовность стыка.
3. Уменьшить до целевого размера, вырезать белый фон, сохранить как
   `main/platforms/spike/platform.png` (перезаписать текущий).
4. Проверить в игре: шипы не должны вылезать за пределы quad'а, иначе сработает discard.
