-- Bumpy v10 gameplay hero: phi-based hit clips, input buffer in ball.script,
-- separate shadow system with 9 cross-faded levels.
local CLIPS = require("main.bumpy_v10.bumpy_v10_clips")
local state = require("main.level.level_state")

local M = {}
M.name = "bumpy_v10"
M.sticks_on_platform = true

local VISUAL = "/bumpy_v10_visual"
local SHADOW = "/bumpy_v10_shadow_visual"

local HERO_SPRITE_SCALE = 42.0 / 72.0
local LATERAL_ARC_SCALE = 1.3

local TARGET_PX = 42.0
local BALL_DIAMETER = 72.0
local FRAME_PX = 144.0
local PIVOT_Y = 107.3
local RADIUS = 16.0
local PIVOT_OFFSET = (PIVOT_Y - FRAME_PX * 0.5) * HERO_SPRITE_SCALE - RADIUS
local FALL_SPEED = 57.6
local BLINK_MIN = 1.5
local BLINK_MAX = 3.5

local SHADOW_K = 42.0 / 80.0
local SHADOW_MAX_ALPHA = 0.49
local SHADOW_FADE = 0.08
local SHADOW_X_SMOOTH = 0.06
local SHADOW_LEVEL_SMOOTH = 0.2
local SHADOW_LEVELS = 9
local SHADOW_EDGE = 10.0
local PLATFORM_HALF_W = 70.0
local CELL_W = 160.0
local CELL_H = 106.6666667
local PLATFORM_Y_BASE = 20.0
local PLATFORM_H = 20.0

local BLINK_VARIANT = {
    beat_up = "beat_up_blink",
    jump_head = "jump_head_blink",
    hop_flip = "hop_flip_blink",
    second_jump = "second_jump_blink",
}

local function clip_by_name(name)
    for _, clip in ipairs(CLIPS) do
        if clip.name == name then
            return clip
        end
    end
    return nil
end

local function blink_delay()
    return BLINK_MIN + math.random() * (BLINK_MAX - BLINK_MIN)
end

local function facing_name(self)
    return self.v10_dir < 0 and "left" or "right"
end

local function held_direction(self)
    local left = (self.left_held or self.touch_left or self.tap_left)
        and not (self.right_held or self.touch_right or self.tap_right)
    local right = (self.right_held or self.touch_right or self.tap_right)
        and not (self.left_held or self.touch_left or self.tap_left)
    if right then return 1 end
    if left then return -1 end
    return 0
end

local function set_visual_scale(self)
    go.set(VISUAL .. "#sprite", "scale",
        vmath.vector3(self.v10_sprite_k * self.v10_dir, self.v10_sprite_k, 1.0))
end

local function sync_visual(self)
    local pos = go.get_position()
    go.set_position(vmath.vector3(pos.x, pos.y + PIVOT_OFFSET, pos.z), self.v10_visual)
    go.set(self.v10_visual, "rotation", vmath.quat())
end

local function play_clip(self, name, target_duration, force)
    local clip = clip_by_name(name)
    if not clip then
        return
    end
    if self.v10_current_name == name and not force then
        return
    end
    local target = target_duration or clip.duration_sec
    if target <= 0.0 then
        target = clip.duration_sec
    end
    self.v10_clip = clip
    self.v10_current_name = name
    self.v10_clip_time = 0.0
    self.v10_target = target
    self.v10_locked = not clip.loop
    self.v10_start_time = self.time
    msg.post(VISUAL .. "#sprite", "play_animation", { id = hash(name) })
    go.set(VISUAL .. "#sprite", "cursor", 0.0)
    go.set(VISUAL .. "#sprite", "playback_rate", (clip.frames / 30.0) / math.max(target, 0.001))
end

local function with_blink(self, name)
    local variant = BLINK_VARIANT[name]
    if variant and self.v10_blink_timer <= 0.0 and clip_by_name(variant) then
        self.v10_blink_timer = blink_delay()
        return variant
    end
    return name
end

local function velocity_y()
    local ok, vel = pcall(go.get, "#collision_object", "linear_velocity")
    return ok and vel and vel.y or 0.0
end

