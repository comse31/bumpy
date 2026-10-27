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
local CEILING_BOUNCE = 280.0  -- px/s вниз при ударе о потолок/низ платформы
local CEILING_COOLDOWN = 0.2  -- защита от повторного отскока о тот же потолок
local REST_FLIP_TIME = 0.30   -- переворот на месте, если герой остался на голове
local REST_FLIP_MIN = 0.6 * math.pi -- минимальный «кривой» угол для переворота на месте
local IMPACT_TIME = 0.22      -- сколько держим позу удара о стену/потолок
local SQUASH_TIME_SCALE = 2.0 -- восстановление после приземления в 2 раза медленнее

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

-- сила сжатия 0..1 по времени после касания (s: 1 -> 0).
-- В момент удара сразу максимальное сжатие (sq6), затем плавное восстановление
-- без быстрого «вспыхивания» кадров; короткая задержка держит самый сжатый кадр.
local function squash_amount(s)
    local a = math.min(1.0, s * 1.2)
    return a * a * (3.0 - 2.0 * a)
end

-- ближайшая «нормальная» ориентация: чётное число полуоборотов
local function upright_target(rot)
    return math.floor(rot / (2.0 * math.pi) + 0.5) * 2.0 * math.pi
end

-- герой после приземления остался вверх ногами и игрок не продолжает движение:
-- плавно доворачиваем его на месте, чтобы следующий прыжок не был «на голове»
local function start_rest_flip(self)
    if (self.rest_flip_t or 0.0) > 0.0 then return end
    if (self.rot_t or 0.0) > 0.0 or (self.move_t or 0.0) > 0.0 or (self.bounce_t or 0.0) > 0.0 then
        return
    end
    local rot = self.rot or 0.0
    local target = upright_target(rot)
    if math.abs(rot - target) < REST_FLIP_MIN then return end
    self.rest_flip_from = rot
    self.rest_flip_to = target
    self.rest_flip_duration = REST_FLIP_TIME
    self.rest_flip_t = REST_FLIP_TIME
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
    -- зеркало по X: при прыжке влево голова/лицо смотрят влево, вправо — обычный вид.
    -- Рисуется той же картинкой, без дополнительных PNG.
    if self.sprite_k and self.applied_face ~= self.face_dir then
        go.set(VISUAL .. "#sprite", "scale",
            vmath.vector3(self.sprite_k * self.face_dir, self.sprite_k, 1.0))
        self.applied_face = self.face_dir
    end

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

    -- Удар о потолок/стену показываем «перевёрнутым приземлением»: берём
    -- обычные sq-кадры и поворачиваем визуал плоской стороной к поверхности.
    -- Потолок — 180°, стена — ±90°. Это временно, до отдельных кадров из ТЗ.
    local impact_angle = nil
    if (self.impact_t or 0.0) > 0.0 then
        if self.impact_kind == "ceiling" then
            impact_angle = math.pi
        elseif self.impact_kind == "wall_left" then
            impact_angle = math.pi / 2.0
        elseif self.impact_kind == "wall_right" then
            impact_angle = -math.pi / 2.0
        end
    end

    local name, angle
    if impact_angle then
        local a = squash_amount(self.squash or 0.0)
        name = a > 0.02 and ("sq" .. level_index(a, 6)) or "rest"
        orient = 0
        angle = impact_angle
    else
        name = pick_frame(self, vn, res)
        angle = res
    end

    local anim = ANIM[orient][name]
    if anim ~= self.vis_anim then
        self.vis_anim = anim
        msg.post(VISUAL .. "#sprite", "play_animation", { id = anim })
    end

    go.set(self.visual, "rotation", vmath.quat_rotation_z(angle))

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
    self.sprite_k = k
    self.face_dir = 1
    self.applied_face = 1
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
    self.rest_flip_t = 0.0
    self.rest_flip_from = nil
    self.rest_flip_to = nil
    self.rest_flip_duration = 0.0
    self.last_ceiling_time = -math.huge
    self.impact_kind = nil
    self.impact_t = 0.0
    self.face_dir = 1
    self.applied_face = nil
    self.vis_anim = nil
    go.set(self.visual, "rotation", vmath.quat())
    update_visual(self)
