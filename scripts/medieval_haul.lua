-- Shared, pure medieval hauler policy; no engine calls in this module.
-- The hauler moves a resource between two "storage hubs" of the same team. In
-- this total conversion the resource stockpile is per-TEAM (gadget_medieval_economy
-- keeps one { food, wood, stone, iron } table per team), so "surplus" and
-- "deficit" are role projections over that single pool: a source hub is the kind
-- of building that stores a resource (dropoff), a sink hub is the kind that
-- consumes it (blacksmith/fletcher crafting). This module only answers the
-- policy question -- which route to drive next -- and leaves all mutation to the
-- synced gadget.
local M = {
  CART_UNIT_NAME = "medieval_cart",

  -- Carry-capacity fallback: mirrors units/medieval_cart.lua customparams.carry_capacity.
  DEFAULT_CART_CAPACITY = 400,

  -- One haul moves at most this much, matching the deterministic completion log
  -- ("... amount=25"). The cart carry capacity can clamp it lower, never higher.
  HAUL_STEP = 25,

  -- A sink hub is "in deficit" for a resource when the team pool holds less than
  -- this many units. A haul keeps firing while the pool sits in the band
  -- [HAUL_STEP, DEFICIT_THRESHOLD): there is still some resource to reallocate
  -- toward the demanding hub but not enough to consider it stocked.
  DEFICIT_THRESHOLD = 80,

  -- Deterministic order used both for hub tie-breaking and for choosing which of
  -- several deficit resources hauls first. Only wood and iron have sink hubs
  -- (blacksmith/fletcher consume them); food and stone have sources but no sinks.
  HUB_NAMES = {
    "medieval_town_center",
    "medieval_granary",
    "medieval_lumber_camp",
    "medieval_blacksmith",
    "medieval_fletcher",
  },

  -- Resources are iterated in this fixed order when scanning for a deficit, so
  -- the chosen route is stable across Lua table iteration order.
  RESOURCE_ORDER = { "wood", "iron" },
}

-- Per-hub role profile.
--   supply[R]   = true when the hub is a source for resource R (it stores/accepts it)
--   specific[R] = true when the hub is the DEDICATED source for R (dropoff_resource),
--                 preferred over a generic storehouse when both exist
--   demand[R]   = true when the hub consumes R (a sink / deficit point)
M.HUB_PROFILES = {
  medieval_town_center = {
    supply = { food = true, wood = true, stone = true, iron = true },
    specific = {},
    demand = {},
  },
  medieval_granary = {
    supply = { food = true },
    specific = { food = true },
    demand = {},
  },
  medieval_lumber_camp = {
    supply = { wood = true },
    specific = { wood = true },
    demand = {},
  },
  medieval_blacksmith = {
    supply = {},
    specific = {},
    -- production chains: sword = { iron = 5, wood = 2 }
    demand = { iron = true, wood = true },
  },
  medieval_fletcher = {
    supply = {},
    specific = {},
    -- production chains: bow = { wood = 5, iron = 1 }
    demand = { wood = true, iron = true },
  },
}

local floor = math.floor
local huge = math.huge

