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
    DESC с ограничением окна, чтобы давно забытые уровни не вытесняли свежие;
  * для конкретного игрока (player_id) уровень не повторяется, пока ему не
    были предложены все доступные: история выдач хранится в level_plays
    (backend/migrations/005_level_plays.sql), а когда непросмотренные
    заканчиваются — история очищается и начинается новый круг.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from . import level_prompts
from .db import Database, utc_now
from .prompts_repository import LevelPromptRepository
from .schemas import GeneratedLevelIn, GeneratedLevelOut, GeneratedLevelsStatsOut


def _level_id(seed: int, payload: str) -> str:
    """Стабильный идентификатор записи: seed + хэш payload.

    По seed уровень воспроизводим, поэтому повторная генерация того же самого
    уровня даёт тот же level_id — клиент не получит «новый» уровень, который
    на самом деле тот же.
    """
    digest = hashlib.sha1(f"{seed}:{payload}".encode("utf-8")).hexdigest()[:16]
    return f"g{seed}_{digest}"


def _row_value(row: sqlite3.Row, key: str):
    """Значение колонки, если она есть в выборке (иначе None).

    Запросы здесь собираются по-разному: часть выборок идёт с JOIN на
    level_prompts (там есть prompt/rating), часть — по одной таблице.
    """
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


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
        # Промт приходит из level_prompts (JOIN LEFT): у старых записей его
        # может не быть до запуска tools/backfill_prompts.py.
        prompt=_row_value(row, "prompt"),
        prompt_version=int(_row_value(row, "prompt_version") or 0),
        rating=_row_value(row, "rating"),
    )


# Выборка уровня вместе с его промтом: промт лежит отдельно (level_prompts),
# потому что он переживает удаление забракованного уровня.
SELECT_WITH_PROMPT = (
    "SELECT g.*, p.prompt AS prompt, p.prompt_version AS prompt_version, "
    "       p.rating AS rating, p.signature AS signature "
    "FROM generated_levels g "
    "LEFT JOIN level_prompts p ON p.level_id = g.level_id "
)


