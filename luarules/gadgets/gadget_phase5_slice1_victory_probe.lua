-- Phase 5 Slice 1 headless probe: match objectives and the victory/defeat engine.
--
-- Gated on the `medievalvictory` modoption (docs/phase-5.md modoption table).
--
-- Stages (frame-bounded, all verdicts greppable):
--   1. f=20  spawn two ally teams, each with one Town Center and one villager.
--   2. f=40  both alive: no winner under `conquest` and none under `tc_destruction`.
--   3. f=60  destroy ally team 1's Town Center.
--   4. f=90  `tc-verdict PASS winner=0` (team 1 eliminated under tc_destruction
--            while still holding its villager), the discriminating
--            `conquest-verdict` (still no winner: team 1 has units left), the live
--            `gameover-verdict` (GG.MedievalVictory status + rules params), and
--            pure-policy `regicide-verdict` / `surrender-verdict` projections.
--   5. f=120 `probe-complete PASS`.
--
-- The probe drives the live gadget through its exported API and additionally
-- feeds synthetic projections straight into scripts/medieval_victory.lua, so the
-- mode verdicts that the tc_destruction match cannot reach in-engine (regicide,
-- surrender) are still exercised against the real policy.

function gadget:GetInfo()
  return {
    name = "Phase 5 Slice 1 Victory Probe",
    desc = "Headless probe verifying the conquest / tc_destruction / regicide / surrender verdicts and the Spring.GameOver declaration",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 1000,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}
local enabled = (mo.medievalvictory == "1") or (mo.medievalvictory == 1) or (mo.medievalvictory == true)
if not enabled then return end

local victory = VFS.Include("scripts/medieval_victory.lua")

local TEAM0, TEAM1 = 0, 1
local ALLY0, ALLY1 = 0, 1

local SPAWN_FRAME = 20
local BASELINE_FRAME = 40
local DESTROY_FRAME = 60
local VERDICT_FRAME = 90
local COMPLETE_FRAME = 120

local TC0_X, TC0_Z = 1800, 2400
local TC1_X, TC1_Z = 4200, 2400

local tc0, tc1 = nil, nil
local spawned, destroyed = false, false
local stage40Done, stage90Done, completeDone = false, false, false
local gameOverWinner = nil

local function echo(fmt, ...)
  Spring.Echo(string.format("PHASE5 VICTORY " .. fmt, ...))
end

local function verdict(name, pass, detail)
  echo("%s-verdict %s %s", name, pass and "PASS" or "FAIL", detail or "")
end

local function createUnit(defName, x, z, teamID)
  local def = UnitDefNames and UnitDefNames[defName]
  if not def then
    echo("missing UnitDef %s", defName)
    return nil
  end
  local y = Spring.GetGroundHeight and Spring.GetGroundHeight(x, z) or 0
  return Spring.CreateUnit(def.id, x, y, z, "south", teamID)
end

-- Live projection maintained by the synced victory gadget. Falls back to an empty
-- table so the probe reports FAIL rather than erroring when the gadget is absent.
local function projection()
  local api = GG and GG.MedievalVictory
  if not (api and type(api.GetProjection) == "function") then return {} end
  local ok, state = pcall(api.GetProjection)
  if not ok or type(state) ~= "table" then return {} end
  return state
end

local function modeOf()
  local api = GG and GG.MedievalVictory
  if api and type(api.GetMode) == "function" then
    local ok, mode = pcall(api.GetMode)
    if ok and type(mode) == "string" then return mode end
  end
  return victory.normalizeMode((Spring.GetModOptions() or {}).victorymode)
end

local function winnerOf(state, mode)
  local ok, v = pcall(victory.evaluate, state, mode)
  if not ok or type(v) ~= "table" then return nil, nil end
  return v.winnerAllyTeam, v.reason
end

-- Pure-policy synthetic projection for the modes the live match cannot reach.
local function synthetic(spec)
  local state = {}
  for allyTeam, entry in pairs(spec) do
    state[allyTeam] = {
      tcs = entry.tcs or 0,
      kings = entry.kings or 0,
      units = entry.units or 0,
      surrendered = entry.surrendered == true,
    }
  end
  return state
end

local function rulesParam(key)
  if type(Spring.GetGameRulesParam) ~= "function" then return nil end
  local ok, value = pcall(Spring.GetGameRulesParam, key)
  if not ok then return nil end
  return value
end

-- ---------------------------------------------------------------------------
-- Stage 1: spawn
-- ---------------------------------------------------------------------------

local function spawnStage()
  tc0 = createUnit("medieval_town_center", TC0_X, TC0_Z, TEAM0)
  tc1 = createUnit("medieval_town_center", TC1_X, TC1_Z, TEAM1)
  createUnit("medieval_villager", TC0_X + 64, TC0_Z + 64, TEAM0)
  createUnit("medieval_villager", TC1_X + 64, TC1_Z + 64, TEAM1)
  echo("setup ally0-tc=%s ally1-tc=%s", tostring(tc0), tostring(tc1))
end

-- ---------------------------------------------------------------------------
-- Stage 2 (f=40): neither mode has a verdict while both settlements stand
-- ---------------------------------------------------------------------------

local function baselineStage()
  local state = projection()
  local conquestWinner = winnerOf(state, "conquest")
  local tcWinner = winnerOf(state, "tc_destruction")
  local live = modeOf()
  local pass = (conquestWinner == nil) and (tcWinner == nil)
    and state[ALLY0] ~= nil and state[ALLY1] ~= nil
    and (state[ALLY0].tcs or 0) >= 1 and (state[ALLY1].tcs or 0) >= 1
  verdict("baseline", pass, string.format("mode=%s ally0-tcs=%s ally1-tcs=%s",
    live, tostring(state[ALLY0] and state[ALLY0].tcs), tostring(state[ALLY1] and state[ALLY1].tcs)))
