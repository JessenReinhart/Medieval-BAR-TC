-- Shared, pure medieval HUD formatting; no engine calls in this module.
-- The LuaUI widget VFS.Includes this file so the on-screen text and the pytest
-- goldens agree byte-for-byte. Nothing here may touch Spring/gl/VFS/GG.
local M = {}

local floor = math.floor
local huge = math.huge

local KILO = 1000
local MEGA = 1000000

-- Canonical team rules-param keys published by gadget_medieval_hud.lua and read
-- by gui_medieval_hud.lua. The gadget repeats these literals so the contract is
-- greppable in the publisher source; a test asserts the two stay identical.
M.PARAM_KEYS = {
  food = "food",
  wood = "wood",
  stone = "stone",
  iron = "iron",
  pop = "pop",
  popcap = "popcap",
  idle = "idle_villagers",
  starvation = "starvation",
  upkeep = "food_upkeep",
  victoryWinner = "victory_winner",
  victoryReason = "victory_reason",
}

M.RESOURCE_ORDER = { "food", "wood", "stone", "iron" }

M.RESOURCE_LABELS = {
  food = "Food",
  wood = "Wood",
  stone = "Stone",
  iron = "Iron",
}

-- RGB (0..1) per resource, used by the widget for the label cells.
M.RESOURCE_COLORS = {
  food = { 0.55, 0.85, 0.35 },
  wood = { 0.72, 0.50, 0.25 },
  stone = { 0.72, 0.72, 0.72 },
  iron = { 0.55, 0.62, 0.78 },
}

-- Ticks of remaining supply at which the alert steps up a severity.
M.LOW_TICKS = 10
M.CRITICAL_TICKS = 3

M.ALERT_PREFIX = {
  ok = "Food",
  low = "LOW FOOD",
  critical = "STARVING",
}

-- Terminal verdict reasons, keyed exactly as GG.MedievalVictory reports them.
M.REASON_LABELS = {
  tc_destruction = "Town Center destroyed",
  conquest = "Conquest",
  regicide = "King slain",
  surrender = "Surrender",
}

function M.finite(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- Non-negative integer coercion; anything unreadable becomes 0.
function M.count(n)
  local v = tonumber(n)
  if not M.finite(v) or v <= 0 then return 0 end
  return floor(v)
end

-- "1.2" / "15": one decimal, trailing ".0" trimmed.
local function oneDecimal(v)
  local text = string.format("%.1f", v)
  if string.sub(text, -2) == ".0" then text = string.sub(text, 1, -3) end
  return text
end

-- 0 -> "0"; 850 -> "850"; 1200 -> "1.2k"; 15000 -> "15k"; 1200000 -> "1.2M".
-- Negatives keep their sign ("-1.2k"); unreadable input formats as "0".
function M.formatStock(n)
  local v = tonumber(n)
  if not M.finite(v) then return "0" end
  local sign = ""
  if v < 0 then
    sign = "-"
    v = -v
  end
  if v < KILO then
    local rounded = floor(v + 0.5)
    if rounded < KILO then
      if rounded == 0 then return "0" end
      return sign .. tostring(rounded)
    end
    v = rounded
  end
  if v < MEGA then
    local text = oneDecimal(v / KILO)
    if text == "1000" then return sign .. "1M" end
    return sign .. text .. "k"
  end
  return sign .. oneDecimal(v / MEGA) .. "M"
end

-- One cell per resource, in RESOURCE_ORDER: { key, label, text, value }.
function M.stockCells(resources)
  local src = type(resources) == "table" and resources or {}
  local cells = {}
  for index, key in ipairs(M.RESOURCE_ORDER) do
    local value = tonumber(src[key])
    if not M.finite(value) then value = 0 end
    cells[index] = {
      key = key,
      label = M.RESOURCE_LABELS[key] or key,
      text = M.formatStock(value),
      value = value,
    }
  end
  return cells
end

-- "Food: 850  Wood: 500  Stone: 100  Iron: 50" (two-space cell separator).
function M.stockLine(resources)
  local parts = {}
  for index, cell in ipairs(M.stockCells(resources)) do
    parts[index] = cell.label .. ": " .. cell.text
  end
  return table.concat(parts, "  ")
end

function M.popLine(pop, cap)
  return "Pop: " .. tostring(M.count(pop)) .. "/" .. tostring(M.count(cap))
end

function M.idleLine(n)
  return "Idle: " .. tostring(M.count(n))
end

-- Supply grade for the food cell. `upkeepPerTick` is the food owed per upkeep
-- tick; <= 0 means the team has no drain, so the alert is always "ok".
-- Unreadable stock grades as empty, so a broken param fails loud, not silent.
function M.starvationAlert(food, upkeepPerTick)
  local stock = tonumber(food)
  if not M.finite(stock) or stock < 0 then stock = 0 end
  stock = floor(stock)
  local upkeep = tonumber(upkeepPerTick)
  local level = "ok"
  if M.finite(upkeep) and upkeep > 0 then
    local ticks = stock / upkeep
    if ticks < M.CRITICAL_TICKS then
      level = "critical"
    elseif ticks < M.LOW_TICKS then
      level = "low"
    end
  end
  return {
    level = level,
    text = (M.ALERT_PREFIX[level] or M.ALERT_PREFIX.ok) .. ": " .. M.formatStock(stock),
  }
end

-- Trimmed reason text, or nil when there is nothing worth showing.
function M.reasonText(reason)
  if type(reason) ~= "string" then return nil end
  local trimmed = string.gsub(reason, "^%s+", "")
  trimmed = string.gsub(trimmed, "%s+$", "")
  if trimmed == "" then return nil end
  return M.REASON_LABELS[trimmed] or trimmed
end

-- nil winner means "no verdict yet" (rules param unset) — the widget draws
-- nothing. Otherwise "VICTORY" / "DEFEAT", plus " - <reason>" when known.
function M.victoryBanner(winner, myAllyTeam, reason)
  local w = tonumber(winner)
  local mine = tonumber(myAllyTeam)
  if not M.finite(w) or not M.finite(mine) then return nil end
  local title = "DEFEAT"
  if floor(w) == floor(mine) then title = "VICTORY" end
  local detail = M.reasonText(reason)
  if detail then return title .. " - " .. detail end
  return title
end

return M
