# Bumpy — арт-план v2 (после разведки по коду)

Положить в `C:\dev\bumpy\docs\BUMPY_ART_PIPELINE.md`. DeepSeek читает этот файл и `docs/GAME_FACTS.md` (его собственный отчёт по коду, см. этап 0).

**Версия 2.1. Если в разделах 1–8 есть расхождение с разделом 9 (в конце файла), главнее раздел 9.**

Правила:
1. Делаем то, что написано в ТЗ **и** то, что есть в игре (`main/levels.json`). Ничего лишнего.
2. Всё, что уже сделано сверх ТЗ и согласовано с разработчиком (раздел 10 отчёта DeepSeek: Bumpy 48 px при коллайдере 32, `HERO_SPEED`, impact-позы, замедленный squash, 4 временных AI-фона и т.д.), **не откатывать**.
3. Работаем в ветке `design-art`, в `master` не коммитим.

---

## 1. Главные решения (что изменилось после чтения кода)

| Тема | Было в моём плане v1 | Теперь | Почему |
|---|---|---|---|
| Цвет фона для вырезания | зелёный → синий | **синий #0000FF** | у Bumpy зелёные глаза |
| Холст героя | сомнение про 208×208 | **оставляем 208×208, персонаж ~104 px, нижняя точка y=155, центр x=104** | в игре визуал 96 px при контенте 48 px (208×0,0625×7,3846), 48 текущих кадров уже 208×208 |
| Анимации героя | 14 клипов по 24–30 кадров | **«лестницы поз» по фазе движения + короткие клипы только для реакций** | код сам выбирает позу по фазе (rise/fall/sq/wl/wr), а высокий прыжок длится от 0,8 до 2,3 с: фиксированный клип не подходит |
| Видео-ИИ (Kling) | запасной | почти не нужен | не нужна длительность клипа, нет альфы, лимиты и водяной знак |
| Платформы | tile kit (центр/края) | **цельные спрайты нужного размера** | платформа цельная: один меш и одна текстура, сегментов нет |
| Сердца и фрукты | «убрать» | **оставить** | в `levels.json`: heart=30, fruits=647 (12 видов), drop=57, key=207, hammer=67 |
| Параллакс и ближний слой | сомнение | **фон 1 слой, без бесшовности** (камера статична, подтверждено) | отцу сказать одной фразой: ТЗ про параллакс, но камеры нет |
| Темы | 12 | в коде 7; рисуем 12 по порядку ТЗ, DeepSeek подключает по мере готовности | распределение 100 уровней по 12 темам — вопрос к разработчику |
| Фон для 960×720 | 16:9 | **1344×768, ключевое содержимое в центральной зоне 4:3** | окно 960×720; текущий фон 1344×768 при scale 0,9375 даёт ~1260×720 и режется по бокам |

---

## 2. Анимация героя

### 2.1. Что показал код
- Bumpy — шар в ритм-механике: период прыжка **0,5 с** (0,25 вверх, 0,25 вниз), BPM 120. Отскок идёт непрерывно, значит «Anticipation», «Landing» и «Bounce» — это части одного цикла сжатия у платформы.
- Приземление: контакт мгновенный, squash 0,15 с × `SQUASH_TIME_SCALE=2.0` = **0,30 с**. Переворот на месте 0,30 с, в полёте ~0,5 с. Высокий прыжок: **0,8–2,3 с** в зависимости от препятствия.
- Рендер 60 Гц. Кадры переключаются `play_animation` одно-кадровыми анимациями; поворот и зеркало делает код (`rotation`, отрицательный scale X).
- Уже есть 48 кадров 208×208: `rest, fall1-4, rise1-3, sq1-6, tm1-2, wl1-4, wr1-4` в двух наборах `u_*` и `f_*`.
- Нет: Idle, Anticipation, Hurt, Death, Win, Collect.

### 2.2. Принцип «лестниц»
Вместо клипа по времени делаем **лестницу кадров от круглого шара до полной капли**, а код выбирает ступень по скорости или фазе. Одна лестница работает для любого прыжка (0,5 с или 2,3 с).

