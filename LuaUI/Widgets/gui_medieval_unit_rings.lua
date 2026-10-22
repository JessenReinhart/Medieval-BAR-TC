-- Medieval Unit Rings — team-color ground rings that make friendly and enemy
-- units instantly distinguishable on the battlefield.
--
-- Draws a crisp team-colored ground ring under every visible unit, keyed to
-- its owner (Spring.GetUnitTeam -> Spring.GetTeamColor). Enemy units get a
-- brighter outer warning ring (double ring) so they read as hostile at a
-- glance even under colorblind conditions; friendly units keep a single
-- subtle team-color ring.
--
-- Rendering path: DrawWorldPreUnit with a DrawWorld fallback. Rings are drawn
-- before unit geometry so they sit UNDER the feet of the units instead of
-- clipping on top of models. The visible-unit query is throttled to avoid a
-- full Spring.GetVisibleUnits sweep every render frame.
--
-- Gate on modoption "medievalunitrings" (default on, defensive fallback).
-- Hides itself when the in-game medieval main menu is open
-- (WG.medievalMainMenuOpen). Pure unsynced widget. No synced GG access.

function widget:GetInfo()
  return {
    name    = "Medieval Unit Rings",
    desc    = "Team-color ground rings under every unit with ally/enemy distinction",
    author  = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer   = -8, -- below most world widgets, above terrain decals
    enabled = true,
  }
end

-- Mod option gate; defaults to ON when the option is absent (older modoptions).
local options = Spring.GetModOptions and Spring.GetModOptions() or {}
local optionValue = options.medievalunitrings
if optionValue == false or optionValue == 0 or optionValue == "0" then return end

--------------------------------------------------------------------------------
-- GL / engine shorthand (cached up-front for per-frame performance)
--------------------------------------------------------------------------------

local spGetMyTeamID          = Spring.GetMyTeamID
local spAreTeamsAllied       = Spring.AreTeamsAllied
local spGetVisibleUnits      = Spring.GetVisibleUnits
local spGetUnitTeam          = Spring.GetUnitTeam
local spGetTeamColor         = Spring.GetTeamColor
local spGetUnitDefID         = Spring.GetUnitDefID
local spGetUnitPosition      = Spring.GetUnitPosition
local spGetGroundHeight      = Spring.GetGroundHeight
local spGetSelectedUnits     = Spring.GetSelectedUnits
local spGetDrawFrame         = Spring.GetDrawFrame

local gl = gl or {}
local glColor               = gl.Color               or function() end
local glDrawGroundCircle    = gl.DrawGroundCircle    or function() end
local glResetState          = gl.ResetState          or function() end

--------------------------------------------------------------------------------
-- Tunables
--------------------------------------------------------------------------------

-- World units. Visible units are queried within this radius of the camera.
local QUERY_RADIUS = 5000
-- Recompute the visible unit list every N render frames.
local THROTTLE_FRAMES = 3
-- Base ring radius multiplier vs. the unit def's footprint radius.
local RING_SCALE = 1.0
-- Extra ground-height lift so the ring does not z-fight the terrain mesh.
local GROUND_LIFT = 0.6

-- Ally ring: a single, subtle team-color outline.
local ALLY_LINE_WIDTH = 3.0
local ALLY_ALPHA = 0.55

-- Enemy ring: same team-color ring plus a high-contrast outer warning ring.
local ENEMY_LINE_WIDTH = 3.0
local ENEMY_ALPHA = 0.85
local ENEMY_OUTER_SCALE = 1.18
local ENEMY_OUTER_LINE_WIDTH = 2.5
local ENEMY_OUTER_COLOR = { 1.0, 0.86, 0.86, 0.9 }

-- Selection ring: bright antique gold, drawn above the ground ring.
local SEL_LINE_WIDTH = 3.5
local SEL_COLOR = { 1.0, 0.84, 0.35, 0.95 }

--------------------------------------------------------------------------------
-- Caches (per-team color and per-unit-def radius are stable during a match)
--------------------------------------------------------------------------------

local teamColorCache = {}   -- teamID -> { r, g, b }
local radiusCache = {}      -- unitDefID -> footprint radius in world units
local myTeamID
local selectedUnitIDs = {}

local frameTick = 0
local lastQueryFrame = -1
local cachedUnits = {}      -- { { x, y, z, radius, isEnemy, r, g, b } }

-- Spring "SQUARE_SIZE" is 8 world units per footprint cell by convention.
local FOOTPRINT_TO_WORLD = 8

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function getTeamColor(teamID)
  local cached = teamColorCache[teamID]
  if cached then return cached.r, cached.g, cached.b end

  local r, g, b = spGetTeamColor(teamID)
  if not r then r, g, b = 1, 1, 1 end
  teamColorCache[teamID] = { r = r, g = g, b = b }
  return r, g, b
end

-- Returns the unit's rough footprint radius in world units. Prefers the
-- engine-computed UnitDef `radius`; falls back to the common 8/footprint-cell
-- convention when the engine does not populate it.
local function getUnitRadius(unitDefID)
  local cached = radiusCache[unitDefID]
  if cached then return cached end

  local radius = 8
  if UnitDefs and UnitDefs[unitDefID] then
    local ud = UnitDefs[unitDefID]
    if ud and type(ud.radius) == "number" and ud.radius > 0 then
      radius = ud.radius
    else
      local fx = type(ud.footprintX) == "number" and ud.footprintX or 1
      local fz = type(ud.footprintZ) == "number" and ud.footprintZ or 1
      radius = math.max(fx, fz) * FOOTPRINT_TO_WORLD * 0.5
    end
    if not (radius > 0) then radius = 8 end
  end

  radiusCache[unitDefID] = radius
  return radius
