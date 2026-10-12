-- Shared, pure medieval garrison policy; no engine calls in this module.
-- The synced garrison gadget (luarules/gadgets/gadget_medieval_garrison.lua)
-- owns modoption gating, unit tracking, the GG.MedievalGarrison surface, the
-- heal ticks and every engine call, and delegates each "how much" question
-- here so the numbers are unit-testable in isolation.
--
-- Loadability contract: this file must stay loadable by a bare Lua 5.1/LuaJIT
-- interpreter with no VFS/engine present, so it never VFS.Include()s a sibling
-- module and never touches the gadget-global API surface.
--
-- Damage-pipeline contract (docs/phase-5.md, architectural goal 2): this module
-- only *computes* the per-garrison defensive-output multiplier. It never applies
-- it. Slice 5 owns the single UnitPreDamaged hook and composes the multiplier
-- chain (supply -> garrison -> tactics) there, so garrison scaling can never
-- double-apply.
--
-- Totality: every function answers the conservative verdict (1.0 / 0 / false /
-- a zeroed shelter table) for malformed or missing inputs instead of raising, so
-- the gadget can call it with partially-populated state without a pcall guard.
local M = {}

-- Engine transport capacities mirrored by units/medieval_town_center.lua and
-- units/medieval_tower.lua `transportCapacity`. tests/test_phase5_slice4.py
-- asserts the two stay equal.
M.GARRISON_CAP = {
  medieval_town_center = 10,
  medieval_tower = 4,
}

-- Defensive-output scaling per garrisoned ranged unit, additive. A garrisoned
-- archer makes the shelter hit harder; the engine has no dynamic per-volley
-- projectile-count lever, so "more archers" is realized as this deterministic
-- damage multiplier (docs/phase-5.md, Slice 4 engine-limitation note).
M.ARCHER_DAMAGE_PER = 0.15

-- Shelter recovery: one point of HP per unit per heal tick, one tick every
-- HEAL_TICK_FRAMES frames. Deterministic, so a probe can assert the delta.
M.SHELTER_HEAL_PER_TICK = 1
M.HEAL_TICK_FRAMES = 30

-- Only civilians and ranged infantry may shelter; the gate keeps melee and
-- cavalry (and every building) out of the transport primitive.
M.GARRISONABLE = {
  medieval_villager = true,
  medieval_archer = true,
  medieval_crossbow = true,
}

-- Ceiling for the count-only multiplier: the largest shelter in the game.
M.GARRISON_DAMAGE_CAP = 10

-- Radius inside which a hostile unit suspends shelter healing (a besieged
-- shelter stops mending its occupants). Consumed by the gadget's enemy probe.
M.BESIEGE_RADIUS = 350

local function isFinite(n)
  return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end

-- Counts are non-negative integers; anything else collapses to 0.
local function countOf(n)
  if not isFinite(n) then return 0 end
  if n < 0 then return 0 end
  return math.floor(n)
end

local function nameOf(unitDef)
  if type(unitDef) == "string" then return unitDef end
  if type(unitDef) == "table" then return unitDef.name end
  return nil
end

--- Transport capacity of a shelter def name (or def table). 0 = not a shelter.
function M.capacityFor(buildingDef)
  local name = nameOf(buildingDef)
  if type(name) ~= "string" then return 0 end
  return M.GARRISON_CAP[name] or 0
end

--- May this unit def shelter? Accepts a def name or a def table.
function M.garrisonAllowed(unitDef)
  local name = nameOf(unitDef)
  if type(name) ~= "string" then return false end
  return M.GARRISONABLE[name] == true
end

--- Capacity clamp helper: is there room for one more occupant?
function M.maxGarrison(capacity, count)
  local cap = countOf(capacity)
  if cap <= 0 then return false end
  return countOf(count) < cap
end

--- Cap check by building def rather than by raw capacity (docs/phase-5.md).
function M.canGarrison(buildingDef, count)
  return M.maxGarrison(M.capacityFor(buildingDef), count)
end

--- Deterministic defensive-output multiplier for a shelter holding `count`
--- garrisoned units: 1 + min(count, GARRISON_DAMAGE_CAP) * ARCHER_DAMAGE_PER.
--- Application belongs to Slice 5's single UnitPreDamaged hook, never here.
function M.garrison_damage_multiplier(count)
  local cur = countOf(count)
  if cur > M.GARRISON_DAMAGE_CAP then cur = M.GARRISON_DAMAGE_CAP end
  return 1.0 + cur * M.ARCHER_DAMAGE_PER
end

-- Doc-name alias for the same curve (scripts/medieval_garrison.lua spec name).
M.garrisonDamageMult = M.garrison_damage_multiplier

--- HP restored per heal tick to EACH sheltered unit; 0 with nobody inside.
function M.healRate(count)
  if countOf(count) <= 0 then return 0 end
  return M.SHELTER_HEAL_PER_TICK
end

--- HP a single sheltered unit recovers over `frameDelta` elapsed frames,
--- counting only whole heal ticks (docs/phase-5.md `shelterHealFor`).
function M.shelterHealFor(frameDelta)
  return math.floor(countOf(frameDelta) / M.HEAL_TICK_FRAMES) * M.SHELTER_HEAL_PER_TICK
end

--- Pure aggregate the gadget projects into display/probe state:
---   sheltered - at least one occupant inside (after the capacity clamp)
---   heal      - HP per tick per sheltered unit (0 while an enemy is near)
---   bonus     - defensive-output multiplier from garrison_damage_multiplier
function M.shelterState(count, capacity, isEnemyNear)
  local cap = countOf(capacity)
  local effective = countOf(count)
  if cap > 0 and effective > cap then effective = cap end
  if effective > M.GARRISON_DAMAGE_CAP then effective = M.GARRISON_DAMAGE_CAP end

  local sheltered = effective > 0
  local heal = 0
  if sheltered and not isEnemyNear then
    heal = M.healRate(effective)
  end

  return {
    sheltered = sheltered,
    heal = heal,
    bonus = M.garrison_damage_multiplier(effective),
  }
end

return M
