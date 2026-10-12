"""Phase-6 Slice 4 tests: skirmish-AI pacing tuning and reactive strategy.

Covers the Slice-4 balance pass over `scripts/medieval_skirmish_ai.lua` and the
AI-adjacent defensive/victory unit defs (`units/medieval_tower.lua`,
`units/medieval_king.lua`, `units/medieval_wall.lua`).

Layers under test:

1. Tuned pacing constants — `HOUSE_POP_BUFFER` (2 -> 3) and the food gather
   target (100 -> 110) plus the legacy `HOUSE_POP_THRESHOLD` alias kept in
   lock-step; the recruit identity (`RECRUIT_DEF` / `RECRUIT_COST`) is pinned
   as unchanged so the policy and the gadget never drift.
2. Reactive recruit — `ROLE_OF` / `COUNTER_RECRUIT` role classification and
   `computeRatios` / `countRoles` / `majorityRole` / `counterRecruit` pick the
   counter to the opponent's majority unit type (melee -> archer, ranged ->
   cavalry, cavalry -> men_at_arms, siege -> cavalry), with conservative
   nil/empty verdicts for malformed or empty input.
3. Defensive-unit stats read back from the unit defs (tower/wall HP, tower/king
   sight) and the unchanged Phase-5 king HP pin (1200).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_skirmish_ai.lua"
TOWER_PATH = ROOT / "units" / "medieval_tower.lua"
KING_PATH = ROOT / "units" / "medieval_king.lua"
WALL_PATH = ROOT / "units" / "medieval_wall.lua"

# Tuned values pinned from scripts/medieval_skirmish_ai.lua (Phase 6 Slice 4).
HOUSE_POP_BUFFER = 3
HOUSE_POP_THRESHOLD = 3  # legacy alias, lock-step with HOUSE_POP_BUFFER
GATHER_TARGETS = {"food": 110, "wood": 100, "stone": 50, "iron": 30}

# Reactive role classification and counter table (documented in the module).
ROLE_OF = {
    "medieval_infantry": "melee",
    "medieval_men_at_arms": "melee",
    "medieval_archer": "ranged",
    "medieval_crossbow": "ranged",
    "medieval_cavalry": "cavalry",
    "medieval_knight": "cavalry",
    "medieval_catapult": "siege",
}
COUNTER_RECRUIT = {
    "melee": "medieval_archer",
    "ranged": "medieval_cavalry",
    "cavalry": "medieval_men_at_arms",
    "siege": "medieval_cavalry",
}
ROLE_ORDER = ("melee", "ranged", "cavalry", "siege")


class PacingAndReactiveBase(unittest.TestCase):
    """Fresh module instance per test (no shared Lua state)."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _counts(self, **kwargs):
        """Build a Lua def-name -> count map for the opponent field army."""
        return self.lua.table(**kwargs)


class TestPacingConstants(PacingAndReactiveBase):
    def test_house_pop_buffer_tuned(self):
        # Phase 6 Slice 4: 2 -> 3 so housing is pre-built a tick earlier and
        # recruitment never blocks on a nearly-full pop cap.
        self.assertEqual(self.m.HOUSE_POP_BUFFER, HOUSE_POP_BUFFER)

    def test_legacy_house_pop_threshold_aliases_buffer(self):
        # The legacy alias must stay in lock-step with HOUSE_POP_BUFFER.
        self.assertEqual(self.m.HOUSE_POP_THRESHOLD, HOUSE_POP_THRESHOLD)
        self.assertEqual(self.m.HOUSE_POP_THRESHOLD, self.m.HOUSE_POP_BUFFER)

    def test_food_gather_target_tuned(self):
        # Phase 6 Slice 4: food target 100 -> 110 (food is the only standing
        # drain via recruit cost + per-tick upkeep).
        self.assertEqual(dict(self.m.GATHER_TARGETS), GATHER_TARGETS)

    def test_recruit_identity_preserved(self):
        # Not retuned this slice: the AI still trains the base infantry by
        # default and the two cost tables must not drift apart.
        self.assertEqual(self.m.RECRUIT_DEF, "medieval_infantry")
        self.assertEqual(dict(self.m.INFANTRY_COST), dict(self.m.RECRUIT_COST))


