-- Shared, pure medieval logistics, tech upgrades, and fortification definitions.
-- No engine calls in this module.
local M = {
  ROAD_SPEED_MULT = 1.5,
  ROAD_PROXIMITY_RADIUS = 48.0, -- distance in elmos within which a unit is considered on a road
  ROAD_PLACEMENT_MIN_SPACING = 32.0, -- minimum distance in elmos between road placements

  BUILD_LINK_RADIUS = 64.0, -- supply-endpoint buildings must lie within this distance of a road node (matches medieval_road_graph.LINK_RADIUS)

  COSTS = {
    medieval_road = { wood = 5, stone = 2 },
    medieval_wall = { wood = 10, stone = 40 },
    medieval_tower = { wood = 20, stone = 50 },
  },

  TECHS = {
    iron_swords = {
      name = "Iron Swords",
      cost = { wood = 50, iron = 100 },
      prereq = nil,
      description = "+25% infantry melee damage",
      damage_mult = { medieval_infantry = 1.25 },
    },
    plate_armor = {
      name = "Plate Armor",
      cost = { iron = 150 },
      prereq = "iron_swords",
      description = "+25% infantry and cavalry max HP",
      health_mult = { medieval_infantry = 1.25, medieval_cavalry = 1.25 },
    },
    masonry = {
      name = "Masonry",
      cost = { stone = 150, wood = 50 },
      prereq = nil,
      description = "+50% wall and tower hitpoints",
      health_mult = { medieval_wall = 1.5, medieval_tower = 1.5 },
    },
  },
}

function M.getCost(defName)
  local c = M.COSTS[defName]
  if not c then return nil end
  local out = {}
  for k, v in pairs(c) do out[k] = v end
  return out
end

function M.getTech(techID)
  return M.TECHS[techID]
end

function M.canResearch(unlocked, techID, stock, economy)
  local t = M.TECHS[techID]
  if not t then return false, "unknown_tech" end
  unlocked = unlocked or {}
  if unlocked[techID] then return false, "already_researched" end
  if t.prereq and not unlocked[t.prereq] then return false, "prereq_missing" end
  if stock and economy and type(economy.canAffordCosts) == "function" then
    if not economy.canAffordCosts(stock, t.cost) then
      return false, "insufficient_resources"
    end
  end
  return true
end

function M.applyUnlock(unlocked, techID)
  local t = M.TECHS[techID]
  if not t then return nil end
  local copy = {}
  if type(unlocked) == "table" then
    for k, v in pairs(unlocked) do copy[k] = v end
  end
  copy[techID] = true
  return copy
end

-- Team-local attachment, not connectivity to every component or another endpoint.
-- Pass only the team's road nodes. Invalid coordinates/roads/radius return false;
-- malformed nodes are ignored. The boundary is inclusive, like LINK_RADIUS.
function M.isBuildingConnected(roads, x, z, radius)
  local function finite(n)
    return type(n) == "number" and n == n and n > -math.huge and n < math.huge
  end
  if not finite(x) or not finite(z) or type(roads) ~= "table" then return false end
  if radius == nil then radius = M.BUILD_LINK_RADIUS end
  if not finite(radius) or radius < 0 then return false end
  for _, node in pairs(roads) do
    if type(node) == "table" and finite(node.x) and finite(node.z) then
      local dx, dz = x - node.x, z - node.z
      if dx * dx + dz * dz <= radius * radius then return true end
    end
  end
  return false
end

M.isSupplyEndpointConnected = M.isBuildingConnected

-- Normalize truthiness for customParams values that may be Lua booleans,
-- strings like "true"/"false"/"1"/"0", or numbers.
local TRUTHY_STRINGS = { ["true"] = true, ["1"] = true, ["yes"] = true, ["on"] = true }
local FALSY_STRINGS = { ["false"] = true, ["0"] = true, ["no"] = true, ["off"] = true, [""] = true }

function M.truthy(value)
  if value == nil then return false end
  if type(value) == "boolean" then return value end
  if type(value) == "number" then return value ~= 0 end
  if type(value) == "string" then
    local key = string.lower(value)
    if TRUTHY_STRINGS[key] then return true end
    if FALSY_STRINGS[key] then return false end
    return false
  end
  return false
end

-- Engine defs expose customparams with lowercase keys; source-side defs may
-- use customParams with mixed case. Check both spellings and normalize.
function M.isSupplyEndpointDef(def)
  if not def then return false end
  local cp = def.customParams or def.customparams
  if not cp then return false end
  if cp.dropoff ~= nil then return M.truthy(cp.dropoff) end
  if cp.DropOff ~= nil then return M.truthy(cp.DropOff) end
  return false
