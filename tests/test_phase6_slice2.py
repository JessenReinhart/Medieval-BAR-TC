"""Phase-6 Slice 2 tests: Combat Stats & Counter-Matrix Verification.

Layers under test:
1. Pure module — `scripts/medieval_damage_types.lua`: the siege/melee/ranged
   x fortification/building/standard damage multiplier matrix, its weapon /
   armor class key sets, `multiplier()` fallback, and `classForUnitDef()`.
2. Pure module — `scripts/medieval_tactics.lua`: charge / brace / flank /
   stance constants and their factor functions (chargeMult, braceMult,
   flankMult, stanceMult, counterCavalryMult).
3. Counter-matchup arithmetic — a small helper recomputes effective outgoing
   DPS from unit def stats (weapon name -> gamedata/weapondefs damage class /
   raw damage / reloadtime), the damage-type matrix, and the tactical factors,
   faithfully mirroring the gadget's `base * matrix * charge * flank * brace *
   stance * counter` pipeline. It is used to assert the four-way counter loop:

     cavalry  counters  ranged    (speed + charge burst)
     spearman counters  cavalry   (brace + anti-cavalry bonus)
     infantry counters  spearman  (higher HP, sustained melee DPS)
     ranged   counters  infantry  (range kiting before contact)

No number is changed in this slice: every counter relationship already held on
paper, so this suite pins the actuals to guard against silent regressions.
"""

import math
import unittest
from pathlib import Path

from lupa import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DAMAGE_TYPES_PATH = SCRIPTS / "medieval_damage_types.lua"
TACTICS_PATH = SCRIPTS / "medieval_tactics.lua"
WEAPONDEFS_PATH = ROOT / "gamedata" / "weapondefs.lua"
UNITS_DIR = ROOT / "units"

# Combat unit defs read for the counter-matchup arithmetic (all owned files).
COMBAT_UNITS = [
    "medieval_infantry",
    "medieval_spearman",
    "medieval_archer",
    "medieval_crossbow",
    "medieval_cavalry",
    "medieval_knight",
    "medieval_men_at_arms",
    "medieval_catapult",
]

# ---------------------------------------------------------------------------
# Mirrored policy constants (same pattern as tests/test_phase5_slice5.py).
# ---------------------------------------------------------------------------

WEAPON_CLASSES = ["siege", "melee", "ranged"]
ARMOR_CLASSES = ["fortification", "building", "standard"]

MATRIX = {
    "siege": {"fortification": 3.0, "building": 1.5, "standard": 1.0},
    "melee": {"fortification": 0.25, "building": 1.0, "standard": 1.0},
    "ranged": {"fortification": 0.25, "building": 1.0, "standard": 1.0},
}

CHARGE_SPEED_THRESHOLD = 1.0
CHARGE_DMG_MULT_MAX = 1.6
BRACE_DMG_REDUCTION = 0.5
BRACE_BONUS_VS_CAVALRY = 1.25
FLANK_SIDE_MULT = 1.15
FLANK_REAR_MULT = 1.25
STANCE_DEF_DAMAGE_MULT = 0.8
STANCE_DEF_ARMOR_MULT = 1.25
STANCES = {"aggressive", "hold", "standground"}


def _to_py(lua, value):
    """Recursively convert a lupa value into plain Python (list / dict / scalar)."""
    if value is None:
        return None
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _to_py(lua, value[k]) for k in keys}
    return value


# ---------------------------------------------------------------------------
# 1. Damage-type matrix (scripts/medieval_damage_types.lua)
# ---------------------------------------------------------------------------

