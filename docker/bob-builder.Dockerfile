# Переиспользуемый образ-сборщик Defold (bob.jar) для CI.
#
# bob.jar собран под Java 25 (class file version 69), поэтому базой служит
# eclipse-temurin:25-jdk. Нативные инструменты bob (ModelImporterJni и др.)
# динамически линкуются с системными библиотеками X11/GL — устанавливаем их
# здесь один раз, чтобы не выполнять apt-get при каждом запуске workflow.
# Реальный X-сервер (дисплей) не требуется — нужны только сами .so.
#
# Сборка (кэшируется Docker'ом на раннере):
#   docker build -f docker/bob-builder.Dockerfile -t bumpy-bob-builder:25-jdk .

FROM eclipse-temurin:25-jdk

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libx11-6 libxext6 libxrender1 libxi6 libxcursor1 \
        libxrandr2 libxinerama1 libxfixes3 libxxf86vm1 \
        libxcb1 libxau6 libxdmcp6 libbsd0 \
        libgl1 libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*
