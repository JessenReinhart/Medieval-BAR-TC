-- Shared, pure medieval skirmish-AI decision policy; no engine calls in this
-- module. The synced AI gadget (luarules/gadgets/gadget_medieval_skirmish_ai.lua)
-- owns team enablement, unit tracking, the GG API surface and every Spring.*
-- call, and delegates each "what should happen next" question and every
-- placement calculation here so the policy is unit-testable in isolation.
--
-- Loadability contract: this file must stay loadable by a bare Lua 5.1/LuaJIT
-- interpreter with no VFS/Spring present, so it never VFS.Include()s a sibling
-- module. The small amount of shared data it needs (the military def set) is
-- inlined and mirrors scripts/medieval_recruitment.lua UPKEEP > 0.
--
-- Totality: every decision function answers the conservative verdict
-- (false / nil / "none") for malformed or missing inputs instead of raising,
-- so a gadget can call it with partially-populated state without a pcall guard.
local M = {
  -- Construction / recruitment costs charged through GG.MedievalEconomy.
  HOUSE_COST = { wood = 60 },
  ROAD_COST = { wood = 5, stone = 2 },
  INFANTRY_COST = { food = 30, wood = 20, stone = 10, iron = 5 },

  -- Decision thresholds.
  HOUSE_POP_BUFFER = 3, -- build a house when (cap - pop) <= this
  -- Phase 6 Slice 4: old 2 -> 3 (build housing one pop earlier so recruitment
  -- never blocks on a nearly-full pop cap).
  ATTACK_ARMY_MIN = 2,  -- attack when the field army reaches this size

  -- Optional-argument defaults.
  DEFAULT_MAX_ROADS = 5,
  DEFAULT_MAX_ARMY = 10,
  ROAD_MIN_DISTANCE = 32.0, -- elmos; a midpoint this close to a road is linked

  -- Gathering: the resource furthest below its target proportion is harvested
  -- first; GATHER_ORDER breaks ties so the choice is deterministic.
  -- Phase 6 Slice 4: food target 100 -> 110. Food is the only standing drain
  -- (recruit cost + per-tick upkeep), so weighting it higher banks food early
  -- and keeps the settlement from stalling on food.
  GATHER_TARGETS = { food = 110, wood = 100, stone = 50, iron = 30 },
  GATHER_ORDER = { "food", "wood", "stone", "iron" },

  -- AI thinks once per second (30 sim frames) rather than every frame.
  CADENCE_FRAMES = 30,

  -- Attack search radius (elmos) used by the gadget to locate an enemy target.
  ATTACK_RADIUS = 3000,

  -- Placement offsets in elmos, relative to the team's town center / barracks.
  HOUSE_OFFSET = 96,
  ROAD_OFFSET = 160,

  -- Recruitment identity, kept here so gadget and policy never disagree.
  RECRUIT_DEF = "medieval_infantry",
  RECRUIT_COST = { food = 30, wood = 20, stone = 10, iron = 5 },

  -- Legacy alias retained for callers of the earlier threshold name.
  -- Phase 6 Slice 4: old 2 -> 3 (lock-step with HOUSE_POP_BUFFER).
  HOUSE_POP_THRESHOLD = 3,
  MAX_ROADS = 5,
  ARMY_TARGET = 10,
}

-- Military def names: exactly the upkeep-paying units of
-- scripts/medieval_recruitment.lua (the civilian cart pays 0 and is excluded).
local MILITARY_DEFS = {
  "medieval_infantry",
  "medieval_archer",
  "medieval_cavalry",
  "medieval_catapult",
  "medieval_men_at_arms",
  "medieval_crossbow",
  "medieval_knight",
}

-- Set form ({ name = true }) as the gadget indexes it directly.
M.MILITARY_SET = {}
for _, name in ipairs(MILITARY_DEFS) do
  M.MILITARY_SET[name] = true
end

