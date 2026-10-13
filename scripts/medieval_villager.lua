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
end

function script.Create()
  restPose()
end

-- == Locomotion: loaded trudge while hauling loads across the settlement =====
-- Slower and heavier than a soldier: short thigh swing, low bob, forward lean.
function script.StartMoving()
  Signal(SIG_MOVE)
  StartThread(function()
    SetSignalMask(SIG_MOVE)
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
  restPose()
end

-- == Labour: gather / build bob -- torso and arms pitch up, then down ========
function script.StartBuilding()
  Signal(SIG_WORK)
  StartThread(function()
    SetSignalMask(SIG_WORK)
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
  restPose()
end

-- == Defeat: an unarmed civilian simply crumples forward ====================
function script.Killed(recentDamage, maxHealth)
  Signal(SIG_MOVE)
  Signal(SIG_WORK)
  Signal(SIG_DEATH)
  SetSignalMask(SIG_DEATH)
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