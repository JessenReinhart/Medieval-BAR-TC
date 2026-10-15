-- Lua Unit Script (LUS) for the Medieval Villager (builder / gatherer).
--
-- Uses 0ad model geometry (objects3d/0ad/medieval_villager.obj).
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted 0 A.D. mesh exposes per-bone pieces and no "base" hull, so every
-- bone is resolved through optPiece(): the canonical humanoid bone is probed
-- first, then the 0 A.D. alias the OBJ actually carries, and finally the resolved
-- root hull (the hip). safeCall() keeps
-- each transform best-effort on engine builds that do not expose the piece
-- animation call-ins.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (the trudge loop is spawned
--   with StartThread); StartBuilding / StopBuilding ARE thread-wrapped, so the
--   work cadence may Sleep directly in its own body.

-- Optional sub-pieces. `piece()` raises for an unknown name, so probe with pcall.
local function optPiece(name)
  local ok, p = pcall(piece, name)
  if ok and p then return p end
  return nil
end

-- Root hull. The converted OBJ is articulated (per-bone pieces, no "base" hull),
-- so probe the bones the exporter actually emits, then the engine root name.
local base = optPiece('base') or optPiece('hip') or optPiece('root') or optPiece('spine')
if not base then
  base = optPiece('$$$___magic___$$$.')  -- Recoil model root; nil if not exposed
end

-- == Articulated humanoid rig ================================================
-- canonical bone -> alias the 0 A.D. OBJ may carry -> root hull.
local hip = optPiece('hip') or optPiece('torso') or base
local spine = optPiece('spine') or optPiece('torso') or base
local chest = optPiece('chest') or optPiece('torso') or base
local head = optPiece('head') or base
local thigh_l = optPiece('thigh_l') or optPiece('l_thigh') or optPiece('l_leg') or base
local leg_l = optPiece('leg_l') or optPiece('l_leg') or base
local foot_l = optPiece('foot_l') or optPiece('l_foot') or base
local thigh_r = optPiece('thigh_r') or optPiece('r_thigh') or optPiece('r_leg') or base
local leg_r = optPiece('leg_r') or optPiece('r_leg') or base
local foot_r = optPiece('foot_r') or optPiece('r_foot') or base
local arm_l = optPiece('arm_l') or optPiece('l_arm') or optPiece('arm') or base
local forearm_l = optPiece('forearm_l') or optPiece('l_forearm') or optPiece('l_arm') or optPiece('arm') or base
local arm_r = optPiece('arm_r') or optPiece('r_arm') or optPiece('arm') or base
local forearm_r = optPiece('forearm_r') or optPiece('r_forearm') or optPiece('r_arm') or optPiece('arm') or base
-- The hoe/sickle the villager swings while working or gathering.
local weapon = optPiece('weapon') or base
local shield = optPiece('shield') or base

