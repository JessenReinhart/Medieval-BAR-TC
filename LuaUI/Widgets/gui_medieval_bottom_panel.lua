-- Medieval bottom selection & command panel: an AoE / 0 A.D. style
-- bottom-center panel that shows selected unit portraits, health bars,
-- stats, and building production queues.
--
-- Pure unsynced widget. No synced GG access. Reads via Spring.GetUnitHealth,
-- Spring.GetUnitDefID, UnitDefs, Spring.GetSelectedUnits.
--
-- Textured panel background from bitmaps/ui/bar_background.png.
-- Gate on modoption "medievalbottompanel" (default on, defensive fallback).

function widget:GetInfo()
  return {
    name    = "Medieval Bottom Panel",
    desc    = "AoE / 0 A.D. style bottom selection, portrait and command panel",
    author  = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer   = 1,
    enabled = true,
  }
end

-- Mod option gate; defaults to ON when the option is absent (older modoptions).
local options = Spring.GetModOptions and Spring.GetModOptions() or {}
local optionValue = options.medievalbottompanel
if optionValue == false or optionValue == 0 or optionValue == "0" then return end

--------------------------------------------------------------------------------
-- Constants & Colors (from docs/ui-specs.md)
--------------------------------------------------------------------------------

local PANEL_HEIGHT       = 140
local PORTRAIT_SIZE      = 96
local PORTRAIT_PAD       = 6
local MULTI_PORTRAIT     = 40   -- small portrait for multi-select grid
local MULTI_COLS         = 8    -- columns in multi-select grid
local MULTI_ROWS         = 3    -- max rows
local HEALTH_BAR_HEIGHT  = 6
local STAT_FONT_SIZE     = 12
local NAME_FONT_SIZE     = 14
local BORDER_THICKNESS   = 16   -- panel_border.png 9-slice rim

-- Color palette (docs/ui-specs.md §3)
local COL_PARCHMENT  = { 0.92, 0.88, 0.80, 1.00 }
local COL_GOLD       = { 0.98, 0.82, 0.35, 1.00 }
local COL_STAT       = { 0.88, 0.86, 0.82, 1.00 }
local COL_DARK_BG    = { 0.11, 0.08, 0.06, 0.94 }
local COL_HEALTH_OK  = { 0.15, 0.75, 0.15, 1.00 }
local COL_HEALTH_LOW = { 1.00, 0.75, 0.20, 1.00 }
local COL_HEALTH_CRIT = { 1.00, 0.25, 0.20, 1.00 }
local COL_BRONZE     = { 0.60, 0.46, 0.24, 1.00 }
local COL_SHADOW     = { 0.00, 0.00, 0.00, 0.80 }
local COL_QUEUE_BG   = { 0.14, 0.12, 0.10, 0.90 }
local COL_QUEUE_BAR  = { 0.30, 0.60, 0.95, 1.00 }

--------------------------------------------------------------------------------
-- Texture paths
--------------------------------------------------------------------------------

local TEX_BACKGROUND  = "bitmaps/ui/bar_background.png"
local TEX_BORDER      = "bitmaps/ui/panel_border.png"
local TEX_CORNER      = "bitmaps/ui/frame_corner.png"

-- Cache for unit portrait textures (unitDef name -> path, or false if missing)
local portraitCache = {}

local function getPortraitPath(unitDefName)
  if portraitCache[unitDefName] ~= nil then
    return portraitCache[unitDefName]
  end
  local path = "unitpics/" .. unitDefName .. ".png"
  -- Check existence via VFS if available
  if VFS and VFS.FileExists then
    if VFS.FileExists(path) then
      portraitCache[unitDefName] = path
    else
      portraitCache[unitDefName] = false
    end
  else
    -- Assume available (engine will handle missing gracefully)
    portraitCache[unitDefName] = path
  end
  return portraitCache[unitDefName]
end

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function healthColor(fraction)
  if fraction > 0.5 then
    return COL_HEALTH_OK
  elseif fraction > 0.25 then
    return COL_HEALTH_LOW
  else
    return COL_HEALTH_CRIT
  end
end

local function clamp(v, lo, hi)
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

-- Safe Spring API wrappers
local function getSelectedUnits()
  if Spring and Spring.GetSelectedUnits then
    return Spring.GetSelectedUnits()
  end
  return {}
end

local function getUnitDefID(unitID)
  if Spring and Spring.GetUnitDefID then
    return Spring.GetUnitDefID(unitID)
  end
  return nil
end

local function getUnitHealth(unitID)
  if Spring and Spring.GetUnitHealth then
    return Spring.GetUnitHealth(unitID)
  end
  return nil, nil
end

