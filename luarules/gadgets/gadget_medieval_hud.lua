function gadget:GetInfo()
  return {
    name = "Medieval HUD Publisher",
    desc = "Aggregates stockpiles, population, idle villagers, starvation and the terminal verdict into team rules params for the LuaUI HUD",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 5,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local hud = VFS.Include("scripts/medieval_hud.lua")

-- ---------------------------------------------------------------------------
-- Param-key contract
-- ---------------------------------------------------------------------------
-- These literals are greppable here on purpose: tests/test_phase5_slice2.py
-- reads them back and asserts they equal scripts/medieval_hud.lua PARAM_KEYS,
-- so the publisher and the widget can never drift apart silently.
local KEY_FOOD = "food"
local KEY_WOOD = "wood"
local KEY_STONE = "stone"
local KEY_IRON = "iron"
local KEY_POP = "pop"
local KEY_POPCAP = "popcap"
local KEY_IDLE = "idle_villagers"
local KEY_STARVATION = "starvation"
local KEY_UPKEEP = "food_upkeep"
local KEY_VICTORY_WINNER = "victory_winner"
local KEY_VICTORY_REASON = "victory_reason"

-- 30-frame recache cadence: the HUD is a read-out, not a sim input.
local CADENCE_FRAMES = 30

local VILLAGER_DEF = "medieval_villager"

-- ---------------------------------------------------------------------------
-- Sources (all optional: the publisher degrades to zeroes rather than erroring
-- when a sibling gadget is absent, e.g. the economy gadget disabled by option)
-- ---------------------------------------------------------------------------

local function setParam(teamID, key, value)
  if value == nil then return end
  Spring.SetTeamRulesParam(teamID, key, value)
end

local function stockpiles(teamID)
  local api = GG and GG.MedievalEconomy
  if not api or not api.GetStockpiles then return nil end
  return api.GetStockpiles(teamID)
end

local function housingCounts(teamID)
  local api = GG and GG.MedievalHousing
  local pop, cap = 0, 0
  if api then
    if api.GetPopulation then pop = tonumber(api.GetPopulation(teamID)) or 0 end
    if api.GetCap then cap = tonumber(api.GetCap(teamID)) or 0 end
  end
  return pop, cap
end

-- A villager is idle when the gather gadget holds no job for it. Villagers that
-- are walking, harvesting or delivering all carry a job record.
local function idleVillagers(teamID)
  local total = 0
  if not (Spring.GetTeamUnits and Spring.GetUnitDefID) then return 0 end
  local gather = GG and GG.MedievalGather
  for _, unitID in ipairs(Spring.GetTeamUnits(teamID) or {}) do
    local defID = Spring.GetUnitDefID(unitID)
    local def = defID and UnitDefs and UnitDefs[defID]
    if def and def.name == VILLAGER_DEF then
      local job = gather and gather.GetJob and gather.GetJob(unitID)
      if not job then total = total + 1 end
    end
  end
  return total
end

-- 0/1 marker. Prefers the recruitment gadget's live state, then the
-- team_<id>_starving game rule it already publishes, then "fed".
local function starvationState(teamID)
  local recruit = GG and GG.MedievalRecruitment
  if recruit and recruit.IsStarving then
    if recruit.IsStarving(teamID) then return 1 end
    return 0
  end
  local published = Spring.GetGameRulesParam(string.format("team_%d_starving", teamID))
  if published ~= nil and (tonumber(published) or 0) ~= 0 then return 1 end
  return 0
end

-- Food owed per upkeep tick, so the widget can grade how many ticks of supply
-- remain instead of only flashing on the binary starvation flag.
local function foodUpkeep(teamID)
  local recruit = GG and GG.MedievalRecruitment
  if recruit and recruit.Upkeep then return tonumber(recruit.Upkeep(teamID)) or 0 end
  return 0
end

-- Slice 1 owns GG.MedievalVictory; its shape is probed defensively so this
-- gadget keeps working whichever accessor that slice settles on.
local function victoryState()
  local api = GG and GG.MedievalVictory
  if not api then return nil, nil end
  local winner, reason
  if api.GetWinner then winner = api.GetWinner() end
  if winner == nil then winner = api.winner end
  if api.GetReason then reason = api.GetReason() end
  if reason == nil then reason = api.reason end
  return tonumber(winner), reason
end

local STOCK_KEYS = {
  food = KEY_FOOD,
  wood = KEY_WOOD,
  stone = KEY_STONE,
  iron = KEY_IRON,
}

local function publishTeam(teamID)
  local stock = stockpiles(teamID)
  -- Iterate the shared formatter's resource order so the publisher and the HUD
  -- render cells in the same sequence.
  for _, resource in ipairs(hud.RESOURCE_ORDER) do
    setParam(teamID, STOCK_KEYS[resource], stock and stock[resource] or 0)
  end

  local pop, cap = housingCounts(teamID)
  setParam(teamID, KEY_POP, pop)
  setParam(teamID, KEY_POPCAP, cap)
  setParam(teamID, KEY_IDLE, idleVillagers(teamID))

  setParam(teamID, KEY_STARVATION, starvationState(teamID))
  setParam(teamID, KEY_UPKEEP, foodUpkeep(teamID))

  local winner, reason = victoryState()
  if winner ~= nil then
    setParam(teamID, KEY_VICTORY_WINNER, winner)
    setParam(teamID, KEY_VICTORY_REASON, reason or "")
    Spring.SetGameRulesParam(KEY_VICTORY_WINNER, winner)
    if reason then Spring.SetGameRulesParam(KEY_VICTORY_REASON, reason) end
  end
end

local function publishAll()
  for _, teamID in ipairs(Spring.GetTeamList() or {}) do
    publishTeam(teamID)
  end
end

function gadget:Initialize()
  publishAll()
end

function gadget:GameFrame(frame)
  if type(frame) ~= "number" or frame < 0 then return end
  if (frame % CADENCE_FRAMES) ~= 0 then return end
  publishAll()
end
