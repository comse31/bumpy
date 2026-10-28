-- Препятствия уровня: перегородки и кирпичная кладка.
--
-- Оба вида геометрически «мешают» мячу, но физики у них нет: перегородка —
-- тонкая вертикальная коллизия, кладка — скриптовый блок (у #platform_block нет
-- collision object). Поэтому пересечения проверяются по координатам и
-- реестру уровня, а не через Box2D.
--
-- Модуль зависит от конфигурации, сетки, реестра уровня (ball_world) и
-- отладки. Решений о жизни/смерти не принимает.
local C = require("main.ball.ball_config")
local grid = require("main.ball.ball_grid")
local world = require("main.ball.ball_world")
local dbg = require("main.ball.ball_debug")
local phys = require("main.ball.ball_physics")
local state = require("main.level.level_state")

local M = {}

local COLS = C.COLS
local CELL_H = C.CELL_H
local PLATFORM_H = C.PLATFORM_H
local PLATFORM_Y_BASE = C.PLATFORM_Y_BASE
local RADIUS = C.RADIUS
local BOUNCE_Y = C.BOUNCE_Y
local BLOCK_HEIGHT = C.BLOCK_HEIGHT

-- перегородки: псевдонимы реестра, чтобы логика читалась коротко
M.is_wall_destroyed = world.is_wall_destroyed
M.has_wall_right = world.has_wall_right
M.has_wall_left = world.has_wall_left
M.wall_blocking = world.wall_blocking

-- удар по разрушаемой перегородке: вид меняется только если в кармане есть
-- ключик — расходим один ключ и шлём "hit" (стена сама ведёт прочность и вид);
-- без ключа отскок обычный, стена не повреждается
function M.hit_destructible_wall(self, direction)
    local b = direction > 0 and self.col + 1 or self.col
    local id = state.wall_id(self.row, b)
    -- только у разрушаемой перегородки есть компонент #destructible
    if not id or not pcall(go.get, state.component(id, "destructible"), "destroyed") then
        return
    end
    if self.key_pocket > 0 then
        self.key_pocket = self.key_pocket - 1
        msg.post(id, "hit")
        dbg.log("KEYS -1 total=%d: hit destructible wall", self.key_pocket)
        -- ключ потрачен — убрать его из HUD-кармана
        msg.post("/pocket", "remove", { kind = 1 })
    end
end

-- стоит ли мяч на верхней грани кирпичной стены: кладка занимает всю ячейку
-- row, поэтому приземлившись на её верх мяч оказывается на уровне ряда row+1.
-- Верхняя грань блока лежит ровно на поверхности платформы ряда выше, поэтому
-- мяч на кладке ведёт себя как на липкой платформе (высокий прыжок недоступен)
function M.is_block_top(row, col)
    return row > 0 and world.has_block(row - 1, col)
end

-- мировая Y нижней грани оставшейся кладки. Кладка занимает всю ячейку: её
-- низ лежит на верхней грани платформы своего ряда (platform_y(row) +
-- PLATFORM_H/2), а верхний край совпадает с верхней гранью платформы ряда выше;
-- каждый разбитый снизу ряд поднимает нижнюю грань на 1/rows высоты кладки.
-- nil, если блока нет или он разрушен
function M.block_bottom_face(row, col)
    local id, broken, destroyed = world.block_state(row, col)
    if not id or destroyed > 0 then
        return nil
    end
    local rows = world.block_rows(id)
    local bottom = PLATFORM_Y_BASE + row * CELL_H + PLATFORM_H / 2.0
    return bottom + (broken / rows) * BLOCK_HEIGHT
end

-- удар мяча снизу по кирпичной стене: каждый удар сносит один ряд кладки, а
-- самый первый удар по стене расходует один молоток из кармана (без молотка
-- кладку не разбить). Молоток берётся один раз на стену — повторные удары по
-- той же стене молотков не тратят; стена сама ведёт число разбитых рядов и вид
function M.hit_block_from_below(self, row, col)
    local id, _, destroyed = world.block_state(row, col)
    if not id or destroyed > 0 then
        return
    end
    -- защита от двойного сноса ряда в одном кадре: удар может прийти и из
    -- скриптовой проверки потолка, и из контакта с верхней гранью кладки (#top)
    if self.block_hit_id == id and self.time - (self.block_hit_time or -math.huge) < 0.1 then
        return
    end
    self.block_hit_id = id
    self.block_hit_time = self.time
    if self.hammer_wall_id ~= id then
        if self.hammer_pocket <= 0 then
            dbg.log("BLOCK hit from below: no hammers, wall intact cell=(%d, %d)", col, row)
            return
        end
        self.hammer_pocket = self.hammer_pocket - 1
        self.hammer_wall_id = id
        -- молоток потрачен — убрать его из HUD-кармана
        msg.post("/pocket", "remove", { kind = 2 })
        dbg.log("HAMMERS -1 total=%d: brick wall hit from below", self.hammer_pocket)
    end
    msg.post(id, "hit")
end

-- приземление мяча на верх кирпичной стены. Кладка занимает всю ячейку, её
-- верх совпадает с поверхностью платформы ряда выше. Физики у кладки нет,
-- поэтому приземление проверяется скриптово: если мяч падает в колонке с
-- кладкой и его центр достиг уровня ряда выше — он приземляется на верх кладки
-- и «прилипает» (как на липкую платформу: высокий прыжок недоступен)
function M.land_on_block_top(self)
    -- только при свободном падении (без смещения/отскока/высокого прыжка)
    if self.high_jump or self.move_t > 0.0 or self.bounce_t > 0.0 then
        return false
    end
    -- защита от повторного срабатывания в одном кадре/на месте
    if self.time - (self.block_top_time or -math.huge) < 0.1 then
        return false
    end
    if phys.moving_up() then
        return false
    end
    local pos = go.get_position()
    local crow = grid.row_at(pos.y)
    -- если в этой ячейке есть настоящая платформа — приземление обрабатывает
    -- обычная физика, скриптовый «верх кладки» не нужен
    if world.platform_id(crow, self.col) then
        return false
    end
    -- кладка в ряду ниже: её верх — уровень текущего ряда crow
    if crow < 1 or not world.has_block(crow - 1, self.col) then
        return false
    end
    local land_y = BOUNCE_Y[crow]
    if pos.y > land_y or pos.y <= land_y - CELL_H then
        return false
    end
    -- приземление на верх кладки: центр мяча — на уровне ряда выше.
    -- Верх кладки — обычная твёрдая поверхность: мяч пружинит как всегда, но
    -- высокий прыжок с неё запрещён (флаг high_jump_locked)
    self.row = crow
    self.ground_y = land_y
    self.touch_time = self.time
    self.last_contact_time = self.time
    self.high_jump_locked = true
    -- кладка не липкая: покой снимается
    self.sticky_rest = false
    self.sticky_cell = nil
    self.press_used = false
    self.block_top_time = self.time
    go.set_position(vmath.vector3(grid.column_center(self.col), land_y, pos.z))
    self.hero.settle(self)
    self.squash = 1.0
    self.squash_axis = "y"
    self.hero.apply_squash(self)
    dbg.log("BLOCK top landing cell=(%d, %d)", self.col, crow)
    return true
end

return M
