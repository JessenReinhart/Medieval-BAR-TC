"""Phase-5 Slice 5 tests: Tactical Combat Dynamics.

Layers under test:
1. Pure module — `scripts/medieval_tactics.lua`, a dependency-free, engine-free
   policy module. Each test boots its OWN fresh Lua runtime so a case cannot
   leak mutated module tables into another.
2. Purity — the module must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present (hard requirement for the gadget's VFS.Include + direct load).
3. Math — chargeMult / flankMult / braceMult / stanceMult / counterCavalryMult
   and the ordered composeDamage chain.
4. Composite chain — the full multiplicative product plus the no-double-apply
   guarantee (exactly one live UnitPreDamaged across the repo).
5. Unit def — `units/medieval_spearman.lua` is an anti-cavalry melee infantry
   with a dedicated Phase 7 Slice 3 mesh and the shared infantry LUS.
6. Gadget contract/behaviour — `gadget_medieval_tactics.lua` owns the single
   UnitPreDamaged hook, exports GG.MedievalTactics additively, and echoes one
   "PHASE5 DAMAGE" line.
7. Probe wiring — the Slice 5 probe gadget, runner and startscript.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_tactics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_tactics.lua"
LOGISTICS_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"
GARRISON_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_garrison.lua"
PROBE_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase5_slice5_tactics_probe.lua"
RUNNER_PATH = ROOT / "tools" / "launch" / "run_phase5_slice5_probe.py"
STARTSCRIPT_PATH = ROOT / "tools" / "launch" / "startscript_phase5_slice5.txt"
SPEARMAN_UNIT_PATH = ROOT / "units" / "medieval_spearman.lua"

# Policy constants mirrored from scripts/medieval_tactics.lua.
CHARGE_SPEED_THRESHOLD = 1.0
CHARGE_DMG_MULT_MAX = 1.6
BRACE_DMG_REDUCTION = 0.5
BRACE_BONUS_VS_CAVALRY = 1.25
FLANK_SIDE_MULT = 1.15
FLANK_REAR_MULT = 1.25
STANCE_DEF_DAMAGE_MULT = 0.8
STANCE_DEF_ARMOR_MULT = 1.25
STANCES = {"aggressive", "hold", "standground"}


def _lua_to_py(lua, value):
    if value is None:
        return None
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class TacticsBase(unittest.TestCase):
    """Fresh module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------

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

    def test_stances_set(self):
        stances = set(_lua_to_py(self.lua, self.m.STANCES).keys())
        self.assertEqual(stances, STANCES)

    def test_brace_classes_include_spear_pike(self):
        brace = _lua_to_py(self.lua, self.m.BRACE_CLASSES)
        for token in ("spear", "pike", "spearman", "pikeman", "medieval_spearman"):
            self.assertTrue(brace.get(token))

    def test_cavalry_classes_include_cavalry_and_knight(self):
        cav = _lua_to_py(self.lua, self.m.CAVALRY_CLASSES)
        for token in ("cavalry", "medieval_cavalry", "medieval_knight"):
            self.assertTrue(cav.get(token))

    def test_module_exports_the_required_functions(self):
        for fn in (
            "chargeMult", "flankMult", "braceMult", "stanceMult",
            "counterCavalryMult", "composeDamage",
        ):
            self.assertIsNotNone(self.m[fn], fn)


# ---------------------------------------------------------------------------
# 2. Purity
# ---------------------------------------------------------------------------

class TestTacticsPurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_no_vfs_include(self):
        self.assertNotIn('VFS.Include("', self.source)

    def test_no_spring_calls(self):
        calls = re.findall(r"Spring\.[A-Za-z_]+\(", self.source)
        self.assertEqual(calls, [])

    def test_no_require(self):
        self.assertNotIn("require(", self.source)

    def test_no_gg_api_calls(self):
        calls = re.findall(r"GG\.[A-Za-z_]+\.[A-Za-z_]+\(", self.source)
        self.assertEqual(calls, [])

    def test_loads_without_any_globals(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("Spring"))
        self.assertIsNone(lua.eval("GG"))
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        self.assertAlmostEqual(module.chargeMult(20, 10), CHARGE_DMG_MULT_MAX)


# ---------------------------------------------------------------------------
# 3. chargeMult
# ---------------------------------------------------------------------------

