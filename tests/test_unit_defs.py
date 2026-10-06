"""
Automated validation test suite for Phase 1 unit definitions and licensing.
Validates units/medieval_infantry.lua, units/medieval_archer.lua, units/medieval_cavalry.lua.
Verifies Recoil engine conventions, movedef compatibility, scripts, placeholder models,
and strict avoidance of CC-BY-NC-ND assets.
"""

import os
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UNITS_DIR = REPO_ROOT / "units"
SCRIPTS_DIR = REPO_ROOT / "scripts"
OBJECTS_DIR = REPO_ROOT / "objects3d"
CREDITS_FILE = REPO_ROOT / "CREDITS.md"
LICENSE_FILE = REPO_ROOT / "LICENSE.md"
WEAPONDEFS_FILE = REPO_ROOT / "gamedata" / "weapondefs.lua"

VALID_MOVEDEFS = {
    "BOT2", "BOT3", "HBOT4", "HABOT5", "HTBOT6", "VBOT6", "HBOT7", "TBOT3",
    "SBOT2", "ABOT3", "ABOTBOMB2", "COMMANDERBOT", "SCAVCOMMANDERBOT", "EPICBOT",
    "TANK2", "TANK3", "MTANK3", "HTANK4", "HTANK7", "ATANK3",
}

FORBIDDEN_ASSET_PATTERNS = [
    r"armwar",
    r"armrock",
    r"armfav",
    r"\.cob\b",
    r"\.bos\b",
    r"CC-BY-NC-ND",
]

try:
    import lupa
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False


