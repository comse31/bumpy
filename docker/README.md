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

Скрипт читает порт и токен из `.internal/editor.port` и `.internal/editor.token`
(их создаёт открытый редактор Defold) и вызывает `resolve build bundle` с
`--architectures wasm-web` — собирается только однопоточный движок, который
лежит внутри `bob.jar` (движка `wasm_pthread-web` там нет, и за ним пришлось бы
идти на `d.defold.com`). Доступные опции:

| Опция | По умолчанию | Назначение |
|-------|--------------|------------|
| `--output <dir>` | `dist/web` | Каталог `--bundle-output` |
| `--variant <v>` | `debug` | `debug` (быстрее) или `release` |
| `--architectures <a>` | `wasm-web` | Архитектуры движка |
| `--timeout <sec>` | `1800` | Таймаут запроса к `/bob` |

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

Скрипт делает всё то же самое (бандл → образ → контейнер) и сам

* проверяет, что `dist/web/bumpy/index.html` появился;
* при сбое `docker compose build` откатывается на `DOCKER_BUILDKIT=0` и затем на
  `docker build` (см. ниже);
* удаляет старый контейнер `bumpy-web` перед созданием нового — иначе
  `docker compose up` падает с `Conflict. The container name "/bumpy-web" is
  already in use`, если контейнер был запущен вручную или другим
  compose-проектом.

### Windows/Docker Desktop: `changes out of order`

На части конфигураций (Docker Compose 2.24 + BuildKit, контекст сборки — корень
репозитория) `docker compose build` падает ещё до первого шага:

```
ERROR: changes out of order: "docker/nginx.conf" ""
failed to solve: changes out of order
```

Это баг bake-ридера compose, а не Dockerfile: тот же контекст успешно
собирается через `docker build` и `docker buildx build`. Обходные пути:

```bash
# 1) классический сборщик (быстрее всего)
set DOCKER_BUILDKIT=0
docker compose -f docker/docker-compose.yml build

# 2) прямой docker build (без compose)
docker build -f docker/Dockerfile -t bumpy-web:latest .

# 3) buildx напрямую из каталога docker/
cd docker && docker buildx build -f Dockerfile -t bumpy-web:latest .. && cd ..
```

После этого контейнер поднимается обычным
`docker compose -f docker/docker-compose.yml up -d --force-recreate`.

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

1. тянет из GitHub Container Registry готовый образ-сборщик
   `ghcr.io/<owner>/bumpy-bob-builder:<sha1>` (публикуется вручную workflow
   `build-bob-image.yml`, см. ниже). Своего `docker build` в deploy нет;
2. собирает HTML5-бандл: `java -jar bob.jar --platform wasm-web
   --architectures wasm-web --archive --bundle-output dist/web resolve build
   bundle`
   (команда `bundle` обязательна — без неё `bob` только собирает, но не
   выкладывает бандл в `--bundle-output`; для HTML5 внутри `--bundle-output`
   создаётся вложенная папка с именем проекта, поэтому результат оказывается в
   `dist/web/bumpy/`);
3. останавливает и удаляет старый контейнер `bumpy-web`, если он существует
   (`docker stop` + `docker rm`);
4. собирает Docker-образ `bumpy-web:latest` из [`docker/Dockerfile`](docker/Dockerfile);
5. разворачивает контейнер на раннере (`docker run -d -p <HOST_PORT>:80`) и
   проверяет, что `http://localhost:<HOST_PORT>/` отвечает.

`--architectures wasm-web` важен: по умолчанию HTML5-бандлер собирает **два**
движка — `wasm-web` и `wasm_pthread-web` (`HTML5Bundler.bundleApplication` →
`buildWasm` для каждой платформы из `--architectures`). Движка
`wasm_pthread-web` в `bob.jar` нет, и `bob` качает его с `d.defold.com`, который
на раннере сильно троттлится (~100–200 Б/с) — сборка «зависает» на этапе
`Bundling`. Игре потоки не нужны (в проекте нет app manifest / `set_thread_count`),
поэтому собираем только однопоточный движок — он лежит внутри `bob.jar`
(`libexec/wasm-web`), в сеть ходить не нужно.

В отличие от локальной сборки, CI **не требует запущенного редактора Defold**:
используется `bob.jar` — тот же сборщик, но в режиме командной строки.

### Образ-сборщик (ручная задача build-bob-image.yml)

