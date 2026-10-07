-- Shared, pure medieval recruitment math; no engine calls in this module.
local M = {
  MILITARY_UPKEEP_FOOD = 1,
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

return M