-- phi of the current clip on the current frame (from animations.json)
local function current_phi(self)
    local clip = self.v10_clip
    if not clip or not clip.phi or #clip.phi == 0 then
        return 0.0
    end
    local n = #clip.phi
    local elapsed = (self.time or 0.0) - (self.v10_start_time or 0.0)
    local dur = math.max(self.v10_target or clip.duration_sec, 0.001)
    local t = elapsed / dur
    if clip.loop then
        t = t % 1.0
    end
    local idx = math.floor(t * n) + 1
    if idx < 1 then
        idx = 1
    elseif idx > n then
        idx = n
    end
    return (clip.phi[idx] or 0.0) % 360.0
end

local function angle_distance(a, b)
    local d = math.abs(a - b) % 360.0
    if d > 180.0 then
        d = 360.0 - d
    end
    return d
end

local function log_contact(self, kind, contact_t, clip_name)
    print(string.format("CONTACT t=%.3f kind=%s clip=%s phi=%.1f facing=%s",
        contact_t, kind, clip_name, current_phi(self), facing_name(self)))
end

-- shadow: raycast to the platform surface, 9 cross-faded levels
local function shadow_hit(self, pos)
    local from = vmath.vector3(pos.x, pos.y - RADIUS, 0.0)
    local to = vmath.vector3(pos.x, pos.y - 900.0, 0.0)
    local ok, hit = pcall(physics.raycast, from, to, { hash("platform") })
    if ok and type(hit) == "table" and hit.position then
        local px = nil
        if hit.collision_object then
            local pok, ppos = pcall(go.get_position, hit.collision_object)
            if pok and ppos then
                px = ppos.x
            end
        end
        return hit.position.y, px
    end
    local col = math.max(0, math.min(5, math.floor(pos.x / CELL_W)))
    local start_row = math.max(0, math.min(5, math.floor((pos.y - PLATFORM_Y_BASE) / CELL_H)))
    for row = start_row, 0, -1 do
        local id = state.platform_id(row, col)
        if id then
            local ppos = go.get_position(id)
            local py = ppos.y + PLATFORM_H * 0.5
            if py <= pos.y - 1.0 then
                return py, ppos.x
            end
        end
    end
    return nil, nil
end

local function update_shadow(self, dt, pos)
    local surface, platform_x = shadow_hit(self, pos)
    local edge = false
    if surface and platform_x then
        edge = math.abs(pos.x - platform_x) > (PLATFORM_HALF_W - SHADOW_EDGE)
    end
    local valid = surface ~= nil and not edge

    if valid then
        if self.v10_shadow_surface and math.abs(surface - self.v10_shadow_surface) > 0.5 then
            -- platform changed: reappear on the new height, never slide between them
            self.v10_shadow_surface = surface
            self.v10_shadow_y = surface
            self.v10_shadow_visibility = 0.0
            self.v10_shadow_level = nil
        elseif not self.v10_shadow_surface then
            self.v10_shadow_surface = surface
            self.v10_shadow_y = surface
        end
    end

    local target_vis = valid and 1.0 or 0.0
    local step = dt / SHADOW_FADE
    if self.v10_shadow_visibility < target_vis then
        self.v10_shadow_visibility = math.min(target_vis, self.v10_shadow_visibility + step)
    else
        self.v10_shadow_visibility = math.max(target_vis, self.v10_shadow_visibility - step)
    end

    if valid and self.v10_shadow_surface then
        local h = math.max(0.0, pos.y - self.v10_shadow_surface)
        local H = self.env.high_jump_height or 154.6667
        local level = math.max(0.0, math.min(SHADOW_LEVELS - 1, 8.0 * h / H))
        if not self.v10_shadow_level then
            self.v10_shadow_level = level
        else
            local k = math.min(1.0, dt / SHADOW_LEVEL_SMOOTH)
            self.v10_shadow_level = self.v10_shadow_level + (level - self.v10_shadow_level) * k
        end
        if not self.v10_shadow_x then
            self.v10_shadow_x = pos.x
        else
            local kx = math.min(1.0, dt / SHADOW_X_SMOOTH)
            self.v10_shadow_x = self.v10_shadow_x + (pos.x - self.v10_shadow_x) * kx
        end
        go.set_position(vmath.vector3(self.v10_shadow_x, self.v10_shadow_y, -0.1), go.get_id(SHADOW))

        local lf = self.v10_shadow_level
        local i0 = math.floor(lf)
        if i0 > SHADOW_LEVELS - 1 then i0 = SHADOW_LEVELS - 1 end
        local i1 = math.min(SHADOW_LEVELS - 1, i0 + 1)
        local w = lf - i0
        local a0 = SHADOW_MAX_ALPHA * self.v10_shadow_visibility * (1.0 - w)
        local a1 = SHADOW_MAX_ALPHA * self.v10_shadow_visibility * w
        if self.v10_shadow_i0 ~= i0 then
            self.v10_shadow_i0 = i0
            msg.post(SHADOW .. "#s0", "play_animation", { id = hash("shadow_" .. i0) })
        end
        if self.v10_shadow_i1 ~= i1 then
            self.v10_shadow_i1 = i1
            msg.post(SHADOW .. "#s1", "play_animation", { id = hash("shadow_" .. i1) })
        end
        go.set(SHADOW .. "#s0", "tint", vmath.vector4(1, 1, 1, a0))
        go.set(SHADOW .. "#s1", "tint", vmath.vector4(1, 1, 1, a1))
        go.set(SHADOW .. "#s0", "scale", vmath.vector3(SHADOW_K, SHADOW_K, 1.0))
        go.set(SHADOW .. "#s1", "scale", vmath.vector3(SHADOW_K, SHADOW_K, 1.0))
    end

    if self.v10_shadow_visibility <= 0.01 then
        msg.post(SHADOW .. "#s0", "disable")
        msg.post(SHADOW .. "#s1", "disable")
    else
        msg.post(SHADOW .. "#s0", "enable")
        msg.post(SHADOW .. "#s1", "enable")
    end
