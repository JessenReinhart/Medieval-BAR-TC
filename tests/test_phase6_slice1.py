"""
Phase-6 Slice 1 tests: Economic Pacing & Production Build-Costs.

Layers under test, all read from the real repository files:

1. Pure modules -- `scripts/medieval_economy.lua`, `scripts/medieval_gather.lua`,
   `scripts/medieval_market.lua`: engine-free policy constants and rate
   functions, loaded via lupa exactly like tests/test_phase5_slice5.py. Each
   test boots its OWN fresh Lua runtime so no mutated module table leaks.
2. Unit defs -- `units/medieval_villager.lua`, `medieval_house.lua`,
   `medieval_granary.lua`, `medieval_lumber_camp.lua`, `medieval_town_center.lua`,
   `medieval_cart.lua`: build costs, build times, and the
   resource_cost_* / carry_capacity / harvest_rate / pop_provided customparams
   that gate the opening ramp.
3. Opening arithmetic -- starting reserves vs the 4-villager + 1-house build
   order: the order must be affordable, leave a strictly positive food reserve
   (no idle starvation), and fit its production pipeline inside the 90-frame
   opening window.
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]

ECONOMY_PATH = ROOT / "scripts" / "medieval_economy.lua"
GATHER_PATH = ROOT / "scripts" / "medieval_gather.lua"
MARKET_PATH = ROOT / "scripts" / "medieval_market.lua"

UNIT_PATHS = {
    "medieval_villager": ROOT / "units" / "medieval_villager.lua",
    "medieval_house": ROOT / "units" / "medieval_house.lua",
    "medieval_granary": ROOT / "units" / "medieval_granary.lua",
    "medieval_lumber_camp": ROOT / "units" / "medieval_lumber_camp.lua",
    "medieval_town_center": ROOT / "units" / "medieval_town_center.lua",
    "medieval_cart": ROOT / "units" / "medieval_cart.lua",
}


class Slice1Base(unittest.TestCase):
    """Fresh Lua runtime per test; loads the three pure modules."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.economy = self.lua.execute(ECONOMY_PATH.read_text(encoding="utf-8"))
        self.gather = self.lua.execute(GATHER_PATH.read_text(encoding="utf-8"))
        self.market = self.lua.execute(MARKET_PATH.read_text(encoding="utf-8"))

    def _unit(self, name):
        path = UNIT_PATHS[name]
        return self.lua.execute(path.read_text(encoding="utf-8"))[name]


# ---------------------------------------------------------------------------
# 1. Starting reserves (scripts/medieval_economy.lua)
# ---------------------------------------------------------------------------

class TestStartingReserves(Slice1Base):
    def test_reserve_constants(self):
        self.assertEqual(self.economy.STARTING_RESERVES["food"], 200)
        self.assertEqual(self.economy.STARTING_RESERVES["wood"], 200)
        self.assertEqual(self.economy.STARTING_RESERVES["stone"], 100)
        self.assertEqual(self.economy.STARTING_RESERVES["iron"], 50)

    def test_max_stockpile(self):
        self.assertEqual(self.economy.MAX_STOCKPILE, 100000)

    def test_starting_stockpiles_match_reserves(self):
        s = self.economy.startingStockpiles()
        self.assertEqual(s["food"], 200)
        self.assertEqual(s["wood"], 200)
        self.assertEqual(s["stone"], 100)
        self.assertEqual(s["iron"], 50)


# ---------------------------------------------------------------------------
# 2. Opening arithmetic: 4 villagers + 1 house, no idle starvation
# ---------------------------------------------------------------------------

class TestOpeningBuildOrder(Slice1Base):
    def test_four_villagers_and_house_are_affordable(self):
        villager = self._unit("medieval_villager")
        house = self._unit("medieval_house")
        vf = villager["customparams"]["resource_cost_food"]
        hw = house["customparams"]["resource_cost_wood"]

        reserves = self.economy.startingStockpiles()
        self.assertLessEqual(4 * vf, reserves["food"])  # 4 villagers
        self.assertLessEqual(hw, reserves["wood"])      # 1 house

    def test_opening_leaves_positive_food_reserve(self):
        villager = self._unit("medieval_villager")
        vf = villager["customparams"]["resource_cost_food"]
        reserves = self.economy.startingStockpiles()
        self.assertGreater(reserves["food"] - 4 * vf, 0)  # no idle starvation

    def test_opening_passes_atomic_affordability(self):
        villager = self._unit("medieval_villager")
        house = self._unit("medieval_house")
        vf = villager["customparams"]["resource_cost_food"]
        hw = house["customparams"]["resource_cost_wood"]
        costs = self.lua.table(food=4 * vf, wood=hw)
        self.assertTrue(self.economy.canAffordCosts(self.economy.startingStockpiles(), costs))

    def test_four_villagers_produce_inside_90_frames(self):
        villager = self._unit("medieval_villager")
        self.assertLessEqual(4 * villager["buildTime"], 90)

    def test_house_finishes_inside_90_after_first_villager(self):
        villager = self._unit("medieval_villager")
        house = self._unit("medieval_house")
        # Villager #1 done at buildTime; then it builds the house.
        self.assertLessEqual(villager["buildTime"] + house["buildTime"], 90)


# ---------------------------------------------------------------------------
# 3. Gather constants & bounds (scripts/medieval_gather.lua)
# ---------------------------------------------------------------------------

