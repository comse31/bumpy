-- Запросы к реестру уровня (main/level/level_state.lua).
--
-- Уровень генерируется level.script, поэтому вместо жёстких URL "/p1_1"
-- объекты берутся из общего реестра. Модуль инкапсулирует все pcall(go.get)
-- проверки свойств платформ: у разных прототипов (обычная, липкая, шипы,
-- горящая, расходуемая) набор компонентов разный, поэтому отсутствие компонента
-- не должно ломать игру.
--
-- Модуль-лист по зависимостям: читает только реестр и конфигурацию сетки,
-- состояние мяча не меняет.
local state = require("main.level.level_state")
local dbg = require("main.ball.ball_debug")
local grid = require("main.ball.ball_grid")
local C = require("main.ball.ball_config")

local M = {}

local COLS = C.COLS

-- свойства платформ: имя настройки -> компонент скрипта платформы.
-- Компоненты есть только у соответствующих прототипов, поэтому чтение идёт
-- через pcall: у обычной платформы нет ни #sticky, ни #spike, ни #shrink
local FLAGS = {
    sticky = { comp = "sticky", prop = "sticky" },
    spike = { comp = "spike", prop = "spike" },
    burning = { comp = "burning", prop = "burning" },
    gone = { comp = "shrink", prop = "gone" },
}

-- id платформы в ячейке (row/col — индексы с нуля, row 0 — нижний ряд)
function M.platform_id(row, col)
    return state.platform_id(row, col)
end

-- id goodies (собираемого объекта) в ячейке
function M.goodie_id(row, col)
    return state.goodie_id(row, col)
end

-- id перегородки на границе b (между колонками b-1 и b)
function M.wall_id(row, b)
    return state.wall_id(row, b)
end

-- обобщённая проверка свойства платформы (sticky/spike/burning/gone).
-- Возвращает false, если платформы нет, компонента нет или свойство == 0
function M.platform_flag(row, col, flag)
    local def = FLAGS[flag]
    if not def then
        return false
    end
    local id = state.platform_id(row, col)
    if not id then
        return false
    end
    local ok, value = pcall(go.get, state.component(id, def.comp), def.prop)
    return ok and value and value > 0 or false
end

-- направление наклона платформы: 1 = вправо, -1 = влево, 0 = плоская.
-- Определяется по повороту объекта (компонент slope поворачивает всю платформу):
-- отрицательный угол вокруг Z опускает правый конец (наклон вправо),
-- положительный — поднимает его (наклон влево)
function M.slope_direction(row, col)
    local id = state.platform_id(row, col)
    if not id then
        return 0
    end
    local rot = go.get(id, "rotation")
    if not rot or math.abs(rot.z) < 0.01 then
        return 0
    end
    return rot.z > 0 and -1 or 1
end

-- достиг ли мяч финишной ячейки уровня (выхода)
function M.is_exit_cell(row, col)
    local er, ec = grid.from_cell_index(state.exit_cell)
    return row == er and col == ec
end

-- открыть выход уровня: вызывается, когда собрано timer объектов.
-- Табличку включает и снимает платформу в финишной ячейке level.script
-- (сообщение "exit_open"), чтобы появление выхода не зависело от порядка
-- инициализации и работало и для уровней без собираемых объектов
function M.open_exit(self)
    if self.exit_open then
        return
    end
    self.exit_open = true
    msg.post("/level", "exit_open")
    dbg.log("EXIT open: cell=" .. tostring(state.exit_cell))
end

-- прошла ли перегородка разрушение (компонент #destructible есть только у
-- разрушаемых; у стеклянной border его нет — она неразрушаема)
function M.is_wall_destroyed(row, b)
    local id = state.wall_id(row, b)
    if not id then
        return false
    end
    local ok, destroyed = pcall(go.get, state.component(id, "destructible"), "destroyed")
    return ok and destroyed and destroyed > 0
end

-- есть ли на границе справа от колонки col (между col и col+1) препятствие
function M.has_wall_right(row, col)
    return state.wall_id(row, col + 1) ~= nil and not M.is_wall_destroyed(row, col + 1)
end

-- есть ли на границе слева от колонки col (между col-1 и col) препятствие
function M.has_wall_left(row, col)
    return state.wall_id(row, col) ~= nil and not M.is_wall_destroyed(row, col)
end

-- есть ли перегородка в направлении dir (±1) от колонки col
function M.wall_blocking(row, col, dir)
    if dir > 0 then
        return M.has_wall_right(row, col)
    elseif dir < 0 then
        return M.has_wall_left(row, col)
    end
    return false
end

-- состояние кирпичной стены в ячейке. Блок создаётся фабрикой #platform_block и
-- лежит в реестре платформ, а его состояние хранит компонент #block (у обычных
-- платформ его нет, поэтому go.get оборачиваем в pcall). Возвращает
-- id, число разбитых снизу рядов и признак разрушения; nil, если блока нет
function M.block_state(row, col)
    local id = state.platform_id(row, col)
    if not id then
        return nil
    end
    local comp = state.component(id, "block")
    local ok, broken = pcall(go.get, comp, "broken")
    if not ok then
        return nil
    end
    local _, destroyed = pcall(go.get, comp, "destroyed")
    return id, broken or 0, destroyed or 0
end

-- есть ли целая (не разрушенная) кирпичная стена в ячейке?
function M.has_block(row, col)
    local _, _, destroyed = M.block_state(row, col)
    return destroyed == 0
end

-- число рядов кладки (для расчёта поднятой разбитыми рядами грани)
function M.block_rows(id)
    local ok, rows = pcall(go.get, state.component(id, "block"), "rows")
    return (ok and rows and rows > 0) and rows or 8
end

-- визуальный прогиб платформы: dir = 1 — вниз (отталкивание сверху),
-- dir = -1 — вверх (удар мяча снизу); коллизия не меняется — эффект чисто визуальный
function M.bend_platform(row, col, dir)
    local id = state.platform_id(row, col)
    if id then
        msg.post(id, "bend", { dir = dir or 1 })
    end
end

-- уведомить платформу о приземлении мяча (нужно расходуемым платформам)
function M.land_platform(row, col)
    local id = state.platform_id(row, col)
    if id then
        msg.post(id, "land")
    end
end

-- погасить горящую платформу: платформа становится обычной (burning = 0,
-- текстура default), игра продолжается
function M.extinguish_platform(row, col)
    local id = state.platform_id(row, col)
    if not id then
        return false
    end
    msg.post(id, "extinguish")
    return true
end

return M
