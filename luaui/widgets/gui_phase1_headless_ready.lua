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

function widget:Update()
  if sent then return end
  sent = true
  -- Client-side readiness. The server still needs every local player to signal
  -- ready; the synced GameSetup override alone does not emit this network message.
  Spring.SendCommands("ready")
  Spring.Echo("Phase 1: sent headless ready command")
end