end

-- Same-team road attachment for supply endpoints. When the team has no roads
-- yet the endpoint is allowed regardless of position (bootstrap).
function M.isEndpointPlacementAllowed(roads, x, z, radius)
  if x == nil or z == nil then return true end
  local function finite(n)
    return type(n) == "number" and n == n and n > -math.huge and n < math.huge
  end
  if not finite(x) or not finite(z) then return false end
  if type(roads) ~= "table" or next(roads) == nil then return true end
  return M.isBuildingConnected(roads, x, z, radius)
end

function M.isBuildingConnectedSummary(buildings, roads, radius)
  local summary = { total = 0, connected = 0, disconnected = 0 }
  for _ in pairs(buildings or {}) do summary.total = summary.total + 1 end
  if type(roads) ~= "table" or next(roads) == nil then
    summary.connected = summary.total
    return summary
  end
  for _, b in pairs(buildings or {}) do
    if M.isBuildingConnected(roads, b.x, b.z, radius) then
      summary.connected = summary.connected + 1
    else
      summary.disconnected = summary.disconnected + 1
    end
  end
  return summary
end

function M.isPositionOnRoad(x, z, roadCoords, radius)
  if type(x) ~= "number" or type(z) ~= "number" then return false end
  if type(roadCoords) ~= "table" then return false end
  radius = radius or M.ROAD_PROXIMITY_RADIUS
  local r2 = radius * radius
  for _, coord in pairs(roadCoords) do
    if type(coord) == "table" and type(coord.x) == "number" and type(coord.z) == "number" then
      local dx = x - coord.x
      local dz = z - coord.z
      if (dx * dx + dz * dz) <= r2 then
        return true
      end
    end
  end
  return false
end

function M.speedMultiplier(isOnRoad)
  if isOnRoad then
    return M.ROAD_SPEED_MULT
  end
  return 1.0
end

function M.damageMultiplier(unlocked, unitName)
  if not unlocked or type(unlocked) ~= "table" then return 1.0 end
  local mult = 1.0
  for techID, active in pairs(unlocked) do
    if active and M.TECHS[techID] and M.TECHS[techID].damage_mult then
      local bonus = M.TECHS[techID].damage_mult[unitName]
      if bonus then mult = mult * bonus end
    end
  end
  return mult
end

function M.healthMultiplier(unlocked, unitName)
  if not unlocked or type(unlocked) ~= "table" then return 1.0 end
  local mult = 1.0
  for techID, active in pairs(unlocked) do
    if active and M.TECHS[techID] and M.TECHS[techID].health_mult then
      local bonus = M.TECHS[techID].health_mult[unitName]
      if bonus then mult = mult * bonus end
    end
  end
  return mult
end

function M.isBuildable(defName)
  return M.COSTS[defName] ~= nil
end

function M.scaledDamage(baseDamage, multiplier)
  local d = baseDamage * multiplier
  if d < 0 then d = 0 end
  return d
end

local function finiteNumber(value)
  return type(value) == "number" and value == value and value > -math.huge and value < math.huge
end

function M.canPlaceRoad(x, z, existingRoads, stock, minSpacing)
  if not finiteNumber(x) or not finiteNumber(z) then
    return false, "invalid_coordinates"
  end
  minSpacing = minSpacing or M.ROAD_PLACEMENT_MIN_SPACING
  if not finiteNumber(minSpacing) or minSpacing < 0 then return false, "invalid_spacing" end
  local spacingSquared = minSpacing * minSpacing
  for _, coord in pairs(type(existingRoads) == "table" and existingRoads or {}) do
    if type(coord) == "table" and finiteNumber(coord.x) and finiteNumber(coord.z) then
      local dx, dz = x - coord.x, z - coord.z
      if dx * dx + dz * dz <= spacingSquared then return false, "too_close" end
    end
  end
  stock = type(stock) == "table" and stock or {}
  for resource, amount in pairs(M.COSTS.medieval_road) do
    if not finiteNumber(stock[resource]) or stock[resource] < amount then
      return false, "insufficient_resources"
    end
  end
  return true, "ok"
end

function M.roadBuildQueueValidation(canAfford, costs)
  if type(costs) ~= "table" then
    return "bad_costs"
  end
  if canAfford then
    return "ok"
  end
  return "insufficient_resources"
end

return M
