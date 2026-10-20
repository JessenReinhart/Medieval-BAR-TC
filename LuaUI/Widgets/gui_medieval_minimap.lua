-- Medieval minimap frame: an ornamental stone/wood frame around the
-- engine minimap, positioned in the bottom-left corner matching 0 A.D. style.
--
-- Loads bitmaps/ui/minimap_frame.png if available, else draws a styled
-- gl.Rect border as fallback.
--
-- Gate on modoption "medievalminimap" (default on, defensive fallback).
-- Pure unsynced widget. No synced GG access.

function widget:GetInfo()
  return {
    name    = "Medieval Minimap Frame",
    desc    = "Ornamental stone/wood frame around the engine minimap (bottom-left)",
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
-- Constants
--------------------------------------------------------------------------------

local MINIMAP_SIZE    = 220   -- minimap square side length in pixels
local FRAME_BORDER   = 18    -- frame texture extends this far beyond the minimap
local FRAME_TEX      = "bitmaps/ui/minimap_frame.png"
local CORNER_TEX     = "bitmaps/ui/frame_corner.png"

-- Color palette (docs/ui-specs.md §3)
local COL_BRONZE     = { 0.60, 0.46, 0.24, 1.00 }
local COL_DARK_BG    = { 0.11, 0.08, 0.06, 0.94 }
local COL_STONE_OUTER = { 0.38, 0.34, 0.28, 0.95 }
local COL_STONE_INNER = { 0.28, 0.24, 0.18, 0.90 }

--------------------------------------------------------------------------------
-- State
--------------------------------------------------------------------------------

local vsx, vsy = 0, 0
local hasFrameTex = false

-- Minimap geometry (bottom-left corner, with padding)
local mmX, mmY, mmW, mmH = 8, 8, MINIMAP_SIZE, MINIMAP_SIZE

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
  mmX = FRAME_BORDER + 6
  mmY = FRAME_BORDER + 6
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
-- Fallback: draw a styled rect border when texture is missing
--------------------------------------------------------------------------------

local function drawFallbackFrame(fx, fy, fw, fh)
  local b = FRAME_BORDER

  -- Outer stone border
  gl.Color(COL_STONE_OUTER)
  gl.Rect(fx, fy, fx + fw, fy + fh)

  -- Inner darker border
  gl.Color(COL_STONE_INNER)
  gl.Rect(fx + 3, fy + 3, fx + fw - 3, fy + fh - 3)

  -- Bronze inlay lines (top and bottom of frame border)
  gl.Color(COL_BRONZE)
  -- Outer top
  gl.Rect(fx, fy + fh - 2, fx + fw, fy + fh)
  -- Outer bottom
  gl.Rect(fx, fy, fx + fw, fy + 2)
  -- Outer left
  gl.Rect(fx, fy, fx + 2, fy + fh)
  -- Outer right
  gl.Rect(fx + fw - 2, fy, fx + fw, fy + fh)

  -- Inner bronze lines (around minimap viewport)
  local ix = fx + b
  local iy = fy + b
  local iw = fw - b * 2
  local ih = fh - b * 2
  gl.Rect(ix - 1, iy - 1, ix + iw + 1, iy)       -- bottom
  gl.Rect(ix - 1, iy + ih, ix + iw + 1, iy + ih + 1) -- top
  gl.Rect(ix - 1, iy, ix, iy + ih)                 -- left
  gl.Rect(ix + iw, iy, ix + iw + 1, iy + ih)       -- right

  -- Corner studs (small bronze squares at corners)
  local stud = 6
  gl.Color(COL_BRONZE[1], COL_BRONZE[2], COL_BRONZE[3], 0.9)
  gl.Rect(fx + 2, fy + 2, fx + 2 + stud, fy + 2 + stud)
  gl.Rect(fx + fw - 2 - stud, fy + 2, fx + fw - 2, fy + 2 + stud)
  gl.Rect(fx + 2, fy + fh - 2 - stud, fx + 2 + stud, fy + fh - 2)
  gl.Rect(fx + fw - 2 - stud, fy + fh - 2 - stud, fx + fw - 2, fy + fh - 2)
end

--------------------------------------------------------------------------------
-- Textured frame drawing
--------------------------------------------------------------------------------

local function drawTexturedFrame(fx, fy, fw, fh)
  gl.Color(1, 1, 1, 1)
  gl.Texture(FRAME_TEX)
  gl.TexRect(fx, fy, fx + fw, fy + fh)
  gl.Texture(false)
end

--------------------------------------------------------------------------------
-- Corner bracket overlays
--------------------------------------------------------------------------------

local function drawCornerBrackets(fx, fy, fw, fh)
  if not checkTexture(CORNER_TEX) then return end

  local s = 20
  gl.Color(1, 1, 1, 0.9)
  gl.Texture(CORNER_TEX)

  -- bottom-left
  gl.TexRect(fx, fy, fx + s, fy + s, 0, 0, 1, 1)
  -- bottom-right (mirror x)
  gl.TexRect(fx + fw, fy, fx + fw - s, fy + s, 0, 0, 1, 1)
  -- top-left (mirror y)
  gl.TexRect(fx, fy + fh, fx + s, fy + fh - s, 0, 0, 1, 1)
  -- top-right (mirror x+y)
  gl.TexRect(fx + fw, fy + fh, fx + fw - s, fy + fh - s, 0, 0, 1, 1)

  gl.Texture(false)
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
  hasFrameTex = checkTexture(FRAME_TEX)
  positionMinimap()
end

function widget:ViewResize(viewSizeX, viewSizeY)
  vsx = viewSizeX
  vsy = viewSizeY
  positionMinimap()
end

function widget:DrawScreen()
  -- Frame extends beyond the minimap by FRAME_BORDER on each side
  local fx = mmX - FRAME_BORDER
  local fy = mmY - FRAME_BORDER
  local fw = mmW + FRAME_BORDER * 2
  local fh = mmH + FRAME_BORDER * 2

  -- Dark background behind the entire frame area (under the minimap)
  gl.Color(COL_DARK_BG)
  gl.Rect(fx, fy, fx + fw, fy + fh)

  -- Draw frame (textured or fallback)
  if hasFrameTex then
    drawTexturedFrame(fx, fy, fw, fh)
  else
    drawFallbackFrame(fx, fy, fw, fh)
  end

  -- Corner brackets on top
  drawCornerBrackets(fx, fy, fw, fh)
end

function widget:Shutdown()
  -- Reset minimap to default engine position on widget removal
  if Spring and Spring.SendCommands then
    Spring.SendCommands("minimap geometry 0 0 1 1")
  end
end
