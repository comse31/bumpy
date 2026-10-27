-- Текущая видимая область мира — общее состояние камеры, HUD и сенсорного
-- управления.
--
-- Камера (main/render/camera.script) каждый кадр публикует здесь видимый
-- прямоугольник мира и трансформ полосы HUD-кармана. Остальные системы
-- пересчитывают по этим значениям координаты:
--   * сенсорное управление — координаты GUI (дизайн 960x720) <-> мир;
--   * предметы HUD-кармана (main/pocket/pocket_item.script) — свои локальные
--     координаты полосы (0..960, 640..720) -> мировые.
--
-- Модуль общий для всех скриптов (в game.project включён shared_state = 1).
--
-- Начальные значения — вся сцена 960x720 при масштабе 1: до первого кадра
-- камеры пересчёт остаётся корректным.
local M = {}

-- дизайн-пространство GUI: в нём верстались интерфейс и плашки
local DESIGN_W = 960.0
local DESIGN_H = 720.0

M.left = 0.0     -- мировая X левого края экрана
M.bottom = 0.0   -- мировая Y нижнего края экрана
M.width = DESIGN_W  -- ширина видимой области в мировых единицах
M.height = DESIGN_H -- высота видимой области в мировых единицах

-- трансформ полосы HUD-кармана в мире: локальная точка (x, y) предмета
-- (x в 0..960, y в 640..720) попадает в мир в (hud_x + x*hud_scale,
-- hud_y + y*hud_scale)
M.hud_x = 0.0
M.hud_y = 0.0
M.hud_scale = 1.0

-- Мировая точка -> координаты GUI (дизайн 960x720, левый низ — 0,0).
function M.world_to_screen(wx, wy)
    if M.width <= 0.0 or M.height <= 0.0 then
        return wx, wy
    end
    return (wx - M.left) * DESIGN_W / M.width,
        (wy - M.bottom) * DESIGN_H / M.height
end

-- Координаты GUI (дизайн 960x720) -> мировая точка.
function M.screen_to_world(gx, gy)
    if M.width <= 0.0 or M.height <= 0.0 then
        return gx, gy
    end
    return M.left + gx * M.width / DESIGN_W,
        M.bottom + gy * M.height / DESIGN_H
end

return M
