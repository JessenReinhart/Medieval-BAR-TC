"""Tests for Phase 6 Slice 5: Content Polish, Modoptions & HUD Labels.

Verifies modoptions player-facing descriptions and keys, as well as HUD
formatting invariants in scripts/medieval_hud.lua.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False


@unittest.skipUnless(HAS_LUPA, "lupa not installed")
class TestPhase6Slice5(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)

    def test_modoptions_structure_and_keys(self):
        """Modoptions must be valid Lua returning a list of options with expected keys."""
        modoptions_path = ROOT / "modoptions.lua"
        self.assertTrue(modoptions_path.exists())
        with open(modoptions_path, "r", encoding="utf-8") as f:
            code = f.read()
        opts = self.lua.execute(code)
        
        found_keys = {}
        for idx in range(1, len(opts) + 1):
            opt = opts[idx]
            found_keys[opt.key] = {
                "name": opt.name,
                "desc": opt.desc,
                "type": opt.type,
                "def": opt.def_,
            }

        # Check required modoptions keys
        self.assertIn("victorymode", found_keys)
        self.assertIn("medievalvictory", found_keys)
        self.assertIn("medievalhud", found_keys)
        self.assertIn("medievalmarket", found_keys)
        self.assertIn("medievalgarrison", found_keys)
        self.assertIn("medievaltactics", found_keys)

        # Ensure names are player-facing (not placeholder probe names)
        self.assertEqual(found_keys["medievalvictory"]["name"], "Victory Conditions")
        self.assertEqual(found_keys["medievalmarket"]["name"], "Market & Trade")
        self.assertEqual(found_keys["medievalgarrison"]["name"], "Garrisoning")
        self.assertEqual(found_keys["medievaltactics"]["name"], "Combat Tactics")

    def test_hud_formatting_purity(self):
        """scripts/medieval_hud.lua pure formatting functions."""
        hud_path = ROOT / "scripts" / "medieval_hud.lua"
        self.assertTrue(hud_path.exists())
        with open(hud_path, "r", encoding="utf-8") as f:
            code = f.read()
        hud = self.lua.execute(code)

        # PARAM_KEYS check
        self.assertEqual(hud.PARAM_KEYS.food, "food")
        self.assertEqual(hud.PARAM_KEYS.pop, "pop")
        self.assertEqual(hud.PARAM_KEYS.popcap, "popcap")

        # Format stock number
        self.assertEqual(hud.formatStock(150), "150")
        self.assertEqual(hud.formatStock(1250), "1.2k")
        self.assertEqual(hud.formatStock(2000000), "2M")

        # popLine with colon per Phase 5 recorded deviation
        self.assertEqual(hud.popLine(12, 40), "Pop: 12/40")
        self.assertEqual(hud.popLine(0, 10), "Pop: 0/10")

    def _load_unit_def(self, unit_name):
        """Load units/<unit_name>.lua and return its inner def table."""
        path = ROOT / "units" / f"{unit_name}.lua"
        self.assertTrue(path.exists(), f"missing unit def: {unit_name}")
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        outer = self.lua.execute(code)
        return outer[unit_name]

    def test_veteran_tier_hp_exceeds_base_tier(self):
        """Phase 6 reconciliation: a veteran tier must outlast its base tier.

        Regression for the inverted 350/550/160 HP values that undercut the
        base 1200/2200/750 HP tiers while costing more metal, mass and time.
        """
        pairs = (
            ("medieval_men_at_arms", "medieval_infantry", 1600),
            ("medieval_knight", "medieval_cavalry", 2900),
            ("medieval_crossbow", "medieval_archer", 1000),
        )
        for veteran, base, expected_hp in pairs:
            vdef = self._load_unit_def(veteran)
            bdef = self._load_unit_def(base)
            self.assertEqual(vdef["maxDamage"], expected_hp)
            self.assertGreater(vdef["maxDamage"], bdef["maxDamage"])

    def test_base_units_drop_prototype_placeholder_descriptions(self):
        """No shipping unit def may carry the Phase 1 placeholder description tag."""
        for unit_name in ("medieval_infantry", "medieval_archer", "medieval_cavalry"):
            def_ = self._load_unit_def(unit_name)
            self.assertNotIn("prototype placeholder", def_["description"])


if __name__ == "__main__":
    unittest.main()
