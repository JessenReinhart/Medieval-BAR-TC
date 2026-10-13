"""Phase-5 Slice 2 tests: the Medieval Economy HUD.

Layers under test:

1. Formatter — `scripts/medieval_hud.lua`, a dependency-free, engine-free module.
   Every test boots its OWN fresh Lua runtime so one case cannot leak mutated
   module tables into another.
2. Purity — the formatter must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present, because the widget `VFS.Include`s it and the tests load it
   directly.
3. Publisher contract — `luarules/gadgets/gadget_medieval_hud.lua` must publish
   exactly the team rules-param keys the formatter names, on a 30-frame cadence,
   in a synced layer.
4. Publisher behaviour — the gadget source is executed against mocked
   Spring/GG/VFS stubs and driven through Initialize/GameFrame.
5. Widget contract + render — `luaui/widgets/gui_medieval_hud.lua` is gated on
   the `medievalhud` modoption, reads rules params in DrawScreen, and draws with
   gl.Color/gl.Rect/gl.Text only.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_hud.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_hud.lua"
WIDGET_PATH = ROOT / "luaui" / "widgets" / "gui_medieval_hud.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"

# Rules-param keys, mirrored from scripts/medieval_hud.lua PARAM_KEYS.
PARAM_KEYS = {
    "food": "food",
    "wood": "wood",
    "stone": "stone",
    "iron": "iron",
    "pop": "pop",
    "popcap": "popcap",
    "idle": "idle_villagers",
    "starvation": "starvation",
    "upkeep": "food_upkeep",
    "victoryWinner": "victory_winner",
    "victoryReason": "victory_reason",
}

# Gadget local name -> formatter PARAM_KEYS name, for the contract regex.
GADGET_KEY_LOCALS = {
    "FOOD": "food",
    "WOOD": "wood",
    "STONE": "stone",
    "IRON": "iron",
    "POP": "pop",
    "POPCAP": "popcap",
    "IDLE": "idle_villagers",
    "STARVATION": "starvation",
    "UPKEEP": "food_upkeep",
    "VICTORY_WINNER": "victory_winner",
    "VICTORY_REASON": "victory_reason",
}

REQUIRED_FUNCTIONS = (
    "formatStock",
    "stockLine",
    "popLine",
    "idleLine",
    "starvationAlert",
    "victoryBanner",
)

CADENCE_FRAMES = 30


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


class Slice2Base(unittest.TestCase):
    """Fresh formatter module per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _stock(self, **resources):
        return self.lua.table(**resources)

    def _alert(self, food, upkeep):
        return _lua_to_py(self.lua, self.m.starvationAlert(food, upkeep))

    def _cells(self, **resources):
        return _lua_to_py(self.lua, self.m.stockCells(self._stock(**resources)))


# ---------------------------------------------------------------------------
# 1. formatStock
# ---------------------------------------------------------------------------


