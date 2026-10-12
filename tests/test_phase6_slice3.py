"""
Phase-6 Slice 3 tests: logistics, hauling and production-flow calibration.

Covers the pure modules + unit defs, each against the real repository files:

1. `scripts/medieval_haul.lua` — the haul pacing constants stay in the pinned
   flat-band relationship (DEFAULT_CART_CAPACITY / HAUL_STEP / DEFICIT_THRESHOLD),
   and `chooseHaulRoute` deterministically drives the wood deficit sink
   (blacksmith) from its dedicated source (lumber camp).
2. `scripts/medieval_logistics.lua` — ROAD_SPEED_MULT and the on-road vs
   off-road speed relationship: a meaningful bonus that never cripples off-road.
3. `scripts/medieval_recruitment.lua` — the recruit/upkeep pacing constants.
4. `units/medieval_blacksmith.lua` / `units/medieval_fletcher.lua` — the craft
   timers (buildTime) and craft costs (resource_cost_*).

Each test boots its OWN fresh Lua runtime (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
UNITS_DIR = ROOT / "units"

HAUL_PATH = SCRIPTS_DIR / "medieval_haul.lua"
LOGISTICS_PATH = SCRIPTS_DIR / "medieval_logistics.lua"
RECRUITMENT_PATH = SCRIPTS_DIR / "medieval_recruitment.lua"
BLACKSMITH_PATH = UNITS_DIR / "medieval_blacksmith.lua"
FLETCHER_PATH = UNITS_DIR / "medieval_fletcher.lua"

# Pacing constants mirrored from the modules (Phase 6 Slice 3 values). The haul,
# road-speed, and upkeep constants are carried over unchanged because Phase 4/3
# tests already pin them; this slice re-pins them and calibrates the craft costs.
DEFAULT_CART_CAPACITY = 400
HAUL_STEP = 25
DEFICIT_THRESHOLD = 80
ROAD_SPEED_MULT = 1.5
UPKEEP_TICK_FRAMES = 90
MILITARY_UPKEEP_FOOD = 1
STARVATION_HP_FRACTION = 0.05

# Craft cadence mirrored from gadget_production_chains.lua (CRAFT_INTERVAL = 30).
# A crafter produces ~1 equipment per 30 frames, so its buildTime must exceed
# that cadence or a player could stand up production faster than it produces.
CRAFT_INTERVAL = 30

# Post-calibration craft timers/costs (units/medieval_blacksmith.lua and
# units/medieval_fletcher.lua).
BLACKSMITH_BUILD_TIME = 60
BLACKSMITH_COST = {"wood": 100, "iron": 80}
FLETCHER_BUILD_TIME = 55
FLETCHER_COST = {"wood": 90, "iron": 20}

# Hub ids for the deterministic routing assertion.
LUMBER_ID, SMITH_ID = 101, 102


def _lua_to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists."""
    if value is None:
        return None
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class TestSlice3HaulPacing(unittest.TestCase):
    """Haul pacing constants and the deterministic deficit routing."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(HAUL_PATH.read_text(encoding="utf-8"))

    def _hubs(self, *pairs):
        out = self.lua.table()
        for hub_id, name in pairs:
            out[hub_id] = self.lua.table(name=name)
        return out

    def _stocks(self, wood=0, iron=0):
        return self.lua.table(wood=wood, iron=iron)

    def _route(self, hubs, stocks):
        return _lua_to_py(
            self.lua, self.m.chooseHaulRoute(0, 1, hubs, stocks, DEFAULT_CART_CAPACITY)
        )

    def test_haul_pacing_constants_stay_pinned(self):
        self.assertEqual(self.m.DEFAULT_CART_CAPACITY, DEFAULT_CART_CAPACITY)
        self.assertEqual(self.m.HAUL_STEP, HAUL_STEP)
        self.assertEqual(self.m.DEFICIT_THRESHOLD, DEFICIT_THRESHOLD)
        # Flat band [HAUL_STEP, DEFICIT_THRESHOLD) with HAUL_STEP strictly below
        # the reorder point, so hauls stream smoothly instead of oscillating.
        self.assertLess(self.m.HAUL_STEP, self.m.DEFICIT_THRESHOLD)

    def test_route_deficit_picks_lumber_to_blacksmith(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        route = self._route(hubs, self._stocks(wood=40))
        self.assertEqual(route["resource"], "wood")
        self.assertEqual(route["from"], LUMBER_ID)
        self.assertEqual(route["to"], SMITH_ID)
        self.assertEqual(route["amount"], HAUL_STEP)


class TestSlice3RoadSpeed(unittest.TestCase):
    """Road speed multiplier and the on/off-road relationship."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(LOGISTICS_PATH.read_text(encoding="utf-8"))

    def test_road_speed_multiplier_stay_pinned(self):
        self.assertEqual(self.m.ROAD_SPEED_MULT, ROAD_SPEED_MULT)

    def test_on_offroad_relationship_meaningful_not_crippling(self):
        on_road = self.m.speedMultiplier(True)
        off_road = self.m.speedMultiplier(False)
        self.assertEqual(on_road, ROAD_SPEED_MULT)
        self.assertEqual(off_road, 1.0)
        # Meaningful: roads are strictly faster than open ground.
        self.assertGreater(on_road, off_road)
        # Not crippling: off-road never drops below base speed.
        self.assertGreaterEqual(off_road, 1.0)

    def test_target_speed_applies_road_bonus(self):
        self.assertAlmostEqual(self.m.targetSpeed(10, True), 10 * ROAD_SPEED_MULT)
        self.assertAlmostEqual(self.m.targetSpeed(10, False), 10)


