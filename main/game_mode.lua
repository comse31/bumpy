-- Режим игры, выбранный в стартовом меню.
--
--   "classic"   — классическая игра: у мяча есть жизни, при 0 жизней —
--                 GAME OVER и возврат в стартовое меню;
--   "adventure" — случайный сгенерированный уровень из БД: игрок получает
--                 3 жизни и снаряжение ровно в минимально требуемом объёме
--                 (приходит с уровнем из GET /api/levels/random), а после
--                 прохождения уровня игра возвращается в стартовое меню.
--                 Смерть мяча в этом режиме тратит жизни, но по их исчерпании
--                 GAME OVER не показывается — игра возвращается в меню.
--
-- Здесь же хранится флаг «открыто стартовое меню»: пока меню открыто, игра
-- стоит на паузе (мяч не двигается, READY не показывается), а ввод получает
-- меню, а не мяч. Плюс номер уровня для «Приключения» (adventure_level): он
-- всегда 1, потому что сгенерированный уровень строится из payload, а не по
-- индексу в main/levels.json.
--
-- Модуль общий для всех скриптов (game.project: shared_state = 1), поэтому
-- решение о режиме принимается один раз и читается из любого слоя
-- (ball.script, ball_progress.lua).
local M = {}

M.CLASSIC = "classic"
M.ADVENTURE = "adventure"

local mode = M.CLASSIC
local menu_open = true
-- уровень, выбранный в подменю «Приключения» (1..max)
local adventure_level = 1

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

function M.set_adventure_level(level)
    adventure_level = math.max(1, math.floor(tonumber(level) or 1))
    return adventure_level
end

function M.get_adventure_level()
    return adventure_level
end

-- учитываются ли жизни в текущем режиме.
-- Жизни есть в обоих режимах, но исчерпание жизней трактуется по-разному:
-- в классике — GAME OVER, в «Приключении» — возврат в стартовое меню
-- (см. game_mode.is_adventure). Функция оставлена для проверок, где нужен
-- именно классический учёт.
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
