function widget:GetInfo()
  return { name = "Medieval Line Formation Preview", desc = "Opt-in text-command preview and synced intent",
    author = "Medieval-BAR-TC", license = "GPL-v2", layer = 0, enabled = true }
end

local options = Spring.GetModOptions() or {}
if not (options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1") then return end
local formation = VFS.Include("scripts/phase1_line_formation.lua")
local preview
local allowedDefs = {}
for _, name in ipairs({ "medieval_infantry", "medieval_archer", "medieval_cavalry" }) do
  if UnitDefNames[name] then allowedDefs[UnitDefNames[name].id] = true end
end

-- /luaui medievalpreview x z [spacing=48] [facing=1]
-- /luaui medievalformation x z [spacing=48] [facing=1]
-- Facing: 0/2 line along X, 1/3 line along Z. No mouse or ordinary command interception.
-- Spacing automatically clamped downward (never below 8) if requested line exceeds map bounds.
function widget:TextCommand(command)
  local words = {}
  for word in command:gmatch("%S+") do words[#words + 1] = word end
  if words[1] ~= "medievalformation" and words[1] ~= "medievalpreview" then return false end
  preview = nil
  if Spring.GetSpectatingState() then return true end
  local x, z = tonumber(words[2]), tonumber(words[3])
  local spacing = words[4] and tonumber(words[4]) or 48
  local facing = words[5] and tonumber(words[5]) or 1
  local ids, myTeam = {}, Spring.GetMyTeamID()
  for _, id in ipairs(Spring.GetSelectedUnits() or {}) do
    if Spring.GetUnitTeam(id) == myTeam and allowedDefs[Spring.GetUnitDefID(id)] then ids[#ids + 1] = id end
  end
  table.sort(ids)
  local slots = #words <= 5 and formation.destinations(#ids, x, z, spacing, facing, Game.mapSizeX, Game.mapSizeZ, true)
  if not slots then
    Spring.Echo("Phase 1: select medieval units; use medievalformation/medievalpreview x z [spacing 8..128] [facing 0..3]; line must fit within map (spacing auto-fits when possible)")
    return true
  end
  preview = slots -- visual estimate only, not transmitted as authoritative positions
  if words[1] == "medievalformation" then
    local params = { x, z, spacing, facing, #ids }
    for _, id in ipairs(ids) do params[#params + 1] = id end
    Spring.GiveOrderToUnitArray(ids, formation.CMD_ID, params, 0)
  end
  return true
end

function widget:SelectionChanged() preview = nil end
function widget:DrawWorld()
  if not preview then return end
  gl.Color(0.2, 0.9, 0.3, 0.7)
  for _, slot in ipairs(preview) do
    local y = Spring.GetGroundHeight(slot.x, slot.z)
    if formation.finite(y) then gl.DrawGroundCircle(slot.x, y, slot.z, 16, 16) end
  end
  gl.Color(1, 1, 1, 1)
end
