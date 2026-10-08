-- Shared, pure medieval logistics, tech upgrades, and fortification definitions.
-- No engine calls in this module.
local M = {
  ROAD_SPEED_MULT = 1.5,
  ROAD_PROXIMITY_RADIUS = 48.0, -- distance in elmos within which a unit is considered on a road
  ROAD_PLACEMENT_MIN_SPACING = 32.0, -- minimum distance in elmos between road placements

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
