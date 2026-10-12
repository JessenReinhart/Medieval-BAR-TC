"""Phase-4 Slice 6 tests: the pure skirmish-AI decision module.

Covers `scripts/medieval_skirmish_ai.lua` — a dependency-free, engine-free policy
module. Every test boots its OWN fresh Lua runtime (no shared setUpClass state)
so one case cannot leak mutated module tables into another.

Layers under test:

1. Constants — build costs (`HOUSE_COST`, `ROAD_COST`, `INFANTRY_COST`), the two
   decision thresholds (`HOUSE_POP_BUFFER`, `ATTACK_ARMY_MIN`) and the gather
   target proportions.
2. Purity — the module must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present, which means no `VFS.Include` and no engine calls in the
   source. This is a hard requirement, not a style preference: the AI gadget
   loads it through `VFS.Include`, but the tests load it directly.
3. Decisions — `canAfford`, `shouldBuildHouse`, `shouldBuildRoad`,
   `shouldRecruit`, `shouldAttack`.
4. Placement & gathering — `selectCandidateRoadPos` (midpoint of the first
   consecutive endpoint pair not already served by a road) and
   `prioritizeGatherResource` (lowest stock/target ratio wins).
5. Dispatch — `decideVillagerAction` ordering (house > road > gather), its
   busy-villager short circuit and its `{ type = "none" }` fallbacks.
6. Legacy gadget contract — the exports the synced
   `luarules/gadgets/gadget_medieval_skirmish_ai.lua` indexes directly
   (`MILITARY_SET`, `newStats`, `normalizeStats`, `countKeys`, `houseSpot`,
   `roadSpot`, `recruitSpot`, `CADENCE_FRAMES`, `ATTACK_RADIUS`).
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_skirmish_ai.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_skirmish_ai.lua"

# Policy constants mirrored from scripts/medieval_skirmish_ai.lua.
HOUSE_COST = {"wood": 60}
ROAD_COST = {"wood": 5, "stone": 2}
INFANTRY_COST = {"food": 30, "wood": 20, "stone": 10, "iron": 5}
HOUSE_POP_BUFFER = 2
ATTACK_ARMY_MIN = 2
GATHER_TARGETS = {"food": 100, "wood": 100, "stone": 50, "iron": 30}
DEFAULT_MAX_ROADS = 5
DEFAULT_MAX_ARMY = 10

# Military roster mirrored from scripts/medieval_recruitment.lua UPKEEP > 0.
MILITARY_NAMES = (
    "medieval_infantry",
    "medieval_archer",
    "medieval_cavalry",
    "medieval_catapult",
    "medieval_men_at_arms",
    "medieval_crossbow",
    "medieval_knight",
)

# Decision function names the module must export.
REQUIRED_FUNCTIONS = (
    "canAfford",
    "shouldBuildHouse",
    "shouldBuildRoad",
    "shouldRecruit",
    "shouldAttack",
    "selectCandidateRoadPos",
    "prioritizeGatherResource",
    "decideVillagerAction",
)

# Legacy exports the synced gadget indexes directly.
GADGET_FUNCTIONS = (
    "newStats",
    "normalizeStats",
    "countKeys",
    "houseSpot",
    "roadSpot",
    "recruitSpot",
    "cadenceHit",
    "militaryDefs",
    "isMilitaryName",
    "validCount",
)


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


class Slice6Base(unittest.TestCase):
    """Fresh module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    # -- helpers -------------------------------------------------------------

    def _stock(self, **resources):
        return self.lua.table(**resources)

    def _full_stock(self):
        return self._stock(food=500, wood=500, stone=500, iron=500)

    def _endpoints(self, *pairs):
        table = self.lua.table()
        for index, (x, z) in enumerate(pairs, start=1):
            table[index] = self.lua.table(x=x, z=z)
        return table

    def _roads(self, *pairs):
        return self._endpoints(*pairs)

    def _candidate(self, endpoints, roads=None, min_distance=None):
        value = self.m.selectCandidateRoadPos(endpoints, roads, min_distance)
        return _lua_to_py(self.lua, value)

    def _action(self, **kwargs):
        defaults = dict(
            villagerID=1,
            isIdle=True,
            currentJob=None,
            pop=5,
            cap=10,
            stock=self._full_stock(),
            endpoints=None,
            roadCount=0,
        )
        defaults.update(kwargs)
        value = self.m.decideVillagerAction(
            defaults["villagerID"],
            defaults["isIdle"],
            defaults["currentJob"],
            defaults["pop"],
            defaults["cap"],
            defaults["stock"],
            defaults["endpoints"],
            defaults["roadCount"],
        )
        return _lua_to_py(self.lua, value)


