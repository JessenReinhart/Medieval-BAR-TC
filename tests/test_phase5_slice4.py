"""Phase-5 Slice 4 tests: Garrisoning & Town Defense.

Layers under test:

1. Pure module — `scripts/medieval_garrison.lua`, a dependency-free, engine-free
   policy module. Every test boots its OWN fresh Lua runtime (no shared
   setUpClass state) so one case cannot leak mutated module tables into another.
2. Purity — the module must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present, because the synced gadget `VFS.Include`s it and the tests
   load it directly. This is a hard requirement, not a style preference.
3. Math — `garrison_damage_multiplier`, `healRate`, `maxGarrison` /
   `canGarrison` / `capacityFor` / `garrisonAllowed`, `shelterHealFor` and the
   `shelterState` aggregate.
4. Unit defs — `units/medieval_town_center.lua` and `units/medieval_tower.lua`
   must carry the engine transport fields that make them garrisonable, and the
   capacities must match `GARRISON_CAP`.
5. Gadget contract — `luarules/gadgets/gadget_medieval_garrison.lua` is layer 5,
   gated on `medievalgarrison`, exports `GG.MedievalGarrison` additively, tracks
   `UnitLoaded`/`UnitUnloaded`, heals with `Spring.SetUnitHealth`, and — the
   architectural invariant of docs/phase-5.md goal 2 — implements NO
   `UnitPreDamaged` hook and never intercepts damage.
6. Gadget behaviour — the gadget source is executed against mocked
   Spring/GG/VFS stubs and driven through Initialize/UnitLoaded/GameFrame.
7. Probe wiring — the Slice 4 probe gadget, its runner and its startscript.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_garrison.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_garrison.lua"
PROBE_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase5_slice4_garrison_probe.lua"
RUNNER_PATH = ROOT / "tools" / "launch" / "run_phase5_slice4_probe.py"
STARTSCRIPT_PATH = ROOT / "tools" / "launch" / "startscript_phase5_slice4.txt"
TC_UNIT_PATH = ROOT / "units" / "medieval_town_center.lua"
TOWER_UNIT_PATH = ROOT / "units" / "medieval_tower.lua"

# Policy constants mirrored from scripts/medieval_garrison.lua.
GARRISON_CAP = {"medieval_town_center": 10, "medieval_tower": 4}
ARCHER_DAMAGE_PER = 0.15
SHELTER_HEAL_PER_TICK = 1
HEAL_TICK_FRAMES = 30
GARRISON_DAMAGE_CAP = 10
BESIEGE_RADIUS = 350
GARRISONABLE = ("medieval_villager", "medieval_archer", "medieval_crossbow")

# Transport capacities the two shelter unit defs must declare.
TC_TRANSPORT_CAPACITY = 10
TOWER_TRANSPORT_CAPACITY = 4

# Gadget harness def ids / unit ids.
TC, TOWER, VILLAGER, ARCHER = 1, 2, 3, 4
TC_ID, TOWER_ID, VILLAGER_ID, ARCHER_ID = 100, 200, 10, 11

CMD_UNLOAD_UNITS = 140


def _lua_to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists."""
    if value is None:
        return None
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class GarrisonBase(unittest.TestCase):
    """Fresh module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------


class TestGarrisonConstants(GarrisonBase):
    def test_town_center_capacity(self):
        self.assertEqual(self.m.GARRISON_CAP["medieval_town_center"], GARRISON_CAP["medieval_town_center"])

    def test_tower_capacity(self):
        self.assertEqual(self.m.GARRISON_CAP["medieval_tower"], GARRISON_CAP["medieval_tower"])

    def test_cap_table_has_exactly_the_two_shelters(self):
        caps = _lua_to_py(self.lua, self.m.GARRISON_CAP)
        self.assertEqual(set(caps.keys()), set(GARRISON_CAP.keys()))

    def test_archer_damage_per(self):
        self.assertAlmostEqual(self.m.ARCHER_DAMAGE_PER, ARCHER_DAMAGE_PER)

    def test_shelter_heal_per_tick(self):
        self.assertEqual(self.m.SHELTER_HEAL_PER_TICK, SHELTER_HEAL_PER_TICK)

    def test_heal_tick_frames(self):
        self.assertEqual(self.m.HEAL_TICK_FRAMES, HEAL_TICK_FRAMES)

    def test_damage_cap_covers_the_largest_shelter(self):
        self.assertEqual(self.m.GARRISON_DAMAGE_CAP, GARRISON_DAMAGE_CAP)
        self.assertGreaterEqual(self.m.GARRISON_DAMAGE_CAP, GARRISON_CAP["medieval_town_center"])

    def test_besiege_radius_is_positive(self):
        self.assertEqual(self.m.BESIEGE_RADIUS, BESIEGE_RADIUS)
        self.assertGreater(self.m.BESIEGE_RADIUS, 0)

    def test_garrisonable_set(self):
        for name in GARRISONABLE:
            self.assertTrue(self.m.GARRISONABLE[name], f"{name} must be garrisonable")

    def test_garrisonable_excludes_melee_and_cavalry(self):
        for name in ("medieval_infantry", "medieval_cavalry", "medieval_knight", "medieval_catapult"):
            self.assertIsNone(
                self.m.GARRISONABLE[name], f"{name} must not be garrisonable"
            )

    def test_required_functions_exported(self):
        for name in (
            "garrison_damage_multiplier",
            "healRate",
            "maxGarrison",
            "shelterState",
            "canGarrison",
            "capacityFor",
            "garrisonAllowed",
            "shelterHealFor",
        ):
            self.assertEqual(
                self.lua.eval("type")(self.m[name]), "function", f"M.{name} must be a function"
            )

    def test_module_is_a_plain_table(self):
        self.assertEqual(self.lua.eval("type")(self.m), "table")


# ---------------------------------------------------------------------------
# 2. Purity
# ---------------------------------------------------------------------------


class TestGarrisonPurity(GarrisonBase):
    """No engine, no VFS, no sibling-module include."""

    def setUp(self):
        super().setUp()
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_no_vfs_include(self):
        self.assertNotIn('VFS.Include("', self.source)

    def test_no_spring_calls(self):
        calls = re.findall(r"Spring\.[A-Za-z_]+\(|Spring\.[A-Za-z_]+:", self.source)
        self.assertEqual(calls, [])

    def test_no_require(self):
        self.assertNotIn("require(", self.source)

    def test_no_gg_api_calls(self):
        calls = re.findall(r"GG\.[A-Za-z_]+\.[A-Za-z_]+\(", self.source)
        self.assertEqual(calls, [])

    def test_no_unitpredamaged_hook_marker(self):
        # The module only computes the multiplier; Slice 5 applies it. The name
        # may appear in prose, but never as an engine call or callin.
        calls = re.findall(r"UnitPreDamaged\s*[=(]", self.source)
        self.assertEqual(calls, [])

    def test_loads_without_any_globals(self):
        # A bare runtime: no VFS, no Spring, no UnitDefs. Loading must succeed
        # and the policy must answer from its arguments alone.
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("Spring"))
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        self.assertAlmostEqual(module.garrison_damage_multiplier(3), 1.45)


# ---------------------------------------------------------------------------
# 3. Damage multiplier
# ---------------------------------------------------------------------------


class TestGarrisonDamageMultiplier(GarrisonBase):
    def test_empty_garrison_is_neutral(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(0), 1.0)

    def test_one_occupant(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(1), 1.0 + ARCHER_DAMAGE_PER)

    def test_three_occupants_matches_the_doc_example(self):
        # docs/phase-5.md Slice 4 probe: tower mult = 1 + 3*0.15 = 1.45.
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(3), 1.45)

    def test_full_town_center_garrison(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(10), 1.0 + 10 * ARCHER_DAMAGE_PER)

    def test_is_additive_per_unit(self):
        one = self.m.garrison_damage_multiplier(1) - 1.0
        two = self.m.garrison_damage_multiplier(2) - 1.0
        self.assertAlmostEqual(two, 2 * one)

    def test_monotonic_non_decreasing(self):
        previous = -1.0
        for count in range(0, 16):
            current = self.m.garrison_damage_multiplier(count)
            self.assertGreaterEqual(current, previous)
            previous = current

    def test_clamps_at_the_damage_cap(self):
        capped = self.m.garrison_damage_multiplier(GARRISON_DAMAGE_CAP)
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(GARRISON_DAMAGE_CAP + 1), capped)
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(1000), capped)

    def test_negative_count_is_neutral(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(-4), 1.0)

    def test_nil_count_is_neutral(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier(None), 1.0)

    def test_string_count_is_neutral(self):
        self.assertAlmostEqual(self.m.garrison_damage_multiplier("three"), 1.0)

    def test_fractional_count_floors(self):
        self.assertAlmostEqual(
            self.m.garrison_damage_multiplier(2.9), self.m.garrison_damage_multiplier(2)
        )

    def test_alias_matches(self):
        for count in (0, 1, 3, 12):
            self.assertAlmostEqual(
                self.m.garrisonDamageMult(count), self.m.garrison_damage_multiplier(count)
            )


# ---------------------------------------------------------------------------
# 4. Heal rate and tick math
# ---------------------------------------------------------------------------


class TestGarrisonHealRate(GarrisonBase):
    def test_empty_shelter_heals_nothing(self):
        self.assertEqual(self.m.healRate(0), 0)

    def test_one_occupant_heals_the_per_tick_amount(self):
        self.assertEqual(self.m.healRate(1), SHELTER_HEAL_PER_TICK)

    def test_rate_is_flat_per_unit(self):
        for count in (1, 4, 10, 40):
            self.assertEqual(self.m.healRate(count), SHELTER_HEAL_PER_TICK)

    def test_negative_and_nil_heal_nothing(self):
        self.assertEqual(self.m.healRate(-1), 0)
        self.assertEqual(self.m.healRate(None), 0)

    def test_shelter_heal_for_one_tick(self):
        self.assertEqual(self.m.shelterHealFor(HEAL_TICK_FRAMES), SHELTER_HEAL_PER_TICK)

    def test_shelter_heal_for_partial_tick(self):
        self.assertEqual(self.m.shelterHealFor(HEAL_TICK_FRAMES - 1), 0)

    def test_shelter_heal_for_multiple_ticks(self):
        self.assertEqual(self.m.shelterHealFor(HEAL_TICK_FRAMES * 3), 3 * SHELTER_HEAL_PER_TICK)

    def test_shelter_heal_for_zero_and_nil(self):
        self.assertEqual(self.m.shelterHealFor(0), 0)
        self.assertEqual(self.m.shelterHealFor(None), 0)

    def test_shelter_heal_is_monotonic(self):
        previous = -1
        for delta in range(0, 4 * HEAL_TICK_FRAMES, 7):
            current = self.m.shelterHealFor(delta)
            self.assertGreaterEqual(current, previous)
            previous = current


# ---------------------------------------------------------------------------
# 5. Capacity clamp
# ---------------------------------------------------------------------------


class TestGarrisonCapacity(GarrisonBase):
    def test_room_below_capacity(self):
        self.assertTrue(self.m.maxGarrison(4, 3))

    def test_room_when_empty(self):
        self.assertTrue(self.m.maxGarrison(10, 0))

    def test_full_shelter_rejects(self):
        self.assertFalse(self.m.maxGarrison(4, 4))

    def test_overfull_shelter_rejects(self):
        self.assertFalse(self.m.maxGarrison(4, 9))

    def test_zero_capacity_never_accepts(self):
        self.assertFalse(self.m.maxGarrison(0, 0))

    def test_negative_capacity_never_accepts(self):
        self.assertFalse(self.m.maxGarrison(-5, 0))

    def test_nil_arguments(self):
        # A nil capacity is "not a shelter" -> reject; a nil count is an empty
        # shelter -> room available.
        self.assertFalse(self.m.maxGarrison(None, None))
        self.assertTrue(self.m.maxGarrison(4, None))
        self.assertFalse(self.m.maxGarrison(None, 0))

    def test_capacity_for_known_shelters(self):
        self.assertEqual(self.m.capacityFor("medieval_town_center"), TC_TRANSPORT_CAPACITY)
        self.assertEqual(self.m.capacityFor("medieval_tower"), TOWER_TRANSPORT_CAPACITY)

    def test_capacity_for_accepts_a_def_table(self):
        def_ = self.lua.table(name="medieval_tower")
        self.assertEqual(self.m.capacityFor(def_), TOWER_TRANSPORT_CAPACITY)

    def test_capacity_for_unknown_or_nil_is_zero(self):
        self.assertEqual(self.m.capacityFor("medieval_barracks"), 0)
        self.assertEqual(self.m.capacityFor(None), 0)

    def test_can_garrison_by_def_name(self):
        self.assertTrue(self.m.canGarrison("medieval_town_center", 9))
        self.assertFalse(self.m.canGarrison("medieval_town_center", 10))
        self.assertFalse(self.m.canGarrison("medieval_tower", 4))

    def test_can_garrison_rejects_non_shelters(self):
        self.assertFalse(self.m.canGarrison("medieval_house", 0))
        self.assertFalse(self.m.canGarrison(None, 0))

    def test_garrison_allowed_accepts_civilians_and_ranged(self):
        for name in GARRISONABLE:
            self.assertTrue(self.m.garrisonAllowed(name), f"{name} must be allowed")

    def test_garrison_allowed_accepts_a_def_table(self):
        def_ = self.lua.table(name="medieval_archer")
        self.assertTrue(self.m.garrisonAllowed(def_))

    def test_garrison_allowed_rejects_others(self):
        for name in ("medieval_infantry", "medieval_tower", "medieval_villager_king", None):
            self.assertFalse(self.m.garrisonAllowed(name), f"{name} must be rejected")


# ---------------------------------------------------------------------------
# 6. shelterState aggregate
# ---------------------------------------------------------------------------


class TestGarrisonShelterState(GarrisonBase):
    def test_empty_shelter(self):
        state = self.m.shelterState(0, 10, False)
        self.assertFalse(state["sheltered"])
        self.assertEqual(state["heal"], 0)
        self.assertAlmostEqual(state["bonus"], 1.0)

    def test_occupied_shelter(self):
        state = self.m.shelterState(3, 10, False)
        self.assertTrue(state["sheltered"])
        self.assertEqual(state["heal"], SHELTER_HEAL_PER_TICK)
        self.assertAlmostEqual(state["bonus"], 1.45)

    def test_enemy_near_shelters_but_suspends_healing(self):
        state = self.m.shelterState(3, 10, True)
        self.assertTrue(state["sheltered"])
        self.assertEqual(state["heal"], 0)
        self.assertAlmostEqual(state["bonus"], 1.45)

    def test_count_is_clamped_to_capacity(self):
        state = self.m.shelterState(99, TOWER_TRANSPORT_CAPACITY, False)
        self.assertAlmostEqual(state["bonus"], self.m.garrison_damage_multiplier(TOWER_TRANSPORT_CAPACITY))

    def test_count_is_clamped_to_the_damage_cap_without_capacity(self):
        state = self.m.shelterState(99, 0, False)
        self.assertAlmostEqual(state["bonus"], self.m.garrison_damage_multiplier(GARRISON_DAMAGE_CAP))

    def test_zero_capacity_with_occupants_still_shelters(self):
        # Defensive: a shelter whose def lookup failed still reports its load.
        state = self.m.shelterState(2, 0, False)
        self.assertTrue(state["sheltered"])

    def test_malformed_arguments_degrade_to_empty(self):
        state = self.m.shelterState(None, None, None)
        self.assertFalse(state["sheltered"])
        self.assertEqual(state["heal"], 0)
        self.assertAlmostEqual(state["bonus"], 1.0)

    def test_negative_count_is_empty(self):
        state = self.m.shelterState(-3, 10, False)
        self.assertFalse(state["sheltered"])
        self.assertAlmostEqual(state["bonus"], 1.0)

    def test_state_is_a_fresh_table_each_call(self):
        first = self.m.shelterState(1, 10, False)
        second = self.m.shelterState(1, 10, False)
        first["heal"] = 999
        self.assertEqual(second["heal"], SHELTER_HEAL_PER_TICK)

    def test_truthy_enemy_flag_of_any_shape_suspends_healing(self):
        for flag in (1, "yes"):
            state = self.m.shelterState(2, 10, flag)
            self.assertEqual(state["heal"], 0, f"flag {flag!r} must suspend healing")


# ---------------------------------------------------------------------------
# 7. Unit defs carry the transport fields
# ---------------------------------------------------------------------------


class TestGarrisonUnitDefs(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)

    def _def(self, path, name):
        table = self.lua.execute(path.read_text(encoding="utf-8"))
        return _lua_to_py(self.lua, table[name])

    def test_town_center_is_a_transport(self):
        tc = self._def(TC_UNIT_PATH, "medieval_town_center")
        self.assertTrue(tc["isTransport"])
        self.assertEqual(tc["transportCapacity"], TC_TRANSPORT_CAPACITY)
        self.assertEqual(tc["transportMass"], 50)
        self.assertEqual(tc["transportSize"], 1)

    def test_town_center_load_unload_flags(self):
        tc = self._def(TC_UNIT_PATH, "medieval_town_center")
        self.assertTrue(tc["canLoad"])
        self.assertTrue(tc["canUnload"])
        self.assertTrue(tc["allowUnload"])

    def test_town_center_small_radius_and_unload_spread(self):
        tc = self._def(TC_UNIT_PATH, "medieval_town_center")
        self.assertLessEqual(tc["loadingRadius"], 128)
        self.assertGreater(tc["unloadSpread"], 0)

    def test_tower_is_a_transport(self):
        tower = self._def(TOWER_UNIT_PATH, "medieval_tower")
        self.assertTrue(tower["isTransport"])
        self.assertEqual(tower["transportCapacity"], TOWER_TRANSPORT_CAPACITY)
        self.assertEqual(tower["transportMass"], 50)
        self.assertTrue(tower["canLoad"])
        self.assertTrue(tower["canUnload"])
        self.assertTrue(tower["allowUnload"])

    def test_existing_town_center_fields_survive(self):
        tc = self._def(TC_UNIT_PATH, "medieval_town_center")
        self.assertEqual(tc["name"], "Town Center")
        self.assertTrue(tc["isFactory"])
        self.assertEqual(tc["maxDamage"], 3000)
        self.assertEqual(tc["footprintX"], 7)
        self.assertTrue(tc["customparams"]["dropoff"])
        self.assertEqual(tc["buildoptions"][0], "medieval_villager")

    def test_existing_tower_fields_survive(self):
        tower = self._def(TOWER_UNIT_PATH, "medieval_tower")
        self.assertEqual(tower["name"], "Watchtower")
        self.assertEqual(tower["maxDamage"], 1800)
        self.assertEqual(tower["sightDistance"], 700)
        self.assertEqual(tower["customparams"]["armor_class"], "fortification")
        self.assertFalse(tower["canMove"])

    def test_capacities_match_the_pure_module(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        tc = self._def(TC_UNIT_PATH, "medieval_town_center")
        tower = self._def(TOWER_UNIT_PATH, "medieval_tower")
        self.assertEqual(module.GARRISON_CAP["medieval_town_center"], tc["transportCapacity"])
        self.assertEqual(module.GARRISON_CAP["medieval_tower"], tower["transportCapacity"])


# ---------------------------------------------------------------------------
# 8. Gadget contract (source level)
# ---------------------------------------------------------------------------


class TestGarrisonGadgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_layer_is_five(self):
        self.assertIn("layer = 5,", self.src)

    def test_gated_on_the_medievalgarrison_modoption(self):
        self.assertIn("medievalgarrison", self.src)

    def test_includes_the_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_garrison.lua")', self.src)

    def test_synced_only(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.src)

    def test_exports_gg_medieval_garrison(self):
        self.assertIn("GG.MedievalGarrison", self.src)

    def test_export_is_additive(self):
        # Never reassign the whole table: a sibling slice may already own fields.
        self.assertIn("GG.MedievalGarrison = GG.MedievalGarrison or {}", self.src)
        self.assertNotIn("GG.MedievalGarrison = {", self.src)

    def test_tracks_load_and_unload(self):
        self.assertIn("function gadget:UnitLoaded", self.src)
        self.assertIn("function gadget:UnitUnloaded", self.src)

    def test_handles_destroyed_shelters_and_occupants(self):
        self.assertIn("function gadget:UnitDestroyed", self.src)

    def test_heals_via_setunithealth(self):
        self.assertIn("Spring.SetUnitHealth", self.src)
        self.assertIn("Spring.GetUnitHealth", self.src)

    def test_heal_tick_uses_the_module_cadence(self):
        self.assertIn("garrison.HEAL_TICK_FRAMES", self.src)

    def test_publishes_the_team_garrison_param(self):
        self.assertIn('"team_%d_garrison"', self.src)
        self.assertIn("SetGameRulesParam", self.src)

    def test_does_not_implement_unitpredamaged(self):
        # docs/phase-5.md goal 2: Slice 5 owns the single UnitPreDamaged hook.
        # The name may appear in prose explaining the boundary, never as a callin.
        self.assertNotIn("function gadget:UnitPreDamaged", self.src)

    def test_does_not_intercept_damage(self):
        for callin in ("AllowUnitCreation", "AllowUnitTransfer", "UnitPreDamaged", "ShieldPreDamaged"):
            self.assertNotIn(
                f"function gadget:{callin}", self.src, f"garrison must not implement {callin}"
            )

    def test_caps_come_from_the_pure_module(self):
        self.assertIn("garrison.GARRISON_CAP", self.src)

    def test_exports_the_documented_api(self):
        for name in ("Occupy", "Eject", "GetOccupancy", "GetDamageMult"):
            self.assertIn(f"GG.MedievalGarrison.{name}", self.src)


# ---------------------------------------------------------------------------
# 9. Gadget behaviour (executed against stubs)
# ---------------------------------------------------------------------------


GADGET_HARNESS = r"""
GADGET_SRC = io.open(ROOT_PATH .. "/luarules/gadgets/gadget_medieval_garrison.lua", "r"):read("*a")
MODULE_SRC = io.open(ROOT_PATH .. "/scripts/medieval_garrison.lua", "r"):read("*a")

