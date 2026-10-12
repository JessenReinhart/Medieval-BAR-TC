"""Phase-5 Slice 1 tests: match objectives and the victory/defeat engine.

Layers under test:

1. Pure module — `scripts/medieval_victory.lua`, a dependency-free, engine-free
   policy module. Every test boots its OWN fresh Lua runtime (no shared
   setUpClass state) so one case cannot leak mutated module tables into another.
2. Purity — the module must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present, because the synced gadget `VFS.Include`s it and the tests load
   it directly. This is a hard requirement, not a style preference.
3. Classification — `classifyDef` across the full `units/*.lua` roster, plus the
   totality fallback for unknown/non-string input.
4. Verdicts — `evaluate` for all four modes, the two-team terminal rule, draws,
   single-team projections and malformed input.
5. Helpers — `teamEliminated`, `remainingAllyTeams`, `canSurrender` (frame floor)
   and `normalizeMode`.
6. Unit def — `units/medieval_king.lua` (unarmed-but-for-a-dagger, high health,
   with the dedicated Phase 7 Slice 3 king mesh).
7. Gadget contract — `luarules/gadgets/gadget_medieval_victory.lua` is layer 6,
   gated on `medievalvictory` / `victorymode`, tracks the six documented callins,
   calls `Spring.GameOver` with a winner tuple, and publishes the two rules
   params.
8. Probe contract — `luarules/gadgets/gadget_phase5_slice1_victory_probe.lua`
   emits the verdict keys the runner greps for.
9. Modoption — `modoptions.lua` still declares `victorymode` and `medievalvictory`.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_victory.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_victory.lua"
PROBE_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase5_slice1_victory_probe.lua"
KING_PATH = ROOT / "units" / "medieval_king.lua"
UNITS_DIR = ROOT / "units"
MODOPTIONS_PATH = ROOT / "modoptions.lua"
WEAPONDEFS_PATH = ROOT / "gamedata" / "weapondefs.lua"
RUNNER_PATH = ROOT / "tools" / "launch" / "run_phase5_slice1_probe.py"
STARTSCRIPT_PATH = ROOT / "tools" / "launch" / "startscript_slice1.txt"

# Constants mirrored from scripts/medieval_victory.lua.
WIN_MODES = ("conquest", "tc_destruction", "regicide", "surrender")
DEFAULT_MODE = "tc_destruction"
SURRENDER_MIN_FRAMES = 120
REGICIDE_KING_DEF = "medieval_king"

# The military roster, mirrored from scripts/medieval_recruitment.lua UPKEEP > 0
# plus the Phase 5 Slice 5 spearman.
MILITARY_NAMES = (
    "medieval_infantry",
    "medieval_archer",
    "medieval_cavalry",
    "medieval_catapult",
    "medieval_men_at_arms",
    "medieval_crossbow",
    "medieval_knight",
    "medieval_spearman",
)

CIVILIAN_NAMES = ("medieval_villager", "medieval_cart")

BUILDING_NAMES = (
    "medieval_house",
    "medieval_granary",
    "medieval_lumber_camp",
    "medieval_barracks",
    "medieval_stables",
    "medieval_blacksmith",
    "medieval_fletcher",
    "medieval_wall",
    "medieval_tower",
    "medieval_market",
)

REQUIRED_FUNCTIONS = (
    "classifyDef",
    "evaluate",
    "teamEliminated",
    "remainingAllyTeams",
    "canSurrender",
)

GADGET_API = (
    "GetMode",
    "GetStatus",
    "Evaluate",
    "SurrenderTeam",
    "RegisterKing",
    "ForceDefeat",
)


def _lua_to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists.

    A Lua table with no keys is ambiguous (empty array vs empty map); every
    empty table this suite converts is an array (a `losers` list or a team
    roster), so it becomes [].
    """
    if value is None:
        return None
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if not keys:
            return []
        if all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


def _verdict_to_py(lua, value):
    """Convert an `evaluate` result, filling the keys Lua drops when nil."""
    out = {"winnerAllyTeam": None, "losers": [], "reason": None}
    if value is None or lua.eval("type")(value) != "table":
        return out
    for key in list(value.keys()):
        out[key] = _lua_to_py(lua, value[key])
    return out


