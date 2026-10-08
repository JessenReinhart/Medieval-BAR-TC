"""
Phase-3 Slice 4 tests: the road-build command (CMD_BUILD_ROAD = 371922,
params {x, z}), its validation matrix, deferred economy transaction, feature
creation, and refund-on-failure behaviour.

Covers the pure module (scripts/medieval_logistics.lua):
- COSTS.medieval_road = { wood = 5, stone = 2 }
- ROAD_PLACEMENT_MIN_SPACING = 32.0
- canPlaceRoad(x, z, existingRoads, stock, minSpacing)
- roadBuildQueueValidation(canAfford, costs)

And the real gadget (luarules/gadgets/gadget_medieval_logistics.lua):
- GG.MedievalLogistics.CanPlaceRoad / PlaceRoad
- map-bounds (off_map) rejection via Spring.GetMapSize
- AllowCommand intent recording + deferred GameFrame execution
- refund via GG.MedievalEconomy.Deposit when Spring.CreateFeature fails
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"


class TestRoadPlacementPure(unittest.TestCase):
    """Pure-module matrix for M.canPlaceRoad (no engine calls)."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _t(self, **kwargs):
        return self.lua.table(**kwargs)

    def _node(self, x, z):
        return self._t(x=x, z=z)

    def test_costs_and_spacing_constants(self):
        self.assertEqual(self.m.ROAD_PLACEMENT_MIN_SPACING, 32.0)
        costs = self.m.COSTS.medieval_road
        self.assertEqual(costs["wood"], 5)
        self.assertEqual(costs["stone"], 2)

    def test_get_cost_returns_copy_of_road_costs(self):
        costs = self.m.getCost("medieval_road")
        self.assertEqual(costs["wood"], 5)
        self.assertEqual(costs["stone"], 2)
        # Unknown defs have no cost entry
        self.assertIsNone(self.m.getCost("bigrock"))

    def test_can_place_road_affordable(self):
        stock = self._t(wood=5, stone=2)
        ok, reason = self.m.canPlaceRoad(2400, 3884, self.lua.table(), stock)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_can_place_road_unaffordable(self):
        # Missing wood (4 < 5) and missing stone both reject
        ok1, reason1 = self.m.canPlaceRoad(0, 0, self.lua.table(), self._t(wood=4, stone=2))
        self.assertFalse(ok1)
        self.assertEqual(reason1, "insufficient_resources")
        ok2, reason2 = self.m.canPlaceRoad(0, 0, self.lua.table(), self._t(wood=5, stone=1))
        self.assertFalse(ok2)
        self.assertEqual(reason2, "insufficient_resources")
        # Missing / nil stock also rejects
        ok3, reason3 = self.m.canPlaceRoad(0, 0, self.lua.table(), None)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "insufficient_resources")

    def test_can_place_road_too_close(self):
        roads = self._t(f1=self._node(2400, 3884))
        stock = self._t(wood=5, stone=2)
        # 20 elmos away < 32 spacing
        ok1, reason1 = self.m.canPlaceRoad(2420, 3884, roads, stock)
        self.assertFalse(ok1)
        self.assertEqual(reason1, "too_close")
        # Diagonal inside the radius circle is also too close
        ok2, reason2 = self.m.canPlaceRoad(2420, 3904, roads, stock)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "too_close")
        # Exactly on the boundary (32 <= 32) is rejected
        ok3, reason3 = self.m.canPlaceRoad(2432, 3884, roads, stock)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "too_close")

    def test_can_place_road_at_or_beyond_boundary_ok(self):
        roads = self._t(f1=self._node(2400, 3884))
        stock = self._t(wood=5, stone=2)
        ok, reason = self.m.canPlaceRoad(2433, 3884, roads, stock)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        # Far away is fine too
        ok2, reason2 = self.m.canPlaceRoad(3000, 4000, roads, stock)
        self.assertTrue(ok2)
        self.assertEqual(reason2, "ok")

    def test_can_place_road_non_numeric_coordinates(self):
        stock = self._t(wood=5, stone=2)
        roads = self.lua.table()
        for bad in [None, "bad", self.lua.eval("0/0"), self.lua.eval("math.huge")]:
            ok, reason = self.m.canPlaceRoad(bad, 3884, roads, stock)
            self.assertFalse(ok)
            self.assertEqual(reason, "invalid_coordinates")
            ok2, reason2 = self.m.canPlaceRoad(2400, bad, roads, stock)
            self.assertFalse(ok2)
            self.assertEqual(reason2, "invalid_coordinates")

    def test_can_place_road_custom_spacing(self):
        roads = self._t(f1=self._node(0, 0))
        stock = self._t(wood=5, stone=2)
        # 20 elmos is fine when spacing is raised to 10
        ok, _ = self.m.canPlaceRoad(20, 0, roads, stock, 10)
        self.assertTrue(ok)
        # 20 elmos is too close when spacing is raised to 20
        ok2, reason2 = self.m.canPlaceRoad(20, 0, roads, stock, 20)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "too_close")
        # Negative / non-numeric spacing is rejected
        ok3, reason3 = self.m.canPlaceRoad(20, 0, roads, stock, -5)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "invalid_spacing")
        ok4, reason4 = self.m.canPlaceRoad(20, 0, roads, stock, "x")
        self.assertFalse(ok4)
        self.assertEqual(reason4, "invalid_spacing")

    def test_can_place_road_ignores_malformed_existing(self):
        roads = self._t(
            junk1="string",
            junk2=42,
            junk3=self.lua.table(),
            bad_nan=self._node(self.lua.eval("0/0"), 0),
        )
        stock = self._t(wood=5, stone=2)
        # None of the malformed entries block placement near their nominal spot
        ok, reason = self.m.canPlaceRoad(0, 0, roads, stock)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        # nil roads table behaves as empty
        ok2, _ = self.m.canPlaceRoad(0, 0, None, stock)
        self.assertTrue(ok2)

    def test_road_build_queue_validation(self):
        self.assertEqual(self.m.roadBuildQueueValidation(True, self._t(wood=5)), "ok")
        self.assertEqual(
            self.m.roadBuildQueueValidation(False, self._t(wood=5)),
            "insufficient_resources",
        )
        self.assertEqual(self.m.roadBuildQueueValidation(True, None), "bad_costs")
        self.assertEqual(self.m.roadBuildQueueValidation(False, None), "bad_costs")


