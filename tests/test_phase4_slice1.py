"""
Phase-4 Slice 1 tests: siege warfare core (medieval_catapult).

Validates four things, each against the real repository files:

1. `units/medieval_catapult.lua` — identity, footprint/movementclass agreement,
   speed/damage envelope, `0ad/medieval_catapult.obj` + `medieval_catapult.lua`
   bindings, discrete `resource_cost_*` customparams, and the weapon entry.
2. `gamedata/weapondefs.lua` "catapult" — 550 range, 120 minRange dead zone
   (design value; enforced in the LUS because this engine build does not implement
   the tag), 5.0 reload, 350 velocity, ballistic `myGravity`/`heightBoostFactor`,
   500 default damage, 48 AoE with 0.5 edge effectiveness, turret + tolerance,
   and `noSelfDamage` (the mesh has no muzzle piece).
3. `scripts/medieval_catapult.lua` — compiles under LuaJIT/Lua, exports the LUS
   call-ins, resolves every weapon call-in to the single "base" piece, enforces the
   120-elmo dead zone, and publishes aim/fire rules params for the headless probe.
4. Economy/recruitment/housing integration — the catapult's discrete cost is
   affordable from starting reserves, its mirrored `medieval_recruitment.COSTS`
   entry matches the unitdef, it pays food upkeep as a military unit, and it
   consumes 1 population.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
UNITS_DIR = ROOT / "units"
SCRIPTS_DIR = ROOT / "scripts"
WEAPONDEFS_PATH = ROOT / "gamedata" / "weapondefs.lua"
OBJECTS_DIR = ROOT / "objects3d" / "0ad"
TEXTURES_DIR = ROOT / "unittextures" / "0ad"
MANIFEST_PATH = ROOT / "tools" / "assets" / "0ad-manifest.json"

UNIT_NAME = "medieval_catapult"


def _lua_table_to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists."""
    if lua.eval("type")(value) == "table":
        # Array-like tables become lists; maps become dicts.
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_table_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_table_to_py(lua, value[k]) for k in keys}
    return value


class TestCatapultUnitDef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        table = cls.lua.execute((UNITS_DIR / f"{UNIT_NAME}.lua").read_text(encoding="utf-8"))
        cls.defn = _lua_table_to_py(cls.lua, table[UNIT_NAME])

    def test_identity(self):
        self.assertEqual(self.defn["name"], "Catapult")
        self.assertEqual(self.defn["description"], "Siege engine firing heavy stones at long range")
        self.assertEqual(self.defn["category"], "LAND")
        self.assertEqual(self.defn["side"], "MEDIEVAL")

    def test_mobility_and_footprint_agree_with_movedef(self):
        self.assertTrue(self.defn["canMove"])
        self.assertTrue(self.defn["canAttack"])
        self.assertEqual(self.defn["footprintX"], 3)
        self.assertEqual(self.defn["footprintZ"], 3)
        self.assertEqual(self.defn["speed"], 18)
        self.assertEqual(self.defn["maxVelocity"], 1.2)
        # TANK3 is the repository's 3x3 vehicle move def (see gamedata/movedefs.lua);
        # BOT2 declares a 2x2 footprint and would contradict the def above.
        self.assertEqual(self.defn["movementclass"], "TANK3")

    def test_survivability_envelope(self):
        self.assertEqual(self.defn["maxDamage"], 600)
        self.assertGreater(self.defn["mass"], 0)
        self.assertTrue(self.defn["upright"])

    def test_art_and_script_bindings(self):
        self.assertEqual(self.defn["objectName"], "0ad/medieval_catapult.obj")
        self.assertEqual(self.defn["script"], "medieval_catapult.lua")

    def test_discrete_resource_costs(self):
        cp = self.defn["customparams"]
        self.assertEqual(cp["resource_cost_wood"], 120)
        self.assertEqual(cp["resource_cost_stone"], 40)
        self.assertEqual(cp["resource_cost_iron"], 10)
        self.assertEqual(cp["unitgroup"], "weapon")
        # The catapult is built from wood/stone/iron; it must not silently carry a
        # food cost that the recruitment gadget would charge from another pool.
        self.assertNotIn("resource_cost_food", cp)

    def test_weapon_table(self):
        weapons = self.defn["weapons"]
        self.assertEqual(len(weapons), 1)
        weapon = weapons[0]
        self.assertEqual(weapon["name"], "catapult")
        self.assertEqual(list(weapon["mainDir"]), [0, 0, 1])
        # Full traverse: the lithobolos sits on a turntable. A narrow arc combined
        # with an unconditional LUS `return true` lets the engine fire while the
        # barrel still points off-axis, and the rock then lands nowhere near the
        # target (observed in-engine before this was widened to 360).
        self.assertEqual(weapon["maxAngleDif"], 360)
        self.assertEqual(weapon["onlyTargetCategory"], "LAND")


