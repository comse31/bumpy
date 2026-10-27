# GAME_FACTS — разведка по коду Bumpy

Дата: 2026-10-27.
Ветка: `design-art`. Последний коммит: `cad25a7 add bumpy hero`.
Отчёт составлен только чтением репозитория. В этом этапе записан только этот файл.

## 0. Источники и расхождения

- `docs/BUMPY_ART_PIPELINE.md` в репозитории **не найдено**. Файл прочитан по фактическому пути:
  `C:\dev\bumpy-art\BUMPY_ART_PIPELINE.md`.
- Art-ТЗ: `C:\dev\bumpy-art\Bumpy_TZ_Design_Animation_RU.docx`.
- Общее ТЗ геймплея: `tz.txt` (6x6, 100 уровней, механики).
- Расхождение стиля: pipeline задаёт целевой STYLE LOCK (круглый красный шар,
  три коричневых хохолка, зелёные радужки). В коде используется текущий набор
  `main/bumpy/frames/*.png` (48 кадров 208x208). Совпадает ли он визуально —
  не оцениваю (не вижу изображения). До утверждения стиля ничего не менять.
- Расхождение ТЗ и кода: в art-ТЗ 12 миров, в `levels.json` 7 тем; в ТЗ параллакс,
  в коде камера статична. Решение за заказчиком.

---

# 1. Игровое окно и сетка

- `game.project`: display width=960, height=720, high_dpi=1.
- Отдельного поля `orientation` нет; по размерам окно горизонтальное.
- Масштабирование: `[html5] scale_mode=stretch`; в рантайме
  `main/render/projection.script` включает `use_fixed_fit_projection` (near=-1, far=1).
- Целевые платформы: явного списка не найдено. Есть секции `[html5]` и `[android]`;
  фактически проект рассчитан на HTML5/десктоп, мобильный ввод заложен.
- Поле уровня: 960x640 (`SCREEN_W`/`SCREEN_H` в `ball.script`), сверху HUD-полоса 80 px
  (всего 720). Сетка 6x6.
- `CELL_W = 960/6 = 160`, `CELL_H = 640/6 = 106.6667` world units.
- 1 world unit = 1 px при scale 1; physics scale = 0.01 (100 px/м).
- Игровая платформа: 140x20; визуальный меш платформы 140x50 (см. раздел 7).

# 2. Камера

- Камера статична. Camera GO нет, follow/scroll/zoom не найдено.
- `main/render/projection.script` только переключает fixed-fit projection.
- Уровни 6x6 целиком на одном экране; движения камеры на всех уровнях нет.

# 3. Bumpy сейчас

- Нарисован спрайтом/атласом: `main/bumpy/bumpy.atlas` + `bumpy.sprite`;
  48 кадров 208x208 (24 позы `u_*` и 24 позы `f_*`).
- Кадры переключаются `msg.post(VISUAL.."#sprite", "play_animation")`; это
  покадровые одно-кадровые анимации, не таймлайн.
- Размер: `TARGET_PX = 32 * 1.5 = 48` px контента (`hero_bumpy.lua:15`).
  Визуальный квад 208 * 0.0625 * 7.3846 = 96 px; видимый контент 48 px.
- Коллизия: `SIZE=32`, `RADIUS=16` (`ball.script:9,23`). Визуал 48 px больше
  коллайдера 32 px.
- В коде есть поворот `go.set(self.visual, "rotation", quat_rotation_z(...))`,
  масштаб `go.set(VISUAL.."#sprite","scale",...)` (включая отрицательный X для
  зеркала), позиция `go.set_position`. `go.animate` не найдено.
- Процедурно: flip/поворот, зеркало, impact-позы, in-place flip; деформация — кадрами
  `sq/fall/rise/tm/wl/wr`.
- Уже есть кадры: `rest, fall1-4, rise1-3, sq1-6, tm1-2, wl1-4, wr1-4` в наборах
  `u_*` и `f_*` (48 всего).
- Нет: Idle, Anticipation, Hurt, Death, Win, Collect; нет 30-кадровых секвенций;
  нет финального TZ-арта.