class TestSlice6Constants(Slice6Base):
    """The cost and threshold contract the gadget spends against."""

    def test_house_cost(self):
        self.assertEqual(dict(self.m.HOUSE_COST), HOUSE_COST)

    def test_road_cost(self):
        self.assertEqual(dict(self.m.ROAD_COST), ROAD_COST)

    def test_infantry_cost(self):
        self.assertEqual(dict(self.m.INFANTRY_COST), INFANTRY_COST)

    def test_pop_buffer_threshold(self):
        self.assertEqual(self.m.HOUSE_POP_BUFFER, HOUSE_POP_BUFFER)

    def test_attack_army_minimum(self):
        self.assertEqual(self.m.ATTACK_ARMY_MIN, ATTACK_ARMY_MIN)

    def test_gather_targets(self):
        self.assertEqual(dict(self.m.GATHER_TARGETS), GATHER_TARGETS)

    def test_optional_defaults(self):
        self.assertEqual(self.m.DEFAULT_MAX_ROADS, DEFAULT_MAX_ROADS)
        self.assertEqual(self.m.DEFAULT_MAX_ARMY, DEFAULT_MAX_ARMY)

    def test_infantry_cost_matches_recruitment_def_cost(self):
        # The AI charges RECRUIT_COST for RECRUIT_DEF; the two must not drift.
        self.assertEqual(dict(self.m.INFANTRY_COST), dict(self.m.RECRUIT_COST))
        self.assertEqual(self.m.RECRUIT_DEF, "medieval_infantry")

    def test_required_functions_exported(self):
        for name in REQUIRED_FUNCTIONS:
            self.assertEqual(
                self.lua.eval("type")(self.m[name]),
                "function",
                f"M.{name} must be a function",
            )

    def test_module_is_a_plain_table(self):
        self.assertEqual(self.lua.eval("type")(self.m), "table")


class TestSlice6Purity(Slice6Base):
    """No engine, no VFS, no sibling-module include."""

    def setUp(self):
        super().setUp()
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_no_vfs_include(self):
        self.assertNotIn('VFS.Include("', self.source)

    def test_no_spring_calls(self):
        calls = re.findall(r"Spring\.[A-Za-z_]+\(|Spring\.[A-Za-z_]+:", self.source)
        self.assertEqual(calls, [])

    def test_no_require(self):
        self.assertNotIn("require(", self.source)

    def test_no_gg_api_calls(self):
        calls = re.findall(r"GG\.[A-Za-z_]+\.[A-Za-z_]+\(", self.source)
        self.assertEqual(calls, [])

    def test_loads_without_any_globals(self):
        # A bare runtime: no VFS, no Spring, no UnitDefs. Loading must succeed
        # and the policy must answer from its arguments alone.
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("Spring"))
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        stock = lua.table(wood=60)
        self.assertTrue(module.shouldBuildHouse(9, 10, stock))

    def test_module_has_no_engine_references_in_comments_only(self):
        # Guards against a future edit adding a real call while keeping the
        # comment that promises purity.
        self.assertNotIn("VFS.Include(", self.source.split("local M = {")[1])