class TestCatapultWeaponDef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        table = cls.lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        cls.defn = _lua_table_to_py(cls.lua, table["catapult"])

    def test_identity_and_type(self):
        self.assertEqual(self.defn["name"], "Catapult Rock")
        self.assertEqual(self.defn["weaponType"], "Cannon")
        self.assertTrue(self.defn["turret"])
        self.assertEqual(self.defn["tolerance"], 8000)

    def test_range_window_has_a_dead_zone(self):
        self.assertEqual(self.defn["range"], 550)
        self.assertEqual(self.defn["minRange"], 120)
        self.assertLess(self.defn["minRange"], self.defn["range"])

    def test_slow_heavy_reload(self):
        self.assertEqual(self.defn["reloadtime"], 5.0)

    def test_ballistic_profile(self):
        self.assertEqual(self.defn["weaponVelocity"], 350)
        self.assertEqual(self.defn["heightBoostFactor"], 1.5)
        # `myGravity` is elmos/frame^2 in this engine, so the ballistic reach of a
        # Cannon weapon is v^2 / g. At the originally specified 0.6 the reach is
        # only 350^2 / 0.6 ~= 227 elmos, short of the 550-elmo range, and the solver
        # degenerates into a flat shot that spawns under the terrain and dies on the
        # first frame. 0.2 keeps a real arc that covers `range`.
        self.assertEqual(self.defn["myGravity"], 0.2)
        reach = self.defn["weaponVelocity"] ** 2 / self.defn["myGravity"]
        self.assertGreater(reach, self.defn["range"])

    def test_damage_and_area_effect(self):
        self.assertEqual(self.defn["damage"]["default"], 500)
        self.assertEqual(self.defn["areaOfEffect"], 48)
        self.assertEqual(self.defn["edgeEffectiveness"], 0.5)
        # The converted mesh has no muzzle piece, so the rock launches from the unit
        # origin and its own 48-elmo AoE would destroy the launcher on the first shot.
        self.assertTrue(self.defn["noSelfDamage"])
        # Siege rocks leave no crater and must not be usable as a water weapon.
        self.assertEqual(self.defn["craterBoost"], 0)
        self.assertEqual(self.defn["craterMult"], 0)
        self.assertNotIn("waterWeapon", self.defn)

    def test_heavy_siege_outdamages_longbow_per_second(self):
        # 500 / 5.0 = 100 dps vs the longbow's 90 / 2.0 = 45 dps.
        catapult_dps = self.defn["damage"]["default"] / self.defn["reloadtime"]
        self.assertAlmostEqual(catapult_dps, 100.0)
        self.assertGreater(catapult_dps, 45.0)


class TestCatapultLuaScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = SCRIPTS_DIR / f"{UNIT_NAME}.lua"
        cls.source = cls.path.read_text(encoding="utf-8")
        cls.lua = LuaRuntime(unpack_returned_tuples=True)

    def test_compiles(self):
        self.lua.globals().c = self.source
        result = self.lua.execute("local fn, err = load(c); return { fn = fn, err = err }")
        self.assertIsNotNone(result["fn"], f"Lua compile failure: {result['err']}")

    def test_exports_expected_callins(self):
        for callin in (
            "script.Create",
            "script.AimFromWeapon1",
            "script.QueryWeapon1",
            "script.AimWeapon1",
            "script.FireWeapon1",
            "script.AimFromWeapon",
            "script.QueryWeapon",
            "script.AimWeapon",
            "script.FireWeapon",
            "script.Killed",
        ):
            self.assertIn(callin, self.source, f"missing {callin}")

    @staticmethod
    def _function_body(source: str, header: str) -> str:
        """Source between a `function script.X` header and the next top-level header."""
        start = source.index(header)
        rest = source[start + len(header):]
        next_header = rest.find("\nfunction script.")
        return rest if next_header == -1 else rest[:next_header]

    def test_all_weapon_callins_resolve_to_base_piece(self):
        # The converted 0 A.D. mesh is a single static hull, so every piece-returning
        # call-in must yield `base`; a stray piece name would raise at runtime.
        self.assertIn('local base = piece "base"', self.source)
        for header in (
            "function script.AimFromWeapon1",
            "function script.QueryWeapon1",
            "function script.AimFromWeapon",
            "function script.QueryWeapon",
        ):
            body = self._function_body(self.source, header)
            self.assertIn("return base", body, f"{header} must return the base piece")

    def test_aim_returns_true_so_angle_good_can_clear(self):
        body = self._function_body(self.source, "function script.AimWeapon1")
        self.assertIn("return true", body)
        unnumbered = self._function_body(self.source, "function script.AimWeapon(")
        self.assertIn("return true", unnumbered)

    def test_dead_zone_is_enforced_in_the_lus(self):
        # This engine build has no weapondef-level minimum-range tag: `minRange` is
        # logged as `Unknown tag "minrange"` and ignored. The dead zone therefore has
        # to live in the unit script, so assert it is actually implemented there.
        self.assertIn("local MIN_RANGE = 120", self.source)
        self.assertIn("targetBeyondDeadZone", self.source)
        # A target inside the dead zone must refuse to aim, which is what stops the
        # catapult from firing point-blank.
        for header in ("function script.AimWeapon1", "function script.AimWeapon("):
            body = self._function_body(self.source, header)
            self.assertIn("return false", body)

    def test_publishes_aim_and_fire_rules_params(self):
        # The probe reads these back in synced code; the names are the contract.
        self.assertIn("medieval_catapult_aiming", self.source)
        self.assertIn("medieval_catapult_fired", self.source)
        self.assertIn("SetUnitRulesParam", self.source)

    def test_echo_prefixes_are_catapult_specific(self):
        self.assertIn("LUS AIM catapult", self.source)
        self.assertIn("LUS FIRE catapult", self.source)
        # Echoes are rate-limited so a long siege does not flood the log.
        self.assertIn("aimEchoes < 5", self.source)
        self.assertIn("fireEchoes < 3", self.source)


class TestCatapultEconomyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.econ = cls.lua.execute((SCRIPTS_DIR / "medieval_economy.lua").read_text(encoding="utf-8"))
        cls.recruit = cls.lua.execute((SCRIPTS_DIR / "medieval_recruitment.lua").read_text(encoding="utf-8"))
        cls.housing = cls.lua.execute((SCRIPTS_DIR / "medieval_housing.lua").read_text(encoding="utf-8"))
        unit_table = cls.lua.execute((UNITS_DIR / f"{UNIT_NAME}.lua").read_text(encoding="utf-8"))
        cls.defn = _lua_table_to_py(cls.lua, unit_table[UNIT_NAME])

    def test_recruitment_cost_table_mirrors_unitdef(self):
        cost = self.recruit.getCost(UNIT_NAME)
        self.assertIsNotNone(cost)
        cp = self.defn["customparams"]
        self.assertEqual(cost["wood"], cp["resource_cost_wood"])
        self.assertEqual(cost["stone"], cp["resource_cost_stone"])
        self.assertEqual(cost["iron"], cp["resource_cost_iron"])

    def test_cost_is_affordable_from_starting_reserves(self):
        stock = self.econ.startingStockpiles()
        cost = self.recruit.getCost(UNIT_NAME)
        self.assertTrue(self.econ.canAffordCosts(stock, cost))

    def test_cost_is_not_free(self):
        total = self.econ.costTotal(self.recruit.getCost(UNIT_NAME))
        self.assertGreater(total, 0)

    def test_catapult_pays_military_upkeep(self):
        self.assertTrue(self.recruit.isMilitary(UNIT_NAME))
        self.assertEqual(self.recruit.upkeepFor(UNIT_NAME), 3)

    def test_catapult_consumes_one_population(self):
        self.assertEqual(self.housing.unitConsumesPop(UNIT_NAME), 1)
        cap = self.housing.computeCap(self.lua.table(medieval_town_center=1, medieval_house=2))
        self.assertTrue(self.housing.canSupport(5, cap, 1))

    def test_upkeep_is_charged_by_army_upkeep(self):
        counts = self.lua.table(**{UNIT_NAME: 2})
        self.assertEqual(self.recruit.armyUpkeep(counts), 6)

    def test_starvation_marker_tracks_catapult_upkeep(self):
        counts = self.lua.table(**{UNIT_NAME: 3})
        # 9 food owed; 8 is starving, 9 is fed.
        self.assertEqual(self.recruit.starvationMarker(8, counts), 1)
        self.assertEqual(self.recruit.starvationMarker(9, counts), 0)


class TestCatapultArtAssets(unittest.TestCase):
    def test_obj_and_dds_and_metadata_exist(self):
        import json

        obj = OBJECTS_DIR / f"{UNIT_NAME}.obj"
        dds = TEXTURES_DIR / f"{UNIT_NAME}.dds"
        meta = OBJECTS_DIR / f"{UNIT_NAME}.lua"
        self.assertTrue(obj.is_file(), f"missing {obj}")
        self.assertTrue(dds.is_file(), f"missing {dds}")
        self.assertTrue(meta.is_file(), f"missing {meta}")

        self.assertEqual(dds.read_bytes()[:4], b"DDS ")
        self.assertIn(f'tex1 = "0ad/{UNIT_NAME}.dds"', meta.read_text(encoding="utf-8"))

        text = obj.read_text(encoding="utf-8")
        self.assertIn("o base", text)
        self.assertIn("g base", text)
        faces = [l for l in text.splitlines() if l.startswith("f ")]
        verts = [l for l in text.splitlines() if l.startswith("v ")]
        self.assertGreaterEqual(len(faces), 500)
        self.assertGreaterEqual(len(verts), 900)

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        entry = manifest["units"][UNIT_NAME]
        self.assertEqual(entry["obj"], f"objects3d/0ad/{UNIT_NAME}.obj")
        self.assertEqual(entry["tex1"], f"0ad/{UNIT_NAME}.dds")
        # Provenance must name the real 0 A.D. source entries.
        self.assertEqual(entry["actor"], "art/actors/units/hellenes/siege_rock.xml")
        self.assertEqual(entry["mesh"], "art/meshes/structural/hele_lithobolos.dae.cached.pmd")
        self.assertEqual(entry["texture"], "art/textures/skins/structural/hele_siege.dds.cached.dds")
        for path in (entry["actor"], entry["mesh"], entry["texture"]):
            self.assertIn(path, manifest["entries"], f"{path} missing from manifest entries")


class TestCatapultLicenseSafety(unittest.TestCase):
    def test_no_restricted_bar_assets_referenced(self):
        blob = "\n".join([
            (UNITS_DIR / f"{UNIT_NAME}.lua").read_text(encoding="utf-8"),
            (SCRIPTS_DIR / f"{UNIT_NAME}.lua").read_text(encoding="utf-8"),
        ])
        for forbidden in (r"armwar", r"armrock", r"armfav", r"\.cob\b", r"\.bos\b", r"CC-BY-NC-ND"):
            self.assertIsNone(re.search(forbidden, blob), f"forbidden pattern {forbidden} present")


if __name__ == "__main__":
    unittest.main()
