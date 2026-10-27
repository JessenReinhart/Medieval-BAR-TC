-- Medieval Main Menu Widget — In-game menu overlay with skirmish launcher,
-- settings, and credits tabs. Driven by the pure policy module
-- scripts/medieval_main_menu.lua.
--
-- Pure unsynced widget. No synced GG access.
-- Gate on modoption "medievalmainmenu" (default on, defensive fallback).

function widget:GetInfo()
  return {
    name    = "Medieval Main Menu",
    desc    = "In-game medieval main menu and skirmish launcher (Escape to toggle)",
    author  = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer   = 1000,
    enabled = true,
  }
end

-- Mod option gate; defaults to ON when the option is absent (older modoptions).
local options = Spring.GetModOptions and Spring.GetModOptions() or {}
local optionValue = options.medievalmainmenu
if optionValue == false or optionValue == 0 or optionValue == "0" then return end

--------------------------------------------------------------------------------
-- Includes & state
--------------------------------------------------------------------------------

local menuPolicy = VFS.Include("scripts/medieval_main_menu.lua")

-- A launched match is recorded in the startscript modoptions as
-- medievalmatchlaunched=1. A fresh game boot (launch-game.ps1 or a bare
-- session) leaves it 0, which means the player is in the main menu and the
-- match has NOT started. In menu mode the menu is open and the simulation is
-- paused; the match only begins when the player launches it from the menu.
local matchLaunched = false
if (options.medievalmatchlaunched == "1")
  or (options.medievalmatchlaunched == 1)
  or (options.medievalmatchlaunched == true) then
  matchLaunched = true
end

local menuState = menuPolicy.newMenuState(not matchLaunched)

local function syncMenuVisibility()
  if WG then
    WG.medievalMainMenuOpen = menuState.isOpen
  end
  if Spring and Spring.SendCommands then
    if menuState.isOpen then
      Spring.SendCommands("minimap min 1")
    else
      Spring.SendCommands("minimap min 0")
    end
  end
end

local vsx, vsy = 1280, 720
if Spring.GetViewGeometry then
  vsx, vsy = Spring.GetViewGeometry()
end

local launchStatusMessage = nil
local launchStatusTimer = 0

-- Track hitboxes for interactive clicks: { x1, y1, x2, y2, onClick }
local clickTargets = {}

local function registerClick(x1, y1, x2, y2, onClick)
  table.insert(clickTargets, { x1 = x1, y1 = y1, x2 = x2, y2 = y2, onClick = onClick })
end

-- Launch the configured skirmish match. Marks the match as launched, closes the
-- menu, and either reloads the engine with the generated startscript (which
-- carries medievalmatchlaunched=1 so the fresh widget starts closed and
-- unpaused) or, if no reload API is available, unpauses the live session.
local function launchBattle()
  local valid, err = menuPolicy.validateConfig(menuState.skirmishConfig)
  if not valid then
    launchStatusMessage = "Config Error: " .. tostring(err)
    return
  end

  local scriptText = menuPolicy.generateStartscript(menuState.skirmishConfig)
  launchStatusMessage = "Launching Skirmish Match..."

  menuState.isOpen = false
  matchLaunched = true
  syncMenuVisibility()

  if Spring and Spring.Reload then
    pcall(function() Spring.Reload(scriptText) end)
  elseif Spring and Spring.SendCommands then
    Spring.SendCommands("pause 0")
  end
end

--------------------------------------------------------------------------------
-- Design tokens — dark iron war room, burnished bronze, wax-tinted ivory.
-- Contrast: ink 0.93 on plate 0.16 ≈ 8.4:1; muted 0.72 on plate ≈ 5.2:1.
--------------------------------------------------------------------------------

local COL_BG       = { 0.10, 0.09, 0.08, 0.96 }
local COL_PLATE    = { 0.16, 0.14, 0.12, 0.96 }
local COL_SURFACE  = { 0.20, 0.18, 0.15, 0.97 }
local COL_SURFACE2 = { 0.24, 0.21, 0.17, 0.98 }
local COL_HOVER    = { 0.30, 0.25, 0.18, 0.98 }
local COL_ACTIVE   = { 0.36, 0.28, 0.15, 0.98 }
local COL_HAIRLINE = { 0.34, 0.29, 0.22, 0.80 }
local COL_BRONZE   = { 0.72, 0.58, 0.28, 0.95 }
local COL_BRONZE2  = { 0.55, 0.44, 0.20, 0.85 }
local COL_GOLD     = { 0.94, 0.79, 0.36, 1.00 }
local COL_INK      = { 0.93, 0.90, 0.82, 1.00 }
local COL_MUTED    = { 0.74, 0.70, 0.61, 0.96 }
local COL_OK       = { 0.36, 0.72, 0.40, 1.00 }
local COL_RED      = { 0.82, 0.30, 0.25, 1.00 }

