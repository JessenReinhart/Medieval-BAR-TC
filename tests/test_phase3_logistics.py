"""
Phase-3 tests: medieval logistics, tech research, and fortifications.

Covers the pure module (scripts/medieval_logistics.lua): road/wall/tower
build costs, tech prerequisites and affordability, unlock math, road
proximity + speed, and the iron_swords/plate_armor/masonry damage and
health multipliers. A source-level section pins the gadget wiring (road
feature tracking, tech sync on unit finish, fortification validation, and
the GG.MedievalLogistics public API).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"
ECON_PATH = ROOT / "scripts" / "medieval_economy.lua"


class TestLogisticsCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_road_cost(self):
        self.assertEqual(dict(self.m.getCost("medieval_road")), {"wood": 5, "stone": 2})

    def test_wall_cost(self):
        self.assertEqual(dict(self.m.getCost("medieval_wall")), {"wood": 10, "stone": 40})

    def test_tower_cost(self):
        self.assertEqual(dict(self.m.getCost("medieval_tower")), {"wood": 20, "stone": 50})

    def test_unknown_cost_is_nil(self):
        self.assertIsNone(self.m.getCost("medieval_house"))

    def test_cost_copy_isolated_from_source(self):
        road = self.m.getCost("medieval_road")
        road["wood"] = 999
        self.assertEqual(self.m.COSTS["medieval_road"]["wood"], 5)


class TestLogisticsTech(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        cls.econ = cls.lua.execute(ECON_PATH.read_text(encoding="utf-8"))

    def _stock(self, **kwargs):
        return self.lua.table(**kwargs)

    def _unlocked(self, **kwargs):
        return self.lua.table(**kwargs)

    def test_getTech_returns_definition(self):
        swords = self.m.getTech("iron_swords")
        self.assertIsNotNone(swords)
        self.assertEqual(swords["name"], "Iron Swords")
        self.assertEqual(dict(swords["cost"]), {"wood": 50, "iron": 100})
        self.assertEqual(swords["damage_mult"]["medieval_infantry"], 1.25)
        self.assertFalse(swords["prereq"])
        self.assertIsNone(self.m.getTech("unknown_tech"))

    def test_getTech_plate_armor_has_prereq(self):
        plate = self.m.getTech("plate_armor")
        self.assertEqual(plate["prereq"], "iron_swords")
        self.assertEqual(plate["health_mult"]["medieval_cavalry"], 1.25)

    def test_canResearch_no_prereq_affordable(self):
        # Masonry (stone=150, wood=50) has no prerequisite.
        generous = self._stock(food=1000, wood=1000, stone=1000, iron=1000)
        self.assertTrue(self.m.canResearch(self._unlocked(), "masonry", generous, self.econ))

    def test_canResearch_prereq_met(self):
        # Plate armor requires iron_swords plus iron=150.
        stock = self._stock(iron=200, wood=50, stone=10)
        unlocked = self._unlocked(iron_swords=True)
        self.assertTrue(self.m.canResearch(unlocked, "plate_armor", stock, self.econ))

    def test_canResearch_prereq_missing(self):
        stock = self._stock(iron=200, wood=50, stone=10)
        ok, reason = self.m.canResearch(self._unlocked(), "plate_armor", stock, self.econ)
        self.assertFalse(ok)
        self.assertEqual(reason, "prereq_missing")

    def test_canResearch_already_researched(self):
        unlocked = self._unlocked(iron_swords=True)
        ok, reason = self.m.canResearch(unlocked, "iron_swords", self._stock(iron=200), self.econ)
        self.assertFalse(ok)
        self.assertEqual(reason, "already_researched")

    def test_canResearch_insufficient_resources(self):
        # iron_swords wants iron=100; starting reserves only carry iron=50.
        stock = self.econ.startingStockpiles()
        ok, reason = self.m.canResearch(self._unlocked(), "iron_swords", stock, self.econ)
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_resources")

    def test_canResearch_unknown_tech(self):
        ok, reason = self.m.canResearch(self._unlocked(), "not_a_tech", self._stock(), self.econ)
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_tech")

    def test_canResearch_with_mock_economy_afford(self):
        econ = self.lua.table()
        econ.canAffordCosts = self.lua.eval("function(stock, cost) return true end")
        self.assertTrue(self.m.canResearch(self._unlocked(), "iron_swords", self._stock(), econ))

    def test_canResearch_with_mock_economy_reject(self):
        econ = self.lua.table()
        econ.canAffordCosts = self.lua.eval("function(stock, cost) return false end")
        ok, reason = self.m.canResearch(self._unlocked(), "iron_swords", self._stock(), econ)
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_resources")

    def test_canResearch_skips_cost_check_without_economy(self):
        # No stock/economy supplied: only prereq/already checks run.
        self.assertTrue(self.m.canResearch(self._unlocked(), "masonry"))


class TestLogisticsApplyUnlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_applyUnlock_adds_tech(self):
        out = self.m.applyUnlock(self.lua.table(), "iron_swords")
        self.assertTrue(out["iron_swords"])

    def test_applyUnlock_is_copy_not_mutation(self):
        original = self.lua.table()
        out = self.m.applyUnlock(original, "masonry")
        self.assertFalse(original["masonry"])
        self.assertTrue(out["masonry"])

    def test_applyUnlock_preserves_existing(self):
        original = self.lua.table(iron_swords=True)
        out = self.m.applyUnlock(original, "plate_armor")
        self.assertTrue(out["iron_swords"])
        self.assertTrue(out["plate_armor"])

    def test_applyUnlock_handles_nil_unlocked(self):
        out = self.m.applyUnlock(None, "masonry")
        self.assertTrue(out["masonry"])

    def test_applyUnlock_unknown_tech_is_nil(self):
        self.assertIsNone(self.m.applyUnlock(self.lua.table(), "nope"))


class TestLogisticsRoads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _coords(self, **kwargs):
        return self.lua.table(**kwargs)

    def test_constants(self):
        self.assertEqual(self.m.ROAD_SPEED_MULT, 1.5)
        self.assertEqual(self.m.ROAD_PROXIMITY_RADIUS, 48.0)

    def test_isPositionOnRoad_exact(self):
        roads = self._coords(a=self.lua.table(x=100, z=200))
        self.assertTrue(self.m.isPositionOnRoad(100, 200, roads))

    def test_isPositionOnRoad_within_radius(self):
        roads = self._coords(a=self.lua.table(x=0, z=0))
        # dx=20, dz=20 -> 800 <= 48^2
        self.assertTrue(self.m.isPositionOnRoad(20, 20, roads))

    def test_isPositionOnRoad_outside_radius(self):
        roads = self._coords(a=self.lua.table(x=0, z=0))
        self.assertFalse(self.m.isPositionOnRoad(100, 0, roads))

    def test_isPositionOnRoad_custom_radius(self):
        roads = self._coords(a=self.lua.table(x=0, z=0))
        self.assertTrue(self.m.isPositionOnRoad(10, 0, roads, 10))
        self.assertFalse(self.m.isPositionOnRoad(11, 0, roads, 10))

    def test_isPositionOnRoad_bad_input(self):
        self.assertFalse(self.m.isPositionOnRoad("x", 0, self._coords(a=self.lua.table(x=0, z=0))))
        self.assertFalse(self.m.isPositionOnRoad(0, 0, None))
        # Table without coordinate entries -> no hit.
        self.assertFalse(self.m.isPositionOnRoad(0, 0, self.lua.table(x=0, z=0)))

    def test_speedMultiplier(self):
        self.assertEqual(self.m.speedMultiplier(True), 1.5)
        self.assertEqual(self.m.speedMultiplier(1), 1.5)
        self.assertEqual(self.m.speedMultiplier(False), 1.0)
        self.assertEqual(self.m.speedMultiplier(None), 1.0)


class TestLogisticsMultipliers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_damageMultiplier_iron_swords(self):
        unlocked = self.lua.table(iron_swords=True)
        self.assertAlmostEqual(self.m.damageMultiplier(unlocked, "medieval_infantry"), 1.25)
        self.assertEqual(self.m.damageMultiplier(unlocked, "medieval_cavalry"), 1.0)

    def test_damageMultiplier_no_unlocks(self):
        self.assertEqual(self.m.damageMultiplier(self.lua.table(), "medieval_infantry"), 1.0)
        self.assertEqual(self.m.damageMultiplier(None, "medieval_infantry"), 1.0)

    def test_healthMultiplier_plate_armor(self):
        unlocked = self.lua.table(plate_armor=True)
        self.assertAlmostEqual(self.m.healthMultiplier(unlocked, "medieval_infantry"), 1.25)
        self.assertAlmostEqual(self.m.healthMultiplier(unlocked, "medieval_cavalry"), 1.25)
        self.assertEqual(self.m.healthMultiplier(unlocked, "medieval_archer"), 1.0)

    def test_healthMultiplier_masonry(self):
        unlocked = self.lua.table(masonry=True)
        self.assertAlmostEqual(self.m.healthMultiplier(unlocked, "medieval_wall"), 1.5)
        self.assertAlmostEqual(self.m.healthMultiplier(unlocked, "medieval_tower"), 1.5)
        self.assertEqual(self.m.healthMultiplier(unlocked, "medieval_infantry"), 1.0)

    def test_healthMultiplier_no_unlocks(self):
        self.assertEqual(self.m.healthMultiplier(self.lua.table(), "medieval_wall"), 1.0)
        self.assertEqual(self.m.healthMultiplier(None, "medieval_wall"), 1.0)


class TestModulePurity(unittest.TestCase):
    def test_module_has_no_engine_globals(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("Spring.", "GG.", "VFS.", "gadgetHandler", "UnitDefs", "FeatureDefs"):
            self.assertNotIn(token, src, f"pure module must not reference {token}")


class TestLogisticsGadgetWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_gadget_includes_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_logistics.lua")', self.src)

    def test_road_feature_callins_present(self):
        self.assertRegex(self.src, r"function gadget:FeatureCreated")
        self.assertRegex(self.src, r"function gadget:FeatureDestroyed")
        self.assertIn('fDef.name ~= "medieval_road"', self.src)
        self.assertIn("GetFeatureDefID", self.src)

    def test_tech_applied_on_unit_finished(self):
        self.assertRegex(self.src, r"function gadget:UnitFinished")
        self.assertIn("healthMultiplier", self.src)
        self.assertIn("Spring.SetUnitMaxHealth", self.src)

    def test_fortification_validation_callin(self):
        self.assertRegex(self.src, r"function gadget:AllowUnitCreation")
        self.assertIn("logistics.getCost", self.src)
        self.assertIn("economy.CanAfford", self.src)

    def test_gg_medieval_logistics_api(self):
        self.assertIn("GG.MedievalLogistics", self.src)
        methods = (
            "GetSpeedMultiplier",
            "IsOnRoad",
            "RoadCount",
            "CanResearch",
            "Research",
            "IsResearched",
            "DamageMultiplier",
            "HealthMultiplier",
        )
        for method in methods:
            self.assertIn(method, self.src, f"GG.MedievalLogistics.{method} missing")

    def test_speed_multiplier_derives_from_road(self):
        self.assertIn("logistics.isPositionOnRoad", self.src)
        self.assertIn("logistics.speedMultiplier(onRoad)", self.src)


if __name__ == "__main__":
    unittest.main()