-- Distinct resolved pieces only: on a single-hull mesh every bone *is* `base`.
local PARTS = {}
do
  local seen = {}
  local list = {
    hip, spine, chest, head,
    thigh_l, leg_l, foot_l, thigh_r, leg_r, foot_r,
    arm_l, forearm_l, arm_r, forearm_r, weapon, shield,
  }
  for i = 1, #list do
    local p = list[i]
    if p and not seen[p] then
      seen[p] = true
      PARTS[#PARTS + 1] = p
    end
  end
end

local function safeCall(fn, ...)
  if type(fn) ~= 'function' then return false end
  return (pcall(fn, ...))
end

local SIG_MOVE, SIG_WORK, SIG_DEATH = 1, 2, 4

-- Current clip name, declared here because the playback thread and the
-- StartMoving / StopMoving / StartBuilding / StopBuilding / Killed call-ins all
-- write it.
local currentClip = "idle"
local lastDrivenClip = nil

-- == Baked-clip playback (Phase 7 Slice 12) ==================================
-- scripts/animdata/medieval_villager.lua holds world-space pose frames for
-- walk / run / idle / attack_melee / build / death. scripts/anim_player.lua
-- turns them into Turn/Move calls on the mesh's pieces.
--
-- The villager gathers and builds through the same `build` clip: the bake
-- carries no separate gather cycle. Everything is pcall-wrapped: a build with
-- no filesystem, no bake bundle or no piece call-ins leaves animCtx nil and the
-- procedural trudge / labour cadence below takes over.
local function loadModule(path)
  local inc = include
  if type(inc) ~= "function" then
    return nil, "include unavailable"
  end
  -- include() resolves paths against scripts/ and runs the chunk in this
  -- unit's environment, so drop the scripts/ prefix the callers carry. The
  -- old VFS loader is gone: a VFS chunk executes in the wrong environment.
  local rel = type(path) == "string" and path:gsub("^scripts[/\\]", "") or path
  local ok, value = pcall(inc, rel)
  if not ok then
    return nil, tostring(value)
  end
  if type(value) ~= "table" then
    return nil, "module returned " .. type(value)
  end
  return value
end

local animPlayer, animClips = nil, nil
local animFailReason = nil
do
  local mod, perr = loadModule("scripts/anim_player.lua")
  if type(mod) == "table" then
    animPlayer = mod
    local clips, cerr = loadModule("scripts/animdata/medieval_villager.lua")
    if type(clips) == "table" then
      animClips = clips
    else
      animFailReason = cerr or "clips load failed"
    end
  else
    animFailReason = perr or "anim_player load failed"
  end
end

local bakedNames = {}
local animCtx = nil
do
  if animPlayer and type(animClips) == "table" then
    if type(animPlayer.isLooping) == "function" then
      local baseIsLooping = animPlayer.isLooping
      animPlayer.isLooping = function(clip)
        if clip == "build" then return true end
        return baseIsLooping(clip)
      end
    end
    local ctx = animPlayer.new()
    animPlayer.setClips(ctx, animClips)
    animPlayer.setPrimitives(ctx, Turn, Move)
    animPlayer.setSpeed(ctx, 14)
    animPlayer.bindRest(ctx, animClips.idle)

    -- Rigid bone-as-piece port: bind every exact bone name the idle frame
    -- carries to its own resolved piece (optPiece maps the 0 A.D. alias chain
    -- to the emitted piece). Each engine handle is bound once, so two alias
    -- names sharing a piece cannot clobber each other, and props like the hoe
    -- or shield -- which fall back to the hull but never appear in a frame --
    -- can never hijack the hip channel: they stay in PARTS for the procedural
    -- trudge / labour loops.
    local restFrame = (animClips.idle and animClips.idle.frames
      and animClips.idle.frames[1]) or {}
    local bound = 0
    local seen = {}
    for name, _ in pairs(restFrame) do
      local handle = optPiece(name)
      if handle and not seen[handle] then
        seen[handle] = true
        bakedNames[#bakedNames + 1] = name
        animPlayer.bindPiece(ctx, name, handle)
        bound = bound + 1
      end
    end
    -- Single-hull mesh: no bone name resolved to a piece, so pin the hull to
    -- the canonical hip the procedural fallback still animates.
    if bound == 0 then
      animPlayer.bindPiece(ctx, "hip", base)
    end
    animCtx = ctx
  end
end

-- One-time init diagnostic, logged once per unit at chunk scope: proves the
-- baked 0 A.D. clips initialised, or the procedural trudge took over. Uses
-- Spring.Echo when present and no-ops in a bare-Lua test harness.
do
  local spring = type(Spring) == "table" and Spring or nil
  if spring and type(spring.Echo) == "function" then
    if animCtx then
      local n = 0
      for _ in pairs(animClips) do n = n + 1 end
      spring.Echo("MEDIEVAL ANIM baked init unit=" .. tostring(unitID) .. " clips=" .. n)
    else
      spring.Echo("MEDIEVAL ANIM fallback unit=" .. tostring(unitID) .. " reason=" .. tostring(animFailReason or "none"))
    end
  end
end

-- Player slot callbacks, bound once. The driver drains these into safeCall.
local animTurnSlots, animMoveSlots = {}, {}
local animFrames = 0

local function say(msg)
  pcall(function()
    if Spring and Spring.Echo then Spring.Echo(msg) else print(msg) end
  end)
end

do
  if animPlayer then
    -- Rebuild the primitive set against the collector tables.
    local ctx = animCtx
    if ctx then
      animPlayer.setPrimitives(ctx,
        function(handle, axis, value, speed)
          animTurnSlots[#animTurnSlots + 1] = { handle, axis, value, speed }
        end,
        function(handle, axis, value, speed)
          animMoveSlots[#animMoveSlots + 1] = { handle, axis, value, speed }
        end)
    end
  end
end

local function driveClip(clipName, dtMs)
  if not animCtx then return 0 end
  -- The player keeps one shared clock, so a clip's timeline only resets when
  -- the switch actually changes clip; restarting a one-shot from zero would
  -- otherwise rewind the loop it was layered on top of.
  if lastDrivenClip ~= clipName then
    animPlayer.reset(animCtx)
    lastDrivenClip = clipName
  elseif animPlayer.elapsed(animCtx, clipName) > 100000 then
    animPlayer.reset(animCtx)  -- wrap the accumulating clock, never diverge
  end
  for i = #animTurnSlots, 1, -1 do animTurnSlots[i] = nil end
  for i = #animMoveSlots, 1, -1 do animMoveSlots[i] = nil end

  local driven, done = animPlayer.emit(animCtx, clipName, animPlayer.elapsed(animCtx, clipName))
  for i = 1, #animTurnSlots do
    local s = animTurnSlots[i]
    safeCall(Turn, s[1], s[2], s[3], s[4])
  end
  for i = 1, #animMoveSlots do
    local s = animMoveSlots[i]
    safeCall(Move, s[1], s[2], s[3], s[4])
  end
  animPlayer.advance(animCtx, dtMs)

  if driven > 0 then
    animFrames = animFrames + 1
    if animFrames <= 5 then
      say(string.format("LUS ANIM villager %s driven=%d", clipName, driven))
    end
  end
  return driven, done
end

-- Exactly one playback thread per unit; StartMoving / StartBuilding spawns it.
local animThreadLive = false
local function startAnimThread()
  if not animCtx then return false end
  if not animThreadLive then
    animThreadLive = true
    StartThread(function()
      SetSignalMask(SIG_DEATH)
      while true do
        driveClip(currentClip, 33)
        Sleep(1)
      end
    end)
  end
  return true
end

local function restPose()
  for i = 1, #PARTS do
    local p = PARTS[i]
    safeCall(Turn, p, x_axis, 0, 6)
    safeCall(Turn, p, y_axis, 0, 6)
    safeCall(Turn, p, z_axis, 0, 6)
    safeCall(Move, p, x_axis, 0, 6)
    safeCall(Move, p, y_axis, 0, 6)
    safeCall(Move, p, z_axis, 0, 6)
  end
  -- The rigid bone-as-piece bind drives shoulder / hand / neck / finger
  -- pieces too, so clear them as well or a stopped unit freezes mid-pose.
  for i = 1, #bakedNames do
    local p = optPiece(bakedNames[i])
    if p then
      safeCall(Turn, p, x_axis, 0, 6)
      safeCall(Turn, p, y_axis, 0, 6)
      safeCall(Turn, p, z_axis, 0, 6)
      safeCall(Move, p, x_axis, 0, 6)
      safeCall(Move, p, y_axis, 0, 6)
      safeCall(Move, p, z_axis, 0, 6)
    end
  end
end

function script.Create()
  restPose()
end

-- == Locomotion: loaded trudge while hauling loads across the settlement =====
-- Slower and heavier than a soldier: short thigh swing, low bob, forward lean.
function script.StartMoving()
  Signal(SIG_MOVE)
  -- Primary: the baked `walk` clip, driven by scripts/anim_player.lua on the
  -- playback thread. Fallback: the procedural trudge below, used when the
  -- build ships no bake bundle or no player module. StartMoving is not
  -- thread-wrapped by the framework, so it spawns its own loop here.
  currentClip = "walk"
  StartThread(function()
    SetSignalMask(SIG_MOVE)
    if startAnimThread() then return end
    while true do
      -- Left contact: left thigh forward, right thigh back, arms counter-swing.
      safeCall(Turn, thigh_l, x_axis, 0.26, 6)
      safeCall(Turn, leg_l, x_axis, -0.18, 6)
      safeCall(Turn, foot_l, x_axis, 0.08, 6)
      safeCall(Turn, thigh_r, x_axis, -0.26, 6)
      safeCall(Turn, leg_r, x_axis, -0.03, 6)
      safeCall(Turn, foot_r, x_axis, 0.04, 6)
      safeCall(Turn, arm_l, x_axis, -0.18, 6)
      safeCall(Turn, forearm_l, x_axis, -0.14, 6)
      safeCall(Turn, arm_r, x_axis, 0.18, 6)
      safeCall(Turn, forearm_r, x_axis, -0.20, 6)
      safeCall(Turn, chest, x_axis, 0.10, 6)
      safeCall(Turn, spine, z_axis, 0.04, 6)
      safeCall(Move, hip, y_axis, 0.62, 6)
      Sleep(170)
      -- Passing pose: the load settles back onto the hips.
      safeCall(Turn, thigh_l, x_axis, 0.01, 6)
      safeCall(Turn, leg_l, x_axis, -0.05, 6)
      safeCall(Turn, foot_l, x_axis, 0.0, 6)
      safeCall(Turn, thigh_r, x_axis, -0.01, 6)
      safeCall(Turn, leg_r, x_axis, -0.07, 6)
      safeCall(Turn, foot_r, x_axis, -0.02, 6)
      safeCall(Turn, arm_l, x_axis, 0.0, 6)
      safeCall(Turn, forearm_l, x_axis, -0.06, 6)
      safeCall(Turn, arm_r, x_axis, 0.0, 6)
      safeCall(Turn, forearm_r, x_axis, -0.06, 6)
      safeCall(Turn, chest, x_axis, 0.04, 6)
      safeCall(Turn, spine, z_axis, 0.0, 6)
      safeCall(Move, hip, y_axis, 0.0, 6)
      Sleep(170)
      -- Right contact: mirror of the left.
      safeCall(Turn, thigh_l, x_axis, -0.26, 6)
      safeCall(Turn, leg_l, x_axis, -0.03, 6)
      safeCall(Turn, foot_l, x_axis, 0.04, 6)
      safeCall(Turn, thigh_r, x_axis, 0.26, 6)
      safeCall(Turn, leg_r, x_axis, -0.18, 6)
      safeCall(Turn, foot_r, x_axis, 0.08, 6)
      safeCall(Turn, arm_l, x_axis, 0.18, 6)
      safeCall(Turn, forearm_l, x_axis, -0.20, 6)
      safeCall(Turn, arm_r, x_axis, -0.18, 6)
      safeCall(Turn, forearm_r, x_axis, -0.14, 6)
      safeCall(Turn, chest, x_axis, 0.10, 6)
      safeCall(Turn, spine, z_axis, -0.04, 6)
      safeCall(Move, hip, y_axis, 0.62, 6)
      Sleep(170)
      -- Passing pose again.
      safeCall(Turn, thigh_l, x_axis, -0.01, 6)
      safeCall(Turn, leg_l, x_axis, -0.07, 6)
      safeCall(Turn, foot_l, x_axis, -0.02, 6)
      safeCall(Turn, thigh_r, x_axis, 0.01, 6)
      safeCall(Turn, leg_r, x_axis, -0.05, 6)
      safeCall(Turn, foot_r, x_axis, 0.0, 6)
      safeCall(Turn, arm_l, x_axis, 0.0, 6)
      safeCall(Turn, forearm_l, x_axis, -0.06, 6)
      safeCall(Turn, arm_r, x_axis, 0.0, 6)
      safeCall(Turn, forearm_r, x_axis, -0.06, 6)
      safeCall(Turn, chest, x_axis, 0.04, 6)
      safeCall(Turn, spine, z_axis, 0.0, 6)
      safeCall(Move, hip, y_axis, 0.0, 6)
      Sleep(170)
    end
  end)
end

function script.StopMoving()
  Signal(SIG_MOVE)
  -- StopMoving is not thread-wrapped, so it may only Signal and reset the pose;
  -- the playback thread picks up `idle` on its next tick.
  currentClip = "idle"
  restPose()
end

-- == Labour: gather / build, driven by the baked `build` clip ================
-- Primary: the baked `build` loop. The villager gathers through the same clip,
-- as the bake carries no separate gather cycle. Fallback: the procedural bob
-- below, used when the build ships no bake bundle or no player module.
function script.StartBuilding()
  Signal(SIG_WORK)
  currentClip = "build"
  StartThread(function()
    SetSignalMask(SIG_WORK)
    if startAnimThread() then return end
    while true do
      -- Raise: torso and arms pitch back and up, tool cocked over the shoulder.
      safeCall(Turn, chest, x_axis, -0.14, 10)
      safeCall(Turn, spine, x_axis, -0.06, 10)
      safeCall(Turn, arm_l, x_axis, -0.30, 10)
      safeCall(Turn, forearm_l, x_axis, -0.22, 10)
      safeCall(Turn, arm_r, x_axis, -0.30, 10)
      safeCall(Turn, forearm_r, x_axis, -0.22, 10)
      safeCall(Turn, weapon, x_axis, -0.5, 12)
      safeCall(Turn, hip, x_axis, -0.08, 10)
      safeCall(Move, hip, y_axis, 0.12, 10)
      Sleep(260)
      -- Strike / gather: the torso folds over the work and the arms drive down.
      safeCall(Turn, chest, x_axis, 0.20, 16)
      safeCall(Turn, spine, x_axis, 0.10, 16)
      safeCall(Turn, arm_l, x_axis, 0.35, 16)
      safeCall(Turn, forearm_l, x_axis, 0.16, 16)
      safeCall(Turn, arm_r, x_axis, 0.35, 16)
      safeCall(Turn, forearm_r, x_axis, 0.16, 16)
      safeCall(Turn, weapon, x_axis, 0.45, 16)
      safeCall(Turn, hip, x_axis, 0.14, 16)
      safeCall(Move, hip, y_axis, -0.18, 16)
      Sleep(180)
    end
  end)
end

function script.StopBuilding()
  Signal(SIG_WORK)
  currentClip = "idle"
  restPose()
end

-- == Defeat: an unarmed civilian simply crumples forward ====================
function script.Killed(recentDamage, maxHealth)
  Signal(SIG_MOVE)
  Signal(SIG_WORK)
  Signal(SIG_DEATH)
  SetSignalMask(SIG_DEATH)
  -- Primary: the baked `death` one-shot, held on its last frame while the
  -- engine waits out the thread. Fallback: the procedural crumple below.
  if animCtx then
    animPlayer.reset(animCtx)
    while true do
      local _driven, done = driveClip("death", 33)
      if done then break end
      Sleep(1)
    end
    return 1
  end
  -- The knees give way first, then the torso folds onto the ground.
  safeCall(Turn, thigh_l, x_axis, 0.5, 3)
  safeCall(Turn, thigh_r, x_axis, 0.42, 3)
  safeCall(Turn, leg_l, x_axis, -0.8, 3)
  safeCall(Turn, leg_r, x_axis, -0.7, 3)
  safeCall(Turn, hip, x_axis, 1.3, 3)
  safeCall(Turn, hip, z_axis, 0.4, 3)
  safeCall(Turn, chest, x_axis, 0.45, 3)
  safeCall(Turn, head, x_axis, 0.5, 4)
  safeCall(Turn, arm_l, x_axis, 0.6, 3)
  safeCall(Turn, arm_r, x_axis, 0.5, 3)
  safeCall(Turn, weapon, x_axis, 0.4, 3)
  safeCall(Move, hip, y_axis, -1.2, 2)
  Sleep(340)
  -- Settle face down with the load spilled beside the body.
  safeCall(Turn, hip, x_axis, 1.5, 2)
  safeCall(Turn, hip, z_axis, 0.5, 2)
  safeCall(Turn, chest, x_axis, 0.15, 2)
  safeCall(Turn, arm_l, x_axis, 0.2, 2)
  safeCall(Turn, arm_r, x_axis, 0.15, 2)
  safeCall(Move, hip, y_axis, -1.5, 2)
  Sleep(220)
  return 1
end
