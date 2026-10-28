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
    self.lives = self.lives - 1
    msg.post("/pocket", "set_lives", { count = math.max(0, self.lives) })
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
    -- жизни кончились: показать плашку GAME OVER, уровень не перезапускаем.
    -- Обнуляем сохранение (lives = 0), иначе после переоткрытия браузера
    -- игрок вернулся бы в проигранную игру
    save.clear()
    msg.post("/game_over", "show")
    dbg.always("GAME OVER (%s): no lives left", cause or "?")
end

-- новая игра после GAME OVER: полные жизни и пустой карман, плашка скрывается,
-- уровень 1 пересобирается (level_start снимет game_over и вернёт мяч на старт)
function M.restart_game(self)
    self.lives = START_LIVES
    self.pocket = 0
    self.key_pocket = 0
    self.hammer_pocket = 0
    self.start_pocket = 0
    self.start_keys = 0
    self.start_hammers = 0
    self.collected = {}
    self.restart_pending = true
    msg.post("/pocket", "set_lives", { count = self.lives })
    msg.post("/pocket", "set_items", { drops = 0, keys = 0, hammers = 0 })
    msg.post("/game_over", "hide")
    dbg.always("RESTART: new game from level 1")
    -- новая игра затирает обнулённое сохранение: переоткрытие браузера вернёт
    -- игрока в начало с полным запасом жизней (дальше снимок обновит level_start)
    save.store({ level = 1, lives = self.lives, drops = 0, keys = 0, hammers = 0 })
    msg.post("/level", "reload_level", { level = 1 })
end

-- восстановление прогресса после закрытия браузера: если есть сохранение с
-- нерастраченными жизнями, продолжаем с сохранёнными жизнями и карманом.
-- lives = 0 означает, что жизни кончились — начинаем новую игру с нуля
function M.resume(self)
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
