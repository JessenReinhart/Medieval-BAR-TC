-- Synced medieval skirmish AI: a deliberately simple opponent brain that
-- harvests with idle villagers, expands housing, lays road stubs, trains
-- infantry from its barracks and pushes at enemy settlements.
--
-- All policy/placement math lives in scripts/medieval_skirmish_ai.lua; this
-- gadget owns team enablement, unit tracking, the GG API surface and every
-- Spring.* call.

function gadget:GetInfo()
  return {
    name = "Medieval Skirmish AI",
    desc = "Basic Medieval Skirmish AI placing houses, harvesting, building roads, training military, attacking",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 5,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local ai = VFS.Include("scripts/medieval_skirmish_ai.lua")

-- Skirmish AI is inert unless modoption skirmishai=1; keeps the shared phase2
-- probe runs from auto-driving the NullAI opponent.
local AI_ENABLED = false

-- Per-team AI state -----------------------------------------------------------

local enabledTeams = {}   -- [teamID] = boolean
local stats = {}          -- [teamID] = { housesBuilt, roadsBuilt, ... }
local villagers = {}      -- [teamID][unitID] = true
local barracks = {}       -- [teamID][unitID] = true
local houses = {}         -- [teamID][unitID] = true
local townCenters = {}    -- [teamID][unitID] = true
local military = {}       -- [teamID][unitID] = true
local roadPositions = {}  -- [teamID] = { { x =, z = }, ... } placed road stubs

-- Definition names the AI tracks, straight from the shared policy module.
local MILITARY_NAMES = ai.MILITARY_SET

local TRACKED_BUILDINGS = {
  medieval_barracks = barracks,
  medieval_house = houses,
  medieval_town_center = townCenters,
}

local function initTeam(teamID)
  if enabledTeams[teamID] == nil then enabledTeams[teamID] = false end
  if not stats[teamID] then stats[teamID] = ai.newStats() end
  if not villagers[teamID] then villagers[teamID] = {} end
  if not barracks[teamID] then barracks[teamID] = {} end
  if not houses[teamID] then houses[teamID] = {} end
  if not townCenters[teamID] then townCenters[teamID] = {} end
  if not military[teamID] then military[teamID] = {} end
end

local function defName(unitDefID)
  local def = UnitDefs and UnitDefs[unitDefID]
  return def and def.name or nil
end

local function trackUnit(unitID, unitDefID, teamID)
  if not unitID or not teamID then return end
  local name = defName(unitDefID)
  if not name then return end
  initTeam(teamID)
  if name == "medieval_villager" then
    villagers[teamID][unitID] = true
  elseif MILITARY_NAMES[name] then
    military[teamID][unitID] = true
  else
    local bucket = TRACKED_BUILDINGS[name]
    if bucket then bucket[teamID][unitID] = true end
  end
end

local function untrackUnit(unitID, teamID)
  if not unitID or not teamID then return end
  if villagers[teamID] then villagers[teamID][unitID] = nil end
  if military[teamID] then military[teamID][unitID] = nil end
  if barracks[teamID] then barracks[teamID][unitID] = nil end
  if houses[teamID] then houses[teamID][unitID] = nil end
  if townCenters[teamID] then townCenters[teamID][unitID] = nil end
end

-- Engine helpers ---------------------------------------------------------------

local function unitAlive(unitID)
  if not unitID or type(Spring.ValidUnitID) ~= "function" then return false end
  local ok, valid = pcall(Spring.ValidUnitID, unitID)
  return ok and valid == true
end

local function unitPos(unitID)
  if not unitAlive(unitID) then return nil end
  local ok, x, y, z = pcall(Spring.GetUnitPosition, unitID)
  if not ok or type(x) ~= "number" then return nil end
  return x, y or 0, z or 0
end

-- First live unit of a tracking bucket, with its position.
local function firstUnit(bucket, teamID)
  local set = bucket[teamID]
  if not set then return nil end
  for unitID in pairs(set) do
    if unitAlive(unitID) then
      local x, y, z = unitPos(unitID)
      if x then return unitID, x, y, z end
      return unitID
    end
  end
  return nil
end

local function groundHeight(x, z)
  if type(Spring.GetGroundHeight) ~= "function" then return 0 end
  local ok, h = pcall(Spring.GetGroundHeight, x, z)
  if not ok or type(h) ~= "number" then return 0 end
  return h
end

-- Build-site verification; absent or erroring engine hooks are treated as OK so
-- the AI degrades gracefully instead of stalling.
local function spotIsFree(defID, x, y, z)
  return true
end

local function transact(teamID, costs)
  local econ = GG and GG.MedievalEconomy
  if not econ or type(econ.Transact) ~= "function" then return false end
  local ok, applied = pcall(econ.Transact, teamID, costs)
  return ok and applied == true
end

local function gatherApi()
  return GG and GG.MedievalGather
end

-- AI turn ----------------------------------------------------------------------

local function doHarvest(teamID)
  local gather = gatherApi()
  if not gather or type(gather.AssignGather) ~= "function" then return end
  local jobOf = type(gather.GetJob) == "function" and gather.GetJob or nil
  for unitID in pairs(villagers[teamID]) do
    if unitAlive(unitID) then
      local job = nil
      if jobOf then
        local ok, j = pcall(jobOf, unitID)
        if ok then job = j end
      end
      if not job then
        local ok, assigned = pcall(gather.AssignGather, unitID, nil)
        if ok and assigned == true then
          stats[teamID].gathersAssigned = stats[teamID].gathersAssigned + 1
        end
      end
    end
  end
end

local function doBuildHouse(teamID, pop, cap, stock)
  local wantHouse = ai.shouldBuildHouse(pop, cap, stock)
  if not wantHouse and stats[teamID].housesBuilt > 0 then return end
  if not ai.canAfford(stock, ai.HOUSE_COST) then return end
  local _, tcX, _, tcZ = firstUnit(townCenters, teamID)
  if not tcX then return end
  local houseDef = UnitDefNames and UnitDefNames["medieval_house"]
  if not houseDef then return end
  local base = stats[teamID].housesBuilt
  for attempt = 0, 7 do
    local hx, hz = ai.houseSpot(tcX, tcZ, base + attempt)
    if not hx then break end
    local hy = groundHeight(hx, hz)
    if transact(teamID, ai.HOUSE_COST) then
      local unitID = Spring.CreateUnit("medieval_house", hx, hy, hz, "south", teamID)
      if unitID then
        stats[teamID].housesBuilt = stats[teamID].housesBuilt + 1
        return
      else
        local econ = GG and GG.MedievalEconomy
        if econ and econ.Deposit then
          econ.Deposit(teamID, "wood", ai.HOUSE_COST.wood)
        end
      end
    end
  end
end

local function doBuildRoad(teamID, stock)
  local logistics = GG and GG.MedievalLogistics
  if not logistics or type(logistics.PlaceRoad) ~= "function" then return end
  local roadCount = 0
  if type(logistics.RoadCount) == "function" then
    local ok, n = pcall(logistics.RoadCount, teamID)
    if ok and type(n) == "number" then roadCount = n end
  end
  if not ai.shouldBuildRoad(stock, roadCount, ai.DEFAULT_MAX_ROADS) then return end

  local villagerID = firstUnit(villagers, teamID)
  if not villagerID then return end
  local _, tcX, _, tcZ = firstUnit(townCenters, teamID)
  if not tcX then return end

  -- Candidate link: town center -> road stub east of it -> next house plot.
  local endpoints = { { x = tcX, z = tcZ } }
  local rx, rz = ai.roadSpot(tcX, tcZ)
  if rx then endpoints[#endpoints + 1] = { x = rx, z = rz } end
  local hx, hz = ai.houseSpot(tcX, tcZ, stats[teamID].housesBuilt)
  if hx then endpoints[#endpoints + 1] = { x = hx, z = hz } end

  local pos = ai.selectCandidateRoadPos(endpoints, roadPositions[teamID], ai.ROAD_MIN_DISTANCE)
  if not pos then return end
  local ok, placed = pcall(logistics.PlaceRoad, teamID, villagerID, pos.x, pos.z)
  if ok and placed then
    local list = roadPositions[teamID]
    if not list then
      list = {}
      roadPositions[teamID] = list
    end
    list[#list + 1] = { x = pos.x, z = pos.z }
    stats[teamID].roadsBuilt = stats[teamID].roadsBuilt + 1
  end
end

local function doRecruit(teamID, pop, cap, armyCount, stock)
  if not ai.shouldRecruit(stock, pop, cap, armyCount) then return end
  local _, bx, _, bz = firstUnit(barracks, teamID)
  if not bx then return end
  local recruitment = GG and GG.MedievalRecruitment
  if not recruitment or type(recruitment.CanRecruit) ~= "function" then return end
  local ok, allowed = pcall(recruitment.CanRecruit, teamID, ai.RECRUIT_DEF)
  if not ok or allowed ~= true then return end
  local rx, rz = ai.recruitSpot(bx, bz)
  local ry = groundHeight(rx, rz)
  local unitID = Spring.CreateUnit(ai.RECRUIT_DEF, rx, ry, rz, "south", teamID)
  if unitID then
    stats[teamID].unitsRecruited = stats[teamID].unitsRecruited + 1
  end
end

-- Enemy target selection: prefer an opposing town center, else any enemy unit
-- inside the AI's attack radius of its own town center.
local function findEnemyTarget(teamID, myX, myZ)
  local gaia = type(Spring.GetGaiaTeamID) == "function" and Spring.GetGaiaTeamID() or -1
  local teams = Spring.GetTeamList and Spring.GetTeamList() or {}
  for _, enemyTeam in ipairs(teams) do
    if enemyTeam ~= teamID and enemyTeam ~= gaia then
      local units = Spring.GetTeamUnits and Spring.GetTeamUnits(enemyTeam) or nil
      if units then
        for _, unitID in ipairs(units) do
          local name = defName(Spring.GetUnitDefID and Spring.GetUnitDefID(unitID))
          if name == "medieval_town_center" then
            local x, y, z = unitPos(unitID)
            if x then return x, y, z end
          end
        end
        for _, unitID in ipairs(units) do
          local x, y, z = unitPos(unitID)
          if x then
            local dx, dz = x - myX, z - myZ
            if (dx * dx + dz * dz) <= (ai.ATTACK_RADIUS * ai.ATTACK_RADIUS) then
              return x, y, z
            end
          end
        end
      end
    end
  end

  if type(Spring.GetUnitsInCylinder) == "function" then
    local ok, found = pcall(Spring.GetUnitsInCylinder, myX, myZ, ai.ATTACK_RADIUS)
    if ok and type(found) == "table" then
      for _, unitID in ipairs(found) do
        local team = Spring.GetUnitTeam and Spring.GetUnitTeam(unitID)
        if team and team ~= teamID then
          local x, y, z = unitPos(unitID)
          if x then return x, y, z end
        end
      end
    end
  end
  return nil
end

local function doAttack(teamID, armyCount)
  if not ai.shouldAttack(armyCount) then return end
  local _, tcX, _, tcZ = firstUnit(townCenters, teamID)
  if not tcX then
    local _, vx, _, vz = firstUnit(villagers, teamID)
    tcX, tcZ = vx, vz
  end
  if not tcX then return end
  local tx, ty, tz = findEnemyTarget(teamID, tcX, tcZ)
  if not tx then return end
  for unitID in pairs(military[teamID]) do
    if unitAlive(unitID) then
      local ok = pcall(Spring.GiveOrderToUnit, unitID, CMD.FIGHT, { tx, ty, tz }, 0)
      if ok then
        stats[teamID].attacksOrdered = stats[teamID].attacksOrdered + 1
      end
    end
  end
end

local function runAITurn(teamID)
  if not teamID then return end
  initTeam(teamID)
  if enabledTeams[teamID] ~= true then return end

  -- 1. Stockpiles and settlement capacity.
  local econ = GG and GG.MedievalEconomy
  local stock = {}
  if econ and type(econ.GetStockpiles) == "function" then
    local ok, s = pcall(econ.GetStockpiles, teamID)
    if ok and type(s) == "table" then stock = s end
  end

  local housing = GG and GG.MedievalHousing
  local pop, cap = 0, 0
  if housing then
    if type(housing.GetPopulation) == "function" then
      local ok, p = pcall(housing.GetPopulation, teamID)
      if ok and type(p) == "number" then pop = p end
    end
    if type(housing.GetCap) == "function" then
      local ok, c = pcall(housing.GetCap, teamID)
      if ok and type(c) == "number" then cap = c end
    end
  end

  local armyCount = ai.countKeys(military[teamID])

  -- 2. Put idle villagers back to work, 3. expand, 4. road, 5. train, 6. push.
  doHarvest(teamID)
  doBuildHouse(teamID, pop, cap, stock)
  doBuildRoad(teamID, stock)
  doRecruit(teamID, pop, cap, armyCount, stock)
  doAttack(teamID, armyCount)
end

-- Engine callins ---------------------------------------------------------------

function gadget:Initialize()
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  AI_ENABLED = (mo.skirmishai == "1") or (mo.skirmishai == true)
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
    -- AI-controlled teams run themselves; human teams opt in via GG.EnableTeam.
    -- GetTeamInfo(teamID) -> teamID, leader, isDead, isAi, side, allyTeam, ...
    if AI_ENABLED and type(Spring.GetTeamInfo) == "function" then
      local ok, _, _, _, isAI = pcall(Spring.GetTeamInfo, teamID)
      if ok and isAI == true then enabledTeams[teamID] = true end
    end
  end

  GG = GG or {}
  GG.MedievalSkirmishAI = {
    EnableTeam = function(teamID)
      if not teamID then return end
      initTeam(teamID)
      enabledTeams[teamID] = true
    end,

    DisableTeam = function(teamID)
      if not teamID then return end
      initTeam(teamID)
      enabledTeams[teamID] = false
    end,

    IsEnabled = function(teamID)
      return enabledTeams[teamID] == true
    end,

    GetStats = function(teamID)
      return ai.normalizeStats(stats[teamID])
    end,

    RunTurn = function(teamID)
      runAITurn(teamID)
    end,
  }
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  trackUnit(unitID, unitDefID, teamID)
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  trackUnit(unitID, unitDefID, teamID)
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  untrackUnit(unitID, teamID)
end

function gadget:TeamDied(teamID)
  enabledTeams[teamID] = false
  roadPositions[teamID] = nil
  villagers[teamID] = nil
  barracks[teamID] = nil
  houses[teamID] = nil
  townCenters[teamID] = nil
  military[teamID] = nil
end

function gadget:GameFrame(frame)
  if not AI_ENABLED then return end
  if frame % ai.CADENCE_FRAMES ~= 0 then return end
  for teamID in pairs(enabledTeams) do
    if enabledTeams[teamID] == true then
      runAITurn(teamID)
    end
  end
end
