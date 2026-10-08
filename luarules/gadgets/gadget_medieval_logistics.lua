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
local roadGraph = VFS.Include("scripts/medieval_road_graph.lua")

local DEBUG_LOG = true

-- Synced state:
-- roads[teamID] = { [featureID] = { x = number, z = number } }
-- buildings[teamID] = { [unitID] = { x = number, z = number, name = string } }
-- unlocked[teamID][techID] = true
-- speedMovers[teamID][unitID] = { base, onRoad, applied, source }
local roads = {}
local buildings = {}
local unlocked = {}
local speedMovers = {}

-- Supply endpoints are only town center, granary and lumber camp, identified
-- by the `dropoff` customparam (engine lowercases keys; source defs may not).
local function isSupplyEndpointDef(def)
  return logistics.isSupplyEndpointDef(def)
end
local removeTrackedBuilding, trackSupplyEndpoint
-- Forward declarations: the speed scan and its interval are referenced by
-- gadget:GameFrame and the lifecycle callins above their definitions.
local trackSpeedMover, removeSpeedMover, scanSpeedMovers, isUnitBuilt
local SPEED_SCAN_INTERVAL = 15 -- frames; 15 frames = 0.5s at 30 game-fps

-- Road-build command intent: AllowCommand records it here; the next
-- GameFrame pass performs the economy transaction and feature creation.
local pendingRoadBuilds = {}

local function syncTechParams(teamID)
  for techID in pairs(logistics.TECHS) do
    local flag = (unlocked[teamID] and unlocked[teamID][techID]) and 1 or 0
    Spring.SetGameRulesParam(string.format("team_%d_tech_%s", teamID, techID), flag)
  end
end

local function initTeam(teamID)
  roads[teamID] = roads[teamID] or {}
  buildings[teamID] = buildings[teamID] or {}
  unlocked[teamID] = unlocked[teamID] or {}
  syncTechParams(teamID)
end


local function echo(fmt, ...)
  if DEBUG_LOG and Spring and Spring.Echo then
    Spring.Echo(string.format(fmt, ...))
  end
end

local CMD_BUILD_ROAD = 371922

local roadCommandAttached = {}

local function isVillager(unitDefID)
  local internal = UnitDefNames and UnitDefNames.medieval_villager
  if internal then return unitDefID == internal.id end
  local def = UnitDefs and UnitDefs[unitDefID]
  return def and def.name == "medieval_villager"
end

local function validRoadIssuer(teamID, unitID)
  -- If engine lacks unit APIs, assume issuer valid (tests stub)
  if not (Spring.GetUnitDefID and Spring.GetUnitTeam) then return true end
  local defID = Spring.GetUnitDefID(unitID)
  if not defID then return false, "invalid_issuer" end
  if Spring.GetUnitIsDead and Spring.GetUnitIsDead(unitID) then
    return false, "invalid_issuer"
  end
  if not isVillager(defID) then return false, "not_villager" end
  if Spring.GetUnitTeam(unitID) ~= teamID then return false, "wrong_team" end
  return true
end

local function attachRoadCommand(unitID, unitDefID)
  if not isVillager(unitDefID) or roadCommandAttached[unitID] then return end
  if not (Spring.InsertUnitCmdDesc and CMDTYPE) then return end
  if not (Spring.FindUnitCmdDesc and Spring.FindUnitCmdDesc(unitID, CMD_BUILD_ROAD)) then
    Spring.InsertUnitCmdDesc(unitID, {
      id = CMD_BUILD_ROAD, type = CMDTYPE.ICON_MAP, name = "Build Road",
      action = "buildroad", tooltip = "Place a road (5 wood, 2 stone)", params = {},
    })
  end
  roadCommandAttached[unitID] = true
end

local function cancelRoadOrders(unitID)
  for i = #pendingRoadBuilds, 1, -1 do
    if pendingRoadBuilds[i].unitID == unitID then table.remove(pendingRoadBuilds, i) end
  end
end

-- ------------------------------------------------------------------
-- Road-build command helpers (UI {x, y, z}; probe/API {x, z})
-- ------------------------------------------------------------------

local function getRoadStock(teamID)
  local economy = GG and GG.MedievalEconomy
  if economy and economy.GetStockpiles then
    return economy.GetStockpiles(teamID)
  end
  return nil
