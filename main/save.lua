-- Сохранение прогресса игры между сессиями.
--
-- Для HTML5-сборки это ключевой сценарий: при закрытии вкладки/браузера игра
-- должна возобновляться с текущего уровня, сохраняя число жизней и содержимое
-- кармана. Модуль опирается на sys.save/sys.load — на HTML5 они пишут в
-- IndexedDB (IDBFS), поэтому данные переживают перезапуск вкладки.
--
-- Хранится только то, что даёт право на продолжение:
--   level   — номер текущего уровня (1..level_count);
--   lives   — оставшиеся жизни (0 = игра окончена, восстановление запрещено);
--   drops, keys, hammers — содержимое кармана (капли/ключи/молотки).
--
-- Модуль общий для всех скриптов (в game.project включён shared_state = 1),
-- поэтому одна и та же таблица доступна и level.script, и ball.script.
local M = {}

-- имя файла сохранения в sandbox приложения
local FILE = "bumpy_save"
-- версия формата: при несовпадении сохранение игнорируется (сброс к новой игре)
local VERSION = 1

-- прочитать сохранение. Возвращает таблицу или nil, если сохранения нет,
-- формат устарел либо данные повреждены. sys.load может бросить ошибку
-- (например, при первом запуске), поэтому оборачиваем в pcall
function M.load()
    local ok, data = pcall(sys.load, FILE)
    if not ok or type(data) ~= "table" then
        return nil
    end
    if data.version ~= VERSION then
        return nil
    end
    return data
end

-- записать прогресс. Поля: level, lives, drops, keys, hammers.
-- Неполные/битые значения приводим к безопасным умолчаниям.
--
-- ВАЖНО (HTML5): sys.save пишет в файловую систему Emscripten. Даже при
-- html5.use_indexeddb = 1 данные сначала оседают в памяти (MEMFS) и лишь по
-- sys.sync_fs() сбрасываются в IndexedDB. Без sync_fs() сохранение теряется
-- при перезагрузке вкладки — именно поэтому игра начиналась с 1-го уровня.
-- На настольных платформах sys.sync_fs() — no-op, поэтому вызываем всегда
function M.store(data)
    if type(data) ~= "table" then
        return
    end
    local record = {
        version = VERSION,
        level = data.level or 1,
        lives = data.lives or 0,
        drops = data.drops or 0,
        keys = data.keys or 0,
        hammers = data.hammers or 0,
    }
    pcall(sys.save, FILE, record)
    -- сбросить MEMFS в постоянное хранилище (IndexedDB на HTML5)
    pcall(sys.sync_fs)
end

-- обнулить сохранение: используется, когда продолжать нельзя (жизни кончились).
-- Записываем lives = 0 — при следующем запуске это означает «новая игра»
function M.clear()
    M.store({ level = 1, lives = 0 })
end

return M
