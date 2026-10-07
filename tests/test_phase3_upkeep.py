"""
Phase-3 tests: standing-army food upkeep and the starvation penalty.

Covers the pure module (scripts/medieval_recruitment.lua) exactly like the
Phase-2 tests do: armyUpkeep summing, the starvation marker feedback, and the
non-lethal HP penalty math. A light source-level section pins the gadget
wiring (90-frame tick, GG.MedievalEconomy charge, team_<id>_starving param).
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_recruitment.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_recruitment.lua"

BUILDINGS_AND_TOWNS = (
    "medieval_town_center",
    "medieval_house",
    "medieval_granary",
    "medieval_lumber_camp",
    "medieval_barracks",
    "medieval_stables",
    "medieval_blacksmith",
)


class TestArmyUpkeep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.recruit = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _counts(self, **kwargs):
        return self.lua.table(**kwargs)

    def test_upkeep_rates(self):
        self.assertEqual(self.recruit.UPKEEP["medieval_infantry"], 2)
        self.assertEqual(self.recruit.UPKEEP["medieval_archer"], 2)
        self.assertEqual(self.recruit.UPKEEP["medieval_cavalry"], 3)
        self.assertEqual(self.recruit.UPKEEP_TICK_FRAMES, 90)

    def test_upkeep_for_and_is_military(self):
        self.assertEqual(self.recruit.upkeepFor("medieval_cavalry"), 3)
        self.assertEqual(self.recruit.upkeepFor("medieval_villager"), 0)
        self.assertEqual(self.recruit.upkeepFor("medieval_granary"), 0)
        self.assertEqual(self.recruit.upkeepFor(123), 0)
        self.assertTrue(self.recruit.isMilitary("medieval_infantry"))
        self.assertFalse(self.recruit.isMilitary("medieval_villager"))
        self.assertFalse(self.recruit.isMilitary("medieval_town_center"))

    def test_army_upkeep_sums(self):
        counts = self._counts(medieval_infantry=3, medieval_archer=2, medieval_cavalry=1)
        # 3*2 + 2*2 + 1*3 = 13 food per tick
        self.assertEqual(self.recruit.armyUpkeep(counts), 13)

    def test_army_upkeep_single_unit_types(self):
        self.assertEqual(self.recruit.armyUpkeep(self._counts(medieval_infantry=1)), 2)
        self.assertEqual(self.recruit.armyUpkeep(self._counts(medieval_archer=1)), 2)
        self.assertEqual(self.recruit.armyUpkeep(self._counts(medieval_cavalry=1)), 3)
        self.assertEqual(self.recruit.armyUpkeep(self._counts(medieval_cavalry=10)), 30)

    def test_army_upkeep_ignores_non_military(self):
        counts = self.lua.table(**{name: 4 for name in BUILDINGS_AND_TOWNS})
        counts["medieval_villager"] = 12
        self.assertEqual(self.recruit.armyUpkeep(counts), 0)

    def test_army_upkeep_mixed_military_and_civilians(self):
        counts = self.lua.table(**{
            "medieval_infantry": 2,
            "medieval_villager": 9,
            "medieval_house": 3,
        })
        self.assertEqual(self.recruit.armyUpkeep(counts), 4)

    def test_army_upkeep_ignores_bad_counts(self):
        counts = self.lua.table(**{"medieval_infantry": -5})
        counts["medieval_cavalry"] = 0
        self.assertEqual(self.recruit.armyUpkeep(counts), 0)
        fractional = self.lua.table(**{"medieval_infantry": 2.7})
        self.assertEqual(self.recruit.armyUpkeep(fractional), 4)

    def test_army_upkeep_handles_empty_and_non_table(self):
        self.assertEqual(self.recruit.armyUpkeep(self.lua.table()), 0)
        self.assertEqual(self.recruit.armyUpkeep(None), 0)
        self.assertEqual(self.recruit.armyUpkeep("medieval_infantry"), 0)

    def test_army_counts_folds_name_list(self):
        names = self.lua.eval(
            '{ "medieval_cavalry", "medieval_cavalry", "medieval_infantry",'
            ' "medieval_villager", "medieval_town_center", "medieval_house" }'
        )
        counts = self.recruit.armyCounts(names)
        self.assertEqual(counts["medieval_cavalry"], 2)
        self.assertEqual(counts["medieval_infantry"], 1)
        self.assertIsNone(counts["medieval_villager"])
        self.assertIsNone(counts["medieval_town_center"])
        # Folding then summing matches the hand-written count table: 2*3 + 1*2.
        self.assertEqual(self.recruit.armyUpkeep(counts), 8)

    def test_army_counts_empty_input(self):
        self.assertEqual(self.recruit.armyUpkeep(self.recruit.armyCounts(None)), 0)


class TestStarvationMarker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.recruit = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_marker_fed_when_food_covers_upkeep(self):
        counts = self.lua.table(**{"medieval_infantry": 3, "medieval_cavalry": 1})  # 9 food
        self.assertEqual(self.recruit.starvationMarker(50, counts), 0)
        self.assertEqual(self.recruit.starvationMarker(9, counts), 0)  # exact cover
        self.assertEqual(self.recruit.starvationMarker(0, self.lua.table()), 0)

    def test_marker_starving_when_food_short(self):
        counts = self.lua.table(**{"medieval_infantry": 3, "medieval_cavalry": 1})  # 9 food
        self.assertEqual(self.recruit.starvationMarker(8, counts), 1)
        self.assertEqual(self.recruit.starvationMarker(0, counts), 1)
        self.assertEqual(self.recruit.starvationMarker(-4, counts), 1)

    def test_marker_nil_for_unusable_balance(self):
        counts = self.lua.table(**{"medieval_infantry": 1})
        self.assertIsNone(self.recruit.starvationMarker(None, counts))
        self.assertIsNone(self.recruit.starvationMarker("lots", counts))

    def test_pay_upkeep_charges_food_when_covered(self):
        stock = self.lua.table(food=100, wood=200, stone=100, iron=50)
        counts = self.lua.table(**{"medieval_infantry": 2, "medieval_archer": 2, "medieval_cavalry": 2})
        marker = self.recruit.payUpkeep(stock, counts)  # 2+2+2+2+3+3 = 14
        self.assertEqual(marker, 0)
        self.assertEqual(stock["food"], 86)
        # Other resources untouched.
        self.assertEqual(stock["wood"], 200)
        self.assertEqual(stock["stone"], 100)
        self.assertEqual(stock["iron"], 50)

    def test_pay_upkeep_reports_starving_and_keeps_stock(self):
        stock = self.lua.table(food=5, wood=200)
        counts = self.lua.table(**{"medieval_cavalry": 4})  # 12 food needed
        marker = self.recruit.payUpkeep(stock, counts)
        self.assertEqual(marker, 1)
        self.assertEqual(stock["food"], 5)  # no partial charge

    def test_pay_upkeep_repeats_drain_until_starving(self):
        stock = self.lua.table(food=10)
        counts = self.lua.table(**{"medieval_infantry": 2})  # 4 food per tick
        self.assertEqual(self.recruit.payUpkeep(stock, counts), 0)
        self.assertEqual(stock["food"], 6)
        self.assertEqual(self.recruit.payUpkeep(stock, counts), 0)
        self.assertEqual(stock["food"], 2)
        self.assertEqual(self.recruit.payUpkeep(stock, counts), 1)
        self.assertEqual(stock["food"], 2)

    def test_pay_upkeep_bad_stock(self):
        self.assertEqual(self.recruit.payUpkeep(None, self.lua.table()), 1)

    def test_starved_health_penalty_is_mild(self):
        self.assertAlmostEqual(self.recruit.starvedHealth(100), 95.0, places=6)
        self.assertAlmostEqual(self.recruit.starvedHealth(200), 190.0, places=6)
        self.assertAlmostEqual(self.recruit.starvedHealth(1), 0.95, places=6)

    def test_starved_health_never_fatal_or_invalid(self):
        hp = self.recruit.starvedHealth(0.0001)
        self.assertIsNotNone(hp)
        self.assertGreater(hp, 0)
        self.assertLess(hp, 0.0001)
        self.assertIsNone(self.recruit.starvedHealth(0))
        self.assertIsNone(self.recruit.starvedHealth(-30))
        self.assertIsNone(self.recruit.starvedHealth(None))


class TestModulePurity(unittest.TestCase):
    def test_module_has_no_engine_globals(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("Spring.", "GG.", "VFS.", "gadgetHandler", "UnitDefs"):
            self.assertNotIn(token, src, f"pure module must not reference {token}")


class TestUpkeepGadgetWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")
        banner = cls.src.index("-- Phase-3")
        export = cls.src.index("GG = GG or {}", banner)
        cls.upkeep_src = cls.src[banner:export]

    def test_gadget_includes_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_recruitment.lua")', self.src)

    def test_tick_cadence_is_90_frames(self):
        self.assertRegex(self.src, r"function gadget:GameFrame")
        self.assertIn("UPKEEP_TICK_FRAMES", self.upkeep_src)
        self.assertRegex(self.upkeep_src, r"%\s*UPKEEP_TICK_FRAMES")
        module = LuaRuntime(unpack_returned_tuples=True).execute(
            MODULE_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(module.UPKEEP_TICK_FRAMES, 90)

    def test_upkeep_charges_food_through_economy(self):
        self.assertIn("GG.MedievalEconomy", self.upkeep_src)
        self.assertRegex(self.upkeep_src, r"economy\.CanAfford\(teamID")
        self.assertRegex(self.upkeep_src, r"economy\.Transact\(teamID")
        self.assertRegex(self.upkeep_src, r"\{\s*food\s*=\s*total\s*\}")
        self.assertIn("armyUpkeep", self.upkeep_src)

    def test_starving_gamerule_param_is_synced(self):
        self.assertIn("team_%d_starving", self.upkeep_src)
        self.assertIn("Spring.SetGameRulesParam", self.upkeep_src)
        # Both branches published: 1 when unpaid, 0 when covered.
        self.assertRegex(self.upkeep_src, r"starving and 1 or 0")
        # Seeded at game start so the param exists before the first tick.
        self.assertIn("function gadget:GameStart", self.upkeep_src)

    def test_starvation_penalty_uses_health_not_destruction(self):
        self.assertIn("Spring.SetUnitHealth", self.upkeep_src)
        self.assertIn("Spring.GetUnitHealth", self.upkeep_src)
        self.assertIn("starvedHealth", self.upkeep_src)
        # Starvation must never remove units outright.
        self.assertNotIn("DestroyUnit", self.upkeep_src)

    def test_upkeep_counts_only_military_units(self):
        self.assertIn("isMilitary", self.upkeep_src)
        self.assertRegex(self.upkeep_src, r"\^medieval_")
        self.assertIn("armyCounts", self.upkeep_src)
        for building in ("medieval_town_center", "medieval_granary", "medieval_barracks"):
            self.assertNotIn(building, self.upkeep_src)

    def test_gg_uses_are_nil_guarded(self):
        # Single accessor, nil-guarded before it hands out the economy table.
        guarded = re.findall(
            r"if not GG or not GG\.MedievalEconomy then return nil end\s*\n\s*return GG\.MedievalEconomy",
            self.upkeep_src,
        )
        self.assertEqual(len(guarded), 1)
        # Upkeep never calls into GG.* directly; it goes through the local.
        self.assertNotRegex(self.upkeep_src, r"GG\.Medieval\w+\.")
        for match in re.finditer(r"GG\.Medieval", self.upkeep_src):
            line_start = self.upkeep_src.rfind("\n", 0, match.start()) + 1
            line = self.upkeep_src[line_start:match.end()].strip()
            self.assertTrue(
                line.startswith("if not GG") or line.startswith("return GG."),
                f"unguarded GG use: {line}",
            )

    def test_engine_calls_are_guarded(self):
        self.assertRegex(self.upkeep_src, r"if not Spring or not Spring\.GetTeamList then return end")
        self.assertRegex(self.upkeep_src, r"if not Spring or not Spring\.GetTeamUnits then")
        self.assertRegex(self.upkeep_src, r"if not Spring or not Spring\.SetUnitHealth then return end")


if __name__ == "__main__":
    unittest.main()
