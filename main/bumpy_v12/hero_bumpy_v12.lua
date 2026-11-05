-- Bumpy v12 gameplay hero: 2D frames, one beat = contact_* + flight_*.
local CLIPS = require("main.bumpy_v12.bumpy_v12_clips")
local PHI = require("main.bumpy_v12.bumpy_v12_phi")
local state = require("main.level.level_state")

local M = {}
M.name = "bumpy_v12"
M.sticks_on_platform = true
-- ball.script runs the DWELL/FLIGHT contact state machine only for this hero.
M.contact_dwell = true

local VISUAL = "/bumpy_v12_visual"
local SHADOW = "/bumpy_v12_shadow_visual"

local HERO_SPRITE_SCALE = 42.0 / 72.0
local FRAME_PX = 144.0
local PIVOT_Y = 107.3
local RADIUS = 16.0
local PIVOT_OFFSET = (PIVOT_Y - FRAME_PX * 0.5) * HERO_SPRITE_SCALE - RADIUS
local BLINK_MIN = 1.5
local BLINK_MAX = 3.5

-- render order: platforms use z=0, the shadow is above them, the hero above it.
local SHADOW_Z = 0.01
local HERO_Z = 0.02

local SHADOW_K = 42.0 / 80.0
-- shadow texture is 192 px wide; at SHADOW_K its world half-width is this.
local SHADOW_HALF_W = 96.0 * SHADOW_K
local SHADOW_MAX_ALPHA = 0.49
local SHADOW_FADE = 0.08
local SHADOW_X_SMOOTH = 0.06
local SHADOW_LEVEL_SMOOTH = 0.2
local SHADOW_LEVELS = 9
local LAND_SQUASH_TIME = 0.22
local LAND_SQUASH_X = 0.45
local LAND_SQUASH_Y = 0.55
local SHADOW_MAX_HEIGHT_K = 3.0
local PLATFORM_HALF_W = 70.0
local CELL_W = 160.0
local CELL_H = 106.6666667
local PLATFORM_Y_BASE = 20.0
local PLATFORM_H = 20.0

local ROTATION_END = {
    flight_feet_to_head = 32,
    flight_feet_to_head_blink = 32,
    flight_head_side = 32,
    flight_head_side_blink = 32,
    flight_head_hop = 16,
    flight_head_hop_blink = 16,
}

local FLIGHT_BLINK = {
    flight_up = "flight_up_blink",
    flight_feet_to_head = "flight_feet_to_head_blink",
    flight_head_hop = "flight_head_hop_blink",
    flight_head_side = "flight_head_side_blink",
}

local function clip_by_name(name)
    for _, clip in ipairs(CLIPS) do
        if clip.name == name then
            return clip
        end
    end
    return nil
end

local function stretched_flight_target(name, target)
    local endf = ROTATION_END[name]
    local clip = clip_by_name(name)
    if endf and clip and endf > 1 then
        -- map the last rotation frame to the landing moment
        return target * clip.frames / (endf - 1)
    end
    return target
end

local function blink_delay()
    return BLINK_MIN + math.random() * (BLINK_MAX - BLINK_MIN)
end

local function set_visual_scale(self)
    local sx = self.v12_squash_x or 1.0
    local sy = self.v12_squash_y or 1.0
    go.set(VISUAL .. "#sprite", "scale",
        vmath.vector3(self.v12_sprite_k * self.v12_dir * sx, self.v12_sprite_k * sy, 1.0))
end

local function sync_visual(self)
    local pos = go.get_position()
    go.set_position(vmath.vector3(pos.x, pos.y + PIVOT_OFFSET, HERO_Z), self.v12_visual)
    go.set(self.v12_visual, "rotation", vmath.quat())
end

local function velocity_y()
    local ok, vel = pcall(go.get, "#collision_object", "linear_velocity")
    return ok and vel and vel.y or 0.0
end

local function held_direction(self)
    local left = (self.left_held or self.touch_left or self.tap_left)
        and not (self.right_held or self.touch_right or self.tap_right)
    local right = (self.right_held or self.touch_right or self.tap_right)
        and not (self.left_held or self.touch_left or self.tap_left)
    if right then
        return 1
    end
    if left then
        return -1
    end
    return 0
