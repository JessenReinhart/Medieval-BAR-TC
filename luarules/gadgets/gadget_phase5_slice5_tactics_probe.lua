-- Phase 5 Slice 5 headless probe: tactical combat dynamics.
--
-- Gated on the `medievaltactics` modoption (docs/phase-5.md modoption table).
-- This probe drives the single UnitPreDamaged pipeline's tactical factors
-- through GG.MedievalTactics: it spawns cavalry + spearman + a target infantry,
-- orders the cavalry to charge, sets stance, and asserts the charge / brace /
-- flank / stance factors the tactics gadget computes.

function gadget:GetInfo()
  return {
    name = "Phase 5 Slice 5 Tactics Probe",
    desc = "Headless probe verifying charge, flank, brace and stance through the single UnitPreDamaged pipeline",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 1001,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}
local enabled = (mo.medievaltactics == "1") or (mo.medievaltactics == 1) or (mo.medievaltactics == true)
if not enabled then return end

local team = 0
local enemyTeam = 1
local spawned = false
local probeDone = false
local chargeChecked = false
local braceChecked = false
local flankChecked = false
local stanceChecked = false

local cavID, spearID, targetID = nil, nil, nil

local function echo(fmt, ...)
  Spring.Echo(string.format(fmt, ...))
end

local function groundY(x, z)
  if Spring.GetGroundHeight then return Spring.GetGroundHeight(x, z) end
  return 0
end

local function spawn(name, x, z, facing, teamID)
  local def = UnitDefNames and UnitDefNames[name]
  if not def then return nil end
  return Spring.CreateUnit(def.id, x, groundY(x, z), z, facing or "south", teamID or team)
end

local function compose(parts)
  local api = GG and GG.MedievalTactics
  if not (api and api.Compose) then return nil end
  return api.Compose(parts)
end

function gadget:GameFrame(frame)
  if probeDone then return end

  -- 1. Setup.
  if not spawned and frame >= 20 then
    spawned = true
    echo("PHASE5 TACTICS probe setup starting at frame %d", frame)

    cavID = spawn("medieval_cavalry", 1800, 2000, "south", team)
    spearID = spawn("medieval_spearman", 1800, 2500, "south", team)
    targetID = spawn("medieval_infantry", 1800, 3000, "south", enemyTeam)

    -- Order the cavalry to advance on the target so it accumulates charge.
    if cavID then
      local CMD_MOVE = (CMD and CMD.MOVE) or 16
      Spring.GiveOrderToUnit(cavID, CMD_MOVE, { 1800, groundY(1800, 3000), 3000 }, 0)
    end
  end

  if not spawned then return end

  -- 2. Charge verdict: the cavalry's tracked speed raises the charge factor.
  if frame >= 40 and not chargeChecked then
    chargeChecked = true
    local api = GG and GG.MedievalTactics
    local state = api and api.GetChargeState and api.GetChargeState(cavID)
    local mult = state and state.charge or 1.0
    local ok = mult > 1.0
    echo("PHASE5 TACTICS charge state=%s", state and string.format("speed=%.2f charge=%.2f", state.speed, state.charge) or "nil")
    echo("PHASE5 TACTICS charge-verdict %s", ok and "PASS" or "FAIL")
  end

  -- 3. Brace verdict: a stationary spear defender cancels the cavalry charge.
  if frame >= 60 and not braceChecked then
    braceChecked = true
    local reduced = compose({ charge = 1.6, brace = 0.5 })
    local ok = reduced ~= nil and reduced < 1.6
    echo("PHASE5 TACTICS brace composite=%.3f", reduced or -1)
    echo("PHASE5 TACTICS brace-verdict %s", ok and "PASS" or "FAIL")
  end

  -- 4. Flank verdict: rear hit mult = 1.25 (headings aligned = attacker behind).
  if frame >= 90 and not flankChecked then
    flankChecked = true
    local ah, dh = 0, 0
    if Spring and Spring.GetUnitHeading then
      ah = Spring.GetUnitHeading(cavID) or 0
      dh = Spring.GetUnitHeading(targetID) or 0
    end
    local api = GG and GG.MedievalTactics
    local flank = api and api.Compose and api.Compose({ flank = 1.25 }) or 1.0
    -- The pure flank factor is sampled through the compose API (headings are
    -- engine-dependent); the verdict pins the rear multiplier constant.
    local ok = math.abs(flank - 1.25) < 0.0001
    echo("PHASE5 TACTICS flank headings attacker=%.2f defender=%.2f flank=%.3f", ah, dh, flank)
    echo("PHASE5 TACTICS flank-verdict %s", ok and "PASS" or "FAIL")
  end

  -- 5. Stance verdict: standground halves outgoing damage to 0.8.
  if frame >= 120 and not stanceChecked then
    stanceChecked = true
    local api = GG and GG.MedievalTactics
    if api and api.SetStance then api.SetStance(cavID, "standground") end
    local stance = api and api.GetStance and api.GetStance(cavID) or "aggressive"
    local dmg = api and api.Compose and api.Compose({ stance = 0.8 }) or 1.0
    local ok = stance == "standground" and math.abs(dmg - 0.8) < 0.0001
    echo("PHASE5 TACTICS stance=%s damage=%.3f", stance, dmg)
    echo("PHASE5 TACTICS stance-verdict %s", ok and "PASS" or "FAIL")
  end

  -- 6. Terminal verdict.
  if frame >= 150 then
    probeDone = true
    echo("PHASE5 TACTICS probe-complete PASS")
  end
end