| Лестница | Кадров (старт) | Содержание | Выбор ступени |
|---|---:|---|---|
| Rise (взлёт) | 8 | круглый → вытянутая капля, острый кончик вверх, глаза широкие | по `vy / JUMP_SPEED` |
| Apex | 2 | в верхней точке форма снова почти круглая | у вершины |
| Fall (падение) | 8 | капля кончиком вверх, вытягивание растёт со скоростью, испуганное лицо | по скорости падения |
| Impact squash | 8 | касание → сплющивание с боковым «разливом» → отскок с перелётом (overshoot) → затухание (settle) | по времени 0,30 с |
| Side (бок) wl/wr | 6 на сторону | капля под наклоном, кончик отстаёт от движения; лево — зеркало право | по фазе бокового прыжка |
| Flip 180° | — | поворот спрайта кодом, лицо «вверх ногами» | `rotation` |
| Idle | 16 (цикл) + 4 моргание | дыхание, покачивание | по времени |
| Hurt | 12 | сжатие, гримаса, дрожь | по времени |
| Death | 24 | сдувание → расплющивание → исчезновение | по времени |
| Win | 24 (цикл) | радостные прыжки, блеск | по времени |
| Collect | 12 | быстрое сжатие, радость, искры | по времени |

Числа стартовые, их корректирует пилот. DeepSeek обязан выяснить (этап 0), какие именно переменные кода выбирают `rise/fall/sq/tm/wl/wr` и что такое `tm` и `f_*`.

### 2.3. Как делать кадры (пилот двух способов, выбираем глазами в игре)

**Способ A — скрипт-деформация одного изображения.** Из утверждённого Bumpy (P1) скрипт делает каплю: верх сужается до кончика, низ круглый, объём сохраняется (scale_x · scale_y ≈ 1), лицо остаётся в круглой части и меняет вариант (спокойное / широкие глаза / испуг / зажмурен). Сплющивание у платформы: ширина растёт, высота падает, «бока» чуть выпучиваются, верх запаздывает. Плюсы: герой идентичен, 0 кредитов, правки за минуты. Минус: блики и контур деформируются «математически».

**Способ B — ключевые позы от нейросети + интерполяция.** Один лист ~9 поз одного Bumpy (промт P3) → вырезать → промежуточные кадры строит RIFE (`rife-ncnn-vulkan`, работает на GTX 1660 SUPER через Vulkan) → лестницы. Плюсы: капля «нарисована», блик живой. Минусы: позы разнятся размером и бликом (нормализуем скриптом), у интерполяции бывают «призраки».

**Критерий выбора:** оба набора для лестниц Rise / Fall / Impact подставить в **тестовую копию** (`bumpy_test.atlas`, переключатель в `heroes.lua`), запустить в реальном размере 48 px и сравнить. Побеждает тот, где форма капли читается и нет мерцания. Можно смешать: тело по A, лица по B.

**Честная оценка:** «рисованного Диснея» ИИ не гарантирует, но у шара простая форма, а в игре он 48 px. На такой размер хорошо читаются **форма капли, тайминг и лицо**, а не текстура.

---

## 3. Размеры ассетов (по коду)

Рисуем в **4× от игрового размера** (для hi-dpi), потом DeepSeek уменьшает до нужного.

| Ассет | Сейчас в игре | Авторский размер (аспект!) | Примечание |
|---|---|---|---|
| Bumpy (кадр) | 208×208 → 48 px контента | 208×208, шар ~104 px, низ y=155, центр x=104 | как у текущих 48 кадров |
| Платформа default/sticky/burning | текстура 960×200 → показ **140×50** | **560×200** | сейчас картинка 960×200 сжимается неравномерно (x×0,146, y×0,25): рисуем сразу в видимом аспекте и ставим scale 1:1 |
| Shrinkable | 960×152 → 140×38 | 560×152 | |
| Burning+sticky, Spike | 960×256 → 140×64 | 560×256 | |
| Наклонные left/right | отдельные прототипы | размер выяснить (этап 0) | |
| Стена разрушаемая (cracked/broken/destroyed) и неразрушаемая | 64×280 | размер показа выяснить | |
| Border | 32×64 | | |
| Кирпичная кладка | block.png 1193×1310, 8 рядов | размер показа выяснить | |
| Предметы (drop, key, hammer, heart, 12 фруктов) | 32×32 | 128×128 (или 256) | |
| Выход | 240×160 (closed/open) | 480×320 | |
| Фон | 1344×768 | 1344×768 | центр 4:3 спокойный и без контраста |

