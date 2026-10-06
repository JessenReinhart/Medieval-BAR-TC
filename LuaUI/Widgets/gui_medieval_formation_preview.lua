function widget:GetInfo()
  return { name = "Medieval Line Formation Preview", desc = "Opt-in text-command and mouse-drag formation preview",
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

-- Mouse-drag state. Spacing is fixed (same default as the TextCommand path);
-- facing is derived from drag direction in ground space.
local DRAG_SPACING = 48
local dragging = false
local dragStartGround
local dragEndGround
local dragUnitIDs

local function SelectedFormationUnits()
  local ids, myTeam = {}, Spring.GetMyTeamID()
  for _, id in ipairs(Spring.GetSelectedUnits() or {}) do
    if Spring.GetUnitTeam(id) == myTeam and allowedDefs[Spring.GetUnitDefID(id)] then ids[#ids + 1] = id end
  end
  table.sort(ids)
  return ids
end

local function IssueFormation(ids, x, z, spacing, facing)
  local params = { x, z, spacing, facing, #ids }
  for _, id in ipairs(ids) do params[#params + 1] = id end
  Spring.GiveOrderToUnitArray(ids, formation.CMD_ID, params, 0)
end

-- 0/2 line along X, 1/3 line along Z (matches formation.destinations semantics).
local function FacingFromDrag()
  local gdx = dragEndGround.x - dragStartGround.x
  local gdz = dragEndGround.z - dragStartGround.z
  if math.abs(gdx) >= math.abs(gdz) then
    return (gdx >= 0) and 0 or 2
  else
    return (gdz >= 0) and 1 or 3
  end
end

local function RecomputePreview()
  local facing = FacingFromDrag()
  preview = formation.destinations(#dragUnitIDs, dragEndGround.x, dragEndGround.z,
    DRAG_SPACING, facing, Game.mapSizeX, Game.mapSizeZ, true)
end

local function ClearDrag()
  dragging = false
  dragStartGround = nil
  dragEndGround = nil
  dragUnitIDs = nil
end

-- /luaui medievalpreview x z [spacing=48] [facing=1]
-- /luaui medievalformation x z [spacing=48] [facing=1]
-- Facing: 0/2 line along X, 1/3 line along Z.
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
  local ids = SelectedFormationUnits()
  local slots = #words <= 5 and formation.destinations(#ids, x, z, spacing, facing, Game.mapSizeX, Game.mapSizeZ, true)
  if not slots then
    Spring.Echo("Phase 1: select medieval units; use medievalformation/medievalpreview x z [spacing 8..128] [facing 0..3]; line must fit within map (spacing auto-fits when possible)")
    return true
  end
  preview = slots -- visual estimate only, not transmitted as authoritative positions
  if words[1] == "medievalformation" then
    IssueFormation(ids, x, z, spacing, facing)
  end
  return true
end

function widget:MousePress(x, y, button)
  if button ~= 1 then return false end
  if Spring.GetSpectatingState() then return false end
  local ids = SelectedFormationUnits()
  if #ids == 0 then return false end

  local hitType, value = Spring.TraceScreenRay(x, y)
  if hitType ~= "ground" or type(value) ~= "table"
    or not formation.finite(value.x) or not formation.finite(value.z) then
    return false
  end

  dragging = true
  dragStartGround = value
  dragEndGround = value
  dragUnitIDs = ids
  RecomputePreview()
  return true
end

function widget:MouseMove(x, y, dx, dy, button)
  if not dragging then return false end
  local hitType, value = Spring.TraceScreenRay(x, y)
  if hitType ~= "ground" or type(value) ~= "table"
    or not formation.finite(value.x) or not formation.finite(value.z) then
    return false
  end
  dragEndGround = value
  RecomputePreview()
  return true
end

function widget:MouseRelease(x, y, button)
  if not dragging or button ~= 1 then return false end
  local ids = SelectedFormationUnits()
  if #ids > 0 and dragEndGround then
    IssueFormation(ids, dragEndGround.x, dragEndGround.z, DRAG_SPACING, FacingFromDrag())
  end
  preview = nil
  ClearDrag()
  return true
end

-- Base-content widget manager has no SelectionChanged call-in (that is a
-- BAR WidgetManager-only extension), so detect selection changes in Update
-- and clear the transient preview the same way SelectionChanged would.
local lastSelectedCount = -1
function widget:Update()
  local count = #(Spring.GetSelectedUnits() or {})
  if count ~= lastSelectedCount then
    lastSelectedCount = count
    preview = nil
    ClearDrag()
  end
end

function widget:DrawWorld()
  if not dragging and not preview then return end
  gl.Color(0.2, 0.9, 0.3, 0.7)
  if dragging and dragStartGround and dragEndGround then
    local y1 = Spring.GetGroundHeight(dragStartGround.x, dragStartGround.z)
    local y2 = Spring.GetGroundHeight(dragEndGround.x, dragEndGround.z)
    gl.Shape(gl.LINES, {
      { v = { dragStartGround.x, y1 + 1, dragStartGround.z } },
      { v = { dragEndGround.x, y2 + 1, dragEndGround.z } },
    })
  end
  if preview then
    for _, slot in ipairs(preview) do
      local y = Spring.GetGroundHeight(slot.x, slot.z)
      if formation.finite(y) then gl.DrawGroundCircle(slot.x, y, slot.z, 16, 16) end
    end
  end
  gl.Color(1, 1, 1, 1)
end