local function getUnitCurrentBuildPower(unitID)
  -- Returns: health, maxHP, paralyzeDamage, captureProgress, buildProgress
  if Spring and Spring.GetUnitHealth then
    local health, maxHP, paraDmg, capProg, buildProg = Spring.GetUnitHealth(unitID)
    return buildProg
  end
  return nil
end

local function getFactoryCommands(unitID, count)
  if Spring and Spring.GetFactoryCommands then
    return Spring.GetFactoryCommands(unitID, count or 20)
  end
  return nil
end

--------------------------------------------------------------------------------
-- 9-slice border rendering
--------------------------------------------------------------------------------

local function drawNineSlice(texPath, x0, y0, x1, y1, rim)
  local r = rim or BORDER_THICKNESS
  local uvLo = r / 128.0
  local uvHi = 1.0 - uvLo

  gl.Texture(texPath)

  -- Corners: bottom-left, bottom-right, top-left, top-right
  gl.TexRect(x0,     y0,     x0 + r, y0 + r, 0.0, 0.0, uvLo, uvLo)
  gl.TexRect(x1 - r, y0,     x1,     y0 + r, uvHi, 0.0, 1.0, uvLo)
  gl.TexRect(x0,     y1 - r, x0 + r, y1,     0.0, uvHi, uvLo, 1.0)
  gl.TexRect(x1 - r, y1 - r, x1,     y1,     uvHi, uvHi, 1.0, 1.0)

  -- Edges: bottom, top, left, right
  gl.TexRect(x0 + r, y0,     x1 - r, y0 + r, uvLo, 0.0, uvHi, uvLo)
  gl.TexRect(x0 + r, y1 - r, x1 - r, y1,     uvLo, uvHi, uvHi, 1.0)
  gl.TexRect(x0,     y0 + r, x0 + r, y1 - r, 0.0, uvLo, uvLo, uvHi)
  gl.TexRect(x1 - r, y0 + r, x1,     y1 - r, uvHi, uvLo, 1.0, uvHi)

  -- Center fill
  gl.TexRect(x0 + r, y0 + r, x1 - r, y1 - r, uvLo, uvLo, uvHi, uvHi)

  gl.Texture(false)
end

local function drawCornerBrackets(x0, y0, x1, y1, sz)
  local s = sz or 20
  gl.Texture(TEX_CORNER)
  -- bottom-left
  gl.TexRect(x0, y0, x0 + s, y0 + s, 0, 0, 1, 1)
  -- bottom-right (mirror x)
  gl.TexRect(x1, y0, x1 - s, y0 + s, 0, 0, 1, 1)
  -- top-left (mirror y)
  gl.TexRect(x0, y1, x0 + s, y1 - s, 0, 0, 1, 1)
  -- top-right (mirror x+y)
  gl.TexRect(x1, y1, x1 - s, y1 - s, 0, 0, 1, 1)
  gl.Texture(false)
end

--------------------------------------------------------------------------------
-- Drawing: single unit info
--------------------------------------------------------------------------------

