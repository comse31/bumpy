-- Промты (правила генерации) для сгенерированных уровней и обратная связь.
--
-- Промт — текстовое описание уровня в терминах правил игры (состав, требования,
-- схема прохождения), а не его seed. По такому описанию уровень можно
-- сгенерировать заново (человеком или моделью), а не только воспроизвести по
-- seed. Промт строится tools/level_prompt.py и приходит от генератора вместе с
-- уровнем.
--
-- Таблица отдельная (а не колонки generated_levels), чтобы миграция оставалась
-- идемпотентной: SQLite не поддерживает ADD COLUMN IF NOT EXISTS, а миграции
-- выполняются без транзакции (см. backend/app/db.py: migrate).
--
-- signature — компактный вектор признаков уровня (JSON) из того же модуля. Он
-- нужен отрицательному отбору: когда игрок ставит «палец вниз», уровень
-- удаляется, а его промт и подпись уходят в level_feedback. Генератор
-- (tools/gen_hourly.py) получает такие подписи через
-- GET /api/levels/negative-prompts и отбрасывает слишком похожие кандидаты,
-- чтобы подобные уровни больше не появлялись.

CREATE TABLE IF NOT EXISTS level_prompts (
    -- Идентификатор уровня в generated_levels (1:1).
    level_id        TEXT    PRIMARY KEY,

    -- Текст промта: по нему воспроизводится уровень.
    prompt          TEXT    NOT NULL,

    -- Версия формата промта: по ней видно, какие записи нужно пересобрать.
    prompt_version  INTEGER NOT NULL DEFAULT 1,

    -- Вектор признаков уровня (JSON) для отсева похожих уровней.
    signature       TEXT,

    -- Оценка игрока: 'up' / 'down' (NULL — уровень ещё не оценивали).
    rating          TEXT,
    rated_at        TEXT,
    rated_by        TEXT,

    updated_at      TEXT    NOT NULL
);

-- История оценок. Запись здесь остаётся даже после удаления уровня из
-- generated_levels: она — источник отрицательных примеров для генератора.
CREATE TABLE IF NOT EXISTS level_feedback (
    -- Суррогатный ключ: один и тот же уровень может быть оценён разными
    -- игроками, история оценок не должна затираться.
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Идентификатор уровня, к которому относится оценка.
    level_id    TEXT    NOT NULL,

    -- Кто оценил (идентификатор игрока/устройства), может быть NULL.
    player_id   TEXT,

    -- 'up' — понравился, 'down' — не понравился (уровень удаляется).
    verdict     TEXT    NOT NULL,

    -- Промт и подпись уровня на момент оценки: отрицательный пример для
    -- последующей генерации.
    prompt      TEXT,
    signature   TEXT,

    -- JSON уровня на момент оценки (что именно забраковали).
    payload     TEXT,

    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_level_feedback_verdict
    ON level_feedback (verdict, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_level_feedback_level
    ON level_feedback (level_id);

-- Бэкфилл промтов (tools/backfill_prompts.py) ищет уровни, у которых записи
-- в level_prompts ещё нет, либо она сделана старой версией формата.
CREATE INDEX IF NOT EXISTS idx_level_prompts_version
    ON level_prompts (prompt_version);
