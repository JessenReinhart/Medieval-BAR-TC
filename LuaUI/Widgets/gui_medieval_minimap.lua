-- Medieval Minimap Frame — AAA-quality ornamental stone/wood frame around the
-- engine minimap, positioned in the bottom-left corner (0 A.D. / AoE style).
--
-- Renders the upgraded bitmaps/ui/minimap_frame.png (256×256 thick chiseled-
-- stone frame with transparent viewport center, rounded bevel edges, and
-- bronze N/S/E/W cardinal medallions) via gl.Texture / gl.TexRect.
-- Overlays frame_corner.png brackets at the four outer corners.
-- Tints the inner viewport with a translucent fog-of-war wash.
-- Draws team-colour unit blips with owner-color halo rings.
--
-- Gate on modoption "medievalminimap" (default on, defensive fallback).
-- Pure unsynced widget. No synced GG access.

function widget:GetInfo()
  return {
    name    = "Medieval Minimap Frame",
    desc    = "AAA stone-textured frame with fog tint and team blips (bottom-left)",
    author  = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer   = 2,
    enabled = true,
  }
end

-- Mod option gate; defaults to ON when the option is absent (older modoptions).
local options = Spring.GetModOptions and Spring.GetModOptions() or {}
local optionValue = options.medievalminimap
if optionValue == false or optionValue == 0 or optionValue == "0" then return end

--------------------------------------------------------------------------------
-- GL shorthand
--------------------------------------------------------------------------------

local gl = gl or {}
local glColor     = gl.Color     or function() end
local glRect      = gl.Rect      or function() end
local glTexture   = gl.Texture   or function() end
local glTexRect   = gl.TexRect   or function() end

--------------------------------------------------------------------------------
-- Constants
--------------------------------------------------------------------------------

local MINIMAP_SIZE   = 220   -- minimap square side length in pixels
local FRAME_BORDER   = 46   -- frame texture extends this far beyond the minimap
local FRAME_TEX      = "bitmaps/ui/minimap_frame.png"
local CORNER_TEX     = "bitmaps/ui/frame_corner.png"

-- Viewport fog-of-war tint (dark bluish-brown, translucent)
local COL_FOG_TINT   = { 0.08, 0.10, 0.14, 0.42 }

-- Fallback frame colours (used when texture is missing)
local COL_STONE_FILL  = { 0.36, 0.32, 0.26, 0.95 }
local COL_STONE_DARK  = { 0.22, 0.18, 0.14, 1.00 }
local COL_STONE_HI    = { 0.52, 0.48, 0.40, 1.00 }
local COL_BRONZE      = { 0.60, 0.46, 0.24, 1.00 }
local COL_BRONZE_DARK = { 0.35, 0.26, 0.14, 1.00 }

-- Blip drawing
local BLIP_OUTER      = 4    -- outer halo radius
local BLIP_INNER      = 2    -- inner solid dot radius
local BLIP_INTERVAL   = 6    -- frames between blip updates (cheap throttle)

--------------------------------------------------------------------------------
-- State
--------------------------------------------------------------------------------

local vsx, vsy = 0, 0
local hasFrameTex  = false
local hasCornerTex = false

-- Minimap geometry (bottom-left corner, with padding)
local mmX, mmY, mmW, mmH = 8, 8, MINIMAP_SIZE, MINIMAP_SIZE

-- Cached blip data: { {sx, sy, r, g, b}, ... }
local blipCache = {}
local blipFrame = 0

-- Map dimensions for coordinate conversion
local mapSizeX, mapSizeZ = 8192, 8192

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function checkTexture(path)
  if VFS and VFS.FileExists then
    return VFS.FileExists(path)
  end
  return true  -- optimistic fallback
end

local function positionMinimap()
  -- Place minimap in bottom-left corner with frame border offset
  mmX = FRAME_BORDER + 8
  mmY = FRAME_BORDER + 8
  mmW = MINIMAP_SIZE
  mmH = MINIMAP_SIZE

  -- Tell the engine where the minimap lives
  if Spring and Spring.SendCommands then
    local cmd = string.format("minimap geometry %d %d %d %d",
      mmX, vsy - mmY - mmH, mmW, mmH)
    Spring.SendCommands(cmd)
  end
end

--------------------------------------------------------------------------------
-- Viewport fog tint
--------------------------------------------------------------------------------

