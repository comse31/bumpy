-- Прогресс игрока: жизни, карман предметов, сохранение между сессиями и
-- переходы между уровнями.
--
-- Здесь собраны все решения «игра продолжается / уровень перезапускается /
-- игра окончена», а также единая точка записи сохранения (persist) вместо трёх
-- копий save.store с одинаковым набором полей.
--
-- Модуль зависит от конфигурации, физики, отладки, реестра уровня и глав
-- (визуал героя) — но не от логики приземления/ввода, поэтому его можно
-- безопасно вызывать из любого слоя.
local C = require("main.ball.ball_config")
local phys = require("main.ball.ball_physics")
local dbg = require("main.ball.ball_debug")
local trap = require("main.ball.ball_trap")
local state = require("main.level.level_state")
local save = require("main.save")
-- режим игры (classic/adventure) и флаг открытого стартового меню
local game_mode = require("main.game_mode")
-- минимальные требования уровня по снаряжению (п. 19 плана)
local requirements = require("main.level.level_requirements")

local M = {}

local START_LIVES = C.START_LIVES
-- «Приключение»: 3 жизни на попытку; снаряжение выдаётся ровно в том объёме,
-- который нужен уровню для прохождения (см. M.adventure_items)
local ADVENTURE_LIVES = 3
-- запасной набор, если для уровня нет данных (файл не сгенерирован или уровень
-- появился позже): по 5 предметов каждого вида
local ADVENTURE_ITEMS = 5

-- записать прогресс в сохранение. Всегда сохраняется снимок кармана на начало
-- уровня (start_*), к которому карман откатывается при потере жизни: так
-- переоткрытие браузера вернёт ровно то же состояние, что и перезапуск уровня
--
-- В «Приключении» сохранение не пишется: этот режим — отдельная попытка на
-- выбранном уровне со своим набором, он не должен затирать прогресс
-- классической игры (уровень, жизни и карман)
function M.persist(self, level)
    if game_mode.is_adventure() then
        return
    end
    save.store({
        level = level or state.index,
        lives = self.lives,
        drops = self.start_pocket,
        keys = self.start_keys,
        hammers = self.start_hammers,
    })
end

-- снимок кармана на старте уровня: предметы сохраняются между уровнями, но при
-- смерти откатываются к этому состоянию
function M.snapshot_pocket(self)
    self.start_pocket = self.pocket
    self.start_keys = self.key_pocket
    self.start_hammers = self.hammer_pocket
    dbg.log("POCKET snapshot level %d: drops=%d keys=%d hammers=%d",
        state.index, self.start_pocket, self.start_keys, self.start_hammers)
end

-- откатить карман к снимку начала уровня и обновить HUD-карман
function M.rollback_pocket(self)
    self.pocket = self.start_pocket
    self.key_pocket = self.start_keys
    self.hammer_pocket = self.start_hammers
    msg.post("/pocket", "set_items", {
        drops = self.pocket,
        keys = self.key_pocket,
        hammers = self.hammer_pocket,
    })
    dbg.log("POCKET rollback to level start: drops=%d keys=%d hammers=%d (reload level %d)",
        self.start_pocket, self.start_keys, self.start_hammers, state.index)
end

