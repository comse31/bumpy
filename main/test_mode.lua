-- Режим тестового уровня: включается настройкой bumpy.test_level = 1
-- в game.project и выключается значением 0 (по умолчанию).
--
-- В этом режиме:
--   * level.script грузит /main/test_levels.json вместо /main/levels.json
--     и всегда начинает с первого (единственного) уровня;
--   * сохранение прогресса полностью игнорируется: save.load() возвращает nil,
--     save.store()/clear() ничего не пишут. Иначе тестовый прогон затирал бы
--     сохранение реальной игры (и наоборот — продолжал бы её с 47-го уровня).
--
-- Модуль общий для всех скриптов (в game.project включён shared_state = 1),
-- поэтому решение принимается один раз и в одном месте.
local M = {}

-- sys.get_config_string возвращает значение как есть, вместе с кавычками из
-- game.project ('"1"' вместо 1), поэтому кавычки и пробелы срезаем перед tonumber.
-- Тот же приём — в main/level/level.script, main/ball/ball_debug.lua
-- и main/controls/controls.gui_script
local function config_number(key, default)
    local ok, value = pcall(sys.get_config_string, key, tostring(default))
    if not ok or type(value) ~= "string" then
        return default
    end
    value = value:gsub('^%s*"(.*)"%s*$', "%1"):gsub("%s", "")
    return tonumber(value) or default
end

local enabled = nil

-- включён ли тестовый режим (кэшируется: значение из game.project неизменно)
function M.is_enabled()
    if enabled == nil then
        enabled = config_number("bumpy.test_level", 0) ~= 0
    end
    return enabled
end

-- путь к метаданным уровней для текущего режима
function M.levels_path(default_path)
    if M.is_enabled() then
        return "/main/test_levels.json"
    end
    return default_path
end

return M
