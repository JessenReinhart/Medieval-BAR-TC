-- Synced medieval tactics: the single authoritative outgoing-damage pipeline.
--
-- Architectural responsibility (docs/phase-5.md goal 2): this is the ONLY
-- gadget that implements UnitPreDamaged. It composes the full deterministic
-- multiplier chain in one place so Phase 3 supply, Slice 4 garrison and Slice 5
-- tactics can never double-apply. The chain, in order, is:
--
--   final = base * tech * supply * matrix * garrison
--           * charge * flank * brace * stance (* counter_cavalry)
--
-- tech / supply are read from GG.MedievalLogistics (the Phase 3 owner), matrix
-- from scripts/medieval_damage_types.lua, garrison from GG.MedievalGarrison
-- (the Slice 4 owner), and the tactical factors from scripts/medieval_tactics.lua.
function gadget:GetInfo()
  return {
    name = "Medieval Tactics",
    desc = "Single authoritative outgoing-damage pipeline: tech * supply * matrix * garrison * charge * flank * brace * stance",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 6,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local tactics = VFS.Include("scripts/medieval_tactics.lua")
local damageTypes = VFS.Include("scripts/medieval_damage_types.lua")

local function modOptionOn(key)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[key]
  -- Default to enabled when the option is unset (covers the unit-test harnesses
  -- that stub GetModOptions to {}); only an explicit "0"/false disables it.
  if v == nil then return true end
  if v == false or tostring(v) == "0" then return false end
  return true
end

local TACTICS_PROBE = modOptionOn("medievaltactics")

-- Synced state -----------------------------------------------------------------
-- movers[unitID] = { fx, fz, dist, frames, speed } — position-delta sampling for
-- the charge estimator; speed is the moving average distance per frame.
-- stances[unitID]  = "aggressive" | "hold" | "standground"
local movers = {}
local stances = {}
local lastAugScan = -1

local function finite(n)
  return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end

local function unitDef(unitDefID)
  return unitDefID and UnitDefs and UnitDefs[unitDefID]
end

-- Weapon damage class: mirrors the read the Phase 3 logistics gadget used, from
-- the same gamedata/weapondefs.lua `damage_class` customparam.
local function weaponDamageClass(weaponDefID)
  local wd = weaponDefID and WeaponDefs and WeaponDefs[weaponDefID]
  if not wd then return nil end
  local cp = wd.customParams or wd.customparams
  return cp and cp.damage_class
end

-- Armor class: customparam first, then the pure damage-type classification.
local function unitArmorClass(unitDefID)
  local def = unitDef(unitDefID)
  if not def then return "standard" end
  local cp = def.customParams or def.customparams
  if cp and cp.armor_class then return cp.armor_class end
  return damageTypes.classForUnitDef(def.name)
end

-- Brace/counter class token for a def: "spear" for brace-capable spear/pike
-- units, otherwise nil (callers fall back to the def name).
local function braceClassOf(unitDefID)
  local def = unitDef(unitDefID)
  if not def then return nil end
  if def.name == "medieval_spearman" or def.name == "medieval_pikeman" then
    return "spear"
  end
  local cp = def.customParams or def.customparams
  if cp and (cp.counter_cavalry == true or cp.brace == true) then
    return cp.brace_class or "spear"
  end
  return nil
end

local function isCavalryDef(unitDefID)
  local def = unitDef(unitDefID)
  if not def then return false end
  if def.name == "medieval_cavalry" or def.name == "medieval_knight" then
    return true
  end
  local cp = def.customParams or def.customparams
  return cp and (cp.unit_class == "cavalry" or cp.cavalry == true)
end

local function speedOf(unitID)
  local m = movers[unitID]
  if m and finite(m.speed) then return m.speed end
  return nil
end

local function isStationary(unitID)
  -- Unmoved / untracked units are stationary; a tiny epsilon avoids treating a
  -- near-zero EMA as "moving" when a unit has just stopped.
  local m = movers[unitID]
  if not m then return true end
  local s = m.speed
  return (s == nil) or (s <= 0.01)
end

local function stanceOf(unitID)
  return stances[unitID] or "aggressive"
end

-- ---------------------------------------------------------------------------
-- Charge motion sampling
-- ---------------------------------------------------------------------------

-- Per-frame position deltas are converted into the same units as Def::speed.
-- At full tilt a unit moves maxVelocity elmos/sec => ~0.12 elmos/frame, while
-- Def::speed = maxVelocity * SPEED_CONVENTION. CHARGE_HEADROOM lets a sustained
-- approach read as a 2× charge ahead the module's max-charge point) so the
-- bonus actually activates on a fast approach instead of staying pinned at base
-- speed forever. The constant is unit-independent (maxVelocity cancels).
local SPRING_FPS = 30
local SPEED_CONVENTION = 15     -- Def::speed = maxVelocity * 15
local CHARGE_HEADROOM = 2       -- full-tilt reads as 2× base speed
local PER_FRAME_TO_SPEED = CHARGE_HEADROOM * SPEED_CONVENTION * SPRING_FPS

local SPEED_DECAY = 0.6         -- EMA factor applied per frame (recent speed)

local function positionOf(unitID)
  if not (Spring and Spring.GetUnitPosition) then return nil end
  local x, _, z = Spring.GetUnitPosition(unitID)
  if not (finite(x) and finite(z)) then return nil end
  return x, z
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  local def = unitDef(unitDefID)
  if not (def and def.canMove and finite(def.speed) and def.speed > 0) then
    return
  end
  movers[unitID] = { fx = nil, fz = nil, speed = 0 }
end

function gadget:GameFrame(n)
  if not (Spring and Spring.GetUnitPosition and Spring.GetUnitDefID) then
    return
  end
  -- Fallback for harnesses that never fire UnitCreated: re-scan the live unit
  -- list occasionally (not every frame) and register any missing movers.
  if n >= lastAugScan + 600 then
    lastAugScan = n
    for _, uid in ipairs(Spring.GetAllUnits and Spring.GetAllUnits() or {}) do
      local did = Spring.GetUnitDefID(uid)
      local d = unitDef(did)
      if d and d.canMove and finite(d.speed) and d.speed > 0 then
        movers[uid] = movers[uid] or { fx = nil, fz = nil, speed = 0 }
      end
    end
  end
  -- Iterate the event-tracked mover set; never rescan GetAllUnits() every frame.
  for uid, m in pairs(movers) do
    local defID = Spring.GetUnitDefID(uid)
    local def = unitDef(defID)
    if not (def and def.canMove and finite(def.speed) and def.speed > 0) then
      movers[uid] = nil
    else
      local x, z = positionOf(uid)
      if not x then
        m.speed = 0
      elseif m.fx == nil then
        m.fx, m.fz = x, z
        m.speed = 0
      else
        local dx = x - m.fx
        local dz = z - m.fz
        m.fx, m.fz = x, z
        local d = math.sqrt(dx * dx + dz * dz)
        if d <= 0.0001 then
          m.speed = 0
        else
          local inst = d * PER_FRAME_TO_SPEED
          m.speed = m.speed * SPEED_DECAY + inst * (1 - SPEED_DECAY)
        end
      end
    end
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  movers[unitID] = nil
  stances[unitID] = nil
end

-- ---------------------------------------------------------------------------
-- GG export surface (additive)
-- ---------------------------------------------------------------------------

function gadget:Initialize()
  GG = GG or {}
  GG.MedievalTactics = GG.MedievalTactics or {}

  GG.MedievalTactics.SetStance = function(unitID, stance)
    if stance and tactics.STANCES[stance] then
      stances[unitID] = stance
      return true
    end
    return false
  end

  GG.MedievalTactics.GetStance = function(unitID)
    return stanceOf(unitID)
  end

  GG.MedievalTactics.GetChargeState = function(unitID)
    local defID = Spring and Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
    local def = unitDef(defID)
    local speed = speedOf(unitID)
    local charge = 1.0
    if speed and def and def.speed then
      charge = tactics.chargeMult(speed, def.speed)
    end
    return { speed = speed or 0, charge = charge }
  end

  GG.MedievalTactics.Compose = function(parts)
    return tactics.composeDamage(parts)
  end

  -- Seed the charge tracker with units already alive so charges register
  -- without waiting for UnitCreated (covers probe harnesses and reloads).
  if Spring and Spring.GetAllUnits and Spring.GetUnitDefID then
    for _, uid in ipairs(Spring.GetAllUnits() or {}) do
      local did = Spring.GetUnitDefID(uid)
      local d = unitDef(did)
      if d and d.canMove and finite(d.speed) and d.speed > 0 then
        movers[uid] = movers[uid] or { fx = nil, fz = nil, speed = 0 }
      end
    end
  end

  if TACTICS_PROBE and Spring.Echo then
    Spring.Echo("PHASE5 TACTICS gadget active (medievaltactics=1)")
  end
end

-- ---------------------------------------------------------------------------
-- The single authoritative outgoing-damage hook
-- ---------------------------------------------------------------------------

function gadget:UnitPreDamaged(unitID, unitDefID, unitTeam, damage, paralyzer, weaponDefID, projectileID, attackerID, attackerDefID, attackerTeam)
  if not attackerID or not attackerDefID then
    return damage, 1.0
  end
  local attackerDef = unitDef(attackerDefID)
  if not attackerDef or not attackerDef.name or not string.find(attackerDef.name, "^medieval_") then
    return damage, 1.0
  end

  -- 1. Tech (Phase 3, owner gadget_medieval_logistics.lua) --------------------
  local logisticsApi = GG and GG.MedievalLogistics
  local techMult = 1.0
  if logisticsApi and logisticsApi.DamageMultiplier then
    techMult = logisticsApi.DamageMultiplier(attackerTeam, attackerDef.name) or 1.0
  end

  -- 2. Supply (Phase 3) ------------------------------------------------------
  local supplyMult = 1.0
  if logisticsApi and logisticsApi.SupplyBonus then
    local bonus = logisticsApi.SupplyBonus(attackerID) or 0.0
    if bonus > 0 then supplyMult = 1.0 + bonus end
  end

  -- 3. Damage-type matrix (Phase 4 Slice 2) ----------------------------------
  local weaponClass = weaponDamageClass(weaponDefID)
  local armorClass = unitArmorClass(unitDefID)
  local matrixMult = damageTypes.multiplier(weaponClass, armorClass)

  -- 4. Garrison (Slice 4) -----------------------------------------------------
  local garrisonApi = GG and GG.MedievalGarrison
  local garrisonMult = 1.0
  if garrisonApi and garrisonApi.GetDamageMult then
    garrisonMult = garrisonApi.GetDamageMult(attackerID) or 1.0
  end

  -- 5. Tactics (Slice 5) ------------------------------------------------------
  local tacticsMult = 1.0
  if modOptionOn("medievaltactics") then
    local chargeMult = tactics.chargeMult(speedOf(attackerID), attackerDef.speed)
    local flankMult = 1.0
    if Spring and Spring.GetUnitHeading then
      local ah = Spring.GetUnitHeading(attackerID)
      local dh = Spring.GetUnitHeading(unitID)
      -- Spring.GetUnitHeading returns 16-bit heading ticks; convert to radians.
      -- Preserve direct radian values (unit tests and mocked engines pass them).
      if ah and math.abs(ah) > 2 * math.pi then ah = ah * math.pi / 32768 end
      if dh and math.abs(dh) > 2 * math.pi then dh = dh * math.pi / 32768 end
      -- If unit positions exist, attack direction is relative to defender facing:
      local ax, az = positionOf(attackerID)
      local ux, uz = positionOf(unitID)
      if ax and az and ux and uz and dh then
        local vx, vz = ux - ax, uz - az
        if vx * vx + vz * vz > 1.0 then
          local attackHeading = math.atan2(vx, vz)
          if finite(attackHeading) then ah = attackHeading end
        end
      end
      flankMult = tactics.flankMult(ah, dh)
    end
    -- Brace only degrades melee cavalry charges, not arrows or siege boulders.
    local braceMult = 1.0
    local wc = weaponDamageClass(weaponDefID)
    local attackerIsCharge =
      (wc == "melee" and isCavalryDef(attackerDefID)) or
      (speedOf(attackerID) or 0) > (attackerDef.speed or 0)
    if attackerIsCharge then
      braceMult = tactics.braceMult(isStationary(unitID), braceClassOf(unitDefID))
    end
    local stanceMult = tactics.stanceMult(stanceOf(attackerID))
    local attackerClass = braceClassOf(attackerDefID) or attackerDef.name
    local defenderClass = isCavalryDef(unitDefID) and "cavalry" or unitArmorClass(unitDefID)
    local counterMult = tactics.counterCavalryMult(attackerClass, defenderClass)

    tacticsMult = tactics.composeDamage({
      charge = chargeMult,
      flank = flankMult,
      brace = braceMult,
      stance = stanceMult,
      counter = counterMult,
    })
  end

  local final = damage
    * techMult
    * supplyMult
    * matrixMult
    * garrisonMult
    * tacticsMult

  -- NaN ~= NaN in Lua, so this exact check also catches and clamps NaN to 0.
  if final ~= final or final < 0 then final = 0 end

  if Spring and Spring.Echo then
    Spring.Echo(string.format(
      "PHASE5 DAMAGE attacker=%d defender=%d base=%.1f tech=%.3f supply=%.3f matrix=%.3f garrison=%.3f tactics=%.3f final=%.1f",
      attackerID, unitID, damage, techMult, supplyMult, matrixMult, garrisonMult, tacticsMult, final))
  end

  -- Under-attack alert for the defender's team. Keyed by team so the klaxon is
  -- rate-limited within the FX gadget; only fire when the defender is a real,
  -- non-Gaia team.
  if final > 0 and unitTeam then
    local gaia = -1
    if Spring and type(Spring.GetGaiaTeamID) == "function" then
      gaia = Spring.GetGaiaTeamID() or -1
    end
    if unitTeam ~= gaia then
      local fx = GG and GG.MedievalFX
      if fx and fx.PlayUnderAttack then
        local x, y, z = positionOf(unitID)
        fx.PlayUnderAttack(unitTeam, x, y, z)
      end
    end
  end

  return final, 1.0
end