end

local function canPlaceRoad(teamID, x, z)
  initTeam(teamID)
  if type(x) ~= "number" or type(z) ~= "number" then
    return false, "invalid_coordinates"
  end
  local mapX = Game and Game.mapSizeX
  local mapZ = Game and Game.mapSizeZ
  if mapX == nil and Spring and Spring.GetMapSize then
    mapX, mapZ = Spring.GetMapSize()
  end
  if mapX and mapZ and (x < 0 or z < 0 or x > mapX or z > mapZ) then
    return false, "off_map"
  end
  return logistics.canPlaceRoad(x, z, roads[teamID] or {}, getRoadStock(teamID))
end

local function refundRoadCost(teamID)
  -- Transact only withdraws; reversal is done via per-resource Deposit.
  local economy = GG and GG.MedievalEconomy
  if not (economy and economy.Deposit) then return end
  for resource, amount in pairs(logistics.COSTS.medieval_road) do
    economy.Deposit(teamID, resource, amount)
  end
end

-- Charges the team and creates the road feature; safe to call from either
-- the deferred GameFrame pass or GG.MedievalLogistics.PlaceRoad.
local function executeRoadOrder(teamID, unitID, x, z)
  initTeam(teamID)
  local economy = GG and GG.MedievalEconomy
  local costs = logistics.COSTS.medieval_road

  local issuerOK, issuerReason = validRoadIssuer(teamID, unitID)
  if not issuerOK then return false, issuerReason end
  local ok, reason = canPlaceRoad(teamID, x, z)
  if not ok then
    echo("PHASE3 PROBE road-cmd refused team=%d reason=%s", teamID, tostring(reason))
    return false, reason
  end
  if not economy or not economy.Transact or not economy.Deposit then
    echo("PHASE3 PROBE road-cmd refused team=%d reason=no_economy", teamID)
    return false, "no_economy"
  end
  if not economy.Transact(teamID, costs) then
    echo("PHASE3 PROBE road-cmd refused team=%d reason=insufficient_resources", teamID)
    return false, "insufficient_resources"
  end

  local y = 0
  if Spring and Spring.GetGroundHeight then y = Spring.GetGroundHeight(x, z) end
  local ftrID = Spring and Spring.CreateFeature
    and Spring.CreateFeature("medieval_road", x, y, z, 0, teamID)
  if not ftrID then
    refundRoadCost(teamID)
    echo("PHASE3 PROBE road-cmd refused team=%d reason=create_failed", teamID)
    return false, "create_failed"
  end
  echo("PHASE3 PROBE road-cmd placed team=%d reason=ok ftr=%d x=%.0f z=%.0f", teamID, ftrID, x, z)
  return true, ftrID
end

function gadget:Initialize()
  roads = {}
  buildings = {}
  unlocked = {}
  pendingRoadBuilds = {}
  speedMovers = {}
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
  -- Register the custom road-build command id (371922), following the
  -- gadget_medieval_gather.lua registration pattern.
  local ok = pcall(gadgetHandler.RegisterCMDID, gadgetHandler, CMD_BUILD_ROAD)
  if ok then gadgetHandler:RegisterAllowCommand(CMD.ANY) end
  roadCommandAttached = {}
  for _, unitID in ipairs(Spring.GetAllUnits and Spring.GetAllUnits() or {}) do
    local unitDefID = Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
    attachRoadCommand(unitID, unitDefID)
    -- Re-track supply endpoints that already exist at initialization.
    trackSupplyEndpoint(unitID, unitDefID, Spring.GetUnitTeam and Spring.GetUnitTeam(unitID))
    -- Re-track speed movers that already exist at initialization (must be finished).
    if isUnitBuilt(unitID) then
      trackSpeedMover(unitID, unitDefID, Spring.GetUnitTeam and Spring.GetUnitTeam(unitID))
    end
  end
end