PARAMS = {}
HP = {}
MAXHP = {}
ORDERS = {}
UNIT_DEF = {}
TEAM_OF = {}
NEAR = {}

gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }

CMD = { UNLOAD_UNITS = 140 }

UnitDefs = {
  [TC]      = { name = "medieval_town_center" },
  [TOWER]   = { name = "medieval_tower" },
  [VILLAGER]= { name = "medieval_villager" },
  [ARCHER]  = { name = "medieval_archer" },
}

Spring = {
  GetModOptions = function() return MODOPTIONS end,
  Echo = function() end,
  GetUnitDefID = function(uid) return UNIT_DEF[uid] end,
  GetUnitTeam = function(uid) return TEAM_OF[uid] or 0 end,
  AreTeamsAllied = function(a, b) return a == b end,
  GetUnitHealth = function(uid) return HP[uid], MAXHP[uid] end,
  SetUnitHealth = function(uid, hp) HP[uid] = hp end,
  SetGameRulesParam = function(key, value) PARAMS[key] = value end,
  GetUnitPosition = function(uid) return 100, 0, 100 end,
  GetUnitsInCylinder = function(x, z, r) return NEAR end,
  GiveOrderToUnit = function(uid, cmd, params, opts) ORDERS[#ORDERS + 1] = cmd end,
}

VFS = {
  Include = function(path) return assert(load(MODULE_SRC, "@" .. path))() end,
}

GG = {}

assert(load(GADGET_SRC, "@gadget_medieval_garrison.lua"))()

local function occupy(unitID, defID, team, transportID, transportTeam)
  UNIT_DEF[unitID] = defID
  TEAM_OF[unitID] = team
  HP[unitID] = 100
  MAXHP[unitID] = 450
  gadget:UnitLoaded(unitID, defID, team, transportID, transportTeam or team)
end

-- One town center (100) holding two villagers (10, 11).
UNIT_DEF[TC_ID] = TC
TEAM_OF[TC_ID] = 0
gadget:Initialize()
occupy(VILLAGER_ID, VILLAGER, 0, TC_ID, 0)
occupy(ARCHER_ID, ARCHER, 0, TC_ID, 0)
"""


class TestGarrisonGadgetBehaviour(unittest.TestCase):
    def _boot(self, modoption=True):
        lua = LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.MODOPTIONS = lua.table(medievalgarrison=1 if modoption else 0)
        g.TC, g.TOWER, g.VILLAGER, g.ARCHER = TC, TOWER, VILLAGER, ARCHER
        g.TC_ID, g.TOWER_ID, g.VILLAGER_ID, g.ARCHER_ID = TC_ID, TOWER_ID, VILLAGER_ID, ARCHER_ID
        lua.execute(GADGET_HARNESS)
        return lua

    def test_api_is_exported(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        for name in ("Occupy", "Eject", "GetOccupancy", "GetDamageMult", "GetShelterState", "IsGarrisonable"):
            self.assertEqual(lua.eval("type")(api[name]), "function", f"{name} must be a function")

    def test_occupancy_tracks_loads(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        self.assertEqual(api.GetOccupancy(TC_ID), 2)

    def test_unknown_transport_is_ignored(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        # def id 999 has no UnitDefs entry -> not a shelter.
        lua.globals().UNIT_DEF[999] = 999
        lua.execute("gadget:UnitLoaded(999, 999, 0, 999, 0)")
        self.assertEqual(api.GetOccupancy(999), 0)

    def test_damage_multiplier_from_occupancy(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        self.assertAlmostEqual(api.GetDamageMult(TC_ID), 1.0 + 2 * ARCHER_DAMAGE_PER)

    def test_capacity_comes_from_the_unit_def(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        self.assertEqual(api.GetCapacity(TC_ID), TC_TRANSPORT_CAPACITY)

    def test_garrison_rules_param_published(self):
        lua = self._boot()
        self.assertEqual(lua.globals().PARAMS["team_0_garrison"], 2)

    def test_heal_tick_restores_hp(self):
        lua = self._boot()
        lua.globals().HP[VILLAGER_ID] = 100
        lua.execute("gadget:GameFrame(30)")
        self.assertEqual(lua.globals().HP[VILLAGER_ID], 101)

    def test_heal_respects_the_frame_cadence(self):
        lua = self._boot()
        lua.globals().HP[VILLAGER_ID] = 100
        lua.execute("gadget:GameFrame(31)")
        self.assertEqual(lua.globals().HP[VILLAGER_ID], 100)

    def test_heal_never_exceeds_max(self):
        lua = self._boot()
        lua.globals().HP[VILLAGER_ID] = 450
        lua.execute("gadget:GameFrame(60)")
        self.assertEqual(lua.globals().HP[VILLAGER_ID], 450)

    def test_enemy_near_suspends_healing(self):
        lua = self._boot()
        lua.globals().HP[VILLAGER_ID] = 100
        # Enemy team 1 unit inside the siege radius.
        lua.execute("NEAR = { 77 }; TEAM_OF[77] = 1; gadget:GameFrame(90)")
        self.assertEqual(lua.globals().HP[VILLAGER_ID], 100)

    def test_unload_clears_occupancy(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        lua.execute("gadget:UnitUnloaded(%d, %d, 0, %d, 0)" % (VILLAGER_ID, VILLAGER, TC_ID))
        self.assertEqual(api.GetOccupancy(TC_ID), 1)

    def test_eject_issues_an_unload_order(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        api.Eject(TC_ID)
        orders = _lua_to_py(lua, lua.globals().ORDERS)
        self.assertIn(CMD_UNLOAD_UNITS, orders)

    def test_destroyed_occupant_leaves_the_ledger(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        lua.execute("gadget:UnitDestroyed(%d, %d, 0)" % (VILLAGER_ID, VILLAGER))
        self.assertEqual(api.GetOccupancy(TC_ID), 1)

    def test_destroyed_shelter_drops_its_ledger(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        lua.execute("gadget:UnitDestroyed(%d, %d, 0)" % (TC_ID, TC))
        self.assertEqual(api.GetOccupancy(TC_ID), 0)

    def test_shelter_state_shape(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        state = api.GetShelterState(TC_ID)
        self.assertTrue(state["sheltered"])
        self.assertEqual(state["heal"], SHELTER_HEAL_PER_TICK)
        self.assertAlmostEqual(state["bonus"], 1.0 + 2 * ARCHER_DAMAGE_PER)

    def test_garrisonable_gate_matches_the_module(self):
        lua = self._boot()
        api = lua.globals().GG.MedievalGarrison
        self.assertTrue(api.IsGarrisonable("medieval_villager"))
        self.assertFalse(api.IsGarrisonable("medieval_infantry"))

    def test_no_unitpredamaged_callin_is_defined(self):
        lua = self._boot()
        self.assertIsNone(lua.globals().gadget.UnitPreDamaged)


# ---------------------------------------------------------------------------
# 10. Probe wiring
# ---------------------------------------------------------------------------


class TestGarrisonProbeWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = PROBE_PATH.read_text(encoding="utf-8")
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.startscript = STARTSCRIPT_PATH.read_text(encoding="utf-8")

    def test_probe_exists_and_is_synced(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.probe)

    def test_probe_gated_on_the_modoption(self):
        self.assertIn("medievalgarrison", self.probe)

    def test_probe_spawns_a_town_center_and_villagers(self):
        self.assertIn("medieval_town_center", self.probe)
        self.assertIn("medieval_villager", self.probe)

    def test_probe_issues_a_load_order(self):
        self.assertIn("LOAD_UNITS", self.probe)

    def test_probe_emits_the_required_verdicts(self):
        self.assertIn("shelter-verdict", self.probe)
        self.assertIn("PHASE5 GARRISON probe-complete PASS", self.probe)

    def test_probe_emits_the_supporting_verdicts(self):
        for verdict in ("damage-mult-verdict", "heal-verdict", "eject-verdict"):
            self.assertIn(verdict, self.probe)

    def test_probe_does_not_hook_damage(self):
        self.assertNotIn("function gadget:UnitPreDamaged", self.probe)

    def test_runner_watches_every_verdict(self):
        for resource in ("shelter", "damage-mult", "heal", "eject", "probe-complete"):
            self.assertIn(f'"{resource}"', self.runner)

    def test_runner_uses_the_slice4_startscript(self):
        self.assertIn("startscript_phase5_slice4.txt", self.runner)

    def test_startscript_enables_the_modoption(self):
        self.assertIn("medievalgarrison=1;", self.startscript)

    def test_startscript_reaches_the_probe_terminal_frame(self):
        match = re.search(r"quitforce", self.startscript)
        self.assertIsNotNone(match)
        self.assertIn("forcestart", self.startscript)


if __name__ == "__main__":
    unittest.main()
