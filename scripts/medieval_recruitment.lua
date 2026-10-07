-- Shared, pure medieval recruitment math; no engine calls in this module.
local M = {
  MILITARY_UPKEEP_FOOD = 1,
  -- Phase-3: standing-army food upkeep, charged once per upkeep tick.
  UPKEEP_TICK_FRAMES = 90,        -- 1 tick = 90 engine frames
  STARVATION_HP_FRACTION = 0.05,  -- starved units lose up to 5% of current HP per tick
  UPKEEP = {                      -- food per unit per tick, keyed by internal def name
    medieval_infantry = 2,
    medieval_archer = 2,
    medieval_cavalry = 3,
  },
  COSTS = {
    medieval_infantry = { food = 30, wood = 20, stone = 10, iron = 5 },
    medieval_archer = { food = 25, wood = 30, stone = 5, iron = 2 },
    medieval_cavalry = { food = 50, wood = 20, stone = 20, iron = 25 },
  },
}

function M.getCost(unitName)
  local source = M.COSTS[unitName]
  if not source then return nil end
  local result = {}
  for resource, amount in pairs(source) do result[resource] = amount end
  return result
end

function M.canAfford(stock, unitName, economy)
  local cost = M.getCost(unitName)
  if not cost or type(economy) ~= "table" or type(economy.canAffordCosts) ~= "function" then return false end
  return economy.canAffordCosts(stock, cost)
end

-- Legacy Phase-2 flat-rate helper (1 food per military unit per tick).
-- Phase-3 uses the per-unit UPKEEP table via armyUpkeep/payUpkeep below.
function M.applyUpkeep(stock, militaryCount, frames, framesPerTick)
  if type(stock) ~= "table" or type(militaryCount) ~= "number" or type(frames) ~= "number" then return false end
  framesPerTick = framesPerTick or 30
  if framesPerTick <= 0 then return false end
  local ticks = math.floor(frames / framesPerTick)
  local amount = ticks * math.max(0, militaryCount) * M.MILITARY_UPKEEP_FOOD
  if (stock.food or 0) < amount then return false end
  stock.food = stock.food - amount
  return true
end

-- Per-unit food upkeep rate for one tick; 0 for anything not in the UPKEEP table
-- (villagers, houses, town centers, granaries, barracks, ...).
function M.upkeepFor(unitName)
  if type(unitName) ~= "string" then return 0 end
  return M.UPKEEP[unitName] or 0
end

-- Military units are exactly the pop-consuming units that carry an upkeep rate,
-- so villagers and every building/town are excluded by construction.
function M.isMilitary(unitName)
  return M.upkeepFor(unitName) > 0
end

-- Fold a flat list of internal def names into { [militaryName] = count },
-- dropping anything that does not pay upkeep.
function M.armyCounts(unitNames)
  local counts = {}
  if type(unitNames) ~= "table" then return counts end
  for _, name in pairs(unitNames) do
    if M.isMilitary(name) then
      counts[name] = (counts[name] or 0) + 1
    end
  end
  return counts
end

-- Total food upkeep for one tick given { [unitName] = count }.
-- Non-military keys, non-positive and non-finite counts contribute nothing.
function M.armyUpkeep(unitCounts)
  if type(unitCounts) ~= "table" then return 0 end
  local total = 0
  for name, count in pairs(unitCounts) do
    local per = M.UPKEEP[name]
    if per and type(count) == "number" and count == count and count > 0 then
      total = total + per * math.floor(count)
    end
  end
  return total
end

-- Pure starvation marker for one tick: 0 = upkeep covered, 1 = starving.
-- Returns nil when the food balance is not usable, so callers cannot mistake
-- "unknown" for "fed".
function M.starvationMarker(food, unitCounts)
  local balance = tonumber(food)
  if not balance or balance ~= balance then return nil end
  if balance >= M.armyUpkeep(unitCounts) then return 0 end
  return 1
end

-- Charge one tick of upkeep straight from a stock table (pure stand-in for the
-- economy gadget's CanAfford + Transact pair). Returns the starvation marker;
-- the stock is only mutated when the full amount can be paid.
function M.payUpkeep(stock, unitCounts)
  if type(stock) ~= "table" then return 1 end
  local balance = tonumber(stock.food)
  local marker = M.starvationMarker(balance, unitCounts)
  if marker ~= 0 then return 1 end
  local total = M.armyUpkeep(unitCounts)
  if total > 0 then stock.food = balance - total end
  return 0
end

-- Mild, never-lethal starvation penalty: current HP minus up to
-- STARVATION_HP_FRACTION of itself. Returns nil for dead/invalid units.
function M.starvedHealth(health)
  local hp = tonumber(health)
  if not hp or hp ~= hp or hp <= 0 then return nil end
  local fraction = tonumber(M.STARVATION_HP_FRACTION) or 0
  if fraction <= 0 then return hp end
  if fraction > 0.99 then fraction = 0.99 end
  local newHp = hp - hp * fraction
  if newHp <= 0 then return hp end
  return newHp
end

return M
