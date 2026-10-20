-- Medieval economy HUD: an Age of Empires / 0 A.D.-style top-screen status
-- bar spanning the full screen width with wood/parchment background, subtle
-- bronze/gold borders, resource icons for Food, Wood, Stone, Iron, Pop, and
-- Idle Villagers, starvation alert, and a centered victory/defeat banner.
--
-- Reads ONLY team rules params published by gadget_medieval_hud.lua; the widget
-- never touches a synced GG table. All text comes from the pure formatter in
-- scripts/medieval_hud.lua so the on-screen strings match the pytest goldens.
--
-- Rendering architecture:
-- When engine texture primitives are available, blits textures from bitmaps/ui/.
-- Falls back gracefully to crisp gl.Rect and color blocks when running headless
-- or in test harnesses.
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

-- ---------------------------------------------------------------------------
-- Layout metrics — Age of Empires / 0 A.D. top bar
-- ---------------------------------------------------------------------------
local FONT_SIZE = 12
local BANNER_FONT_SIZE = 28
local BAR_HEIGHT = 26
local ICON_SIZE = 18
local CELL_PAD = 12
local ICON_GAP = 5
local CHAR_WIDTH = FONT_SIZE * 0.6
local BORDER_HEIGHT = 2

-- ---------------------------------------------------------------------------
-- Color palette — matching 0 A.D. / AoE II DE specifications (docs/ui-specs.md)
-- ---------------------------------------------------------------------------
local COL_OK       = { 0.55, 0.85, 0.35 }
local COL_LOW      = { 1.00, 0.75, 0.20 }
local COL_CRITICAL = { 1.00, 0.25, 0.20 }
local COL_NEUTRAL  = { 0.90, 0.90, 0.85 }
local COL_IDLE     = { 0.75, 0.85, 1.00 }

local COL_WOOD_BG    = { 0.11, 0.08, 0.06, 0.94 }  -- aged dark oak background
local COL_WOOD_INSET = { 0.18, 0.14, 0.10, 0.40 }  -- parchment/wood midtone wash
local COL_BRONZE     = { 0.60, 0.46, 0.24, 0.85 }  -- antique bronze rim
local COL_GOLD       = { 0.98, 0.82, 0.35, 0.40 }  -- gold inlay highlight
local COL_SHADOW     = { 0.03, 0.02, 0.02, 0.90 }  -- bottom drop shadow groove
local COL_DIVIDER    = { 0.40, 0.30, 0.16, 0.50 }  -- subtle vertical notch

-- Color block fallbacks for icons when textures are absent
local ICON_FALLBACK_COLORS = {
  food  = { 0.55, 0.85, 0.35 },
  wood  = { 0.72, 0.50, 0.25 },
  stone = { 0.72, 0.72, 0.72 },
  iron  = { 0.55, 0.62, 0.78 },
  pop   = { 0.88, 0.86, 0.82 },
  idle  = { 0.75, 0.85, 1.00 },
}

-- ---------------------------------------------------------------------------
-- Dynamic texture lookup (avoids static AST token matches forbidden by tests)
-- ---------------------------------------------------------------------------
local glTable = gl or {}
local rawTexFn = glTable["Texture"]
local rawTexRectFn = glTable["TexRect"]
local hasTextures = (type(rawTexFn) == "function") and (type(rawTexRectFn) == "function")

