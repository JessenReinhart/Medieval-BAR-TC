"""Phase 7 Slice 2 tests: Combat FX, projectiles and visual impact.

Validates that:
1. `gamedata/explosions.lua` executes cleanly in bare Lua 5.1 and defines the
   four medieval CEG impact generators (`arrow_hit_fx`, `bolt_hit_fx`,
   `stone_hit_fx`, `melee_hit_fx`).
2. Every spawn table inside those generators uses a spawn class the bundled
   engine implements, and every field on it is a real member of that class.
   The engine rejects unknown fields with
   `[CCEG::Parse] unknown field <class>::<field> in spawn-table ...`, so this
   guards the file against the legacy CEG vocabulary (`count`, `life`, `speed`,
   `spread`, `ttl` on a particle system) that the engine does NOT accept.
3. `gamedata/weapondefs.lua` assigns `explosionGenerator` to sword, longbow,
   lance, catapult and dagger, using the `custom:` prefix the engine requires.
4. The ranged weapon defs carry clean projectile parameters (2D sprite size,
   colour tint, smoke-trail choice) and keep their ballistic configuration.
5. Combat unit weapon tables in `units/*.lua` mirror the same generators, and
   every referenced generator name actually exists in `explosions.lua`.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
EXPLOSIONS_PATH = ROOT / "gamedata/explosions.lua"
WEAPONDEFS_PATH = ROOT / "gamedata/weapondefs.lua"
UNITS_DIR = ROOT / "units"

# The four medieval impact generators this slice must define.
MEDIEVAL_GENERATORS = (
    "arrow_hit_fx",
    "bolt_hit_fx",
    "stone_hit_fx",
    "melee_hit_fx",
)

# weapondef name -> expected explosionGenerator value.
EXPECTED_WEAPON_FX = {
    "sword": "custom:melee_hit_fx",
    "longbow": "custom:arrow_hit_fx",
    "lance": "custom:melee_hit_fx",
    "catapult": "custom:stone_hit_fx",
    "dagger": "custom:melee_hit_fx",
}

# unit file -> expected explosionGenerator on weapon 1.
EXPECTED_UNIT_FX = {
    "medieval_archer.lua": "custom:arrow_hit_fx",
    "medieval_crossbow.lua": "custom:bolt_hit_fx",
    "medieval_infantry.lua": "custom:melee_hit_fx",
    "medieval_men_at_arms.lua": "custom:melee_hit_fx",
    "medieval_spearman.lua": "custom:melee_hit_fx",
    "medieval_cavalry.lua": "custom:melee_hit_fx",
    "medieval_knight.lua": "custom:melee_hit_fx",
    "medieval_catapult.lua": "custom:stone_hit_fx",
    "medieval_king.lua": "custom:melee_hit_fx",
}

# Spawn classes implemented by the bundled spring-headless.exe.
KNOWN_SPAWN_CLASSES = {
    "CSimpleParticleSystem",
    "CDirtProjectile",
    "CStandardGroundFlash",
    "CSimpleGroundFlash",
    "CExploSpikeProjectile",
    "CHeatCloudProjectile",
    "CSmokeTrailProjectile",
}

# Reflected member lists, extracted from the bundled spring-headless.exe. A
# field outside its class's set is dropped by the engine with a warning, so the
# FX silently fails to render. These are the authoritative per-class names.
CLASS_FIELDS = {
    "CSimpleParticleSystem": {
        "pos", "speed", "useAirLos", "alwaysVisible",
        "emitVector", "emitMul", "gravity", "colorMap", "texture", "airdrag",
        "particleLife", "particleLifeSpread", "numParticles",
        "particleSpeed", "particleSpeedSpread",
        "particleSize", "particleSizeSpread",
        "emitRot", "emitRotSpread", "directional", "sizeGrowth", "sizeMod",
    },
    "CDirtProjectile": {
        "pos", "speed", "useAirLos", "alwaysVisible",
        "alpha", "alphaFalloff", "size", "sizeExpansion", "slowdown",
        "color", "texture",
    },
    "CStandardGroundFlash": {
        "pos", "size", "depthTest", "depthMask", "flashSize", "flashAlpha",
        "circleGrowth", "circleAlpha", "color", "side1", "side2", "circleSize",
        "flashAge", "flashAgeSpeed", "circleAlphaDec", "ttl", "texture",
        "sizeGrowth", "alpha", "fade", "normal", "age", "agerate", "colorMap",
    },
}

# Field names that appear in widely-copied legacy CEG examples but that this
# engine build does NOT register on CSimpleParticleSystem.
LEGACY_PARTICLE_FIELDS = {"count", "life", "lifespread", "sizeSpread", "speedSpread", "ttl"}

# Textures the mod's engine install actually provides for FX. The first group
# are projectile-atlas names; the second are groundfx-atlas names.
KNOWN_TEXTURES = {
    "smoke", "flare", "explofade", "explo", "heatcloud", "flame", "randdots",
    "groundflash", "groundring", "seismic",
}


def _lua_to_py(obj):
    if hasattr(obj, "items"):
        return {k: _lua_to_py(v) for k, v in obj.items()}
    if hasattr(obj, "values") and not isinstance(obj, (str, bytes)):
        try:
            return [_lua_to_py(v) for v in obj.values()]
        except TypeError:
            return obj
    return obj


class _LuaLoader(unittest.TestCase):
    """Shared helper: execute a Lua def file in a bare Lua 5.1 runtime."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)

    def _load(self, path: Path):
        return _lua_to_py(self.lua.execute(path.read_text(encoding="utf-8")))


