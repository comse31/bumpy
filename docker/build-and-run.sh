#!/usr/bin/env bash
# Build the HTML5 bundle and (re)build + start the nginx docker container.
# Run from the repository root: bash docker/build-and-run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Bundling HTML5 (wasm-web) via Defold editor API"
node tools/api_bundle_html5.js

echo "==> Building docker image"
docker compose -f docker/docker-compose.yml build

echo "==> Starting container on http://localhost:8080"
docker compose -f docker/docker-compose.yml up -d

echo "Done. Open http://localhost:8080"
