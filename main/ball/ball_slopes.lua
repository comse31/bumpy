-- «Призрачные» наклонные платформы над мячом.
--
-- Наклонная платформа повёрнута на 10°, поэтому её нижний угол опускается ниже
-- плоской грани примерно на 12 px. Мяч подпрыгивает над своей платформой на
-- высоту HEIGHT: в верхней точке его верх почти достаёт платформу ряда выше (до
-- плоского низа остаётся ~6.7 px), и скошенный угол наклона из соседней колонки
-- попадает на траекторию. Box2D присылает контакт снизу, общий обработчик
-- принимает его за удар в потолок: подъём гасится, наклон прогибается, играется
-- «потолочная» анимация, а боковой прыжок срывается (мяч отбрасывает вбок по
-- склону вместо перехода в соседнюю колонку).
--
-- Поэтому пока мяч находится ЦЕЛИКОМ ПОД наклонной платформой (верх мяча ниже
-- её нижней грани), её физика отключается — платформа становится «призраком»:
-- визуал и свойства остаются, но мяч спокойно пролетает под ней и не задевает
-- скошенный угол. Как только мяч оказывается не ниже нижней грани (падает
-- сверху или стоит на поверхности), физика возвращается, и приземление на
-- наклон работает как раньше — неуправляемый отскок в сторону склона
-- (см. ball_landing и slope_direction в ball_world).
--
-- Условие «целиком под платформой» выбрано намеренно: при падении СВЕРХУ мяч в
-- момент касания поверхности находится ВЫШЕ нижней грани платформы, поэтому
-- физика включена и он не может «протуннелировать» сквозь наклон (страхует и
-- swept-тест приземления). Отключение затрагивает только наклоны, под которыми
-- мяч пролетает или стоит снизу, — ровно случай «прыжок под наклонной
-- платформой».
--
-- Высокий прыжок не затрагивается: пока он идёт, физика наклонов всегда
-- включена (подъём до нижней грани и удар снизу по кладке — часть его правил).
--
-- Листовые зависимости: конфигурация сетки, геометрия сетки, реестр уровня и
-- отладка. Набор выключенных платформ хранится в self, как состояние остальных
-- модулей мяча.
local C = require("main.ball.ball_config")
local grid = require("main.ball.ball_grid")
local world = require("main.ball.ball_world")
local dbg = require("main.ball.ball_debug")

local M = {}

local CELL_W = C.CELL_W
local RADIUS = C.RADIUS
local COLS = C.COLS
local PLATFORM_H = C.PLATFORM_H
local BOUNCE_Y = C.BOUNCE_Y
-- зазор у нижней грани: «призрак» не должен спорить с касанием при приземлении
local EPS = 0.5

-- колонки, которые перекрывает мяч по X: в прыжке он проходит между колонками,
-- поэтому «призраками» должны быть наклоны всех перекрытых колонок
local function spanned_cols(x)
    local lo = math.floor((x - RADIUS) / CELL_W)
    local hi = math.floor((x + RADIUS) / CELL_W)
    if lo < 0 then lo = 0 end
    if hi > COLS - 1 then hi = COLS - 1 end
    local cols = {}
    for c = lo, hi do
        cols[#cols + 1] = c
    end
    return cols
end

-- вернуть физику всем выключенным платформам
function M.reset(self)
    local ghosts = self.slope_ghosts
    self.slope_ghosts = nil
    if not ghosts then
        return
    end
    for id, g in pairs(ghosts) do
        world.set_platform_collision(id, true)
        dbg.log("SLOPE ghost on: cell=(%d, %d)", g.col, g.row)
    end
end

-- выключить физику наклону под мячом; повторный вызов для того же id — no-op
local function ghost_off(self, g)
    local ghosts = self.slope_ghosts
    if ghosts and ghosts[g.id] then
        return
    end
    world.set_platform_collision(g.id, false)
    dbg.log("SLOPE ghost off: cell=(%d, %d)", g.col, g.row)
    self.slope_ghosts = ghosts or {}
    self.slope_ghosts[g.id] = g
end

-- каждый кадр привести набор «призраков» к текущему положению мяча
function M.update(self)
    -- высокий прыжок не меняем: подъём должен упираться в платформы как раньше
    if self.high_jump then
        M.reset(self)
        return
    end
    local pos = go.get_position()
    local ball_top = pos.y + RADIUS
    -- проверяем ряд мяча и ряд выше: подскок поднимает мяч меньше чем на ряд,
    -- поэтому выше он ничего не встретит. Диапазон считается от фактической
    -- позиции, а не от последнего приземления — так работает и в падении
    local want = {}
    local cols = spanned_cols(pos.x)
    local first = grid.row_at(pos.y)
    local last = math.min(COLS - 1, first + 1)
    for row = first, last do
        -- нижняя грань платформы ряда row (плоская, без учёта скоса)
        local bottom = BOUNCE_Y[row] - RADIUS - PLATFORM_H
        -- «призрак»: мяч целиком под платформой — его верх ниже нижней грани
        if ball_top <= bottom + EPS then
            local list = world.slopes_in_row(row, cols)
            for i = 1, #list do
                want[list[i].id] = list[i]
            end
        end
    end
    -- вернуть физику наклонам, под которыми мяч уже не находится
    local ghosts = self.slope_ghosts
    if ghosts then
        for id, g in pairs(ghosts) do
            if not want[id] then
                world.set_platform_collision(id, true)
                dbg.log("SLOPE ghost on: cell=(%d, %d)", g.col, g.row)
                ghosts[id] = nil
            end
        end
        if next(ghosts) == nil then
            self.slope_ghosts = nil
        end
    end
    -- отключить физику наклонам, под которыми мяч оказался
    for _, g in pairs(want) do
        ghost_off(self, g)
    end
end

return M
