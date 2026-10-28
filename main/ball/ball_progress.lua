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

local M = {}

local START_LIVES = C.START_LIVES

-- записать прогресс в сохранение. Всегда сохраняется снимок кармана на начало
-- уровня (start_*), к которому карман откатывается при потере жизни: так
-- переоткрытие браузера вернёт ровно то же состояние, что и перезапуск уровня
function M.persist(self, level)
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
-- пришлёт level_start, и мяч вернётся в стартовую ячейку); иначе игра окончена.
--
-- В режиме «Приключение» (game_mode.ADVENTURE) жизни не учитываются: смерть
-- мяча не уменьшает их счётчик и никогда не приводит к GAME OVER — уровень
-- просто перезапускается, как при обычной потере жизни.
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
    if game_mode.lives_enabled() then
        self.lives = self.lives - 1
        msg.post("/pocket", "set_lives", { count = math.max(0, self.lives) })
    end
    dbg.always("LIFE LOST (%s): %d left, pocket now=(%d, %d, %d), level %d",
        cause or "?", self.lives, self.pocket, self.key_pocket, self.hammer_pocket, state.index)
    -- в режиме «Приключение» жизни не тратятся: всегда перезапускаем уровень
    if not game_mode.lives_enabled() or self.lives > 0 then
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
    -- жизни кончились: показать плашку GAME OVER и вернуть игрока в стартовое
    -- меню. Обнуляем сохранение (lives = 0), иначе после переоткрытия браузера
    -- игрок вернулся бы в проигранную игру
    save.clear()
    msg.post("/game_over", "show")
    -- меню открывается поверх плашки GAME OVER: игрок выбирает режим заново
    game_mode.set_menu_open(true)
    msg.post("/menu", "open")
    dbg.always("GAME OVER (%s): no lives left", cause or "?")
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
    if resumable then
        level = data.level or 1
        if game_mode.lives_enabled() then
            self.lives = data.lives
        else
            self.lives = START_LIVES
        end
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
-- lives = 0 означает, что жизни кончились — начинаем новую игру с нуля
function M.resume(self)
    local data = save.load()
    if not data or (data.lives or 0) <= 0 then
        return false
    end
    self.lives = game_mode.lives_enabled() and data.lives or START_LIVES
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
