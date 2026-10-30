-- Приземление мяча на платформу и скриптовый swept-тест.
--
-- Общая логика приземления для двух путей: физического контакта Box2D и
-- скриптовой проверки пересечения верхней грани (swept). Оба пути должны вести
-- себя одинаково, иначе приземление зависит от частоты кадров.
--
-- Модуль собирает решения о поверхности (шипы/огонь/выход/липкость) и запускает
-- действие игрока. Зависит от движения (через M.bind) и от слоя жизни; это
-- верхний уровень дерева зависимостей, поэтому действия передаются снаружи.
local C = require("main.ball.ball_config")
local grid = require("main.ball.ball_grid")
local world = require("main.ball.ball_world")
local obstacles = require("main.ball.ball_obstacles")
local goodies = require("main.ball.ball_goodies")
local trap = require("main.ball.ball_trap")
local progress = require("main.ball.ball_progress")
local input = require("main.ball.ball_input")
local dbg = require("main.ball.ball_debug")
local phys = require("main.ball.ball_physics")
local state = require("main.level.level_state")

local M = {}

local COLS = C.COLS
local CELL_H = C.CELL_H
local BOUNCE_Y = C.BOUNCE_Y
local THRESHOLD = C.THRESHOLD

-- действия слоя движения и ввода; подставляются в bind
local motion = {}
local actions = {}

-- подключить слои действия:
--   motion   = ball_motion   (hop_and_move, bounce_off_wall, settle...)
--   actions  = { settle_or_stick(self), check_slope_trap(self,row,col,dir) }
function M.bind(deps)
    deps = deps or {}
    motion = deps.motion or {}
    actions = deps.actions or {}
end

-- поведение при приземлении без команды игрока делегируется герою:
-- мяч автоматически отскакивает, Slinky встаёт на платформу и стоит
local function settle_or_stick(self)
    if actions.settle_or_stick then
        return actions.settle_or_stick(self)
    end
end

