-- Shared, pure medieval gathering math; no engine calls in this module.
-- The synced gather gadget owns per-unit and per-node state, but delegates all
-- arithmetic here so the harvest/deliver cycle is unit-testable in isolation.
local M = {
  RESOURCE_COLORS = { food = "green", wood = "brown", stone = "grey", iron = "grey" },
  HARVEST_RATE = 2,          -- resource units per second
  CARRY_CAPACITY = 10,       -- villager inventory threshold
  HARVEST_RADIUS = 40,       -- elmos; within this distance harvesting ticks
  DROPOFF_RADIUS = 64,       -- elmos; within this distance deposit succeeds
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

return M