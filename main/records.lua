-- Загрузка таблицы рекордов (топ игроков) с backend.
--
-- Данные берутся из GET /api/players (backend/app/main.py: leaderboard) —
-- это тот же лидерборд, что сортирует игроков по достигнутому уровню:
--   ORDER BY max_level DESC, visits DESC, updated_at ASC
-- (backend/app/repository.py: leaderboard).
--
-- Модуль только читает данные и не блокирует игру: пока ответа нет, меню
-- показывает «Loading...», а при ошибке — сообщение и кнопку Back. Сеть
-- необязательна, как и во всех остальных серверных вызовах
-- (main/remote_db.lua, main/auth.lua).
--
-- Адрес API и ключ берутся из remote_db, чтобы настройки (bumpy.api_url /
-- bumpy.api_key) читались в одном месте.
local remote_db = require("main.remote_db")

local M = {}

-- Сколько строк показываем в меню (по числу узлов rec_row1..rec_row10).
M.LIMIT = 10

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

-- Запросить топ игроков. callback(entries, error):
--   entries — список { rank, name, max_level } (может быть пустым);
--   error   — текст ошибки или nil при успехе.
--
-- Игрок без имени (name = null, запись ещё не закреплена) показывается как
-- «Player», чтобы строка не выглядела пустой.
function M.load(callback, limit)
    limit = math.max(1, math.floor(tonumber(limit) or M.LIMIT))

    if not http or not http.request then
        callback({}, "Leaderboard is unavailable")
        return
    end

    local url = string.format("%s/api/players?limit=%d", remote_db.api_base(), limit)
    local called = false

    local function done(_, _, response)
        if called then
            return
        end
        called = true

        local status = response and response.status or 0
        if status ~= 200 then
            callback({}, string.format("Server error (status %s)", tostring(status)))
            return
        end

        local body = response_body(response)
        local ok, parsed = pcall(json.decode, body or "")
        if not ok or type(parsed) ~= "table" or type(parsed.entries) ~= "table" then
            callback({}, "Bad response from server")
            return
        end

        local entries = {}
        for index, item in ipairs(parsed.entries) do
            if index > limit then
                break
            end
            local name = item.name
            if type(name) ~= "string" or name == "" then
                name = "Player"
            end
            entries[index] = {
                rank = tonumber(item.rank) or index,
                name = name,
                max_level = math.max(1, math.floor(tonumber(item.max_level) or 1)),
            }
        end
        callback(entries, nil)
    end

    local sent = pcall(http.request, url, "GET", done, headers(), nil)
    if not sent then
        done(nil, nil, nil)
    end
end

-- Строка таблицы: «1. Name - 12».
function M.format_entry(entry)
    if type(entry) ~= "table" then
        return ""
    end
    return string.format("%d. %s - %d", entry.rank or 0, tostring(entry.name or "Player"),
        math.max(1, math.floor(tonumber(entry.max_level) or 1)))
end

return M
