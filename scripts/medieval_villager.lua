-- Lua Unit Script (LUS) for the Medieval Villager (builder / gatherer).
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted 0 A.D. mesh is a single bind-pose hull, so optPiece() resolves
-- every animated part to the root "base" piece when no sub-piece exists, and
-- safeCall() keeps each transform best-effort on engine builds that do not
-- expose the piece animation call-ins.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (the trudge loop is spawned
--   with StartThread); StartBuilding / StopBuilding ARE thread-wrapped, so the
--   work cadence may Sleep directly in its own body.

local base = piece('base')

local function optPiece(name)
  local ok, p = pcall(piece, name)
  if ok and p then return p end
  return nil
end

local torso = optPiece('torso') or base
local tool = optPiece('weapon') or base

local function safeCall(fn, ...)
  if type(fn) ~= 'function' then return false end
  return (pcall(fn, ...))
end

local SIG_MOVE, SIG_WORK, SIG_DEATH = 1, 2, 4

-- Loaded trudge: the villager walks slower and heavier than a soldier.
local STRIDE = {
  { pitch = 0.06, roll = 0.05, lift = 0.8 },
  { pitch = 0.0, roll = 0.0, lift = 0.0 },
  { pitch = 0.06, roll = -0.05, lift = 0.8 },
  { pitch = 0.0, roll = 0.0, lift = 0.0 },
}

local function restPose()
  safeCall(Turn, torso, x_axis, 0, 6)
  safeCall(Turn, torso, z_axis, 0, 6)
  safeCall(Move, torso, y_axis, 0, 6)
  safeCall(Turn, base, x_axis, 0, 6)
  safeCall(Turn, base, z_axis, 0, 6)
  safeCall(Move, base, y_axis, 0, 6)
end

function script.Create()
  restPose()
end

-- == Locomotion: trudge bob while hauling loads across the settlement =======
function script.StartMoving()
  Signal(SIG_MOVE)
  StartThread(function()
    SetSignalMask(SIG_MOVE)
    local phase = 1
    while true do
      local step = STRIDE[phase]
      safeCall(Turn, torso, x_axis, step.pitch, 6)
      safeCall(Turn, torso, z_axis, step.roll, 6)
      safeCall(Move, torso, y_axis, step.lift, 8)
      phase = phase % #STRIDE + 1
      Sleep(170)
    end
  end)
end

function script.StopMoving()
  Signal(SIG_MOVE)
  restPose()
end

-- == Labour: swing the tool while constructing or harvesting ================
function script.StartBuilding()
  Signal(SIG_WORK)
  StartThread(function()
    SetSignalMask(SIG_WORK)
    while true do
      -- Raise the tool, then strike down.
      safeCall(Turn, torso, x_axis, -0.14, 10)
      safeCall(Turn, tool, x_axis, -0.5, 12)
      Sleep(260)
      safeCall(Turn, torso, x_axis, 0.20, 16)
      safeCall(Turn, tool, x_axis, 0.45, 16)
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
  safeCall(Turn, base, x_axis, 1.3, 3)
  safeCall(Turn, torso, x_axis, 1.3, 3)
  safeCall(Move, base, y_axis, -1.2, 2)
  safeCall(Move, torso, y_axis, -1.2, 2)
  Sleep(340)
  safeCall(Turn, base, z_axis, 0.4, 2)
  safeCall(Turn, torso, z_axis, 0.4, 2)
  Sleep(220)
  return 1
end