Видимая платформа 140×50 при поле 960×640 очень мала: детали должны быть **крупными и простыми**.

---

## 4. Нейросети и бюджет

Проверено поиском в октябре 2026, цифры меняются: сверяй цену на кнопке Generate.

- **Leonardo (основной):** 150 токенов в день без накопления; на своих моделях (Phoenix/Lucid) выходит заметно больше картинок, чем при 40 токенах за «Gemini»-картинку. Бесплатные генерации публичные; коммерческие условия сверить в правилах Leonardo.
- **SeaArt (запасной):** ~150 stamina в день (~21 картинка), на бесплатном плане водяные знаки и «для личного использования» по обзорам.
- **Kling:** 66 кредитов в день, водяной знак, личное использование. Для лестниц не нужен.
- **Локально:** GTX 1660 SUPER (6 ГБ), 32 ГБ RAM. SDXL/ComfyUI потянет, но для новичка тяжело. Берём только как запасной вариант. RIFE на этой видеокарте работает.
- **ffmpeg не установлен:** нужен для RIFE и сборки; ставит DeepSeek (`winget install Gyan.FFmpeg`) после моего «ок».

**Сколько генераций:** герой 2–3, лист поз 1–2, мир по 4 (фон, платформы, шипы+склоны, декор) × 12 = 48, общие объекты 8–10 (стены, кладка, выход, предметы, 12 фруктов, эффекты). Итого ~65–70 без неудачных.

**Порядок:** (1) цена картинки в Leonardo → (2) P1 герой → (3) P2 лист → (4) P3 лист поз → (5) пилот лестниц A и B → (6) концепт-набор: платформа, шипы, серая стена, фон → (7) мир «Солнечный» → (8) остальные по приоритету ТЗ: ночь, зима → осень, хэллоуин → япония, пустыня, космос → дождь, рождество, индустриальный, тропики → (9) общие объекты и эффекты. Первая картинка каждой новой темы — только фон-тест.

---

## 5. Промты

Язык: английский. В Leonardo: Image Guidance → Character Reference / Style Reference (чистый Bumpy и обложка 3008). Модель: Phoenix/Lucid или другая своя; seed фиксировать, 1 картинка за раз.

### STYLE LOCK (в начало всех промтов с героем)

```
Bumpy: a round glossy bright red ball character with a perfectly spherical body, smooth red (#E8261C) with soft darker red shading at the bottom-right and a soft white highlight at the top-left, thin dark-red outline. Four short thick curved brown hair strands in a row lying along the top of the head (small comma-like strokes, not curls). Big round white eyes with green irises, black pupils and tiny white highlights. Wide open happy smile with a pink tongue. No arms, no legs.
Style: smooth glossy 2.5D cartoon mobile game art, soft gradients and volumetric lighting, saturated colors, clean readable shapes, expressive and bouncy, in the spirit of Cut the Rope. Not pixel art, not flat vector, not photorealistic.
```

### STYLE LOCK ENV (в начало всех промтов окружения)

```
Smooth glossy 2.5D cartoon mobile game art, thin dark outline, soft top-left light, saturated but balanced colors, big simple readable shapes (the asset is shown very small in game), consistent with a bright casual mobile platformer. No text, no characters.
```

### Negative (общий)

```
text, letters, watermark, logo, UI, frame, border, floor, ground, cast shadow on background, scenery, multiple characters, extra eyes, deformed face, cross-eyed, arms, legs, photorealistic, anime, manga, horror, blurry, noisy edges, cropped, cut off, different colors, different eye color, missing or extra hair tufts
```

### P1. Чистый Bumpy (1 генерация)

```
[STYLE LOCK]
Single full-body character, front view, neutral happy expression, centered, filling about 70% of the frame, floating (no floor), on a perfectly flat pure blue background #0000FF, no shadow, no gradient in the background, no text. High quality, clean edges.
```
1:1, Character Reference = обложка 3008.

### P2. Модельный лист (1 генерация, после утверждения P1)

