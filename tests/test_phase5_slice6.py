"""Phase-5 Slice 6 tests: Full Skirmish Match Integration & Victory Probe.

Layers under test:

1. Pure module — `scripts/medieval_victory.lua`, a dependency-free, engine-free
   policy module. Every test boots its OWN fresh Lua runtime so one case cannot
   leak mutated module tables into another.
2. Win-projection integration — `evaluate` fed by synthetic Slice-6 match
   timelines (settlement start -> economy flow -> engagement -> TC destruction
   -> terminal victory), asserting the winner appears only at the terminal step.
3. `classifyDef` coverage across the full `units/*.lua` roster, including the
   Slice-1 king, the Slice-5 spearman and the Slice-3 market.
4. Mode-transition matrix — conquest / tc_destruction / regicide / surrender,
   each mode's terminal transition and the discriminating liminal state.
5. Probe verdict strings — regex validation of the `PHASE5 INTEGRATION` verdict
   line format and the six required verdict keys.
6. Gadget contract — `gadget_phase5_slice6_integration_probe.lua` is a layer-10
   synced observer gated on `medievalvictory=1` + `skirmishai=1`, spawns two
   settlements, observes GameOver, and never owns the single UnitPreDamaged hook.
7. Probe wiring — runner and startscript.

"""
import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_victory.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase5_slice6_integration_probe.lua"
RUNNER_PATH = ROOT / "tools" / "launch" / "run_phase5_slice6_probe.py"
STARTSCRIPT_PATH = ROOT / "tools" / "launch" / "startscript_slice6b.txt"
UNITS_DIR = ROOT / "units"

VERDICT_KEYS = (
    "settlement-start",
    "economy-flow",
    "military-engagement",
    "tc-destroyed",
    "victory-gameover",
    "probe-complete",
)

# The verdict line shape: "PHASE5 INTEGRATION <key> <PASS|FAIL> [detail]".
VERDICT_RE = re.compile(r"PHASE5 INTEGRATION ([\w-]+) (PASS|FAIL)")

# Full units/*.lua roster -> classification (source of truth is
# scripts/medieval_victory.lua classifyDef).
CLASSIFIED = {
    "medieval_town_center": "town_center",
    "medieval_king": "king",
    # military roster (recruitment UPKEEP > 0 plus the Slice-5 spearman)
    "medieval_infantry": "military",
    "medieval_archer": "military",
    "medieval_cavalry": "military",
    "medieval_catapult": "military",
    "medieval_men_at_arms": "military",
    "medieval_crossbow": "military",
    "medieval_knight": "military",
    "medieval_spearman": "military",
    # civilians
    "medieval_villager": "civilian",
    "medieval_cart": "civilian",
    # buildings
    "medieval_house": "building",
    "medieval_granary": "building",
    "medieval_lumber_camp": "building",
    "medieval_barracks": "building",
    "medieval_stables": "building",
    "medieval_blacksmith": "building",
    "medieval_fletcher": "building",
    "medieval_wall": "building",
    "medieval_tower": "building",
    "medieval_market": "building",
}


def _lua_to_py(lua, value):
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


# ---------------------------------------------------------------------------
# 1. Win-projection integration: synthetic Slice-6 match timelines
# ---------------------------------------------------------------------------

class TestWinProjectionIntegration(VictoryBase):
    def test_tc_destruction_timeline(self):
        # Opening: two settlements, both alive.
        opening = {0: {"tcs": 1, "units": 5, "kings": 1}, 1: {"tcs": 1, "units": 5, "kings": 1}}
        self.assertIsNone(self._evaluate(opening, "tc_destruction")["winnerAllyTeam"])

        # Economy/engagement: both sides still field TCs -> no winner.
        mid = {0: {"tcs": 1, "units": 6, "kings": 1}, 1: {"tcs": 1, "units": 8, "kings": 1}}
        self.assertIsNone(self._evaluate(mid, "tc_destruction")["winnerAllyTeam"])

        # Team 0's TC falls but its army survives; tc_destruction ignores units.
        fallen = {0: {"tcs": 0, "units": 3, "kings": 1}, 1: {"tcs": 1, "units": 7, "kings": 1}}
        verdict = self._evaluate(fallen, "tc_destruction")
        self.assertEqual(verdict["winnerAllyTeam"], 1)
        self.assertEqual(verdict["reason"], "tc_destruction")
        self.assertEqual(verdict["losers"], [0])

    def test_conquest_timeline_requires_seat_and_army_gone(self):
        # Loses the seat but keeps the army: no winner under conquest yet.
        seatless = {0: {"tcs": 0, "units": 3}, 1: {"tcs": 1, "units": 7}}
        self.assertIsNone(self._evaluate(seatless, "conquest")["winnerAllyTeam"])

        # The last units die off -> team 0 gone, team 1 wins.
        wiped = {0: {"tcs": 0, "units": 0}, 1: {"tcs": 1, "units": 7}}
        verdict = self._evaluate(wiped, "conquest")
        self.assertEqual(verdict["winnerAllyTeam"], 1)
        self.assertEqual(verdict["reason"], "conquest")

    def test_timeline_stays_open_until_the_terminal_step(self):
        timeline = [
            {0: {"tcs": 1, "units": 5}, 1: {"tcs": 1, "units": 5}},
            {0: {"tcs": 1, "units": 5}, 1: {"tcs": 1, "units": 9}},
            {0: {"tcs": 1, "units": 4}, 1: {"tcs": 1, "units": 11}},
        ]
        for state in timeline:
            self.assertIsNone(self._evaluate(state, "tc_destruction")["winnerAllyTeam"])
        terminal = self._evaluate({0: {"tcs": 0, "units": 4}, 1: {"tcs": 1, "units": 11}}, "tc_destruction")
        self.assertEqual(terminal["winnerAllyTeam"], 1)