def load_lua_unit(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    if HAS_LUPA:
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(code)
        def lua_to_py(obj):
            if lua.eval("type")(obj) == "table":
                d = {}
                for k in obj:
                    val = obj[k]
                    d[k] = lua_to_py(val)
                return d
            return obj
        return lua_to_py(table)

    # Fallback basic parser if lupa unavailable
    return parse_lua_table_simple(code)


def parse_lua_table_simple(code: str) -> dict:
    unit_id_match = re.search(r"^\s*([a-zA-Z0-9_]+)\s*=\s*\{", code, re.MULTILINE)
    unit_id = unit_id_match.group(1) if unit_id_match else "unknown"
    data = {}
    for line in code.splitlines():
        line = line.split("--")[0].strip()
        m = re.match(r'([a-zA-Z0-9_]+)\s*=\s*["\']([^"\']+)["\']', line)
        if m:
            data[m.group(1)] = m.group(2)
            continue
        m = re.match(r'([a-zA-Z0-9_]+)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)', line)
        if m:
            val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
            data[m.group(1)] = val
            continue
        m = re.match(r'([a-zA-Z0-9_]+)\s*=\s*(true|false)', line)
        if m:
            data[m.group(1)] = (m.group(2) == "true")
            continue
    return {unit_id: data}


class TestUnitDefinitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected_units = {
            "medieval_infantry": UNITS_DIR / "medieval_infantry.lua",
            "medieval_archer": UNITS_DIR / "medieval_archer.lua",
            "medieval_cavalry": UNITS_DIR / "medieval_cavalry.lua",
        }
        cls.unit_defs = {}
        for unit_id, path in cls.expected_units.items():
            if not path.exists():
                raise AssertionError(f"Unit file missing: {path}")
            table = load_lua_unit(path)
            if unit_id not in table:
                raise AssertionError(f"Unit key {unit_id} not returned in {path}")
            cls.unit_defs[unit_id] = table[unit_id]
        cls.weapon_defs = load_lua_unit(WEAPONDEFS_FILE) if WEAPONDEFS_FILE.exists() else {}

    def test_movement_classes_valid_in_recoil(self):
        for unit_id, defn in self.unit_defs.items():
            self.assertTrue(defn.get("canMove"), f"{unit_id} must have canMove = true")
            mclass = defn.get("movementclass")
            self.assertIsNotNone(mclass, f"{unit_id} missing movementclass")
            self.assertIn(mclass, VALID_MOVEDEFS, f"{unit_id} has invalid movedef '{mclass}'")

        self.assertEqual(self.unit_defs["medieval_infantry"]["movementclass"], "BOT2")
        self.assertEqual(self.unit_defs["medieval_archer"]["movementclass"], "BOT2")
        self.assertEqual(self.unit_defs["medieval_cavalry"]["movementclass"], "TANK3")

    def test_footprints_match_movedef(self):
        inf = self.unit_defs["medieval_infantry"]
        arc = self.unit_defs["medieval_archer"]
        cav = self.unit_defs["medieval_cavalry"]
        self.assertEqual(inf.get("footprintX"), 2)
        self.assertEqual(inf.get("footprintZ"), 2)
        self.assertEqual(arc.get("footprintX"), 2)
        self.assertEqual(arc.get("footprintZ"), 2)
        self.assertEqual(cav.get("footprintX"), 3)
        self.assertEqual(cav.get("footprintZ"), 3)

    def test_cavalry_speed_and_mass(self):
        cav = self.unit_defs["medieval_cavalry"]
        inf = self.unit_defs["medieval_infantry"]
        arc = self.unit_defs["medieval_archer"]

        self.assertGreater(cav.get("speed", 0), inf.get("speed", 0), "Cavalry speed must exceed infantry")
        self.assertGreater(cav.get("speed", 0), arc.get("speed", 0), "Cavalry speed must exceed archer")
        self.assertGreater(cav.get("mass", 0), inf.get("mass", 0), "Cavalry mass must exceed infantry")
        self.assertGreater(cav.get("mass", 0), arc.get("mass", 0), "Cavalry mass must exceed archer")
        self.assertGreater(cav.get("maxVelocity", 0), inf.get("maxVelocity", 0))

    def test_melee_infantry_weapon_definition(self):
        inf = self.unit_defs["medieval_infantry"]
        weapons = inf.get("weapons", {})
        weapon_names = [w.get("name") or w.get("def") for w in weapons.values()] if isinstance(weapons, dict) else [w.get("name") or w.get("def") for w in weapons]
        self.assertTrue(any(n and n.lower() == "sword" for n in weapon_names), f"medieval_infantry missing sword weapon reference: {weapon_names}")
        sword = self.weapon_defs.get("sword") or self.weapon_defs.get("SWORD") or {}
        self.assertEqual(sword.get("weaponType"), "Melee")
        self.assertFalse(sword.get("turret", True), "Melee sword must not be a turret")
        self.assertLessEqual(sword.get("range", 999), 60, "Melee weapon range should be close combat")

    def test_archer_ballistic_weapon_definition(self):
        arc = self.unit_defs["medieval_archer"]
        weapons = arc.get("weapons", {})
        weapon_names = [w.get("name") or w.get("def") for w in weapons.values()] if isinstance(weapons, dict) else [w.get("name") or w.get("def") for w in weapons]
        self.assertTrue(any(n and n.lower() == "longbow" for n in weapon_names), f"medieval_archer missing longbow weapon reference: {weapon_names}")
        bow = self.weapon_defs.get("longbow") or self.weapon_defs.get("LONGBOW") or {}
        self.assertEqual(bow.get("weaponType"), "Cannon")
        self.assertTrue(bow.get("turret", False), "Archer weapon requires turret aiming")
        self.assertGreater(bow.get("weaponVelocity", 0), 100, "Ballistic projectile requires velocity")
        self.assertGreater(bow.get("range", 0), 200, "Archer requires ranged engagement envelope")
        self.assertIn("heightBoostFactor", bow, "Ballistic archer should configure heightBoostFactor")
        self.assertIn("myGravity", bow, "Ballistic archer should configure myGravity")

    def test_cavalry_lance_weapon_definition(self):
        cav = self.unit_defs["medieval_cavalry"]
        weapons = cav.get("weapons", {})
        weapon_names = [w.get("name") or w.get("def") for w in weapons.values()] if isinstance(weapons, dict) else [w.get("name") or w.get("def") for w in weapons]
        self.assertTrue(any(n and n.lower() == "lance" for n in weapon_names), f"medieval_cavalry missing lance weapon reference: {weapon_names}")
        lance = self.weapon_defs.get("lance") or self.weapon_defs.get("LANCE") or {}
        self.assertEqual(lance.get("weaponType"), "Melee")
        self.assertFalse(lance.get("turret", True))
        self.assertLessEqual(lance.get("range", 999), 70)

    def test_script_and_model_endpoints_exist(self):
        for unit_id, defn in self.unit_defs.items():
            script_file = defn.get("script")
            self.assertIsNotNone(script_file, f"{unit_id} missing script endpoint")
            script_path = SCRIPTS_DIR / script_file
            self.assertTrue(script_path.exists(), f"Script file {script_path} does not exist")

            with open(script_path, "r", encoding="utf-8") as sf:
                script_code = sf.read()
            for required_call in ["AimFromWeapon", "QueryWeapon", "AimWeapon", "FireWeapon", "piece"]:
                self.assertIn(required_call, script_code, f"{script_path} missing LUS function/call {required_call}")

            model_file = defn.get("objectName")
            self.assertIsNotNone(model_file, f"{unit_id} missing objectName")
            model_path = OBJECTS_DIR / model_file
            self.assertTrue(model_path.exists(), f"Model file {model_path} does not exist")


class TestLicensingCompliance(unittest.TestCase):
    def test_no_forbidden_bar_assets_in_unit_defs(self):
        for fname in ["medieval_infantry.lua", "medieval_archer.lua", "medieval_cavalry.lua"]:
            fpath = UNITS_DIR / fname
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            for pat in FORBIDDEN_ASSET_PATTERNS:
                self.assertIsNone(
                    re.search(pat, content, re.IGNORECASE),
                    f"Forbidden pattern '{pat}' found in {fname}"
                )

    def test_credits_and_license_files_exist_and_document_policy(self):
        self.assertTrue(CREDITS_FILE.exists(), "CREDITS.md missing")
        self.assertTrue(LICENSE_FILE.exists(), "LICENSE.md missing")

        with open(CREDITS_FILE, "r", encoding="utf-8") as f:
            credits_text = f.read()
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            license_text = f.read()

        self.assertIn("c7eaa46992959435c6d3332e28e1169e1ddd43a6", credits_text)
        self.assertIn("CC-BY-NC-ND", credits_text)
        self.assertIn("no-derivatives", credits_text)
        self.assertIn("Cremuss", credits_text)

        self.assertIn("GPL", license_text)
        self.assertIn("CC-BY-NC-ND", license_text)
        self.assertIn("no-derivatives", license_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
