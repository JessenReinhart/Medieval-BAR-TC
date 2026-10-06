function widget:GetInfo()
  return {
    name = "Phase 1 Headless Ready",
    desc = "Readies the local test client for the opt-in headless simulation",
    author = "Medieval-BAR-TC",
    layer = 0,
    enabled = true,
  }
end

local options = Spring.GetModOptions() or {}
local enabled = options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1"
if not enabled then
  widgetHandler:RemoveWidget(widget)
  return
end

local sent = false

-- The engine asks the client LuaUI whether it is ready to start. Basecontent
-- widgets.lua answers false when no widget handles this callin, which stalls the
-- headless client in pregame forever. Opting in here (medievaltest only) is the
-- supported way to let an unattended client start the match.
function widget:GameSetup(state, ready, playerStates)
  return true, true
end

function widget:Update()
  if sent then return end
  sent = true
  -- Server-side counterpart for the local player. Harmless if this build has no
  -- "ready" action; GameSetup above is what actually clears the LuaUI veto.
  Spring.SendCommands("ready")
  Spring.Echo("Phase 1: headless client ready (GameSetup opt-in)")
end
