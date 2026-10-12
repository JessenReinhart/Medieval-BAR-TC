-- Shared, pure medieval tactics policy; no engine calls in this module.
--
-- Loadability contract (docs/phase-5.md architectural goal 1): this file must
-- stay loadable by a bare Lua 5.1/LuaJIT interpreter with no VFS/Spring/GG
-- present, so it never VFS.Include()s a sibling and never touches engine API.
-- The synced gadget (luarules/gadgets/gadget_medieval_tactics.lua) owns every
-- Spring.* call and the single authoritative UnitPreDamaged hook.
--
-- Damage-pipeline contract (docs/phase-5.md architectural goal 2): this module
-- only *computes* the tactical multipliers. The gadget composes them with the
-- Phase 3 tech/supply factors and the Slice 4 garrison factor in one place, so
-- no factor can double-apply. Order is fixed and tested:
--   charge * flank * brace * stance (counter_cavalry is an optional appendix).
local M = {}

-- ---------------------------------------------------------------------------
-- Constants
-- ---------------------------------------------------------------------------

-- Charge: an attacker moving above its base speed ramps toward the max charge
-- multiplier. t = (speed / baseSpeed - 1) / CHARGE_SPEED_THRESHOLD, clamped to
-- [0, 1]; at base speed (or below) there is no charge bonus.
M.CHARGE_SPEED_THRESHOLD = 1.0
M.CHARGE_DMG_MULT_MAX = 1.6

-- Brace: a stationary spear/pike defender sets its weapon against the incoming
-- swing, halving the hit (the charger's momentum is neutralized).
M.BRACE_DMG_REDUCTION = 0.5

-- Anti-cavalry counter: a spear/pike attacker gains this bonus vs cavalry.
M.BRACE_BONUS_VS_CAVALRY = 1.25

-- Flank: rear > side > front.
M.FLANK_SIDE_MULT = 1.15
M.FLANK_REAR_MULT = 1.25

-- Stance: standground trades outgoing damage for defensive posture. `hold`
-- keeps units in place without the damage penalty.
M.STANCE_DEF_DAMAGE_MULT = 0.8
M.STANCE_DEF_ARMOR_MULT = 1.25
M.STANCES = {
  aggressive = true,
  hold = true,
  standground = true,
}

-- Def names / class tokens that can brace (set spears against a charge).
M.BRACE_CLASSES = {
  spear = true,
  pike = true,
  spearman = true,
  pikeman = true,
  medieval_spearman = true,
  medieval_pikeman = true,
}

-- Def names / class tokens that count as cavalry for the counter bonus.
M.CAVALRY_CLASSES = {
  cavalry = true,
  medieval_cavalry = true,
  medieval_knight = true,
}

local function finite(n)
  return type(n) == "number" and n == n and n > -math.huge and n < math.huge
end

-- ---------------------------------------------------------------------------
-- Tactical factors
-- ---------------------------------------------------------------------------

--- Charge multiplier ramping from 1.0 to CHARGE_DMG_MULT_MAX as the attacker's
--- speed rises above baseSpeed. Malformed/base-speed-less inputs return 1.0.
function M.chargeMult(speed, baseSpeed)
  if not finite(speed) or not finite(baseSpeed) or baseSpeed <= 0 then
    return 1.0
  end
  if speed <= baseSpeed then
    return 1.0
  end
  local t = (speed / baseSpeed - 1.0) / M.CHARGE_SPEED_THRESHOLD
  if t < 0 then t = 0 end
  if t > 1 then t = 1 end
  return 1.0 + (M.CHARGE_DMG_MULT_MAX - 1.0) * t
end

--- Directional flank multiplier via the heading-angle dot product.
---
--- Spring.GetUnitHeading returns radians; the dot of the two facing vectors is
--- cos(attackerHeading - defenderHeading). When the attacker approaches from
--- behind the defender's facing (headings aligned) the dot is +1 -> rear;
--- head-on (opposed) is -1 -> front = 1.0; perpendicular is 0 -> side.
function M.flankMult(attackerHeading, defenderHeading)
  if not finite(attackerHeading) or not finite(defenderHeading) then
    return 1.0
  end
  local dot = math.cos(attackerHeading - defenderHeading)
  local side = math.cos(math.pi / 4) -- 45 degree cutoff
  if dot > side then
    return M.FLANK_REAR_MULT
  end
  if dot < -side then
    return 1.0 -- frontal
  end
  return M.FLANK_SIDE_MULT
end

--- Brace reduction for a stationary spear/pike defender. Returns
--- BRACE_DMG_REDUCTION (0.5) only when the defender is stationary AND its class
--- is brace-capable; every other case returns 1.0 (no-op).
function M.braceMult(isStationary, defenderClass)
  if not isStationary then
    return 1.0
  end
  if M.BRACE_CLASSES[defenderClass] then
    return M.BRACE_DMG_REDUCTION
  end
  return 1.0
end

--- Outgoing damage multiplier for the attacker's stance.
---   aggressive  -> 1.0 (full damage)
---   hold        -> 1.0 (holds position, no penalty)
---   standground -> STANCE_DEF_DAMAGE_MULT (0.8)
---   unknown/nil -> 1.0
function M.stanceMult(stance)
  if stance == "standground" then
    return M.STANCE_DEF_DAMAGE_MULT
  end
  return 1.0
end

--- Anti-cavalry counter: a spear/pike attacker deals BRACE_BONUS_VS_CAVALRY to a
--- cavalry defender. Any other pairing returns 1.0.
function M.counterCavalryMult(attackerClass, defenderClass)
  if M.BRACE_CLASSES[attackerClass] and M.CAVALRY_CLASSES[defenderClass] then
    return M.BRACE_BONUS_VS_CAVALRY
  end
  return 1.0
end

--- Compose the tactical factors in the fixed, deterministic order
--- charge * flank * brace * stance. `counter` is an optional anti-cavalry
--- appendix (defaults to 1.0) that the gadget folds in last so the four core
--- flags keep their documented order. Missing/nil parts default to 1.0.
function M.composeDamage(parts)
  parts = parts or {}
  local charge = finite(parts.charge) and parts.charge or 1.0
  local flank = finite(parts.flank) and parts.flank or 1.0
  local brace = finite(parts.brace) and parts.brace or 1.0
  local stance = finite(parts.stance) and parts.stance or 1.0
  local counter = finite(parts.counter) and parts.counter or 1.0
  return charge * flank * brace * stance * counter
end

return M