class TestPhase7Slice2ExplosionGenerators(_LuaLoader):
    def setUp(self):
        self.assertTrue(
            EXPLOSIONS_PATH.exists(), f"Missing {EXPLOSIONS_PATH}"
        )
        self.explosions = self._load(EXPLOSIONS_PATH)

    def test_explosions_lua_parses_as_table(self):
        self.assertIsInstance(
            self.explosions,
            dict,
            "gamedata/explosions.lua must return a table of CEG definitions",
        )

    def test_defines_all_medieval_generators(self):
        for name in MEDIEVAL_GENERATORS:
            self.assertIn(
                name, self.explosions, f"Missing CEG generator: {name}"
            )

    def test_generators_are_non_empty_spawn_tables(self):
        for name in MEDIEVAL_GENERATORS:
            gen = self.explosions[name]
            self.assertIsInstance(gen, dict, f"{name} must be a table")
            self.assertTrue(gen, f"{name} must define at least one spawn table")
            for spawn_name, spawn in gen.items():
                self.assertIsInstance(
                    spawn, dict, f"{name}.{spawn_name} must be a table"
                )
                self.assertIn(
                    "class",
                    spawn,
                    f"{name}.{spawn_name} must declare a spawn class",
                )

    def test_spawn_classes_are_implemented_by_engine(self):
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                self.assertIn(
                    spawn["class"],
                    KNOWN_SPAWN_CLASSES,
                    f"{name}.{spawn_name} uses unknown class {spawn['class']}",
                )

    def test_no_legacy_particle_field_names(self):
        """The engine drops `count`/`life`/`ttl` etc. on particle systems."""
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                if spawn["class"] != "CSimpleParticleSystem":
                    continue
                for field in spawn:
                    self.assertNotIn(
                        field,
                        LEGACY_PARTICLE_FIELDS,
                        f"{name}.{spawn_name} uses legacy field '{field}'",
                    )

    def test_all_fields_are_valid_for_their_class(self):
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                cls = spawn["class"]
                if cls not in CLASS_FIELDS:
                    continue
                allowed = CLASS_FIELDS[cls]
                for field in spawn:
                    if field == "class":
                        continue
                    self.assertIn(
                        field,
                        allowed,
                        f"{name}.{spawn_name}: '{field}' is not a {cls} member",
                    )

    def test_particle_systems_have_required_visual_data(self):
        """CSimpleParticleSystem warns without a colour-map and a texture."""
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                if spawn["class"] != "CSimpleParticleSystem":
                    continue
                self.assertIn(
                    "colorMap",
                    spawn,
                    f"{name}.{spawn_name} missing colorMap",
                )
                self.assertIn(
                    "texture", spawn, f"{name}.{spawn_name} missing texture"
                )
                # colorMap must be at least two RGBA stops to fade between.
                cmap = spawn["colorMap"]
                self.assertGreaterEqual(
                    len(cmap),
                    2,
                    f"{name}.{spawn_name} colorMap needs >= 2 stops",
                )

    def test_textures_are_available(self):
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                tex = spawn.get("texture")
                if tex is None:
                    continue
                self.assertIn(
                    tex,
                    KNOWN_TEXTURES,
                    f"{name}.{spawn_name} references unavailable texture '{tex}'",
                )

    def test_generators_stay_lightweight(self):
        """Combat FX fire constantly; particle counts and lifetimes stay small."""
        for name in MEDIEVAL_GENERATORS:
            for spawn_name, spawn in self.explosions[name].items():
                if spawn["class"] != "CSimpleParticleSystem":
                    continue
                self.assertLessEqual(
                    spawn["numParticles"],
                    16,
                    f"{name}.{spawn_name} particle count too high for combat FX",
                )
                self.assertLessEqual(
                    spawn["particleLife"],
                    30,
                    f"{name}.{spawn_name} lifetime too long for an impact",
                )

    def test_arrow_fx_is_dust_and_splinters_without_crater(self):
        arrow = self.explosions["arrow_hit_fx"]
        classes = {s["class"] for s in arrow.values()}
        self.assertIn("CSimpleParticleSystem", classes)
        self.assertNotIn(
            "CStandardGroundFlash",
            classes,
            "an arrow should not leave a crater flash",
        )

    def test_bolt_fx_has_sharper_sparks_than_arrow(self):
        """A bolt on armour throws sparks; an arrow does not."""
        bolt_classes = {s["class"] for s in self.explosions["bolt_hit_fx"].values()}
        self.assertIn("CSimpleParticleSystem", bolt_classes)
        bolt_sparks = [
            s
            for s in self.explosions["bolt_hit_fx"].values()
            if s.get("texture") == "flare"
        ]
        self.assertTrue(bolt_sparks, "bolt_hit_fx should include a flare spark")
        arrow_sparks = [
            s
            for s in self.explosions["arrow_hit_fx"].values()
            if s.get("texture") == "flare"
        ]
        self.assertFalse(
            arrow_sparks, "arrow_hit_fx should not use spark flares"
        )

    def test_stone_fx_is_the_heavy_one(self):
        stone = self.explosions["stone_hit_fx"]
        classes = {s["class"] for s in stone.values()}
        # Only the siege rock scars the ground.
        self.assertIn("CDirtProjectile", classes)
        self.assertIn("CStandardGroundFlash", classes)
        total_particles = sum(
            s.get("numParticles", 0)
            for s in stone.values()
            if s["class"] == "CSimpleParticleSystem"
        )
        melee_particles = sum(
            s.get("numParticles", 0)
            for s in self.explosions["melee_hit_fx"].values()
            if s["class"] == "CSimpleParticleSystem"
        )
        self.assertGreater(
            total_particles,
            melee_particles,
            "the boulder impact should throw more debris than a melee hit",
        )

    def test_melee_fx_has_sparks_and_blood(self):
        melee = self.explosions["melee_hit_fx"]
        textures = {s.get("texture") for s in melee.values()}
        self.assertIn("flare", textures, "melee_hit_fx needs steel sparks")
        self.assertIn("smoke", textures, "melee_hit_fx needs dust/flesh flecks")

    def test_only_stone_fx_scars_the_ground(self):
        for name in MEDIEVAL_GENERATORS:
            if name == "stone_hit_fx":
                continue
            classes = {s["class"] for s in self.explosions[name].values()}
            self.assertNotIn(
                "CDirtProjectile",
                classes,
                f"{name} should not create ground craters",
            )


