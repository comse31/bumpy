-- Загрузка случайного сгенерированного уровня из БД (backend).
--
-- Уровни создаёт часовой генератор (tools/gen_hourly.py) и сохраняет в таблицу
-- generated_levels только после проверки проходимости решателем
-- (tools/solve_level.py: is_solvable → "solvable"). Игра получает уровень
-- через GET /api/levels/random и строит его тем же main/level/level.script,
-- что и классические уровни из main/levels.json: формат payload совпадает,
-- поэтому схема данных на клиенте не дублируется.
--
-- Режим использования — «Приключение»: пункт меню заменяет выбор уровня на
-- загрузку случайного уровня из БД. Сеть необязательна, как и во всех
-- серверных вызовах (main/records.lua, main/remote_db.lua, main/auth.lua):
-- если backend недоступен или уровней в БД ещё нет, меню показывает ошибку.
--
-- Адрес API и ключ берутся из remote_db, чтобы настройки (bumpy.api_url /
-- bumpy.api_key) читались в одном месте.
local remote_db = require("main.remote_db")

local M = {}

-- Последний полученный уровень: его читает level.script, когда игрок запускает
-- «Приключение». Хранится в общем состоянии (game.project: shared_state = 1),
-- поэтому модуль общий для всех скриптов.
local current = nil
-- Запрос уже выполняется: повторные клики не должны плодить запросы.
local in_flight = false

-- Тело HTTP-ответа: в Defold http.request он лежит в response.response
-- (поля response.body нет).
local function response_body(response)
    if type(response) ~= "table" then
        return nil
    end
    local body = response.response
    if type(body) ~= "string" then
        body = response.body
    end
    return body
end

local function headers()
    local result = { ["Content-Type"] = "application/json" }
    local key = remote_db.api_key()
    if key ~= "" then
        result["X-Api-Key"] = key
    end
    return result
end

-- Текст ошибки для меню (короткий: шрифт меню — только латиница).
local function error_text(status)
    if status == 404 then
        return "No generated levels yet"
    end
    if status == 0 then
        return "Server is unavailable"
    end
    return string.format("Server error (status %s)", tostring(status))
end

-- Разобрать payload уровня. Возвращает таблицу уровня или nil, err.
--
-- payload приходит JSON-строкой (в формате main/levels.json) внутри JSON
-- ответа, поэтому декодируется отдельным вызовом json.decode.
local function decode_level(item)
    if type(item) ~= "table" then
        return nil, "Bad level data"
    end
    local raw = item.payload
    if type(raw) ~= "string" or raw == "" then
        return nil, "Bad level data"
    end
    local ok, level = pcall(json.decode, raw)
    if not ok or type(level) ~= "table" then
        return nil, "Bad level data"
    end
    if type(level.grid_lo) ~= "table" or type(level.grid_hi) ~= "table"
        or type(level.objects) ~= "table" then
        return nil, "Bad level data"
    end
    -- номер уровня в модели levels.json (для отладочных сообщений)
    level.level = tonumber(item.level) or 1
    -- требования по снаряжению: игра выдаёт их в «Приключении»
    level.drops = math.max(0, math.floor(tonumber(item.drops) or 0))
    level.keys = math.max(0, math.floor(tonumber(item.keys) or 0))
    level.hammers = math.max(0, math.floor(tonumber(item.hammers) or 0))
    -- идентификатор записи в БД (для логов и повторных попыток)
    level.level_id = item.level_id
    level.seed = tonumber(item.seed)
    return level
end

-- Запросить случайный сгенерированный уровень.
-- callback(level, error):
--   level — таблица уровня (формат levels.json) или nil при ошибке;
--   error — текст ошибки или nil при успехе.
--
-- Ответ устаревшего запроса отбрасывается: игрок мог нажать пункт меню
-- несколько раз, и поздний ответ первого запроса не должен перезаписать
-- свежий.
function M.load(callback)
    if in_flight then
        return
    end
    if not http or not http.request then
        callback(nil, "Server is unavailable")
        return
    end

    in_flight = true
    local url = string.format("%s/api/levels/random", remote_db.api_base())
    local called = false

    local function done(_, _, response)
        if called then
            return
        end
        called = true
        in_flight = false

        local status = response and response.status or 0
        if status ~= 200 then
            callback(nil, error_text(status))
            return
        end

        local body = response_body(response)
        local ok, item = pcall(json.decode, body or "")
        if not ok or type(item) ~= "table" then
            callback(nil, "Bad response from server")
            return
        end

        local level, err = decode_level(item)
        if not level then
            callback(nil, err)
            return
        end

        current = level
        print(string.format("random_level: got level_id=%s seed=%s timer=%s",
            tostring(level.level_id), tostring(level.seed), tostring(level.timer)))
        callback(level, nil)
    end

    local sent = pcall(http.request, url, "GET", done, headers(), nil)
    if not sent then
        in_flight = false
        done(nil, nil, nil)
    end
end

-- Уровень, загруженный последним (или nil, если ещё не загружали).
function M.current()
    return current
end

-- Очистить текущий уровень (после прохождения/выхода в меню).
function M.clear()
    current = nil
end

-- Есть ли загруженный уровень.
function M.has()
    return current ~= nil
end

-- Загружен ли уровень в БД (всегда true: сервер отдаёт только solvable).
function M.is_generated()
    return current ~= nil
end

return M
