-- Сохранение прогресса игры между сессиями.
--
-- Для HTML5-сборки это ключевой сценарий: при закрытии вкладки/браузера игра
-- должна возобновляться с текущего уровня, сохраняя число жизней и содержимое
-- кармана. Модуль опирается на sys.save/sys.load.
--
-- ВАЖНО (HTML5): путь сохранения нужно получать через sys.get_save_file().
-- Только он даёт путь внутри постоянного каталога приложения, который на HTML5
-- монтируется движком как IndexedDB (IDBFS, каталог /data) с автосохранением.
-- «Голое» имя файла (например "bumpy_save") на HTML5 попадает в корень MEMFS
-- вне точки монтирования IDBFS — файл живёт в памяти и теряется при
-- перезагрузке вкладки (игра начиналась с 1-го уровня). На настольных
-- платформах sys.get_save_file() возвращает путь в каталоге пользователя
-- (например, %APPDATA%\bumpy\bumpy_save).
--
-- Хранится только то, что даёт право на продолжение:
--   level     — номер текущего уровня (1..level_count);
--   max_level — максимально достигнутый уровень (только растёт, служит для
--               статистики в стартовом меню и не сбрасывается при GAME OVER);
--   lives     — оставшиеся жизни (0 = игра окончена, восстановление запрещено);
--   drops, keys, hammers — содержимое кармана (капли/ключи/молотки).
--
-- Модуль общий для всех скриптов (в game.project включён shared_state = 1),
-- поэтому одна и та же таблица доступна и level.script, и ball.script.
local test_mode = require("main.test_mode")
-- дублирование сохранения в серверную БД (backend, SQLite). Локальный файл
-- остаётся основным: без сети игра работает как раньше
local remote_db = require("main.remote_db")
-- имя и счётчик визитов игрока: уходят на сервер вместе с прогрессом
local profile = require("main.player_profile")

local M = {}

-- id приложения и имя файла для sys.get_save_file
local APP_ID = "bumpy"
local FILE_NAME = "bumpy_save"
-- версия формата: при несовпадении сохранение игнорируется (сброс к новой игре)
local VERSION = 1

-- путь к файлу сохранения в постоянном каталоге приложения.
-- sys.get_save_file может бросить ошибку, если каталог недоступен, поэтому
-- оборачиваем в pcall и кэшируем результат (путь в течение сессии не меняется)
local save_path = nil
local function path()
    if save_path then
        return save_path
    end
    local ok, p = pcall(sys.get_save_file, APP_ID, FILE_NAME)
    if ok and p then
        save_path = p
    end
    return save_path
end

-- прочитать сохранение. Возвращает таблицу или nil, если сохранения нет,
-- формат устарел либо данные повреждены. sys.load может бросить ошибку
-- (например, при первом запуске), поэтому оборачиваем в pcall.
--
-- В тестовом режиме (bumpy.test_level = 1) сохранение не читается: тестовый
-- уровень всегда начинается с начала, а прогресс реальной игры не подмешивается
function M.load()
    if test_mode.is_enabled() then
        return nil
    end
    local p = path()
    if not p then
        return nil
    end
    local ok, data = pcall(sys.load, p)
    if not ok or type(data) ~= "table" then
        return nil
    end
    if data.version ~= VERSION then
        return nil
    end
    return data
end