class TestSlice6CanAfford(Slice6Base):
    """canAfford(stock, costTable)."""

    def test_exact_stock_is_affordable(self):
        self.assertTrue(self.m.canAfford(self._stock(wood=60), self.m.HOUSE_COST))

    def test_short_stock_is_not_affordable(self):
        self.assertFalse(self.m.canAfford(self._stock(wood=59), self.m.HOUSE_COST))

    def test_surplus_stock_is_affordable(self):
        self.assertTrue(self.m.canAfford(self._stock(wood=1000), self.m.HOUSE_COST))

    def test_multi_resource_cost_needs_every_entry(self):
        self.assertTrue(
            self.m.canAfford(self._stock(wood=5, stone=2), self.m.ROAD_COST)
        )
        self.assertFalse(
            self.m.canAfford(self._stock(wood=5, stone=1), self.m.ROAD_COST)
        )
        self.assertFalse(self.m.canAfford(self._stock(wood=5), self.m.ROAD_COST))

    def test_missing_resource_counts_as_zero(self):
        self.assertFalse(
            self.m.canAfford(self._stock(food=30, wood=20, stone=10), self.m.INFANTRY_COST)
        )
        self.assertTrue(
            self.m.canAfford(
                self._stock(food=30, wood=20, stone=10, iron=5), self.m.INFANTRY_COST
            )
        )

    def test_empty_cost_table_is_affordable(self):
        self.assertTrue(self.m.canAfford(self._stock(), self.lua.table()))

    def test_nil_stock_is_not_affordable(self):
        self.assertFalse(self.m.canAfford(None, self.m.HOUSE_COST))

    def test_nil_cost_table_is_not_affordable(self):
        self.assertFalse(self.m.canAfford(self._stock(wood=60), None))


class TestSlice6BuildHouse(Slice6Base):
    """shouldBuildHouse(pop, cap, stock)."""

    def test_builds_when_at_the_cap(self):
        self.assertTrue(self.m.shouldBuildHouse(10, 10, self._stock(wood=60)))

    def test_builds_inside_the_buffer(self):
        # cap - pop == HOUSE_POP_BUFFER is inclusive.
        self.assertTrue(self.m.shouldBuildHouse(8, 10, self._stock(wood=60)))

    def test_does_not_build_above_the_buffer(self):
        self.assertFalse(self.m.shouldBuildHouse(7, 10, self._stock(wood=60)))

    def test_does_not_build_without_wood(self):
        self.assertFalse(self.m.shouldBuildHouse(10, 10, self._stock(wood=59)))
        self.assertFalse(self.m.shouldBuildHouse(10, 10, self._stock(stone=500)))

    def test_does_not_build_with_invalid_counts(self):
        stock = self._stock(wood=500)
        self.assertFalse(self.m.shouldBuildHouse(None, 10, stock))
        self.assertFalse(self.m.shouldBuildHouse(5, None, stock))
        self.assertFalse(self.m.shouldBuildHouse(-1, 10, stock))
        self.assertFalse(self.m.shouldBuildHouse(5, 9.5, stock))

    def test_ignores_other_resources(self):
        # Only wood matters for a house; a food-only stockpile is not enough.
        self.assertFalse(self.m.shouldBuildHouse(10, 10, self._stock(food=1000)))


class TestSlice6BuildRoad(Slice6Base):
    """shouldBuildRoad(stock, roadCount, maxRoads)."""

    def test_builds_under_the_default_budget(self):
        self.assertTrue(self.m.shouldBuildRoad(self._stock(wood=5, stone=2), 0))
        self.assertTrue(self.m.shouldBuildRoad(self._stock(wood=5, stone=2), 4))

    def test_default_budget_is_five(self):
        self.assertFalse(self.m.shouldBuildRoad(self._stock(wood=500, stone=500), 5))

    def test_explicit_max_roads_overrides_the_default(self):
        self.assertTrue(
            self.m.shouldBuildRoad(self._stock(wood=500, stone=500), 5, 10)
        )
        self.assertFalse(
            self.m.shouldBuildRoad(self._stock(wood=500, stone=500), 10, 10)
        )

    def test_needs_both_wood_and_stone(self):
        self.assertFalse(self.m.shouldBuildRoad(self._stock(wood=5), 0))
        self.assertFalse(self.m.shouldBuildRoad(self._stock(stone=2), 0))
        self.assertFalse(self.m.shouldBuildRoad(self._stock(wood=4, stone=2), 0))

    def test_nil_road_count_is_treated_as_zero(self):
        self.assertTrue(self.m.shouldBuildRoad(self._stock(wood=5, stone=2), None))

    def test_invalid_max_roads_is_refused(self):
        self.assertFalse(self.m.shouldBuildRoad(self._stock(wood=500, stone=500), 0, -1))


