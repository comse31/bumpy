-- Собираемые предметы (goodies) и контакт с табличкой EXIT.
--
-- Всё, что связано с «взять предмет» и «дойти до выхода»: геометрические
-- проверки касания (круг мяча против квадрата спрайта / прямоугольника
-- таблички) и разбор типа предмета при сборе.
--
-- Модуль зависит только от конфигурации, реестра уровня и отладки; счётчики
-- кармана меняет на самом self, но решений о смерти/перезапуске уровня не
-- принимает — это слой progress.
local C = require("main.ball.ball_config")
local world = require("main.ball.ball_world")
local dbg = require("main.ball.ball_debug")
local state = require("main.level.level_state")

local M = {}

local RADIUS = C.RADIUS
local GOODIE_HALF = C.GOODIE_HALF
local EXIT_SIGN_HALF_W = C.EXIT_SIGN_HALF_W
local EXIT_SIGN_HALF_H = C.EXIT_SIGN_HALF_H

-- круг против квадрата: ближайшая к центру мяча точка квадрата
local function circle_touches_box(center, half_w, half_h)
    local bpos = go.get_position()
    local cx = vmath.clamp(bpos.x, center.x - half_w, center.x + half_w)
    local cy = vmath.clamp(bpos.y, center.y - half_h, center.y + half_h)
    local dx = bpos.x - cx
    local dy = bpos.y - cy
    return dx * dx + dy * dy <= RADIUS * RADIUS
end

-- касается ли мяч спрайта предмета (квадрат GOODIE_HALF вокруг центра)
function M.goodie_touched(id)
    return circle_touches_box(go.get(id, "position"), GOODIE_HALF, GOODIE_HALF)
end

-- касается ли мяч таблички EXIT (прямоугольник вокруг её центра)
function M.exit_touched(id)
    return circle_touches_box(go.get(id, "position"), EXIT_SIGN_HALF_W, EXIT_SIGN_HALF_H)
end

-- собрать goodies в ячейке: если объект существует и ещё не собран — отправить
-- ему "collect" (он скроет себя и пометит collected = 1) и увеличить
-- соответствующий счётчик мяча. Предмет берётся только при фактическом касании:
-- одной ячейки с мячом недостаточно (иначе берётся «не касаясь»).
--
-- Тип (kind) в прототипах: 0 — капля (drop), 1 — ключ (key), 2 — молоток
-- (hammer), 3 — собираемый объект, открывающий выход (collectible),
-- 4 — дополнительная жизнь (сердечко)
function M.collect(self, row, col)
    local id = world.goodie_id(row, col)
    if not id then
        return false
    end
    -- локальная защита от повторного сбора: сбор идёт покадрово по ячейке мяча,
    -- а флаг collected у самого объекта выставляется только при обработке
    -- сообщения "collect" и может отставать на кадр
    if self.collected[id] then
        return false
    end
    local comp = state.component(id, "goodie")
    local ok, collected = pcall(go.get, comp, "collected")
    if not ok or (collected and collected > 0) then
        return false
    end
    -- сбор только по касанию: пока мяч не дотянулся до спрайта предмета — не берём
    if not M.goodie_touched(id) then
        return false
    end
    self.collected[id] = true
    local pos = go.get(id, "position")
    msg.post(id, "collect")

    local kind_ok, kind = pcall(go.get, comp, "kind")

    if kind_ok and kind == 4 then
        -- сердечко: жизнь прибавляется сразу, в карман предметов не попадает
        self.lives = self.lives + 1
        dbg.log("LIFE +1 total=%d cell=(%d, %d)", self.lives, col, row)
        msg.post("/pocket", "add_life", { x = pos.x, y = pos.y, count = self.lives })
        return true
    end
    if kind_ok and kind == 3 then
        self.collectibles = self.collectibles + 1
        dbg.log("COLLECT %d/%d cell=(%d, %d)", self.collectibles, state.timer, col, row)
        if state.timer > 0 and self.collectibles >= state.timer then
            world.open_exit(self)
        end
        return true
    elseif kind_ok and kind == 2 then
        self.hammer_pocket = self.hammer_pocket + 1
        dbg.log("HAMMERS +1 total=%d cell=(%d, %d)", self.hammer_pocket, col, row)
    elseif kind_ok and kind == 1 then
        self.key_pocket = self.key_pocket + 1
        dbg.log("KEYS +1 total=%d cell=(%d, %d)", self.key_pocket, col, row)
    else
        self.pocket = self.pocket + 1
        dbg.log("POCKET +1 total=%d cell=(%d, %d)", self.pocket, col, row)
    end
    -- уведомить HUD-карман: предмет перелетает в полосу над игровым полем
    local hud_kind = 0
    if kind_ok then
        if kind == 2 then
            hud_kind = 2
        elseif kind == 1 then
            hud_kind = 1
        end
    end
    msg.post("/pocket", "add", { kind = hud_kind, x = pos.x, y = pos.y })
    return true
end

-- погасить горящую платформу каплей из кармана: платформа становится обычной,
-- игра продолжается; возвращает true, если гашение произошло (капля потрачена)
function M.extinguish_burning(self, row, col)
    if self.pocket <= 0 then
        return false
    end
    if not world.extinguish_platform(row, col) then
        return false
    end
    self.pocket = self.pocket - 1
    dbg.log("POCKET -1 total=%d cell=(%d, %d): burning platform extinguished", self.pocket, col, row)
    -- капля потрачена — убрать её из HUD-кармана
    msg.post("/pocket", "remove", { kind = 0 })
    return true
end

return M
