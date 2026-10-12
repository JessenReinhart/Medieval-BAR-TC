"""Phase 7 Slice 1 tests: Audio pipeline and combat/economy soundscape.

Validates that:
1. Sound extraction manifest `tools/assets/0ad-sound-manifest.json` is well-formed,
   documents provenance under CC-BY-SA-3.0, and records exact SHA-256 hashes.
2. Every extracted sound file exists on disk in `sounds/` and matches its manifest hash.
3. `gamedata/sounds.lua` executes cleanly in bare Lua 5.1 and maps all required
   sound items (weapons, economy, UI) to valid on-disk sound files.
4. `gamedata/weapondefs.lua` weapons declare `soundStart` and `soundHit`.
5. Combat unit definitions in `units/*.lua` carry concrete weapon sound bindings
   and contain no unresolved `<... sfx>` placeholders.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools/assets/0ad-sound-manifest.json"
SOUNDS_LUA_PATH = ROOT / "gamedata/sounds.lua"
WEAPONDEFS_PATH = ROOT / "gamedata/weapondefs.lua"
UNITS_DIR = ROOT / "units"


def _lua_to_py(obj):
    if hasattr(obj, "items"):
        return {k: _lua_to_py(v) for k, v in obj.items()}
    return obj


class TestPhase7Slice1AudioManifest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            MANIFEST_PATH.exists(), f"Missing manifest: {MANIFEST_PATH}"
        )
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_metadata(self):
        self.assertEqual(
            self.manifest.get("source"), "0 A.D. alpha 28 public.zip"
        )
        self.assertIn("CC-BY-SA-3.0", self.manifest.get("license", ""))
        self.assertGreaterEqual(len(self.manifest.get("sounds", {})), 20)

    def test_all_manifest_sound_files_exist_and_match_hashes(self):
        sounds = self.manifest.get("sounds", {})
        for rel_path, meta in sounds.items():
            full_path = ROOT / rel_path
            self.assertTrue(
                full_path.exists(), f"Sound file not found: {full_path}"
            )
            data = full_path.read_bytes()
            self.assertEqual(
                len(data), meta["bytes"], f"Byte count mismatch for {rel_path}"
            )
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(
                digest, meta["sha256"], f"SHA256 mismatch for {rel_path}"
            )


class TestPhase7Slice1SoundDefinitions(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertTrue(
            SOUNDS_LUA_PATH.exists(), f"Missing: {SOUNDS_LUA_PATH}"
        )
        self.sounds_mod = _lua_to_py(
            self.lua.execute(SOUNDS_LUA_PATH.read_text(encoding="utf-8"))
        )

    def test_sound_items_present(self):
        items = self.sounds_mod.get("SoundItems", {})
        self.assertIn("sword_swing", items)
        self.assertIn("sword_hit", items)
        self.assertIn("bow_shoot", items)
        self.assertIn("arrow_hit", items)
        self.assertIn("crossbow_shoot", items)
        self.assertIn("bolt_hit", items)
        self.assertIn("lance_charge", items)
        self.assertIn("lance_hit", items)
        self.assertIn("catapult_shoot", items)
        self.assertIn("catapult_hit", items)
        self.assertIn("spear_thrust", items)
        self.assertIn("spear_hit", items)
        self.assertIn("wood_chop", items)
        self.assertIn("stone_mine", items)
        self.assertIn("building_complete", items)

    def test_sound_files_referenced_by_sound_items_exist(self):
        items = self.sounds_mod.get("SoundItems", {})
        for name, item in items.items():
            rel_file = item.get("file")
            self.assertIsNotNone(
                rel_file, f"Sound item {name} missing file property"
            )
            full_path = ROOT / rel_file
            self.assertTrue(
                full_path.exists(),
                f"Sound item {name} points to missing file: {full_path}",
            )


class TestPhase7Slice1WeaponAndUnitSounds(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.weapondefs = _lua_to_py(
            self.lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        )

    def test_weapondefs_have_sound_start_and_hit(self):
        for wname in ("sword", "longbow", "lance", "catapult", "dagger"):
            w = self.weapondefs.get(wname)
            self.assertIsNotNone(w, f"Weapondef {wname} missing")
            self.assertTrue(
                w.get("soundStart"), f"{wname} missing soundStart property"
            )
            self.assertTrue(
                w.get("soundHit"), f"{wname} missing soundHit property"
            )

    def test_combat_units_have_concrete_weapon_sounds(self):
        combat_units = [
            "medieval_archer.lua",
            "medieval_crossbow.lua",
            "medieval_infantry.lua",
            "medieval_men_at_arms.lua",
            "medieval_spearman.lua",
            "medieval_cavalry.lua",
            "medieval_knight.lua",
            "medieval_catapult.lua",
            "medieval_king.lua",
        ]
        for ufilename in combat_units:
            upath = UNITS_DIR / ufilename
            self.assertTrue(upath.exists(), f"Missing unit file: {upath}")
            text = upath.read_text(encoding="utf-8")
            self.assertNotIn(
                "<",
                text,
                f"Placeholder angle brackets remain in {ufilename}",
            )
            udef_table = _lua_to_py(self.lua.execute(text))
            uname = ufilename.replace(".lua", "")
            udef = udef_table[uname]
            weapons = udef.get("weapons", {})
            # Either numerical index 1 or direct array
            w1 = weapons.get(1) if isinstance(weapons, dict) else weapons[0]
            self.assertIsNotNone(w1, f"{ufilename} has no weapon 1")
            self.assertTrue(
                w1.get("soundStart"), f"{ufilename} weapon missing soundStart"
            )
            self.assertTrue(
                w1.get("soundHit"), f"{ufilename} weapon missing soundHit"
            )


if __name__ == "__main__":
    unittest.main()
