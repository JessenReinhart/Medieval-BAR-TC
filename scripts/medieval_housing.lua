-- Shared, pure medieval housing and population math; no engine calls in this module.
local M = {
  DEFAULT_CAP = 10,       -- baseline for a settlement with no buildings
  MAX_POP_CAP = 300,      -- hard ceiling for settlement population
  POP_PROVIDERS = {
    medieval_town_center = 10,
    medieval_house = 5,
  },
}

local floor = math.floor
local huge = math.huge

function M.finite(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

function M.validCount(n)
  return M.finite(n) and n >= 0 and n == floor(n)
end

-- Housing cap given a multiset of live building definition names.
-- e.g. { medieval_town_center = 1, medieval_house = 4 } -> 10 + 10 + 20 = 40
function M.computeCap(buildingsTable)
  if type(buildingsTable) ~= "table" then return M.DEFAULT_CAP end
  local cap = M.DEFAULT_CAP
  for defName, count in pairs(buildingsTable) do
    if M.validCount(count) then
      local per = M.POP_PROVIDERS[defName] or 0
      cap = cap + per * count
    end
  end
  return math.min(cap, M.MAX_POP_CAP)
end

-- Can a team train/construct an additional unit consuming `popCost`?
function M.canSupport(currentPop, cap, popCost)
  popCost = popCost or 1
  if not M.validCount(currentPop) or not M.validCount(cap) or not M.validCount(popCost) then
    return false
  end
  return (currentPop + popCost) <= cap
end

-- Category tags: does this unitDef count towards population?
-- Settlers and military units consume 1 population each; buildings do not.
function M.unitConsumesPop(defName)
  if type(defName) ~= "string" then return false end
  local popUnits = {
    medieval_villager = 1,
    medieval_infantry = 1,
    medieval_archer = 1,
    medieval_cavalry = 1,
    medieval_catapult = 1,
  }
  return popUnits[defName] or 0
end

return M