class TestSlice2FormatStock(Slice2Base):
    """formatStock(n): 0, 850, 1.2k, 15k — plus negatives, decimals, millions."""

    def test_zero(self):
        self.assertEqual(self.m.formatStock(0), "0")

    def test_plain_values_below_a_thousand(self):
        for value, expected in ((1, "1"), (42, "42"), (850, "850"), (999, "999")):
            with self.subTest(value=value):
                self.assertEqual(self.m.formatStock(value), expected)

    def test_decimal_rounding_below_a_thousand(self):
        self.assertEqual(self.m.formatStock(850.4), "850")
        self.assertEqual(self.m.formatStock(850.6), "851")
        self.assertEqual(self.m.formatStock(0.4), "0")

    def test_thousands_use_one_decimal_k(self):
        self.assertEqual(self.m.formatStock(1000), "1k")
        self.assertEqual(self.m.formatStock(1200), "1.2k")
        self.assertEqual(self.m.formatStock(1240), "1.2k")
        self.assertEqual(self.m.formatStock(1260), "1.3k")
        self.assertEqual(self.m.formatStock(15000), "15k")
        self.assertEqual(self.m.formatStock(99400), "99.4k")
        self.assertEqual(self.m.formatStock(999000), "999k")

    def test_rounding_carries_into_the_next_unit(self):
        # 999.6 rounds to 1000, which is a kilo, not "1000".
        self.assertEqual(self.m.formatStock(999.6), "1k")

    def test_millions(self):
        self.assertEqual(self.m.formatStock(1000000), "1M")
        self.assertEqual(self.m.formatStock(1200000), "1.2M")
        self.assertEqual(self.m.formatStock(15000000), "15M")

    def test_negatives_keep_the_sign(self):
        self.assertEqual(self.m.formatStock(-1), "-1")
        self.assertEqual(self.m.formatStock(-850), "-850")
        self.assertEqual(self.m.formatStock(-1200), "-1.2k")
        self.assertEqual(self.m.formatStock(-15000), "-15k")
        self.assertEqual(self.m.formatStock(-1200000), "-1.2M")

    def test_negative_fractions_collapse_to_zero(self):
        self.assertEqual(self.m.formatStock(-0.4), "0")

    def test_unreadable_input_formats_as_zero(self):
        for value in (None, "abc", {}, self.lua.eval("nil")):
            with self.subTest(value=repr(value)):
                self.assertEqual(self.m.formatStock(value), "0")

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(self.m.formatStock("1200"), "1.2k")
        self.assertEqual(self.m.formatStock("850"), "850")

    def test_infinities_and_nan_are_not_numbers(self):
        for expr in ("1/0", "-1/0", "0/0"):
            with self.subTest(expr=expr):
                self.assertEqual(self.m.formatStock(self.lua.eval(expr)), "0")

    def test_returns_a_string(self):
        self.assertEqual(self.lua.eval("type")(self.m.formatStock(1200)), "string")


# ---------------------------------------------------------------------------
# 2. stockLine / popLine / idleLine
# ---------------------------------------------------------------------------


class TestSlice2StockLine(Slice2Base):
    """stockLine(resources): the four-cell text layout."""

    def test_full_stock_layout(self):
        self.assertEqual(
            self.m.stockLine(self._stock(food=850, wood=500, stone=100, iron=50)),
            "Food: 850  Wood: 500  Stone: 100  Iron: 50",
        )

    def test_canonical_order_is_food_wood_stone_iron(self):
        line = self.m.stockLine(self._stock(iron=4, stone=3, wood=2, food=1))
        self.assertEqual(line, "Food: 1  Wood: 2  Stone: 3  Iron: 4")

    def test_missing_resources_read_as_zero(self):
        self.assertEqual(
            self.m.stockLine(self._stock(food=1200)),
            "Food: 1.2k  Wood: 0  Stone: 0  Iron: 0",
        )

    def test_nil_and_non_table_inputs_are_all_zero(self):
        zero_line = "Food: 0  Wood: 0  Stone: 0  Iron: 0"
        self.assertEqual(self.m.stockLine(None), zero_line)
        self.assertEqual(self.m.stockLine(7), zero_line)

    def test_large_and_negative_values_render(self):
        line = self.m.stockLine(self._stock(food=1200000, wood=-1500, stone=0, iron=999))
        self.assertEqual(line, "Food: 1.2M  Wood: -1.5k  Stone: 0  Iron: 999")

    def test_cells_expose_key_label_text_value(self):
        cells = self._cells(food=1200, wood=0, stone=0, iron=0)
        self.assertEqual([c["key"] for c in cells], ["food", "wood", "stone", "iron"])
        self.assertEqual(cells[0]["label"], "Food")
        self.assertEqual(cells[0]["text"], "1.2k")
        self.assertEqual(cells[0]["value"], 1200)
        self.assertEqual(cells[1]["text"], "0")