- Для сравнения: ball hero — `football.png` 512x512 + squash через `go.set scale`;
  Slinky — кольца `ring.png` 256x160.

# 4. Тайминг (числа из кода)

Ключевые константы `main/ball/ball.script`:

```lua
SIZE = 32.0
BPM = 120.0
HERO_SPEED = 1.0
PERIOD = 60.0 / BPM * HERO_SPEED          -- 0.5
HEIGHT = 1.5 * SIZE                        -- 48
GRAVITY = 8.0 * HEIGHT / (PERIOD^2)       -- 1536
JUMP_SPEED = GRAVITY * PERIOD * 0.5       -- 384
HIGH_JUMP_HEIGHT = CELL_H + HEIGHT        -- 154.6667
HIGH_JUMP_SPEED = sqrt(2*GRAVITY*HIGH_JUMP_HEIGHT) -- ~689.3
SQUASH_DURATION = 0.15
MOVE_DURATION = 0.25
```

- Обычный отскок/прыжок вверх: полный цикл 0.5 с; вверх 0.25 с, вниз 0.25 с.
- Боковой прыжок: `move_duration = t_land` (`landing_time`), обычно ~0.5 с;
  fallback `MOVE_DURATION=0.25`.
- Высокий прыжок: фиксированной длительности нет, зависит от препятствия/колонки
  (`high_jump_touch_time`). Для пустой колонки от нижнего ряда до верхнего края:
  подъём ~1.43 с, падение ~0.87 с, всего ~2.29 с. Если платформа на ряд выше:
  ~0.34 с вверх + ~0.46 с вниз, всего ~0.8 с.
- Падение: обычно 0.25 с с обычной высоты; при высоком прыжке — переменное.
- Приземление: контакт мгновенный; визуальный squash 0.15 с (`SQUASH_DURATION`),
  у Bumpy `SQUASH_TIME_SCALE=2.0` → 0.30 с.
- Отскок: период 0.5 с; отскок от стены/блока — `landing_time`, обычно ~0.5 с.
- Переворот 180°: в полёте = `move_duration` (обычно ~0.5 с); на месте
  `REST_FLIP_TIME=0.30` с.
- Второй прыжок: тот же боковой прыжок, ~0.5 с.
- Дополнительно: `THRESHOLD=0.1` с, `CONTACT_DEDUP=0.1`, `CONTACT_GUARD=0.05`,
  `TOUCH_CMD_TIMEOUT=0.7`; `IMPACT_TIME=0.22`; `CEILING_BOUNCE=280` px/s.
- Логика: physics `fixed_update_frequency=120` Гц; скрипты/рендер — дефолт Defold
  60 Гц (частота в `game.project` не задана); `max_time_step=0.0333`.

# 5. Объекты и механики из main/levels.json (100 уровней)

Коды слоя `lo`: 1=389, 2=263, 3=169, 4=486, 5=94, 6=158, 7=160, 8=40, 9=30,
10=144, 12=248.

Коды слоя `hi`: 1=153, 2=46, 3=190, 4=326; border-стены спавнятся по 12 на уровень
(1200 всего).

Объекты: hammer=67, key=207, drop=57, heart=30, fruits=647 (36 кодов 5..40,
12 спрайтов фруктов), всего 1008.

- Обычная платформа: 389; состояние — визуальный bend при приземлении, логики
  состояния нет.
- Shrinkable (исчезающая): 918 всего (263+169+486); durability=3, initial_hits
  (коды 3/4), scale, gone; состояния целая/уменьшенная/исчезла, коллизия
  отключается.
- Sticky (липкая): 94; `sticky=1`; мяч лежит (`sticky_rest`), одно действие за
  касание; высокий прыжок только в момент первого касания, пока лежит — нельзя.
- Наклонная: 318 (158 left + 160 right); `direction ±1`; после падения
  неуправляемый отскок по склону.
- Горящая: 40; `burning=1`; при контакте без капли — смерть; с каплей — extinguish,
  меш меняется на безопасный.
