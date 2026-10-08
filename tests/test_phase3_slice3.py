"""
Phase-3 Slice 3 tests: road adjacency graph, connected components,
connectivity queries, and network summary statistics, plus gadget wiring.

Covers the pure module (scripts/medieval_road_graph.lua):
- LINK_RADIUS = 64.0
- planarDist(ax, az, bx, bz)
- buildEdges(roads, radius)
- adjacency(roads, radius)
- componentCount(roads, radius)
- componentOf(roads, key, radius)
- isConnected(roads, keyA, keyB, radius)
- connectedToNetwork(roads, x, z, radius)
- networkSummary(roads, radius)
"""

import math
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_road_graph.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"


class TestRoadGraphPure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _t(self, **kwargs):
        return self.lua.table(**kwargs)

    def _node(self, x, z):
        return self._t(x=x, z=z)

    def test_constants_and_planar_dist(self):
        self.assertEqual(self.m.LINK_RADIUS, 64.0)
        self.assertEqual(self.m.planarDist(0, 0, 30, 40), 50.0)
        self.assertEqual(self.m.planarDist(0, 0, 0, 0), 0.0)
        # Guards against nil / non-numbers: returns math.huge
        self.assertEqual(self.m.planarDist(None, 0, 10, 10), math.inf)
        self.assertEqual(self.m.planarDist(0, "bad", 10, 10), math.inf)

    def test_build_edges_basic_and_sort(self):
        # Two nodes within 64 elmos -> 1 edge
        roads = self._t(
            r1=self._node(0, 0),
            r2=self._node(50, 0),
        )
        edges = list(self.m.buildEdges(roads).values())
        self.assertEqual(len(edges), 1)
        e = edges[0]
        self.assertEqual(e["a"], "r1")
        self.assertEqual(e["b"], "r2")
        self.assertEqual(e["dist"], 50.0)

        # Two nodes beyond default radius -> 0 edges
        roads_far = self._t(
            r1=self._node(0, 0),
            r2=self._node(100, 0),
        )
        self.assertEqual(len(list(self.m.buildEdges(roads_far).values())), 0)

        # Custom radius overrides default
        edges_custom = list(self.m.buildEdges(roads_far, 150).values())
        self.assertEqual(len(edges_custom), 1)

    def test_build_edges_skips_malformed(self):
        roads = self._t(
            r1=self._node(0, 0),
            r2=self._t(x="bad", z=0),
            r3=None,
            r4=self._node(40, 0),
        )
        edges = list(self.m.buildEdges(roads).values())
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["a"], "r1")
        self.assertEqual(edges[0]["b"], "r4")

    def test_adjacency_mirroring(self):
        roads = self._t(
            a=self._node(0, 0),
            b=self._node(30, 0),
            c=self._node(200, 200),
        )
        adj = self.m.adjacency(roads)
        self.assertEqual(adj["a"]["b"], 30.0)
        self.assertEqual(adj["b"]["a"], 30.0)
        # c is isolated: table exists but empty
        self.assertEqual(len(list(adj["c"].values())), 0)

    def test_component_count(self):
        # Single isolated node
        self.assertEqual(self.m.componentCount(self._t(a=self._node(0, 0))), 1)

        # 3 linked nodes in chain
        chain = self._t(
            a=self._node(0, 0),
            b=self._node(50, 0),
            c=self._node(100, 0),
        )
        self.assertEqual(self.m.componentCount(chain), 1)

        # Two separate 2-node clusters
        two_clusters = self._t(
            a1=self._node(0, 0),
            a2=self._node(40, 0),
            b1=self._node(500, 500),
            b2=self._node(530, 500),
        )
        self.assertEqual(self.m.componentCount(two_clusters), 2)

    def test_component_of(self):
        chain = self._t(
            a=self._node(0, 0),
            b=self._node(50, 0),
            c=self._node(100, 0),
            isolated=self._node(500, 500),
        )
        comp_b = list(self.m.componentOf(chain, "b").values())
        self.assertEqual(comp_b, ["a", "b", "c"])

        comp_iso = list(self.m.componentOf(chain, "isolated").values())
        self.assertEqual(comp_iso, ["isolated"])

        comp_missing = list(self.m.componentOf(chain, "nonexistent").values())
        self.assertEqual(comp_missing, [])

    def test_is_connected(self):
        chain = self._t(
            a=self._node(0, 0),
            b=self._node(50, 0),
            c=self._node(100, 0),
            isolated=self._node(500, 500),
        )
        self.assertTrue(self.m.isConnected(chain, "a", "c"))
        self.assertTrue(self.m.isConnected(chain, "b", "c"))
        self.assertFalse(self.m.isConnected(chain, "a", "isolated"))
        self.assertFalse(self.m.isConnected(chain, "a", "missing"))
        self.assertFalse(self.m.isConnected(chain, "missing1", "missing2"))

    def test_connected_to_network(self):
        roads = self._t(
            r1=self._node(100, 200),
        )
        # Exactly on node
        self.assertTrue(self.m.connectedToNetwork(roads, 100, 200))
        # Within radius (64 default)
        self.assertTrue(self.m.connectedToNetwork(roads, 150, 200))
        # Beyond radius
        self.assertFalse(self.m.connectedToNetwork(roads, 200, 200))
        # Non-numeric guards
        self.assertFalse(self.m.connectedToNetwork(roads, None, 200))
        self.assertFalse(self.m.connectedToNetwork(None, 100, 200))

    def test_network_summary(self):
        # Fixture: a 3-node chain (a-b-c) plus 1 isolated node (d)
        roads = self._t(
            a=self._node(0, 0),
            b=self._node(40, 0),
            c=self._node(80, 0),
            d=self._node(500, 500),
        )
        summary = self.m.networkSummary(roads)
        self.assertEqual(summary["nodes"], 4)
        self.assertEqual(summary["edges"], 2)
        self.assertEqual(summary["components"], 2)
        self.assertEqual(summary["isolated"], 1)
        self.assertEqual(summary["largest"], 3)


