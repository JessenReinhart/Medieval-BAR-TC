function widget:GetInfo()
  return { name = "Medieval Line Formation Preview", desc = "Opt-in text-command and mouse-drag formation preview",
    author = "Medieval-BAR-TC", license = "GPL-v2", layer = 0, enabled = true }
end

local options = Spring.GetModOptions() or {}
if not (options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1") then return end
local formation = VFS.Include("scripts/phase1_line_formation.lua")
local preview
local allowedDefs = {}
for _, name in ipairs({
  "medieval_infantry",
  "medieval_archer",
  "medieval_cavalry",
  "medieval_spearman",
  "medieval_men_at_arms",
  "medieval_knight",
  "medieval_crossbow",
  "medieval_catapult",
}) do
  if UnitDefNames[name] then allowedDefs[UnitDefNames[name].id] = true end
end

local function isBuildingUnit(unitID)
  local udID = Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
  if not udID then return true end
  local ud = UnitDefs and UnitDefs[udID]
  if not ud then return false end -- unknown def: rely on allowedDefs name allowlist
  if ud.isBuilding then return true end
  if ud.canMove == false then return true end
  if (ud.speed or 0) <= 0 and (ud.maxVelocity or 0) <= 0 then return true end
  return false
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
    if Spring.GetUnitTeam(id) == myTeam and not isBuildingUnit(id) and allowedDefs[Spring.GetUnitDefID(id)] then
      ids[#ids + 1] = id
    end
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
  if #ids < 2 then
    Spring.Echo("Phase 1: select at least 2 mobile medieval military units (buildings are excluded); use medievalformation/medievalpreview x z [spacing 8..128] [facing 0..3]")
    return true
  end
  local slots = #words <= 5 and formation.destinations(#ids, x, z, spacing, facing, Game.mapSizeX, Game.mapSizeZ, true)
  if not slots then
    Spring.Echo("Phase 1: select medieval units; use medievalformation/medievalpreview x z [spacing 8..128] [facing 0..3]; line must fit within map (spacing auto-fits when possible)")
    return true
  end
  preview = slots -- visual estimate only, not transmitted as authoritative positions
  if words[1] == "medievalformation" then
    IssueFormation(ids, x, z, slots.spacing or spacing, facing)
  end
  return true
end

function widget:MousePress(x, y, button)
  if button ~= 1 then return false end
  if Spring.GetSpectatingState() then return false end
  local ids = SelectedFormationUnits()
  if #ids < 2 then return false end

  local hitType, value = Spring.TraceScreenRay(x, y)
  if hitType ~= "ground" or type(value) ~= "table" then
    return false
  end
  -- Recoil returns indexed { [1]=x, [2]=y, [3]=z }; accept table .x/.z keys as fallback.
  local gx = value[1] or value.x
  local gz = value[3] or value.z
  if not formation.finite(gx) or not formation.finite(gz) then
    return false
  end
  value = { x = gx, y = (value[2] or value.y or 0), z = gz }

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
  if hitType ~= "ground" or type(value) ~= "table" then
    return false
  end
  local gx = value[1] or value.x
  local gz = value[3] or value.z
  if not formation.finite(gx) or not formation.finite(gz) then
    return false
  end
  dragEndGround = { x = gx, y = (value[2] or value.y or 0), z = gz }
  RecomputePreview()
  return true
end

function widget:MouseRelease(x, y, button)
  if not dragging or button ~= 1 then return false end
  local ids = SelectedFormationUnits()
  if #ids > 0 and dragEndGround and preview then
    local spacing = preview.spacing or DRAG_SPACING
    IssueFormation(ids, dragEndGround.x, dragEndGround.z, spacing, FacingFromDrag())
  end
  preview = nil
  ClearDrag()
  return true
end

function widget:KeyPress(key, mods, isRepeat, label, unicode)
  if key == 27 and (dragging or preview) then -- 27 = ESC
    preview = nil
    ClearDrag()
    return true
  end
  return false
end

-- Base-content widget manager has no SelectionChanged call-in (that is a
-- BAR WidgetManager-only extension), so detect selection changes in Update
-- and clear the transient preview the same way SelectionChanged would.
local lastSelectedSig = ""
function widget:Update()
  local sel = Spring.GetSelectedUnits() or {}
  local sig = table.concat(sel, ",")
  if sig ~= lastSelectedSig then
    lastSelectedSig = sig
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