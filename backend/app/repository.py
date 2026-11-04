"""Операции над профилями игроков в SQLite.

Слой намеренно тонкий: SQL-запросы собраны в одном месте, API-слой занимается
только HTTP и валидацией.

Правила слияния (клиент может прислать снимок повторно, из другой вкладки или
из старой версии игры):
  * NULL-поля запроса не затирают сохранённые значения;
  * max_level только растёт — это рекорд, как и в main/save.lua;
  * visits не уменьшается (счётчик запусков игры).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .db import Database, utc_now
from .passwords import hash_password, verify_password
from .schemas import EventOut, LeaderboardEntry, LeaderboardOut, PlayerOut, PlayerSyncIn

# Поля players, которые клиент может прислать в снимке.
_PLAYER_FIELDS = (
    "name",
    "visits",
    "level",
    "max_level",
    "lives",
    "drops",
    "keys",
    "hammers",
    "client_version",
    "platform",
)

# Ограничения, приходящие из config.yml (передаются в конструктор).
class Limits:
    def __init__(self, *, max_levels: int, max_visits: int, max_items: int) -> None:
        self.max_levels = max_levels
        self.max_visits = max_visits
        self.max_items = max_items


def _clamp(value: int | None, low: int, high: int) -> int | None:
    if value is None:
        return None
    return max(low, min(high, int(value)))


def _row_to_player(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _player_out(row: sqlite3.Row) -> PlayerOut:
    return PlayerOut(**_row_to_player(row))


class PlayerRepository:
    """Доступ к таблицам players / player_events."""

    def __init__(
        self,
        db: Database,
        limits: Limits,
        *,
        events: bool = True,
        password_iterations: int = 120000,
        max_name_len: int = 16,
    ) -> None:
        self.db = db
        self.limits = limits
        self.events = events
        # итерации PBKDF2 для новых паролей (из config.yml)
        self.password_iterations = password_iterations
        self.max_name_len = max_name_len

    # --- чтение -------------------------------------------------------------

    def get(self, player_id: str, *, with_events: bool = False, events_limit: int = 20) -> PlayerOut | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM players WHERE player_id = ?", (player_id,)
            ).fetchone()
            if row is None:
                return None
            player = _player_out(row)
            if with_events and self.events and events_limit > 0:
                player.events = self._events(conn, player_id, events_limit)
        return player

    def _events(self, conn: sqlite3.Connection, player_id: str, limit: int):
        rows = conn.execute(
            "SELECT kind, payload, created_at FROM player_events "
            "WHERE player_id = ? ORDER BY id DESC LIMIT ?",
            (player_id, int(limit)),
        ).fetchall()
        out: list[EventOut] = []
        for row in rows:
            payload = None
            if row["payload"]:
                try:
                    payload = json.loads(row["payload"])
                except (TypeError, ValueError):
                    payload = None
            out.append(
                EventOut(kind=row["kind"], payload=payload, created_at=row["created_at"])
            )
        return out

    # --- имена и пароли -----------------------------------------------------

    def find_by_name(self, name: str) -> sqlite3.Row | None:
        """Найти запись по имени без учёта регистра."""
        with self.db.connection() as conn:
            return conn.execute(
                "SELECT * FROM players WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()

    def name_owner(self, name: str) -> str | None:
        """player_id владельца имени, либо None, если имя свободно."""
        row = self.find_by_name(name)
        return None if row is None else str(row["player_id"])

    def check_name(self, name: str) -> tuple[bool, bool]:
        """(имя занято, у имени задан пароль)."""
        row = self.find_by_name(name)
        if row is None:
            return False, False
        return True, bool(row["password_hash"])

    def set_password(self, player_id: str, password: str) -> None:
        """Задать/сменить пароль игрока (PBKDF2, соль на запись)."""
        hash_hex, salt_hex, iterations = hash_password(password, self.password_iterations)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE players SET password_hash = ?, password_salt = ?, "
                "password_iterations = ?, password_updated_at = ?, updated_at = ? "
                "WHERE player_id = ?",
                (hash_hex, salt_hex, iterations, utc_now(), utc_now(), player_id),
            )

    def check_password(self, player_id: str, password: str) -> bool:
        """Проверить пароль игрока. False, если пароля ещё нет."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT password_hash, password_salt, password_iterations "
                "FROM players WHERE player_id = ?",
                (player_id,),
            ).fetchone()
        if row is None:
            return False
        return verify_password(
            password,
            row["password_hash"],
            row["password_salt"],
            row["password_iterations"],
        )

    def register_or_login(self, name: str, password: str, player_id: str | None) -> dict[str, Any]:
        """Вход по имени или первичная привязка пароля к имени.

        Сценарии:
          * имени нет в БД — создаётся новый игрок с этим именем и паролем
            (player_id: присланный клиентом или новый свободный);
          * имя есть, пароля ещё нет (автоматическое PlayerN) — пароль
            привязывается к существующей записи, прогресс сохраняется;
          * имя есть, пароль задан — проверяется; при неверном пароле вход
            отклоняется (reason = wrong_password).

        Возвращает dict с полями ok/reason/player_id/player.
        """
        now = utc_now()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM players WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()

            if row is None:
                # новое имя: заводим запись. player_id клиента может быть уже
                # занят другой записью — тогда подбираем свободный
                pid = player_id
                if pid is None or conn.execute(
                    "SELECT 1 FROM players WHERE player_id = ?", (pid,)
                ).fetchone():
                    pid = self._free_player_id(conn, name)
                conn.execute(
                    "INSERT INTO players (player_id, name, visits, level, max_level, "
                    "lives, drops, keys, hammers, created_at, updated_at) "
                    "VALUES (?, ?, 0, 1, 1, 0, 0, 0, 0, ?, ?)",
                    (pid, name, now, now),
                )
                hash_hex, salt_hex, iterations = hash_password(password, self.password_iterations)
                conn.execute(
                    "UPDATE players SET password_hash = ?, password_salt = ?, "
                    "password_iterations = ?, password_updated_at = ? WHERE player_id = ?",
                    (hash_hex, salt_hex, iterations, now, pid),
                )
                self._add_event(conn, pid, "name", {"name": name, "via": "register"}, now)
                result_row = conn.execute(
                    "SELECT * FROM players WHERE player_id = ?", (pid,)
                ).fetchone()
                return {
                    "ok": True,
                    "reason": None,
                    "player_id": pid,
                    "player": _player_out(result_row),
                }

            pid = str(row["player_id"])
            has_password = bool(row["password_hash"])

            if not has_password:
                # автоматическое имя: первый задавший пароль закрепляет его
                hash_hex, salt_hex, iterations = hash_password(password, self.password_iterations)
                conn.execute(
                    "UPDATE players SET password_hash = ?, password_salt = ?, "
                    "password_iterations = ?, password_updated_at = ?, updated_at = ? "
                    "WHERE player_id = ?",
                    (hash_hex, salt_hex, iterations, now, now, pid),
                )
                self._add_event(conn, pid, "name", {"name": name, "via": "claim"}, now)
                result_row = conn.execute(
                    "SELECT * FROM players WHERE player_id = ?", (pid,)
                ).fetchone()
                return {
                    "ok": True,
                    "reason": None,
                    "player_id": pid,
                    "player": _player_out(result_row),
                }

            if verify_password(
                password,
                row["password_hash"],
                row["password_salt"],
                row["password_iterations"],
            ):
                self._add_event(conn, pid, "name", {"name": name, "via": "login"}, now)
                result_row = conn.execute(
                    "SELECT * FROM players WHERE player_id = ?", (pid,)
                ).fetchone()
                return {
                    "ok": True,
                    "reason": None,
                    "player_id": pid,
                    "player": _player_out(result_row),
                }

            return {"ok": False, "reason": "wrong_password", "player_id": pid, "player": None}

    def claim_name(self, name: str, player_id: str) -> bool:
        """Занять свободное имя за существующей записью player_id.

        False, если имя уже занято другим игроком.
        """
        with self.db.transaction() as conn:
            owner = conn.execute(
                "SELECT player_id FROM players WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()
            if owner is not None and str(owner["player_id"]) != player_id:
                return False
            exists = conn.execute(
                "SELECT 1 FROM players WHERE player_id = ?", (player_id,)
            ).fetchone()
            if exists is None:
                return False
            conn.execute(
                "UPDATE players SET name = ?, updated_at = ? WHERE player_id = ?",
                (name, utc_now(), player_id),
            )
        return True

    def _free_player_id(self, conn: sqlite3.Connection, name: str) -> str:
        """Свободный player_id на основе имени и случайного хвоста."""
        import secrets
        import re as _re

        slug = _re.sub(r"[^A-Za-z0-9_-]", "", name) or "player"
        slug = slug[:24]
        for _ in range(50):
            candidate = f"{slug}{secrets.token_hex(4)}"
            if conn.execute(
                "SELECT 1 FROM players WHERE player_id = ?", (candidate,)
            ).fetchone() is None:
                return candidate
        # практически недостижимо: увеличиваем энтропию
        return f"{slug}{secrets.token_hex(8)}"

    def next_default_name(self) -> str:
        """Свободное имя PlayerN: минимальный N, отсутствующий в БД.

        Учитываются и чужие имена: «Player3» может быть занято кем угодно,
        поэтому проверка идёт по всей таблице, а не по числу визитов.
        """
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM players WHERE name LIKE 'Player%' COLLATE NOCASE"
            ).fetchall()
        taken: set[int] = set()
        for row in rows:
            suffix = str(row["name"])[6:]
            if suffix.isdigit():
                taken.add(int(suffix))
        n = 1
        while n in taken:
            n += 1
        return f"Player{n}"

    # --- запись -------------------------------------------------------------

    def upsert(self, data: PlayerSyncIn) -> PlayerOut:
        """Создать или обновить профиль по снимку клиента.

        Первое обращение создаёт запись, дальнейшие — обновляют её по правилам
        слияния (см. docstring модуля).
        """
        now = utc_now()

        name = data.name
        if name is not None:
            name = name[: self.max_name_len]
            # имя уникально в БД: если его уже занял другой игрок, снимок
            # не перезаписывает имя (иначе вход по имени стал бы невозможен)
            owner = self.name_owner(name)
            if owner is not None and owner != data.player_id:
                name = None

        values = {
            "name": name,
            "visits": _clamp(data.visits, 0, self.limits.max_visits),
            "level": _clamp(data.level, 1, self.limits.max_levels),
            "max_level": _clamp(data.max_level, 1, self.limits.max_levels),
            "lives": _clamp(data.lives, 0, self.limits.max_items),
            "drops": _clamp(data.drops, 0, self.limits.max_items),
            "keys": _clamp(data.keys, 0, self.limits.max_items),
            "hammers": _clamp(data.hammers, 0, self.limits.max_items),
            "client_version": (data.client_version or None),
            "platform": (data.platform or None),
        }

        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM players WHERE player_id = ?", (data.player_id,)
            ).fetchone()

            if existing is None:
                record = {
                    "player_id": data.player_id,
                    "name": values["name"],
                    "visits": values["visits"] or 0,
                    "level": values["level"] or 1,
                    "max_level": values["max_level"] or values["level"] or 1,
                    "lives": values["lives"] or 0,
                    "drops": values["drops"] or 0,
                    "keys": values["keys"] or 0,
                    "hammers": values["hammers"] or 0,
                    "client_version": values["client_version"],
                    "platform": values["platform"],
                    "created_at": now,
                    "updated_at": now,
                }
                # max_level не может быть меньше текущего уровня
                if record["max_level"] < record["level"]:
                    record["max_level"] = record["level"]
                conn.execute(
                    "INSERT INTO players ("
                    "player_id, name, visits, level, max_level, lives, drops, keys, hammers,"
                    "client_version, platform, created_at, updated_at"
                    ") VALUES ("
                    ":player_id, :name, :visits, :level, :max_level, :lives, :drops, :keys,"
                    ":hammers, :client_version, :platform, :created_at, :updated_at)",
                    record,
                )
            else:
                current = _row_to_player(existing)
                merged: dict[str, Any] = {}
                for field in _PLAYER_FIELDS:
                    new_value = values.get(field)
                    old_value = current.get(field)
                    if new_value is None:
                        merged[field] = old_value
                    elif field == "max_level":
                        merged[field] = max(int(old_value or 0), int(new_value))
                    elif field == "visits":
                        merged[field] = max(int(old_value or 0), int(new_value))
                    else:
                        merged[field] = new_value

                # уровень не может превышать рекорд
                if merged["max_level"] is None:
                    merged["max_level"] = merged.get("level") or 1
                if merged.get("level") is None:
                    merged["level"] = 1
                if merged["max_level"] < merged["level"]:
                    merged["max_level"] = merged["level"]

                merged["player_id"] = data.player_id
                merged["updated_at"] = now
                conn.execute(
                    "UPDATE players SET "
                    "name = :name, visits = :visits, level = :level, max_level = :max_level,"
                    "lives = :lives, drops = :drops, keys = :keys, hammers = :hammers,"
                    "client_version = :client_version, platform = :platform,"
                    "updated_at = :updated_at "
                    "WHERE player_id = :player_id",
                    merged,
                )

            if data.event is not None and self.events:
                self._add_event(conn, data.player_id, data.event.kind, data.event.payload, now)

            row = conn.execute(
                "SELECT * FROM players WHERE player_id = ?", (data.player_id,)
            ).fetchone()

        return _player_out(row)

    def _add_event(
        self,
        conn: sqlite3.Connection,
        player_id: str,
        kind: str,
        payload: dict[str, Any] | None,
        created_at: str,
    ) -> None:
        conn.execute(
            "INSERT INTO player_events (player_id, kind, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                player_id,
                kind,
                json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")),
                created_at,
            ),
        )

    def add_event(self, player_id: str, kind: str, payload: dict[str, Any] | None = None) -> bool:
        """Добавить событие игроку. False — если игрока нет или события выключены."""
        if not self.events:
            return False
        with self.db.transaction() as conn:
            exists = conn.execute(
                "SELECT 1 FROM players WHERE player_id = ?", (player_id,)
            ).fetchone()
            if exists is None:
                return False
            self._add_event(conn, player_id, kind, payload, utc_now())
        return True

    def delete(self, player_id: str) -> bool:
        """Удалить профиль и его события (данные игрока по его запросу)."""
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        return cur.rowcount > 0

    # --- агрегаты -----------------------------------------------------------

    def count(self) -> int:
        with self.db.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()
        return int(row["n"]) if row else 0

    def leaderboard(self, *, limit: int, offset: int) -> LeaderboardOut:
        """Топ игроков: сначала по достигнутому уровню, затем по числу визитов."""
        with self.db.connection() as conn:
            total = int(
                conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
            )
            rows = conn.execute(
                "SELECT player_id, name, max_level, level, visits FROM players "
                "ORDER BY max_level DESC, visits DESC, updated_at ASC "
                "LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()

        entries: Iterable[LeaderboardEntry] = [
            LeaderboardEntry(
                rank=int(offset) + index + 1,
                player_id=row["player_id"],
                name=row["name"],
                max_level=row["max_level"],
                level=row["level"],
                visits=row["visits"],
            )
            for index, row in enumerate(rows)
        ]
        return LeaderboardOut(
            total=total, limit=int(limit), offset=int(offset), entries=list(entries)
        )