end

-- ---------------------------------------------------------------------------
-- Stage 3 (f=60): destroy ally team 1's settlement
-- ---------------------------------------------------------------------------

local function destroyStage()
  if tc1 then
    Spring.DestroyUnit(tc1, false, true)
    echo("destroy ally1-tc=%s", tostring(tc1))
  else
    echo("destroy ally1-tc SKIPPED (no town center was created)")
  end
end

-- ---------------------------------------------------------------------------
-- Stage 4 (f=90): the verdicts
-- ---------------------------------------------------------------------------

local function tcVerdictStage()
  local state = projection()
  local winner, reason = winnerOf(state, "tc_destruction")
  local pass = (winner == ALLY0) and (reason == "tc_destruction")
  verdict("tc", pass, string.format("winner=%s reason=%s", tostring(winner), tostring(reason)))
end

-- The discriminator: ally team 1 lost its seat but kept its villager, so
-- `conquest` must NOT call the match while `tc_destruction` did.
local function conquestVerdictStage()
  local state = projection()
  local winner = winnerOf(state, "conquest")
  local units1 = state[ALLY1] and state[ALLY1].units or 0
  local pass = (winner == nil) and (units1 >= 1)
  verdict("conquest", pass, string.format("winner=%s ally1-units=%s", tostring(winner), tostring(units1)))
end

-- Regicide: the king is the realm. Synthetic projection so the live
-- tc_destruction match does not have to be restarted.
local function regicideVerdictStage()
  local state = synthetic({
    [ALLY0] = { tcs = 1, kings = 0, units = 6 },
    [ALLY1] = { tcs = 1, kings = 1, units = 2 },
  })
  local winner, reason = winnerOf(state, "regicide")
  -- The inverse must hold too: killing the king is what loses, not the army.
  local inverse = winnerOf(synthetic({
    [ALLY0] = { tcs = 1, kings = 1, units = 0 },
    [ALLY1] = { tcs = 1, kings = 1, units = 9 },
  }), "regicide")
  local pass = (winner == ALLY1) and (reason == "regicide") and (inverse == nil)
  verdict("regicide", pass, string.format("winner=%s reason=%s kingless-with-army=%s",
    tostring(winner), tostring(reason), tostring(inverse)))
end

-- Surrender: explicit only, and gated by the frame floor.
local function surrenderVerdictStage()
  local state = synthetic({
    [ALLY0] = { tcs = 1, kings = 1, units = 4 },
    [ALLY1] = { tcs = 1, kings = 1, units = 4, surrendered = true },
  })
  local winner, reason = winnerOf(state, "surrender")
  local early = victory.canSurrender(state, ALLY1, victory.SURRENDER_MIN_FRAMES - 1)
  local late = victory.canSurrender(state, ALLY1, victory.SURRENDER_MIN_FRAMES)
  local pass = (winner == ALLY0) and (reason == "surrender") and (not early) and late
  verdict("surrender", pass, string.format("winner=%s reason=%s floor-gate=%s/%s",
    tostring(winner), tostring(reason), tostring(early), tostring(late)))
end

-- Live declaration: force an evaluation through the exported API, then read back
-- the status and the published rules params.
local function gameoverVerdictStage()
  local api = GG and GG.MedievalVictory
  if api and type(api.Evaluate) == "function" then pcall(api.Evaluate) end

  local status = nil
  if api and type(api.GetStatus) == "function" then
    local ok, value = pcall(api.GetStatus)
    if ok then status = value end
  end
  local winner = status and tonumber(status.winner) or gameOverWinner
  local reason = status and status.reason or nil
  local paramWinner = tonumber(rulesParam("victory_winner"))
  local paramReason = rulesParam("victory_reason")

  local pass = (winner == ALLY0)
    and (reason == "tc_destruction")
    and (paramWinner == ALLY0)
    and (paramReason == "tc_destruction")
  verdict("gameover", pass, string.format("winner=%s reason=%s param-winner=%s param-reason=%s",
    tostring(winner), tostring(reason), tostring(paramWinner), tostring(paramReason)))
end

-- ---------------------------------------------------------------------------
-- Callins
-- ---------------------------------------------------------------------------

-- The engine dispatches GameOver(winningAllyTeams) to every gadget; record the
-- terminal verdict the probe reports on. Purely an observer.
function gadget:GameOver(winningAllyTeams)
  if type(winningAllyTeams) == "table" then
    gameOverWinner = next(winningAllyTeams)
  end
  echo("gameover-callin winner=%s", tostring(gameOverWinner))
end

function gadget:GameFrame(frame)
  if not spawned and frame >= SPAWN_FRAME then
    spawned = true
    spawnStage()
  end

  if spawned and not stage40Done and frame >= BASELINE_FRAME then
    stage40Done = true
    baselineStage()
  end

  if stage40Done and not destroyed and frame >= DESTROY_FRAME then
    destroyed = true
    destroyStage()
  end

  if destroyed and not stage90Done and frame >= VERDICT_FRAME then
    stage90Done = true
    tcVerdictStage()
    conquestVerdictStage()
    regicideVerdictStage()
    surrenderVerdictStage()
    gameoverVerdictStage()
    -- Emitted here as well as at f=120: Spring.GameOver has just fired, and an
    -- engine build that halts the synced sim on the terminal callin would
    -- otherwise swallow the closing verdict.
    echo("probe-complete PASS mode=%s frame=%d", modeOf(), frame)
  end

  if stage90Done and not completeDone and frame >= COMPLETE_FRAME then
    completeDone = true
    echo("probe-complete PASS mode=%s frame=%d", modeOf(), frame)
  end
end