end

local function play_clip(self, name, target, force, reason)
    local clip = clip_by_name(name)
    if not clip then
        return nil
    end
    if self.v12_current_name == name and not force then
        return clip
    end
    self.v12_clip = clip
    self.v12_current_name = name
    self.v12_kind = clip.kind or "event"
    self.v12_start_time = self.time
    local tempo = self.env.tempo or 1.0
    local eff_target = target
    if not eff_target and clip.kind ~= "flight" and clip.kind ~= "contact" then
        eff_target = clip.duration_sec * tempo
    end
    self.v12_target = eff_target or clip.duration_sec
    if self.v12_target <= 0.0 then
        self.v12_target = clip.duration_sec
    end
    msg.post(VISUAL .. "#sprite", "play_animation", { id = hash(name) })
    if clip.loop then
        go.set(VISUAL .. "#sprite", "playback_rate",
            (clip.frames / 30.0) / math.max(clip.duration_sec, 0.001) / tempo)
    else
        go.set(VISUAL .. "#sprite", "playback_rate", 0.0)
        go.set(VISUAL .. "#sprite", "cursor", 0.0)
    end
    return clip
end

local function cursor_progress(self)
    local clip = self.v12_clip
    if not clip or clip.loop then
        return 1.0
    end
    local dur = math.max(self.v12_target or clip.duration_sec, 0.001)
    return vmath.clamp((self.time - self.v12_start_time) / dur, 0.0, 1.0)
end

local function set_cursor(self, progress)
    go.set(VISUAL .. "#sprite", "cursor", progress)
end

local function current_frame_index(self)
    local clip = self.v12_clip
    if not clip then
        return nil, 0
    end
    local n = clip.frames
    local progress = cursor_progress(self)
    local t = clip.loop
        and ((self.time - self.v12_start_time) % math.max(clip.duration_sec, 0.001))
            / math.max(clip.duration_sec, 0.001)
        or progress
    local idx = math.floor(t * n) + 1
    if idx < 1 then idx = 1 elseif idx > n then idx = n end
    return clip, idx
end

local function current_phi(self)
    local clip, idx = current_frame_index(self)
    if not clip or not clip.phi or #clip.phi == 0 then
        return 0.0
    end
    return (clip.phi[idx] or 0.0) % 360.0
end



local function log_contact(self, kind, contact_t, clip_name)
    local dt = contact_t - (self.v12_last_contact_t or contact_t)
    self.v12_last_contact_t = contact_t
    print(string.format("CONTACT t=%.3f clip=%s kind=%s dt=%.3f",
        contact_t, clip_name, kind, dt))
end

-- shadow: raycast down only against platforms, from center and both edges.
local function raycast_down(x, y, max_len)
    local from = vmath.vector3(x, y, 0.0)
    local to = vmath.vector3(x, y - max_len, 0.0)
    local ok, hit = pcall(physics.raycast, from, to, { hash("platform") })
    if ok and type(hit) == "table" and hit.position then
        local px = nil
        local id = hit.collision_object
        if id then
            local pok, ppos = pcall(go.get_position, id)
            if pok and ppos then
                px = ppos.x
            end
        end
        if not id then
            -- some engine builds omit collision_object in the raycast result
            local row = math.floor((hit.position.y - PLATFORM_Y_BASE - PLATFORM_H * 0.5) / CELL_H + 0.5)
            local col = math.floor((px or x) / CELL_W)
            if row >= 0 and row <= 5 and col >= 0 and col <= 5 then
                id = state.platform_id(row, col)
            end
        end
        return hit.position.y, px or x, id
    end
    return nil, nil, nil
end

-- fallback used only if physics.raycast is unavailable (headless/editor edge cases)
local function state_platform(x, y, max_len)
    local col = math.max(0, math.min(5, math.floor(x / CELL_W)))
    local start_row = math.max(0, math.min(5, math.floor((y - PLATFORM_Y_BASE) / CELL_H)))
    for row = start_row, 0, -1 do
        local id = state.platform_id(row, col)
        if id then
            local ppos = go.get_position(id)
            local py = ppos.y + PLATFORM_H * 0.5
            if py <= y - 1.0 and y - py <= max_len then
                return py, ppos.x, id
            end
        end
    end
    return nil, nil, nil
