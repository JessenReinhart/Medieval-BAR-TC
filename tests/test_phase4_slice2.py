"""
Phase-4 Slice 2 tests: damage types & fortification destruction.

Covers the pure damage matrix in scripts/medieval_damage_types.lua, the
damage_class / armor_class datadef tags, and the gadget wiring in
gadget_medieval_logistics.lua (GG.MedievalLogistics.DamageTypeMultiplier +
UnitPreDamaged stacking tech * supply * matrix multiplicatively on the real
base damage).
"""

from pathlib import Path
from lupa import LuaRuntime

import unittest

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "scripts" / "medieval_damage_types.lua"
WEAPONDEFS_PATH = ROOT / "gamedata" / "weapondefs.lua"
WALL_PATH = ROOT / "units" / "medieval_wall.lua"
TOWER_PATH = ROOT / "units" / "medieval_tower.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"

# UnitDef / WeaponDef ids used by the gadget harness stubs.
INFANTRY, CATAPULT, ARCHER = 1, 2, 3
WALL, TOWER = 4, 5
TOWN_CENTER, GRANARY = 6, 7
SWORD, CATAPULT_WPN, LONGBOW, LANCE = 10, 11, 12, 13
ROAD_FDEF = 20

BONUS_PER_ENDPOINT = 0.10


class TestSlice2PureMatrix(unittest.TestCase):
    """Pure-module checks against scripts/medieval_damage_types.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MATRIX_PATH.read_text(encoding="utf-8"))

    def test_weapon_and_armor_class_lists(self):
        wc = self.m["WEAPON_CLASSES"]
        ac = self.m["ARMOR_CLASSES"]
        self.assertEqual(len(wc), 3)
        self.assertEqual(wc[1], "siege")
        self.assertEqual(wc[2], "melee")
        self.assertEqual(wc[3], "ranged")
        self.assertEqual(len(ac), 3)
        self.assertEqual(ac[1], "fortification")
        self.assertEqual(ac[2], "building")
        self.assertEqual(ac[3], "standard")

    def test_matrix_is_complete(self):
        for w in ["siege", "melee", "ranged"]:
            for a in ["fortification", "building", "standard"]:
                v = self.m["multiplier"](w, a)
                self.assertIsInstance(v, float)
                self.assertGreaterEqual(v, 0.0)

    def test_matrix_starting_values(self):
        cases = {
            ("siege", "fortification"): 3.0,
            ("siege", "building"): 1.5,
            ("siege", "standard"): 1.0,
            ("melee", "fortification"): 0.25,
            ("melee", "building"): 1.0,
            ("melee", "standard"): 1.0,
            ("ranged", "fortification"): 0.25,
            ("ranged", "building"): 1.0,
            ("ranged", "standard"): 1.0,
        }
        for (w, a), expected in cases.items():
            self.assertAlmostEqual(self.m["multiplier"](w, a), expected)

    def test_unknown_class_is_noop(self):
        self.assertAlmostEqual(self.m["multiplier"]("fire", "fortification"), 1.0)
        self.assertAlmostEqual(self.m["multiplier"]("siege", "unknown"), 1.0)
        self.assertEqual(self.m["multiplier"](None, None), 1.0)

    def test_class_for_unit_def(self):
        self.assertEqual(self.m["classForUnitDef"]("medieval_wall"), "fortification")
        self.assertEqual(self.m["classForUnitDef"]("medieval_tower"), "fortification")
        self.assertEqual(self.m["classForUnitDef"]("medieval_town_center"), "building")
        self.assertEqual(self.m["classForUnitDef"]("medieval_granary"), "building")
        self.assertEqual(self.m["classForUnitDef"]("medieval_infantry"), "standard")
        self.assertEqual(self.m["classForUnitDef"]("medieval_catapult"), "standard")
        self.assertEqual(self.m["classForUnitDef"]("unknown_unit"), "standard")

    def test_class_for_feature_def(self):
        self.assertEqual(self.m["classForFeatureDef"]("medieval_tree"), "standard")
        self.assertEqual(self.m["classForFeatureDef"]("medieval_road"), "standard")
        self.assertEqual(self.m["classForFeatureDef"]("medieval_wall"), "fortification")
        self.assertEqual(self.m["classForFeatureDef"]("medieval_tower"), "fortification")


class TestSlice2DataTags(unittest.TestCase):
    """Datadef tags: weapondef damage_class + unitdef armor_class."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.weapondefs = self.lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        self.wall = self.lua.execute(WALL_PATH.read_text(encoding="utf-8"))
        self.tower = self.lua.execute(TOWER_PATH.read_text(encoding="utf-8"))

    def test_weapon_damage_classes(self):
        self.assertEqual(self.weapondefs["catapult"]["customparams"]["damage_class"], "siege")
        self.assertEqual(self.weapondefs["sword"]["customparams"]["damage_class"], "melee")
        self.assertEqual(self.weapondefs["lance"]["customparams"]["damage_class"], "melee")
        self.assertEqual(self.weapondefs["longbow"]["customparams"]["damage_class"], "ranged")

    def test_fortification_armor_classes(self):
        self.assertEqual(self.wall["medieval_wall"]["customparams"]["armor_class"], "fortification")
        self.assertEqual(self.tower["medieval_tower"]["customparams"]["armor_class"], "fortification")


