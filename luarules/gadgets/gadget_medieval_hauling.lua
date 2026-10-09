function gadget:GetInfo()
  return {
    name = "Medieval Hauling",
    desc = "Supply carts auto-haul resources between storage hubs on a local deficit, with the Slice 6 road-speed mutator",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 4,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local haul = VFS.Include("scripts/medieval_haul.lua")
-- Reused (not duplicated) for the road-speed mutator: targetSpeed/speedMultiplier
-- are the exact Slice 6 multiplier helpers, and on-road detection uses the live
-- GG.MedievalLogistics.IsOnRoad path already exported by gadget_medieval_logistics.
local logistics = VFS.Include("scripts/medieval_logistics.lua")

local DEBUG_LOG = true

local SPEED_SCAN_INTERVAL = 15 -- frames; same cadence as the Slice 6 road-speed scan
local HAUL_SCAN_INTERVAL  = 30 -- frames; one haul decision pass per ~1s
local HAUL_ARRIVAL_RADIUS = 64.0 -- elmos; within this of a hub the cart loads/unloads

-- Synced state:
--   carts[teamID][unitID] = { base = number, applied = number }
--   hubs[teamID][unitID]  = { name = string, x = number, y = number, z = number }
--   jobs[unitID]          = { teamID = number, phase = "to_source"|"to_sink", route = {...} }
--   stats[teamID]         = { routesAssigned, delivered, deficitsResolved }
--   hubDelivered[teamID][unitID][resource] = number  (storage ledger at the sink hub)
local carts = {}
local hubs = {}
local jobs = {}
local stats = {}
local hubDelivered = {}

-- Forward declarations (defined below, referenced by lifecycle callins above).
local ensureApi, completeHaul

local function echo(fmt, ...)
  if DEBUG_LOG and Spring and Spring.Echo then
    Spring.Echo(string.format(fmt, ...))
  end
end

local function aliveUnit(unitID)
  return type(unitID) == "number"
    and Spring and Spring.GetUnitDefID and Spring.GetUnitDefID(unitID) ~= nil
end

local function numSpeed(def)
  local s = def and def.speed
  if type(s) == "number" and s > 0 then return s end
  return 1.0
end

local function initTeam(teamID)
  carts[teamID] = carts[teamID] or {}
  hubs[teamID] = hubs[teamID] or {}
  stats[teamID] = stats[teamID] or { routesAssigned = 0, delivered = 0, deficitsResolved = 0 }
  hubDelivered[teamID] = hubDelivered[teamID] or {}
end

-- ---------------------------------------------------------------------------
-- Unit / hub lifecycle
-- ---------------------------------------------------------------------------

local function trackHub(unitID, unitDefID, teamID, def)
  if teamID == nil then return end
  local x, y, z
  if Spring and Spring.GetUnitPosition then x, y, z = Spring.GetUnitPosition(unitID) end
  if not x or not z then return end
  initTeam(teamID)
  hubs[teamID][unitID] = { name = def.name, x = x, y = y, z = z }
  echo("PHASE4 HAUL hub tracked unit=%d team=%d name=%s", unitID, teamID, def.name)
end

local function trackUnit(unitID, unitDefID, teamID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return end
  if haul.canHaul(teamID, unitID, def.name) then
    initTeam(teamID)
    carts[teamID][unitID] = { base = numSpeed(def), applied = nil }
    echo("PHASE4 HAUL cart tracked unit=%d team=%d", unitID, teamID)
  elseif haul.isHubName(def.name) then
    trackHub(unitID, unitDefID, teamID, def)
  end
end

function gadget:Initialize()
  ensureApi()
  local units = Spring.GetAllUnits and Spring.GetAllUnits() or {}
  for i = 1, #units do
    local unitID = units[i]
    local defID = Spring.GetUnitDefID(unitID)
    if defID then
      trackUnit(unitID, defID, Spring.GetUnitTeam(unitID))
    end
  end
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  trackUnit(unitID, unitDefID, teamID)
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  jobs[unitID] = nil
  for t, list in pairs(carts) do list[unitID] = nil end
  for t, list in pairs(hubs) do list[unitID] = nil end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == nil and Spring and Spring.GetUnitTeam then newTeam = Spring.GetUnitTeam(unitID) end
  trackUnit(unitID, unitDefID, newTeam)
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  jobs[unitID] = nil
  for t, list in pairs(carts) do if list[unitID] then list[unitID] = nil end end
  for t, list in pairs(hubs) do if list[unitID] then list[unitID] = nil end end
end

function gadget:TeamDied(teamID)
  carts[teamID] = nil
  hubs[teamID] = nil
  for unitID, job in pairs(jobs) do
    if job.teamID == teamID then jobs[unitID] = nil end
  end
end

-- ---------------------------------------------------------------------------
-- Road-speed mutator (reuses the Slice 6 helper + the live on-road path)
-- ---------------------------------------------------------------------------

-- On-road status via the pre-existing exported API; falls back to false (no
-- boost) rather than re-scanning the road network here.
local function cartOnRoad(teamID, unitID)
  if GG and GG.MedievalLogistics and GG.MedievalLogistics.IsOnRoad then
    local ok, v = pcall(GG.MedievalLogistics.IsOnRoad, teamID, unitID)
    if ok then return v == true end
  end
  return false
end

-- Same MoveCtrl.SetGroundMoveTypeData call Slice 6's applySpeed uses; the
-- multiplier comes from logistics.targetSpeed -> logistics.speedMultiplier
-- (ROAD_SPEED_MULT). Nothing here re-declares the multiplier constant.
local function applyRoadSpeed(unitID, target)
  local moveCtrl = Spring and Spring.MoveCtrl
  if moveCtrl and moveCtrl.SetGroundMoveTypeData then
    local ok, assigned = pcall(moveCtrl.SetGroundMoveTypeData, unitID, {
      maxSpeed = target,
      maxWantedSpeed = target,
    })
    if ok and type(assigned) == "number" and assigned > 0 then
      return true, "mutator"
    end
  end
  return false, "none"
end

local function scanCartSpeeds()
  for teamID, list in pairs(carts) do
    for unitID, state in pairs(list) do
      if not aliveUnit(unitID) then
        list[unitID] = nil
        jobs[unitID] = nil
      else
        local onRoad = cartOnRoad(teamID, unitID)
        local target = logistics.targetSpeed(state.base, onRoad)
        if target ~= state.applied then
          local ok, source = applyRoadSpeed(unitID, target)
          if ok then state.applied = target end
          echo("PHASE4 HAUL speed unit=%d team=%d base=%.2f target=%.2f onRoad=%s source=%s",
            unitID, teamID, state.base, target, tostring(onRoad), source)
        end
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Movement helpers
-- ---------------------------------------------------------------------------

local function unitPos(unitID)
  if Spring and Spring.GetUnitPosition then
    return Spring.GetUnitPosition(unitID)
  end
end

local function issueMove(unitID, x, y, z)
  if not (Spring and Spring.GiveOrderToUnit) then return false end
  local ok = pcall(Spring.GiveOrderToUnit, unitID, CMD.MOVE, { x, y or 0, z }, 0)
  return ok
end

local function stopUnit(unitID)
  if Spring and Spring.GiveOrderToUnit then
    pcall(Spring.GiveOrderToUnit, unitID, CMD.STOP, {}, 0)
  end
end

local function hubNear(unitID, hubID, radius)
  if not aliveUnit(hubID) then return false end
  local ux, _, uz = unitPos(unitID)
  local hx, _, hz = unitPos(hubID)
  if not ux or not hx then return false end
  local dx, dz = ux - hx, uz - hz
  return (dx * dx + dz * dz) <= radius * radius
end

-- ---------------------------------------------------------------------------
-- Haul state machine (throttled)
-- ---------------------------------------------------------------------------

completeHaul = function(unitID, job)
  local teamID = job.teamID
  local route = job.route
  initTeam(teamID)

  local s = stats[teamID]
  s.delivered = s.delivered + 1
  s.deficitsResolved = s.deficitsResolved + 1

  -- Storage ledger at the sink hub. The team pool (gadget_medieval_economy) is
  -- shared, not per-hub, so a same-team hub->hub haul conserves the pool; this
  -- ledger is the per-hub "storage" view the haul repositions. No pool debit
  -- happens here -- production chains own the actual pool consumption via
  -- GG.MedievalEconomy.Transact -- so a haul cannot double-spend the stockpile.
  local d = hubDelivered[teamID][route.to] or {}
  d[route.resource] = (d[route.resource] or 0) + route.amount
  hubDelivered[teamID][route.to] = d

  echo("PHASE4 HAUL route team=%d from=%s to=%s kind=%s amount=%d",
    teamID, tostring(route.from), tostring(route.to), route.resource, route.amount)
  stopUnit(unitID)
end

local function advanceJob(unitID, job)
  local teamID = job.teamID
  local route = job.route
  local teamHubs = hubs[teamID] or {}

  if job.phase == "to_source" then
    local fromHub = teamHubs[route.from]
    if not fromHub or not aliveUnit(route.from) then
      jobs[unitID] = nil -- source hub vanished; release the cart
      return
    end
    if hubNear(unitID, route.from, HAUL_ARRIVAL_RADIUS) then
      job.phase = "to_sink"
      local toHub = teamHubs[route.to]
      if toHub then issueMove(unitID, toHub.x, toHub.y, toHub.z) end
    end
  elseif job.phase == "to_sink" then
    local toHub = teamHubs[route.to]
    if not toHub or not aliveUnit(route.to) then
      jobs[unitID] = nil
      return
    end
    if hubNear(unitID, route.to, HAUL_ARRIVAL_RADIUS) then
      completeHaul(unitID, job)
      jobs[unitID] = nil
    end
  end
end

local function runTeamHaul(teamID)
  initTeam(teamID)

  -- Drop gone hubs/carts.
  for unitID in pairs(hubs[teamID]) do
    if not aliveUnit(unitID) then hubs[teamID][unitID] = nil end
  end
  for unitID, state in pairs(carts[teamID]) do
    if not aliveUnit(unitID) then carts[teamID][unitID] = nil; jobs[unitID] = nil end
  end

  -- Refresh hub positions (hubs are static, but cheap to confirm).
  for unitID, h in pairs(hubs[teamID]) do
    local x, y, z = unitPos(unitID)
    if x then h.x, h.y, h.z = x, y, z end
  end

  local stocks = GG.MedievalEconomy and GG.MedievalEconomy.GetStockpiles
    and GG.MedievalEconomy.GetStockpiles(teamID) or {}
  haul.setRouteContext(hubs[teamID], stocks, haul.DEFAULT_CART_CAPACITY)

  -- Advance carts already under way.
  for unitID, job in pairs(jobs) do
    if not aliveUnit(unitID) then
      jobs[unitID] = nil
    else
      advanceJob(unitID, job)
    end
  end

  -- Assign idle carts to a fresh route.
  for unitID in pairs(carts[teamID]) do
    if not jobs[unitID] then
      local defID = Spring.GetUnitDefID(unitID)
      local def = defID and UnitDefs and UnitDefs[defID]
      local cp = def and (def.customParams or def.customparams)
      local cap = cp and cp.carry_capacity
      local route = haul.chooseHaulRoute(teamID, unitID, nil, nil, haul.clampCapacity(cap))
      if route then
        jobs[unitID] = { teamID = teamID, phase = "to_source", route = route }
        stats[teamID].routesAssigned = stats[teamID].routesAssigned + 1
        local h = hubs[teamID][route.from]
        if h then issueMove(unitID, h.x, h.y, h.z) end
        echo("PHASE4 HAUL assigned cart=%d team=%d from=%s to=%s kind=%s amount=%d",
          unitID, teamID, tostring(route.from), tostring(route.to), route.resource, route.amount)
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Public API on GG.MedievalLogistics (additive; never reassigns the whole table,
-- because gadget_medieval_logistics rebuilds it and production chains posts
-- equipmentStock onto it -- ensureApi only ADDS our two closures on top).
-- ---------------------------------------------------------------------------

local function HaulSummary(teamID)
  initTeam(teamID)
  local cartCount, hubCount = 0, 0
  for _ in pairs(carts[teamID] or {}) do cartCount = cartCount + 1 end
  for _ in pairs(hubs[teamID] or {}) do hubCount = hubCount + 1 end
  local s = stats[teamID] or { routesAssigned = 0, delivered = 0, deficitsResolved = 0 }
  return {
    carts = cartCount,
    hubs = hubCount,
    routesAssigned = s.routesAssigned or 0,
    delivered = s.delivered or 0,
    deficitsResolved = s.deficitsResolved or 0,
  }
end

local function HaulRoute(teamID, cartID)
  local job = jobs[cartID]
  if not job or job.teamID ~= teamID then return nil end
  return job.route
end

-- Per-hub storage ledger, read-only. The team pool is shared, so this ledger is
-- the only per-hub "stock" a completed haul moves; probes and UI read it to see
-- what a haul actually delivered to a sink hub. 0 when nothing landed yet.
local function HaulHubStock(teamID, hubID, resource)
  local team = hubDelivered[teamID]
  local hub = team and team[hubID]
  if type(hub) ~= "table" then return 0 end
  local value = hub[resource]
  if type(value) ~= "number" then return 0 end
  return value
end

ensureApi = function()
  GG = GG or {}
  GG.MedievalLogistics = GG.MedievalLogistics or {}
  GG.MedievalLogistics.HaulSummary = HaulSummary
  GG.MedievalLogistics.HaulRoute = HaulRoute
  GG.MedievalLogistics.HaulHubStock = HaulHubStock
end

function gadget:GameFrame(frame)
  ensureApi()
  if frame % SPEED_SCAN_INTERVAL == 0 then
    scanCartSpeeds()
  end
  if frame % HAUL_SCAN_INTERVAL == 0 then
    local teams = Spring.GetTeamList and Spring.GetTeamList() or {}
    for _, teamID in ipairs(teams) do
      runTeamHaul(teamID)
    end
  end
end