Workflow [`.github/workflows/build-bob-image.yml`](.github/workflows/build-bob-image.yml)
**запускается только вручную** (Actions → «Build & Publish bob-builder image» →
Run workflow). Он собирает образ-сборщик со **всеми** зависимостями и публикует
его в GitHub Container Registry (ghcr.io) под тегом версии `bob`:

```
ghcr.io/<owner>/bumpy-bob-builder:<sha1>
```

Этот же тег использует `deploy-master` (по текущей stable-версии Defold). При
смене версии Defold нужно один раз пересобрать образ (можно передать нужный
`sha1` во входном параметре `defold_sha1`).

Авторизация — через встроенный `GITHUB_TOKEN` (секреты не нужны): сборка
требует право `packages: write`, загрузка в deploy — `packages: read`.

Образ содержит `bob.jar` (≈220 МБ) — из ассета GitHub Release `bob-jar-<sha1>`,
а если релиза нет — с `d.defold.com`; в образе лежит `/opt/bob/bob.jar`. Движки
HTML5 не зашиваются: нужный однопоточный движок уже внутри `bob.jar`.

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

- **`bob.jar`** (≈220 МБ) зашивается в образ-сборщик слоем `RUN`, который
  инвалидируется только при смене `BOB_SHA1` (версии Defold);
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
| [`.github/workflows/build-bob-image.yml`](.github/workflows/build-bob-image.yml) | Ручная сборка и публикация образа-сборщика в ghcr.io (тег = версия bob) |
| [`docker/Dockerfile`](docker/Dockerfile) | Образ `nginx:1.27-alpine`, копирует бандл в `/usr/share/nginx/html` |
| [`docker/bob-builder.Dockerfile`](docker/bob-builder.Dockerfile) | Образ-сборщик `bumpy-bob-builder` (JDK 25 + библиотеки X11/GL + bob.jar) для CI |
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

## 6. Панель Services в IntelliJ IDEA (Ubuntu)

Чтобы [`docker/docker-compose.yml`](docker/docker-compose.yml) отображался в
окне **Services** (View → Tool Windows → Services) и контейнерами можно было
управлять из IDE, нужны три вещи: доступ к Docker-сокету, включённый плагин
Docker и добавленная конфигурация Docker/Compose.

### 6.1 Доступ к `/var/run/docker.sock`

Сокет принадлежит `root:docker` с правами `660`, поэтому пользователь должен
входить в группу `docker`:

```bash
sudo usermod -aG docker "$USER"
```

Группы применяются только к **новым** процессам. После `usermod`:

- перелогиньтесь в сессию (или выполните `newgrp docker` в терминале);
- **обязательно перезапустите IDEA**, если она была запущена до `usermod` —
  процесс наследует список групп на момент старта. Проверить, видит ли IDE
  сокет, можно так:

```bash
cat /proc/$(pgrep -f idea-IU | head -1)/status | grep ^Groups
getent group docker        # убедиться, что gid есть в списке Groups
```

Если gid группы `docker` в `Groups` процесса IDEA отсутствует — Docker-плагин
будет показывать «Cannot connect» независимо от настроек.

Временное решение без перелогина (ACL на сокет, действует до перезапуска
Docker — после него сокет создаётся заново):

```bash
sudo setfacl -m "u:$USER:rw" /var/run/docker.sock
```

Проверка, что доступ есть именно через сокет, без группы:

```bash
env -i PATH=/usr/bin:/bin HOME="$HOME" docker ps
```

### 6.2 Плагин Docker

Плагин **Docker** (`Docker`, id `Docker`) входит в состав IntelliJ IDEA
Ultimate и обычно включён. Проверить: Settings → Plugins → Installed → вкладка
Bundled, найти «Docker». Если выключен — включить и перезапустить IDE.

Плагин **Dev Containers** (`org.jetbrains.plugins.docker.gateway`) для запуска
compose не нужен; в логе он может ругаться
`requires plugin with id=com.intellij.modules.ultimate` — на работу
Docker/Compose это не влияет.

### 6.3 Подключение Docker-демона

Settings → Build, Execution, Deployment → Docker → **+** → Docker:

| Поле | Значение |
|------|----------|
| Name | `Docker` |
| Connect to Docker daemon with | Docker for Linux |
| Docker executable | `/usr/bin/docker` |
| Docker Compose executable | `/usr/libexec/docker/cli-plugins/docker-compose` либо `docker compose` |