function gadget:UnitCreated(unitID, unitDefID)
  attachRoadCommand(unitID, unitDefID)
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  cancelRoadOrders(unitID)
  -- Supply-endpoint buildings move with the unit: drop the old-team entry.
  removeTrackedBuilding(unitID)
  -- Speed tracking is per-team; the receiving team re-tracks in UnitGiven.
  removeSpeedMover(unitID)
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  cancelRoadOrders(unitID)
  attachRoadCommand(unitID, unitDefID)
  -- Re-track under the receiving team, if this is a supply endpoint.
  if newTeam == nil and Spring and Spring.GetUnitTeam then newTeam = Spring.GetUnitTeam(unitID) end
  trackSupplyEndpoint(unitID, unitDefID, newTeam)
  -- Re-track the speed mover under the receiving team.
  removeSpeedMover(unitID)
  trackSpeedMover(unitID, unitDefID, newTeam)
end

-- ---------------------------------------------------------------------------
-- Supply-endpoint buildings: track finished drop-off buildings per team.
-- ---------------------------------------------------------------------------

removeTrackedBuilding = function(unitID)
  for teamID, list in pairs(buildings) do
    if list[unitID] then
      list[unitID] = nil
      echo("PHASE3 BUILDING removed unit=%d team=%d", unitID, teamID)
      return teamID
    end
  end
  return nil
end

-- Finished means build progress is 1 (or unknown). Mid-construction units
-- (progress in (0,1)) are not tracked as endpoints.
isUnitBuilt = function(unitID)
  if not (Spring and Spring.GetUnitHealth) then return true end
  local _, _, _, _, buildProgress = Spring.GetUnitHealth(unitID)
  if buildProgress == nil then return true end
  return buildProgress == 1
end

trackSupplyEndpoint = function(unitID, unitDefID, teamID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def or not isSupplyEndpointDef(def) then return end
  if teamID == nil then return end
  if not isUnitBuilt(unitID) then return end
  local x, _, z
  if Spring and Spring.GetUnitPosition then x, _, z = Spring.GetUnitPosition(unitID) end
  if not x or not z then return end
  initTeam(teamID)
  buildings[teamID][unitID] = { x = x, z = z }
  echo("PHASE3 BUILDING tracked unit=%d team=%d x=%.0f z=%.0f", unitID, teamID, x, z)
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
  local s = roadGraph.networkSummary(roads[owner])
  echo("PHASE3 ROADGRAPH team=%d nodes=%d edges=%d components=%d isolated=%d largest=%d",
    owner, s.nodes, s.edges, s.components, s.isolated, s.largest)
end

function gadget:FeatureDestroyed(featureID, allyTeam)
  for teamID, list in pairs(roads) do
    if list[featureID] then
      list[featureID] = nil
      echo("PHASE3 ROAD removed ftr=%d team=%d", featureID, teamID)
      local s = roadGraph.networkSummary(list)
      echo("PHASE3 ROADGRAPH team=%d nodes=%d edges=%d components=%d isolated=%d largest=%d",
        teamID, s.nodes, s.edges, s.components, s.isolated, s.largest)
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
  -- Track finished supply endpoints for the owning team.
  trackSupplyEndpoint(unitID, unitDefID, unitTeam)
  -- Track finished speed-eligible movers (base speed from the unit def).
  trackSpeedMover(unitID, unitDefID, unitTeam)
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
  attachRoadCommand(unitID, unitDefID)
end

-- ---------------------------------------------------------------------------
-- Fortifications: validate costs at placement like recruitment does.
-- ---------------------------------------------------------------------------

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam, x, y, z, facing)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return true end
  -- Supply-endpoint placement policy: drop-off buildings must sit within
  -- BUILD_LINK_RADIUS (64 elmos) of a team road node. When the team has no
  -- roads yet the first endpoint is allowed (seed building); a missing or
  -- invalid build position is invalid input and allowed to keep the engine
  -- callin contract (creation without buildInfo) unchanged.
  if isSupplyEndpointDef(def) then
    -- Non-placement callins (nil build coordinates) bypass the road gate.
    if x == nil or z == nil then
      initTeam(builderTeam)
      return true
    end
    initTeam(builderTeam)
    if not logistics.isEndpointPlacementAllowed(roads[builderTeam], x, z, logistics.BUILD_LINK_RADIUS) then
      echo("PHASE3 BUILDING denied team=%d def=%s reason=off_road", builderTeam, def.name)
      return false
    end
  end
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
  -- Any queued road-build intent for a destroyed/gone villager is void.
  cancelRoadOrders(unitID)
  -- A destroyed endpoint building leaves the tracking table.
  removeTrackedBuilding(unitID)
  -- A destroyed mover leaves the speed table.
  removeSpeedMover(unitID)