class TestSlice6Recruit(Slice6Base):
    """shouldRecruit(stock, pop, cap, armyCount, maxArmy)."""

    def test_recruits_with_room_and_stock(self):
        self.assertTrue(self.m.shouldRecruit(self._full_stock(), 5, 10, 0))

    def test_refuses_at_the_pop_cap(self):
        self.assertFalse(self.m.shouldRecruit(self._full_stock(), 10, 10, 0))

    def test_refuses_at_the_army_cap(self):
        self.assertFalse(self.m.shouldRecruit(self._full_stock(), 5, 10, 10))

    def test_explicit_max_army_overrides_the_default(self):
        self.assertTrue(self.m.shouldRecruit(self._full_stock(), 5, 10, 2, 3))
        self.assertFalse(self.m.shouldRecruit(self._full_stock(), 5, 10, 3, 3))

    def test_refuses_without_the_full_infantry_cost(self):
        self.assertFalse(
            self.m.shouldRecruit(
                self._stock(food=30, wood=20, stone=10), 5, 10, 0
            )
        )

    def test_nil_army_count_is_treated_as_zero(self):
        self.assertTrue(self.m.shouldRecruit(self._full_stock(), 5, 10, None))

    def test_invalid_pop_or_cap_is_refused(self):
        self.assertFalse(self.m.shouldRecruit(self._full_stock(), None, 10, 0))
        self.assertFalse(self.m.shouldRecruit(self._full_stock(), 5, None, 0))


class TestSlice6Attack(Slice6Base):
    """shouldAttack(armyCount)."""

    def test_attacks_at_the_minimum(self):
        self.assertTrue(self.m.shouldAttack(ATTACK_ARMY_MIN))

    def test_attacks_above_the_minimum(self):
        self.assertTrue(self.m.shouldAttack(12))

    def test_holds_below_the_minimum(self):
        self.assertFalse(self.m.shouldAttack(ATTACK_ARMY_MIN - 1))
        self.assertFalse(self.m.shouldAttack(0))

    def test_invalid_count_does_not_attack(self):
        self.assertIs(self.m.shouldAttack(None), False)
        self.assertIs(self.m.shouldAttack("2"), False)


