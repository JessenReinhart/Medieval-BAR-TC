function widget:GetInfo()
  return {
    name = "Phase 1 Headless Ready",
    desc = "Opt-in headless readiness lever: answers GameSetup ready and pumps the host forcestart command until the sim starts",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 0,
    enabled = true,
  }
end

local options = Spring.GetModOptions() or {}
local enabled = options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1"
if not enabled then
  return false
end

local gameSetupCalls = 0
local gameActuallyStarted = false
local sent = false

-- Engine Host side: GameSetupDrawer::Draw() calls the LuaUI GameSetup callin every
-- pregame draw. For StartPosType=0 the CStartPosSelecter never exists, so the
-- "newReady" result is discarded and an unattended client stalls in pregame.
-- Pumping the blacklisted server command "forcestart" here drives
-- CGameServer::CheckForGameStart(true) once the connection is live, starting the
-- match. The pump stops as soon as GameStart has fired.
function widget:GameSetup(state, ready, playerStates)
  gameSetupCalls = gameSetupCalls + 1
  if (gameSetupCalls == 1) or (gameSetupCalls % 10 == 0) then
    Spring.Echo("Phase 1: GameSetup call #" .. tostring(gameSetupCalls)
      .. " (state=" .. tostring(state) .. ", ready=" .. tostring(ready) .. ")")
  end
  if not gameActuallyStarted then
    Spring.SendCommands("forcestart")
  end
  return true, true -- handled, and the client answers it is ready
end

function widget:GameStart()
  -- Stops the forcestart pump; the canonical "sim started" echo lives in
  -- LuaUI/main.lua (sim lifecycle) to avoid double-printing it here.
  gameActuallyStarted = true
end

function widget:Update()
  if not gameActuallyStarted then
    -- "ready" is the server-side counterpart of the local readiness state above.
    Spring.SendCommands("ready")
  end
  if sent then return end
  sent = true
  Spring.Echo("Phase 1: headless client ready (LuaUI widget GameSetup/Update opt-in)")
end