-- Дублирование сохранений игры в серверную БД (backend, SQLite).
--
-- Локальное сохранение (main/save.lua, main/player_profile.lua) остаётся
-- основным: игра работает и без сети. Этот модуль отправляет те же данные на
-- сервер, чтобы прогресс игрока и его имя не терялись при очистке браузера и
-- были видны в лидерборде.
--
-- Что уходит на сервер (то же, что лежит в локальных файлах):
--   name, visits        — main/player_profile.lua;
--   level, max_level,   — main/save.lua (плюс lives/drops/keys/hammers).
--   lives, drops,
--   keys, hammers
--
-- Адрес API:
--   * bumpy.api_url в game.project — если задан (например, для отдельного
--     хоста API). Пустое значение — работа через тот же origin, что и игра:
--     в HTML5 берётся window.location.origin, и запрос идёт на /api/... —
--     этот путь проксирует nginx (docker/nginx.conf), поэтому CORS не нужен;
--   * вне HTML5 (редактор, нативные сборки) — http://127.0.0.1:8000.
--
-- Модуль общий (game.project: shared_state = 1), поэтому один и тот же кэш
-- снимка и player_id доступны всем скриптам.

local M = {}

-- имя файла для player_id (в постоянном каталоге приложения)
local APP_ID = "bumpy"
local ID_FILE = "bumpy_player_id"
-- версия формата файла player_id
local ID_VERSION = 1

-- Идентификатор игрока: генерируется один раз на устройство/браузер и
-- переиспользуется, поэтому записи в БД не «размазываются» по новым строкам
-- при каждом запуске.
local player_id = nil

-- Последний отправленный/ожидающий снимок и служебное состояние очереди.
-- Отправка асинхронная: снимок перезаписывается, лишние запросы не плодятся.
local pending = nil       -- снимок, который нужно отправить
local in_flight = false   -- запрос уже выполняется
local last_send = 0       -- время последней отправки (os.time)
local last_payload = nil  -- что именно отправлялось (для отсева повторов)

-- Минимальный интервал между запросами (секунды). Смерть/старт уровня могут
-- сменить состояние несколько раз подряд — лишние запросы не нужны.
local MIN_INTERVAL = 1.0

-- предупреждения печатаем один раз, чтобы не засорять консоль
local warned_http = false

local function now_seconds()
    return os.time()
end

-- --- сохранение player_id ----------------------------------------------------

local id_path_cached = nil
local function id_path()
    if id_path_cached ~= nil then
        return id_path_cached or nil
    end
    local ok, p = pcall(sys.get_save_file, APP_ID, ID_FILE)
    if ok and p then
        id_path_cached = p
        return p
    end
    id_path_cached = false
    return nil
end