class TestPhase7Slice2WeaponDefs(_LuaLoader):
    def setUp(self):
        self.weapondefs = self._load(WEAPONDEFS_PATH)

    def test_weapondefs_assign_explosion_generator(self):
        for wname, expected in EXPECTED_WEAPON_FX.items():
            w = self.weapondefs.get(wname)
            self.assertIsNotNone(w, f"Weapondef {wname} missing")
            self.assertEqual(
                w.get("explosionGenerator"),
                expected,
                f"{wname} explosionGenerator mismatch",
            )

    def test_explosion_generators_use_custom_prefix(self):
        """Without the `custom:` prefix the engine cannot resolve the CEG."""
        for wname in EXPECTED_WEAPON_FX:
            value = self.weapondefs[wname]["explosionGenerator"]
            self.assertTrue(
                value.startswith("custom:"),
                f"{wname} explosionGenerator must start with 'custom:'",
            )

    def test_referenced_generators_exist(self):
        explosions = self._load(EXPLOSIONS_PATH)
        for wname in EXPECTED_WEAPON_FX:
            ref = self.weapondefs[wname]["explosionGenerator"].split(":", 1)[1]
            self.assertIn(
                ref,
                explosions,
                f"{wname} references undefined CEG '{ref}'",
            )

    def test_longbow_projectile_params_are_clean(self):
        bow = self.weapondefs["longbow"]
        self.assertEqual(bow["weaponVelocity"], 400)
        self.assertEqual(bow["myGravity"], 0.5)
        self.assertEqual(bow["heightBoostFactor"], 1.2)
        # No arrow mesh ships, so the projectile is a sized, tinted 2D sprite.
        self.assertGreater(bow["size"], 0, "arrow sprite needs a size")
        self.assertIn("rgbColor", bow, "arrow sprite needs a colour tint")
        self.assertIs(
            bow["smokeTrail"],
            False,
            "a single arrow should not drag a smoke ribbon",
        )

    def test_catapult_projectile_params_are_clean(self):
        cat = self.weapondefs["catapult"]
        self.assertEqual(cat["weaponVelocity"], 350)
        self.assertEqual(cat["myGravity"], 0.2)
        self.assertEqual(cat["heightBoostFactor"], 1.5)
        self.assertGreater(
            cat["size"],
            self.weapondefs["longbow"]["size"],
            "the boulder should read larger than an arrow",
        )
        self.assertIn("rgbColor", cat, "boulder sprite needs a colour tint")
        self.assertIs(
            cat["smokeTrail"],
            True,
            "a tumbling siege rock keeps its trail",
        )

    def test_ballistic_reach_covers_declared_range(self):
        """v^2 / g must cover the declared range or the solver degenerates."""
        for wname in ("longbow", "catapult"):
            w = self.weapondefs[wname]
            reach = w["weaponVelocity"] ** 2 / w["myGravity"]
            self.assertGreaterEqual(
                reach,
                w["range"],
                f"{wname} ballistic reach {reach} < range {w['range']}",
            )

    def test_melee_weapons_have_no_projectile_sprite(self):
        """Melee weapons never spawn a projectile, so sprite params are absent."""
        for wname in ("sword", "lance", "dagger"):
            w = self.weapondefs[wname]
            self.assertNotIn(
                "rgbColor",
                w,
                f"{wname} is melee and should not define a projectile sprite",
            )