class DamageTypesBase(unittest.TestCase):
    """Fresh runtime per test so a case cannot leak mutated module table state."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(DAMAGE_TYPES_PATH.read_text(encoding="utf-8"))


class TestDamageMatrix(DamageTypesBase):
    def test_weapon_and_armor_class_key_sets(self):
        self.assertEqual(_to_py(self.lua, self.m.WEAPON_CLASSES), WEAPON_CLASSES)
        self.assertEqual(_to_py(self.lua, self.m.ARMOR_CLASSES), ARMOR_CLASSES)

    def test_matrix_cell_values(self):
        self.assertEqual(_to_py(self.lua, self.m.MATRIX), MATRIX)

    def test_multiplier_known_pairs(self):
        self.assertAlmostEqual(self.m.multiplier("siege", "fortification"), 3.0)
        self.assertAlmostEqual(self.m.multiplier("siege", "building"), 1.5)
        self.assertAlmostEqual(self.m.multiplier("siege", "standard"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("melee", "fortification"), 0.25)
        self.assertAlmostEqual(self.m.multiplier("melee", "building"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("melee", "standard"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("ranged", "fortification"), 0.25)
        self.assertAlmostEqual(self.m.multiplier("ranged", "building"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("ranged", "standard"), 1.0)

    def test_multiplier_unknown_inputs_fall_back_to_one(self):
        self.assertAlmostEqual(self.m.multiplier("plasma", "standard"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("melee", "shields"), 1.0)
        self.assertAlmostEqual(self.m.multiplier("plasma", "shields"), 1.0)

    def test_class_for_unit_def(self):
        self.assertEqual(self.m.classForUnitDef("medieval_wall"), "fortification")
        self.assertEqual(self.m.classForUnitDef("medieval_tower"), "fortification")
        self.assertEqual(self.m.classForUnitDef("medieval_town_center"), "building")
        self.assertEqual(self.m.classForUnitDef("medieval_house"), "building")
        self.assertEqual(self.m.classForUnitDef("medieval_infantry"), "standard")
        self.assertEqual(self.m.classForUnitDef("no_such_unit"), "standard")

    def test_class_for_feature_def(self):
        self.assertEqual(self.m.classForFeatureDef("medieval_wall"), "fortification")
        self.assertEqual(self.m.classForFeatureDef("medieval_tower"), "fortification")
        self.assertEqual(self.m.classForFeatureDef("medieval_deer"), "standard")


# ---------------------------------------------------------------------------
# 2. Tactics constants & factors (scripts/medieval_tactics.lua)
# ---------------------------------------------------------------------------

class TacticsBase(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(TACTICS_PATH.read_text(encoding="utf-8"))


class TestTacticsConstants(TacticsBase):
    def test_charge_constants(self):
        self.assertEqual(self.m.CHARGE_SPEED_THRESHOLD, CHARGE_SPEED_THRESHOLD)
        self.assertEqual(self.m.CHARGE_DMG_MULT_MAX, CHARGE_DMG_MULT_MAX)

    def test_brace_constants(self):
        self.assertEqual(self.m.BRACE_DMG_REDUCTION, BRACE_DMG_REDUCTION)
        self.assertEqual(self.m.BRACE_BONUS_VS_CAVALRY, BRACE_BONUS_VS_CAVALRY)

    def test_flank_constants(self):
        self.assertEqual(self.m.FLANK_SIDE_MULT, FLANK_SIDE_MULT)
        self.assertEqual(self.m.FLANK_REAR_MULT, FLANK_REAR_MULT)

    def test_stance_constants(self):
        self.assertEqual(self.m.STANCE_DEF_DAMAGE_MULT, STANCE_DEF_DAMAGE_MULT)
        self.assertEqual(self.m.STANCE_DEF_ARMOR_MULT, STANCE_DEF_ARMOR_MULT)
        self.assertEqual(set(_to_py(self.lua, self.m.STANCES).keys()), STANCES)


class TestTacticsFactors(TacticsBase):
    def test_flank_ordering(self):
        self.assertAlmostEqual(self.m.flankMult(0, math.pi), 1.0)          # front
        self.assertAlmostEqual(self.m.flankMult(0, math.pi / 2), FLANK_SIDE_MULT)  # side
        self.assertAlmostEqual(self.m.flankMult(0, 0), FLANK_REAR_MULT)     # rear
        self.assertGreater(FLANK_REAR_MULT, FLANK_SIDE_MULT)
        self.assertGreater(FLANK_SIDE_MULT, 1.0)

    def test_flank_malformed_inputs_are_noop(self):
        self.assertAlmostEqual(self.m.flankMult(None, 0), 1.0)
        self.assertAlmostEqual(self.m.flankMult(0, None), 1.0)

    def test_stance_factor(self):
        self.assertAlmostEqual(self.m.stanceMult("standground"), STANCE_DEF_DAMAGE_MULT)
        self.assertAlmostEqual(self.m.stanceMult("hold"), 1.0)
        self.assertAlmostEqual(self.m.stanceMult("aggressive"), 1.0)
        self.assertAlmostEqual(self.m.stanceMult("unknown"), 1.0)

    def test_brace_factor(self):
        self.assertAlmostEqual(self.m.braceMult(True, "spear"), BRACE_DMG_REDUCTION)
        self.assertAlmostEqual(self.m.braceMult(False, "spear"), 1.0)
        self.assertAlmostEqual(self.m.braceMult(True, "sword"), 1.0)

    def test_counter_cavalry_factor(self):
        self.assertAlmostEqual(
            self.m.counterCavalryMult("spear", "cavalry"), BRACE_BONUS_VS_CAVALRY
        )
        self.assertAlmostEqual(self.m.counterCavalryMult("sword", "cavalry"), 1.0)
        self.assertAlmostEqual(self.m.counterCavalryMult("spear", "infantry"), 1.0)

    def test_charge_ramp(self):
        self.assertAlmostEqual(self.m.chargeMult(10, 10), 1.0)       # at base speed
        self.assertAlmostEqual(self.m.chargeMult(20, 10), CHARGE_DMG_MULT_MAX)  # clamped
        self.assertAlmostEqual(self.m.chargeMult(5, 10), 1.0)        # below base speed
        self.assertAlmostEqual(self.m.chargeMult(None, 10), 1.0)     # malformed


# ---------------------------------------------------------------------------
# 3. Counter-matchup arithmetic (matrix x tactics x unit def stats)
# ---------------------------------------------------------------------------

class CounterMatchupBase(unittest.TestCase):
    """Loads the two pure modules plus weapondefs and the combat unit defs.

    Data tables are converted to plain Python dicts/lists; the damage-type and
    tactics modules stay as Lua modules so the factor functions themselves are
    exercised (not reimplemented) exactly as the gadget calls them.
    """

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.dmg = cls.lua.execute(DAMAGE_TYPES_PATH.read_text(encoding="utf-8"))
        cls.tactics = cls.lua.execute(TACTICS_PATH.read_text(encoding="utf-8"))
        cls.weapondefs = _to_py(
            cls.lua, cls.lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        )
        cls.units = {}
        for name in COMBAT_UNITS:
            table = _to_py(
                cls.lua,
                cls.lua.execute((UNITS_DIR / f"{name}.lua").read_text(encoding="utf-8")),
            )
            cls.units[name] = table[name]

    # -- classification helpers mirroring gadget_medieval_tactics.lua ----------

    def _armor_class(self, def_key, unit):
        # customparam first, then the pure damage-type classification.
        cp = unit.get("customparams") or {}
        if "armor_class" in cp:
            return cp["armor_class"]
        return self.dmg.classForUnitDef(def_key)

    def _brace_class(self, def_key, unit):
        # "spear" for brace-capable spear/pike, else the def key (only names
        # present in tactics.BRACE_CLASSES ever qualify for brace/counter).
        if def_key in ("medieval_spearman", "medieval_pikeman"):
            return "spear"
        cp = unit.get("customparams") or {}
        if cp.get("counter_cavalry") is True or cp.get("brace") is True:
            return cp.get("brace_class") or "spear"
        return def_key

    def _is_cavalry(self, def_key):
        return def_key in ("medieval_cavalry", "medieval_knight")

    def effective_dps(self, attacker, defender, *, defender_stationary=False,
                      attacker_charge=None):
        """Effective outgoing DPS of `attacker` against `defender`.

        = raw_dps * matrix * counter * brace * charge, where raw_dps comes from
        the attacker's weapon def (damage / reloadtime) and the tactical factors
        come straight from scripts/medieval_tactics.lua. Flank and stance are
        assumed frontal/aggressive (1.0) unless a caller opts in.
        """
        a = self.units[attacker]
        d = self.units[defender]
        weapon = self.weapondefs[a["weapons"][0]["name"]]
        raw_dps = weapon["damage"]["default"] / weapon["reloadtime"]

        weapon_class = weapon["customparams"]["damage_class"]
        armor_class = self._armor_class(defender, d)
        matrix = float(self.dmg.multiplier(weapon_class, armor_class))

        attacker_class = self._brace_class(attacker, a)
        defender_class = "cavalry" if self._is_cavalry(defender) else armor_class
        counter = float(self.tactics.counterCavalryMult(attacker_class, defender_class))

        brace = float(self.tactics.braceMult(
            defender_stationary, self._brace_class(defender, d)
        ))

        if attacker_charge is None:
            charge = 1.0
        else:
            charge = float(self.tactics.chargeMult(attacker_charge, a["speed"]))

        return raw_dps * matrix * counter * brace * charge


class TestCounterMatchups(CounterMatchupBase):
    def test_spearman_beats_cavalry_per_entity_dps(self):
        # Spear: 150/1.2 = 125, x counter 1.25 (spear -> cavalry) => 156.25.
        spear_dps = self.effective_dps("medieval_spearman", "medieval_cavalry")
        self.assertAlmostEqual(spear_dps, 156.25)

        # Lance: 240/1.5 = 160, x brace 0.5 (braced stationary spearman) => 80.
        cav_dps = self.effective_dps(
            "medieval_cavalry", "medieval_spearman", defender_stationary=True
        )
        self.assertAlmostEqual(cav_dps, 80.0)

        self.assertGreater(spear_dps, cav_dps)

    def test_spearman_beats_equal_cost_cavalry_squad(self):
        spear_dps = self.effective_dps("medieval_spearman", "medieval_cavalry")
        cav_dps = self.effective_dps(
            "medieval_cavalry", "medieval_spearman", defender_stationary=True
        )
        spear_cost = self.units["medieval_spearman"]["buildCostMetal"]
        cav_cost = self.units["medieval_cavalry"]["buildCostMetal"]

        # Per-metal DPS: spearman is strictly more damage per resource invested.
        self.assertGreater(spear_dps / spear_cost, cav_dps / cav_cost)

        # Equal-cost squad time-to-kill: 220 metal buys ~2.3 spearmen vs 1 knight.
        budget = 220
        n_spear = budget / spear_cost
        n_cav = budget / cav_cost
        spear_squad_dps = n_spear * spear_dps
        cav_squad_dps = n_cav * cav_dps
        cav_squad_hp = n_cav * self.units["medieval_cavalry"]["maxDamage"]
        spear_squad_hp = n_spear * self.units["medieval_spearman"]["maxDamage"]

        # Spearman squad chews through the cavalry's HP faster than reverse.
        self.assertLess(cav_squad_hp / spear_squad_dps, spear_squad_hp / cav_squad_dps)

    def test_infantry_beats_spearman(self):
        # Both wield the same `sword` DPS (125), so the matchup is decided by
        # HP: infantry (1200) outlasts spearman (1050) in a mutual engagement.
        inf_dps = self.effective_dps("medieval_infantry", "medieval_spearman")
        spear_dps = self.effective_dps("medieval_spearman", "medieval_infantry")
        self.assertAlmostEqual(inf_dps, spear_dps)  # same broadsword, no counters

        ttk_inf = self.units["medieval_spearman"]["maxDamage"] / inf_dps   # 1050/125
        ttk_spear = self.units["medieval_infantry"]["maxDamage"] / spear_dps  # 1200/125
        self.assertLess(ttk_inf, ttk_spear)

    def test_cavalry_beats_ranged(self):
        # Speed: cavalry (3.6) closes the range gap on archers (1.9).
        self.assertGreater(
            self.units["medieval_cavalry"]["maxVelocity"],
            self.units["medieval_archer"]["maxVelocity"],
        )

        # Charge burst: at 2x base speed the lance hits for 1.6x => 256 vs the
        # archer's 45 sustained DPS.
        cav_charged = self.effective_dps(
            "medieval_cavalry",
            "medieval_archer",
            attacker_charge=2 * self.units["medieval_cavalry"]["speed"],
        )
        archer_dps = self.effective_dps("medieval_archer", "medieval_cavalry")
        self.assertGreater(cav_charged, archer_dps)

    def test_ranged_beats_infantry(self):
        # Range kiting: longbow reach (380) dwarfs the sword's melee reach (45).
        self.assertGreater(
            self.weapondefs["longbow"]["range"], self.weapondefs["sword"]["range"]
        )

    def test_siege_breaks_fortifications(self):
        # Closure of the extended loop: catapult (siege) vs wall (fortification)
        # gets the 3.0 multiplier, far above the melee/ranged anti-stone 0.25.
        cat_weapon = self.weapondefs[
            self.units["medieval_catapult"]["weapons"][0]["name"]
        ]
        self.assertEqual(cat_weapon["customparams"]["damage_class"], "siege")
        self.assertGreater(
            float(self.dmg.multiplier("siege", "fortification")),
            float(self.dmg.multiplier("melee", "fortification")),
        )
        self.assertGreater(
            float(self.dmg.multiplier("siege", "fortification")),
            float(self.dmg.multiplier("ranged", "fortification")),
        )


if __name__ == "__main__":
    unittest.main()