"""
Comprehensive pytest test suite for the Medieval-BAR-TC main menu subsystem.

Covers:
  1. TestMenuPurity         – purity checks and exported API surface
  2. TestMenuStateMachine   – tab transitions, isOpen toggle
  3. TestSkirmishConfigValidation – validateConfig edge cases
  4. TestStartscriptGeneration    – Recoil startscript output
  5. TestSettingsManagement  – updateSetting with clamping
  6. TestMenuWidgetContract  – widget file structure checks
  7. TestMenuModoptions      – modoptions.lua declaration
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_main_menu.lua"
WIDGET_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_main_menu.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lua_to_py(lua, value):
    """Recursively convert Lua tables to Python primitives."""
    if value is None:
        return None
    val_type = lua.eval("type")(value)
    if val_type == "table":
        keys = list(value.keys())
        if not keys:
            return []
        if all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class MenuBase(unittest.TestCase):
    """Base class: fresh LuaRuntime and module per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.source = MODULE_PATH.read_text(encoding="utf-8")
        self.m = self.lua.execute(self.source)

    # Convenience: create a new menu state from the module.
    def _new_state(self):
        return self.m.newMenuState()


# ===========================================================================
# 1. TestMenuPurity
# ===========================================================================


class TestMenuPurity(MenuBase):
    """scripts/medieval_main_menu.lua contains no engine globals and exports
    every required symbol."""

    def test_no_spring_calls(self):
        calls = re.findall(r"Spring\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed Spring calls found: {calls}")

    def test_no_vfs_calls(self):
        calls = re.findall(r"VFS\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed VFS calls found: {calls}")

    def test_no_gg_calls(self):
        calls = re.findall(r"GG\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed GG calls found: {calls}")

    def test_loads_cleanly_in_pure_runtime(self):
        """Loads in a bare LuaRuntime with zero injected globals."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        m = lua.execute(self.source)
        self.assertIsNotNone(m)

    def test_exports_newMenuState(self):
        self.assertTrue(callable(self.m.newMenuState))

    def test_exports_setTab(self):
        self.assertTrue(callable(self.m.setTab))

    def test_exports_toggleOpen(self):
        self.assertTrue(callable(self.m.toggleOpen))

    def test_exports_updateSkirmishOption(self):
        self.assertTrue(callable(self.m.updateSkirmishOption))

    def test_exports_updateSetting(self):
        self.assertTrue(callable(self.m.updateSetting))

    def test_exports_validateConfig(self):
        self.assertTrue(callable(self.m.validateConfig))

    def test_exports_generateStartscript(self):
        self.assertTrue(callable(self.m.generateStartscript))

    def test_exports_DEFAULT_CONFIG(self):
        cfg = self.m.DEFAULT_CONFIG
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["mapName"], "Quicksilver Remake 1.24")

    def test_exports_DEFAULT_SETTINGS(self):
        settings = self.m.DEFAULT_SETTINGS
        self.assertIsNotNone(settings)
        self.assertEqual(settings["masterVolume"], 80)


# ===========================================================================
# 2. TestMenuStateMachine
# ===========================================================================


class TestMenuStateMachine(MenuBase):
    """State machine: tab transitions and open/close toggle."""

    def test_default_tab_is_main(self):
        state = self._new_state()
        self.assertEqual(state.activeTab, "MAIN")

    def test_default_isOpen_true(self):
        state = self._new_state()
        self.assertTrue(state.isOpen)

    def test_setTab_skirmish(self):
        state = self._new_state()
        ok = self.m.setTab(state, "SKIRMISH")
        self.assertTrue(ok)
        self.assertEqual(state.activeTab, "SKIRMISH")

    def test_setTab_settings(self):
        state = self._new_state()
        self.assertTrue(self.m.setTab(state, "SETTINGS"))
        self.assertEqual(state.activeTab, "SETTINGS")

    def test_setTab_credits(self):
        state = self._new_state()
        self.assertTrue(self.m.setTab(state, "CREDITS"))
        self.assertEqual(state.activeTab, "CREDITS")

    def test_setTab_back_to_main(self):
        state = self._new_state()
        self.m.setTab(state, "CREDITS")
        self.m.setTab(state, "MAIN")
        self.assertEqual(state.activeTab, "MAIN")

    def test_setTab_rejects_invalid(self):
        state = self._new_state()
        ok = self.m.setTab(state, "NONEXISTENT")
        self.assertFalse(ok)
        self.assertEqual(state.activeTab, "MAIN")  # unchanged

    def test_setTab_rejects_empty_string(self):
        state = self._new_state()
        ok = self.m.setTab(state, "")
        self.assertFalse(ok)

    def test_toggleOpen_flips_to_false(self):
        state = self._new_state()
        self.assertTrue(state.isOpen)
        self.m.toggleOpen(state)
        self.assertFalse(state.isOpen)

    def test_toggleOpen_round_trip(self):
        state = self._new_state()
        self.m.toggleOpen(state)
        self.m.toggleOpen(state)
        self.assertTrue(state.isOpen)


# ===========================================================================
# 3. TestSkirmishConfigValidation
# ===========================================================================


class TestSkirmishConfigValidation(MenuBase):
    """validateConfig: valid configs pass, invalid configs fail."""

    def _default_py_config(self, **overrides):
        """Build a Python dict matching DEFAULT_CONFIG, apply overrides,
        then convert to a Lua table."""
        base = {
            "mapName": "Quicksilver Remake 1.24",
            "myPlayerName": "Player",
            "playerColor": "Blue",
            "playerFaction": "Britons",
            "playerTeamID": 0,
            "numAI": 1,
            "aiType": "NullAI",
            "aiDifficulty": "Medium",
            "gameMode": "tc_destruction",
            "proceduralMap": False,
            "seed": 0,
            "density": "normal",
            "numTeams": 2,
            "medievalmapgen": True,
            "medievaltactics": True,
            "medievalmarket": True,
            "medievalgarrison": True,
        }
        base.update(overrides)
        tbl = self.lua.table(**{k: v for k, v in base.items()})
        return tbl

    def test_valid_default_config(self):
        cfg = self._default_py_config()
        ok, err = self.m.validateConfig(cfg)
        self.assertTrue(ok, f"Expected valid but got: {err}")

    def test_invalid_numTeams_too_low(self):
        cfg = self._default_py_config(numTeams=1)
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("numTeams", err)

    def test_invalid_numTeams_too_high(self):
        cfg = self._default_py_config(numTeams=5)
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("numTeams", err)

    def test_valid_numTeams_boundary_2(self):
        cfg = self._default_py_config(numTeams=2)
        ok, _ = self.m.validateConfig(cfg)
        self.assertTrue(ok)

    def test_valid_numTeams_boundary_4(self):
        cfg = self._default_py_config(numTeams=4, numAI=3)
        ok, _ = self.m.validateConfig(cfg)
        self.assertTrue(ok)

    def test_invalid_victory_mode(self):
        cfg = self._default_py_config(gameMode="deathmatch")
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("victoryMode", err)

    def test_valid_victory_modes(self):
        for mode in ("tc_destruction", "conquest", "regicide", "time_limit"):
            cfg = self._default_py_config(gameMode=mode)
            ok, err = self.m.validateConfig(cfg)
            self.assertTrue(ok, f"Mode {mode} should be valid but got: {err}")

    def test_invalid_ai_type(self):
        cfg = self._default_py_config(aiType="CheatingAI")
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("aiType", err)

    def test_valid_ai_types(self):
        for ai in ("SkirmishAI", "NullAI"):
            cfg = self._default_py_config(aiType=ai)
            ok, err = self.m.validateConfig(cfg)
            self.assertTrue(ok, f"AI type {ai} should be valid but got: {err}")

    def test_invalid_mapName_empty(self):
        cfg = self._default_py_config(mapName="")
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("mapName", err)

    def test_invalid_myPlayerName_empty(self):
        cfg = self._default_py_config(myPlayerName="")
        ok, err = self.m.validateConfig(cfg)
        self.assertFalse(ok)
        self.assertIn("myPlayerName", err)

    def test_updateSkirmishOption_known_key(self):
        state = self._new_state()
        ok = self.m.updateSkirmishOption(state, "mapName", "TestMap")
        self.assertTrue(ok)
        self.assertEqual(state.skirmishConfig["mapName"], "TestMap")

    def test_updateSkirmishOption_unknown_key(self):
        state = self._new_state()
        ok = self.m.updateSkirmishOption(state, "totallyFakeKey", 42)
        self.assertFalse(ok)


# ===========================================================================
# 4. TestStartscriptGeneration
# ===========================================================================


class TestStartscriptGeneration(MenuBase):
    """generateStartscript produces valid Recoil startscript syntax."""

    def _gen(self, **overrides):
        cfg = {
            "mapName": "Quicksilver Remake 1.24",
            "myPlayerName": "Player",
            "numTeams": 2,
            "numAI": 1,
            "aiType": "NullAI",
            "aiDifficulty": "Medium",
            "gameMode": "tc_destruction",
        }
        cfg.update(overrides)
        tbl = self.lua.table(**{k: v for k, v in cfg.items()})
        return self.m.generateStartscript(tbl)

    def test_contains_game_block(self):
        txt = self._gen()
        self.assertIn("[GAME]", txt)

    def test_contains_allyteam0(self):
        txt = self._gen()
        self.assertIn("[ALLYTEAM0]", txt)

    def test_contains_allyteam1(self):
        txt = self._gen()
        self.assertIn("[ALLYTEAM1]", txt)

    def test_contains_team0(self):
        txt = self._gen()
        self.assertIn("[TEAM0]", txt)

    def test_contains_team1(self):
        txt = self._gen()
        self.assertIn("[TEAM1]", txt)

    def test_contains_player0(self):
        txt = self._gen()
        self.assertIn("[PLAYER0]", txt)

    def test_contains_ai0(self):
        txt = self._gen()
        self.assertIn("[AI0]", txt)

    def test_contains_modoptions(self):
        txt = self._gen()
        self.assertIn("[MODOPTIONS]", txt)

    def test_mapname_written(self):
        txt = self._gen(mapName="MyCustomMap")
        self.assertIn("MapName=MyCustomMap;", txt)

    def test_procedural_map_resolves_to_installed_base_map(self):
        """'Procedural Random Map' is a UI label; startscript must resolve to a real map archive."""
        txt = self._gen(mapName="Procedural Random Map")
        self.assertIn("MapName=Quicksilver Remake 1.24;", txt)
        self.assertIn("medievalmapgenseed=", txt)
        self.assertIn("medievalmapdensity=", txt)

    def test_ai_shortname_written(self):
        txt = self._gen(aiType="SkirmishAI")
        self.assertIn("ShortName=SkirmishAI;", txt)

    def test_modoptions_victorymode(self):
        txt = self._gen(gameMode="conquest")
        self.assertIn("victorymode=conquest;", txt)

    def test_modoptions_medievalmapgen(self):
        txt = self._gen()
        self.assertIn("medievalmapgen=", txt)

    def test_modoptions_skirmishai(self):
        txt = self._gen()
        self.assertIn("skirmishai=1;", txt)

    def test_modoptions_medievalvictory(self):
        txt = self._gen()
        self.assertIn("medievalvictory=1;", txt)

    def test_modoptions_medievalhud(self):
        txt = self._gen()
        self.assertIn("medievalhud=1;", txt)

    def test_multi_team_3_allyteams(self):
        txt = self._gen(numTeams=3, numAI=2)
        self.assertIn("[ALLYTEAM0]", txt)
        self.assertIn("[ALLYTEAM1]", txt)
        self.assertIn("[ALLYTEAM2]", txt)

    def test_multi_team_3_teams(self):
        txt = self._gen(numTeams=3, numAI=2)
        self.assertIn("[TEAM0]", txt)
        self.assertIn("[TEAM1]", txt)
        self.assertIn("[TEAM2]", txt)

    def test_multi_team_3_ai_blocks(self):
        txt = self._gen(numTeams=3, numAI=2)
        self.assertIn("[AI0]", txt)
        self.assertIn("[AI1]", txt)

    def test_multi_team_4_allyteams(self):
        txt = self._gen(numTeams=4, numAI=3)
        for i in range(4):
            self.assertIn(f"[ALLYTEAM{i}]", txt)

    def test_multi_team_4_teams(self):
        txt = self._gen(numTeams=4, numAI=3)
        for i in range(4):
            self.assertIn(f"[TEAM{i}]", txt)

    def test_multi_team_4_ai_blocks(self):
        txt = self._gen(numTeams=4, numAI=3)
        for i in range(3):
            self.assertIn(f"[AI{i}]", txt)

    def test_player_name_in_player0(self):
        txt = self._gen(myPlayerName="Hero")
        self.assertIn("Name=Hero;", txt)

    def test_ai_difficulty_in_modoptions(self):
        txt = self._gen(aiDifficulty="Hard")
        self.assertIn("aidifficulty=hard;", txt)


# ===========================================================================
# 5. TestSettingsManagement
# ===========================================================================


class TestSettingsManagement(MenuBase):
    """updateSetting: valid keys, clamping, rejection of unknown keys."""

    def test_update_masterVolume(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "masterVolume", 50)
        self.assertTrue(ok)
        self.assertEqual(state.settingsConfig["masterVolume"], 50)

    def test_update_musicVolume(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "musicVolume", 30)
        self.assertTrue(ok)
        self.assertEqual(state.settingsConfig["musicVolume"], 30)

    def test_update_sfxVolume(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "sfxVolume", 90)
        self.assertTrue(ok)
        self.assertEqual(state.settingsConfig["sfxVolume"], 90)

    def test_update_fullscreen(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "fullscreen", False)
        self.assertTrue(ok)
        self.assertFalse(state.settingsConfig["fullscreen"])

    def test_update_resolution(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "resolution", "2560x1440")
        self.assertTrue(ok)
        self.assertEqual(state.settingsConfig["resolution"], "2560x1440")

    def test_volume_clamped_above_100(self):
        state = self._new_state()
        self.m.updateSetting(state, "masterVolume", 150)
        self.assertEqual(state.settingsConfig["masterVolume"], 100)

    def test_volume_clamped_below_0(self):
        state = self._new_state()
        self.m.updateSetting(state, "sfxVolume", -20)
        self.assertEqual(state.settingsConfig["sfxVolume"], 0)

    def test_musicVolume_clamped(self):
        state = self._new_state()
        self.m.updateSetting(state, "musicVolume", 200)
        self.assertEqual(state.settingsConfig["musicVolume"], 100)

    def test_unknown_setting_rejected(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "nonexistentSetting", 42)
        self.assertFalse(ok)

    def test_update_waterQuality(self):
        state = self._new_state()
        ok = self.m.updateSetting(state, "waterQuality", "Ultra")
        self.assertTrue(ok)
        self.assertEqual(state.settingsConfig["waterQuality"], "Ultra")


# ===========================================================================
# 6. TestMenuWidgetContract
# ===========================================================================


class TestMenuWidgetContract(unittest.TestCase):
    """Widget file structure and contract checks."""

    @classmethod
    def setUpClass(cls):
        cls.src = WIDGET_PATH.read_text(encoding="utf-8")

    def test_widget_file_exists(self):
        self.assertTrue(WIDGET_PATH.exists())

    def test_getinfo_layer_1000(self):
        self.assertIn("layer   = 1000,", self.src)

    def test_getinfo_enabled_true(self):
        self.assertIn("enabled = true,", self.src)

    def test_implements_KeyPress(self):
        self.assertIn("function widget:KeyPress(", self.src)

    def test_implements_MousePress(self):
        self.assertIn("function widget:MousePress(", self.src)

    def test_implements_DrawScreen(self):
        self.assertIn("function widget:DrawScreen(", self.src)

    def test_escape_key_toggles_menu(self):
        # Escape key code 27 must appear in KeyPress context
        self.assertIn("key == 27", self.src)

    def test_gated_on_medievalmainmenu(self):
        self.assertIn("medievalmainmenu", self.src)


# ===========================================================================
# 7. TestMenuModoptions
# ===========================================================================


class TestMenuModoptions(unittest.TestCase):
    """modoptions.lua declares medievalmainmenu (bool, def = true)."""

    @classmethod
    def setUpClass(cls):
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(MODOPTIONS_PATH.read_text(encoding="utf-8"))
        cls.options = {}
        for i in range(1, len(table) + 1):
            entry = table[i]
            cls.options[entry["key"]] = entry

    def test_medievalmainmenu_exists(self):
        self.assertIn("medievalmainmenu", self.options)

    def test_medievalmainmenu_is_bool(self):
        self.assertEqual(self.options["medievalmainmenu"]["type"], "bool")

    def test_medievalmainmenu_default_true(self):
        self.assertTrue(self.options["medievalmainmenu"]["def"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
