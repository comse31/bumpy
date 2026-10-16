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

## 3. Готовый комплект для передачи

Всё, что нужно для запуска игры на другой машине (только Docker, без Node.js и Defold),
собрано в один архив:

- [`dist/bumpy-docker.zip`](dist/bumpy-docker.zip) — комплект для передачи;
- [`dist/bumpy-docker/`](dist/bumpy-docker) — та же сборка распакованной.

Содержимое комплекта:

| Файл | Назначение |
|------|------------|
| `bumpy-web-image.tar.gz` | готовый docker-образ (nginx + wasm-бандл игры) |
| `bumpy-web-image.tar.gz.sha256` | контрольная сумма SHA-256 |
| `run.cmd` / `run.sh` | загрузка образа и запуск контейнера (Windows / Linux-macOS) |
| `docker-compose.yml` | запуск через docker compose |
| `README.txt` | инструкция по запуску |

Запуск у получателя: распаковать архив и выполнить `run.cmd` (Windows) либо
`bash run.sh` (Linux/macOS), затем открыть <http://localhost:8080>.

Пересобрать комплект:

```bash
bash docker/export-image.sh          # -> dist/bumpy-web-image.tar.gz
```

## 4. Передача образа архивом

Если нужно передать игру на другую машину без исходников и сборки — экспортируйте
готовый образ в архив.

### Экспорт

Linux/macOS (bash):
```bash
bash docker/export-image.sh
# -> dist/bumpy-web-image.tar.gz
```

Windows (cmd):
```bat
docker\export-image.cmd
```

Ручной вариант:
```bash
# сжатый архив (~23 МБ)
docker save bumpy-web:latest -o dist/bumpy-web-image.tar
tar -czf dist/bumpy-web-image.tar.gz -C dist bumpy-web-image.tar

# либо сразу несжатый .tar (~54 МБ)
docker save bumpy-web:latest -o dist/bumpy-web-image.tar
```

В [`dist/`](dist) лежат оба варианта:
- [`dist/bumpy-web-image.tar`](dist/bumpy-web-image.tar) — несжатый образ (`docker save`), ~54 МБ;
- [`dist/bumpy-web-image.tar.gz`](dist/bumpy-web-image.tar.gz) — сжатый образ, ~23 МБ.

Оба подходят для передачи (например, через файлообменник или `scp`). Несжатый `.tar`
загружается командой `docker load -i dist/bumpy-web-image.tar` напрямую, без распаковки.

### Импорт и запуск на другой машине

Требуется только Docker (без Node.js, Defold и исходников).

Linux/macOS (bash):
```bash
bash docker/load-image.sh dist/bumpy-web-image.tar.gz
```

Windows (cmd):
```bat
docker\load-image.cmd dist\bumpy-web-image.tar.gz
```

Ручной вариант:
```bash
tar -xzf dist/bumpy-web-image.tar.gz -C dist
docker load -i dist/bumpy-web-image.tar
docker run -d --name bumpy-web -p 8080:80 bumpy-web:latest
```

Либо через compose с уже загруженным образом:
```bash
docker compose -f docker/docker-compose.image.yml up -d
```

Открыть <http://localhost:8080>.

## 5. CI: сборка и развёртывание на GitHub-раннере

Workflow [`.github/workflows/deploy-master.yml`](.github/workflows/deploy-master.yml)
запускается при **push в ветку `master`** (и вручную через `workflow_dispatch`) и:

1. скачивает headless-сборщик Defold `bob.jar` стабильной версии
   (`https://d.defold.com/stable/info.json` → `sha1`);
2. собирает HTML5-бандл: `java -jar bob.jar --platform wasm-web --archive
   --bundle-output dist/web/bumpy resolve build`;
3. собирает Docker-образ `bumpy-web:latest` из [`docker/Dockerfile`](docker/Dockerfile);
4. разворачивает контейнер на раннере (`docker run -d -p 8080:80`) и проверяет,
   что `http://localhost:8080/` отвечает.

В отличие от локальной сборки, CI **не требует запущенного редактора Defold**:
используется `bob.jar` — тот же сборщик, но в режиме командной строки.

Сборка бандла выполняется в официальном JDK-контейнере
(`eclipse-temurin:25-jdk`) через `docker run`, поэтому **не зависит от версии
Java, установленной на раннере**. Это важно, т.к. актуальный `bob.jar` собран под
Java 25 (class file version 69) и на старой системной Java падает с
`UnsupportedClassVersionError`. Репозиторий монтируется в контейнер
(`-v "$PWD":/project -w /project`), готовый бандл остаётся на раннере в
`dist/web/bumpy` и затем попадает в docker-образ.

Внутри этого же контейнера перед запуском `bob.jar` устанавливаются системные
библиотеки X11/GL (`libx11-6`, `libxext6`, `libxrender1`, `libgl1` и др.):
нативные инструменты `bob` (например, `ModelImporterJni`) динамически
линкуются с ними, и без этих `.so` сборка падает с
`Failed to unpack bundled Bob tools` / `UnsatisfiedLinkError: libXext.so.6`.
Реальный X-сервер не требуется — нужны только сами библиотеки.

> Раннер GitHub Actions эфемерный: контейнер живёт только во время выполнения
> job'а. Это развёртывание проверяет, что образ собирается и корректно
> запускается. Для постоянного хостинга замените шаг развёртывания на публикацию
> в реестр (`docker/build-push-action`) либо на деплой на ваш сервер.

## Структура

| Файл | Назначение |
|------|------------|
| [`docker/Dockerfile`](docker/Dockerfile) | Образ `nginx:1.27-alpine`, копирует бандл в `/usr/share/nginx/html` |
| [`docker/nginx.conf`](docker/nginx.conf) | MIME `application/wasm`, gzip, кэширование, SPA-fallback |
| [`docker/docker-compose.yml`](docker/docker-compose.yml) | Сборка образа из исходников и запуск, порт `8080:80` |
| [`docker/docker-compose.image.yml`](docker/docker-compose.image.yml) | Запуск уже загруженного образа (без сборки) |
| [`docker/build-and-run.sh`](docker/build-and-run.sh) | Сборка бандла + образ + запуск |
| [`docker/export-image.sh`](docker/export-image.sh) / [`docker/export-image.cmd`](docker/export-image.cmd) | Экспорт образа в `dist/bumpy-web-image.tar.gz` |
| [`docker/load-image.sh`](docker/load-image.sh) / [`docker/load-image.cmd`](docker/load-image.cmd) | Импорт образа из архива и запуск |
| [`dist/bumpy-docker.zip`](dist/bumpy-docker.zip) | Готовый комплект для передачи (образ + скрипты запуска + README) |
| [`dist/bumpy-docker/`](dist/bumpy-docker) | Распакованный комплект для передачи |
| [`tools/api_bundle_html5.js`](tools/api_bundle_html5.js) | Бандлинг `wasm-web` через Defold Editor HTTP API |
| [`.dockerignore`](.dockerignore) | Минимизация контекста сборки образа |

## Замечания

- Игра должна открываться по HTTP (не через `file://`) — бандл рассчитан на загрузку с веб-сервера.
- Заголовки `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` для `.wasm` заданы на случай включения потоков (pthread) в бандле.
- Порт публикации меняется в [`docker/docker-compose.yml`](docker/docker-compose.yml) (`ports`).
