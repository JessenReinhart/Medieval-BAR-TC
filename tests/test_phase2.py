"""
Automated unit tests for Phase 2 settlement, economy, and housing systems.
Validates pure modules (scripts/medieval_economy.lua, scripts/medieval_housing.lua,
scripts/medieval_gather.lua) and unit definitions for villagers, town centers,
granaries, lumber camps, and peasant houses.
"""

from pathlib import Path
import unittest
from lupa import LuaRuntime

ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = ROOT / "scripts"
UNITS_DIR = ROOT / "units"
GAMEDATA_DIR = ROOT / "gamedata"


class TestMedievalEconomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        src = (SCRIPTS_DIR / "medieval_economy.lua").read_text(encoding="utf-8")
        cls.econ = cls.lua.execute(src)

    def test_resources_list(self):
        res = [self.econ.RESOURCES[i] for i in range(1, 5)]
        self.assertEqual(res, ["food", "wood", "stone", "iron"])

    def test_valid_resource(self):
        self.assertTrue(self.econ.validResource("food"))
        self.assertTrue(self.econ.validResource("wood"))
        self.assertTrue(self.econ.validResource("stone"))
        self.assertTrue(self.econ.validResource("iron"))
        self.assertFalse(self.econ.validResource("gold"))
        self.assertFalse(self.econ.validResource(123))

    def test_valid_amount(self):
        self.assertTrue(self.econ.validAmount(0))
        self.assertTrue(self.econ.validAmount(50))
        self.assertFalse(self.econ.validAmount(-10))
        self.assertFalse(self.econ.validAmount(1.5))
        self.assertFalse(self.econ.validAmount(float("nan")))
        self.assertFalse(self.econ.validAmount(float("inf")))

    def test_starting_stockpiles(self):
        s = self.econ.startingStockpiles()
        self.assertEqual(s["food"], 200)
        self.assertEqual(s["wood"], 200)
        self.assertEqual(s["stone"], 100)
        self.assertEqual(s["iron"], 50)

    def test_deposit(self):
        s = self.econ.newStockpiles()
        res = self.econ.deposit(s, "food", 50)
        self.assertEqual(res, 50)
        self.assertEqual(s["food"], 50)

        # Deposit invalid resource returns None
        self.assertIsNone(self.econ.deposit(s, "gold", 50))
        # Negative amount returns None
        self.assertIsNone(self.econ.deposit(s, "food", -10))

    def test_withdraw(self):
        s = self.econ.startingStockpiles()
        res = self.econ.withdraw(s, "wood", 50)
        self.assertEqual(res, 150)
        self.assertEqual(s["wood"], 150)

        # Overdraw returns None and does not mutate
        self.assertIsNone(self.econ.withdraw(s, "iron", 200))
        self.assertEqual(s["iron"], 50)

    def test_can_afford(self):
        s = self.econ.startingStockpiles()
        self.assertTrue(self.econ.canAfford(s, "food", 100))
        self.assertTrue(self.econ.canAfford(s, "food", 200))
        self.assertFalse(self.econ.canAfford(s, "food", 201))

    def test_atomic_transaction(self):
        s = self.econ.startingStockpiles()
        costs = self.lua.table_from({"food": 100, "wood": 100})
        self.assertTrue(self.econ.transact(s, costs))
        self.assertEqual(s["food"], 100)
        self.assertEqual(s["wood"], 100)

        # Partial affordability fails atomically
        bad_costs = self.lua.table_from({"food": 50, "iron": 999})
        self.assertIsNone(self.econ.transact(s, bad_costs))
        self.assertEqual(s["food"], 100)  # Unmodified!


class TestMedievalHousing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        src = (SCRIPTS_DIR / "medieval_housing.lua").read_text(encoding="utf-8")
        cls.housing = cls.lua.execute(src)

    def test_baseline_cap(self):
        self.assertEqual(self.housing.computeCap(self.lua.table_from({})), 10)

    def test_building_cap_computation(self):
        buildings = self.lua.table_from({
            "medieval_town_center": 1,
            "medieval_house": 3,
        })
        # Base 10 + TC 10 + 3*5 = 35
        self.assertEqual(self.housing.computeCap(buildings), 35)

    def test_max_cap_clamp(self):
        many = self.lua.table_from({"medieval_house": 100})
        # 10 + 500 = 510, clamped to 300
        self.assertEqual(self.housing.computeCap(many), 300)

    def test_can_support(self):
        self.assertTrue(self.housing.canSupport(10, 20, 1))
        self.assertTrue(self.housing.canSupport(19, 20, 1))
        self.assertFalse(self.housing.canSupport(20, 20, 1))
        self.assertFalse(self.housing.canSupport(19, 20, 2))

    def test_unit_consumes_pop(self):
        self.assertEqual(self.housing.unitConsumesPop("medieval_villager"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_infantry"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_archer"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_cavalry"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_town_center"), 0)
        self.assertEqual(self.housing.unitConsumesPop("medieval_house"), 0)


