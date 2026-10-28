-- Ввод игрока: удержания клавиш/жестов и отложенный тап по игровой ячейке.
--
-- Здесь нет физики: модуль только переводит состояние ввода в «намерения»
-- (какую сторону держат, какая ячейка нажата) и решает, когда намерение можно
-- выполнить. Сами действия (шаг, отскок, высокий прыжок) передаются снаружи
-- через M.bind — так модуль не зависит от ball_motion и ball.script.
local C = require("main.ball.ball_config")
local world = require("main.ball.ball_world")
local dbg = require("main.ball.ball_debug")

local M = {}

local COLS = C.COLS
local RADIUS = C.RADIUS
local BOUNCE_Y = C.BOUNCE_Y
local THRESHOLD = C.THRESHOLD
local CELL_CMD_TIMEOUT = C.CELL_CMD_TIMEOUT
local TOUCH_CMD_TIMEOUT = C.TOUCH_CMD_TIMEOUT

-- действия, которые выполняет слой движения; подставляются в bind
local actions = {}

-- подключить слой действия. Обязательные ключи:
--   start_high_jump(self), hop_and_move(self, dir), bounce_off_wall(self, dir)
function M.bind(table_of_actions)
    actions = table_of_actions or {}
end

-- направление удерживаемой клавиши/тач-команды; если нажаты обе — смещения нет.
-- Тач даёт два вида команд: удержание (touch_left/touch_right — свайп с
-- удержанием пальца, живёт пока палец на экране) и одноразовый тап
-- (tap_left/tap_right — короткая команда после отпускания пальца, см.
-- TOUCH_CMD_TIMEOUT). В управлении учитываются все источники.
function M.held_direction(self)
    local left = (self.left_held or self.touch_left or self.tap_left)
        and not (self.right_held or self.touch_right or self.tap_right)
    local right = (self.right_held or self.touch_right or self.tap_right)
        and not (self.left_held or self.touch_left or self.tap_left)

    if right then
        return 1
    end
    if left then
        return -1
    end
    return 0
end

-- «удержание» высокого прыжка с учётом тач-команд (свайп вверх/удержание или тап)
function M.jump_active(self)
    return self.jump_held or self.touch_jump or self.tap_jump
end

-- снять одноразовые тап-команды (после выполнения действия или по тайм-ауту);
-- удержания (touch_*) при этом не трогаются — они живут, пока палец на экране
function M.clear_tap(self)
    self.tap_left = false
    self.tap_right = false
    self.tap_jump = false
    self.touch_timer = 0.0
end

-- снять все тач-команды, включая удержания (при старте уровня/потере жизни)
function M.clear_touch(self)
    M.clear_tap(self)
    self.touch_left = false
    self.touch_right = false
    self.touch_jump = false
end

-- запустить «время жизни» тап-команды (TOUCH_CMD_TIMEOUT)
function M.set_touch_timer(self)
    self.touch_timer = TOUCH_CMD_TIMEOUT
end

-- тайм-аут одноразовых тап-команд: тап держится чуть дольше одного отскока,
-- затем снимается, чтобы жест не сработал повторно. Удержания (touch_*) при
-- этом не снимаются — они живут, пока палец на экране
function M.update_touch_timeout(self, dt)
    if self.touch_timer <= 0.0 then
        return
    end
    self.touch_timer = math.max(0.0, self.touch_timer - dt)
    if self.touch_timer == 0.0 then
        M.clear_tap(self)
    end
end

-- сенсорное управление «тап по ячейке» (bumpy.controls_mode = "cells").
-- /controls присылает "cell_tap" с игровой ячейкой (row 0 — низ, col 0..5)
-- либо с направлением dir = ±1 для тапа за боковой границей поля.
-- Намерение живёт CELL_CMD_TIMEOUT и выполняется, когда мяч готов к действию.
function M.clear_cell_cmd(self)
    self.cell_cmd = nil
    self.cell_jump = nil
end

