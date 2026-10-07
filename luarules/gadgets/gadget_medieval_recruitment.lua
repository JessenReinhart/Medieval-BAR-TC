function gadget:GetInfo()
  return {
    name = "Medieval Recruitment",
    desc = "Intercepts building placement and unit training for discrete resource cost checks and pop-cap enforcement",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local housing = VFS.Include("scripts/medieval_housing.lua")

local COST_PREFIX = "resource_cost_"

-- Spring engine exposes custom parameters under either def.customParams or def.customparams.
-- Check both so neither loader variant slips through.
local function getCustomParams(def)
  if not def then return nil end
  return def.customParams or def.customparams
end

local function unitCosts(def)
  local cp = getCustomParams(def)
  if not cp then return nil end
  local costs = nil
  for key, value in pairs(cp) do
    local res = string.match(key, "^" .. COST_PREFIX .. "(%a+)$")
    if res then
      -- Runtime customParams values are strings (Spring CustomMap); coerce.
      local amount = tonumber(value)
      if amount and amount > 0 then
        costs = costs or {}
        costs[res] = amount
      end
    end
  end
  return costs
end

-- Resolve internal unit definition name reliably: try name, then id lookup.
local function internalName(unitDefID)
  local def = UnitDefs[unitDefID]
  if not def then return nil end
  -- Recoil engine populates UnitDefs[id].name as internal or short name
  return def.name
end

-- Pop-cap gate shared with housing; military and villager units each cost 1 pop.
local function popBlocked(teamID, defName)
  if not GG or not GG.MedievalHousing then return false end
  if housing.unitConsumesPop(defName) ~= 1 then return false end
  local cur = GG.MedievalHousing.GetPopulation(teamID) or 0
  local cap = GG.MedievalHousing.GetCap(teamID) or 0
  return not housing.canSupport(cur, cap, 1)
end

local chargedUnits = {}

function gadget:Initialize()
  chargedUnits = {}
end

-- Block building placement that cannot be paid for or supported by housing.
function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  local def = UnitDefs[unitDefID]
  if not def then return true end

  if popBlocked(builderTeam, internalName(unitDefID)) then return false end

  if not GG or not GG.MedievalEconomy then return true end
  local costs = unitCosts(def)
  if costs and not GG.MedievalEconomy.CanAfford(builderTeam, costs) then
    return false
  end
  return true
end

-- UnitFinished fires for builder-constructed buildings when fully completed.
-- Debit discrete construction cost atomically; destroy unit if team can no longer pay.
function gadget:UnitFinished(unitID, unitDefID, unitTeam)
  if chargedUnits[unitID] then return end
  local def = UnitDefs[unitDefID]
  if not def then return end

  local costs = unitCosts(def)
  if not costs then return end

  if not GG or not GG.MedievalEconomy then return end
  if not GG.MedievalEconomy.Transact(unitTeam, costs) then
    -- Cannot afford at completion; tear down
    Spring.DestroyUnit(unitID, true, true)
    return
  end
  chargedUnits[unitID] = true
end

-- UnitFromFactory fires when a factory produces a unit (infantry, archer, cavalry, villager).
-- Enforces pop cap and debits recruitment resources at birth.
function gadget:UnitFromFactory(unitID, unitDefID, unitTeam, factID, factDefID, userOrders)
  local name = internalName(unitDefID)
  if popBlocked(unitTeam, name) then
    Spring.DestroyUnit(unitID, true, true)
    return
  end

  local def = UnitDefs[unitDefID]
  local costs = unitCosts(def)
  if costs and GG and GG.MedievalEconomy then
    if not GG.MedievalEconomy.Transact(unitTeam, costs) then
      Spring.DestroyUnit(unitID, true, true)
      return
    end
  end
  chargedUnits[unitID] = true
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  chargedUnits[unitID] = nil
end

GG = GG or {}
GG.MedievalRecruitment = {
  UnitCosts = unitCosts,

  CanRecruit = function(teamID, defName)
    local def = UnitDefNames and UnitDefNames[defName]
    if not def then return false end
    if popBlocked(teamID, defName) then return false end
    local costs = unitCosts(def)
    if costs and GG and GG.MedievalEconomy and not GG.MedievalEconomy.CanAfford(teamID, costs) then
      return false
    end
    return true
  end,
}
