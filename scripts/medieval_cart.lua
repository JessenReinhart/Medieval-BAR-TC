-- Lua Unit Script (LUS) for Medieval Supply Cart (civilian hauler)
-- Uses the reused wheeled carriage geometry (objects3d/0ad/medieval_catapult.obj,
-- single piece "base"). The cart has no weapons and never gathers, so this script
-- carries no aim/fire/gather state: it exposes idle behaviour plus a hauling
-- motion marker, published as a unit rules param exactly the way
-- scripts/medieval_catapult.lua publishes its aiming/firing markers.

local base = piece('base')

-- Rules param read back by probes/tests: 1 while the cart is under way, 0 idle.
local HAULING_PARAM = "medieval_cart_hauling"

local function setHauling(value)
  if type(Spring) ~= "table" or type(Spring.SetUnitRulesParam) ~= "function" then
    return
  end
  pcall(Spring.SetUnitRulesParam, unitID, HAULING_PARAM, value)
end

function script.Create()
  setHauling(0)
end

-- Motion marker only; the cart has no combat or build call-ins.
function script.StartMoving()
  setHauling(1)
end

function script.StopMoving()
  setHauling(0)
end

function script.Killed(recentDamage, maxHealth)
  return 1
end
