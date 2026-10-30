-- Движение мяча: прыжки, шаги между колонками, отскоки от препятствий и
-- высокий прыжок.
--
-- Два отскока (перегородка и кирпичная кладка) сведены к одной функции
-- M.bounce_off_barrier: различается только X грани, с которой мяч встречает
-- препятствие. Это же устраняет прежнюю несогласованность — для кладки не
-- вызывался hero.on_action, и Slinky не выгибался при ударе о блок.
--
-- Модуль не зависит от ball_landing и ball.script: всё, что нужно знать о
-- поверхности и вводе, приходит через self и модули-листья.
local C = require("main.ball.ball_config")
local phys = require("main.ball.ball_physics")
local grid = require("main.ball.ball_grid")
local world = require("main.ball.ball_world")
local obstacles = require("main.ball.ball_obstacles")
local dbg = require("main.ball.ball_debug")

local M = {}

local COLS = C.COLS
local SCREEN_H = C.SCREEN_H
local CELL_W = C.CELL_W
local RADIUS = C.RADIUS
local PLATFORM_H = C.PLATFORM_H
local BOUNCE_Y = C.BOUNCE_Y
local GRAVITY = C.GRAVITY
local JUMP_SPEED = C.JUMP_SPEED
local HIGH_JUMP_SPEED = C.HIGH_JUMP_SPEED
local SQUASH_AMOUNT = C.SQUASH_AMOUNT
local WALL_THICKNESS = C.WALL_THICKNESS
local BLOCK_HALF_W = C.BLOCK_HALF_W
local MOVE_DURATION = C.MOVE_DURATION

-- X перегородки на границе: справа от col — (col+1)*CELL_W, слева — col*CELL_W
local function wall_face_x(self, direction)
    return (direction > 0 and (self.col + 1) or self.col) * CELL_W
end

-- X боковой грани кладки: блок стоит в соседней колонке col+direction по центру
-- её ячейки, поэтому его грань — центр той ячейки ∓ полуширина кладки
local function block_face_x(self, direction)
    return grid.column_center(self.col + direction) - direction * BLOCK_HALF_W
end

-- отскок от препятствия (перегородка или кладка): мяч прыгает в сторону
-- препятствия, касается его грани в верхней точке дуги и возвращается в центр
-- своей колонки; X — линейно во времени (туда и обратно), Y — физическая
-- парабола до приземления на свою платформу.
-- face_x — мировая X грани; inset — дополнительный отступ точки касания
-- (у перегородки учитывается её толщина)
function M.bounce_off_barrier(self, direction, face_x, inset)
    self.bounce_x_start = go.get_position().x
    -- в момент удара мяч сплющен по X на SQUASH_AMOUNT, поэтому до грани
    -- дотягивается сжатый край (RADIUS * (1 - SQUASH_AMOUNT))
    self.bounce_x_wall = face_x - direction * (RADIUS * (1.0 - SQUASH_AMOUNT) + (inset or 0.0))
    self.bounce_x_end = grid.column_center(self.col)
    local vy = M.hop_velocity(self)
    phys.set_vertical(vy)
    self.bounce_duration = M.landing_time(self, vy)
    self.bounce_t = self.bounce_duration
    self.next_touch_time = self.time + self.bounce_duration
    -- сплющивание по X (горизонтальное) включается в момент касания грани
    self.bounce_squash_pending = true
    self.action_time = self.time
    -- специфика героя: мяч переворачивается, Slinky выгибается в сторону стены
    self.hero.on_action(self, direction, self.bounce_duration)
end

-- отскок от вертикальной перегородки
function M.bounce_off_wall(self, direction)
    M.bounce_off_barrier(self, direction, wall_face_x(self, direction), WALL_THICKNESS / 2.0)
end

-- отскок от кирпичной кладки
function M.bounce_off_block(self, direction)
    M.bounce_off_barrier(self, direction, block_face_x(self, direction), 0.0)
end

-- отскок строго вниз после удара мяча в НИЖНЮЮ грань наклонной платформы.
-- У наклонной платформы нормаль контакта наклонена (есть компонента по X),
-- поэтому Box2D отбрасывает мяч вбок по склону. Гасим горизонтальную скорость
-- и возвращаем мяч в центр его колонки, чтобы падение было строго вертикальным
function M.rebound_straight_down(self)
    local pos = go.get_position()
    local vy = phys.vy()
    -- X не трогаем, пока идёт скриптовое смещение (там позицией управляет update)
    if self.move_t <= 0.0 and self.bounce_t <= 0.0 then
        pos = vmath.vector3(grid.column_center(self.col), pos.y, pos.z)
        go.set_position(pos)
    end
    -- только вертикальная составляющая, направленная вниз (без подскока вверх)
    phys.set_vertical(math.min(vy, 0.0))
