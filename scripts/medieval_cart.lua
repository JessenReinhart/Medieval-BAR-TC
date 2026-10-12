-- Lua Unit Script (LUS) for Medieval Supply Cart (civilian hauler)
-- Uses the reused wheeled carriage geometry (objects3d/0ad/medieval_catapult.obj,
-- single piece "base"). The cart has no weapons and never gathers, so this script
-- carries no aim/fire/gather state: it exposes idle behaviour plus a hauling
-- motion marker, published as a unit rules param exactly the way
-- scripts/medieval_catapult.lua publishes its aiming/firing markers.
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics: the cart now
-- creaks and rocks on its axles while under way, and tips over when destroyed.
-- optPiece() resolves every animated part to the root "base" piece on the
-- single-hull converted mesh, and safeCall() keeps each transform best-effort.
--
-- Threading contract (luarules/gadgets/unit_script.lua): StartMoving /
-- StopMoving are NOT thread-wrapped, so the rumble loop is spawned explicitly
-- with StartThread and StopMoving only signals and resets the pose.

local base = piece('base')

-- Rules param read back by probes/tests: 1 while the cart is under way, 0 idle.
local HAULING_PARAM = "medieval_cart_hauling"

local function setHauling(value)
  if type(Spring) ~= "table" or type(Spring.SetUnitRulesParam) ~= "function" then
    return
  end
  pcall(Spring.SetUnitRulesParam, unitID, HAULING_PARAM, value)
end

local function optPiece(name)
  local ok, p = pcall(piece, name)
  if ok and p then return p end
  return nil
end

local body = optPiece('torso') or base
local axle = optPiece('axle') or base
local wheel = optPiece('wheel') or base

-- Spinning the root piece would tumble the whole cart, so wheel rotation is
-- only applied when the mesh really carries a separate wheel piece.
local hasWheel = wheel ~= base

local function safeCall(fn, ...)
  if type(fn) ~= 'function' then return false end
  return (pcall(fn, ...))
end

local SIG_MOVE, SIG_DEATH = 1, 4

-- Loaded-cart rumble: a slow roll that lets the wheels ride the ruts.
local RUMBLE = {
  { pitch = 0.035, roll = 0.04, lift = 0.5 },
  { pitch = 0.0, roll = 0.0, lift = 0.0 },
  { pitch = -0.02, roll = -0.04, lift = 0.3 },
  { pitch = 0.0, roll = 0.0, lift = 0.0 },
}

local function restPose()
  safeCall(Turn, body, x_axis, 0, 6)
  safeCall(Turn, body, z_axis, 0, 6)
  safeCall(Move, body, y_axis, 0, 6)
  safeCall(Turn, base, x_axis, 0, 6)
  safeCall(Turn, base, z_axis, 0, 6)
  safeCall(Move, base, y_axis, 0, 6)
end

function script.Create()
  restPose()
  setHauling(0)
end

-- Motion marker plus the axle rumble; the cart has no combat or build call-ins.
function script.StartMoving()
  setHauling(1)
  Signal(SIG_MOVE)
  StartThread(function()
    SetSignalMask(SIG_MOVE)
    local phase = 1
    while true do
      local beat = RUMBLE[phase]
      safeCall(Turn, body, x_axis, beat.pitch, 6)
      safeCall(Turn, body, z_axis, beat.roll, 8)
      safeCall(Move, body, y_axis, beat.lift, 10)
      safeCall(Turn, axle, x_axis, beat.pitch * 0.5, 8)
      if hasWheel then
        safeCall(Spin, wheel, x_axis, 3.0, 0)
      end
      phase = phase % #RUMBLE + 1
      Sleep(200)
    end
  end)
end

function script.StopMoving()
  setHauling(0)
  Signal(SIG_MOVE)
  if hasWheel then
    safeCall(StopSpin, wheel, x_axis)
  end
  restPose()
end

-- == Defeat: the cart sheds its load and goes over on one axle ===============
function script.Killed(recentDamage, maxHealth)
  setHauling(0)
  Signal(SIG_MOVE)
  Signal(SIG_DEATH)
  SetSignalMask(SIG_DEATH)
  if hasWheel then
    safeCall(StopSpin, wheel, x_axis)
  end
  safeCall(Turn, base, z_axis, 1.1, 3)
  safeCall(Turn, body, z_axis, 1.1, 3)
  safeCall(Move, base, y_axis, -2.0, 2)
  safeCall(Move, body, y_axis, -2.0, 2)
  Sleep(300)
  return 1
end
