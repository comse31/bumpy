-- Герой «Slinky» (пружинка): собран из сегментов-колец (id из main.collection).
-- Движение строится вокруг общей траектории переката и распространяющейся по
-- кольцам волны — каждое кольцо не живёт своей физикой, а следует за общим
-- законом со временным сдвигом.
--
-- Четыре независимых эффекта:
--   1) перекат  — центр движется по дуге с плавным разгоном/торможением;
--   2) волна    — кольца последовательно проходят траекторию и деформируются;
--   3) удар     — сжатие распространяется снизу вверх после приземления;
--   4) покой    — затухающее покачивание, нижняя опора почти неподвижна.
local M = {}

-- пружина длины: чуть более собранная, чем при недодемпфировании
local SPRING_K = 100.0        -- жёсткость пружины
local SPRING_C = 18.0         -- демпфирование
local SPRING_STRETCH = 0.45   -- растяжение на максимальной скорости прыжка
local SPRING_COMPRESS = 0.6   -- сжатие в момент удара (self.squash == 1)

-- геометрия пружинки
local SLINKY_RINGS = { "si_1", "si_2", "si_3", "si_4", "si_5", "si_6", "si_7" }
local SLINKY_LEN = 34.0        -- длина пружины в покое (мировые единицы)
local SLINKY_STEP_LIFT = 10.0  -- подъём при шаге: Slinky почти не отрывается от опоры
local SLINKY_BEND = 16.0       -- выгиб в дугу при отскоке от перегородки
local SLINKY_ARC_H = 12.0      -- высота дуги переката (центр движется «по радиусу»)

-- волна переката: верхнее кольцо стартует первым и заканчивает раньше нижнего;
-- FLOW_DURATION + FLOW_STAGGER = 1.0 — последнее (нижнее) кольцо финиширует в
-- конце шага
local FLOW_DURATION = 0.68
local FLOW_STAGGER = 0.32

-- покой: покачивание сильнее сразу после приземления и затухает до слабого;
-- волна бежит по высоте кольца (фазовый сдвиг), нижняя опора почти неподвижна
local WAVE_KICK = 3.0          -- амплитуда сразу после приземления (px)
local WAVE_MIN = 0.6          -- слабая амплитуда в устоявшемся покое (px)
local WAVE_DECAY = 2.5        -- скорость затухания к минимуму
local WAVE_FREQ = 2.4         -- частота покачивания
local WAVE_PHASE = 2.0        -- фазовый сдвиг по высоте (рад)

-- удар: сжатие распространяется снизу вверх с задержкой на кольцо
local IMPACT_DELAY = 0.05     -- задержка реакции соседнего кольца (с)
local IMPACT_DURATION = 0.18  -- длительность импульса сжатия (с)
local IMPACT_AMOUNT = 0.30    -- доля сжатия длины пружины от импульса

-- URL спрайта сегмента-кольца
local function ring_sprite(self, i)
    return msg.url(nil, self.rings[i], "sprite")
end

-- показать/скрыть все сегменты-кольца
local function show_rings(self, on)
    local id = on and "enable" or "disable"
    for i = 1, #self.rings do
        msg.post(ring_sprite(self, i), id)
    end
end

-- точка на дуге окружности между (x0, y) и (x1, y) с высотой подъёма h:
-- перекат идёт «по радиусу» — центр пружинки движется по дуге, а не по прямой
local function arc_point(x0, x1, y, h, t)
    local c = x1 - x0
    if math.abs(c) < 1e-3 or h <= 1e-6 then
        return x0 + c * t, y
    end
    local s = c >= 0.0 and 1.0 or -1.0
    local cabs = math.abs(c)
    local mx = x0 + 0.5 * c
    local R = (cabs * cabs / 4.0 + h * h) / (2.0 * h)
    local phi = math.asin(math.min(1.0, (0.5 * cabs) / R))
    local a = (-phi + 2.0 * phi * t) * s
    return mx + R * math.sin(a), (y + h - R) + R * math.cos(a)
end

-- прогресс переката конкретного кольца (u: 0 — низ, 1 — верх): верхние кольца
-- стартуют раньше и заканчивают раньше нижних — возникает последовательная волна
local function flow_t(u, p)
    local delay = (1.0 - u) * FLOW_STAGGER
    local t = vmath.clamp((p - delay) / FLOW_DURATION, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)          -- плавный разгон и финиш кольца
end

-- импульс удара для кольца: сжатие приходит снизу вверх с задержкой
local function impact(u, age_since_land)
    local age = age_since_land - u * IMPACT_DELAY
    if age < 0.0 or age >= IMPACT_DURATION then
        return 0.0
    end
    return math.sin(math.pi * age / IMPACT_DURATION)
end