После **Apply** внизу окна появится «Connection successful». Если плагин
использует CLI (`docker-compose`), а не плагин compose v2, путь нужно указать
явно: отдельного бинарника `docker-compose` в системе нет, есть только
`/usr/libexec/docker/cli-plugins/docker-compose` (Compose v5.6.0).

### 6.4 Добавление compose-файла

В окне **Services**: **+** → Docker → Docker Compose (или правый клик по
`docker/docker-compose.yml` в Project → **Run 'docker-compose.yml'**).

- Compose file: `docker/docker-compose.yml`
- Project name / Environment: оставить по умолчанию (`name: bumpy` уже задан
  в файле, `build.context: ..` разрешается относительно каталога compose-файла)
- После первого запуска сервис `bumpy-web` появится в дереве Services: логи,
  port bindings `8080→80`, кнопки Start/Stop/Restart/Down.

Конфигурация запуска сохраняется в `.idea/` (каталог в `.gitignore`), поэтому
каждому разработчику нужно добавить её один раз.

### 6.5 Частые проблемы

| Симптом | Причина / решение |
|---------|-------------------|
| «Cannot connect to Docker daemon» | пользователь не в группе `docker`, либо IDEA запущена до `usermod` — перезапустить IDE |
| «Permission denied … docker.sock» | то же; проверить `/proc/<pid идеи>/status` → `Groups` |
| Compose-файл открывается, но сервисы не видны | не добавлена конфигурация Docker Compose в Services |
| «Docker Compose executable not found» | указать `/usr/libexec/docker/cli-plugins/docker-compose` |
| После перезапуска Docker снова «permission denied» | слетел ACL — лечится группой `docker` (постоянное решение), а не `setfacl` |
| Контейнер запущен, но порт занят | изменить `ports` в [`docker/docker-compose.yml`](docker/docker-compose.yml), у нашего CI занят `9999` |

## 7. Управление и камера в HTML5

### Камера

В вебе камера всегда работает в игровом режиме (настройка
`bumpy.camera_mode = "auto"` в [`game.project`](../game.project:38) трактуется
как `cover` для платформы `HTML5`):

- центр экрана плавно ведётся к центру **ячейки**, в которой находится мяч, —
  камера зависит только от номера ячейки, но не от позиции мяча внутри неё;
  поэтому при прыжках мяча в пределах одной ячейки камера не двигается;
- отступ за краем поля — половина ячейки (`CELL_W/2 = 80`, `CELL_H/2 = 53.3`):
  в крайней ячейке поле не упирается в край экрана, и камера там тоже стоит;
- по оси, где поле видно целиком, камера зафиксирована по центру поля.

### Панорамирование свайпом

Свайп по экрану двигает камеру. Когда игрок отпускает палец и в течение
**1 секунды** (`PAN_IDLE_SEC`) ничего не делает, фокус плавно возвращается к
ячейке мяча. Любое игровое действие (тап по ячейке или нажатие экранной
кнопки) возвращает фокус немедленно — сообщением `camera_focus`.

| Параметр | Значение | Где |
|---|---|---|
| Порог свайпа | 3% меньшей стороны окна | `PAN_THRESHOLD_FRAC` в [`controls.gui_script`](../main/controls/controls.gui_script:35) |
| Задержка возврата фокуса | 1.0 с | `PAN_IDLE_SEC` в [`camera.script`](../main/render/camera.script:69) |
| Предел сдвига | половина ячейки за краем поля | `MARGIN_X` / `MARGIN_Y` в [`camera.script`](../main/render/camera.script:50) |

Свайп не мешает управлению: в режиме `cells` команда мячу отправляется только
при отпускании, если смещение пальца не превысило порог; в режиме `buttons`
свайп начинается только при нажатии вне экранных кнопок. Сообщение
`camera_pan` несёт сдвиг в мировых единицах, камера сама ограничивает его
границами поля.

Проверка на окне 1280×720 (видимая область 960×460): свайп на 200 px сдвигает
камеру на 150 мировых единиц (упирается в предел 80 за краем поля), после 1 с
бездействия камера возвращается к центру ячейки ≈1.2 с.

## Замечания

- Игра должна открываться по HTTP (не через `file://`) — бандл рассчитан на загрузку с веб-сервера.
- Заголовки `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` для `.wasm` заданы на случай включения потоков (pthread) в бандле.
- Порт публикации меняется в [`docker/docker-compose.yml`](docker/docker-compose.yml) (`ports`).
