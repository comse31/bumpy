-- Вход по имени и паролю (backend, SQLite).
--
-- Правила (требование):
--   * имя игрока уникально в БД;
--   * при первом запуске устройство получает автоматическое имя от сервера
--     (GET /api/auth/next-name?player_id=...) — свободное и уже закреплённое
--     за записью устройства;
--   * игрок может задать пароль, НЕ меняя автоматическое имя: подтверждение
--     того же имени отправляет пароль на /api/auth/login, и он сохраняется;
--   * если имени в БД нет — игра просит задать пароль и сохраняет его
--     (регистрация имени); запись устройства при этом переименовывается,
--     поэтому прогресс не теряется;
--   * если имя уже есть в БД, игра спрашивает пароль и проверяет его; при
--     неверном пароле имя откатывается к предыдущему;
--   * после успешного входа с сервера приходит профиль, и все текущие статусы
--     (уровень, жизни, карман, рекорд) подгружаются в локальное сохранение;
--   * на устройстве, где игрок уже входил, пароль не спрашивается: он лежит в
--     локальном кэше в постоянном каталоге приложения и отправляется молча.
--
-- Модуль работает поверх main/remote_db.lua (тот же адрес API, тот же ключ) и
-- не блокирует игру: пока ответа нет, вызывающий код получает состояние
-- "pending" и продолжает работать с локальным сохранением.
--
-- Состояния (M.state()):
--   "idle"       — ничего не проверяется;
--   "checking"   — запрос check имени отправлен;
--   "need_pass"  — имя занято (или у имени нет пароля): нужен ввод пароля;
--   "submitting" — пароль отправлен, ждём ответ;
--   "ok"         — вход выполнен;
--   "error"      — сеть/сервер недоступны (игра работает локально).

local remote_db = require("main.remote_db")

local M = {}

local APP_ID = "bumpy"
local CACHE_FILE = "bumpy_auth"
local CACHE_VERSION = 1

-- Состояние и данные последнего запроса.
local state = "idle"
local pending_name = nil     -- имя, для которого запрошен/отправлен пароль
local last_previous = nil    -- имя, к которому откатываться при неверном пароле
local last_error = nil       -- текст ошибки для UI
local last_player_id = nil   -- player_id записи в БД (имя может принадлежать
                             -- записи, созданной на другом устройстве)

-- Токен актуального запроса. HTTP-ответы приходят асинхронно и могут
-- обгонять друг друга: поздний ответ на УСТАРЕВШИЙ запрос выставлял
-- wrong_password уже после успешного входа, и игрок видел красную подсветку
-- при сохранённом пароле. Каждой новой проверке/входу выдаётся новый токен,
-- ответы со старым токеном игнорируются.
local request_id = 0

local function next_request()
    request_id = request_id + 1
    return request_id
end

-- Кэш пароля на этом устройстве: { name = <последнее имя>, password = <пароль> }.
-- Хранится в постоянном каталоге приложения (HTML5: IndexedDB через sys.save).
local cache = nil

-- --- локальный кэш -----------------------------------------------------------

local function cache_path()
    local ok, p = pcall(sys.get_save_file, APP_ID, CACHE_FILE)
    if ok then
        return p
    end
    return nil
end

local function read_cache()
    if cache then
        return cache
    end
    cache = {}
    local p = cache_path()
    if not p then
        return cache
    end
    local ok, data = pcall(sys.load, p)
    if ok and type(data) == "table" and data.version == CACHE_VERSION then
        cache = {
            name = type(data.name) == "string" and data.name or nil,
            password = type(data.password) == "string" and data.password or nil,
            player_id = type(data.player_id) == "string" and data.player_id or nil,
        }
    end
    return cache
end

local function write_cache()
    local p = cache_path()
    if not p then
        return
    end
    pcall(sys.save, p, {
        version = CACHE_VERSION,
        name = cache.name,
        password = cache.password,
        player_id = cache.player_id,
    })
end

-- --- http ---------------------------------------------------------------------

-- Адрес и заголовки берём из remote_db, чтобы не дублировать настройки
-- (bumpy.api_url / bumpy.api_key читаются в одном месте).
local function endpoint(path)
    return remote_db.api_base() .. path
end

