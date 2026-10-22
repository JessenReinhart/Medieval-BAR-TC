"""Phase 8 camera widget (WASD + Q/E) source-level contract tests.

Covers:
- LuaUI/Widgets/gui_medieval_camera.lua exists and compiles with lupa.
- GetInfo metadata (author Medieval-BAR-TC, license GPL-v2, layer, enabled).
- Key handlers for W/A/S/D (pan) and Q/E (yaw) plus the WG.medievalMainMenuOpen
  and text-input focus guards.
- Unsynced camera APIs only (Spring.GetCameraState / SetCameraState /
  GetCameraVectors), no synced engine mutations.
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
CAMERA_WIDGET_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_camera.lua"

# Synced mutation APIs that unsynced UI widgets must never call.
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


class TestMedievalCameraWidget(unittest.TestCase):
    def setUp(self):
        self.src = CAMERA_WIDGET_PATH.read_text(encoding="utf-8")

    def test_widget_file_exists(self):
        self.assertTrue(CAMERA_WIDGET_PATH.is_file(), f"Missing {CAMERA_WIDGET_PATH}")

    def test_widget_compiles(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().c = self.src
        ret = lua.execute("local fn, err = load(c); return { fn = fn, err = err }")
        self.assertIsNotNone(
            ret["fn"], f"Lua compile failure in gui_medieval_camera.lua: {ret['err']}"
        )

    def test_widget_getinfo_metadata(self):
        self.assertIn("function widget:GetInfo()", self.src)
        self.assertRegex(self.src, r'author\s*=\s*"Medieval-BAR-TC"')
        self.assertRegex(self.src, r'license\s*=\s*"GPL-v2"')
        self.assertRegex(self.src, r"layer\s*=\s*\d+")
        self.assertRegex(self.src, r"enabled\s*=\s*true")

    def test_uses_unsynced_camera_apis(self):
        self.assertIn("Spring.GetCameraState", self.src)
        self.assertIn("Spring.SetCameraState", self.src)
        self.assertIn("Spring.GetCameraVectors", self.src)
        # SetCameraState must use a 0-second transition for immediate response.
        self.assertRegex(self.src, r"SetCameraState\(cs,\s*0\)")

    def test_has_key_handlers(self):
        self.assertIn("function widget:KeyPress(", self.src)
        self.assertIn("function widget:KeyRelease(", self.src)
        self.assertIn("function widget:Update(", self.src)

    def test_binds_wasd_and_qe_keys(self):
        # Numeric keysyms (KEYSYMS): W=119 S=115 A=97 D=100 Q=113 E=101
        for keysym in (119, 115, 97, 100, 113, 101):
            self.assertIn(f"[{keysym}]", self.src, f"Missing keysym {keysym}")

        # Label fallback for lowercase / shifted input.
        for label in ("w", "s", "a", "d", "q", "e"):
            self.assertIn(label, self.src.lower(), f"Missing label {label}")

    def test_pan_and_yaw_movement(self):
        # Pan mutates camera position along ground plane; yaw mutates cs.ry.
        self.assertIn("cs.px", self.src)
        self.assertIn("cs.pz", self.src)
        self.assertIn("cs.ry", self.src)
        self.assertIn("PAN_SPEED", self.src)
        self.assertIn("ROT_SPEED", self.src)

    def test_guards_main_menu_and_text_input(self):
        self.assertIn("WG.medievalMainMenuOpen", self.src)
        self.assertIn("WG.medievalChatInputActive", self.src)
        self.assertIn("WG.medievalConsoleInputActive", self.src)
        self.assertIn("WG.editBoxActive", self.src)

    def test_no_synced_engine_mutation_calls(self):
        for forbidden in FORBIDDEN_SYNCED_APIS:
            self.assertNotIn(
                forbidden,
                self.src,
                f"Camera widget contains forbidden synced engine call: {forbidden}",
            )


if __name__ == "__main__":
    unittest.main()