class TestGatherConstants(Slice1Base):
    def test_harvest_rate(self):
        self.assertEqual(self.gather.HARVEST_RATE, 2)

    def test_carry_capacity(self):
        self.assertEqual(self.gather.CARRY_CAPACITY, 10)

    def test_node_capacity_by_type(self):
        caps = self.gather.NODE_CAPACITY_BY_TYPE
        self.assertEqual(caps["medieval_tree"], 500)
        self.assertEqual(caps["medieval_stone"], 400)
        self.assertEqual(caps["medieval_iron"], 300)
        self.assertEqual(caps["medieval_deer"], 250)

    def test_default_node_capacity(self):
        self.assertEqual(self.gather.DEFAULT_NODE_CAPACITY, 500)

    def test_harvest_amount_per_frame(self):
        # 30 frames at rate 2/sec -> exactly 2.0 units harvested.
        amt = self.gather.harvestAmount("medieval_tree", 500, 0, 30)
        self.assertAlmostEqual(amt, 2.0, delta=0.01)


# ---------------------------------------------------------------------------
# 4. Market rate functions (scripts/medieval_market.lua)
# ---------------------------------------------------------------------------

class TestMarketRates(Slice1Base):
    def test_base_rates(self):
        base = self.market.BASE_RATES
        self.assertEqual(base["food"], 1.0)
        self.assertEqual(base["wood"], 1.0)
        self.assertEqual(base["stone"], 1.5)
        self.assertEqual(base["iron"], 2.0)

    def test_elasticity_and_scale(self):
        self.assertEqual(self.market.ELASTICITY, 0.5)
        self.assertEqual(self.market.STOCK_SCALE, 400)
        self.assertEqual(self.market.TRADE_MARGIN, 0.1)

    def test_trade_surplus(self):
        surplus = self.market.TRADE_SURPLUS
        self.assertEqual(surplus["food"], 3)
        self.assertEqual(surplus["wood"], 3)
        self.assertEqual(surplus["stone"], 2)
        self.assertEqual(surplus["iron"], 1)

    def test_balanced_rate_is_pure_base_ratio(self):
        # No stock: balanced, so iron (2.0) costs 2.0 food.
        self.assertAlmostEqual(self.market.rate("food", "iron"), 2.0)

    def test_same_resource_rate_is_one(self):
        self.assertEqual(self.market.rate("wood", "wood"), 1.0)

    def test_elastic_rate_rises_with_scarcity(self):
        # food abundant (200), wood scarce (0): 1 + 0.5*(200-0)/400 = 1.25.
        stock = self.lua.table(food=200, wood=0, stone=0, iron=0)
        self.assertAlmostEqual(self.market.rate("food", "wood", stock), 1.25)


# ---------------------------------------------------------------------------
# 5. Unit def costs, carry capacity, harvest rate, pop_provided
# ---------------------------------------------------------------------------

class TestVillagerDef(Slice1Base):
    def test_identity_and_costs(self):
        v = self._unit("medieval_villager")
        self.assertEqual(v["name"], "Villager")
        self.assertTrue(v["builder"])
        # Phase 6 Slice 1 tunings.
        self.assertEqual(v["buildCostMetal"], 40)
        self.assertEqual(v["buildTime"], 20)
        self.assertEqual(v["customparams"]["resource_cost_food"], 40)

    def test_gather_customparams(self):
        v = self._unit("medieval_villager")
        self.assertEqual(v["customparams"]["carry_capacity"], 10)
        self.assertEqual(v["customparams"]["harvest_rate"], 2)


class TestHouseDef(Slice1Base):
    def test_house_definition(self):
        h = self._unit("medieval_house")
        self.assertEqual(h["customparams"]["pop_provided"], 5)
        self.assertEqual(h["customparams"]["resource_cost_wood"], 60)
        self.assertEqual(h["buildCostMetal"], 60)
        self.assertEqual(h["buildTime"], 25)


class TestTownCenterDef(Slice1Base):
    def test_town_center_definition(self):
        tc = self._unit("medieval_town_center")
        self.assertTrue(tc["isFactory"])
        self.assertEqual(tc["transportCapacity"], 10)
        self.assertEqual(tc["customparams"]["pop_provided"], 10)
        self.assertEqual(tc["buildCostMetal"], 300)
        self.assertEqual(tc["buildTime"], 90)


class TestDropoffDefs(Slice1Base):
    def test_granary(self):
        g = self._unit("medieval_granary")
        self.assertEqual(g["buildCostMetal"], 50)
        self.assertEqual(g["buildTime"], 25)
        self.assertEqual(g["customparams"]["resource_cost_wood"], 50)
        self.assertEqual(g["customparams"]["dropoff_resource"], "food")

    def test_lumber_camp(self):
        lc = self._unit("medieval_lumber_camp")
        self.assertEqual(lc["buildCostMetal"], 50)
        self.assertEqual(lc["buildTime"], 25)
        self.assertEqual(lc["customparams"]["resource_cost_wood"], 50)
        self.assertEqual(lc["customparams"]["dropoff_resource"], "wood")


class TestCartDef(Slice1Base):
    def test_cart_definition(self):
        c = self._unit("medieval_cart")
        self.assertEqual(c["customparams"]["carry_capacity"], 400)
        self.assertEqual(c["buildCostMetal"], 60)
        self.assertEqual(c["buildTime"], 35)
        self.assertEqual(c["customparams"]["resource_cost_wood"], 60)
        self.assertEqual(c["customparams"]["resource_cost_iron"], 10)


if __name__ == "__main__":
    unittest.main()