end

-- высота мяча над землей (реальная позиция мяча)
function M.height_above_ground(self)
    if not self.ground_y then
        return 0.0
    end
    return math.max(0.0, go.get_position().y - self.ground_y)
end

-- высота подскока при смещении между платформами задаётся героем: мяч прыгает
-- на обычную высоту, Slinky «переступает» (минимальный подъём)
function M.hop_height(self)
    return self.hero.hop_height(self)
end

-- вертикальная скорость, чтобы достичь вершины подскока из текущей высоты
function M.hop_velocity(self)
    local h = M.height_above_ground(self)
    local target = M.hop_height(self)
    if h >= target then
        return 0.0
    end
    return math.sqrt(2.0 * GRAVITY * (target - h))
end

-- время до приземления при текущей высоте и вертикальной скорости
function M.landing_time(self, vy)
    local h = M.height_above_ground(self)
    return (vy + math.sqrt(vy * vy + 2.0 * GRAVITY * h)) / GRAVITY
end

-- длительность смещения равна времени до приземления: мяч достигает
-- центра целевой платформы ровно в момент касания (нижняя точка траектории)
function M.move_duration_for(t_land)
    if t_land <= 0.0 then
        return MOVE_DURATION
    end
    return math.max(1.0 / 60.0, t_land)
end

-- скриптовое смещение по X (см. update_move_tween в ball.script)
function M.move(self, direction, duration)
    local position = go.get_position()
    self.move_from = position.x
    -- всегда приземляемся точно в центр целевой платформы
    self.move_to = grid.column_center(self.col)
    self.move_duration = duration or MOVE_DURATION
    self.move_t = self.move_duration
    self.action_time = self.time
    -- специфика героя: мяч переворачивается, Slinky запоминает сторону переката
    self.hero.on_action(self, direction, self.move_duration)
end

-- оценка времени до следующего контакта во время высокого прыжка: первый уровень —
-- гравитационное замедление (парабола), выше — постоянная скорость JUMP_SPEED до
-- ближайшей платформы сверху в колонке (или верхнего края поля) + падение под
-- гравитацией на платформу текущего ряда
function M.high_jump_touch_time(self)
    local pos = go.get_position()
    local vel = phys.velocity()
    -- Y центра мяча в момент удара о препятствие: нижняя грань ближайшей
    -- платформы выше в колонке, нижняя грань стены (блока) или верхний край поля
    local stop_y = SCREEN_H - RADIUS
    for r = self.row + 1, COLS - 1 do
        -- кирпичная кладка проверяется ПЕРВОЙ: у неё нет меша платформы, и иначе
        -- она была бы ошибочно принята за платформу ряда
        local block_bottom = obstacles.block_bottom_face(r, self.col)
        if block_bottom then
            stop_y = math.min(stop_y, block_bottom - RADIUS)
            break
        end
        local id = world.platform_id(r, self.col)
        if id then
            local py = go.get(id, "position").y
            stop_y = math.min(stop_y, py - PLATFORM_H / 2.0 - RADIUS)
            break
        end
    end
    -- высота перехода на постоянную скорость: центр мяча на уровне отскока ряда выше
    local level_y = self.row + 1 < COLS and BOUNCE_Y[self.row + 1] or math.huge
    local t = 0.0
    if pos.y < level_y then
        -- параболический подъём до первого уровня (или до препятствия, если оно ниже)
        local rise_to = math.min(level_y, stop_y)
        if pos.y < rise_to then
            local dy = rise_to - pos.y
            t = (vel.y - math.sqrt(math.max(0.0, vel.y * vel.y - 2.0 * GRAVITY * dy))) / GRAVITY
        end
    end
    -- постоянная скорость до препятствия
    t = t + math.max(0.0, (stop_y - math.max(pos.y, level_y)) / JUMP_SPEED)
    -- падение под гравитацией на платформу текущего ряда
    local fall_h = math.max(0.0, stop_y - BOUNCE_Y[self.row])
    return t + math.sqrt(2.0 * fall_h / GRAVITY)
end