local function drawViewportTint()
  -- Slightly darkened bluish-brown translucent rect over the minimap area
  -- so the minimap reads as fog-of-war tinted terrain rather than a void.
  glColor(COL_FOG_TINT[1], COL_FOG_TINT[2], COL_FOG_TINT[3], COL_FOG_TINT[4])
  glRect(mmX, mmY, mmX + mmW, mmY + mmH)
end

--------------------------------------------------------------------------------
-- Team blips with owner-color halo/ring
--------------------------------------------------------------------------------

local function updateBlipCache()
  blipCache = {}

  -- Guard: only run inside the engine
  if not Spring.GetAllUnits then return end
  if not Spring.GetUnitPosition then return end
  if not Spring.GetUnitTeam then return end
  if not Spring.GetTeamColor then return end

  -- Map dimensions for scaling
  if Game and Game.mapSizeX then
    mapSizeX = Game.mapSizeX
    mapSizeZ = Game.mapSizeZ
  end

  local units = Spring.GetAllUnits()
  if not units then return end

  for i = 1, #units do
    local uid = units[i]
    local ux, _, uz = Spring.GetUnitPosition(uid)
    if ux and uz then
      local teamID = Spring.GetUnitTeam(uid)
      if teamID then
        local r, g, b = Spring.GetTeamColor(teamID)
        if r then
          -- Map world coordinates to minimap pixel coordinates
          local sx = mmX + (ux / mapSizeX) * mmW
          local sy = mmY + mmH - (uz / mapSizeZ) * mmH  -- flip Z axis
          blipCache[#blipCache + 1] = { sx, sy, r, g, b }
        end
      end
    end
  end
end

local function drawBlips()
  for i = 1, #blipCache do
    local b = blipCache[i]
    local sx, sy, r, g, bv = b[1], b[2], b[3], b[4], b[5]

    -- Outer soft halo ring (team color, semi-transparent)
    glColor(r, g, bv, 0.35)
    glRect(sx - BLIP_OUTER, sy - BLIP_OUTER, sx + BLIP_OUTER, sy + BLIP_OUTER)

    -- Inner solid dot (team color, opaque)
    glColor(r, g, bv, 0.95)
    glRect(sx - BLIP_INNER, sy - BLIP_INNER, sx + BLIP_INNER, sy + BLIP_INNER)
  end
end

--------------------------------------------------------------------------------
-- Textured frame drawing (thick stone-filled frame with bevels and cardinals)
--------------------------------------------------------------------------------

local function drawTexturedFrame(fx, fy, fw, fh)
  glColor(1, 1, 1, 1)
  glTexture(FRAME_TEX)
  glTexRect(fx, fy, fx + fw, fy + fh)
  glTexture(false)
end

--------------------------------------------------------------------------------
-- Fallback: draw styled rect frame when texture is missing
--------------------------------------------------------------------------------

local function drawFallbackFrame(fx, fy, fw, fh)
  local b = FRAME_BORDER

  -- Stone fill
  glColor(COL_STONE_FILL[1], COL_STONE_FILL[2], COL_STONE_FILL[3], COL_STONE_FILL[4])
  glRect(fx, fy, fx + fw, fy + fh)

  -- Dark inner background (viewport area)
  glColor(COL_STONE_DARK[1], COL_STONE_DARK[2], COL_STONE_DARK[3], COL_STONE_DARK[4])
  glRect(fx + b, fy + b, fx + fw - b, fy + fh - b)

  -- Outer bevel highlight (top and left edges)
  glColor(COL_STONE_HI[1], COL_STONE_HI[2], COL_STONE_HI[3], COL_STONE_HI[4])
  glRect(fx, fy + fh - 3, fx + fw, fy + fh)  -- top
  glRect(fx, fy, fx + 3, fy + fh)              -- left

  -- Outer bevel shadow (bottom and right edges)
  glColor(COL_STONE_DARK[1], COL_STONE_DARK[2], COL_STONE_DARK[3], COL_STONE_DARK[4])
  glRect(fx, fy, fx + fw, fy + 3)              -- bottom
  glRect(fx + fw - 3, fy, fx + fw, fy + fh)    -- right

  -- Bronze inlay band around viewport
  glColor(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], COL_BRONZE[4])
  local ix, iy = fx + b, fy + b
  local iw, ih = fw - b * 2, fh - b * 2
  glRect(ix - 2, iy - 2, ix + iw + 2, iy)        -- bottom
  glRect(ix - 2, iy + ih, ix + iw + 2, iy + ih + 2) -- top
  glRect(ix - 2, iy, ix, iy + ih)                  -- left
  glRect(ix + iw, iy, ix + iw + 2, iy + ih)        -- right

  -- Cardinal pointer stubs (N/S/E/W bronze marks)
  local cx = fx + fw * 0.5
  local cy = fy + fh * 0.5
  glColor(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], 0.9)
  -- North
  glRect(cx - 4, fy + fh - 10, cx + 4, fy + fh - 2)
  -- South
  glRect(cx - 4, fy + 2, cx + 4, fy + 10)
  -- West
  glRect(fx + 2, cy - 4, fx + 10, cy + 4)
  -- East
  glRect(fx + fw - 10, cy - 4, fx + fw - 2, cy + 4)

  -- Corner bosses (bronze squares at frame corners)
  local stud = 8
  glColor(COL_BRONZE_DARK[1], COL_BRONZE_DARK[2], COL_BRONZE_DARK[3], 0.9)
  glRect(fx + 4, fy + 4, fx + 4 + stud, fy + 4 + stud)
  glRect(fx + fw - 4 - stud, fy + 4, fx + fw - 4, fy + 4 + stud)
  glRect(fx + 4, fy + fh - 4 - stud, fx + 4 + stud, fy + fh - 4)
  glRect(fx + fw - 4 - stud, fy + fh - 4 - stud, fx + fw - 4, fy + fh - 4)