```
Character reference sheet of the same character, clean 4 columns by 2 rows grid on a flat pure blue background #0000FF.
Top row: the ball turned to show the face front, face turned 30 degrees left, face turned 30 degrees right, and the back of the head (no face, only the four brown hair tufts and shading).
Bottom row: face close-ups, same head size: happy, scared (round open mouth, wide eyes), hurt (squinted eyes, grimace), dizzy (spiral eyes).
Identical design, identical scale, centered in every cell, no cast shadows, no text, no labels.
[STYLE LOCK]
```

### P3. Лист ключевых поз (способ B; 1–2 генерации)

```
Animation key pose sheet of the same character, 3 columns by 3 rows grid on a flat pure blue background #0000FF, every pose centered in an equal cell, same scale, no floor, no cast shadows, no motion lines, no text:
1) perfectly round, calm smile;
2) slightly stretched upward, eyes a bit wider;
3) strongly stretched into a teardrop / water-drop shape with a pointed tip at the top, wide excited eyes, round lower body;
4) falling teardrop with the pointed tip at the top, scared face, mouth round and open;
5) perfectly round at the top of a jump, relaxed happy face;
6) stretched teardrop just before impact, eyes squeezed, worried face;
7) maximum squash: very flat and wide like a puddle-bulge, eyes squeezed shut, mouth wide;
8) rebound: slightly taller than round, overshoot, happy surprised face;
9) settling back to round, smiling.
The body volume stays the same in all poses, the four brown hair tufts and green irises stay identical.
[STYLE LOCK]
```
Если сетка кривая — не перегенерируй: пришли как есть.

### P4. Платформы мира (1 генерация на мир)

Листы с **отдельными цельными** платформами, не тайлами:

```
2D platformer platform sprites, side view, flat pure blue background #0000FF, each piece separate with wide spacing, all the same wide rectangular proportion (about 2.8 : 1, width to height), equal size:
1) normal platform: {PLATFORM_TOP} on top, {PLATFORM_SIDE} underneath;
2) sticky platform: same shape, covered with glossy sticky goo, slightly gummy look;
3) shrinkable platform: same shape, made of fragile segmented material, looks like it can wear away;
4) burning platform: same shape with glowing cracks, charred, ready for flames on top;
5) burning sticky platform: sticky goo mixed with ember glow.
Top surface clearly lighter than the side so the standing surface reads at small size. [STYLE LOCK ENV]
```

### P5. Шипы и склоны мира (1 генерация на мир)

```
2D platformer hazards and slopes on a flat pure blue background #0000FF, separate pieces with wide spacing:
1) spike platform: a wide base strip with a row of sharp {SPIKES} on top, aspect about 2.2 : 1;
2) the same spike platform with fewer, larger spikes;
3) slope platform rising to the right, same material as the normal platform: {PLATFORM_TOP} on top, {PLATFORM_SIDE} underneath;
4) the mirrored slope falling to the right.
Sharp triangular silhouettes that are clearly dangerous and different in shape from every platform. [STYLE LOCK ENV]
```

### P6. Фон мира

```
Horizontal 16:9 background for a 2D mobile platformer, {BG}. Layered depth: distant sky, soft mid-ground shapes, calm composition. Gentle soft focus and low contrast everywhere gameplay happens: the whole central area and lower two thirds; the main interest and brighter details only near the left and right edges. No characters, no platforms, no UI, no text, nothing sharp or high-contrast in the middle. [STYLE LOCK ENV]
```

### P7. Декор мира (1 генерация)

```
Decor set on a flat pure blue background #0000FF: separate small items with wide spacing, same style and scale: {DECOR}. [STYLE LOCK ENV]
```

### P8. Общие объекты (один раз; тематические варианты потом)

- **Серая разрушаемая стена** (в коде durability 3/2/1; файлы cracked/broken/destroyed; размер 64×280, вертикальный): лист 4 состояния — целая, трещины, сильно разбита, разрушена с осколками.
- **Неразрушаемая стена** и **border** (стеклянный край 32×64): один лист.
- **Кирпичная кладка** (8 рядов, состояния целая / сломаны ряды / разрушена).
- **Выход:** закрыт / открыт / активация (по темам: портал, дверь, арка).
- **Предметы** 32×32 в игре: drop, key, hammer, heart и **12 видов фруктов** (список видов — из `main/goodies/fruit/`).
- **Эффекты** (спрайты-частицы для Defold ParticleFX): пыль, искра, осколок, дым, пламя, снежинка, капля, лист, свечение. Горящая платформа: 6–8 кадров пламени, свечение, дым.