local FONT_HEADER  = 24
local FONT_TITLE   = 18
local FONT_BODY    = 13
local FONT_SMALL   = 11
local FONT_LABEL   = 10

--------------------------------------------------------------------------------
-- Drawing utilities & state-aware hitboxes
--------------------------------------------------------------------------------

local mouseX, mouseY = -1, -1

local function drawRect(x1, y1, x2, y2, c)
  if not gl or not gl.Rect then return end
  gl.Color(c[1], c[2], c[3], c[4])
  gl.Rect(x1, y1, x2, y2)
end

local function drawBorder(x1, y1, x2, y2, w, c)
  drawRect(x1, y1, x2, y1 + w, c)
  drawRect(x1, y2 - w, x2, y2, c)
  drawRect(x1, y1, x1 + w, y2, c)
  drawRect(x2 - w, y1, x2, y2, c)
end

local function drawText(text, x, y, size, options, c)
  if not gl or not gl.Text then return end
  gl.Color(c[1], c[2], c[3], c[4])
  gl.Text(text, x, y, size, options or "o")
end

local function isHovered(x1, y1, x2, y2)
  return mouseX >= x1 and mouseX <= x2 and mouseY >= y1 and mouseY <= y2
end

-- Hairline divider: a true 1px line, the structural joint between panes.
local function drawHairline(x1, y, x2, c)
  drawRect(x1, y, x2, y + 1, c)
end

-- Rounded-plate panel: one solid backing plate, one hairline, no ghost shadow.
local function drawPanel(x, y, w, h, c)
  drawRect(x, y, x + w, y + h, c)
  drawBorder(x, y, x + w, y + h, 1, COL_HAIRLINE)
end

-- Section marking: Roman numeral + small label. A deliberate sequence marker
-- that names a real ordered step, not decoration on every heading.
local function drawSectionMark(x, y, roman, label, c)
  drawText(roman, x, y, FONT_TITLE, "o", c)
  drawText(label, x + 36, y + 1, FONT_LABEL, "o", COL_MUTED)
end

-- Primary action plate with title + subtitle; hover lifts the plate, active
-- surface uses gold for the launch trigger.
local function drawActionCard(x, y, w, h, title, subtitle, isPrimary, onClick)
  registerClick(x, y, x + w, y + h, onClick)
  local base = isPrimary and COL_ACTIVE or COL_SURFACE
  if isHovered(x, y, x + w, y + h) then
    base = isPrimary and COL_HOVER or COL_SURFACE2
  end
  drawRect(x, y, x + w, y + h, base)
  drawBorder(x, y, x + w, y + h, 1, isPrimary and COL_GOLD or COL_HAIRLINE)
  drawText(title, x + 16, y + h - 22, 14, "o", COL_INK)
  drawText(subtitle, x + 16, y + 12, FONT_SMALL, "o", COL_MUTED)
  drawText("›", x + w - 26, y + (h * 0.5) - 6, 18, "oc", COL_GOLD)
end

-- Segmented control: options laid out in a single row; selected fill uses
-- gold surface + ink text for 4.5:1 contrast.
local function drawSegment(x, y, w, h, options, selectedKey, onSelect)
  local n = #options
  local segW = (w + n - 1) / n
  drawRect(x, y, x + w, y + h, COL_PLATE)
  drawBorder(x, y, x + w, y + h, 1, COL_HAIRLINE)
  for i, opt in ipairs(options) do
    local sx = x + (i - 1) * segW
    local selected = (opt.key == selectedKey)
    local cx = sx + segW
    registerClick(sx, y, cx, y + h, function()
      if onSelect then onSelect(opt.key) end
    end)
    if selected then
      drawRect(sx, y, cx, y + h, COL_ACTIVE)
      drawText(opt.label, sx + segW * 0.5, y + (h * 0.5) - 6, 13, "c", COL_INK)
    else
      if isHovered(sx, y, cx, y + h) then
        drawRect(sx, y, cx, y + h, COL_HOVER)
      end
      drawText(opt.label, sx + segW * 0.5, y + (h * 0.5) - 6, 13, "c", COL_MUTED)
    end
    if i < n then drawHairline(cx, y, y + h, COL_HAIRLINE) end
  end
