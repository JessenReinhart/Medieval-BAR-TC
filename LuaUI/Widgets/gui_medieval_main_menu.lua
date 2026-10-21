-- Medieval Main Menu Widget — In-game menu overlay with skirmish launcher,
-- settings, and credits tabs.  Driven by the pure policy module
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
local menuState  = menuPolicy.newMenuState()

local vsx, vsy = Spring.GetViewGeometry()

--------------------------------------------------------------------------------
-- Drawing helpers
--------------------------------------------------------------------------------

local function drawBackground()
  gl.Color(0.05, 0.05, 0.08, 0.85)
  gl.Rect(0, 0, vsx, vsy)
end

local function drawTabBar()
  -- stub: draw tab bar buttons across the top
  local tabs = menuPolicy.VALID_TABS
  local tabW = 140
  local y = vsy - 50
  for i, tab in ipairs(tabs) do
    local x = (i - 1) * tabW + 20
    if menuState.activeTab == tab then
      gl.Color(0.8, 0.65, 0.2, 1.0)
    else
      gl.Color(0.4, 0.4, 0.4, 1.0)
    end
    gl.Rect(x, y, x + tabW - 4, y + 36)
    gl.Color(1, 1, 1, 1)
    gl.Text(tab, x + 10, y + 10, 14)
  end
end

--------------------------------------------------------------------------------
-- Callins
--------------------------------------------------------------------------------

function widget:ViewResize(newX, newY)
  vsx, vsy = newX, newY
end

function widget:DrawScreen()
  if not menuState.isOpen then return end
  drawBackground()
  drawTabBar()
end

function widget:KeyPress(key, mods, isRepeat, label, unicode)
  -- Escape (key code 27) toggles the menu
  if key == 27 then
    menuPolicy.toggleOpen(menuState)
    return true
  end
  return false
end

function widget:MousePress(mx, my, button)
  if not menuState.isOpen then return false end
  -- Check tab bar clicks
  local tabs = menuPolicy.VALID_TABS
  local tabW = 140
  local y = vsy - 50
  for i, tab in ipairs(tabs) do
    local x = (i - 1) * tabW + 20
    if mx >= x and mx <= x + tabW - 4 and my >= y and my <= y + 36 then
      menuPolicy.setTab(menuState, tab)
      return true
    end
  end
  return true  -- consume clicks when menu is open
end
