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
-- Drawing utilities (Bronze/Wood medieval theme)
--------------------------------------------------------------------------------

local function drawRect(x1, y1, x2, y2, r, g, b, a)
  if not gl or not gl.Rect then return end
  gl.Color(r, g, b, a or 1.0)
  gl.Rect(x1, y1, x2, y2)
end

local function drawBorder(x1, y1, x2, y2, w, r, g, b, a)
  drawRect(x1, y1, x2, y1 + w, r, g, b, a)
  drawRect(x1, y2 - w, x2, y2, r, g, b, a)
  drawRect(x1, y1, x1 + w, y2, r, g, b, a)
  drawRect(x2 - w, y1, x2, y2, r, g, b, a)
end

local function drawText(text, x, y, size, options)
  if not gl or not gl.Text then return end
  gl.Text(text, x, y, size, options or "o")
end

local function drawButton(x, y, w, h, label, isHighlighted, onClick)
  registerClick(x, y, x + w, y + h, onClick)
  if isHighlighted then
    drawRect(x, y, x + w, y + h, 0.28, 0.22, 0.12, 0.95)
    drawBorder(x, y, x + w, y + h, 2, 0.90, 0.75, 0.30, 1.0)
    gl.Color(1.0, 0.92, 0.65, 1.0)
  else
    drawRect(x, y, x + w, y + h, 0.16, 0.13, 0.10, 0.90)
    drawBorder(x, y, x + w, y + h, 1, 0.55, 0.45, 0.25, 0.8)
    gl.Color(0.85, 0.80, 0.70, 1.0)
  end
  drawText(label, x + w * 0.5, y + (h * 0.5) - 6, 14, "c")
end

--------------------------------------------------------------------------------
-- Tab & Header rendering
--------------------------------------------------------------------------------

local function drawBackgroundAndHeader()
  -- Fullscreen dark parchment overlay
  drawRect(0, 0, vsx, vsy, 0.06, 0.05, 0.04, 0.94)

  -- Ornate bronze border frame (24px margin)
  local m = 24
  drawBorder(m, m, vsx - m, vsy - m, 2, 0.70, 0.55, 0.25, 0.9)
  drawBorder(m + 4, m + 4, vsx - m - 4, vsy - m - 4, 1, 0.40, 0.32, 0.15, 0.7)

  -- Top Title Banner
  gl.Color(0.95, 0.82, 0.40, 1.0)
  drawText("MEDIEVAL: TOTAL CONVERSION", vsx * 0.5, vsy - 65, 24, "oc")
  gl.Color(0.70, 0.65, 0.55, 0.9)
  drawText("HISTORICAL REAL-TIME STRATEGY", vsx * 0.5, vsy - 88, 12, "oc")

  -- Navigation Tabs
  local tabs = { "MAIN", "SKIRMISH", "SETTINGS", "CREDITS" }
  local tabW = 130
  local tabH = 32
  local totalTabsW = #tabs * tabW
  local startX = (vsx - totalTabsW) * 0.5
  local tabY = vsy - 130

  for i, tab in ipairs(tabs) do
    local tx = startX + (i - 1) * tabW
    local isActive = (menuState.activeTab == tab)
    drawButton(tx + 4, tabY, tabW - 8, tabH, tab, isActive, function()
      menuPolicy.setTab(menuState, tab)
    end)
  end

  -- Horizontal bronze divider under tabs
  drawRect(m + 10, tabY - 10, vsx - m - 10, tabY - 8, 0.55, 0.45, 0.25, 0.8)
end

--------------------------------------------------------------------------------
-- View: MAIN Tab
--------------------------------------------------------------------------------

