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
-- unlocked[teamID][techID] = true
local roads = {}
local unlocked = {}

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
  unlocked = {}
  pendingRoadBuilds = {}
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
  -- Register the custom road-build command id (371922), following the
  -- gadget_medieval_gather.lua registration pattern.
  local ok = pcall(gadgetHandler.RegisterCMDID, gadgetHandler, CMD_BUILD_ROAD)
  if ok then gadgetHandler:RegisterAllowCommand(CMD.ANY) end
  roadCommandAttached = {}
  for _, unitID in ipairs(Spring.GetAllUnits and Spring.GetAllUnits() or {}) do
    attachRoadCommand(unitID, Spring.GetUnitDefID(unitID))
  end
end

function gadget:UnitCreated(unitID, unitDefID)
  attachRoadCommand(unitID, unitDefID)
end

function gadget:UnitTaken(unitID)
  cancelRoadOrders(unitID)
end

function gadget:UnitGiven(unitID, unitDefID)
  cancelRoadOrders(unitID)
  attachRoadCommand(unitID, unitDefID)
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
  if #pendingRoadBuilds == 0 then return end
  local pending = pendingRoadBuilds
  pendingRoadBuilds = {}
  for _, order in ipairs(pending) do
    executeRoadOrder(order.teamID, order.unitID, order.x, order.z)
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
}
