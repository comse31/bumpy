# Часовой генератор уровней Bumpy (tools/gen_hourly.py).
#
# Образ содержит только генератор и решатель: зависимостей нет, всё на
# стандартной библиотеке Python. Запускается в docker-сети рядом с backend и
# пишет уровень через POST /api/levels.
#
# Сборка (из корня репозитория):
#   docker build -f docker/gen/Dockerfile -t bumpy-gen:latest .
# Ручной запуск:
#   docker run --rm --network bumpy-net -e BUMPY_API_URL=http://bumpy-backend:8000 bumpy-gen:latest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUMPY_API_URL=http://bumpy-backend:8000

WORKDIR /app

# Генератор и решатель. Импорты внутри образа:
#   gen_hourly.py → gen_level.py → level_interest.py, solve_level.py
#   gen_level.py / gen_hourly.py → backend.app.level_prompts
# .dockerignore пропускает из tools/ только эти файлы, поэтому копируем
# каталог целиком (остальные в контекст не попадают).
COPY tools/ /app/tools/
# Промт/подпись уровня живут в общем модуле backend/app/level_prompts.py:
# генератор импортирует его как backend.app.level_prompts (см. sys.path в
# gen_level.py/gen_hourly.py), поэтому пакет нужен и здесь. Копируется только
# сам модуль: остальные файлы backend в образ генератора не нужны.
COPY backend/app/__init__.py /app/backend/app/__init__.py
COPY backend/app/level_prompts.py /app/backend/app/level_prompts.py
# Уровни классики нужны только для сравнения/отладки, но solve_level.py ищет
# levels.json по относительному пути — копируем, чтобы инструменты работали
# из контейнера так же, как на хосте.
COPY main/levels.json /app/main/levels.json

# Непривилегированный пользователь: генератору не нужен root.
RUN useradd --system --uid 10002 --home /app bumpy \
    && chown -R bumpy:bumpy /app
USER bumpy

# Один уровень в час: цикл внутри контейнера (расписание снаружи не нужно).
# --count 1 — ровно один проходимый уровень за запуск.
CMD ["python3", "tools/gen_hourly.py", "--loop", "3600", "--count", "1"]