-- Приземление мяча на платформу ряда row. Общая логика для физического контакта
-- (contact_point_response) и скриптового swept-теста: проверки поверхности
-- (шипы/огонь/выход/липкость), снап в центр колонки и запуск действия игрока.
-- Вынесена отдельно, чтобы оба пути приземления вели себя одинаково и
-- приземление не зависело от частоты кадров
function M.land_on_platform(self, row)
    -- после смерти мяч уже не взаимодействует с уровнем: level.script
    -- пересобирает уровень, и любая реакция на контакт в этом окне изменила бы
    -- карман (капля на горящую платформу) уже после отката к снимку уровня
    if self.game_over then
        return
    end
    -- приземление точно в центр платформы; пока смещение идёт,
    -- не снапим X — смещение само доведёт мяч до центра (без телепортации)
    local position = go.get_position()
    if self.move_t <= 0.0 then
        go.set_position(vmath.vector3(grid.column_center(self.col), position.y, position.z))
    end
    self.touch_time = self.time
    -- Y отскока для ряда — постоянная величина из массива (зависит от высоты платформы)
    self.row = row
    self.ground_y = BOUNCE_Y[row]
    -- тап по ячейке, который не удалось выполнить в полёте (мяч упёрся в
    -- препятствие/потолок), не переносится на следующий прыжок. Цель
    -- допрыгивания по своему ряду сохраняется, пока мяч к ней идёт
    self.cell_jump = nil
    -- цель допрыгивания относится к нажатому ряду: если мяч оказался на другом
    -- ряду (соскочил в колонку без платформы и провалился ниже), цель устарела
    -- и не должна «выстрелить» позже, когда мяч снова окажется на том ряду
    if self.target_row and self.target_row ~= row then
        self.target_col = nil
        self.target_row = nil
    end
    -- шипы: контакт всегда разрушает мяч — теряется жизнь
    if world.platform_flag(row, self.col, "spike") then
        progress.lose_life(self, "spikes")
        return
    end
    -- горящая платформа: если в кармане есть капля — мяч гасит её
    -- (платформа превращается в default, капля тратится, игра продолжается);
    -- без капли контакт разрушает мяч и игра прекращается
    if world.platform_flag(row, self.col, "burning") then
        if not goodies.extinguish_burning(self, row, self.col) then
            progress.lose_life(self, "burning platform")
            return
        end
    end
    world.land_platform(row, self.col)
    -- предметы в ячейке собираются в update по фактической позиции мяча
    -- (ball_goodies.collect вызывается там), чтобы были достижимы предметы и в
    -- ячейках без платформы; здесь только проверка выхода
    if self.exit_open and not self.level_complete and world.is_exit_cell(row, self.col) then
        self.level_complete = true
        dbg.always("LEVEL COMPLETE cell=(%d, %d)", self.col, row)
        msg.post("/level", "level_complete")
        return
    end
    -- верх кирпичной кладки: обычная твёрдая поверхность — мяч пружинит как
    -- всегда, но высокий прыжок с неё запрещён (high_jump_locked)
    self.high_jump_locked = obstacles.is_block_top(row, self.col)
    -- липкая (закрашенная) платформа: мяч не пружинит — лежит на ней и ждёт
    -- команды игрока. Высокий прыжок доступен всегда, а влево/вправо дают
    -- обычный соскок на соседнюю ячейку (мяч не скатывается, а прыгает)
    go.set_position(vmath.vector3(position.x, self.ground_y, position.z))
    self.high_jump = false
    local sticky_here = self.hero.sticks_on_platform and world.platform_flag(row, self.col, "sticky")
    if sticky_here then
        local cell = row * COLS + self.col
        -- новое касание этой липкой платформы: снова доступно одно действие;
        -- возврат на ту же ячейку — не новое касание
        if self.sticky_cell ~= cell then
            self.sticky_action_used = false
            self.sticky_cell = cell
        end
        self.sticky_rest = true
    else
        self.sticky_rest = false
        self.sticky_cell = nil
    end
    -- приземление после смены траектории высокого прыжка: дополнительное
    -- управляемое смещение в этом цикле запрещено, но наклонная платформа
    -- всё равно даёт неуправляемый отскок в сторону наклона (приоритет)
    if self.rising_moved then
        self.rising_moved = false
        self.pending_dir = 0
        self.pending_jump = false
        local slope_dir = world.slope_direction(row, self.col)
        if slope_dir ~= 0 then
            -- наклон в сторону непреодолимой преграды — бесконечная ловушка
            trap.check_slope(self, row, self.col, slope_dir)
            -- как и при обычном приземлении: наклон даёт неуправляемый прыжок в
            -- сторону наклона, а у боковой стенки (border) — отскок от неё
            motion.hop_and_move(self, slope_dir)
            self.press_used = true
        else
            self.press_used = false
            settle_or_stick(self)
        end
        self.squash = 1.0
        self.squash_axis = "y"
        self.hero.apply_squash(self)
        return
    end
    local direction = 0
    if self.pending_dir ~= 0 and (self.time - self.pending_time) <= THRESHOLD then
        direction = self.pending_dir
    end
    self.pending_dir = 0
    -- новый цикл отскока: разрешено одно нажатие
    self.press_used = false
    -- наклонная платформа: неуправляемый отскок в сторону наклона,
    -- приоритет над любыми командами игрока («шар неуправляемо отскакивает»);
    -- направление определяется по повороту объекта платформы (компонент slope)
    local slope_dir = world.slope_direction(row, self.col)
    if slope_dir ~= 0 then
        -- наклонная платформа: мяч неуправляемо прыгает в сторону наклона.
        -- Если в стороне наклона стоит боковая стенка (border) — мяч прыгает
        -- в её сторону и отскакивает обратно (hop_and_move → bounce_off_wall),
        -- это бесконечная ловушка: мяч вечно мечется между платформой и стенкой
        trap.check_slope(self, row, self.col, slope_dir)
        motion.hop_and_move(self, slope_dir)
        self.press_used = true
    elseif direction ~= 0 then
        -- ручное управление отменяет отложенную цель допрыгивания
        self.target_col = nil
        if self.sticky_rest then
            -- на липкой платформе удержанная в момент касания клавиша даёт
            -- обычный соскок на соседнюю ячейку (а не скатывание) и расходует
            -- действие за это касание
            self.sticky_action_used = true
            self.sticky_rest = false
        end
        if motion.hop_and_move(self, direction) then
            self.press_used = true
        end
        input.clear_tap(self)
    elseif self.target_col and self.target_row == row then
        -- тап по ячейке своего ряда: мяч допрыгивает до неё, делая по одному
        -- шагу за приземление. Если впереди перегородка/кладка — шаг
        -- превращается в отскок, и цель снимается: дальше не пройти
        --
        -- отложенная команда тапа (cell_cmd) здесь уже израсходована: шаг
        -- выполняет именно она. Без сброса она остаётся в силе до следующего
        -- приземления, а если в целевой колонке нет платформы, мяч спрыгивает
        -- на ряд ниже — и там устаревшая команда выглядит как тап по ячейке
        -- ВЫШЕ мяча (cmd.row остался прежним), то есть запускает высокий
        -- прыжок вместо обычного соскока
        self.cell_cmd = nil
        if self.col ~= self.target_col then
            local step = self.target_col > self.col and 1 or -1
            if self.sticky_rest then
                self.sticky_action_used = true
                self.sticky_rest = false
            end
            if not motion.hop_and_move(self, step) then
                -- отскок от препятствия: цель недостижима
                self.target_col = nil
            end
            self.press_used = true
            input.clear_tap(self)
        else
            -- мяч дошёл до нажатой ячейки
            self.target_col = nil
            settle_or_stick(self)
        end
    elseif (input.jump_active(self) or self.pending_jump)
        and not self.high_jump_locked
        and not (self.sticky_rest and self.sticky_action_used) then
        -- высокий прыжок: постоянное движение вверх до платформы снизу или
        -- верхнего края поля; во время полёта можно запрыгнуть на соседнюю
        -- ячейку любого ряда. На липкой поверхности доступен, пока действие
        -- за касание не израсходовано
        if self.sticky_rest then
            self.sticky_action_used = true
            self.sticky_rest = false
        end
        motion.start_high_jump(self)
        input.clear_tap(self)
    else
        settle_or_stick(self)
    end
    self.pending_jump = false
    self.squash = 1.0
    self.squash_axis = "y"
    self.hero.apply_squash(self)