-- разложить кольца пружинки по общей траектории (покой / перекат / удар)
local function place_rings(self)
    local pos = go.get_position()
    local n = #self.rings
    local length = SLINKY_LEN * self.slinky_scale

    local walking = self.move_t > 0.0 and self.move_from ~= nil
    local p = walking and (1.0 - self.move_t / self.move_duration) or 1.0
    local dir = 1.0
    if walking and self.move_to < self.move_from then
        dir = -1.0
    end
    local base_y = walking and (self.ground_y or pos.y) or pos.y
    local age_since_land = self.time - (self.impact_t or -math.huge)

    for i = 1, n do
        local u = (i - 1) / (n - 1)                 -- 0 (низ) .. 1 (верх)
        local d = (u - 0.5) * length                -- смещение вдоль оси пружинки
        local x, y, theta
        if walking then
            -- перекат: каждое кольцо проходит общую дугу со своим сдвигом, а
            -- смещение вдоль оси вращается вместе с кольцом (верх становится
            -- низом, кольцо прокручивается на 180°)
            local t = flow_t(u, p)
            local cx, cy = arc_point(self.move_from, self.move_to, base_y, SLINKY_ARC_H, t)
            local a = dir * math.pi * t
            x = cx + d * math.sin(a)
            y = cy + d * math.cos(a)
            theta = -a
        else
            -- нижняя опора закреплена у платформы; удар сжимает пружинку снизу вверх
            local imp = impact(u, age_since_land)
            local bottom = base_y - length / 2.0
            y = bottom + (d + length / 2.0) * (1.0 - IMPACT_AMOUNT * imp)
            -- бегущая волна деформации (в покое затухает до слабой)
            local wave = math.sin(self.time * WAVE_FREQ - u * WAVE_PHASE)
            x = pos.x + self.slinky_bend * u * u + wave * self.wave_amp
            theta = -math.atan2(2.0 * self.slinky_bend * u, length)
        end
        go.set_position(vmath.vector3(x, y, pos.z), self.rings[i])
        go.set(self.rings[i], "rotation", vmath.quat_rotation_z(theta))
    end
end

function M.setup(self, env)
    self.env = env
    self.rings = {}
    for i = 1, #SLINKY_RINGS do
        self.rings[i] = go.get_id(SLINKY_RINGS[i])
    end
    self.slinky_scale = 1.0
    self.slinky_vel = 0.0
    self.slinky_bend = 0.0
    self.slinky_bend_dir = 1.0
    self.wave_amp = 0.0
    self.impact_t = -math.huge
    self.resting = false
    place_rings(self)
end

function M.activate(self)
    show_rings(self, true)
end

function M.deactivate(self)
    show_rings(self, false)
end

function M.reset(self)
    self.slinky_scale = 1.0
    self.slinky_vel = 0.0
    self.slinky_bend = 0.0
    self.wave_amp = 0.0
    self.impact_t = -math.huge
    self.resting = false
    place_rings(self)
end

function M.update(self, dt)
    if self.game_over then
        return
    end
    -- длина пружины: целевая растёт со скоростью полёта и падает в момент удара
    -- (self.squash); текущая догоняет целевую через затухающую пружину. При
    -- просадке FPS интегрируем подшагами, чтобы не было резких скачков
    local vy = go.get("#collision_object", "linear_velocity").y
    local speed = math.min(math.abs(vy) / self.env.jump_speed, 1.5)
    local target = 1.0 + SPRING_STRETCH * speed * (1.0 - self.squash)
        - SPRING_COMPRESS * self.squash
    target = vmath.clamp(target, 0.45, 2.2)
    local steps = math.max(1, math.ceil(dt / (1.0 / 120.0)))
    local h = dt / steps
    for _ = 1, steps do
        local accel = (target - self.slinky_scale) * SPRING_K - self.slinky_vel * SPRING_C
        self.slinky_vel = self.slinky_vel + accel * h
        self.slinky_scale = vmath.clamp(self.slinky_scale + self.slinky_vel * h, 0.4, 2.4)
    end

    -- выгиб дугой только при отскоке от перегородки; перекат задаёт place_rings
    if self.bounce_t > 0.0 then
        local bp = 1.0 - self.bounce_t / self.bounce_duration
        self.slinky_bend = self.slinky_bend_dir * SLINKY_BEND * math.sin(math.pi * bp)
    else
        self.slinky_bend = 0.0
    end

    -- амплитуда покачивания: в покое затухает от толчка после приземления до
    -- слабой; вне покоя гаснет полностью (волна только для состояния покоя)
    local wave_target = self.resting and WAVE_MIN or 0.0
    self.wave_amp = self.wave_amp
        + (wave_target - self.wave_amp) * math.min(1.0, dt * WAVE_DECAY)

    place_rings(self)
end

-- деформацию Slinky ведёт update (пружина и кольца), обычное сплющивание не нужно
function M.apply_squash(self)
end

function M.hop_height(self)
    return SLINKY_STEP_LIFT
end

-- приземление без команды: Slinky не отскакивает, а встаёт и стоит (покачиваясь).
-- Здесь же запускаются удар (сжатие снизу вверх) и затухающее покачивание
function M.settle(self)
    go.set("#collision_object", "linear_velocity", vmath.vector3(0.0, 0.0, 0.0))
    self.resting = true
    self.impact_t = self.time
    self.wave_amp = WAVE_KICK
end

function M.allow_from_rest(self)
    return self.resting
end

function M.ignore_contacts(self)
    return self.resting
end

function M.on_action(self, direction, duration)
    self.resting = false
    if direction then
        self.slinky_bend_dir = direction
    end
end

return M