-- подскок на обычную высоту отскока со смещением в заданном направлении: смещение
-- X линейно во времени, а высота — физическая парабола, поэтому мяч летит по дуге.
-- Возвращает true, если смещение выполнено (мяч перешёл в соседнюю колонку)
function M.hop_and_move(self, direction)
    local old_col = self.col
    -- вертикальная перегородка на границе ячеек: прыжок сквозь неё невозможен —
    -- мяч прыгает в её сторону, отскакивает и возвращается на свою платформу
    if world.wall_blocking(self.row, old_col, direction) then
        dbg.log("WALL bounce dir=%d col=%d row=%d", direction, old_col, self.row)
        -- удар наносится в момент касания перегородки (середина дуги), а не в
        -- начале прыжка — флаг снимается в update при k <= 0.5
        self.bounce_hit_pending = true
        self.bounce_hit_dir = direction
        M.bounce_off_wall(self, direction)
        return false
    end
    -- стена (блок) в целевой ячейке: прыжок сквозь неё невозможен — мяч прыгает
    -- в её сторону, отскакивает от боковой грани и возвращается на свою платформу
    if world.has_block(self.row, old_col + direction) then
        dbg.log("BLOCK bounce dir=%d col=%d row=%d", direction, old_col, self.row)
        M.bounce_off_block(self, direction)
        return false
    end
    -- любое управляемое смещение срывает мяч с липкой поверхности: сбрасываем
    -- покой, иначе контакты навсегда игнорируются (hero.ignore_contacts) и мяч
    -- перестаёт отскакивать на обычных платформах
    self.sticky_rest = false
    self.col = self.col + direction
    dbg.log("HOP dir=%d col %d->%d", direction, old_col, self.col)
    -- масштаб длительности шага задаёт герой (Slinky перекатывается медленнее):
    -- вертикальный импульс растягивается во времени, поэтому X-смещение и
    -- приземление остаются синхронными
    local vy = M.hop_velocity(self) * self.hero.step_scale(self)
    local t_land = M.landing_time(self, vy)
    phys.set_vertical(vy)
    M.move(self, direction, M.move_duration_for(t_land))
    self.next_touch_time = self.time + t_land
    return true
end

-- Сообщить /controls, идёт ли сейчас высокий прыжок. Пока мяч летит вверх,
-- сенсорное управление отправляет тап по ячейке СРАЗУ при нажатии (палец не
-- успевает отпустить: ячейку мяч пролетает за доли секунды). Вне полёта тап
-- отправляется по отпусканию — так свайп-панорамирование не превращается в
-- команду мячу.
function M.report_motion(self)
    local high = self.high_jump and true or false
    if self.reported_high ~= high then
        self.reported_high = high
        msg.post("/controls", "motion_state", { high = high })
    end
end

-- высокий прыжок: постоянное движение вверх до платформы снизу или верхнего края
-- поля; во время полёта можно запрыгнуть на соседнюю ячейку любого ряда.
-- Используется и с обычной платформы, и с липкой (там высокий прыжок доступен
-- и при параллельном перемещении)
function M.start_high_jump(self)
    world.bend_platform(self.row, self.col)
    phys.set_vertical(HIGH_JUMP_SPEED)
    self.rising = true
    self.high_jump = true
    M.report_motion(self)
    -- мяч оторвался от липкой поверхности: покой снят
    self.sticky_rest = false
    self.action_time = self.time
    self.hero.on_action(self, nil, nil)
    -- первый уровень для проверки пересечения — над текущим рядом
    self.hj_row = self.row + 1
    self.next_touch_time = self.time + M.high_jump_touch_time(self)
end

-- Прервать высокий прыжок по команде «вниз» (клавиша Down или тап по ячейке
-- ниже мяча в тач-режиме). Мяч перестаёт подниматься и падает из той ячейки,
-- в которой находится в момент нажатия: скорость гасится, дальше работает
-- обычная гравитация, а приземление ловит swept-тест (см. ball_landing).
-- Возвращает true, если прыжок действительно был прерван
function M.cancel_high_jump(self)
    if not self.high_jump then
        return false
    end
    self.high_jump = false
    self.rising = false
    self.hj_row = nil
    -- намерение соскока ставилось для полёта и после отмены не актуально
    self.cell_jump = nil
    -- оценка времени полёта относилась к высокому прыжку: после отмены мяч
    -- просто падает, и следующее касание определит физика/приземление
    self.next_touch_time = nil
    -- прерывание расходует удержание прыжка: пока игрок не отпустит кнопку
    -- высокого прыжка, новый прыжок не начнётся (иначе зажатая клавиша или
    -- экранная кнопка запустила бы его снова сразу при приземлении).
    -- Флаги снова поднимутся только по свежему нажатию: клавиша — по
    -- pressed (см. on_input), экранная кнопка — по новому touch_control
    self.jump_held = false
    self.touch_jump = false
    self.tap_jump = false
    self.pending_jump = false
    phys.stop()
    self.action_time = self.time
    dbg.log("HIGH JUMP cancelled at y=%.1f row=%d col=%d",
        go.get_position().y, self.row, self.col)
    M.report_motion(self)
    return true
end

-- визуальный прогиб платформы (dir = 1 — вниз, -1 — вверх) и уведомление
-- о приземлении — тонкие обёртки, чтобы движение не зависело от сигнатур ball_world
function M.bend_platform(self, row, col, dir)
    world.bend_platform(row, col, dir)
end

function M.land_platform(self, row, col)
    world.land_platform(row, col)
end

return M