end

--------------------------------------------------------------------------------
-- Corner bracket overlays
--------------------------------------------------------------------------------

local function drawCornerBrackets(fx, fy, fw, fh)
  if not hasCornerTex then return end

  local s = 28
  glColor(1, 1, 1, 0.92)
  glTexture(CORNER_TEX)

  -- bottom-left (original orientation)
  glTexRect(fx, fy, fx + s, fy + s, 0, 0, 1, 1)
  -- bottom-right (mirror x)
  glTexRect(fx + fw, fy, fx + fw - s, fy + s, 0, 0, 1, 1)
  -- top-left (mirror y)
  glTexRect(fx, fy + fh, fx + s, fy + fh - s, 0, 0, 1, 1)
  -- top-right (mirror x+y)
  glTexRect(fx + fw, fy + fh, fx + fw - s, fy + fh - s, 0, 0, 1, 1)

  glTexture(false)
end

--------------------------------------------------------------------------------
-- Widget callins
--------------------------------------------------------------------------------

function widget:Initialize()
  if Spring and Spring.GetViewGeometry then
    vsx, vsy = Spring.GetViewGeometry()
  else
    vsx, vsy = 1920, 1080
  end
  hasFrameTex  = checkTexture(FRAME_TEX)
  hasCornerTex = checkTexture(CORNER_TEX)
  positionMinimap()
end

function widget:ViewResize(viewSizeX, viewSizeY)
  vsx = viewSizeX
  vsy = viewSizeY
  positionMinimap()
end

function widget:DrawScreen()
  -- Hide minimap frame when main menu is open
  if WG and WG.medievalMainMenuOpen then return end

  -- Frame extends beyond the minimap by FRAME_BORDER on each side
  local fx = mmX - FRAME_BORDER
  local fy = mmY - FRAME_BORDER
  local fw = mmW + FRAME_BORDER * 2
  local fh = mmH + FRAME_BORDER * 2

  -- 1. Fog-of-war viewport tint (translucent overlay on minimap area)
  drawViewportTint()

  -- 2. Update blip cache (throttled)
  blipFrame = blipFrame + 1
  if blipFrame >= BLIP_INTERVAL then
    blipFrame = 0
    updateBlipCache()
  end

  -- 3. Draw team blips (under the frame overlay)
  drawBlips()

  -- 4. Draw the stone frame (textured or fallback)
  if hasFrameTex then
    drawTexturedFrame(fx, fy, fw, fh)
  else
    drawFallbackFrame(fx, fy, fw, fh)
  end

  -- 5. Corner brackets on top of the frame
  drawCornerBrackets(fx, fy, fw, fh)

  -- Reset color
  glColor(1, 1, 1, 1)
end

function widget:Shutdown()
  -- Reset minimap to default engine position on widget removal
  if Spring and Spring.SendCommands then
    Spring.SendCommands("minimap geometry 0 0 1 1")
  end
end