class TestRoadBuildGadget(unittest.TestCase):
    """REAL behavioural execution: runs the actual gadget file
    (luarules/gadgets/gadget_medieval_logistics.lua) inside lupa with stub
    Spring / VFS / GG / gadgetHandler / UnitDefs / FeatureDefs, then drives
    the real callins Initialize / AllowCommand / GameFrame / FeatureCreated
    and asserts the GG.MedievalLogistics road-build APIs."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        cls.lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        cls.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}           -- featureID -> { defID, x, z, team }
        TEAM_LIST = {0, 1}
        STOCK = { wood = 10, stone = 10 }
        TRANSACTS = {}          -- { { team, wood, stone }, ... }
        DEPOSITS = {}           -- { { team, resource, amount }, ... }
        CREATE_CALLS = {}       -- { { name, x, y, z }, ... }
        NEXT_FID = 9000
        FORCE_TRANSACT_FAIL = false
        gadget = {}             -- provided by the engine before gadget files load
        gadgetHandler = {
          IsSyncedCode = function() return true end,
          RegisterCMDID = function(cmdID) return true end,
          RegisterAllowCommand = function(cmdID) return true end,
        }
        CMD = { ANY = 31000 }
        GG = {}
        FeatureDefs = {
          [7] = { name = "medieval_road" },
          [8] = { name = "bigrock" },
        }
        UnitDefs = {
          [1] = { name = "medieval_villager" },
          [2] = { name = "medieval_infantry" },
        }
        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
          GetMapSize = function() return 5000, 5000 end,
          GetFeatureDefID = function(id)
            local f = FEATURES[id]
            if f then return f.defID end
          end,
          GetFeaturePosition = function(id)
            local f = FEATURES[id]
            if f then return f.x, 0, f.z end
          end,
          GetFeatureTeam = function(id)
            local f = FEATURES[id]
            if f then return f.team end
          end,
          GetGroundHeight = function(x, z) return 0 end,
          SetGameRulesParam = function(k, v) GAME_RULES[k] = v end,
          GetUnitPosition = function() return nil end,
          GetUnitHealth = function() return nil end,
          SetUnitMaxHealth = function() end,
          SetUnitHealth = function() end,
        }
        function defaultCreateFeature(name, x, y, z)
          table.insert(CREATE_CALLS, { name = name, x = x, y = y, z = z })
          NEXT_FID = NEXT_FID + 1
          return NEXT_FID
        end
        Spring.CreateFeature = defaultCreateFeature
        VFS = {
          -- Execute the REAL module files from the repo, like the engine does.
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }
        -- Economy stub: records transactions and refunds against STOCK ----------
        GG.MedievalEconomy = {
          GetStockpiles = function(team) return STOCK end,
          GetResource = function(team, r) return STOCK[r] or 0 end,
          CanAfford = function(team, costs)
            for r, amt in pairs(costs) do
              if (STOCK[r] or 0) < amt then return false end
            end
            return true
          end,
          Transact = function(team, costs)
            table.insert(TRANSACTS, { team = team, wood = costs.wood or 0, stone = costs.stone or 0 })
            if FORCE_TRANSACT_FAIL then return false end
            for r, amt in pairs(costs) do
              if (STOCK[r] or 0) < amt then return false end
            end
            for r, amt in pairs(costs) do
              STOCK[r] = STOCK[r] - amt
            end
            return true
          end,
          Deposit = function(team, resource, amount)
            table.insert(DEPOSITS, { team = team, resource = resource, amount = amount })
            STOCK[resource] = (STOCK[resource] or 0) + amount
          end,
        }
        -- Harness helpers -------------------------------------------------------
        function PlaceFeature(id, defID, x, z, team)
          FEATURES[id] = { defID = defID, x = x, z = z, team = team }
        end
        function FireInitialize() gadget:Initialize() end
        function FireFeatureCreated(id, allyTeam) gadget:FeatureCreated(id, allyTeam) end
        function FireFeatureDestroyed(id, allyTeam) gadget:FeatureDestroyed(id, allyTeam) end
        function FireAllowCommand(unitID, unitDefID, teamID, cmdID, params, opts)
          return gadget:AllowCommand(unitID, unitDefID, teamID, cmdID, params, opts)
        end
        function FireGameFrame(frame) gadget:GameFrame(frame) end
        -- Getters --------------------------------------------------------------
        function TransactCount() return #TRANSACTS end
        function DepositCount() return #DEPOSITS end
        function CreateCount() return #CREATE_CALLS end
        function LastTransact() return TRANSACTS[#TRANSACTS] end
        function LastCreate() return CREATE_CALLS[#CREATE_CALLS] end
        function GetStock() return STOCK end
        function SetStock(wood, stone) STOCK.wood = wood; STOCK.stone = stone end
        function ForceTransactFail(v) FORCE_TRANSACT_FAIL = v end
        function ResetRunState()
          ECHO_LINES = {}
          GAME_RULES = {}
          FEATURES = {}
          STOCK = { wood = 10, stone = 10 }
          TRANSACTS = {}
          DEPOSITS = {}
          CREATE_CALLS = {}
          NEXT_FID = 9000
          FORCE_TRANSACT_FAIL = false
          Spring.CreateFeature = defaultCreateFeature
        end
        -- Load the REAL gadget --------------------------------------------------
        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    def setUp(self):
        self.lua.globals().ResetRunState()
        self.lua.globals().FireInitialize()

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _register(self, fid, x, z, team):
        """Register a created feature with the gadget, like the engine would."""
        self._g("PlaceFeature")(fid, 7, float(x), float(z), team)
        self._g("FireFeatureCreated")(fid, 0)

    def _place_and_register(self, x, z, team=0):
        """PlaceRoad + engine-side FeatureCreated, returning (ok, fid)."""
        api = self._api()
        ok, fid = api.PlaceRoad(team, 1, x, z)
        if ok and fid:
            self._register(fid, x, z, team)
        return ok, fid

    def _echoes(self):
        return list(self._g("ECHO_LINES").values())

    # -- GG.MedievalLogistics.CanPlaceRoad matrix ---------------------------

    def test_can_place_road_affordable(self):
        api = self._api()
        ok, reason = api.CanPlaceRoad(0, 2400, 3884)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        # No transaction happens on a pure pre-check
        self.assertEqual(self._g("TransactCount")(), 0)

    def test_can_place_road_unaffordable(self):
        api = self._api()
        self._g("SetStock")(4, 2)
        ok, reason = api.CanPlaceRoad(0, 2400, 3884)
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_resources")
        self._g("SetStock")(5, 1)
        ok2, reason2 = api.CanPlaceRoad(0, 2400, 3884)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "insufficient_resources")

    def test_can_place_road_too_close(self):
        ok, fid = self._place_and_register(2400, 3884)
        self.assertTrue(ok)
        api = self._api()
        ok2, reason2 = api.CanPlaceRoad(0, 2420, 3884)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "too_close")
        # Far away from the existing road is fine
        ok3, reason3 = api.CanPlaceRoad(0, 2600, 3884)
        self.assertTrue(ok3)
        self.assertEqual(reason3, "ok")

    def test_can_place_road_non_numeric(self):
        api = self._api()
        ok, reason = api.CanPlaceRoad(0, None, 3884)
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_coordinates")
        ok2, reason2 = api.CanPlaceRoad(0, 2400, "bad")
        self.assertFalse(ok2)
        self.assertEqual(reason2, "invalid_coordinates")
        nan = self.lua.eval("0/0")
        ok3, reason3 = api.CanPlaceRoad(0, nan, 3884)
        self.assertFalse(ok3)
        self.assertIn(reason3, ("invalid_coordinates", "off_map"))

    def test_can_place_road_off_map(self):
        api = self._api()
        ok, reason = api.CanPlaceRoad(0, -1, 500)
        self.assertFalse(ok)
        self.assertEqual(reason, "off_map")
        ok2, reason2 = api.CanPlaceRoad(0, 5001, 500)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "off_map")
        ok3, reason3 = api.CanPlaceRoad(0, 500, -1)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "off_map")
        ok4, reason4 = api.CanPlaceRoad(0, 500, 5001)
        self.assertFalse(ok4)
        self.assertEqual(reason4, "off_map")
        # Boundary corners are still on the map
        ok5, reason5 = api.CanPlaceRoad(0, 0, 0)
        self.assertTrue(ok5)
        ok6, reason6 = api.CanPlaceRoad(0, 5000, 5000)
        self.assertTrue(ok6)
        self.assertEqual(reason6, "ok")

    # -- GG.MedievalLogistics.PlaceRoad -------------------------------------

    def test_place_road_happy_path_deducts_and_creates(self):
        api = self._api()
        ok, fid = api.PlaceRoad(0, 1, 2400, 3884)
        self.assertTrue(ok)
        self.assertIsInstance(int(fid), int)
        self.assertGreater(fid, 0)
        # The recorder saw the medieval_road cost table
        self.assertEqual(self._g("TransactCount")(), 1)
        t = self._g("LastTransact")()
        self.assertEqual(t["team"], 0)
        self.assertEqual(t["wood"], 5)
        self.assertEqual(t["stone"], 2)
        # Stock was actually debited 10/10 -> 5/8
        stock = self._g("GetStock")()
        self.assertEqual(stock["wood"], 5)
        self.assertEqual(stock["stone"], 8)
        # Feature creation was requested with the right def name and position
        self.assertEqual(self._g("CreateCount")(), 1)
        c = self._g("LastCreate")()
        self.assertEqual(c["name"], "medieval_road")
        self.assertEqual(c["x"], 2400)
        self.assertEqual(c["y"], 0)
        self.assertEqual(c["z"], 3884)
        # Once the engine reports FeatureCreated the road is tracked
        self._register(fid, 2400, 3884, 0)
        self.assertEqual(api.RoadCount(0), 1)
        self.assertTrue(api.PointOnRoadNetwork(0, 2400, 3884))
        self.assertIn("PHASE3 PROBE road-cmd placed team=0 reason=ok ftr=%d x=2400 z=3884" % int(fid), self._echoes())

    def test_place_road_refusal_leaves_resources_and_map_untouched(self):
        api = self._api()
        # Unaffordable
        self._g("SetStock")(4, 2)
        ok, reason = api.PlaceRoad(0, 1, 2400, 3884)
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_resources")
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        stock = self._g("GetStock")()
        self.assertEqual(stock["wood"], 4)
        self.assertEqual(stock["stone"], 2)
        # Off map
        self._g("SetStock")(10, 10)
        ok2, reason2 = api.PlaceRoad(0, 1, 5001, 5001)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "off_map")
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        # Non-numeric coordinates
        ok3, reason3 = api.PlaceRoad(0, 1, None, 3884)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "invalid_coordinates")
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        stock2 = self._g("GetStock")()
        self.assertEqual(stock2["wood"], 10)
        self.assertEqual(stock2["stone"], 10)

    def test_place_road_duplicate_inside_spacing_refused(self):
        ok, fid = self._place_and_register(2400, 3884)
        self.assertTrue(ok)
        api = self._api()
        before_transacts = self._g("TransactCount")()
        before_creates = self._g("CreateCount")()
        before_count = api.RoadCount(0)
        # 20 elmos from the existing road
        ok2, reason2 = api.PlaceRoad(0, 1, 2420, 3884)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "too_close")
        self.assertEqual(self._g("TransactCount")(), before_transacts)
        self.assertEqual(self._g("CreateCount")(), before_creates)
        self.assertEqual(api.RoadCount(0), before_count)
        # A placement outside the spacing succeeds
        ok3, fid3 = api.PlaceRoad(0, 1, 2600, 3884)
        self.assertTrue(ok3)
        self._register(fid3, 2600, 3884, 0)
        self.assertEqual(api.RoadCount(0), before_count + 1)

    def test_place_road_refund_when_create_feature_fails(self):
        api = self._api()
        self._g("Spring").CreateFeature = lambda *args: None
        ok, reason = api.PlaceRoad(0, 1, 2400, 3884)
        self.assertFalse(ok)
        self.assertEqual(reason, "create_failed")
        # The transaction was attempted once
        self.assertEqual(self._g("TransactCount")(), 1)
        # Refund deposits restore wood=5, stone=2 exactly
        self.assertEqual(self._g("DepositCount")(), 2)
        deposits = list(self._g("DEPOSITS").values())
        by_resource = {d["resource"]: d["amount"] for d in deposits}
        self.assertEqual(by_resource["wood"], 5)
        self.assertEqual(by_resource["stone"], 2)
        stock = self._g("GetStock")()
        self.assertEqual(stock["wood"], 10)
        self.assertEqual(stock["stone"], 10)
        # Nothing was placed
        self.assertEqual(api.RoadCount(0), 0)
        self.assertIn("PHASE3 PROBE road-cmd refused team=0 reason=create_failed", self._echoes())

    def test_place_road_rejected_when_transact_fails(self):
        api = self._api()
        self._g("ForceTransactFail")(True)
        ok, reason = api.PlaceRoad(0, 1, 2400, 3884)
        self.assertFalse(ok)
        self.assertEqual(reason, "insufficient_resources")
        # Transact was attempted, but nothing was created or refunded
        self.assertEqual(self._g("TransactCount")(), 1)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(self._g("DepositCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        stock = self._g("GetStock")()
        self.assertEqual(stock["wood"], 10)
        self.assertEqual(stock["stone"], 10)

    def test_can_place_road_mirrors_refusal_reasons(self):
        api = self._api()
        cases = [
            (-1, 500, "off_map"),
            (5001, 500, "off_map"),
            (None, 3884, "invalid_coordinates"),
        ]
        for x, z, reason in cases:
            ok_c, reason_c = api.CanPlaceRoad(0, x, z)
            self.assertFalse(ok_c)
            ok_p, reason_p = api.PlaceRoad(0, 1, x, z)
            self.assertFalse(ok_p)
            self.assertEqual(reason_c, reason_p)
        # too_close mirrors after a first placement
        ok, fid = self._place_and_register(2400, 3884)
        self.assertTrue(ok)
        ok_c, reason_c = api.CanPlaceRoad(0, 2420, 3884)
        ok_p, reason_p = api.PlaceRoad(0, 1, 2420, 3884)
        self.assertFalse(ok_c)
        self.assertFalse(ok_p)
        self.assertEqual(reason_c, reason_p)
        self.assertEqual(reason_c, "too_close")
        # insufficient_resources mirrors on an empty stockpile
        self._g("SetStock")(0, 0)
        ok_c, reason_c = api.CanPlaceRoad(0, 3000, 4000)
        ok_p, reason_p = api.PlaceRoad(0, 1, 3000, 4000)
        self.assertFalse(ok_c)
        self.assertFalse(ok_p)
        self.assertEqual(reason_c, reason_p)
        self.assertEqual(reason_c, "insufficient_resources")

    # -- AllowCommand -> deferred GameFrame pipeline --------------------------

    def test_allow_command_requires_villager(self):
        params = self.lua.table(2400, 3884)
        # Non-villager issuer is rejected outright
        allowed = self._g("FireAllowCommand")(1, 2, 0, 371922, params, None)
        self.assertFalse(allowed)
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        # Modifier-heavy queueing is rejected too
        opts = self.lua.table(shift=True)
        allowed2 = self._g("FireAllowCommand")(1, 1, 0, 371922, params, opts)
        self.assertFalse(allowed2)
        # Unrelated command ids pass through untouched
        allowed3 = self._g("FireAllowCommand")(1, 1, 0, 20, params, None)
        self.assertTrue(allowed3)
        self.assertEqual(self._g("CreateCount")(), 0)

    def test_allow_command_queues_and_gameframe_executes(self):
        api = self._api()
        params = self.lua.table(2400, 3884)
        # AllowCommand consumes the order (returns false) and queues intent
        allowed = self._g("FireAllowCommand")(1, 1, 0, 371922, params, None)
        self.assertFalse(allowed)
        # Nothing executed yet: no transaction, no feature, no road
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        # The next GameFrame pass performs the transaction and creation
        self._g("FireGameFrame")(1)
        self.assertEqual(self._g("TransactCount")(), 1)
        self.assertEqual(self._g("CreateCount")(), 1)
        stock = self._g("GetStock")()
        self.assertEqual(stock["wood"], 5)
        self.assertEqual(stock["stone"], 8)
        # An empty GameFrame pass is a no-op
        before = self._g("CreateCount")()
        self._g("FireGameFrame")(2)
        self.assertEqual(self._g("CreateCount")(), before)

    def test_allow_command_refusal_does_not_queue(self):
        api = self._api()
        self._g("SetStock")(0, 0)
        params = self.lua.table(2400, 3884)
        allowed = self._g("FireAllowCommand")(1, 1, 0, 371922, params, None)
        self.assertFalse(allowed)
        self._g("FireGameFrame")(1)
        self.assertEqual(self._g("TransactCount")(), 0)
        self.assertEqual(self._g("CreateCount")(), 0)
        self.assertEqual(api.RoadCount(0), 0)
        self.assertIn("PHASE3 PROBE road-cmd refused team=0 reason=insufficient_resources", self._echoes())

    # -- Wiring ---------------------------------------------------------------

    def test_gadget_wiring_anchors(self):
        src = GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("CMD_BUILD_ROAD = 371922", src)
        self.assertIn('gadgetHandler:RegisterAllowCommand(CMD.ANY)', src)
        self.assertIn('Spring.CreateFeature("medieval_road"', src)
        self.assertIn("PHASE3 PROBE road-cmd placed", src)
        self.assertIn("PHASE3 PROBE road-cmd refused", src)


if __name__ == "__main__":
    unittest.main()