-- потеря жизни: остановить мяч, скрыть визуал героя, вычесть жизнь и обновить
-- HUD-карман. Если жизни остались — перезапустить текущий уровень (level.script
-- пришлёт level_start, и мяч вернётся в стартовую ячейку).
--
-- В «Приключении» (game_mode.ADVENTURE) жизни тоже тратятся (их 3 на попытку),
-- но по их исчерпании GAME OVER не показывается: игра просто возвращается в
-- стартовое меню, где можно выбрать уровень и начать попытку заново. В
-- классическом режиме при 0 жизней — GAME OVER и меню.
function M.lose_life(self, cause)
    if self.game_over then
        return
    end
    self.game_over = true
    -- полёт прерван смертью: управление должно снова отправлять тап по
    -- отпусканию, а не мгновенно при нажатии (см. report_motion)
    if self.reported_high then
        self.reported_high = false
        msg.post("/controls", "motion_state", { high = false })
    end
    -- ловушка (если была): скрыть плашку и снять отсчёт
    if self.trap_active then
        trap.reset(self)
    end
    phys.stop()
    -- мяч умер прямо сейчас: выключаем коллизию, иначе до пересборки уровня
    -- (1-2 кадра) продолжают приходить contact_point_response, и приземление
    -- на горящую платформу тратит каплю УЖЕ ПОСЛЕ отката кармана. На
    -- перезапущенном уровне игрок видел бы не тот набор, с которым пришёл
    phys.disable()
    -- скрыть визуал активного героя (у спрайта нет свойства visible,
    -- скрываем сообщением disable)
    self.hero.deactivate(self)
    self.lives = math.max(0, self.lives - 1)
    msg.post("/pocket", "set_lives", { count = self.lives })
    dbg.always("LIFE LOST (%s): %d left, pocket now=(%d, %d, %d), level %d",
        cause or "?", self.lives, self.pocket, self.key_pocket, self.hammer_pocket, state.index)
    if self.lives > 0 then
        -- предметы в кармане откатываются к состоянию на старте текущего уровня:
        -- собранное на этом уровне не сохраняется, но накопленное между
        -- уровнями остаётся (см. снимок в level_start)
        M.rollback_pocket(self)
        -- обновить сохранение: если браузер закрыть сразу после смерти, при
        -- переоткрытии должно восстановиться уже уменьшенное число жизней
        -- (карман — снимок на начало уровня, к которому мы только что откатились)
        M.persist(self)
        msg.post("/level", "reload_level", { level = state.index })
        return
    end
    -- жизни кончились
    if game_mode.is_adventure() then
        -- «Приключение»: попытка окончена, но GAME OVER не показываем —
        -- возвращаемся в стартовое меню, прогресс классики не трогаем
        msg.post("/game_over", "hide")
        game_mode.set_menu_open(true)
        msg.post("/menu", "open")
        dbg.always("ADVENTURE: no lives left (%s), back to menu", cause or "?")
        return
    end
    -- классический режим: показать плашку GAME OVER и вернуть игрока в
    -- стартовое меню. Обнуляем сохранение (lives = 0), иначе после переоткрытия
    -- браузера игрок вернулся бы в проигранную игру
    save.clear()
    msg.post("/game_over", "show")
    -- меню открывается поверх плашки GAME OVER: игрок выбирает режим заново
    game_mode.set_menu_open(true)
    msg.post("/menu", "open")
    dbg.always("GAME OVER (%s): no lives left", cause or "?")
end

-- Проверка снаряжения на старте уровня (п. 19 плана): если для прохождения
-- уровня заведомо не хватает капель/ключей/молотков, уровень не начинается —
-- игроку показывается плашка «NOT ENOUGH THINGS / PRESS ANY KEY», а любое
-- нажатие возвращает в главное меню. Это проигрыш вне зависимости от числа
-- жизней (tz.txt, «Жизни»), но без GAME OVER: в «Приключении» игрок может
-- сразу выбрать другой уровень, в классике — начать заново.
--
-- Требования берутся из main/level_requirements.json (генерируется
-- tools/gen_level_requirements.py по решателю уровней): это минимальный
-- набор, который нужен на СТАРТЕ, с учётом того, что часть предметов можно
-- подобрать по пути.
--
-- Возвращает true, если снаряжения хватает (игра продолжается), и false,
-- если показана плашка и уровень не начался.
function M.require_gear(self)
    -- пока открыто стартовое меню, уровень загружен «за кадром»: проверять
    -- нечего — игрок ещё не выбрал режим и не начинал игру. Проверка
    -- выполнится на level_start, пришедшем после start_game (меню закрыто).
    if game_mode.is_menu_open() then
        return true
    end
    local ok, lack = requirements.check(state.index,
        self.pocket, self.key_pocket, self.hammer_pocket)
    if ok then
        return true
    end
    local missing = requirements.describe(lack)
    dbg.always("NOT ENOUGH THINGS: level %d needs (%s); "
        .. "have drops=%d keys=%d hammers=%d",
        state.index, missing, self.pocket, self.key_pocket, self.hammer_pocket)
    -- мяч не играет: остановить физику и скрыть визуал героя.
    -- ready_wait снимаем: иначе первое нажатие клавиши «запустило» бы уровень
    -- (см. on_input -> ready_wait) уже после показа плашки
    self.game_over = true
    self.ready_wait = false
    -- взводим флаг «ждём нажатия для выхода в меню»: его обрабатывает on_input
    self.gear_blocked = true
    if self.reported_high then
        self.reported_high = false
        msg.post("/controls", "motion_state", { high = false })
    end
    if self.trap_active then
        trap.reset(self)
    end
    phys.stop()
    phys.disable()
    self.hero.deactivate(self)
    -- READY не показываем: уровень даже не начинается
    msg.post("/ready", "hide")
    msg.post("/game_over", "hide")
    -- плашка с причиной; конкретика («2 keys, 1 hammer») уходит в detail,
    -- если её нет — строка скрыта
    msg.post("/no_gear", "show", { detail = missing })
    return false
end

