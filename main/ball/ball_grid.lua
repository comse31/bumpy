-- Геометрия игровой сетки 6x6: центр колонки, ячейка по мировой позиции,
-- стартовая ячейка уровня.
--
-- Все функции — чистые преобразования координат, состояние мяча не читают и не
-- меняют. Поэтому модуль не зависит ни от чего, кроме конфигурации сетки, и его
-- можно использовать из любого слоя (landing, world, motion).
local C = require("main.ball.ball_config")

local M = {}

local COLS = C.COLS
local CELL_W = C.CELL_W
local CELL_H = C.CELL_H
local PLATFORM_Y_BASE = C.PLATFORM_Y_BASE

-- центр колонки (платформы) по X
function M.column_center(col)
    return (col + 0.5) * CELL_W
end

-- ячейка (row, col) по мировой позиции: row 0 — низ экрана.
-- Нужна для сбора предметов по фактической ячейке мяча, в том числе в ячейках
-- без платформы, которые мяч пролетает при прыжке/падении
function M.cell_at(position)
    local col = vmath.clamp(math.floor(position.x / CELL_W), 0, COLS - 1)
    local row = vmath.clamp(math.floor((position.y - PLATFORM_Y_BASE) / CELL_H + 1e-6), 0, COLS - 1)
    return row, col
end

-- ряд по мировой Y (0 — низ экрана)
function M.row_at(y)
    return vmath.clamp(math.floor((y - PLATFORM_Y_BASE) / CELL_H + 1e-6), 0, COLS - 1)
end

-- индекс ячейки метаданных (0..35, строка 0 — верх) -> экранные row/col.
-- Индекс приходит от level.script (start_cell/exit_cell из levels.json)
function M.from_cell_index(cell)
    local col = cell % COLS
    local row = (COLS - 1) - math.floor(cell / COLS)
    return row, col
end

return M
