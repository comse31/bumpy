-- Пароль игрока и уникальность имени.
--
-- Требования:
--   * имя игрока уникально в БД — по нему игрок входит на другом устройстве;
--   * пароль хранится только в виде хэша (PBKDF2-HMAC-SHA256 + соль);
--   * password_hash IS NULL означает «имя занято, но пароль ещё не задан»
--     (так создаются автоматические default-имена PlayerN). Первый, кто задаст
--     пароль для такого имени, закрепляет его за собой.
--
-- ВАЖНО: уникальный индекс создаётся ПОСЛЕ разрешения дублей. В предыдущей
-- версии схемы имя не было уникальным, и несколько записей могли называться
-- одинаково (например, «Player1» на разных устройствах). Оставляем самое
-- раннее имя, остальные получают суффикс из player_id.

-- 1. Разрешение существующих дублей имён: первую запись в группе (минимальный
--    rowid) оставляем как есть, остальным добавляем «_XXXX» из хвоста player_id.
UPDATE players
SET name = substr(name, 1, 11) || '_' || substr(player_id, -4)
WHERE name IS NOT NULL
  AND rowid NOT IN (
      SELECT MIN(rowid) FROM players
      WHERE name IS NOT NULL
      GROUP BY name COLLATE NOCASE
  );

-- 2. Новые поля пароля. ALTER TABLE ... ADD COLUMN в SQLite не идемпотентен,
--    но миграция выполняется ровно один раз (учёт в schema_migrations).
ALTER TABLE players ADD COLUMN password_hash TEXT;
ALTER TABLE players ADD COLUMN password_salt TEXT;
ALTER TABLE players ADD COLUMN password_iterations INTEGER;
ALTER TABLE players ADD COLUMN password_updated_at TEXT;

-- 3. Уникальность имени без учёта регистра: «Tom» и «tom» — одно имя.
--    Partial index (WHERE name IS NOT NULL) позволяет держать записи без имени.
CREATE UNIQUE INDEX IF NOT EXISTS idx_players_name_unique
    ON players (name COLLATE NOCASE)
    WHERE name IS NOT NULL;

-- 4. Поиск по имени — основной запрос при входе.
CREATE INDEX IF NOT EXISTS idx_players_name_lookup
    ON players (name COLLATE NOCASE);