end

-- Скриптовое приземление (swept-тест). Физика Box2D шагает один раз за кадр, и
-- при большой скорости падения (с верхнего ряда) мяч за один шаг проникает в
-- тонкую платформу (20 px) глубже её середины. Тогда ближайшей гранью контакта
-- становится нижняя, нормаль смотрит вниз, и обработчик контакта принимает
-- падение за удар снизу — приземление не выполняется, мяч «пролетает» платформу
-- и теряет жизнь. Чтобы приземление не зависело от частоты кадров, каждый кадр
-- проверяем, не пересёк ли мяч верхнюю грань платформы в его колонке при
-- движении вниз (по позициям прошлого и текущего кадра), и приземляем скриптово
function M.swept_land(self, dt)
    -- после смерти мяч не взаимодействует с уровнем (см. lose_life)
    if self.game_over then
        return false
    end
    -- только свободное падение: смещение/отскок/высокий прыжок ведут себя иначе
    if self.high_jump or self.move_t > 0.0 or self.bounce_t > 0.0 then
        return false
    end
    local prev_y = self.prev_pos_y
    if not prev_y then
        return false
    end
    -- защита от повторного срабатывания на месте
    if self.time - (self.swept_time or -math.huge) < 0.1 then
        return false
    end
    local pos = go.get_position()
    -- падение вниз: при движении вверх/в покое приземления быть не может
    if phys.moving_up() then
        return false
    end
    -- проверяем фактический интервал кадра [prev_y, pos.y]: если низ мяча пересёк
    -- верхнюю грань платформы (в предыдущем кадре был выше, сейчас ниже) —
    -- физика «проскочила» её и нужно приземлить мяч скриптово. Обычное
    -- приземление (физика остановила мяч на поверхности) не срабатывает: там
    -- pos.y ≈ top, а не ниже грани
    --
    -- среди пересёкших грань берём самую верхнюю (при падении вниз мяч встречает её первой).
    -- ячейки с кирпичной кладкой пропускаем: кладка регистрируется в реестре
    -- платформ, но садиться на уровень её ряда нельзя — её верх/низ определяются
    -- скриптово (block_bottom_face/land_on_block_top), а не BOUNCE_Y.
    -- исчезнувшие (схлопнувшиеся) расходуемые платформы тоже пропускаем: они
    -- остаются в реестре, но коллизия у них отключена — мяч должен провалиться
    local land_row = nil
    for row = 0, COLS - 1 do
        if world.platform_id(row, self.col)
            and not world.block_state(row, self.col)
            and not world.platform_flag(row, self.col, "gone") then
            local top = BOUNCE_Y[row]
            if prev_y > top + 0.1 and pos.y < top - 0.1 then
                if not land_row or top > BOUNCE_Y[land_row] then
                    land_row = row
                end
            end
        end
    end
    if not land_row then
        return false
    end
    self.swept_time = self.time
    self.last_contact_time = self.time
    self.contact_processed = true
    dbg.log("SWEPT LAND cell=(%d, %d) prev_y=%.1f y=%.1f", self.col, land_row, prev_y, pos.y)
    -- снап на верхнюю грань и общая логика приземления
    go.set_position(vmath.vector3(pos.x, BOUNCE_Y[land_row], pos.z))
    M.land_on_platform(self, land_row)
    return true
end

return M