class TestSlice6RoadPlacement(Slice6Base):
    """selectCandidateRoadPos(endpoints, existingRoads, minDistance)."""

    def test_midpoint_of_the_first_pair(self):
        pos = self._candidate(self._endpoints((0, 0), (100, 0)))
        self.assertEqual(pos, {"x": 50.0, "z": 0.0})

    def test_midpoint_of_a_diagonal_pair(self):
        pos = self._candidate(self._endpoints((0, 0), (60, 80)))
        self.assertEqual(pos, {"x": 30.0, "z": 40.0})

    def test_skips_a_pair_already_linked(self):
        endpoints = self._endpoints((0, 0), (100, 0), (100, 200))
        roads = self._roads((50, 0))
        pos = self._candidate(endpoints, roads)
        self.assertEqual(pos, {"x": 100.0, "z": 100.0})

    def test_returns_nil_when_every_pair_is_linked(self):
        endpoints = self._endpoints((0, 0), (100, 0), (100, 200))
        roads = self._roads((50, 0), (100, 100))
        self.assertIsNone(self._candidate(endpoints, roads))

    def test_min_distance_boundary_is_inclusive(self):
        endpoints = self._endpoints((0, 0), (100, 0))
        # A road exactly minDistance from the midpoint still counts as linked.
        roads = self._roads((50 + 32, 0))
        self.assertIsNone(self._candidate(endpoints, roads, 32.0))
        # One elmo further out and the midpoint is free again.
        pos = self._candidate(endpoints, roads, 31.0)
        self.assertEqual(pos, {"x": 50.0, "z": 0.0})

    def test_returns_nil_with_fewer_than_two_endpoints(self):
        self.assertIsNone(self._candidate(self._endpoints((0, 0))))
        self.assertIsNone(self._candidate(self._endpoints()))
        self.assertIsNone(self._candidate(None))

    def test_malformed_endpoint_is_skipped(self):
        endpoints = self.lua.table()
        endpoints[1] = self.lua.table(x="nope", z=0)
        endpoints[2] = self.lua.table(x=100, z=0)
        self.assertIsNone(self._candidate(endpoints))

    def test_accepts_positional_endpoint_tables(self):
        endpoints = self.lua.table()
        endpoints[1] = self.lua.table(0, 0)
        endpoints[2] = self.lua.table(40, 20)
        pos = self._candidate(endpoints)
        self.assertEqual(pos, {"x": 20.0, "z": 10.0})


class TestSlice6GatherPriority(Slice6Base):
    """prioritizeGatherResource(stock)."""

    def test_empty_stock_gathers_food_first(self):
        self.assertEqual(self.m.prioritizeGatherResource(self._stock()), "food")

    def test_nil_stock_gathers_food_first(self):
        self.assertEqual(self.m.prioritizeGatherResource(None), "food")

    def test_all_targets_met_falls_back_to_order(self):
        self.assertEqual(
            self.m.prioritizeGatherResource(
                self._stock(food=100, wood=100, stone=50, iron=30)
            ),
            "food",
        )

    def test_picks_the_lowest_ratio_not_the_lowest_absolute(self):
        # iron 0/30 and stone 0/50 tie at ratio 0 -> stone precedes iron.
        self.assertEqual(
            self.m.prioritizeGatherResource(
                self._stock(food=100, wood=100, stone=0, iron=0)
            ),
            "stone",
        )

    def test_picks_the_proportionally_scarcest(self):
        # food 40/100 = 0.40 vs wood 39/100 = 0.39 -> wood, even though the
        # absolute food number is larger than the stone/iron gaps.
        self.assertEqual(
            self.m.prioritizeGatherResource(
                self._stock(food=40, wood=39, stone=50, iron=30)
            ),
            "wood",
        )

    def test_iron_wins_when_only_iron_is_missing(self):
        self.assertEqual(
            self.m.prioritizeGatherResource(
                self._stock(food=100, wood=100, stone=50, iron=0)
            ),
            "iron",
        )

    def test_missing_keys_count_as_zero(self):
        self.assertEqual(
            self.m.prioritizeGatherResource(self._stock(food=100, wood=100, stone=50)),
            "iron",
        )

    def test_non_numeric_stock_value_counts_as_zero(self):
        self.assertEqual(
            self.m.prioritizeGatherResource(
                self._stock(food=100, wood=100, stone=50, iron="n/a")
            ),
            "iron",
        )

    def test_result_is_always_a_target_resource(self):
        for resource in ("food", "wood", "stone", "iron"):
            value = self.m.prioritizeGatherResource(self._stock(**{resource: 9999}))
            self.assertIn(value, GATHER_TARGETS)