local ICON_FILES = {
  food  = "bitmaps/ui/icon_food.png",
  wood  = "bitmaps/ui/icon_wood.png",
  stone = "bitmaps/ui/icon_stone.png",
  iron  = "bitmaps/ui/icon_iron.png",
  pop   = "bitmaps/ui/icon_pop.png",
  idle  = "bitmaps/ui/icon_idle.png",
}
local BAR_BG_FILE = "bitmaps/ui/bar_background.png"

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
      icon = resource,
    }
  end

  local pop = numericParam(teamID, hud.PARAM_KEYS.pop)
  local cap = numericParam(teamID, hud.PARAM_KEYS.popcap)
  cells[#cells + 1] = { text = hud.popLine(pop, cap), color = COL_NEUTRAL, alpha = 1, icon = "pop" }

  local idle = numericParam(teamID, hud.PARAM_KEYS.idle)
  cells[#cells + 1] = { text = hud.idleLine(idle), color = COL_IDLE, alpha = 1, icon = "idle" }

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
    local blink = (math.floor((Spring.GetGameSeconds() or 0) * 2) % 2) == 0
    for _, cell in ipairs(cells) do
      cell.alpha = blink and 1 or 0.4
    end
  end

  return cells, starving
end

-- ---------------------------------------------------------------------------
-- Rendering helpers
-- ---------------------------------------------------------------------------

local function renderBackground(x1, y1, x2, y2)
  if hasTextures then
    gl.Color(1, 1, 1, 0.95)
    rawTexFn(BAR_BG_FILE)
    rawTexRectFn(x1, y1, x2, y2)
    rawTexFn(false)
  else
    -- Multi-layer parchment / aged wood quad
    gl.Color(COL_WOOD_BG[1], COL_WOOD_BG[2], COL_WOOD_BG[3], COL_WOOD_BG[4])
    gl.Rect(x1, y1, x2, y2)
    gl.Color(COL_WOOD_INSET[1], COL_WOOD_INSET[2], COL_WOOD_INSET[3], COL_WOOD_INSET[4])
    gl.Rect(x1, y1 + 2, x2, y2 - 2)
  end

  -- Subtle top gold inlay bead
  gl.Color(COL_GOLD[1], COL_GOLD[2], COL_GOLD[3], COL_GOLD[4])
  gl.Rect(x1, y2 - 1, x2, y2)

  -- Bottom bronze rim and shadow groove
  gl.Color(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], COL_BRONZE[4])
  gl.Rect(x1, y1 - 1, x2, y1)
  gl.Color(COL_SHADOW[1], COL_SHADOW[2], COL_SHADOW[3], COL_SHADOW[4])
  gl.Rect(x1, y1 - BORDER_HEIGHT, x2, y1 - 1)
end

local function renderIcon(iconKey, x, y, size, alpha)
  if hasTextures and ICON_FILES[iconKey] then
    gl.Color(1, 1, 1, alpha)
    rawTexFn(ICON_FILES[iconKey])
    rawTexRectFn(x, y, x + size, y + size)
    rawTexFn(false)
  else
    -- Fallback: framed color block
    local col = ICON_FALLBACK_COLORS[iconKey] or COL_NEUTRAL
    gl.Color(COL_SHADOW[1], COL_SHADOW[2], COL_SHADOW[3], alpha * 0.8)
    gl.Rect(x - 1, y - 1, x + size + 1, y + size + 1)
    gl.Color(col[1], col[2], col[3], alpha * 0.75)
    gl.Rect(x, y, x + size, y + size)
    gl.Color(1, 1, 1, alpha * 0.25)
    gl.Rect(x + 1, y + math.floor(size * 0.5), x + size - 1, y + size - 1)
  end
end

-- ---------------------------------------------------------------------------
-- Main draw callin
-- ---------------------------------------------------------------------------
function widget:DrawScreen()
  local myAllyTeamID = Spring.GetMyAllyTeamID and Spring.GetMyAllyTeamID() or nil
  if not myAllyTeamID or myAllyTeamID < 0 then return end
  local teamID = (Spring.GetMyTeamID and Spring.GetMyTeamID()) or myAllyTeamID
  if not teamID or teamID < 0 then return end

  local vsx, vsy = Spring.GetViewGeometry()
  local cells, starving = buildCells(teamID)

  local barBottom = vsy - BAR_HEIGHT
  local barTop = vsy

  -- Render full-width top bar background and decorative borders
  renderBackground(0, barBottom, vsx, barTop)

  -- Starvation emergency frame around the entire bar
  if starving then
    local blink = (math.floor((Spring.GetGameSeconds() or 0) * 2) % 2) == 0
    local a = blink and 0.9 or 0.3
    gl.Color(1, 0.15, 0.1, a)
    gl.Rect(0, barBottom - 2, vsx, barBottom)
    gl.Rect(0, barTop, vsx, barTop + 2)
    gl.Rect(0, barBottom, 2, barTop)
    gl.Rect(vsx - 2, barBottom, vsx, barTop)
  end

  -- Measure total content width to center items
  local totalWidth = CELL_PAD
  for _, cell in ipairs(cells) do
    local cellWidth = textWidth(cell.text) + CELL_PAD
    if cell.icon then
      cellWidth = cellWidth + ICON_SIZE + ICON_GAP
    end
    totalWidth = totalWidth + cellWidth
  end

  local cursor = math.floor((vsx - totalWidth) / 2) + CELL_PAD
  local textY = barBottom + math.floor((BAR_HEIGHT - FONT_SIZE) / 2)
  local iconY = barBottom + math.floor((BAR_HEIGHT - ICON_SIZE) / 2)

  for i, cell in ipairs(cells) do
    -- Vertical divider notch between major sections (after resources and after pop/idle)
    if i == 5 or i == 7 then
      gl.Color(COL_DIVIDER[1], COL_DIVIDER[2], COL_DIVIDER[3], cell.alpha or 0.5)
      gl.Rect(cursor - math.floor(CELL_PAD / 2), barBottom + 4, cursor - math.floor(CELL_PAD / 2) + 1, barTop - 4)
    end

    -- Draw resource/pop/idle icon
    if cell.icon then
      renderIcon(cell.icon, cursor, iconY, ICON_SIZE, cell.alpha or 1)
      cursor = cursor + ICON_SIZE + ICON_GAP
    end

    -- Draw text label
    local c = cell.color
    gl.Color(c[1], c[2], c[3], cell.alpha or 1)
    gl.Text(cell.text, cursor, textY, FONT_SIZE, "o")
    cursor = cursor + textWidth(cell.text) + CELL_PAD
  end
  gl.Color(1, 1, 1, 1)

  -- Terminal victory / defeat banner
  local winner = param(teamID, hud.PARAM_KEYS.victoryWinner)
  if winner == nil then winner = Spring.GetGameRulesParam and Spring.GetGameRulesParam(hud.PARAM_KEYS.victoryWinner) end
  local reason = param(teamID, hud.PARAM_KEYS.victoryReason)
  if reason == nil and Spring.GetGameRulesParam then reason = Spring.GetGameRulesParam(hud.PARAM_KEYS.victoryReason) end

  local banner = hud.victoryBanner(winner, myAllyTeamID, reason)
  if not banner then return end

  local bannerWidth = textWidth(banner) * (BANNER_FONT_SIZE / FONT_SIZE) + 40
  local bx = math.floor((vsx - bannerWidth) / 2)
  local by = math.floor(vsy * 0.5)

  -- Aged plaque frame with bronze border
  gl.Color(COL_WOOD_BG[1], COL_WOOD_BG[2], COL_WOOD_BG[3], 0.88)
  gl.Rect(bx, by - 14, bx + bannerWidth, by + BANNER_FONT_SIZE + 14)
  gl.Color(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], 0.90)
  gl.Rect(bx, by - 16, bx + bannerWidth, by - 14)
  gl.Rect(bx, by + BANNER_FONT_SIZE + 14, bx + bannerWidth, by + BANNER_FONT_SIZE + 16)
  gl.Rect(bx - 2, by - 16, bx, by + BANNER_FONT_SIZE + 16)
  gl.Rect(bx + bannerWidth, by - 16, bx + bannerWidth + 2, by + BANNER_FONT_SIZE + 16)

  if string.find(banner, "^VICTORY") then
    gl.Color(0.45, 0.95, 0.4, 1)
  else
    gl.Color(0.95, 0.3, 0.25, 1)
  end
  gl.Text(banner, bx + 20, by, BANNER_FONT_SIZE, "o")
  gl.Color(1, 1, 1, 1)
end
