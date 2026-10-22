"""Unit tests for LuaUI/Widgets/gui_medieval_unit_rings.lua.

Verifies:
- Widget metadata (GetInfo: name, author, license, layer, enabled)
- Modoption declaration in modoptions.lua and defensive gating in widget
- Unsynced UI isolation (no synced engine mutation calls, no GG access)
- Respects WG.medievalMainMenuOpen to hide during open menu
- Drawing callins: DrawWorldPreUnit and DrawWorld
- Engine query calls: Spring.GetVisibleUnits, Spring.GetUnitTeam, Spring.GetTeamColor
- Unit radius calculation using UnitDefs and footprint fallback
- Ally vs Enemy differentiation (hostile warning ring)
- Selection ring rendering using Spring.GetSelectedUnits
- GL state cleanup (resetting color and state)
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RINGS_WIDGET_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_unit_rings.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"

FORBIDDEN_SYNCED_APIS = (
    "Spring.CreateUnit",
    "Spring.DestroyUnit",
    "Spring.TransferUnit",
    "Spring.SetUnitHealth",
    "Spring.SetUnitMaxHealth",
    "Spring.SetUnitExperience",
    "Spring.SetTeamRulesParam",
    "Spring.SetGameRulesParam",
    "Spring.SetUnitRulesParam",
    "gadgetHandler:IsSyncedCode",
)

try:
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False


class TestMedievalUnitRingsWidget(unittest.TestCase):
    def setUp(self):
        self.assertTrue(RINGS_WIDGET_PATH.is_file(), f"Missing {RINGS_WIDGET_PATH}")
        self.src = RINGS_WIDGET_PATH.read_text(encoding="utf-8")
        self.modoptions_src = MODOPTIONS_PATH.read_text(encoding="utf-8")

    def test_widget_getinfo_metadata(self):
        self.assertIn("function widget:GetInfo()", self.src)
        self.assertIn('name    = "Medieval Unit Rings"', self.src)
        self.assertIn('author  = "Medieval-BAR-TC"', self.src)
        self.assertIn('license = "GPL-v2"', self.src)
        self.assertIn("enabled = true", self.src)
        self.assertRegex(self.src, r"layer\s*=\s*-?\d+")

    def test_modoption_declared_in_modoptions_lua(self):
        self.assertIn('key = "medievalunitrings"', self.modoptions_src)
        block = self.modoptions_src.split('key = "medievalunitrings"')[1].split("},")[0]
        self.assertIn('type = "bool"', block)
        self.assertIn("def = true", block)

    def test_modoption_defensive_gating(self):
        self.assertIn("options.medievalunitrings", self.src)
        self.assertRegex(
            self.src,
            r'if optionValue == false or optionValue == 0 or optionValue == "0" then return end',
        )

    def test_no_synced_engine_mutations(self):
        for forbidden in FORBIDDEN_SYNCED_APIS:
            with self.subTest(api=forbidden):
                self.assertNotIn(
                    forbidden,
                    self.src,
                    f"gui_medieval_unit_rings.lua contains forbidden synced call: {forbidden}",
                )

    def test_no_synced_gg_writes(self):
        self.assertNotIn("GG.", self.src)
        self.assertNotIn("GG[", self.src)

    def test_menu_visibility_guard(self):
        self.assertIn("WG.medievalMainMenuOpen", self.src)

    def test_draw_callins(self):
        self.assertIn("function widget:DrawWorldPreUnit()", self.src)
        self.assertIn("function widget:DrawWorld()", self.src)

    def test_engine_api_usage(self):
        self.assertIn("Spring.GetVisibleUnits", self.src)
        self.assertIn("Spring.GetUnitTeam", self.src)
        self.assertIn("Spring.GetTeamColor", self.src)
        self.assertIn("Spring.GetUnitPosition", self.src)
        self.assertIn("Spring.GetUnitDefID", self.src)
        self.assertIn("Spring.GetMyTeamID", self.src)
        self.assertIn("Spring.AreTeamsAllied", self.src)
        self.assertIn("Spring.GetSelectedUnits", self.src)

    def test_ground_circle_rendering(self):
        self.assertIn("glDrawGroundCircle", self.src)
        self.assertIn("drawUnitRings", self.src)
        self.assertIn("drawSelectionRings", self.src)

    def test_ally_vs_enemy_differentiation(self):
        self.assertIn("isEnemy", self.src)
        self.assertIn("ENEMY_OUTER_COLOR", self.src)
        self.assertIn("ENEMY_OUTER_SCALE", self.src)
        self.assertIn("ALLY_ALPHA", self.src)
        self.assertIn("ENEMY_ALPHA", self.src)

    def test_unit_radius_caching_and_fallback(self):
        self.assertIn("getUnitRadius", self.src)
        self.assertIn("radiusCache", self.src)
        self.assertIn("FOOTPRINT_TO_WORLD", self.src)

    def test_gl_state_cleanup(self):
        self.assertIn("glResetState()", self.src)
        self.assertIn("glColor(1, 1, 1, 1)", self.src)


@unittest.skipUnless(HAS_LUPA, "lupa not installed")
class TestMedievalUnitRingsRuntime(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)

    def test_getinfo_execution(self):
        # Extract widget:GetInfo() definition and execute
        src = RINGS_WIDGET_PATH.read_text(encoding="utf-8")
        match = re.search(r"function widget:GetInfo\(\).*?end", src, re.DOTALL)
        self.assertIsNotNone(match)
        getinfo_code = f"widget = {{}}\n{match.group(0)}\nreturn widget:GetInfo()"
        info = self.lua.execute(getinfo_code)
        self.assertEqual(info["name"], "Medieval Unit Rings")
        self.assertEqual(info["author"], "Medieval-BAR-TC")
        self.assertEqual(info["license"], "GPL-v2")
        self.assertEqual(info["enabled"], True)


if __name__ == "__main__":
    unittest.main()