class TestSlice3RecruitPacing(unittest.TestCase):
    """Recruit/upkeep pacing constants in scripts/medieval_recruitment.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))

    def test_tick_and_upkeep_pacing_constants(self):
        self.assertEqual(self.m.UPKEEP_TICK_FRAMES, UPKEEP_TICK_FRAMES)
        self.assertEqual(self.m.MILITARY_UPKEEP_FOOD, MILITARY_UPKEEP_FOOD)
        self.assertAlmostEqual(self.m.STARVATION_HP_FRACTION, STARVATION_HP_FRACTION)

    def test_upkeep_rates_keyed_by_roster(self):
        self.assertEqual(self.m.UPKEEP["medieval_infantry"], 2)
        self.assertEqual(self.m.UPKEEP["medieval_archer"], 2)
        self.assertEqual(self.m.UPKEEP["medieval_cavalry"], 3)
        self.assertEqual(self.m.UPKEEP["medieval_cart"], 0)

    def test_starved_health_penalty_fraction(self):
        self.assertAlmostEqual(self.m.starvedHealth(100), 100 * (1 - STARVATION_HP_FRACTION))


class TestSlice3CraftCosts(unittest.TestCase):
    """Crafter craft timers (buildTime) and craft costs (resource_cost_*)."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        blacksmith = self.lua.execute(BLACKSMITH_PATH.read_text(encoding="utf-8"))
        fletcher = self.lua.execute(FLETCHER_PATH.read_text(encoding="utf-8"))
        self.blacksmith = _lua_to_py(self.lua, blacksmith["medieval_blacksmith"])
        self.fletcher = _lua_to_py(self.lua, fletcher["medieval_fletcher"])

    def test_blacksmith_craft_timer_and_cost(self):
        self.assertEqual(self.blacksmith["buildTime"], BLACKSMITH_BUILD_TIME)
        self.assertEqual(self.blacksmith["customparams"]["crafting"], "sword")
        self.assertEqual(
            self.blacksmith["customparams"]["resource_cost_wood"],
            BLACKSMITH_COST["wood"],
        )
        self.assertEqual(
            self.blacksmith["customparams"]["resource_cost_iron"],
            BLACKSMITH_COST["iron"],
        )

    def test_fletcher_craft_timer_and_cost(self):
        self.assertEqual(self.fletcher["buildTime"], FLETCHER_BUILD_TIME)
        self.assertEqual(self.fletcher["customparams"]["crafting"], "bow")
        self.assertEqual(
            self.fletcher["customparams"]["resource_cost_wood"],
            FLETCHER_COST["wood"],
        )
        self.assertEqual(
            self.fletcher["customparams"]["resource_cost_iron"],
            FLETCHER_COST["iron"],
        )

    def test_craft_timer_outpaces_the_craft_cadence(self):
        # Each crafter must take longer to build than its 30-frame craft cadence,
        # so a player cannot stand up production buildings faster than they craft.
        for def_ in (self.blacksmith, self.fletcher):
            self.assertGreater(def_["buildTime"], CRAFT_INTERVAL)


if __name__ == "__main__":
    unittest.main()