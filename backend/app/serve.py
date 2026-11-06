"""Запуск API через uvicorn с параметрами из config.yml.

Скрипт вместо команды `uvicorn app.main:app --host ... --port ...` нужен, чтобы
host/port/log_level не дублировались в Dockerfile и compose: единственный
источник — секция api в config.yml.
"""

from __future__ import annotations

import logging

import uvicorn

from .settings import load_settings


def main() -> None:
    settings = load_settings()
    logging.getLogger("bumpy").info(
        "запуск API на %s:%s (конфиг: %s)",
        settings.api.host,
        settings.api.port,
        settings.config_path,
    )
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.api.log_level,
        access_log=True,
        # За nginx реальный клиент приходит в X-Forwarded-For; uvicorn по
        # умолчанию доверяет только localhost, а nginx в той же сети docker.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
