# Bumpy — HTML5 сборка в Docker (nginx)

Публикация игры Bumpy (Defold, платформа `wasm-web`) в веб через nginx в Docker.

## Требования

- Node.js (для скрипта сборки бандла через HTTP API редактора Defold)
- Открытый редактор Defold с проектом (файлы `.internal/editor.port` и `.internal/editor.token` создаются редактором)
- Docker + Docker Compose

## 1. Сборка HTML5 бандла

Бандл собирается через Defold Editor HTTP API (`/bob`, `platform=wasm-web`, `archive=true`):

```bash
node tools/api_bundle_html5.js
```

Результат:
- [`build/web/`](build/web) — кэш/промежуточные артефакты сборки (в `.gitignore`)
- [`dist/web/bumpy/`](dist/web/bumpy) — готовый к раздаче бандл: `index.html`, `dmloader.js`, `*.wasm`, `archive/`

## 2. Сборка и запуск контейнера

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

Открыть в браузере: <http://localhost:8080>

Остановить:

```bash
docker compose -f docker/docker-compose.yml down
```

## Альтернатива: без docker-compose

```bash
docker build -f docker/Dockerfile -t bumpy-web .
docker run --rm -p 8080:80 bumpy-web
```

## Всё одной командой

```bash
bash docker/build-and-run.sh
```

## Структура

| Файл | Назначение |
|------|------------|
| [`docker/Dockerfile`](docker/Dockerfile) | Образ `nginx:1.27-alpine`, копирует бандл в `/usr/share/nginx/html` |
| [`docker/nginx.conf`](docker/nginx.conf) | MIME `application/wasm`, gzip, кэширование, SPA-fallback |
| [`docker/docker-compose.yml`](docker/docker-compose.yml) | Проброс порта `8080:80` |
| [`docker/build-and-run.sh`](docker/build-and-run.sh) | Сборка бандла + образ + запуск |
| [`tools/api_bundle_html5.js`](tools/api_bundle_html5.js) | Бандлинг `wasm-web` через Defold Editor HTTP API |
| [`.dockerignore`](.dockerignore) | Минимизация контекста сборки образа |

## Замечания

- Игра должна открываться по HTTP (не через `file://`) — бандл рассчитан на загрузку с веб-сервера.
- Заголовки `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` для `.wasm` заданы на случай включения потоков (pthread) в бандле.
- Порт публикации меняется в [`docker/docker-compose.yml`](docker/docker-compose.yml) (`ports`).
