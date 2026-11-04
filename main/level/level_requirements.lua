-- Минимальные требования уровня по снаряжению (пункт 19 плана).
--
-- main/level_requirements.json генерируется оффлайн скриптом
-- tools/gen_level_requirements.py: для каждого уровня решатель
-- (tools/solve_level.py) ищет план прохождения и берёт из него минимальный
-- набор предметов, который нужен игроку УЖЕ НА СТАРТЕ уровня (остальное
-- можно подобрать по пути).
--
-- Зачем: нехватка снаряжения — проигрыш вне зависимости от числа жизней
-- (tz.txt, «Жизни»). Игрок может физически не пробить перегородки/кладку и не
-- погасить горящие платформы, сколько бы жизней у него ни осталось, поэтому
-- проверка делается на старте уровня.
--
-- Модуль общий для всех скриптов (game.project: shared_state = 1), поэтому
-- таблица читается и из ball.script, и из ball_progress.lua.
local M = {}

local PATH = "/main/level_requirements.json"

-- поля требований в порядке RESOURCES из tools/solve_level.py
local FIELDS = { "drops", "keys", "hammers" }

local levels = nil

-- прочитать файл требований один раз за сессию
local function ensure_loaded()
    if levels ~= nil then
        return levels
    end
    levels = {}
    local data = sys.load_resource(PATH)
    if not data then
        print("level_requirements: cannot load " .. PATH)
        return levels
    end
    local ok, model = pcall(json.decode, data)
    if not ok or type(model) ~= "table" or type(model.levels) ~= "table" then
        print("level_requirements: cannot decode " .. PATH .. ": " .. tostring(model))
        return levels
    end
    levels = model.levels
    return levels
end

-- Есть ли для уровня запись требований (чтобы отсутствующий файл или новый
-- уровень без перегенерации данных не блокировали игру).
function M.has(index)
    local all = ensure_loaded()
    return type(all[tostring(index)]) == "table"
end

-- Требования уровня: (drops, keys, hammers) или nil, если данных нет.
-- Для статуса "impossible" возвращаем nil: такой уровень нельзя пройти ни с
-- каким снаряжением, проверять нечего (в текущих данных таких уровней нет).
function M.required(index)
    local all = ensure_loaded()
    local item = all[tostring(index)]
    if type(item) ~= "table" or item.status == "impossible" then
        return nil
    end
    return tonumber(item.drops) or 0,
        tonumber(item.keys) or 0,
        tonumber(item.hammers) or 0
end

-- Хватает ли снаряжения: true, nil — если хватает; false, { drops = N, ... } —
-- если нет (значение — сколько единиц не хватает).
function M.check(index, pocket, keys, hammers)
    local need_drops, need_keys, need_hammers = M.required(index)
    if need_drops == nil then
        return true, nil
    end
    local have = {
        tonumber(pocket) or 0,
        tonumber(keys) or 0,
        tonumber(hammers) or 0,
    }
    local need = { need_drops, need_keys, need_hammers }
    local lack, missing = {}, false
    for i = 1, #FIELDS do
        local diff = need[i] - have[i]
        if diff > 0 then
            lack[FIELDS[i]] = diff
            missing = true
        end
    end
    if not missing then
        return true, nil
    end
    return false, lack
end

-- Названия предметов для плашки (единственное/множественное число)
local NAMES = {
    drops = { "1 drop", "%d drops" },
    keys = { "1 key", "%d keys" },
    hammers = { "1 hammer", "%d hammers" },
}

-- Текст недостачи для плашки: «2 keys, 1 hammer» ("" если всё есть)
function M.describe(lack)
    if type(lack) ~= "table" then
        return ""
    end
    local parts = {}
    for i = 1, #FIELDS do
        local field = FIELDS[i]
        local n = lack[field]
        if n and n > 0 then
            local fmt = NAMES[field][n == 1 and 1 or 2]
            parts[#parts + 1] = (n == 1) and fmt or string.format(fmt, n)
        end
    end
    return table.concat(parts, ", ")
end

-- Сбросить кеш (перегенерация данных на лету / тестовый режим)
function M.reset()
    levels = nil
end

return M
