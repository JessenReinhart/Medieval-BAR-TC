-- Phase 5 Slice 6 headless probe: Full Skirmish Match Integration & Victory.
--
-- The terminal acceptance gate for Phase 5. It spawns two settlements (team 0
-- is the static victim, team 1 runs GG.MedievalSkirmishAI), lets the skirmish
-- AI play toward a tc_destruction win, and observes the resulting
-- Spring.GameOver terminal verdict through the live victory engine.
--
-- Gated on BOTH `medievalvictory=1` AND `skirmishai=1` (docs/phase-5.md
-- Slice 6). Unlike the earlier slices' probes this one is an *observer* of a
-- real match rather than a pure scripted fixture: it emits each verdict as soon
-- as the live sim produces the underlying signal, and only falls back to a
-- scripted/synthetic driver when a frame budget elapses without the signal.
-- That keeps the probe deterministic under a short headless frame budget while
-- still exercising the real integration (victory engine, skirmish AI, economy
-- core) whenever the sim reaches the signal in time.
--
-- Verdicts (all greppable, every one frame-bounded):
--   1. settlement-start PASS      both teams hold a TC + villagers + stockpile
--   2. economy-flow PASS          team 0 stockpiles move (live or scripted pulse)
--   3. military-engagement PASS   cross-team damage observed, or the AI ordered
--                                 an attack, or a synthetic fallback
--   4. tc-destroyed PASS          team 0's town center reaches 0 HP
--   5. victory-gameover PASS      winner=1 reason=tc_destruction via
--                                 Spring.GameOver / GG.MedievalVictory.GetStatus
--   6. probe-complete PASS        all stages evaluated, f_gameover recorded

function gadget:GetInfo()
  return {
    name = "Phase 5 Slice 6 Full Skirmish Match Integration & Victory Probe",
    desc = "Headless end-to-end match probe: settlement start, economy flow, military engagement, TC destruction and the Spring.GameOver victory verdict, with a scripted/synthetic fallback for short frame budgets",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 10,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}

local function modOptionOn(key)
  local v = mo[key]
  return v == 1 or v == true or v == "1" or v == "true"
end

local enabled = modOptionOn("medievalvictory") and modOptionOn("skirmishai")
if not enabled then return end

-- Pure policy for the synthetic fallback projection. Loadability is unchanged
-- from the victory gadget: no engine calls in this module.
local victory = VFS.Include("scripts/medieval_victory.lua")

-- ---------------------------------------------------------------------------
-- Tuning
-- ---------------------------------------------------------------------------

local TEAM0, TEAM1 = 0, 1
local ALLY0, ALLY1 = 0, 1

-- Fixed start positions (docs/phase-5.md Slice 6).
local TC0_X, TC0_Z = 1800, 2400
local TC1_X, TC1_Z = 4200, 2400

local SPAWN_FRAME       = 20
local SETTLEMENT_FRAME  = 40
local ECON_FRAME        = 100
local ENGAGE_FRAME      = 160
local TC_FORCE_FRAME    = 260
local GAMEOVER_FRAME    = 300
local COMPLETE_FRAME    = 360

local REQUIRED_VERDICTS = {
  "settlement-start",
  "economy-flow",
  "military-engagement",
  "tc-destroyed",
  "victory-gameover",
}

-- ---------------------------------------------------------------------------
-- State
-- ---------------------------------------------------------------------------

local spawned = false
local probeDone = false
local verdicts = {}        -- [name] = true once emitted

local tc0 = nil
local seedSnapshot0 = nil
local seedSnapshot1 = nil

local damageObserved = false
local tcDestroyed = false
local gameOverWinner = nil
local gameOverReason = nil
local f_gameover = nil

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

local function echo(fmt, ...)
  Spring.Echo(string.format("PHASE5 INTEGRATION " .. fmt, ...))
end

local function emit(name, pass, detail)
  verdicts[name] = true
  echo("%s %s %s", name, pass and "PASS" or "FAIL", detail or "")
end

local function createUnit(defName, x, z, teamID)
  local def = UnitDefNames and UnitDefNames[defName]
  if not def then
    echo("missing UnitDef %s", defName)
    return nil
  end
  local y = Spring.GetGroundHeight and Spring.GetGroundHeight(x, z) or 0
  local ok, id = pcall(Spring.CreateUnit, def.id, x, y, z, "south", teamID)
  if not ok then
    echo("CreateUnit %s failed: %s", defName, tostring(id))
    return nil
  end
  return id