-- Phase 6 Slice 4 reactive recruit: classify each military def into a
-- tactical role, then train the unit that counters the opponent's majority
-- role. Upgraded tiers collapse onto their base unit's role. The roster has
-- no dedicated spearman def, so the armoured veteran `medieval_men_at_arms`
-- fills the anti-cavalry slot (Infantry counters Cavalry closes the loop that
-- the doc's "Spearman counters Cavalry" edge would otherwise leave open).
M.ROLE_OF = {
  medieval_infantry = "melee",
  medieval_men_at_arms = "melee",
  medieval_archer = "ranged",
  medieval_crossbow = "ranged",
  medieval_cavalry = "cavalry",
  medieval_knight = "cavalry",
  medieval_catapult = "siege",
}

-- The recruit def to train in reaction to each opponent-majority role.
M.COUNTER_RECRUIT = {
  melee   = "medieval_archer",      -- ranged kites melee before contact
  ranged  = "medieval_cavalry",     -- cavalry speed + charge overruns ranged
  cavalry = "medieval_men_at_arms", -- armoured veteran infantry braces the charge
  siege   = "medieval_cavalry",     -- fast cavalry closes on siege before it fires
}

-- Deterministic tie-break order for majorityRole when two roles are equal.
M.ROLE_ORDER = { "melee", "ranged", "cavalry", "siege" }

local floor = math.floor
local huge = math.huge
local sqrt = math.sqrt

local function isNum(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- A stock table, or an empty one when the caller passed nothing usable.
local function stockOf(stock)
  if type(stock) == "table" then return stock end
  return {}
end

-- Read {x, z} (or {x=, z=}) out of a position-like entry; nil when malformed.
local function coordOf(entry)
  if type(entry) ~= "table" then return nil end
  local x, z = entry.x, entry.z
  if not isNum(x) or not isNum(z) then
    x, z = entry[1], entry[2]
  end
  if not isNum(x) or not isNum(z) then return nil end
  return x, z
end

-- Does any existing road lie within `minDistance` of (x, z)?
local function hasRoadNear(existingRoads, x, z, minDistance)
  if type(existingRoads) ~= "table" then return false end
  for _, entry in pairs(existingRoads) do
    local rx, rz = coordOf(entry)
    if rx then
      local dx, dz = rx - x, rz - z
      if sqrt(dx * dx + dz * dz) <= minDistance then
        return true
      end
    end
  end
  return false
end

-- Fresh per-team statistics table; callers get their own copy.
function M.newStats()
  return {
    housesBuilt = 0,
    roadsBuilt = 0,
    gathersAssigned = 0,
    unitsRecruited = 0,
    attacksOrdered = 0,
  }
end

-- Every def name the AI classifies as military, sorted for determinism.
function M.militaryDefs()
  local names = {}
  for i, name in ipairs(MILITARY_DEFS) do names[i] = name end
  return names
end

-- True when the unit is one the AI tracks as a field army member.
function M.isMilitaryName(name)
  return M.MILITARY_SET[name] == true
end

-- Key count for a set table; 0 for nil or non-tables.
function M.countKeys(t)
  if type(t) ~= "table" then return 0 end
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

-- Non-negative integral count (the numeric contract for pop/cap/army sizes).
function M.validCount(n)
  return isNum(n) and n >= 0 and n == floor(n)
end

-- Does the cadence gate fire on this frame? 0 is a valid (if unlikely) hit.
function M.cadenceHit(frame)
  if type(frame) ~= "number" then return false end
  return frame % M.CADENCE_FRAMES == 0
end

-- Can this stock table pay every entry of `costTable`?
-- An empty cost table is always affordable; a missing resource counts as 0.
function M.canAfford(stock, costTable)
  if type(costTable) ~= "table" then return false end
  local have = stockOf(stock)
  for resource, amount in pairs(costTable) do
    if isNum(amount) then
      local owned = have[resource]
      if not isNum(owned) or owned < amount then
        return false
      end
    end
  end
  return true
end

-- Legacy name for the same resource check, kept for existing callers.
function M.canAffordCosts(stock, costs)
  if type(stock) ~= "table" or type(costs) ~= "table" then return false end
  return M.canAfford(stock, costs)
end

-- House: the settlement is at (or within the buffer of) its cap and can pay.
function M.shouldBuildHouse(pop, cap, stock)
  if not M.validCount(pop) or not M.validCount(cap) then return false end
  if (cap - pop) > M.HOUSE_POP_BUFFER then return false end
  return M.canAfford(stock, M.HOUSE_COST)
end

-- Road: still under the road budget and able to pay for one more segment.
function M.shouldBuildRoad(stock, roadCount, maxRoads)
  maxRoads = maxRoads or M.DEFAULT_MAX_ROADS
  roadCount = roadCount or 0
  if not isNum(roadCount) or not isNum(maxRoads) then return false end
  if roadCount >= maxRoads then return false end
  return M.canAfford(stock, M.ROAD_COST)
end

-- Recruitment: room under the pop cap, room under the army cap, and affordable.
function M.shouldRecruit(stock, pop, cap, armyCount, maxArmy)
  maxArmy = maxArmy or M.DEFAULT_MAX_ARMY
  armyCount = armyCount or 0
  if not isNum(pop) or not isNum(cap) then return false end
  if pop >= cap then return false end
  if not isNum(armyCount) or not isNum(maxArmy) then return false end
  if armyCount >= maxArmy then return false end
  return M.canAfford(stock, M.INFANTRY_COST)
end

-- Attack: the field army has reached the minimum striking size.
function M.shouldAttack(armyCount)
  if not isNum(armyCount) then return false end
  return armyCount >= M.ATTACK_ARMY_MIN
end

-- Road placement: the midpoint of the first consecutive endpoint pair that is
-- not already served by a road within `minDistance`. nil when every pair is
-- linked, or when fewer than two usable endpoints were supplied.
function M.selectCandidateRoadPos(endpoints, existingRoads, minDistance)
  if type(endpoints) ~= "table" then return nil end
  if not isNum(minDistance) then minDistance = M.ROAD_MIN_DISTANCE end
  local count = #endpoints
  if count < 2 then return nil end
  for i = 1, count - 1 do
    local ax, az = coordOf(endpoints[i])
    local bx, bz = coordOf(endpoints[i + 1])
    if ax and bx then
      local mx, mz = (ax + bx) / 2, (az + bz) / 2
      if not hasRoadNear(existingRoads, mx, mz, minDistance) then
        return { x = mx, z = mz }
      end
    end
  end
  return nil
end

-- Gathering: the resource furthest below its target proportion wins.
function M.prioritizeGatherResource(stock)
  local have = stockOf(stock)
  local best, bestRatio
  for _, resource in ipairs(M.GATHER_ORDER) do
    local target = M.GATHER_TARGETS[resource]
    local owned = have[resource]
    if not isNum(owned) then owned = 0 end
    local ratio = owned / target
    if bestRatio == nil or ratio < bestRatio then
      best, bestRatio = resource, ratio
    end
  end
  return best
end

-- Reactive recruit helpers ---------------------------------------------------

-- Sum opponent unit counts per tactical role. `counts` is a def-name -> count
-- map; non-military names, non-numeric and negative values are ignored. A
-- non-table (or empty) `counts` yields an empty table (conservative).
function M.countRoles(counts)
  local out = {}
  if type(counts) ~= "table" then return out end
  for name, amount in pairs(counts) do
    if M.isMilitaryName(name) then
      local role = M.ROLE_OF[name]
      if role then
        local n = tonumber(amount)
        if n == nil or n < 0 then n = 0 end
        out[role] = (out[role] or 0) + n
      end
    end
  end
  return out
end

-- Each role's share of the opponent field army, in ROLE_ORDER. Empty/malformed
-- input returns an empty table (conservative).
function M.computeRatios(counts)
  local totals = M.countRoles(counts)
  local grand = 0
  for _, role in ipairs(M.ROLE_ORDER) do
    grand = grand + (totals[role] or 0)
  end
  local ratios = {}
  if grand > 0 then
    for _, role in ipairs(M.ROLE_ORDER) do
      ratios[role] = (totals[role] or 0) / grand
    end
  end
  return ratios
end

-- The opponent's majority role, ties broken by ROLE_ORDER. nil for empty or
-- malformed input (conservative).
function M.majorityRole(counts)
  local totals = M.countRoles(counts)
  local best, bestTotal
  for _, role in ipairs(M.ROLE_ORDER) do
    local total = totals[role] or 0
    if total > 0 and (bestTotal == nil or total > bestTotal) then
      best, bestTotal = role, total
    end
  end
  return best
end

-- The recruit def that counters the opponent's majority unit type; nil when
-- the opponent has no tracked military (conservative).
function M.counterRecruit(counts)
  local role = M.majorityRole(counts)
  if not role then return nil end
  return M.COUNTER_RECRUIT[role]
end

-- Villager dispatch: busy villagers do nothing; idle ones close the housing
-- gap first, then extend the road network, then gather the scarcest resource.
-- `currentJob` may carry the roads already placed for this villager (as a
-- position table); a plain job string is ignored as "no roads placed yet".
function M.decideVillagerAction(villagerID, isIdle, currentJob, pop, cap, stock, endpoints, roadCount)
  if not isIdle then return { type = "none" } end

  if M.shouldBuildHouse(pop, cap, stock) then
    return { type = "build_house" }
  end

  if M.shouldBuildRoad(stock, roadCount) then
    local existing = (type(currentJob) == "table") and currentJob or nil
    local pos = M.selectCandidateRoadPos(endpoints, existing, M.ROAD_MIN_DISTANCE)
    if pos then
      return { type = "build_road", x = pos.x, z = pos.z }
    end
  end

  local resource = M.prioritizeGatherResource(stock)
  if resource then
    return { type = "gather", resource = resource }
  end

  return { type = "none" }
end

-- Deterministic spiral of house plots around the town center so successive
-- houses never stack on one spot. index is 0-based (pass housesBuilt).
function M.houseSpot(tcX, tcZ, index)
  if not isNum(tcX) or not isNum(tcZ) then return nil end
  local i = M.validCount(index) and index or 0
  local ring = floor(i / 4)
  local side = i % 4
  local d = M.HOUSE_OFFSET + ring * M.HOUSE_OFFSET
  if side == 0 then return tcX + d, tcZ + d end
  if side == 1 then return tcX - d, tcZ + d end
  if side == 2 then return tcX - d, tcZ - d end
  return tcX + d, tcZ - d
end

-- Road stub endpoint, offset east of the town center.
function M.roadSpot(tcX, tcZ)
  if not isNum(tcX) or not isNum(tcZ) then return nil end
  return tcX + M.ROAD_OFFSET, tcZ
end

-- Barracks spawn point for a trained unit, clear of the barracks footprint.
function M.recruitSpot(bx, bz)
  if not isNum(bx) or not isNum(bz) then return nil end
  return bx + 32, bz + 32
end

-- Clamp a possibly-nil/partial stats table into a full stats record.
function M.normalizeStats(s)
  local out = M.newStats()
  if type(s) ~= "table" then return out end
  for key in pairs(out) do
    local value = s[key]
    if M.validCount(value) then out[key] = value end
  end
  return out
end

return M