function M.set_cell_cmd(self, message)
    if type(message) ~= "table" then
        return
    end
    local row = tonumber(message.row)
    if not row then
        return
    end
    local dir = tonumber(message.dir) or 0
    if dir > 0 then
        dir = 1
    elseif dir < 0 then
        dir = -1
    else
        dir = 0
    end
    local col = tonumber(message.col)
    if col then
        col = vmath.clamp(math.floor(col), -1, COLS)
    end
    -- цель допрыгивания по своему ряду: мяч шагает к нажатой ячейке на каждом
    -- приземлении, пока не дойдёт до неё или не встретит препятствие.
    -- Тап во время высокого прыжка цель допрыгивания НЕ ставит: он либо меняет
    -- траекторию полёта (запрыгивание на одну ячейку в сторону нажатия), либо
    -- игнорируется, если мяч уже пролетел нажатую ячейку
    local side = message.side and true or false
    if self.high_jump then
        -- намерение полёта не должно превращаться в цель после приземления
    elseif not side and col and col >= 0 and col < COLS then
        self.target_col = col
        self.target_row = vmath.clamp(math.floor(tonumber(message.row) or 0), 0, COLS - 1)
    else
        self.target_col = nil
    end
    self.cell_cmd = {
        row = vmath.clamp(math.floor(row), 0, COLS - 1),
        col = col,
        dir = dir,
        -- тап за боковой границей поля: подсвечена только боковая стенка;
        -- мяч прыгает в её сторону на уровне нажатия и ударяется о перегородку
        side = side,
        time = self.time,
        -- ряд мяча в момент нажатия: если к моменту исполнения мяч оказался
        -- НИЖЕ (соскочил в соседнюю колонку без платформы и провалился),
        -- нажатая ячейка уже не «выше мяча» — высокий прыжок по ней
        -- запрещён (см. try_cell_command)
        from_row = self.row,
        -- id тач-касания: по нему команда отменяется, если жест окажется
        -- свайпом-панорамированием (см. "cell_cancel")
        id = message.id,
    }
    -- уже назначенная цель соскока (cell_jump) НЕ сбрасывается: если новый тап
    -- придёт по уже пролётенной ячейке, он будет проигнорирован, а прежняя цель
    -- останется в силе (см. try_cell_command)
end

-- отменить тап, если жест оказался свайпом (панорамирование камеры).
-- Отменяем только ещё не исполненное намерение, и только своё касание:
-- в высоком прыжке команда применяется мгновенно (cell_cmd уже пуст), и
-- свайп после неё не должен сбрасывать назначенный соскок
function M.cancel_cell_cmd(self, id)
    if not self.cell_cmd then
        return false
    end
    if id ~= nil and self.cell_cmd.id ~= id then
        return false
    end
    -- цель допрыгивания тоже снимаем: игрок тянул экран, а не целился
    self.target_col = nil
    self.target_row = nil
    M.clear_cell_cmd(self)
    return true
end

