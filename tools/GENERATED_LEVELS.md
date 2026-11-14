# Генератор уровней Bumpy

Уровни создаются процедурно, проверяются решателем и хранятся в БД. Игра берёт
случайный уровень из БД для режима **Adventure**.

## Как это работает

```
tools/gen_level.py     — генератор кандидатов: seed → уровень (формат levels.json)
        │
        ├─ tools/solve_level.py: is_solvable() — оракул проходимости
        │     "solvable"   → уровень принимается
        │     "impossible" → брак, следующий seed
        │     "limit"      → проходимость не доказана → тоже брак
        │
tools/gen_hourly.py    — часовой запуск: 1 проходимый уровень → POST /api/levels
        │
backend (FastAPI)      — таблица generated_levels (миграция 003)
        │
GET /api/levels/random — клиент: main/random_level.lua → main/level/level.script
```

Ключевые правила:

1. **в БД попадает только уровень, проходимость которого доказана**;
2. **уровень обязан требовать хотя бы один предмет** (`drops + keys + hammers > 0`):
   слишком простые уровни в БД не сохраняются и не выдаются клиенту;
3. **над кирпичной кладкой не может быть платформ**: в оригинале
   (`main/levels.json`, 144 кладки) прямо над кладкой стоит только другая
   кладка — столбик кирпичей. Иначе шар, разбивающий кладку снизу молотком,
   упирался бы в платформу сверху;
4. **нельзя начинать уровень на огне или шипах**: главный герой не должен
   погибать в первом же касании. Старт на сжимающейся платформе любого остатка
   (коды 2/3/4) разрешён — игрок сам решает, как её использовать;
5. **уровень должен быть интересен человеку**, а не только проходим:
   кандидат оценивается по [`tools/level_interest.py`](level_interest.py:1)
   (см. ниже), скучные уровни отбрасываются.

### «Человеческая» интересность уровня

[`tools/level_interest.py`](level_interest.py:1) считает балл 0..100 по
механике прохождения, а не по количеству объектов на карте:

| Компонент | Вес | Что измеряет |
|---|---:|---|
| `precision` | 0.18 | доля высоких прыжков с перестроением в полёте (тап по ячейке) |
| `irreversible` | 0.13 | доля ходов, после которых платформа под шаром исчезает |
| `no_rest` | 0.10 | самая длинная серия опор без безопасной платформы (6 ходов = 1.0) |
| `forced_motion` | 0.07 | наклон/липкая двигают шар без решения игрока |
| `hazard_goal` | 0.13 | фрукты, которые нельзя взять без риска: лежат на шипах/огне или висят над ними |
| `puzzle` | 0.09 | кладки и перегородки против стартового снаряжения |
| `trap_risk` | 0.06 | наклоны, сбрасывающие шар в край поля или в неразрушаемую стену |
| `variety` | 0.07 | сколько разных механик задействовано |
| `maze` | 0.09 | сколько поля заложено кирпичом (уровень-головоломка) |
| `oneshot_field` | 0.08 | доля клеток поля, которые исчезают после действия |

Оценка **не заменяет** проверку проходимости: сначала решатель доказывает,
что уровень проходим, и только потом считается интересность. Поэтому генератор
не может «выбрать красивый, но непроходимый» уровень.

Отбор в генераторе:

* `MIN_INTEREST = 26.0` — порог [`gen_level.py`](gen_level.py:1): ниже —
  кандидат бракуется как скучный (порог откалиброван по `--bench`: у
  проходимых кандидатов интересность 20..32, у классических уровней до 50);
* `DEFAULT_INTEREST_POOL = 4` — из скольких подходящих кандидатов берётся
  лучший. Замер на одинаковом диапазоне seed: `pool=1` даёт 20.5,
  `pool=2` и `pool=4` — 31.5 (рост в 1.5 раза), `pool=8` не улучшает
  результат, поэтому 4 — оптимум по времени;
* [`gen_hourly.py`](gen_hourly.py:1) прокидывает `--min-interest` и
  `--interest-pool`; в лог пишется `interest=NN.N` выбранного уровня;
* [`bench_solve.py`](bench_solve.py:1) показывает интересность отдельной
  колонкой (`Интересность`) рядом со статической сложностью, а JSON-отчёт
  хранит `interest` и `interest_parts`;
* [`gen_walkthrough.py`](gen_walkthrough.py:1) выводит в
  [`LEVELS_WALKTHROUGH.md`](LEVELS_WALKTHROUGH.md:1) топ-10 по интересности
  **и** топ-10 по статической сложности — они расходятся: прицельные прыжки
  над шипами (уровни 36, 61, 92) ценятся выше, чем «много предметов на карте».

Проверка интереса вручную:

```bash
py tools/gen_level.py --bench 25 --min-interest 0 --node-cap 200000
py tools/gen_hourly.py --dry-run --min-interest 30 --interest-pool 4
py tools/bench_solve.py --from 36 --to 36     # смотреть колонку «Интересность»
```