-- записать прогресс. Поля: level, max_level, lives, drops, keys, hammers.
-- Неполные/битые значения приводим к безопасным умолчаниям.
--
-- max_level только растёт: перед записью сравниваем с уже сохранённым
-- значением, чтобы GAME OVER или новая игра не уменьшили рекорд.
--
-- ВАЖНО (HTML5): пишем по пути из sys.get_save_file() — только он указывает
-- внутрь каталога, смонтированного на IndexedDB (IDBFS, /data). Движок
-- монтирует этот каталог с autoPersist: данные файла сбрасываются в IndexedDB
-- при закрытии файлового дескриптора (close), т.е. сразу после sys.save.
-- Отдельной функции синхронизации в API нет (sys.sync_fs не существует).
--
-- В тестовом режиме (bumpy.test_level = 1) запись не выполняется: прогон
-- тестового уровня не должен затирать сохранение реальной игры
function M.store(data)
    if type(data) ~= "table" then
        return
    end
    if test_mode.is_enabled() then
        return
    end
    local p = path()
    if not p then
        return
    end
    local level = math.max(1, tonumber(data.level) or 1)
    local max_level = math.max(1, tonumber(data.max_level) or level)
    -- рекорд только растёт: сравниваем с уже сохранённым максимумом и с
    -- текущим уровнем (если он больше записанного)
    local prev = M.load()
    local prev_max = prev and tonumber(prev.max_level) or 0
    max_level = math.max(max_level, prev_max or 0, level)

    local record = {
        version = VERSION,
        level = level,
        max_level = max_level,
        lives = data.lives or 0,
        drops = data.drops or 0,
        keys = data.keys or 0,
        hammers = data.hammers or 0,
    }
    -- sys.save закрывает файл, что запускает автосохранение IDBFS в IndexedDB
    pcall(sys.save, p, record)

    -- Дублирование того же снимка в серверную БД. Отправка асинхронная и не
    -- влияет на локальное сохранение: без сети или при недоступном backend
    -- игра продолжает работать с файлом. Имя/визиты берём из уже
    -- инициализированного профиля (peek без побочных эффектов): если профиль
    -- ещё не читался, поля останутся пустыми — их не затрёт, серверное
    -- слияние оставит прежние значения.
    local name, visits = profile.peek()
    remote_db.sync({
        name = name,
        visits = visits,
        level = level,
        max_level = max_level,
        lives = record.lives,
        drops = record.drops,
        keys = record.keys,
        hammers = record.hammers,
    })
end

-- Подгрузить статусы из БД после успешного входа по паролю.
--
-- Требование: если игрок уже есть в системе и пароль проверен, все текущие
-- статусы (уровень, жизни, карман, рекорд) берутся из БД — на новом устройстве
-- прогресс продолжается с того места, где игрок остановился.
--
-- Слияние осторожное, чтобы не потерять данные:
--   * рекорд (max_level) только растёт — локальный рекорд не уменьшается,
--     если игра шла без сети;
--   * если серверная запись «пустая» (уровень 1, рекорд 1, жизней нет — так
--     выглядит запись, созданная только именем), локальный прогресс остаётся:
--     затирать им реальную игру нельзя;
--   * иначе состояние аккаунта (уровень/жизни/карман) берётся с сервера.
--
-- player — профиль из ответа /api/auth/login (может быть nil).
-- Возвращает true, если локальное сохранение обновлено.
function M.import(player)
    if type(player) ~= "table" then
        return false
    end
    if test_mode.is_enabled() then
        return false
    end
    local server_level = math.max(1, tonumber(player.level) or 1)
    local server_max = math.max(1, tonumber(player.max_level) or server_level)
    local server_lives = tonumber(player.lives) or 0

    local prev = M.load()
    local prev_max = prev and tonumber(prev.max_level) or 0
    local prev_level = prev and math.max(1, tonumber(prev.level) or 1) or 1
    local prev_lives = prev and tonumber(prev.lives) or 0

    -- серверная запись пуста: игрок только завёл имя (пароль), прогресса там
    -- ещё нет — сохраняем локальную игру как есть
    local server_empty = server_level <= 1 and server_max <= 1 and server_lives <= 0
    if server_empty then
        M.store({
            level = prev_level,
            max_level = math.max(prev_max, server_max),
            lives = prev_lives,
            drops = prev and prev.drops or 0,
            keys = prev and prev.keys or 0,
            hammers = prev and prev.hammers or 0,
        })
        return false
    end

    M.store({
        level = server_level,
        max_level = math.max(server_max, prev_max or 0),
        lives = server_lives,
        drops = tonumber(player.drops) or 0,
        keys = tonumber(player.keys) or 0,
        hammers = tonumber(player.hammers) or 0,
    })
    return true
end

-- обнулить сохранение: используется, когда продолжать нельзя (жизни кончились).
-- Записываем lives = 0 — при следующем запуске это означает «новая игра».
-- Рекорд (max_level) при этом сохраняется: его подставляет M.store.
function M.clear()
    M.store({ level = 1, lives = 0 })
end

-- Прогресс для стартового меню: текущий уровень и максимально достигнутый.
-- Если сохранения нет или жизни кончились (lives = 0), текущим считается
-- 1-й уровень; рекорд берётся из сохранения и не сбрасывается.
function M.progress()
    local data = M.load()
    local level = 1
    local max_level = 1
    if data then
        max_level = math.max(1, tonumber(data.max_level) or 1, tonumber(data.level) or 1)
        if (tonumber(data.lives) or 0) > 0 then
            level = math.max(1, tonumber(data.level) or 1)
        end
    end
    return level, max_level
end

return M