end

function M.update(self, dt)
    -- переворот на месте после приземления, если игрок не продолжил движение
    if (self.rest_flip_t or 0.0) > 0.0 then
        self.rest_flip_t = math.max(0.0, self.rest_flip_t - dt)
        local k = 1.0 - self.rest_flip_t / self.rest_flip_duration
        self.rot = self.rest_flip_from + (self.rest_flip_to - self.rest_flip_from) * k
        if self.rest_flip_t == 0.0 then
            self.rot = self.rest_flip_to % (2.0 * math.pi)
            self.rest_flip_from = nil
            self.rest_flip_to = nil
            self.rest_flip_duration = 0.0
        end
    elseif self.rot_t > 0.0 then
        -- переворот на 180° в сторону прыжка во время смещения между платформами
        self.rot_t = math.max(0.0, self.rot_t - dt)
        local k = 1.0 - self.rot_t / self.rot_duration
        self.rot = self.rot_from + (self.rot_to - self.rot_from) * k
    end
    -- поза удара о стену/потолок живёт короткое время, затем возвращаемся
    -- к обычной ориентации
    if (self.impact_t or 0.0) > 0.0 then
        self.impact_t = math.max(0.0, self.impact_t - dt)
        if self.impact_t == 0.0 then
            self.impact_kind = nil
        end
    end
    -- на липкой платформе герой лежит (sq3) — переворот на месте не нужен;
    -- кадр обновляется по обычной логике
    -- кадр деформации выбирается каждый кадр: self.squash затухает в общем update
    update_visual(self)
end

-- удар о потолок/низ платформы: Bumpy отскакивает вниз, а не просто зависает
function M.on_ceiling(self)
    if self.time - (self.last_ceiling_time or -math.huge) < CEILING_COOLDOWN then
        return false
    end
    self.last_ceiling_time = self.time
    self.impact_kind = "ceiling"
    self.impact_t = IMPACT_TIME
    go.set("#collision_object", "linear_velocity", vmath.vector3(0.0, -CEILING_BOUNCE, 0.0))
    update_visual(self)
    return true
end

function M.apply_squash(self)
    if self.squash_axis == "x" then
        -- удар боком о перегородку/кладку: временно кладём героя плоской
        -- стороной к стене (перевёрнутое приземление), пока длится squash
        local d = (self.bounce_x_wall or 0.0) - (self.bounce_x_start or 0.0)
        self.impact_kind = d < 0.0 and "wall_left" or "wall_right"
        self.impact_t = IMPACT_TIME
    elseif self.impact_kind ~= "ceiling" then
        self.impact_kind = "floor"
        self.impact_t = 0.0
    end
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

-- приземление/удар восстанавливается медленнее обычного: кадры не мелькают
function M.squash_time_scale(self)
    return SQUASH_TIME_SCALE
end

-- приземление без команды игрока: мяч автоматически отскакивает.
-- moving — игрок удерживает/заказал горизонтальное движение: тогда переворот
-- на месте не нужен, следующий прыжок сам развернёт героя в полёте.
function M.settle(self, moving)
    go.set("#collision_object", "linear_velocity", vmath.vector3(0.0, self.env.jump_speed, 0.0))
    self.next_touch_time = self.time + self.env.period
    if not moving then
        start_rest_flip(self)
    end
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
        -- при прыжке влево разворачиваем лицо/голову влево; вправо — обычный вид
        self.face_dir = direction < 0 and -1 or 1
        -- боковое действие: переворот на месте отменяется, вместо него
        -- обычный переворот в полёте на соседнюю клетку
        self.rest_flip_t = 0.0
        self.rest_flip_from = nil
        self.rest_flip_to = nil
        self.rest_flip_duration = 0.0
        self.rot_from = self.rot
        self.rot_to = self.rot - direction * math.pi
        self.rot_duration = duration
        self.rot_t = duration
    end
end

return M