class TestSlice2PopAndIdleLines(Slice2Base):
    """popLine(pop, cap) / idleLine(n)."""

    def test_pop_line(self):
        self.assertEqual(self.m.popLine(12, 40), "Pop: 12/40")

    def test_pop_line_floors_fractions(self):
        self.assertEqual(self.m.popLine(12.9, 40.2), "Pop: 12/40")

    def test_pop_line_zero_and_missing(self):
        self.assertEqual(self.m.popLine(0, 0), "Pop: 0/0")
        self.assertEqual(self.m.popLine(None, None), "Pop: 0/0")

    def test_pop_line_clamps_negatives(self):
        self.assertEqual(self.m.popLine(-3, 10), "Pop: 0/10")
        self.assertEqual(self.m.popLine(3, -10), "Pop: 3/0")

    def test_pop_line_accepts_numeric_strings(self):
        self.assertEqual(self.m.popLine("7", "20"), "Pop: 7/20")

    def test_idle_line(self):
        self.assertEqual(self.m.idleLine(3), "Idle: 3")

    def test_idle_line_floors_and_clamps(self):
        self.assertEqual(self.m.idleLine(4.7), "Idle: 4")
        self.assertEqual(self.m.idleLine(-2), "Idle: 0")

    def test_idle_line_missing(self):
        self.assertEqual(self.m.idleLine(None), "Idle: 0")


# ---------------------------------------------------------------------------
# 3. starvationAlert
# ---------------------------------------------------------------------------


class TestSlice2StarvationAlert(Slice2Base):
    """starvationAlert(food, upkeepPerTick) -> { level, text }."""

    def test_no_upkeep_is_always_ok(self):
        for food in (0, 5, 850, 1_000_000):
            with self.subTest(food=food):
                alert = self._alert(food, 0)
                self.assertEqual(alert["level"], "ok")
                self.assertEqual(alert["text"], f"Food: {self.m.formatStock(food)}")

    def test_missing_upkeep_is_ok(self):
        self.assertEqual(self._alert(0, None)["level"], "ok")

    def test_plenty_of_supply_is_ok(self):
        self.assertEqual(self._alert(850, 1)["level"], "ok")
        self.assertEqual(self._alert(100, 10)["level"], "ok")

    def test_ok_boundary_is_ten_ticks(self):
        self.assertEqual(self._alert(50, 5)["level"], "ok")
        self.assertEqual(self._alert(49, 5)["level"], "low")

    def test_low_boundary_is_three_ticks(self):
        self.assertEqual(self._alert(15, 5)["level"], "low")
        self.assertEqual(self._alert(14, 5)["level"], "critical")

    def test_empty_stock_is_critical(self):
        alert = self._alert(0, 5)
        self.assertEqual(alert["level"], "critical")
        self.assertEqual(alert["text"], "STARVING: 0")

    def test_negative_stock_clamps_to_zero(self):
        alert = self._alert(-50, 5)
        self.assertEqual(alert["level"], "critical")
        self.assertEqual(alert["text"], "STARVING: 0")

    def test_unreadable_stock_is_critical(self):
        self.assertEqual(self._alert(None, 5)["level"], "critical")

    def test_text_prefix_tracks_the_level(self):
        self.assertTrue(self._alert(850, 1)["text"].startswith("Food: "))
        self.assertTrue(self._alert(30, 5)["text"].startswith("LOW FOOD: "))
        self.assertTrue(self._alert(5, 5)["text"].startswith("STARVING: "))

    def test_text_carries_the_formatted_stock(self):
        self.assertEqual(self._alert(1200, 10)["text"], "Food: 1.2k")
        self.assertEqual(self._alert(30, 5)["text"], "LOW FOOD: 30")

    def test_levels_are_restricted_to_the_three_names(self):
        for food, upkeep in ((0, 0), (0, 5), (20, 5), (500, 5)):
            with self.subTest(food=food, upkeep=upkeep):
                self.assertIn(self._alert(food, upkeep)["level"], ("ok", "low", "critical"))

    def test_returns_a_table_with_exactly_level_and_text(self):
        alert = self._alert(100, 5)
        self.assertEqual(sorted(alert.keys()), ["level", "text"])


# ---------------------------------------------------------------------------
# 4. victoryBanner
# ---------------------------------------------------------------------------