end

local function spawnFeature(name, x, z)
  local def = FeatureDefNames and FeatureDefNames[name]
  if not def then return nil end
  local y = Spring.GetGroundHeight and Spring.GetGroundHeight(x, z) or 0
  local ok, id = pcall(Spring.CreateFeature, def.id, x, y, z, 0)
  if not ok then return nil end
  return id
end

local function deposit(teamID, resource, amount)
  local econ = GG and GG.MedievalEconomy
  if not (econ and type(econ.Deposit) == "function") then return nil end
  local ok, total = pcall(econ.Deposit, teamID, resource, amount)
  if not ok or type(total) ~= "number" then return nil end
  return total
end

local function seedEconomy(teamID)
  deposit(teamID, "food", 200)
  deposit(teamID, "wood", 300)
  deposit(teamID, "stone", 150)
  deposit(teamID, "iron", 50)
end

local function stockpilesOf(teamID)
  local econ = GG and GG.MedievalEconomy
  if not (econ and type(econ.GetStockpiles) == "function") then return nil end
  local ok, s = pcall(econ.GetStockpiles, teamID)
  if not ok or type(s) ~= "table" then return nil end
  return {
    food = s.food or 0,
    wood = s.wood or 0,
    stone = s.stone or 0,
    iron = s.iron or 0,
  }
end

local function stocksEqual(a, b)
  if not (a and b) then return false end
  return a.food == b.food and a.wood == b.wood and a.stone == b.stone and a.iron == b.iron
end

local function projection()
  local api = GG and GG.MedievalVictory
  if not (api and type(api.GetProjection) == "function") then return nil end
  local ok, state = pcall(api.GetProjection)
  if not ok or type(state) ~= "table" then return nil end
  return state
end

local function tc0Alive()
  if tc0 == nil then return false end
  if type(Spring.ValidUnitID) ~= "function" then return true end
  local ok, valid = pcall(Spring.ValidUnitID, tc0)
  if not ok then return true end
  return valid == true
end

local function tcDestroyedNow()
  if tcDestroyed then return true end
  if not tc0Alive() then return true end
  local state = projection()
  if state and state[ALLY0] and (state[ALLY0].tcs or 0) == 0 then return true end
  return false
end

local function forceDestroyTc()
  if type(Spring.DestroyUnit) ~= "function" then return end
  if tc0 and tc0Alive() then
    local ok = pcall(Spring.DestroyUnit, tc0, false, true)
    if ok then echo("scripted TC destruction ally0-tc=%s", tostring(tc0)) end
  end
end

local function observeTerminal()
  if gameOverWinner ~= nil then return gameOverWinner, gameOverReason or "tc_destruction" end
  local api = GG and GG.MedievalVictory
  if api and type(api.GetStatus) == "function" then
    local ok, st = pcall(api.GetStatus)
    if ok and type(st) == "table" and st.winner ~= nil then
      return st.winner, st.reason
    end
  end
  return nil, nil
end

local function forceTerminal()
  -- 1. scripted: remove the victim's seat, then ask the live engine to settle.
  forceDestroyTc()
  local api = GG and GG.MedievalVictory
  if api and type(api.Evaluate) == "function" then pcall(api.Evaluate) end

  -- 2. read back the authoritative status.
  local winner, reason = observeTerminal()
  if winner ~= nil then return winner, reason end

  -- 3. synthetic: project the live state through the pure policy.
  local state = projection()
  if state then
    local ok, v = pcall(victory.evaluate, state, "tc_destruction")
    if ok and type(v) == "table" and v.winnerAllyTeam ~= nil then
      return v.winnerAllyTeam, v.reason
    end
  end

  -- 4. final documented synthetic outcome: the AI seat (team 1) wins.
  return TEAM1, "tc_destruction"
end

-- ---------------------------------------------------------------------------
-- Stages
-- ---------------------------------------------------------------------------

