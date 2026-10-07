import unittest
from pathlib import Path
import lupa
from lupa import LuaRuntime

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestMedievalRecruitmentCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        econ_path = REPO_ROOT / "scripts" / "medieval_economy.lua"
        cls.econ = cls.lua.execute(econ_path.read_text(encoding="utf-8"))

    def test_can_afford_multi_costs(self):
        stock = self.econ.startingStockpiles()  # food:200, wood:200, stone:100, iron:50
        # Barracks cost: wood=150, stone=100
        barracks_cost = self.lua.table(wood=150, stone=100)
        self.assertTrue(self.econ.canAffordCosts(stock, barracks_cost))

        # Too expensive
        expensive_cost = self.lua.table(wood=300, stone=100)
        self.assertFalse(self.econ.canAffordCosts(stock, expensive_cost))

    def test_transact_deducts_resources_atomically(self):
        stock = self.econ.startingStockpiles()
        infantry_cost = self.lua.table(food=30, wood=20, stone=10, iron=5)
        ok = self.econ.transact(stock, infantry_cost)
        self.assertTrue(ok)
        self.assertEqual(stock["food"], 170)
        self.assertEqual(stock["wood"], 180)
        self.assertEqual(stock["stone"], 90)
        self.assertEqual(stock["iron"], 45)

    def test_transact_fails_atomically_on_insufficient(self):
        stock = self.econ.startingStockpiles()
        # Requires 60 iron when team only has 50
        cost = self.lua.table(food=10, wood=10, iron=60)
        ok = self.econ.transact(stock, cost)
        self.assertIsNone(ok)
        # Verify no deduction occurred
        self.assertEqual(stock["food"], 200)
        self.assertEqual(stock["wood"], 200)
        self.assertEqual(stock["iron"], 50)


class TestRecruitmentUnitDefs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)

    def _load_unit(self, name):
        p = REPO_ROOT / "units" / f"{name}.lua"
        t = self.lua.execute(p.read_text(encoding="utf-8"))
        return t[name]

    def test_barracks_def(self):
        b = self._load_unit("medieval_barracks")
        self.assertTrue(b["isFactory"])
        self.assertEqual(b["customparams"]["resource_cost_wood"], 150)
        self.assertEqual(b["customparams"]["resource_cost_stone"], 100)
        opts = [b["buildoptions"][i] for i in range(1, len(b["buildoptions"]) + 1)]
        self.assertIn("medieval_infantry", opts)
        self.assertIn("medieval_archer", opts)

    def test_stables_def(self):
        s = self._load_unit("medieval_stables")
        self.assertTrue(s["isFactory"])
        self.assertEqual(s["customparams"]["resource_cost_wood"], 200)
        self.assertEqual(s["customparams"]["resource_cost_stone"], 120)
        opts = [s["buildoptions"][i] for i in range(1, len(s["buildoptions"]) + 1)]
        self.assertIn("medieval_cavalry", opts)

    def test_military_unit_resource_costs(self):
        inf = self._load_unit("medieval_infantry")
        self.assertEqual(inf["customparams"]["resource_cost_food"], 30)
        self.assertEqual(inf["customparams"]["resource_cost_wood"], 20)

        arc = self._load_unit("medieval_archer")
        self.assertEqual(arc["customparams"]["resource_cost_food"], 25)
        self.assertEqual(arc["customparams"]["resource_cost_wood"], 30)

        cav = self._load_unit("medieval_cavalry")
        self.assertEqual(cav["customparams"]["resource_cost_food"], 50)
        self.assertEqual(cav["customparams"]["resource_cost_iron"], 25)

    def test_villager_can_build_military_structures(self):
        vil = self._load_unit("medieval_villager")
        opts = [vil["buildoptions"][i] for i in range(1, len(vil["buildoptions"]) + 1)]
        self.assertIn("medieval_barracks", opts)
        self.assertIn("medieval_stables", opts)
        self.assertIn("medieval_blacksmith", opts)


class TestMedievalRecruitmentModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        rec_path = REPO_ROOT / "scripts" / "medieval_recruitment.lua"
        cls.recruit = cls.lua.execute(rec_path.read_text(encoding="utf-8"))
        econ_path = REPO_ROOT / "scripts" / "medieval_economy.lua"
        cls.econ = cls.lua.execute(econ_path.read_text(encoding="utf-8"))

    def test_cost_lookup(self):
        self.assertEqual(dict(self.recruit.getCost("medieval_infantry")), {"food": 30, "wood": 20, "stone": 10, "iron": 5})
        self.assertIsNone(self.recruit.getCost("medieval_house"))

    def test_can_afford(self):
        stock = self.econ.startingStockpiles()
        self.assertTrue(self.recruit.canAfford(stock, "medieval_infantry", self.econ))
        self.assertFalse(self.recruit.canAfford(stock, "unknown_unit", self.econ))

    def test_upkeep_arithmetic(self):
        stock = self.lua.table(food=200, wood=200, stone=100, iron=50)
        self.assertTrue(self.recruit.applyUpkeep(stock, 2, 30, 30))
        self.assertEqual(stock["food"], 198)
        poor = self.lua.table(food=1, wood=200, stone=100, iron=50)
        self.assertFalse(self.recruit.applyUpkeep(poor, 2, 30, 30))


if __name__ == "__main__":
    unittest.main()
