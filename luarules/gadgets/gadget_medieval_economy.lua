function gadget:GetInfo()
  return {
    name = "Medieval Economy Core",
    desc = "Tracks Food, Wood, Stone, Iron discrete stockpiles per team in synced state",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 1,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local econ = VFS.Include("scripts/medieval_economy.lua")

-- Synced state: per-team stockpiles { [teamID] = { food=N, wood=N, stone=N, iron=N } }
local teamStockpiles = {}

local function syncRulesParams(teamID)
  local s = teamStockpiles[teamID]
  if not s then return end
  for _, r in ipairs(econ.RESOURCES) do
    Spring.SetGameRulesParam(string.format("team_%d_%s", teamID, r), s[r] or 0)
  end
end

local function initTeam(teamID)
  if not teamStockpiles[teamID] then
    teamStockpiles[teamID] = econ.startingStockpiles()
    syncRulesParams(teamID)
  end
end

function gadget:Initialize()
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
end

function gadget:TeamDied(teamID)
  teamStockpiles[teamID] = nil
end

-- Export authoritative API through GG so other gadgets (villager gather, recruitment, UI) can interact
GG = GG or {}
GG.MedievalEconomy = {
  GetStockpiles = function(teamID)
    initTeam(teamID)
    return teamStockpiles[teamID]
  end,

  GetResource = function(teamID, resource)
    initTeam(teamID)
    local s = teamStockpiles[teamID]
    return s and s[resource] or 0
  end,

  Deposit = function(teamID, resource, amount)
    initTeam(teamID)
    local s = teamStockpiles[teamID]
    local newTotal = econ.deposit(s, resource, amount)
    if newTotal then syncRulesParams(teamID) end
    return newTotal
  end,

  Withdraw = function(teamID, resource, amount)
    initTeam(teamID)
    local s = teamStockpiles[teamID]
    local newTotal = econ.withdraw(s, resource, amount)
    if newTotal then syncRulesParams(teamID) end
    return newTotal
  end,

  CanAfford = function(teamID, resource, amount)
    initTeam(teamID)
    local s = teamStockpiles[teamID]
    return econ.canAfford(s, resource, amount)
  end,

  Transact = function(teamID, costs)
    initTeam(teamID)
    local s = teamStockpiles[teamID]
    local ok = econ.transact(s, costs)
    if ok then syncRulesParams(teamID) end
    return ok
  end,
}
