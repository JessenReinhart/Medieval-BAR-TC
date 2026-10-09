"""
Phase-3 Slice 7 tests: supply bonuses and road-aware pathing.

Pure policy in scripts/medieval_logistics.lua:
- SUPPLY_RADIUS = 96.0, SUPPLY_BONUS_PER_ENDPOINT = 0.10, SUPPLY_BONUS_MAX = 0.50
- supplyEndpointCount(buildings, roads, x, z, ...) counts only ROAD-CONNECTED
  endpoints whose supply area covers the point.
- supplyBonus(count) is additive per endpoint and clamped to SUPPLY_BONUS_MAX.
- supplyState(...) reports { count, bonus, multiplier, inSupply }.
- isSupplyEligibleUnitDef(def) accepts non-building defs only.
- pathCostMultiplier/pathCost/roadRoutePreferred implement the road discount
  (ROAD_PATH_COST_MULT) and the unsupplied-target penalty
  (UNSUPPLIED_PATH_COST_MULT).

Gadget enforcement in luarules/gadgets/gadget_medieval_logistics.lua:
- finished non-building units are tracked, scanned on the 15-frame cadence
- the bonus is published via Spring.SetUnitRulesParam and applied to outgoing
  damage in UnitPreDamaged
- GetSupplyState / SupplyBonus / InSupply / SupplyStateAt / SupplySummary
- lifecycle removal and re-track on transfer

Gathering pathing in luarules/gadgets/gadget_medieval_gather.lua:
- dropoff and node selection is cost-based, preferring road-connected targets
- with no road network the previous nearest-wins behaviour is unchanged

Each test boots its OWN fresh Lua runtime (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GATHER_MODULE_PATH = ROOT / "scripts" / "medieval_gather.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"
GATHER_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_gather.lua"

# UnitDef ids used by the gadget harness stubs
VILLAGER, INFANTRY, GRANARY = 1, 2, 3
TOWN_CENTER, WALL = 4, 5
OUTSIDER = 6
ROAD_FDEF = 7

SUPPLY_RADIUS = 96.0
LINK_RADIUS = 64.0
BONUS_PER_ENDPOINT = 0.10
BONUS_MAX = 0.50


class TestSlice7PureSupplyPolicy(unittest.TestCase):
    """Pure-module supply checks against scripts/medieval_logistics.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _t(self, **kwargs):
        return self.lua.table(**kwargs)

    def _roads(self, *coords):
        out = self.lua.table()
        for i, (x, z) in enumerate(coords, start=1):
            out[i] = self._t(x=float(x), z=float(z))
        return out

    def _buildings(self, *coords):
        out = self.lua.table()
        for i, (x, z) in enumerate(coords, start=1):
            out[i] = self._t(x=float(x), z=float(z))
        return out

    # -- constants ---------------------------------------------------------

    def test_supply_constants(self):
        self.assertEqual(self.m.SUPPLY_RADIUS, SUPPLY_RADIUS)
        self.assertEqual(self.m.SUPPLY_BONUS_PER_ENDPOINT, BONUS_PER_ENDPOINT)
        self.assertEqual(self.m.SUPPLY_BONUS_MAX, BONUS_MAX)
        self.assertEqual(self.m.ROAD_PATH_COST_MULT, 0.75)
        self.assertEqual(self.m.UNSUPPLIED_PATH_COST_MULT, 1.5)

    # -- supplyEndpointCount ----------------------------------------------

    def test_connected_endpoint_in_range_counts(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000))
        count = self.m.supplyEndpointCount(buildings, roads, 1050, 1000)
        self.assertEqual(count, 1)

    def test_unconnected_endpoint_does_not_supply(self):
        # Road is far from the building, so the endpoint is not road-connected
        # and projects no supply even though the unit is right next to it.
        roads = self._roads((5000, 5000))
        buildings = self._buildings((1000, 1000))
        count = self.m.supplyEndpointCount(buildings, roads, 1010, 1000)
        self.assertEqual(count, 0)

    def test_no_roads_means_no_supply(self):
        buildings = self._buildings((1000, 1000))
        count = self.m.supplyEndpointCount(buildings, self.lua.table(), 1000, 1000)
        self.assertEqual(count, 0)

    def test_unit_outside_supply_radius_is_not_supplied(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000))
        # 96 elmos is inclusive; 97 is outside.
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, 1096, 1000), 1)
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, 1097, 1000), 0)

    def test_supply_radius_boundary_is_inclusive(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000))
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, 1000, 1096), 1)

    def test_endpoint_link_boundary_is_inclusive(self):
        roads = self._roads((1064, 1000))
        buildings = self._buildings((1000, 1000))
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, 1000, 1000), 1)
        roads2 = self._roads((1065, 1000))
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads2, 1000, 1000), 0)

    def test_multiple_endpoints_accumulate(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000), (1040, 1000), (1000, 1040))
        count = self.m.supplyEndpointCount(buildings, roads, 1020, 1000)
        self.assertEqual(count, 3)

    def test_malformed_input_returns_zero(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000))
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, None, 1000), 0)
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, 1000, None), 0)
        self.assertEqual(self.m.supplyEndpointCount(None, roads, 1000, 1000), 0)
        self.assertEqual(self.m.supplyEndpointCount(buildings, None, 1000, 1000), 0)
        nan = self.lua.eval("0/0")
        inf = self.lua.eval("math.huge")
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, nan, 1000), 0)
        self.assertEqual(self.m.supplyEndpointCount(buildings, roads, inf, 1000), 0)

    def test_malformed_building_nodes_are_ignored(self):
        roads = self._roads((1000, 1000))
        buildings = self.lua.table()
        buildings[1] = self._t(x=1000.0, z=1000.0)
        buildings[2] = self._t(x="bad", z=1000.0)
        buildings[3] = "not a table"
        count = self.m.supplyEndpointCount(buildings, roads, 1000, 1000)
        self.assertEqual(count, 1)

    # -- supplyBonus -------------------------------------------------------

    def test_bonus_is_additive_per_endpoint(self):
        self.assertAlmostEqual(self.m.supplyBonus(1), 0.10)
        self.assertAlmostEqual(self.m.supplyBonus(2), 0.20)

    def test_bonus_is_clamped_at_max(self):
        self.assertAlmostEqual(self.m.supplyBonus(5), BONUS_MAX)
        self.assertAlmostEqual(self.m.supplyBonus(100), BONUS_MAX)

    def test_bonus_is_zero_for_non_positive_or_invalid_counts(self):
        self.assertEqual(self.m.supplyBonus(0), 0)
        self.assertEqual(self.m.supplyBonus(-3), 0)
        self.assertEqual(self.m.supplyBonus(None), 0)
        self.assertEqual(self.m.supplyBonus("two"), 0)
        nan = self.lua.eval("0/0")
        self.assertEqual(self.m.supplyBonus(nan), 0)

    def test_bonus_honours_custom_rates(self):
        self.assertAlmostEqual(self.m.supplyBonus(2, 0.25, 1.0), 0.5)
        self.assertAlmostEqual(self.m.supplyBonus(10, 0.25, 1.0), 1.0)
        # A non-positive custom rate or cap yields nothing.
        self.assertEqual(self.m.supplyBonus(2, 0.0, 1.0), 0)
        self.assertEqual(self.m.supplyBonus(2, 0.25, 0.0), 0)

    # -- supplyState / isInSupply -----------------------------------------

    def test_supply_state_reports_count_bonus_and_multiplier(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000), (1040, 1000))
        state = self.m.supplyState(buildings, roads, 1020, 1000)
        self.assertEqual(state["count"], 2)
        self.assertAlmostEqual(state["bonus"], 0.20)
        self.assertAlmostEqual(state["multiplier"], 1.20)
        self.assertTrue(state["inSupply"])

    def test_supply_state_out_of_supply(self):
        buildings = self._buildings((1000, 1000))
        state = self.m.supplyState(buildings, self.lua.table(), 1000, 1000)
        self.assertEqual(state["count"], 0)
        self.assertAlmostEqual(state["bonus"], 0.0)
        self.assertAlmostEqual(state["multiplier"], 1.0)
        self.assertFalse(state["inSupply"])

    def test_is_in_supply_matches_supply_state(self):
        roads = self._roads((1000, 1000))
        buildings = self._buildings((1000, 1000))
        self.assertTrue(self.m.isInSupply(buildings, roads, 1000, 1000))
        self.assertFalse(self.m.isInSupply(buildings, self.lua.table(), 1000, 1000))

    # -- isSupplyEligibleUnitDef ------------------------------------------

    def test_supply_eligibility_accepts_non_buildings(self):
        # Engine-shaped mobile defs: every mobile unit sets `canMove = true`;
        # this TC's source defs never set `isBuilding`, so eligibility is keyed
        # on mobility rather than the engine's unreliable derived `isBuilding`.
        t = self.lua.table
        self.assertTrue(self.m.isSupplyEligibleUnitDef(t(name="medieval_infantry", canMove=True)))
        self.assertTrue(self.m.isSupplyEligibleUnitDef(t(name="medieval_villager", canMove=True, canBuild=True)))
        self.assertTrue(self.m.isSupplyEligibleUnitDef(t(name="medieval_cart", canMove=True, isBuilding=False)))

    def test_supply_eligibility_rejects_buildings_and_nil(self):
        t = self.lua.table
        # Engine-shaped building: `canMove = false` (the reliable discriminator).
        self.assertFalse(self.m.isSupplyEligibleUnitDef(t(name="medieval_wall", canMove=False)))
        # A def that merely claims `isBuilding = true` but is not mobile stays excluded.
        self.assertFalse(self.m.isSupplyEligibleUnitDef(t(name="medieval_wall", canMove=False, isBuilding=True)))
        self.assertFalse(self.m.isSupplyEligibleUnitDef(None))

    # -- pathing cost policy ----------------------------------------------

    def test_path_cost_multiplier_matrix(self):
        self.assertAlmostEqual(self.m.pathCostMultiplier(False, None), 1.0)
        self.assertAlmostEqual(self.m.pathCostMultiplier(True, None), 0.75)
        self.assertAlmostEqual(self.m.pathCostMultiplier(False, True), 1.0)
        self.assertAlmostEqual(self.m.pathCostMultiplier(True, True), 0.75)
        self.assertAlmostEqual(self.m.pathCostMultiplier(False, False), 1.5)
        self.assertAlmostEqual(self.m.pathCostMultiplier(True, False), 1.125)

    def test_path_cost_multiplier_only_honours_real_booleans(self):
        # Non-boolean values must not silently enable a discount or penalty.
        self.assertAlmostEqual(self.m.pathCostMultiplier(1, 0), 1.0)
        self.assertAlmostEqual(self.m.pathCostMultiplier("yes", "no"), 1.0)

    def test_path_cost_scales_distance(self):
        self.assertAlmostEqual(self.m.pathCost(100.0, False, None), 100.0)
        self.assertAlmostEqual(self.m.pathCost(100.0, True, None), 75.0)
        self.assertAlmostEqual(self.m.pathCost(100.0, False, False), 150.0)
        self.assertEqual(self.m.pathCost(0.0, True, True), 0.0)

    def test_path_cost_is_infinite_for_invalid_distance(self):
        self.assertEqual(self.m.pathCost(None, False, None), self.lua.eval("math.huge"))
        self.assertEqual(self.m.pathCost(-1.0, False, None), self.lua.eval("math.huge"))
        nan = self.lua.eval("0/0")
        self.assertEqual(self.m.pathCost(nan, False, None), self.lua.eval("math.huge"))

    def test_road_route_preferred(self):
        self.assertTrue(self.m.roadRoutePreferred(100.0, 75.0))
        self.assertFalse(self.m.roadRoutePreferred(75.0, 100.0))
        # Ties keep the open route.
        self.assertFalse(self.m.roadRoutePreferred(100.0, 100.0))

    def test_road_route_not_preferred_for_invalid_costs(self):
        inf = self.lua.eval("math.huge")
        self.assertFalse(self.m.roadRoutePreferred(100.0, inf))
        self.assertFalse(self.m.roadRoutePreferred(inf, 100.0))
        self.assertFalse(self.m.roadRoutePreferred(None, 100.0))
        self.assertFalse(self.m.roadRoutePreferred(100.0, -5.0))


