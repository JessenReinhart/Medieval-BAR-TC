"""Phase 7 Slice 5 tests: minimap icons, build pictures and UI polish options.

Validates that:

1. `modoptions.lua` is well-formed, every entry is complete (key/name/desc/type/
   default), defaults are valid for their type, and the slice's player-facing
   audio (`medievalaudio`) and visual (`medievalbuildicons`) toggles exist with
   the documented enabled-by-default values.
2. Every `units/*.lua` def carries a `buildpic` and an `iconType`, the buildpic
   resolves to its own on-disk `unitpics/<unitdef>.png`, and no two units share
   a picture (the placeholder recycling this slice removes cannot return).
3. The `iconType` assignments are thematic and complete: every name used is
   declared in `gamedata/icontypes.lua`, every declared type is used, and the
   mapping respects the roster's weapon/role classification.
4. `gamedata/icontypes.lua` uses only the fields the engine parses
   (`bitmap`, `size`, `distance`, `radiusAdjust`, `u0/v0/u1/v1`, `drawOrder`),
   points at real on-disk bitmaps, and those bitmaps follow the engine's
   white-on-transparent radar-icon convention.
5. `luarules/gadgets/gadget_medieval_fx.lua` gates every sound on the
   `medievalaudio` mod option while leaving the synced training/destruction log
   lines intact, and `LuaUI/Widgets/gui_medieval_build_icons.lua` consumes
   `medievalbuildicons`.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
import unittest

from lupa import LuaRuntime

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:  # pragma: no cover - PIL ships with the tooling env
    HAS_PIL = False

ROOT = Path(__file__).resolve().parents[1]
MODOPTIONS_PATH = ROOT / "modoptions.lua"
ICONTYPES_PATH = ROOT / "gamedata" / "icontypes.lua"
UNITS_DIR = ROOT / "units"
UNITPICS_DIR = ROOT / "unitpics"
MINIMAP_DIR = ROOT / "bitmaps" / "icons"
FX_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_fx.lua"
BUILD_ICONS_WIDGET_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_build_icons.lua"

# The engine only parses these keys in CIconHandler::LoadIcons; anything else in
# an icontypes entry is silently ignored and therefore a typo waiting to happen.
ICON_TYPE_KEYS = {
    "bitmap",
    "size",
    "distance",
    "radiusAdjust",
    "u0",
    "v0",
    "u1",
    "v1",
    "drawOrder",
}

# The slice's roster: 11 combat/utility units + 11 buildings.
EXPECTED_ICON_TYPES = {
    "medieval_melee",
    "medieval_spear",
    "medieval_ranged",
    "medieval_cavalry",
    "medieval_siege",
    "medieval_builder",
    "medieval_supply",
    "medieval_royal",
    "medieval_military_building",
    "medieval_economy_building",
    "medieval_defense",
}

# Thematic assignment contract: unit def name -> icon type.
EXPECTED_UNIT_ICONS = {
    "medieval_villager": "medieval_builder",
    "medieval_cart": "medieval_supply",
    "medieval_infantry": "medieval_melee",
    "medieval_men_at_arms": "medieval_melee",
    "medieval_spearman": "medieval_spear",
    "medieval_archer": "medieval_ranged",
    "medieval_crossbow": "medieval_ranged",
    "medieval_cavalry": "medieval_cavalry",
    "medieval_knight": "medieval_cavalry",
    "medieval_catapult": "medieval_siege",
    "medieval_king": "medieval_royal",
    "medieval_town_center": "medieval_royal",
    "medieval_barracks": "medieval_military_building",
    "medieval_stables": "medieval_military_building",
    "medieval_blacksmith": "medieval_economy_building",
    "medieval_fletcher": "medieval_economy_building",
    "medieval_granary": "medieval_economy_building",
    "medieval_house": "medieval_economy_building",
    "medieval_lumber_camp": "medieval_economy_building",
    "medieval_market": "medieval_economy_building",
    "medieval_tower": "medieval_defense",
    "medieval_wall": "medieval_defense",
}

MILITARY_ICONS = {
    "medieval_melee",
    "medieval_spear",
    "medieval_ranged",
    "medieval_cavalry",
    "medieval_siege",
}

BUILDING_ICONS = {
    "medieval_military_building",
    "medieval_economy_building",
    "medieval_defense",
}

# Valid Recoil UnitDef category strings for a ground-only medieval conversion.
VALID_CATEGORIES = {"LAND"}

MODOPTION_TYPES = {"bool", "number", "string", "list"}


def _lua_to_py(obj):
    """Recursively convert a Lua table (or scalar) into Python objects.

    Lua has no array/map distinction, so a table whose keys are exactly
    1..n is returned as a list and anything else as a dict. modoptions.lua is
    a top-level array, units/*.lua are name-keyed maps.
    """
    if not hasattr(obj, "items"):
        return obj
    pairs = {k: _lua_to_py(v) for k, v in obj.items()}
    if pairs and all(isinstance(k, int) for k in pairs):
        if sorted(pairs) == list(range(1, len(pairs) + 1)):
            return [pairs[i] for i in range(1, len(pairs) + 1)]
    return pairs


def _load_lua(path: Path):
    lua = LuaRuntime(unpack_returned_tuples=True)
    return _lua_to_py(lua.execute(path.read_text(encoding="utf-8")))


def _png_header(path: Path):
    """Return (width, height, bit_depth, color_type) from a PNG IHDR."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    length, chunk_type = struct.unpack(">I4s", data[8:16])
    if chunk_type != b"IHDR" or length != 13:
        raise AssertionError(f"{path} has no leading IHDR chunk")
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    return width, height, depth, color_type


def _unit_defs():
    """unit def name -> def table, for every def in units/*.lua."""
    defs = {}
    for path in sorted(UNITS_DIR.glob("*.lua")):
        for name, body in _load_lua(path).items():
            defs[name] = body
    return defs


# ---------------------------------------------------------------------------
# 1. modoptions.lua
# ---------------------------------------------------------------------------


class TestPhase7Slice5Modoptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = _load_lua(MODOPTIONS_PATH)
        cls.by_key = {entry["key"]: entry for entry in cls.entries}

    def test_is_a_non_empty_array_of_entries(self):
        self.assertIsInstance(self.entries, list)
        self.assertGreaterEqual(len(self.entries), 8)
        for entry in self.entries:
            self.assertIsInstance(entry, dict)

    def test_every_entry_is_complete(self):
        for entry in self.entries:
            key = entry.get("key")
            self.assertTrue(key, f"entry without a key: {entry}")
            self.assertTrue(entry.get("name"), f"{key} has no player-facing name")
            self.assertTrue(entry.get("desc"), f"{key} has no player-facing desc")
            self.assertIn(
                entry.get("type"),
                MODOPTION_TYPES,
                f"{key} has an unsupported modoption type",
            )
            self.assertIn("def", entry, f"{key} declares no default")

    def test_keys_are_unique(self):
        keys = [entry["key"] for entry in self.entries]
        self.assertEqual(len(keys), len(set(keys)), f"duplicate modoption keys: {keys}")

    def test_defaults_are_valid_for_their_type(self):
        for entry in self.entries:
            key = entry["key"]
            value = entry["def"]
            with self.subTest(key=key):
                if entry["type"] == "bool":
                    self.assertIn(value, (True, False))
                elif entry["type"] == "number":
                    self.assertIsInstance(value, (int, float))
                    if "min" in entry:
                        self.assertGreaterEqual(value, entry["min"])
                    if "max" in entry:
                        self.assertLessEqual(value, entry["max"])
                elif entry["type"] == "string":
                    self.assertIsInstance(value, str)
                elif entry["type"] == "list":
                    keys = [item["key"] for item in entry["items"]]
                    self.assertIn(value, keys)

    def test_audio_toggle_is_player_facing_and_enabled_by_default(self):
        entry = self.by_key.get("medievalaudio")
        self.assertIsNotNone(entry, "modoptions.lua must declare medievalaudio")
        self.assertEqual(entry["type"], "bool")
        self.assertIs(entry["def"], True)
        self.assertIn("Audio", entry["name"])
        self.assertIn("sound", entry["desc"].lower())

    def test_visual_toggle_is_player_facing_and_enabled_by_default(self):
        entry = self.by_key.get("medievalbuildicons")
        self.assertIsNotNone(entry, "modoptions.lua must declare medievalbuildicons")
        self.assertEqual(entry["type"], "bool")
        self.assertIs(entry["def"], True)
        self.assertIn("Icon", entry["name"])
        self.assertIn("icon", entry["desc"].lower())

    def test_existing_subsystem_options_survive(self):
        for key in (
            "medievalvictory",
            "medievalhud",
            "medievalmarket",
            "medievalgarrison",
            "medievaltactics",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.by_key)


# ---------------------------------------------------------------------------
# 2. Build pictures
# ---------------------------------------------------------------------------


class TestPhase7Slice5BuildPictures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = _unit_defs()

    def test_every_def_declares_a_buildpic(self):
        for name, body in self.defs.items():
            with self.subTest(unit=name):
                self.assertEqual(
                    body.get("buildpic"),
                    f"{name}.png",
                    f"{name} must point at its own dedicated build picture",
                )

    def test_every_buildpic_exists_on_disk(self):
        for name, body in self.defs.items():
            path = UNITPICS_DIR / body["buildpic"]
            with self.subTest(unit=name):
                self.assertTrue(path.exists(), f"missing build picture: {path}")

    def test_buildpics_are_well_formed_squares(self):
        for name, body in self.defs.items():
            path = UNITPICS_DIR / body["buildpic"]
            with self.subTest(unit=name):
                width, height, depth, color_type = _png_header(path)
                self.assertEqual((width, height), (128, 128))
                self.assertEqual(depth, 8)
                self.assertIn(color_type, (2, 6))

    def test_buildpics_are_all_distinct(self):
        digests = {}
        for name, body in self.defs.items():
            path = UNITPICS_DIR / body["buildpic"]
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(
            len(set(digests.values())),
            len(digests),
            "two units share a build picture; the slice must ship 22 distinct icons",
        )

    def test_roster_and_pictures_match_one_to_one(self):
        self.assertEqual(len(self.defs), 22)
        on_disk = {p.stem for p in UNITPICS_DIR.glob("*.png")}
        self.assertEqual(on_disk, set(self.defs), "unitpics/ and units/ disagree")

    def test_no_buildpic_references_an_upstream_bar_asset(self):
        # The whole point of generating the pictures locally: nothing may point
        # at a BAR/CC-BY-NC-ND file.
        for name, body in self.defs.items():
            with self.subTest(unit=name):
                self.assertNotIn(".dds", body["buildpic"].lower())
                self.assertNotIn("unitpics/", body["buildpic"])


# ---------------------------------------------------------------------------
# 3. Radar / minimap icon types
# ---------------------------------------------------------------------------


class TestPhase7Slice5IconTypes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = _unit_defs()
        cls.icon_types = _load_lua(ICONTYPES_PATH)

    def test_icontypes_declares_the_expected_set(self):
        self.assertEqual(set(self.icon_types), EXPECTED_ICON_TYPES)

    def test_every_def_declares_an_icontype(self):
        for name, body in self.defs.items():
            with self.subTest(unit=name):
                icon = body.get("iconType")
                self.assertIsInstance(icon, str)
                self.assertTrue(icon, f"{name} has an empty iconType")

    def test_every_used_icontype_is_declared(self):
        declared = set(self.icon_types)
        for name, body in self.defs.items():
            with self.subTest(unit=name):
                self.assertIn(
                    body["iconType"],
                    declared,
                    f"{name} uses an iconType the engine cannot resolve",
                )

    def test_every_declared_icontype_is_used(self):
        used = {body["iconType"] for body in self.defs.values()}
        self.assertEqual(set(self.icon_types), used, "dead icon types in icontypes.lua")

    def test_assignments_are_thematic(self):
        for name, expected in EXPECTED_UNIT_ICONS.items():
            with self.subTest(unit=name):
                self.assertIn(name, self.defs)
                self.assertEqual(self.defs[name]["iconType"], expected)

    def test_combat_units_use_combat_icons(self):
        for name, body in self.defs.items():
            if not body.get("canAttack"):
                continue
            with self.subTest(unit=name):
                self.assertIn(
                    body["iconType"],
                    MILITARY_ICONS | {"medieval_royal"},
                    f"{name} is armed but has a non-combat radar icon",
                )

    def test_static_buildings_use_building_icons(self):
        for name, body in self.defs.items():
            if body.get("canMove") is not False or body.get("builder"):
                continue
            with self.subTest(unit=name):
                self.assertIn(
                    body["iconType"],
                    BUILDING_ICONS | {"medieval_royal"},
                    f"{name} is a static structure but has a mobile-unit icon",
                )

    def test_every_def_has_a_valid_category(self):
        for name, body in self.defs.items():
            with self.subTest(unit=name):
                self.assertIn(body.get("category"), VALID_CATEGORIES)

    def test_builders_and_carts_get_utility_icons(self):
        self.assertEqual(self.defs["medieval_villager"]["iconType"], "medieval_builder")
        self.assertEqual(self.defs["medieval_cart"]["iconType"], "medieval_supply")

    def test_icon_entries_use_only_engine_parsed_fields(self):
        for name, entry in self.icon_types.items():
            with self.subTest(icon=name):
                self.assertIsInstance(entry, dict)
                unknown = set(entry) - ICON_TYPE_KEYS
                self.assertEqual(unknown, set(), f"{name} has unparsed keys: {unknown}")
                self.assertIn("bitmap", entry)
                self.assertIsInstance(entry["bitmap"], str)
                self.assertIsInstance(entry.get("size"), (int, float))
                self.assertGreater(entry.get("size", 0), 0)
                self.assertIsInstance(entry.get("distance"), (int, float))
                self.assertGreater(entry.get("distance", 0), 0)
                self.assertIsInstance(entry.get("radiusAdjust"), bool)

    def test_icon_bitmaps_exist_and_are_reachable_from_the_vfs_root(self):
        for name, entry in self.icon_types.items():
            with self.subTest(icon=name):
                bitmap = entry["bitmap"]
                # No leading slash: the engine resolves bitmap paths relative to
                # the VFS root, exactly like bitmaps/defaultradardot.png.
                self.assertFalse(bitmap.startswith("/"))
                self.assertTrue((ROOT / bitmap).exists(), f"missing icon bitmap {bitmap}")

    def test_icon_bitmaps_follow_the_radar_dot_convention(self):
        for name, entry in self.icon_types.items():
            with self.subTest(icon=name):
                path = ROOT / entry["bitmap"]
                width, height, depth, color_type = _png_header(path)
                self.assertEqual((width, height), (64, 64))
                self.assertEqual(color_type, 6, "radar icons must carry an alpha channel")
                self.assertEqual(depth, 8)

    def test_icon_bitmaps_are_distinct_and_non_empty(self):
        digests = {}
        for name, entry in self.icon_types.items():
            path = ROOT / entry["bitmap"]
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(len(set(digests.values())), len(digests))

    @unittest.skipUnless(HAS_PIL, "Pillow not installed")
    def test_icon_bitmaps_are_white_with_a_populated_alpha(self):
        for name, entry in self.icon_types.items():
            with self.subTest(icon=name):
                image = Image.open(ROOT / entry["bitmap"]).convert("RGBA")
                alpha = image.getchannel("A")
                histogram = alpha.histogram()
                pixels = image.width * image.height

                opaque = sum(histogram[129:])
                self.assertGreater(opaque, 40, f"{name} renders nothing")
                self.assertLess(
                    opaque, pixels * 0.8, f"{name} is a filled square, not a glyph"
                )
                # Team colour is applied as a modulation, so every visible texel
                # must stay exactly white (the defaultradardot.png convention).
                red = image.getchannel("R")
                self.assertEqual(
                    red.getextrema(), (255, 255), f"{name} has non-white RGB"
                )
                green = image.getchannel("G")
                self.assertEqual(
                    green.getextrema(), (255, 255), f"{name} has non-white RGB"
                )
                blue = image.getchannel("B")
                self.assertEqual(
                    blue.getextrema(), (255, 255), f"{name} has non-white RGB"
                )


# ---------------------------------------------------------------------------
# 4. Gadget: medievalaudio gating
# ---------------------------------------------------------------------------

GADGET_HARNESS = r"""
GADGET_SRC = io.open(ROOT_PATH .. "/luarules/gadgets/gadget_medieval_fx.lua", "r"):read("*a")

MODOPTIONS = { medievalaudio = MODOPTION_VALUE }
SOUND_CALLS = {}
ECHO_CALLS = {}
GAME_RULES = {}

UnitDefs = {
  [1] = { name = "medieval_town_center", isFactory = true, canMove = false },
  [2] = { name = "medieval_infantry", isFactory = false, canMove = true },
  [3] = { name = "armcom", isFactory = false, canMove = true },
}

gadgetHandler = { IsSyncedCode = function() return true end }

Spring = {
  GetModOptions = function() return MODOPTIONS end,
  PlaySoundFile = function(path)
    if PLAY_SOUND_RAISES then error("no audio device") end
    SOUND_CALLS[#SOUND_CALLS + 1] = path
    return true
  end,
  Echo = function(text) ECHO_CALLS[#ECHO_CALLS + 1] = text end,
  SetGameRulesParam = function(key, value) GAME_RULES[key] = value end,
}

GG = {}
gadget = {}

assert(load(GADGET_SRC, "@gadget_medieval_fx.lua", "t", _G))()

function Initialize() gadget:Initialize() end
function UnitCreated(id, defID, team) gadget:UnitCreated(id, defID, team) end
function UnitFinished(id, defID, team) gadget:UnitFinished(id, defID, team) end
function UnitDestroyed(id, defID, team) gadget:UnitDestroyed(id, defID, team) end
function SoundCount() return #SOUND_CALLS end
function EchoCount() return #ECHO_CALLS end
function AudioEnabled() return GG.MedievalFX.audioEnabled end
"""


class TestPhase7Slice5FxGadget(unittest.TestCase):
    def _boot(self, modoption, play_sound_raises=False):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        lua.globals().MODOPTION_VALUE = modoption
        lua.globals().PLAY_SOUND_RAISES = play_sound_raises
        lua.execute(GADGET_HARNESS)
        return lua

    def test_gadget_reads_the_medievalaudio_option(self):
        source = FX_GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("GetModOptions", source)
        self.assertIn('"medievalaudio"', source)

    def test_audio_enabled_by_default_when_the_key_is_absent(self):
        lua = self._boot(None)
        self.assertTrue(lua.eval("AudioEnabled()"))

    def test_audio_enabled_for_truthy_option_spellings(self):
        for value in (1, True, "1", "true"):
            with self.subTest(value=value):
                lua = self._boot(value)
                self.assertTrue(lua.eval("AudioEnabled()"))

    def test_audio_disabled_for_falsy_option_spellings(self):
        for value in (0, False, "0", "false"):
            with self.subTest(value=value):
                lua = self._boot(value)
                self.assertFalse(lua.eval("AudioEnabled()"))

    def test_building_completion_plays_a_sound_when_enabled(self):
        lua = self._boot(1)
        lua.execute("UnitFinished(10, 1, 0)")
        self.assertEqual(lua.eval("SoundCount()"), 1)

    def test_building_completion_is_silent_when_disabled(self):
        lua = self._boot(0)
        lua.execute("UnitFinished(10, 1, 0)")
        self.assertEqual(lua.eval("SoundCount()"), 0)

    def test_mobile_units_never_play_the_building_sound(self):
        lua = self._boot(1)
        lua.execute("UnitFinished(11, 2, 0)")
        lua.execute("UnitFinished(12, 3, 0)")
        self.assertEqual(lua.eval("SoundCount()"), 0)

    def test_a_failing_audio_backend_is_tolerated(self):
        lua = self._boot(1, play_sound_raises=True)
        lua.execute("UnitFinished(10, 1, 0)")
        self.assertEqual(lua.eval("SoundCount()"), 0)

    def test_synced_log_lines_survive_audio_muting(self):
        # The headless probes grep these lines; muting audio must not hide them.
        for value in (0, 1):
            with self.subTest(medievalaudio=value):
                lua = self._boot(value)
                lua.execute("UnitCreated(1, 2, 0)")
                lua.execute("UnitDestroyed(1, 2, 0)")
                self.assertEqual(lua.eval("EchoCount()"), 2)

    def test_non_medieval_units_are_ignored(self):
        lua = self._boot(1)
        lua.execute("UnitCreated(3, 3, 0)")
        lua.execute("UnitDestroyed(3, 3, 0)")
        lua.execute("UnitFinished(3, 3, 0)")
        self.assertEqual(lua.eval("EchoCount()"), 0)
        self.assertEqual(lua.eval("SoundCount()"), 0)

    def test_audio_state_is_published_as_a_rules_param(self):
        lua = self._boot(0)
        lua.execute("Initialize()")
        self.assertEqual(lua.eval("GAME_RULES.medieval_audio"), 0)

        lua = self._boot(1)
        lua.execute("Initialize()")
        self.assertEqual(lua.eval("GAME_RULES.medieval_audio"), 1)


# ---------------------------------------------------------------------------
# 5. Widget: medievalbuildicons consumer
# ---------------------------------------------------------------------------

WIDGET_HARNESS = r"""
WIDGET_SRC = io.open(ROOT_PATH .. "/LuaUI/Widgets/gui_medieval_build_icons.lua", "r"):read("*a")

MODOPTIONS = { medievalbuildicons = MODOPTION_VALUE }
ICON_CALLS = {}

UnitDefs = {
  [1] = { name = "medieval_town_center" },
  [2] = { name = "medieval_infantry" },
  [3] = { name = "armcom" },
}

Spring = {
  GetModOptions = function() return MODOPTIONS end,
  SetUnitDefIcon = function(defID, iconName)
    if SET_ICON_RAISES then error("Invalid icon name") end
    ICON_CALLS[#ICON_CALLS + 1] = { defID, iconName }
  end,}

widget = {}
assert(load(WIDGET_SRC, "@gui_medieval_build_icons.lua", "t", _G))()

function Initialize() widget:Initialize() end
function IconsEnabled() return widget.medievalIconsEnabled end
function IconCount() return #ICON_CALLS end
function IconTargets()
  local t = {}
  for i, call in ipairs(ICON_CALLS) do t[i] = call[1] end
  return t
end
function IconNames()
  local t = {}
  for i, call in ipairs(ICON_CALLS) do t[i] = call[2] end
  return t
end
"""


class TestPhase7Slice5BuildIconsWidget(unittest.TestCase):
    def _boot(self, modoption, set_icon_raises=False):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        lua.globals().MODOPTION_VALUE = modoption
        lua.globals().SET_ICON_RAISES = set_icon_raises
        lua.execute(WIDGET_HARNESS)
        return lua

    def test_widget_metadata(self):
        lua = self._boot(True)
        info = lua.eval("widget:GetInfo()")
        self.assertEqual(info["name"], "Medieval Build Icons")
        self.assertEqual(info["license"], "GPL-v2")

    def test_enabled_by_default_when_the_key_is_absent(self):
        lua = self._boot(None)
        self.assertTrue(lua.eval("IconsEnabled()"))

    def test_disabled_only_for_falsy_option_spellings(self):
        for value in (0, False, "0"):
            with self.subTest(value=value):
                self.assertFalse(self._boot(value).eval("IconsEnabled()"))
        for value in (1, True, "1", None):
            with self.subTest(value=value):
                self.assertTrue(self._boot(value).eval("IconsEnabled()"))

    def test_no_override_while_the_option_is_enabled(self):
        lua = self._boot(1)
        lua.execute("Initialize()")
        self.assertEqual(lua.eval("IconCount()"), 0)

    def test_disabling_the_option_restores_plain_radar_dots(self):
        lua = self._boot(0)
        lua.execute("Initialize()")
        targets = lua.eval("IconTargets()")
        self.assertEqual(sorted(targets.values()), [1, 2])
        names = lua.eval("IconNames()")
        self.assertEqual({names[i] for i in names}, {"default"})

    def test_engine_rejection_is_tolerated(self):
        lua = self._boot(0, set_icon_raises=True)
        lua.execute("Initialize()")
        self.assertEqual(lua.eval("IconCount()"), 0)


if __name__ == "__main__":
    unittest.main()
