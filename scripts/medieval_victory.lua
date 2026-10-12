-- Shared, pure medieval match-objective policy; no engine calls in this module.
-- The synced victory gadget (luarules/gadgets/gadget_medieval_victory.lua) owns
-- modoption gating, per-ally-team unit tracking, the GG.MedievalVictory surface
-- and every Spring.* call, and delegates each "who has won?" question here so
-- the policy is unit-testable in isolation.
--
-- Loadability contract: this file must stay loadable by a bare Lua 5.1/LuaJIT
-- interpreter with no VFS/Spring present, so it never VFS.Include()s a sibling
-- module. The unit-name knowledge it needs (the military roster) is inlined and
-- mirrors scripts/medieval_recruitment.lua UPKEEP > 0.
--
-- Totality: every decision function answers the conservative verdict
-- (nil / {} / true / false) for malformed or missing inputs instead of raising,
-- so the gadget can call it with a partially-populated projection and no pcall
-- guard. `evaluate` never raises and never invents a winner.
local M = {}

-- ---------------------------------------------------------------------------
-- Constants (docs/phase-5.md Slice 1)
-- ---------------------------------------------------------------------------

-- Win/loss conditions. `victorymode` (modoptions.lua) selects one by key.
M.WIN_MODES = { "conquest", "tc_destruction", "regicide", "surrender" }
M.DEFAULT_MODE = "tc_destruction"

-- Frame floor before a team may surrender; keeps a match from ending during the
-- opening build order.
M.SURRENDER_MIN_FRAMES = 120

-- The regicide objective: this def must exist and be classified "king".
M.REGICIDE_KING_DEF = "medieval_king"

-- Every classification `classifyDef` can return.
M.CLASSES = { "town_center", "king", "military", "civilian", "building", "other" }

