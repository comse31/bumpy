-- Реестр экземпляров текущего уровня.
--
-- Уровень больше не лежит в main.collection статически: level.script генерирует
-- его из метаданных (main/levels.json) через factory-компоненты и складывает id
-- созданных объектов в этот модуль. ball.script читает реестр вместо жёстко
-- прописанных URL вида /p1_1, /w2_3, /g1_2.
--
-- Индексация совпадает с ball.script: row 0 — НИЖНИЙ ряд экрана (row = 0..5).
-- В метаданных (levels.json) строки идут сверху вниз, поэтому level.script
-- переворачивает их при регистрации.
--
-- Модуль общий для всех скриптов (в game.project включён shared_state = 1),
-- поэтому таблица, заполненная level.script, видна ball.script.
local M = {}

M.index = 1       -- номер текущего уровня (1..level_count)
M.start_cell = 0  -- стартовая ячейка шара (индекс в метаданных, 0..35)
M.exit_cell = 0   -- финишная ячейка/выход (индекс в метаданных, 0..35)
M.timer = 0       -- сколько собираемых объектов открывают выход
M.exit_id = nil   -- id объекта выхода текущего уровня | nil

M.platforms = {}  -- platforms[row][col] = id | nil
M.walls = {}      -- walls[row][b] = id | nil (b = 1..cols-1, граница между b-1 и b)
M.goodies = {}    -- goodies[row][col] = id | nil

function M.reset()
    M.platforms = {}
    M.walls = {}
    M.goodies = {}
end

function M.platform_id(row, col)
    local r = M.platforms[row]
    return r and r[col] or nil
end

function M.wall_id(row, b)
    local r = M.walls[row]
    return r and r[b] or nil
end

function M.goodie_id(row, col)
    local r = M.goodies[row]
    return r and r[col] or nil
end

function M.has_platform(row, col)
    return M.platform_id(row, col) ~= nil
end

-- URL компонента по id объекта (например M.component(id, "sticky")).
-- Нужен потому, что у созданных фабрикой объектов нельзя собрать строковый URL
-- "/p1_1#sticky" — доступ идёт по возвращённому factory.create() хэшу id.
function M.component(id, comp)
    return msg.url(nil, id, comp)
end

return M
