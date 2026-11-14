-- Герой «мячик» — ЭТАЛОН взаимодействия с миром. Сплющивание при ударе,
-- переворот на 180° в сторону прыжка и автоматический отскок при приземлении.
--
-- Вся физика взаимодействия с миром (липкие платформы, автоотскок, приём ввода,
-- высота подскока, длительность шага) живёт в hero_base, поэтому мячик ничего
-- из этого не переопределяет: он задаёт только визуал и то, что его визуал
-- уникален. Остальные герои наследуют тот же контракт и не могут разойтись
-- с мячиком в поведении.
local base = require("main.ball.hero_base")

local M = setmetatable({}, { __index = base })

M.name = "ball"

-- применить сплющивание с учётом текущего self.squash (0..1)
local function apply_squash(self)
    local amount = self.env.squash_amount
    local sx = 1.0 + amount * self.squash
    local sy = 1.0 - amount * self.squash
    go.set(self.ball_visual, "scale", vmath.vector3(sx, sy, 1.0))
end

function M.setup(self, env)
    base.setup(self, env)
    self.ball_visual = go.get_id("ball_visual")
    go.set_parent(self.ball_visual, go.get_id(), true)
end

function M.activate(self)
    msg.post("ball_visual#sprite", "enable")
end

function M.deactivate(self)
    msg.post("ball_visual#sprite", "disable")
end

function M.reset(self)
    self.rot = 0.0
    self.rot_from = 0.0
    self.rot_to = 0.0
    self.rot_t = 0.0
    self.rot_duration = 0.0
    go.set(self.ball_visual, "rotation", vmath.quat())
    apply_squash(self)
end

function M.update(self, dt)
    -- переворот на 180° в сторону прыжка во время смещения между платформами
    if self.rot_t > 0.0 then
        self.rot_t = math.max(0.0, self.rot_t - dt)
        local k = 1.0 - self.rot_t / self.rot_duration
        self.rot = self.rot_from + (self.rot_to - self.rot_from) * k
        go.set(self.ball_visual, "rotation", vmath.quat_rotation_z(self.rot))
    end
    -- сплющивание применяется каждый кадр: self.squash затухает в общем update
    apply_squash(self)
end

function M.apply_squash(self)
    apply_squash(self)
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