local function finiteNum(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- Hold the per-frame snapshot the gadget pushes before calling chooseHaulRoute;
-- lets the two-argument form stay pure while the synced gadget supplies data.
local defaultContext = {
  hubs = {},
  stocks = {},
  capacity = M.DEFAULT_CART_CAPACITY,
}

function M.isHubName(defName)
  return type(defName) == "string" and M.HUB_PROFILES[defName] ~= nil
end

function M.hubProfile(defName)
  return M.HUB_PROFILES[defName]
end

function M.hubRank(defName)
  for i, name in ipairs(M.HUB_NAMES) do
    if name == defName then return i end
  end
  return #M.HUB_NAMES + 1
end

-- Clamp a carry capacity to a usable non-negative integer. Invalid/nil input
-- falls back to the cart default; a negative or zero capacity hauls nothing.
function M.clampCapacity(capacity)
  if not finiteNum(capacity) then return M.DEFAULT_CART_CAPACITY end
  if capacity < 0 then return 0 end
  return floor(capacity)
end

-- Whether a unit may haul at all: a valid team/unit plus the cart def name.
-- unitDefName == nil answers conservatively (false): a pure module cannot resolve
-- an engine unit id to a def, so callers must pass the name they already have.
function M.canHaul(teamID, unitID, unitDefName)
  if type(teamID) ~= "number" or teamID < 0 then return false end
  if type(unitID) ~= "number" then return false end
  -- Fail closed: the name must be the cart. A nil name cannot be resolved by a
  -- pure module, so it denies rather than assumes.
  if unitDefName ~= M.CART_UNIT_NAME then return false end
  return true
end

-- Register the per-frame snapshot: hubs keyed by hubID -> { name = defName, ... },
-- the team stock table, and the cart carry capacity. chooseHaulRoute reads this
-- unless the explicit arguments are supplied.
function M.setRouteContext(hubs, stocks, capacity)
  defaultContext.hubs = type(hubs) == "table" and hubs or {}
  defaultContext.stocks = type(stocks) == "table" and stocks or {}
  defaultContext.capacity = M.clampCapacity(capacity)
  return defaultContext
end

-- Normalise a hubs input (map keyed by hubID, or an array of { id=, name= })
-- into a deterministic array of { id = number, name = string }, sorted by
-- (profile rank, then id). Non-hub or malformed entries are dropped.
function M.collectHubs(hubs)
  local out = {}
  if type(hubs) ~= "table" then return out end
  for key, rec in pairs(hubs) do
    if type(rec) == "table" then
      local hubID, name
      if rec.name ~= nil and rec.id ~= nil then
        hubID, name = rec.id, rec.name -- array-style record
      else
        hubID, name = key, rec.name    -- map-style record keyed by hubID
      end
      if type(hubID) == "number" and M.isHubName(name) then
        out[#out + 1] = { id = hubID, name = name }
      end
    end
  end
  table.sort(out, function(a, b)
    local ra, rb = M.hubRank(a.name), M.hubRank(b.name)
    if ra ~= rb then return ra < rb end
    return a.id < b.id
  end)
  return out
end

local function firstDemandHub(list, resource)
  for _, h in ipairs(list) do
    local p = M.HUB_PROFILES[h.name]
    if p and p.demand and p.demand[resource] then
      return h.id
    end
  end
  return nil
end

-- Prefer the dedicated source (dropoff_resource == resource), then a generic
-- storehouse. Deterministic within each tier by hub rank/id.
local function firstSupplyHub(list, resource)
  for _, h in ipairs(list) do
    local p = M.HUB_PROFILES[h.name]
    if p and p.specific and p.specific[resource] then
      return h.id
    end
  end
  for _, h in ipairs(list) do
    local p = M.HUB_PROFILES[h.name]
    if p and p.supply and p.supply[resource] then
      return h.id
    end
  end
  return nil
end

-- Pick the next haul route, or nil when nothing needs hauling.
-- Returns { from = hubID, to = hubID, resource = kind, amount = n }.
-- amount is clamped to the cart carry capacity, HAUL_STEP, and the available
-- stock -- the smallest deterministic chunk wins.
function M.chooseHaulRoute(teamID, cartID, hubs, stocks, capacity)
  hubs = hubs or defaultContext.hubs
  stocks = stocks or defaultContext.stocks
  capacity = capacity or defaultContext.capacity

  capacity = M.clampCapacity(capacity)
  if capacity < 1 then return nil end

  local list = M.collectHubs(hubs)
  if #list == 0 then return nil end

  stocks = type(stocks) == "table" and stocks or {}

  for _, resource in ipairs(M.RESOURCE_ORDER) do
    local raw = stocks[resource]
    local stock = finiteNum(raw) and floor(raw) or 0
    -- Deficit (sink wants more) AND surplus (a positive chunk is available).
    if stock >= M.HAUL_STEP and stock < M.DEFICIT_THRESHOLD then
      local toID = firstDemandHub(list, resource)
      local fromID = firstSupplyHub(list, resource)
      if toID and fromID and toID ~= fromID then
        local amount = floor(math.min(capacity, M.HAUL_STEP, stock))
        if amount >= 1 then
          return { from = fromID, to = toID, resource = resource, amount = amount }
        end
      end
    end
  end

  return nil
end

return M