local function headers()
    local result = { ["Content-Type"] = "application/json" }
    local key = remote_db.api_key()
    if key ~= "" then
        result["X-Api-Key"] = key
    end
    return result
end

-- Тело HTTP-ответа. В Defold http.request кладёт его в response.response
-- (поля response.body нет): ошибка в имени поля делала разбор ответа всегда
-- неуспешным, и клиент молча откатывался в локальный режим без пароля.
local function response_body(response)
    if type(response) ~= "table" then
        return nil
    end
    local body = response.response
    if type(body) ~= "string" then
        body = response.body
    end
    return body
end

-- Разобрать тело ответа. Возвращает таблицу или nil.
local function decode(body)
    if type(body) ~= "string" or body == "" then
        return nil
    end
    local ok, parsed = pcall(json.decode, body)
    if not ok or type(parsed) ~= "table" then
        return nil
    end
    return parsed
end

local function post(path, payload, callback)
    if not http or not http.request then
        state = "error"
        last_error = "no_http"
        callback(nil)
        return
    end
    local ok, body = pcall(json.encode, payload)
    if not ok then
        state = "error"
        last_error = "encode"
        callback(nil)
        return
    end
    local called = false
    local function done(_, _, response)
        if called then
            return
        end
        called = true
        callback(response)
    end
    local sent = pcall(http.request, endpoint(path), "POST", done, headers(), body)
    if not sent then
        state = "error"
        last_error = "request"
        done(nil, nil, nil)
    end
end

-- --- публичный интерфейс -----------------------------------------------------

function M.state()
    return state
end

function M.error()
    return last_error
end

-- Имя, для которого сейчас запрашивается пароль (для UI-подсказки).
function M.pending_name()
    return pending_name
end

-- Предыдущее имя: к нему откатываемся, если пароль неверен.
function M.previous_name()
    return last_previous
end

-- player_id записи в БД, если имя принадлежит другому устройству.
function M.player_id()
    return last_player_id
end

-- Пароль, сохранённый на этом устройстве (nil, если игрок ещё не входил).
function M.cached_password()
    local c = read_cache()
    return c.password
end

-- Имя, под которым устройство последний раз успешно входило.
function M.cached_name()
    local c = read_cache()
    return c.name
end

-- Есть ли на устройстве сохранённый вход для имени.
--
-- Нужно, чтобы отличить «игрок уже входил, пароль можно отправить молча» от
-- «первое посещение: пароль ещё не задан». Без этого повторное подтверждение
-- неизменённого авто-имени ничего не делало, и игрок не мог задать пароль.
-- name == nil — проверяется наличие любого сохранённого входа.
function M.has_cached_login(name)
    local c = read_cache()
    if type(c.password) ~= "string" or c.password == "" then
        return false
    end
    if type(c.name) ~= "string" or c.name == "" then
        return false
    end
    if type(name) == "string" and name ~= "" and c.name:lower() ~= name:lower() then
        return false
    end
    return true
end

-- Запомнить успешный вход: пароль и имя остаются только на этом устройстве,
-- поэтому при следующем запуске пароль не спрашивается.
local function remember(name, password, player_id)
    read_cache()
    cache.name = name
    cache.password = password
    cache.player_id = player_id
    write_cache()
end

-- Очистить кэш (используется, если пароль отвергнут сервером).
function M.forget()
    read_cache()
    cache.password = nil
    cache.player_id = nil
    write_cache()
end

-- Очистить кэш, только если он относится к имени name.
--
-- Нужно при неверном пароле к НОВОМУ имени: кэш прежнего (рабочего) входа
-- должен остаться, иначе одно опечатанное имя выбивало бы игрока из аккаунта
-- на этом устройстве. Без имени (name == nil) кэш очищается полностью.
function M.forget_if(name)
    if type(name) ~= "string" or name == "" then
        M.forget()
        return
    end
    local c = read_cache()
    if type(c.name) == "string" and c.name:lower() == name:lower() then
        M.forget()
    end
end

-- Сбросить состояние перед новой попыткой.
--
-- Токен увеличивается: ответы на уже отправленные запросы перестают быть
-- актуальными и не должны менять состояние/рисовать ошибку после сброса
-- (например, после отмены ввода по Esc).
function M.reset()
    next_request()
    state = "idle"
    pending_name = nil
    last_error = nil