class TestChargeMult(TacticsBase):
    def test_below_base_speed_is_no_charge(self):
        self.assertAlmostEqual(self.m.chargeMult(0, 10), 1.0)
        self.assertAlmostEqual(self.m.chargeMult(5, 10), 1.0)

    def test_at_base_speed_is_no_charge(self):
        self.assertAlmostEqual(self.m.chargeMult(10, 10), 1.0)

    def test_double_speed_is_max_charge(self):
        self.assertAlmostEqual(self.m.chargeMult(20, 10), CHARGE_DMG_MULT_MAX)

    def test_halfway_ramp(self):
        # t = (15/10 - 1)/1 = 0.5 -> 1 + 0.6*0.5 = 1.3
        self.assertAlmostEqual(self.m.chargeMult(15, 10), 1.3)

    def test_clamps_above_max(self):
        self.assertAlmostEqual(self.m.chargeMult(100, 10), CHARGE_DMG_MULT_MAX)

    def test_malformed_inputs_are_noop(self):
        self.assertAlmostEqual(self.m.chargeMult(None, 10), 1.0)
        self.assertAlmostEqual(self.m.chargeMult(20, None), 1.0)
        self.assertAlmostEqual(self.m.chargeMult(20, 0), 1.0)
        self.assertAlmostEqual(self.m.chargeMult(20, -5), 1.0)


# ---------------------------------------------------------------------------
# 4. flankMult (heading-angle dot product)
# ---------------------------------------------------------------------------

class TestFlankMult(TacticsBase):
    def test_rear_when_headings_aligned(self):
        self.assertAlmostEqual(self.m.flankMult(0, 0), FLANK_REAR_MULT)

    def test_front_when_headings_opposed(self):
        self.assertAlmostEqual(self.m.flankMult(0, 3.1415926535), 1.0)

    def test_side_when_headings_perpendicular(self):
        self.assertAlmostEqual(self.m.flankMult(0, 1.5707963268), FLANK_SIDE_MULT)

    def test_rear_exceeds_side_exceeds_front(self):
        self.assertGreater(FLANK_REAR_MULT, FLANK_SIDE_MULT)
        self.assertGreater(FLANK_SIDE_MULT, 1.0)

    def test_malformed_inputs_are_noop(self):
        self.assertAlmostEqual(self.m.flankMult(None, 0), 1.0)
        self.assertAlmostEqual(self.m.flankMult(0, None), 1.0)


# ---------------------------------------------------------------------------
# 5. braceMult
# ---------------------------------------------------------------------------

class TestBraceMult(TacticsBase):
    def test_stationary_spear_braces(self):
        self.assertAlmostEqual(self.m.braceMult(True, "spear"), BRACE_DMG_REDUCTION)

    def test_stationary_pike_braces(self):
        self.assertAlmostEqual(self.m.braceMult(True, "pike"), BRACE_DMG_REDUCTION)

    def test_stationary_spearman_def_name_braces(self):
        self.assertAlmostEqual(self.m.braceMult(True, "medieval_spearman"), BRACE_DMG_REDUCTION)

    def test_non_stationary_spear_does_not_brace(self):
        self.assertAlmostEqual(self.m.braceMult(False, "spear"), 1.0)
        self.assertAlmostEqual(self.m.braceMult(None, "spear"), 1.0)

    def test_non_spear_defender_is_unaffected(self):
        self.assertAlmostEqual(self.m.braceMult(True, "medieval_infantry"), 1.0)
        self.assertAlmostEqual(self.m.braceMult(True, "infantry"), 1.0)
        self.assertAlmostEqual(self.m.braceMult(True, None), 1.0)


# ---------------------------------------------------------------------------
# 6. stanceMult
# ---------------------------------------------------------------------------

class TestStanceMult(TacticsBase):
    def test_aggressive_is_full_damage(self):
        self.assertAlmostEqual(self.m.stanceMult("aggressive"), 1.0)

    def test_hold_is_full_damage(self):
        self.assertAlmostEqual(self.m.stanceMult("hold"), 1.0)

    def test_standground_reduces_damage(self):
        self.assertAlmostEqual(self.m.stanceMult("standground"), STANCE_DEF_DAMAGE_MULT)

    def test_unknown_or_missing_is_full_damage(self):
        self.assertAlmostEqual(self.m.stanceMult(None), 1.0)
        self.assertAlmostEqual(self.m.stanceMult("berserk"), 1.0)


# ---------------------------------------------------------------------------
# 7. counterCavalryMult
# ---------------------------------------------------------------------------