local function drawMainView()
  local btnW = 260
  local btnH = 44
  local btnX = (vsx - btnW) * 0.5
  local startY = vsy * 0.5 + 60

  if not matchLaunched then
    -- Flow: initial game boot arrives directly at the main menu.
    -- The player can start a match immediately or customize their skirmish.
    drawButton(btnX, startY, btnW, btnH, "START MATCH", true, function()
      launchBattle()
    end)

    drawButton(btnX, startY - 56, btnW, btnH, "CUSTOM SKIRMISH", false, function()
      menuPolicy.setTab(menuState, "SKIRMISH")
    end)
  else
    -- Match already active in background: Resume is the primary action.
    drawButton(btnX, startY, btnW, btnH, "RESUME MATCH", true, function()
      menuPolicy.toggleOpen(menuState)
      syncMenuVisibility()
    end)

    drawButton(btnX, startY - 56, btnW, btnH, "NEW SKIRMISH", false, function()
      menuPolicy.setTab(menuState, "SKIRMISH")
    end)
  end

  drawButton(btnX, startY - 112, btnW, btnH, "GAME SETTINGS", false, function()
    menuPolicy.setTab(menuState, "SETTINGS")
  end)

  drawButton(btnX, startY - 168, btnW, btnH, "CREDITS & LICENSES", false, function()
    menuPolicy.setTab(menuState, "CREDITS")
  end)

  drawButton(btnX, startY - 224, btnW, btnH, "EXIT TO DESKTOP", false, function()
    if Spring.SendCommands then
      Spring.SendCommands("quitforce")
    end
  end)

  gl.Color(0.50, 0.48, 0.42, 0.7)
  drawText("Recoil Engine 2026.07.04 — Age of Empires / 0 A.D. Total Conversion", vsx * 0.5, 45, 11, "c")
end

--------------------------------------------------------------------------------
-- View: SKIRMISH Tab
--------------------------------------------------------------------------------