class TestRoadGraphDefensive(unittest.TestCase):
    """Defensive coverage: bad inputs, empty tables, NaN/inf, custom keys."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _t(self, **kwargs):
        return self.lua.table(**kwargs)

    def _node(self, x, z):
        return self._t(x=x, z=z)

    def test_nil_and_non_table_roads(self):
        m = self.m
        self.assertEqual(m.componentCount(None), 0)
        self.assertEqual(m.componentCount(42), 0)
        self.assertEqual(m.componentCount("roads"), 0)
        self.assertEqual(len(list(m.buildEdges(None).values())), 0)
        self.assertEqual(len(list(m.adjacency(None).values())), 0)
        self.assertEqual(len(list(m.componentOf(None, "k").values())), 0)
        self.assertFalse(m.isConnected(None, "a", "b"))
        self.assertFalse(m.connectedToNetwork(None, 10, 10))
        s = m.networkSummary(None)
        self.assertEqual(s["nodes"], 0)
        self.assertEqual(s["edges"], 0)
        self.assertEqual(s["components"], 0)
        self.assertEqual(s["isolated"], 0)
        self.assertEqual(s["largest"], 0)

    def test_empty_roads_table(self):
        m = self.m
        empty = self.lua.table()
        self.assertEqual(m.componentCount(empty), 0)
        self.assertEqual(len(list(m.buildEdges(empty).values())), 0)
        self.assertFalse(m.connectedToNetwork(empty, 0, 0))
        s = m.networkSummary(empty)
        self.assertEqual(s["nodes"], 0)
        self.assertEqual(s["components"], 0)

    def test_nan_and_infinite_coords_rejected(self):
        m = self.m
        lua = self.lua
        nan = lua.eval("0/0")
        inf = lua.eval("math.huge")
        roads = self._t(
            bad_nan=self._node(nan, 0),
            bad_inf=self._node(0, inf),
            good=self._node(0, 0),
        )
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 1)
        self.assertEqual(s["components"], 1)
        self.assertEqual(s["isolated"], 1)
        # connectedToNetwork with NaN query point is false
        self.assertFalse(m.connectedToNetwork(roads, nan, 0))
        self.assertFalse(m.connectedToNetwork(roads, inf, 0))

    def test_zero_and_negative_radius(self):
        m = self.m
        roads = self._t(
            a=self._node(0, 0),
            b=self._node(10, 0),
        )
        # radius 0: only coincident nodes link
        self.assertEqual(m.componentCount(roads, 0), 2)
        # negative radius is unusable -> falls back to default 64, so nodes link
        self.assertEqual(m.componentCount(roads, -5), 1)
        # non-numeric radius falls back too
        self.assertEqual(m.componentCount(roads, "x"), 1)

    def test_non_table_entries_ignored_everywhere(self):
        m = self.m
        roads = self._t(
            good=self._node(0, 0),
            junk1="string",
            junk2=42,
            junk3=self.lua.table(),  # table but no x/z
        )
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 1)
        self.assertEqual(s["isolated"], 1)
        self.assertEqual(len(list(m.buildEdges(roads).values())), 0)

    def test_numeric_keys_supported(self):
        # The gadget keys roads by featureID (numbers); tostring sorting must work.
        m = self.m
        # 3 nodes spaced 60 elmos apart: adjacent pairs are within the 64
        # radius (distance 60), non-adjacent are 120 apart -> exactly 2 edges.
        roads = self.lua.table()
        for i in range(1, 4):
            roads[i] = self._node(i * 60.0, 0)  # actual numeric keys, like featureIDs
        self.assertEqual(m.componentCount(roads), 1)
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 3)
        self.assertEqual(s["edges"], 2)
        self.assertEqual(s["largest"], 3)

    def test_is_connected_self(self):
        m = self.m
        roads = self._t(a=self._node(0, 0))
        self.assertTrue(m.isConnected(roads, "a", "a"))

    def test_large_chain_connectivity(self):
        m = self.m
        # 20 nodes spaced 60 elmos: adjacent pairs link (60 <= 64), nodes two
        # apart are 120 > 64 so no skip edges -> one component, 19 edges.
        kwargs = {str(i): self._node(i * 60.0, 0) for i in range(1, 21)}
        roads = self._t(**kwargs)
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 20)
        self.assertEqual(s["edges"], 19)
        self.assertEqual(s["components"], 1)
        self.assertEqual(s["largest"], 20)
        self.assertTrue(m.isConnected(roads, "1", "20"))


class TestRoadGraphCallPatterns(unittest.TestCase):
    """Exercises the pure module only, with the exact call patterns the gadget
    uses (mirroring GG.MedievalLogistics API semantics). This does NOT execute
    the gadget; see TestGadgetRoadGraphBehaviour for real gadget execution."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.m = cls.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _t(self, **kwargs):
        return self.lua.table(**kwargs)

    def _node(self, x, z):
        return self._t(x=x, z=z)

    def test_road_lifecycle_updates_summary(self):
        m = self.m
        # Start empty (mirrors roads[team] = {} after initTeam)
        roads = self.lua.table()
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 0)

        # FeatureCreated: roads[owner][featureID] = {x=..., z=...}
        roads[101] = self._node(2400, 3884)
        roads[102] = self._node(2460, 3884)
        roads[103] = self._node(2520, 3884)
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 3)
        self.assertEqual(s["edges"], 2)
        self.assertEqual(s["components"], 1)

        # FeatureDestroyed: roads[owner][featureID] = nil removes the bridge
        roads[102] = None
        s = m.networkSummary(roads)
        self.assertEqual(s["nodes"], 2)
        self.assertEqual(s["edges"], 0)
        self.assertEqual(s["components"], 2)
        self.assertFalse(m.isConnected(roads, 101, 103))

    def test_point_on_road_network_matches_gadget_semantics(self):
        m = self.m
        roads = self._t(
            road1=self._node(2608, 3884),
            road2=self._node(2668, 3884),
            road3=self._node(2728, 3884),
            iso=self._node(2908, 4184),
        )
        # Points the probe queries
        self.assertTrue(m.connectedToNetwork(roads, 2668, 3884))
        self.assertFalse(m.connectedToNetwork(roads, 3408, 4484))

    def test_road_connected_api_semantics(self):
        m = self.m
        roads = self._t(
            road1=self._node(2608, 3884),
            road2=self._node(2668, 3884),
            road3=self._node(2728, 3884),
            iso=self._node(2908, 4184),
        )
        self.assertTrue(m.isConnected(roads, "road1", "road3"))
        self.assertFalse(m.isConnected(roads, "road1", "iso"))
        # Unknown feature IDs are safe
        self.assertFalse(m.isConnected(roads, 999, 1000))


class TestGadgetRoadGraphWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_module_include(self):
        self.assertIn('VFS.Include("scripts/medieval_road_graph.lua")', self.src)

    def test_gg_api_exposed(self):
        self.assertIn("RoadNetworkSummary = function(teamID)", self.src)
        self.assertIn("RoadConnected = function(teamID, keyA, keyB)", self.src)
        self.assertIn("PointOnRoadNetwork = function(teamID, x, z)", self.src)

    def test_phase3_roadgraph_echo(self):
        self.assertIn("PHASE3 ROADGRAPH", self.src)


class TestGadgetRoadGraphBehaviour(unittest.TestCase):
    """REAL behavioural execution: runs the actual gadget file
    (luarules/gadgets/gadget_medieval_logistics.lua) inside lupa with stub
    Spring, VFS, GG, gadgetHandler, UnitDefs and FeatureDefs, then drives the
    real callins Initialize / FeatureCreated / FeatureDestroyed and asserts
    the GG.MedievalLogistics road-graph APIs."""

    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        cls.lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")

    def setUp(self):
        # Fresh engine-like environment per test; re-executes the real gadget file.
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}           -- featureID -> { defID, x, z, team }
        TEAM_LIST = {0, 1}
        gadget = {}             -- provided by the engine before gadget files load
        gadgetHandler = { IsSyncedCode = function() return true end }
        GG = {}
        FeatureDefs = {
          [7] = { name = "medieval_road" },
          [8] = { name = "bigrock" },
        }
        UnitDefs = {}
        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
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
          SetGameRulesParam = function(k, v) GAME_RULES[k] = v end,
          GetUnitPosition = function() return nil end,
          GetUnitHealth = function() return nil end,
          SetUnitMaxHealth = function() end,
          SetUnitHealth = function() end,
        }
        VFS = {
          -- Execute the REAL module files from the repo, like the engine does.
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }
        -- Harness helpers -------------------------------------------------------
        function PlaceFeature(id, defID, x, z, team)
          FEATURES[id] = { defID = defID, x = x, z = z, team = team }
        end
        function FireInitialize()
          gadget:Initialize()
        end
        function FireFeatureCreated(id, allyTeam)
          gadget:FeatureCreated(id, allyTeam)
        end
        function FireFeatureDestroyed(id, allyTeam)
          gadget:FeatureDestroyed(id, allyTeam)
        end
        -- Load the REAL gadget --------------------------------------------------
        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _init(self):
        self._g("FireInitialize")()

    def _place(self, fid, def_id, x, z, team):
        self._g("PlaceFeature")(fid, def_id, float(x), float(z), team)

    def _created(self, *fids):
        fire = self._g("FireFeatureCreated")
        for fid in fids:
            fire(fid, 0)

    def _echoes(self):
        return list(self._g("ECHO_LINES").values())

    def test_initialize_prepares_teams_and_exposes_gg_api(self):
        self._init()
        api = self._api()
        self.assertEqual(api.RoadCount(0), 0)
        self.assertEqual(api.RoadCount(1), 0)
        s = api.RoadNetworkSummary(0)
        self.assertEqual(s["nodes"], 0)
        self.assertEqual(s["edges"], 0)
        self.assertEqual(s["components"], 0)
        self.assertEqual(s["isolated"], 0)
        self.assertEqual(s["largest"], 0)
        self.assertFalse(api.RoadConnected(0, 101, 102))
        self.assertFalse(api.PointOnRoadNetwork(0, 2400, 3884))

    def test_feature_created_tracks_numeric_feature_ids(self):
        self._init()
        api = self._api()
        self._place(101, 7, 2400, 3884, 0)
        self._place(102, 7, 2460, 3884, 0)
        self._place(103, 7, 2520, 3884, 0)
        self._created(101, 102, 103)
        self.assertEqual(api.RoadCount(0), 3)
        s = api.RoadNetworkSummary(0)
        self.assertEqual(s["nodes"], 3)
        self.assertEqual(s["edges"], 2)
        self.assertEqual(s["components"], 1)
        self.assertEqual(s["largest"], 3)
        self.assertTrue(api.RoadConnected(0, 101, 103))
        self.assertTrue(api.PointOnRoadNetwork(0, 2400, 3884))
        self.assertFalse(api.PointOnRoadNetwork(0, 3408, 4484))
        # Non-road feature defs and unregistered feature IDs are ignored.
        self._place(300, 8, 2400, 3884, 0)
        self._created(300, 999)
        self.assertEqual(api.RoadCount(0), 3)
        # The gadget echoes the numeric feature IDs and the live graph summary.
        echoes = self._echoes()
        self.assertIn("PHASE3 ROAD placed ftr=101 team=0 x=2400 z=3884", echoes)
        self.assertIn("PHASE3 ROADGRAPH team=0 nodes=3 edges=2 components=1 isolated=0 largest=3", echoes)

    def test_team_isolation_between_road_tables(self):
        self._init()
        api = self._api()
        self._place(101, 7, 2400, 3884, 0)
        self._place(102, 7, 2460, 3884, 0)
        self._place(103, 7, 2520, 3884, 0)
        self._created(101, 102, 103)
        self._place(201, 7, 5000, 1000, 1)
        self._place(202, 7, 5060, 1000, 1)
        self._g("FireFeatureCreated")(201, 1)
        self._g("FireFeatureCreated")(202, 1)
        self.assertEqual(api.RoadCount(0), 3)
        self.assertEqual(api.RoadCount(1), 2)
        self.assertEqual(api.RoadNetworkSummary(1)["nodes"], 2)
        self.assertEqual(api.RoadNetworkSummary(1)["edges"], 1)
        # Same-shaped chains stay team-local: no cross-team adjacency.
        self.assertTrue(api.RoadConnected(0, 101, 103))
        self.assertTrue(api.RoadConnected(1, 201, 202))
        self.assertFalse(api.RoadConnected(0, 101, 201))
        self.assertFalse(api.RoadConnected(1, 101, 201))
        self.assertFalse(api.PointOnRoadNetwork(0, 5000, 1000))
        self.assertFalse(api.PointOnRoadNetwork(1, 2400, 3884))
        # Destroying a team-0 road leaves team 1 untouched.
        self._g("FireFeatureDestroyed")(101, 0)
        self.assertEqual(api.RoadCount(1), 2)
        self.assertTrue(api.RoadConnected(1, 201, 202))

    def test_missing_team_defaults_safely(self):
        self._init()
        api = self._api()
        # GetFeatureTeam returning nil makes the gadget default the owner to 0.
        self._place(101, 7, 2400, 3884, 0)
        self._place(102, 7, 2460, 3884, None)
        self._created(101, 102)
        self.assertEqual(api.RoadCount(0), 2)
        # Unknown team IDs return empty results instead of erroring.
        self.assertEqual(api.RoadCount(99), 0)
        s = api.RoadNetworkSummary(99)
        self.assertEqual(s["nodes"], 0)
        self.assertEqual(s["edges"], 0)
        self.assertEqual(s["components"], 0)
        self.assertFalse(api.RoadConnected(99, 101, 102))
        self.assertFalse(api.PointOnRoadNetwork(99, 2400, 3884))

    def test_bridge_destruction_splits_components(self):
        self._init()
        api = self._api()
        self._place(101, 7, 2400, 3884, 0)
        self._place(102, 7, 2460, 3884, 0)
        self._place(103, 7, 2520, 3884, 0)
        self._created(101, 102, 103)
        self.assertTrue(api.RoadConnected(0, 101, 103))
        # Destroying the middle road segment splits the chain.
        self._g("FireFeatureDestroyed")(102, 0)
        self.assertEqual(api.RoadCount(0), 2)
        s = api.RoadNetworkSummary(0)
        self.assertEqual(s["nodes"], 2)
        self.assertEqual(s["edges"], 0)
        self.assertEqual(s["components"], 2)
        self.assertEqual(s["isolated"], 2)
        self.assertEqual(s["largest"], 1)
        self.assertFalse(api.RoadConnected(0, 101, 103))
        self.assertIn("PHASE3 ROAD removed ftr=102 team=0", self._echoes())
        # Destroying unknown / never-tracked feature IDs is a safe no-op.
        self._g("FireFeatureDestroyed")(999, 0)
        self._g("FireFeatureDestroyed")(101, 0)
        self.assertEqual(api.RoadCount(0), 1)