class TestCounterCavalryMult(TacticsBase):
    def test_spear_vs_cavalry_gets_bonus(self):
        self.assertAlmostEqual(self.m.counterCavalryMult("spear", "cavalry"), BRACE_BONUS_VS_CAVALRY)

    def test_pike_vs_knight_gets_bonus(self):
        self.assertAlmostEqual(self.m.counterCavalryMult("pike", "medieval_knight"), BRACE_BONUS_VS_CAVALRY)

    def test_non_spear_attacker_no_bonus(self):
        self.assertAlmostEqual(self.m.counterCavalryMult("medieval_infantry", "cavalry"), 1.0)
        self.assertAlmostEqual(self.m.counterCavalryMult(None, "cavalry"), 1.0)

    def test_non_cavalry_defender_no_bonus(self):
        self.assertAlmostEqual(self.m.counterCavalryMult("spear", "infantry"), 1.0)
        self.assertAlmostEqual(self.m.counterCavalryMult("spear", None), 1.0)


# ---------------------------------------------------------------------------
# 8. composeDamage (ordered chain)
# ---------------------------------------------------------------------------

class TestComposeDamage(TacticsBase):
    def test_empty_parts_is_identity(self):
        self.assertAlmostEqual(self.m.composeDamage(None), 1.0)
        self.assertAlmostEqual(self.m.composeDamage(self.lua.table()), 1.0)

    def test_single_part_scales(self):
        parts = self.lua.table()
        parts["charge"] = 2.0
        self.assertAlmostEqual(self.m.composeDamage(parts), 2.0)

    def test_four_factor_product(self):
        parts = self.lua.table()
        parts["charge"] = 1.6
        parts["flank"] = 1.25
        parts["brace"] = 0.5
        parts["stance"] = 0.8
        expected = 1.6 * 1.25 * 0.5 * 0.8
        self.assertAlmostEqual(self.m.composeDamage(parts), expected)

    def test_missing_parts_default_to_one(self):
        # tech/supply/matrix/garrison must NOT be re-applied inside the tactics
        # compose; any omitted tactical flag is a 1.0 no-op.
        parts = self.lua.table()
        parts["charge"] = 1.6
        parts["stance"] = 0.8
        self.assertAlmostEqual(self.m.composeDamage(parts), 1.6 * 0.8)

    def test_source_orders_charge_flank_brace_stance(self):
        body = MODULE_PATH.read_text(encoding="utf-8")
        i_charge = body.find("parts.charge")
        i_flank = body.find("parts.flank")
        i_brace = body.find("parts.brace")
        i_stance = body.find("parts.stance")
        self.assertTrue(-1 < i_charge < i_flank < i_brace < i_stance)


# ---------------------------------------------------------------------------
# 9. Composite chain + no-double-apply
# ---------------------------------------------------------------------------

class TestCompositeChain(TacticsBase):
    def test_full_multiplier_chain_product(self):
        base = 100.0
        tech = 1.25
        supply = 1.1
        matrix = 0.25
        garrison = 1.3
        parts = self.lua.table()
        parts["charge"] = 1.6
        parts["flank"] = 1.25
        parts["brace"] = 0.5
        parts["stance"] = 0.8
        tactics_mult = self.m.composeDamage(parts)
        final = base * tech * supply * matrix * garrison * tactics_mult
        # 100 * 1.25 * 1.1 * 0.25 * 1.3 * 0.8 = 35.75
        self.assertAlmostEqual(final, 35.75)

    def test_no_double_apply_exactly_one_live_unitpredamaged(self):
        live = []
        for pattern in ("luarules/gadgets/*.lua", "scripts/*.lua"):
            for p in sorted(ROOT.glob(pattern)):
                src = p.read_text(encoding="utf-8")
                if re.search(r"function gadget:UnitPreDamaged\s*\(", src):
                    live.append(p.name)
        self.assertEqual(live, ["gadget_medieval_tactics.lua"])

    def test_logistics_gadget_no_longer_hooks_damage(self):
        src = LOGISTICS_GADGET_PATH.read_text(encoding="utf-8")
        self.assertNotIn("function gadget:UnitPreDamaged", src)

    def test_garrison_gadget_still_does_not_hook_damage(self):
        src = GARRISON_GADGET_PATH.read_text(encoding="utf-8")
        self.assertNotIn("function gadget:UnitPreDamaged", src)


