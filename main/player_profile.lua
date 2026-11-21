-- Профиль игрока: имя и автоинкремент визитов (счётчик запусков игры).
--
-- Приветствия в меню нет: имя показывается только в строке «Name: ...».
-- Пока игрок не изменил имя, оно собирается как "Player" .. N, где N — номер
-- запуска игры (автоинкремент визитов). Как только игрок задал своё имя, оно
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
--
-- Имя и счётчик визитов дублируются в серверную БД (main/remote_db.lua,
-- backend/): при смене имени и при первом запуске отправляется снимок, чтобы
-- имя игрока хранилось не только в браузере. Сеть необязательна.
--
-- ИМЯ УНИКАЛЬНО В БД: имя по умолчанию (PlayerN) выдаёт сервер, а смена имени
-- проходит проверку пароля (main/auth.lua).
local M = {}

-- дублирование профиля в БД (backend). Модуль безопасен без сети
local remote_db = require("main.remote_db")
-- вход по имени и паролю: проверка имени и кэш пароля на устройстве
local auth = require("main.auth")

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

-- Отправить профиль в БД. Клиентское имя (custom или "PlayerN") уходит в поле
-- name, счётчик визитов — в visits: обе величины дублируются в серверной
-- таблице players. progress-поля сюда не входят, поэтому сервер сохранит уже
-- известные ему значения уровня/жизней/кармана.
--
-- Локальное имя, придуманное клиентом (PlayerN по числу визитов), НЕ
-- отправляется: имя должно быть уникальным в БД, и его выдаёт сервер
-- (GET /api/auth/next-name). Иначе клиент «занимал» имя, которое могло уже
-- принадлежать другому игроку, а сервер это имя отбрасывал.
local function push_to_db(state)
    if not state then
        return
    end
    remote_db.sync({
        name = state.custom and state.name or nil,
        visits = state.visits,
    })
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
-- Возвращает имя и номер визита.
--
-- Имя по умолчанию больше не считается как "Player" .. visits: оно должно
-- быть уникальным в БД, поэтому кандидат запрашивается у сервера
-- (GET /api/auth/next-name). Пока ответа нет, используется локальное имя —
-- игра не должна ждать сеть на старте.
function M.init()
    if state then
        return state.name, state.visits
    end
    local data = read()
    local prev_visits = data and tonumber(data.visits) or 0
    local visits = math.max(0, math.floor(prev_visits)) + 1
    local custom = data and sanitize(data.name) or nil
    local fallback = "Player" .. visits
    state = {
        visits = visits,
        custom = custom,
        -- автоматическое имя (может прийти от сервера): к нему возвращаемся,
        -- если игрок отменил правку или пароль не подошёл
        default_name = custom or fallback,
        name = custom or fallback,
    }
    write(state.custom, state.visits)
    -- первый запуск: заводим запись в БД вместе с именем и номером визита
    push_to_db(state)
    print(string.format("player_profile: %s (visit %d)", state.name, state.visits))
    -- если игрок ещё не задавал имя — уточняем свободный PlayerN у сервера
    if not custom then
        M.refresh_default_name()
    end
    return state.name, state.visits
end

-- Запросить у сервера свободное имя PlayerN (уникальное в БД) и подставить
-- его, если игрок ещё не задал своё имя. Ответ приходит асинхронно: до него
-- игра работает с локальным именем, после — с серверным.
function M.refresh_default_name()
    if not state or state.custom then
        return
    end
    auth.next_default_name(function(name)
        if not state or state.custom or type(name) ~= "string" or name == "" then
            return
        end
        if name == state.name then
            return
        end
        state.name = name
        state.default_name = name
        write(state.custom, state.visits)
        push_to_db(state)
        print("player_profile: default name from DB: " .. name)
        -- сообщаем подписчикам (меню), что имя изменилось: оно уже показано
        -- в поле, и его нужно обновить, иначе игрок увидит старое «Player1»
        if M.on_name_changed then
            M.on_name_changed(name)
        end
    end)
end

-- Прочитать профиль без инициализации (не увеличивает визиты и не пишет файл).
-- Нужен там, где профиль лишь дополняет уже готовые данные — например, в
-- main/save.lua: инициализация профиля из сохранения прогресса создала бы
-- лишний визит и повторную отправку в БД.
function M.peek()
    if not state then
        return nil, nil
    end
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
--
-- ВАЖНО: сохранение имени в БД выполняет меню (main/auth.lua): сначала
-- проверка/пароль, и только после успеха вызывается M.set_name. Поэтому
-- здесь имя фиксируется локально и отправляется как снимок профиля.
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
    -- новое имя сразу дублируется в БД: имя игрока не должно теряться при
    -- очистке браузера
    push_to_db(state)
    print("player_profile: name saved: " .. state.name)
    return state.name
end

-- Откатить имя к прежнему (отмена правки или неверный пароль).
--
-- Если прежним было автоматическое имя (state.default_name), оно НЕ
-- закрепляется: state.custom остаётся nil, поэтому сервер по-прежнему может
-- выдать свободный PlayerN. Иначе любой откат делал авто-имя
-- «пользовательским», и игрок навсегда оставался с ним.
-- Для обычного пользовательского имени оно просто восстанавливается.
function M.rollback_to(name)
    if not state then
        M.init()
    end
    local clean = sanitize(name)
    local target = clean or state.default_name or state.name
    state.name = target
    if clean and clean ~= state.default_name then
        state.custom = clean
        write(clean, state.visits)
    else
        state.custom = nil
        write(nil, state.visits)
    end
    if M.on_name_changed then
        M.on_name_changed(target)
    end
    return target
end

-- Вернуть автоматическое имя устройства (без закрепления).
function M.restore_default()
    return M.rollback_to(nil)
end

-- Автоматическое имя устройства (для отката и подсказок).
function M.default_name()
    if not state then
        M.init()
    end
    return state.default_name or state.name
end

-- Текущее имя без побочных эффектов (см. M.peek).
function M.current_name()
    return M.get_name()
end

return M
