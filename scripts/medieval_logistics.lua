-- Shared, pure medieval logistics, tech upgrades, and fortification definitions.
-- No engine calls in this module.
local M = {
  ROAD_SPEED_MULT = 1.5,
  ROAD_PROXIMITY_RADIUS = 48.0, -- distance in elmos within which a unit is considered on a road
  ROAD_PLACEMENT_MIN_SPACING = 32.0, -- minimum distance in elmos between road placements

  BUILD_LINK_RADIUS = 64.0, -- supply-endpoint buildings must lie within this distance of a road node (matches medieval_road_graph.LINK_RADIUS)

  -- Supply bonus policy: every road-connected supply endpoint projects a supply
  -- area around itself and adds an additive bonus, capped at SUPPLY_BONUS_MAX.
  SUPPLY_RADIUS = 96.0,            -- elmos; within this distance of a connected endpoint a unit is in supply
  SUPPLY_BONUS_PER_ENDPOINT = 0.10,
  SUPPLY_BONUS_MAX = 0.50,

  -- Road-aware pathing policy: legs that run along the road network are cheaper
  -- than open ground, and targets that are not attached to the network are
  -- penalized so routes prefer supplied destinations.
  ROAD_PATH_COST_MULT = 0.75,
  UNSUPPLIED_PATH_COST_MULT = 1.5,

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
    -- Military unlock techs. `unlocks` lists the unit defs the tech makes
    -- trainable; `damage_mult` is the per-unit damage bonus, keyed by unit name
    -- and folded multiplicatively by M.damageMultiplier. A tech may boost both
    -- the base unit and the advanced unit it unlocks (veteran_infantry).
    veteran_infantry = {
      name = "Veteran Infantry",
      cost = { iron = 50, wood = 50 },
      prereq = nil,
      description = "Unlocks Men-at-Arms; +15% melee damage for infantry and men-at-arms",
      unlocks = { medieval_men_at_arms = true },
      damage_mult = { medieval_infantry = 1.15, medieval_men_at_arms = 1.15 },
    },
    crossbow_tech = {
      name = "Crossbow Technology",
      cost = { wood = 60, iron = 40 },
      prereq = nil,
      description = "Unlocks Crossbowmen; +15% ranged damage for archers and crossbows",
      unlocks = { medieval_crossbow = true },
      damage_mult = { medieval_archer = 1.15, medieval_crossbow = 1.15 },
    },
    chivalry = {
      name = "Chivalry",
      cost = { food = 80, iron = 60 },
      prereq = nil,
      description = "Unlocks Knights; +20% damage for cavalry and knights",
      unlocks = { medieval_knight = true },
      damage_mult = { medieval_cavalry = 1.20, medieval_knight = 1.20 },
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

-- Tech that makes a unit trainable, or nil when the unit is not tech-gated.
-- Derived from the `unlocks` field on TECHS so the registry stays the single
-- source of truth for which tech opens which unit.
function M.techUnlockPrereq(unitName)
  if type(unitName) ~= "string" then return nil end
  for techID, t in pairs(M.TECHS) do
    if type(t) == "table" and type(t.unlocks) == "table" and t.unlocks[unitName] then
      return techID
    end
  end
  return nil
end

-- Whether a unit may be trained given a team's unlocked-tech table. Units with
-- no tech prereq always pass; a gated unit with no/nil unlocked table fails
-- closed so an unpublished registry can never leak advanced units.
function M.isUnitUnlocked(unlocked, unitName)
  local prereq = M.techUnlockPrereq(unitName)
  if not prereq then return true end
  if type(unlocked) ~= "table" then return false end
  return unlocked[prereq] and true or false
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

-- Road movement-speed policy. baseSpeed is in elmos/sec (the unit def's speed).
-- Non-numeric or non-positive bases pass through untouched so callers never
-- have to guess whether a def is speed-controllable.
function M.targetSpeed(baseSpeed, onRoad)
  if type(baseSpeed) ~= "number" or baseSpeed <= 0 then
    return baseSpeed
  end
  return baseSpeed * M.speedMultiplier(onRoad == true)
end

-- A unit def is speed-eligible when it can move. Mobility is the reliable
-- engine discriminator for this total conversion: every source building def
-- sets `canMove = false` (and none sets `isBuilding`), so the engine's derived
-- `isBuilding` field is false/nil for static structures and cannot be used to
-- exclude them. Villagers are builders (canBuild) but stay eligible.
function M.isEligibleSpeedUnitDef(def)
  return def ~= nil and def.canMove == true
end

-- ---------------------------------------------------------------------------
-- Supply bonuses
-- ---------------------------------------------------------------------------
-- A unit is "in supply" when it stands within SUPPLY_RADIUS of at least one
-- supply endpoint that is itself attached to the team's road network
-- (BUILD_LINK_RADIUS). Only connected endpoints project supply: an endpoint
-- whose road was destroyed stops supplying immediately, matching the live
-- recomputation the connectivity queries already use. The bonus is additive
-- per contributing endpoint and clamped to SUPPLY_BONUS_MAX, so a dense road
-- network cannot multiply a unit's effectiveness without bound.

local function finiteNum(n)
  return type(n) == "number" and n == n and n > -math.huge and n < math.huge
end

-- Road-connected endpoints whose supply area covers (x, z). Malformed input
-- yields 0 rather than an error so callers can query freely.
function M.supplyEndpointCount(buildings, roads, x, z, supplyRadius, linkRadius)
  if not finiteNum(x) or not finiteNum(z) then return 0 end
  if type(buildings) ~= "table" or type(roads) ~= "table" then return 0 end
  if supplyRadius == nil then supplyRadius = M.SUPPLY_RADIUS end
  if linkRadius == nil then linkRadius = M.BUILD_LINK_RADIUS end
  if not finiteNum(supplyRadius) or supplyRadius < 0 then return 0 end
  if not finiteNum(linkRadius) or linkRadius < 0 then return 0 end
  local count = 0
  for _, b in pairs(buildings) do
    if type(b) == "table" and finiteNum(b.x) and finiteNum(b.z) then
      local dx, dz = x - b.x, z - b.z
      if (dx * dx + dz * dz) <= supplyRadius * supplyRadius
        and M.isBuildingConnected(roads, b.x, b.z, linkRadius) then
        count = count + 1
      end
    end
  end
  return count
end

-- Additive bonus for `count` contributing endpoints, clamped to maxBonus.
-- Non-finite or negative counts contribute nothing.
function M.supplyBonus(count, perEndpoint, maxBonus)
  if perEndpoint == nil then perEndpoint = M.SUPPLY_BONUS_PER_ENDPOINT end
  if maxBonus == nil then maxBonus = M.SUPPLY_BONUS_MAX end
  if not finiteNum(count) or count <= 0 then return 0 end
  if not finiteNum(perEndpoint) or perEndpoint <= 0 then return 0 end
  if not finiteNum(maxBonus) or maxBonus <= 0 then return 0 end
  local bonus = count * perEndpoint
  if bonus > maxBonus then bonus = maxBonus end
  return bonus
end

-- A unit def receives supply when it is a mobile unit. Buildings in this
-- total conversion are identified by `canMove == false` (every static def sets
-- it; the engine exposes `isBuilding` as false/nil for them, so that field
-- cannot exclude buildings). Static fortifications are supplied by the same
-- endpoints but gain nothing from a damage/speed bonus, so they are not tracked.
function M.isSupplyEligibleUnitDef(def)
  return def ~= nil and def.canMove == true
end

-- Full supply state for a point: contributing endpoint count, raw additive
-- bonus, the resulting multiplier (1 + bonus), and the in-supply verdict.
function M.supplyState(buildings, roads, x, z, supplyRadius, linkRadius)
  local count = M.supplyEndpointCount(buildings, roads, x, z, supplyRadius, linkRadius)
  local bonus = M.supplyBonus(count)
  return {
    count = count,
    bonus = bonus,
    multiplier = 1.0 + bonus,
    inSupply = count > 0,
  }
end

function M.isInSupply(buildings, roads, x, z, supplyRadius, linkRadius)
  return M.supplyEndpointCount(buildings, roads, x, z, supplyRadius, linkRadius) > 0
end

-- ---------------------------------------------------------------------------
-- Road-aware pathing cost model
-- ---------------------------------------------------------------------------
-- Pure cost policy for choosing between an open-ground leg and a road leg.
-- Road legs are discounted; a destination that is known to be off the supply
-- network is penalized so routes prefer supplied destinations. An unknown
-- destination (`targetSupplied == nil`) is never penalized - the model stays
-- conservative when the caller has no connectivity information.

function M.pathCostMultiplier(onRoad, targetSupplied)
  local mult = 1.0
  if onRoad == true then mult = mult * M.ROAD_PATH_COST_MULT end
  if targetSupplied == false then mult = mult * M.UNSUPPLIED_PATH_COST_MULT end
  return mult
end

-- Cost of a leg of `distance` elmos. Invalid or negative distances are
-- unreachable (math.huge) rather than silently free.
function M.pathCost(distance, onRoad, targetSupplied)
  if not finiteNum(distance) or distance < 0 then return math.huge end
  return distance * M.pathCostMultiplier(onRoad, targetSupplied)
end

-- Whether the road route should be preferred over the open-ground route.
-- Non-finite or negative costs are not preferred; ties keep the open route.
function M.roadRoutePreferred(openCost, roadCost)
  if not finiteNum(roadCost) or roadCost < 0 then return false end
  if not finiteNum(openCost) or openCost < 0 then return false end
  return roadCost < openCost
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