-- ---------------------------------------------------------------------------
-- Definition classification
-- ---------------------------------------------------------------------------
-- Source of truth for the def names: the keys of units/*.lua. Classification is
-- by unit-def NAME (the engine's UnitDefs[id].name, i.e. the units/*.lua key),
-- never by the human-readable `name` field inside a def.
--
-- Only the settlement seat counts as a town center; a bare house or wall is a
-- "building" and therefore never keeps a team alive under `conquest`.
M.TOWN_CENTER_DEFS = {
  medieval_town_center = true,
}

M.KING_DEFS = {
  medieval_king = true,
}

-- Mirrors scripts/medieval_recruitment.lua UPKEEP > 0, plus the Phase 5 Slice 5
-- spearman (a recruit of the tactical roster).
M.MILITARY_DEFS = {
  medieval_infantry = true,
  medieval_archer = true,
  medieval_cavalry = true,
  medieval_catapult = true,
  medieval_men_at_arms = true,
  medieval_crossbow = true,
  medieval_knight = true,
  medieval_spearman = true,
}

-- Non-combatant mobile units: villagers and the supply cart.
M.CIVILIAN_DEFS = {
  medieval_villager = true,
  medieval_cart = true,
}

-- Static settlement structures (everything immobile that is not the seat or the
-- king). Buildings are counted in neither `tcs` nor `units`.
M.BUILDING_DEFS = {
  medieval_house = true,
  medieval_granary = true,
  medieval_lumber_camp = true,
  medieval_barracks = true,
  medieval_stables = true,
  medieval_blacksmith = true,
  medieval_fletcher = true,
  medieval_wall = true,
  medieval_tower = true,
  medieval_market = true,
}

local floor = math.floor
local huge = math.huge

local function isStr(v)
  return type(v) == "string"
end

local function isNum(v)
  return type(v) == "number" and v == v and v ~= huge and v ~= -huge
end

-- A frame number is a finite, non-negative number.
local function isFrame(v)
  return isNum(v) and v >= 0
end

-- Counts are non-negative integers; anything else reads as 0.
local function countOf(v)
  if not isNum(v) or v < 0 then return 0 end
  return floor(v)
end

-- Classify a unit-def name into exactly one of M.CLASSES.
function M.classifyDef(defName)
  if not isStr(defName) then return "other" end
  if M.TOWN_CENTER_DEFS[defName] then return "town_center" end
  if M.KING_DEFS[defName] then return "king" end
  if M.MILITARY_DEFS[defName] then return "military" end
  if M.CIVILIAN_DEFS[defName] then return "civilian" end
  if M.BUILDING_DEFS[defName] then return "building" end
  return "other"
end

-- ---------------------------------------------------------------------------
-- Mode helpers
-- ---------------------------------------------------------------------------

function M.isWinMode(mode)
  if not isStr(mode) then return false end
  for _, candidate in ipairs(M.WIN_MODES) do
    if candidate == mode then return true end
  end
  return false
end

-- Unknown/missing modes fall back to DEFAULT_MODE rather than disabling the
-- victory engine.
function M.normalizeMode(mode)
  if M.isWinMode(mode) then return mode end
  return M.DEFAULT_MODE
end

-- ---------------------------------------------------------------------------
-- State projection
-- ---------------------------------------------------------------------------
-- The gadget assembles `state` as:
--   { [allyTeamID] = { tcs = N, kings = N, units = N, surrendered = bool } }
-- `tcs` counts town centers, `kings` counts kings, `units` counts live mobile
-- non-structure units (military + civilian + other). Buildings are counted
-- nowhere: a settlement of bare houses is not a defended settlement.

-- A zeroed projection entry, for callers that build state incrementally.
function M.emptyEntry()
  return { tcs = 0, kings = 0, units = 0, surrendered = false }
end

-- Coerce one projection entry; nil for a non-table entry (i.e. "no such team").
local function normalizeEntry(entry)
  if type(entry) ~= "table" then return nil end
  return {
    tcs = countOf(entry.tcs),
    kings = countOf(entry.kings),
    units = countOf(entry.units),
    surrendered = entry.surrendered == true,
  }
end

-- Sorted numeric ally-team keys of a projection (non-numeric keys are ignored).
local function rosterOf(state)
  local roster = {}
  if type(state) ~= "table" then return roster end
  for allyTeam in pairs(state) do
    if type(allyTeam) == "number" then roster[#roster + 1] = allyTeam end
  end
  table.sort(roster)
  return roster
end

-- Has this ally team lost the match under `mode`?
-- A team absent from the projection counts as eliminated: a team with no live
-- units has nothing left to defend.
function M.teamEliminated(state, allyTeam, mode)
  if type(state) ~= "table" or allyTeam == nil then return true end
  local entry = normalizeEntry(state[allyTeam])
  if not entry then return true end

  local m = M.normalizeMode(mode)
  if m == "conquest" then
    -- Units may hold the field, but with no settlement seat the team is done.
    return entry.tcs == 0 and entry.units == 0
  elseif m == "tc_destruction" then
    -- The settlement is the team; surviving units do not save it.
    return entry.tcs == 0
  elseif m == "regicide" then
    -- Economy and remaining units are irrelevant: the king is the realm.
    return entry.kings == 0
  end
  -- surrender: only an explicit surrender removes a team.
  return entry.surrendered == true
end

-- Ally teams still in the match under `mode`, ascending.
function M.remainingAllyTeams(state, mode)
  local out = {}
  for _, allyTeam in ipairs(rosterOf(state)) do
    if not M.teamEliminated(state, allyTeam, mode) then
      out[#out + 1] = allyTeam
    end
  end
  return out
end

-- ---------------------------------------------------------------------------
-- Verdict
-- ---------------------------------------------------------------------------

-- Evaluate a projection into { winnerAllyTeam = <id|nil>, losers = {…},
-- reason = <mode|nil> }.
--
-- Terminal rule: a match ends when exactly one ally team remains. A projection
-- with fewer than two ally teams never produces a winner (a single-team game
-- would otherwise be "won" on frame 0), and a mutual elimination (every ally
-- team eliminated) is a draw: no winner, no reason, all teams in `losers`.
-- `reason` is non-nil exactly when `winnerAllyTeam` is.
function M.evaluate(state, mode)
  local verdict = { winnerAllyTeam = nil, losers = {}, reason = nil }
  if type(state) ~= "table" then return verdict end

  local m = M.normalizeMode(mode)
  local roster = rosterOf(state)
  local remaining = {}

  for _, allyTeam in ipairs(roster) do
    if M.teamEliminated(state, allyTeam, m) then
      verdict.losers[#verdict.losers + 1] = allyTeam
    else
      remaining[#remaining + 1] = allyTeam
    end
  end

  if #roster < 2 then return verdict end

  if #remaining == 1 then
    verdict.winnerAllyTeam = remaining[1]
    verdict.reason = m
  end
  return verdict
end

-- ---------------------------------------------------------------------------
-- Surrender
-- ---------------------------------------------------------------------------

-- May this ally team surrender at `frame`? The frame floor is the whole gate
-- here; the mode gate (`surrender` only) is the gadget's, because the pure
-- policy is not told which mode the command arrived under.
function M.canSurrender(state, allyTeam, frame)
  if type(state) ~= "table" or allyTeam == nil then return false end
  local entry = normalizeEntry(state[allyTeam])
  if not entry then return false end
  if entry.surrendered then return false end
  if not isFrame(frame) then return false end
  return frame >= M.SURRENDER_MIN_FRAMES
end

return M