end

local function platform_below(self, pos)
    local max_len = SHADOW_MAX_HEIGHT_K * (self.env.h_default or 48.0)
    -- the platform directly under the center is authoritative; edge rays only
    -- keep the shadow alive while the hero is still hanging over a platform
    local function at(x)
        local surface, px, id = raycast_down(x, pos.y, max_len)
        if not surface then
            surface, px, id = state_platform(x, pos.y, max_len)
        end
        if surface then
            return { surface = surface, x = px or x, id = id }
        end
        return nil
    end
    local center = at(pos.x)
    if center then
        return center
    end
    local left = at(pos.x - RADIUS)
    local right = at(pos.x + RADIUS)
    if left and right then
        return left.surface >= right.surface and left or right
    end
    return left or right
end

local function platform_text(pid)
    if not pid then
        return "none"
    end
    return tostring(pid)
end

local function update_shadow(self, dt, pos)
    local platform = platform_below(self, pos)
    self.v12_has_floor_below = platform ~= nil
    local valid = false
    local surface = nil
    local shadow_center = pos.x
    local scale_x = 1.0
    local platform_id = nil

    if platform and platform.x then
        surface = platform.surface
        platform_id = platform.id
        -- shadow interval [x-rx, x+rx] clipped by the platform top surface
        local left = math.max(pos.x - SHADOW_HALF_W, platform.x - PLATFORM_HALF_W)
        local right = math.min(pos.x + SHADOW_HALF_W, platform.x + PLATFORM_HALF_W)
        if right - left > 0.5 then
            valid = true
            shadow_center = (left + right) * 0.5
            scale_x = (right - left) / (2.0 * SHADOW_HALF_W)
        end
    end

    if valid then
        if self.v12_shadow_surface and math.abs(surface - self.v12_shadow_surface) > 0.5 then
            -- platform changed: reappear on the new height, never slide between them
            self.v12_shadow_surface = surface
            self.v12_shadow_y = surface
            self.v12_shadow_visibility = 0.0
            self.v12_shadow_level = nil
            self.v12_shadow_x = nil
        elseif not self.v12_shadow_surface then
            self.v12_shadow_surface = surface
            self.v12_shadow_y = surface
        end
    end

    local target_vis = valid and 1.0 or 0.0
    local step = dt / SHADOW_FADE
    if self.v12_shadow_visibility < target_vis then
        self.v12_shadow_visibility = math.min(target_vis, self.v12_shadow_visibility + step)
    else
        self.v12_shadow_visibility = math.max(target_vis, self.v12_shadow_visibility - step)
    end

    if valid and self.v12_shadow_surface then
        -- gap between the bottom of the ball and the platform top
        local h = math.max(0.0, (pos.y - RADIUS) - self.v12_shadow_surface)
        local H = self.env.h_default or 48.0
        local level = math.max(0.0, math.min(SHADOW_LEVELS - 1, 8.0 * h / H))
        if not self.v12_shadow_level then
            self.v12_shadow_level = level
        else
            local k = math.min(1.0, dt / SHADOW_LEVEL_SMOOTH)
            self.v12_shadow_level = self.v12_shadow_level + (level - self.v12_shadow_level) * k
        end
        if not self.v12_shadow_x then
            self.v12_shadow_x = shadow_center
        else
            local kx = math.min(1.0, dt / SHADOW_X_SMOOTH)
            self.v12_shadow_x = self.v12_shadow_x + (shadow_center - self.v12_shadow_x) * kx
        end
        go.set_position(vmath.vector3(self.v12_shadow_x, self.v12_shadow_y, SHADOW_Z), go.get_id(SHADOW))

        local lf = self.v12_shadow_level
        local i0 = math.floor(lf)
        if i0 > SHADOW_LEVELS - 1 then i0 = SHADOW_LEVELS - 1 end
        local i1 = math.min(SHADOW_LEVELS - 1, i0 + 1)
        local w = lf - i0
        local a0 = SHADOW_MAX_ALPHA * self.v12_shadow_visibility * (1.0 - w)
        local a1 = SHADOW_MAX_ALPHA * self.v12_shadow_visibility * w
        if self.v12_shadow_i0 ~= i0 then
            self.v12_shadow_i0 = i0
            msg.post(SHADOW .. "#s0", "play_animation", { id = hash("shadow_" .. i0) })
        end
        if self.v12_shadow_i1 ~= i1 then
            self.v12_shadow_i1 = i1
            msg.post(SHADOW .. "#s1", "play_animation", { id = hash("shadow_" .. i1) })
        end
        go.set(SHADOW .. "#s0", "tint", vmath.vector4(1, 1, 1, a0))
        go.set(SHADOW .. "#s1", "tint", vmath.vector4(1, 1, 1, a1))
        go.set(SHADOW .. "#s0", "scale", vmath.vector3(SHADOW_K * scale_x, SHADOW_K, 1.0))
        go.set(SHADOW .. "#s1", "scale", vmath.vector3(SHADOW_K * scale_x, SHADOW_K, 1.0))
    end

    local hidden = self.v12_shadow_visibility <= 0.01 or not valid
    if self.v12_shadow_log_hidden ~= hidden or self.v12_shadow_log_platform ~= platform_id then
        self.v12_shadow_log_hidden = hidden
        self.v12_shadow_log_platform = platform_id
        print(string.format("SHADOW t=%.3f hidden=%s platform=%s",
            self.time or 0.0, hidden and "true" or "false", platform_text(platform_id)))
    end

    if self.v12_shadow_visibility <= 0.01 then
        msg.post(SHADOW .. "#s0", "disable")
        msg.post(SHADOW .. "#s1", "disable")
    else
        msg.post(SHADOW .. "#s0", "enable")
        msg.post(SHADOW .. "#s1", "enable")
    end