- Горящая+липкая: 30; после гашения `sticky_after=1`, становится липкой.
- Кирпичная кладка: 144; `rows=8`, `broken` (ряды), `destroyed`; удар снизу,
  расход молотка.
- Шипы: 248; `spike=1`; контакт — потеря жизни.
- Разрушаемая серая стена: 389 (hi 1/2/3 = 153/46/190); durability 3/2/1,
  `destroyed`; стадии cracked/broken/разрушена.
- Неразрушаемая стена: 326 (hi=4); состояния нет.
- Border (стеклянные края): 1200; статичные, неразрушимые.
- Выход: 1 на уровень (100); closed/open; спрайт выключен до open.
- Goodie collectible: фабрика есть, но в `goodie_factory` не используется —
  в `levels.json` отдельного кода не найдено.
- Состояния goodies: idle/collected; фрукты 12 видов, анимация по `kind`.

# 6. Уровни, темы, фон

- Уровней: 100 (`level_count=100`).
- Тем: 7. Распределение: 1=15, 2=15, 3=14, 4=14, 5=14, 6=14, 7=14.
  В ТЗ 12 — в коде 12 тем не найдено.
- Выбора темы игроком нет: theme берётся из level data
  (`state.theme = lvl.theme or 1`).
- `theme_table`: 7 цветов (палитры) в `levels.json`.
- Фон: 4 плоских спрайта в `main/background` (bg_beautiful/cosmic/magic/industrial),
  по одному на темы 1..4; темы 5..7 без фона.
- `background.script` включает нужный спрайт по `state.theme`.
  GO: position (480,360), z=-0.9, scale 0.9375. Слоёв/параллакса нет — 1 слой.

# 7. Платформа

- Текстуры: default 960x200, sticky 960x200, shrinkable 960x152, burning 960x200,
  burning_sticky 960x256, spike 960x256; block.png 1193x1310.
- Меш платформы: 960x200 (позиции x -480..480, y -40..160), масштаб
  `PLATFORM_SCALE = 140/960 x 20/80`; визуал 140x50, коллизия 140x20.
- Платформа цельная: один mesh + одна текстура, UV 0..1. Сегментов
  «левый край/центр/правый край» нет.
- Склоны — отдельные прототипы `/main/platforms/sloped/left.go` и `right.go`.
- Текущие default/sticky/shrinkable текстуры — временный кроп из raw tile sheet,
  не финальные тайлы ТЗ.

# 8. Текущие графические ассеты (93 PNG)

- `main/background`: bg_beautiful, bg_cosmic, bg_magic, bg_industrial — 1344x768 (4).
- `main/ball`: football.png — 512x512.
- `main/bumpy`: bumpy.png — 512x512; `frames/` — 48 файлов 208x208
  (`u_/f_` rest/fall1-4/rise1-3/sq1-6/tm1-2/wl1-4/wr1-4).
- `main/controls`: left/right/up.png — 128x128 (3).
- `main/exit`: exit.png — 240x160.
- `main/goodies`: drop/key/hammer/heart/collectible — 32x32 (5);
  `fruit/fr_*.png` — 32x32 (12).
- `main/pocket`: ball.png, heart.png — 32x32 (2).
- `main/slinky`: ring.png — 256x160.
- `main/ui`: game_over 560x210, ready 640x220, trap 520x200 (3).
- `main/platforms`: default/sticky 960x200; shrinkable 960x152; burning 960x200;
  burning_sticky/spike 960x256 (6).
- `main/walls`: block 1193x1310; border 32x64; destructible/broken/cracked 64x280 (3);
  indestructible 64x280.
- Всего 93 PNG. Плюс `.atlas/.sprite/.go` ресурсы (bumpy, ball, fruit и т.д.).

# 9. Среда

- GPU: NVIDIA GeForce GTX 1660 SUPER; WMI AdapterRAM=4,293,918,720 B;
  драйвер 32.0.16.1656.
- RAM: 34,273,857,536 B (~32 GB).
- Python: 3.15.1.
- ffmpeg: NOT FOUND (не установлен).

