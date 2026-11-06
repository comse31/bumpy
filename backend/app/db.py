"""Работа с SQLite: подключение, PRAGMA и применение миграций.

SQLite выбран как лёгкая встраиваемая СУБД: вся база — один файл, отдельный
сервер БД не нужен, а WAL позволяет читать данные, пока идёт запись. Файл
лежит в docker-томе, поэтому данные переживают пересоздание контейнера.

Соединение открывается на запрос и закрывается после него: у sqlite3 нет
пула, а открытие локального файла дешево. Схема (таблицы) создаётся из
SQL-миграций в database.migrations_dir при старте приложения.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .settings import DatabaseSettings

log = logging.getLogger("bumpy.db")


def utc_now() -> str:
    """Текущее время в UTC в виде ISO-8601 с суффиксом Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Database:
    """Владелец файла БД: миграции и выдача соединений."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.path: Path = settings.path
        self.migrations_dir: Path = settings.migrations_dir

    # --- соединение ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=max(self.settings.busy_timeout_ms, 0) / 1000.0,
            isolation_level=None,  # транзакции управляются явно (BEGIN/COMMIT)
        )
        conn.row_factory = sqlite3.Row
        # Внешние ключи в SQLite выключены по умолчанию — включаем для
        # ON DELETE CASCADE у player_events.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA journal_mode = {self.settings.journal_mode}")
        conn.execute(f"PRAGMA synchronous = {self.settings.synchronous}")
        conn.execute(f"PRAGMA busy_timeout = {int(self.settings.busy_timeout_ms)}")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Соединение на время запроса; закрывается в любом случае."""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Соединение с открытой транзакцией записи (BEGIN IMMEDIATE ... COMMIT)."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    # --- миграции -----------------------------------------------------------

    def _applied(self, conn: sqlite3.Connection) -> set[str]:
        """Уже применённые миграции (пусто, если таблицы ещё нет)."""
        try:
            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {str(row["version"]) for row in rows}

    def migrate(self) -> list[str]:
        """Применить миграции из migrations_dir в порядке имени файла.

        Возвращает список применённых версий.

        ВАЖНО: sqlite3.Connection.executescript() перед выполнением неявно
        коммитит и работает вне транзакции, поэтому оборачивать его в
        BEGIN/COMMIT нельзя («cannot commit - no transaction is active»).
        SQL-миграции написаны идемпотентно (CREATE TABLE IF NOT EXISTS), а
        версия фиксируется отдельной транзакцией сразу после скрипта: при
        прерывании между этими шагами повторный запуск безопасно выполнит
        скрипт ещё раз.
        """
        if not self.migrations_dir.is_dir():
            raise RuntimeError(f"каталог миграций не найден: {self.migrations_dir}")

        files = sorted(p for p in self.migrations_dir.iterdir() if p.suffix == ".sql")
        applied: list[str] = []
        if not files:
            log.warning("в %s нет SQL-миграций", self.migrations_dir)
            return applied

        with self.connection() as conn:
            done = self._applied(conn)

            for file in files:
                version = file.stem
                if version in done:
                    continue
                sql = file.read_text(encoding="utf-8")
                conn.executescript(sql)
                # запись о версии — отдельной транзакцией (executescript её уже закрыл)
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )
                conn.execute("COMMIT")
                applied.append(version)
                log.info("миграция применена: %s", version)

        return applied

    def init(self) -> None:
        """Подготовить каталог файла БД и применить миграции."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        log.info("база данных: %s", self.path)
        applied = self.migrate()
        if applied:
            log.info("применено миграций: %d (%s)", len(applied), ", ".join(applied))
        else:
            log.info("схема БД актуальна")

    def healthcheck(self) -> bool:
        """Быстрая проверка: БД открывается и отвечает на простой запрос."""
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error as exc:
            log.error("healthcheck БД не прошёл: %s", exc)
            return False
