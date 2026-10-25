-- Герой «Bumpy»: покадровая анимация из /main/bumpy/frames (+ bumpy.atlas).
-- Вся специфика героя — в этом модуле; общая механика (сетка, физика,
-- столкновения, предметы, выход) — в ball.script.
--
--   u_* — обычное положение, f_* — после переворота на 180° (лицо вверх ногами,
--   плоская сторона всё равно внизу). Кадр выбирается по скорости шара и по
--   self.squash, который считает ball.script (1 в момент касания -> 0).
-- Коллизия шара не меняется: деформация только визуальная.
local M = {}

M.name = "bumpy"

-- ---- настройки (можно крутить без правки логики) ----
local VISUAL = "/bumpy_visual"
local TARGET_PX = 32 * 1.5     -- размер героя в игре: на 50% больше мяча (SIZE в ball.script)
local FRAME_CONTENT_PX = 104  -- высота персонажа в кадре u_rest (кадры 208x208)
local PIN = 0.6           -- 0..1: насколько лужица «прилипает» к полу, пока шар уже летит вверх (0 = выкл.)
local PIN_MAX_GAP = 40.0  -- ограничение подлёта для прилипания, px
local TUMBLE_RES = 0.25   -- рад: при большем повороте в воздухе показываем симметричные кадры кувырка

local ORIENT = { [0] = "u", [1] = "f" }
local NAMES = { "rest", "fall1", "fall2", "fall3", "fall4", "rise1", "rise2", "rise3",
    "sq1", "sq2", "sq3", "sq4", "sq5", "sq6", "tm1", "tm2",
    "wl1", "wl2", "wl3", "wl4", "wr1", "wr2", "wr3", "wr4" }
local ANIM = { [0] = {}, [1] = {} }
for o = 0, 1 do
    for _, name in ipairs(NAMES) do
        ANIM[o][name] = hash(ORIENT[o] .. "_" .. name)
    end
end

local function level_index(a, count)
    return math.max(1, math.min(count, math.ceil(a * count)))
end

-- сила сжатия 0..1 по времени после касания (s: 1 -> 0): быстро вдавливается, затем расправляется
local function squash_amount(s)
    local u = 1.0 - s
    if u < 0.2 then
        return 0.35 + 0.65 * (u / 0.2)
    elseif u < 0.6 then
        return 1.0 - (u - 0.2) / 0.4
    end
    return 0.0
end

-- вытягивание по вертикальной скорости: падает — капля, взлетает — вытянутый овал
local function stretch_name(vn)
    local m = math.min(1.0, math.abs(vn))
    if m < 0.15 then
        return "rest"
    end
    local k = (m - 0.1) / 0.9
    if vn < 0.0 then
        return "fall" .. level_index(k, 4)
    end
    return "rise" .. level_index(k, 3)
end

local function pick_frame(self, vn, res)
    if math.abs(res) > TUMBLE_RES then
        local m = math.min(1.0, math.abs(vn))
        if m > 0.6 then return "tm2" end
        if m > 0.15 then return "tm1" end
        return "rest"
    end
    local s = self.squash or 0.0
    if s > 0.0 then
        local a = squash_amount(s)
        if a > 0.02 then
            if self.squash_axis == "x" then
                local d = (self.bounce_x_wall or 0.0) - (self.bounce_x_start or 0.0)
                if d ~= 0.0 then
                    return (d > 0.0 and "wr" or "wl") .. level_index(a, 4)
                end
            else
                return "sq" .. level_index(a, 6)
            end
        end
    end
    if self.sticky_rest then
        return "sq3" -- липкая платформа: шар прилип и лежит приплюснутым
    end
    return stretch_name(vn)
end

