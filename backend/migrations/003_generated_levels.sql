-- Сгенерированные уровни Bumpy (tools/gen_level.py + hourly generator).
--
-- Уровень попадает в таблицу ТОЛЬКО если решатель (tools/solve_level.py,
-- is_solvable) подтвердил проходимость: status = 'solvable'. Записи со
-- статусом 'limit' (недоказанная проходимость) не сохраняются.
--
-- payload — JSON уровня в формате main/levels.json (grid_lo, grid_hi, objects,
-- start_cell, timer, timer_cell, theme). Клиент получает его целиком через
-- GET /api/levels/random и строит уровень тем же level.script, что и
-- классические уровни, поэтому схема данных здесь не дублируется.

CREATE TABLE IF NOT EXISTS generated_levels (
    -- Идентификатор записи: нужен клиенту, чтобы ссылаться на конкретный
    -- уровень и чтобы дедуплицировать повторные вставки.
    level_id    TEXT    PRIMARY KEY,

    -- seed генератора: уровень полностью воспроизводим по нему.
    seed        INTEGER NOT NULL,

    -- Номер уровня, под который генерировалось (влияет на сложность).
    level       INTEGER NOT NULL DEFAULT 1,

    -- JSON уровня в формате main/levels.json (без служебных полей).
    payload     TEXT    NOT NULL,

    -- Результат проверки проходимости: только 'solvable' сохраняется.
    status      TEXT    NOT NULL DEFAULT 'solvable',

    -- Минимальный стартовый набор предметов (из solve_level.solve) — нужен
    -- игре, чтобы выдать снаряжение для «Приключения».
    drops       INTEGER NOT NULL DEFAULT 0,
    keys        INTEGER NOT NULL DEFAULT 0,
    hammers     INTEGER NOT NULL DEFAULT 0,

    -- Когда и каким генератором создан уровень (UTC, ISO-8601).
    generator   TEXT,
    created_at  TEXT    NOT NULL
);

-- Случайная выдача уровня: выборка по времени создания + индексы для
-- чтения последних и для дедупликации по seed.
CREATE INDEX IF NOT EXISTS idx_generated_levels_created
    ON generated_levels (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_generated_levels_seed
    ON generated_levels (seed);