# ---------------------------------------------------------------------------
# 10. Unit def
# ---------------------------------------------------------------------------

class TestSpearmanUnitDef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        src = SPEARMAN_UNIT_PATH.read_text(encoding="utf-8")
        cls.defn = cls.lua.execute(src)["medieval_spearman"]

    def test_is_melee_infantry_with_anti_cavalry_tags(self):
        self.assertEqual(self.defn["name"], "Spearman")
        self.assertEqual(self.defn["customparams"]["counter_cavalry"], True)
        self.assertEqual(self.defn["customparams"]["brace"], True)

    def test_armor_class_is_standard(self):
        self.assertEqual(self.defn["customparams"]["armor_class"], "standard")

    def test_has_a_dedicated_mesh_and_reuses_the_infantry_script(self):
        # Phase 7 Slice 3 replaced the infantry-body reuse with a dedicated
        # objects3d/0ad/medieval_spearman.obj; the LUS stays shared.
        self.assertEqual(self.defn["objectName"], "0ad/medieval_spearman.obj")
        self.assertEqual(self.defn["script"], "medieval_infantry.lua")

    def test_reuses_a_melee_weapon(self):
        weapons = _lua_to_py(self.lua, self.defn["weapons"])
        names = [w["name"] for w in weapons]
        self.assertIn("sword", names)

    def test_is_mobile_combat_unit(self):
        self.assertTrue(self.defn["canMove"])
        self.assertTrue(self.defn["canAttack"])
        self.assertTrue(self.defn["canFight"])
        self.assertGreater(self.defn["speed"], 0)


# ---------------------------------------------------------------------------
# 11. Gadget contract
# ---------------------------------------------------------------------------

class TestTacticsGadgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_synced_only(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.src)

    def test_layer_is_six(self):
        self.assertIn("layer = 6,", self.src)

    def test_gated_on_the_medievaltactics_modoption(self):
        self.assertIn("medievaltactics", self.src)

    def test_includes_the_pure_modules(self):
        self.assertIn('VFS.Include("scripts/medieval_tactics.lua")', self.src)
        self.assertIn('VFS.Include("scripts/medieval_damage_types.lua")', self.src)

    def test_owns_the_single_unitpredamaged_hook(self):
        self.assertIn("function gadget:UnitPreDamaged", self.src)

    def test_exports_gg_medieval_tactics(self):
        self.assertIn("GG.MedievalTactics", self.src)

    def test_export_is_additive(self):
        self.assertIn("GG.MedievalTactics = GG.MedievalTactics or {}", self.src)

    def test_echos_the_phase5_damage_line(self):
        self.assertIn("PHASE5 DAMAGE", self.src)

    def test_reads_tech_and_supply_from_logistics(self):
        self.assertIn("GG.MedievalLogistics", self.src)

    def test_reads_garrison_from_the_slice4_owner(self):
        self.assertIn("GG.MedievalGarrison", self.src)

    def test_exports_the_documented_api(self):
        for token in ("SetStance", "GetStance", "GetChargeState", "Compose"):
            self.assertIn(token, self.src)


# ---------------------------------------------------------------------------
# 12. Gadget behaviour
# ---------------------------------------------------------------------------