end

local function flight_clip_for(self, start_on_head, direction)
    local base
    if direction ~= 0 then
        base = start_on_head and "flight_head_side" or "flight_feet_to_head"
    else
        base = start_on_head and "flight_head_hop" or "flight_up"
    end
    local blink = FLIGHT_BLINK[base]
    local name = base
    if blink and self.v12_blink_timer <= 0.0 and clip_by_name(blink) then
        self.v12_blink_timer = blink_delay()
        name = blink
    end
    local lands_on_head = (base == "flight_feet_to_head")
    return name, lands_on_head
end

function M.setup(self, env)
    self.env = env
    self.v12_visual = go.get_id(VISUAL)
    self.v12_sprite_k = HERO_SPRITE_SCALE / go.get_scale(self.v12_visual).x
    self.v12_shadow = go.get_id(SHADOW)
    self.v12_shadow_surface = nil
    self.v12_shadow_y = nil
    self.v12_shadow_x = nil
    self.v12_shadow_visibility = 0.0
    self.v12_shadow_level = nil
    self.v12_shadow_i0 = -1
    self.v12_shadow_i1 = -1
    self.v12_shadow_log_hidden = nil
    self.v12_shadow_log_platform = nil
    self.v12_dir = 1
    self.v12_squash_t = 0.0
    self.v12_squash_strength = 0.0
    self.v12_squash_x = 1.0
    self.v12_squash_y = 1.0
    self.v12_turn_to = nil
    self.v12_current_name = nil
    self.v12_kind = nil
    self.v12_blink_timer = blink_delay()
    self.v12_on_head = false
    self.v12_flight_start_on_head = false
    self.v12_fall_hurt_done = false
    self.v12_surprise_started = false
    self.v12_fall_start_time = nil
    self.v12_fall_start_y = nil
    self.v12_has_floor_below = true
    self.v12_last_contact_t = nil
    set_visual_scale(self)
    sync_visual(self)
end

function M.activate(self)
    msg.post(VISUAL .. "#sprite", "enable")
    play_clip(self, "idle", nil, false, "idle")
    self.v12_kind = "idle"
    set_visual_scale(self)
    sync_visual(self)
end

function M.deactivate(self)
    msg.post(VISUAL .. "#sprite", "disable")
    msg.post(SHADOW .. "#s0", "disable")
    msg.post(SHADOW .. "#s1", "disable")
end

