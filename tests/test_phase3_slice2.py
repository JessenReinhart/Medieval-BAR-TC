"""
Phase-3 Slice 2 tests: buildable detection, road positioning, scaled damage,
and road build-queue validation helpers, plus the gadget damage wiring.

Covers the pure module (scripts/medieval_logistics.lua): isBuildable,
isPositionOnRoad, scaledDamage, and roadBuildQueueValidation. A source-level
section pins the gadget wiring for UnitPreDamaged and the PHASE3 DAMAGE log.
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"


class TestLogisticsBuildable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_isBuildable_fortifications(self):
        self.assertTrue(self.m.isBuildable("medieval_road"))
        self.assertTrue(self.m.isBuildable("medieval_wall"))
        self.assertTrue(self.m.isBuildable("medieval_tower"))

    def test_isBuildable_unit_is_false(self):
        self.assertFalse(self.m.isBuildable("medieval_infantry"))

    def test_isBuildable_unknown_is_false(self):
        self.assertFalse(self.m.isBuildable("medieval_house"))


class TestLogisticsRoadPosition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _coords(self, **kwargs):
        return self.lua.table(**kwargs)

    def test_isPositionOnRoad_basic(self):
        # Basic guard: non-numeric coordinates or a non-table road list never match.
        roads = self._coords(a=self.lua.table(x=0, z=0))
        self.assertFalse(self.m.isPositionOnRoad("x", 0, roads))
        self.assertFalse(self.m.isPositionOnRoad(0, 0, None))

    def test_isPositionOnRoad_onroad(self):
        roads = self._coords(a=self.lua.table(x=100, z=200))
        self.assertTrue(self.m.isPositionOnRoad(100, 200, roads))
        self.assertTrue(self.m.isPositionOnRoad(120, 200, roads))

    def test_isPositionOnRoad_offroad(self):
        roads = self._coords(a=self.lua.table(x=0, z=0))
        self.assertFalse(self.m.isPositionOnRoad(100, 0, roads))


class TestLogisticsScaledDamage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_scaledDamage_scales(self):
        self.assertEqual(self.m.scaledDamage(10.0, 1.25), 12.5)

    def test_scaledDamage_zero(self):
        self.assertEqual(self.m.scaledDamage(0, 1.25), 0)


class TestLogisticsRoadQueueValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _costs(self, **kwargs):
        return self.lua.table(**kwargs)

    def test_roadBuildQueueValidation_affordable(self):
        can_afford = self.lua.eval("function() return true end")
        result = self.m.roadBuildQueueValidation(can_afford, self._costs(wood=5, stone=2))
        self.assertEqual(result, "ok")

    def test_roadBuildQueueValidation_insufficient(self):
        result = self.m.roadBuildQueueValidation(False, self._costs(wood=5, stone=2))
        self.assertEqual(result, "insufficient_resources")


class TestLogisticsGadgetWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_unit_predamaged_callin(self):
        self.assertIn("UnitPreDamaged", self.src)
        self.assertRegex(self.src, r"function gadget:UnitPreDamaged")

    def test_phase3_damage_log(self):
        self.assertIn("PHASE3 DAMAGE", self.src)

    def test_scaled_damage_wired(self):
        self.assertIn("logistics.scaledDamage(damage, 1.25)", self.src)


if __name__ == "__main__":
    unittest.main()