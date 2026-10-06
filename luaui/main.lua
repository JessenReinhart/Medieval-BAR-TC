--------------------------------------------------------------------------------
--  game-owned LuaUI entry point (Phase 1, headless-first)
--
--  Why we override basecontent's LuaUI/main.lua:
--
--  Basecontent's manager boots LuaUI/widgets.lua -> widgetHandler, whose
--  GameSetup callin forwards to widgets and returns `false` when no widget
--  handles GameSetup. In headless/host-only runs that false is a permanent
--  veto of the client's readiness: the client sits in pregame forever
--  (empirically confirmed: "finished loading and is now ingame" then nothing,
--  f stays -1). The synced LuaRules GameSetup callin is never invoked by the
--  engine (verified in matrix bisect runs), so the only reliable readiness
--  lever the mod owns is the LuaUI entry point itself.
--
--  Headless pregame facts (verified against engine sources + infologs):
--   * `Update()` is NOT called during headless pregame; only `GameSetup`
--     runs, pumped from GameSetupDrawer::Draw() while the drawer is active.
--   * `Spring.SendCommands("forcestart")` before the client connection is
--     established is silently dropped (infolog: forcestart echoed at
--     t=3.084131, "Connection established (given id 0)" at t=3.084440).
--   * `forcestart` (rts/Net/GameServer.cpp:2508) runs CheckForGameStart(true)
--     on the server, which bypasses the player-readiness gate
--     (CStartPosSelecter only exists for StartPosType=2 and cannot ready us).
--
--  Therefore this file pumps `forcestart` from every GameSetup call until the
--  simulation reports a positive frame, with call counting for observability.
--------------------------------------------------------------------------------

local gameSetupCalls = 0
local gameActuallyStarted = false

local lastReportedFrame = -1

function GameStart()
  gameActuallyStarted = true
  Spring.Echo("Phase 1: GameStart callin reached! Sim has started.")
end

function GameSetup(state, ready, playerStates)
  gameSetupCalls = gameSetupCalls + 1
  if (gameSetupCalls == 1) or (gameSetupCalls % 10 == 0) then
    Spring.Echo("Phase 1: GameSetup call #" .. tostring(gameSetupCalls)
      .. " (state=" .. tostring(state) .. ", ready=" .. tostring(ready) .. ")")
  end
  if not gameActuallyStarted then
    Spring.SendCommands("forcestart")
  end
  return true, true -- success (callin answered), newReady (client is ready)
end

function Update(dt)
  local f = Spring.GetGameFrame()
  if f >= 0 and f ~= lastReportedFrame and (f % 30 == 0) then
    lastReportedFrame = f
    Spring.Echo("Phase 1: LuaUI sim frame " .. tostring(f))
  end
end

Spring.Echo("Phase 1: game-owned LuaUI entry point loaded (GameSetup-driven forcestart pump)")