class TestReactiveRecruit(PacingAndReactiveBase):
    def test_role_classification_table(self):
        self.assertEqual(dict(self.m.ROLE_OF), ROLE_OF)

    def test_counter_table(self):
        self.assertEqual(dict(self.m.COUNTER_RECRUIT), COUNTER_RECRUIT)

    def test_role_tie_break_order(self):
        order = [self.m.ROLE_ORDER[i] for i in range(1, 5)]
        self.assertEqual(order, list(ROLE_ORDER))

    def test_compute_ratios_distribution(self):
        counts = self._counts(
            medieval_infantry=2, medieval_archer=2, medieval_cavalry=1
        )
        ratios = dict(self.m.computeRatios(counts))
        # 5 total: melee 2, ranged 2, cavalry 1, siege 0.
        self.assertAlmostEqual(ratios["melee"], 0.4)
        self.assertAlmostEqual(ratios["ranged"], 0.4)
        self.assertAlmostEqual(ratios["cavalry"], 0.2)
        self.assertAlmostEqual(ratios["siege"], 0.0)

    def test_count_roles_totals(self):
        counts = self._counts(
            medieval_infantry=3, medieval_crossbow=2, medieval_knight=1
        )
        totals = dict(self.m.countRoles(counts))
        self.assertEqual(totals["melee"], 3)
        self.assertEqual(totals["ranged"], 2)
        self.assertEqual(totals["cavalry"], 1)
        self.assertEqual(totals.get("siege", 0), 0)

    def test_majority_role_per_case(self):
        cases = (
            (dict(medieval_infantry=5, medieval_archer=2, medieval_cavalry=1), "melee"),
            (dict(medieval_archer=3, medieval_crossbow=2, medieval_cavalry=1), "ranged"),
            (dict(medieval_cavalry=4, medieval_knight=1, medieval_archer=2), "cavalry"),
            (dict(medieval_catapult=2, medieval_infantry=1), "siege"),
        )
        for counts_kw, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.m.majorityRole(self.lua.table(**counts_kw)), expected)

    def test_counter_recruit_per_case(self):
        # The AI trains the counter to the opponent's majority unit type.
        cases = (
            (dict(medieval_infantry=5, medieval_archer=2), "medieval_archer"),
            (dict(medieval_archer=3, medieval_crossbow=2), "medieval_cavalry"),
            (dict(medieval_cavalry=4, medieval_knight=1), "medieval_men_at_arms"),
            (dict(medieval_catapult=2, medieval_infantry=1), "medieval_cavalry"),
        )
        for counts_kw, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.m.counterRecruit(self.lua.table(**counts_kw)), expected)

    def test_majority_tie_break_deterministic(self):
        # Equal melee/ranged totals resolve to the earlier ROLE_ORDER entry.
        counts = self._counts(medieval_infantry=2, medieval_archer=2)
        self.assertEqual(self.m.majorityRole(counts), "melee")
        self.assertEqual(self.m.counterRecruit(counts), "medieval_archer")

    def test_non_military_and_bad_values_ignored(self):
        # civvies are never military, and negative/non-numeric counts drop out.
        counts = self._counts(
            medieval_cart=10, medieval_villager=5, medieval_archer=3, medieval_cavalry=-2
        )
        self.assertEqual(self.m.majorityRole(counts), "ranged")

    def test_conservative_malformed(self):
        self.assertIsNone(self.m.majorityRole(None))
        self.assertIsNone(self.m.counterRecruit(None))
        self.assertEqual(dict(self.m.computeRatios(None)), {})
        self.assertEqual(dict(self.m.countRoles(None)), {})

    def test_conservative_empty(self):
        empty = self.lua.table()
        self.assertIsNone(self.m.majorityRole(empty))
        self.assertIsNone(self.m.counterRecruit(empty))
        self.assertEqual(dict(self.m.computeRatios(empty)), {})


class TestDefensiveUnitStats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lua = LuaRuntime(unpack_returned_tuples=True)
        cls.tower = lua.execute(TOWER_PATH.read_text(encoding="utf-8"))["medieval_tower"]
        cls.king = lua.execute(KING_PATH.read_text(encoding="utf-8"))["medieval_king"]
        cls.wall = lua.execute(WALL_PATH.read_text(encoding="utf-8"))["medieval_wall"]

    def test_tower_defensive_stats(self):
        # Phase 6 Slice 4: HP 1500 -> 1800, sight 600 -> 700.
        self.assertEqual(self.tower["maxDamage"], 1800)
        self.assertEqual(self.tower["sightDistance"], 700)
        # Garrison shelter is unchanged (mirrors medieval_garrison GARRISON_CAP).
        self.assertEqual(self.tower["transportCapacity"], 4)
        # Still a sight/garrison anchor, not a combat tower.
        self.assertFalse(self.tower["canAttack"])

    def test_wall_defensive_stats(self):
        # Phase 6 Slice 4: HP 2500 -> 2800 (still below the Town Center's 3000).
        self.assertEqual(self.wall["maxDamage"], 2800)

    def test_king_victory_stats(self):
        # Phase 6 Slice 4: sight 400 -> 500; the objective's durability
        # (maxDamage 1200) is a Phase-5 pin and is intentionally unchanged.
        self.assertEqual(self.king["sightDistance"], 500)
        self.assertEqual(self.king["maxDamage"], 1200)


if __name__ == "__main__":
    unittest.main()