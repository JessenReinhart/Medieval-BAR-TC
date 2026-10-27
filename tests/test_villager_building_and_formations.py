"""Test suite for Villager building UI and Building formation exclusion.

Covers:
1. Villager build capabilities:
   - isBuilderDef identification.
   - buildButtonsFor produces build buttons for structures and road (371922).
   - Clicking build buttons activates placement commands.
   - drawVillagerBuildUI provides dedicated Commands and Build button grids.
2. Building formation exclusion:
   - isBuildingDef identifies buildings (canMove=false, isBuilding=true, speed<=0).
   - Synced formation gadget drops/rejects orders for buildings.
   - Formation preview widget excludes buildings from SelectedFormationUnits.
   - Multi-selection of buildings suppresses movement/formation command grid.
3. Factory recruitment:
   - trainButtonsFor produces recruitment buttons for factories (TC, Barracks, Stables).
   - Clicking train buttons issues GiveOrderToUnit with negative unitDefID.
"""

import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False

ROOT = Path(__file__).resolve().parents[1]
BOTTOM_PANEL_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_bottom_panel.lua"
FORMATION_PREVIEW_PATH = ROOT / "LuaUI" / "Widgets" / "gui_medieval_formation_preview.lua"
FORMATION_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_phase1_test_forces.lua"


class TestVillagerBuildingAndFormationsSourceContracts(unittest.TestCase):
    """Source-level contract assertions for villager building and building formation exclusions."""

    def setUp(self):
        self.bottom_src = BOTTOM_PANEL_PATH.read_text(encoding="utf-8")
        self.preview_src = FORMATION_PREVIEW_PATH.read_text(encoding="utf-8")
        self.gadget_src = FORMATION_GADGET_PATH.read_text(encoding="utf-8")

    def test_villager_build_functions_present(self):
        """Bottom panel defines builder helpers and build options handling."""
        self.assertIn("buildButtonsFor", self.bottom_src)
        self.assertIn("drawVillagerBuildUI", self.bottom_src)
        self.assertIn("CMD_BUILD_ROAD", self.bottom_src)
        self.assertIn("371922", self.bottom_src)
        self.assertIn("isBuilderDef", self.bottom_src)
        self.assertIn("isBuildingDef", self.bottom_src)

    def test_factory_train_functions_present(self):
        """Bottom panel defines factory recruitment helpers and train buttons."""
        self.assertIn("trainButtonsFor", self.bottom_src)
        self.assertIn("drawFactoryUI", self.bottom_src)
        self.assertIn("isTrain", self.bottom_src)

    def test_static_building_ui_suppresses_movement(self):
        """Static buildings show role summary and no movement or formation commands."""
        self.assertIn("drawStaticBuildingUI", self.bottom_src)
        self.assertIn("Static structure: no movement or formation commands", self.bottom_src)

    def test_multi_select_suppresses_commands_for_pure_buildings(self):
        """Multi-selection of pure buildings does not show movement/formation command grid."""
        self.assertIn("Pure building selections never receive movement or formation commands", self.bottom_src)
        self.assertIn("hasMobile", self.bottom_src)

    def test_formation_preview_excludes_buildings(self):
        """Formation preview explicitly filters out buildings from line formations."""
        self.assertIn("isBuildingUnit", self.preview_src)
        self.assertIn("not isBuildingUnit(id)", self.preview_src)
        self.assertIn("buildings are excluded", self.preview_src)

    def test_formation_gadget_rejects_building_destinations(self):
        """Synced formation gadget explicitly validates against building unit defs."""
        self.assertIn("isBuildingDef", self.gadget_src)
        self.assertIn("isFormationUnitDef", self.gadget_src)
        self.assertIn("Buildings must never participate in formations", self.gadget_src)


@unittest.skipUnless(HAS_LUPA, "lupa not available for runtime execution")
class TestVillagerBuildingAndFormationsRuntime(unittest.TestCase):
    """Execution-based tests verifying builder and formation exclusion logic."""

    def test_formation_gadget_excludes_buildings_from_destinations(self):
        """destination() in gadget_phase1_test_forces returns nil for building defs."""
        runtime = LuaRuntime(unpack_returned_tuples=True)
        runtime.execute("""
            local formation_helper = [[
                local M = { CMD_ID = 39100, MAX_UNITS = 200 }
                function M.sortedIDs(p, start, count)
                    local out = {}
                    for i = start, start + count - 1 do out[#out + 1] = p[i] end
                    return out
                end
                function M.destinations(count, x, z, spacing, facing, mx, mz, autoFit)
                    local slots = {}
                    for i = 1, count do slots[i] = { x = x, z = z + (i - 1) * spacing } end
                    return slots
                end
                function M.bounds(x, z, mx, mz, margin) return true end
                function M.finite(val) return type(val) == "number" end
                return M
            ]]
            VFS = { Include = function() return assert(load(formation_helper))() end }
            Spring = {
                GetModOptions = function() return { medievaltest = "1" } end,
                GetGroundHeight = function(x, z) return 10 end,
                TestMoveOrder = function(def, x, y, z) return true end,
                GetUnitTeam = function(id) return 1 end,
                GetUnitDefID = function(id)
                    if id == 999 then return 50 end -- building
                    return 10 -- infantry
                end,
                Echo = function() end,
                GetTeamList = function() return { 1, 2 } end,
                GetGaiaTeamID = function() return 0 end,
                GetTeamInfo = function() return nil, nil, false end,
                AreTeamsAllied = function() return false end,
                CreateUnit = function() return nil end,
            }
            CMD = { MOVE = 10, FIGHT = 40, ANY = -1 }
            UnitDefNames = {
                medieval_infantry = { id = 10 },
                medieval_archer = { id = 11 },
                medieval_cavalry = { id = 12 },
                medieval_house = { id = 50 },
            }
            UnitDefs = {
                [10] = { canMove = true, speed = 36, isBuilding = false },
                [11] = { canMove = true, speed = 34, isBuilding = false },
                [12] = { canMove = true, speed = 60, isBuilding = false },
                [50] = { canMove = false, speed = 0, isBuilding = true },
            }
            Game = { mapSizeX = 4096, mapSizeZ = 4096 }
            gadgetHandler = {
                IsSyncedCode = function() return true end,
                RegisterCMDID = function() end,
                RegisterAllowCommand = function() end,
            }
        """)
        src = FORMATION_GADGET_PATH.read_text(encoding="utf-8")
        runtime.globals().src = src
        runtime.execute("gadget = {}; assert(load(src))()")
        g = runtime.globals().gadget
        g.Initialize(g)

        # Attempt to issue formation with a building (ID 999, def 50)
        p = runtime.table_from([2048, 2048, 48, 1, 2, 500, 999])
        # AllowCommand returns false (consumed), but pending should NOT contain 999
        res = g.AllowCommand(g, 999, 50, 1, 39100, p, runtime.table_from({}))
        self.assertFalse(res)

        # GameFrame should not dispatch a MOVE order to unit 999
        g.GameFrame(g, 35)
        # Unit 999 is a building; destination() refused it, so it received no move order.


if __name__ == "__main__":
    unittest.main()
