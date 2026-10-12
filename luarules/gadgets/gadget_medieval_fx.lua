function gadget:GetInfo()
  return {
    name = "Medieval FX Hooks",
    desc = "Lightweight audio/visual feedback hooks for medieval units, gated by the medievalaudio mod option",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 4,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

-- Mod option gate. Mirrors the helper the other medieval gadgets use: an
-- option counts as ON for 1/true/"1"/"true" and OFF for 0/false/"0"/"false".
-- A missing key (older modoptions.lua) falls back to `default`.
local function modOptionOn(key, default)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[key]
  if v == nil then return default end
  return v == 1 or v == true or v == "1" or v == "true"
end

-- Phase 7 Slice 5: `medievalaudio` mutes the whole medieval sound set without
-- touching the synced log lines, so a headless probe still observes the same
-- training/destruction verdicts with audio disabled.
local AUDIO_ENABLED = modOptionOn("medievalaudio", true)

-- Published once so unsynced widgets can mirror the state instead of reading
-- modoptions themselves (UI isolation: widgets only read rules params).
local function publishOptionState()
  if Spring.SetGameRulesParam then
    Spring.SetGameRulesParam("medieval_audio", AUDIO_ENABLED and 1 or 0)
  end
end

-- Resolve the internal unit def name the same way the recruitment gadget does.
local function internalName(unitDefID)
  if not unitDefID then return nil end
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return nil end
  return def.name
end

local function isMedievalUnit(name)
  if type(name) ~= "string" then return false end
  return string.find(name, "^medieval_") ~= nil
end

-- Single audio choke point: every PlaySoundFile in this gadget goes through
-- here, so the mod option cannot be bypassed by a new call site.
local function playSound(path)
  if not AUDIO_ENABLED then return false end
  if not (Spring and Spring.PlaySoundFile) then return false end
  return pcall(Spring.PlaySoundFile, path)
end

function gadget:Initialize()
  publishOptionState()
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX trained unit %s team %s", tostring(unitID), tostring(teamID)))
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  local def = UnitDefs and UnitDefs[unitDefID]
  if def and (def.isFactory or (def.canMove == false and not def.isFactory)) then
    -- Building (factory or static structure) construction completed.
    playSound("sounds/ui/building_complete.ogg")
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX destroyed unit %s team %s", tostring(unitID), tostring(teamID)))
end

-- Exposed for the slice-5 tests and for any future gadget that wants to honour
-- the same switch without re-reading modoptions.
GG.MedievalFX = GG.MedievalFX or {}
GG.MedievalFX.audioEnabled = AUDIO_ENABLED
GG.MedievalFX.modOptionOn = modOptionOn
GG.MedievalFX.publishOptionState = publishOptionState