class TestSlice6VillagerDispatch(Slice6Base):
    """decideVillagerAction(villagerID, isIdle, currentJob, pop, cap, stock, ...)."""

    def test_busy_villager_does_nothing(self):
        action = self._action(isIdle=False, pop=10, cap=10)
        self.assertEqual(action, {"type": "none"})

    def test_busy_villager_ignores_every_other_trigger(self):
        # Even with a housing gap and a full stockpile, a non-idle villager is
        # never reassigned.
        action = self._action(isIdle=False, stock=self._full_stock(), pop=10, cap=10)
        self.assertEqual(action, {"type": "none"})

    def test_house_takes_priority_over_road_and_gather(self):
        action = self._action(
            pop=9,
            cap=10,
            stock=self._stock(wood=100, stone=50),
            endpoints=self._endpoints((0, 0), (100, 0)),
            roadCount=0,
        )
        self.assertEqual(action, {"type": "build_house"})

    def test_road_is_chosen_when_housing_is_not_pressing(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(wood=100, stone=50),
            endpoints=self._endpoints((0, 0), (100, 0)),
            roadCount=0,
        )
        self.assertEqual(action, {"type": "build_road", "x": 50.0, "z": 0.0})

    def test_gather_fallback_when_road_budget_is_exhausted(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(food=100, wood=100, stone=10, iron=30),
            endpoints=self._endpoints((0, 0), (100, 0)),
            roadCount=DEFAULT_MAX_ROADS,
        )
        self.assertEqual(action, {"type": "gather", "resource": "stone"})

    def test_gather_fallback_when_every_endpoint_is_linked(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(food=100, wood=100, stone=10, iron=30),
            endpoints=self._endpoints((0, 0), (100, 0)),
            currentJob=self._roads((50, 0)),
            roadCount=0,
        )
        self.assertEqual(action, {"type": "gather", "resource": "stone"})

    def test_gather_fallback_when_no_endpoints_are_known(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(food=100, wood=100, stone=10, iron=30),
        )
        self.assertEqual(action, {"type": "gather", "resource": "stone"})

    def test_gather_picks_the_scarcest_resource(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(food=0, wood=100, stone=50, iron=30),
        )
        self.assertEqual(action, {"type": "gather", "resource": "food"})

    def test_unaffordable_house_falls_through_to_gather(self):
        # A housing gap with no wood cannot be acted on; the villager gathers
        # instead of idling.
        action = self._action(pop=10, cap=10, stock=self._stock(food=500))
        self.assertEqual(action, {"type": "gather", "resource": "wood"})

    def test_empty_stock_still_dispatches_a_gather(self):
        action = self._action(pop=0, cap=10, stock=self._stock())
        self.assertEqual(action, {"type": "gather", "resource": "food"})

    def test_build_road_carries_numeric_coordinates(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(wood=5, stone=2),
            endpoints=self._endpoints((10, 20), (30, 60)),
            roadCount=0,
        )
        self.assertEqual(action["type"], "build_road")
        self.assertEqual(action["x"], 20.0)
        self.assertEqual(action["z"], 40.0)

    def test_string_current_job_is_treated_as_no_roads(self):
        action = self._action(
            pop=2,
            cap=20,
            stock=self._stock(wood=100, stone=50),
            endpoints=self._endpoints((0, 0), (100, 0)),
            currentJob="gathering",
            roadCount=0,
        )
        self.assertEqual(action, {"type": "build_road", "x": 50.0, "z": 0.0})

    def test_house_decision_does_not_need_endpoints(self):
        action = self._action(
            pop=10, cap=10, stock=self._stock(wood=60), endpoints=None
        )
        self.assertEqual(action, {"type": "build_house"})

    def test_action_type_is_always_present(self):
        cases = (
            dict(isIdle=False),
            dict(pop=10, cap=10, stock=self._stock(wood=60)),
            dict(pop=2, cap=20, stock=self._stock(wood=5, stone=2),
                 endpoints=self._endpoints((0, 0), (10, 0))),
            dict(pop=2, cap=20, stock=self._stock()),
        )
        for case in cases:
            action = self._action(**case)
            self.assertIn("type", action)