class GeneratedLevelRepository:
    """Доступ к таблице generated_levels."""

    def __init__(self, db: Database, *, window: int = 500,
                 prompts: LevelPromptRepository | None = None,
                 negative_limit: int = 200) -> None:
        self.db = db
        # сколько последних уровней участвует в случайной выдаче
        self.window = max(1, int(window))
        # Промты и оценки уровней: отдельный репозиторий, потому что записи
        # об оценках переживают удаление самого уровня из generated_levels.
        self.prompts = prompts or LevelPromptRepository(
            db, negative_limit=negative_limit)

    # --- запись -------------------------------------------------------------

    def add(self, item: GeneratedLevelIn) -> GeneratedLevelOut:
        """Сохранить уровень и его промт. Дубликат по seed не создаёт новую запись.

        Промт приходит от генератора; если его нет (старый генератор), он
        собирается здесь из payload — правило генерации должно быть у каждого
        уровня, иначе отрицательный отбор по «пальцу вниз» работать не сможет.
        """
        if item.status != "solvable":
            raise ValueError("сохраняются только уровни со статусом solvable")

        now = utc_now()
        level_id = _level_id(item.seed, item.payload)
        prompt = item.prompt
        prompt_version = int(item.prompt_version or 0)
        signature = item.signature
        if not prompt:
            prompt, prompt_version, signature = self._build_prompt(
                item.payload,
                drops=int(item.drops),
                keys=int(item.keys),
                hammers=int(item.hammers),
                fallback_signature=signature,
            )
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
        stored_id = str(row["level_id"])
        if prompt:
            # Промт записывается всегда (в т.ч. для уже существующего уровня —
            # так можно дозаполнить запись, пришедшую от старого генератора).
            self.prompts.upsert(
                stored_id, prompt,
                prompt_version=prompt_version,
                signature=signature,
            )
        with self.db.connection() as conn:
            merged = conn.execute(
                SELECT_WITH_PROMPT + "WHERE g.level_id = ?", (stored_id,)
            ).fetchone()
        return _row_to_level(merged if merged is not None else row)

    @staticmethod
    def _build_prompt(payload: str, *, drops: int = 0, keys: int = 0,
                      hammers: int = 0,
                      fallback_signature: str | None = None
                      ) -> tuple[str | None, int, str | None]:
        """Собрать промт из payload, если генератор его не прислал.

        Требования по снаряжению лежат в отдельных колонках, а не в payload,
        но без них промт теряет важную часть правила — поэтому они передаются
        из записи (drops/keys/hammers).

        Возвращает (prompt, version, signature). Ошибки разбора не пробрасываются:
        уровень важнее промта, и без промта он останется работоспособным
        (бэкфилл дозаполнит его позже).
        """
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            return None, 0, fallback_signature
        if not isinstance(decoded, dict):
            return None, 0, fallback_signature
        # значения из колонок приоритетнее: payload мог прийти без требований
        decoded["drops"] = int(drops)
        decoded["keys"] = int(keys)
        decoded["hammers"] = int(hammers)
        try:
            info = level_prompts.build(decoded)
        except Exception:  # pragma: no cover - защита от неожиданного payload
            return None, 0, fallback_signature
        signature = json.dumps(
            info["signature"], ensure_ascii=False, separators=(",", ":"))
        return info["prompt"], int(info["version"]), signature

    def liked_seed(self) -> int:
        """Следующий seed для генератора: максимальный + 1.

        Так генерация продолжает последовательность и не зацикливается на уже
        проверенных кандидатах между часовыми запусками.
        """
        with self.db.connection() as conn:
            row = conn.execute("SELECT MAX(seed) AS s FROM generated_levels").fetchone()
        return int(row["s"] or 0) + 1 if row else 1

    # --- чтение -------------------------------------------------------------

    # Уровень обязан требовать хотя бы один предмет (иначе он слишком простой).
    # Генератор это гарантирует (tools/gen_level.py: MIN_REQUIRED_ITEMS), но в
    # БД могли остаться записи, созданные до появления требования, поэтому
    # фильтр продублирован здесь: старые «пустые» уровни не выдаются клиенту.
    MIN_ITEMS_SQL = "(drops + keys + hammers) > 0"

    @staticmethod
    def _no_platform_above_block(payload: str) -> bool:
        """Проверить правило «над кирпичной кладкой нет платформ».

        Кладка — код 10 в grid_lo. В оригинале над ней стоит только другая
        кладка (столбик кирпичей). Если над кладкой платформа, шар не сможет
        разбить кладку снизу — уровень сломан геометрически.

        Фильтр нужен для записей, созданных до появления проверки в схеме
        (уровни в БД могли быть сохранены раньше): клиенту они не выдаются.
        """
        try:
            grid = json.loads(payload)["grid_lo"]
        except (TypeError, ValueError, KeyError):
            return False
        for row in range(1, len(grid)):
            for col in range(len(grid[row])):
                if grid[row][col] != 10:
                    continue
                if grid[row - 1][col] in (1, 2, 3, 4, 5, 6, 7, 8, 9):
                    return False
        return True

    @staticmethod
    def _safe_start(payload: str) -> bool:
        """Старт не на горящей платформе и не на шипах.

        Коды lo: 8 — горящая, 9 — горящая липкая, 12 — шипы. Правило игры:
        главный герой не должен погибать сразу на старте. Сжимающаяся
        платформа любого остатка (2/3/4) разрешена.

        Фильтр нужен для записей, созданных до появления проверки в схеме:
        клиенту они не выдаются.
        """
        try:
            decoded = json.loads(payload)
            grid = decoded["grid_lo"]
            cell = int(decoded["start_cell"])
        except (TypeError, ValueError, KeyError, IndexError):
            return False
        row, col = divmod(cell, len(grid))
        if not (0 <= row < len(grid) and 0 <= col < len(grid[row])):
            return False
        return grid[row][col] not in (8, 9, 12)

    def _fetch_candidates(self, conn: sqlite3.Connection, *, player_id: str | None,
                          require_items: bool, limit: int) -> list[sqlite3.Row]:
        """Выборка кандидатов на выдачу из окна последних уровней.

        Уже выданные игроку уровни исключаются В SQL, а не после LIMIT:
        иначе при большом окне запас в 200 строк мог целиком состоять из
        сыгранных уровней, и выдача ошибочно решала бы, что круг пройден.

        require_items=False снимает фильтр «уровень требует хотя бы один
        предмет» — запасной вариант, чтобы режим «Приключение» продолжал
        работать на старых записях.
        """
        sql = (
            SELECT_WITH_PROMPT +
            "WHERE g.level_id IN ("
            "  SELECT level_id FROM generated_levels "
            "  ORDER BY created_at DESC LIMIT ?"
            ") {exclude} {items} ORDER BY RANDOM() LIMIT ?"
        )
        params: list[Any] = [self.window]
        exclude = ""
        if player_id:
            exclude = (
                "AND g.level_id NOT IN ("
                "  SELECT level_id FROM level_plays WHERE player_id = ?"
                ")"
            )
            params.append(player_id)
        items = f"AND {self.MIN_ITEMS_SQL}" if require_items else ""
        params.append(max(1, int(limit)))
        rows = conn.execute(
            sql.format(exclude=exclude, items=items), tuple(params)
        ).fetchall()
        # Правило «нельзя начинать на огне/шипах» не отключается никогда:
        # иначе старое нарушение снова попадёт клиенту. Геометрию над кладкой
        # можно ослабить — лучше отдать уровень, чем оставить игрока без него.
        rows = [row for row in rows if self._safe_start(row["payload"])]
        valid = [row for row in rows if self._no_platform_above_block(row["payload"])]
        return valid or rows

    def _candidates(self, conn: sqlite3.Connection,
                    player_id: str | None = None) -> list[sqlite3.Row]:
        """Уровни-кандидаты на выдачу (перемешаны, проходят проверки)."""
        rows = self._fetch_candidates(
            conn, player_id=player_id, require_items=True, limit=200)
        if rows:
            return rows
        # фильтр по предметам ослабляется только если без него что-то есть
        return self._fetch_candidates(
            conn, player_id=player_id, require_items=False, limit=200)

    def _clear_plays(self, conn: sqlite3.Connection, player_id: str) -> None:
        """Начать новый круг: игрок снова может получить любой уровень."""
        conn.execute("DELETE FROM level_plays WHERE player_id = ?", (player_id,))

    def _remember_play(self, conn: sqlite3.Connection, player_id: str,
                       level_id: str) -> None:
        """Запомнить выдачу уровня игроку (история текущего круга)."""
        conn.execute(
            "INSERT INTO level_plays (player_id, level_id, played_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(player_id, level_id) DO UPDATE SET "
            "  played_at = excluded.played_at",
            (player_id, level_id, utc_now()),
        )

    def random(self, player_id: str | None = None) -> GeneratedLevelOut | None:
        """Случайный уровень из окна последних записей.

        Если передан player_id, уровень не повторяется, пока игроку не были
        предложены все доступные уровни: выдача идёт только из ещё не
        выданных ему. Когда непросмотренные заканчиваются, история игрока
        очищается — начинается новый круг, и уровни снова доступны в
        случайном порядке.

        Без player_id поведение прежнее — чистая случайная выдача: клиент без
        идентификатора (например, отладочный запрос) не должен зависеть от
        чужой истории.

        Выбор и запись истории выполняются в одной транзакции: две вкладки не
        получат один и тот же уровень одновременно.
        """
        pid = (player_id or "").strip() or None
        with self.db.transaction() as conn:
            candidates = self._candidates(conn, pid)
            if not candidates:
                if not pid:
                    return None
                # Все доступные уровни уже предложены — начинается новый круг.
                self._clear_plays(conn, pid)
                candidates = self._candidates(conn, pid)
                if not candidates:
                    return None

            # случайный выбор из подходящих (ORDER BY RANDOM в SQL уже перемешал)
            chosen = candidates[0]
            if pid:
                self._remember_play(conn, pid, str(chosen["level_id"]))
        return _row_to_level(chosen)

    def plays_count(self, player_id: str) -> int:
        """Сколько уровней игрок получил в текущем круге."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM level_plays WHERE player_id = ?",
                (player_id,),
            ).fetchone()
        return int(row["n"] or 0) if row else 0

    def count_with_items(self) -> int:
        """Сколько в БД уровней, требующих хотя бы один предмет."""
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM generated_levels WHERE {self.MIN_ITEMS_SQL}"
            ).fetchone()
        return int(row["n"] or 0) if row else 0

    def latest(self, limit: int = 10) -> list[GeneratedLevelOut]:
        """Последние сгенерированные уровни (для отладки и админки)."""
        with self.db.connection() as conn:
            rows = conn.execute(
                SELECT_WITH_PROMPT +
                "ORDER BY g.created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_to_level(row) for row in rows]

    def get(self, level_id: str) -> GeneratedLevelOut | None:
        with self.db.connection() as conn:
            row = conn.execute(
                SELECT_WITH_PROMPT + "WHERE g.level_id = ?", (level_id,)
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
            without_prompt=self.prompts.count_missing(),
            rejected=self.prompts.count_negative(),
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
