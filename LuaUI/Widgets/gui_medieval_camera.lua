-- Medieval WASD Camera Widget — WASD pan + Q/E yaw rotation for the RTS
-- overhead camera, in the style of 0 A.D. / Age of Empires II.
--
-- Pure unsynced LuaUI widget (portable and mod-specific, unlike engine
-- uikeys.txt). Polls held keys in widget:Update() and mutates the camera
-- state returned by Spring.GetCameraState(), then commits it with
-- Spring.SetCameraState(camState, 0):
--
--   * W / S       : pan forward / backward along the camera's ground vector
--   * A / D       : strafe left / right along the camera's ground right vector
--   * Q / E       : yaw left / right (cameraState.ry, radians)
--
-- Movement uses Spring.GetCameraVectors() so panning stays aligned to the
-- current camera yaw (the same pattern used by the engine's own example
-- widget tools/engine/recoil_2026.07.04/examples/Widgets/camera_smooth_move.lua).
--
-- Input is suppressed while the medieval main menu is open
-- (WG.medievalMainMenuOpen, published by gui_medieval_main_menu.lua) or while
-- any text-input surface is focused (WG.medievalChatInputActive,
-- WG.medievalConsoleInputActive, WG.editBoxActive).
--
-- GPL-v2 safe: original procedural widget code only.

function widget:GetInfo()
  return {
    name    = "Medieval WASD Camera",
    desc    = "WASD camera pan and Q/E yaw rotation for the RTS overhead camera",
    author  = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer   = 0,
    enabled = true,
  }
end

--------------------------------------------------------------------------------
-- Key tables (numeric keysyms match KEYSYMS: W=119, S=115, A=97, D=100,
-- Q=113, E=101). Labels are also matched so shifted/lowercase input still works.
--------------------------------------------------------------------------------

local KEYS = {
  [119] = "forward",   -- W
  [115] = "back",      -- S
  [97]  = "left",      -- A
  [100] = "right",     -- D
  [113] = "rotLeft",   -- Q
  [101] = "rotRight",  -- E
}

local LABEL_KEYS = {
  w = "forward",
  s = "back",
  a = "left",
  d = "right",
  q = "rotLeft",
  e = "rotRight",
}

--------------------------------------------------------------------------------
-- Tunables
--------------------------------------------------------------------------------

-- World-units per second of ground panning.
local PAN_SPEED = 900.0
-- Radians per second of yaw rotation (about 86 deg/s).
local ROT_SPEED = 1.5

-- Clamp per-frame dt so a long hitch never teleports the camera.
local MAX_DT = 0.1

--------------------------------------------------------------------------------
-- Camera API refs
--------------------------------------------------------------------------------

local spGetCameraState   = Spring.GetCameraState
local spSetCameraState   = Spring.SetCameraState
local spGetCameraVectors = Spring.GetCameraVectors

--------------------------------------------------------------------------------
-- Held-key state
--------------------------------------------------------------------------------

local pressed = {}

local function hasAnyCameraKey()
  return pressed.forward or pressed.back or pressed.left or pressed.right
      or pressed.rotLeft or pressed.rotRight
end

local function clearHeldKeys()
  pressed.forward   = nil
  pressed.back      = nil
  pressed.left      = nil
  pressed.right     = nil
  pressed.rotLeft   = nil
  pressed.rotRight  = nil
end

--------------------------------------------------------------------------------
-- Input-focus guards
--------------------------------------------------------------------------------

local function ignoreInput()
  -- Medieval main menu published by gui_medieval_main_menu.lua.
  if WG and WG.medievalMainMenuOpen then
    return true
  end

  -- Text-input surfaces. Chat / console / edit-box widgets are expected to
  -- publish one of these WG flags while they own the keyboard.
  if WG and (WG.medievalChatInputActive
          or WG.medievalConsoleInputActive
          or WG.editBoxActive) then
    return true
  end

  return false
end

--------------------------------------------------------------------------------
-- Call-ins
--------------------------------------------------------------------------------

function widget:KeyPress(key, mods, isRepeat, label, unicode)
  if ignoreInput() then
    return false
  end

  local action = KEYS[key]
  if not action and label then
    action = LABEL_KEYS[label:lower()]
  end

  if action then
    pressed[action] = true
    return true
  end

  return false
end

function widget:KeyRelease(key, mods, isRepeat, label, unicode)
  local action = KEYS[key]
  if not action and label then
    action = LABEL_KEYS[label:lower()]
  end

  if action then
    pressed[action] = nil
    return true
  end

  return false
end

function widget:Update(dt)
  -- If a menu or text input opened while a key was held, release everything so
  -- the camera doesn't keep drifting after focus returns.
  if ignoreInput() then
    clearHeldKeys()
    return
  end

  if not hasAnyCameraKey() then
    return
  end

  -- Defensive in case a stripped LuaUI headless stub omits the camera APIs.
  if not spGetCameraState or not spSetCameraState then
    return
  end

  local cs = spGetCameraState()
  if not cs then
    return
  end

  local d = dt or 0
  if d <= 0 then
    return
  end
  d = math.min(d, MAX_DT)

  local moveX = (pressed.right and 1 or 0) - (pressed.left and 1 or 0)
  local moveZ = (pressed.forward and 1 or 0) - (pressed.back and 1 or 0)
  local yaw   = (pressed.rotRight and 1 or 0) - (pressed.rotLeft and 1 or 0)

  -- Pan along the ground plane, aligned with the current camera yaw.
  if (moveX ~= 0 or moveZ ~= 0) and spGetCameraVectors then
    local cv = spGetCameraVectors()
    if cv and cv.forward and cv.right then
      local fx, fz = cv.forward[1], cv.forward[3]
      local rx, rz = cv.right[1], cv.right[3]

      local fLen = math.sqrt(fx * fx + fz * fz)
      local rLen = math.sqrt(rx * rx + rz * rz)
      if fLen > 1e-4 then fx, fz = fx / fLen, fz / fLen end
      if rLen > 1e-4 then rx, rz = rx / rLen, rz / rLen end

      local pan = PAN_SPEED * d
      cs.px = (cs.px or 0) + (moveX * rx + moveZ * fx) * pan
      cs.pz = (cs.pz or 0) + (moveX * rz + moveZ * fz) * pan
    end
  end

  -- Yaw rotation around the vertical axis. The overhead camera stores yaw in
  -- the opaque state field `ry` (radians); SetCameraState accepts the full
  -- state table back with a 0-second transition for immediate response.
  if yaw ~= 0 then
    cs.ry = (cs.ry or 0) + yaw * ROT_SPEED * d
  end

  spSetCameraState(cs, 0)
end