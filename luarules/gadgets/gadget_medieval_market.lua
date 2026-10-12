-- Synced medieval market: barter exchange over the existing four-resource pool,
-- plus cart-driven trade routes that mint a deterministic surplus bonus.
--
-- All rate/quote/transition math lives in scripts/medieval_market.lua; this
-- gadget owns the modoption gate, market-unit tracking, the GG API surface and
-- every Spring.* call.
--
-- Registration contract: this gadget is ALWAYS registered (enabled = true) so
-- GG.MedievalMarket exists in every match, but it is INERT unless modoption
-- `medievalmarket` is on -- no market tracking, no route bonus, no stockpile
-- mutation, and Exchange/ValidateTrade answer { ok = false, reason =
-- "market-disabled" }. That keeps the shared Phase 2/3/4 probe runs untouched.
--
-- Reuse contract: stockpiles are read and written ONLY through the public
-- GG.MedievalEconomy API (GetStockpiles / Transact / Deposit), and cart movement
-- is never reimplemented -- routes observe the existing hauler through
-- GG.MedievalLogistics (HaulSummary / HaulRoute / HaulHubStock), which is where
-- gadget_medieval_hauling publishes them.

function gadget:GetInfo()
  return {
    name = "Medieval Market",
    desc = "Elastic four-resource barter exchange with cart trade routes",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 6,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local market = VFS.Include("scripts/medieval_market.lua")

-- Modoption gate: "1"/1/true all read as enabled, matching the other Phase 5
-- probe gadgets' tolerance for the three shapes Spring returns.
local mo = Spring.GetModOptions() or {}
local ENABLED = (mo.medievalmarket == "1") or (mo.medievalmarket == 1) or (mo.medievalmarket == true)

local MARKET_DEF = "medieval_market"
local CADENCE_FRAMES = 30 -- one route/bonus pass per ~1s

-- Synced state:
--   markets[teamID][unitID]      = { x =, y =, z = }
--   routes[teamID]               = { { from =, to =, index =, surplus = }, ... }
--   stats[teamID]                = { routes =, bonuses =, delivered =, lastDelivered = }
local markets = {}
local routes = {}
local stats = {}

-- Forward declaration: trackMarket (below) rebuilds the route table whenever the
-- market set changes; the definition follows the marketList helper it needs.
local rebuildRoutes

local function initTeam(teamID)
  markets[teamID] = markets[teamID] or {}
  routes[teamID] = routes[teamID] or {}
  stats[teamID] = stats[teamID] or { routes = 0, bonuses = 0, delivered = 0, lastDelivered = 0 }
end

local function echo(fmt, ...)
  if Spring and Spring.Echo then
    Spring.Echo(string.format(fmt, ...))
  end
end

local function unitPos(unitID)
  if not (Spring and Spring.GetUnitPosition) then return nil end
  local x, y, z = Spring.GetUnitPosition(unitID)
  if not x or not z then return nil end
  return { x = x, y = y, z = z }
end

local function isMarketDef(unitDefID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def or def.name ~= MARKET_DEF then return false end
  return true
end

-- ---------------------------------------------------------------------------
-- Economy access (public API only)
-- ---------------------------------------------------------------------------

local function economy()
  local api = GG and GG.MedievalEconomy
  if not api or type(api.GetStockpiles) ~= "function" then return nil end
  return api
end

-- State projection the pure module consumes: { stockpiles = <live team table> }.
-- The live table is only ever read here; the transition copies before mutating.
local function teamState(teamID)
  local econ = economy()
  if not econ then return nil end
  local stock = econ.GetStockpiles(teamID)
  if type(stock) ~= "table" then return nil end
  return { stockpiles = stock }
end

-- Relative GLOBAL stockpiles: the sum of every live team's pool. Used by GetRate
-- when no team is named, so a rate can be quoted without a team context.
local function globalStockpiles()
  local econ = economy()
  local out = {}
  for _, r in ipairs(market.RESOURCES) do out[r] = 0 end
  if not econ then return out end
  local teams = (Spring and Spring.GetTeamList and Spring.GetTeamList()) or {}
  for _, teamID in ipairs(teams) do
    local stock = econ.GetStockpiles(teamID)
    if type(stock) == "table" then
      for _, r in ipairs(market.RESOURCES) do
        local v = stock[r]
        if type(v) == "number" and v == v then out[r] = out[r] + v end
      end
    end
  end
  return out
end

local function stockFor(teamID)
  if teamID == nil then return globalStockpiles() end
  local state = teamState(teamID)
  if not state then return globalStockpiles() end
  return state.stockpiles
end

-- ---------------------------------------------------------------------------
-- Market-unit tracking
-- ---------------------------------------------------------------------------

local function trackMarket(unitID, unitDefID, teamID)
  if not ENABLED then return end
  if teamID == nil or not isMarketDef(unitDefID) then return end
  local pos = unitPos(unitID)
  if not pos then return end
  initTeam(teamID)
  markets[teamID][unitID] = pos
  echo("PHASE5 MARKET tracked unit=%d team=%d x=%d z=%d", unitID, teamID, pos.x, pos.z)
  rebuildRoutes(teamID)
end
-- ---------------------------------------------------------------------------
-- Trade routes
-- ---------------------------------------------------------------------------
-- A route pairs two markets of one team, nearest-first, using the pure
-- selectRouteDestination policy. Cart movement stays entirely with
-- gadget_medieval_hauling (the market is registered as a haul hub in
-- scripts/medieval_haul.lua HUB_PROFILES); this gadget only OBSERVES deliveries
-- through GG.MedievalLogistics and mints the surplus bonus.

local function marketList(teamID)
  initTeam(teamID)
  local list = {}
  for unitID, pos in pairs(markets[teamID]) do
    list[#list + 1] = { id = unitID, x = pos.x, y = pos.y, z = pos.z }
  end
  table.sort(list, function(a, b) return a.id < b.id end)
  return list
end

rebuildRoutes = function(teamID)
  initTeam(teamID)
  local list = marketList(teamID)
  local out = {}
  local index = 0
  for i = 1, #list do
    local dest = market.selectRouteDestination(list, i)
    if dest then
      index = index + 1
      local resource = market.surplusFor(index)
      out[#out + 1] = {
        from = list[i].id,
        to = dest.id,
        index = index,
        distance = dest.distance,
        value = dest.value,
        surplus = resource,
      }
    end
  end
  routes[teamID] = out
  stats[teamID].routes = #out
  return out
end

-- The hauler's public delivery counter. GG.MedievalLogistics is where
-- gadget_medieval_hauling posts HaulSummary; GG.MedievalHauling is accepted as a
-- fallback name so the market works whichever table the hauler published to.
local function haulSummary(teamID)
  local api = GG and GG.MedievalLogistics
  if not (api and type(api.HaulSummary) == "function") then
    api = GG and GG.MedievalHauling
  end
  if not (api and type(api.HaulSummary) == "function") then return nil end
  local ok, summary = pcall(api.HaulSummary, teamID)
  if not ok or type(summary) ~= "table" then return nil end
  return summary
end

-- Road/supply context from the logistics public API: a market route is only
-- worth a bonus when the hauler can actually reach it (same public reader the
-- hauler itself uses for its road-speed mutator). Absent API reads as connected,
-- so the market degrades to "no logistics gadget" rather than to "no bonus".
local function routeConnected(teamID, unitID)
  local api = GG and GG.MedievalLogistics
  if not (api and type(api.IsOnRoad) == "function") then return true end
  local ok, onRoad = pcall(api.IsOnRoad, teamID, unitID)
  if not ok then return true end
  return onRoad and true or false
end

-- Nearest route for a team, used to gate the surplus on a reachable market.
local function firstConnectedRoute(teamID)
  local list = routes[teamID]
  if type(list) ~= "table" then return nil end
  for _, route in ipairs(list) do
    if routeConnected(teamID, route.from) or routeConnected(teamID, route.to) then
      return route
    end
  end
  return nil
end

local function awardBonuses(teamID)
  initTeam(teamID)
  local summary = haulSummary(teamID)
  if not summary then return end
  local delivered = tonumber(summary.delivered) or 0
  local s = stats[teamID]
  if delivered <= s.lastDelivered then
    s.lastDelivered = delivered
    return
  end

  local econ = economy()
  local connected = firstConnectedRoute(teamID)
  local list = routes[teamID]
  for _ = s.lastDelivered + 1, delivered do
    local route = connected or (list and list[(s.bonuses % math.max(#list, 1)) + 1])
    local resource = route and route.surplus
    if resource and econ and type(econ.Deposit) == "function" then
      econ.Deposit(teamID, resource, market.TRADE_SURPLUS[resource] or 0)
    end
    s.bonuses = s.bonuses + 1
    if resource then
      echo("PHASE5 MARKET route-bonus team=%d resource=%s amount=%d",
        teamID, resource, market.TRADE_SURPLUS[resource] or 0)
    end
  end
  s.delivered = delivered
  s.lastDelivered = delivered
end

-- ---------------------------------------------------------------------------
-- GG API (additive: never reassigns GG.MedievalMarket wholesale)
-- ---------------------------------------------------------------------------

local function GetRate(fromResource, toResource, teamID)
  return market.rate(fromResource, toResource, stockFor(teamID))
end

local function ValidateTrade(teamID, fromResource, toResource, amountWanted)
  if not ENABLED then return { ok = false, reason = "market-disabled" } end
  local state = teamState(teamID)
  if not state then return { ok = false, reason = "invalid-state" } end
  return market.validateTrade(state, fromResource, toResource, amountWanted)
end

-- Exchange(teamID, from, to, amount) -> { ok, reason, cost, amount }
-- Commits atomically: the pure transition decides, the debit goes through
-- GG.MedievalEconomy.Transact FIRST, and only a successful debit earns the
-- deposit. A failed debit leaves the pool untouched.
local function Exchange(teamID, fromResource, toResource, amountWanted)
  if not ENABLED then return { ok = false, reason = "market-disabled" } end
  local econ = economy()
  if not econ then return { ok = false, reason = "no-economy" } end
  local state = teamState(teamID)
  if not state then return { ok = false, reason = "invalid-state" } end

  local order = market.marketOrder(teamID, fromResource, toResource, amountWanted)
  local result = market.applyTrade(state, order)
  if not result.ok then return result end

  local costs = {}
  costs[result.from] = result.cost
  if type(econ.Transact) ~= "function" or not econ.Transact(teamID, costs) then
    return { ok = false, reason = "transact-failed", cost = result.cost }
  end
  if type(econ.Deposit) == "function" then
    econ.Deposit(teamID, result.to, result.amount)
  end

  return {
    ok = true,
    reason = "ok",
    cost = result.cost,
    amount = result.amount,
    from = result.from,
    to = result.to,
    teamID = teamID,
  }
end

local function MarketCount(teamID)
  initTeam(teamID)
  local n = 0
  for _ in pairs(markets[teamID]) do n = n + 1 end
  return n
end

local function GetRoutes(teamID)
  initTeam(teamID)
  return routes[teamID]
end

local function RouteBonusTotal(teamID)
  initTeam(teamID)
  return stats[teamID].bonuses
end

local function IsEnabled()
  return ENABLED
end

local function ensureApi()
  GG = GG or {}
  GG.MedievalMarket = GG.MedievalMarket or {}
  GG.MedievalMarket.GetRate = GetRate
  GG.MedievalMarket.Exchange = Exchange
  GG.MedievalMarket.ValidateTrade = ValidateTrade
  GG.MedievalMarket.MarketCount = MarketCount
  GG.MedievalMarket.GetRoutes = GetRoutes
  GG.MedievalMarket.RebuildRoutes = rebuildRoutes
  GG.MedievalMarket.RouteBonusTotal = RouteBonusTotal
  GG.MedievalMarket.IsEnabled = IsEnabled
  GG.MedievalMarket.MARKET_DEF = MARKET_DEF
end

-- Register at load time, not just on Initialize: GG.MedievalMarket must exist
-- (and answer "disabled") even when the modoption is off or a consumer asks
-- before the first Initialize.
ensureApi()

-- ---------------------------------------------------------------------------
-- Gadget callbacks
-- ---------------------------------------------------------------------------

function gadget:Initialize()
  ensureApi()
  if not ENABLED then return end
  local units = (Spring.GetAllUnits and Spring.GetAllUnits()) or {}
  for i = 1, #units do
    local unitID = units[i]
    local defID = Spring.GetUnitDefID(unitID)
    if defID and isMarketDef(defID) then
      trackMarket(unitID, defID, Spring.GetUnitTeam(unitID))
    end
  end
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  ensureApi()
  trackMarket(unitID, unitDefID, teamID)
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  if teamID == nil then return end
  initTeam(teamID)
  if markets[teamID][unitID] then
    markets[teamID][unitID] = nil
    rebuildRoutes(teamID)
  end
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  if oldTeam == nil then return end
  initTeam(oldTeam)
  if markets[oldTeam][unitID] then
    markets[oldTeam][unitID] = nil
    rebuildRoutes(oldTeam)
  end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == nil and Spring and Spring.GetUnitTeam then newTeam = Spring.GetUnitTeam(unitID) end
  trackMarket(unitID, unitDefID, newTeam)
end

function gadget:TeamDied(teamID)
  markets[teamID] = nil
  routes[teamID] = nil
  stats[teamID] = nil
end

function gadget:GameFrame(frame)
  ensureApi()
  if not ENABLED then return end
  if frame % CADENCE_FRAMES ~= 0 then return end
  local teams = (Spring.GetTeamList and Spring.GetTeamList()) or {}
  for _, teamID in ipairs(teams) do
    initTeam(teamID)
    rebuildRoutes(teamID)
    awardBonuses(teamID)
  end
end
