function gadget:GetInfo()
  return {
    name = "Medieval Logistics, Tech & Fortifications",
    desc = "Road speed multipliers, blacksmith technology unlocks, and fortification validation",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local logistics = VFS.Include("scripts/medieval_logistics.lua")

local DEBUG_LOG = true

-- Synced state:
-- roads[teamID] = { [featureID] = { x = number, z = number } }
-- unlocked[teamID][techID] = true
local roads = {}
local unlocked = {}

local function syncTechParams(teamID)
  for techID in pairs(logistics.TECHS) do
    local flag = (unlocked[teamID] and unlocked[teamID][techID]) and 1 or 0
    Spring.SetGameRulesParam(string.format("team_%d_tech_%s", teamID, techID), flag)
  end
end

local function initTeam(teamID)
  roads[teamID] = roads[teamID] or {}
  unlocked[teamID] = unlocked[teamID] or {}
  syncTechParams(teamID)
end

local function echo(fmt, ...)
  if DEBUG_LOG and Spring and Spring.Echo then
    Spring.Echo(string.format(fmt, ...))
  end
end

function gadget:Initialize()
  roads = {}
  unlocked = {}
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
end

-- ---------------------------------------------------------------------------
-- Roads: tracked as features placed by villagers.
-- ---------------------------------------------------------------------------

function gadget:FeatureCreated(featureID, allyTeam)
  local fd = Spring and Spring.GetFeatureDefID and Spring.GetFeatureDefID(featureID)
  if not fd then return end
  local fDef = FeatureDefs and FeatureDefs[fd]
  if not fDef or fDef.name ~= "medieval_road" then return end
  local x, _, z = Spring.GetFeaturePosition(featureID)
  if not x then return end
  local owner = Spring.GetFeatureTeam and Spring.GetFeatureTeam(featureID)
  if owner == nil then owner = 0 end
  initTeam(owner)
  roads[owner][featureID] = { x = x, z = z }
  echo("PHASE3 ROAD placed ftr=%d team=%d x=%.0f z=%.0f", featureID, owner, x, z)
end

function gadget:FeatureDestroyed(featureID, allyTeam)
  for teamID, list in pairs(roads) do
    if list[featureID] then
      list[featureID] = nil
      echo("PHASE3 ROAD removed ftr=%d team=%d", featureID, teamID)
    end
  end
end

-- ---------------------------------------------------------------------------
-- Tech research: atomic unlock via GG.MedievalEconomy.Transact.
-- ---------------------------------------------------------------------------

local function researchTech(teamID, techID)
  initTeam(teamID)
  local economy = GG and GG.MedievalEconomy
  local stock = economy and economy.GetStockpiles and economy.GetStockpiles(teamID)
  local ok, reason = logistics.canResearch(unlocked[teamID], techID, stock, economy)
  if not ok then
    echo("PHASE3 TECH rejected team=%d tech=%s reason=%s", teamID, tostring(techID), tostring(reason))
    return false, reason
  end
  local t = logistics.TECHS[techID]
  if economy and economy.Transact then
    if not economy.Transact(teamID, t.cost) then
      echo("PHASE3 TECH rejected team=%d tech=%s reason=transact_failed", teamID, tostring(techID))
      return false, "transact_failed"
    end
  end
  unlocked[teamID] = logistics.applyUnlock(unlocked[teamID], techID)
  syncTechParams(teamID)
  echo("PHASE3 TECH researched team=%d tech=%s", teamID, techID)
  return true
end

-- Apply health/damage tech effects at unit completion (called from UnitFinished).
function gadget:UnitFinished(unitID, unitDefID, unitTeam)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return end
  local u = unlocked[unitTeam]
  if not u then return end
  local healthMult = logistics.healthMultiplier(u, def.name)
  if healthMult > 1.0 and Spring and Spring.GetUnitHealth then
    local hp, maxHp = Spring.GetUnitHealth(unitID)
    if maxHp and maxHp > 0 then
      Spring.SetUnitMaxHealth(unitID, maxHp * healthMult)
      Spring.SetUnitHealth(unitID, hp * healthMult)
      echo("PHASE3 TECH applied team=%d unit=%d def=%s hp_mult=%.2f", unitTeam, unitID, def.name, healthMult)
    end
  end
end

-- ---------------------------------------------------------------------------
-- Fortifications: validate costs at placement like recruitment does.
-- ---------------------------------------------------------------------------

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return true end
  local costs = logistics.getCost(def.name)
  if not costs then return true end
  local economy = GG and GG.MedievalEconomy
  if not economy or not economy.CanAfford then return true end
  if not economy.CanAfford(builderTeam, costs) then
    echo("PHASE3 FORT denied team=%d def=%s reason=cannot_afford", builderTeam, def.name)
    return false
  end
  return true
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID, attackerID, attackerDefID, attackerTeam)
  -- no persistent state keyed on destroyed buildings for now
end

-- ---------------------------------------------------------------------------
-- GG public API
-- ---------------------------------------------------------------------------

GG = GG or {}
GG.MedievalLogistics = {
  GetSpeedMultiplier = function(teamID, unitID)
    local u = Spring and Spring.GetUnitPosition and Spring.GetUnitPosition(unitID)
    if not u then return 1.0 end
    local x, _, z = Spring.GetUnitPosition(unitID)
    if not x then return 1.0 end
    local list = roads[teamID]
    if not list then return 1.0 end
    local onRoad = false
    for _, coord in pairs(list) do
      if logistics.isPositionOnRoad(x, z, { [0] = coord }) then
        onRoad = true
        break
      end
    end
    return logistics.speedMultiplier(onRoad)
  end,

  IsOnRoad = function(teamID, unitID)
    return GG.MedievalLogistics.GetSpeedMultiplier(teamID, unitID) > 1.0
  end,

  RoadCount = function(teamID)
    local count = 0
    for _ in pairs(roads[teamID] or {}) do count = count + 1 end
    return count
  end,

  CanResearch = function(teamID, techID)
    initTeam(teamID)
    local economy = GG and GG.MedievalEconomy
    local stock = economy and economy.GetStockpiles and economy.GetStockpiles(teamID)
    local ok = logistics.canResearch(unlocked[teamID], techID, stock, economy)
    return ok
  end,

  Research = function(teamID, techID)
    return researchTech(teamID, techID)
  end,

  IsResearched = function(teamID, techID)
    return (unlocked[teamID] or {})[techID] == true
  end,

  DamageMultiplier = function(teamID, unitName)
    return logistics.damageMultiplier(unlocked[teamID], unitName)
  end,

  HealthMultiplier = function(teamID, unitName)
    return logistics.healthMultiplier(unlocked[teamID], unitName)
  end,
}