function M.reset(self)
    self.v12_dir = 1
    self.v12_squash_t = 0.0
    self.v12_squash_strength = 0.0
    self.v12_squash_x = 1.0
    self.v12_squash_y = 1.0
    self.v12_turn_to = nil
    self.v12_current_name = nil
    self.v12_kind = nil
    self.v12_blink_timer = blink_delay()
    self.v12_on_head = false
    self.v12_flight_start_on_head = false
    self.v12_fall_hurt_done = false
    self.v12_surprise_started = false
    self.v12_fall_start_time = nil
    self.v12_fall_start_y = nil
    self.v12_has_floor_below = true
    self.v12_last_contact_t = nil
    self.v12_shadow_surface = nil
    self.v12_shadow_y = nil
    self.v12_shadow_x = nil
    self.v12_shadow_visibility = 0.0
    self.v12_shadow_level = nil
    self.v12_shadow_i0 = -1
    self.v12_shadow_i1 = -1
    self.v12_shadow_log_hidden = nil
    self.v12_shadow_log_platform = nil
    set_visual_scale(self)
    sync_visual(self)
    play_clip(self, "idle", nil, false, "idle")
    self.v12_kind = "idle"
end

-- accepted contact: contact_feet or contact_head, cursor 0, hold the last frame
function M.begin_contact(self, duration)
    local name = self.v12_on_head and "contact_head" or "contact_feet"
    play_clip(self, name, duration or self.env.contact_dwell, true, "contact")
    self.v12_kind = "contact"
    self.v12_fall_hurt_done = false
    log_contact(self, self.v12_on_head and "head" or "feet", self.time, name)
end

-- idle -> anticipation -> flight (used after a long-fall landing/rest)
function M.begin_anticipation(self)
    local clip = play_clip(self, "anticipation", nil, false, "anticipation")
    self.v12_kind = "anticipation"
    return clip and clip.duration_sec or 0.0
end

-- Long fall: deep landing squash, held for its full 0.3 s
function M.begin_big_landing(self)
    local name = self.v12_on_head and "land_head" or "landing"
    local clip = play_clip(self, name, nil, false, "landing")
    if clip then
        -- frame 1 hangs below the pivot; start from the squash frames so
        -- the landing does not snap into the floor
        self.v12_start_time = self.time - (2.0 / clip.frames) * clip.duration_sec
    end
    self.v12_kind = "big_landing"
    self.v12_fall_hurt_done = false
    self.v12_surprise_started = false
    print(string.format("BIG_LANDING t=%.3f clip=%s", self.time, name))
    return clip and clip.duration_sec or 0.0
end

-- dwell end: flight clip is chosen from the player input at this exact moment
function M.begin_flight(self, direction, duration)
    direction = direction or 0
    if direction ~= 0 then
        self.v12_dir = direction < 0 and -1 or 1
        set_visual_scale(self)
    end
    local start_on_head = self.v12_on_head
    local name, lands_on_head = flight_clip_for(self, start_on_head, direction)
    self.v12_flight_start_on_head = start_on_head
    self.v12_on_head = lands_on_head
    local target = duration or self.env.t_air
    target = stretched_flight_target(name, target)
    play_clip(self, name, target, false, "release")
    self.v12_kind = "flight"
    self.v12_fall_hurt_done = false
end

function M.set_flight_target(self, duration)
    if self.v12_kind == "flight" and self.v12_clip
        and not self.v12_clip.loop and duration and duration > 0.0 then
        local target = duration
        target = stretched_flight_target(self.v12_current_name, target)
        self.v12_target = target
    end
end

function M.begin_high_jump(self)
    self.v12_flight_start_on_head = self.v12_on_head
    self.v12_on_head = false
    play_clip(self, "high_jump", nil, false, "high_jump")
    self.v12_kind = "high_jump"
    self.v12_fall_hurt_done = false
end

function M.begin_rest(self)
    self.v12_blink_timer = blink_delay()
    if self.v12_on_head then
        -- stay stuck on the head, round: frame 1 of flight_head_hop
        play_clip(self, "flight_head_hop", 1.0, false, "contact")
        go.set(VISUAL .. "#sprite", "playback_rate", 0.0)
        -- frame 2 is the round head-down pose (frame 1 is the squash)
        go.set(VISUAL .. "#sprite", "cursor", 1.0 / 34.0)
        self.v12_kind = "head_rest_round"
        return
    end
    play_clip(self, "idle", nil, false, "idle")
    self.v12_kind = "idle"
