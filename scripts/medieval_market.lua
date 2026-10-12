-- Shared, pure medieval market / barter policy; no engine calls in this module.
-- The synced market gadget (luarules/gadgets/gadget_medieval_market.lua) owns
-- team enablement, market-unit tracking, the GG API surface and every Spring.*
-- call, and delegates every rate, quote and state transition here so the policy
-- is unit-testable in isolation.
--
-- Loadability contract: this file must stay loadable by a bare Lua 5.1/LuaJIT
-- interpreter with no VFS/Spring present, so it never VFS.Include()s a sibling
-- module. The small amount of shared data it needs (the four-resource pool and
-- MAX_STOCKPILE) is inlined and mirrors scripts/medieval_economy.lua.
--
-- Barter runs on the EXISTING four-resource pool. There is deliberately no
-- "gold" resource: introducing one would force a migration of Phase 2's discrete
-- economy core for no gameplay gain (see docs/phase-5.md, Slice 3).
--
-- Totality: every function answers the conservative verdict (0 / false / nil /
-- a reason string) for malformed input instead of raising, so the synced gadget
-- can call it with partially-populated state without a pcall guard.
local M = {
  RESOURCES = { "food", "wood", "stone", "iron" },
  FOOD = "food", WOOD = "wood", STONE = "stone", IRON = "iron",

  -- Relative worth of one unit of each resource. Stone and iron are scarcer
  -- than food and wood, so they cost more of the other side of a barter.
  BASE_RATES = { food = 1.0, wood = 1.0, stone = 1.5, iron = 2.0 },

  -- Supply/demand elasticity: a resource the team is short of gets dearer.
  ELASTICITY = 0.5,

  -- Stockpile delta that counts as "one unit" of scarcity signal. Sized so the
  -- default team reserves (food/wood 200, stone 100, iron 50) give a modest,
  -- readable swing rather than saturating the clamp immediately.
  STOCK_SCALE = 400,

  -- Clamp on the elasticity multiplier. Keeps a rate strictly positive (a free
  -- trade would be an exploit) and bounded (a saturated market cannot price the
  -- other side out entirely).
  MIN_RATE_FACTOR = 0.25,
  MAX_RATE_FACTOR = 4.0,

  -- Market spread charged on top of the mid rate; the house always eats a cut.
  TRADE_MARGIN = 0.1,

  -- Cart-route completion bonus, minted round-robin per route.
  TRADE_SURPLUS = { food = 3, wood = 3, stone = 2, iron = 1 },

  -- Two markets further apart than this cannot form a trade route.
  ROUTE_RADIUS = 400,

  -- Mirrors scripts/medieval_economy.lua MAX_STOCKPILE.
  MAX_STOCKPILE = 100000,

  -- Canonical field order of a marketOrder struct.
  ORDER_FIELDS = { "teamID", "from", "to", "amount" },
}

local floor = math.floor
local ceil = math.ceil
local min = math.min
local max = math.max
local sqrt = math.sqrt
local huge = math.huge

-- ---------------------------------------------------------------------------
-- Small shared helpers (inlined; see the loadability contract above)
-- ---------------------------------------------------------------------------