class TestSlice6GadgetContract(Slice6Base):
    """Exports the synced gadget indexes directly must keep working."""

    def test_gadget_functions_exported(self):
        for name in GADGET_FUNCTIONS:
            self.assertEqual(
                self.lua.eval("type")(self.m[name]),
                "function",
                f"M.{name} must be a function",
            )

    def test_gadget_constants_exported(self):
        self.assertEqual(self.m.CADENCE_FRAMES, 30)
        self.assertEqual(self.m.ATTACK_RADIUS, 3000)
        self.assertEqual(self.m.RECRUIT_DEF, "medieval_infantry")

    def test_military_set_is_a_name_keyed_set(self):
        for name in MILITARY_NAMES:
            self.assertTrue(
                self.m.MILITARY_SET[name], f"{name} must be in MILITARY_SET"
            )
        # The civilian hauler pays no upkeep and is not a field-army unit.
        self.assertIsNone(self.m.MILITARY_SET["medieval_cart"])
        self.assertIsNone(self.m.MILITARY_SET["medieval_villager"])

    def test_military_set_matches_recruitment_upkeep_roster(self):
        defs = _lua_to_py(self.lua, self.m.militaryDefs())
        self.assertEqual(sorted(defs), sorted(MILITARY_NAMES))

    def test_count_keys(self):
        self.assertEqual(self.m.countKeys(self._stock(a=1, b=2, c=3)), 3)
        self.assertEqual(self.m.countKeys(self.lua.table()), 0)
        self.assertEqual(self.m.countKeys(None), 0)

    def test_new_stats_shape(self):
        stats = _lua_to_py(self.lua, self.m.newStats())
        self.assertEqual(
            sorted(stats),
            sorted(
                [
                    "housesBuilt",
                    "roadsBuilt",
                    "gathersAssigned",
                    "unitsRecruited",
                    "attacksOrdered",
                ]
            ),
        )
        self.assertTrue(all(value == 0 for value in stats.values()))

    def test_normalize_stats_clamps_partial_input(self):
        partial = self.lua.table(housesBuilt=3, roadsBuilt="x", bogus=7)
        stats = _lua_to_py(self.lua, self.m.normalizeStats(partial))
        self.assertEqual(stats["housesBuilt"], 3)
        self.assertEqual(stats["roadsBuilt"], 0)
        self.assertNotIn("bogus", stats)

    def test_normalize_stats_tolerates_nil(self):
        stats = _lua_to_py(self.lua, self.m.normalizeStats(None))
        self.assertEqual(stats["housesBuilt"], 0)

    def test_house_spot_cycles_four_sides_then_expands(self):
        first = self.m.houseSpot(1000, 1000, 0)
        self.assertEqual(tuple(first), (1096, 1096))
        fourth = self.m.houseSpot(1000, 1000, 3)
        self.assertEqual(tuple(fourth), (1096, 904))
        fifth = self.m.houseSpot(1000, 1000, 4)
        self.assertEqual(tuple(fifth), (1192, 1192))
        self.assertIsNone(self.m.houseSpot(None, 1000, 0))

    def test_road_spot_and_recruit_spot(self):
        self.assertEqual(tuple(self.m.roadSpot(100, 200)), (260, 200))
        self.assertEqual(tuple(self.m.recruitSpot(100, 200)), (132, 232))
        self.assertIsNone(self.m.roadSpot(100, None))
        self.assertIsNone(self.m.recruitSpot(None, 200))

    def test_cadence_gate(self):
        self.assertTrue(self.m.cadenceHit(0))
        self.assertTrue(self.m.cadenceHit(30))
        self.assertFalse(self.m.cadenceHit(29))
        self.assertFalse(self.m.cadenceHit(None))

    def test_gadget_source_still_calls_only_exported_names(self):
        source = GADGET_PATH.read_text(encoding="utf-8")
        used = set(re.findall(r"\bai\.([A-Za-z_][A-Za-z0-9_]*)", source))
        for name in sorted(used):
            self.assertNotEqual(
                self.lua.eval("type")(self.m[name]),
                "nil",
                f"gadget uses ai.{name}, which the module does not export",
            )


if __name__ == "__main__":
    unittest.main()
