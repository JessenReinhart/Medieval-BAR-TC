-- Medieval build icons: applies the `medievalbuildicons` mod option at runtime.
--
-- The engine already honours the per-unitdef `iconType` field, so with the
-- option ON (the default) this widget does nothing at all. When a player turns
-- it OFF, every medieval unit def is pushed back to the engine's built-in
-- "default" icon type (the plain team-coloured radar dot from
-- base/spring/bitmaps.sdz), which is the vanilla BAR-style blip.
--
-- UI isolation: this is a purely unsynced presentation switch. It reads the
-- mod option directly (like gui_medieval_hud.lua does) and only calls the
-- unsynced Spring.SetUnitDefIcon API; no synced state is touched.
function widget:GetInfo()
  return {
    name = "Medieval Build Icons",
    desc = "Applies the medievalbuildicons option: use the medieval icon set or plain radar dots",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 0,
    enabled = true,
  }
end

-- Mod option gate. `medievalbuildicons` defaults to ON when the key is absent
-- (older modoptions.lua) and accepts both boolean and numeric spellings.
local options = Spring.GetModOptions() or {}
local optionValue = options.medievalbuildicons
local ICONS_ENABLED = not (optionValue == false or optionValue == 0 or optionValue == "0")

local DEFAULT_ICON = "default"

-- Push every medieval unit def onto the plain default radar icon. Unknown icon
-- names make Spring.SetUnitDefIcon raise, so the call is guarded: on an engine
-- build without the medieval icontypes the loop simply leaves the defs alone.
local function restoreDefaultIcons()
  if not (Spring and Spring.SetUnitDefIcon) then return 0 end
  local touched = 0
  for unitDefID, def in pairs(UnitDefs or {}) do
    local name = def and def.name
    if type(name) == "string" and string.find(name, "^medieval_") then
      local ok = pcall(Spring.SetUnitDefIcon, unitDefID, DEFAULT_ICON)
      if ok then touched = touched + 1 end
    end
  end
  return touched
end

-- Exposed so the slice-5 tests can drive the behaviour without a live engine.
widget.medievalIconsEnabled = ICONS_ENABLED
widget.restoreDefaultIcons = restoreDefaultIcons

function widget:Initialize()
  if ICONS_ENABLED then return end
  restoreDefaultIcons()
end
