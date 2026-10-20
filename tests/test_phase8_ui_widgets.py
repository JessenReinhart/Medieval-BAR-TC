"""Phase 8 UI widgets test suite.

Covers:
- Source-level contract checks for each UI widget:
  - LuaUI/Widgets/gui_medieval_hud.lua
  - LuaUI/Widgets/gui_medieval_bottom_panel.lua
  - LuaUI/Widgets/gui_medieval_minimap.lua
- GetInfo metadata (name, author, license, layer, enabled)
- Mod option gating (medievalhud, medievalbottompanel, medievalminimap)
- UI isolation: unsynced code only, no synced engine calls, no synced GG mutations
- gui_medieval_bottom_panel.lua: reads Spring.GetSelectedUnits, UnitDefs, Spring.GetUnitHealth
- gui_medieval_minimap.lua: mod option gate and widget metadata
- Refactored HUD: backward-compatible contract (VFS.Include("scripts/medieval_hud.lua"), Spring.GetTeamRulesParam, etc.)
- Modoptions declarations in modoptions.lua
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUD_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_hud.lua"
BOTTOM_PANEL_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_bottom_panel.lua"
MINIMAP_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_minimap.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"

# Synced mutation APIs that unsynced UI widgets must never call
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


class TestWidgetSourceContracts(unittest.TestCase):
    """Source-level contract checks for all medieval UI widgets."""

    def setUp(self):
        self.hud_src = HUD_PATH.read_text(encoding="utf-8")
        self.bottom_src = BOTTOM_PANEL_PATH.read_text(encoding="utf-8")
        self.minimap_src = MINIMAP_PATH.read_text(encoding="utf-8")
        self.modoptions_src = MODOPTIONS_PATH.read_text(encoding="utf-8")
        self.all_widgets = [
            ("HUD", self.hud_src),
            ("BottomPanel", self.bottom_src),
            ("Minimap", self.minimap_src),
        ]

    def test_all_widget_files_exist(self):
        self.assertTrue(HUD_PATH.is_file(), f"Missing {HUD_PATH}")
        self.assertTrue(BOTTOM_PANEL_PATH.is_file(), f"Missing {BOTTOM_PANEL_PATH}")
        self.assertTrue(MINIMAP_PATH.is_file(), f"Missing {MINIMAP_PATH}")

    def test_widget_getinfo_metadata(self):
        for name, src in self.all_widgets:
            with self.subTest(widget=name):
                self.assertIn("function widget:GetInfo()", src)
                self.assertRegex(src, r'author\s*=\s*"Medieval-BAR-TC"')
                self.assertRegex(src, r'license\s*=\s*"GPL-v2"')
                self.assertRegex(src, r"layer\s*=\s*\d+")
                self.assertRegex(src, r"enabled\s*=\s*true")

    def test_no_synced_engine_mutation_calls(self):
        for name, src in self.all_widgets:
            for forbidden in FORBIDDEN_SYNCED_APIS:
                with self.subTest(widget=name, api=forbidden):
                    self.assertNotIn(
                        forbidden,
                        src,
                        f"Widget {name} contains forbidden synced engine call: {forbidden}",
                    )

    def test_no_synced_gg_mutations(self):
        """Unsynced widgets must not modify synced GG tables."""
        for name, src in self.all_widgets:
            with self.subTest(widget=name):
                # Ensure no direct GG writes or imports
                self.assertNotIn("GG.Medieval", src)
                self.assertNotIn("gadgetHandler:RegisterGlobal", src)


class TestBottomPanelWidget(unittest.TestCase):
    """Specific contract tests for gui_medieval_bottom_panel.lua."""

    def setUp(self):
        self.src = BOTTOM_PANEL_PATH.read_text(encoding="utf-8")

    def test_getinfo_name_and_desc(self):
        self.assertIn('name    = "Medieval Bottom Panel"', self.src)
        self.assertIn("selection, portrait and command panel", self.src)
        self.assertRegex(self.src, r"layer\s*=\s*1")

    def test_modoption_gating(self):
        self.assertIn("medievalbottompanel", self.src)
        self.assertIn("options.medievalbottompanel", self.src)
        # Check early return if disabled
        self.assertRegex(
            self.src,
            r'if optionValue == false or optionValue == 0 or optionValue == "0" then return end',
        )

    def test_reads_selected_units(self):
        self.assertIn("Spring.GetSelectedUnits", self.src)

    def test_reads_unit_defs(self):
        self.assertIn("UnitDefs", self.src)
        self.assertIn("UnitDefs[udID]", self.src)

    def test_reads_unit_health(self):
        self.assertIn("Spring.GetUnitHealth", self.src)

    def test_reads_unit_def_id(self):
        self.assertIn("Spring.GetUnitDefID", self.src)

    def test_has_selection_and_command_features(self):
        self.assertIn("widget:DrawScreen", self.src)
        self.assertIn("widget:Initialize", self.src)
        self.assertIn("widget:ViewResize", self.src)
        self.assertIn("drawSingleUnit", self.src)
        self.assertIn("drawMultiSelect", self.src)
        self.assertIn("getPortraitPath", self.src)

    def test_command_button_icons_and_grid(self):
        """AAA polish: command buttons use command_*.png icons in a grid."""
        self.assertIn("COMMAND_BUTTONS", self.src)
        self.assertIn("drawCommandGrid", self.src)
        self.assertIn("bitmaps/ui/command_stop.png", self.src)
        self.assertIn("bitmaps/ui/command_move.png", self.src)
        self.assertIn("bitmaps/ui/command_attack.png", self.src)
        self.assertIn("CMD_ICON_SIZE", self.src)

    def test_prominent_health_bar_and_hp_overlay(self):
        """AAA polish: health bar is wider/taller with HP numbers overlaid."""
        self.assertIn("HEALTH_BAR_HEIGHT  = 14", self.src)
        self.assertIn("HEALTH_BAR_WIDTH   = 180", self.src)
        self.assertIn("math.floor(health)", self.src)
        self.assertIn("math.floor(maxHP)", self.src)

    def test_mouse_hover_state_tracking(self):
        """AAA polish: mouse hover highlight on command buttons."""
        self.assertIn("widget:MouseMove", self.src)
        self.assertIn("COL_CMD_HOVER", self.src)

    def test_panel_flush_geometry(self):
        """AAA polish: panel height 150px centered at bottom."""
        self.assertIn("PANEL_HEIGHT       = 150", self.src)

    def test_modoption_declared_in_modoptions_lua(self):
        src = MODOPTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn('key = "medievalbottompanel"', src)
        block = src.split('key = "medievalbottompanel"')[1].split("},")[0]
        self.assertIn('type = "bool"', block)
        self.assertIn("def = true", block)


class TestMinimapWidget(unittest.TestCase):
    """Specific contract tests for gui_medieval_minimap.lua (AAA polish)."""

    def setUp(self):
        self.src = MINIMAP_PATH.read_text(encoding="utf-8")

    def test_getinfo_name_and_desc(self):
        self.assertIn('name    = "Medieval Minimap Frame"', self.src)
        self.assertIn("minimap", self.src.lower())
        self.assertRegex(self.src, r"layer\s*=\s*2")

    def test_modoption_gating(self):
        self.assertIn("medievalminimap", self.src)
        self.assertIn("options.medievalminimap", self.src)
        self.assertRegex(
            self.src,
            r'if optionValue == false or optionValue == 0 or optionValue == "0" then return end',
        )

    def test_uses_minimap_geometry(self):
        self.assertIn("Spring.SendCommands", self.src)
        self.assertIn("minimap geometry", self.src)

    def test_draws_minimap_frame(self):
        self.assertIn("widget:DrawScreen", self.src)
        self.assertIn("widget:Shutdown", self.src)

    def test_textured_frame_rendering(self):
        """Frame uses gl.Texture + gl.TexRect to blit the stone frame PNG."""
        self.assertIn('FRAME_TEX', self.src)
        self.assertIn('minimap_frame.png', self.src)
        self.assertIn('glTexture(FRAME_TEX)', self.src)
        self.assertIn('glTexRect(', self.src)
        self.assertIn('glTexture(false)', self.src)

    def test_corner_bracket_overlays(self):
        """Corner brackets drawn at four outer frame corners."""
        self.assertIn('CORNER_TEX', self.src)
        self.assertIn('frame_corner.png', self.src)
        self.assertIn('drawCornerBrackets', self.src)

    def test_viewport_fog_tint(self):
        """Inner viewport has a translucent fog-of-war tint, not pure black."""
        self.assertIn('COL_FOG_TINT', self.src)
        self.assertIn('drawViewportTint', self.src)
        # Must draw a rect over the minimap area with alpha < 1
        self.assertRegex(self.src, r'glRect\(mmX.*mmY.*mmW.*mmH\)')

    def test_team_blips_with_halo(self):
        """Unit blips drawn with owner-color halo ring + solid dot."""
        self.assertIn('drawBlips', self.src)
        self.assertIn('updateBlipCache', self.src)
        self.assertIn('Spring.GetAllUnits', self.src)
        self.assertIn('Spring.GetUnitPosition', self.src)
        self.assertIn('Spring.GetTeamColor', self.src)
        self.assertIn('BLIP_OUTER', self.src)
        self.assertIn('BLIP_INNER', self.src)

    def test_fallback_frame_when_no_texture(self):
        """Graceful gl.Rect fallback when texture file is missing."""
        self.assertIn('drawFallbackFrame', self.src)
        # Fallback must draw cardinal pointers and corner bosses
        self.assertIn('COL_BRONZE', self.src)

    def test_geometry_reset_on_shutdown(self):
        """Shutdown resets minimap to default engine position."""
        self.assertRegex(self.src, r'minimap geometry 0 0 1 1')

    def test_pure_unsynced_no_gg_writes(self):
        """Widget must not write to GG (synced global table)."""
        self.assertNotIn("GG.", self.src)
        self.assertNotIn("GG[", self.src)

    def test_modoption_declared_in_modoptions_lua(self):
        src = MODOPTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn('key = "medievalminimap"', src)
        block = src.split('key = "medievalminimap"')[1].split("},")[0]
        self.assertIn('type = "bool"', block)
        self.assertIn("def = true", block)


class TestRefactoredHUDWidget(unittest.TestCase):
    """Backward-compatible contract tests for refactored gui_medieval_hud.lua."""

    def setUp(self):
        self.src = HUD_PATH.read_text(encoding="utf-8")

    def test_includes_shared_hud_formatter(self):
        self.assertIn('VFS.Include("scripts/medieval_hud.lua")', self.src)

    def test_reads_team_rules_params(self):
        self.assertIn("Spring.GetTeamRulesParam", self.src)

    def test_modoption_gating(self):
        self.assertIn("medievalhud", self.src)
        self.assertIn("options.medievalhud", self.src)
        self.assertRegex(
            self.src,
            r'if optionValue == false or optionValue == 0 or optionValue == "0" then return end',
        )

    def test_getinfo_metadata(self):
        self.assertIn('name = "Medieval Economy HUD"', self.src)
        self.assertIn('author = "Medieval-BAR-TC"', self.src)
        self.assertIn('license = "GPL-v2"', self.src)

    def test_drawscreen_renders_cells(self):
        self.assertIn("widget:DrawScreen()", self.src)
        self.assertIn("buildCells(teamID)", self.src)

    def test_pure_formatter_usage(self):
        # Must reference canonical resource order and formatters from hud
        self.assertIn("hud.RESOURCE_ORDER", self.src)
        self.assertIn("hud.PARAM_KEYS", self.src)
        self.assertIn("hud.popLine", self.src)
        self.assertIn("hud.idleLine", self.src)


if __name__ == "__main__":
    unittest.main()