-- выполнить отложенное намерение тапа по ячейке, когда мяч готов к действию.
-- Возвращает true, если команда израсходована (действие выполнено или
-- отброшено) — тогда обычная обработка удержаний в этом кадре не нужна.
function M.try_cell_command(self)
    local cmd = self.cell_cmd
    if not cmd then
        return false
    end
    -- намерение устарело (мяч так и не получил возможности действовать)
    if self.time - cmd.time > CELL_CMD_TIMEOUT then
        M.clear_cell_cmd(self)
        return false
    end
    -- высокий прыжок уже идёт: тап задаёт сторону соскока (запрыгивание).
    -- Траекторию можно изменить, ТОЛЬКО пока мяч не долетел до целевой ячейки.
    -- «Долетел» = нижняя часть мяча пересекла уровень отскока этого ряда
    -- (BOUNCE_Y[row]); тот же признак ведёт счётчик hj_row в update. Проверяем
    -- и по позиции, и по счётчику — команда может прийти из on_message до
    -- ближайшего update, когда hj_row ещё не сдвинулся.
    -- Тап по уже достигнутой ячейке игнорируется, а ранее назначенная цель
    -- соскока сохраняется в силе.
    if self.high_jump then
        local passed = cmd.row < (self.hj_row or self.row)
            or (go.get_position().y - RADIUS >= BOUNCE_Y[cmd.row])
        -- направление соскока: для тапа по ячейке поля — в её сторону,
        -- для тапа за боковой границей поля — задано знаком dir (±1)
        local dir = cmd.dir
        if dir == 0 and cmd.col then
            if cmd.col > self.col then
                dir = 1
            elseif cmd.col < self.col then
                dir = -1
            end
        end
        if passed or dir == 0 then
            -- ячейка пройдена либо тап в собственную колонку: траектория не
            -- меняется, но уже поставленная цель соскока остаётся в силе
            local keep = self.cell_jump
            M.clear_cell_cmd(self)
            self.cell_jump = keep
            -- пройденная ячейка не становится целью допрыгивания после падения
            self.target_col = nil
            self.target_row = nil
            dbg.log("HIGH JUMP tap ignored row=%d passed=%s dir=%d",
                cmd.row, tostring(passed), dir)
            return true
        end
        -- до этой ячейки мяч ещё не долетел: команда меняет траекторию полёта.
        -- Уровень соскока — нажатый ряд, но не ниже ряда, на котором мяч уже
        -- находится (цикл подъёма сам применит цель, как только дотянется до него)
        local level = math.max(cmd.row, self.hj_row or self.row)
        -- цель допрыгивания по ряду относится к приземлению и здесь не нужна:
        -- во время полёта команда задаёт именно сторону соскока
        self.target_col = nil
        self.target_row = nil
        -- cell_jump ставим после сброса: clear_cell_cmd обнуляет и его
        M.clear_cell_cmd(self)
        self.cell_jump = { row = level, dir = dir, border = cmd.side }
        dbg.log("HIGH JUMP relocate row=%d dir=%d col=%d", level, dir, self.col)
        return true
    end
    -- команда принимается только когда мяч не в середине действия
    if self.press_used or self.move_t > 0.0 or self.bounce_t > 0.0 then
        return false
    end
    local since_touch = self.time - self.touch_time
    local from_rest = self.hero.allow_from_rest(self)
    if not (self.sticky_rest or since_touch <= THRESHOLD or from_rest) then
        return false
    end
    -- направление: для тапа по ячейке поля — в сторону этой ячейки,
    -- для тапа за границей поля — задано направлением нажатия (dir = ±1)
    local dir = cmd.dir
    if dir == 0 and cmd.col then
        if cmd.col > self.col then
            dir = 1
        elseif cmd.col < self.col then
            dir = -1
        end
    end
    -- высокий прыжок недоступен с верха кирпичной кладки (high_jump_locked).
    -- На липкой платформе он доступен ТОЛЬКО в момент первого касания — так же,
    -- как при управлении кнопками: пока мяч только что приземлился и окно
    -- THRESHOLD не прошло, а действие за это касание ещё не израсходовано,
    -- тап по ячейке выше даёт высокий прыжок. Жёсткий запрет по self.sticky_rest
    -- срабатывал бы уже на первом кадре после приземления, и игрок, успевший
    -- нажать на ячейку выше сразу при касании липкой платформы, вместо
    -- высокого прыжка получал бы обычный соскок в сторону
    local can_high_jump = not self.high_jump_locked
        and (not self.sticky_rest
            or (not self.sticky_action_used and since_touch <= THRESHOLD))
    -- ячейка (или боковая стенка) выше мяча: высокий прыжок, сторона задаётся
    -- тапом и применяется при пересечении уровня нажатия. Для тапа за границей
    -- поля мяч поднимается до этого уровня и там прыгает в сторону нажатия —
    -- на границе поля его встречает боковая стенка, и он отскакивает от неё
    -- (флаг border в cell_jump)
    --
    -- Тап был БОКОВЫМ (нажата ячейка своего ряда или ниже), но мяч к моменту
    -- исполнения оказался НИЖЕ нажатой ячейки: он соскочил в соседнюю колонку,
    -- платформы на своём ряду там нет, и он провалился на ряд ниже. Команда
    -- устарела — нажатая ячейка больше не «рядом», а «выше мяча», и без этой
    -- проверки она запускала ВЫСОКИЙ ПРЫЖОК вместо обычного соскока.
    -- Правильное поведение: мяч просто падает (соскок уже выполнен)
    local tap_was_above = not cmd.from_row or cmd.row > cmd.from_row
    if cmd.row > self.row and not tap_was_above then
        M.clear_cell_cmd(self)
        self.target_col = nil
        self.target_row = nil
        dbg.log("CELL tap dropped row=%d from_row=%d ball_row=%d (fell below)",
            cmd.row, cmd.from_row or -1, self.row)
        return true
    end
    if cmd.row > self.row and can_high_jump then
        local jump_row = cmd.row
        -- команда израсходована, но сторона соскока нужна уже во время полёта:
        -- ставим cell_jump ПОСЛЕ сброса, иначе clear_cell_cmd его обнулит.
        -- Тап в собственную колонку — просто высокий прыжок без соскока
        M.clear_cell_cmd(self)
        if dir ~= 0 then
            self.cell_jump = { row = jump_row, dir = dir, border = cmd.side }
        end
        -- на липкой платформе высокий прыжок расходует единственное действие
        -- за это касание (как и при нажатии кнопки высокого прыжка)
        if self.sticky_rest then
            self.sticky_action_used = true
        end
        actions.start_high_jump(self)
        self.press_used = true
        self.squash = 1.0
        self.squash_axis = "y"
        self.hero.apply_squash(self)
        return true
    end
    -- тот же ряд или ниже: обычный подскок в сторону нажатия. Если нажатие
    -- было за боковой границей поля, мяч прыгает в сторону стенки и
    -- отскакивает от неё, оставаясь в своей колонке
    if dir ~= 0 then
        if self.sticky_rest then
            self.sticky_action_used = true
            self.sticky_rest = false
        end
        local at_edge = (dir > 0 and self.col >= COLS - 1)
            or (dir < 0 and self.col <= 0)
        if cmd.side and at_edge then
            actions.bounce_off_wall(self, dir)
        else
            actions.hop_and_move(self, dir)
        end
        self.press_used = true
        self.pending_dir = 0
        M.clear_cell_cmd(self)
        return true
    end
    -- тап в собственную ячейку движения не даёт
    M.clear_cell_cmd(self)
    return true
end

return M