end

function M.force_head_landing(self)
    self.v12_on_head = true
end

function M.force_feet_landing(self)
    self.v12_on_head = false
end

function M.start_slime_flip(self, duration)
    -- head-first onto slime: add a 180 flip so the landing is on feet
    self.v12_on_head = false
    play_clip(self, "flight_head_hop", duration or 0.22, false, "release")
    self.v12_kind = "flight"
end

function M.is_over_gap(self)
    return self.v12_has_floor_below == false
end

function M.is_on_head(self)
    return self.v12_on_head == true
end

function M.is_falling(self)
    return self.v12_kind == "fall"
        or self.v12_kind == "fall_surprised"
        or self.v12_kind == "fall_surprise_in"
end

function M.is_surprised_fall(self)
    return self.v12_kind == "fall_surprised"
        or self.v12_kind == "fall_surprise_in"
end

function M.settle(self)
    M.begin_contact(self)
end

local function start_fall(self)
    local pos = go.get_position()
    self.v12_fall_start_time = self.time
    self.v12_fall_start_y = pos.y
    play_clip(self, "fall", nil, false, "fall")
    self.v12_kind = "fall"
end

function M.start_land_squash(self, strength)
    strength = vmath.clamp(strength or 0.0, 0.0, 1.0)
    if strength <= 0.0 then
        return
    end
    local squash_time = LAND_SQUASH_TIME * (self.env.tempo or 1.0)
    self.v12_squash_dur = squash_time
    self.v12_squash_t = squash_time
    self.v12_squash_strength = strength
    self.v12_squash_x = 1.0 + LAND_SQUASH_X * strength
    self.v12_squash_y = 1.0 - LAND_SQUASH_Y * strength
    set_visual_scale(self)
end

function M.update(self, dt)
    sync_visual(self)
    if self.v12_squash_t > 0.0 then
        self.v12_squash_t = math.max(0.0, self.v12_squash_t - dt)
        local k = self.v12_squash_t / (self.v12_squash_dur or LAND_SQUASH_TIME)
        local amt = self.v12_squash_strength * k
        self.v12_squash_x = 1.0 + LAND_SQUASH_X * amt
        self.v12_squash_y = 1.0 - LAND_SQUASH_Y * amt
        set_visual_scale(self)
    end
    update_shadow(self, dt, go.get_position())
    self.v12_blink_timer = self.v12_blink_timer - dt

    local kind = self.v12_kind
    if kind == "contact" then
        set_cursor(self, cursor_progress(self))
        return
    end
    if kind == "flight" then
        set_cursor(self, cursor_progress(self))
        return
    end
    if kind == "anticipation" then
        set_cursor(self, cursor_progress(self))
        return
    end
    if kind == "high_jump" then
        local progress = cursor_progress(self)
        set_cursor(self, progress)
        if self.high_jump and velocity_y() >= 0.0 then
            return
        end
        start_fall(self)
        return
    end
    if kind == "ceiling" then
        local progress = cursor_progress(self)
        set_cursor(self, progress)
        if progress >= 1.0 then
            start_fall(self)
        end
        return
    end
    if kind == "big_landing" then
        set_cursor(self, cursor_progress(self))
        return
    end
    if kind == "fall_surprise_in" then
        local progress = cursor_progress(self)
        set_cursor(self, progress)
        if progress >= 1.0 then
            play_clip(self, "fall_surprised", nil, false, "surprise")
            self.v12_kind = "fall_surprised"
        end
        return
    end
    if kind == "fall_surprised" then
        return
    end
    if kind == "head_rest_round" then
        go.set(VISUAL .. "#sprite", "cursor", 1.0 / 34.0)
        return
    end
    if kind == "hit" or kind == "event" or kind == "hurt" then
        set_cursor(self, cursor_progress(self))
        return
    end
    if kind == "fall" then
        if self.sticky_rest then
            M.begin_rest(self)
            return
        end
        return
    end

    if self.v12_current_name == "turn_in" and cursor_progress(self) >= 1.0 then
        play_clip(self, "half_turn_loop", nil, false, "turn")
        return
    end
    if self.v12_current_name == "turn_out" and cursor_progress(self) >= 1.0 then
        play_clip(self, "idle", nil, false, "idle")
        return
    end
    if self.v12_current_name == "turn_rl" and cursor_progress(self) >= 1.0 then
        if self.v12_turn_to then
            self.v12_dir = self.v12_turn_to
            self.v12_turn_to = nil
            set_visual_scale(self)
        end
        play_clip(self, "half_turn_loop", nil, false, "turn")
        return
    end

    if self.sticky_rest then
        local dir = held_direction(self)
        local name = self.v12_current_name
        if dir ~= 0 then
            if dir ~= self.v12_dir then
                self.v12_turn_to = dir
                play_clip(self, "turn_rl", nil, false, "turn")
                return
            end
            if name ~= "turn_in" and name ~= "half_turn_loop" then
                play_clip(self, "turn_in", nil, false, "turn")
                return
            end
        else
            if name == "half_turn_loop" or name == "turn_in" then
                play_clip(self, "turn_out", nil, false, "turn")
                return
            end
        end
        if name == "idle" and self.v12_blink_timer <= 0.0 then
            self.v12_blink_timer = blink_delay()
            play_clip(self, "blink", nil, false, "blink")
            return
        end
        if name == "blink" and cursor_progress(self) >= 1.0 then
            play_clip(self, "idle", nil, false, "idle")
        end
        return
    end

    if kind == "idle" and velocity_y() < 0.0 then
        play_clip(self, "fall", nil, false, "fall")
        self.v12_kind = "fall"
    end