local function finite(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

function M.finite(n)
  return finite(n)
end

function M.validResource(r)
  return type(r) == "string"
    and (r == "food" or r == "wood" or r == "stone" or r == "iron")
end

-- Positive integer. Zero and fractions are rejected: a barter of nothing is a
-- no-op the gadget should never commit, and fractional resources cannot exist
-- in the discrete pool.
function M.validAmount(n)
  return finite(n) and n >= 1 and n == floor(n)
end

-- Non-negative stock reading for a resource key. Missing/NaN/Inf read as 0 so a
-- partially-populated stockpile table is still quotable.
function M.stockValue(stock, resource)
  if type(stock) ~= "table" then return 0 end
  local v = stock[resource]
  if not finite(v) or v < 0 then return 0 end
  return floor(v)
end

-- A state is either { stockpiles = { food=, ... } } (the gadget's projection) or
-- a raw stock table. Anything else has no stockpile to trade against.
local function resolveStock(state)
  if type(state) ~= "table" then return nil end
  local s = state.stockpiles
  if s == nil then s = state.stock end
  if type(s) == "table" then return s end
  if state.food ~= nil or state.wood ~= nil or state.stone ~= nil or state.iron ~= nil then
    return state
  end
  return nil
end

function M.resolveStock(state)
  return resolveStock(state)
end

-- ---------------------------------------------------------------------------
-- Elastic exchange rate
-- ---------------------------------------------------------------------------

-- Elasticity multiplier on the mid rate, exactly as specified in
-- docs/phase-5.md: 1 + ELASTICITY * (stock[from] - stock[to]) / STOCK_SCALE.
-- A resource the buyer is short of (stock[to] low) is therefore dearer: the
-- price of the GOOD BEING BOUGHT rises with its scarcity. Balanced stocks give
-- exactly 1.0, so the base rates show through unchanged.
local function rateFactor(fromRes, toRes, stock)
  local from = M.stockValue(stock, fromRes)
  local to = M.stockValue(stock, toRes)
  local raw = 1.0 + M.ELASTICITY * (from - to) / M.STOCK_SCALE
  return max(M.MIN_RATE_FACTOR, min(M.MAX_RATE_FACTOR, raw))
end

-- rate(fromResource, toResource, stock) -> number
-- How many units of `fromResource` one unit of `toResource` is worth. `stock` is
-- the optional global stockpile projection; omitted/partial stock reads as
-- balanced, which yields the pure base ratio.
function M.rate(fromResource, toResource, stock)
  if not M.validResource(fromResource) or not M.validResource(toResource) then
    return 0
  end
  if fromResource == toResource then return 1.0 end
  local base = M.BASE_RATES[toResource] / M.BASE_RATES[fromResource]
  return base * rateFactor(fromResource, toResource, stock)
end

-- State-projection form of rate, matching the docs' `exchangeRate(state, from, to)`.
function M.exchangeRate(state, fromResource, toResource)
  return M.rate(fromResource, toResource, resolveStock(state))
end

-- All four rates out of `fromResource`, in canonical resource order. Stable key
-- order keeps HUD/debug output diffable.
function M.ratesFrom(fromResource, stock)
  local out = {}
  for _, r in ipairs(M.RESOURCES) do
    out[r] = M.rate(fromResource, r, stock)
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Quotes
-- ---------------------------------------------------------------------------

local INVALID_QUOTE = { cost = 0, affordable = false }

-- exchangeCost(fromStock, fromRes, toRes, amountWanted)
--   -> { cost = integer, affordable = boolean, rate = number, reason = string }
-- Cost is the mid rate plus TRADE_MARGIN, rounded UP to whole resources: the
-- house never rounds in the trader's favour, so a quote can never be cheaper
-- than the underlying mid rate.
function M.exchangeCost(fromStock, fromRes, toRes, amountWanted)
  if not M.validResource(fromRes) or not M.validResource(toRes) then
    return { cost = 0, affordable = false, rate = 0, reason = "invalid-resource" }
  end
  if fromRes == toRes then
    return { cost = 0, affordable = false, rate = 1.0, reason = "same-resource" }
  end
  if not M.validAmount(amountWanted) then
    return { cost = 0, affordable = false, rate = 0, reason = "invalid-amount" }
  end

  local r = M.rate(fromRes, toRes, fromStock)
  local cost = ceil(amountWanted * r * (1.0 + M.TRADE_MARGIN))
  local have = M.stockValue(fromStock, fromRes)
  return {
    cost = cost,
    affordable = cost > 0 and have >= cost,
    rate = r,
    have = have,
    reason = (cost > 0 and have >= cost) and "ok" or "insufficient-stock",
  }
end

-- Docs-compatible alias: tradeQuote(state, from, to, amount) -> { cost, ok }.
function M.tradeQuote(state, fromResource, toResource, amountWanted)
  local q = M.exchangeCost(resolveStock(state), fromResource, toResource, amountWanted)
  return { cost = q.cost, ok = q.affordable, rate = q.rate, reason = q.reason }
end

-- ---------------------------------------------------------------------------
-- Validation
-- ---------------------------------------------------------------------------

-- validateTrade(state, fromRes, toRes, amountWanted) -> { ok = bool, reason = string }
-- Reasons, in the order they are tested:
--   invalid-state / invalid-resource / same-resource / invalid-amount /
--   stockpile-full / insufficient-stock / ok
function M.validateTrade(state, fromResource, toResource, amountWanted)
  local stock = resolveStock(state)
  if not stock then
    return { ok = false, reason = "invalid-state" }
  end
  if not M.validResource(fromResource) or not M.validResource(toResource) then
    return { ok = false, reason = "invalid-resource" }
  end
  if fromResource == toResource then
    return { ok = false, reason = "same-resource" }
  end
  if not M.validAmount(amountWanted) then
    return { ok = false, reason = "invalid-amount" }
  end

  local q = M.exchangeCost(stock, fromResource, toResource, amountWanted)
  if q.cost < 1 then
    return { ok = false, reason = "insufficient-stock" }
  end
  -- Refuse a trade that would overflow the destination: the gain would be
  -- silently swallowed by the MAX_STOCKPILE clamp, i.e. the trader pays for
  -- goods they never receive.
  local gained = M.stockValue(stock, toResource)
  if gained + amountWanted > M.MAX_STOCKPILE then
    return { ok = false, reason = "stockpile-full" }
  end
  if not q.affordable then
    return { ok = false, reason = "insufficient-stock" }
  end
  return { ok = true, reason = "ok", cost = q.cost, rate = q.rate, amount = amountWanted }
end

-- Boolean convenience wrapper.
function M.canTrade(state, fromResource, toResource, amountWanted)
  return M.validateTrade(state, fromResource, toResource, amountWanted).ok
end

-- ---------------------------------------------------------------------------
-- marketOrder struct + pure transition
-- ---------------------------------------------------------------------------

-- marketOrder(teamID, fromRes, toRes, amountWanted) -> order struct
-- The single shape applyTrade accepts: { teamID, from, to, amount }.
function M.marketOrder(teamID, fromResource, toResource, amountWanted)
  return {
    teamID = teamID,
    from = fromResource,
    to = toResource,
    amount = amountWanted,
  }
end

function M.isMarketOrder(order)
  if type(order) ~= "table" then return false end
  if type(order.from) ~= "string" or type(order.to) ~= "string" then return false end
  if not finite(order.amount) then return false end
  return true
end

-- Shallow copy of a state plus a DEEP copy of its stockpiles, so a transition
-- can never alias (and therefore never mutate) the caller's tables.
function M.copyState(state)
  local out = {}
  if type(state) == "table" then
    for k, v in pairs(state) do out[k] = v end
  end
  local stock = resolveStock(state)
  local copy = {}
  for _, r in ipairs(M.RESOURCES) do
    copy[r] = M.stockValue(stock, r)
  end
  out.stockpiles = copy
  return out
end

-- applyTrade(state, order) -> newState
-- Pure: returns a NEW state table. The input state, its stockpiles table and any
-- shared global are left untouched; the caller (the synced gadget) commits the
-- result through GG.MedievalEconomy.Transact/Deposit. An invalid order yields a
-- copied state with ok = false and the validation reason, never a partial debit.
function M.applyTrade(state, order)
  local out = M.copyState(state)
  if not M.isMarketOrder(order) then
    out.ok = false
    out.reason = "invalid-order"
    return out
  end

  local check = M.validateTrade(state, order.from, order.to, order.amount)
  out.ok = check.ok
  out.reason = check.reason
  if not check.ok then return out end

  out.stockpiles[order.from] = out.stockpiles[order.from] - check.cost
  out.stockpiles[order.to] = min(out.stockpiles[order.to] + order.amount, M.MAX_STOCKPILE)
  out.cost = check.cost
  out.amount = order.amount
  out.from = order.from
  out.to = order.to
  out.teamID = order.teamID
  return out
end

-- ---------------------------------------------------------------------------
-- Cart trade routes
-- ---------------------------------------------------------------------------

function M.distance(a, b)
  if type(a) ~= "table" or type(b) ~= "table" then return nil end
  if not finite(a.x) or not finite(a.z) or not finite(b.x) or not finite(b.z) then return nil end
  local dx, dz = a.x - b.x, a.z - b.z
  return sqrt(dx * dx + dz * dz)
end

-- routeValue(state, fromPos, toPos) -> proportion of TRADE_MARGIN earned.
-- Scales linearly with distance and saturates at ROUTE_RADIUS, so a long haul
-- pays more than a short one but never more than the full margin.
function M.routeValue(state, fromPos, toPos)
  local d = M.distance(fromPos, toPos)
  if d == nil then return 0 end
  local margin = M.TRADE_MARGIN
  if type(state) == "table" and finite(state.margin) and state.margin >= 0 then
    margin = state.margin
  end
  return margin * (min(d, M.ROUTE_RADIUS) / M.ROUTE_RADIUS)
end

-- selectRouteDestination(marketPositions, fromIndex) -> { id, index, distance, value } | nil
-- marketPositions is an array of { id =, x =, z = } (extra fields ignored).
-- fromIndex picks the origin market (default 1). The nearest OTHER market within
-- ROUTE_RADIUS wins; ties break on the lower id so the pick is stable across
-- table iteration order.
function M.selectRouteDestination(marketPositions, fromIndex)
  if type(marketPositions) ~= "table" then return nil end
  if fromIndex == nil then fromIndex = 1 end
  if not finite(fromIndex) or fromIndex < 1 then return nil end

  local origin = marketPositions[fromIndex]
  if type(origin) ~= "table" then return nil end

  local best
  for index, candidate in pairs(marketPositions) do
    if index ~= fromIndex and type(candidate) == "table" and candidate.id ~= nil then
      local d = M.distance(origin, candidate)
      if d ~= nil and d <= M.ROUTE_RADIUS then
        local better = best == nil
          or d < best.distance
          or (d == best.distance and candidate.id < best.id)
        if better then
          best = {
            id = candidate.id,
            index = index,
            distance = d,
            value = M.routeValue(nil, origin, candidate),
          }
        end
      end
    end
  end
  return best
end

-- surplusFor(index) -> resource, amount
-- Deterministic round-robin over RESOURCES, so route N always pays the same
-- resource for the same route count.
function M.surplusFor(index)
  if not finite(index) or index < 1 then return nil, nil end
  local i = ((floor(index) - 1) % #M.RESOURCES) + 1
  local resource = M.RESOURCES[i]
  return resource, M.TRADE_SURPLUS[resource]
end

return M
