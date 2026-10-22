#!/usr/bin/env bash
# Export the bumpy-web docker image to a transferable gzipped archive.
# Run from the repository root: bash docker/export-image.sh [image] [archive]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE="${1:-bumpy-web:latest}"
ARCHIVE="${2:-dist/bumpy-web-image.tar.gz}"

mkdir -p "$(dirname "$ARCHIVE")"

echo "==> Saving image '$IMAGE' -> '$ARCHIVE'"
docker save "$IMAGE" | gzip -9 > "$ARCHIVE"

echo "==> Done: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
