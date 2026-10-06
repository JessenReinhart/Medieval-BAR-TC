function gadget:GetInfo()
  return {
    name = "Medieval Housing and Population",
    desc = "Computes population caps from town centers/houses and enforces population limits",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 2,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local housing = VFS.Include("scripts/medieval_housing.lua")

-- Synced state per team:
-- teamBuildings[teamID][defName] = count
-- teamPopulation[teamID] = current unit count
local teamBuildings = {}
local teamPopulation = {}

local function syncParams(teamID)
  local b = teamBuildings[teamID] or {}
  local cap = housing.computeCap(b)
  local pop = teamPopulation[teamID] or 0
  Spring.SetGameRulesParam(string.format("team_%d_pop_cap", teamID), cap)
  Spring.SetGameRulesParam(string.format("team_%d_population", teamID), pop)
end

local function initTeam(teamID)
  if not teamBuildings[teamID] then teamBuildings[teamID] = {} end
  if not teamPopulation[teamID] then teamPopulation[teamID] = 0 end
  syncParams(teamID)
end

function gadget:Initialize()
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  initTeam(teamID)
  local def = UnitDefs[unitDefID]
  if not def then return end
  local name = def.name

  if housing.POP_PROVIDERS[name] then
    teamBuildings[teamID][name] = (teamBuildings[teamID][name] or 0) + 1
    syncParams(teamID)
  end

  if housing.unitConsumesPop(name) == 1 then
    teamPopulation[teamID] = (teamPopulation[teamID] or 0) + 1
    syncParams(teamID)
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  local def = UnitDefs[unitDefID]
  if not def or not teamBuildings[teamID] then return end
  local name = def.name

  if housing.POP_PROVIDERS[name] then
    local cur = teamBuildings[teamID][name] or 0
    if cur > 0 then teamBuildings[teamID][name] = cur - 1 end
    syncParams(teamID)
  end

  if housing.unitConsumesPop(name) == 1 then
    local cur = teamPopulation[teamID] or 0
    if cur > 0 then teamPopulation[teamID] = cur - 1 end
    syncParams(teamID)
  end
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  initTeam(builderTeam)
  local def = UnitDefs[unitDefID]
  if not def then return true end
  local name = def.name

  if housing.unitConsumesPop(name) == 1 then
    local b = teamBuildings[builderTeam] or {}
    local cap = housing.computeCap(b)
    local cur = teamPopulation[builderTeam] or 0
    if not housing.canSupport(cur, cap, 1) then
      return false
    end
  end
  return true
end

GG = GG or {}
GG.MedievalHousing = {
  GetCap = function(teamID)
    initTeam(teamID)
    return housing.computeCap(teamBuildings[teamID] or {})
  end,
  GetPopulation = function(teamID)
    initTeam(teamID)
    return teamPopulation[teamID] or 0
  end,
}