Все правила продублированы в трёх местах:

1. [`tools/gen_level.py`](gen_level.py:1) — `MIN_REQUIRED_ITEMS = 1`;
   `is_playable()` возвращает `"impossible"` для проходимых, но «пустых»
   уровней, а [`gen_hourly.py`](gen_hourly.py:1) дополнительно сверяет
   `drops + keys + hammers >= min_items` перед отправкой;
2. [`backend/app/schemas.py`](backend/app/schemas.py:1) — `GeneratedLevelIn`
   отвергает `status != "solvable"` и уровень без требуемых предметов (422);
3. [`backend/app/levels_repository.py`](backend/app/levels_repository.py:1) —
   `add()` проверяет статус ещё раз, а `random()` не выдаёт клиенту записи с
   `drops + keys + hammers == 0` (в БД могли остаться старые записи).

### Как уровень гарантированно требует предмет

В [`tools/gen_level.py`](gen_level.py:1) `_lock_start()` строит «камеру» вокруг
стартовой клетки:

| Тип замка | Что ставится | Что требуется |
|---|---|---|
| `block` | кладка над шаром | молоток |
| `wall` | разрушаемая перегородка в ряду старта | ключ |

Замка «горящая платформа под шаром» больше нет: он нарушал правило
безопасного старта (шар погибал в огне без капли). Стартовая платформа
остаётся такой, какой её поставил генератор (обычная, липкая или
сжимающаяся), а смертельные коды заменяются обычной платформой.

Дополнительно по бокам колонки старта на всех рядах выше ставятся
**неразрушаемые** перегородки (закрывают выход вверх через высокий прыжок), а
предметы-расходники не ставятся в ряд старта и в колонку старта — иначе шар
подобрал бы их пролётом и требование обнулилось бы.

Измерено на 70 seed'ах после изменения: **70/70 solvable**, у всех
`drops + keys + hammers >= 1` (ключи 69, капли 23, молотки 0).

### Правило безопасного старта

Стартовая клетка не может содержать огонь или шипы:

| Код lo | Платформа | Старт |
|---|---|---|
| 1 | обычная | разрешён |
| 2, 3, 4 | сжимающаяся (любой остаток) | разрешён |
| 5 | липкая | разрешён |
| 6, 7 | наклонная | разрешён |
| 8 | горящая | **запрещён** |
| 9 | горящая + липкая | **запрещён** |
| 12 | шипы | **запрещён** |

Правило продублировано в трёх местах:

1. [`_pick_start()`](gen_level.py:1) не выбирает смертельные клетки, а
   `generate()` дополнительно нормализует стартовую клетку в обычную
   платформу, если там оказалось что-то небезопасное;
2. [`lethal_start_violation()`](gen_level.py:1) проверяется в `is_playable()`
   до решателя — бракованный кандидат не тратит время на поиск плана;
3. в backend: `GeneratedLevelIn._safe_start`
   ([`schemas.py`](../backend/app/schemas.py:1), 422) и
   `GeneratedLevelRepository._safe_start`
   ([`levels_repository.py`](../backend/app/levels_repository.py:1), такие
   записи не выдаются через `random`). В отличие от правила «над кладкой»,
   фильтр старта не ослабляется при нехватке записей.

Замер на 160 кандидатах: **0 смертельных стартов**; распределение типов
стартовой платформы — обычная 133, сжимающиеся 15, липкая 6, наклонные 6.

### Правило «над кладкой нет платформ»

[`blocks_above_violations()`](gen_level.py:1) возвращает клетки, где над
кирпичной кладкой (код 10) стоит платформа (коды 1..9). Проверка стоит в трёх
местах:

1. при расстановке кладки (`_place_specials`) — кладка не ставится, если выше
   по колонке есть платформа;
2. в `_lock_start()` — платформы над «потолком» камеры убираются;
3. в `is_playable()` — кандидат с нарушением сразу бракуется, не доходя до
   решателя.

На сервере то же правило проверяет
[`GeneratedLevelIn._no_platform_above_block`](../backend/app/schemas.py:1)
(422 на такой уровень) и
[`GeneratedLevelRepository._no_platform_above_block`](../backend/app/levels_repository.py:1)
(такие записи не выдаются через `random`).

Проверено на 300 кандидатах: 217 кладок, **0 нарушений**. Столбик кладки
(кладка над кладкой) разрешён — так сделано в оригинале.

## Генератор уровней

```bash
# один уровень в JSON (перебор seed'ов до первого подходящего)
python3 tools/gen_level.py --seed 1

# отключить требование «хотя бы один предмет» (для отладки)
python3 tools/gen_level.py --seed 1 --min-items 0

# в файл + минимальный стартовый набор предметов
python3 tools/gen_level.py --seed 1 --out /tmp/level.json --requirements

# оценить долю проходимых кандидатов (быстрая проверка генератора)
python3 tools/gen_level.py --bench 50
```