end

function M.on_action(self, direction, duration)
    if direction then
        M.begin_flight(self, direction, duration)
    else
        M.begin_high_jump(self)
    end
end

-- wall hit: choose the clip by the part facing the wall (hair direction)
function M.apply_squash(self)
    if self.squash_axis ~= "x" then
        return
    end
    local d = (self.bounce_x_wall or 0.0) - (self.bounce_x_start or 0.0)
    local wall = d < 0.0 and "left" or "right"
    local clip_name = self.v12_current_name
    local clip, frame = current_frame_index(self)
    local T = clip_name and PHI[clip_name] or nil
    local sinv = T and (T.sin[frame] or 0.0) or 0.0
    local cosv = T and (T.cos[frame] or 0.0)
        or (self.v12_on_head and -1.0 or 1.0)
    local s = self.v12_dir or 1
    local hx = s * sinv
    local move_dir = wall == "right" and 1 or -1
    local lead = hx * move_dir
    local leading
    if lead > 0.15 then
        leading = "head"
    elseif lead < -0.15 then
        leading = "feet"
    else
        leading = cosv > 0.0 and "feet" or "head"
    end
    local up = cosv > 0.0
    local name
    if leading == "head" then
        name = up and "head_hit_side_up" or "head_hit_side_inv"
    else
        name = up and "feet_hit_side_up" or "feet_hit_side_inv"
    end
    -- clips are drawn for the right wall; the left wall is the mirror
    self.v12_dir = wall == "right" and 1 or -1
    set_visual_scale(self)
    self.v12_on_head = false
    self.v12_kind = "hit"
    play_clip(self, name, nil, false, "hit")
    print(string.format(
        "WALLHIT t=%.3f clip=%s frame=%d s=%d hx=%.2f leading=%s result=%s x=%.1f y=%.1f",
        self.time, tostring(clip_name), frame, s, hx, leading, name, go.get_position().x, go.get_position().y))
end

function M.on_ceiling(self)
    local name
    if self.v12_on_head then
        name = "feet_hit_top"
    else
        name = "head_hit_top"
    end
    self.v12_on_head = (name == "feet_hit_top")
    play_clip(self, name, nil, false, "hit")
    self.v12_kind = "ceiling"
    log_contact(self, "ceiling", self.time, name)
    return false
end

function M.hop_height(self)
    return self.env.hop_height
end

function M.step_scale(self)
    return 1.0
end

function M.squash_time_scale(self)
    return 1.0
end

function M.allow_from_rest(self)
    return false
end

function M.ignore_contacts(self)
    return self.sticky_rest == true
end

return M
