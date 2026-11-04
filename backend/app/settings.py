"""Чтение настроек из config.yml.

Все настройки приложения и БД живут в одном YAML-файле (backend/config.yml).
Здесь — только разбор файла и разрешение относительных путей: код приложения
не содержит ни путей, ни лимитов.

Путь к конфигу берётся из переменной окружения BUMPY_CONFIG; если она не
задана, используется config.yml рядом с каталогом backend. Относительные пути
внутри конфига (database.path, database.migrations_dir) разрешаются
относительно каталога самого конфига — так локальный запуск и docker-образ
работают с одним и тем же файлом.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# backend/app/settings.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BACKEND_DIR / "config.yml"


class ConfigError(RuntimeError):
    """Конфиг отсутствует или содержит некорректные значения."""


@dataclass(frozen=True)
class DatabaseSettings:
    path: Path
    migrations_dir: Path
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    busy_timeout_ms: int = 5000
    events: bool = True


@dataclass(frozen=True)
class ApiSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str = ""
    max_name_len: int = 16
    max_levels: int = 1000
    max_visits: int = 1000000
    max_items: int = 9999
    events_limit: int = 20
    page_size: int = 50
    cors_origins: tuple[str, ...] = field(default_factory=tuple)
    log_level: str = "info"
    version: int = 1
    # пароли игроков: итерации PBKDF2 и границы длины
    password_iterations: int = 120000
    password_min_len: int = 4
    password_max_len: int = 32


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings
    api: ApiSettings
    config_path: Path


def _resolve(base: Path, value: Any) -> Path:
    """Разрешить путь из конфига: абсолютный оставить, относительный — от base."""
    if value is None:
        raise ConfigError("путь не задан")
    p = Path(str(value)).expanduser()
    if not p.is_absolute():
        p = base / p
    return p


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"секция {name!r} должна быть словарём")
    return value


def _int(raw: dict[str, Any], key: str, default: int, *, allow_zero: bool = False) -> int:
    value = raw.get(key, default)
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key}: ожидалось целое число, получено {value!r}") from exc
    if ivalue < 0 or (ivalue == 0 and not allow_zero):
        raise ConfigError(f"{key}: ожидалось положительное число, получено {ivalue}")
    return ivalue


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Прочитать конфиг и вернуть настройки. Бросает ConfigError при ошибке."""
    if config_path is None:
        config_path = os.environ.get("BUMPY_CONFIG") or DEFAULT_CONFIG_PATH
    path = Path(config_path).expanduser().resolve()

    if not path.is_file():
        raise ConfigError(f"конфиг не найден: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"конфиг {path} должен быть словарём верхнего уровня")

    base = path.parent
    db_raw = _section(raw, "database")
    api_raw = _section(raw, "api")

    journal_mode = str(db_raw.get("journal_mode", "WAL")).upper()
    if journal_mode not in ("DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"):
        raise ConfigError(f"database.journal_mode: недопустимое значение {journal_mode!r}")

    synchronous = str(db_raw.get("synchronous", "NORMAL")).upper()
    if synchronous not in ("OFF", "NORMAL", "FULL", "EXTRA"):
        raise ConfigError(f"database.synchronous: недопустимое значение {synchronous!r}")

    cors = api_raw.get("cors_origins") or []
    if not isinstance(cors, (list, tuple)):
        raise ConfigError("api.cors_origins: ожидался список строк")

    database = DatabaseSettings(
        path=_resolve(base, db_raw.get("path", "data/bumpy.db")),
        migrations_dir=_resolve(base, db_raw.get("migrations_dir", "migrations")),
        journal_mode=journal_mode,
        synchronous=synchronous,
        busy_timeout_ms=_int(db_raw, "busy_timeout_ms", 5000, allow_zero=True),
        events=bool(db_raw.get("events", True)),
    )

    api = ApiSettings(
        host=str(api_raw.get("host", "0.0.0.0")),
        port=_int(api_raw, "port", 8000),
        api_key=str(api_raw.get("api_key", "") or ""),
        max_name_len=_int(api_raw, "max_name_len", 16),
        max_levels=_int(api_raw, "max_levels", 1000),
        max_visits=_int(api_raw, "max_visits", 1000000, allow_zero=True),
        max_items=_int(api_raw, "max_items", 9999, allow_zero=True),
        events_limit=_int(api_raw, "events_limit", 20, allow_zero=True),
        page_size=_int(api_raw, "page_size", 50),
        cors_origins=tuple(str(origin) for origin in cors),
        log_level=str(api_raw.get("log_level", "info")).lower(),
        version=_int(api_raw, "version", 1),
        password_iterations=_int(api_raw, "password_iterations", 120000),
        password_min_len=_int(api_raw, "password_min_len", 4),
        password_max_len=_int(api_raw, "password_max_len", 32),
    )

    if api.password_min_len >= api.password_max_len:
        raise ConfigError("api.password_min_len должен быть меньше api.password_max_len")

    return Settings(database=database, api=api, config_path=path)
