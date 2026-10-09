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
local recruit = VFS.Include("scripts/medieval_recruitment.lua")

local COST_PREFIX = "resource_cost_"
-- Observability flag: echoes one upkeep line per team per tick into the game log.
local UPKEEP_DEBUG = true

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
  if not unitDefID then return nil end
  local def = UnitDefs and UnitDefs[unitDefID]
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

-- Equipment gate: high-tier units need gear in the team's equipment stock,
-- published by gadget_production_chains.lua as GG.MedievalLogistics.equipmentStock.
-- A missing stock table blocks every unit that carries a requirement.
local function equipmentBlocked(teamID, defName)
  if not recruit or not recruit.equipmentFor then return false end
  if not recruit.equipmentFor(defName) then return false end
  local api = GG and GG.MedievalLogistics
  local stock = recruit.teamEquipmentStock and recruit.teamEquipmentStock(api, teamID) or nil
  return not recruit.hasEquipment(stock, defName)
end

-- Tech gate: advanced units stay locked until the tech that unlocks them is
-- researched. The prerequisite is resolved through the logistics API
-- (GG.MedievalLogistics.TechUnlockPrereq / IsTechUnlocked) when available and
-- falls back to the pure registry in scripts/medieval_recruitment.lua.
local function techBlocked(teamID, defName)
  if not recruit or not recruit.techPrereqFor then return false end
  local api = GG and GG.MedievalLogistics
  local prereq = recruit.techPrereqFor(defName)
  if api and type(api.TechUnlockPrereq) == "function" then
    prereq = api.TechUnlockPrereq(defName) or prereq
  end
  if not prereq then return false end
  if api and type(api.IsTechUnlocked) == "function" then
    return not api.IsTechUnlocked(teamID, prereq)
  end
  if api and type(api.IsResearched) == "function" then
    return not api.IsResearched(teamID, prereq)
  end
  -- No tech registry published: fail closed so advanced units cannot leak.
  return true
end

local chargedUnits = {}
-- Last team_<id>_starving marker published per team; nil until the first tick.
local starvingState = {}

function gadget:Initialize()
  chargedUnits = {}
  starvingState = {}
end

-- Block building placement that cannot be paid for or supported by housing.
function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  local def = UnitDefs[unitDefID]
  if not def then return true end

  if popBlocked(builderTeam, internalName(unitDefID)) then return false end
  if techBlocked(builderTeam, internalName(unitDefID)) then return false end
  if equipmentBlocked(builderTeam, internalName(unitDefID)) then return false end

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
  -- Guard against double charging when UnitFinished also fires for this unit.
  if chargedUnits[unitID] then return end
  local name = internalName(unitDefID)
  if popBlocked(unitTeam, name) then
    Spring.DestroyUnit(unitID, true, true)
    return
  end
  if equipmentBlocked(unitTeam, name) then
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

-- ---------------------------------------------------------------------------
-- Phase-3: standing-army food upkeep and starvation
-- ---------------------------------------------------------------------------

local UPKEEP_TICK_FRAMES = tonumber(recruit and recruit.UPKEEP_TICK_FRAMES) or 90
if not (UPKEEP_TICK_FRAMES > 0) then UPKEEP_TICK_FRAMES = 90 end

local function economyAPI()
  if not GG or not GG.MedievalEconomy then return nil end
  return GG.MedievalEconomy
end

-- Publish team_<id>_starving, writing the gamerule param only on change.
local function setStarving(teamID, starving)
  local marker = starving and 1 or 0
  if starvingState[teamID] ~= marker then
    starvingState[teamID] = marker
    if Spring and Spring.SetGameRulesParam then
      Spring.SetGameRulesParam(string.format("team_%d_starving", teamID), marker)
    end
  end
  return marker
end

-- Standing-army member: military names carry the medieval_ prefix and an
-- upkeep rate, which excludes villagers plus every building and town.
local function isArmyUnit(name)
  if type(name) ~= "string" then return false end
  if not string.find(name, "^medieval_") then return false end
  if not recruit or not recruit.isMilitary then return false end
  return recruit.isMilitary(name)
end