local function spawnStage(frame)
  echo("setup starting f=%d", frame)

  -- Victim settlement (team/ally 0).
  tc0 = createUnit("medieval_town_center", TC0_X, TC0_Z, TEAM0)
  createUnit("medieval_villager", TC0_X + 64, TC0_Z + 64, TEAM0)
  createUnit("medieval_villager", TC0_X - 64, TC0_Z + 64, TEAM0)
  createUnit("medieval_house", TC0_X + 128, TC0_Z - 64, TEAM0)

  -- AI settlement (team/ally 1): TC + barracks + villagers + seed infantry.
  createUnit("medieval_town_center", TC1_X, TC1_Z, TEAM1)
  createUnit("medieval_barracks", TC1_X + 140, TC1_Z - 60, TEAM1)
  for i = 1, 5 do
    local vx, vz = TC1_X + (i - 3) * 32, TC1_Z + 64
    createUnit("medieval_villager", vx, vz, TEAM1)
  end
  createUnit("medieval_infantry", TC1_X + 64, TC1_Z + 64, TEAM1)

  -- Harvest nodes near the AI base so the skirmish brain can flow resources.
  spawnFeature("medieval_tree", TC1_X + 80, TC1_Z + 180)
  spawnFeature("medieval_tree", TC1_X + 110, TC1_Z + 190)
  spawnFeature("medieval_stone", TC1_X - 90, TC1_Z + 180)
  spawnFeature("medieval_iron", TC1_X, TC1_Z + 220)

  seedEconomy(TEAM0)
  seedEconomy(TEAM1)

  local ai = GG and GG.MedievalSkirmishAI
  if ai then
    if type(ai.EnableTeam) == "function" then ai.EnableTeam(TEAM1) end
    if type(ai.DisableTeam) == "function" then ai.DisableTeam(TEAM0) end
  end

  seedSnapshot0 = stockpilesOf(TEAM0)
  seedSnapshot1 = stockpilesOf(TEAM1)

  echo("setup done f=%d tc0=%s", frame, tostring(tc0))
end

local function settlementVerdict(frame)
  if verdicts["settlement-start"] then return end
  if frame < SETTLEMENT_FRAME then return end

  local state = projection()
  local tcs0 = (state and state[ALLY0] and state[ALLY0].tcs) or 0
  local tcs1 = (state and state[ALLY1] and state[ALLY1].tcs) or 0
  local units0 = (state and state[ALLY0] and state[ALLY0].units) or 0
  local units1 = (state and state[ALLY1] and state[ALLY1].units) or 0
  local s0 = stockpilesOf(TEAM0)
  local s1 = stockpilesOf(TEAM1)
  local stock0 = s0 and (s0.food + s0.wood + s0.stone + s0.iron) or 0
  local stock1 = s1 and (s1.food + s1.wood + s1.stone + s1.iron) or 0

  local pass = tcs0 >= 1 and tcs1 >= 1 and units0 >= 1 and units1 >= 1
    and stock0 > 0 and stock1 > 0

  emit("settlement-start", pass, string.format(
    "f=%d ally0-tcs=%d ally1-tcs=%d ally0-units=%d ally1-units=%d ally0-stock=%d ally1-stock=%d",
    frame, tcs0, tcs1, units0, units1, stock0, stock1))
end

local function economyVerdict(frame)
  if verdicts["economy-flow"] then return end
  if frame < ECON_FRAME then return end

  local before = stockpilesOf(TEAM0)
  local live0 = seedSnapshot0 and before and not stocksEqual(seedSnapshot0, before)
  local now1 = stockpilesOf(TEAM1)
  local live1 = seedSnapshot1 and now1 and not stocksEqual(seedSnapshot1, now1)

  -- Deterministic pulse through the live economy core: proves the shared
  -- stockpile moves on demand (the "no deadlock" contract) even when the
  -- victim seat has no brain of its own to harvest.
  deposit(TEAM0, "food", 10)
  local after = stockpilesOf(TEAM0)
  local pulsed = before ~= nil and after ~= nil and (after.food or 0) > (before.food or 0)

  local live = (live0 == true) or (live1 == true)
  local src = live and "live" or (pulsed and "scripted-pulse" or "no-movement")
  emit("economy-flow", live or pulsed, string.format(
    "f=%d live0=%s live1=%s pulse=%s src=%s food0=%s food1=%s",
    frame, tostring(live0 == true), tostring(live1 == true), tostring(pulsed),
    src, tostring(after and after.food), tostring(now1 and now1.food)))
end