class TestSlice2VictoryBanner(Slice2Base):
    """victoryBanner(winner, myAllyTeam, reason)."""

    def test_own_team_wins(self):
        self.assertEqual(self.m.victoryBanner(0, 0, "tc_destruction"), "VICTORY - Town Center destroyed")

    def test_other_team_wins_is_a_defeat(self):
        self.assertEqual(self.m.victoryBanner(1, 0, "tc_destruction"), "DEFEAT - Town Center destroyed")

    def test_winner_and_ally_team_are_compared_by_identity(self):
        self.assertEqual(self.m.victoryBanner(2, 2, "surrender"), "VICTORY - Surrender")
        self.assertEqual(self.m.victoryBanner(2, 3, "surrender"), "DEFEAT - Surrender")

    def test_reason_is_optional(self):
        self.assertEqual(self.m.victoryBanner(0, 0, None), "VICTORY")
        self.assertEqual(self.m.victoryBanner(1, 0, ""), "DEFEAT")

    def test_no_verdict_yet_returns_nil(self):
        self.assertIsNone(self.m.victoryBanner(None, 0, None))
        self.assertIsNone(self.m.victoryBanner(0, None, "conquest"))

    def test_known_reasons_are_pretty_printed(self):
        self.assertEqual(self.m.victoryBanner(0, 0, "conquest"), "VICTORY - Conquest")
        self.assertEqual(self.m.victoryBanner(0, 0, "regicide"), "VICTORY - King slain")
        self.assertEqual(self.m.victoryBanner(0, 0, "surrender"), "VICTORY - Surrender")

    def test_unknown_reason_is_passed_through(self):
        self.assertEqual(self.m.victoryBanner(0, 0, "custom reason"), "VICTORY - custom reason")

    def test_reason_is_trimmed(self):
        self.assertEqual(self.m.victoryBanner(0, 0, "  regicide  "), "VICTORY - King slain")
        self.assertEqual(self.m.victoryBanner(0, 0, "   "), "VICTORY")

    def test_non_string_reason_is_ignored(self):
        self.assertEqual(self.m.victoryBanner(0, 0, 42), "VICTORY")

    def test_banner_always_starts_with_the_verdict_word(self):
        for winner, mine in ((0, 0), (1, 0)):
            with self.subTest(winner=winner):
                banner = self.m.victoryBanner(winner, mine, "conquest")
                self.assertTrue(banner.startswith("VICTORY") or banner.startswith("DEFEAT"))


# ---------------------------------------------------------------------------
# 5. Formatter purity
# ---------------------------------------------------------------------------


class TestSlice2Purity(Slice2Base):
    """No engine, no VFS, no sibling-module include."""

    def setUp(self):
        super().setUp()
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_no_vfs_include(self):
        self.assertNotIn("VFS.Include(", self.source)

    def test_no_spring_calls(self):
        self.assertEqual(re.findall(r"Spring\.[A-Za-z_]+\(|Spring\.[A-Za-z_]+:", self.source), [])

    def test_no_require(self):
        self.assertNotIn("require(", self.source)

    def test_no_gg_api_calls(self):
        self.assertEqual(re.findall(r"GG\.[A-Za-z_]+\.[A-Za-z_]+\(", self.source), [])

    def test_no_gl_calls(self):
        self.assertEqual(re.findall(r"\bgl\.[A-Za-z_]+", self.source), [])

    def test_loads_without_any_globals(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("Spring"))
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(module.formatStock(15000), "15k")

    def test_required_functions_are_exported(self):
        for name in REQUIRED_FUNCTIONS:
            with self.subTest(name=name):
                self.assertEqual(self.lua.eval("type")(self.m[name]), "function")

    def test_param_keys_match_the_documented_contract(self):
        for name, value in PARAM_KEYS.items():
            with self.subTest(name=name):
                self.assertEqual(self.m.PARAM_KEYS[name], value)

    def test_resource_order_is_the_four_canonical_resources(self):
        self.assertEqual(
            [self.m.RESOURCE_ORDER[i] for i in range(1, 5)],
            ["food", "wood", "stone", "iron"],
        )

    def test_thresholds(self):
        self.assertEqual(self.m.LOW_TICKS, 10)
        self.assertEqual(self.m.CRITICAL_TICKS, 3)


# ---------------------------------------------------------------------------
# 6. Publisher contract (source-level)
# ---------------------------------------------------------------------------


