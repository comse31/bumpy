"""Модели запросов/ответов API и валидация значений.

Валидация повторяет ограничения клиента (main/player_profile.lua: имя до 16
символов, только латиница/цифры/пробел/-/_/.), но с границами из config.yml:
то, что приходит по сети, нельзя считать доверенным.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Идентификатор игрока генерирует клиент. Только безопасные для URL символы.
PLAYER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Допустимые символы имени — как в игровом меню (NAME_PATTERN).
NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")
# Виды событий, которые принимает API.
EVENT_KINDS = {"name", "start", "level", "game_over", "sync"}


class EventIn(BaseModel):
    """Событие игрока: тип и произвольные данные."""

    kind: str = Field(..., max_length=32)
    payload: dict[str, Any] | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        kind = value.strip().lower()
        if kind not in EVENT_KINDS:
            raise ValueError(f"недопустимый вид события: {value!r}")
        return kind


class PlayerSyncIn(BaseModel):
    """Снимок состояния игрока, который присылает клиент.

    Набор полей повторяет то, что игра сохраняет локально:
      имя (player_profile), визиты (player_profile),
      уровень/жизни/карман (save.lua).
    """

    player_id: str
    name: str | None = None
    visits: int | None = Field(default=None, ge=0)
    level: int | None = Field(default=None, ge=1)
    max_level: int | None = Field(default=None, ge=1)
    lives: int | None = Field(default=None, ge=0)
    drops: int | None = Field(default=None, ge=0)
    keys: int | None = Field(default=None, ge=0)
    hammers: int | None = Field(default=None, ge=0)
    client_version: str | None = Field(default=None, max_length=32)
    platform: str | None = Field(default=None, max_length=32)
    # Необязательное событие, сохраняемое вместе со снимком.
    event: EventIn | None = None

    @field_validator("player_id")
    @classmethod
    def _player_id(cls, value: str) -> str:
        pid = (value or "").strip()
        if not PLAYER_ID_RE.match(pid):
            raise ValueError(
                "player_id: ожидается 8..64 символа из [A-Za-z0-9_-]"
            )
        return pid

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            return None
        if not NAME_RE.match(name):
            raise ValueError("name: допустимы латиница, цифры, пробел, точка, дефис и подчёркивание")
        return name

    @model_validator(mode="after")
    def _order(self) -> "PlayerSyncIn":
        # max_level не может быть меньше текущего уровня: иначе рекорд в
        # лидерборде «схлопывался» бы от рассинхрона клиента.
        if self.max_level is not None and self.level is not None:
            if self.max_level < self.level:
                self.max_level = self.level
        return self


class EventOut(BaseModel):
    kind: str
    payload: dict[str, Any] | None = None
    created_at: str


class PlayerOut(BaseModel):
    """Профиль игрока в ответе API."""

    player_id: str
    name: str | None = None
    visits: int = 0
    level: int = 1
    max_level: int = 1
    lives: int = 0
    drops: int = 0
    keys: int = 0
    hammers: int = 0
    client_version: str | None = None
    platform: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    events: list[EventOut] = Field(default_factory=list)


class LeaderboardEntry(BaseModel):
    rank: int
    player_id: str
    name: str | None = None
    max_level: int
    level: int
    visits: int


class LeaderboardOut(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[LeaderboardEntry]


class HealthOut(BaseModel):
    status: str
    version: int
    database: str
    players: int | None = None


# --- аутентификация по имени и паролю ---------------------------------------
# Имя игрока уникально в БД. Вход по имени требует пароль; на устройстве, где
# игрок уже входил, пароль берётся из локального кэша и не запрашивается.

# Разрешённые символы пароля: латиница, цифры, пробел, точка, дефис, «_».
PASSWORD_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")


class NameCheckIn(BaseModel):
    """Проверка имени: занято ли оно и нужен ли пароль."""

    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = (value or "").strip()
        if not NAME_RE.match(name):
            raise ValueError("name: допустимы латиница, цифры, пробел, точка, дефис и подчёркивание")
        return name


class CredentialsIn(BaseModel):
    """Имя и пароль для входа или регистрации."""

    name: str
    password: str = Field(..., min_length=1, max_length=128)
    # Идентификатор устройства: по нему сервер понимает, что игрок входит
    # повторно с того же устройства (кэш пароля на клиенте).
    player_id: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = (value or "").strip()
        if not NAME_RE.match(name):
            raise ValueError("name: допустимы латиница, цифры, пробел, точка, дефис и подчёркивание")
        return name

    @field_validator("player_id")
    @classmethod
    def _player_id(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        pid = value.strip()
        if not PLAYER_ID_RE.match(pid):
            raise ValueError("player_id: ожидается 8..64 символа из [A-Za-z0-9_-]")
        return pid


class NameCheckOut(BaseModel):
    """Ответ на проверку имени.

    exists   — имя уже есть в БД;
    has_password — у имени задан пароль (нужен ввод);
    name     — каноническое имя из БД (регистр может отличаться от введённого).
    """

    name: str
    exists: bool
    has_password: bool


class AuthOut(BaseModel):
    """Результат входа/регистрации.

    ok        — пароль принят (или установлен впервые);
    reason    — причина отказа: "wrong_password", "name_taken", "not_found";
    player    — профиль игрока при успехе;
    player_id — идентификатор записи (может отличаться от присланного, если
                игрок вошёл с другого устройства под своим именем).
    """

    ok: bool
    reason: str | None = None
    player_id: str | None = None
    player: PlayerOut | None = None


class NextNameOut(BaseModel):
    """Свободное имя по умолчанию (PlayerN), уникальное в БД."""

    name: str
    player_id: str


# --- сгенерированные уровни --------------------------------------------------
# Уровень попадает в generated_levels (backend/migrations/003_generated_levels.sql)
# только после проверки проходимости решателем tools/solve_level.py. Клиент
# получает уровень целиком и строит его тем же main/level/level.script, что и
# классические уровни из main/levels.json, поэтому payload — это JSON уровня в
# формате levels.json.


class GeneratedLevelIn(BaseModel):
    """Уровень, который присылает генератор (tools/gen_hourly.py).

    Поля повторяют колонки generated_levels. payload передаётся JSON-строкой,
    чтобы сервер не зависел от внутренней структуры уровня.
    """

    seed: int = Field(..., ge=0)
    level: int = Field(default=1, ge=1)
    payload: str = Field(..., min_length=2, max_length=20000)
    status: str = Field(default="solvable", max_length=16)
    drops: int = Field(default=0, ge=0)
    keys: int = Field(default=0, ge=0)
    hammers: int = Field(default=0, ge=0)
    generator: str | None = Field(default=None, max_length=64)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        status = (value or "").strip().lower()
        # Сохраняются только доказанно проходимые уровни: иначе в БД попадут
        # уровни, которые игрок физически не может пройти.
        if status != "solvable":
            raise ValueError("status: сохраняются только уровни со статусом solvable")
        return status

    @field_validator("payload")
    @classmethod
    def _payload(cls, value: str) -> str:
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload: ожидается JSON-строка уровня") from exc
        if not isinstance(decoded, dict):
            raise ValueError("payload: ожидается JSON-объект уровня")
        for field in ("grid_lo", "grid_hi", "objects"):
            grid = decoded.get(field)
            if not isinstance(grid, list) or len(grid) != 6:
                raise ValueError(f"payload: поле {field} должно быть сеткой 6x6")
            for row in grid:
                if not isinstance(row, list) or len(row) != 6:
                    raise ValueError(f"payload: поле {field} должно быть сеткой 6x6")
        for field in ("start_cell", "timer_cell"):
            if not isinstance(decoded.get(field), int):
                raise ValueError(f"payload: поле {field} должно быть целым")
        return value

    @field_validator("payload")
    @classmethod
    def _no_platform_above_block(cls, value: str) -> str:
        """Над кирпичной кладкой (код 10) не может быть платформ.

        Правило оригинала: 144 кладки в main/levels.json, и прямо над кладкой
        стоит только другая кладка (столбик кирпичей) — платформ нет ни в одном
        уровне. Иначе шар, разбивающий кладку снизу молотком, упирался бы в
        платформу сверху, и проём переставал бы быть «пробиваемым».

        Проверка на сервере дублирует фильтр генератора
        (tools/gen_level.py: blocks_above_violations), чтобы такой уровень не
        попал в БД даже от стороннего клиента.
        """
        decoded = json.loads(value)
        grid = decoded["grid_lo"]
        for row in range(1, len(grid)):
            for col in range(len(grid[row])):
                if grid[row][col] != 10:
                    continue
                above = grid[row - 1][col]
                # 1..9 — платформы, 10 — кладка (столбик кирпичей допустим)
                if above in (1, 2, 3, 4, 5, 6, 7, 8, 9):
                    raise ValueError(
                        "payload: над кирпичной кладкой не может быть платформ "
                        f"(строка {row}, колонка {col}, код {above})"
                    )
        return value

    @model_validator(mode="after")
    def _requires_items(self) -> "GeneratedLevelIn":
        """Уровень обязан требовать хотя бы один предмет.

        Это осознанное требование к сложности: уровень, который проходится без
        снаряжения, слишком простой. Проверка дублирует фильтр генератора
        (tools/gen_level.py: MIN_REQUIRED_ITEMS), чтобы «пустой» уровень не
        попал в БД даже от стороннего клиента.
        """
        if int(self.drops) + int(self.keys) + int(self.hammers) < 1:
            raise ValueError(
                "уровень должен требовать хотя бы один предмет "
                "(drops + keys + hammers > 0)"
            )
        return self


class GeneratedLevelOut(BaseModel):
    """Сгенерированный уровень в ответе API."""

    level_id: str
    seed: int
    level: int
    status: str
    drops: int = 0
    keys: int = 0
    hammers: int = 0
    created_at: str | None = None
    # JSON уровня (формат main/levels.json) строкой — клиент декодирует сам
    payload: str


class GeneratedLevelsStatsOut(BaseModel):
    """Сколько сгенерированных уровней есть в БД."""

    total: int
    latest_at: str | None = None