-- случайный идентификатор: 8..64 символа [A-Za-z0-9_-], как требует API.
-- Префикс «p» + время запуска + случайный хвост: id различается между
-- устройствами и не повторяется между запусками, а сохраняется один раз.
local ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
local function random_token(length)
    local out = {}
    for i = 1, length do
        local r = math.random(1, #ALPHABET)
        out[i] = ALPHABET:sub(r, r)
    end
    return table.concat(out)
end

local function generate_id()
    -- os.time в секундах может совпасть у двух устройств в одну секунду,
    -- поэтому к нему добавляется случайный хвост из 16 символов (~83 бита)
    return string.format("p%d%s", now_seconds(), random_token(16))
end

-- Прочитать player_id из файла или создать и сохранить новый.
local function load_player_id()
    if player_id then
        return player_id
    end
    local p = id_path()
    if p then
        local ok, data = pcall(sys.load, p)
        if ok and type(data) == "table" and data.version == ID_VERSION
            and type(data.player_id) == "string" and #data.player_id >= 8 then
            player_id = data.player_id
            return player_id
        end
    end
    player_id = generate_id()
    if p then
        pcall(sys.save, p, { version = ID_VERSION, player_id = player_id })
    end
    return player_id
end

-- --- адрес API ---------------------------------------------------------------

local base_url_cached = nil

-- Адрес API без завершающего слэша. Порядок: настройка проекта → origin
-- браузера → локальный адрес по умолчанию.
local function base_url()
    if base_url_cached then
        return base_url_cached
    end

    local configured = ""
    pcall(function()
        configured = sys.get_config_string("bumpy.api_url", "") or ""
    end)
    -- значение из game.project приходит строкой; пустая настройка может
    -- вернуться как кавычки ("") или с пробелами — нормализуем, иначе в URL
    -- попадёт мусор вроде /""/api/... и запросы будут падать с 405
    configured = configured:gsub("[%s\"']", "")
    configured = configured:gsub("/+$", "")
    if configured ~= "" then
        base_url_cached = configured
        return base_url_cached
    end

    -- HTML5: тот же origin, что и у игры; nginx проксирует /api на backend.
    if html5 and html5.run then
        local ok, origin = pcall(html5.run, "window.location.origin")
        if ok and type(origin) == "string" and origin:match("^https?://") then
            base_url_cached = origin:gsub("/+$", "")
            return base_url_cached
        end
    end

    -- Редактор/нативные сборки: backend из docker-compose на этой же машине.
    base_url_cached = "http://127.0.0.1:8000"
    return base_url_cached
end

-- --- отправка ----------------------------------------------------------------

local function json_encode(value)
    local ok, encoded = pcall(json.encode, value)
    if ok then
        return encoded
    end
    return nil
end

local function send(snapshot, event)
    if not http or not http.request then
        if not warned_http then
            warned_http = true
            print("remote_db: http.request недоступен, серверная синхронизация отключена")
        end
        return
    end

    local payload = {}
    for k, v in pairs(snapshot) do
        payload[k] = v
    end
    if event then
        payload.event = event
    end

    local body = json_encode(payload)
    if not body then
        return
    end
    if body == last_payload then
        -- ничего не изменилось с прошлой отправки
        return
    end

    local url = string.format("%s/api/players/%s", base_url(), load_player_id())
    local headers = { ["Content-Type"] = "application/json" }
    local api_key = ""
    pcall(function()
        api_key = sys.get_config_string("bumpy.api_key", "") or ""
    end)
    api_key = api_key:gsub("[%s\"']", "")
    if api_key ~= "" then
        headers["X-Api-Key"] = api_key
    end

    in_flight = true
    last_payload = body
    last_send = now_seconds()

    local function callback(_, _, response)
        in_flight = false
        local status = response and response.status or 0
        if status == 200 or status == 201 then
            last_payload = body
        else
            -- сервер недоступен или отверг данные: не считаем снимок
            -- отправленным, чтобы следующее сохранение попробовало снова
            last_payload = nil
            print(string.format("remote_db: отправка не удалась (status %s)", tostring(status)))
        end
        -- если за время запроса состояние изменилось — отправляем актуальное
        if pending then
            local next_snapshot = pending
            pending = nil
            send(next_snapshot, nil)
        end
    end

    local ok = pcall(http.request, url, "PUT", callback, headers, body)
    if not ok then
        in_flight = false
        last_payload = nil
        print("remote_db: http.request бросил ошибку")
    end
end

-- --- публичный интерфейс -----------------------------------------------------

-- Снимок текущего состояния: ровно те поля, что хранятся локально.
-- visits/name подставляет player_profile, остальное — save.
function M.sync(snapshot, event)
    if type(snapshot) ~= "table" then
        return
    end
    snapshot.player_id = load_player_id()
    local sys_info = nil
    pcall(function()
        sys_info = sys.get_sys_info()
    end)
    if sys_info and not snapshot.platform then
        snapshot.platform = sys_info.system_name
    end
    if not snapshot.client_version then
        pcall(function()
            snapshot.client_version = sys.get_config_string("project.version", "1.0.0")
        end)
    end

    -- пока предыдущий запрос в полёте — запоминаем только последний снимок
    if in_flight then
        pending = snapshot
        return
    end

    -- троттлинг: не чаще MIN_INTERVAL секунд (кроме явных событий)
    if not event and (now_seconds() - last_send) < MIN_INTERVAL then
        pending = snapshot
        return
    end

    send(snapshot, event)
end

-- Отправить событие (например, "level" при прохождении уровня) отдельным
-- запросом POST /api/players/{id}/events. Снимок при этом не отправляется,
-- поэтому событие не «раздувает» обычное сохранение.
function M.event(kind, payload)
    if not http or not http.request then
        return
    end
    local body = json_encode({ kind = kind, payload = payload or {} })
    if not body then
        return
    end
    local url = string.format("%s/api/players/%s/events", base_url(), load_player_id())
    local headers = { ["Content-Type"] = "application/json" }
    local api_key = ""
    pcall(function()
        api_key = sys.get_config_string("bumpy.api_key", "") or ""
    end)
    api_key = api_key:gsub("[%s\"']", "")
    if api_key ~= "" then
        headers["X-Api-Key"] = api_key
    end
    -- 202 Accepted при успехе; ошибки не влияют на игру
    pcall(http.request, url, "POST", function() end, headers, body)
end

-- Идентификатор игрока (для отладки и UI).
function M.get_player_id()
    return load_player_id()
end

-- Периодический вызов из update-функции любого скрипта: досылает снимок,
-- отложенный троттлингом. Дёшев: без отложенных данных ничего не делает.
function M.update(dt)
    if pending and not in_flight and (now_seconds() - last_send) >= MIN_INTERVAL then
        local snapshot = pending
        pending = nil
        send(snapshot, nil)
    end
    return dt
end

-- Подменить player_id: используется после входа по имени, когда запись в БД
-- уже существует (например, создана на другом устройстве). Прогресс должен
-- уходить в ту же запись, а не создавать новую.
function M.set_player_id(id)
    if type(id) ~= "string" or id == "" then
        return
    end
    player_id = id
    local p = id_path()
    if p then
        pcall(sys.save, p, { version = ID_VERSION, player_id = player_id })
    end
end

-- Адрес API без завершающего слэша: нужен main/auth.lua, чтобы строить
-- эндпоинты входа и не дублировать разбор настроек.
function M.api_base()
    return base_url()
end

-- API-ключ из game.project (bumpy.api_key) или пустая строка: без кавычек и
-- пробелов, чтобы в заголовок не попал мусор.
function M.api_key()
    local key = ""
    pcall(function()
        key = sys.get_config_string("bumpy.api_key", "") or ""
    end)
    return (key:gsub("[%s\"']", ""))
end

return M
