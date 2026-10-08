"""
Phase-3 Slice 6 (stage 1) tests: pure road movement-speed policy in
scripts/medieval_logistics.lua.

Policy under test (narrow and explicit):
- ROAD_SPEED_MULT = 1.5 and ROAD_PROXIMITY_RADIUS = 48.0 stay unchanged.
- speedMultiplier(onRoad) returns ROAD_SPEED_MULT only for a truthy onRoad,
  else 1.0.
- targetSpeed(baseSpeed, onRoad) passes non-number / non-positive bases
  through untouched and otherwise scales by speedMultiplier(onRoad == true),
  so only a real boolean true grants the road bonus.
- isEligibleSpeedUnitDef(def) accepts defs with canMove == true that are not
  buildings; villagers are builders but remain eligible. nil defs and
  non-boolean canMove values are rejected.

Engine-side enforcement (stage 2) is covered below by TestSlice6GadgetSpeedEnforcement:
speedMovers tracking, the 15-frame throttled GameFrame scan, MoveCtrl application
with rules-param fallback, lifecycle hooks, and GG.MedievalLogistics.GetSpeedState.

Each test boots its OWN fresh Lua runtime with the real pure module loaded
(no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_logistics.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"


class TestSlice6PureSpeedPolicy(unittest.TestCase):
    """Pure-module checks against scripts/medieval_logistics.lua."""

    def setUp(self):
        # Independent Lua runtime per test.
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    # -- constants ---------------------------------------------------------

    def test_road_constants_unchanged(self):
        self.assertAlmostEqual(self.m.ROAD_SPEED_MULT, 1.5)
        self.assertAlmostEqual(self.m.ROAD_PROXIMITY_RADIUS, 48.0)

    # -- speedMultiplier ---------------------------------------------------

    def test_speed_multiplier_on_road(self):
        self.assertAlmostEqual(self.m.speedMultiplier(True), 1.5)

    def test_speed_multiplier_off_road_and_nil(self):
        self.assertAlmostEqual(self.m.speedMultiplier(False), 1.0)
        self.assertAlmostEqual(self.m.speedMultiplier(None), 1.0)

    # -- targetSpeed -------------------------------------------------------

    def test_target_speed_on_road_scales(self):
        self.assertAlmostEqual(self.m.targetSpeed(100.0, True), 150.0)

    def test_target_speed_off_road_is_baseline(self):
        self.assertAlmostEqual(self.m.targetSpeed(100.0, False), 100.0)
        self.assertAlmostEqual(self.m.targetSpeed(100.0, None), 100.0)

    def test_target_speed_passes_through_nil_and_non_number(self):
        self.assertIsNone(self.m.targetSpeed(None, True))
        self.assertEqual(self.m.targetSpeed("fast", True), "fast")
        t = self.lua.table
        table_base = t(speed=10)
        # Lupa re-wraps Lua tables crossing the boundary, so compare content.
        passed_through = self.m.targetSpeed(table_base, True)
        self.assertEqual(passed_through.speed, 10)

    def test_target_speed_passes_through_zero_and_negative(self):
        self.assertEqual(self.m.targetSpeed(0, True), 0)
        self.assertEqual(self.m.targetSpeed(-5, True), -5)
        self.assertEqual(self.m.targetSpeed(0.0, False), 0.0)

    def test_target_speed_requires_boolean_true_for_bonus(self):
        # Only a real boolean true grants the road bonus; other truthy values
        # (1, "yes", a table) must fall back to the baseline.
        self.assertAlmostEqual(self.m.targetSpeed(100.0, 1), 100.0)
        self.assertAlmostEqual(self.m.targetSpeed(100.0, "yes"), 100.0)
        self.assertAlmostEqual(self.m.targetSpeed(100.0, self.lua.table()), 100.0)

    # -- isEligibleSpeedUnitDef -------------------------------------------

    def test_eligible_mobile_villager_like_def(self):
        t = self.lua.table
        villager = t(canMove=True, isBuilding=False, canBuild=True)
        self.assertTrue(self.m.isEligibleSpeedUnitDef(villager))

    def test_eligible_mobile_non_builder_def(self):
        t = self.lua.table
        infantry = t(canMove=True, isBuilding=False)
        self.assertTrue(self.m.isEligibleSpeedUnitDef(infantry))

    def test_ineligible_building_def(self):
        t = self.lua.table
        building = t(canMove=True, isBuilding=True)
        self.assertFalse(self.m.isEligibleSpeedUnitDef(building))

    def test_ineligible_immobile_and_nil_defs(self):
        t = self.lua.table
        self.assertFalse(self.m.isEligibleSpeedUnitDef(t(canMove=False, isBuilding=False)))
        self.assertFalse(self.m.isEligibleSpeedUnitDef(t(isBuilding=False)))
        self.assertFalse(self.m.isEligibleSpeedUnitDef(t()))
        self.assertFalse(self.m.isEligibleSpeedUnitDef(None))

    def test_ineligible_non_boolean_can_move(self):
        t = self.lua.table
        self.assertFalse(self.m.isEligibleSpeedUnitDef(t(canMove=1, isBuilding=False)))
        self.assertFalse(self.m.isEligibleSpeedUnitDef(t(canMove="true", isBuilding=False)))


# UnitDef ids used by the gadget harness stubs
VILLAGER, INFANTRY, GRANARY = 1, 2, 3
MOVER_NO_SPEED, STATIC_MOVER, MOBILE_BUILDING = 4, 5, 6
ROAD_FDEF = 7

# Unit def speeds (elmos/sec) mirrored from units/medieval_*.lua
VILLAGER_SPEED = 28.0
INFANTRY_SPEED = 32.0
ROAD_MULT = 1.5


class TestSlice6GadgetSpeedEnforcement(unittest.TestCase):
    """Gadget-level Slice 6: tracking, throttled scan, mutator application,
    rules-param fallback, lifecycle removal/re-track, GetSpeedState."""

    def setUp(self):
        # A completely fresh Lua runtime per test: no shared state.
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().GADGET_SRC = GADGET_PATH.read_text(encoding="utf-8")
        self.lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        self.lua.globals().VILLAGER = VILLAGER
        self.lua.globals().INFANTRY = INFANTRY
        self.lua.globals().GRANARY = GRANARY
        self.lua.globals().MOVER_NO_SPEED = MOVER_NO_SPEED
        self.lua.globals().STATIC_MOVER = STATIC_MOVER
        self.lua.globals().MOBILE_BUILDING = MOBILE_BUILDING
        self.lua.globals().ROAD_FDEF = ROAD_FDEF
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}      -- featureID -> { defID, x, z, team }
        UNITS = {}         -- unitID    -> { defID, x, z, team, progress }
        SET_CALLS = {}     -- MoveCtrl.SetGroundMoveTypeData invocations
        RULES_PARAMS = {}  -- unitID -> { key = value }
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
          [VILLAGER]         = { name = "medieval_villager", canMove = true, speed = 28 },
          [INFANTRY]         = { name = "medieval_infantry", canMove = true, speed = 32 },
          [GRANARY]          = { name = "medieval_granary", canMove = false },
          [MOVER_NO_SPEED]   = { name = "medieval_ghost", canMove = true },
          [STATIC_MOVER]     = { name = "medieval_statue", canMove = false, speed = 10 },
          [MOBILE_BUILDING]  = { name = "medieval_cart", canMove = true, isBuilding = true, speed = 20 },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        local MOVE_CTRL_TABLE = {
          SetGroundMoveTypeData = function(unitID, data)
            if MOVE_CTRL_ERROR then error("stub mutator failure") end
            table.insert(SET_CALLS, {
              unitID = unitID, maxSpeed = data.maxSpeed, maxWantedSpeed = data.maxWantedSpeed,
            })
            return 1
          end,
        }
        local RULES_PARAM_FN = function(unitID, key, value)
          RULES_PARAMS[unitID] = RULES_PARAMS[unitID] or {}
          RULES_PARAMS[unitID][key] = value
        end
        MOVE_CTRL_ERROR = false

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
          MoveCtrl = MOVE_CTRL_TABLE,
          SetUnitRulesParam = RULES_PARAM_FN,
        }

        -- Engine-capability toggles (sync-safety coverage) ---------------------
        function SetMoveCtrlEnabled(enabled)
          Spring.MoveCtrl = enabled and MOVE_CTRL_TABLE or nil
        end
        function SetRulesParamEnabled(enabled)
          Spring.SetUnitRulesParam = enabled and RULES_PARAM_FN or nil
        end

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
        function SetUnitPos(id, x, z)
          UNITS[id].x = x
          UNITS[id].z = z
        end
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
        function FireFeatureDestroyed(id, allyTeam) gadget:FeatureDestroyed(id, allyTeam) end

        -- Load the REAL gadget -------------------------------------------------
        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)

    # -- helpers -----------------------------------------------------------

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _state(self, unit_id):
        """GetSpeedState as plain Python, or None."""
        st = self._api().GetSpeedState(unit_id)
        if st is None:
            return None
        return {
            "base": float(st["base"]),
            "onRoad": bool(st["onRoad"]),
            "applied": float(st["applied"]),
            "source": str(st["source"]),
        }

    def _place_road(self, team, x, z):
        return self._g("Spring").CreateFeature("medieval_road", float(x), 0.0, float(z), 0, team)

    def _finish_unit(self, unit_id, def_id, team, x, z):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team, 1)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    # -- tracking ----------------------------------------------------------

    def test_unit_finished_tracks_eligible_mover_at_baseline(self):
        self._finish_unit(101, VILLAGER, 0, 1000.0, 1000.0)
        st = self._state(101)
        self.assertIsNotNone(st)
        self.assertAlmostEqual(st["base"], VILLAGER_SPEED)
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED)
        self.assertFalse(st["onRoad"])
        self.assertEqual(st["source"], "none")

    def test_buildings_and_ineligible_defs_are_never_tracked(self):
        # Building: canMove false. Speedless mover: no numeric base. Immobile
        # def with a speed, and a mobile building: both ineligible.
        self._finish_unit(201, GRANARY, 0, 1000.0, 1000.0)
        self._finish_unit(202, MOVER_NO_SPEED, 0, 1000.0, 1000.0)
        self._finish_unit(203, STATIC_MOVER, 0, 1000.0, 1000.0)
        self._finish_unit(204, MOBILE_BUILDING, 0, 1000.0, 1000.0)
        for unit_id in (201, 202, 203, 204):
            self.assertIsNone(self._state(unit_id), unit_id)

    def test_initialize_tracks_existing_finished_movers(self):
        self._g("PlaceUnit")(301, VILLAGER, 1000.0, 1000.0, 0, 1)
        self._g("FireInitialize")()
        st = self._state(301)
        self.assertIsNotNone(st)
        self.assertAlmostEqual(st["base"], VILLAGER_SPEED)

    # -- mutator application ----------------------------------------------

    def test_mutator_applies_road_multiplier_and_records_both_keys(self):
        self._place_road(0, 1000, 1000)
        self._finish_unit(401, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(401)
        self.assertTrue(st["onRoad"])
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED * ROAD_MULT)
        self.assertEqual(st["source"], "mutator")
        calls = self._g("SET_CALLS")
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[1]["maxSpeed"], VILLAGER_SPEED * ROAD_MULT)
        self.assertAlmostEqual(calls[1]["maxWantedSpeed"], VILLAGER_SPEED * ROAD_MULT)

    def test_off_road_restores_baseline_speed(self):
        self._place_road(0, 1000, 1000)
        self._finish_unit(402, INFANTRY, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertAlmostEqual(self._state(402)["applied"], INFANTRY_SPEED * ROAD_MULT)
        # Move the unit out of the 48-elmo road radius.
        self._g("SetUnitPos")(402, 3000.0, 3000.0)
        self._g("FireGameFrame")(30)
        st = self._state(402)
        self.assertFalse(st["onRoad"])
        self.assertAlmostEqual(st["applied"], INFANTRY_SPEED)
        self.assertEqual(st["source"], "mutator")
        calls = self._g("SET_CALLS")
        self.assertEqual(len(calls), 2)
        self.assertAlmostEqual(calls[2]["maxSpeed"], INFANTRY_SPEED)

    # -- fallback paths ----------------------------------------------------

    def test_rules_param_fallback_when_movectrl_absent(self):
        self._g("SetMoveCtrlEnabled")(False)
        self._place_road(0, 1000, 1000)
        self._finish_unit(501, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(501)
        self.assertEqual(st["source"], "rules-param")
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED * ROAD_MULT)
        self.assertEqual(len(self._g("SET_CALLS")), 0)
        param = self._g("RULES_PARAMS")[501]["medieval_speed_target"]
        self.assertAlmostEqual(param, VILLAGER_SPEED * ROAD_MULT)

    def test_rules_param_fallback_when_mutator_call_raises(self):
        self._g("FireInitialize")()
        self.lua.globals().MOVE_CTRL_ERROR = True
        self._place_road(0, 1000, 1000)
        self._finish_unit(502, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        st = self._state(502)
        self.assertEqual(st["source"], "rules-param")
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED * ROAD_MULT)

    def test_source_none_when_no_engine_support_and_no_crash(self):
        self._g("SetMoveCtrlEnabled")(False)
        self._g("SetRulesParamEnabled")(False)
        self._place_road(0, 1000, 1000)
        self._finish_unit(503, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)  # must not raise
        st = self._state(503)
        self.assertEqual(st["source"], "none")
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED)
        self.assertTrue(st["onRoad"])

    # -- queries and lifecycle --------------------------------------------

    def test_get_speed_state_returns_nil_for_unknown_unit(self):
        self.assertIsNone(self._api().GetSpeedState(9999))
        self.assertIsNone(self._api().GetSpeedState(0))

    def test_destroyed_and_taken_units_leave_the_speed_table(self):
        self._finish_unit(601, VILLAGER, 0, 1000.0, 1000.0)
        self._finish_unit(602, VILLAGER, 0, 1000.0, 1000.0)
        self.assertIsNotNone(self._state(601))
        self._g("FireUnitDestroyed")(601, VILLAGER, 0)
        self.assertIsNone(self._state(601))
        self._g("FireUnitTaken")(602, VILLAGER, 0, 1)
        self.assertIsNone(self._state(602))

    def test_unit_given_retracks_under_receiving_team(self):
        # Team 0 has no road near the unit; team 1 does.
        self._place_road(0, 3000, 3000)
        self._finish_unit(701, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertAlmostEqual(self._state(701)["applied"], VILLAGER_SPEED)
        self._place_road(1, 1000, 1000)
        self._g("FireUnitGiven")(701, VILLAGER, 1, 0)
        self._g("FireGameFrame")(30)
        st = self._state(701)
        self.assertTrue(st["onRoad"])
        self.assertAlmostEqual(st["applied"], VILLAGER_SPEED * ROAD_MULT)

    # -- throttle and radius fidelity -------------------------------------

    def test_scan_is_throttled_to_every_15_frames_and_idempotent(self):
        self._place_road(0, 1000, 1000)
        self._finish_unit(801, VILLAGER, 0, 1000.0, 1000.0)
        self._g("FireGameFrame")(7)   # off-interval: no scan
        self.assertEqual(len(self._g("SET_CALLS")), 0)
        self.assertEqual(self._state(801)["source"], "none")
        self._g("FireGameFrame")(15)  # first scan applies once
        self.assertEqual(len(self._g("SET_CALLS")), 1)
        self._g("FireGameFrame")(16)  # off-interval: no scan
        self._g("FireGameFrame")(30)  # scan with unchanged target: no re-apply
        self.assertEqual(len(self._g("SET_CALLS")), 1)

    def test_on_road_uses_48_elmo_radius_not_graph_link_radius(self):
        # Road node at (1000, 1000). 40 elmos away is on-road; 50 elmos away is
        # NOT (it is inside the graph's 64-elmo LINK_RADIUS, so this pins the
        # helper choice to logistics.isPositionOnRoad / ROAD_PROXIMITY_RADIUS).
        self._place_road(0, 1000, 1000)
        self._finish_unit(901, VILLAGER, 0, 1040.0, 1000.0)
        self._finish_unit(902, VILLAGER, 0, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)
        self.assertTrue(self._state(901)["onRoad"])
        self.assertAlmostEqual(self._state(901)["applied"], VILLAGER_SPEED * ROAD_MULT)
        self.assertFalse(self._state(902)["onRoad"])
        self.assertAlmostEqual(self._state(902)["applied"], VILLAGER_SPEED)


if __name__ == "__main__":
    unittest.main()
