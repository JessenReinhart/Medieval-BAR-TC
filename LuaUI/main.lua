--------------------------------------------------------------------------------
--------------------------------------------------------------------------------
--
--  file:    main.lua
--  brief:   Medieval-BAR-TC game-owned LuaUI entry point.
--
--           Boots the engine base-content widget manager (widgets.lua) and relays
--           call-ins to it, exactly as the engine reference LuaUI/main.lua does.
--           The headless readiness lever (GameSetup ready + the host `forcestart`
--           pump) lives in LuaUI/Widgets/gui_phase1_headless_ready.lua, because
--           widgetHandler:UpdateCallIn() owns the GameSetup/GameStart/GameFrame
--           relays and would otherwise overwrite any logic placed here.
--
--  Based on: engine base-content LuaUI/main.lua (Dave Rodgers, GPL v2+).
--
--------------------------------------------------------------------------------
--------------------------------------------------------------------------------

LUAUI_DIRNAME = LUAUI_DIRNAME or 'LuaUI/'
LUAUI_VERSION = LUAUI_VERSION or 'LuaUI v0.3'
VFS.DEF_MODE = VFS.RAW_FIRST

Spring.SendCommands({"ctrlpanel " .. LUAUI_DIRNAME .. "ctrlpanel.txt"})

-- The engine ships these base-content LuaUI files RAW next to the binary
-- (not inside springcontent.sdz), so resolve them with the default RAW_FIRST
-- mode rather than VFS.ZIP as the reference main.lua hardcodes.
VFS.Include(LUAUI_DIRNAME .. "rml_setup.lua")
VFS.Include(LUAUI_DIRNAME .. 'utils.lua')

include("setupdefs.lua")
include("savetable.lua")

include("debug.lua")
include("fonts.lua")
include("layout.lua")   -- contains a simple LayoutButtons()
include("widgets.lua")  -- the widget handler


--------------------------------------------------------------------------------
--
-- print the header
--

if (RestartCount == nil) then
  RestartCount = 0
else
  RestartCount = RestartCount + 1
end

do
  local restartStr = ""
  if (RestartCount > 0) then
    restartStr = "  (" .. RestartCount .. " Restarts)"
  end
  Spring.SendCommands({"echo " .. LUAUI_VERSION .. restartStr})
end


--------------------------------------------------------------------------------
-------------------------------------------------------------------------------
--
--  A few helper functions
--

function Say(msg)
  Spring.SendCommands({'say ' .. msg})
end


-------------------------------------------------------------------------------
--
--  Update()  --  called every frame
--

activePage = 0

forceLayout = true


local simStarted = false
local lastReportedFrame = -1

function GameStart()
  simStarted = true
  Spring.Echo("Phase 1: GameStart callin reached! Sim has started.")
  return widgetHandler:GameStart()
end

function GameSetup(state, ready, playerStates)
  if not simStarted then
    Spring.SendCommands("forcestart")
  end
  return widgetHandler:GameSetup(state, ready, playerStates)
end

function Update(dt)
  dt = dt or Spring.GetLastUpdateSeconds()

  local currentPage = Spring.GetActivePage()
  if (forceLayout or (currentPage ~= activePage)) then
    Spring.ForceLayoutUpdate()  --  for the page number indicator
    forceLayout = false
  end
  activePage = currentPage

  fontHandler.Update(dt)

  local f = Spring.GetGameFrame()
  if f >= 0 and f ~= lastReportedFrame and (f % 30 == 0) then
    lastReportedFrame = f
    Spring.Echo("Phase 1: LuaUI sim frame " .. tostring(f))
  end

  widgetHandler:Update(dt)

  return
end


-------------------------------------------------------------------------------
-------------------------------------------------------------------------------
--
--  WidgetHandler fixed calls
--

function Shutdown()
  return widgetHandler:Shutdown()
end

function ConfigureLayout(command)
  return widgetHandler:ConfigureLayout(command)
end

function ActiveCommandChanged(id, cmdType)
  return widgetHandler:ActiveCommandChanged(id, cmdType)
end

function CameraRotationChanged(rotx, roty, rotz)
  return widgetHandler:CameraRotationChanged(rotx, roty, rotz)
end

function CameraPositionChanged(posx, posy, posz)
  return widgetHandler:CameraPositionChanged(posx, posy, posz)
end

function MiniMapRotationChanged(newRot, oldRot)
  return widgetHandler:MiniMapRotationChanged(newRot, oldRot)
end

function MiniMapStateChanged(isMinimized, isMaximized, isSlaved)
  return widgetHandler:MiniMapStateChanged(isMinimized, isMaximized, isSlaved)
end

function MiniMapGeometryChanged(newPosX, newPosY, newDimX, newDimY, oldPosX, oldPosY, oldDimX, oldDimY)
  return widgetHandler:MiniMapGeometryChanged(newPosX, newPosY, newDimX, newDimY, oldPosX, oldPosY, oldDimX, oldDimY)
end

function CommandNotify(id, params, options)
  return widgetHandler:CommandNotify(id, params, options)
end

function DrawScreen(vsx, vsy)
  widgetHandler:SetViewSize(vsx, vsy)
  return widgetHandler:DrawScreen()
end

function KeyMapChanged()
  return widgetHandler:KeyMapChanged()
end

function KeyPress(key, mods, isRepeat, label, unicode, scanCode, actions)
  return widgetHandler:KeyPress(key, mods, isRepeat, label, unicode, scanCode, actions)
end

function KeyRelease(key, mods, label, unicode, scanCode, actions)
  return widgetHandler:KeyRelease(key, mods, label, unicode, scanCode, actions)
end

function MouseMove(x, y, dx, dy, button)
  return widgetHandler:MouseMove(x, y, dx, dy, button)
end

function MousePress(x, y, button)
  return widgetHandler:MousePress(x, y, button)
end

function MouseRelease(x, y, button)
  return widgetHandler:MouseRelease(x, y, button)
end

function IsAbove(x, y)
  return widgetHandler:IsAbove(x, y)
end

function GetTooltip(x, y)
  return widgetHandler:GetTooltip(x, y)
end

function AddConsoleLine(msg, priority)
  return widgetHandler:AddConsoleLine(msg, priority)
end

function GroupChanged(groupID)
  return widgetHandler:GroupChanged(groupID)
end


--
-- The unit (and some of the Draw) call-ins are handled
-- differently (see LuaUI/widgets.lua / UpdateCallIns())
--


--------------------------------------------------------------------------------