end

function M.setup(self, env)
    self.env = env
    self.v10_visual = go.get_id(VISUAL)
    self.v10_sprite_k = HERO_SPRITE_SCALE / go.get_scale(self.v10_visual).x
    self.v10_shadow = go.get_id(SHADOW)
    self.v10_shadow_surface = nil
    self.v10_shadow_y = nil
    self.v10_shadow_x = nil
    self.v10_shadow_visibility = 0.0
    self.v10_shadow_level = nil
    self.v10_shadow_i0 = -1
    self.v10_shadow_i1 = -1
    self.v10_dir = 1
    self.v10_flipped = false
    self.v10_head_pending = false
    self.v10_just_head = false
    self.v10_current_name = nil
    self.v10_locked = false
    self.v10_blink_timer = blink_delay()
    set_visual_scale(self)
    sync_visual(self)
end

function M.activate(self)
    msg.post(VISUAL .. "#sprite", "enable")
    play_clip(self, "idle", nil, true)
    set_visual_scale(self)
    sync_visual(self)
end

function M.deactivate(self)
    msg.post(VISUAL .. "#sprite", "disable")
    msg.post(SHADOW .. "#s0", "disable")
    msg.post(SHADOW .. "#s1", "disable")
end

function M.reset(self)
    self.v10_dir = 1
    self.v10_flipped = false
    self.v10_head_pending = false
    self.v10_just_head = false
    self.v10_current_name = nil
    self.v10_locked = false
    self.v10_blink_timer = blink_delay()
    self.v10_shadow_surface = nil
    self.v10_shadow_y = nil
    self.v10_shadow_x = nil
    self.v10_shadow_visibility = 0.0
    self.v10_shadow_level = nil
    self.v10_shadow_i0 = -1
    self.v10_shadow_i1 = -1
    set_visual_scale(self)
    sync_visual(self)
    play_clip(self, "idle", nil, true)
end

function M.update(self, dt)
    sync_visual(self)
    update_shadow(self, dt, go.get_position())
    self.v10_blink_timer = self.v10_blink_timer - dt

    if self.v10_locked then
        self.v10_clip_time = self.v10_clip_time + dt
        if self.v10_clip_time >= self.v10_target then
            self.v10_locked = false
            go.set(VISUAL .. "#sprite", "playback_rate", 0.0)
        end
    end

    if self.sticky_rest and not self.v10_locked then
        local name = self.v10_current_name
        if name ~= "idle" and name ~= "blink" and name ~= "turn_rl" then
            play_clip(self, "idle", nil, true)
            return
        end
    end

    if self.v10_current_name == "idle" then
        if not self.v10_locked and self.v10_blink_timer <= 0.0 then
            self.v10_blink_timer = blink_delay()
            play_clip(self, "blink", nil, true)
        end
        return
    end
    if self.v10_current_name == "blink" then
        if not self.v10_locked then
            play_clip(self, "idle", nil, true)
        end
        return
    end
    if self.v10_current_name == "beat_up" or self.v10_current_name == "beat_up_blink"
        or self.v10_current_name == "jump_head" or self.v10_current_name == "jump_head_blink"
        or self.v10_current_name == "second_jump" or self.v10_current_name == "second_jump_blink"
        or self.v10_current_name == "hop_flip" or self.v10_current_name == "hop_flip_blink"
        or self.v10_current_name == "head_hit_top" or self.v10_current_name == "feet_hit_top"
        or self.v10_current_name == "head_hit_side" or self.v10_current_name == "feet_hit_side"
        or self.v10_current_name == "body_hit_side" or self.v10_current_name == "body_hit_side_inv" then
        return
    end
    if self.v10_current_name == "high_jump" then
        local vy = velocity_y()
        if self.high_jump and vy >= 0.0 then
            return
        end
        play_clip(self, "fall")
        return
    end
    if self.v10_current_name == "fall" then
        if self.sticky_rest then
            play_clip(self, "idle")
        end
        return
    end
    if not self.v10_locked then
        play_clip(self, "idle")
    end