Уровень полностью определяется seed: `--seed N` всегда даёт один и тот же
уровень. Сложность зависит от `--level` (номер уровня).

Структура уровня — ровно формат [`main/levels.json`](../main/levels.json):
`grid_lo` (платформы), `grid_hi` (перегородки), `objects` (предметы),
`start_cell`, `timer`, `timer_cell`, `theme`. Поэтому клиент строит его тем же
[`level.script`](../main/level/level.script:1), что и классические уровни —
никакого отдельного загрузчика для сгенерированных уровней нет.

## Часовой запуск

```bash
# один уровень за запуск
python3 tools/gen_hourly.py

# свой backend и ключ
BUMPY_API_URL=http://127.0.0.1:8000 BUMPY_API_KEY=... python3 tools/gen_hourly.py

# проверить без записи в БД
python3 tools/gen_hourly.py --dry-run

# три уровня за запуск
python3 tools/gen_hourly.py --count 3

# постоянно, с интервалом (например, внутри контейнера)
python3 tools/gen_hourly.py --loop 3600
```

### Docker (основной способ)

Генератор входит в docker-стек: сервис `bumpy-gen`
([`docker/gen/Dockerfile`](../docker/gen/Dockerfile:1)) запускает
`gen_hourly.py --loop 3600` — один уровень в час, расписание снаружи не нужно.

```bash
docker compose -f docker/docker-compose.yml up -d --build
docker logs -f bumpy-gen
curl -s http://localhost:8080/api/levels/stats
```

В [`deploy-master.yml`](../.github/workflows/deploy-master.yml:1) контейнер
разворачивается вместе с игрой и backend, причём с `--restart unless-stopped`.

### cron

```cron
# каждый час в 5 минут
5 * * * * cd /opt/bumpy && /usr/bin/python3 tools/gen_hourly.py >> /var/log/bumpy-gen.log 2>&1
```

### systemd timer

```bash
sudo cp tools/gen_hourly.service /etc/systemd/system/bumpy-gen.service
sudo cp tools/bumpy-gen.timer /etc/systemd/system/bumpy-gen.timer
# путь к репозиторию и адрес API при необходимости поправить в unit-файле
sudo systemctl daemon-reload
sudo systemctl enable --now bumpy-gen.timer
systemctl list-timers bumpy-gen.timer
journalctl -u bumpy-gen.service -n 50
```

## API

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/levels/random` | случайный уровень (клиент, режим Adventure) |
| GET | `/api/levels/latest?limit=N` | последние N уровней (отладка) |
| GET | `/api/levels/stats` | `total` и время последней записи |
| POST | `/api/levels` | сохранить уровень (часовой генератор) |

```bash
curl -s http://127.0.0.1:8000/api/levels/stats
curl -s http://127.0.0.1:8000/api/levels/random | python3 -m json.tool | head -30
```

`POST /api/levels` принимает `status` только `"solvable"` и проверяет, что
`payload` — валидный JSON уровня с сетками 6x6 и целыми `start_cell` /
`timer_cell`. Повторная вставка того же seed не создаёт дубликат
(`INSERT OR IGNORE`, уникальный индекс по `seed`).

## Настройки

[`backend/config.yml`](../backend/config.yml:1), секция `levels`:

```yaml
levels:
  window: 500        # сколько последних уровней участвует в random
  latest_limit: 10   # размер выдачи /api/levels/latest
  keep: 2000         # сколько хранить при очистке (0 — не чистить)
```

## Данные в БД

Таблица `generated_levels` ([миграция 003](../backend/migrations/003_generated_levels.sql:1)):

| Поле | Смысл |
|---|---|
| `level_id` | стабильный id: `g<seed>_<hash(payload)>` |
| `seed` | seed генератора (уникален, уровень воспроизводим) |
| `level` | номер, под который генерировали (влияет на сложность) |
| `payload` | JSON уровня в формате `levels.json` |
| `status` | всегда `solvable` |
| `drops`/`keys`/`hammers` | минимальный стартовый набор (из решателя) |
| `generator` | чем создан (`tools/gen_hourly.py`) |
| `created_at` | UTC ISO-8601 |

## Проверка вручную

```bash
# 1. генератор
python3 tools/gen_level.py --seed 42 --bench 10

# 2. backend (в docker)
docker build -f backend/Dockerfile -t bumpy-backend:test .
docker run -d --name bumpy-backend-test -p 8765:8000 bumpy-backend:test
sleep 5
curl -s http://127.0.0.1:8765/api/levels/stats

# 3. сохранить один уровень
BUMPY_API_URL=http://127.0.0.1:8765 python3 tools/gen_hourly.py

# 4. прочитать случайный
curl -s http://127.0.0.1:8765/api/levels/random | head -c 400

# 5. убедиться, что не-solvable не принимается (ожидается 422)
curl -s -X POST http://127.0.0.1:8765/api/levels \
  -H 'Content-Type: application/json' \
  -d '{"seed":1,"level":1,"payload":"{}","status":"limit"}'
```
