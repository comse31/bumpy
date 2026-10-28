-- Режим игры, выбранный в стартовом меню.
--
--   "classic"   — классическая игра: у мяча есть жизни, при 0 жизней —
--                 GAME OVER и возврат в стартовое меню;
--   "adventure" — приключение: жизни не учитываются, смерть мяча просто
--                 перезапускает текущий уровень (жизни не тратятся,
--                 GAME OVER недостижим).
--
-- Здесь же хранится флаг «открыто стартовое меню»: пока меню открыто, игра
-- стоит на паузе (мяч не двигается, READY не показывается), а ввод получает
-- меню, а не мяч.
--
-- Модуль общий для всех скриптов (game.project: shared_state = 1), поэтому
-- решение о режиме принимается один раз и читается из любого слоя
-- (ball.script, ball_progress.lua).
local M = {}

M.CLASSIC = "classic"
M.ADVENTURE = "adventure"

local mode = M.CLASSIC
local menu_open = true

-- нормализация значения режима: неизвестное трактуется как классическая игра
local function normalize(value)
    if value == M.ADVENTURE then
        return M.ADVENTURE
    end
    return M.CLASSIC
end

function M.set_mode(value)
    mode = normalize(value)
    return mode
end

function M.get_mode()
    return mode
end

function M.is_adventure()
    return mode == M.ADVENTURE
end

-- учитываются ли жизни в текущем режиме
function M.lives_enabled()
    return mode ~= M.ADVENTURE
end

function M.set_menu_open(open)
    menu_open = open and true or false
    return menu_open
end

function M.is_menu_open()
    return menu_open
end

return M
