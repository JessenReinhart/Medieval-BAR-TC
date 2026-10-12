"""Phase-5 Slice 3 tests: Market & Trade Exchange.

Layers under test:

1. Pure module — `scripts/medieval_market.lua`, a dependency-free, engine-free
   policy module. Every test boots its OWN fresh Lua runtime so one case cannot
   leak mutated module tables into another.
2. Purity — the module must load in a bare Lua 5.1 interpreter with no VFS or
   Spring present. That is a hard requirement, not a style preference: the
   synced gadget loads it through `VFS.Include`, while these tests load it
   directly.
3. Rate model — base ratios, the documented elasticity formula, clamps and
   monotonicity (a scarcer bought resource costs more).
4. Quotes — `exchangeCost` cost arithmetic, margin, ceiling rounding and the
   affordability boundary.
5. Validation — `validateTrade` edge cases: insufficient stock, invalid
   resource, zero/fractional amount, same-resource, full destination, bad state.
6. Transitions — `applyTrade` purity, exact deltas, no free money, no negative
   stock, invalid orders rejected without a partial debit.
7. Unit def + gadget contract — the `medieval_market` datadef, the gadget's
   synced layer, its GG export names, and its reuse of the economy/hauling
   public APIs instead of reimplementing them.
8. Gadget behaviour — the gadget source executed against mocked Spring/GG/VFS
   stubs: inert when the modoption is off, live when it is on.
"""

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_market.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_market.lua"
PROBE_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase5_slice3_market_probe.lua"
UNIT_PATH = ROOT / "units" / "medieval_market.lua"
HAUL_PATH = ROOT / "scripts" / "medieval_haul.lua"
VILLAGER_PATH = ROOT / "units" / "medieval_villager.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"
RUNNER_PATH = ROOT / "tools" / "launch" / "run_phase5_slice3_probe.py"
STARTSCRIPT_PATH = ROOT / "tools" / "launch" / "startscript_phase5_slice3.txt"

# Policy constants mirrored from scripts/medieval_market.lua.
RESOURCES = ("food", "wood", "stone", "iron")
BASE_RATES = {"food": 1.0, "wood": 1.0, "stone": 1.5, "iron": 2.0}
ELASTICITY = 0.5
STOCK_SCALE = 400
TRADE_MARGIN = 0.1
TRADE_SURPLUS = {"food": 3, "wood": 3, "stone": 2, "iron": 1}
ROUTE_RADIUS = 400
MAX_STOCKPILE = 100000

REQUIRED_FUNCTIONS = (
    "rate",
    "exchangeRate",
    "exchangeCost",
    "tradeQuote",
    "validateTrade",
    "canTrade",
    "marketOrder",
    "applyTrade",
    "copyState",
    "routeValue",
    "selectRouteDestination",
    "surplusFor",
)

# Gadget API surface the probe and any future consumer indexes.
GADGET_EXPORTS = ("GetRate", "Exchange", "ValidateTrade")


def _strip_lua_comments(source):
    """Drop whole-line and trailing Lua comments so purity checks read code only."""
    out = []
    for line in source.splitlines():
        stripped = line.split("--", 1)[0]
        out.append(stripped)
    return "\n".join(out)


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


def _order(lua, **kwargs):
    """Build a marketOrder table (kwargs avoids clashing with Python keywords)."""
    return lua.table(**kwargs)


