-- Профиль игрока: имя и автоинкремент визитов (счётчик запусков игры).
--
-- Требование стартового меню: сверху приветствие «hello PlayerN», где N —
-- автоинкремент. Пока игрок не изменил имя, оно собирается как "Player" .. N,
-- где N — номер запуска игры. Как только игрок задал своё имя, оно
-- запоминается и больше не перезаписывается автоинкрементом (счётчик визитов
-- при этом продолжает расти — он хранится отдельно).
--
-- Хранится в отдельном файле сохранения (bumpy_profile) через sys.save, чтобы
-- не смешиваться с игровым прогрессом (main/save.lua): сброс прогресса или
-- GAME OVER не должны стирать имя игрока.
--
-- ВАЖНО (HTML5): путь берётся через sys.get_save_file() — только он указывает
-- внутрь каталога, смонтированного на IndexedDB (см. комментарии в
-- main/save.lua). Модуль общий для всех скриптов (game.project: shared_state).
local M = {}

local APP_ID = "bumpy"
local FILE_NAME = "bumpy_profile"
local VERSION = 1
-- ограничение длины имени в символах UTF-8 (не в байтах)
local MAX_NAME_LEN = 16

-- кэш состояния в пределах сессии: чтение/запись файла не каждый кадр
local state = nil

local function path()
    local ok, p = pcall(sys.get_save_file, APP_ID, FILE_NAME)
    if ok then
        return p
    end
    return nil
end

local function read()
    local p = path()
    if not p then
        return nil
    end
    local ok, data = pcall(sys.load, p)
    if ok and type(data) == "table" and data.version == VERSION then
        return data
    end
    return nil
end

-- имя = только пользовательское (nil, если игрок его ещё не задавал)
local function write(name, visits)
    local p = path()
    if not p then
        return
    end
    pcall(sys.save, p, { version = VERSION, name = name, visits = visits })
end

-- обрезка строки UTF-8 до n символов (не разрезаем многобайтовые символы)
local function utf8_truncate(s, n)
    local i, count = 1, 0
    while i <= #s do
        local b = s:byte(i)
        local size = 1
        if b >= 0xF0 then
            size = 4
        elseif b >= 0xE0 then
            size = 3
        elseif b >= 0xC0 then
            size = 2
        end
        if count == n then
            return s:sub(1, i - 1)
        end
        i = i + size
        count = count + 1
    end
    return s
end
M.utf8_truncate = utf8_truncate

-- число символов UTF-8 в строке
local function utf8_len(s)
    local i, count = 1, 0
    while i <= #s do
        local b = s:byte(i)
        local size = 1
        if b >= 0xF0 then
            size = 4
        elseif b >= 0xE0 then
            size = 3
        elseif b >= 0xC0 then
            size = 2
        end
        i = i + size
        count = count + 1
    end
    return count
end
M.utf8_len = utf8_len

-- убрать последний символ UTF-8
local function utf8_remove_last(s)
    local i = 1
    local last = 1
    while i <= #s do
        last = i
        local b = s:byte(i)
        if b >= 0xF0 then
            i = i + 4
        elseif b >= 0xE0 then
            i = i + 3
        elseif b >= 0xC0 then
            i = i + 2
        else
            i = i + 1
        end
    end
    if last > #s then
        return s
    end
    return s:sub(1, last - 1)
end
M.utf8_remove_last = utf8_remove_last

-- нормализация имени: обрезаем пробелы по краям и ограничиваем длину.
-- Пустое имя (или не строка) => nil — «имя не задано»
local function sanitize(name)
    if type(name) ~= "string" then
        return nil
    end
    name = name:gsub("^%s+", ""):gsub("%s+$", "")
    if name == "" then
        return nil
    end
    return utf8_truncate(name, MAX_NAME_LEN)
end

-- Прочитать профиль (один раз за сессию) и увеличить счётчик визитов.
-- Возвращает имя и номер визита. Первый запуск даёт "Player1".
function M.init()
    if state then
        return state.name, state.visits
    end
    local data = read()
    local prev_visits = data and tonumber(data.visits) or 0
    local visits = math.max(0, math.floor(prev_visits)) + 1
    local custom = data and sanitize(data.name) or nil
    state = {
        visits = visits,
        custom = custom,
        name = custom or ("Player" .. visits),
    }
    write(state.custom, state.visits)
    print(string.format("player_profile: %s (visit %d)", state.name, state.visits))
    return state.name, state.visits
end

function M.get_name()
    if not state then
        M.init()
    end
    return state.name
end

function M.get_visits()
    if not state then
        M.init()
    end
    return state.visits
end

-- Запомнить новое имя. Пустое имя игнорируется (остаётся прежнее).
-- С этого момента автоинкремент имя больше не меняет.
function M.set_name(name)
    if not state then
        M.init()
    end
    local clean = sanitize(name)
    if not clean then
        return state.name
    end
    state.name = clean
    state.custom = clean
    write(state.custom, state.visits)
    print("player_profile: name saved: " .. state.name)
    return state.name
end

return M