-- выставить кадр, поворот и «прилипание» к полу
local function update_visual(self)
    local rot = self.rot or 0.0
    local n = math.floor(rot / math.pi + 0.5) -- сколько полуоборотов уже сделано
    local res = rot - n * math.pi             -- остаток поворота -pi/2..pi/2
    local orient = n % 2                      -- 0 — обычный набор кадров, 1 — перевёрнутый

    local vy = 0.0
    local ok, vel = pcall(go.get, "#collision_object", "linear_velocity")
    if ok and vel then
        vy = vel.y
    end
    local vn = vy / self.env.jump_speed

    local anim = ANIM[orient][pick_frame(self, vn, res)]
    if anim ~= self.vis_anim then
        self.vis_anim = anim
        msg.post(VISUAL .. "#sprite", "play_animation", { id = anim })
    end

    go.set(self.visual, "rotation", vmath.quat_rotation_z(res))

    local dy = 0.0
    local pos = go.get_position()
    local s = self.squash or 0.0
    if PIN > 0.0 and s > 0.0 and self.squash_axis ~= "x" and self.ground_y then
        local gap = pos.y - self.ground_y
        gap = math.max(0.0, math.min(PIN_MAX_GAP, gap))
        dy = -gap * PIN * s
    end
    -- визуал — отдельный корневой объект: следуем за мячом вручную (см. setup)
    go.set_position(vmath.vector3(pos.x, pos.y + dy, pos.z), self.visual)
end

function M.setup(self, env)
    self.env = env
    self.visual = go.get_id(VISUAL)
    self.vis_anim = nil
    -- Визуал не привязываем к мячу через go.set_parent: сообщение о смене
    -- родителя обрабатывается позже, а keep_world_transform сохранил бы уже
    -- изменённый масштаб объекта — герой вырастал в 16 раз. Держим спрайт
    -- размером с мяч и синхронизируем позицию в update_visual.
    local obj_scale = go.get_scale(self.visual).x
    local k = TARGET_PX / (FRAME_CONTENT_PX * obj_scale)
    go.set(VISUAL .. "#sprite", "scale", vmath.vector3(k, k, 1.0))
end

function M.activate(self)
    self.vis_anim = nil
    msg.post(VISUAL .. "#sprite", "enable")
end

function M.deactivate(self)
    msg.post(VISUAL .. "#sprite", "disable")
end

function M.reset(self)
    self.rot = 0.0
    self.rot_from = 0.0
    self.rot_to = 0.0
    self.rot_t = 0.0
    self.rot_duration = 0.0
    self.vis_anim = nil
    go.set(self.visual, "rotation", vmath.quat())
    update_visual(self)
end

function M.update(self, dt)
    -- переворот на 180° в сторону прыжка во время смещения между платформами
    if self.rot_t > 0.0 then
        self.rot_t = math.max(0.0, self.rot_t - dt)
        local k = 1.0 - self.rot_t / self.rot_duration
        self.rot = self.rot_from + (self.rot_to - self.rot_from) * k
    end
    -- кадр деформации выбирается каждый кадр: self.squash затухает в общем update
    update_visual(self)
end

function M.apply_squash(self)
    update_visual(self)
end

function M.hop_height(self)
    return self.env.hop_height
end

-- мячик «прилипает» к липкой (закрашенной) платформе: не пружинит, лежит на
-- ней и ждёт команды игрока: влево/вправо — соскок на соседнюю ячейку
-- (см. hop_and_move в ball.script), высокий прыжок — только при первом касании
M.sticks_on_platform = true

-- длительность бокового шага мячика: без изменений
function M.step_scale(self)
    return 1.0
end

-- приземление без команды игрока: мяч автоматически отскакивает
function M.settle(self)
    go.set("#collision_object", "linear_velocity", vmath.vector3(0.0, self.env.jump_speed, 0.0))
    self.next_touch_time = self.time + self.env.period
end

function M.allow_from_rest(self)
    return false
end

-- мяч лежит на липкой поверхности: повторные контакты Box2D (шар не отрывается
-- от платформы) игнорируем — иначе каждые CONTACT_DEDUP секунд мяч «приземлялся»
-- бы заново и заново запускал соскок при удержании клавиши
function M.ignore_contacts(self)
    return self.sticky_rest == true
end

-- началось действие (шаг/отскок/прыжок): direction/duration заданы для
-- бокового смещения и nil для высокого прыжка
function M.on_action(self, direction, duration)
    if direction then
        self.rot_from = self.rot
        self.rot_to = self.rot - direction * math.pi
        self.rot_duration = duration
        self.rot_t = duration
    end
end

return M
