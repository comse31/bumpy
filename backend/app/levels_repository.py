"""Хранилище сгенерированных уровней (таблица generated_levels).

Слой тонкий, как и PlayerRepository: SQL в одном месте, HTTP-слой занимается
только валидацией и раздачей.

Правила:
  * в таблицу попадают только уровни со статусом "solvable" — это проверяется
    ещё в схеме (GeneratedLevelIn), а здесь дублируется на случай внутренних
    вызовов из скрипта генерации;
  * seed уникален: повторная вставка того же seed не создаёт дубликат
    (INSERT OR IGNORE), потому что уровень по seed воспроизводим;
  * случайная выдача (random) идёт по последним уровням: ORDER BY created_at
    DESC с ограничением окна, чтобы давно забытые уровни не вытесняли свежие.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from .db import Database, utc_now
from .schemas import GeneratedLevelIn, GeneratedLevelOut, GeneratedLevelsStatsOut


def _level_id(seed: int, payload: str) -> str:
    """Стабильный идентификатор записи: seed + хэш payload.

    По seed уровень воспроизводим, поэтому повторная генерация того же самого
    уровня даёт тот же level_id — клиент не получит «новый» уровень, который
    на самом деле тот же.
    """
    digest = hashlib.sha1(f"{seed}:{payload}".encode("utf-8")).hexdigest()[:16]
    return f"g{seed}_{digest}"


def _row_to_level(row: sqlite3.Row) -> GeneratedLevelOut:
    return GeneratedLevelOut(
        level_id=str(row["level_id"]),
        seed=int(row["seed"]),
        level=int(row["level"]),
        status=str(row["status"]),
        drops=int(row["drops"]),
        keys=int(row["keys"]),
        hammers=int(row["hammers"]),
        created_at=row["created_at"],
        payload=str(row["payload"]),
    )


class GeneratedLevelRepository:
    """Доступ к таблице generated_levels."""

    def __init__(self, db: Database, *, window: int = 500) -> None:
        self.db = db
        # сколько последних уровней участвует в случайной выдаче
        self.window = max(1, int(window))

    # --- запись -------------------------------------------------------------

    def add(self, item: GeneratedLevelIn) -> GeneratedLevelOut:
        """Сохранить уровень. Дубликат по seed возвращает уже существующую запись."""
        if item.status != "solvable":
            raise ValueError("сохраняются только уровни со статусом solvable")

        now = utc_now()
        level_id = _level_id(item.seed, item.payload)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO generated_levels "
                "(level_id, seed, level, payload, status, drops, keys, hammers, "
                "generator, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level_id,
                    int(item.seed),
                    int(item.level),
                    item.payload,
                    item.status,
                    int(item.drops),
                    int(item.keys),
                    int(item.hammers),
                    item.generator,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM generated_levels WHERE seed = ?", (int(item.seed),)
            ).fetchone()
        if row is None:  # pragma: no cover — INSERT OR IGNORE не мог не создать
            raise RuntimeError("не удалось сохранить сгенерированный уровень")
        return _row_to_level(row)

    def liked_seed(self) -> int:
        """Следующий seed для генератора: максимальный + 1.

        Так генерация продолжает последовательность и не зацикливается на уже
        проверенных кандидатах между часовыми запусками.
        """
        with self.db.connection() as conn:
            row = conn.execute("SELECT MAX(seed) AS s FROM generated_levels").fetchone()
        return int(row["s"] or 0) + 1 if row else 1

    # --- чтение -------------------------------------------------------------

    def random(self) -> GeneratedLevelOut | None:
        """Случайный уровень из окна последних записей."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM generated_levels "
                "WHERE level_id IN ("
                "  SELECT level_id FROM generated_levels "
                "  ORDER BY created_at DESC LIMIT ?"
                ") ORDER BY RANDOM() LIMIT 1",
                (self.window,),
            ).fetchone()
        return None if row is None else _row_to_level(row)

    def latest(self, limit: int = 10) -> list[GeneratedLevelOut]:
        """Последние сгенерированные уровни (для отладки и админки)."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM generated_levels ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_to_level(row) for row in rows]

    def get(self, level_id: str) -> GeneratedLevelOut | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM generated_levels WHERE level_id = ?", (level_id,)
            ).fetchone()
        return None if row is None else _row_to_level(row)

    def stats(self) -> GeneratedLevelsStatsOut:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, MAX(created_at) AS last FROM generated_levels"
            ).fetchone()
        return GeneratedLevelsStatsOut(
            total=int(row["n"] or 0) if row else 0,
            latest_at=(row["last"] if row else None),
        )

    def count(self) -> int:
        return self.stats().total

    # --- обслуживание -------------------------------------------------------

    def prune(self, keep: int = 2000) -> int:
        """Оставить только последние `keep` уровней, остальные удалить."""
        keep = max(1, int(keep))
        with self.db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM generated_levels WHERE level_id NOT IN ("
                "  SELECT level_id FROM generated_levels "
                "  ORDER BY created_at DESC LIMIT ?"
                ")",
                (keep,),
            )
        return int(cur.rowcount or 0)