local function drawSingleUnit(unitID, px, py, pw, ph)
  local udID = getUnitDefID(unitID)
  if not udID then return end
  local ud = UnitDefs and UnitDefs[udID]
  if not ud then return end

  local unitName = ud.name or "unknown"
  local humanName = ud.humanName or ud.tooltip or unitName

  -- Portrait area (left side of the panel region)
  local portX = px + PORTRAIT_PAD
  local portY = py + (ph - PORTRAIT_SIZE) * 0.5
  local portRight = portX + PORTRAIT_SIZE
  local portTop   = portY + PORTRAIT_SIZE

  -- Portrait background (dark)
  gl.Color(COL_DARK_BG)
  gl.Rect(portX, portY, portRight, portTop)

  -- Draw portrait image
  local portrait = getPortraitPath(unitName)
  if portrait then
    gl.Color(1, 1, 1, 1)
    gl.Texture(portrait)
    gl.TexRect(portX, portY, portRight, portTop)
    gl.Texture(false)
  end

  -- Portrait ornamental border
  drawNineSlice(TEX_BORDER, portX - 4, portY - 4, portRight + 4, portTop + 4, 8)

  -- Text area starts to the right of the portrait
  local textX = portRight + PORTRAIT_PAD + 8
  local textY = portTop - 8

  -- Unit name (gold, larger)
  gl.Color(COL_SHADOW)
  gl.Text(humanName, textX + 1, textY - 1, NAME_FONT_SIZE, "o")
  gl.Color(COL_GOLD)
  gl.Text(humanName, textX, textY, NAME_FONT_SIZE, "o")

  -- Health bar
  local health, maxHP = getUnitHealth(unitID)
  if health and maxHP and maxHP > 0 then
    local frac = clamp(health / maxHP, 0, 1)
    local barX = textX
    local barY = textY - NAME_FONT_SIZE - 8
    local barW = 160
    local barH = HEALTH_BAR_HEIGHT

    -- BG
    gl.Color(0.15, 0.12, 0.10, 0.9)
    gl.Rect(barX, barY, barX + barW, barY + barH)

    -- Fill
    local hc = healthColor(frac)
    gl.Color(hc)
    gl.Rect(barX, barY, barX + barW * frac, barY + barH)

    -- Border
    gl.Color(COL_BRONZE)
    gl.Rect(barX, barY, barX + barW, barY + 1)           -- bottom
    gl.Rect(barX, barY + barH - 1, barX + barW, barY + barH)  -- top
    gl.Rect(barX, barY, barX + 1, barY + barH)            -- left
    gl.Rect(barX + barW - 1, barY, barX + barW, barY + barH)  -- right

    -- HP text
    local hpStr = string.format("%d / %d", math.floor(health), math.floor(maxHP))
    gl.Color(COL_PARCHMENT)
    gl.Text(hpStr, barX + barW * 0.5, barY + 1, STAT_FONT_SIZE - 2, "oc")
  end

  -- Stats: attack, armor, speed
  local statY = textY - NAME_FONT_SIZE - 8 - HEALTH_BAR_HEIGHT - 12

  local stats = {}
  if ud.weapons and #ud.weapons > 0 then
    local wDef = WeaponDefs and WeaponDefs[ud.weapons[1].weaponDef]
    if wDef then
      local dmg = 0
      if wDef.damages and wDef.damages[0] then
        dmg = math.floor(wDef.damages[0])
      end
      stats[#stats + 1] = "Atk: " .. dmg
    end
  end
  if ud.armorType then
    stats[#stats + 1] = "Armor: " .. (ud.armorType or "?")
  end
  if ud.speed and ud.speed > 0 then
    stats[#stats + 1] = "Spd: " .. string.format("%.1f", ud.speed / 30)
  end
  if ud.maxWeaponRange and ud.maxWeaponRange > 0 then
    stats[#stats + 1] = "Rng: " .. math.floor(ud.maxWeaponRange)
  end

  gl.Color(COL_STAT)
  for i, line in ipairs(stats) do
    gl.Text(line, textX, statY - (i - 1) * (STAT_FONT_SIZE + 2), STAT_FONT_SIZE, "o")
  end

  -- Building production queue (if applicable)
  if ud.isFactory or ud.isBuilder then
    drawProductionQueue(unitID, textX + 180, py, pw - (textX - px) - 180, ph)
  end
end

--------------------------------------------------------------------------------
-- Drawing: production queue (buildings)
--------------------------------------------------------------------------------

function drawProductionQueue(unitID, qx, qy, qw, qh)
  local cmds = getFactoryCommands(unitID, 12)
  if not cmds or #cmds == 0 then return end

  local slotSize = 32
  local pad = 4
  local col = 0
  local row = 0
  local maxCols = math.floor((qw - pad) / (slotSize + pad))
  if maxCols < 1 then maxCols = 1 end

  gl.Color(COL_PARCHMENT)
  gl.Text("Queue:", qx, qy + qh - 14, STAT_FONT_SIZE, "o")

  local startY = qy + qh - 14 - STAT_FONT_SIZE - pad

  for i, cmd in ipairs(cmds) do
    local cx = qx + col * (slotSize + pad)
    local cy = startY - row * (slotSize + pad)

    -- Slot background
    gl.Color(COL_QUEUE_BG)
    gl.Rect(cx, cy - slotSize, cx + slotSize, cy)

    -- Try to draw the queued unit portrait
    if cmd.id and cmd.id < 0 then
      local queuedDefID = -cmd.id
      local qud = UnitDefs and UnitDefs[queuedDefID]
      if qud and qud.name then
        local qPortrait = getPortraitPath(qud.name)
        if qPortrait then
          gl.Color(1, 1, 1, 1)
          gl.Texture(qPortrait)
          gl.TexRect(cx, cy - slotSize, cx + slotSize, cy)
          gl.Texture(false)
        end
      end
    end

    -- Queue count badge
    if cmd.params and cmd.params[1] then
      gl.Color(COL_SHADOW)
      gl.Text(tostring(cmd.params[1]), cx + slotSize - 2, cy - slotSize + 2, 10, "or")
      gl.Color(COL_PARCHMENT)
      gl.Text(tostring(cmd.params[1]), cx + slotSize - 3, cy - slotSize + 3, 10, "or")
    end

    -- Build progress bar on the first item
    if i == 1 then
      local buildProg = getUnitCurrentBuildPower(unitID)
      if buildProg and buildProg > 0 and buildProg < 1 then
        gl.Color(COL_QUEUE_BAR)
        gl.Rect(cx, cy - slotSize, cx + slotSize * buildProg, cy - slotSize + 3)
      end
    end

    col = col + 1
    if col >= maxCols then
      col = 0
      row = row + 1
    end
  end
end

--------------------------------------------------------------------------------
-- Drawing: multi-unit grid
--------------------------------------------------------------------------------

local function drawMultiSelect(units, px, py, pw, ph)
  local slotSize = MULTI_PORTRAIT
  local pad = 3
  local maxCols = math.floor((pw - PORTRAIT_PAD * 2) / (slotSize + pad))
  if maxCols < 1 then maxCols = 1 end
  local maxSlots = maxCols * MULTI_ROWS

  local drawCount = math.min(#units, maxSlots)
  local col = 0
  local row = 0

  for i = 1, drawCount do
    local uid = units[i]
    local udID = getUnitDefID(uid)
    if udID then
      local ud = UnitDefs and UnitDefs[udID]
      if ud then
        local sx = px + PORTRAIT_PAD + col * (slotSize + pad)
        local sy = py + ph - PORTRAIT_PAD - (row + 1) * (slotSize + pad)

        -- Slot background
        gl.Color(COL_DARK_BG)
        gl.Rect(sx, sy, sx + slotSize, sy + slotSize)

        -- Portrait
        local portrait = getPortraitPath(ud.name or "")
        if portrait then
          gl.Color(1, 1, 1, 1)
          gl.Texture(portrait)
          gl.TexRect(sx, sy, sx + slotSize, sy + slotSize)
          gl.Texture(false)
        end

        -- Mini health bar
        local health, maxHP = getUnitHealth(uid)
        if health and maxHP and maxHP > 0 then
          local frac = clamp(health / maxHP, 0, 1)
          local hc = healthColor(frac)
          gl.Color(0.10, 0.08, 0.06, 0.8)
          gl.Rect(sx, sy, sx + slotSize, sy + 3)
          gl.Color(hc)
          gl.Rect(sx, sy, sx + slotSize * frac, sy + 3)
        end

        -- Slot border
        gl.Color(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], 0.6)
        gl.Rect(sx, sy, sx + slotSize, sy + 1)
        gl.Rect(sx, sy + slotSize - 1, sx + slotSize, sy + slotSize)
        gl.Rect(sx, sy, sx + 1, sy + slotSize)
        gl.Rect(sx + slotSize - 1, sy, sx + slotSize, sy + slotSize)

        col = col + 1
        if col >= maxCols then
          col = 0
          row = row + 1
        end
      end
    end
  end

  -- "N units selected" label
  if #units > 1 then
    local label = tostring(#units) .. " units selected"
    local labelX = px + pw * 0.5
    local labelY = py + ph - 4
    gl.Color(COL_SHADOW)
    gl.Text(label, labelX + 1, labelY - 1, NAME_FONT_SIZE, "oc")
    gl.Color(COL_GOLD)
    gl.Text(label, labelX, labelY, NAME_FONT_SIZE, "oc")
  end
end

--------------------------------------------------------------------------------
-- Main draw
--------------------------------------------------------------------------------

local vsx, vsy = 0, 0

function widget:ViewResize(viewSizeX, viewSizeY)
  vsx = viewSizeX
  vsy = viewSizeY
end

function widget:Initialize()
  vsx, vsy = Spring.GetViewGeometry and Spring.GetViewGeometry() or 1920, 1080
end

function widget:DrawScreen()
  local selected = getSelectedUnits()
  if not selected or #selected == 0 then return end

  -- Panel geometry: centered at bottom, spanning most of the screen width
  local panelW = math.min(vsx * 0.7, 900)
  local panelH = PANEL_HEIGHT
  local panelX = (vsx - panelW) * 0.5
  local panelY = 0  -- bottom of screen

  -- Background texture (stretched bar_background.png)
  gl.Color(1, 1, 1, 0.95)
  gl.Texture(TEX_BACKGROUND)
  gl.TexRect(panelX, panelY, panelX + panelW, panelY + panelH)
  gl.Texture(false)

  -- Dark overlay for readability
  gl.Color(COL_DARK_BG[1], COL_DARK_BG[2], COL_DARK_BG[3], 0.60)
  gl.Rect(panelX, panelY, panelX + panelW, panelY + panelH)

  -- Ornamental 9-slice border
  drawNineSlice(TEX_BORDER, panelX - 2, panelY - 2, panelX + panelW + 2, panelY + panelH + 2, 10)

  -- Corner brackets
  drawCornerBrackets(panelX - 4, panelY - 4, panelX + panelW + 4, panelY + panelH + 4, 16)

  -- Content: single unit vs multi-select
  if #selected == 1 then
    drawSingleUnit(selected[1], panelX, panelY, panelW, panelH)
  else
    drawMultiSelect(selected, panelX, panelY, panelW, panelH)
  end
end