end

local function isEnemy(teamID)
  if teamID == myTeamID then return false end
  if spAreTeamsAllied and spAreTeamsAllied(myTeamID, teamID) then return false end
  return true
end

-- Refresh the cached visible-unit list. Runs inside a draw callin only when
-- the render frame advances past the throttle window.
local function refreshVisibleUnits()
  if not spGetVisibleUnits then return end

  local currentFrame = 0
  if spGetDrawFrame then
    currentFrame = spGetDrawFrame()
  end
  if currentFrame == lastQueryFrame then return end
  if frameTick % THROTTLE_FRAMES ~= 0 and lastQueryFrame >= 0 then return end
  lastQueryFrame = currentFrame

  cachedUnits = {}
  local units = spGetVisibleUnits(myTeamID or -1, QUERY_RADIUS, false)
  if not units then return end

  for i = 1, #units do
    local uid = units[i]
    local teamID = spGetUnitTeam(uid)
    if teamID then
      local ux, uy, uz = spGetUnitPosition(uid)
      if ux and uz and (not uy) then uy = 0 end
      if ux then
        local udid = spGetUnitDefID(uid)
        local radius = getUnitRadius(udid)
        local enemy = isEnemy(teamID)
        local r, g, b = getTeamColor(teamID)
        local gy = spGetGroundHeight and spGetGroundHeight(ux, uz) or uy or 0
        cachedUnits[#cachedUnits + 1] = {
          x = ux, y = gy, z = uz,
          radius = radius,
          enemy = enemy,
          r = r, g = g, b = b,
        }
      end
    end
  end
end

local function refreshSelectedUnits()
  if not spGetSelectedUnits then
    selectedUnitIDs = {}
    return
  end
  selectedUnitIDs = spGetSelectedUnits() or {}
end

--------------------------------------------------------------------------------
-- World drawing
--------------------------------------------------------------------------------

-- Ground rings for all visible units (team color + enemy warning ring).
local function drawUnitRings()
  for i = 1, #cachedUnits do
    local u = cachedUnits[i]
    local y = u.y + GROUND_LIFT

    -- Team-color ring (both allies and enemies)
    if u.enemy then
      glColor(u.r, u.g, u.b, ENEMY_ALPHA)
      glDrawGroundCircle(u.x, y, u.z, u.radius * RING_SCALE, ENEMY_LINE_WIDTH)
      -- Outer high-contrast warning ring marks hostile units instantly
      glColor(ENEMY_OUTER_COLOR[1], ENEMY_OUTER_COLOR[2], ENEMY_OUTER_COLOR[3], ENEMY_OUTER_COLOR[4])
      glDrawGroundCircle(u.x, y, u.z, u.radius * ENEMY_OUTER_SCALE, ENEMY_OUTER_LINE_WIDTH)
    else
      glColor(u.r, u.g, u.b, ALLY_ALPHA)
      glDrawGroundCircle(u.x, y, u.z, u.radius * RING_SCALE, ALLY_LINE_WIDTH)
    end
  end
end

local function drawSelectionRings()
  if not selectedUnitIDs or #selectedUnitIDs == 0 then return end

  glColor(SEL_COLOR[1], SEL_COLOR[2], SEL_COLOR[3], SEL_COLOR[4])
  for i = 1, #selectedUnitIDs do
    local uid = selectedUnitIDs[i]
    local ux, uy, uz = spGetUnitPosition(uid)
    if ux and uz then
      if not uy then uy = spGetGroundHeight and spGetGroundHeight(ux, uz) or 0 end
      local udid = spGetUnitDefID(uid)
      local radius = getUnitRadius(udid)
      glDrawGroundCircle(ux, uy + GROUND_LIFT + 0.2, uz, radius * 1.05, SEL_LINE_WIDTH)
    end
  end
end

-- DrawWorldPreUnit is preferred: it runs before unit models render so rings
-- sit under feet. A DrawWorld fallback covers engines without PreUnit support
-- and both paths guard with a frame stamp to avoid double-drawing.
local drawnFrame = -1
local function worldDraw()
  if WG and WG.medievalMainMenuOpen then return end

  local currentFrame = 0
  if spGetDrawFrame then currentFrame = spGetDrawFrame() end
  if currentFrame == drawnFrame then return end
  drawnFrame = currentFrame

  frameTick = frameTick + 1
  refreshVisibleUnits()
  refreshSelectedUnits()

  drawUnitRings()
  drawSelectionRings()

  glResetState()
  glColor(1, 1, 1, 1)
end

function widget:DrawWorldPreUnit()
  worldDraw()
end

function widget:DrawWorld()
  worldDraw()
end

--------------------------------------------------------------------------------
-- Lifecycle
--------------------------------------------------------------------------------

function widget:Initialize()
  if spGetMyTeamID then
    myTeamID = spGetMyTeamID()
  else
    myTeamID = -1
  end
end

function widget:Shutdown()
  teamColorCache = {}
  radiusCache = {}
  cachedUnits = {}
  selectedUnitIDs = {}
end