# 10. Что уже согласовано с разработчиком (не откатывать)

- Инженерия героев: `main/heroes.lua` (реестр), `main/bumpy/*`, мяч возвращён к
  `football.png`, Bumpy — первый герой; общий `ball.script` больше не содержит
  анимаций конкретного героя.
- Bumpy визуально 48 px (коллайдер оставлен 32), добавлен `HERO_SPEED`.
- Физика/поведение сверх art-ТЗ: отскок от потолка/низа платформы/низа кладки;
  impact-позы для стен/потолка; переворот на месте 180° при приземлении на голове;
  зеркало лица влево; замедленное/сглаженное приземление Bumpy
  (`SQUASH_TIME_SCALE=2.0`); отскок от кладки через `hero.on_action`.
- Предпросмотр фона: 4 AI-фона (не 4 слоя параллакса) и выбор по теме;
  `state.theme`; background GO.
- Временные тайлы платформ: кроп из raw tile sheet вместо финальных тайлов ТЗ.
- Рабочий процесс арта: `art_inbox` (gitignored), `PROMPTS.md`, `TASK.md`,
  `GENERATION_PLAN.md`; это не игровые ассеты.
- Не добавлено: 12 тем в `levels.json` (осталось 7), финальные 14 анимаций,
  30-кадровые секвенции, финальные тайлы/миры.
- Git: ветка `design-art`, последний коммит `cad25a7`; в рабочем дереве есть
  незакоммиченные изменения (см. раздел 12).

---

# 11. Второй раунд разведки (этап 0 pipeline)

## 11.1. Выбор кадров Bumpy

Код: `main/bumpy/hero_bumpy.lua`, `stretch_name` (72-82), `pick_frame` (84-109),
`update_visual` (112-175).

```lua
local n = math.floor(rot / math.pi + 0.5)
local res = rot - n * math.pi
local orient = n % 2          -- 0 -> u_*, 1 -> f_*
```

- `u_*` — обычный набор (лицо в нормальной ориентации).
- `f_*` — набор после переворота на 180°: лицо «вверх ногами», плоская сторона
  всё равно внизу (комментарий к ассету).
- `tm1`/`tm2` — tumble, кадры кувырка. Выбираются первыми, если остаточный угол
  `|res| > TUMBLE_RES = 0.25` рад:
  - `tm2`: `|vn| > 0.6` (|vy| > 230.4 px/s);
  - `tm1`: `0.15 < |vn| <= 0.6` (57.6..230.4 px/s);
  - иначе `rest`.
- `rest`: при `|vn| < 0.15` (|vy| < 57.6 px/s), если нет squash/tumble/sticky.
- `rise1..3` / `fall1..4`: по вертикальной скорости, не по времени.
  `vn = vy / JUMP_SPEED` (JUMP_SPEED=384), `m = min(1, abs(vn))`,
  `k = (m - 0.1) / 0.9`:
  - `rise` (vn>0): `rise1` при |vy| 57.6..153.6; `rise2` 153.6..268.8;
    `rise3` >268.8 px/s.
  - `fall` (vn<0): `fall1` 57.6..124.8; `fall2` 124.8..211.2;
    `fall3` 211.2..297.6; `fall4` >=297.6 px/s.
- `sq1..6`: по времени от касания. `s = self.squash` (1 -> 0);
  `a = smoothstep(min(1, 1.2*s))`; `index = ceil(a*6)`.
  У Bumpy squash длится 0.30 с (`SQUASH_DURATION=0.15` × `SQUASH_TIME_SCALE=2.0`):
  - `sq6`: 0–114.8 мс (максимум держится первые 50 мс);
  - `sq5`: 114.8–146.7 мс;
  - `sq4`: 146.7–175.0 мс;
  - `sq3`: 175.0–203.3 мс;
  - `sq2`: 203.3–235.2 мс;
  - `sq1`: 235.2–279.0 мс; после ~279 мс `a < 0.02`, кадр падает в rest/другую ветку.
