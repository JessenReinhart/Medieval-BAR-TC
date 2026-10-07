-- Shared, pure medieval economy math; no engine calls in this module.
-- Stockpiles are authored here; synced gadgets keep the authoritative tables.
local M = {
  RESOURCES = { "food", "wood", "stone", "iron" },
  FOOD = "food", WOOD = "wood", STONE = "stone", IRON = "iron",
  STARTING_RESERVES = { food = 200, wood = 200, stone = 100, iron = 50 },
  MAX_STOCKPILE = 100000,
}

local floor = math.floor
local huge = math.huge

function M.validResource(r)
  return type(r) == "string" and (r == "food" or r == "wood" or r == "stone" or r == "iron")
end

function M.finite(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- Non-negative, integer, optionally bounded. Rejects NaN/Inf/negative/fractional.
function M.validAmount(n, max)
  if not M.finite(n) or n < 0 or n ~= floor(n) then return nil end
  if max ~= nil and n > max then return nil end
  return true
end

-- Fresh zeroed stockpile table with canonical key order.
function M.newStockpiles()
  return { food = 0, wood = 0, stone = 0, iron = 0 }
end

-- Starting reserves for a new team (all resources present).
function M.startingStockpiles()
  local s = M.newStockpiles()
  for _, r in ipairs(M.RESOURCES) do
    s[r] = M.STARTING_RESERVES[r]
  end
  return s
end

-- Add a validated amount; returns new total or nil on invalid input.
function M.deposit(stock, resource, amount)
  if not M.validResource(resource) or not M.validAmount(amount) then return nil end
  if type(stock) ~= "table" or not M.finite(stock[resource]) then return nil end
  local v = math.min(math.floor(stock[resource]) + amount, M.MAX_STOCKPILE)
  stock[resource] = v
  return v
end

-- Subtract a validated amount without going negative; nil on insufficient funds.
function M.withdraw(stock, resource, amount)
  if not M.validResource(resource) or not M.validAmount(amount) then return nil end
  if type(stock) ~= "table" or not M.finite(stock[resource]) or stock[resource] < amount then return nil end
  stock[resource] = math.floor(stock[resource]) - amount
  return stock[resource]
end

function M.canAfford(stock, resource, amount)
  return M.validResource(resource) and M.validAmount(amount)
    and type(stock) == "table" and M.finite(stock[resource]) and stock[resource] >= amount
end

-- Can a stock table afford an entire costs table? costs maps resource -> amount.
function M.canAffordCosts(stock, costs)
  if type(stock) ~= "table" or type(costs) ~= "table" then return false end
  for r, a in pairs(costs) do
    if not M.canAfford(stock, r, a) then return false end
  end
  return true
end

-- Apply a costs table atomically. costs maps resource -> amount and MUST be fully
-- affordable; otherwise no stockpile is mutated. Returns true or nil.
function M.transact(stock, costs)
  if type(stock) ~= "table" or type(costs) ~= "table" then return nil end
  for r, a in pairs(costs) do
    if not M.canAfford(stock, r, a) then return nil end
  end
  for r, a in pairs(costs) do
    stock[r] = math.floor(stock[r]) - a
  end
  return true
end

-- Integer resource total for a unit's build cost table {resource=amount,...}.
-- Useful for affordability checks against custom economy rather than energy/metal.
function M.costTotal(costs)
  if type(costs) ~= "table" then return 0 end
  local t = 0
  for r, a in pairs(costs) do
    if M.validResource(r) and M.validAmount(a) then t = t + a end
  end
  return t
end

return M