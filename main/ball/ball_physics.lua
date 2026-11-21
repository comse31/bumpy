-- Доступ к физическому телу мяча (#collision_object).
--
-- В ball.script десятки раз повторялись строковые обращения
-- go.get/go.set/msg.post("#collision_object", ...) — модуль собирает их в одном
-- месте, чтобы компонент-коллизия упоминался в коде ровно один раз: при смене
-- id компонента правится только эта таблица.
--
-- Модуль-лист: других модулей не требует, состояние не хранит.
local M = {}

local COMPONENT = "#collision_object"

-- линейная скорость мяча (vmath.vector3)
function M.velocity()
    return go.get(COMPONENT, "linear_velocity")
end

-- вертикальная составляющая скорости
function M.vy()
    return go.get(COMPONENT, "linear_velocity").y
end

-- задать скорость целиком
function M.set_velocity(vx, vy, vz)
    go.set(COMPONENT, "linear_velocity", vmath.vector3(vx or 0.0, vy or 0.0, vz or 0.0))
end

-- только вертикальный импульс (горизонталь гасится)
function M.set_vertical(vy)
    go.set(COMPONENT, "linear_velocity", vmath.vector3(0.0, vy, 0.0))
end

-- погасить скорость полностью
function M.stop()
    go.set(COMPONENT, "linear_velocity", vmath.vector3(0.0, 0.0, 0.0))
end

-- оставить только вертикальную составляющую текущей скорости
function M.keep_vertical(vy)
    go.set(COMPONENT, "linear_velocity", vmath.vector3(0.0, vy, 0.0))
end

-- включить/выключить физику мяча (на плашке READY и после смерти)
function M.enable()
    msg.post(COMPONENT, "enable")
end

function M.disable()
    msg.post(COMPONENT, "disable")
end

-- движется ли мяч вверх
function M.moving_up()
    return go.get(COMPONENT, "linear_velocity").y > 0.0
end

-- движется ли мяч вниз (вертикальная скорость отрицательна)
function M.moving_down()
    return go.get(COMPONENT, "linear_velocity").y < 0.0
end

return M
