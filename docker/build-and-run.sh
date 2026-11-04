#!/usr/bin/env bash
# Build the HTML5 bundle and (re)build + start the nginx docker container.
# Run from the repository root: bash docker/build-and-run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker/docker-compose.yml"
IMAGE="bumpy-web:latest"
CONTAINER="bumpy-web"

echo "==> Bundling HTML5 (wasm-web) via Defold editor API"
node tools/api_bundle_html5.js

if [ ! -f dist/web/bumpy/index.html ]; then
    echo "ERROR: dist/web/bumpy/index.html не найден — сборка бандла не удалась" >&2
    exit 1
fi

echo "==> Building docker image"
# На некоторых системах (Windows + Docker Compose 2.24) `docker compose build`
# падает с «changes out of order: "docker/nginx.conf"» из-за бага BuildKit в
# compose. Классический сборщик и прямой `docker build` работают, поэтому при
# ошибке откатываемся на них.
if ! docker compose -f "$COMPOSE_FILE" build; then
    echo "==> compose build не удался — повтор через классический сборщик (DOCKER_BUILDKIT=0)"
    if ! DOCKER_BUILDKIT=0 docker compose -f "$COMPOSE_FILE" build; then
        echo "==> повтор через docker build"
        docker build -f docker/Dockerfile -t "$IMAGE" .
    fi
fi

echo "==> Restarting container on http://localhost:8080"
# Контейнер мог быть создан другим compose-проектом или вручную — имя занято,
# поэтому удаляем его до создания нового.
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker compose -f "$COMPOSE_FILE" up -d --force-recreate

echo "Done. Open http://localhost:8080"