end

-- Проверить имя: занято ли, нужен ли пароль.
-- callback(result) — result = { exists=bool, has_password=bool } или nil.
-- previous_name — имя, к которому откатиться при неверном пароле.
function M.check_name(name, previous_name, callback)
    state = "checking"
    pending_name = name
    last_previous = previous_name
    last_error = nil
    local token = next_request()
    post("/api/auth/check", { name = name }, function(response)
        if token ~= request_id then
            -- ответ на устаревший запрос: состояние уже изменилось
            return
        end
        local status = response and response.status or 0
        local parsed = decode(response_body(response))
        if status ~= 200 or not parsed then
            state = "error"
            last_error = "check_failed"
            callback(nil)
            return
        end
        if parsed.exists and parsed.has_password then
            state = "need_pass"
        else
            -- имени нет ИЛИ у него ещё нет пароля: в обоих случаях игрок задаёт
            -- пароль (во втором — закрепляет автоматическое имя за собой)
            state = "need_pass"
        end
        callback(parsed)
    end)
end

-- Отправить имя и пароль. callback(ok, reason, player) —
--   ok = true: пароль принят (вход или регистрация);
--   player — профиль из БД (уровень, жизни, карман) для подгрузки статусов;
--   ok = false, reason = "wrong_password" — имя откатывается к предыдущему.
function M.login(name, password, callback)
    state = "submitting"
    last_error = nil
    local token = next_request()
    post("/api/auth/login", {
        name = name,
        password = password,
        -- идентификатор устройства: сервер поймёт, что вход повторный
        player_id = remote_db.get_player_id(),
    }, function(response)
        if token ~= request_id then
            -- ответ на устаревший запрос: успешный вход уже обработан или
            -- игрок отменил ввод. Поздний wrong_password не должен рисовать
            -- красную подсветку поверх успешного результата.
            return
        end
        local status = response and response.status or 0
        local parsed = decode(response_body(response))
        if status ~= 200 or not parsed then
            state = "error"
            last_error = (parsed and parsed.detail) or "login_failed"
            callback(false, last_error, nil)
            return
        end
        if parsed.ok then
            state = "ok"
            pending_name = nil
            last_player_id = parsed.player_id
            remember(parsed.name or name, password, parsed.player_id)
            -- запись в БД могла быть создана на другом устройстве — сообщаем
            -- remote_db актуальный player_id, чтобы прогресс шёл в ту же запись
            if parsed.player_id then
                remote_db.set_player_id(parsed.player_id)
            end
            callback(true, nil, parsed.player)
            return
        end
        state = "need_pass"
        last_error = parsed.reason or "login_failed"
        callback(false, last_error, nil)
    end)
end

-- Тихий вход по кэшу устройства: пароль уже сохранён после первого входа.
-- callback(ok, player): player — профиль из БД, чтобы подгрузить статусы.
function M.login_cached(callback)
    local c = read_cache()
    if not c.name or not c.password then
        callback(false, nil)
        return
    end
    M.login(c.name, c.password, callback)
end

-- Свободное имя по умолчанию (PlayerN), уникальное в БД.
-- callback(name) — name может быть nil, если сервер недоступен (тогда
-- вызывающий код использует локальное имя).
--
-- Если у устройства есть player_id, сервер сразу ЗАКРЕПЛЯЕТ имя за его
-- записью: иначе два новых устройства могли получить одинаковое «PlayerN»,
-- и второе оставалось без имени.
function M.next_default_name(callback)
    if not http or not http.request then
        callback(nil)
        return
    end
    local called = false
    local function done(_, _, response)
        if called then
            return
        end
        called = true
        local parsed = decode(response_body(response))
        local status = response and response.status or 0
        if status == 200 and parsed and type(parsed.name) == "string" then
            callback(parsed.name)
        else
            callback(nil)
        end
    end
    local pid = remote_db.get_player_id()
    local path = "/api/auth/next-name"
    if type(pid) == "string" and pid ~= "" then
        path = path .. "?player_id=" .. pid
    end
    local ok = pcall(http.request, endpoint(path), "GET", done, headers(), nil)
    if not ok then
        done(nil, nil, nil)
    end
end

return M