class MarketBase(unittest.TestCase):
    """Fresh module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    # -- helpers -------------------------------------------------------------

    def _stock(self, **resources):
        return self.lua.table(**resources)

    def _balanced(self, value=200):
        return self._stock(**{r: value for r in RESOURCES})

    def _state(self, **resources):
        return self.lua.table(stockpiles=self._stock(**resources))

    def _quote(self, stock, from_res, to_res, amount):
        return _lua_to_py(self.lua, self.m.exchangeCost(stock, from_res, to_res, amount))

    def _validate(self, state, from_res, to_res, amount):
        return _lua_to_py(self.lua, self.m.validateTrade(state, from_res, to_res, amount))


# ---------------------------------------------------------------------------
# 1. Constants and purity
# ---------------------------------------------------------------------------


class TestSlice3Constants(MarketBase):
    def test_resource_pool_is_the_existing_four(self):
        self.assertEqual(list(self.m.RESOURCES.values()), list(RESOURCES))

    def test_there_is_no_gold_resource(self):
        # Barter runs on the Phase 2 four-resource pool; a fifth "gold" resource
        # is explicitly out of scope for Phase 5.
        self.assertNotIn("gold", list(self.m.RESOURCES.values()))
        self.assertNotIn("gold", list(self.m.BASE_RATES.keys()))
        self.assertNotIn("gold", list(self.m.TRADE_SURPLUS.keys()))
        self.assertNotIn("gold", list(self.m.RESOURCES.values()))
        self.assertFalse(self.m.validResource("gold"))
        # ...and the gadget never declares one either.
        self.assertNotIn("gold", GADGET_PATH.read_text(encoding="utf-8"))

    def test_base_rates(self):
        for resource, expected in BASE_RATES.items():
            self.assertEqual(self.m.BASE_RATES[resource], expected)

    def test_policy_constants(self):
        self.assertEqual(self.m.ELASTICITY, ELASTICITY)
        self.assertEqual(self.m.STOCK_SCALE, STOCK_SCALE)
        self.assertEqual(self.m.TRADE_MARGIN, TRADE_MARGIN)
        self.assertEqual(self.m.ROUTE_RADIUS, ROUTE_RADIUS)
        self.assertEqual(self.m.MAX_STOCKPILE, MAX_STOCKPILE)
        self.assertLess(self.m.MIN_RATE_FACTOR, 1.0)
        self.assertGreater(self.m.MAX_RATE_FACTOR, 1.0)

    def test_trade_surplus_table(self):
        for resource, amount in TRADE_SURPLUS.items():
            self.assertEqual(self.m.TRADE_SURPLUS[resource], amount)

    def test_required_functions_are_exported(self):
        for name in REQUIRED_FUNCTIONS:
            with self.subTest(name=name):
                self.assertEqual(self.lua.eval("type")(self.m[name]), "function")


class TestSlice3Purity(unittest.TestCase):
    """The module must stay loadable with no VFS/Spring/GG present."""

    def test_module_has_no_engine_calls(self):
        code = _strip_lua_comments(MODULE_PATH.read_text(encoding="utf-8"))
        for token in ("Spring", "VFS", "GG", "gadgetHandler", "UnitDefs"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)

    def test_module_does_not_include_siblings(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("require(", source)
        self.assertNotIn("dofile", source)
        self.assertNotIn("loadfile", source)

    def test_module_loads_in_a_bare_runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("Spring = nil; VFS = nil; GG = nil; gadgetHandler = nil")
        module = lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(lua.eval("type")(module.rate), "function")


# ---------------------------------------------------------------------------
# 2. Rate model
# ---------------------------------------------------------------------------


class TestSlice3Rate(MarketBase):
    def test_balanced_stocks_give_the_pure_base_ratio(self):
        stock = self._balanced()
        # food -> iron: base 2.0/1.0, and a balanced pool contributes factor 1.0.
        self.assertAlmostEqual(self.m.rate("food", "iron", stock), 2.0)
        self.assertAlmostEqual(self.m.rate("iron", "food", stock), 0.5)
        self.assertAlmostEqual(self.m.rate("food", "stone", stock), 1.5)
        self.assertAlmostEqual(self.m.rate("wood", "food", stock), 1.0)

    def test_omitted_stock_gives_the_pure_base_ratio(self):
        self.assertAlmostEqual(self.m.rate("food", "iron"), 2.0)
        self.assertAlmostEqual(self.m.rate("food", "iron", None), 2.0)

    def test_same_resource_rate_is_one(self):
        for resource in RESOURCES:
            with self.subTest(resource=resource):
                self.assertEqual(self.m.rate(resource, resource, self._balanced()), 1.0)

    def test_invalid_resource_rate_is_zero(self):
        stock = self._balanced()
        self.assertEqual(self.m.rate("gold", "iron", stock), 0)
        self.assertEqual(self.m.rate("food", "gold", stock), 0)
        self.assertEqual(self.m.rate(None, "iron", stock), 0)
        self.assertEqual(self.m.rate(7, "iron", stock), 0)

    def test_scarcity_of_the_bought_resource_raises_its_price(self):
        # Documented formula: 1 + E * (stock[from] - stock[to]) / STOCK_SCALE.
        scarce = self._stock(food=400, iron=0)
        expected = 2.0 * (1.0 + ELASTICITY * (400 - 0) / STOCK_SCALE)
        self.assertAlmostEqual(self.m.rate("food", "iron", scarce), expected)
        self.assertGreater(self.m.rate("food", "iron", scarce), 2.0)

    def test_abundance_of_the_bought_resource_lowers_its_price(self):
        glut = self._stock(food=0, iron=400)
        expected = 2.0 * (1.0 + ELASTICITY * (0 - 400) / STOCK_SCALE)
        self.assertAlmostEqual(self.m.rate("food", "iron", glut), expected)
        self.assertLess(self.m.rate("food", "iron", glut), 2.0)

    def test_rate_is_monotonic_in_the_bought_resource_stock(self):
        previous = None
        for iron in (0, 100, 200, 300, 400, 800):
            rate = self.m.rate("food", "iron", self._stock(food=400, iron=iron))
            if previous is not None:
                self.assertLess(rate, previous)
            previous = rate

    def test_rate_is_monotonic_in_the_paid_resource_stock(self):
        previous = None
        for food in (0, 100, 200, 300, 400, 800):
            rate = self.m.rate("food", "iron", self._stock(food=food, iron=0))
            if previous is not None:
                self.assertGreater(rate, previous)
            previous = rate

    def test_rate_is_always_positive_and_bounded(self):
        for food in (0, 100000):
            for iron in (0, 100000):
                rate = self.m.rate("food", "iron", self._stock(food=food, iron=iron))
                self.assertGreater(rate, 0)
                self.assertLessEqual(rate, BASE_RATES["iron"] / BASE_RATES["food"] * self.m.MAX_RATE_FACTOR)

    def test_missing_or_malformed_stock_reads_as_zero(self):
        stock = self.lua.table(food="nonsense", iron=None)
        # Both sides read 0 -> factor 1.0 -> the pure base ratio.
        self.assertAlmostEqual(self.m.rate("food", "iron", stock), 2.0)

    def test_negative_stock_reads_as_zero(self):
        self.assertAlmostEqual(self.m.rate("food", "iron", self._stock(food=-50, iron=0)), 2.0)

    def test_exchange_rate_takes_a_state_projection(self):
        state = self._state(food=400, wood=0, stone=0, iron=0)
        direct = self.m.rate("food", "iron", self._stock(food=400, iron=0))
        self.assertAlmostEqual(self.m.exchangeRate(state, "food", "iron"), direct)

    def test_rates_from_covers_all_four(self):
        rates = _lua_to_py(self.lua, self.m.ratesFrom("food", self._balanced()))
        self.assertEqual(sorted(rates.keys()), sorted(RESOURCES))
        self.assertEqual(rates["food"], 1.0)

    def test_rate_is_deterministic(self):
        stock = self._stock(food=321, wood=77, stone=41, iron=9)
        first = self.m.rate("wood", "stone", stock)
        for _ in range(5):
            self.assertEqual(self.m.rate("wood", "stone", stock), first)


# ---------------------------------------------------------------------------
# 3. exchangeCost
# ---------------------------------------------------------------------------


class TestSlice3ExchangeCost(MarketBase):
    def test_cost_is_the_mid_rate_plus_the_margin_rounded_up(self):
        stock = self._balanced()
        amount = 20
        mid = self.m.rate("food", "iron", stock)
        expected = int(-(-(amount * mid * (1.0 + TRADE_MARGIN)) // 1))  # ceil
        quote = self._quote(stock, "food", "iron", amount)
        self.assertEqual(quote["cost"], expected)

    def test_cost_never_undercuts_the_mid_rate(self):
        stock = self._balanced()
        amount = 7
        mid = self.m.rate("food", "iron", stock)
        quote = self._quote(stock, "food", "iron", amount)
        self.assertGreaterEqual(quote["cost"], amount * mid)

    def test_cost_is_integral(self):
        quote = self._quote(self._stock(food=333, iron=17), "food", "iron", 13)
        self.assertEqual(quote["cost"], int(quote["cost"]))

    def test_affordability_boundary_is_exactly_the_quoted_cost(self):
        # Affordable is a strict `have >= cost` test on the SAME quote, so the
        # verdict must flip exactly once and never disagree with the cost.
        verdicts = []
        for food in range(1, 120):
            stock = self._stock(food=food, wood=0, stone=0, iron=0)
            quote = self._quote(stock, "food", "iron", 10)
            self.assertEqual(quote["affordable"], food >= quote["cost"])
            verdicts.append(quote["affordable"])
        self.assertFalse(verdicts[0])
        self.assertTrue(verdicts[-1])
        # Monotone: once affordable, always affordable as the payer stocks up.
        self.assertEqual(verdicts, sorted(verdicts))

    def test_unaffordable_when_the_pool_is_short_of_the_quote(self):
        # Note the quote is computed on the SAME stock it is tested against: the
        # rate itself depends on the payer's stock, so "one unit short" must be
        # read as `have < cost`, not as a fixed pre-computed number.
        for food in (1, 5, 10, 15):
            with self.subTest(food=food):
                quote = self._quote(self._stock(food=food, wood=0, stone=0, iron=0), "food", "iron", 10)
                self.assertLess(food, quote["cost"])
                self.assertFalse(quote["affordable"])
                self.assertEqual(quote["reason"], "insufficient-stock")

    def test_zero_stock_is_unaffordable(self):
        quote = self._quote(self._stock(food=0, iron=0), "food", "iron", 10)
        self.assertFalse(quote["affordable"])
        self.assertGreater(quote["cost"], 0)

    def test_invalid_resource(self):
        quote = self._quote(self._balanced(), "gold", "iron", 10)
        self.assertEqual(quote["cost"], 0)
        self.assertFalse(quote["affordable"])
        self.assertEqual(quote["reason"], "invalid-resource")

    def test_same_resource_is_rejected(self):
        quote = self._quote(self._balanced(), "food", "food", 10)
        self.assertFalse(quote["affordable"])
        self.assertEqual(quote["reason"], "same-resource")

    def test_zero_amount_is_rejected(self):
        quote = self._quote(self._balanced(), "food", "iron", 0)
        self.assertEqual(quote["cost"], 0)
        self.assertFalse(quote["affordable"])
        self.assertEqual(quote["reason"], "invalid-amount")

    def test_negative_and_fractional_amounts_are_rejected(self):
        for amount in (-1, 1.5, "10", None):
            with self.subTest(amount=amount):
                quote = self._quote(self._balanced(), "food", "iron", amount)
                self.assertFalse(quote["affordable"])
                self.assertEqual(quote["reason"], "invalid-amount")

    def test_invalid_from_stock_table_is_unaffordable_not_an_error(self):
        quote = self._quote(None, "food", "iron", 10)
        self.assertFalse(quote["affordable"])

    def test_cost_grows_with_the_amount(self):
        stock = self._balanced()
        self.assertLess(
            self._quote(stock, "food", "iron", 5)["cost"],
            self._quote(stock, "food", "iron", 50)["cost"],
        )

    def test_trade_quote_mirrors_exchange_cost(self):
        stock = self._balanced()
        direct = self._quote(stock, "food", "iron", 10)
        quote = _lua_to_py(self.lua, self.m.tradeQuote(self.lua.table(stockpiles=stock), "food", "iron", 10))
        self.assertEqual(quote["cost"], direct["cost"])
        self.assertEqual(quote["ok"], direct["affordable"])


# ---------------------------------------------------------------------------
# 4. validateTrade
# ---------------------------------------------------------------------------


class TestSlice3ValidateTrade(MarketBase):
    def test_valid_trade(self):
        result = self._validate(self._balanced(400), "food", "iron", 10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "ok")
        self.assertGreater(result["cost"], 0)

    def test_insufficient_stock(self):
        result = self._validate(self._state(food=5, wood=0, stone=0, iron=0), "food", "iron", 50)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "insufficient-stock")

    def test_invalid_from_resource(self):
        result = self._validate(self._balanced(), "gold", "iron", 10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-resource")

    def test_invalid_to_resource(self):
        result = self._validate(self._balanced(), "food", "gold", 10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-resource")

    def test_nil_resource(self):
        result = self._validate(self._balanced(), None, "iron", 10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-resource")

    def test_zero_amount(self):
        result = self._validate(self._balanced(), "food", "iron", 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-amount")

    def test_negative_amount(self):
        result = self._validate(self._balanced(), "food", "iron", -5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-amount")

    def test_fractional_amount(self):
        result = self._validate(self._balanced(), "food", "iron", 2.5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-amount")

    def test_nan_amount(self):
        nan = self.lua.eval("0/0")
        result = self._validate(self._balanced(), "food", "iron", nan)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid-amount")

    def test_same_resource(self):
        result = self._validate(self._balanced(), "stone", "stone", 10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "same-resource")

    def test_invalid_state(self):
        for state in (None, 42, "state", self.lua.table()):
            with self.subTest(state=state):
                result = self._validate(state, "food", "iron", 10)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], "invalid-state")

    def test_stockpile_full(self):
        state = self._state(food=500, wood=0, stone=0, iron=MAX_STOCKPILE)
        result = self._validate(state, "food", "iron", 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "stockpile-full")

    def test_stockpile_exactly_at_the_limit_minus_amount_is_allowed(self):
        state = self._state(food=500, wood=0, stone=0, iron=MAX_STOCKPILE - 10)
        result = self._validate(state, "food", "iron", 10)
        self.assertTrue(result["ok"])

    def test_validate_reports_the_quote_cost(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        result = self._validate(state, "food", "iron", 10)
        quote = self._quote(self._state(food=500, wood=0, stone=0, iron=0).stockpiles, "food", "iron", 10)
        self.assertEqual(result["cost"], quote["cost"])

    def test_can_trade_wrapper(self):
        self.assertTrue(self.m.canTrade(self._balanced(400), "food", "iron", 10))
        self.assertFalse(self.m.canTrade(self._state(food=1, wood=0, stone=0, iron=0), "food", "iron", 10))

    def test_validate_never_mutates_the_state(self):
        state = self._state(food=500, wood=10, stone=10, iron=10)
        self._validate(state, "food", "iron", 10)
        self.assertEqual(state.stockpiles.food, 500)
        self.assertEqual(state.stockpiles.iron, 10)


# ---------------------------------------------------------------------------
# 5. marketOrder + applyTrade
# ---------------------------------------------------------------------------


class TestSlice3ApplyTrade(MarketBase):
    def _order_table(self, team=0, frm="food", to="iron", amount=10):
        return self.lua.table(teamID=team, **{"from": frm, "to": to, "amount": amount})

    def test_market_order_struct_shape(self):
        order = self.m.marketOrder(3, "wood", "stone", 25)
        self.assertEqual(order.teamID, 3)
        self.assertEqual(order["from"], "wood")
        self.assertEqual(order["to"], "stone")
        self.assertEqual(order.amount, 25)

    def test_order_fields_constant(self):
        self.assertEqual(list(self.m.ORDER_FIELDS.values()), ["teamID", "from", "to", "amount"])

    def test_apply_trade_debits_and_credits_exactly(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        quote = self._quote(state.stockpiles, "food", "iron", 20)
        result = self.m.applyTrade(state, self._order_table(amount=20))
        self.assertTrue(result.ok)
        self.assertEqual(result.stockpiles.food, 500 - quote["cost"])
        self.assertEqual(result.stockpiles.iron, 20)
        self.assertEqual(result.cost, quote["cost"])

    def test_apply_trade_returns_a_new_table(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        result = self.m.applyTrade(state, self._order_table(amount=20))
        self.assertNotEqual(result, state)
        self.assertNotEqual(result.stockpiles, state.stockpiles)

    def test_apply_trade_never_mutates_the_input_state(self):
        state = self._state(food=500, wood=100, stone=100, iron=100)
        before = {r: state.stockpiles[r] for r in RESOURCES}
        self.m.applyTrade(state, self._order_table(amount=20))
        for resource in RESOURCES:
            self.assertEqual(state.stockpiles[resource], before[resource])

    def test_apply_trade_does_not_mutate_a_shared_stock_table(self):
        shared = self._stock(food=500, wood=100, stone=100, iron=100)
        self.m.applyTrade(self.lua.table(stockpiles=shared), self._order_table(amount=20))
        # The caller's live pool table is untouched; the gadget commits the
        # transition through GG.MedievalEconomy, never by aliasing this table.
        self.assertEqual(shared.food, 500)
        self.assertEqual(shared.iron, 100)

    def test_apply_trade_is_deterministic(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        order = self._order_table(amount=20)
        first = self.m.applyTrade(state, order).stockpiles.food
        for _ in range(3):
            self.assertEqual(self.m.applyTrade(state, order).stockpiles.food, first)

    def test_apply_trade_conserves_the_other_resources(self):
        state = self._state(food=500, wood=77, stone=33, iron=11)
        result = self.m.applyTrade(state, self._order_table(amount=5))
        self.assertEqual(result.stockpiles.wood, 77)
        self.assertEqual(result.stockpiles.stone, 33)

    def test_apply_trade_rejects_an_unaffordable_order_without_a_partial_debit(self):
        state = self._state(food=1, wood=0, stone=0, iron=0)
        result = self.m.applyTrade(state, self._order_table(amount=50))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "insufficient-stock")
        self.assertEqual(result.stockpiles.food, 1)
        self.assertEqual(result.stockpiles.iron, 0)

    def test_apply_trade_rejects_an_invalid_order(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        for order in (None, "nope", 7, self.lua.table()):
            with self.subTest(order=order):
                result = self.m.applyTrade(state, order)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason, "invalid-order")
                self.assertEqual(result.stockpiles.food, 500)

    def test_apply_trade_rejects_an_invalid_resource_order(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        result = self.m.applyTrade(state, self._order_table(frm="gold", amount=5))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid-resource")
        self.assertEqual(result.stockpiles.food, 500)

    def test_apply_trade_rejects_a_zero_amount_order(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        result = self.m.applyTrade(state, self._order_table(amount=0))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid-amount")

    def test_no_free_money(self):
        # A trade always costs at least the mid rate; the house margin means the
        # round trip can never be profitable.
        state = self._state(food=1000, wood=0, stone=0, iron=0)
        forward = self.m.applyTrade(state, self._order_table(amount=100))
        back_state = self.lua.table(stockpiles=forward.stockpiles)
        back = self.m.applyTrade(back_state, self.lua.table(teamID=0, **{"from": "iron", "to": "food", "amount": 100}))
        self.assertTrue(back.ok)
        self.assertLess(back.stockpiles.food, 1000)

    def test_stock_never_goes_negative(self):
        state = self._state(food=500, wood=0, stone=0, iron=0)
        for amount in (1, 10, 50, 100, 200):
            result = self.m.applyTrade(state, self._order_table(amount=amount))
            for resource in RESOURCES:
                self.assertGreaterEqual(result.stockpiles[resource], 0)

    def test_destination_is_clamped_at_max_stockpile(self):
        state = self._state(food=100000, wood=0, stone=0, iron=MAX_STOCKPILE - 5)
        result = self.m.applyTrade(state, self._order_table(amount=5))
        self.assertTrue(result.ok)
        self.assertEqual(result.stockpiles.iron, MAX_STOCKPILE)

    def test_copy_state_is_independent(self):
        state = self._state(food=10, wood=20, stone=30, iron=40)
        copy = self.m.copyState(state)
        copy.stockpiles.food = 999
        self.assertEqual(state.stockpiles.food, 10)
        self.assertEqual(copy.stockpiles.iron, 40)

    def test_copy_state_fills_missing_resources_with_zero(self):
        copy = self.m.copyState(self.lua.table(stockpiles=self.lua.table(food=5)))
        for resource in RESOURCES:
            self.assertEqual(self.lua.eval("type")(copy.stockpiles[resource]), "number")
        self.assertEqual(copy.stockpiles.iron, 0)


# ---------------------------------------------------------------------------
# 6. Trade routes
# ---------------------------------------------------------------------------


class TestSlice3Routes(MarketBase):
    def _markets(self, *entries):
        table = self.lua.table()
        for index, (market_id, x, z) in enumerate(entries, start=1):
            table[index] = self.lua.table(id=market_id, x=x, z=z)
        return table

    def test_route_value_scales_with_distance(self):
        near = self.m.routeValue(None, self.lua.table(x=0, z=0), self.lua.table(x=100, z=0))
        far = self.m.routeValue(None, self.lua.table(x=0, z=0), self.lua.table(x=300, z=0))
        self.assertGreater(far, near)
        self.assertAlmostEqual(far, TRADE_MARGIN * 0.75)

    def test_route_value_saturates_at_the_route_radius(self):
        capped = self.m.routeValue(None, self.lua.table(x=0, z=0), self.lua.table(x=ROUTE_RADIUS, z=0))
        beyond = self.m.routeValue(None, self.lua.table(x=0, z=0), self.lua.table(x=ROUTE_RADIUS * 10, z=0))
        self.assertAlmostEqual(capped, TRADE_MARGIN)
        self.assertAlmostEqual(beyond, TRADE_MARGIN)

    def test_route_value_of_malformed_positions_is_zero(self):
        self.assertEqual(self.m.routeValue(None, None, self.lua.table(x=1, z=1)), 0)
        self.assertEqual(self.m.routeValue(None, self.lua.table(x=1), self.lua.table(x=1, z=1)), 0)

    def test_select_route_destination_picks_the_nearest(self):
        markets = self._markets((10, 0, 0), (11, 5000, 0), (12, 200, 0))
        best = _lua_to_py(self.lua, self.m.selectRouteDestination(markets, 1))
        self.assertEqual(best["id"], 12)

    def test_select_route_destination_respects_the_radius(self):
        markets = self._markets((10, 0, 0), (11, ROUTE_RADIUS + 1, 0))
        self.assertIsNone(self.m.selectRouteDestination(markets, 1))

    def test_select_route_destination_breaks_ties_on_the_lower_id(self):
        markets = self._markets((10, 0, 0), (20, 100, 0), (15, 100, 0))
        best = _lua_to_py(self.lua, self.m.selectRouteDestination(markets, 1))
        self.assertEqual(best["id"], 15)

    def test_select_route_destination_needs_another_market(self):
        self.assertIsNone(self.m.selectRouteDestination(self._markets((10, 0, 0)), 1))

    def test_select_route_destination_is_deterministic(self):
        markets = self._markets((10, 0, 0), (11, 120, 0), (12, 300, 0))
        first = _lua_to_py(self.lua, self.m.selectRouteDestination(markets, 1))
        for _ in range(3):
            again = _lua_to_py(self.lua, self.m.selectRouteDestination(markets, 1))
            self.assertEqual(again["id"], first["id"])

    def test_surplus_round_robin_is_deterministic(self):
        expected = [TRADE_SURPLUS[r] for r in RESOURCES]
        for index in range(1, 9):
            resource, amount = self.m.surplusFor(index)
            self.assertEqual(resource, RESOURCES[(index - 1) % 4])
            self.assertEqual(amount, expected[(index - 1) % 4])

    def test_surplus_for_invalid_index(self):
        for index in (0, -3, None, "2"):
            with self.subTest(index=index):
                resource, amount = self.m.surplusFor(index)
                self.assertIsNone(resource)
                self.assertIsNone(amount)


# ---------------------------------------------------------------------------
# 7. Unit def + gadget contract
# ---------------------------------------------------------------------------


class TestSlice3UnitDef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.def_ = cls.lua.execute(UNIT_PATH.read_text(encoding="utf-8"))["medieval_market"]

    def test_identity(self):
        self.assertEqual(self.def_["name"], "Market")
        self.assertEqual(self.def_["category"], "LAND")
        self.assertEqual(self.def_["side"], "MEDIEVAL")

    def test_static_building(self):
        self.assertFalse(self.def_["canMove"])
        self.assertFalse(self.def_["canAttack"])
        self.assertFalse(self.def_["canFight"])
        self.assertFalse(self.def_["builder"])

    def test_cheap_economic_cost(self):
        self.assertEqual(self.def_["buildCostEnergy"], 0)
        self.assertEqual(self.def_["customparams"]["resource_cost_wood"], 80)
        self.assertEqual(self.def_["customparams"]["resource_cost_stone"], 40)

    def test_health_is_about_800(self):
        self.assertEqual(self.def_["maxDamage"], 800)

    def test_has_a_dedicated_0ad_model(self):
        # Phase 7 Slice 3: the market no longer recycles the infantry body.
        self.assertEqual(self.def_["objectName"], "0ad/medieval_market.obj")

    def test_market_and_armor_tags(self):
        self.assertTrue(self.def_["customparams"]["market"])
        self.assertEqual(self.def_["customparams"]["armor_class"], "building")

    def test_villagers_can_build_it(self):
        villager = self.lua.execute(VILLAGER_PATH.read_text(encoding="utf-8"))["medieval_villager"]
        options = [villager["buildoptions"][i] for i in range(1, len(villager["buildoptions"]) + 1)]
        self.assertIn("medieval_market", options)


class TestSlice3GadgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GADGET_PATH.read_text(encoding="utf-8")

    def test_synced_layer_six(self):
        self.assertIn("layer = 6", self.source)
        self.assertIn("enabled = true", self.source)
        self.assertIn("gadgetHandler:IsSyncedCode()", self.source)

    def test_always_registered_but_modoption_gated(self):
        self.assertIn("medievalmarket", self.source)
        self.assertIn("ENABLED", self.source)
        self.assertIn("market-disabled", self.source)

    def test_exports_the_required_gg_api(self):
        for name in GADGET_EXPORTS:
            with self.subTest(name=name):
                self.assertIn(f"GG.MedievalMarket.{name} =", self.source)

    def test_gg_table_is_additive(self):
        # Never reassign GG.MedievalMarket wholesale: other gadgets may already
        # have posted onto it.
        self.assertIn("GG.MedievalMarket = GG.MedievalMarket or {}", self.source)
        self.assertNotIn("GG.MedievalMarket = {", self.source)

    def test_reads_and_writes_stockpiles_only_through_the_public_economy_api(self):
        for name in ("GetStockpiles", "Transact", "Deposit"):
            with self.subTest(name=name):
                self.assertIn(f"econ.{name}", self.source)
        # The live pool is READ (GetStockpiles) but never WRITTEN directly: every
        # mutation goes through Transact/Deposit so the economy gadget stays the
        # single owner of the stockpile tables.
        code = _strip_lua_comments(self.source)
        for match in re.finditer(r"stockpiles?\s*\[[^\]]*\]\s*=", code):
            self.fail(f"direct stockpile write in gadget: {match.group(0)}")

    def test_reuses_the_hauling_api_instead_of_moving_carts(self):
        self.assertIn("GG.MedievalLogistics", self.source)
        self.assertIn("HaulSummary", self.source)
        # Cart movement stays with the hauler; the market never issues orders.
        self.assertNotIn("GiveOrderToUnit", self.source)
        self.assertNotIn("Spring.MoveCtrl", self.source)

    def test_market_is_registered_as_a_haul_hub(self):
        haul = HAUL_PATH.read_text(encoding="utf-8")
        self.assertIn("medieval_market", haul)

    def test_includes_the_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_market.lua")', self.source)


class TestSlice3ProbeAndRunner(unittest.TestCase):
    def test_probe_is_modoption_gated(self):
        source = PROBE_PATH.read_text(encoding="utf-8")
        self.assertIn("medievalmarket", source)
        self.assertIn("if not enabled then return end", source)

    def test_probe_emits_the_required_verdict_lines(self):
        source = PROBE_PATH.read_text(encoding="utf-8")
        self.assertIn("PHASE5 MARKET barter-verdict", source)
        self.assertIn("PHASE5 MARKET probe-complete PASS", source)

    def test_runner_watches_the_verdicts(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("startscript_phase5_slice3.txt", source)
        self.assertIn('"rate", "barter"', source)

    def test_startscript_enables_the_market_modoption(self):
        text = STARTSCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("medievalmarket=1", text)
        self.assertIn("forcestart", text)

    def test_modoption_is_declared(self):
        source = MODOPTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn('key = "medievalmarket"', source)
        self.assertIn('type = "bool"', source)


# ---------------------------------------------------------------------------
# 8. Gadget behaviour against stubs
# ---------------------------------------------------------------------------

GADGET_STUB_TEMPLATE = r"""
ECHO_LINES = {}
TRANSACT_CALLS = {}
DEPOSIT_CALLS = {}
STOCKPILES = {}
UNITS = {}
TEAM_LIST = {0, 1}