class VictoryBase(unittest.TestCase):
    """Fresh module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    # -- helpers -------------------------------------------------------------

    def _state(self, **teams):
        """Build a projection: _state(**{"0": dict(tcs=1)}, ...) is awkward, so
        callers pass a dict of allyTeam -> entry via _projection()."""
        return self._projection(teams)

    def _projection(self, teams):
        table = self.lua.table()
        for ally_team, entry in teams.items():
            row = self.lua.table(
                tcs=entry.get("tcs", 0),
                kings=entry.get("kings", 0),
                units=entry.get("units", 0),
                surrendered=entry.get("surrendered", False),
            )
            table[int(ally_team)] = row
        return table

    def _evaluate(self, teams, mode=None):
        return _verdict_to_py(self.lua, self.m.evaluate(self._projection(teams), mode))

    def _remaining(self, teams, mode=None):
        return _lua_to_py(self.lua, self.m.remainingAllyTeams(self._projection(teams), mode))


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------


class TestVictoryConstants(VictoryBase):
    def test_win_modes(self):
        self.assertEqual(list(_lua_to_py(self.lua, self.m.WIN_MODES)), list(WIN_MODES))

    def test_default_mode(self):
        self.assertEqual(self.m.DEFAULT_MODE, DEFAULT_MODE)

    def test_surrender_min_frames(self):
        self.assertEqual(self.m.SURRENDER_MIN_FRAMES, SURRENDER_MIN_FRAMES)

    def test_regicide_king_def(self):
        self.assertEqual(self.m.REGICIDE_KING_DEF, REGICIDE_KING_DEF)

    def test_classes_cover_every_verdict(self):
        classes = _lua_to_py(self.lua, self.m.CLASSES)
        for expected in ("town_center", "king", "military", "civilian", "building", "other"):
            self.assertIn(expected, classes)

    def test_required_functions_exported(self):
        for name in REQUIRED_FUNCTIONS:
            self.assertNotEqual(
                self.lua.eval("type")(self.m[name]),
                "nil",
                f"module does not export {name}",
            )

    def test_module_is_a_plain_table(self):
        self.assertEqual(self.lua.eval("type")(self.m), "table")


# ---------------------------------------------------------------------------
# 2. Purity
# ---------------------------------------------------------------------------


class TestVictoryPurity(VictoryBase):
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

    def test_loads_without_any_globals(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("Spring"))
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(module.classifyDef("medieval_king"), "king")


# ---------------------------------------------------------------------------
# 3. Classification
# ---------------------------------------------------------------------------


class TestClassifyDef(VictoryBase):
    def test_town_center(self):
        self.assertEqual(self.m.classifyDef("medieval_town_center"), "town_center")

    def test_king(self):
        self.assertEqual(self.m.classifyDef("medieval_king"), "king")

    def test_military_roster(self):
        for name in MILITARY_NAMES:
            self.assertEqual(self.m.classifyDef(name), "military", name)

    def test_civilians(self):
        for name in CIVILIAN_NAMES:
            self.assertEqual(self.m.classifyDef(name), "civilian", name)

    def test_buildings(self):
        for name in BUILDING_NAMES:
            self.assertEqual(self.m.classifyDef(name), "building", name)

    def test_unknown_is_other(self):
        self.assertEqual(self.m.classifyDef("armcom"), "other")
        self.assertEqual(self.m.classifyDef(""), "other")

    def test_non_string_is_other(self):
        self.assertEqual(self.m.classifyDef(None), "other")
        self.assertEqual(self.m.classifyDef(7), "other")
        self.assertEqual(self.m.classifyDef({}), "other")

    def test_the_king_is_not_military(self):
        # Regicide depends on this: a king must never inflate `units`-style
        # elimination logic as if it were a field army.
        self.assertNotEqual(self.m.classifyDef(REGICIDE_KING_DEF), "military")
        self.assertNotEqual(self.m.classifyDef("medieval_town_center"), "building")

    def test_every_unit_def_in_the_repo_is_classified(self):
        """No def may silently fall through to "other": a new unit that nobody
        classified would be invisible to the victory engine."""
        unclassified = []
        for path in sorted(UNITS_DIR.glob("*.lua")):
            table = self.lua.execute(path.read_text(encoding="utf-8"))
            for def_name in table.keys():
                if self.m.classifyDef(def_name) == "other":
                    unclassified.append(def_name)
        self.assertEqual(unclassified, [], f"unclassified unit defs: {unclassified}")


# ---------------------------------------------------------------------------
# 4. Verdicts
# ---------------------------------------------------------------------------


class TestEvaluate(VictoryBase):
    def test_both_alive_is_no_verdict(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "kings": 1, "units": 4}, 1: {"tcs": 1, "kings": 1, "units": 4}}
        )
        self.assertIsNone(verdict["winnerAllyTeam"])
        self.assertIsNone(verdict["reason"])
        self.assertEqual(verdict["losers"], [])

    # -- conquest ------------------------------------------------------------

    def test_conquest_loses_only_with_no_tc_and_no_units(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "units": 0}, 1: {"tcs": 0, "units": 0}}, "conquest"
        )
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["reason"], "conquest")
        self.assertEqual(verdict["losers"], [1])

    def test_conquest_spares_a_team_with_units_left(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "units": 0}, 1: {"tcs": 0, "units": 3}}, "conquest"
        )
        self.assertIsNone(verdict["winnerAllyTeam"])

    def test_conquest_spares_a_team_with_a_tc_left(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "units": 9}, 1: {"tcs": 1, "units": 0}}, "conquest"
        )
        self.assertIsNone(verdict["winnerAllyTeam"])

    # -- tc_destruction ------------------------------------------------------

    def test_tc_destruction_ignores_surviving_units(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "units": 1}, 1: {"tcs": 0, "units": 25}}, "tc_destruction"
        )
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["reason"], "tc_destruction")

    def test_tc_destruction_is_the_default_mode(self):
        state = self._projection({0: {"tcs": 1}, 1: {"tcs": 0}})
        verdict = _verdict_to_py(self.lua, self.m.evaluate(state, None))
        self.assertEqual(verdict["reason"], DEFAULT_MODE)

    def test_tc_destruction_needs_both_tcs_gone_to_end_a_team(self):
        verdict = self._evaluate(
            {0: {"tcs": 1}, 1: {"tcs": 1}}, "tc_destruction"
        )
        self.assertIsNone(verdict["winnerAllyTeam"])

    # -- regicide ------------------------------------------------------------

    def test_regicide_ignores_economy_and_army(self):
        verdict = self._evaluate(
            {0: {"tcs": 3, "kings": 0, "units": 40}, 1: {"tcs": 0, "kings": 1, "units": 0}},
            "regicide",
        )
        self.assertEqual(verdict["winnerAllyTeam"], 1)
        self.assertEqual(verdict["reason"], "regicide")

    def test_regicide_spares_a_kingless_team_while_the_other_king_lives(self):
        verdict = self._evaluate({0: {"kings": 1}, 1: {"kings": 1}}, "regicide")
        self.assertIsNone(verdict["winnerAllyTeam"])

    # -- surrender -----------------------------------------------------------

    def test_surrender_removes_only_the_surrendering_team(self):
        verdict = self._evaluate(
            {0: {"tcs": 1, "units": 4}, 1: {"tcs": 1, "units": 4, "surrendered": True}},
            "surrender",
        )
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["reason"], "surrender")

    def test_surrender_mode_ignores_a_destroyed_tc(self):
        # Under `surrender`, losing the settlement is not a loss condition.
        verdict = self._evaluate({0: {"tcs": 1}, 1: {"tcs": 0}}, "surrender")
        self.assertIsNone(verdict["winnerAllyTeam"])

    def test_surrender_flag_is_ignored_under_other_modes(self):
        teams = {0: {"tcs": 1}, 1: {"tcs": 1, "surrendered": True}}
        for mode in ("conquest", "tc_destruction", "regicide"):
            verdict = self._evaluate(teams, mode)
            self.assertIsNone(verdict["winnerAllyTeam"], mode)

    # -- terminal rule and draws --------------------------------------------

    def test_mutual_elimination_is_a_draw(self):
        verdict = self._evaluate({0: {"tcs": 0}, 1: {"tcs": 0}}, "tc_destruction")
        self.assertIsNone(verdict["winnerAllyTeam"])
        self.assertIsNone(verdict["reason"])
        self.assertEqual(verdict["losers"], [0, 1])

    def test_three_teams_need_two_eliminations(self):
        verdict = self._evaluate(
            {0: {"tcs": 1}, 1: {"tcs": 0}, 2: {"tcs": 1}}, "tc_destruction"
        )
        self.assertIsNone(verdict["winnerAllyTeam"])
        self.assertEqual(verdict["losers"], [1])

    def test_three_teams_declare_the_last_survivor(self):
        verdict = self._evaluate(
            {0: {"tcs": 1}, 1: {"tcs": 0}, 2: {"tcs": 0}}, "tc_destruction"
        )
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["losers"], [1, 2])

    def test_single_team_projection_never_declares_a_winner(self):
        verdict = self._evaluate({0: {"tcs": 1, "units": 5}}, "tc_destruction")
        self.assertIsNone(verdict["winnerAllyTeam"])
        self.assertIsNone(verdict["reason"])

    def test_empty_projection_is_a_no_op(self):
        verdict = self._evaluate({}, "tc_destruction")
        self.assertIsNone(verdict["winnerAllyTeam"])
        self.assertEqual(verdict["losers"], [])

    def test_reason_is_non_nil_exactly_when_a_winner_is(self):
        cases = (
            ({0: {"tcs": 1}, 1: {"tcs": 0}}, "tc_destruction"),
            ({0: {"tcs": 1}, 1: {"tcs": 1}}, "tc_destruction"),
            ({0: {"tcs": 0}, 1: {"tcs": 0}}, "tc_destruction"),
        )
        for teams, mode in cases:
            verdict = self._evaluate(teams, mode)
            self.assertEqual(
                verdict["winnerAllyTeam"] is None,
                verdict["reason"] is None,
                f"winner/reason mismatch for {teams} under {mode}",
            )

    # -- totality ------------------------------------------------------------

    def test_malformed_state_returns_the_no_verdict_shape(self):
        for bad in (None, "nonsense", 42, True):
            verdict = _verdict_to_py(self.lua, self.m.evaluate(bad, "conquest"))
            self.assertIsNone(verdict["winnerAllyTeam"])
            self.assertIsNone(verdict["reason"])
            self.assertEqual(verdict["losers"], [])

    def test_unknown_mode_falls_back_to_the_default(self):
        verdict = self._evaluate({0: {"tcs": 1}, 1: {"tcs": 0}}, "martian_chess")
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["reason"], DEFAULT_MODE)

    def test_non_table_entry_counts_as_eliminated(self):
        state = self.lua.table()
        state[0] = self.lua.table(tcs=1, kings=0, units=0, surrendered=False)
        state[1] = "not a table"
        verdict = _lua_to_py(self.lua, self.m.evaluate(state, "tc_destruction"))
        self.assertEqual(verdict["winnerAllyTeam"], 0)

    def test_garbage_counts_coerce_to_zero(self):
        verdict = self._evaluate(
            {0: {"tcs": 1}, 1: {"tcs": -4, "units": "many"}}, "tc_destruction"
        )
        self.assertEqual(verdict["winnerAllyTeam"], 0)

    def test_float_counts_are_floored(self):
        verdict = self._evaluate({0: {"tcs": 1}, 1: {"tcs": 0.9}}, "tc_destruction")
        self.assertEqual(verdict["winnerAllyTeam"], 0)

    def test_non_numeric_keys_are_ignored(self):
        state = self._projection({0: {"tcs": 1}, 1: {"tcs": 0}})
        state["gaia"] = self.lua.table(tcs=5, kings=5, units=5, surrendered=False)
        verdict = _lua_to_py(self.lua, self.m.evaluate(state, "tc_destruction"))
        self.assertEqual(verdict["winnerAllyTeam"], 0)
        self.assertEqual(verdict["losers"], [1])


# ---------------------------------------------------------------------------
# 5. Helpers
# ---------------------------------------------------------------------------


class TestTeamEliminated(VictoryBase):
    def test_absent_team_is_eliminated(self):
        state = self._projection({0: {"tcs": 1}})
        self.assertTrue(self.m.teamEliminated(state, 7, "tc_destruction"))

    def test_nil_state_is_eliminated(self):
        self.assertTrue(self.m.teamEliminated(None, 0, "conquest"))

    def test_nil_ally_team_is_eliminated(self):
        state = self._projection({0: {"tcs": 1}})
        self.assertTrue(self.m.teamEliminated(state, None, "conquest"))

    def test_alive_team_is_not_eliminated(self):
        state = self._projection({0: {"tcs": 1, "kings": 1, "units": 2}})
        for mode in WIN_MODES:
            self.assertFalse(self.m.teamEliminated(state, 0, mode), mode)


class TestRemainingAllyTeams(VictoryBase):
    def test_ascending_order(self):
        teams = {2: {"tcs": 1}, 0: {"tcs": 1}, 1: {"tcs": 0}}
        self.assertEqual(self._remaining(teams, "tc_destruction"), [0, 2])

    def test_empty_state(self):
        self.assertEqual(self._remaining({}, "conquest"), [])

    def test_malformed_state(self):
        self.assertEqual(_lua_to_py(self.lua, self.m.remainingAllyTeams(None, "conquest")), [])


class TestCanSurrender(VictoryBase):
    def _state(self):
        return self._projection({0: {"tcs": 1, "units": 3}})

    def test_below_the_floor_is_refused(self):
        self.assertFalse(self.m.canSurrender(self._state(), 0, SURRENDER_MIN_FRAMES - 1))

    def test_at_the_floor_is_allowed(self):
        self.assertTrue(self.m.canSurrender(self._state(), 0, SURRENDER_MIN_FRAMES))

    def test_frame_zero_is_refused(self):
        self.assertFalse(self.m.canSurrender(self._state(), 0, 0))

    def test_nil_frame_is_refused(self):
        self.assertFalse(self.m.canSurrender(self._state(), 0, None))

    def test_negative_frame_is_refused(self):
        self.assertFalse(self.m.canSurrender(self._state(), 0, -1))

    def test_already_surrendered_is_refused(self):
        state = self._projection({0: {"tcs": 1, "surrendered": True}})
        self.assertFalse(self.m.canSurrender(state, 0, SURRENDER_MIN_FRAMES + 500))

    def test_unknown_team_is_refused(self):
        self.assertFalse(self.m.canSurrender(self._state(), 9, SURRENDER_MIN_FRAMES))

    def test_malformed_state_is_refused(self):
        self.assertFalse(self.m.canSurrender(None, 0, SURRENDER_MIN_FRAMES))
        self.assertFalse(self.m.canSurrender("nope", 0, SURRENDER_MIN_FRAMES))


class TestNormalizeMode(VictoryBase):
    def test_known_modes_pass_through(self):
        for mode in WIN_MODES:
            self.assertEqual(self.m.normalizeMode(mode), mode)

    def test_unknown_and_missing_fall_back(self):
        self.assertEqual(self.m.normalizeMode("nope"), DEFAULT_MODE)
        self.assertEqual(self.m.normalizeMode(None), DEFAULT_MODE)
        self.assertEqual(self.m.normalizeMode(3), DEFAULT_MODE)

    def test_is_win_mode(self):
        for mode in WIN_MODES:
            self.assertTrue(self.m.isWinMode(mode), mode)
        self.assertFalse(self.m.isWinMode("nope"))
        self.assertFalse(self.m.isWinMode(None))


class TestEmptyEntry(VictoryBase):
    def test_shape(self):
        entry = _lua_to_py(self.lua, self.m.emptyEntry())
        self.assertEqual(entry, {"tcs": 0, "kings": 0, "units": 0, "surrendered": False})


# ---------------------------------------------------------------------------
# 6. Unit def
# ---------------------------------------------------------------------------


class TestKingUnitDef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(KING_PATH.read_text(encoding="utf-8"))
        cls.defn = table["medieval_king"]

    def test_identity(self):
        self.assertEqual(self.defn["name"], REGICIDE_KING_DEF)
        self.assertEqual(self.defn["side"], "MEDIEVAL")
        self.assertEqual(self.defn["category"], "LAND")

    def test_high_health_objective(self):
        self.assertEqual(self.defn["maxDamage"], 1200)
        self.assertGreater(self.defn["maxDamage"], 1000)

    def test_armed_only_with_a_dagger(self):
        weapons = self.defn["weapons"]
        self.assertEqual(len(weapons), 1)
        self.assertEqual(weapons[1]["name"], "dagger")
        self.assertTrue(self.defn["canAttack"])

    def test_has_dedicated_converted_art(self):
        # Phase 7 Slice 3 lifted the Phase-5 "no new asset for the king" boundary:
        # the king now owns objects3d/0ad/medieval_king.obj.
        self.assertEqual(self.defn["objectName"], "0ad/medieval_king.obj")
        self.assertTrue((ROOT / "objects3d" / self.defn["objectName"]).exists())

    def test_script_is_an_existing_lus(self):
        self.assertEqual(self.defn["script"], "medieval_infantry.lua")
        self.assertTrue((ROOT / "scripts" / self.defn["script"]).exists())

    def test_footprint_matches_movedef(self):
        self.assertEqual(self.defn["movementclass"], "BOT2")
        self.assertEqual(self.defn["footprintX"], 2)
        self.assertEqual(self.defn["footprintZ"], 2)

    def test_objective_customparam(self):
        cp = self.defn["customparams"]
        self.assertEqual(cp["unit_role"], "king")
        self.assertEqual(cp["victory_objective"], "king")

    def test_free_to_spawn(self):
        # The gadget spawns kings at match start, so the def must not carry a
        # cost the economy gadget would charge against a team's stockpile.
        for resource in ("food", "wood", "stone", "iron"):
            self.assertEqual(self.defn["customparams"]["resource_cost_" + resource], 0)

    def test_weapondef_exists(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        defs = lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        self.assertIsNotNone(defs["dagger"])
        self.assertEqual(defs["dagger"]["customparams"]["damage_class"], "melee")

    def test_dagger_is_the_weakest_weapon_in_the_repo(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        defs = lua.execute(WEAPONDEFS_PATH.read_text(encoding="utf-8"))
        dagger = defs["dagger"]["damage"]["default"]
        for name in ("sword", "lance", "longbow", "catapult"):
            self.assertLess(dagger, defs[name]["damage"]["default"], name)


# ---------------------------------------------------------------------------
# 7. Gadget contract
# ---------------------------------------------------------------------------


class TestVictoryGadgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_layer_is_six(self):
        self.assertIn("layer = 6,", self.src)

    def test_synced_only(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.src)

    def test_includes_the_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_victory.lua")', self.src)

    def test_gated_on_medievalvictory_and_victorymode(self):
        self.assertIn("medievalvictory", self.src)
        self.assertIn("victorymode", self.src)

    def test_tracking_callins(self):
        for callin in (
            "function gadget:UnitCreated",
            "function gadget:UnitDestroyed",
            "function gadget:UnitTaken",
            "function gadget:UnitGiven",
            "function gadget:TeamDied",
            "function gadget:GameFrame",
        ):
            self.assertIn(callin, self.src)

    def test_gameover_winner_tuple(self):
        self.assertIn("Spring.GameOver({ [winnerAllyTeam] = 1 })", self.src)

    def test_publishes_rules_params(self):
        self.assertIn('Spring.SetGameRulesParam("victory_winner"', self.src)
        self.assertIn('Spring.SetGameRulesParam("victory_reason"', self.src)

    def test_publishes_the_gg_status_for_the_probe(self):
        self.assertIn("GG.MedievalVictory = GG.MedievalVictory or {}", self.src)
        self.assertIn("status = { winner = winner, reason = reason }", self.src)

    def test_gg_api_surface(self):
        for name in GADGET_API:
            self.assertIn(f"function GG.MedievalVictory.{name}(", self.src)

    def test_regicide_spawns_missing_kings(self):
        self.assertIn("Spring.CreateUnit(kingDef.id", self.src)
        self.assertIn("victory.REGICIDE_KING_DEF", self.src)

    def test_surrender_command_channel(self):
        self.assertIn("function gadget:RecvLuaMsg", self.src)
        self.assertIn("surrender", self.src)

    def test_fifteen_frame_cadence(self):
        self.assertIn("frame % CADENCE_FRAMES ~= 0", self.src)

    def test_observes_gameover_without_retriggering(self):
        self.assertIn("function gadget:GameOver(winningAllyTeams)", self.src)

    def test_module_calls_are_all_exported(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        used = set(re.findall(r"\bvictory\.([A-Za-z_][A-Za-z0-9_]*)", self.src))
        self.assertTrue(used)
        for name in sorted(used):
            self.assertNotEqual(
                lua.eval("type")(module[name]),
                "nil",
                f"gadget uses victory.{name}, which the module does not export",
            )


# ---------------------------------------------------------------------------
# 8. Probe contract
# ---------------------------------------------------------------------------


class TestVictoryProbeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PROBE_PATH.read_text(encoding="utf-8")
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.startscript = STARTSCRIPT_PATH.read_text(encoding="utf-8")

    def test_gated_on_medievalvictory(self):
        self.assertIn("medievalvictory", self.src)

    def test_layer_is_last(self):
        self.assertIn("layer = 1000,", self.src)

    def test_verdict_keys(self):
        for key in ("baseline", "tc", "conquest", "regicide", "surrender", "gameover"):
            self.assertIn(f'verdict("{key}"', self.src, key)

    def test_tc_verdict_names_winner_zero(self):
        self.assertIn('winner=%s reason=%s', self.src)
        self.assertIn("winner == ALLY0", self.src)

    def test_probe_complete_line(self):
        self.assertIn('echo("probe-complete PASS', self.src)

    def test_stage_frames(self):
        for frame in ("SPAWN_FRAME = 20", "BASELINE_FRAME = 40", "DESTROY_FRAME = 60",
                      "VERDICT_FRAME = 90", "COMPLETE_FRAME = 120"):
            self.assertIn(frame, self.src, frame)

    def test_destroys_the_second_town_center(self):
        self.assertIn("Spring.DestroyUnit(tc1, false, true)", self.src)

    def test_runner_greps_the_same_keys(self):
        for key in ("baseline", "tc", "conquest", "regicide", "surrender", "gameover", "probe-complete"):
            self.assertIn(f'"{key}"', self.runner, key)

    def test_startscript_sets_the_probe_options(self):
        self.assertIn("medievalvictory=1;", self.startscript)
        self.assertIn("victorymode=tc_destruction;", self.startscript)
        self.assertIn("forcestart", self.startscript)


# ---------------------------------------------------------------------------
# 9. Modoption
# ---------------------------------------------------------------------------


class TestModoptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(MODOPTIONS_PATH.read_text(encoding="utf-8"))
        cls.options = {}
        for i in range(1, len(table) + 1):
            entry = table[i]
            cls.options[entry["key"]] = entry

    def test_victorymode_list(self):
        option = self.options["victorymode"]
        self.assertEqual(option["type"], "list")
        self.assertEqual(option["def"], DEFAULT_MODE)
        items = [option["items"][i]["key"] for i in range(1, len(option["items"]) + 1)]
        self.assertEqual(items, list(WIN_MODES))

    def test_medievalvictory_bool(self):
        option = self.options["medievalvictory"]
        self.assertEqual(option["type"], "bool")
        self.assertFalse(option["def"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