Шаблон листа состояний:
```
Game asset sheet on a flat pure blue background #0000FF: {OBJECT} in {N} states left to right: {STATES}. Same size and framing in every cell, no text. [STYLE LOCK ENV]
```

### Таблица миров (подстановка в P4–P7; ТЗ раздел 4)

| № | Мир | {BG} | {PLATFORM_TOP} / {PLATFORM_SIDE} | {SPIKES} | {DECOR} |
|---|---|---|---|---|---|
| 1 | Солнечный день | blue sky, white clouds, rolling green hills, round trees, flowers | bright green grass / warm brown soil with stones and roots | grey metal spikes | roots, stones, flowers, grass tufts |
| 2 | Дождь и гроза | dark rain clouds, puddles, wet trees, rain | dark wet grass / wet soil, wet stone, wooden planks | dark wet metal spikes | puddles, wet stones, wet roots |
| 3 | Ночь | stars, big moon, fireflies, tree silhouettes | dark grass / dark soil and bluish stones with cold highlights | dark steel spikes with cold blue highlights | glowing mushrooms, bluish stones, roots |
| 4 | Зима | snowy hills, fir trees, snowdrifts, snowflakes | snow on top / frozen soil, ice, frozen stones | ice crystal spikes | snow lumps, icicles, frozen stones |
| 5 | Рождество | christmas trees, garlands, gifts, snowy houses | snow ledges / wooden planks, ice, warm lights | candy-cane striped spikes | gift boxes, lights, snow lumps |
| 6 | Хэллоуин | purple sky, pumpkins, fog, moon, bare trees | dark soil with dry roots / stone, mystic flame | bone-like dark spikes | pumpkins, dry roots, small mystic flames |
| 7 | Япония | Mount Fuji, pagodas, sakura, lanterns, small bridges | wooden planks / stone base, bamboo, petals | stone / bamboo spikes | lanterns, petals, bamboo, stones |
| 8 | Пустыня | dunes, rock formations, cacti, dry plants | sand / sandstone, rock ledges, cracks | bone / stone spikes | cacti, dry bushes, cracked stones |
| 9 | Космос | planets, stars, nebulae, asteroids, space stations | metal panel with glowing energy strip / asteroid rock | metal / energy spikes | crystals, antenna, small asteroids |
| 10 | Индустриальный | factories, pipes, tanks, steam | metal grate / rusty beams, concrete | rusty metal spikes | gears, pipes, rivet plates |
| 11 | Осень | golden trees, red leaves, mushrooms | dry grass and leaves / roots, moss | dry wood / metal spikes | leaves, mushrooms, mossy roots |
| 12 | Тропики | palm trees, jungle, islands, waterfalls | sand and jungle plants / wet soil, roots, mossy stones | thorny plant / stone spikes | palm leaves, roots, mossy stones, shells |

DeepSeek собирает 4 промта на мир из шаблонов P4–P7 скриптом (этап 3).

---

## 6. Чек-лист приёмки (проверяешь ты глазами: DeepSeek не видит)

**Герой:** красный шар, четыре коричневых хохолка, зелёные радужки в белых глазах, большой улыбающийся рот; нет рук и ног; не «капелька» в покое; одинаковые цвет и размер во всех ячейках; фон ровный синий.

**Лестницы поз (пилот):**
- Читается ли капля с острым кончиком на 48 px в игре, а не на просмотрщике.
- Объём не «надувается» между ступенями; лицо читается в каждом кадре.
- Центр и нижняя точка не гуляют; нет мерцания цвета, дублей, обрезки по краю.
- Прыжок 0,5 с и высокий прыжок 2 с выглядят одинаково хорошо (одна лестница на оба).
- Сплющивание у платформы не создаёт ложного впечатления, где мяч относительно платформы (ТЗ раздел 2.3).