gadget = {}
gadgetHandler = { IsSyncedCode = function() return true end }

UnitDefs = {
  [1] = { name = "medieval_market" },
  [2] = { name = "medieval_villager" },
}
UnitDefNames = { medieval_market = { id = 1 } }

local function ensureTeam(team)
  STOCKPILES[team] = STOCKPILES[team] or { food = 0, wood = 0, stone = 0, iron = 0 }
  return STOCKPILES[team]
end

Spring = {
  Echo = function(fmt, ...)
    local ok, msg = pcall(string.format, fmt, ...)
    table.insert(ECHO_LINES, ok and msg or tostring(fmt))
  end,
  GetModOptions = function() return MODOPTIONS end,
  GetTeamList = function() return TEAM_LIST end,
  GetAllUnits = function()
    local out = {}
    for id in pairs(UNITS) do table.insert(out, id) end
    table.sort(out)
    return out
  end,
  GetUnitDefID = function(id) local u = UNITS[id]; return u and u.defID or nil end,
  GetUnitTeam = function(id) local u = UNITS[id]; return u and u.team or nil end,
  GetUnitPosition = function(id)
    local u = UNITS[id]
    if u then return u.x, 0, u.z end
    return nil
  end,
  GetGroundHeight = function() return 0 end,
}

GG = {
  MedievalEconomy = {
    GetStockpiles = function(team) return ensureTeam(team) end,
    Transact = function(team, costs)
      table.insert(TRANSACT_CALLS, { teamID = team, costs = costs })
      local s = ensureTeam(team)
      for r, a in pairs(costs) do
        if (s[r] or 0) < a then return false end
      end
      for r, a in pairs(costs) do s[r] = (s[r] or 0) - a end
      return true
    end,
    Deposit = function(team, resource, amount)
      table.insert(DEPOSIT_CALLS, { teamID = team, resource = resource, amount = amount })
      local s = ensureTeam(team)
      s[resource] = (s[resource] or 0) + amount
      return s[resource]
    end,
  },
  MedievalLogistics = {
    IsOnRoad = function() return true end,
    HaulSummary = function(team) return HAUL_SUMMARY[team] end,
  },
}