class TestSlice2GadgetWiring(unittest.TestCase):
    """Real gadget behaviour: matrix applied via GG API + UnitPreDamaged."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        self.lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        self.lua.globals().INFANTRY = INFANTRY
        self.lua.globals().CATAPULT = CATAPULT
        self.lua.globals().ARCHER = ARCHER
        self.lua.globals().WALL = WALL
        self.lua.globals().TOWER = TOWER
        self.lua.globals().TOWN_CENTER = TOWN_CENTER
        self.lua.globals().GRANARY = GRANARY
        self.lua.globals().SWORD = SWORD
        self.lua.globals().CATAPULT_WPN = CATAPULT_WPN
        self.lua.globals().LONGBOW = LONGBOW
        self.lua.globals().LANCE = LANCE
        self.lua.globals().ROAD_FDEF = ROAD_FDEF
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}
        UNITS = {}
        RULES_PARAMS = {}
        TEAM_LIST = {0, 1}
        NEXT_FID = 9000
        gadget = {}
        gadgetHandler = {
          IsSyncedCode = function() return true end,
          RegisterCMDID = function() return true end,
          RegisterAllowCommand = function() return true end,
        }
        CMD = { ANY = 31000 }
        CMDTYPE = { ICON_MAP = 5 }
        GG = {}

        FeatureDefs = { [ROAD_FDEF] = { name = "medieval_road" } }
        UnitDefs = {
          [INFANTRY]    = { name = "medieval_infantry", canMove = true, speed = 32 },
          [CATAPULT]    = { name = "medieval_catapult", canMove = true, speed = 18 },
          [ARCHER]      = { name = "medieval_archer", canMove = true, speed = 30 },
          [WALL]        = { name = "medieval_wall", canMove = false, customParams = { armor_class = "fortification" } },
          [TOWER]       = { name = "medieval_tower", canMove = false, customParams = { armor_class = "fortification" } },
          [TOWN_CENTER] = { name = "medieval_town_center", canMove = false },
          [GRANARY]     = { name = "medieval_granary", canMove = false, customParams = { dropoff = true } },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        -- WeaponDefs expose the Slice 2 damage_class customParams at runtime.
        WeaponDefs = {
          [SWORD]       = { name = "Broadsword", customParams = { damage_class = "melee" } },
          [CATAPULT_WPN] = { name = "Catapult Rock", customParams = { damage_class = "siege" } },
          [LONGBOW]     = { name = "Longbow", customParams = { damage_class = "ranged" } },
          [LANCE]       = { name = "Heavy Lance", customParams = { damage_class = "melee" } },
        }
        WeaponDefNames = {}
        for id, def in pairs(WeaponDefs) do WeaponDefNames[def.name] = { id = id } end

        local RULES_PARAM_FN = function(unitID, key, value)
          RULES_PARAMS[unitID] = RULES_PARAMS[unitID] or {}
          RULES_PARAMS[unitID][key] = value
        end

        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
          GetMapSize = function() return 8000, 8000 end,
          GetGroundHeight = function() return 0 end,
          SetGameRulesParam = function(k, v) GAME_RULES[k] = v end,
          GetAllUnits = function()
            local out = {}
            for id in pairs(UNITS) do table.insert(out, id) end
            table.sort(out)
            return out
          end,
          GetUnitDefID = function(id)
            local u = UNITS[id]
            return u and u.defID or nil
          end,
          GetUnitTeam = function(id)
            local u = UNITS[id]
            return u and u.team or nil
          end,
          GetUnitPosition = function(id)
            local u = UNITS[id]
            if u then return u.x, 0, u.z end
            return nil
          end,
          GetUnitHealth = function(id)
            local u = UNITS[id]
            if u then return u.hp, u.maxHp, false, 0, u.progress end
            return nil
          end,
          SetUnitMaxHealth = function(id, hp)
            local u = UNITS[id]
            if u then u.maxHp = hp end
          end,
          SetUnitHealth = function(id, hp)
            local u = UNITS[id]
            if u then u.hp = hp end
          end,
          GetFeatureDefID = function(id)
            local f = FEATURES[id]
            return f and f.defID or nil
          end,
          GetFeaturePosition = function(id)
            local f = FEATURES[id]
            if f then return f.x, 0, f.z end
            return nil
          end,
          GetFeatureTeam = function(id)
            local f = FEATURES[id]
            return f and f.team or nil
          end,
          CreateFeature = function(name, x, y, z, heading, team)
            local defID
            for id, def in pairs(FeatureDefs) do
              if def.name == name then defID = id end
            end
            if not defID then return nil end
            NEXT_FID = NEXT_FID + 1
            local fid = NEXT_FID
            FEATURES[fid] = { defID = defID, x = x, z = z, team = team or 0 }
            gadget:FeatureCreated(fid, team or 0)
            return fid
          end,
          SetUnitRulesParam = RULES_PARAM_FN,
          MoveCtrl = nil,
        }

        VFS = {
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }

        -- Minimal economy so GG.MedievalLogistics.Research can unlock iron_swords
        -- (a nil stockpiles report skips the affordability gate).
        GG.MedievalEconomy = {
          GetStockpiles = function() return nil end,
        }

        -- Harness helpers ------------------------------------------------------>
        function PlaceUnit(id, defID, x, z, team, progress)
          UNITS[id] = {
            defID = defID, x = x, z = z, team = team,
            progress = progress or 1, hp = 100, maxHp = 100,
          }
        end
        function PlaceBuilding(id, defID, x, z, team)
          PlaceUnit(id, defID, x, z, team, 1)
        end
        function RemoveUnit(id) UNITS[id] = nil end
        function FireInitialize() gadget:Initialize() end
        function FireUnitFinished(id, defID, team)
          local u = UNITS[id]
          if u then u.progress = 1 end
          gadget:UnitFinished(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireUnitDestroyed(id, defID, team)
          local u = UNITS[id]
          gadget:UnitDestroyed(id, defID or (u and u.defID), team or (u and u.team))
          UNITS[id] = nil
        end
        function FireGameFrame(frame) gadget:GameFrame(frame) end
        function FireUnitPreDamaged(defender, damage, attacker, weaponDefID)
          local attackerDefID = attacker and UNITS[attacker] and UNITS[attacker].defID or nil
          local attackerTeam = attacker and UNITS[attacker] and UNITS[attacker].team or nil
          return gadget:UnitPreDamaged(
            defender, UNITS[defender] and UNITS[defender].defID, UNITS[defender] and UNITS[defender].team,
            damage, false, weaponDefID, nil, attacker, attackerDefID, attackerTeam)
        end

        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _place_road(self, team, x, z):
        return self._g("Spring").CreateFeature("medieval_road", float(x), 0.0, float(z), 0, team)

    def _finish_unit(self, unit_id, def_id, team, x, z):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team, 1)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _finish_building(self, unit_id, def_id, team, x, z):
        self._g("PlaceBuilding")(unit_id, def_id, float(x), float(z), team)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _research(self, team, tech):
        self._g("PlaceUnit")(9900, INFANTRY, 5000.0, 5000.0, team, 1)
        return self._api().Research(team, tech)

    # -- GG API ---------------------------------------------------------------

    def test_damage_type_multiplier_api(self):
        api = self._api()
        self.assertAlmostEqual(api.DamageTypeMultiplier("siege", "fortification"), 3.0)
        self.assertAlmostEqual(api.DamageTypeMultiplier("melee", "fortification"), 0.25)
        self.assertAlmostEqual(api.DamageTypeMultiplier("ranged", "fortification"), 0.25)
        self.assertAlmostEqual(api.DamageTypeMultiplier("siege", "building"), 1.5)
        self.assertAlmostEqual(api.DamageTypeMultiplier("siege", "standard"), 1.0)

    # -- UnitPreDamaged wiring ------------------------------------------------

    def test_siege_vs_fortification_is_3x(self):
        # Catapult (weapon class siege) vs wall (armor class fortification).
        self._finish_unit(503, CATAPULT, 0, 5000.0, 5000.0)
        self._finish_building(504, WALL, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(504, 500.0, 503, CATAPULT_WPN)
        self.assertAlmostEqual(damage, 500.0 * 3.0)

    def test_melee_vs_fortification_is_quarter(self):
        # Infantry sword (melee) vs wall (fortification).
        self._finish_unit(513, INFANTRY, 0, 5000.0, 5000.0)
        self._finish_building(514, WALL, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(514, 150.0, 513, SWORD)
        self.assertAlmostEqual(damage, 150.0 * 0.25)

    def test_ranged_vs_fortification_is_quarter(self):
        # Archer longbow (ranged) vs tower (fortification).
        self._finish_unit(523, ARCHER, 0, 5000.0, 5000.0)
        self._finish_building(524, TOWER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(524, 90.0, 523, LONGBOW)
        self.assertAlmostEqual(damage, 90.0 * 0.25)

    def test_melee_vs_standard_is_1x(self):
        self._finish_unit(533, INFANTRY, 0, 5000.0, 5000.0)
        self._finish_unit(534, INFANTRY, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(534, 150.0, 533, SWORD)
        self.assertAlmostEqual(damage, 150.0)

    def test_siege_vs_standard_is_1x(self):
        self._finish_unit(543, CATAPULT, 0, 5000.0, 5000.0)
        self._finish_unit(544, INFANTRY, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(544, 500.0, 543, CATAPULT_WPN)
        self.assertAlmostEqual(damage, 500.0)

    def test_siege_vs_building_nonfort_is_1_5x(self):
        # Town center has no armor_class tag -> classForUnitDef -> "building".
        self._finish_unit(553, CATAPULT, 0, 5000.0, 5000.0)
        self._finish_building(554, TOWN_CENTER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(554, 500.0, 553, CATAPULT_WPN)
        self.assertAlmostEqual(damage, 500.0 * 1.5)

    def test_supply_and_matrix_stack_multiplicatively(self):
        # Supplied infantry (melee) vs wall: base * (1 + 0.10) * 0.25.
        self._place_road(0, 1000, 1000)
        self._finish_building(901, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(902, INFANTRY, 0, 1050.0, 1000.0)
        self._finish_building(903, WALL, 1, 2000.0, 2000.0)
        self._g("FireGameFrame")(15)
        damage, _ = self._g("FireUnitPreDamaged")(903, 100.0, 902, SWORD)
        self.assertAlmostEqual(damage, 100.0 * (1.0 + BONUS_PER_ENDPOINT) * 0.25)

    def test_tech_supply_matrix_stack_multiplicatively(self):
        # iron_swords infantry (1.25), supplied (1.10), vs wall (0.25):
        # final = base * 1.25 * 1.10 * 0.25.
        self._place_road(0, 1000, 1000)
        self._finish_building(911, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(912, INFANTRY, 0, 1050.0, 1000.0)
        self._finish_building(913, WALL, 1, 2000.0, 2000.0)
        self._research(0, "iron_swords")
        self._g("FireGameFrame")(15)
        damage, _ = self._g("FireUnitPreDamaged")(913, 100.0, 912, SWORD)
        self.assertAlmostEqual(damage, 100.0 * 1.25 * (1.0 + BONUS_PER_ENDPOINT) * 0.25)

    def test_unknown_weapon_class_is_noop(self):
        # weaponDefID is nil -> no weapon class -> matrix 1.0 no-op.
        self._finish_unit(923, INFANTRY, 0, 5000.0, 5000.0)
        self._finish_building(924, WALL, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(924, 150.0, 923, None)
        self.assertAlmostEqual(damage, 150.0)


if __name__ == "__main__":
    unittest.main()