**Платформы:** на 140×50 видно верх и бок; шипы читаются по форме; склон читается по направлению; нет текста и теней на фоне.

**Фон:** центр спокойный; нет персонажей и платформ; стиль и яркость как у обложки 3008 (старые «лес» и «индустриальный» слишком тёмные: перегенерировать).

**Технически (числа даёт DeepSeek):** одинаковый размер кадра, нет синей каймы, нет пикселей на краю холста, прозрачность есть.

---

## 7. Задание для DeepSeek (копировать в Kilo Code по этапам)

> Прочитай `docs/BUMPY_ART_PIPELINE.md` целиком, а также ТЗ `Bumpy_TZ_Design_Animation_RU.docx`. Ты не видишь изображения: не оценивай «похоже ли на героя», только измеряй, режь, собирай и интегрируй. Работай этапами. После каждого этапа покажи отчёт и жди моего «ок». Работаем в ветке `design-art`. Не откатывай то, что уже согласовано с разработчиком (раздел 10 твоего отчёта), не трогай геймплей и коллизии, не удаляй мои исходники.

### Этап 0 — второй раунд разведки (читать, единственная запись: файл отчёта)
1. Сохрани свой предыдущий отчёт по коду в `docs/GAME_FACTS.md`.
2. Добавь туда ответы на вопросы ниже:
   - **Выбор кадров Bumpy.** Покажи фрагменты `hero_bumpy.lua`, которые выбирают `rest, rise1-3, fall1-4, sq1-6, tm1-2, wl1-4, wr1-4`: по какой переменной (скорость, время, фаза) выбирается кадр, и что означают `tm` и префиксы `u_` и `f_`. Ответь для каждой группы: сколько миллисекунд (или какой диапазон скорости) приходится на кадр.
   - **Мгновенность прыжка.** Начинается ли прыжок сразу по команде, и входит ли приседание перед отрывом в squash предыдущего приземления.
   - **Размеры показа:** для склонов (`/main/platforms/sloped/*.go`), стен (destructible, indestructible, border, block.png с 8 рядами), предметов (32×32 при каком scale), выхода: размер на экране в пикселях и scale.
   - **Темы.** Для чего используется `theme_table` (7 цветов): тонирует ли он платформы или стены? Как подключается тема к `background.script` и платформам? Сколько работы нужно, чтобы поддержать 12 тем (какие файлы менять)?
   - **Фрукты:** список 12 видов (имена файлов).
   - **Каналы Defold:** где сейчас можно переключить набор кадров Bumpy на тестовый (`heroes.lua`), чтобы сравнить старый и новый наборы без удаления старого.
   - **Defold-сжатие и атласы:** какие настройки сжатия текстур включены сейчас.
3. Проверка: `git status` показывает только новый/изменённый `docs/GAME_FACTS.md`; покажи итоговый список ответов.

### Этап 1 — каркас и инструменты
1. Создай структуру папок из раздела 7.3 ТЗ в `assets/` (с `.gitkeep`) и поддиректории `art_inbox/03_hero_anim/A/` и `.../B/`.
2. Единый цвет ключа везде **синий #0000FF**: исправь `art_inbox/README.md` и `PROMPTS.md` (замени «зелёный/#00FF00/#FF00FF»). В PROMPTS.md удали «droplet», «no outline», «cool blue rim light» и подставь STYLE LOCK из этого файла.
3. Установи ffmpeg (`winget install Gyan.FFmpeg`), проверь: `ffmpeg -version` печатает версию. Скачай `rife-ncnn-vulkan` в `tools/rife/`, проверь запуск `tools\rife\rife-ncnn-vulkan.exe -h` (должна напечататься справка). Скажи, если сеть блокирует загрузку.
4. Скрипты в `tools/` (Python + Pillow/OpenCV/numpy):
   - `chroma_key.py`: убрать фон #0000FF с мягким краем и despill (убрать синюю кайму), на выходе RGBA PNG.
   - `normalize_frames.py`: общий холст 208×208, нижняя точка шара в y=155, центр x=104, шар не обрезается, один pivot.
   - `validate_frames.py`: таблица по каждому кадру (bbox, центр X, низ Y, непрозрачные пиксели на краю, остатки синего) и вердикт OK/FAIL.
   - `contact_sheet.py`: все кадры в сетку с номерами.
   - `warp_ladder.py` (способ A): из `bumpy_clean.png` строит лестницы Rise (8), Apex (2), Fall (8), Impact squash (8), Side (6): деформация «капля» с сохранением объёма, смена варианта лица, перелёт и затухание.
   - `build_sheet.py`: пакует кадры в sprite sheet + JSON (размер листа и кадра, число кадров, FPS, pivot) по разделу 7.2 ТЗ.
   - `make_prompts.py`: собирает 4 промта на мир (P4–P7) из таблицы миров этого файла в `prompts/world_XX_<name>.md`.
