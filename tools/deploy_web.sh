#!/usr/bin/env bash
#
# Разворачивает образ веб-версии игры (bumpy-web) на удалённой машине по SSH:
# копирует архив, загружает его в docker и поднимает контейнер nginx с
# пробросом порта HOST_PORT (по умолчанию 9999) на 80 внутри контейнера.
#
# Usage:
#   tools/deploy_web.sh user@host [host_port]
#
# Примеры:
#   tools/deploy_web.sh root@192.168.1.50            # http://192.168.1.50:9999
#   tools/deploy_web.sh deploy@server 9999
#
# Переменные окружения (необязательно):
#   IMAGE_FILE      локальный архив образа (по умолчанию bumpy-web-image.tar.gz)
#   IMAGE_TAG       тег образа после docker load (по умолчанию bumpy-web:latest)
#   CONTAINER_NAME  имя контейнера (по умолчанию bumpy-web)
#   CONTAINER_PORT  порт внутри контейнера (по умолчанию 80, порт nginx)
#   REMOTE_DIR      рабочий каталог на удалённой машине (по умолчанию /tmp/bumpy-deploy)
#   DOCKER          команда docker; если нужен sudo — DOCKER="sudo docker"
#   SSH_OPTS        доп. опции ssh/scp, напр. SSH_OPTS="-p 2222 -i ~/.ssh/id"
#   NO_VERIFY=1     не проверять доступность через curl после запуска

set -euo pipefail

REMOTE="${1:-}"
HOST_PORT="${2:-${HOST_PORT:-9999}}"

IMAGE_FILE="${IMAGE_FILE:-bumpy-web-image.tar.gz}"
IMAGE_TAG="${IMAGE_TAG:-bumpy-web:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-bumpy-web}"
CONTAINER_PORT="${CONTAINER_PORT:-80}"
REMOTE_DIR="${REMOTE_DIR:-/tmp/bumpy-deploy}"
DOCKER="${DOCKER:-docker}"
SSH_OPTS="${SSH_OPTS:-}"

if [[ -z "$REMOTE" ]]; then
    echo "usage: $0 user@host [host_port]" >&2
    exit 1
fi

# относительный путь к архиву — ищем от корня проекта
if [[ ! -f "$IMAGE_FILE" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$SCRIPT_DIR/../$IMAGE_FILE" ]]; then
        IMAGE_FILE="$SCRIPT_DIR/../$IMAGE_FILE"
    fi
fi
if [[ ! -f "$IMAGE_FILE" ]]; then
    echo "error: архив образа не найден: $IMAGE_FILE" >&2
    exit 1
fi

IMAGE_BASENAME="$(basename "$IMAGE_FILE")"
HOST_ONLY="${REMOTE#*@}"   # хост без user@ — для проверки через curl

echo "==> Образ:    $IMAGE_FILE ($IMAGE_BASENAME)"
echo "==> Хост:     $REMOTE:$REMOTE_DIR"
echo "==> Контейнер: $CONTAINER_NAME ($IMAGE_TAG), порт $HOST_PORT -> $CONTAINER_PORT"

echo "==> Копирую архив на удалённую машину"
# shellcheck disable=SC2086
ssh $SSH_OPTS "$REMOTE" "mkdir -p '$REMOTE_DIR'"
# shellcheck disable=SC2086
scp $SSH_OPTS "$IMAGE_FILE" "$REMOTE:$REMOTE_DIR/$IMAGE_BASENAME"

echo "==> Загружаю образ и (пере)запускаю контейнер"
# Значения передаём через переменные окружения удалённой команды; тело скрипта
# приходит по stdin, поэтому подстановки на локальной стороне не выполняются.
# shellcheck disable=SC2086
ssh $SSH_OPTS "$REMOTE" \
    "REMOTE_DIR='$REMOTE_DIR' IMAGE_BASENAME='$IMAGE_BASENAME' IMAGE_TAG='$IMAGE_TAG' CONTAINER_NAME='$CONTAINER_NAME' HOST_PORT='$HOST_PORT' CONTAINER_PORT='$CONTAINER_PORT' DOCKER='$DOCKER' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
cd "$REMOTE_DIR"

# Архив вложенный: внешний gzip содержит tar, внутри которого лежит
# docker-архив (blobs/ + manifest.json). Разворачиваем до docker-архива.
gzip -dc "$IMAGE_BASENAME" | tar -xO > image.tar
$DOCKER load -i image.tar
rm -f image.tar

# Пересоздаём контейнер, если он уже был
if $DOCKER ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "==> Удаляю старый контейнер $CONTAINER_NAME"
    $DOCKER rm -f "$CONTAINER_NAME"
fi

$DOCKER run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    -p "$HOST_PORT:$CONTAINER_PORT" "$IMAGE_TAG"

$DOCKER ps --filter "name=$CONTAINER_NAME"
REMOTE_SCRIPT

if [[ "${NO_VERIFY:-0}" != "1" ]]; then
    echo "==> Проверяю доступность http://$HOST_ONLY:$HOST_PORT/"
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS --max-time 10 "http://$HOST_ONLY:$HOST_PORT/" >/dev/null; then
            echo "OK: игра доступна на http://$HOST_ONLY:$HOST_PORT/"
        else
            echo "warning: curl не смог достучаться до http://$HOST_ONLY:$HOST_PORT/" >&2
            echo "         проверьте firewall на удалённой машине (порт $HOST_PORT)" >&2
        fi
    else
        echo "curl не установлен — пропускаю проверку"
    fi
fi
