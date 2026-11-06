# Backend Bumpy: FastAPI + SQLite.
#
# База данных — файл /data/bumpy.db внутри контейнера. Каталог /data
# объявляется томом: в docker-compose он привязан к именованному тому
# bumpy-db, поэтому данные переживают пересоздание контейнера при деплое.
#
# Сборка (из корня репозитория):
#   docker build -f backend/Dockerfile -t bumpy-backend:latest .
# Запуск:
#   docker run --rm -p 8000:8000 -v bumpy-db:/data bumpy-backend:latest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BUMPY_CONFIG=/app/config.yml

WORKDIR /app

# Зависимости отдельным слоем: правка кода не переустанавливает пакеты.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Приложение и настройки (config.yml — единственный источник настроек БД).
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/config.yml ./config.yml

# Каталог файла БД. Владелец — непривилегированный пользователь, чтобы SQLite
# мог создавать bumpy.db и служебные -wal/-shm файлы.
RUN mkdir -p /data \
    && useradd --system --uid 10001 --home /app bumpy \
    && chown -R bumpy:bumpy /data /app

USER bumpy

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# Настройки (host/port) читаются из config.yml тем же загрузчиком, что и в коде:
# единый источник истины, дублирования параметров в командной строке нет.
CMD ["python", "-m", "app.serve"]