5. Проверка: `python tools\validate_frames.py <папка>` на тестовых кадрах печатает таблицу и `OK`; `dir prompts` показывает 12 файлов по 4 блока.

### Этап 2 — пилот лестниц (по моей команде)
1. Когда я положу `art_inbox/01_hero_design/bumpy_clean.png`: вырезать фон, нормализовать, построить способ A (`art_inbox/03_hero_anim/A/`). Показать `contact_sheet` и таблицу `validate`.
2. Когда я положу `art_inbox/02_hero_poses/keyposes_sheet.png`: вырезать 9 поз, нормализовать, достроить лестницы RIFE (`.../B/`). Тоже `contact_sheet` и `validate`.
3. Подключить **тестовые** наборы A и B как `bumpy_test_a.atlas` / `bumpy_test_b.atlas` с переключателем в `heroes.lua` (старый набор не удалять). Сборка и запуск уровня в Defold: сообщи, как запустить.
4. Проверка: игра запускается с каждым из трёх наборов (старый, A, B); я решаю глазами.

### Этап 3 — платформы и концепт-набор (после пилота)
По моей команде: нормализовать картинки платформ, шипов, склонов и серой стены, подготовить текстуры в видимом аспекте (560×200 и т.д.), заменить временные кропы тайлов, поставить scale 1:1. Проверить, что коллизии не изменились.

### Этап 4+ — мир «Солнечный», остальные миры, общие объекты, эффекты, документация, демо-сцена
Только по моей команде и в порядке ТЗ (раздел 9.1). Подключение новых тем (12 вместо 7) в `levels.json` и `theme_table` — только после согласования с разработчиком.

### Запреты
Не придумывать ассеты и механики вне ТЗ и `levels.json`; не коммитить в `master`; не менять коллайдеры; не оценивать картинки «на глаз».

---

## 8. Риски

- **Дрейф персонажа между генерациями:** один Character Reference, один seed, один STYLE LOCK; героя утверждаем один раз.
- **Синяя кайма после вырезания:** despill в скрипте; в промте героя нет синей подсветки.
- **«Призраки» RIFE и мерцание:** проверка `validate` + просмотр в игре на 48 px.
- **Обрезка при растяжении:** холст с запасом; validate ловит пиксели на краю.
- **Лимиты и лицензии:** токены не копятся; на бесплатных тарифах SeaArt/Kling водяные знаки и «личное использование»; условия Leonardo (коммерческое использование, публичность) сверить, при необходимости оплатить месяц-два интенсивной работы.
- **Исходники со слоями (ТЗ 7.1):** при AI-only путь даёт PNG и скрипты, а не PSD со слоями. Уточнить у отца, годится ли.
- **Расхождение ТЗ и игры:** 12 тем в ТЗ против 7 в коде, параллакс в ТЗ против статичной камеры. Решает заказчик; мы фиксируем решение в `docs/GAME_FACTS.md`.


---

## 9. Статус и поправки (версия 2.1, главнее разделов 1–8)