class TestMedievalGather(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        src = (SCRIPTS_DIR / "medieval_gather.lua").read_text(encoding="utf-8")
        cls.gather = cls.lua.execute(src)

    def test_node_resource_mappings(self):
        self.assertEqual(self.gather.nodeResource("medieval_tree"), "wood")
        self.assertEqual(self.gather.nodeResource("medieval_stone"), "stone")
        self.assertEqual(self.gather.nodeResource("medieval_iron"), "iron")
        self.assertEqual(self.gather.nodeResource("medieval_deer"), "food")

    def test_node_capacities(self):
        self.assertEqual(self.gather.nodeCapacity("medieval_tree"), 500)
        self.assertEqual(self.gather.nodeCapacity("medieval_stone"), 400)
        self.assertEqual(self.gather.nodeCapacity("medieval_iron"), 300)
        self.assertEqual(self.gather.nodeCapacity("medieval_deer"), 250)

    def test_harvest_rate_and_bounds(self):
        # 30 frames at rate 2/sec -> exactly 2.0 units harvested
        amt = self.gather.harvestAmount("medieval_tree", 500, 0, 30)
        self.assertAlmostEqual(amt, 2.0, delta=0.01)

        # Inventory cap prevents overflowing carry capacity (10)
        amt_full = self.gather.harvestAmount("medieval_tree", 500, 9.5, 30)
        self.assertAlmostEqual(amt_full, 0.5, delta=0.01)

        # Empty node yields 0
        self.assertEqual(self.gather.harvestAmount("medieval_tree", 0, 0, 30), 0)

    def test_distance_and_ranges(self):
        self.assertTrue(self.gather.inHarvestRange(100, 100, 120, 100))
        self.assertFalse(self.gather.inHarvestRange(100, 100, 200, 100))
        self.assertTrue(self.gather.inDropoffRange(100, 100, 150, 100))
        self.assertFalse(self.gather.inDropoffRange(100, 100, 300, 100))


class TestPhase2UnitDefinitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)

    def _load_unit(self, name: str) -> dict:
        path = UNITS_DIR / f"{name}.lua"
        self.assertTrue(path.exists(), f"Missing unit def: {path}")
        src = path.read_text(encoding="utf-8")
        table = self.lua.execute(src)
        return table[name]

    def test_villager_definition(self):
        v = self._load_unit("medieval_villager")
        self.assertTrue(v["builder"])
        self.assertTrue(v["canMove"])
        self.assertFalse(v["canAttack"])
        self.assertEqual(v["movementclass"], "BOT2")
        self.assertIn("medieval_house", [v["buildoptions"][i] for i in range(1, len(v["buildoptions"]) + 1)])
        self.assertEqual(v["customparams"]["carry_capacity"], 10)

    def test_town_center_definition(self):
        tc = self._load_unit("medieval_town_center")
        self.assertTrue(tc["isFactory"])
        self.assertFalse(tc["canMove"])
        self.assertEqual(tc["footprintX"], 7)
        self.assertEqual(tc["footprintZ"], 7)
        self.assertEqual(tc["customparams"]["pop_provided"], 10)
        self.assertTrue(tc["customparams"]["dropoff"])

    def test_house_definition(self):
        h = self._load_unit("medieval_house")
        self.assertFalse(h["canMove"])
        self.assertEqual(h["customparams"]["pop_provided"], 5)

    def test_granary_definition(self):
        g = self._load_unit("medieval_granary")
        self.assertTrue(g["customparams"]["dropoff"])
        self.assertEqual(g["customparams"]["dropoff_resource"], "food")

    def test_lumber_camp_definition(self):
        lc = self._load_unit("medieval_lumber_camp")
        self.assertTrue(lc["customparams"]["dropoff"])
        self.assertEqual(lc["customparams"]["dropoff_resource"], "wood")


if __name__ == "__main__":
    unittest.main()
