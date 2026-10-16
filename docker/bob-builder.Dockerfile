# Переиспользуемый образ-сборщик Defold (bob.jar) для CI.
#
# bob.jar собран под Java 25 (class file version 69), поэтому базой служит
# eclipse-temurin:25-jdk. Нативные инструменты bob (ModelImporterJni и др.)
# динамически линкуются с системными библиотеками X11/GL — устанавливаем их
# здесь один раз, чтобы не выполнять apt-get при каждом запуске workflow.
# Реальный X-сервер (дисплей) не требуется — нужны только сами .so.
#
# Сам bob.jar СКАЧИВАЕТСЯ ПРЯМО В ОБРАЗ на этапе docker build по аргументу
# BOB_SHA1 (версия Defold). Сначала пробуем ассет GitHub Release
# `bob-jar-<sha1>` (быстрее), при неудаче — d.defold.com. Скачивание идёт
# внутри образа, поэтому на хосте bob.jar не нужен.
#
# Слой RUN инвалидируется при изменении аргумента BOB_SHA1, т.е. при смене
# версии Defold; при неизменной версии слой берётся из кэша Docker.
#
# Сборка (кэшируется Docker'ом на раннере):
#   docker build \
#     --build-arg BOB_SHA1=<sha1> \
#     -f docker/bob-builder.Dockerfile \
#     -t bumpy-bob-builder:25-jdk .

FROM eclipse-temurin:25-jdk

# Версия Defold (sha1) для скачивания bob.jar. Передаётся при docker build:
#   --build-arg BOB_SHA1=<sha1>
ARG BOB_SHA1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates \
        libx11-6 libxext6 libxrender1 libxi6 libxcursor1 \
        libxrandr2 libxinerama1 libxfixes3 libxxf86vm1 \
        libxcb1 libxau6 libxdmcp6 libbsd0 \
        libgl1 libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# bob.jar скачивается прямо в образ. Сначала — ассет GitHub Release
# `bob-jar-<sha1>` (быстрее), при неудаче — с d.defold.com.
# Слой инвалидируется при смене BOB_SHA1 (версии Defold).
RUN set -eux; \
    mkdir -p /opt/bob; \
    ASSET_URL="https://github.com/comse31/bumpy/releases/download/bob-jar-${BOB_SHA1}/bob.jar"; \
    if curl -fsSL -o /opt/bob/bob.jar "${ASSET_URL}"; then \
        echo "bob.jar получен из GitHub Release bob-jar-${BOB_SHA1}"; \
    else \
        echo "Релиз bob-jar-${BOB_SHA1} недоступен — скачиваю с d.defold.com"; \
        curl -fsSL -o /opt/bob/bob.jar "https://d.defold.com/archive/${BOB_SHA1}/bob/bob.jar"; \
    fi; \
    ls -lh /opt/bob/bob.jar

WORKDIR /opt/bob
