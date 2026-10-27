"""Phase 9 UI feedback test suite.

Tests polished UI/UX feedback for bottom panel and HUD:
- Bottom panel contains PlaySoundFile or click feedback hook
- Bottom panel contains tooltip handling for command buttons (hover text with label + desc)
- Bottom panel contains an idle villager indicator/counter
- Bottom panel has a clear 'No selection' fallback prompt
- Bottom panel supports cancelling queued units (right-click queue slot)
- Lua syntax check passes and widget files compile under bare LuaJIT / stubbed globals
"""

from pathlib import Path
import unittest

try:
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False

ROOT = Path(__file__).resolve().parents[1]
BOTTOM_PANEL_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_bottom_panel.lua"
HUD_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_hud.lua"


class TestPhase9UIFeedback(unittest.TestCase):
    """Verify in-game UI/UX feedback features for bottom panel and HUD."""

    def setUp(self):
        self.bottom_src = BOTTOM_PANEL_PATH.read_text(encoding="utf-8")
        self.hud_src = HUD_PATH.read_text(encoding="utf-8")

    def test_bottom_panel_sound_or_click_feedback_hook(self):
        """Bottom panel has sound or click feedback hook when command buttons are clicked."""
        self.assertTrue(
            ("Spring.PlaySoundFile" in self.bottom_src) or ("playCommandClickSound" in self.bottom_src),
            "Expected PlaySoundFile or playCommandClickSound in bottom panel",
        )
        self.assertIn("playCommandClickSound", self.bottom_src)

    def test_bottom_panel_tooltips_for_command_buttons(self):
        """Bottom panel renders tooltips for hovered command buttons with label + desc."""
        self.assertIn("hoveredCmd", self.bottom_src)
        self.assertIn("drawCommandTooltip", self.bottom_src)
        # Ensure command buttons table defines descriptions
        self.assertIn("desc =", self.bottom_src)

    def test_bottom_panel_idle_villager_indicator(self):
        """Bottom panel displays an idle villager counter/indicator."""
        self.assertIn("getIdleVillagers", self.bottom_src)
        self.assertIn("drawIdleIndicator", self.bottom_src)
        self.assertIn("idle_villagers", self.bottom_src)

    def test_bottom_panel_no_selection_fallback(self):
        """Bottom panel shows a clear 'No selection' fallback rather than a blank panel."""
        self.assertIn("No selection", self.bottom_src)
        self.assertIn("drawNoSelectionPrompt", self.bottom_src)

    def test_bottom_panel_queue_cancel_support(self):
        """Bottom panel tracks production queue hitboxes and supports right-click cancel."""
        self.assertIn("queueSlotHitboxes", self.bottom_src)
        self.assertIn("cancelQueuedItem", self.bottom_src)
        self.assertIn("button == 3", self.bottom_src)

    @unittest.skipUnless(HAS_LUPA, "lupa not installed")
    def test_bottom_panel_compiles_and_initializes_with_stubbed_globals(self):
        """Widget file loads cleanly under Lua runtime with stubbed globals."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        # Stub minimal Recoil globals
        stub = """
        _G.widget = {}
        _G.widgetHandler = {
            ConfigLayoutHandler = function(self, state) end
        }
        _G.Spring = {
            GetModOptions = function() return { medievalbottompanel = 1 } end,
            GetViewGeometry = function() return 1920, 1080 end,
            GetSelectedUnits = function() return {} end,
            GetTeamRulesParam = function(teamID, key) return 3 end,
            GetMyTeamID = function() return 0 end,
            Echo = function(msg) end,
            PlaySoundFile = function(path) end,
        }
        _G.gl = {
            Color = function(...) end,
            Rect = function(...) end,
            Texture = function(...) end,
            TexRect = function(...) end,
            Text = function(...) end,
        }
        _G.UnitDefs = {}
        _G.WeaponDefs = {}
        _G.CMD = {
            STOP = 0, MOVE = 10, ATTACK = 20, PATROL = 15,
            GUARD = 25, WAIT = 5, HOLD_POS = 50, FIGHT = 30,
            LOAD_UNITS = 75, REPAIR = 40, REMOVE = 110,
        }
        """
        lua.execute(stub)
        lua.globals().widget_src = self.bottom_src
        res = lua.execute("local fn, err = load(widget_src, '@bottom_panel'); if not fn then return { ok = false, err = err } end; local ok2, err2 = pcall(fn); return { ok = ok2, err = err2 }")
        self.assertTrue(res["ok"], f"Bottom panel execution failed: {res['err']}")

        # Test DrawScreen execution with empty selection
        res_draw = lua.execute("local ok, err = pcall(widget.DrawScreen, widget); return { ok = ok, err = err }")
        self.assertTrue(res_draw["ok"], f"DrawScreen failed: {res_draw['err']}")


if __name__ == "__main__":
    unittest.main()
