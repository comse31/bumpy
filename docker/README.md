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

## 5. CI: сборка и развёртывание на self-hosted раннере

Workflow [`.github/workflows/deploy-master.yml`](.github/workflows/deploy-master.yml)
запускается при **push в ветку `master`** (и вручную через `workflow_dispatch`) на
self-hosted раннере (`runs-on: [self-hosted]`) и:

1. тянет из Docker Hub готовый образ-сборщик `bumpy-bob-builder:<sha1>`
   (публикуется вручную workflow `build-bob-image.yml`, см. ниже). Своего
   `docker build` в deploy нет — во время сборки **ничего не качается**;
2. копирует из образа кэш движков HTML5 (`/opt/bob/engine-cache`) в
   `.internal/cache` проекта — иначе `bob` полез бы качать движок
   `wasm_pthread-web` с `d.defold.com`;
3. собирает HTML5-бандл: `java -jar bob.jar --platform wasm-web --archive
   --bundle-output dist/web resolve build bundle`
   (команда `bundle` обязательна — без неё `bob` только собирает, но не
   выкладывает бандл в `--bundle-output`; для HTML5 внутри `--bundle-output`
   создаётся вложенная папка с именем проекта, поэтому результат оказывается в
   `dist/web/bumpy/`);
4. останавливает и удаляет старый контейнер `bumpy-web`, если он существует
   (`docker stop` + `docker rm`);
5. собирает Docker-образ `bumpy-web:latest` из [`docker/Dockerfile`](docker/Dockerfile);
6. разворачивает контейнер на раннере (`docker run -d -p <HOST_PORT>:80`) и
   проверяет, что `http://localhost:<HOST_PORT>/` отвечает.

В отличие от локальной сборки, CI **не требует запущенного редактора Defold**:
используется `bob.jar` — тот же сборщик, но в режиме командной строки.

### Образ-сборщик (ручная задача build-bob-image.yml)

Workflow [`.github/workflows/build-bob-image.yml`](.github/workflows/build-bob-image.yml)
**запускается только вручную** (Actions → «Build & Publish bob-builder image» →
Run workflow). Он собирает образ-сборщик со **всеми** зависимостями и публикует
его в Docker Hub под тегом версии `bob`:

```
<DOCKERHUB_USERNAME>/bumpy-bob-builder:<sha1>
```

Этот же тег использует `deploy-master` (по текущей stable-версии Defold). При
смене версии Defold нужно один раз пересобрать образ (можно передать нужный
`sha1` во входном параметре `defold_sha1`).

Требуются секреты репозитория `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN`.

Почему образ нужен как зависимость: `bob` при бандлинге HTML5 скачивает движок
с `d.defold.com`, а тот на раннере сильно троттлится (единицы КБ/с) — сборка
«зависает» на этапе `Bundling`. Поэтому в образ заранее кладутся:

- `bob.jar` (≈220 МБ) — из ассета GitHub Release `bob-jar-<sha1>`, а если релиза
  нет — с `d.defold.com`; в образе лежит `/opt/bob/bob.jar`;
- движки HTML5 — в `/opt/bob/engine-cache/<platform>/<sha1>/`:
  `wasm-web` распаковывается из `bob.jar` (`libexec/wasm-web`, сеть не нужна),
  а `wasm_pthread-web` (в `bob.jar` его нет) скачивается один раз на этапе
  `docker build`.

`deploy-master` копирует `engine-cache` в `.internal/cache` проекта — `bob`
кэширует артефакты движка в `<root>/.internal/cache/<platform>/<sha1>/` и
качает с `d.defold.com` только если файла нет.

### Почему контейнер и что внутри

Сборка бандла выполняется в контейнере `bumpy-bob-builder:<sha1>` через
`docker run`, поэтому **не зависит от версии Java, установленной на раннере**.
Это важно, т.к. актуальный `bob.jar` собран под Java 25 (class file version 69) и
на старой системной Java падает с `UnsupportedClassVersionError`. Репозиторий
монтируется в контейнер (`-v "$PWD":/project -w /project`), готовый бандл
остаётся на раннере в `dist/web/bumpy` и затем попадает в docker-образ.

Образ-сборщик [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile)
базируется на `eclipse-temurin:25-jdk` и содержит системные библиотеки X11/GL
(`libx11-6`, `libxext6`, `libxrender1`, `libgl1` и др.): нативные инструменты
`bob` (например, `ModelImporterJni`) динамически линкуются с ними, и без этих
`.so` сборка падает с `Failed to unpack bundled Bob tools` /
`UnsatisfiedLinkError: libXext.so.6`. Реальный X-сервер не требуется — нужны
только сами библиотеки.

### Кэширование артефактов сборки

Чтобы не скачивать/не собирать одно и то же при каждом пуше:

- **`bob.jar`** (≈220 МБ) и движки HTML5 зашиваются в образ-сборщик слоями
  `RUN`, которые инвалидируются только при смене `BOB_SHA1` (версии Defold);
- **образ-сборщик** `bumpy-bob-builder:<sha1>` пересобирается только при
  изменении [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile) или
  значения `sha1` — вручную через `build-bob-image.yml`; слои с `apt-get`
  берутся из кэша Docker;
- базовые образы `nginx:1.27-alpine` и `eclipse-temurin:25-jdk` остаются
  локально на раннере после первой загрузки.

> `docker` в workflow — это Docker-демон **self-hosted раннера** (реальная
> машина, где выполняется job), а не Docker на машине разработчика. Так как
> раннер постоянный, контейнер `bumpy-web` остаётся работать и после завершения
> workflow; при следующем пуше старый контейнер останавливается и удаляется,
> затем поднимается новый. На раннере должны быть установлены Docker и Python 3
> (для разбора `info.json`). Все workflow используют `runs-on: [self-hosted]`.

## Структура

| Файл | Назначение |
|------|------------|
| [`.github/workflows/fetch-bob.yml`](.github/workflows/fetch-bob.yml) | Ручная загрузка `bob.jar` и публикация как ассет GitHub Release |
| [`.github/workflows/build-bob-image.yml`](.github/workflows/build-bob-image.yml) | Ручная сборка и публикация образа-сборщика в Docker Hub (тег = версия bob) |
| [`docker/Dockerfile`](docker/Dockerfile) | Образ `nginx:1.27-alpine`, копирует бандл в `/usr/share/nginx/html` |
| [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile) | Образ-сборщик `bumpy-bob-builder` (JDK 25 + библиотеки X11/GL + bob.jar + движки HTML5) для CI |
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