end

-- Check toggle with a clear state: gold box + ink check when on.
local function drawToggle(x, y, w, h, label, sublabel, isOn, onToggle)
  registerClick(x, y, x + w, y + h, onToggle)
  local box = 20
  local boxX = x
  local boxY = y + (h - box) * 0.5
  if isOn then
    drawRect(boxX, boxY, boxX + box, boxY + box, COL_GOLD)
    drawText("✓", boxX + box * 0.5, boxY + box * 0.5 - 6, 13, "c", {
      0.10, 0.09, 0.08, 1.0 })
  else
    drawBorder(boxX, boxY, boxX + box, boxY + box, 1, COL_HAIRLINE)
  end
  drawText(label, x + box + 12, y + h - 12, 13, "o", COL_INK)
  if sublabel then
    drawText(sublabel, x + box + 12, y + 8, FONT_SMALL, "o", COL_MUTED)
  end
end

-- Generic gold label button; visible hover and pressed tactile shifts.
local function drawButton(x, y, w, h, label, isHighlighted, onClick)
  registerClick(x, y, x + w, y + h, onClick)
  local base = isHighlighted and COL_ACTIVE or COL_SURFACE
  local border = isHighlighted and COL_GOLD or COL_HAIRLINE
  if isHovered(x, y, x + w, y + h) then
    base = isHighlighted and COL_HOVER or COL_SURFACE2
  end
  drawRect(x, y, x + w, y + h, base)
  drawBorder(x, y, x + w, y + h, 1, border)
  drawText(label, x + w * 0.5, y + (h * 0.5) - 6, 13, "c",
    isHighlighted and COL_INK or COL_MUTED)
end

--------------------------------------------------------------------------------
-- Tab & Header rendering
--------------------------------------------------------------------------------

local TAB_NAMES = { "MAIN", "SKIRMISH", "SETTINGS", "CREDITS" }
local TAB_ROMANS = { "I", "II", "III", "IV" }

local function drawBackgroundAndHeader()
  -- Deep iron slate field
  drawRect(0, 0, vsx, vsy, COL_BG)

  -- Ornate bronze frame: dark inner plate, hairline, gold corner fillets.
  local m = 18
  drawBorder(m, m, vsx - m, vsy - m, 2, COL_BRONZE2)
  drawBorder(m + 5, m + 5, vsx - m - 5, vsy - m - 5, 1, COL_HAIRLINE)

  -- Corner heraldic marks (small filled squares at the four corners).
  local fil = 7
  local c = COL_GOLD
  drawRect(m - 4, vsy - m - fil + 4, m - 4 + fil, vsy - m + 4, c)
  drawRect(vsx - m - fil + 4, vsy - m - fil + 4, vsx - m + 4, vsy - m + 4, c)
  drawRect(m - 4, m - 4, m - 4 + fil, m - 4 + fil, c)
  drawRect(vsx - m - fil + 4, m - 4, vsx - m + 4, m - 4 + fil, c)

  -- Title block
  drawText("MEDIEVAL: TOTAL CONVERSION", vsx * 0.5, vsy - 62, FONT_HEADER, "oc", COL_GOLD)
  drawText("HISTORICAL REAL-TIME STRATEGY", vsx * 0.5, vsy - 86, FONT_SMALL, "oc", COL_MUTED)

  -- Navigation tabs: Roman numeral sequence left, name right; active tab gets
  -- a gold underline bar beneath it.
  local tabW = 150
  local tabH = 34
  local totalTabsW = #TAB_NAMES * tabW
  local startX = (vsx - totalTabsW) * 0.5
  local tabY = vsy - 132

  for i, tab in ipairs(TAB_NAMES) do
    local tx = startX + (i - 1) * tabW
    local isActive = (menuState.activeTab == tab)
    registerClick(tx, tabY, tx + tabW, tabY + tabH, function()
      menuPolicy.setTab(menuState, tab)
    end)

    if isHovered(tx, tabY, tx + tabW, tabY + tabH) or isActive then
      drawRect(tx, tabY, tx + tabW, tabY + tabH, COL_SURFACE2)
    end
    drawText(TAB_ROMANS[i], tx + 18, tabY + 10, FONT_BODY, "o",
      isActive and COL_GOLD or COL_MUTED)
    drawText(tab, tx + 44, tabY + 10, FONT_BODY, "o",
      isActive and COL_INK or COL_MUTED)

    if isActive then
      drawRect(tx + 18, tabY + tabH + 2, tx + tabW - 18, tabY + tabH + 4, COL_GOLD)
    end
  end

  -- Hairline joint under the tab bar
  drawHairline(m + 10, tabY + tabH + 9, vsx - m - 10, COL_HAIRLINE)