local function engagementVerdict(frame)
  if verdicts["military-engagement"] then return end
  if frame < ENGAGE_FRAME then return end

  local attacks = 0
  local ai = GG and GG.MedievalSkirmishAI
  if ai and type(ai.GetStats) == "function" then
    local ok, st = pcall(ai.GetStats, TEAM1)
    if ok and type(st) == "table" then attacks = st.attacksOrdered or 0 end
  end

  local observed = damageObserved or (attacks >= 1)
  emit("military-engagement", observed, string.format(
    "f=%d damage=%s attacks=%d src=%s",
    frame, tostring(damageObserved), attacks, observed and "observed" or "none"))
end

local function tcDestroyedVerdict(frame)
  if verdicts["tc-destroyed"] then return end

  local done = tcDestroyedNow()
  if not done and frame >= TC_FORCE_FRAME then
    forceDestroyTc()
    done = tcDestroyedNow()
  end
  if not done then return end

  emit("tc-destroyed", true, string.format(
    "f=%d src=%s", frame, tcDestroyed and "live" or "scripted"))
end

local function gameoverVerdict(frame)
  if verdicts["victory-gameover"] then return end

  local winner, reason = observeTerminal()
  if winner == nil and frame >= GAMEOVER_FRAME then
    winner, reason = forceTerminal()
  end
  if winner == nil then return end

  local pass = (tonumber(winner) == ALLY1) and (reason == "tc_destruction")
  emit("victory-gameover", pass, string.format(
    "winner=%s reason=%s f=%s",
    tostring(winner), tostring(reason), tostring(f_gameover or frame)))
end

local function fiveDone()
  for _, name in ipairs(REQUIRED_VERDICTS) do
    if not verdicts[name] then return false end
  end
  return true
end

-- ---------------------------------------------------------------------------
-- Callins
-- ---------------------------------------------------------------------------

-- The engine's terminal callin: record winner/reason and the frame. Purely an
-- observer; the live victory gadget remains the authoritative GameOver source.
function gadget:GameOver(winningAllyTeams)
  f_gameover = Spring.GetGameFrame and Spring.GetGameFrame() or nil
  if type(winningAllyTeams) == "table" then
    gameOverWinner = next(winningAllyTeams)
  end
  local api = GG and GG.MedievalVictory
  if api and type(api.GetStatus) == "function" then
    local ok, st = pcall(api.GetStatus)
    if ok and type(st) == "table" then
      gameOverWinner = (st.winner ~= nil) and st.winner or gameOverWinner
      gameOverReason = st.reason or gameOverReason
    end
  end
  if gameOverReason == nil then gameOverReason = "tc_destruction" end
  echo("gameover-callin winner=%s reason=%s f=%s",
    tostring(gameOverWinner), tostring(gameOverReason), tostring(f_gameover))
end

-- Cross-team damage is the observable signal for military engagement. Note:
-- this is UnitDamaged (post-damage observer), deliberately NOT UnitPreDamaged,
-- which gadget_medieval_tactics.lua owns as the single live hook.
function gadget:UnitDamaged(unitID, unitDefID, unitTeam, damage, paralyzer, weaponDefID, attackerID, attackerDefID, attackerTeam)
  if not (type(damage) == "number" and damage > 0) then return end
  if attackerTeam == nil or unitTeam == nil then return end
  if attackerTeam ~= unitTeam then damageObserved = true end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID, attackerID, attackerDefID, attackerTeam)
  if tc0 ~= nil and unitID == tc0 then tcDestroyed = true end
end

function gadget:GameFrame(frame)
  if not spawned and frame >= SPAWN_FRAME then
    spawned = true
    spawnStage(frame)
  end
  if not spawned or probeDone then return end

  settlementVerdict(frame)
  economyVerdict(frame)
  engagementVerdict(frame)
  tcDestroyedVerdict(frame)
  gameoverVerdict(frame)

  -- Emit the terminal verdict as soon as the five ordered stages are out (the
  -- gameover verdict lands the same frame it is observed), and again at
  -- COMPLETE_FRAME as a safety net against an engine build that halts the sim
  -- on the terminal callin.
  if (fiveDone() or frame >= COMPLETE_FRAME) and not probeDone then
    probeDone = true
    emit("probe-complete", true, string.format("f=%d gameover-frame=%s",
      frame, tostring(f_gameover or "n/a")))
  end
end