-- Бесконечная ловушка на наклонной платформе.
--
-- Если мяч попал на наклон, который упирается в непреодолимую преграду, он
-- мечется между платформой и преградой вечно. Модуль определяет такую ситуацию
-- и ведёт обратный отсчёт до потери жизни; плашку «YOU ARE TRAPPED» рисует
-- /trap (main/ui/trap/trap.go).
--
-- Модуль зависит от конфигурации, сетки, реестра уровня и отладки. Потерю жизни
-- не выполняет: возвращает признак, что отсчёт закончился, — решение принимает
-- слой progress.
local C = require("main.ball.ball_config")
local world = require("main.ball.ball_world")
local dbg = require("main.ball.ball_debug")
local state = require("main.level.level_state")

local M = {}

local COLS = C.COLS
local TRAP_COUNTDOWN = C.TRAP_COUNTDOWN

-- начать показ плашки и обратный отсчёт (см. M.update)
function M.start(self)
    if self.trap_active or self.game_over then
        return
    end
    self.trap_active = true
    self.trap_timer = TRAP_COUNTDOWN
    self.trap_shown = nil
    msg.post("/trap", "show")
    dbg.log("TRAP: infinite slope trap cell=(%d, %d)", self.col, self.row)
end

-- является ли наклонная платформа (row, col) с направлением slope_dir
-- бесконечной ловушкой: выхода нет, если на пути наклона
--   * край поля (там всегда стоит непробиваемая боковая стенка border),
--   * непробиваемая перегородка (у неё нет компонента #destructible),
--   * разрушаемая перегородка, но в кармане нет ключа,
--   * другая наклонная платформа, направленная навстречу (мяч мечется между ними)
function M.check_slope(self, row, col, slope_dir)
    if self.trap_active then
        return
    end
    local tc = col + slope_dir
    -- наклон в сторону края поля: боковая стенка border не разрушается
    if tc < 0 or tc > COLS - 1 then
        M.start(self)
        return
    end
    -- перегородка на пути наклона (между col и tc)
    local b = slope_dir > 0 and col + 1 or col
    local wall = state.wall_id(row, b)
    if wall and not world.is_wall_destroyed(row, b) then
        -- #destructible есть только у разрушаемых перегородок; без ключа их не пробить
        local destructible = pcall(go.get, state.component(wall, "destructible"), "destroyed")
        if not destructible or self.key_pocket <= 0 then
            M.start(self)
        end
        return
    end
    -- две наклонные платформы в сторону друг друга: мяч бесконечно мечется между ними
    if world.slope_direction(row, tc) == -slope_dir then
        M.start(self)
    end
end

-- обратный отсчёт на плашке. Возвращает true, если время вышло и нужно терять
-- жизнь (уровень перезапускается); плашку скрывает слой progress в lose_life
function M.update(self, dt)
    if not self.trap_active then
        return false
    end
    self.trap_timer = self.trap_timer - dt
    local shown = math.max(1, math.ceil(self.trap_timer))
    if shown ~= self.trap_shown then
        self.trap_shown = shown
        msg.post("/trap", "count", { count = shown })
    end
    return self.trap_timer <= 0.0
end

-- снять плашку и отсчёт (старт уровня, потеря жизни)
function M.reset(self)
    self.trap_active = false
    self.trap_timer = 0.0
    self.trap_shown = nil
    msg.post("/trap", "hide")
end

return M