end

function gadget:UnitPreDamaged(unitID, unitDefID, unitTeam, damage, paralyzer, weaponDefID, projectileID, attackerID, attackerDefID, attackerTeam)
  if not attackerID or not attackerDefID then
    return damage, 1.0
  end
  local attackerDef = UnitDefs and UnitDefs[attackerDefID]
  if not attackerDef or not attackerDef.name or not string.find(attackerDef.name, "^medieval_") then
    return damage, 1.0
  end
  local u = unlocked[attackerTeam]
  if u and u.iron_swords and attackerDef.name == "medieval_infantry" then
    local newDamage = logistics.scaledDamage(damage, 1.25)
    echo("PHASE3 DAMAGE attacker=%d defender=%d base=%.1f scaled=%.1f", attackerID, unitID, damage, newDamage)
    return newDamage, 1.0
  end
  return damage, 1.0
end

function gadget:AllowCommand(unitID, unitDefID, teamID, cmdID, params, opts)
  if cmdID ~= CMD_BUILD_ROAD then return true end
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def or def.name ~= "medieval_villager" then return false end
  if opts and (opts.shift or opts.alt or opts.ctrl or opts.right) then return false end
  local x, z = params and params[1], params and params[2]
  local ok, reason = canPlaceRoad(teamID, x, z)
  if not ok then
    echo("PHASE3 PROBE road-cmd refused team=%d reason=%s", teamID, tostring(reason))
    return false
  end
  pendingRoadBuilds[#pendingRoadBuilds + 1] = { unitID = unitID, teamID = teamID, x = x, z = z }
  return false
end

function gadget:GameFrame(frame)
  if #pendingRoadBuilds > 0 then
    local pending = pendingRoadBuilds
    pendingRoadBuilds = {}
    for _, order in ipairs(pending) do
      executeRoadOrder(order.teamID, order.unitID, order.x, order.z)
    end
  end
  -- Throttled movement-speed scan (every 15 frames = 0.5s).
  if frame % SPEED_SCAN_INTERVAL == 0 then
    scanSpeedMovers()
  end
end


-- ---------------------------------------------------------------------------
-- Road movement-speed enforcement (Slice 6).
--
-- onRoad reuses the EXACT helper the pre-existing GG.MedievalLogistics.
-- GetSpeedMultiplier uses: logistics.isPositionOnRoad(x, z, coords, radius),
-- which defaults to logistics.ROAD_PROXIMITY_RADIUS (48). This is deliberately
-- NOT roadGraph's LINK_RADIUS (64), which is the road-to-road adjacency /
-- building-link distance and would over-report units as being on a road.
--
-- Application order per mover:
--   1. Spring.MoveCtrl.SetGroundMoveTypeData -> source = "mutator" (enforcing)
--   2. Spring.SetUnitRulesParam(..., "medieval_speed_target") -> source =
--      "rules-param" (OBSERVATIONAL ONLY; the engine does not read this param,
--      so no speed change happens - it exists so UI/other gadgets can observe
--      the intended target when the mutator is unavailable)
--   3. neither available -> source = "none"; never an error.
--
-- Out of scope by design: air/hover and transported units, builder-assist
-- interactions, and per-slope effects. Only finished ground units whose def
-- reports a positive numeric `speed` are tracked at all.
-- ---------------------------------------------------------------------------

local function findSpeedMover(unitID)
  for teamID, list in pairs(speedMovers) do
    local state = list[unitID]
    if state then return teamID, state end
  end
  return nil, nil
end

removeSpeedMover = function(unitID)
  local teamID, state = findSpeedMover(unitID)
  if not teamID then return nil end
  speedMovers[teamID][unitID] = nil
  return teamID, state
end

local function isUnitOnRoad(teamID, unitID)
  local list = roads[teamID]
  if not list then return false end
  if not (Spring and Spring.GetUnitPosition) then return false end
  local x, _, z = Spring.GetUnitPosition(unitID)
  if type(x) ~= "number" or type(z) ~= "number" then return false end
  return logistics.isPositionOnRoad(x, z, list)
end

local function applySpeed(unitID, target)
  local moveCtrl = Spring and Spring.MoveCtrl
  if moveCtrl and moveCtrl.SetGroundMoveTypeData then
    -- The engine returns the number of assigned values (0 = nothing applied).
    -- pcall success alone does not prove the assignment landed.
    local ok, assigned = pcall(moveCtrl.SetGroundMoveTypeData, unitID, {
      maxSpeed = target,
      maxWantedSpeed = target,
    })
    if ok and type(assigned) == "number" and assigned > 0 then
      return true, "mutator"
    end
  end
  if Spring and Spring.SetUnitRulesParam then
    local ok = pcall(Spring.SetUnitRulesParam, unitID, "medieval_speed_target", target)
    if ok then return true, "rules-param" end
  end
  return false, "none"
end

trackSpeedMover = function(unitID, unitDefID, teamID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not logistics.isEligibleSpeedUnitDef(def) then return false, "ineligible" end
  local base = def.speed
  if type(base) ~= "number" or base <= 0 then
    echo("PHASE3 SPEED skip unit=%d def=%s reason=no_base", unitID, tostring(def.name))
    return false, "no_base"
  end
  if teamID == nil then return false, "no_team" end
  initTeam(teamID)
  speedMovers[teamID] = speedMovers[teamID] or {}
  speedMovers[teamID][unitID] = {
    base = base,
    onRoad = false,
    applied = base,
    source = "none",
  }
  echo("PHASE3 SPEED tracked unit=%d team=%d base=%.2f", unitID, teamID, base)
  return true
end

-- Throttled scan: recompute onRoad, then apply only on target change.
scanSpeedMovers = function()
  for teamID, list in pairs(speedMovers) do
    for unitID, state in pairs(list) do
      local onRoad = isUnitOnRoad(teamID, unitID)
      local target = logistics.targetSpeed(state.base, onRoad)
      state.onRoad = onRoad
      if target ~= state.applied and target ~= state.triedTarget then
        local ok, source = applySpeed(unitID, target)
        state.source = source
        -- Record the attempt either way: a permanently failing application
        -- (e.g. no mutator, no rules param) must not retry every scan and
        -- spam the log; the next target change re-arms the attempt.
        state.triedTarget = target
        if ok then state.applied = target end
        echo("PHASE3 SPEED applied unit=%d team=%d base=%.2f target=%.2f source=%s",
          unitID, teamID, state.base, target, source)
      end
    end
  end
end

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

  -- Slice 6: current enforced speed state for a tracked mover, or nil when the
  -- unit is unknown/ineligible. The returned table is the live synced entry
  -- { base, onRoad, applied, source } (source: "mutator" | "rules-param" |
  -- "none").
  GetSpeedState = function(unitID)
    local _, state = findSpeedMover(unitID)
    return state
  end,

  CanPlaceRoad = function(teamID, x, z)
    return canPlaceRoad(teamID, x, z)
  end,

  PlaceRoad = function(teamID, unitID, x, z)
    return executeRoadOrder(teamID, unitID, x, z)
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

  RoadNetworkSummary = function(teamID)
    return roadGraph.networkSummary(roads[teamID] or {})
  end,

  RoadConnected = function(teamID, keyA, keyB)
    return roadGraph.isConnected(roads[teamID] or {}, keyA, keyB)
  end,

  PointOnRoadNetwork = function(teamID, x, z)
    return roadGraph.connectedToNetwork(roads[teamID] or {}, x, z)
  end,

  -- Supply-endpoint building queries. Connectivity is recomputed from the
  -- team's roads at query time, so road removal takes effect immediately.
  -- Unknown units or mismatched teams return false.
  BuildingConnected = function(teamID, unitID)
    local list = buildings[teamID]
    local b = list and list[unitID]
    if not b then return false end
    return logistics.isBuildingConnected(roads[teamID] or {}, b.x, b.z, logistics.BUILD_LINK_RADIUS)
  end,

  BuildingConnectivitySummary = function(teamID)
    local list = buildings[teamID]
    local summary = { total = 0, connected = 0, disconnected = 0 }
    if not list then return summary end
    local teamRoads = roads[teamID] or {}
    for _, b in pairs(list) do
      summary.total = summary.total + 1
      if logistics.isBuildingConnected(teamRoads, b.x, b.z, logistics.BUILD_LINK_RADIUS) then
        summary.connected = summary.connected + 1
      else
        summary.disconnected = summary.disconnected + 1
      end
    end
    return summary
  end,
}