### 9.1. Статус
- **P1 готов:** `bumpy_clean` (Bumpy на синем #0000FF, 4 хохолка, сделан в Gemini через Leonardo с референсом `bumpy_ref_crop.png`). Лежит в `art_inbox/01_hero_design/`. Если Leonardo даёт скачать PNG, брать PNG: на JPG у краёв бывает кайма при вырезании.
- **Следующая генерация: P3** (лист из 9 ключевых поз). Лист из 4 видов (P2) пока пропускаем: хватает обложки, листов выражений и P1.
- Phoenix для героя **не использовать**: игнорирует референс и фон. Gemini (40 токенов) для героя, Phoenix/SeaArt для окружения.

### 9.2. Какая нейросеть для чего (лимиты Leonardo: 150 токенов в день, Gemini 40, Phoenix 18)
| Что | Чем | Почему |
|---|---|---|
| Герой: P3 лист поз, лист «реакций» (hurt, death, win, collect, idle-лица) | **Gemini в Leonardo (40)** | нужно точное повторение референса |
| Лестницы анимации (rise/fall/sq/wl/wr) | **скрипт, 0 токенов** (способ A); RIFE только если нужен способ B | нейросеть не нужна |
| Фоны, платформы, шипы, склоны, стены, декор, предметы, эффекты | **Phoenix (18)** или **SeaArt (~150 stamina в день)** | точное копирование героя не нужно; дешевле |
| Видео-ИИ | не используем | |

Правила экономии: одна тестовая картинка на новую тему; листы вместо одиночных картинок; кривую сетку не перегенерировать, присылать как есть; фон-тест на Phoenix и на SeaArt одним и тем же промтом, берём лучший.
Оценка: герой P3 + «реакции» = 2–4 генерации по 40 = 1–2 дня. Мир = 4 генерации по 18 = 72 токена, около 2 миров в день на Phoenix. 12 миров ≈ 6 дней без повторов, ~2 недели с повторами. SeaArt ускоряет.

### 9.3. Пилот лестниц: ровно те же количества кадров, что в коде
По отчёту `docs/GAME_FACTS.md`: `rise` 3, `fall` 4, `sq` 6, `tm` 2, `wl/wr` по 4 (+ `rest`). Имена и порядок как в текущем наборе, `sq6` = кадр сразу после касания, `sq1` самый поздний. Тогда новые кадры встают без изменений в `hero_bumpy.lua`. Больше ступеней (раздел 2.2) добавляем только если в пилоте видна «ступенчатость».
Наборы `u_*` (обычный) и `f_*` (после переворота 180°): делаем оба.

### 9.4. Поправки к заданию для DeepSeek (раздел 7)
- Этап 1, пункт 0: **сначала** закоммитить согласованные незакоммиченные изменения отдельным коммитом в `design-art`, потом работать.
- Скопировать этот файл из `C:\dev\bumpy-art\` в `docs/`.
- **RIFE пока не ставить** (нужен только для способа B). ffmpeg ставить.
- Исходник героя: `art_inbox/01_hero_design/bumpy_clean.*` (png или jpg). Референс: `bumpy_ref_crop.png` там же.

### 9.5. Актуальный промт P3 (Gemini; приложить `bumpy_clean` как референс)
```
Use the attached approved character image as the exact reference for every pose: same red ball, same thin dark-red outline, same white eyes with green irises, same wide smile with pink tongue, same four short brown hair strands on top, same colors and style. Create an animation key pose sheet of this same character: 3 columns by 3 rows grid, 9 poses, every pose centered in its own equal square cell, on a perfectly flat solid pure blue #0000FF background, no gradient, no ground, no floor, no cast shadows, no motion lines, no text, no labels. The face looks slightly up and to the right like in the reference, unless the pose says otherwise.
Poses, left to right, top to bottom:
1) perfectly round, calm happy smile;
2) slightly stretched upward into an egg shape, eyes a little wider;
3) strongly stretched into a water-droplet (teardrop) shape: round lower body, smooth taper to a pointed tip at the top, hair strands sitting on the tip, wide excited eyes, open mouth;
4) falling: teardrop with the pointed tip at the top, scared face, round open mouth, wide eyes;
5) perfectly round at the top of a jump, relaxed happy face;
6) stretched teardrop just before impact, eyes squeezed, worried face;
7) maximum squash: very flat and wide like a bulging puddle-pancake, eyes squeezed shut, mouth wide open;
8) rebound: slightly taller than round, overshoot, happy surprised face;
9) settling back to a round shape, smiling.
The body volume stays the same in every pose. The round poses (1, 5, 9) all have the same ball size. Smooth glossy 2.5D cartoon mobile game art.
```