class TestSlice2GadgetContract(unittest.TestCase):
    """The synced publisher must emit exactly the keys the widget reads."""

    def setUp(self):
        self.source = GADGET_PATH.read_text(encoding="utf-8")

    def test_synced_guard(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.source)

    def test_layer_is_synced(self):
        layer = re.search(r"layer\s*=\s*(\d+)", self.source)
        self.assertIsNotNone(layer)
        self.assertIn(int(layer.group(1)), (5, 6))

    def test_enabled_by_default(self):
        self.assertRegex(self.source, r"enabled\s*=\s*true")

    def test_includes_the_shared_formatter(self):
        self.assertIn('VFS.Include("scripts/medieval_hud.lua")', self.source)

    def test_cadence_is_thirty_frames(self):
        match = re.search(r"local\s+CADENCE_FRAMES\s*=\s*(\d+)", self.source)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), CADENCE_FRAMES)

    def test_uses_set_team_rules_param(self):
        self.assertIn("Spring.SetTeamRulesParam(teamID, key, value)", self.source)

    def test_declared_param_key_literals(self):
        declared = dict(re.findall(r'local\s+KEY_([A-Z_]+)\s*=\s*"([a-z_]+)"', self.source))
        self.assertEqual(declared, GADGET_KEY_LOCALS)

    def test_declared_keys_match_the_formatter_contract(self):
        declared = dict(re.findall(r'local\s+KEY_([A-Z_]+)\s*=\s*"([a-z_]+)"', self.source))
        self.assertEqual(
            {declared[local] for local in GADGET_KEY_LOCALS},
            set(PARAM_KEYS.values()),
        )

    def test_reads_each_documented_source(self):
        for api in (
            "GG.MedievalEconomy",
            "GG.MedievalHousing",
            "GG.MedievalGather",
            "GG.MedievalVictory",
        ):
            with self.subTest(api=api):
                self.assertIn(api, self.source)

    def test_victory_passthrough(self):
        self.assertIn("KEY_VICTORY_WINNER", self.source)
        self.assertIn("KEY_VICTORY_REASON", self.source)


# ---------------------------------------------------------------------------
# 7. Publisher behaviour (mocked synced engine)
# ---------------------------------------------------------------------------

GADGET_HARNESS = r"""
TEAM_RULES = {}       -- TEAM_RULES[teamID][key] = value
GAME_RULES = {}
TEAM_LIST = { 0, 1 }
TEAM_UNITS = { [0] = { 1, 2, 3 }, [1] = {} }
UNIT_DEFS = {
  [10] = { name = "medieval_villager" },
  [11] = { name = "medieval_infantry" },
}
JOBS = { [1] = { state = "harvest" } }   -- unit 2 has no job -> idle
GG = {}

function ResetRules()
  TEAM_RULES = {}
  GAME_RULES = {}
end

function PublishAt(frame)
  gadget:GameFrame(frame)
end

Spring = {
  GetTeamList = function() return TEAM_LIST end,
  SetTeamRulesParam = function(teamID, key, value)
    TEAM_RULES[teamID] = TEAM_RULES[teamID] or {}
    TEAM_RULES[teamID][key] = value
  end,
  SetGameRulesParam = function(key, value) GAME_RULES[key] = value end,
  GetGameRulesParam = function(key) return GAME_RULES[key] end,
  GetTeamUnits = function(teamID) return TEAM_UNITS[teamID] or {} end,
  GetUnitDefID = function(unitID)
    if unitID == 1 or unitID == 2 then return 10 end
    return 11
  end,
}

UnitDefs = UNIT_DEFS
UnitDefNames = {}

gadgetHandler = {
  IsSyncedCode = function() return true end,
}

GG.MedievalEconomy = {
  GetStockpiles = function(teamID)
    if teamID == 0 then return { food = 850, wood = 500, stone = 100, iron = 50 } end
    return { food = 0, wood = 0, stone = 0, iron = 0 }
  end,
}
GG.MedievalHousing = {
  GetPopulation = function(teamID) return teamID == 0 and 12 or 1 end,
  GetCap = function(teamID) return teamID == 0 and 40 or 10 end,
}
GG.MedievalGather = {
  GetJob = function(unitID) return JOBS[unitID] end,
}
GG.MedievalRecruitment = {
  IsStarving = function(teamID) return teamID == 1 end,
  Upkeep = function(teamID) return teamID == 0 and 2 or 5 end,
}
"""