end

function M.on_action(self, direction, duration)
    if direction then
        self.v10_dir = direction < 0 and -1 or 1
        set_visual_scale(self)
        if self.v10_just_head then
            self.v10_just_head = false
            self.v10_head_pending = false
            play_clip(self, with_blink(self, "second_jump"), duration, true)
        else
            self.v10_head_pending = true
            self.v10_just_head = false
            play_clip(self, with_blink(self, "jump_head"), duration, true)
        end
    else
        self.v10_head_pending = false
        self.v10_just_head = false
        play_clip(self, "high_jump", nil, true)
    end
end

function M.settle(self, moving)
    local contact_t = self.time
    go.set("#collision_object", "linear_velocity", vmath.vector3(0.0, self.env.jump_speed, 0.0))
    self.next_touch_time = self.time + self.env.period

    if self.v10_head_pending then
        self.v10_head_pending = false
        self.v10_just_head = true
        if moving then
            local dir = held_direction(self)
            if dir ~= 0 then
                self.v10_dir = dir
                set_visual_scale(self)
            end
            play_clip(self, with_blink(self, "second_jump"), nil, true)
        else
            play_clip(self, with_blink(self, "hop_flip"), nil, true)
        end
        log_contact(self, "head", contact_t, self.v10_current_name)
        return
    end

    self.v10_just_head = false
    local clip = with_blink(self, "beat_up")
    play_clip(self, clip, nil, true)
    log_contact(self, "feet", contact_t, clip)
end

-- section 3: pick the hit clip by phi of the current frame
function M.apply_squash(self)
    if self.squash_axis ~= "x" then
        return
    end
    local d = (self.bounce_x_wall or 0.0) - (self.bounce_x_start or 0.0)
    local left = d < 0.0
    local phi = current_phi(self)
    if left then
        phi = (360.0 - phi) % 360.0
    end
    local best = 0
    local bestd = angle_distance(phi, 0.0)
    for _, a in ipairs({ 90.0, 180.0, 270.0 }) do
        local dd = angle_distance(phi, a)
        if dd < bestd then
            best = a
            bestd = dd
        end
    end
    local name, flip
    if best == 90.0 then
        name, flip = "head_hit_side", false
    elseif best == 270.0 then
        name, flip = "feet_hit_side", false
    elseif best == 0.0 then
        name, flip = "body_hit_side", false
    else
        name, flip = "body_hit_side_inv", true
    end
    self.v10_dir = left and -1 or 1
    set_visual_scale(self)
    self.v10_head_pending = false
    self.v10_just_head = false
    self.v10_flipped = flip
    play_clip(self, name, nil, true)
    print(string.format("WALL_HIT clip=%s phi=%.1f side=%s flipped=%s",
        name, phi, left and "left" or "right", tostring(flip)))
end

function M.on_ceiling(self)
    local contact_t = self.time
    local phi = current_phi(self)
    local name, flip
    if math.cos(math.rad(phi)) >= 0.0 then
        name, flip = "head_hit_top", false
    else
        name, flip = "feet_hit_top", true
    end
    self.v10_head_pending = false
    self.v10_just_head = false
    self.v10_flipped = flip
    play_clip(self, name, nil, true)
    print(string.format("CEILING_HIT clip=%s phi=%.1f flipped=%s", name, phi, tostring(flip)))
    log_contact(self, "ceiling", contact_t, name)
    return false
end

function M.hop_height(self)
    return self.env.hop_height * LATERAL_ARC_SCALE
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