class TestSlice7PureGatherPathing(unittest.TestCase):
    """Pure-module route selection in scripts/medieval_gather.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.execute(GATHER_MODULE_PATH.read_text(encoding="utf-8"))

    def test_path_cost_penalizes_unsupplied_target_only(self):
        self.assertAlmostEqual(self.g.pathCost(0, 0, 100, 0, None), 100.0)
        self.assertAlmostEqual(self.g.pathCost(0, 0, 100, 0, True), 100.0)
        self.assertAlmostEqual(self.g.pathCost(0, 0, 100, 0, False), 150.0)

    def test_path_cost_is_nil_for_malformed_coordinates(self):
        self.assertIsNone(self.g.pathCost(0, 0, None, 0, None))

    def test_best_candidate_prefers_road_connected_target(self):
        t = self.lua.table
        # Unsupplied target is nearer; the supplied one must still win because
        # its penalized cost (200) is below the unsupplied cost (150 * 1.5).
        candidates = t(
            t(key=1, x=150.0, z=0.0, supplied=False),
            t(key=2, x=200.0, z=0.0, supplied=True),
        )
        key, _ = self.g.bestCandidate(candidates, 0.0, 0.0)
        self.assertEqual(key, 2)

    def test_best_candidate_falls_back_to_nearest_when_all_unsupplied(self):
        t = self.lua.table
        candidates = t(
            t(key=1, x=150.0, z=0.0, supplied=False),
            t(key=2, x=300.0, z=0.0, supplied=False),
        )
        key, _ = self.g.bestCandidate(candidates, 0.0, 0.0)
        self.assertEqual(key, 1)

    def test_best_candidate_ignores_unknown_supply_state(self):
        t = self.lua.table
        candidates = t(
            t(key=1, x=150.0, z=0.0, supplied=None),
            t(key=2, x=300.0, z=0.0, supplied=None),
        )
        key, _ = self.g.bestCandidate(candidates, 0.0, 0.0)
        self.assertEqual(key, 1)

    def test_best_candidate_returns_nil_for_empty_or_invalid_input(self):
        key, cost = self.g.bestCandidate(self.lua.table(), 0.0, 0.0)
        self.assertIsNone(key)
        self.assertIsNone(cost)
        key, cost = self.g.bestCandidate(None, 0.0, 0.0)
        self.assertIsNone(key)
        self.assertIsNone(cost)


class TestSlice7GadgetSupply(unittest.TestCase):
    """Gadget-level Slice 7 in a fresh per-test Lua VM with engine stubs."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.VILLAGER = VILLAGER
        g.INFANTRY = INFANTRY
        g.GRANARY = GRANARY
        g.TOWN_CENTER = TOWN_CENTER
        g.WALL = WALL
        g.OUTSIDER = OUTSIDER
        g.ROAD_FDEF = ROAD_FDEF
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}
        UNITS = {}
        RULES_PARAMS = {}
        HEALTH_CALLS = {}
        TEAM_LIST = {0, 1}
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

        FeatureDefs = { [ROAD_FDEF] = { name = "medieval_road" } }
        UnitDefs = {
          -- Engine-shaped defs: mobile units set `canMove = true`; every static
          -- def in this TC sets `canMove = false` and NONE sets `isBuilding`
          -- (the engine derives `isBuilding` as false/nil for them). A foreign
          -- def (`barbarian_raider`) represents the "non-medieval attacker".
          [VILLAGER]    = { name = "medieval_villager", canMove = true, speed = 28 },
          [INFANTRY]    = { name = "medieval_infantry", canMove = true, speed = 32 },
          [GRANARY]     = { name = "medieval_granary", canMove = false, customParams = { dropoff = true } },
          [TOWN_CENTER] = { name = "medieval_town_center", canMove = false, customParams = { dropoff = true } },
          [WALL]        = { name = "medieval_wall", canMove = false },
          [OUTSIDER]    = { name = "barbarian_raider", canMove = true, speed = 30 },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        local RULES_PARAM_FN = function(unitID, key, value)
          RULES_PARAMS[unitID] = RULES_PARAMS[unitID] or {}
          RULES_PARAMS[unitID][key] = value
        end

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
            if u then return u.hp, u.maxHp, false, 0, u.progress end
            return nil
          end,
          SetUnitMaxHealth = function(id, hp)
            local u = UNITS[id]
            if u then u.maxHp = hp end
          end,
          SetUnitHealth = function(id, hp)
            local u = UNITS[id]
            if u then u.hp = hp end
          end,
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
          SetUnitRulesParam = RULES_PARAM_FN,
          MoveCtrl = nil,
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
          UNITS[id] = {
            defID = defID, x = x, z = z, team = team,
            progress = progress or 1, hp = 100, maxHp = 100,
          }
        end
        function PlaceBuilding(id, defID, x, z, team)
          PlaceUnit(id, defID, x, z, team, 1)
        end
        function RemoveUnit(id) UNITS[id] = nil end
        function FireInitialize() gadget:Initialize() end
        function FireUnitFinished(id, defID, team)
          local u = UNITS[id]
          if u then u.progress = 1 end
          gadget:UnitFinished(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireUnitTaken(id, defID, oldTeam, newTeam)
          local u = UNITS[id]
          gadget:UnitTaken(id, defID or (u and u.defID), oldTeam, newTeam)
        end
        function FireUnitGiven(id, defID, newTeam, oldTeam)
          local u = UNITS[id]
          if u then u.team = newTeam end
          gadget:UnitGiven(id, defID or (u and u.defID), newTeam, oldTeam)
        end
        function FireUnitDestroyed(id, defID, team)
          local u = UNITS[id]
          gadget:UnitDestroyed(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireGameFrame(frame) gadget:GameFrame(frame) end
        function FireUnitPreDamaged(defender, damage, attacker)
          local attackerDefID = attacker and UNITS[attacker] and UNITS[attacker].defID or nil
          local attackerTeam = attacker and UNITS[attacker] and UNITS[attacker].team or nil
          return gadget:UnitPreDamaged(
            defender, UNITS[defender] and UNITS[defender].defID, UNITS[defender] and UNITS[defender].team,
            damage, false, nil, nil, attacker, attackerDefID, attackerTeam)
        end
        function FireFeatureDestroyed(id, allyTeam) gadget:FeatureDestroyed(id, allyTeam) end

        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    # -- helpers -----------------------------------------------------------

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _place_road(self, team, x, z):
        return self._g("Spring").CreateFeature("medieval_road", float(x), 0.0, float(z), 0, team)

    def _finish_unit(self, unit_id, def_id, team, x, z):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team, 1)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _finish_building(self, unit_id, def_id, team, x, z):
        self._g("PlaceBuilding")(unit_id, def_id, float(x), float(z), team)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _state(self, unit_id):
        st = self._api().GetSupplyState(unit_id)
        if st is None:
            return None
        return {
            "count": int(st["count"]),
            "bonus": float(st["bonus"]),
            "multiplier": float(st["multiplier"]),
            "inSupply": bool(st["inSupply"]),
        }

    def _rules(self, unit_id, key):
        params = self._g("RULES_PARAMS")[unit_id]
        if params is None:
            return None
        return params[key]

    # -- tracking ----------------------------------------------------------

    def test_untracked_unit_has_no_supply_state(self):
        self.assertIsNone(self._state(9999))
        self.assertAlmostEqual(self._api().SupplyBonus(9999), 0.0)
        self.assertFalse(self._api().InSupply(9999))

    def test_finished_non_building_unit_is_tracked_out_of_supply(self):
        self._finish_unit(101, INFANTRY, 0, 1000.0, 1000.0)
        st = self._state(101)
        self.assertIsNotNone(st)
        self.assertEqual(st["count"], 0)
        self.assertFalse(st["inSupply"])

    def test_buildings_are_never_tracked_as_supply_recipients(self):
        self._finish_building(201, WALL, 0, 1000.0, 1000.0)
        self.assertIsNone(self._state(201))

    def test_endpoints_are_not_supply_recipients(self):
        self._finish_building(202, GRANARY, 0, 1000.0, 1000.0)
        self.assertIsNone(self._state(202))

    def test_initialize_tracks_existing_finished_units(self):
        self._g("PlaceUnit")(301, INFANTRY, 1000.0, 1000.0, 0, 1)
        self._g("FireInitialize")()
        self.assertIsNotNone(self._state(301))

    def test_initialize_resets_previous_supply_state(self):
        # Re-running Initialize must discard all cached supply tables
        # (supply, supplyUnits, supplyBonusMovers). Simulate a tracked unit that
        # leaves the engine roster with no UnitDestroyed callin, then re-init:
        # the stale entry must be gone rather than surviving the reset.
        self._finish_unit(311, INFANTRY, 0, 1000.0, 1000.0)
        self.assertIsNotNone(self._state(311))
        self._g("RemoveUnit")(311)          # gone from Spring.GetAllUnits
        self._g("FireInitialize")()
        self.assertIsNone(self._state(311))
        self.assertAlmostEqual(self._api().SupplyBonus(311), 0.0)
        self.assertFalse(self._api().InSupply(311))

    # -- supply computation ------------------------------------------------

    def test_unit_near_connected_endpoint_gains_supply(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(401, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(402, INFANTRY, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(402)
        self.assertEqual(st["count"], 1)
        self.assertAlmostEqual(st["bonus"], BONUS_PER_ENDPOINT)
        self.assertTrue(st["inSupply"])

    def test_unit_near_unconnected_endpoint_gains_nothing(self):
        # The endpoint has no road within BUILD_LINK_RADIUS, so it supplies
        # nothing even though the unit stands right next to it.
        self._place_road(0, 5000, 5000)
        self._finish_building(411, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(412, INFANTRY, 0, 1010.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(412)
        self.assertEqual(st["count"], 0)
        self.assertFalse(st["inSupply"])

    def test_unit_outside_supply_radius_gains_nothing(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(421, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(422, INFANTRY, 0, 1200.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertEqual(self._state(422)["count"], 0)

    def test_bonus_is_capped_across_many_endpoints(self):
        self._place_road(0, 1000, 1000)
        for i in range(6):
            self._finish_building(500 + i, GRANARY, 0, 1000.0 + i * 10, 1000.0)
        self._finish_unit(530, INFANTRY, 0, 1020.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(530)
        self.assertEqual(st["count"], 6)
        self.assertAlmostEqual(st["bonus"], BONUS_MAX)
        self.assertAlmostEqual(st["multiplier"], 1.0 + BONUS_MAX)

    def test_destroying_the_road_removes_supply(self):
        road = self._place_road(0, 1000, 1000)
        self._finish_building(601, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(602, INFANTRY, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertTrue(self._state(602)["inSupply"])
        self._g("FireFeatureDestroyed")(road, 0)
        self._g("FireGameFrame")(30)
        self.assertFalse(self._state(602)["inSupply"])
        self.assertAlmostEqual(self._api().SupplyBonus(602), 0.0)

    def test_supply_is_per_team(self):
        # Team 0's road+endpoint must not supply team 1's unit.
        self._place_road(0, 1000, 1000)
        self._finish_building(701, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(702, INFANTRY, 1, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertEqual(self._state(702)["count"], 0)

    # -- rules params and queries -----------------------------------------

    def test_supply_rules_params_are_published(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(801, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(802, INFANTRY, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertAlmostEqual(self._rules(802, "medieval_supply_bonus"), BONUS_PER_ENDPOINT)
        self.assertAlmostEqual(self._rules(802, "medieval_supply_mult"), 1.0 + BONUS_PER_ENDPOINT)
        self.assertEqual(self._rules(802, "medieval_in_supply"), 1)

    def test_out_of_supply_publishes_zero_and_flag(self):
        self._finish_unit(811, INFANTRY, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertAlmostEqual(self._rules(811, "medieval_supply_bonus"), 0.0)
        self.assertEqual(self._rules(811, "medieval_in_supply"), 0)

    def test_supply_state_at_recomputes_without_a_unit(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(821, GRANARY, 0, 1000.0, 1000.0)
        state = self._api().SupplyStateAt(0, 1000.0, 1000.0)
        self.assertEqual(int(state["count"]), 1)
        self.assertTrue(bool(state["inSupply"]))
        # A team with no roads has no supply anywhere.
        other = self._api().SupplyStateAt(1, 1000.0, 1000.0)
        self.assertEqual(int(other["count"]), 0)

    def test_supply_summary_counts_tracked_and_connected(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(831, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(832, INFANTRY, 0, 1050.0, 1000.0)
        self._finish_unit(833, INFANTRY, 0, 3000.0, 3000.0)
        self._g("FireGameFrame")(15)
        summary = self._api().SupplySummary(0)
        self.assertEqual(int(summary["tracked"]), 2)
        self.assertEqual(int(summary["inSupply"]), 1)
        self.assertEqual(int(summary["outOfSupply"]), 1)
        self.assertEqual(int(summary["endpoints"]), 1)

    # -- exposed API wrappers ----------------------------------------------

    def test_supply_endpoint_count_at_wrapper(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(851, GRANARY, 0, 1000.0, 1000.0)
        # A second endpoint with no road within BUILD_LINK_RADIUS must not count.
        self._finish_building(852, GRANARY, 0, 5000.0, 5000.0)
        self.assertEqual(int(self._api().SupplyEndpointCountAt(0, 1000.0, 1000.0)), 1)
        self.assertEqual(int(self._api().SupplyEndpointCountAt(0, 1200.0, 1000.0)), 0)  # outside SUPPLY_RADIUS
        self.assertEqual(int(self._api().SupplyEndpointCountAt(1, 1000.0, 1000.0)), 0)  # team isolated

    def test_path_cost_wrappers(self):
        api = self._api()
        self.assertAlmostEqual(api.PathCostMultiplier(True, True), 0.75)
        self.assertAlmostEqual(api.PathCostMultiplier(True, False), 0.75 * 1.5)
        self.assertAlmostEqual(api.PathCost(100.0, False, False), 150.0)
        self.assertEqual(api.PathCost(-1.0, True, True), self.lua.eval("math.huge"))
        self.assertTrue(api.RoadRoutePreferred(100.0, 75.0))
        self.assertFalse(api.RoadRoutePreferred(100.0, 100.0))

    # -- damage application ------------------------------------------------

    def test_supplied_attacker_deals_more_damage(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(901, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(902, INFANTRY, 0, 1050.0, 1000.0)
        self._finish_unit(903, INFANTRY, 1, 2000.0, 2000.0)
        self._g("FireGameFrame")(15)
        damage, _ = self._g("FireUnitPreDamaged")(903, 100.0, 902)
        self.assertAlmostEqual(damage, 100.0 * (1.0 + BONUS_PER_ENDPOINT))

    def test_unsupplied_attacker_deals_base_damage(self):
        self._finish_unit(911, INFANTRY, 0, 1000.0, 1000.0)
        self._finish_unit(912, INFANTRY, 1, 2000.0, 2000.0)
        self._g("FireGameFrame")(15)
        damage, _ = self._g("FireUnitPreDamaged")(912, 100.0, 911)
        self.assertAlmostEqual(damage, 100.0)

    def test_non_medieval_attacker_is_untouched(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(921, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(922, INFANTRY, 1, 2000.0, 2000.0)   # defender (enemy)
        # A REAL attacker whose def is not a medieval_* def: the callin must
        # return the damage unchanged (it must not apply tech or supply).
        self._finish_unit(923, OUTSIDER, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        damage, _ = self._g("FireUnitPreDamaged")(922, 100.0, 923)
        self.assertAlmostEqual(damage, 100.0)

    def test_missing_attacker_returns_damage_unchanged(self):
        # No attacker id/def id at all: the callin must pass damage through.
        self._finish_unit(924, INFANTRY, 0, 1000.0, 1000.0)
        damage, _ = self._g("FireUnitPreDamaged")(924, 100.0, None)
        self.assertAlmostEqual(damage, 100.0)

    def test_tech_and_supply_bonuses_stack_multiplicatively(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(931, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(932, INFANTRY, 0, 1050.0, 1000.0)
        self._finish_unit(933, INFANTRY, 1, 2000.0, 2000.0)
        self._g("FireGameFrame")(15)
        self._api().Research(0, "iron_swords")
        damage, _ = self._g("FireUnitPreDamaged")(933, 100.0, 932)
        expected = 100.0 * 1.25 * (1.0 + BONUS_PER_ENDPOINT)
        self.assertAlmostEqual(damage, expected)

    # -- lifecycle ---------------------------------------------------------

    def test_destroyed_units_leave_the_supply_table(self):
        self._finish_unit(1001, INFANTRY, 0, 1000.0, 1000.0)
        self.assertIsNotNone(self._state(1001))
        self._g("FireUnitDestroyed")(1001, INFANTRY, 0)
        self.assertIsNone(self._state(1001))

    def test_taken_units_leave_the_supply_table(self):
        self._finish_unit(1011, INFANTRY, 0, 1000.0, 1000.0)
        self._g("FireUnitTaken")(1011, INFANTRY, 0, 1)
        self.assertIsNone(self._state(1011))

    def test_unit_given_retracks_under_receiving_team(self):
        self._place_road(1, 1000, 1000)
        self._finish_building(1021, GRANARY, 1, 1000.0, 1000.0)
        self._finish_unit(1022, INFANTRY, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertFalse(self._state(1022)["inSupply"])
        self._g("FireUnitGiven")(1022, INFANTRY, 1, 0)
        self._g("FireGameFrame")(30)
        self.assertTrue(self._state(1022)["inSupply"])

    # -- throttle ----------------------------------------------------------

    def test_supply_scan_is_throttled_to_the_shared_cadence(self):
        self._place_road(0, 1000, 1000)
        self._finish_building(1101, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(1102, INFANTRY, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(7)   # off-interval: no scan, nothing published
        self.assertIsNone(self._rules(1102, "medieval_supply_bonus"))
        self._g("FireGameFrame")(15)  # scan publishes the live state
        self.assertEqual(self._rules(1102, "medieval_in_supply"), 1)
        self.assertEqual(self._state(1102)["count"], 1)


class TestSlice7GatherGadgetPathing(unittest.TestCase):
    """Gather-gadget destination selection prefers the supply network."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = GATHER_GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        NODES = {}      -- featureID -> { x, z, resource }
        UNITS = {}
        MOVES = {}      -- { unitID = , x = , z = }
        NEXT_FID = 5000
        gadget = {}
        gadgetHandler = {
          IsSyncedCode = function() return true end,
          RegisterCMDID = function() return true end,
          RegisterAllowCommand = function() return true end,
        }
        CMD = { ANY = 31000, MOVE = 10, STOP = 11 }
        GG = {
          MedievalEconomy = { Deposit = function() end },
        }

        FeatureDefs = {
          [1] = { name = "medieval_tree", customParams = { resource = "wood", capacity = 500 } },
        }
        UnitDefs = {
          [1] = { name = "medieval_villager" },
          [2] = { name = "medieval_lumber_camp", customParams = { dropoff = true, dropoff_resource = "wood" } },
        }

        Spring = {
          Echo = function(fmt, ...) end,
          GetFeatureDefID = function(id)
            local n = NODES[id]
            return n and 1 or nil
          end,
          GetFeaturePosition = function(id)
            local n = NODES[id]
            if n then return n.x, 0, n.z end
            return nil
          end,
          GetUnitPosition = function(id)
            local u = UNITS[id]
            if u then return u.x, 0, u.z end
            return nil
          end,
          GetUnitDefID = function(id)
            local u = UNITS[id]
            return u and u.defID or nil
          end,
          GetUnitTeam = function(id)
            local u = UNITS[id]
            return u and u.team or nil
          end,
          GetUnitIsDead = function(id) return UNITS[id] == nil end,
          GiveOrderToUnit = function(unitID, cmd, params, opts)
            MOVES[#MOVES + 1] = { unitID = unitID, cmd = cmd, x = params[1], z = params[3] }
            return true
          end,
          GetUnitHealth = function(id) return 100, 100, false, 0, 1 end,
        }

        VFS = {
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }

        function AddNode(id, x, z)
          NODES[id] = { x = x, z = z, resource = "wood" }
          gadget:FeatureCreated(id, 0)
        end
        function AddUnit(id, defID, x, z, team)
          UNITS[id] = { defID = defID, x = x, z = z, team = team }
          gadget:UnitCreated(id, defID, team)
        end
        function FireInitialize() gadget:Initialize() end

        assert(load(GADGET_SRC, "@gadget_medieval_gather.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _last_move(self):
        moves = self._g("MOVES")
        n = len(moves)
        return moves[n] if n else None

    def test_no_logistics_api_falls_back_to_nearest_node(self):
        self._g("AddUnit")(1, 1, 0.0, 0.0, 0)
        self._g("AddNode")(501, 100.0, 0.0)
        self._g("AddNode")(502, 400.0, 0.0)
        self.assertTrue(self._g("GG").MedievalGather.AssignGather(1, None))
        mv = self._last_move()
        self.assertAlmostEqual(mv["x"], 100.0)

    def test_road_connected_node_is_preferred_when_cheaper(self):
        # Provide a logistics API where the far node is on the network and the
        # near node is not: penalized cost 150*1.5=225 > 200, so the far wins.
        self._g("AddUnit")(1, 1, 0.0, 0.0, 0)
        self._g("AddNode")(501, 150.0, 0.0)
        self._g("AddNode")(502, 200.0, 0.0)
        self.lua.execute(r"""
        GG.MedievalLogistics = {
          PointOnRoadNetwork = function(teamID, x, z) return x > 175 end,
          SupplyStateAt = function(teamID, x, z)
            return { count = (x > 175) and 1 or 0, bonus = 0, multiplier = 1, inSupply = (x > 175) }
          end,
        }
        """)
        self._g("FireInitialize")()
        self.assertTrue(self._g("GG").MedievalGather.AssignGather(1, None))
        mv = self._last_move()
        self.assertAlmostEqual(mv["x"], 200.0)

    def test_road_connected_dropoff_is_preferred(self):
        self._g("AddUnit")(1, 1, 0.0, 0.0, 0)
        self._g("AddNode")(501, 300.0, 0.0)          # a node to gather from
        self._g("AddUnit")(2, 2, 150.0, 0.0, 0)      # near dropoff, unsupplied
        self._g("AddUnit")(3, 2, 200.0, 0.0, 0)      # farther dropoff, supplied
        self.lua.execute(r"""
        GG.MedievalLogistics = {
          PointOnRoadNetwork = function(teamID, x, z) return x > 175 end,
          SupplyStateAt = function(teamID, x, z)
            return { count = (x > 175) and 1 or 0, bonus = 0, multiplier = 1, inSupply = (x > 175) }
          end,
        }
        """)
        self._g("FireInitialize")()
        # Give the villager a job with a full inventory so AssignDeliver has work.
        self.assertTrue(self._g("GG").MedievalGather.AssignGather(1, None))
        self._g("GG").MedievalGather.GetJob(1)["carried"] = 10
        self.assertTrue(self._g("GG").MedievalGather.AssignDeliver(1, None))
        mv = self._last_move()
        self.assertAlmostEqual(mv["x"], 200.0)


if __name__ == "__main__":
    unittest.main()