- `wl1..4` / `wr1..4`: горизонтальный squash при `squash_axis == "x"`.
  `d = bounce_x_wall - bounce_x_start`; `d > 0` → `wr*`, `d < 0` → `wl*`.
  `index = ceil(a*4)`; при том же 0.30 с:
  - `w4`: 0–131.6 мс (максимум до 50 мс);
  - `w3`: 131.6–175.0 мс;
  - `w2`: 175.0–218.4 мс;
  - `w1`: 218.4–279.0 мс.
- `sticky_rest` → всегда `sq3` (шар лежит на липкой платформе).
- **Текущий impact override**: в `update_visual` при `impact_t > 0` кадры
  `u_sq` принудительно поворачиваются на 180° (потолок) или ±90° (стена);
  `impact_t = 0.22` с. Поэтому в текущем билде `wl/wr` для Bumpy на ударах
  фактически перекрываются impact-позой; они остаются в `pick_frame` как fallback.

## 11.2. Мгновенность прыжка и Anticipation

- Обычный отскок: при приземлении `settle` сразу выставляет
  `linear_velocity = (0, env.jump_speed, 0)`; задержки нет.
- Боковой прыжок: `hop_and_move` вызывается в окне `THRESHOLD=0.1` с вокруг касания
  (или ставится в `pending_dir`, если до следующего касания ≤0.1 с). В момент
  выполнения сразу выставляется вертикальная скорость и начинается смещение X.
- Высокий прыжок: `start_high_jump` сразу выставляет `HIGH_JUMP_SPEED`.
- Отдельного состояния/задержки Anticipation нет. `self.squash = 1` ставится на
  приземлении (и повторно при старте действия, строки ~1035, 1088, 1499), поэтому
  видимое «приседание» перед отрывом — это squash предыдущего приземления /
  squash текущего действия, а не отдельная фаза. Прыжок не ждёт окончания squash.
- Landing и Bounce — части одного непрерывного цикла; отдельных состояний нет.

## 11.3. Размеры показа

| Объект | Локальный размер / scale | Размер на экране |
|---|---|---|
| Обычная платформа | mesh 960x200, `PLATFORM_SCALE=140/960 x 20/80` | визуал 140x50, коллизия 140x20 |
| Склоны left/right | тот же buffer/texture, тот же `PLATFORM_SCALE` | визуал 140x50, коллизия 140x20 |
| Стена destructible/indestructible/border | mesh 20x70, `WALL_SCALE=(1, CELL_H/70=1.5238, 1)` | 20x106.67; коллизия 20x106.67; текстура 64x280 |
| Кирпичная кладка | mesh 140x112.5, `BLOCK_SCALE=(1, CELL_H/100=1.0667, 1)` | визуал 140x120; коллизия 140x106.67; текстура 1193x1310; 8 рядов |
| Предметы drop/key/hammer/heart | 32x32, scale 1 | 32x32, без collision; `GOODIE_HALF=16` |
| Фрукты | 32x32, scale 1 | 32x32 |
| Выход | текстура 240x160, scale (120/240, 80/160) = 0.5 | 120x80; без collision; half 60x40 |

## 11.4. Темы и `theme_table`

- `theme_table` (7 цветов) **нигде не читается** в коде — не найдено использования.
  Платформы и стены им **не тонируются**.
- Тема используется только:
  - `main/level/level.script`: `state.theme = lvl.theme or 1`;
  - `main/background/background.script`: `BY_THEME[1..4]` включает один из 4 фонов;
  - лог загрузки уровня.
- Платформы/стены тему не используют: у них один набор текстур.
- Чтобы поддержать 12 тем, менять:
  - `main/levels.json`: темы 8..12 и распределение 100 уровней; при необходимости
    `theme_table`;
  - `main/background/background.script`: mapping 1..12;
  - `main/background/background.go` + `main.collection`: 8 новых фоновых спрайтов
    (или динамическая загрузка);
  - новые фоны/атласы;
  - для тематических платформ/стен — новые текстуры/прототипы или система tint
    в материалах; сейчас её нет.
