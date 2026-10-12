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
  return v == 1 or v == true or v == "1" or v == "true"
end

local TACTICS_PROBE = modOptionOn("medievaltactics")

-- Synced state -----------------------------------------------------------------
-- movers[unitID] = { fx, fz, dist, frames, speed } — position-delta sampling for
-- the charge estimator; speed is the moving average distance per frame.
-- stances[unitID]  = "aggressive" | "hold" | "standground"
local movers = {}
local stances = {}

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
  local s = speedOf(unitID)
  return s ~= nil and s <= 0.0
end

local function stanceOf(unitID)
  return stances[unitID] or "aggressive"
end

-- ---------------------------------------------------------------------------
-- Charge motion sampling
-- ---------------------------------------------------------------------------

function gadget:GameFrame(n)
  if not (Spring and Spring.GetAllUnits and Spring.GetUnitPosition and Spring.GetUnitDefID) then
    return
  end
  for _, uid in ipairs(Spring.GetAllUnits() or {}) do
    local defID = Spring.GetUnitDefID(uid)
    local def = unitDef(defID)
    if def and def.canMove and finite(def.speed) and def.speed > 0 then
      local x, _, z = Spring.GetUnitPosition(uid)
      if finite(x) and finite(z) then
        local m = movers[uid]
        if not m then
          m = { fx = x, fz = z, dist = 0, frames = 0, speed = 0 }
        end
        local dx = x - m.fx
        local dz = z - m.fz
        m.dist = m.dist + math.sqrt(dx * dx + dz * dz)
        m.frames = m.frames + 1
        m.fx, m.fz = x, z
        m.speed = m.frames > 0 and (m.dist / m.frames) or 0
        movers[uid] = m
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
  local chargeMult = tactics.chargeMult(speedOf(attackerID), attackerDef.speed)
  local flankMult = 1.0
  if Spring and Spring.GetUnitHeading then
    local ah = Spring.GetUnitHeading(attackerID)
    local dh = Spring.GetUnitHeading(unitID)
    flankMult = tactics.flankMult(ah, dh)
  end
  local braceMult = tactics.braceMult(isStationary(unitID), braceClassOf(unitDefID))
  local stanceMult = tactics.stanceMult(stanceOf(attackerID))
  local attackerClass = braceClassOf(attackerDefID) or attackerDef.name
  local defenderClass = isCavalryDef(unitDefID) and "cavalry" or unitArmorClass(unitDefID)
  local counterMult = tactics.counterCavalryMult(attackerClass, defenderClass)

  local tacticsMult = tactics.composeDamage({
    charge = chargeMult,
    flank = flankMult,
    brace = braceMult,
    stance = stanceMult,
    counter = counterMult,
  })

  local final = damage
    * techMult
    * supplyMult
    * matrixMult
    * garrisonMult
    * tacticsMult

  if final < 0 then final = 0 end

  if Spring and Spring.Echo then
    Spring.Echo(string.format(
      "PHASE5 DAMAGE attacker=%d defender=%d base=%.1f tech=%.3f supply=%.3f matrix=%.3f garrison=%.3f tactics=%.3f final=%.1f",
      attackerID, unitID, damage, techMult, supplyMult, matrixMult, garrisonMult, tacticsMult, final))
  end

  return final, 1.0
end