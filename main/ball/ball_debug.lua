-- Отладочный вывод ball.script.
--
-- В проекте ~30 вызовов print с диагностикой игрового цикла (TOUCH, HOP, SWEPT
-- LAND, TRAP, POCKET, LIFE LOST и т.п.). Модуль даёт единый переключатель:
-- отладочный вывод включается настройкой bumpy.debug = 1 в game.project
-- (по умолчанию 0 — консоль чистая), а сообщения об ошибках/критических
-- событиях остаются всегда доступными через log.always.
--
-- Модуль-лист: других модулей не требует.
local M = {}

local enabled = nil

-- sys.get_config_string возвращает значение как есть, вместе с кавычками из
-- game.project ('"1"' вместо 1), поэтому кавычки срезаем перед tonumber.
-- Тот же приём — в main/controls/controls.gui_script и main/level/level.script
local function config_number(key, default)
    local ok, value = pcall(sys.get_config_string, key, tostring(default))
    if not ok or type(value) ~= "string" then
        return default
    end
    value = value:gsub('^%s*"(.*)"%s*$', "%1"):gsub("%s", "")
    return tonumber(value) or default
end

local function is_enabled()
    if enabled == nil then
        enabled = config_number("bumpy.debug", 0) > 0
    end
    return enabled
end

-- форматированный отладочный вывод: печатается только при bumpy.debug = 1
function M.log(fmt, ...)
    if not is_enabled() then
        return
    end
    if select("#", ...) > 0 then
        print(string.format(fmt, ...))
    else
        print(fmt)
    end
end

-- безусловный вывод: для событий, которые нужно видеть всегда
-- (загрузка уровня, GAME OVER, CHARACTER)
function M.always(fmt, ...)
    if select("#", ...) > 0 then
        print(string.format(fmt, ...))
    else
        print(fmt)
    end
end

return M
