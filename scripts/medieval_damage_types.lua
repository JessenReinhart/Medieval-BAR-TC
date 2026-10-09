-- Phase 4 Slice 2: damage-type matrix.
--
-- Maps an attacker WEAPON class against a defender ARMOR class to a damage
-- multiplier. The matrix is pure policy: no Spring API, no shared state, so it
-- is loadable by lupa in the test harness exactly like
-- scripts/medieval_logistics.lua.
--
-- Weapon classes:
--   siege  -- catapult rock
--   melee  -- sword, lance
--   ranged -- longbow
--
-- Armor classes:
--   fortification -- medieval_wall, medieval_tower (stone defenses)
--   building      -- non-fortification static buildings (town center, granary, ...)
--   standard      -- everything else (infantry/archer/cavalry/villager/catapult,
--                    resource features, roads, ...)
--
-- Starting values (design constants, documented so future tuning is explicit):
--   siege -> fortification 3.0   (siege engines breach walls fast)
--   siege -> building      1.5   (siege is also good vs buildings, less than vs walls)
--   siege -> standard      1.0
--   melee -> fortification 0.25  (swords bounce off stone)
--   melee -> building      1.0
--   melee -> standard      1.0
--   ranged-> fortification 0.25  (arrows bounce off stone)
--   ranged-> building      1.0
--   ranged-> standard      1.0
--
-- Every weapon class x armor class pair is present; an unknown weapon class
-- falls back to 1.0 (no scaling) so unknown/future attackers are never broken.

local M = {}

M.WEAPON_CLASSES = { "siege", "melee", "ranged" }
M.ARMOR_CLASSES = { "fortification", "building", "standard" }

M.MATRIX = {
  siege = {
    fortification = 3.0,
    building = 1.5,
    standard = 1.0,
  },
  melee = {
    fortification = 0.25,
    building = 1.0,
    standard = 1.0,
  },
  ranged = {
    fortification = 0.25,
    building = 1.0,
    standard = 1.0,
  },
}

-- Armor classes keyed by unitdef name. Fortifications are the two stone defense
-- units; the remaining static settlement buildings are their own "building"
-- class so siege gets the 1.5 building bonus without touching mobile units.
M.FORTIFICATION_UNITS = {
  medieval_wall = true,
  medieval_tower = true,
}

M.BUILDING_UNITS = {
  medieval_town_center = true,
  medieval_house = true,
  medieval_granary = true,
  medieval_lumber_camp = true,
  medieval_barracks = true,
  medieval_stables = true,
  medieval_blacksmith = true,
}

-- Armor class for a unit, resolved by name. Unknown names are "standard".
function M.classForUnitDef(unitDefName)
  if M.FORTIFICATION_UNITS[unitDefName] then return "fortification" end
  if M.BUILDING_UNITS[unitDefName] then return "building" end
  return "standard"
end

-- Armor class for a feature. This TC implements walls and towers as UNITS, and
-- the only features (resource nodes, roads, deer) are non-armored, so everything
-- resolves to "standard". The wall/tower names are kept as a defensive mapping in
-- case a corpse feature of the same name ever appears.
function M.classForFeatureDef(featureDefName)
  if featureDefName == "medieval_wall" or featureDefName == "medieval_tower" then
    return "fortification"
  end
  return "standard"
end

-- Matrix multiplier for a weapon class vs armor class. Unknown weapon or armor
-- classes return 1.0 so the matrix is a no-op for anything not explicitly mapped.
function M.multiplier(weaponClass, armorClass)
  local row = M.MATRIX[weaponClass]
  if not row then return 1.0 end
  return row[armorClass] or 1.0
end

return M