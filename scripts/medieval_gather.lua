-- Shared, pure medieval gathering math; no engine calls in this module.
-- The synced gather gadget owns per-unit and per-node state, but delegates all
-- arithmetic here so the harvest/deliver cycle is unit-testable in isolation.
local M = {
  RESOURCE_COLORS = { food = "green", wood = "brown", stone = "grey", iron = "grey" },
  HARVEST_RATE = 2,          -- resource units per second
  CARRY_CAPACITY = 10,       -- villager inventory threshold
  HARVEST_RADIUS = 40,       -- elmos; within this distance harvesting ticks
  DROPOFF_RADIUS = 64,       -- elmos; within this distance deposit succeeds
  -- Multiplier applied to the distance of a destination that is NOT on the
  -- team's supply network; supplied/unknown destinations use 1.0.
  PATH_COST_UNSUPPLIED = 1.5,
  DEFAULT_NODE_CAPACITY = 500,
  NODE_CAPACITY_BY_TYPE = {
    medieval_tree = 500,
    medieval_stone = 400,
    medieval_iron = 300,
    medieval_deer = 250,
  },
}

local floor = math.floor
local huge = math.huge

function M.finite(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- Resource type keyed by node definition name.
function M.nodeResource(defName)
  local map = {
    medieval_tree = "wood",
    medieval_stone = "stone",
    medieval_iron = "iron",
    medieval_deer = "food",
  }
  return map[defName]
end

-- Remaining capacity of a node definition.
function M.nodeCapacity(defName)
  return (M.NODE_CAPACITY_BY_TYPE[defName]) or M.DEFAULT_NODE_CAPACITY
end

-- Harvested amount per sim tick (frame), bounded by node remaining and carry space.
-- dtFrames is the number of sim frames elapsed since the previous tick.
function M.harvestAmount(defName, nodeRemaining, carried, dtFrames)
  local rate = M.HARVEST_RATE or 2
  if not M.finite(dtFrames) or dtFrames <= 0 then return 0 end
  local perFrame = rate / 30
  local nodeCap = M.nodeCapacity(defName)
  local fromNode = math.max(0, math.min(nodeRemaining, nodeCap))
  local toCarry = math.max(0, M.CARRY_CAPACITY - carried)
  local raw = math.min(fromNode, toCarry, perFrame * dtFrames)
  return math.floor(raw * 100) / 100
end

-- Whether a villager inventory has reached carrying threshold.
function M.carryFull(carried)
  return M.finite(carried) and carried >= M.CARRY_CAPACITY
end

-- Distance in the XZ plane; nil for malformed coordinates.
function M.planarDist(ax, az, bx, bz)
  if not (M.finite(ax) and M.finite(az) and M.finite(bx) and M.finite(bz)) then return nil end
  local dx, dz = ax - bx, az - bz
  return math.sqrt(dx * dx + dz * dz)
end

-- Within-harvest-radius predicate.
function M.inHarvestRange(ax, az, bx, bz)
  local d = M.planarDist(ax, az, bx, bz)
  return d ~= nil and d <= M.HARVEST_RADIUS
end

-- Within-dropoff-radius predicate.
function M.inDropoffRange(ax, az, bx, bz)
  local d = M.planarDist(ax, az, bx, bz)
  return d ~= nil and d <= M.DROPOFF_RADIUS
end

-- ---------------------------------------------------------------------------
-- Road-aware route selection
-- ---------------------------------------------------------------------------
-- Destination choice uses a cost, not raw distance: a destination that is not
-- on the team's supply network costs PATH_COST_UNSUPPLIED times its distance,
-- so a villager walks past an unsupplied shed to a road-connected one. An
-- unknown supply state (nil) is never penalized - the caller may simply have
-- no road network yet, and the pre-road behaviour must be unchanged.

function M.pathCost(ux, uz, tx, tz, supplied)
  local d = M.planarDist(ux, uz, tx, tz)
  if d == nil then return nil end
  if supplied == false then return d * M.PATH_COST_UNSUPPLIED end
  return d
end

-- Lowest-cost entry of `candidates` (each { key=, x=, z=, supplied= }) for a
-- unit at (ux, uz). Returns key, cost; nil, nil when nothing is reachable.
function M.bestCandidate(candidates, ux, uz)
  if type(candidates) ~= "table" then return nil, nil end
  local bestKey, bestCost
  for _, c in ipairs(candidates) do
    if type(c) == "table" then
      local cost = M.pathCost(ux, uz, c.x, c.z, c.supplied)
      if cost ~= nil and (bestCost == nil or cost < bestCost) then
        bestKey, bestCost = c.key, cost
      end
    end
  end
  return bestKey, bestCost
end

return M