"""HTTP-API Bumpy: профиль игрока и игровой прогресс.

Эндпоинты (префикс /api, за nginx он же и проксируется):
    GET    /api/health              — состояние сервиса и БД;
    GET    /api/players             — лидерборд (limit/offset);
    GET    /api/players/{id}        — профиль игрока + последние события;
    PUT    /api/players/{id}        — создать/обновить профиль (идемпотентно);
    POST   /api/players/{id}/events — добавить событие игрока;
    DELETE /api/players/{id}        — удалить данные игрока.

Клиент игры работает только через PUT: при каждом сохранении он отправляет
полный снимок (имя, визиты, уровень, жизни, карман) и сервер сам решает, что
обновить — это исключает гонки между вкладками.
"""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .db import Database
from .passwords import PasswordError, validate as validate_password
from .repository import Limits, PlayerRepository
from .schemas import (
    AuthOut,
    CredentialsIn,
    EventIn,
    HealthOut,
    LeaderboardOut,
    NameCheckIn,
    NameCheckOut,
    NextNameOut,
    PlayerOut,
    PlayerSyncIn,
)
from .settings import ApiSettings, Settings, load_settings

log = logging.getLogger("bumpy")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собрать приложение. Настройки можно передать явно (для тестов)."""
    settings = settings or load_settings()
    _configure_logging(settings.api.log_level)

    database = Database(settings.database)
    repository = PlayerRepository(
        database,
        Limits(
            max_levels=settings.api.max_levels,
            max_visits=settings.api.max_visits,
            max_items=settings.api.max_items,
        ),
        events=settings.database.events,
        password_iterations=settings.api.password_iterations,
        max_name_len=settings.api.max_name_len,
    )

    # Миграции применяются на старте: при первом запуске в docker-томе пусто,
    # и схема создаётся здесь же — отдельного шага деплоя не требуется.
    database.init()

    app = FastAPI(
        title="Bumpy backend",
        version=f"api-{settings.api.version}",
        description="Хранение профилей игроков и игрового прогресса Bumpy.",
    )
    app.state.settings = settings
    app.state.database = database
    app.state.repository = repository

    if settings.api.cors_origins:
        # Нужен не только для чужих origin: даже на том же origin браузер делает
        # preflight OPTIONS перед PUT с Content-Type: application/json (этот тип
        # не «простой»). Без обработчика preflight получал 405, и сохранение в
        # БД в HTML5-сборке молча не работало.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.api.cors_origins),
            allow_methods=["GET", "PUT", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            allow_credentials=False,
            max_age=600,
        )

    # --- проверка ключа -----------------------------------------------------

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        """Необязательный API-ключ: включается только если задан в config.yml."""
        expected = settings.api.api_key
        if not expected:
            return
        if x_api_key != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="неверный API-ключ"
            )

    def get_repo() -> PlayerRepository:
        return repository

    def get_api() -> ApiSettings:
        return settings.api

    # --- служебные ----------------------------------------------------------

    @app.get("/api/health", response_model=HealthOut)
    def health() -> HealthOut:
        ok = database.healthcheck()
        return HealthOut(
            status="ok" if ok else "error",
            version=settings.api.version,
            database="ok" if ok else "unavailable",
            players=repository.count() if ok else None,
        )

    @app.get("/api/config", dependencies=[Depends(require_key)])
    def client_config(api: ApiSettings = Depends(get_api)) -> dict:
        """Публичные настройки для клиента: что он вправе присылать.

        Клиент сверяет с ними свои локальные лимиты (длина имени и т.п.), чтобы
        не получать 422 на валидных с его точки зрения данных.
        """
        return {
            "version": api.version,
            "max_name_len": api.max_name_len,
            "max_levels": api.max_levels,
            "max_visits": api.max_visits,
            "max_items": api.max_items,
            "events": settings.database.events,
            # клиент сверяет с этими значениями поле пароля
            "password_min_len": api.password_min_len,
            "password_max_len": api.password_max_len,
        }

    # --- вход по имени и паролю ---------------------------------------------

    @app.post(
        "/api/auth/check",
        response_model=NameCheckOut,
        dependencies=[Depends(require_key)],
    )
    def check_name(
        payload: NameCheckIn,
        repo: PlayerRepository = Depends(get_repo),
    ) -> NameCheckOut:
        """Занято ли имя и нужен ли для него пароль.

        Клиент вызывает это при попытке задать имя: если имя свободно —
        просит задать пароль (регистрация), если занято — просит пароль на
        проверку, если у имени пароля нет (автоматическое PlayerN) — тоже
        просит задать пароль, чтобы закрепить имя.
        """
        exists, has_password = repo.check_name(payload.name)
        return NameCheckOut(name=payload.name, exists=exists, has_password=has_password)

    @app.post(
        "/api/auth/login",
        response_model=AuthOut,
        dependencies=[Depends(require_key)],
    )
    def login(
        payload: CredentialsIn,
        repo: PlayerRepository = Depends(get_repo),
        api: ApiSettings = Depends(get_api),
    ) -> AuthOut:
        """Вход или первичная привязка пароля к имени.

        Один и тот же эндпоинт покрывает оба сценария из требований:
          * игрок вводит новое имя — запись создаётся, пароль сохраняется;
          * игрок вводит существующее имя — пароль проверяется; при неверном
            пароле клиент откатывает имя к предыдущему.
        """
        try:
            password = validate_password(payload.password)
        except PasswordError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if len(password) < api.password_min_len or len(password) > api.password_max_len:
            raise HTTPException(
                status_code=422,
                detail=f"пароль должен быть от {api.password_min_len} до {api.password_max_len} символов",
            )

        result = repo.register_or_login(payload.name, password, payload.player_id)
        return AuthOut(
            ok=result["ok"],
            reason=result["reason"],
            player_id=result["player_id"],
            player=result["player"],
        )

    @app.get(
        "/api/auth/next-name",
        response_model=NextNameOut,
        dependencies=[Depends(require_key)],
    )
    def next_name(
        repo: PlayerRepository = Depends(get_repo),
    ) -> NextNameOut:
        """Свободное имя по умолчанию, уникальное в БД.

        Игра использует его при первом запуске вместо «PlayerN по числу
        визитов»: номер выбирается по фактически занятым именам в БД, поэтому
        два новых устройства не получат одинаковое имя.
        """
        name = repo.next_default_name()
        return NextNameOut(name=name, player_id="")

    # --- игроки -------------------------------------------------------------

    @app.get(
        "/api/players",
        response_model=LeaderboardOut,
        dependencies=[Depends(require_key)],
    )
    def leaderboard(
        limit: int = Query(default=None, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        repo: PlayerRepository = Depends(get_repo),
        api: ApiSettings = Depends(get_api),
    ) -> LeaderboardOut:
        page = api.page_size if limit is None else limit
        return repo.leaderboard(limit=page, offset=offset)

    @app.get(
        "/api/players/{player_id}",
        response_model=PlayerOut,
        dependencies=[Depends(require_key)],
    )
    def get_player(
        player_id: str,
        repo: PlayerRepository = Depends(get_repo),
        api: ApiSettings = Depends(get_api),
    ) -> PlayerOut:
        player = repo.get(player_id, with_events=True, events_limit=api.events_limit)
        if player is None:
            raise HTTPException(status_code=404, detail="игрок не найден")
        return player

    @app.put(
        "/api/players/{player_id}",
        response_model=PlayerOut,
        dependencies=[Depends(require_key)],
    )
    def sync_player(
        player_id: str,
        payload: PlayerSyncIn,
        repo: PlayerRepository = Depends(get_repo),
    ) -> PlayerOut:
        """Идемпотентная синхронизация профиля.

        Идентификатор берётся из пути, а не из тела: клиент не должен иметь
        возможность переписать чужую запись не тем id.
        """
        if payload.player_id != player_id:
            raise HTTPException(
                status_code=422,
                detail="player_id в пути и в теле не совпадают",
            )
        return repo.upsert(payload)

    @app.post(
        "/api/players/{player_id}/events",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_key)],
    )
    def add_event(
        player_id: str,
        event: EventIn,
        repo: PlayerRepository = Depends(get_repo),
    ) -> dict:
        added = repo.add_event(player_id, event.kind, event.payload)
        if not added:
            raise HTTPException(
                status_code=404,
                detail="игрок не найден или запись событий отключена",
            )
        return {"status": "accepted"}

    @app.delete(
        "/api/players/{player_id}",
        # 204 не допускает тела ответа, поэтому явно отдаём «пустой» Response:
        # иначе FastAPI отвергает маршрут при создании приложения.
        response_class=Response,
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_key)],
    )
    def delete_player(
        player_id: str,
        repo: PlayerRepository = Depends(get_repo),
    ) -> Response:
        repo.delete(player_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover
        log.exception("необработанная ошибка на %s", request.url.path)
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=500, content={"detail": "внутренняя ошибка сервера"})

    return app


def _build() -> FastAPI:
    """Точка входа uvicorn: настройки читаются из BUMPY_CONFIG/config.yml."""
    config_path = os.environ.get("BUMPY_CONFIG")
    return create_app(load_settings(config_path))


app = _build()
