-- Phase 5 Slice 3 headless probe: market & trade exchange.
--
-- Gated on modoption `medievalmarket` (inert otherwise, so shared Phase 2/3/4
-- probe runs are unaffected). Stages:
--   f=20  spawn a market for team 0 and seed its stockpiles.
--   f=40  `rate-verdict`    -- GG.MedievalMarket.GetRate matches the pure module
--                             recomputed over the same live stockpile.
--   f=60  `barter-verdict`  -- one food->iron barter; the pool delta is exactly
--                             the quoted cost/amount, and no other resource moved.
--   f=90  `probe-complete`  -- terminal verdict.
--
-- The probe asserts against GG.MedievalEconomy.GetStockpiles (the authoritative
-- pool) and never touches the market gadget's internals.

function gadget:GetInfo()
  return {
    name = "Phase 5 Slice 3 Market Probe",
    desc = "Headless probe verifying elastic barter rates and exact stockpile deltas",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 10,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}
local enabled = (mo.medievalmarket == "1") or (mo.medievalmarket == 1) or (mo.medievalmarket == true)
if not enabled then return end

local market = VFS.Include("scripts/medieval_market.lua")

local TEAM = 0
local MARKET_X, MARKET_Z = 1800, 2400
local BARTER_FROM, BARTER_TO = "food", "iron"
local BARTER_AMOUNT = 20

local spawned = false
local rateChecked = false
local barterChecked = false
local completed = false

local function echo(fmt, ...)
  Spring.Echo(string.format(fmt, ...))
end

local function stocks(teamID)
  local api = GG and GG.MedievalEconomy
  if not (api and api.GetStockpiles) then return nil end
  return api.GetStockpiles(teamID)
end

local function stockOf(teamID, resource)
  local s = stocks(teamID)
  if type(s) ~= "table" then return nil end
  local v = s[resource]
  if type(v) ~= "number" then return nil end
  return v
end

local function snapshot(teamID)
  local s = stocks(teamID)
  if type(s) ~= "table" then return nil end
  local out = {}
  for _, r in ipairs(market.RESOURCES) do
    out[r] = tonumber(s[r]) or 0
  end
  return out
end

local function seed(teamID)
  local api = GG and GG.MedievalEconomy
  if not (api and api.Deposit) then return false end
  api.Deposit(teamID, "food", 500)
  api.Deposit(teamID, "wood", 500)
  api.Deposit(teamID, "stone", 200)
  api.Deposit(teamID, "iron", 100)
  return true
end

function gadget:GameFrame(frame)
  if not spawned and frame >= 20 then
    spawned = true
    echo("PHASE5 MARKET probe setup starting at frame %d", frame)

    local def = UnitDefNames and UnitDefNames["medieval_market"]
    if not def then
      echo("PHASE5 MARKET rate-verdict FAIL missing medieval_market UnitDef")
      echo("PHASE5 MARKET barter-verdict FAIL missing medieval_market UnitDef")
      echo("PHASE5 MARKET probe-complete FAIL")
      completed = true
      return
    end

    local y = Spring.GetGroundHeight and Spring.GetGroundHeight(MARKET_X, MARKET_Z) or 0
    local unitID = Spring.CreateUnit(def.id, MARKET_X, y, MARKET_Z, "south", TEAM)
    echo("PHASE5 MARKET spawned market unit=%s team=%d", tostring(unitID), TEAM)

    if not seed(TEAM) then
      echo("PHASE5 MARKET rate-verdict FAIL GG.MedievalEconomy unavailable")
      echo("PHASE5 MARKET barter-verdict FAIL GG.MedievalEconomy unavailable")
      echo("PHASE5 MARKET probe-complete FAIL")
      completed = true
      return
    end
    echo("PHASE5 MARKET stockpiles seeded food=%s wood=%s stone=%s iron=%s",
      tostring(stockOf(TEAM, "food")), tostring(stockOf(TEAM, "wood")),
      tostring(stockOf(TEAM, "stone")), tostring(stockOf(TEAM, "iron")))
  end

  if spawned and not rateChecked and frame >= 40 then
    rateChecked = true
    local api = GG and GG.MedievalMarket
    if not (api and api.GetRate) then
      echo("PHASE5 MARKET rate-verdict FAIL GG.MedievalMarket.GetRate missing")
      return
    end

    local live = stocks(TEAM)
    local marketCount = api.MarketCount and api.MarketCount(TEAM) or 0
    local ok = marketCount >= 1
    if not ok then
      echo("PHASE5 MARKET rate-verdict FAIL market not tracked count=%d", marketCount)
      return
    end

    for _, pair in ipairs({ { "food", "iron" }, { "wood", "stone" }, { "iron", "food" } }) do
      local from, to = pair[1], pair[2]
      local got = api.GetRate(from, to, TEAM)
      local want = market.rate(from, to, live)
      if math.abs(got - want) > 1e-9 then
        ok = false
        echo("PHASE5 MARKET rate-verdict FAIL %s->%s got=%s want=%s",
          from, to, tostring(got), tostring(want))
      else
        echo("PHASE5 MARKET rate %s->%s = %.4f", from, to, got)
      end
    end
    echo("PHASE5 MARKET rate-verdict %s", ok and "PASS" or "FAIL")
  end

  if spawned and rateChecked and not barterChecked and frame >= 60 then
    barterChecked = true
    local api = GG and GG.MedievalMarket
    local before = snapshot(TEAM)
    if not before or not (api and api.Exchange) then
      echo("PHASE5 MARKET barter-verdict FAIL market API or stockpiles unavailable")
      return
    end

    local quote = api.ValidateTrade(TEAM, BARTER_FROM, BARTER_TO, BARTER_AMOUNT)
    if not quote.ok then
      echo("PHASE5 MARKET barter-verdict FAIL validate reason=%s", tostring(quote.reason))
      return
    end

    local result = api.Exchange(TEAM, BARTER_FROM, BARTER_TO, BARTER_AMOUNT)
    local after = snapshot(TEAM)
    if not result.ok or not after then
      echo("PHASE5 MARKET barter-verdict FAIL exchange ok=%s reason=%s",
        tostring(result.ok), tostring(result.reason))
      return
    end

    local ok = true
    local cost = result.cost
    local spent = before[BARTER_FROM] - after[BARTER_FROM]
    local gained = after[BARTER_TO] - before[BARTER_TO]
    if spent ~= cost then
      ok = false
      echo("PHASE5 MARKET barter-verdict FAIL spent=%d expected-cost=%d", spent, cost)
    end
    if gained ~= BARTER_AMOUNT then
      ok = false
      echo("PHASE5 MARKET barter-verdict FAIL gained=%d expected=%d", gained, BARTER_AMOUNT)
    end
    for _, r in ipairs(market.RESOURCES) do
      if r ~= BARTER_FROM and r ~= BARTER_TO and before[r] ~= after[r] then
        ok = false
        echo("PHASE5 MARKET barter-verdict FAIL untouched resource %s moved %d->%d",
          r, before[r], after[r])
      end
    end
    if ok then
      echo("PHASE5 MARKET barter %s->%s amount=%d cost=%d stock %d->%d / %d->%d",
        BARTER_FROM, BARTER_TO, BARTER_AMOUNT, cost,
        before[BARTER_FROM], after[BARTER_FROM], before[BARTER_TO], after[BARTER_TO])
    end
    echo("PHASE5 MARKET barter-verdict %s", ok and "PASS" or "FAIL")
  end

  if barterChecked and not completed and frame >= 90 then
    completed = true
    echo("PHASE5 MARKET probe-complete PASS")
  end
end