class TestTacticsGadgetBehaviour(unittest.TestCase):
    INFANTRY, WALL = 1, 2
    SWORD = 10
    ATTACKER_ID, DEFENDER_ID = 500, 501

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.INFANTRY = self.INFANTRY
        g.WALL = self.WALL
        g.SWORD = self.SWORD
        g.ATTACKER_ID = self.ATTACKER_ID
        g.DEFENDER_ID = self.DEFENDER_ID
        self.lua.execute(r"""
        ECHO_LINES = {}
        gadget = {}
        gadgetHandler = { IsSyncedCode = function() return true end }
        GG = {}
        GG.MedievalLogistics = {
          DamageMultiplier = function(teamID, name) return 1.25 end,
          SupplyBonus = function(unitID) return 0.10 end,
        }
        GG.MedievalGarrison = {
          GetDamageMult = function(unitID) return 1.30 end,
        }
        UnitDefs = {
          [INFANTRY] = { name = "medieval_infantry", canMove = true, speed = 32 },
          [WALL]     = { name = "medieval_wall", canMove = false, customParams = { armor_class = "fortification" } },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end
        WeaponDefs = {
          [SWORD] = { name = "Broadsword", customParams = { damage_class = "melee" } },
        }
        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetModOptions = function() return {} end,
          GetUnitDefID = function(id) return id == ATTACKER_ID and INFANTRY or (id == DEFENDER_ID and WALL or nil) end,
          GetUnitPosition = function() return nil end,
        }
        VFS = {
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }
        function FireInitialize() gadget:Initialize() end
        function FireUnitPreDamaged(defender, damage, attacker, weaponDefID)
          local defID = attacker and UnitDefs[INFANTRY] and INFANTRY or nil
          local defID2 = defender and UnitDefs[WALL] and WALL or nil
          return gadget:UnitPreDamaged(
            defender, defID2, 1, damage, false, weaponDefID, nil,
            attacker, defID, 0)
        end
        assert(load(GADGET_SRC, "@gadget_medieval_tactics.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalTactics

    def _echo_lines(self):
        return self._g("ECHO_LINES")

    def test_composes_the_full_chain_once(self):
        self._g("FireInitialize")()
        damage, _ = self._g("FireUnitPreDamaged")(self.DEFENDER_ID, 100.0, self.ATTACKER_ID, self.SWORD)
        # base * tech(1.25) * supply(1.10) * matrix(melee->fort = 0.25)
        #        * garrison(1.30) * tactics(1.0: no charge/flank/brace/stance)
        expected = 100.0 * 1.25 * 1.10 * 0.25 * 1.30
        self.assertAlmostEqual(damage, expected)

    def test_echos_the_single_phase5_damage_line(self):
        self._g("FireInitialize")()
        self._g("FireUnitPreDamaged")(self.DEFENDER_ID, 100.0, self.ATTACKER_ID, self.SWORD)
        lines = _lua_to_py(self.lua, self._g("ECHO_LINES"))
        phase5 = [ln for ln in lines if ln.startswith("PHASE5 DAMAGE")]
        self.assertEqual(len(phase5), 1)

    def test_no_attacker_returns_unchanged(self):
        self._g("FireInitialize")()
        damage, _ = self._g("FireUnitPreDamaged")(self.DEFENDER_ID, 100.0, None, None)
        self.assertAlmostEqual(damage, 100.0)

    def test_export_surface_is_additive_and_works(self):
        self._g("FireInitialize")()
        api = self._api()
        self.assertTrue(api.SetStance(self.ATTACKER_ID, "standground"))
        self.assertEqual(api.GetStance(self.ATTACKER_ID), "standground")
        self.assertAlmostEqual(api.Compose(self.lua.table()), 1.0)
        state = api.GetChargeState(self.ATTACKER_ID)
        self.assertAlmostEqual(float(state["charge"]), 1.0)


# ---------------------------------------------------------------------------
# 13. Probe wiring
# ---------------------------------------------------------------------------

class TestTacticsProbeWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = PROBE_PATH.read_text(encoding="utf-8")
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.startscript = STARTSCRIPT_PATH.read_text(encoding="utf-8")

    def test_probe_exists_and_is_synced(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.probe)

    def test_probe_gated_on_the_modoption(self):
        self.assertIn("medievaltactics", self.probe)

    def test_probe_spawns_cavalry_and_spearman_and_target(self):
        self.assertIn("medieval_cavalry", self.probe)
        self.assertIn("medieval_spearman", self.probe)
        self.assertIn("medieval_infantry", self.probe)

    def test_probe_emits_the_required_verdicts(self):
        for verdict in ("charge", "brace", "flank", "stance"):
            self.assertIn(f"{verdict}-verdict", self.probe)
        self.assertIn("PHASE5 TACTICS probe-complete PASS", self.probe)

    def test_probe_does_not_hook_damage(self):
        self.assertNotIn("function gadget:UnitPreDamaged", self.probe)

    def test_runner_watches_every_verdict(self):
        for resource in ("charge", "brace", "flank", "stance", "probe-complete"):
            self.assertIn(f'"{resource}"', self.runner)

    def test_runner_uses_the_slice5_startscript(self):
        self.assertIn("startscript_phase5_slice5.txt", self.runner)

    def test_startscript_enables_the_modoption(self):
        self.assertIn("medievaltactics=1;", self.startscript)

    def test_startscript_reaches_the_probe_terminal_frame(self):
        self.assertIsNotNone(re.search(r"quitforce", self.startscript))
        self.assertIn("forcestart", self.startscript)


if __name__ == "__main__":
    unittest.main()