# ---------------------------------------------------------------------------
# 2. classifyDef coverage across the full roster
# ---------------------------------------------------------------------------

class TestClassifyDefRoster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        cls.roster = sorted(p.stem for p in UNITS_DIR.glob("*.lua"))

    def test_every_roster_def_is_classified(self):
        for name in self.roster:
            got = self.m.classifyDef(name)
            self.assertNotEqual(got, "other", name)
            self.assertIn(got, ("town_center", "king", "military", "civilian", "building"), name)

    def test_full_roster_class_map(self):
        for name, expected in CLASSIFIED.items():
            self.assertEqual(self.m.classifyDef(name), expected, name)

    def test_spotlight_defs(self):
        # The three defs the spec calls out explicitly.
        self.assertEqual(self.m.classifyDef("medieval_spearman"), "military")
        self.assertEqual(self.m.classifyDef("medieval_king"), "king")
        self.assertEqual(self.m.classifyDef("medieval_market"), "building")

    def test_unknown_and_non_string_inputs_stay_other(self):
        self.assertEqual(self.m.classifyDef("armcom"), "other")
        self.assertEqual(self.m.classifyDef(""), "other")
        self.assertEqual(self.m.classifyDef(None), "other")
        self.assertEqual(self.m.classifyDef(7), "other")
        self.assertEqual(self.m.classifyDef({}), "other")


# ---------------------------------------------------------------------------
# 3. Mode transition matrix
# ---------------------------------------------------------------------------

class TestModeTransitionMatrix(VictoryBase):
    def test_liminal_state_reads_differently_per_mode(self):
        # Team 0: no TC, a surviving army, a surviving king, no surrender flag.
        # Each mode reads this liminal state differently.
        base = {0: {"tcs": 0, "units": 4, "kings": 1, "surrendered": False},
                1: {"tcs": 1, "units": 6, "kings": 1, "surrendered": False}}
        cases = [
            # (mode, expected winner, expected reason)
            ("conquest",       None, None),            # army survives -> not dead
            ("tc_destruction", 1,    "tc_destruction"),  # no TC -> dead
            ("regicide",       None, None),            # king alive -> not dead
            ("surrender",      None, None),            # no flag -> not dead
        ]
        for mode, winner, reason in cases:
            verdict = self._evaluate(base, mode)
            self.assertEqual(verdict["winnerAllyTeam"], winner, mode)
            self.assertEqual(verdict["reason"], reason, mode)

    def test_every_mode_has_a_terminal_transition(self):
        transitions = [
            ("conquest",       {0: {"tcs": 0, "units": 0}, 1: {"tcs": 1, "units": 1}}, 1, "conquest"),
            ("tc_destruction", {0: {"tcs": 0, "units": 9}, 1: {"tcs": 1, "units": 1}}, 1, "tc_destruction"),
            ("regicide",       {0: {"tcs": 1, "kings": 0, "units": 3}, 1: {"tcs": 1, "kings": 1, "units": 1}}, 1, "regicide"),
            ("surrender",      {0: {"tcs": 1, "units": 1, "surrendered": True}, 1: {"tcs": 1, "units": 1}}, 1, "surrender"),
        ]
        for mode, teams, winner, reason in transitions:
            verdict = self._evaluate(teams, mode)
            self.assertEqual(verdict["winnerAllyTeam"], winner, mode)
            self.assertEqual(verdict["reason"], reason, mode)

    def test_surrender_flag_is_ignored_under_non_surrender_modes(self):
        # A surrendered team is not eliminated by any other mode's condition.
        state = {0: {"tcs": 1, "units": 1, "surrendered": True}, 1: {"tcs": 1, "units": 1}}
        for mode in ("conquest", "tc_destruction", "regicide"):
            verdict = self._evaluate(state, mode)
            self.assertIsNone(verdict["winnerAllyTeam"], mode)


# ---------------------------------------------------------------------------
# 4. Probe verdict string parsing & regex validation
# ---------------------------------------------------------------------------

