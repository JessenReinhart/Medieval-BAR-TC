function gadget:GetInfo()
  return {
    name = "Medieval Gathering and Delivery",
    desc = "Villager harvest/deliver work cycle against resource-node features and drop-off buildings",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local gather = VFS.Include("scripts/medieval_gather.lua")

local CMD_GATHER = 371920
local CMD_DELIVER = 371921

-- Per-feature harvested state: nodes[featureID] = { defID, resource, remaining }
local nodes = {}

-- Per-villager job: jobs[unitID] = { state, nodeID, resource, carried, dropoffID }
-- state: "move_node", "harvest", "move_drop", "deliver"
local jobs = {}

-- Drop-off registry: dropoffs[teamID][buildingUnitID] = true
-- Declared before nearestDropoff: that function closes over these locals, so a
-- later declaration would silently bind them as nil globals.
local dropoffs = {}
-- allowsResource[teamID][resource] = true if some dropoff of that team accepts it
local allowsResource = {}

-- ---------------------------------------------------------------------------
-- Node registry (auto-populated from FeatureCreated)
-- ---------------------------------------------------------------------------

local function registerFeature(featureID)
  local ok, defID = pcall(Spring.GetFeatureDefID, featureID)
  if not ok or not defID then return false end
  local def = FeatureDefs and FeatureDefs[defID]
  if not def or not def.customParams or not def.customParams.resource then return false end
  local cap = tonumber(def.customParams.capacity) or gather.DEFAULT_NODE_CAPACITY
  nodes[featureID] = {
    defID = defID,
    resource = def.customParams.resource,
    remaining = cap,
  }
  return true
end

function gadget:FeatureCreated(featureID, allyTeamID)
  registerFeature(featureID)
end

function gadget:FeatureDestroyed(featureID, allyTeamID)
  nodes[featureID] = nil
  -- Detach any villager currently harvesting the destroyed node.
  for unitID, job in pairs(jobs) do
    if job.nodeID == featureID then
      job.nodeID = nil
      if job.state == "harvest" or job.state == "move_node" then
        job.state = "move_node"  -- will find a fresh node next tick
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Position / availability helpers
-- ---------------------------------------------------------------------------

local function unitPos(unitID)
  local ok, x, y, z = pcall(Spring.GetUnitPosition, unitID, false)
  if not ok or not x then return nil end
  return x, y, z
end

local function featurePos(featureID)
  local ok, x, y, z = pcall(Spring.GetFeaturePosition, featureID)
  if not ok or not x then return nil end
  return x, y, z
end

local function alive(unitID)
  local ok, alive = pcall(Spring.GetUnitIsDead, unitID)
  return ok and not alive
end

-- Supply state of a point for pathing cost purposes. Returns true/false when
-- the logistics gadget is available, nil when it is not (no penalty applied).
local function pointSupplied(teamID, x, z)
  local api = GG and GG.MedievalLogistics
  if not (api and api.SupplyStateAt) then return nil end
  local state = api.SupplyStateAt(teamID, x, z)
  if not state then return nil end
  return state.inSupply == true
end

-- Whether a point lies on the team's road network (true/false), or nil when the
-- logistics gadget is unavailable. Used to make road-adjacent nodes cheaper.
local function pointOnNetwork(teamID, x, z)
  local api = GG and GG.MedievalLogistics
  if not (api and api.PointOnRoadNetwork) then return nil end
  local ok, onRoad = pcall(api.PointOnRoadNetwork, teamID, x, z)
  if not ok then return nil end
  return onRoad == true
end

local function nearestNode(ux, uz, resource, teamID)
  -- Nodes are registered by FeatureCreated; resource is optional for auto-assignment.
  -- Selection is cost-based (Slice 7): a node off the team's road network costs
  -- more, so villagers prefer harvest sites they can haul from along roads.
  -- With no roads every node is penalized equally and nearest-wins is unchanged.
  local candidates = {}
  for featureID, node in pairs(nodes) do
    if node.remaining > 0 and (resource == nil or node.resource == resource) then
      local x, _, z = featurePos(featureID)
      if x then
        local supplied
        if teamID ~= nil then supplied = pointOnNetwork(teamID, x, z) end
        candidates[#candidates + 1] = {
          key = featureID, x = x, z = z, supplied = supplied,
        }
      end
    end
  end
  local best = gather.bestCandidate(candidates, ux, uz)
  return best
end

local function nearestDropoff(ux, uz, resource, teamID)
  -- Cost-based selection (Slice 7): a dropoff that is not on the team's supply
  -- network costs PATH_COST_UNSUPPLIED times its distance, so a villager walks
  -- past an unsupplied shed to a road-connected one.
  local candidates = {}
  for dropTeamID, list in pairs(dropoffs) do
    if resource == nil or (allowsResource[dropTeamID] and allowsResource[dropTeamID][resource]) then
      for unitID in pairs(list) do
        local x, _, z = unitPos(unitID)
        if x then
          local supplied
          if dropTeamID ~= nil then supplied = pointSupplied(dropTeamID, x, z) end
          candidates[#candidates + 1] = {
            key = unitID, x = x, z = z, supplied = supplied,
          }
        end
      end
    end
  end
  local best = gather.bestCandidate(candidates, ux, uz)
  return best
end

-- Drop-off registry: dropoffs[teamID][buildingUnitID] = true
-- allowsResource[teamID][resource] = true if some dropoff of that team accepts it
local function refreshTeamDropoffs(teamID)
  dropoffs[teamID] = dropoffs[teamID] or {}
  allowsResource[teamID] = allowsResource[teamID] or {}
  local anyGeneric = false
  for uid in pairs(dropoffs[teamID]) do
    if alive(uid) then
      local defID = Spring.GetUnitDefID(uid)
      local def = UnitDefs and UnitDefs[defID]
      local ok, r = pcall(function() return def.customParams.dropoff_resource end)
      if ok and r then
        allowsResource[teamID][r] = true
      else
        anyGeneric = true
      end
    end
  end
  -- generic dropoffs (no dropoff_resource) accept all four resources
  if anyGeneric then
    for _, r in ipairs({ "food", "wood", "stone", "iron" }) do
      allowsResource[teamID][r] = true
    end
  end
end

local function registerDropoff(unitID, teamID)
  dropoffs[teamID] = dropoffs[teamID] or {}
  dropoffs[teamID][unitID] = true
  refreshTeamDropoffs(teamID)
end

local function unregisterDropoff(unitID, teamID)
  if dropoffs[teamID] then
    dropoffs[teamID][unitID] = nil
    refreshTeamDropoffs(teamID)
  end
end

-- Register a drop-off building as it is created (unit, not feature).
function gadget:UnitCreated(unitID, unitDefID, teamID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if def and def.customParams and def.customParams.dropoff then
    registerDropoff(unitID, teamID)
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  unregisterDropoff(unitID, teamID)
  jobs[unitID] = nil
end

-- ---------------------------------------------------------------------------
-- Work-cycle API and command handling
-- ---------------------------------------------------------------------------

local function issueMove(unitID, x, y, z)
  pcall(Spring.GiveOrderToUnit, unitID, CMD.MOVE, { x, y, z }, 0)
end

local function stopUnit(unitID)
  pcall(Spring.GiveOrderToUnit, unitID, CMD.STOP, {}, 0)
end

-- Begin or resume gathering for a villager. nodeID is optional (auto-pick nearest).
local function assignGather(unitID, nodeID)
  if not alive(unitID) then return false end
  local x, y, z = unitPos(unitID)
  if not x then return false end

  if not nodeID then
    nodeID = nearestNode(x, z, nil, Spring.GetUnitTeam(unitID))
  end
  if not nodeID or not (nodes[nodeID] and nodes[nodeID].remaining > 0) then
    jobs[unitID] = nil
    stopUnit(unitID)
    return false
  end

  local node = nodes[nodeID]
  jobs[unitID] = {
    state = "move_node",
    nodeID = nodeID,
    resource = node.resource,
    carried = 0,
  }
  local nx, ny, nz = featurePos(nodeID)
  if nx then issueMove(unitID, nx, ny, nz) end
  return true
end

-- Deliver a villager's carried resource to the nearest compatible dropoff.
local function assignDeliver(unitID, dropoffID)
  if not alive(unitID) then return false end
  local job = jobs[unitID]
  if not job or not (job.carried and job.carried > 0) then
    -- If idle with nothing carried, just resume gathering.
    return assignGather(unitID, nil)
  end
  local teamID = Spring.GetUnitTeam(unitID)

  if not dropoffID then
    local x, _, z = unitPos(unitID)
    if not x then return false end
    refreshTeamDropoffs(teamID)
    dropoffID = nearestDropoff(x, z, job.resource, teamID)
  end
  if not dropoffID then
    return false  -- no compatible dropoff; hold (resume later)
  end

  job.state = "move_drop"
  job.dropoffID = dropoffID
  local dx, dy, dz = unitPos(dropoffID)
  if dx then issueMove(unitID, dx, dy, dz) end
  return true
end

function gadget:Initialize()
  -- Register custom command IDs (371920, 371921).
  local ok = pcall(gadgetHandler.RegisterCMDID, gadgetHandler, CMD_GATHER)
  if ok then gadgetHandler:RegisterAllowCommand(CMD.ANY) end
  pcall(gadgetHandler.RegisterCMDID, gadgetHandler, CMD_DELIVER)
end

function gadget:AllowCommand(unitID, unitDefID, teamID, cmdID, params, opts)
  if cmdID ~= CMD_GATHER and cmdID ~= CMD_DELIVER then
    return true
  end
  -- Reject modifier-heavy queueing; these are immediate action commands.
  if opts and (opts.shift or opts.alt or opts.ctrl or opts.right) then return false end

  if cmdID == CMD_GATHER then
    local nodeID = params and params[1]
    if nodeID and not nodes[nodeID] then return false end
  elseif cmdID == CMD_DELIVER then
    local job = jobs[unitID]
    if not (job and job.carried and job.carried > 0) then return false end
  end
  return false  -- consume; actual side effects applied on the deferred GameFrame pass
end

local function deferredAssignments()
  -- AllowCommand collected intent; actionable commands are applied on next frame.
end

GG = GG or {}
GG.MedievalGather = {
  AssignGather = assignGather,
  AssignDeliver = assignDeliver,
  GetJob = function(unitID) return jobs[unitID] end,
  GetCarried = function(unitID)
    local job = jobs[unitID]
    return job and job.carried or 0
  end,
  NodeRemaining = function(featureID) return nodes[featureID] and nodes[featureID].remaining or 0 end,
}

-- ---------------------------------------------------------------------------
-- Per-frame work-cycle update
-- ---------------------------------------------------------------------------

function gadget:GameFrame(frame)
  for unitID, job in pairs(jobs) do
    if not alive(unitID) then
      jobs[unitID] = nil
    end
  end

  for unitID, job in pairs(jobs) do
    local state = job.state
    local teamID = Spring.GetUnitTeam(unitID)

    if state == "move_node" then
      local node = nodes[job.nodeID]
      if not node or node.remaining <= 0 then
        assignGather(unitID, nil)
      else
        local ux, _, uz = unitPos(unitID)
        local nx, _, nz = featurePos(job.nodeID)
        if ux and nx and gather.inHarvestRange(ux, uz, nx, nz) then
          stopUnit(unitID)
          job.state = "harvest"
        end
      end

    elseif state == "harvest" then
      local node = nodes[job.nodeID]
      if not node or node.remaining <= 0 then
        job.nodeID = nil
        assignDeliver(unitID, nil)
      else
        local ux, _, uz = unitPos(unitID)
        local nx, _, nz = featurePos(job.nodeID)
        if not (ux and nx and gather.inHarvestRange(ux, uz, nx, nz)) then
          job.state = "move_node"
          local _, ny = featurePos(job.nodeID)
          issueMove(unitID, nx, ny, nz)
        else
          local amount = gather.harvestAmount(
            node.defID and (FeatureDefs and FeatureDefs[node.defID] and FeatureDefs[node.defID].name or "tree") or "medieval_tree",
            node.remaining,
            job.carried,
            1
          )
          if amount > 0 then
            job.carried = (job.carried or 0) + amount
            node.remaining = node.remaining - amount
          end
          if gather.carryFull(job.carried) or node.remaining <= 0 then
            assignDeliver(unitID, nil)
          end
        end
      end

    elseif state == "move_drop" then
      local dx, _, dz = unitPos(job.dropoffID)
      local ux, _, uz = unitPos(unitID)
      if not (dx and ux) then
        -- dropoff gone; try to re-acquire
        job.state = "deliver"
      elseif gather.inDropoffRange(ux, uz, dx, dz) then
        stopUnit(unitID)
        job.state = "deliver"
      end

    elseif state == "deliver" then
      local econ = GG.MedievalEconomy
      if econ and job.carried and job.carried > 0 then
        econ.Deposit(teamID, job.resource, math.floor(job.carried + 0.5))
      end
      job.carried = 0
      local node = nodes[job.nodeID]
      if node and node.remaining > 0 then
        assignGather(unitID, job.nodeID)
      else
        job.nodeID = nil
        assignGather(unitID, nil)
      end
    end
  end
end