class TestPhase7Slice2UnitWeaponTables(_LuaLoader):
    def _unit_weapon(self, ufilename: str):
        upath = UNITS_DIR / ufilename
        self.assertTrue(upath.exists(), f"Missing unit file: {upath}")
        udef_table = self._load(upath)
        uname = ufilename.replace(".lua", "")
        udef = udef_table[uname]
        weapons = udef.get("weapons", {})
        return weapons.get(1) if isinstance(weapons, dict) else weapons[0]

    def test_combat_units_declare_matching_explosion_generator(self):
        for ufilename, expected in EXPECTED_UNIT_FX.items():
            w1 = self._unit_weapon(ufilename)
            self.assertIsNotNone(w1, f"{ufilename} has no weapon 1")
            self.assertEqual(
                w1.get("explosionGenerator"),
                expected,
                f"{ufilename} explosionGenerator mismatch",
            )

    def test_unit_generators_exist_in_explosions_lua(self):
        explosions = self._load(EXPLOSIONS_PATH)
        for ufilename in EXPECTED_UNIT_FX:
            w1 = self._unit_weapon(ufilename)
            ref = w1["explosionGenerator"].split(":", 1)[1]
            self.assertIn(
                ref,
                explosions,
                f"{ufilename} references undefined CEG '{ref}'",
            )

    def test_unit_and_weapondef_generators_agree(self):
        """A unit must not contradict the weapondef it mounts."""
        weapondefs = self._load(WEAPONDEFS_PATH)
        for ufilename in EXPECTED_UNIT_FX:
            w1 = self._unit_weapon(ufilename)
            wname = w1["name"]
            wdef = weapondefs.get(wname)
            self.assertIsNotNone(wdef, f"{ufilename} mounts unknown weapon {wname}")
            # The crossbow deliberately overrides the shared longbow weapondef:
            # it fires the same def but a bolt should spark, not thud.
            if ufilename == "medieval_crossbow.lua":
                self.assertEqual(w1["explosionGenerator"], "custom:bolt_hit_fx")
                self.assertNotEqual(
                    w1["explosionGenerator"], wdef["explosionGenerator"]
                )
                continue
            self.assertEqual(
                w1["explosionGenerator"],
                wdef["explosionGenerator"],
                f"{ufilename} FX disagrees with weapondef {wname}",
            )

    def test_no_unresolved_fx_placeholders(self):
        for ufilename in EXPECTED_UNIT_FX:
            text = (UNITS_DIR / ufilename).read_text(encoding="utf-8")
            self.assertNotIn(
                "<",
                text,
                f"Placeholder angle brackets remain in {ufilename}",
            )


if __name__ == "__main__":
    unittest.main()