end

--------------------------------------------------------------------------------
-- View: MAIN Tab (War Chamber split layout)
--------------------------------------------------------------------------------

local function drawMainView()
  local paneW = 440
  local sideW = 380
  local gap = 24
  local totalW = paneW + sideW + gap
  local leftX = (vsx - totalW) * 0.5
  local rightX = leftX + paneW + gap
  local startY = vsy - 200

  -- Left Pane: War Chamber Actions
  drawSectionMark(leftX, startY + 28, "⚜", "ROYAL WAR CHAMBER", COL_GOLD)
  drawText("Assemble your commanders, review the terms of engagement, and take the field.",
    leftX, startY + 6, FONT_SMALL, "o", COL_MUTED)

  local curY = startY - 24

  if not matchLaunched then
    drawActionCard(leftX, curY - 54, paneW, 54, "START MATCH",
      "Deploy immediately with default skirmish settings", true, function()
        launchBattle()
      end)
    curY = curY - 64

    drawActionCard(leftX, curY - 50, paneW, 50, "CUSTOM SKIRMISH",
      "Configure battlefield, alliances, and victory terms", false, function()
        menuPolicy.setTab(menuState, "SKIRMISH")
      end)
    curY = curY - 60
  else
    drawActionCard(leftX, curY - 54, paneW, 54, "RESUME MATCH",
      "Return to the active battlefield", true, function()
        menuPolicy.toggleOpen(menuState)
        syncMenuVisibility()
      end)
    curY = curY - 64

    drawActionCard(leftX, curY - 50, paneW, 50, "NEW SKIRMISH",
      "Configure and launch a fresh battle", false, function()
        menuPolicy.setTab(menuState, "SKIRMISH")
      end)
    curY = curY - 60
  end

  drawActionCard(leftX, curY - 48, paneW, 48, "GAME SETTINGS",
    "Audio levels, display resolution, and fidelity", false, function()
      menuPolicy.setTab(menuState, "SETTINGS")
    end)
  curY = curY - 56

  drawActionCard(leftX, curY - 48, paneW, 48, "CREDITS & LICENSES",
    "Attribution for code, music, and converted 0 A.D. assets", false, function()
      menuPolicy.setTab(menuState, "CREDITS")
    end)
  curY = curY - 56

  drawActionCard(leftX, curY - 44, paneW, 44, "EXIT TO DESKTOP",
    "Quit the application immediately", false, function()
      if Spring.SendCommands then Spring.SendCommands("quitforce") end
    end)

  -- Right Pane: Active Engagement Overview
  local cfg = menuState.skirmishConfig
  local cardH = 340
  local cardY = startY - cardH + 20
  drawPanel(rightX, cardY, sideW, cardH, COL_PLATE)

  drawText("ENGAGEMENT PROFILE", rightX + 20, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(rightX + 20, cardY + cardH - 36, rightX + sideW - 20, COL_HAIRLINE)

  local rowY = cardY + cardH - 64
  local function drawSpecRow(label, val)
    drawText(label, rightX + 22, rowY, FONT_SMALL, "o", COL_MUTED)
    drawText(tostring(val), rightX + sideW - 22, rowY, FONT_BODY, "ro", COL_INK)
    rowY = rowY - 26
  end

  drawSpecRow("Battlefield", cfg.mapName or "Quicksilver Remake 1.24")
  drawSpecRow("Commanders", (cfg.numTeams or 2) .. " Teams (" .. (cfg.numAI or 1) .. " AI)")
  drawSpecRow("Victory Terms", cfg.victoryMode or "tc_destruction")
  drawSpecRow("AI Discipline", cfg.aiDifficulty or "Medium")
  drawSpecRow("Resource Density", cfg.proceduralDensity or "normal")
  drawSpecRow("Tactics & Bracing", cfg.tactics and "Enabled" or "Disabled")

  drawHairline(rightX + 20, rowY - 6, rightX + sideW - 20, COL_HAIRLINE)
  rowY = rowY - 28

  -- Status badge
  local badgeH = 38
  local badgeY = cardY + 68
  drawRect(rightX + 20, badgeY, rightX + sideW - 20, badgeY + badgeH, COL_SURFACE2)
  drawBorder(rightX + 20, badgeY, rightX + sideW - 20, badgeY + badgeH, 1, COL_HAIRLINE)

  local dotX = rightX + 34
  local dotY = badgeY + badgeH * 0.5
  drawRect(dotX - 4, dotY - 4, dotX + 4, dotY + 4, matchLaunched and COL_GOLD or COL_OK)
  drawText(matchLaunched and "MATCH IN PROGRESS" or "SIMULATION PAUSED",
    rightX + 48, badgeY + 12, FONT_SMALL, "o", COL_INK)

  -- Quick Action Button inside Right Pane
  if not matchLaunched then
    drawButton(rightX + 20, cardY + 18, sideW - 40, 38, "DEPLOY TO FIELD", true, function()
      launchBattle()
    end)
  else
    drawButton(rightX + 20, cardY + 18, sideW - 40, 38, "RETURN TO FIELD", true, function()
      menuPolicy.toggleOpen(menuState)
      syncMenuVisibility()
    end)
  end

  -- Engine footer
  drawText("Recoil Engine 2026.07.04 — Medieval-BAR-TC Total Conversion (GPL v2 / CC-BY-SA 3.0)",
    vsx * 0.5, 36, FONT_LABEL, "c", COL_MUTED)
end

--------------------------------------------------------------------------------
-- View: SKIRMISH Tab (3-card split layout)
--------------------------------------------------------------------------------

local function drawSkirmishView()
  local cfg = menuState.skirmishConfig
  local cardW = math.min(380, (vsx - 100) / 3)
  local totalW = cardW * 3 + 40
  local startX = (vsx - totalW) * 0.5
  local col1X = startX
  local col2X = col1X + cardW + 20
  local col3X = col2X + cardW + 20
  local cardH = 430
  local cardY = vsy - 180 - cardH

  -- Card 1: Battlefield & Map
  drawPanel(col1X, cardY, cardW, cardH, COL_PLATE)
  drawText("I · BATTLEFIELD", col1X + 18, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(col1X + 18, cardY + cardH - 36, col1X + cardW - 18, COL_HAIRLINE)

  local curY = cardY + cardH - 60
  drawText("Select Map", col1X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 24

  local isQuick = (cfg.mapName == "Quicksilver Remake 1.24")
  registerClick(col1X + 18, curY - 42, col1X + cardW - 18, curY, function()
    menuPolicy.updateSkirmishOption(menuState, "mapName", "Quicksilver Remake 1.24")
    menuPolicy.updateSkirmishOption(menuState, "proceduralMap", false)
  end)
  drawRect(col1X + 18, curY - 42, col1X + cardW - 18, curY, isQuick and COL_ACTIVE or COL_SURFACE)
  drawBorder(col1X + 18, curY - 42, col1X + cardW - 18, curY, 1, isQuick and COL_GOLD or COL_HAIRLINE)
  drawText("Quicksilver Remake 1.24", col1X + 28, curY - 20, 13, "o", COL_INK)
  drawText("Flat valley lane · Verified start positions", col1X + 28, curY - 34, FONT_LABEL, "o", COL_MUTED)
  curY = curY - 52

  local isProc = not isQuick
  registerClick(col1X + 18, curY - 42, col1X + cardW - 18, curY, function()
    menuPolicy.updateSkirmishOption(menuState, "mapName", "Procedural Random Map")
    menuPolicy.updateSkirmishOption(menuState, "proceduralMap", true)
  end)
  drawRect(col1X + 18, curY - 42, col1X + cardW - 18, curY, isProc and COL_ACTIVE or COL_SURFACE)
  drawBorder(col1X + 18, curY - 42, col1X + cardW - 18, curY, 1, isProc and COL_GOLD or COL_HAIRLINE)
  drawText("Procedural Random Map", col1X + 28, curY - 20, 13, "o", COL_INK)
  drawText("Fair resource nodes · Variable wilderness", col1X + 28, curY - 34, FONT_LABEL, "o", COL_MUTED)
  curY = curY - 60

  drawText("Resource Density", col1X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 32
  local densityOpts = {
    { key = "sparse", label = "Sparse" },
    { key = "normal", label = "Normal" },
    { key = "dense",  label = "Dense" },
  }
  drawSegment(col1X + 18, curY, cardW - 36, 28, densityOpts, cfg.density or "normal", function(k)
    menuPolicy.updateSkirmishOption(menuState, "density", k)
  end)
  curY = curY - 50

  drawText("Starting Settlements", col1X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 20
  drawText("East/West plain lanes with town center & 3 villagers.", col1X + 20, curY, FONT_SMALL, "o", COL_INK)

  -- Card 2: Forces & Victory Terms
  drawPanel(col2X, cardY, cardW, cardH, COL_PLATE)
  drawText("II · FORCES & VICTORY", col2X + 18, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(col2X + 18, cardY + cardH - 36, col2X + cardW - 18, COL_HAIRLINE)

  curY = cardY + cardH - 60
  drawText("Victory Terms", col2X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 32

  local victoryOpts = {
    { key = "tc_destruction", label = "TC Fall" },
    { key = "conquest",       label = "Conquest" },
    { key = "regicide",       label = "Regicide" },
  }
  drawSegment(col2X + 18, curY, cardW - 36, 28, victoryOpts, cfg.victoryMode or "tc_destruction", function(k)
    menuPolicy.updateSkirmishOption(menuState, "victoryMode", k)
  end)
  curY = curY - 48

  drawText("Battle Format", col2X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 32
  local teamOpts = {
    { key = 2, label = "1v1 (2 Teams)" },
    { key = 3, label = "3 Teams" },
    { key = 4, label = "4 Teams" },
  }
  drawSegment(col2X + 18, curY, cardW - 36, 28, teamOpts, cfg.numTeams or 2, function(k)
    menuPolicy.updateSkirmishOption(menuState, "numTeams", k)
    menuPolicy.updateSkirmishOption(menuState, "numAI", k - 1)
  end)
  curY = curY - 48

  drawText("Opponent Commander", col2X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 32
  local aiTypeOpts = {
    { key = "SkirmishAI", label = "Skirmish AI" },
    { key = "NullAI",     label = "Passive (Sandbox)" },
  }
  drawSegment(col2X + 18, curY, cardW - 36, 28, aiTypeOpts, cfg.aiType or "SkirmishAI", function(k)
    menuPolicy.updateSkirmishOption(menuState, "aiType", k)
  end)
  curY = curY - 48

  drawText("AI Discipline & Agility", col2X + 20, curY, FONT_SMALL, "o", COL_MUTED)
  curY = curY - 32
  local diffOpts = {
    { key = "Easy",   label = "Easy" },
    { key = "Medium", label = "Medium" },
    { key = "Hard",   label = "Hard" },
  }
  drawSegment(col2X + 18, curY, cardW - 36, 28, diffOpts, cfg.aiDifficulty or "Medium", function(k)
    menuPolicy.updateSkirmishOption(menuState, "aiDifficulty", k)
  end)

  -- Card 3: Mod Subsystems
  drawPanel(col3X, cardY, cardW, cardH, COL_PLATE)
  drawText("III · SUBSYSTEMS", col3X + 18, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(col3X + 18, cardY + cardH - 36, col3X + cardW - 18, COL_HAIRLINE)

  curY = cardY + cardH - 60
  local toggles = {
    { key = "medievaltactics",  label = "Tactics & Bracing",      sub = "Charges, bracing, and flanking pipeline" },
    { key = "medievalmarket",   label = "Marketplace Barter",     sub = "Commodity pricing and barter exchange" },
    { key = "medievalgarrison", label = "TC Garrison & Healing",  sub = "Shelter villagers & passive regeneration" },
    { key = "medievalmapgen",   label = "Procedural Map Gen",     sub = "Dynamic resource cluster generation" },
  }

  for _, t in ipairs(toggles) do
    local isChecked = (cfg[t.key] ~= false)
    drawToggle(col3X + 18, curY - 38, cardW - 36, 38, t.label, t.sub, isChecked, function()
      menuPolicy.updateSkirmishOption(menuState, t.key, not isChecked)
    end)
    curY = curY - 50
  end

  -- Bottom Action Row
  local btmY = 48
  drawButton(col1X, btmY, 180, 42, "< BACK TO MAIN", false, function()
    menuPolicy.setTab(menuState, "MAIN")
  end)

  local launchW = 260
  local launchX = col3X + cardW - launchW
  drawButton(launchX, btmY, launchW, 42, "LAUNCH BATTLE", true, function()
    launchBattle()
  end)

  if launchStatusMessage then
    drawText(launchStatusMessage, vsx * 0.5, btmY + 54, FONT_BODY, "c", COL_GOLD)
  end
end

--------------------------------------------------------------------------------
-- View: SETTINGS Tab
--------------------------------------------------------------------------------

local function drawSettingsView()
  local cfg = menuState.settingsConfig
  local cardW = math.min(500, vsx - 80)
  local cardH = 430
  local startX = (vsx - cardW) * 0.5
  local cardY = vsy - 180 - cardH

  drawPanel(startX, cardY, cardW, cardH, COL_PLATE)
  drawText("AUDIO & GRAPHICS PREFERENCES", startX + 24, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(startX + 24, cardY + cardH - 36, startX + cardW - 24, COL_HAIRLINE)

  local curY = cardY + cardH - 64
  local volumeSettings = {
    { key = "masterVolume", label = "Master Volume" },
    { key = "musicVolume",  label = "Music Volume" },
    { key = "sfxVolume",    label = "Sound Effects" },
  }

  for _, s in ipairs(volumeSettings) do
    local val = cfg[s.key] or 80
    drawText(s.label, startX + 26, curY + 6, FONT_BODY, "o", COL_INK)

    drawButton(startX + cardW - 170, curY, 34, 28, "-", false, function()
      menuPolicy.updateSetting(menuState, s.key, val - 10)
    end)

    drawText(tostring(val) .. "%", startX + cardW - 105, curY + 6, FONT_BODY, "c", COL_GOLD)

    drawButton(startX + cardW - 60, curY, 34, 28, "+", false, function()
      menuPolicy.updateSetting(menuState, s.key, val + 10)
    end)
    curY = curY - 44
  end

  drawHairline(startX + 24, curY - 6, startX + cardW - 24, COL_HAIRLINE)
  curY = curY - 32

  -- Water quality
  drawText("Water Quality", startX + 26, curY + 6, FONT_BODY, "o", COL_INK)
  local qOpts = {
    { key = "Low",    label = "Low" },
    { key = "Medium", label = "Med" },
    { key = "High",   label = "High" },
    { key = "Ultra",  label = "Ultra" },
  }
  drawSegment(startX + cardW - 220, curY, 196, 28, qOpts, cfg.waterQuality or "High", function(k)
    menuPolicy.updateSetting(menuState, "waterQuality", k)
  end)
  curY = curY - 44

  -- Shadows
  drawText("Shadow Fidelity", startX + 26, curY + 6, FONT_BODY, "o", COL_INK)
  drawSegment(startX + cardW - 220, curY, 196, 28, qOpts, cfg.shadows or "High", function(k)
    menuPolicy.updateSetting(menuState, "shadows", k)
  end)
  curY = curY - 44

  -- Fullscreen
  drawText("Display Mode", startX + 26, curY + 6, FONT_BODY, "o", COL_INK)
  local fsOpts = {
    { key = true,  label = "Fullscreen" },
    { key = false, label = "Windowed" },
  }
  drawSegment(startX + cardW - 220, curY, 196, 28, fsOpts, cfg.fullscreen, function(k)
    menuPolicy.updateSetting(menuState, "fullscreen", k)
  end)

  -- Back button
  local btmY = 48
  drawButton((vsx - 200) * 0.5, btmY, 200, 42, "< BACK TO MAIN", false, function()
    menuPolicy.setTab(menuState, "MAIN")
  end)
end

--------------------------------------------------------------------------------
-- View: CREDITS Tab
--------------------------------------------------------------------------------

local function drawCreditsView()
  local cardW = math.min(820, vsx - 80)
  local cardH = 430
  local startX = (vsx - cardW) * 0.5
  local cardY = vsy - 180 - cardH

  drawPanel(startX, cardY, cardW, cardH, COL_PLATE)
  drawText("PROJECT CREDITS & LICENSING", startX + 24, cardY + cardH - 28, 14, "o", COL_GOLD)
  drawHairline(startX + 24, cardY + cardH - 36, startX + cardW - 24, COL_HAIRLINE)

  local curY = cardY + cardH - 62
  local textLines = {
    "MEDIEVAL-BAR-TC: TOTAL CONVERSION RTS",
    "",
    "A standalone historical medieval real-time strategy total conversion built for",
    "the Recoil engine (formerly Spring RTS).",
    "",
    "CREDITS & SOURCES:",
    "  • Core Design & Systems: Medieval-BAR-TC Contributors (GPL-v2)",
    "  • Historical Models, Textures & Audio: 0 A.D. (Wildfire Games) — CC-BY-SA 3.0",
    "  • Recoil Engine: Recoil Engine Contributors (GPL-v2)",
    "  • Medieval Audio & Ambience: OpenGameArt.org contributors (CC0 & CC-BY 3.0)",
    "",
    "LICENSING SUMMARY:",
    "  • Mod Code & Scripts: GNU General Public License v2 (GPL-v2)",
    "  • Art Assets: Creative Commons Attribution-ShareAlike 3.0 (CC-BY-SA 3.0)",
    "  • Zero proprietary or non-commercial restricted assets are included.",
  }

  for _, line in ipairs(textLines) do
    if string.find(line, ":") then
      drawText(line, startX + 26, curY, FONT_BODY, "o", COL_GOLD)
    else
      drawText(line, startX + 26, curY, FONT_SMALL, "o", COL_INK)
    end
    curY = curY - 20
  end

  local btmY = 48
  drawButton((vsx - 200) * 0.5, btmY, 200, 42, "< BACK TO MAIN", false, function()
    menuPolicy.setTab(menuState, "MAIN")
  end)
end

--------------------------------------------------------------------------------
-- Callins
--------------------------------------------------------------------------------

function widget:Initialize()
  syncMenuVisibility()
  -- If opening into the main menu without a launched match, pause simulation
  -- so the match never runs automatically in the background.
  if not matchLaunched and Spring and Spring.SendCommands then
    Spring.SendCommands("pause 1")
  end
end

function widget:Shutdown()
  -- Restore engine minimap and clear global flag on widget removal
  if WG then
    WG.medievalMainMenuOpen = false
  end
  if Spring and Spring.SendCommands then
    Spring.SendCommands("minimap min 0")
  end
end

function widget:ViewResize(newX, newY)
  vsx, vsy = newX, newY
end

function widget:MouseMove(mx, my, dx, dy)
  mouseX, mouseY = mx, my
end

function widget:DrawScreen()
  if not menuState.isOpen then return end
  clickTargets = {}

  drawBackgroundAndHeader()

  local tab = menuState.activeTab
  if tab == "MAIN" then
    drawMainView()
  elseif tab == "SKIRMISH" then
    drawSkirmishView()
  elseif tab == "SETTINGS" then
    drawSettingsView()
  elseif tab == "CREDITS" then
    drawCreditsView()
  end
end

function widget:KeyPress(key, mods, isRepeat, label, unicode)
  -- Escape (key code 27) toggles the menu ONLY when a match is active.
  -- Before the match is launched, Escape remains in the menu (switches back to MAIN tab).
  if key == 27 then
    if matchLaunched then
      menuPolicy.toggleOpen(menuState)
      syncMenuVisibility()
    else
      menuPolicy.setTab(menuState, "MAIN")
    end
    return true
  end

  -- When the menu is open, swallow keys to prevent game controls beneath
  if menuState.isOpen then
    return true
  end

  return false
end

function widget:MousePress(mx, my, button)
  if not menuState.isOpen then return false end

  -- Test clicks from back to front
  for i = #clickTargets, 1, -1 do
    local t = clickTargets[i]
    if mx >= t.x1 and mx <= t.x2 and my >= t.y1 and my <= t.y2 then
      if t.onClick then
        t.onClick()
      end
      return true
    end
  end

  return true -- swallow click so game beneath doesn't receive it
end
