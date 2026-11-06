"""Модели запросов/ответов API и валидация значений.

Валидация повторяет ограничения клиента (main/player_profile.lua: имя до 16
символов, только латиница/цифры/пробел/-/_/.), но с границами из config.yml:
то, что приходит по сети, нельзя считать доверенным.
"""

from __future__ import annotations

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
