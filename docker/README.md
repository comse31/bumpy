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

1. собирает образ-сборщик, в который headless-сборщик Defold `bob.jar`
   скачивается прямо на этапе `docker build` (`--build-arg BOB_SHA1`): из ассета
   GitHub Release `bob-jar-<sha1>` (публикуется вручную workflow
   `fetch-bob.yml`), иначе с `https://d.defold.com`;
2. собирает HTML5-бандл: `java -jar bob.jar --platform wasm-web --archive
   --bundle-output dist/web resolve build bundle`
   (команда `bundle` обязательна — без неё `bob` только собирает, но не
   выкладывает бандл в `--bundle-output`; для HTML5 внутри `--bundle-output`
   создаётся вложенная папка с именем проекта, поэтому результат оказывается в
   `dist/web/bumpy/`);
3. останавливает и удаляет старый контейнер `bumpy-web`, если он существует
   (`docker stop` + `docker rm`);
4. собирает Docker-образ `bumpy-web:latest` из [`docker/Dockerfile`](docker/Dockerfile);
5. разворачивает контейнер на раннере (`docker run -d -p <HOST_PORT>:80`) и
   проверяет, что `http://localhost:<HOST_PORT>/` отвечает.

В отличие от локальной сборки, CI **не требует запущенного редактора Defold**:
используется `bob.jar` — тот же сборщик, но в режиме командной строки.

### Предзагрузка bob.jar (ручная задача)

Чтобы не скачивать `bob.jar` (≈220 МБ) с `d.defold.com` при каждой сборке,
он загружается на GitHub один раз отдельным workflow
[`.github/workflows/fetch-bob.yml`](.github/workflows/fetch-bob.yml)
(**запускается только вручную**: Actions → «Fetch bob.jar (manual)» → Run
workflow). Задача выполняется на self-hosted раннере (`runs-on: [self-hosted]`)
и публикует файл как ассет GitHub Release с тегом `bob-jar-<sha1>`.

Основная задача сборки ([`deploy-master.yml`](.github/workflows/deploy-master.yml))
при сборке образа-сборщика передаёт в `docker build` аргумент
`--build-arg BOB_SHA1=<sha1>`, и `bob.jar` скачивается **внутри образа** прямо из
этого релиза по адресу
`https://github.com/comse31/bumpy/releases/download/bob-jar-<sha1>/bob.jar`,
и только если релиза нет — берётся из исходного `d.defold.com`. На хост-раннере
файл не сохраняется (см. ниже).

Порядок работы:
1. (однократно или при смене версии Defold) вручную запустить «Fetch bob.jar (manual)»;
2. обычные пуши в `master` запускают сборку: `docker build` скачивает `bob.jar`
   из релиза прямо в образ-сборщик.

Сборка бандла выполняется в контейнере `bumpy-bob-builder:25-jdk` через
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
только сами библиотеки. Образ собирается один раз и кэшируется Docker'ом, так
что `apt-get` при каждом запуске workflow не выполняется.

`bob.jar` **скачивается прямо в образ**. Последовательность такая:
1. workflow передаёт в `docker build` аргумент `--build-arg BOB_SHA1=<sha1>`;
2. `docker build` по [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile)
   в слое `RUN curl …` скачивает `bob.jar` (из GitHub Release или `d.defold.com`)
   сразу в образ: `/opt/bob/bob.jar`;
3. сборка бандла запускается как `java -jar /opt/bob/bob.jar …` — из образа, а
   не из смонтированного каталога.

Поэтому `bob.jar` не нужно ни монтировать в контейнер, ни сохранять на хост-раннере,
и слой `RUN`, скачивающий файл, инвалидируется только при смене значения
`BOB_SHA1`, т.е. при смене версии Defold.

### Кэширование артефактов сборки

Чтобы не скачивать/не собирать одно и то же при каждом пуше:

- **`bob.jar`** (≈220 МБ) скачивается из ассета GitHub Release `bob-jar-<sha1>`
  (публикуется вручную workflow `fetch-bob.yml`), а если релиза нет — с
  `d.defold.com`. Файл скачивается в образ-сборщик слоем `RUN curl …`, и этот
  слой инвалидируется только при смене `BOB_SHA1`, т.е. при смене версии
  Defold — повторно файл не скачивается;
- **образ-сборщик** `bumpy-bob-builder:25-jdk` пересобирается только при
  изменении [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile) или
  значения `BOB_SHA1`: слои с `apt-get` берутся из кэша Docker;
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
| [`docker/Dockerfile`](docker/Dockerfile) | Образ `nginx:1.27-alpine`, копирует бандл в `/usr/share/nginx/html` |
| [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile) | Образ-сборщик `bumpy-bob-builder` (JDK 25 + библиотеки X11/GL) для CI |
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