class TestProbeVerdictStrings(unittest.TestCase):
    REQUIRED_LINES = [
        "PHASE5 INTEGRATION settlement-start PASS",
        "PHASE5 INTEGRATION economy-flow PASS",
        "PHASE5 INTEGRATION military-engagement PASS",
        "PHASE5 INTEGRATION tc-destroyed PASS",
        "PHASE5 INTEGRATION victory-gameover PASS winner=1 reason=tc_destruction",
        "PHASE5 INTEGRATION probe-complete PASS",
    ]

    def test_every_required_verdict_matches_the_regex(self):
        for line in self.REQUIRED_LINES:
            m = VERDICT_RE.search(line)
            self.assertIsNotNone(m, line)
            self.assertEqual(m.group(2), "PASS", line)

    def test_regex_captures_the_verdict_key(self):
        for key in VERDICT_KEYS:
            line = f"PHASE5 INTEGRATION {key} PASS"
            m = VERDICT_RE.search(line)
            self.assertIsNotNone(m, key)
            self.assertEqual(m.group(1), key)

    def test_fail_is_also_parseable(self):
        for key in VERDICT_KEYS:
            m = VERDICT_RE.search(f"PHASE5 INTEGRATION {key} FAIL")
            self.assertIsNotNone(m, key)
            self.assertEqual(m.group(2), "FAIL", key)

    def test_victory_gameover_carries_winner_and_reason(self):
        m = VERDICT_RE.search("PHASE5 INTEGRATION victory-gameover PASS winner=1 reason=tc_destruction f=270")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "victory-gameover")
        # The trailing detail encodes the terminal verdict tokens.
        line = "PHASE5 INTEGRATION victory-gameover PASS winner=1 reason=tc_destruction f=270"
        self.assertIn("winner=1", line)
        self.assertIn("reason=tc_destruction", line)

    def test_probe_source_contains_all_verdict_keys_and_prefix(self):
        src = GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("PHASE5 INTEGRATION ", src)
        for key in VERDICT_KEYS:
            self.assertIn(f'"{key}"', src, key)


# ---------------------------------------------------------------------------
# 5. Gadget contract
# ---------------------------------------------------------------------------

class TestIntegrationProbeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_synced_only(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.src)

    def test_layer_is_ten(self):
        self.assertIn("layer = 10,", self.src)

    def test_gated_on_both_modoptions(self):
        self.assertIn("medievalvictory", self.src)
        self.assertIn("skirmishai", self.src)

    def test_gate_requires_both(self):
        # The enable expression conjoins both flags.
        self.assertIn('modOptionOn("medievalvictory") and modOptionOn("skirmishai")', self.src)

    def test_includes_the_pure_victory_module(self):
        self.assertIn('VFS.Include("scripts/medieval_victory.lua")', self.src)

    def test_spawns_both_settlements(self):
        for token in ("medieval_town_center", "medieval_villager", "medieval_barracks", "medieval_infantry"):
            self.assertIn(token, self.src)

    def test_spawns_at_the_documented_positions(self):
        self.assertIn("1800", self.src)
        self.assertIn("4200", self.src)

    def test_observes_gameover(self):
        self.assertIn("function gadget:GameOver", self.src)

    def test_falls_back_to_synthetic_policy(self):
        self.assertIn("victory.evaluate", self.src)
        self.assertIn("Spring.DestroyUnit", self.src)

    def test_does_not_own_the_unitpreDamaged_hook(self):
        self.assertNotIn("function gadget:UnitPreDamaged", self.src)

    def test_emits_the_required_verdict_keys(self):
        for key in VERDICT_KEYS:
            self.assertIn(f'"{key}"', self.src, key)


# ---------------------------------------------------------------------------
# 6. Probe wiring: runner + startscript
# ---------------------------------------------------------------------------

class TestSlice6ProbeWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.startscript = STARTSCRIPT_PATH.read_text(encoding="utf-8")

    def test_runner_watches_every_verdict(self):
        for key in VERDICT_KEYS:
            self.assertIn(f'"{key}"', self.runner, key)

    def test_runner_greps_the_integration_prefix(self):
        self.assertIn("PHASE5 INTEGRATION", self.runner)

    def test_runner_uses_the_slice6b_startscript(self):
        self.assertIn("startscript_slice6b.txt", self.runner)

    def test_startscript_enables_victory_and_skirmish_ai(self):
        self.assertIn("medievalvictory=1;", self.startscript)
        self.assertIn("skirmishai=1;", self.startscript)

    def test_startscript_sets_the_terminal_mode(self):
        self.assertIn("victorymode=tc_destruction;", self.startscript)

    def test_startscript_forcestarts_and_terminal_quits(self):
        self.assertIn("forcestart", self.startscript)
        self.assertIsNotNone(re.search(r"quitforce", self.startscript))


if __name__ == "__main__":
    unittest.main()