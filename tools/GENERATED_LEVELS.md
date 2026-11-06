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

Ключевое правило: **в БД попадает только уровень, проходимость которого
доказана**. Оно продублировано в трёх местах:

1. [`tools/gen_hourly.py`](gen_hourly.py:1) — не отправляет уровень, если
   `is_solvable` вернул не `"solvable"`;
2. [`backend/app/schemas.py`](backend/app/schemas.py:1) — `GeneratedLevelIn`
   отвергает `status != "solvable"` (422);
3. [`backend/app/levels_repository.py`](backend/app/levels_repository.py:1) —
   `add()` проверяет статус ещё раз.

## Генератор уровней

```bash
# один уровень в JSON (перебор seed'ов до первого проходимого)
python3 tools/gen_level.py --seed 1

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