- `level.script` уже передаёт `theme` в `state`; менять его почти не нужно.

## 11.5. Фрукты

`main/level/level.script` (FRUITS), файлы `main/goodies/fruit/fr_*.png`:

1. mushroom — `fr_mushroom.png`
2. strawberry — `fr_strawberry.png`
3. apple — `fr_apple.png`
4. pear — `fr_pear.png`
5. cherry — `fr_cherry.png`
6. banana — `fr_banana.png`
7. orange — `fr_orange.png`
8. grapes — `fr_grapes.png`
9. plum — `fr_plum.png`
10. lemon — `fr_lemon.png`
11. carrot — `fr_carrot.png`
12. watermelon — `fr_watermelon.png`

Все 32x32. Коды объектов 5..40 распределяются по кругу; всего 647 фруктов.

## 11.6. Переключение набора кадров Bumpy

- Реестр: `main/heroes.lua`; порядок сейчас: bumpy, ball, slinky; `T` в игре
  переключает по кругу.
- `ball.script` в init берёт `HEROES[1]`; активный герой — `self.hero`.
- Чтобы сравнить старый и новый набор, не удаляя старый:
  1. Создать второй модуль, например `main/bumpy/hero_bumpy_test.lua`, с тем же
     интерфейсом (`setup/activate/deactivate/reset/update/...`).
  2. Создать отдельный атлас/спрайт/визуал, например `bumpy_test.atlas`,
     `bumpy_test.sprite`, `bumpy_test_visual.go`, и инстанс в `main.collection`
     (потому что `tile_set` спрайта фиксирован).
  3. В тестовом модуле указать свой `VISUAL` и свой `ANIM`.
  4. Добавить модуль в `main/heroes.lua` после bumpy; `T` будет переключать
     bumpy → bumpy_test → ball → slinky.
- Быстрый вариант (только A/B, без одновременного presence): заменить require в
  `main/heroes.lua` на тестовый модуль, старый файл сохранить. Но для сравнения
  в игре лучше добавить второй герой в реестр.

## 11.7. Сжатие текстур и атласы

- В `game.project` настроек сжатия текстур **нет**: нет `[graphics]`/texture
  profiles, нет `.texture_profiles`. Значит, по умолчанию текстуры не сжимаются
  (RGBA).
- Существующие атласы (bumpy, ball, UI, goodies и т.д.):
  - `sprite_trim_mode: SPRITE_TRIM_MODE_OFF`;
  - `margin: 0`;
  - `extrude_borders: 2`;
  - `inner_padding: 0`.
- Новые фоновые атласы (`main/background/bg_*.atlas`) содержат по одному image
  1344x768 без явных margin/extrude (дефолты).
- `bumpy.atlas`: 48 изображений 208x208, trim off, extrude 2.
- Отдельного texture profile/сжатия нет; при необходимости оптимизации нужно
  добавить настройки и пересобрать.

---

# 12. Проверка git status

Ожидание этапа: изменён только `docs/GAME_FACTS.md`.
Фактически в рабочем дереве уже были незакоммиченные изменения, которые
согласованы с разработчиком и не откатываются (раздел 10). В этом этапе
записан только `docs/GAME_FACTS.md`; остальные изменения не трогались.

Фактический `git status` на момент отчёта:

```
 M .gitignore
 M main/ball/ball.script
 M main/bumpy/hero_bumpy.lua
 M main/level/level.script
 M main/level/level_state.lua
 M main/main.collection
 M main/platforms/default/platform.png
 M main/platforms/shrinkable/platform.png
 M main/platforms/sticky/platform.png
?? docs/
?? main/background/
```

`docs/` — новый каталог с этим отчётом. `main/background/` — 4 AI-фона и
background.script, добавленные ранее по согласованию. Остальные `M` — уже
согласованные изменения героя/физики/фона/тайлов. В этапе 0 ничего из этого
не менялось и не коммитилось.

Итог: в этом этапе записан только `docs/GAME_FACTS.md`; git status не может
показывать «только его», потому что в дереве уже были согласованные изменения.

