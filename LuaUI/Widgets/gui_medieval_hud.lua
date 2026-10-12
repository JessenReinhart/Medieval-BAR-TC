-- Medieval economy HUD: a top-screen status bar over the four stockpiles,
-- population, idle villagers and the starvation/food-supply alert, plus a
-- centered victory/defeat banner once the terminal verdict is published.
--
-- Reads ONLY team rules params published by gadget_medieval_hud.lua; the widget
-- never touches a synced GG table. All text comes from the pure formatter in
-- scripts/medieval_hud.lua so the on-screen strings match the pytest goldens.
function widget:GetInfo()
  return {
    name = "Medieval Economy HUD",
    desc = "Top-screen HUD bar: food/wood/stone/iron, population, idle villagers and starvation alert",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 0,
    enabled = true,
  }
end

-- Mod option gate; defaults to ON when the option is absent (older modoptions).
local options = Spring.GetModOptions() or {}
local optionValue = options.medievalhud
if optionValue == false or optionValue == 0 or optionValue == "0" then return end

local hud = VFS.Include("scripts/medieval_hud.lua")

local FONT_SIZE = 12
local BANNER_FONT_SIZE = 28
local PANEL_HEIGHT = 22
local PANEL_MARGIN = 6
local CELL_PAD = 10
local CHAR_WIDTH = FONT_SIZE * 0.6

local COL_OK = { 0.55, 0.85, 0.35 }
local COL_LOW = { 1.00, 0.75, 0.20 }
local COL_CRITICAL = { 1.00, 0.25, 0.20 }
local COL_NEUTRAL = { 0.90, 0.90, 0.85 }
local COL_IDLE = { 0.75, 0.85, 1.00 }

local function textWidth(text)
  return #text * CHAR_WIDTH
end

-- Rules param read; an unset param is nil and is shown as zero.
local function param(teamID, key)
  return Spring.GetTeamRulesParam(teamID, key)
end

local function numericParam(teamID, key)
  return tonumber(param(teamID, key)) or 0
end

local function buildCells(teamID)
  local cells = {}
  for _, resource in ipairs(hud.RESOURCE_ORDER) do
    local key = hud.PARAM_KEYS[resource]
    local value = numericParam(teamID, key)
    cells[#cells + 1] = {
      text = (hud.RESOURCE_LABELS[resource] or resource) .. ": " .. hud.formatStock(value),
      color = hud.RESOURCE_COLORS[resource] or COL_NEUTRAL,
      alpha = 1,
    }
  end

  local pop = numericParam(teamID, hud.PARAM_KEYS.pop)
  local cap = numericParam(teamID, hud.PARAM_KEYS.popcap)
  cells[#cells + 1] = { text = hud.popLine(pop, cap), color = COL_NEUTRAL, alpha = 1 }

  local idle = numericParam(teamID, hud.PARAM_KEYS.idle)
  cells[#cells + 1] = { text = hud.idleLine(idle), color = COL_IDLE, alpha = 1 }

  -- Food-supply alert. The binary starvation flag drives the hard red flash;
  -- the upkeep param grades the severity in between ticks.
  local starving = numericParam(teamID, hud.PARAM_KEYS.starvation) ~= 0
  local alert = hud.starvationAlert(
    numericParam(teamID, hud.PARAM_KEYS.food),
    numericParam(teamID, hud.PARAM_KEYS.upkeep)
  )
  local color = COL_OK
  if starving then
    color = COL_CRITICAL
  elseif alert.level == "critical" then
    color = COL_CRITICAL
  elseif alert.level == "low" then
    color = COL_LOW
  end
  cells[#cells + 1] = { text = alert.text, color = color, alpha = 1, alert = true }

  if starving then
    -- Blink on a timer phase: no art, no animation files, just alpha.
    local blink = (math.floor((Spring.GetTimer() or 0) * 2) % 2) == 0
    for _, cell in ipairs(cells) do
      cell.alpha = blink and 1 or 0.4
    end
  end

  return cells, starving
end

function widget:DrawScreen()
  local myAllyTeamID = Spring.GetMyAllyTeamID and Spring.GetMyAllyTeamID() or nil
  if not myAllyTeamID or myAllyTeamID < 0 then return end
  local teamID = (Spring.GetMyTeamID and Spring.GetMyTeamID()) or myAllyTeamID
  if not teamID or teamID < 0 then return end

  local vsx, vsy = Spring.GetViewGeometry()
  local cells, starving = buildCells(teamID)

  local width = CELL_PAD
  for _, cell in ipairs(cells) do
    width = width + textWidth(cell.text) + CELL_PAD
  end

  local left = math.floor((vsx - width) / 2)
  local bottom = vsy - PANEL_HEIGHT - PANEL_MARGIN
  local top = bottom + PANEL_HEIGHT

  gl.Color(0, 0, 0, 0.55)
  gl.Rect(left, bottom, left + width, top)

  if starving then
    -- Red frame around the bar while the team is starving.
    local blink = (math.floor((Spring.GetTimer() or 0) * 2) % 2) == 0
    local a = blink and 0.9 or 0.3
    gl.Color(1, 0.15, 0.1, a)
    gl.Rect(left - 2, bottom - 2, left + width + 2, bottom)
    gl.Rect(left - 2, top, left + width + 2, top + 2)
    gl.Rect(left - 2, bottom, left, top)
    gl.Rect(left + width, bottom, left + width + 2, top)
  end

  local cursor = left + CELL_PAD
  local textY = bottom + math.floor((PANEL_HEIGHT - FONT_SIZE) / 2)
  for _, cell in ipairs(cells) do
    local c = cell.color
    gl.Color(c[1], c[2], c[3], cell.alpha or 1)
    gl.Text(cell.text, cursor, textY, FONT_SIZE, "o")
    cursor = cursor + textWidth(cell.text) + CELL_PAD
  end
  gl.Color(1, 1, 1, 1)

  local winner = param(teamID, hud.PARAM_KEYS.victoryWinner)
  if winner == nil then winner = Spring.GetGameRulesParam and Spring.GetGameRulesParam(hud.PARAM_KEYS.victoryWinner) end
  local reason = param(teamID, hud.PARAM_KEYS.victoryReason)
  if reason == nil and Spring.GetGameRulesParam then reason = Spring.GetGameRulesParam(hud.PARAM_KEYS.victoryReason) end

  local banner = hud.victoryBanner(winner, myAllyTeamID, reason)
  if not banner then return end

  local bannerWidth = textWidth(banner) * (BANNER_FONT_SIZE / FONT_SIZE) + 40
  local bx = math.floor((vsx - bannerWidth) / 2)
  local by = math.floor(vsy * 0.5)
  gl.Color(0, 0, 0, 0.7)
  gl.Rect(bx, by - 14, bx + bannerWidth, by + BANNER_FONT_SIZE + 14)
  if string.find(banner, "^VICTORY") then
    gl.Color(0.45, 0.95, 0.4, 1)
  else
    gl.Color(0.95, 0.3, 0.25, 1)
  end
  gl.Text(banner, bx + 20, by, BANNER_FONT_SIZE, "o")
  gl.Color(1, 1, 1, 1)
end
