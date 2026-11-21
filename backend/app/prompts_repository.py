"""Промты уровней и обратная связь игроков (таблицы level_prompts/level_feedback).

Разделение с GeneratedLevelRepository намеренное: уровни — «фабрика» контента,
а промты и оценки — отдельная история, которая живёт дольше самого уровня.
Когда игрок ставит «палец вниз», уровень удаляется из generated_levels, но
запись в level_feedback остаётся: она — отрицательный пример для генератора.

Правила:
  * промт хранится отдельной строкой prompt в level_prompts; отсутствие записи
    означает «промт ещё не собран» (для старых уровней это норма);
  * оценка 'down' удаляет уровень из generated_levels и переносит его промт,
    подпись и payload в level_feedback — по этим данным генератор отбрасывает
    похожие кандидаты;
  * оценка 'up' ничего не удаляет, но тоже попадает в историю: положительные
    примеры полезны при настройке порогов.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import Database, utc_now
from .schemas import NegativePromptOut


def _row_prompt(row: sqlite3.Row | None) -> dict[str, Any]:
    """Строка level_prompts -> словарь полей (пустой, если записи нет)."""
    if row is None:
        return {}
    return {
        "prompt": row["prompt"],
        "prompt_version": int(row["prompt_version"] or 0),
        "signature": row["signature"],
        "rating": row["rating"],
        "rated_at": row["rated_at"],
        "rated_by": row["rated_by"],
    }


class LevelPromptRepository:
    """Промты уровней и оценки игроков."""

    def __init__(self, db: Database, *, negative_limit: int = 200) -> None:
        self.db = db
        # Сколько последних отрицательных примеров отдавать генератору.
        self.negative_limit = max(1, int(negative_limit))

    # --- промты -------------------------------------------------------------

    def upsert(self, level_id: str, prompt: str, *,
               prompt_version: int = 1,
               signature: Any = None) -> dict[str, Any]:
        """Записать (или обновить) промт уровня.

        Существующая оценка не затирается: бэкфилл промтов может выполняться
        после того, как игрок уже поставил палец вверх.
        """
        if signature is not None and not isinstance(signature, str):
            signature = json.dumps(signature, ensure_ascii=False, separators=(",", ":"))
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO level_prompts "
                "(level_id, prompt, prompt_version, signature, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(level_id) DO UPDATE SET "
                "  prompt = excluded.prompt, "
                "  prompt_version = excluded.prompt_version, "
                "  signature = COALESCE(excluded.signature, level_prompts.signature), "
                "  updated_at = excluded.updated_at",
                (level_id, prompt, int(prompt_version), signature, now),
            )
            row = conn.execute(
                "SELECT * FROM level_prompts WHERE level_id = ?", (level_id,)
            ).fetchone()
        return _row_prompt(row)

    def get(self, level_id: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM level_prompts WHERE level_id = ?", (level_id,)
            ).fetchone()
        return _row_prompt(row)

    def for_levels(self, level_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Промты для набора уровней (одним запросом: списки в API частые)."""
        if not level_ids:
            return {}
        placeholders = ",".join("?" for _ in level_ids)
        with self.db.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM level_prompts WHERE level_id IN ({placeholders})",
                tuple(level_ids),
            ).fetchall()
        return {str(row["level_id"]): _row_prompt(row) for row in rows}

    def missing(self, limit: int = 200, *, version: int = 1) -> list[dict[str, Any]]:
        """Уровни без промта (или с промтом более старой версии).

        Нужен tools/backfill_prompts.py: он берёт payload, собирает промт
        заново и вызывает upsert. Записи с более новой версией формата не
        трогаются.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT g.level_id, g.payload, g.seed, g.level AS level_no, "
                "       g.drops, g.keys, g.hammers "
                "FROM generated_levels g "
                "LEFT JOIN level_prompts p ON p.level_id = g.level_id "
                "WHERE p.level_id IS NULL OR p.prompt_version < ? "
                "ORDER BY g.created_at DESC LIMIT ?",
                (int(version), max(1, int(limit))),
            ).fetchall()
        out = []
        for row in rows:
            out.append({
                "level_id": str(row["level_id"]),
                "payload": str(row["payload"]),
                "seed": int(row["seed"]),
                "level": int(row["level_no"] or 1),
                "drops": int(row["drops"] or 0),
                "keys": int(row["keys"] or 0),
                "hammers": int(row["hammers"] or 0),
            })
        return out

    def count_missing(self) -> int:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM generated_levels g "
                "LEFT JOIN level_prompts p ON p.level_id = g.level_id "
                "WHERE p.level_id IS NULL"
            ).fetchone()
        return int(row["n"] or 0) if row else 0

    # --- оценки -------------------------------------------------------------

    def rate(self, level_id: str, verdict: str, *,
             player_id: str | None = None,
             payload: str | None = None,
             delete_on_down: bool = True) -> dict[str, Any]:
        """Оценить уровень. 'down' удаляет уровень из generated_levels.

        Возвращает {rating, prompt, deleted, found}. Оценка 'up' не удаляет
        уровень и не мешает ему выдаваться снова — она только фиксируется.
        """
        verdict = (verdict or "").strip().lower()
        if verdict not in ("up", "down"):
            raise ValueError("verdict: ожидается 'up' или 'down'")

        now = utc_now()
        with self.db.transaction() as conn:
            level = conn.execute(
                "SELECT * FROM generated_levels WHERE level_id = ?", (level_id,)
            ).fetchone()
            prompt_row = conn.execute(
                "SELECT * FROM level_prompts WHERE level_id = ?", (level_id,)
            ).fetchone()
            info = _row_prompt(prompt_row)
            found = level is not None or bool(info)

            prompt_text = info.get("prompt")
            signature = info.get("signature")
            level_payload = payload
            if level is not None and level_payload is None:
                level_payload = str(level["payload"])
            if prompt_row is not None:
                # оценка уровня: сохраняем её в карточке промта
                conn.execute(
                    "UPDATE level_prompts SET rating = ?, rated_at = ?, rated_by = ? "
                    "WHERE level_id = ?",
                    (verdict, now, player_id, level_id),
                )
            # история оценок: источник отрицательных примеров для генератора
            conn.execute(
                "INSERT INTO level_feedback "
                "(level_id, player_id, verdict, prompt, signature, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (level_id, player_id, verdict, prompt_text, signature,
                 level_payload, now),
            )

            deleted = False
            if verdict == "down" and delete_on_down and level is not None:
                # Уровень забракован — убираем его из выдачи. Промт остаётся
                # в level_feedback как отрицательный пример.
                conn.execute(
                    "DELETE FROM generated_levels WHERE level_id = ?", (level_id,)
                )
                deleted = True

        return {
            "rating": verdict,
            "prompt": prompt_text,
            "deleted": deleted,
            "found": found,
        }

    def has_rating(self, level_id: str, player_id: str | None) -> bool:
        """Ставил ли этот игрок оценку уровню (повторную не показываем)."""
        with self.db.connection() as conn:
            if player_id:
                row = conn.execute(
                    "SELECT 1 FROM level_feedback "
                    "WHERE level_id = ? AND player_id = ? LIMIT 1",
                    (level_id, player_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM level_feedback WHERE level_id = ? LIMIT 1",
                    (level_id,),
                ).fetchone()
        return row is not None

    def negatives(self, limit: int | None = None, *,
                  player_id: str | None = None) -> list[NegativePromptOut]:
        """Отрицательные примеры для генератора (последние забракованные).

        Отдаются только записи, у которых есть подпись: без неё сравнение
        «похож ли кандидат» невозможно, и такая запись бесполезна.
        """
        page = self.negative_limit if limit is None else max(1, int(limit))
        sql = (
            "SELECT level_id, prompt, signature, player_id, created_at "
            "FROM level_feedback WHERE verdict = 'down' "
            "AND signature IS NOT NULL AND signature <> '' "
        )
        params: list[Any] = []
        if player_id:
            sql += "AND player_id = ? "
            params.append(player_id)
        sql += "ORDER BY created_at DESC LIMIT ?"
        params.append(page)
        with self.db.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            NegativePromptOut(
                level_id=str(row["level_id"]),
                prompt=row["prompt"],
                signature=row["signature"],
                player_id=row["player_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def count_negative(self) -> int:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM level_feedback WHERE verdict = 'down'"
            ).fetchone()
        return int(row["n"] or 0) if row else 0