class TestSlice2GadgetBehaviour(unittest.TestCase):
    """Executes the real gadget source against mocked engine globals."""

    def _boot(self, with_victory=False):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        lua.globals().WITH_VICTORY = with_victory
        lua.execute(GADGET_HARNESS)
        lua.execute(r"""
        VFS = {
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }
        if WITH_VICTORY then
          GG.MedievalVictory = {
            GetWinner = function() return 1 end,
            GetReason = function() return "tc_destruction" end,
          }
        end
        gadget = {}
        assert(load(GADGET_SRC, "@gadget_medieval_hud.lua", "t", _G))()
        """)
        return lua

    def _rules(self, lua, team, key):
        return lua.execute(f"return TEAM_RULES[{team}] and TEAM_RULES[{team}][{key!r}]")

    def test_initialize_publishes_every_team(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        for team in (0, 1):
            self.assertIsNotNone(lua.execute(f"return TEAM_RULES[{team}]"))

    def test_stockpiles_are_published(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        self.assertEqual(self._rules(lua, 0, "food"), 850)
        self.assertEqual(self._rules(lua, 0, "wood"), 500)
        self.assertEqual(self._rules(lua, 0, "stone"), 100)
        self.assertEqual(self._rules(lua, 0, "iron"), 50)

    def test_population_is_published(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        self.assertEqual(self._rules(lua, 0, "pop"), 12)
        self.assertEqual(self._rules(lua, 0, "popcap"), 40)
        self.assertEqual(self._rules(lua, 1, "pop"), 1)
        self.assertEqual(self._rules(lua, 1, "popcap"), 10)

    def test_idle_villagers_count_only_jobless_villagers(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        # Units 1 and 2 are villagers; unit 1 holds a gather job, unit 3 is
        # infantry. Exactly one idle villager.
        self.assertEqual(self._rules(lua, 0, "idle_villagers"), 1)
        self.assertEqual(self._rules(lua, 1, "idle_villagers"), 0)

    def test_starvation_and_upkeep_are_published(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        self.assertEqual(self._rules(lua, 0, "starvation"), 0)
        self.assertEqual(self._rules(lua, 1, "starvation"), 1)
        self.assertEqual(self._rules(lua, 0, "food_upkeep"), 2)
        self.assertEqual(self._rules(lua, 1, "food_upkeep"), 5)

    def test_every_contract_key_is_published(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        published = lua.execute("local t = {} for k in pairs(TEAM_RULES[0]) do t[#t+1] = k end return t")
        names = {published[i] for i in range(1, len(published) + 1)}
        for key in PARAM_KEYS.values():
            if key in ("victory_winner", "victory_reason"):
                continue
            with self.subTest(key=key):
                self.assertIn(key, names)

    def test_game_frame_cadence_is_thirty(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        lua.execute("GG.MedievalEconomy.GetStockpiles = function() return { food = 7, wood = 0, stone = 0, iron = 0 } end")
        for frame in (1, 15, 29):
            lua.execute(f"gadget:GameFrame({frame})")
        self.assertEqual(self._rules(lua, 0, "food"), 850)
        lua.execute("gadget:GameFrame(30)")
        self.assertEqual(self._rules(lua, 0, "food"), 7)

    def test_game_frame_ignores_bad_frames(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        lua.execute("GG.MedievalEconomy.GetStockpiles = function() return { food = 7, wood = 0, stone = 0, iron = 0 } end")
        lua.execute("gadget:GameFrame(-1) gadget:GameFrame(nil) gadget:GameFrame('30')")
        self.assertEqual(self._rules(lua, 0, "food"), 850)

    def test_missing_sibling_apis_degrade_to_zero(self):
        lua = self._boot()
        lua.execute("GG = {}")
        lua.execute("gadget:Initialize()")
        self.assertEqual(self._rules(lua, 0, "food"), 0)
        self.assertEqual(self._rules(lua, 0, "pop"), 0)
        self.assertEqual(self._rules(lua, 0, "popcap"), 0)
        self.assertEqual(self._rules(lua, 0, "food_upkeep"), 0)

    def test_victory_params_published_when_available(self):
        lua = self._boot(with_victory=True)
        lua.execute("gadget:Initialize()")
        self.assertEqual(self._rules(lua, 0, "victory_winner"), 1)
        self.assertEqual(self._rules(lua, 0, "victory_reason"), "tc_destruction")
        self.assertEqual(lua.eval("GAME_RULES")["victory_winner"], 1)
        self.assertEqual(lua.eval("GAME_RULES")["victory_reason"], "tc_destruction")

    def test_victory_params_absent_without_the_victory_api(self):
        lua = self._boot()
        lua.execute("gadget:Initialize()")
        self.assertIsNone(self._rules(lua, 0, "victory_winner"))
        self.assertIsNone(lua.eval("GAME_RULES")["victory_winner"])


# ---------------------------------------------------------------------------
# 8. Widget contract + mocked render
# ---------------------------------------------------------------------------

WIDGET_HARNESS = r"""
WIDGET_SRC = io.open(ROOT_PATH .. "/luaui/widgets/gui_medieval_hud.lua", "r"):read("*a")
TEXT_CALLS = {}
COLOR_CALLS = {}
RECT_CALLS = {}
TEAM_PARAMS = {
  [0] = {
    food = 850, wood = 500, stone = 100, iron = 50,
    pop = 12, popcap = 40, idle_villagers = 3,
    starvation = 0, food_upkeep = 2,
  },
}
GAME_PARAMS = {}
TIMER = 0.0
LAST_ALPHA = 1
MODOPTIONS = { medievalhud = MODOPTION_VALUE }

Spring = {
  GetModOptions = function() return MODOPTIONS end,
  GetMyAllyTeamID = function() return 0 end,
  GetMyTeamID = function() return 0 end,
  GetViewGeometry = function() return 1600, 900 end,
  GetGameSeconds = function() return TIMER end,
  GetTeamRulesParam = function(teamID, key)
    local t = TEAM_PARAMS[teamID]
    return t and t[key] or nil
  end,
  GetGameRulesParam = function(key) return GAME_PARAMS[key] end,
}

gl = {
  Color = function(r, g, b, a)
    COLOR_CALLS[#COLOR_CALLS + 1] = { r, g, b, a }
    LAST_ALPHA = a
  end,
  Rect = function(x1, y1, x2, y2) RECT_CALLS[#RECT_CALLS + 1] = { x1, y1, x2, y2 } end,
  Text = function(text, x, y, size, opts)
    TEXT_CALLS[#TEXT_CALLS + 1] = { text, size, LAST_ALPHA }
  end,
}

VFS = {
  Include = function(path)
    local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
    local src = fh:read("*a")
    fh:close()
    return assert(load(src, "@" .. path, "t", _G))()
  end,
}

widget = {}
assert(load(WIDGET_SRC, "@gui_medieval_hud.lua", "t", _G))()

function DrawnTexts()
  local t = {}
  for i, call in ipairs(TEXT_CALLS) do t[i] = call[1] end
  return t
end

function Draw()
  TEXT_CALLS = {}
  COLOR_CALLS = {}
  RECT_CALLS = {}
  widget:DrawScreen()
end
"""


class TestSlice2Widget(unittest.TestCase):
    """Executes the real widget source against mocked Spring/gl globals."""

    def _boot(self, modoption=True):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        lua.globals().MODOPTION_VALUE = modoption
        lua.execute(WIDGET_HARNESS)
        return lua

    def test_getinfo_metadata(self):
        lua = self._boot()
        info = lua.eval("widget:GetInfo()")
        self.assertEqual(info["name"], "Medieval Economy HUD")
        self.assertEqual(info["license"], "GPL-v2")
        self.assertIn("HUD", info["desc"])

    def test_widget_disabled_by_modoption(self):
        lua = self._boot(modoption=False)
        self.assertIsNone(lua.eval("widget.DrawScreen"))

    def test_widget_enabled_when_option_unset(self):
        lua = self._boot(modoption=None)
        self.assertIsNotNone(lua.eval("widget.DrawScreen"))

    def test_draw_renders_the_four_stockpiles(self):
        lua = self._boot()
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        for expected in ("Food: 850", "Wood: 500", "Stone: 100", "Iron: 50"):
            with self.subTest(expected=expected):
                self.assertIn(expected, joined)

    def test_draw_renders_pop_and_idle_cells(self):
        lua = self._boot()
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        self.assertIn("Pop: 12/40", joined)
        self.assertIn("Idle: 3", joined)

    def test_draw_uses_gl_color_rect_and_text(self):
        lua = self._boot()
        lua.execute("Draw()")
        self.assertGreater(lua.eval("#RECT_CALLS"), 0)
        self.assertGreater(lua.eval("#COLOR_CALLS"), 0)
        self.assertGreater(lua.eval("#TEXT_CALLS"), 0)

    def test_no_victory_banner_before_a_verdict(self):
        lua = self._boot()
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        self.assertNotIn("VICTORY", joined)
        self.assertNotIn("DEFEAT", joined)

    def test_victory_banner_when_winner_matches(self):
        lua = self._boot()
        lua.execute("TEAM_PARAMS[0].victory_winner = 0 TEAM_PARAMS[0].victory_reason = 'conquest'")
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        self.assertIn("VICTORY - Conquest", joined)

    def test_defeat_banner_when_another_team_wins(self):
        lua = self._boot()
        lua.execute("TEAM_PARAMS[0].victory_winner = 1 TEAM_PARAMS[0].victory_reason = 'regicide'")
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        self.assertIn("DEFEAT - King slain", joined)

    def test_starvation_flashes_red_and_dimms(self):
        lua = self._boot()
        lua.execute("TEAM_PARAMS[0].starvation = 1 TEAM_PARAMS[0].food = 0")
        # Timer phase 0 -> floor(0*2) even -> lit; phase 0.6 -> floor(1.2) odd -> dim.
        lua.execute("TIMER = 0.0 Draw()")
        bright = lua.execute("return TEXT_CALLS")
        bright_alpha = max(bright[i][3] for i in range(1, len(bright) + 1))
        lua.execute("TIMER = 0.6 Draw()")
        dim = lua.execute("return TEXT_CALLS")
        dim_alpha = max(dim[i][3] for i in range(1, len(dim) + 1))
        self.assertEqual(bright_alpha, 1)
        self.assertLess(dim_alpha, bright_alpha)

    def test_starvation_alert_text_shows(self):
        lua = self._boot()
        lua.execute("TEAM_PARAMS[0].starvation = 1 TEAM_PARAMS[0].food = 0")
        lua.execute("Draw()")
        texts = lua.execute("return DrawnTexts()")
        joined = " | ".join(texts[i] for i in range(1, len(texts) + 1))
        self.assertIn("STARVING: 0", joined)

    def test_spectator_without_an_ally_team_draws_nothing(self):
        lua = self._boot()
        lua.execute("Spring.GetMyAllyTeamID = function() return -1 end")
        lua.execute("Draw()")
        self.assertEqual(lua.eval("#TEXT_CALLS"), 0)

    def test_source_reads_rules_params_in_drawscreen(self):
        source = WIDGET_PATH.read_text(encoding="utf-8")
        self.assertIn("Spring.GetTeamRulesParam(teamID, key)", source)
        draw = source.split("function widget:DrawScreen()")[1]
        self.assertIn("buildCells(teamID)", draw)

    def test_source_uses_only_engine_primitives(self):
        source = WIDGET_PATH.read_text(encoding="utf-8")
        self.assertIn("gl.Color(", source)
        self.assertIn("gl.Rect(", source)
        self.assertIn("gl.Text(", source)
        for forbidden in ("gl.Texture(", "gl.BeginEnd(", "VFS.LoadFile", "Spring.GetUnitRulesParam"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_source_includes_the_shared_formatter(self):
        source = WIDGET_PATH.read_text(encoding="utf-8")
        self.assertIn('VFS.Include("scripts/medieval_hud.lua")', source)

    def test_modoption_is_declared_and_defaults_true(self):
        source = MODOPTIONS_PATH.read_text(encoding="utf-8")
        block = source.split('key = "medievalhud"')[1].split("},")[0]
        self.assertIn('type = "bool"', block)
        self.assertIn("def = true", block)


if __name__ == "__main__":
    unittest.main()