-- Live army of a team as parallel lists: def names and unit IDs.
local function armyOf(teamID)
  local names, ids = {}, {}
  if not Spring or not Spring.GetTeamUnits then return names, ids end
  for _, uid in ipairs(Spring.GetTeamUnits(teamID) or {}) do
    local name = nil
    if Spring.GetUnitDefID then name = internalName(Spring.GetUnitDefID(uid)) end
    if isArmyUnit(name) then
      local hp = Spring.GetUnitHealth and Spring.GetUnitHealth(uid)
      if hp and hp > 0 then
        names[#names + 1] = name
        ids[#ids + 1] = uid
      end
    end
  end
  return names, ids
end

-- Food owed by a team for one tick, plus the folded unit counts behind it.
local function teamUpkeep(teamID)
  local names = armyOf(teamID)
  local counts = (recruit and recruit.armyCounts) and recruit.armyCounts(names) or {}
  local total = (recruit and recruit.armyUpkeep) and recruit.armyUpkeep(counts) or 0
  return total, counts
end

-- Mild attrition while starving: up to 5% of current HP, never lethal, so the
-- standing army shrinks in strength instead of vanishing.
local function starveUnits(ids)
  if not Spring or not Spring.SetUnitHealth then return end
  for _, uid in ipairs(ids or {}) do
    local hp = Spring.GetUnitHealth and Spring.GetUnitHealth(uid)
    if hp and hp > 0 and recruit and recruit.starvedHealth then
      local newHp = recruit.starvedHealth(hp)
      if newHp and newHp > 0 and newHp < hp then
        Spring.SetUnitHealth(uid, newHp)
      end
    end
  end
end

-- One upkeep tick per team: charge food, publish the starving marker, and
-- apply attrition when the team cannot pay.
local function upkeepTick()
  if not Spring or not Spring.GetTeamList then return end
  local economy = economyAPI()
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    local names, ids = armyOf(teamID)
    local counts = (recruit and recruit.armyCounts) and recruit.armyCounts(names) or {}
    local total = (recruit and recruit.armyUpkeep) and recruit.armyUpkeep(counts) or 0

    local starving = false
    if total > 0 then
      local costs = { food = total }
      if economy and economy.CanAfford and economy.CanAfford(teamID, costs) then
        if economy.Transact then
          -- Transact re-checks the balance, so a concurrent spend cannot overdraw.
          starving = not economy.Transact(teamID, costs)
        else
          starving = true
        end
      else
        starving = true
      end
    end

    setStarving(teamID, starving)
    if starving then starveUnits(ids) end

    -- Headless/probe observability: upkeep is otherwise invisible because the
    -- starving marker is a game-rules param, not a log line.
    if UPKEEP_DEBUG and Spring.Echo then
      local food = "?"
      if economy and economy.GetResource then
        food = tostring(economy.GetResource(teamID, "food") or "?")
      end
      Spring.Echo(string.format(
        "PHASE2 UPKEEP team=%d army=%d cost=%d paid=%s food_left=%s starving=%s",
        teamID, #ids, total, tostring(not starving), food, tostring(starving)))
    end
  end
end

-- Seed the marker at game start so team_<id>_starving is readable before the
-- first upkeep tick instead of being absent.
function gadget:GameStart()
  if not Spring or not Spring.GetTeamList then return end
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    setStarving(teamID, false)
  end
end

function gadget:GameFrame(frame)
  if type(frame) ~= "number" or frame <= 0 then return end
  if (frame % UPKEEP_TICK_FRAMES) ~= 0 then return end
  upkeepTick()
end

GG = GG or {}
GG.MedievalRecruitment = {
  UnitCosts = unitCosts,

  -- Food owed by a team for the next upkeep tick.
  Upkeep = function(teamID)
    local total = teamUpkeep(teamID)
    return total or 0
  end,

  IsStarving = function(teamID)
    return starvingState[teamID] == 1
  end,

  -- Force an upkeep pass (used by probes; GameFrame drives it in-game).
  RunUpkeepTick = upkeepTick,

  CanRecruit = function(teamID, defName)
    local def = UnitDefNames and UnitDefNames[defName]
    if not def then return false end
    if popBlocked(teamID, defName) then return false end
    if techBlocked(teamID, defName) then return false end
    if equipmentBlocked(teamID, defName) then return false end
    local costs = unitCosts(def)
    if costs and GG and GG.MedievalEconomy and not GG.MedievalEconomy.CanAfford(teamID, costs) then
      return false
    end
    return true
  end,
}
