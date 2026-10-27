import unittest
from pathlib import Path
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_skirmish_ai.lua"

class TestSkirmishAICounters(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        code = MODULE_PATH.read_text(encoding="utf-8")
        self.lua.globals()._code = code
        self.ai = self.lua.execute("return assert(load(_code))()")

    def test_recruit_costs_table(self):
        costs = self.ai.RECRUIT_COSTS
        self.assertIsNotNone(costs)
        infantry = dict(costs.medieval_infantry)
        self.assertEqual(infantry, {"food": 30, "wood": 20, "stone": 10, "iron": 5})
        spearman = dict(costs.medieval_spearman)
        self.assertEqual(spearman, {"food": 25, "wood": 30, "stone": 0, "iron": 5})
        archer = dict(costs.medieval_archer)
        self.assertEqual(archer, {"food": 25, "wood": 35, "stone": 0, "iron": 0})
        cavalry = dict(costs.medieval_cavalry)
        self.assertEqual(cavalry, {"food": 50, "wood": 10, "stone": 0, "iron": 15})

    def test_counter_cavalry_selects_spearman(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table(medieval_cavalry=5, medieval_infantry=1)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertEqual(pick, "medieval_spearman")

    def test_counter_spearman_selects_infantry(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table(medieval_spearman=6, medieval_archer=2)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertEqual(pick, "medieval_infantry")

    def test_counter_infantry_selects_archer(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table(medieval_infantry=7, medieval_cavalry=2)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertEqual(pick, "medieval_archer")

    def test_counter_archer_selects_cavalry(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table(medieval_archer=8, medieval_infantry=3)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertEqual(pick, "medieval_cavalry")

    def test_combined_arms_fallback_no_enemy(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table()
        # Friendly already has 4 infantry (40%), 0 spearmen, 0 archers, 0 cavalry
        friendly = self.lua.table(medieval_infantry=4)
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        # Target ratios: 40% inf, 25% spear, 20% arch, 15% cav.
        # Spearman deficit: 0.25 - 0 = 0.25 (highest deficit)
        self.assertEqual(pick, "medieval_spearman")

    def test_combined_arms_fallback_empty_friendly(self):
        stock = self.lua.table(food=100, wood=100, stone=100, iron=100)
        enemy = self.lua.table()
        friendly = self.lua.table()
        # All deficits = target ratio - 0: inf=0.40, spear=0.25, arch=0.20, cav=0.15
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertEqual(pick, "medieval_infantry")

    def test_unaffordable_counter_falls_back(self):
        # Cannot afford spearman (wood=30, iron=5), but can afford infantry (food=30, wood=20, stone=10, iron=5)
        # Let's give food=50, wood=20, stone=20, iron=10. Spearman needs 30 wood -> unaffordable.
        stock = self.lua.table(food=50, wood=20, stone=20, iron=10)
        enemy = self.lua.table(medieval_cavalry=10)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        # Preferred counter was spearman, but unaffordable, falls back to combined arms / affordable unit
        self.assertEqual(pick, "medieval_infantry")

    def test_cannot_afford_anything_returns_nil(self):
        stock = self.lua.table(food=0, wood=0, stone=0, iron=0)
        enemy = self.lua.table(medieval_cavalry=5)
        friendly = self.lua.table()
        pick = self.ai.selectRecruitDef(stock, enemy, friendly)
        self.assertIsNone(pick)

    def test_should_retreat_logic(self):
        # Low health ratio (< 0.35)
        self.assertTrue(self.ai.shouldRetreat(0.25, 10, 5))
        self.assertTrue(self.ai.shouldRetreat(0.34, 10, 1))
        # Normal health, not outnumbered
        self.assertFalse(self.ai.shouldRetreat(0.8, 10, 5))
        self.assertFalse(self.ai.shouldRetreat(0.5, 10, 10))
        # Outnumbered 2 to 1 or more
        self.assertTrue(self.ai.shouldRetreat(0.8, 5, 10))
        self.assertTrue(self.ai.shouldRetreat(1.0, 3, 8))
