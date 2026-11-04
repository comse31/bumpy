-- Начальная схема backend Bumpy.
--
-- Все миграции идемпотентны по построению: их выполняет только раннер миграций
-- и ровно один раз (запись в schema_migrations создаётся в той же транзакции).
--
-- Хранится ровно то, что игра сохраняет локально (main/save.lua и
-- main/player_profile.lua), плюс идентификатор игрока, чтобы объединять данные
-- по устройству/браузеру:
--   players.name       — имя игрока (как в player_profile);
--   players.visits     — счётчик запусков игры (автоинкремент визитов);
--   players.level      — текущий уровень (save.lua: level);
--   players.max_level  — максимально достигнутый уровень (save.lua: max_level);
--   players.lives      — оставшиеся жизни (save.lua: lives);
--   players.drops/keys/hammers — содержимое кармана (save.lua: drops/keys/hammers).

CREATE TABLE IF NOT EXISTS players (
    -- Идентификатор игрока генерирует клиент и хранит в своём файле профиля.
    -- Формат: 8..64 символа [A-Za-z0-9_-]; проверяется в API до записи.
    player_id   TEXT    PRIMARY KEY,

    -- Имя игрока. NULL — имя ещё не задано (клиент подставляет "PlayerN").
    name        TEXT,

    -- Счётчик запусков игры: растёт на каждом старте клиента.
    visits      INTEGER NOT NULL DEFAULT 0,

    -- Прогресс классического режима.
    level       INTEGER NOT NULL DEFAULT 1,
    max_level   INTEGER NOT NULL DEFAULT 1,
    lives       INTEGER NOT NULL DEFAULT 0,
    drops       INTEGER NOT NULL DEFAULT 0,
    keys        INTEGER NOT NULL DEFAULT 0,
    hammers     INTEGER NOT NULL DEFAULT 0,

    -- Версия клиента (game.project: project.version) и платформа последней
    -- записи — нужны, чтобы понимать, с какой сборкой пришёл игрок.
    client_version TEXT,
    platform       TEXT,

    -- Время в UTC (ISO-8601), проставляется сервером.
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

-- Лидерборд: топ по достигнутому уровню, затем по числу визитов.
CREATE INDEX IF NOT EXISTS idx_players_max_level
    ON players (max_level DESC, visits DESC);

-- История игровых событий (изменение имени, старт игры, прохождение уровня,
-- game over). Пишется, только если database.events: true в config.yml.
CREATE TABLE IF NOT EXISTS player_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT    NOT NULL,
    -- Тип события: name, start, level, game_over, sync.
    kind        TEXT    NOT NULL,
    -- Произвольные данные события в виде JSON (номер уровня, жизни и т.п.).
    payload     TEXT,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players (player_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_player_events_player
    ON player_events (player_id, id DESC);

-- Учёт применённых миграций: повторный запуск ничего не выполняет.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT    PRIMARY KEY,
    applied_at  TEXT    NOT NULL
);
