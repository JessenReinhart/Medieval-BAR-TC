"""
Phase-3 Slice 5 tests: same-team road attachment for supply-endpoint
drop-off buildings (town_center, granary, lumber_camp), finished-building
tracking lifecycle, and the public building-connectivity APIs.

Policy under test (narrow and explicit):
- Buildings are UNITS (not features); roads are features whose owner comes
  from the sixth Spring.CreateFeature argument.
- isSupplyEndpointDef reads engine `customParams` with a lowercase
  `customparams` fallback and normalizes bool/string/number truth values.
  Internal identity never uses display names.
- AllowUnitCreation gates endpoint placement within BUILD_LINK_RADIUS = 64
  (inclusive) of a same-team road WHEN the team has roads. Zero-road
  bootstrap allows endpoints at any valid coordinates (not just the first).
  Nil coordinates bypass the gate (non-placement callin); invalid explicit
  coordinates (NaN/inf/non-number) are rejected.
- Finished endpoints are tracked in Initialize / UnitFinished / UnitGiven
  (completion is checked when transferred), and removed on UnitDestroyed /
  UnitTaken.
- GG.MedievalLogistics.BuildingConnected(teamID, unitID) and
  BuildingConnectivitySummary(teamID) recompute from the team's roads at
  query time (road removal is instant); unknown units / mismatched teams
  return false / zero totals.
- Existing tech and road-command logic is untouched; fortification cost
  gating still applies.

Each test boots its OWN fresh Lua runtime with the real module and gadget
files loaded (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"

# UnitDef ids used by the harness stubs
VILLAGER, INFANTRY, GRANARY, TOWN_CENTER, LUMBER_CAMP, WALL = 1, 2, 3, 4, 5, 6
ROAD_FDEF, ROCK_FDEF = 7, 8


class TestSlice5PureModule(unittest.TestCase):
    """Pure-module checks against scripts/medieval_logistics.lua."""

    def setUp(self):
        # Independent Lua runtime per test.
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def test_supply_endpoint_def_truth_matrix(self):
        t = self.lua.table
        # Boolean values via engine-style lowercase customparams
        self.assertTrue(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=True))))
        self.assertFalse(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=False))))
        # String flags, case-insensitive
        for truthy in ["true", "TRUE", "1", "yes"]:
            self.assertTrue(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=truthy))), truthy)
        for falsy in ["false", "FALSE", "0", "no", "", "garbage"]:
            self.assertFalse(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=falsy))), falsy)
        # Number flags
        self.assertTrue(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=1))))
        self.assertFalse(self.m.isSupplyEndpointDef(t(customparams=t(dropoff=0))))
        # Source-style mixed-case customParams with mixed-case key
        self.assertTrue(self.m.isSupplyEndpointDef(t(customParams=t(DropOff=True))))
        # Lowercase key inside source-style customParams
        self.assertTrue(self.m.isSupplyEndpointDef(t(customParams=t(dropoff=True))))
        # Missing / empty customparams
        self.assertFalse(self.m.isSupplyEndpointDef(t()))
        self.assertFalse(self.m.isSupplyEndpointDef(t(customparams=t())))
        self.assertFalse(self.m.isSupplyEndpointDef(None))

    def test_is_building_connected_inclusive_boundary_and_malformed(self):
        t = self.lua.table
        roads = t(n1=t(x=0, z=0))
        # Exactly 64 elmos is inclusive
        self.assertTrue(self.m.isBuildingConnected(roads, 64, 0))
        self.assertTrue(self.m.isBuildingConnected(roads, 0, 64))
        # Diagonal point at exactly 64 elmos (64/sqrt(2) per axis) is inclusive.
        diag = self.lua.eval("64 / math.sqrt(2)")
        self.assertTrue(self.m.isBuildingConnected(roads, diag, diag))
        # 64.0001 is not
        just_over = self.lua.eval("64.001")
        self.assertFalse(self.m.isBuildingConnected(roads, just_over, 0))
        # Custom radius honoured
        self.assertTrue(self.m.isBuildingConnected(roads, 30, 0, 30))
        self.assertFalse(self.m.isBuildingConnected(roads, 31, 0, 30))
        # Empty / malformed roads tables are never connected
        for bad in [t(), t(junk="str"), t(n=42), t(bad=t(x="a", z=0)),
                    t(nan=t(x=self.lua.eval("0/0"), z=0)),
                    t(inf=t(x=self.lua.eval("math.huge"), z=0))]:
            self.assertFalse(self.m.isBuildingConnected(bad, 0, 0))
        # NaN/inf query coordinates are invalid input
        nan = self.lua.eval("0/0")
        inf = self.lua.eval("math.huge")
        self.assertFalse(self.m.isBuildingConnected(roads, nan, 0))
        self.assertFalse(self.m.isBuildingConnected(roads, 0, nan))
        self.assertFalse(self.m.isBuildingConnected(roads, inf, 0))
        self.assertFalse(self.m.isBuildingConnected(roads, 0, -inf))
        # Non-table roads and non-finite radius
        self.assertFalse(self.m.isBuildingConnected(None, 0, 0))
        self.assertFalse(self.m.isBuildingConnected(roads, 0, 0, nan))


class TestSlice5Gadget(unittest.TestCase):
    """Real gadget execution in a fresh per-test Lua VM with engine stubs."""

    def setUp(self):
        # A completely fresh Lua runtime per test: no shared state.
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        self.lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        self.lua.globals().VILLAGER = VILLAGER
        self.lua.globals().INFANTRY = INFANTRY
        self.lua.globals().GRANARY = GRANARY
        self.lua.globals().TOWN_CENTER = TOWN_CENTER
        self.lua.globals().LUMBER_CAMP = LUMBER_CAMP
        self.lua.globals().WALL = WALL
        self.lua.globals().ROAD_FDEF = ROAD_FDEF
        self.lua.globals().ROCK_FDEF = ROCK_FDEF
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}   -- featureID -> { defID, x, z, team }
        UNITS = {}      -- unitID    -> { defID, x, z, team, progress }
        TEAM_LIST = {0, 1}
        STOCK = { wood = 200, stone = 200, iron = 200 }
        TRANSACTS = {}
        DEPOSITS = {}
        CREATE_CALLS = {}
        NEXT_FID = 9000
        gadget = {}
        gadgetHandler = {
          IsSyncedCode = function() return true end,
          RegisterCMDID = function() return true end,
          RegisterAllowCommand = function() return true end,
        }
        CMD = { ANY = 31000 }
        CMDTYPE = { ICON_MAP = 5 }
        GG = {}

        FeatureDefs = {
          [ROAD_FDEF] = { name = "medieval_road" },
          [ROCK_FDEF] = { name = "bigrock" },
        }
        UnitDefs = {
          [VILLAGER]     = { name = "medieval_villager" },
          [INFANTRY]     = { name = "medieval_infantry" },
          [GRANARY]      = { name = "medieval_granary", customParams = { dropoff = true } },
          [TOWN_CENTER]  = { name = "medieval_town_center", customparams = { dropoff = true } },
          [LUMBER_CAMP]  = { name = "medieval_lumber_camp", customParams = { dropoff = "true" } },
          [WALL]         = { name = "medieval_wall" },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
          GetMapSize = function() return 8000, 8000 end,
          GetGroundHeight = function() return 0 end,
          SetGameRulesParam = function(k, v) GAME_RULES[k] = v end,
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
          GetUnitHealth = function(id)
            local u = UNITS[id]
            if u then return 100, 100, false, 0, u.progress end
            return nil
          end,
          SetUnitMaxHealth = function() end,
          SetUnitHealth = function() end,
          GetFeatureDefID = function(id)
            local f = FEATURES[id]
            return f and f.defID or nil
          end,
          GetFeaturePosition = function(id)
            local f = FEATURES[id]
            if f then return f.x, 0, f.z end
            return nil
          end,
          GetFeatureTeam = function(id)
            local f = FEATURES[id]
            return f and f.team or nil
          end,
          -- Sixth argument is the owning team; registering a road feature fires
          -- FeatureCreated so the gadget's road table updates like in-engine.
          CreateFeature = function(name, x, y, z, heading, team)
            local defID
            for id, def in pairs(FeatureDefs) do
              if def.name == name then defID = id end
            end
            if not defID then return nil end
            NEXT_FID = NEXT_FID + 1
            local fid = NEXT_FID
            FEATURES[fid] = { defID = defID, x = x, z = z, team = team or 0 }
            gadget:FeatureCreated(fid, team or 0)
            return fid
          end,
        }

        GG.MedievalEconomy = {
          GetStockpiles = function() return STOCK end,
          GetResource = function(_, r) return STOCK[r] or 0 end,
          CanAfford = function(_, costs)
            for r, amt in pairs(costs) do
              if (STOCK[r] or 0) < amt then return false end
            end
            return true
          end,
          Transact = function(team, costs)
            table.insert(TRANSACTS, { team = team })
            for r, amt in pairs(costs) do
              if (STOCK[r] or 0) < amt then return false end
            end
            for r, amt in pairs(costs) do STOCK[r] = STOCK[r] - amt end
            return true
          end,
          Deposit = function(team, resource, amount)
            table.insert(DEPOSITS, { team = team, resource = resource })
            STOCK[resource] = (STOCK[resource] or 0) + amount
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
        function PlaceUnit(id, defID, x, z, team, progress)
          UNITS[id] = { defID = defID, x = x, z = z, team = team, progress = progress or 1 }
        end
        function RemoveUnit(id) UNITS[id] = nil end
        function SetUnitProgress(id, progress) UNITS[id].progress = progress end
        function FireInitialize() gadget:Initialize() end
        function FireUnitFinished(id, defID, team)
          local u = UNITS[id]
          -- In-engine UnitFinished only fires once build progress reaches 1.
          if u then u.progress = 1 end
          gadget:UnitFinished(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireUnitTaken(id, defID, oldTeam, newTeam)
          local u = UNITS[id]
          gadget:UnitTaken(id, defID or (u and u.defID), oldTeam, newTeam)
        end
        function FireUnitGiven(id, defID, newTeam, oldTeam)
          local u = UNITS[id]
          gadget:UnitGiven(id, defID or (u and u.defID), newTeam, oldTeam)
        end
        function FireUnitDestroyed(id, defID, team)
          local u = UNITS[id]
          gadget:UnitDestroyed(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireAllowUnitCreation(defID, builderID, team, x, z)
          return gadget:AllowUnitCreation(defID, builderID, team, x, 0, z, 0)
        end
        function FireFeatureDestroyed(id, allyTeam) gadget:FeatureDestroyed(id, allyTeam) end

        -- Load the REAL gadget -------------------------------------------------
        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _place_road(self, team, x, z):
        # Sixth-arg ownership: the stub fires FeatureCreated with the team.
        return self._g("Spring").CreateFeature("medieval_road", float(x), 0.0, float(z), 0, team)

    def _finish_unit(self, unit_id, def_id, team, x, z, progress=1):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team, progress)
        self._g("FireUnitFinished")(unit_id, def_id, team)


class TestEndpointPlacementPolicy(TestSlice5Gadget):
    """AllowUnitCreation road-attachment policy for drop-off endpoints."""

    def test_zero_road_bootstrap_allows_any_valid_position(self):
        api = self._api()
        # No roads for team 0: every finite position is allowed, not just one.
        for x, z in [(100, 100), (2500, 3500), (5000, 5000)]:
            self.assertTrue(api.CanPlaceRoad is not None)  # sanity: api live
            ok = self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, float(x), float(z))
            self.assertTrue(ok, (x, z))

    def test_endpoint_requires_same_team_road_within_64_inclusive(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        # Exactly 64 elmos east: inclusive boundary.
        self.assertTrue(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 1064.0, 1000.0))
        # Exactly 64 elmos on the diagonal is out (64*sqrt(2) > 64).
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 1048.0, 1048.0))
        # 65 elmos: rejected.
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 1065.0, 1000.0))
        # Far away: rejected.
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 2500.0, 3500.0))
        # Same distance but from the OTHER team's road: still rejected (team-local).
        self._place_road(1, 2500, 3500)
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 2500.0, 3500.0))

    def test_nil_coordinates_bypass_gate_but_invalid_explicit_coords_reject(self):
        self._place_road(0, 1000, 1000)  # team has roads, so gate would matter
        # Nil coordinates: non-placement callin, allowed.
        lua = self.lua
        nil_x = lua.eval("nil")
        self.assertTrue(
            self.lua.eval("function(def, b, t) return gadget:AllowUnitCreation(def, b, t, nil, nil, nil, 0) end")(
                GRANARY, VILLAGER, 0
            )
        )
        # NaN / inf / non-number explicit coordinates are rejected.
        nan = lua.eval("0/0")
        inf = lua.eval("math.huge")
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, nan, 1000.0))
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 1000.0, nan))
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, inf, 1000.0))
        self.assertFalse(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, "bad", 1000.0))

    def test_all_three_endpoint_defs_gated_and_non_endpoints_not_gated(self):
        self._place_road(0, 1000, 1000)
        for endpoint_def in [GRANARY, TOWN_CENTER, LUMBER_CAMP]:
            self.assertFalse(
                self._g("FireAllowUnitCreation")(endpoint_def, VILLAGER, 0, 2500.0, 3500.0),
                endpoint_def,
            )
            self.assertTrue(
                self._g("FireAllowUnitCreation")(endpoint_def, VILLAGER, 0, 1064.0, 1000.0),
                endpoint_def,
            )
        # A non-endpoint (wall) at the same far position is not road-gated; its
        # cost gate (preserved from previous slices) applies instead.
        self.assertTrue(self._g("FireAllowUnitCreation")(WALL, VILLAGER, 0, 2500.0, 3500.0))

    def test_fortification_cost_gate_still_applies(self):
        self._g("SetStockProxy") if False else None
        stock = self._g("GG").MedievalEconomy
        # medieval_wall costs { wood = 10, stone = 40 }
        self._g("DrainStock") if False else None
        # Drain the stockpile via Transact: spend everything.
        drain = self.lua.table(wood=200, stone=200, iron=200)
        self.assertTrue(stock.Transact(0, drain))
        self.assertFalse(self._g("FireAllowUnitCreation")(WALL, VILLAGER, 0, 2500.0, 3500.0))
        # Endpoints have no COSTS entry: unaffected by the empty stock.
        self.assertTrue(self._g("FireAllowUnitCreation")(GRANARY, VILLAGER, 0, 2500.0, 3500.0))


class TestBuildingTrackingLifecycle(TestSlice5Gadget):
    """Finished-endpoint tracking: Initialize / UnitFinished / UnitGiven /
    UnitDestroyed / UnitTaken and the public building APIs."""

    def test_unrelated_units_are_never_tracked(self):
        api = self._api()
        self._finish_unit(101, VILLAGER, 0, 1000.0, 1000.0)
        self._finish_unit(102, INFANTRY, 0, 1000.0, 1000.0)
        self.assertFalse(api.BuildingConnected(0, 101))
        self.assertFalse(api.BuildingConnected(0, 102))
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 0)
        self.assertEqual(s.connected, 0)
        self.assertEqual(s.disconnected, 0)

    def test_unit_finished_tracks_only_finished_endpoint(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        # Mid-construction unit: UnitFinished is not the right event; simulate
        # a transfer of an unfinished building instead via FireUnitGiven below.
        self._g("PlaceUnit")(201, GRANARY, 1060.0, 1000.0, 0, 0.5)
        self._g("FireUnitGiven")(201, GRANARY, 0, 0)
        self.assertFalse(api.BuildingConnected(0, 201))
        # Completed via UnitFinished: tracked.
        self._g("FireUnitFinished")(201, GRANARY, 0)
        self.assertTrue(api.BuildingConnected(0, 201))

    def test_unit_finished_beyond_radius_tracked_but_disconnected(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        self._finish_unit(202, GRANARY, 0, 2500.0, 3500.0)
        self.assertTrue(api.BuildingConnected(0, 202) is False)
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 1)
        self.assertEqual(s.connected, 0)
        self.assertEqual(s.disconnected, 1)

    def test_initialization_tracks_existing_finished_endpoints_only(self):
        api = self._api()
        # Existing world at Initialize: one finished granary, one unfinished.
        # (Initialize resets road state; roads are created after game init.)
        self._g("PlaceUnit")(301, GRANARY, 1060.0, 1000.0, 0, 1.0)
        self._g("PlaceUnit")(302, GRANARY, 1060.0, 1000.0, 0, 0.5)
        self._g("FireInitialize")()
        self._place_road(0, 1000, 1000)
        self.assertTrue(api.BuildingConnected(0, 301))
        self.assertFalse(api.BuildingConnected(0, 302))
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 1)
        self.assertEqual(s.connected, 1)

    def test_team_isolation_of_roads_and_buildings(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        self._finish_unit(401, GRANARY, 1, 1064.0, 1000.0)  # team 1 building
        # Team 1's building is NOT connected by team 0's road.
        self.assertFalse(api.BuildingConnected(1, 401))
        self.assertFalse(api.BuildingConnected(0, 401))  # mismatched team
        s1 = api.BuildingConnectivitySummary(1)
        self.assertEqual(s1.total, 1)
        self.assertEqual(s1.connected, 0)
        self.assertEqual(s1.disconnected, 1)
        s0 = api.BuildingConnectivitySummary(0)
        self.assertEqual(s0.total, 0)
        # Team 1 placing its own road connects it immediately.
        self._place_road(1, 1000, 1000)
        self.assertTrue(api.BuildingConnected(1, 401))

    def test_unit_taken_and_destroyed_remove_tracking(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        self._finish_unit(501, GRANARY, 0, 1060.0, 1000.0)
        self.assertTrue(api.BuildingConnected(0, 501))
        # Taken away: removed from the old team.
        self._g("FireUnitTaken")(501, GRANARY, 0, 1)
        self.assertFalse(api.BuildingConnected(0, 501))
        # Re-track under team 0 then destroy: removed.
        self._g("FireUnitFinished")(501, GRANARY, 0)
        self.assertTrue(api.BuildingConnected(0, 501))
        self._g("FireUnitDestroyed")(501, GRANARY, 0)
        self.assertFalse(api.BuildingConnected(0, 501))
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 0)

    def test_unit_given_retracks_under_receiving_team_only_if_finished(self):
        api = self._api()
        self._place_road(1, 2000, 2000)
        # Finished granary given from team 0 to team 1: tracked under team 1.
        self._finish_unit(601, GRANARY, 0, 2064.0, 2000.0)
        self.assertFalse(api.BuildingConnected(0, 601))
        self._g("FireUnitGiven")(601, GRANARY, 1, 0)
        self.assertTrue(api.BuildingConnected(1, 601))
        self.assertFalse(api.BuildingConnected(0, 601))
        # Unfinished granary given: NOT tracked.
        self._g("PlaceUnit")(602, GRANARY, 2064.0, 2000.0, 1, 0.5)
        self._g("FireUnitGiven")(602, GRANARY, 1, 0)
        self.assertFalse(api.BuildingConnected(1, 602))

    def test_road_removal_disconnects_instantly(self):
        api = self._api()
        fid = self._place_road(0, 1000, 1000)
        self._finish_unit(701, GRANARY, 0, 1060.0, 1000.0)
        self.assertTrue(api.BuildingConnected(0, 701))
        self._g("FireFeatureDestroyed")(fid, 0)
        self.assertFalse(api.BuildingConnected(0, 701))
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 1)
        self.assertEqual(s.connected, 0)
        self.assertEqual(s.disconnected, 1)

    def test_summary_counts_multiple_buildings(self):
        api = self._api()
        self._place_road(0, 1000, 1000)
        self._finish_unit(801, GRANARY, 0, 1060.0, 1000.0)      # connected
        self._finish_unit(802, TOWN_CENTER, 0, 3000.0, 3000.0)  # disconnected
        self._finish_unit(803, LUMBER_CAMP, 0, 1030.0, 1000.0)  # connected
        s = api.BuildingConnectivitySummary(0)
        self.assertEqual(s.total, 3)
        self.assertEqual(s.connected, 2)
        self.assertEqual(s.disconnected, 1)

    def test_unknown_unit_and_team_queries_return_false_or_zero(self):
        api = self._api()
        self.assertFalse(api.BuildingConnected(0, 999))
        self.assertFalse(api.BuildingConnected(7, 1))
        s = api.BuildingConnectivitySummary(7)
        self.assertEqual(s.total, 0)
        self.assertEqual(s.connected, 0)
        self.assertEqual(s.disconnected, 0)


if __name__ == "__main__":
    unittest.main()