-- Вернуться в главное меню после плашки «NOT ENOUGH THINGS». Вызывается из
-- on_input по любому нажатию, пока self.gear_blocked. Плашка скрывается,
-- прогресс классической игры обнуляется (уровень заведомо непроходим с
-- текущим карманом), затем открывается меню — оно снова даст выбрать режим.
function M.gear_back_to_menu(self)
    if not self.gear_blocked then
        return
    end
    self.gear_blocked = false
    msg.post("/no_gear", "hide")
    if not game_mode.is_adventure() then
        -- классика: обнулить сохранение, иначе после переоткрытия браузера
        -- игрок вернулся бы в заведомо проигранный уровень
        save.clear()
    end
    game_mode.set_menu_open(true)
    msg.post("/menu", "open")
    dbg.always("NOT ENOUGH THINGS: back to menu")
end

-- Запуск игры из стартового меню. Режим (classic/adventure) уже выставлен
-- меню (game_mode.set_mode) либо передаётся здесь.
--
-- Классическая игра продолжает сохранённый прогресс (уровень, жизни, карман),
-- если в сохранении остались жизни; после GAME OVER сохранение обнулено
-- (lives = 0), поэтому игра начнётся с 1-го уровня с полным запасом жизней.
-- «Приключение» использует тот же прогресс по уровню и карману, но жизни
-- игнорируются: они всегда полные и в режиме не тратятся.
function M.start_game(self, chosen)
    local new_mode = game_mode.set_mode(chosen)
    local data = save.load()
    local resumable = data and (data.lives or 0) > 0
    local level = 1
    if game_mode.is_adventure() then
        -- «Приключение»: выбранный в меню уровень и 3 жизни на попытку.
        -- Снаряжение выдаётся ровно в минимально требуемом объёме (п. 19):
        -- набор из main/level_requirements.json. Сохранение классической игры
        -- (уровень, карман, жизни) не подмешивается.
        level = game_mode.get_adventure_level()
        self.lives = ADVENTURE_LIVES
        local need_drops, need_keys, need_hammers = requirements.required(level)
        if need_drops == nil then
            -- данных о требованиях нет — запасной набор по 5 предметов
            self.pocket = ADVENTURE_ITEMS
            self.key_pocket = ADVENTURE_ITEMS
            self.hammer_pocket = ADVENTURE_ITEMS
        else
            self.pocket = need_drops
            self.key_pocket = need_keys
            self.hammer_pocket = need_hammers
        end
    elseif resumable then
        level = data.level or 1
        self.lives = data.lives
        self.pocket = data.drops or 0
        self.key_pocket = data.keys or 0
        self.hammer_pocket = data.hammers or 0
    else
        self.lives = START_LIVES
        self.pocket = 0
        self.key_pocket = 0
        self.hammer_pocket = 0
    end
    self.start_pocket = self.pocket
    self.start_keys = self.key_pocket
    self.start_hammers = self.hammer_pocket
    self.collected = {}
    self.restart_pending = false
    self.game_over = false
    self.level_complete = false
    msg.post("/pocket", "set_lives", { count = self.lives })
    msg.post("/pocket", "set_items", {
        drops = self.pocket,
        keys = self.key_pocket,
        hammers = self.hammer_pocket,
    })
    msg.post("/game_over", "hide")
    dbg.always("START GAME: mode %s, level %d, lives=%d", tostring(new_mode), level, self.lives)
    -- сохранение под режим: в «Приключении» жизни всегда полные, иначе
    -- переоткрытие браузера вернуло бы уменьшенный счётчик
    M.persist(self, level)
    msg.post("/level", "reload_level", { level = level })
end

-- восстановление прогресса после закрытия браузера: если есть сохранение с
-- нерастраченными жизнями, продолжаем с сохранёнными жизнями и карманом.
-- lives = 0 означает, что жизни кончились — начинаем новую игру с нуля.
-- Восстановление относится только к классическому режиму: «Приключение» —
-- отдельная попытка и в сохранении не участвует
function M.resume(self)
    if game_mode.is_adventure() then
        return false
    end
    local data = save.load()
    if not data or (data.lives or 0) <= 0 then
        return false
    end
    self.lives = data.lives
    self.pocket = data.drops or 0
    self.key_pocket = data.keys or 0
    self.hammer_pocket = data.hammers or 0
    -- восстановленный карман — это ровно тот набор, с которым игрок попал
    -- на сохранённый уровень: сразу фиксируем его как снимок, чтобы потеря
    -- жизни откатывала карман к нему, даже если level_start придёт раньше
    -- (или не придёт вовсе при ошибке загрузки уровня)
    self.start_pocket = self.pocket
    self.start_keys = self.key_pocket
    self.start_hammers = self.hammer_pocket
    msg.post("/pocket", "set_lives", { count = self.lives })
    msg.post("/pocket", "set_items", {
        drops = self.pocket,
        keys = self.key_pocket,
        hammers = self.hammer_pocket,
    })
    dbg.always("RESUME: lives=%d pocket=(%d, %d, %d) level=%d",
        self.lives, self.pocket, self.key_pocket, self.hammer_pocket, data.level or 1)
    return true
end

return M