local function drawSkirmishView()
  local cfg = menuState.skirmishConfig
  local contentY = vsy - 170

  -- 3 Columns layout
  local colW = (vsx - 120) / 3
  local col1X = 60
  local col2X = col1X + colW + 20
  local col3X = col2X + colW + 20

  -- Column 1: Match & Map Settings
  gl.Color(0.90, 0.80, 0.45, 1.0)
  drawText("MAP & SCENARIO", col1X, contentY, 15, "o")
  drawRect(col1X, contentY - 6, col1X + colW, contentY - 4, 0.5, 0.4, 0.2, 0.7)

  -- Map selector
  local rowY = contentY - 35
  gl.Color(0.8, 0.8, 0.8, 1)
  drawText("Map:", col1X, rowY + 6, 12, "o")
  local currentMap = cfg.mapName or "Quicksilver Remake 1.24"
  drawButton(col1X + 80, rowY, colW - 85, 26, currentMap, false, function()
    if cfg.mapName == "Quicksilver Remake 1.24" then
      menuPolicy.updateSkirmishOption(menuState, "mapName", "Procedural Random Map")
      menuPolicy.updateSkirmishOption(menuState, "proceduralMap", true)
    else
      menuPolicy.updateSkirmishOption(menuState, "mapName", "Quicksilver Remake 1.24")
      menuPolicy.updateSkirmishOption(menuState, "proceduralMap", false)
    end
  end)

  -- Victory Mode
  rowY = rowY - 40
  drawText("Victory:", col1X, rowY + 6, 12, "o")
  local vMode = cfg.victoryMode or "tc_destruction"
  local vLabel = (vMode == "tc_destruction" and "TC Destruction") or (vMode == "conquest" and "Conquest") or (vMode == "regicide" and "Regicide") or "Time Limit"
  drawButton(col1X + 80, rowY, colW - 85, 26, vLabel, false, function()
    local modes = { "tc_destruction", "conquest", "regicide", "time_limit" }
    for i, m in ipairs(modes) do
      if m == vMode then
        local nextM = modes[(i % #modes) + 1]
        menuPolicy.updateSkirmishOption(menuState, "victoryMode", nextM)
        break
      end
    end
  end)

  -- Procedural Generation Density
  rowY = rowY - 40
  drawText("Density:", col1X, rowY + 6, 12, "o")
  local density = cfg.density or "normal"
  drawButton(col1X + 80, rowY, colW - 85, 26, string.upper(density), false, function()
    local densities = { "sparse", "normal", "dense" }
    for i, d in ipairs(densities) do
      if d == density then
        local nextD = densities[(i % #densities) + 1]
        menuPolicy.updateSkirmishOption(menuState, "density", nextD)
        break
      end
    end
  end)

  -- Column 2: Players & AI Setup
  gl.Color(0.90, 0.80, 0.45, 1.0)
  drawText("PLAYERS & AI SETUP", col2X, contentY, 15, "o")
  drawRect(col2X, contentY - 6, col2X + colW, contentY - 4, 0.5, 0.4, 0.2, 0.7)

  -- Teams Count
  rowY = contentY - 35
  drawText("Teams:", col2X, rowY + 6, 12, "o")
  local numTeams = cfg.numTeams or 2
  drawButton(col2X + 80, rowY, 32, 26, "-", false, function()
    if numTeams > 2 then
      menuPolicy.updateSkirmishOption(menuState, "numTeams", numTeams - 1)
      menuPolicy.updateSkirmishOption(menuState, "numAI", numTeams - 2)
    end
  end)
  gl.Color(1, 1, 1, 1)
  drawText(tostring(numTeams) .. " Teams", col2X + 130, rowY + 6, 12, "o")
  drawButton(col2X + 195, rowY, 32, 26, "+", false, function()
    if numTeams < 4 then
      menuPolicy.updateSkirmishOption(menuState, "numTeams", numTeams + 1)
      menuPolicy.updateSkirmishOption(menuState, "numAI", numTeams)
    end
  end)

  -- Opponent AI Type
  rowY = rowY - 40
  drawText("Bot AI:", col2X, rowY + 6, 12, "o")
  local aiType = cfg.aiType or "SkirmishAI"
  local aiLabel = (aiType == "SkirmishAI" and "Skirmish AI (Active)") or "NullAI (Sandbox)"
  drawButton(col2X + 80, rowY, colW - 85, 26, aiLabel, false, function()
    local nextAi = (aiType == "SkirmishAI" and "NullAI") or "SkirmishAI"
    menuPolicy.updateSkirmishOption(menuState, "aiType", nextAi)
  end)

  -- AI Difficulty
  rowY = rowY - 40
  drawText("Difficulty:", col2X, rowY + 6, 12, "o")
  local diff = cfg.aiDifficulty or "Medium"
  drawButton(col2X + 80, rowY, colW - 85, 26, diff, false, function()
    local diffs = { "Easy", "Medium", "Hard" }
    for i, d in ipairs(diffs) do
      if d == diff then
        local nextDiff = diffs[(i % #diffs) + 1]
        menuPolicy.updateSkirmishOption(menuState, "aiDifficulty", nextDiff)
        break
      end
    end
  end)

  -- Column 3: Mod Subsystems
  gl.Color(0.90, 0.80, 0.45, 1.0)
  drawText("MOD SUBSYSTEMS", col3X, contentY, 15, "o")
  drawRect(col3X, contentY - 6, col3X + colW, contentY - 4, 0.5, 0.4, 0.2, 0.7)

  local toggles = {
    { key = "tactics", label = "Combat Tactics & Formations" },
    { key = "market",  label = "Marketplace Barter System" },
    { key = "garrison", label = "Town Center Garrison & Healing" },
    { key = "hud",     label = "Medieval Economy Top HUD" },
  }
  rowY = contentY - 35
  for _, t in ipairs(toggles) do
    local isChecked = (cfg[t.key] ~= false)
    local checkStr = isChecked and "[X]" or "[  ]"
    drawButton(col3X, rowY, 36, 24, checkStr, isChecked, function()
      menuPolicy.updateSkirmishOption(menuState, t.key, not isChecked)
    end)
    gl.Color(0.85, 0.85, 0.85, 1)
    drawText(t.label, col3X + 46, rowY + 5, 11, "o")
    rowY = rowY - 32
  end

  -- Bottom Action Row
  local btmY = 70
  drawButton(col1X, btmY, 180, 40, "< BACK TO MAIN", false, function()
    menuPolicy.setTab(menuState, "MAIN")
  end)

  local launchW = 240
  local launchX = vsx - col1X - launchW
  drawButton(launchX, btmY, launchW, 40, "LAUNCH BATTLE", true, function()
    launchBattle()
  end)

  if launchStatusMessage then
    gl.Color(1.0, 0.85, 0.3, 1.0)
    drawText(launchStatusMessage, vsx * 0.5, btmY + 50, 13, "c")
  end
end

--------------------------------------------------------------------------------
-- View: SETTINGS Tab
--------------------------------------------------------------------------------

local function drawSettingsView()
  local cfg = menuState.settingsConfig
  local contentY = vsy - 170
  local startX = vsx * 0.5 - 200

  gl.Color(0.90, 0.80, 0.45, 1.0)
  drawText("AUDIO & GRAPHICS SETTINGS", vsx * 0.5, contentY, 16, "oc")
  drawRect(startX - 20, contentY - 8, startX + 420, contentY - 6, 0.5, 0.4, 0.2, 0.7)

  local rowY = contentY - 45
  local volumeSettings = {
    { key = "masterVolume", label = "Master Volume" },
    { key = "musicVolume",  label = "Music Volume" },
    { key = "sfxVolume",    label = "Sound FX Volume" },
  }

  for _, s in ipairs(volumeSettings) do
    local val = cfg[s.key] or 80
    gl.Color(0.85, 0.85, 0.85, 1)
    drawText(s.label .. ":", startX, rowY + 6, 13, "o")

    drawButton(startX + 180, rowY, 32, 26, "-", false, function()
      menuPolicy.updateSetting(menuState, s.key, val - 10)
    end)

    gl.Color(1, 1, 0.8, 1)
    drawText(tostring(val) .. "%", startX + 235, rowY + 6, 13, "c")

    drawButton(startX + 270, rowY, 32, 26, "+", false, function()
      menuPolicy.updateSetting(menuState, s.key, val + 10)
    end)

    rowY = rowY - 42
  end

  -- Video settings
  rowY = rowY - 15
  drawRect(startX - 20, rowY + 20, startX + 420, rowY + 21, 0.35, 0.30, 0.20, 0.5)

  -- Fullscreen
  gl.Color(0.85, 0.85, 0.85, 1)
  drawText("Fullscreen:", startX, rowY + 6, 13, "o")
  local fsVal = cfg.fullscreen and "ON" or "OFF"
  drawButton(startX + 180, rowY, 122, 26, fsVal, cfg.fullscreen, function()
    menuPolicy.updateSetting(menuState, "fullscreen", not cfg.fullscreen)
  end)

  -- Water Quality
  rowY = rowY - 42
  gl.Color(0.85, 0.85, 0.85, 1)
  drawText("Water Quality:", startX, rowY + 6, 13, "o")
  local waterQ = cfg.waterQuality or "High"
  drawButton(startX + 180, rowY, 122, 26, waterQ, false, function()
    local qList = { "Low", "Medium", "High", "Ultra" }
    for i, q in ipairs(qList) do
      if q == waterQ then
        local nextQ = qList[(i % #qList) + 1]
        menuPolicy.updateSetting(menuState, "waterQuality", nextQ)
        break
      end
    end
  end)

  -- Back button
  drawButton(vsx * 0.5 - 90, 70, 180, 40, "< BACK TO MAIN", false, function()
    menuPolicy.setTab(menuState, "MAIN")
  end)
end

--------------------------------------------------------------------------------
-- View: CREDITS Tab
--------------------------------------------------------------------------------

local function drawCreditsView()
  local contentY = vsy - 170
  local boxW = math.min(760, vsx - 100)
  local boxX = (vsx - boxW) * 0.5

  gl.Color(0.90, 0.80, 0.45, 1.0)
  drawText("PROJECT CREDITS & LICENSING", vsx * 0.5, contentY, 16, "oc")
  drawRect(boxX, contentY - 8, boxX + boxW, contentY - 6, 0.5, 0.4, 0.2, 0.7)

  local textLines = {
    "MEDIEVAL: TOTAL CONVERSION RTS MOD",
    "Developed for Recoil / Spring RTS Engine (GPL-v2).",
    "",
    "HISTORICAL 3D ASSETS & ARTWORK:",
    "- 3D Models, Textures, and Animations converted from 0 A.D.",
    "- Developed and generously published by Wildfire Games.",
    "- Licensed under Creative Commons Attribution-ShareAlike 3.0 Unported (CC-BY-SA 3.0).",
    "",
    "CODEBASE ARCHITECTURE & GAME DESIGN:",
    "- Medieval resource logistics, supply networks, and economic barter.",
    "- Tactical melee formations, charge mechanics, and directional bracing.",
    "- Procedural resource and biome generator.",
    "- Pure policy and synced gadget isolation.",
    "",
    "TOTAL CONVERSION LICENSE: GPL-v2 (Code) & CC-BY-SA 3.0 (Assets).",
  }

  local textY = contentY - 35
  for _, line in ipairs(textLines) do
    if string.find(line, ":") then
      gl.Color(0.95, 0.85, 0.50, 1.0)
      drawText(line, boxX + 15, textY, 12, "o")
    else
      gl.Color(0.80, 0.78, 0.72, 0.9)
      drawText(line, boxX + 15, textY, 11, "o")
    end
    textY = textY - 20
  end

  drawButton(vsx * 0.5 - 90, 70, 180, 40, "< BACK TO MAIN", false, function()
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