VFS = {
  Include = function(path)
    local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
    local src = fh:read("*a")
    fh:close()
    return assert(load(src, "@" .. path, "t", _G))()
  end,
}

function PlaceUnit(id, defID, x, z, team)
  UNITS[id] = { defID = defID, x = x, z = z, team = team }
end
function SetStock(team, resource, value) ensureTeam(team)[resource] = value end
function StockOf(team, resource) return ensureTeam(team)[resource] or 0 end
function SetHaulSummary(team, delivered) HAUL_SUMMARY[team] = { delivered = delivered } end
function GadgetInfo() return gadget:GetInfo() end
function FireInitialize() gadget:Initialize() end
function FireUnitFinished(id, defID, team) gadget:UnitFinished(id, defID, team) end
function FireUnitDestroyed(id, defID, team) gadget:UnitDestroyed(id, defID, team) end
function FireGameFrame(frame) gadget:GameFrame(frame) end
function FireTeamDied(team) gadget:TeamDied(team) end
function HasEcho(fragment)
  for _, line in ipairs(ECHO_LINES) do
    if string.find(line, fragment, 1, true) then return true end
  end
  return false
end

assert(load(GADGET_SRC, "@gadget_medieval_market.lua", "t", _G))()
"""


class Slice3GadgetBase(unittest.TestCase):
    """Fresh gadget VM with engine stubs, per test."""

    modoptions = {"medievalmarket": "1"}

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.MODOPTIONS = self.lua.table(**self.modoptions)
        g.HAUL_SUMMARY = self.lua.table()
        self.lua.execute(GADGET_STUB_TEMPLATE)

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self.lua.globals().GG.MedievalMarket

    def _stock(self, team, resource):
        return self._g("StockOf")(team, resource)


class TestSlice3GadgetEnabled(Slice3GadgetBase):
    def test_gadget_metadata(self):
        info = _lua_to_py(self.lua, self._g("GadgetInfo")())
        self.assertEqual(info["name"], "Medieval Market")
        self.assertEqual(info["layer"], 6)
        self.assertTrue(info["enabled"])

    def test_api_is_registered_on_load(self):
        api = self._api()
        for name in GADGET_EXPORTS:
            with self.subTest(name=name):
                self.assertEqual(self.lua.eval("type")(api[name]), "function")
        self.assertTrue(api.IsEnabled())

    def test_market_unit_is_tracked(self):
        self._g("FireInitialize")()
        self._g("PlaceUnit")(101, 1, 1800, 2400, 0)
        self._g("FireUnitFinished")(101, 1, 0)
        self.assertEqual(self._api().MarketCount(0), 1)
        self.assertTrue(self._g("HasEcho")("PHASE5 MARKET tracked"))

    def test_non_market_units_are_ignored(self):
        self._g("FireInitialize")()
        self._g("PlaceUnit")(202, 2, 1800, 2400, 0)
        self._g("FireUnitFinished")(202, 2, 0)
        self.assertEqual(self._api().MarketCount(0), 0)

    def test_destroyed_market_is_untracked(self):
        self._g("FireInitialize")()
        self._g("PlaceUnit")(101, 1, 1800, 2400, 0)
        self._g("FireUnitFinished")(101, 1, 0)
        self._g("FireUnitDestroyed")(101, 1, 0)
        self.assertEqual(self._api().MarketCount(0), 0)

    def test_get_rate_matches_the_pure_module(self):
        self._g("FireInitialize")()
        self._g("SetStock")(0, "food", 400)
        self._g("SetStock")(0, "iron", 0)
        market = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))
        live = self._g("GG").MedievalEconomy.GetStockpiles(0)
        self.assertAlmostEqual(self._api().GetRate("food", "iron", 0), market.rate("food", "iron", live))

    def test_validate_trade_reports_insufficient_stock(self):
        self._g("FireInitialize")()
        self._g("SetStock")(0, "food", 1)
        result = _lua_to_py(self.lua, self._api().ValidateTrade(0, "food", "iron", 50))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "insufficient-stock")

    def test_exchange_moves_the_pool_through_the_economy_api(self):
        self._g("FireInitialize")()
        self._g("SetStock")(0, "food", 500)
        self._g("SetStock")(0, "iron", 0)
        result = _lua_to_py(self.lua, self._api().Exchange(0, "food", "iron", 20))
        self.assertTrue(result["ok"])
        self.assertEqual(self._stock(0, "iron"), 20)
        self.assertEqual(self._stock(0, "food"), 500 - result["cost"])
        self.assertEqual(len(_lua_to_py(self.lua, self._g("TRANSACT_CALLS"))), 1)
        self.assertEqual(len(_lua_to_py(self.lua, self._g("DEPOSIT_CALLS"))), 1)

    def test_exchange_debits_before_it_credits(self):
        # A refused debit must leave the pool exactly as it was: no free goods.
        self._g("FireInitialize")()
        self._g("SetStock")(0, "food", 0)
        self._g("SetStock")(0, "iron", 0)
        result = _lua_to_py(self.lua, self._api().Exchange(0, "food", "iron", 20))
        self.assertFalse(result["ok"])
        self.assertEqual(self._stock(0, "iron"), 0)
        self.assertEqual(len(_lua_to_py(self.lua, self._g("DEPOSIT_CALLS"))), 0)

    def test_routes_pair_two_markets(self):
        self._g("FireInitialize")()
        for unit_id, x in ((101, 1800), (102, 1900)):
            self._g("PlaceUnit")(unit_id, 1, x, 2400, 0)
            self._g("FireUnitFinished")(unit_id, 1, 0)
        routes = _lua_to_py(self.lua, self._api().GetRoutes(0))
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0]["from"], 101)
        self.assertEqual(routes[0]["to"], 102)

    def test_route_bonus_is_minted_on_a_delivery(self):
        self._g("FireInitialize")()
        for unit_id, x in ((101, 1800), (102, 1900)):
            self._g("PlaceUnit")(unit_id, 1, x, 2400, 0)
            self._g("FireUnitFinished")(unit_id, 1, 0)
        self._g("SetStock")(0, "food", 0)
        self._g("SetHaulSummary")(0, 1)
        self._g("FireGameFrame")(30)
        self.assertEqual(self._api().RouteBonusTotal(0), 1)
        self.assertEqual(self._stock(0, "food"), TRADE_SURPLUS["food"])
        self.assertTrue(self._g("HasEcho")("PHASE5 MARKET route-bonus"))

    def test_route_bonus_is_not_re_minted_for_the_same_delivery(self):
        self._g("FireInitialize")()
        for unit_id, x in ((101, 1800), (102, 1900)):
            self._g("PlaceUnit")(unit_id, 1, x, 2400, 0)
            self._g("FireUnitFinished")(unit_id, 1, 0)
        self._g("SetHaulSummary")(0, 1)
        self._g("FireGameFrame")(30)
        self._g("FireGameFrame")(60)
        self.assertEqual(self._api().RouteBonusTotal(0), 1)

    def test_market_can_be_a_haul_hub(self):
        haul = self.lua.execute(HAUL_PATH.read_text(encoding="utf-8"))
        self.assertTrue(haul.isHubName("medieval_market"))
        self.assertTrue(haul.hubProfile("medieval_market").supply["food"])
        self.assertFalse(haul.hubProfile("medieval_market").demand["food"])


class TestSlice3GadgetDisabled(Slice3GadgetBase):
    modoptions = {"medievalmarket": "0"}

    def test_api_is_still_registered(self):
        for name in GADGET_EXPORTS:
            with self.subTest(name=name):
                self.assertEqual(self.lua.eval("type")(self._api()[name]), "function")
        self.assertFalse(self._api().IsEnabled())

    def test_no_market_is_tracked(self):
        self._g("FireInitialize")()
        self._g("PlaceUnit")(101, 1, 1800, 2400, 0)
        self._g("FireUnitFinished")(101, 1, 0)
        self.assertEqual(self._api().MarketCount(0), 0)

    def test_exchange_is_refused(self):
        self._g("FireInitialize")()
        self._g("SetStock")(0, "food", 500)
        result = _lua_to_py(self.lua, self._api().Exchange(0, "food", "iron", 20))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "market-disabled")
        self.assertEqual(self._stock(0, "food"), 500)
        self.assertEqual(self._stock(0, "iron"), 0)

    def test_validate_is_refused(self):
        self._g("FireInitialize")()
        result = _lua_to_py(self.lua, self._api().ValidateTrade(0, "food", "iron", 20))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "market-disabled")

    def test_gameframe_mints_nothing(self):
        self._g("FireInitialize")()
        self._g("SetHaulSummary")(0, 5)
        self._g("FireGameFrame")(30)
        self.assertEqual(self._api().RouteBonusTotal(0), 0)
        self.assertEqual(len(_lua_to_py(self.lua, self._g("DEPOSIT_CALLS"))), 0)


if __name__ == "__main__":
    unittest.main()
