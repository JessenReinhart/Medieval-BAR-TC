function gadget:GetInfo()
  return {
    name = "Medieval FX Hooks",
    desc = "Lightweight audio/visual feedback hooks for medieval units (headless log verification only)",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 4,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

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

function gadget:UnitCreated(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX trained unit %s team %s", tostring(unitID), tostring(teamID)))
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX destroyed unit %s team %s", tostring(unitID), tostring(teamID)))
end