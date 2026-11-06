#!/usr/bin/env bash
# Load the bumpy-web docker image from an archive and run the container.
# Run anywhere: bash docker/load-image.sh [archive]
set -euo pipefail

ARCHIVE="${1:-dist/bumpy-web-image.tar.gz}"
IMAGE="bumpy-web:latest"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "archive not found: $ARCHIVE" >&2
  exit 1
fi

echo "==> Loading image from '$ARCHIVE'"
case "$ARCHIVE" in
  *.gz|*.tgz)
    # docker load does not read gzip on all platforms; unpack first
    TMP="$(mktemp -d)"
    tar -xzf "$ARCHIVE" -C "$TMP"
    docker load -i "$TMP/bumpy-web-image.tar"
    rm -rf "$TMP"
    ;;
  *)
    docker load -i "$ARCHIVE"
    ;;
esac

echo "==> Running container on http://localhost:8080"
docker rm -f bumpy-web >/dev/null 2>&1 || true
docker run -d --name bumpy-web -p 8080:80 "$IMAGE"

echo "Done. Open http://localhost:8080"
