-- Synced medieval victory engine: the authoritative match-end trigger.
--
-- It replaces the engine's death logic (docs/phase-5.md: `deathmode = neverend`
-- means "no engine auto-end, the gadget decides") by projecting live per-ally-team
-- unit counts into the pure policy in scripts/medieval_victory.lua and calling
-- Spring.GameOver once a terminal condition is reached.
--
-- All "who has won?" math lives in scripts/medieval_victory.lua; this gadget owns
-- modoption gating, the live unit tracking, the GG.MedievalVictory surface and
-- every Spring.* call. The projection handed to the policy is exactly:
--   { [allyTeamID] = { tcs = N, kings = N, units = N, surrendered = bool } }
--
-- Layer 6: after economy (1), housing (2), gather (3), recruitment (4) and the
-- skirmish AI (5), so a team that spends its last frame recruiting a unit is
-- evaluated with that unit already counted.
--
-- Gating (docs/phase-5.md Slice 1): modoption `medievalvictory=1` enables the
-- Slice 1/6 probe runs, where the probe drives the stages and this gadget must be
-- live; otherwise the gadget reads `victorymode` and runs in "live" mode with a
-- conservative 15-frame cadence.

function gadget:GetInfo()
  return {
    name = "Medieval Victory",
    desc = "Match objectives and the victory/defeat engine: conquest, TC destruction, regicide and surrender, declared through Spring.GameOver",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 6,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local victory = VFS.Include("scripts/medieval_victory.lua")

-- ---------------------------------------------------------------------------
-- Options
-- ---------------------------------------------------------------------------

local function modOptionOn(key)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[key]
  return v == 1 or v == true or v == "1" or v == "true"
end

-- `medievalvictory` gates the Slice 1/6 probe runs. The engine itself is core
-- gameplay and always runs: a match must be able to end even when no probe asked
-- for it. The option only selects the tighter probe cadence.
local PROBE_MODE = modOptionOn("medievalvictory")

local function configuredMode()
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  return victory.normalizeMode(mo.victorymode)
end

local MODE = configuredMode()

-- Live matches evaluate once per second; probe runs want a verdict promptly after
-- each scripted stage, so they evaluate every 15 frames.
local CADENCE_FRAMES = PROBE_MODE and 15 or 30

-- Regicide kings are anchored to a live unit (the starting Town Center), which
-- only exists after GameStart(). This window lets GameFrame retry the spawn
-- until a Town Center appears, then stops retrying so we never resurrect a
-- team late into the match.
local REGICIDE_SPAWN_WINDOW = 30 * 30  -- ~30 seconds

-- ---------------------------------------------------------------------------
-- Live state
-- ---------------------------------------------------------------------------
-- units[allyTeam][unitID] = classification ("town_center" / "king" / "military" /
-- "civilian" / "building" / "other"). Only town_center, king and the mobile
-- classes matter to the projection; buildings are tracked so a re-classification
-- or a future mode cannot silently miss them, and so UnitDestroyed can decrement
-- the right counter without re-reading the def of a dead unit.
local units = {}          -- [allyTeam][unitID] = class
local counts = {}         -- [allyTeam] = { tcs, kings, units }
local surrendered = {}    -- [allyTeam] = true
local registeredKings = {} -- [allyTeam] = unitID (regicide bookkeeping)
local knownAllyTeams = {} -- [allyTeam] = true, the roster that ever existed

local status = nil        -- { winner = <id>, reason = <mode> } once terminal
local gameOverSeen = false

local function newCounts()
  return { tcs = 0, kings = 0, units = 0 }
end

local function teamOfUnit(unitID)
  if type(Spring.GetUnitTeam) ~= "function" then return nil end
  local ok, teamID = pcall(Spring.GetUnitTeam, unitID)
  if not ok then return nil end
  return teamID
end

local function allyTeamOfTeam(teamID)
  if teamID == nil then return nil end
  if type(Spring.GetTeamInfo) ~= "function" then return nil end
  -- GetTeamInfo(teamID) -> teamID, leader, isDead, isAi, side, allyTeam, ...
  local ok, _, _, _, _, _, allyTeam = pcall(Spring.GetTeamInfo, teamID, false)
  if not ok then return nil end
  return allyTeam
end

local function allyTeamOfUnit(unitID)
  return allyTeamOfTeam(teamOfUnit(unitID))
end

local function defNameOf(unitDefID)
  local def = UnitDefs and unitDefID and UnitDefs[unitDefID]
  return def and def.name or nil
end

local function initAllyTeam(allyTeam)
  if allyTeam == nil then return nil end
  knownAllyTeams[allyTeam] = true
  if not units[allyTeam] then units[allyTeam] = {} end
  if not counts[allyTeam] then counts[allyTeam] = newCounts() end
  if surrendered[allyTeam] == nil then surrendered[allyTeam] = false end
  return counts[allyTeam]
end

-- Apply a classification delta to one ally team's counters.
local function applyDelta(allyTeam, class, sign)
  local c = initAllyTeam(allyTeam)
  if not c then return end
  if class == "town_center" then
    c.tcs = math.max(0, c.tcs + sign)
  elseif class == "king" then
    c.kings = math.max(0, c.kings + sign)
  elseif class == "military" or class == "civilian" or class == "other" then
    -- Only mobile non-structure units count towards `units`: a "building" never
    -- does, which is what makes `conquest` mean "no seat and no field force".
    c.units = math.max(0, c.units + sign)
  end
end

local function trackUnit(unitID, unitDefID, allyTeam)
  if unitID == nil or allyTeam == nil then return nil end
  local name = defNameOf(unitDefID)
  if not name then return nil end
  local class = victory.classifyDef(name)
  initAllyTeam(allyTeam)
  -- Re-tracking the same unit (UnitTaken/UnitGiven churn) must not double-count.
  local previous = units[allyTeam][unitID]
  if previous ~= nil then return class end
  units[allyTeam][unitID] = class
  applyDelta(allyTeam, class, 1)
  return class
end

local function untrackUnit(unitID, allyTeam)
  if unitID == nil then return end
  allyTeam = allyTeam or allyTeamOfUnit(unitID)
  if allyTeam == nil then return end
  local bucket = units[allyTeam]
  if not bucket then return end
  local class = bucket[unitID]
  if class == nil then return end
  bucket[unitID] = nil
  applyDelta(allyTeam, class, -1)
end

-- ---------------------------------------------------------------------------
-- Projection
-- ---------------------------------------------------------------------------

local function projection()
  local state = {}
  for allyTeam in pairs(knownAllyTeams) do
    local c = counts[allyTeam] or newCounts()
    state[allyTeam] = {
      tcs = c.tcs,
      kings = c.kings,
      units = c.units,
      surrendered = surrendered[allyTeam] == true,
    }
  end
  return state
end

-- ---------------------------------------------------------------------------
-- Terminal handling
-- ---------------------------------------------------------------------------

local function publishStatus(winner, reason)
  status = { winner = winner, reason = reason }
  if type(Spring.SetGameRulesParam) == "function" then
    Spring.SetGameRulesParam("victory_winner", winner)
    Spring.SetGameRulesParam("victory_reason", reason)
  end
end

local function declareWinner(winnerAllyTeam, reason)
  if status then return false end
  publishStatus(winnerAllyTeam, reason)
  Spring.Echo(string.format("PHASE5 VICTORY gameover winner=%s reason=%s", tostring(winnerAllyTeam), tostring(reason)))
  -- Recoil's winning-ally-team tuple: a set keyed by ally team ID. Verify this
  -- shape against the engine build when the Slice 1 probe runs; the callin path
  -- (luarules/gadgets.lua -> gadgetHandler:GameOver(winningAllyTeams)) exists
  -- either way, and this gadget's own GameOver observer logs the terminal verdict.
  Spring.GameOver({ [winnerAllyTeam] = 1 })
  return true
end

local function evaluateNow()
  local state = projection()
  local verdict = victory.evaluate(state, MODE)
  if verdict.winnerAllyTeam ~= nil then
    declareWinner(verdict.winnerAllyTeam, verdict.reason)
  end
  return verdict
end

-- ---------------------------------------------------------------------------
-- Regicide setup
-- ---------------------------------------------------------------------------

-- Spawn one medieval_king per ally team that has none, at the position of that
-- ally team's first live unit (its Town Center at match start). A team with no
-- units at all is left alone: it is already eliminated and spawning a king would
-- resurrect it.
--
-- Spring.CreateUnit takes a TEAM id, so the anchor records the unit's team, not
-- its ally team.
local function ensureKings()
  local kingDef = UnitDefNames and UnitDefNames[victory.REGICIDE_KING_DEF]
  if not kingDef then
    Spring.Echo("PHASE5 VICTORY regicide skipped: missing " .. victory.REGICIDE_KING_DEF .. " UnitDef")
    return
  end
  if type(Spring.GetAllUnits) ~= "function" or type(Spring.GetUnitPosition) ~= "function" then return end

  local anchor = {}  -- [allyTeam] = { x =, z =, team = }
  for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
    local allyTeam = allyTeamOfUnit(unitID)
    if allyTeam and not anchor[allyTeam] then
      local ok, x, _, z = pcall(Spring.GetUnitPosition, unitID)
      local teamID = teamOfUnit(unitID)
      if ok and type(x) == "number" and teamID ~= nil then
        anchor[allyTeam] = { x = x, z = z, team = teamID }
      end
    end
  end

  for allyTeam in pairs(knownAllyTeams) do
    local c = counts[allyTeam] or newCounts()
    local spot = anchor[allyTeam]
    if c.kings == 0 and spot then
      local y = Spring.GetGroundHeight and Spring.GetGroundHeight(spot.x, spot.z) or 0
      local unitID = Spring.CreateUnit(kingDef.id, spot.x, y, spot.z, "south", spot.team)
      Spring.Echo(string.format("PHASE5 VICTORY regicide spawn allyTeam=%d team=%d king=%s at=(%.0f, %.0f)",
        allyTeam, spot.team, tostring(unitID), spot.x, spot.z))
      if unitID then
        registeredKings[allyTeam] = unitID
        -- UnitCreated already fired for this id on the same frame in most builds;
        -- trackUnit's guard makes this call idempotent either way.
        trackUnit(unitID, kingDef.id, allyTeam)
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Callins
-- ---------------------------------------------------------------------------

function gadget:Initialize()
  for _, allyTeam in ipairs(Spring.GetAllyTeamList and Spring.GetAllyTeamList() or {}) do
    initAllyTeam(allyTeam)
  end
  for _, teamID in ipairs(Spring.GetTeamList and Spring.GetTeamList() or {}) do
    local allyTeam = allyTeamOfTeam(teamID)
    if allyTeam ~= nil then initAllyTeam(allyTeam) end
  end

  -- Best effort at Initialize: GetAllUnits may still be empty before GameStart,
  -- so this is a last-resort attempt that GameStart/GameFrame will re-try.
  if MODE == "regicide" then ensureKings() end

  Spring.Echo(string.format("PHASE5 VICTORY ready mode=%s probe=%s cadence=%d",
    MODE, tostring(PROBE_MODE), CADENCE_FRAMES))
end

-- GameStart fires after the first units (Town Centers) exist, which is the first
-- frame where ensureKings can actually anchor a king to a live unit.
function gadget:GameStart()
  if MODE == "regicide" then ensureKings() end
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  local allyTeam = allyTeamOfTeam(teamID)
  if allyTeam == nil then return end
  local class = trackUnit(unitID, unitDefID, allyTeam)
  if class == "king" then
    registeredKings[allyTeam] = registeredKings[allyTeam] or unitID
  end
end

-- UnitFinished is the completion of a factory build; UnitCreated already fired,
-- so this only backfills units that existed before Initialize (none in practice)
-- and never double-counts thanks to trackUnit's guard.
function gadget:UnitFinished(unitID, unitDefID, teamID)
  local allyTeam = allyTeamOfTeam(teamID)
  if allyTeam == nil then return end
  trackUnit(unitID, unitDefID, allyTeam)
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  local allyTeam = allyTeamOfTeam(teamID)
  if allyTeam == nil then allyTeam = allyTeamOfUnit(unitID) end
  if allyTeam == nil then
    -- A unit that never entered the table (spawned before this gadget was live)
    -- still cannot be uncounted; drop it from every bucket defensively.
    for team, bucket in pairs(units) do
      if bucket[unitID] ~= nil then untrackUnit(unitID, team) end
    end
    return
  end
  untrackUnit(unitID, allyTeam)
  if registeredKings[allyTeam] == unitID then registeredKings[allyTeam] = nil end
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  local oldAlly = allyTeamOfTeam(oldTeam)
  if oldAlly ~= nil then untrackUnit(unitID, oldAlly) end
  local newAlly = allyTeamOfTeam(newTeam)
  if newAlly ~= nil then trackUnit(unitID, unitDefID, newAlly) end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  -- Signature is (unitID, unitDefID, newTeam, oldTeam) for UnitGiven and
  -- (unitID, unitDefID, oldTeam, newTeam) for UnitTaken: mirror the transfer
  -- either way so a gift and a take both land the unit on its new ally team.
  local newAlly = allyTeamOfTeam(newTeam)
  local oldAlly = allyTeamOfTeam(oldTeam)
  if oldAlly ~= nil and oldAlly ~= newAlly then untrackUnit(unitID, oldAlly) end
  if newAlly ~= nil then trackUnit(unitID, unitDefID, newAlly) end
end

function gadget:TeamDied(teamID)
  local allyTeam = allyTeamOfTeam(teamID)
  if allyTeam == nil then return end

  -- Determine whether every team in this alliance is now dead. When the ally
  -- group holds more than one team and at least one other team is still alive,
  -- we must NOT wipe the shared ally bucket: the survivors' units and counters
  -- are still valid. Only a fully-dead alliance is removed wholesale.
  local wipeAll = true
  if type(Spring.GetTeamList) == "function" and type(Spring.GetTeamInfo) == "function" then
    local teamList = Spring.GetTeamList(allyTeam)
    if type(teamList) == "table" and #teamList > 1 then
      for _, other in ipairs(teamList) do
        if other ~= teamID then
          local ok, _, _, isDead = pcall(Spring.GetTeamInfo, other)
          if not (ok and isDead) then
            wipeAll = false
            break
          end
        end
      end
    end
    -- If GetTeamList is not mocked / returns nil or a single team, fall back to
    -- the legacy whole-ally wipe so single-team-per-ally tests keep passing.
  end

  if wipeAll then
    -- The whole alliance is gone: drop its bucket and let the projection report
    -- zeroes, which the policy reads as eliminated under every mode.
    units[allyTeam] = nil
    counts[allyTeam] = newCounts()
    registeredKings[allyTeam] = nil
    return
  end

  -- Another team in this alliance is still alive: remove only this dead team's
  -- units from the shared ally bucket and leave the survivors untouched.
  local bucket = units[allyTeam]
  if bucket then
    for unitID, class in pairs(bucket) do
      if teamOfUnit(unitID) == teamID then
        bucket[unitID] = nil
        applyDelta(allyTeam, class, -1)
      end
    end
  end
  -- If the registered king belonged to the dead team, clear it so a survivor in
  -- this alliance can be re-anchored by ensureKings later.
  local king = registeredKings[allyTeam]
  if king and teamOfUnit(king) == teamID then
    registeredKings[allyTeam] = nil
  end
end

function gadget:GameFrame(frame)
  if status then return end

  -- In regicide mode, make sure kings are spawned once starting Town Centers
  -- exist. Retried on early frames within the spawn window in case GameStart
  -- callin did not fire (e.g. headless stubs or late TC unit creation).
  if MODE == "regicide" and frame < REGICIDE_SPAWN_WINDOW then
    ensureKings()
  end

  if frame % CADENCE_FRAMES ~= 0 then return end
  evaluateNow()
end

-- The engine's terminal callin: log the verdict for the probe and never re-trigger.
function gadget:GameOver(winningAllyTeams)
  gameOverSeen = true
  local winner = status and status.winner or nil
  if winner == nil and type(winningAllyTeams) == "table" then
    winner = next(winningAllyTeams)
  end
  Spring.Echo(string.format("PHASE5 VICTORY gameover-callin winner=%s reason=%s",
    tostring(winner), tostring(status and status.reason)))
end

-- ---------------------------------------------------------------------------
-- Unsynced-side commands
-- ---------------------------------------------------------------------------

-- `/surrender` arrives through the unsynced->synced LuaMsg channel. Validation is
-- deliberately strict: only the caller's own ally team, and only under
-- `surrender` mode (docs/phase-5.md Slice 1).
local function surrenderTeam(allyTeam, frame)
  if allyTeam == nil then return false, "no_team" end
  if MODE ~= "surrender" then return false, "wrong_mode" end
  local state = projection()
  if not victory.canSurrender(state, allyTeam, frame) then
    return false, "too_early"
  end
  if surrendered[allyTeam] then return false, "already" end
  surrendered[allyTeam] = true
  Spring.Echo(string.format("PHASE5 VICTORY surrender allyTeam=%s frame=%s", tostring(allyTeam), tostring(frame)))
  evaluateNow()
  return true
end

-- ---------------------------------------------------------------------------
-- GG API
-- ---------------------------------------------------------------------------

GG.MedievalVictory = GG.MedievalVictory or {}

function GG.MedievalVictory.GetMode()
  return MODE
end

function GG.MedievalVictory.GetStatus()
  return status
end

-- Flat accessors: gadget_medieval_hud.lua probes both `GetWinner`/`GetReason` and
-- the plain `winner`/`reason` fields, so publish both shapes.
function GG.MedievalVictory.GetWinner()
  return status and status.winner or nil
end

function GG.MedievalVictory.GetReason()
  return status and status.reason or nil
end

function GG.MedievalVictory.Evaluate()
  return evaluateNow()
end

function GG.MedievalVictory.SurrenderTeam(allyTeam, frame)
  if frame == nil then frame = Spring.GetGameFrame and Spring.GetGameFrame() or 0 end
  return surrenderTeam(allyTeam, frame)
end

function GG.MedievalVictory.RegisterKing(allyTeam, unitID)
  if allyTeam == nil or unitID == nil then return false end
  registeredKings[allyTeam] = unitID
  return true
end

-- Force a defeat for one ally team (probe/debug lever): marks it eliminated by
-- dropping its counters and re-evaluates.
function GG.MedievalVictory.ForceDefeat(allyTeam)
  if allyTeam == nil then return false end
  initAllyTeam(allyTeam)
  units[allyTeam] = {}
  counts[allyTeam] = newCounts()
  evaluateNow()
  return true
end

function GG.MedievalVictory.GetProjection()
  return projection()
end

function GG.MedievalVictory.IsGameOver()
  return status ~= nil and gameOverSeen
end

function gadget:RecvLuaMsg(msg, playerID)
  if type(msg) ~= "string" then return false end
  if msg ~= "surrender" and msg ~= "/surrender" then return false end
  local _, _, teamID = Spring.GetPlayerInfo(playerID, false)
  local allyTeam = allyTeamOfTeam(teamID)
  local ok, reason = surrenderTeam(allyTeam, Spring.GetGameFrame and Spring.GetGameFrame() or 0)
  if not ok then
    Spring.Echo(string.format("PHASE5 VICTORY surrender refused allyTeam=%s reason=%s",
      tostring(allyTeam), tostring(reason)))
  end
  return true
end
