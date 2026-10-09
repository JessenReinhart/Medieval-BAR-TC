"""
Phase-4 Slice 5 tests: transport & hauler units (the supply cart).

Covers three layers, each against the real repository files:

1. `units/medieval_cart.lua` — identity (unarmed, mobile civilian), the
   `customparams` that bind it to the hauling policy (`carry_capacity = 400`,
   `unit_role = "hauler"`) and its population contract: the cart is registered
   at 0 slots in `scripts/medieval_housing.lua` and pays no military upkeep in
   `scripts/medieval_recruitment.lua`.
2. Haul policy — `scripts/medieval_haul.lua`: `canHaul` accepts the cart only,
   and `chooseHaulRoute` maps a surplus hub to a deficit hub, returning
   `{ from, to, resource, amount }` with `amount` clamped by the cart's carry
   capacity (and by HAUL_STEP / the available stock).
3. Gadget enforcement — `luarules/gadgets/gadget_medieval_hauling.lua`: hub and
   deficit detection pick the correct sink, completion records the route amount
   and increments `HaulSummary.delivered`, the Slice 6 road-speed mutator is
   applied to carts standing on roads using the existing
   `medieval_logistics.ROAD_SPEED_MULT` factor, and `HaulRoute` reflects the
   active route.

Economy note: the team stockpile is per-TEAM (gadget_medieval_economy keeps one
pool per team), so a same-team hub -> hub haul CONSERVES the pool. The gadget's
`completeHaul` therefore moves the per-hub storage ledger and never debits the
pool through `GG.MedievalEconomy.Transact` (only production chains spend).
`test_completion_conserves_the_shared_team_pool` pins that invariant.

Each test boots its OWN fresh Lua runtime (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
UNITS_DIR = ROOT / "units"
SCRIPTS_DIR = ROOT / "scripts"

CART_UNIT_PATH = UNITS_DIR / "medieval_cart.lua"
HAUL_PATH = SCRIPTS_DIR / "medieval_haul.lua"
LOGISTICS_PATH = SCRIPTS_DIR / "medieval_logistics.lua"
HOUSING_PATH = SCRIPTS_DIR / "medieval_housing.lua"
RECRUITMENT_PATH = SCRIPTS_DIR / "medieval_recruitment.lua"
HAUL_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_hauling.lua"

# Policy constants mirrored from scripts/medieval_haul.lua.
CART_UNIT_NAME = "medieval_cart"
DEFAULT_CART_CAPACITY = 400
HAUL_STEP = 25
DEFICIT_THRESHOLD = 80

# Slice 6 road-speed factor, reused (never re-declared) by the hauling gadget.
ROAD_SPEED_MULT = 1.5

# UnitDef ids used by the gadget harness stubs.
CART, LUMBER_CAMP, BLACKSMITH, GRANARY, VILLAGER, TOWN_CENTER = 1, 2, 3, 4, 5, 6
CART_SMALL = 7

# Unit ids used by the gadget harness stubs.
CART_ID, LUMBER_ID, SMITH_ID, TC_ID = 10, 101, 102, 103

# Order ids.
CMD_MOVE, CMD_STOP = 10, 0

# Cart def speed in elmos/sec (units/medieval_cart.lua: speed = 15).
CART_SPEED = 15.0


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


class TestSlice5CartUnitDef(unittest.TestCase):
    """The cart datadef: identity, carry tags and its zero-population contract."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        table = self.lua.execute(CART_UNIT_PATH.read_text(encoding="utf-8"))
        self.cart = _lua_to_py(self.lua, table[CART_UNIT_NAME])
        self.customparams = self.cart["customparams"]
        self.housing = self.lua.execute(HOUSING_PATH.read_text(encoding="utf-8"))
        self.recruit = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))
        self.haul = self.lua.execute(HAUL_PATH.read_text(encoding="utf-8"))

    # -- identity -------------------------------------------------------------

    def test_cart_identity(self):
        self.assertEqual(self.cart["name"], "Supply Cart")
        self.assertEqual(self.cart["category"], "LAND")
        self.assertEqual(self.cart["side"], "MEDIEVAL")
        self.assertTrue(self.cart["canMove"])
        self.assertEqual(self.cart["movementclass"], "TANK3")

    def test_cart_is_unarmed_and_cannot_build(self):
        self.assertFalse(self.cart["canAttack"])
        self.assertFalse(self.cart["canFight"])
        self.assertFalse(self.cart["builder"])

    # -- customparams ---------------------------------------------------------

    def test_cart_customparams_carry_capacity(self):
        self.assertEqual(self.customparams["carry_capacity"], DEFAULT_CART_CAPACITY)
        self.assertEqual(self.customparams["carry_capacity"], 400)

    def test_cart_customparams_role_is_hauler(self):
        self.assertEqual(self.customparams["unit_role"], "hauler")
        self.assertEqual(self.customparams["unitgroup"], "civilian")
        self.assertNotIn("equipment_needed", self.customparams)

    def test_cart_capacity_matches_the_haul_default(self):
        # Cross-layer pin: the datadef tag and the pure-module fallback agree, so
        # a cart whose customparams are unreadable still hauls its real capacity.
        self.assertEqual(
            self.customparams["carry_capacity"], self.haul.DEFAULT_CART_CAPACITY
        )
        self.assertEqual(self.haul.CART_UNIT_NAME, CART_UNIT_NAME)

    # -- population -----------------------------------------------------------

    def test_cart_consumes_no_population(self):
        self.assertEqual(self.housing.unitConsumesPop(CART_UNIT_NAME), 0)
        # 0 is truthy in Lua, so the explicit registry entry must win over the
        # `popUnits[defName] or 0` fallback rather than reading as "unregistered".
        self.assertFalse(self.housing.unitConsumesPop(CART_UNIT_NAME))

    def test_cart_pays_no_military_upkeep(self):
        self.assertFalse(self.recruit.isMilitary(CART_UNIT_NAME))
        self.assertEqual(self.recruit.upkeepFor(CART_UNIT_NAME), 0)

    def test_cart_zero_pop_is_not_a_free_pass_for_other_units(self):
        # Guard against the cart entry accidentally zeroing the whole registry.
        self.assertEqual(self.housing.unitConsumesPop("medieval_villager"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_knight"), 2)


class TestSlice5HaulPolicy(unittest.TestCase):
    """Pure-module haul checks against scripts/medieval_haul.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(HAUL_PATH.read_text(encoding="utf-8"))

    # -- harness helpers ------------------------------------------------------

    def _hubs(self, *pairs):
        """Build the gadget-shaped hub map: hubID -> { name = defName }."""
        out = self.lua.table()
        for hub_id, name in pairs:
            out[hub_id] = self.lua.table(name=name)
        return out

    def _stocks(self, wood=0, iron=0):
        return self.lua.table(wood=wood, iron=iron)

    def _route(self, hubs, stocks, capacity=DEFAULT_CART_CAPACITY):
        value = self.m.chooseHaulRoute(0, 1, hubs, stocks, capacity)
        return _lua_to_py(self.lua, value)

    # -- constants ------------------------------------------------------------

    def test_haul_constants(self):
        self.assertEqual(self.m.CART_UNIT_NAME, CART_UNIT_NAME)
        self.assertEqual(self.m.DEFAULT_CART_CAPACITY, DEFAULT_CART_CAPACITY)
        self.assertEqual(self.m.HAUL_STEP, HAUL_STEP)
        self.assertEqual(self.m.DEFICIT_THRESHOLD, DEFICIT_THRESHOLD)
        self.assertLess(self.m.HAUL_STEP, self.m.DEFICIT_THRESHOLD)

    # -- canHaul --------------------------------------------------------------

    def test_can_haul_accepts_the_cart_only(self):
        self.assertTrue(self.m.canHaul(0, 1, CART_UNIT_NAME))
        self.assertTrue(self.m.canHaul(3, 77, CART_UNIT_NAME))

    def test_can_haul_rejects_every_other_def(self):
        for name in ("medieval_villager", "medieval_infantry", "medieval_blacksmith"):
            self.assertFalse(self.m.canHaul(0, 1, name))

    def test_can_haul_rejects_malformed_arguments(self):
        # A pure module cannot resolve a unit id to a def, so a nil name denies.
        self.assertFalse(self.m.canHaul(0, 1, None))
        self.assertFalse(self.m.canHaul(None, 1, CART_UNIT_NAME))
        self.assertFalse(self.m.canHaul(-1, 1, CART_UNIT_NAME))
        self.assertFalse(self.m.canHaul(0, None, CART_UNIT_NAME))
        self.assertFalse(self.m.canHaul(0, 1, 42))

    # -- clampCapacity --------------------------------------------------------

    def test_clamp_capacity(self):
        self.assertEqual(self.m.clampCapacity(400), 400)
        self.assertEqual(self.m.clampCapacity(12.9), 12)
        self.assertEqual(self.m.clampCapacity(0), 0)
        self.assertEqual(self.m.clampCapacity(-5), 0)
        # Invalid input falls back to the cart default rather than to zero.
        self.assertEqual(self.m.clampCapacity(None), DEFAULT_CART_CAPACITY)
        self.assertEqual(self.m.clampCapacity("big"), DEFAULT_CART_CAPACITY)

    # -- chooseHaulRoute ------------------------------------------------------

    def test_choose_route_maps_a_surplus_hub_to_a_deficit_hub(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        route = self._route(hubs, self._stocks(wood=40))
        self.assertEqual(
            route,
            {
                "from": LUMBER_ID,
                "to": SMITH_ID,
                "resource": "wood",
                "amount": HAUL_STEP,
            },
        )

    def test_choose_route_prefers_the_dedicated_source_hub(self):
        # The town centre also supplies wood generically, but the lumber camp is
        # the DEDICATED dropoff and must win.
        hubs = self._hubs(
            (TC_ID, "medieval_town_center"),
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        route = self._route(hubs, self._stocks(wood=40))
        self.assertEqual(route["from"], LUMBER_ID)
        self.assertEqual(route["to"], SMITH_ID)

    def test_choose_route_falls_back_to_a_generic_storehouse(self):
        hubs = self._hubs(
            (TC_ID, "medieval_town_center"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        route = self._route(hubs, self._stocks(wood=40))
        self.assertEqual(route["from"], TC_ID)
        self.assertEqual(route["to"], SMITH_ID)

    def test_amount_is_clamped_by_carry_capacity(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        stocks = self._stocks(wood=40)
        # Capacity below HAUL_STEP wins; capacity above it does not raise the step.
        self.assertEqual(self._route(hubs, stocks, 10)["amount"], 10)
        self.assertEqual(self._route(hubs, stocks, 24)["amount"], 24)
        self.assertEqual(self._route(hubs, stocks, 400)["amount"], HAUL_STEP)

    def test_amount_is_clamped_by_the_available_stock(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        # 26 in the pool -> only 25 leaves, never more than the surplus chunk.
        self.assertEqual(self._route(hubs, self._stocks(wood=26))["amount"], HAUL_STEP)

    def test_no_route_when_the_pool_is_not_in_deficit(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        # At or above DEFICIT_THRESHOLD the sink is considered stocked.
        self.assertIsNone(self._route(hubs, self._stocks(wood=DEFICIT_THRESHOLD)))
        self.assertIsNone(self._route(hubs, self._stocks(wood=500)))

    def test_no_route_without_a_surplus_chunk(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        self.assertIsNone(self._route(hubs, self._stocks(wood=0)))
        self.assertIsNone(self._route(hubs, self._stocks(wood=HAUL_STEP - 1)))
        self.assertIsNone(self._route(hubs, self._stocks(wood=None)))

    def test_no_route_without_hubs_or_with_zero_capacity(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        self.assertIsNone(self._route(self._hubs(), self._stocks(wood=40)))
        self.assertIsNone(self._route(hubs, self._stocks(wood=40), 0))
        # A lone source hub has no sink to drive to.
        self.assertIsNone(
            self._route(self._hubs((LUMBER_ID, "medieval_lumber_camp")), self._stocks(wood=40))
        )

    def test_resource_order_prefers_wood_over_iron(self):
        hubs = self._hubs(
            (LUMBER_ID, "medieval_lumber_camp"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        # Both resources are in the deficit band; RESOURCE_ORDER puts wood first.
        route = self._route(hubs, self._stocks(wood=40, iron=40))
        self.assertEqual(route["resource"], "wood")

    def test_iron_route_when_wood_is_stocked(self):
        hubs = self._hubs(
            (TC_ID, "medieval_town_center"),
            (SMITH_ID, "medieval_blacksmith"),
        )
        route = self._route(hubs, self._stocks(wood=500, iron=40))
        self.assertEqual(route["resource"], "iron")
        self.assertEqual(route["to"], SMITH_ID)

    def test_collect_hubs_drops_non_hub_entries(self):
        hubs = self.lua.table()
        hubs[LUMBER_ID] = self.lua.table(name="medieval_lumber_camp")
        hubs[SMITH_ID] = self.lua.table(name="medieval_blacksmith")
        hubs[55] = self.lua.table(name="medieval_house")   # not a hub
        hubs[56] = "garbage"                               # malformed record
        hubs[57] = self.lua.table(name="medieval_granary")
        collected = _lua_to_py(self.lua, self.m.collectHubs(hubs))
        # Sorted by hub rank: granary (2) < lumber camp (3) < blacksmith (4).
        self.assertEqual([rec["id"] for rec in collected], [57, LUMBER_ID, SMITH_ID])

    def test_collect_hubs_is_empty_for_invalid_input(self):
        # An empty Lua array converts to an empty Python dict (no integer keys).
        self.assertEqual(len(_lua_to_py(self.lua, self.m.collectHubs(None))), 0)
        self.assertEqual(len(_lua_to_py(self.lua, self.m.collectHubs("nope"))), 0)

    def test_hub_rank_is_deterministic(self):
        self.assertEqual(self.m.hubRank("medieval_town_center"), 1)
        self.assertLess(
            self.m.hubRank("medieval_lumber_camp"),
            self.m.hubRank("medieval_blacksmith"),
        )
        self.assertEqual(self.m.hubRank("medieval_house"), len(self.m.HUB_NAMES) + 1)


class TestSlice5HaulingGadget(unittest.TestCase):
    """Gadget-level Slice 5 in a fresh per-test Lua VM with engine stubs."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        # Read the live road-speed factor from the module the gadget reuses, so
        # the mutator assertion cannot drift from a hardcoded copy.
        self.logistics = self.lua.execute(LOGISTICS_PATH.read_text(encoding="utf-8"))
        g = self.lua.globals()
        g.GADGET_SRC = HAUL_GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.CART = CART
        g.CART_SMALL = CART_SMALL
        g.LUMBER_CAMP = LUMBER_CAMP
        g.BLACKSMITH = BLACKSMITH
        g.GRANARY = GRANARY
        g.VILLAGER = VILLAGER
        g.TOWN_CENTER = TOWN_CENTER
        g.CART_ID = CART_ID
        g.LUMBER_ID = LUMBER_ID
        g.SMITH_ID = SMITH_ID
        g.TC_ID = TC_ID
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        ORDERS = {}
        SET_CALLS = {}
        TRANSACT_CALLS = {}
        ON_ROAD = {}
        UNITS = {}
        STOCKPILES = {}
        TEAM_LIST = {0, 1}
        gadget = {}
        gadgetHandler = {
          IsSyncedCode = function() return true end,
        }
        CMD = { MOVE = 10, STOP = 0 }
        GG = {}

        UnitDefs = {
          [CART]        = { name = "medieval_cart", speed = 15,
                            customParams = { carry_capacity = 400, unit_role = "hauler" } },
          [CART_SMALL]  = { name = "medieval_cart", speed = 15,
                            customParams = { carry_capacity = 10 } },
          [LUMBER_CAMP] = { name = "medieval_lumber_camp" },
          [BLACKSMITH]  = { name = "medieval_blacksmith" },
          [GRANARY]     = { name = "medieval_granary" },
          [VILLAGER]    = { name = "medieval_villager", speed = 12 },
          [TOWN_CENTER] = { name = "medieval_town_center" },
        }

        local MOVE_CTRL = {
          SetGroundMoveTypeData = function(unitID, data)
            table.insert(SET_CALLS, {
              unitID = unitID, maxSpeed = data.maxSpeed,
              maxWantedSpeed = data.maxWantedSpeed,
            })
            return 1
          end,
        }

        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
          GetAllUnits = function()
            local out = {}
            for id in pairs(UNITS) do table.insert(out, id) end
            table.sort(out)
            return out
          end,
          GetUnitDefID = function(id)
            local u = UNITS[id]
            return u and u.defID or nil
          end,
          GetUnitTeam = function(id)
            local u = UNITS[id]
            return u and u.team or nil
          end,
          GetUnitPosition = function(id)
            local u = UNITS[id]
            if u then return u.x, 0, u.z end
            return nil
          end,
          GiveOrderToUnit = function(id, cmd, params, opts)
            table.insert(ORDERS, { unitID = id, cmd = cmd, params = params, opts = opts })
            return true
          end,
          MoveCtrl = MOVE_CTRL,
        }

        -- Slice 6 API the hauling gadget reuses for the road-speed mutator.
        GG.MedievalLogistics = {
          IsOnRoad = function(teamID, unitID) return ON_ROAD[unitID] == true end,
        }
        -- Economy stub: GetStockpiles drives deficit detection, Transact is the
        -- only pool mutation entry point (and must not be called by a haul).
        GG.MedievalEconomy = {
          GetStockpiles = function(teamID)
            local s = STOCKPILES[teamID]
            if not s then return nil end
            return s
          end,
          Transact = function(teamID, costs)
            table.insert(TRANSACT_CALLS, { teamID = teamID, costs = costs })
            return true
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

        -- Harness helpers ------------------------------------------------------
        function PlaceUnit(id, defID, x, z, team)
          UNITS[id] = { defID = defID, x = x, z = z, team = team }
        end
        function MoveUnit(id, x, z)
          local u = UNITS[id]
          if u then u.x, u.z = x, z end
        end
        function RemoveUnit(id) UNITS[id] = nil end
        function SetStocks(team, wood, iron)
          STOCKPILES[team] = { wood = wood, iron = iron }
        end
        function StockOf(team, resource)
          local s = STOCKPILES[team]
          if not s then return 0 end
          return s[resource] or 0
        end
        function SetOnRoad(id, value) ON_ROAD[id] = value end
        function GadgetInfo() return gadget:GetInfo() end
        function FireInitialize() gadget:Initialize() end
        function FireUnitFinished(id, defID, team) gadget:UnitFinished(id, defID, team) end
        function FireUnitTaken(id, defID, oldTeam, newTeam)
          gadget:UnitTaken(id, defID, oldTeam, newTeam)
        end
        function FireUnitGiven(id, defID, newTeam, oldTeam)
          gadget:UnitGiven(id, defID, newTeam, oldTeam)
        end
        function FireTeamDied(team) gadget:TeamDied(team) end
        function FireGameFrame(frame) gadget:GameFrame(frame) end
        function RouteFor(team, cartID) return GG.MedievalLogistics.HaulRoute(team, cartID) end
        function SummaryFor(team) return GG.MedievalLogistics.HaulSummary(team) end
        function OrdersFor(unitID)
          local out = {}
          for _, o in ipairs(ORDERS) do
            if o.unitID == unitID then table.insert(out, o) end
          end
          return out
        end
        function HasEcho(fragment)
          for _, line in ipairs(ECHO_LINES) do
            if string.find(line, fragment, 1, true) then return true end
          end
          return false
        end
        function EchoLines() return ECHO_LINES end
        function TransactCalls() return TRANSACT_CALLS end
        function SpeedSets() return SET_CALLS end

        assert(load(GADGET_SRC, "@gadget_medieval_hauling.lua", "t", _G))()
        """)
        self._g("FireInitialize")()

    # -- harness accessors ----------------------------------------------------

    def _g(self, name):
        return self.lua.globals()[name]

    def _place(self, unit_id, def_id, x, z, team=0):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team)

    def _finish(self, unit_id, def_id, team=0):
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _summary(self, team=0):
        return _lua_to_py(self.lua, self._g("SummaryFor")(team))

    def _route(self, team=0, cart_id=CART_ID):
        return _lua_to_py(self.lua, self._g("RouteFor")(team, cart_id))

    def _orders(self, unit_id):
        return _lua_to_py(self.lua, self._g("OrdersFor")(unit_id))

    def _speed_sets(self):
        return _lua_to_py(self.lua, self._g("SpeedSets")())

    def _setup_haul(self, cart_def=CART, wood=40.0, cart_id=CART_ID, cart_at=(1000, 1000)):
        """Cart + dedicated wood source + blacksmith sink, all finished.

        The cart defaults to the source hub's tile, so the very first decision
        pass assigns a route AND advances the cart to the sink phase in the same
        frame. Pass `cart_at` to park it away from both hubs instead.
        """
        self._place(cart_id, cart_def, cart_at[0], cart_at[1])
        self._place(LUMBER_ID, LUMBER_CAMP, 1000, 1000)
        self._place(SMITH_ID, BLACKSMITH, 1200, 1000)
        self._g("SetStocks")(0, float(wood), 0.0)
        self._finish(cart_id, cart_def)
        self._finish(LUMBER_ID, LUMBER_CAMP)
        self._finish(SMITH_ID, BLACKSMITH)

    # -- gadget metadata ------------------------------------------------------

    def test_gadget_getinfo_is_the_hauling_gadget(self):
        info = _lua_to_py(self.lua, self._g("GadgetInfo")())
        self.assertEqual(info["name"], "Medieval Hauling")
        self.assertTrue(info["enabled"])
        self.assertEqual(info["layer"], 4)

    # -- tracking / summary ---------------------------------------------------

    def test_hub_and_cart_tracking_in_summary(self):
        self._setup_haul()
        summary = self._summary()
        self.assertEqual(summary["carts"], 1)
        self.assertEqual(summary["hubs"], 2)
        self.assertEqual(summary["routesAssigned"], 0)
        self.assertEqual(summary["delivered"], 0)

    def test_non_hub_civilian_units_are_not_tracked(self):
        self._place(900, VILLAGER, 1500, 1500)
        self._finish(900, VILLAGER)
        self._place(901, GRANARY, 1600, 1600)
        self._finish(901, GRANARY)
        summary = self._summary()
        self.assertEqual(summary["carts"], 0)
        # The granary is a hub (source), but not a cart.
        self.assertEqual(summary["hubs"], 1)

    # -- (a) hub / deficit detection ------------------------------------------

    def test_deficit_detection_picks_the_sink_hub(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        route = self._route()
        self.assertIsNotNone(route)
        self.assertEqual(route["from"], LUMBER_ID)
        self.assertEqual(route["to"], SMITH_ID)
        self.assertEqual(route["resource"], "wood")
        self.assertEqual(self._summary()["routesAssigned"], 1)

    def test_deficit_detection_prefers_the_dedicated_source(self):
        # Town centre (generic wood source) + lumber camp (dedicated) + sink.
        self._place(CART_ID, CART, 1000, 1000)
        self._place(TC_ID, TOWN_CENTER, 1400, 1000)
        self._place(LUMBER_ID, LUMBER_CAMP, 1000, 1000)
        self._place(SMITH_ID, BLACKSMITH, 1200, 1000)
        self._g("SetStocks")(0, 40.0, 0.0)
        for unit_id, def_id in (
            (CART_ID, CART), (TC_ID, TOWN_CENTER), (LUMBER_ID, LUMBER_CAMP), (SMITH_ID, BLACKSMITH)
        ):
            self._finish(unit_id, def_id)
        self._g("FireGameFrame")(30)
        self.assertEqual(self._route()["from"], LUMBER_ID)

    def test_no_route_when_the_pool_is_stocked(self):
        self._setup_haul(wood=DEFICIT_THRESHOLD)
        self._g("FireGameFrame")(30)
        self.assertIsNone(self._route())
        self.assertEqual(self._summary()["routesAssigned"], 0)

    def test_no_route_without_a_sink_hub(self):
        self._place(CART_ID, CART, 1000, 1000)
        self._place(LUMBER_ID, LUMBER_CAMP, 1000, 1000)
        self._g("SetStocks")(0, 40.0, 0.0)
        self._finish(CART_ID, CART)
        self._finish(LUMBER_ID, LUMBER_CAMP)
        self._g("FireGameFrame")(30)
        self.assertIsNone(self._route())

    def test_assignment_orders_the_cart_to_the_source_hub(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        orders = self._orders(CART_ID)
        # runTeamHaul runs once per team and its advance pass iterates the shared
        # job table, so the cart is ordered to the source and then, in the same
        # frame, advanced to the sink it is already standing next to.
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]["cmd"], CMD_MOVE)
        self.assertAlmostEqual(orders[0]["params"][0], 1000.0)  # lumber camp x
        self.assertAlmostEqual(orders[0]["params"][2], 1000.0)  # lumber camp z
        self.assertAlmostEqual(orders[1]["params"][0], 1200.0)  # blacksmith x
        self.assertAlmostEqual(orders[1]["params"][2], 1000.0)  # blacksmith z

    def test_capacity_clamps_the_assigned_amount(self):
        # A cart whose customparams carry_capacity is 10 hauls 10, not HAUL_STEP.
        self._setup_haul(cart_def=CART_SMALL)
        self._g("FireGameFrame")(30)
        self.assertEqual(self._route()["amount"], 10)

    # -- (d) HaulRoute reflects the active route -------------------------------

    def test_haul_route_is_nil_before_assignment(self):
        self._setup_haul()
        self.assertIsNone(self._route())
        self.assertIsNone(self._route(cart_id=999))

    def test_haul_route_is_scoped_to_the_owning_team(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        self.assertIsNotNone(self._route(team=0))
        self.assertIsNone(self._route(team=1))

    def test_haul_route_matches_the_pure_module_decision(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        route = self._route()
        self.assertEqual(
            route,
            {
                "from": LUMBER_ID,
                "to": SMITH_ID,
                "resource": "wood",
                "amount": HAUL_STEP,
            },
        )

    # -- (b) completion -------------------------------------------------------

    def test_completion_delivers_the_route_amount(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)          # assign: cart heads to the source
        self._g("FireGameFrame")(60)          # arrive at source -> phase to_sink
        self._g("MoveUnit")(CART_ID, 1200.0, 1000.0)
        # Stock the pool so no replacement route is chosen after delivery, which
        # would otherwise mask the cleared job.
        self._g("SetStocks")(0, 200.0, 0.0)
        self._g("FireGameFrame")(90)          # arrive at sink -> completeHaul

        summary = self._summary()
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(summary["deficitsResolved"], 1)
        self.assertEqual(summary["routesAssigned"], 1)
        # The deterministic completion log carries the transferred amount.
        self.assertTrue(self._g("HasEcho")("PHASE4 HAUL route team=0"))
        self.assertTrue(self._g("HasEcho")("amount=25"))
        self.assertTrue(self._g("HasEcho")("kind=wood"))

    def test_completion_is_idempotent_per_route(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        self._g("FireGameFrame")(60)
        self._g("MoveUnit")(CART_ID, 1200.0, 1000.0)
        self._g("SetStocks")(0, 200.0, 0.0)
        self._g("FireGameFrame")(90)
        self._g("FireGameFrame")(120)
        self._g("FireGameFrame")(150)
        self.assertEqual(self._summary()["delivered"], 1)

    def test_completion_conserves_the_shared_team_pool(self):
        # The pool is per-TEAM, so a same-team hub -> hub haul must not debit it:
        # completeHaul records the storage ledger only, never Transact.
        self._setup_haul()
        self._g("FireGameFrame")(30)
        self._g("FireGameFrame")(60)
        self._g("MoveUnit")(CART_ID, 1200.0, 1000.0)
        self._g("SetStocks")(0, 200.0, 0.0)
        self._g("FireGameFrame")(90)
        self.assertEqual(self._g("StockOf")(0, "wood"), 200.0)
        self.assertEqual(len(_lua_to_py(self.lua, self._g("TransactCalls")())), 0)

    def test_completion_stops_the_cart_and_clears_the_route(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        self._g("FireGameFrame")(60)
        self._g("MoveUnit")(CART_ID, 1200.0, 1000.0)
        self._g("SetStocks")(0, 200.0, 0.0)
        self._g("FireGameFrame")(90)
        self.assertIsNone(self._route())
        self.assertEqual(self._orders(CART_ID)[-1]["cmd"], CMD_STOP)

    def test_cart_mid_route_keeps_its_assignment(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        first = self._route()
        self._g("FireGameFrame")(60)  # now travelling to the sink
        self.assertEqual(self._route(), first)
        self.assertEqual(self._summary()["routesAssigned"], 1)

    def test_vanished_source_hub_releases_the_cart(self):
        # Park the cart away from both hubs so it stays in the to_source phase.
        self._setup_haul(cart_at=(1600, 1000))
        self._g("FireGameFrame")(30)
        self.assertIsNotNone(self._route())
        # The source is destroyed before the cart reaches it.
        self._g("RemoveUnit")(LUMBER_ID)
        self._g("FireGameFrame")(60)
        self.assertIsNone(self._route())

    # -- (c) road-speed mutator ------------------------------------------------

    def test_road_speed_mutator_uses_the_road_speed_factor(self):
        self._place(CART_ID, CART, 1000, 1000)
        self._g("SetOnRoad")(CART_ID, True)
        self._finish(CART_ID, CART)
        self._g("FireGameFrame")(15)
        sets = self._speed_sets()
        self.assertEqual(len(sets), 1)
        self.assertAlmostEqual(sets[0]["maxSpeed"], CART_SPEED * ROAD_SPEED_MULT)
        self.assertAlmostEqual(sets[0]["maxWantedSpeed"], CART_SPEED * ROAD_SPEED_MULT)
        # The multiplier is the existing Slice 6 factor, not a local copy.
        self.assertAlmostEqual(sets[0]["maxSpeed"] / CART_SPEED, self.logistics.ROAD_SPEED_MULT)
        self.assertEqual(self.logistics.ROAD_SPEED_MULT, ROAD_SPEED_MULT)

    def test_road_speed_mutator_off_road_keeps_the_base_speed(self):
        self._place(CART_ID, CART, 1000, 1000)
        self._g("SetOnRoad")(CART_ID, False)
        self._finish(CART_ID, CART)
        self._g("FireGameFrame")(15)
        sets = self._speed_sets()
        self.assertEqual(len(sets), 1)
        self.assertAlmostEqual(sets[0]["maxSpeed"], CART_SPEED)
        self.assertAlmostEqual(sets[0]["maxSpeed"] / CART_SPEED, 1.0)

    def test_road_speed_mutator_follows_a_cart_onto_a_road(self):
        self._place(CART_ID, CART, 1000, 1000)
        self._g("SetOnRoad")(CART_ID, False)
        self._finish(CART_ID, CART)
        self._g("FireGameFrame")(15)
        self.assertAlmostEqual(self._speed_sets()[0]["maxSpeed"], CART_SPEED)
        # The cart rolls onto a road: the next scan must raise it to the factor.
        self._g("SetOnRoad")(CART_ID, True)
        self._g("FireGameFrame")(30)
        self.assertEqual(len(self._speed_sets()), 2)
        self.assertAlmostEqual(
            self._speed_sets()[1]["maxSpeed"], CART_SPEED * ROAD_SPEED_MULT
        )

    def test_road_speed_scan_is_idempotent(self):
        self._place(CART_ID, CART, 1000, 1000)
        self._g("SetOnRoad")(CART_ID, True)
        self._finish(CART_ID, CART)
        self._g("FireGameFrame")(15)
        self._g("FireGameFrame")(30)
        self._g("FireGameFrame")(45)
        # Unchanged road status re-applies nothing.
        self.assertEqual(len(self._speed_sets()), 1)

    def test_destroyed_cart_drops_out_of_the_summary(self):
        self._setup_haul()
        self._g("RemoveUnit")(CART_ID)
        self._g("FireGameFrame")(30)
        self.assertEqual(self._summary()["carts"], 0)

    # -- lifecycle ------------------------------------------------------------

    def test_transfer_retracks_the_cart_on_the_new_team(self):
        self._setup_haul()
        self._g("FireUnitTaken")(CART_ID, CART, 0, 1)
        self._g("FireUnitGiven")(CART_ID, CART, 1, 0)
        self.assertEqual(self._summary(team=0)["carts"], 0)
        self.assertEqual(self._summary(team=1)["carts"], 1)

    def test_team_died_clears_haul_state(self):
        self._setup_haul()
        self._g("FireGameFrame")(30)
        self.assertEqual(self._summary()["routesAssigned"], 1)
        self._g("FireTeamDied")(0)
        summary = self._summary()
        # Carts, hubs and the in-flight job go away; the delivered/routes
        # counters live in the separate stats table and are preserved.
        self.assertEqual(summary["carts"], 0)
        self.assertEqual(summary["hubs"], 0)
        self.assertEqual(summary["routesAssigned"], 1)
        self.assertIsNone(self._route())


if __name__ == "__main__":
    unittest.main()
