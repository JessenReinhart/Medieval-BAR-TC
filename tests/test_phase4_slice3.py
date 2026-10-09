"""
Phase-4 Slice 3 tests: equipment crafting (blacksmith/fletcher) and the
equipment gate on high-tier recruitment.

Covers three layers, each against the real repository files:

1. `units/medieval_blacksmith.lua` / `units/medieval_fletcher.lua` — identity
   (`name`, `isFactory`) and the `customparams.crafting` kind that binds each
   building to exactly one recipe ("sword" / "bow"), plus its discrete
   `resource_cost_*` build costs.
2. `luarules/gadgets/gadget_production_chains.lua` — the crafting cadence
   (CRAFT_INTERVAL = 30 frames), the per-kind recipes
   (sword = { iron = 5, wood = 2 }, bow = { wood = 5, iron = 1 }), consumption
   through GG.MedievalEconomy.Transact, and the resulting per-team equipment
   stock published as GG.MedievalLogistics.equipmentStock / CraftingStock.
3. `scripts/medieval_recruitment.lua` — the pure equipment gate
   (EQUIPMENT / equipmentFor / hasEquipment / teamEquipmentStock): a high-tier
   unit is blocked at stock 0 and allowed at stock > 0.

Each test boots its OWN fresh Lua runtime (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
BLACKSMITH_PATH = ROOT / "units" / "medieval_blacksmith.lua"
FLETCHER_PATH = ROOT / "units" / "medieval_fletcher.lua"
CHAINS_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_production_chains.lua"
RECRUITMENT_PATH = ROOT / "scripts" / "medieval_recruitment.lua"

# UnitDef ids used by the crafting-gadget harness stubs.
BLACKSMITH, FLETCHER, INFANTRY, BLACKSMITH_PLAIN = 1, 2, 3, 4

# Recipes mirrored from CRAFT_KINDS in gadget_production_chains.lua.
SWORD_COST = {"iron": 5, "wood": 2}
BOW_COST = {"wood": 5, "iron": 1}

CRAFT_INTERVAL = 30


class TestSlice3CrafterUnitDefs(unittest.TestCase):
    """Crafter datadefs: identity + the crafting kind each one produces."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.blacksmith = self.lua.execute(BLACKSMITH_PATH.read_text(encoding="utf-8"))
        self.fletcher = self.lua.execute(FLETCHER_PATH.read_text(encoding="utf-8"))
        self.recruit = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))

    def test_blacksmith_identity_and_crafting_kind(self):
        def_ = self.blacksmith["medieval_blacksmith"]
        self.assertEqual(def_["name"], "Blacksmith")
        self.assertEqual(def_["customparams"]["crafting"], "sword")
        self.assertTrue(def_["isFactory"])
        self.assertFalse(def_["canMove"])
        self.assertFalse(def_["builder"])

    def test_fletcher_identity_and_crafting_kind(self):
        def_ = self.fletcher["medieval_fletcher"]
        self.assertEqual(def_["name"], "Fletcher")
        self.assertEqual(def_["customparams"]["crafting"], "bow")
        self.assertTrue(def_["isFactory"])
        self.assertFalse(def_["canMove"])
        self.assertFalse(def_["builder"])

    def test_crafter_build_costs_are_discrete(self):
        for def_ in (self.blacksmith["medieval_blacksmith"],
                     self.fletcher["medieval_fletcher"]):
            self.assertEqual(def_["buildCostEnergy"], 0)
            self.assertGreater(def_["buildCostMetal"], 0)
            self.assertGreater(def_["customparams"]["resource_cost_wood"], 0)
            self.assertGreater(def_["customparams"]["resource_cost_iron"], 0)

    def test_crafting_kinds_cover_recruitment_equipment(self):
        # Every equipment resource the recruitment gate can demand must be a kind
        # that some crafter unitdef actually produces.
        produced = {
            self.blacksmith["medieval_blacksmith"]["customparams"]["crafting"],
            self.fletcher["medieval_fletcher"]["customparams"]["crafting"],
        }
        self.assertEqual(produced, {"sword", "bow"})
        for unit_name in ("medieval_cavalry", "medieval_catapult", "medieval_archer"):
            self.assertIn(self.recruit.equipmentFor(unit_name), produced)


class TestSlice3CraftingGadget(unittest.TestCase):
    """Real gadget behaviour in a fresh per-test Lua VM with engine stubs."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = CHAINS_GADGET_PATH.read_text(encoding="utf-8")
        g.BLACKSMITH = BLACKSMITH
        g.FLETCHER = FLETCHER
        g.INFANTRY = INFANTRY
        g.BLACKSMITH_PLAIN = BLACKSMITH_PLAIN
        g.SWORD_IRON = SWORD_COST["iron"]
        g.SWORD_WOOD = SWORD_COST["wood"]
        g.BOW_WOOD = BOW_COST["wood"]
        g.BOW_IRON = BOW_COST["iron"]
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        TEAM_LIST = {0, 1}
        UNITS = {}
        STOCKPILES = {}
        gadget = {}
        gadgetHandler = {
          IsSyncedCode = function() return true end,
        }
        GG = {}

        UnitDefs = {
          [BLACKSMITH]       = { name = "medieval_blacksmith",
                                 customParams = { crafting = "sword" } },
          [FLETCHER]         = { name = "medieval_fletcher",
                                 customParams = { crafting = "bow" } },
          [INFANTRY]         = { name = "medieval_infantry" },
          -- Same unitdef name, no customParams: exercises the name fallback in
          -- kindForDef.
          [BLACKSMITH_PLAIN] = { name = "medieval_blacksmith" },
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
        }

        -- Economy stub: Transact is the only entry point the crafting gadget uses.
        GG.MedievalEconomy = {
          Transact = function(teamID, costs)
            local stock = STOCKPILES[teamID]
            if not stock then return false end
            for resource, amount in pairs(costs) do
              if (stock[resource] or 0) < amount then return false end
            end
            for resource, amount in pairs(costs) do
              stock[resource] = stock[resource] - amount
            end
            return true
          end,
        }

        -- Harness helpers ------------------------------------------------------
        function SetStockpile(team, wood, iron)
          STOCKPILES[team] = { wood = wood, iron = iron }
        end
        function StockOf(team, resource)
          local s = STOCKPILES[team]
          if not s then return 0 end
          return s[resource] or 0
        end
        function CraftingStock(team, kind)
          return GG.MedievalLogistics.CraftingStock(team, kind)
        end
        function LastEcho() return ECHO_LINES[#ECHO_LINES] end
        function FireInitialize() gadget:Initialize() end
        function FireUnitCreated(id, defID, team)
          UNITS[id] = { defID = defID, team = team }
          gadget:UnitCreated(id, defID, team)
        end
        function FireUnitDestroyed(id)
          UNITS[id] = nil
          gadget:UnitDestroyed(id)
        end
        function FireGameFrame(frame) gadget:GameFrame(frame) end

        assert(load(GADGET_SRC, "@gadget_production_chains.lua", "t", _G))()
        """)
        self._g("FireInitialize")()

    def _g(self, name):
        return self.lua.globals()[name]

    def _set_stockpile(self, team, wood, iron):
        self._g("SetStockpile")(team, wood, iron)

    def _stock(self, team, kind):
        return self._g("CraftingStock")(team, kind)

    def _resource(self, team, resource):
        return self._g("StockOf")(team, resource)

    # -- sword recipe (blacksmith) --------------------------------------------

    def test_blacksmith_consumes_iron_and_wood_for_one_sword(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(101, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)
        self.assertEqual(self._resource(0, "iron"), 50 - SWORD_COST["iron"])
        self.assertEqual(self._resource(0, "wood"), 200 - SWORD_COST["wood"])

    def test_sword_craft_is_cadence_gated(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(102, BLACKSMITH, 0)
        self._g("FireGameFrame")(15)
        self.assertEqual(self._stock(0, "sword"), 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)

    def test_blacksmith_blocked_below_iron_threshold(self):
        # iron 4 < recipe 5: nothing is crafted and nothing is consumed.
        self._set_stockpile(0, 200, SWORD_COST["iron"] - 1)
        self._g("FireUnitCreated")(103, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 0)
        self.assertEqual(self._resource(0, "iron"), SWORD_COST["iron"] - 1)
        self.assertEqual(self._resource(0, "wood"), 200)

    def test_blacksmith_blocked_below_wood_threshold(self):
        # wood 1 < recipe 2 even though iron is plentiful.
        self._set_stockpile(0, SWORD_COST["wood"] - 1, 50)
        self._g("FireUnitCreated")(104, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 0)
        self.assertEqual(self._resource(0, "iron"), 50)

    def test_two_blacksmiths_craft_two_swords_per_tick(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(105, BLACKSMITH, 0)
        self._g("FireUnitCreated")(106, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 2)
        self.assertEqual(self._resource(0, "iron"), 50 - 2 * SWORD_COST["iron"])

    def test_blacksmith_stops_once_stockpile_is_exhausted(self):
        self._set_stockpile(0, SWORD_COST["wood"], SWORD_COST["iron"])
        self._g("FireUnitCreated")(107, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)
        self._g("FireGameFrame")(CRAFT_INTERVAL * 2)
        self.assertEqual(self._stock(0, "sword"), 1)

    # -- bow recipe (fletcher) ------------------------------------------------

    def test_fletcher_consumes_wood_and_iron_for_one_bow(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(111, FLETCHER, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "bow"), 1)
        self.assertEqual(self._resource(0, "wood"), 200 - BOW_COST["wood"])
        self.assertEqual(self._resource(0, "iron"), 50 - BOW_COST["iron"])

    def test_fletcher_blocked_below_wood_threshold(self):
        self._set_stockpile(0, BOW_COST["wood"] - 1, 50)
        self._g("FireUnitCreated")(112, FLETCHER, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "bow"), 0)
        self.assertEqual(self._resource(0, "iron"), 50)

    def test_both_kinds_craft_independently_on_one_team(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(121, BLACKSMITH, 0)
        self._g("FireUnitCreated")(122, FLETCHER, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)
        self.assertEqual(self._stock(0, "bow"), 1)

    # -- tracking / lifecycle -------------------------------------------------

    def test_non_crafter_unit_is_not_tracked(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(131, INFANTRY, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 0)
        self.assertEqual(self._stock(0, "bow"), 0)

    def test_crafting_kind_falls_back_to_unitdef_name(self):
        # No customParams: kindForDef matches the "medieval_blacksmith" name.
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(141, BLACKSMITH_PLAIN, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)

    def test_destroyed_crafter_stops_producing(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(151, BLACKSMITH, 0)
        self._g("FireUnitDestroyed")(151)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 0)

    def test_stock_is_isolated_per_team(self):
        self._set_stockpile(0, 200, 50)
        self._set_stockpile(1, 200, 50)
        self._g("FireUnitCreated")(161, BLACKSMITH, 0)
        self._g("FireUnitCreated")(162, FLETCHER, 1)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        self.assertEqual(self._stock(0, "sword"), 1)
        self.assertEqual(self._stock(0, "bow"), 0)
        self.assertEqual(self._stock(1, "bow"), 1)
        self.assertEqual(self._stock(1, "sword"), 0)

    def test_stock_is_published_on_logistics_api(self):
        self._set_stockpile(0, 200, 50)
        self._g("FireUnitCreated")(171, BLACKSMITH, 0)
        self._g("FireGameFrame")(CRAFT_INTERVAL)
        api = self._g("GG").MedievalLogistics
        self.assertEqual(api.CraftingStock(0, "sword"), 1)
        self.assertEqual(api.equipmentStock[0]["sword"], 1)
        self.assertEqual(api.CraftingStock(7, "sword"), 0)
        self.assertIn("PHASE4 CRAFT kind=sword", self._g("LastEcho")())


class TestSlice3EquipmentGating(unittest.TestCase):
    """Pure equipment gate in scripts/medieval_recruitment.lua."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.recruit = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))

    def _api(self, src):
        return self.lua.eval(src)

    # -- requirement table ----------------------------------------------------

    def test_equipment_requirements(self):
        self.assertEqual(self.recruit.equipmentFor("medieval_cavalry"), "sword")
        self.assertEqual(self.recruit.equipmentFor("medieval_catapult"), "sword")
        self.assertEqual(self.recruit.equipmentFor("medieval_archer"), "bow")

    def test_ungated_units_have_no_requirement(self):
        self.assertIsNone(self.recruit.equipmentFor("medieval_infantry"))
        self.assertIsNone(self.recruit.equipmentFor("medieval_villager"))
        self.assertIsNone(self.recruit.equipmentFor(None))

    # -- block at 0 / allow above 0 -------------------------------------------

    def test_high_tier_blocked_at_zero_stock(self):
        for unit_name, kind in (("medieval_cavalry", "sword"),
                                ("medieval_catapult", "sword"),
                                ("medieval_archer", "bow")):
            stock = self.lua.table(**{kind: 0})
            self.assertFalse(self.recruit.hasEquipment(stock, unit_name))

    def test_high_tier_allowed_at_positive_stock(self):
        stock = self.lua.table(sword=1, bow=1)
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_cavalry"))
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_catapult"))
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_archer"))
        rich = self.lua.table(sword=12, bow=7)
        self.assertTrue(self.recruit.hasEquipment(rich, "medieval_archer"))

    def test_ungated_units_ignore_stock(self):
        self.assertTrue(self.recruit.hasEquipment(None, "medieval_infantry"))
        self.assertTrue(self.recruit.hasEquipment(self.lua.table(), "medieval_infantry"))

    def test_missing_or_malformed_stock_blocks_gated_units(self):
        self.assertFalse(self.recruit.hasEquipment(None, "medieval_archer"))
        self.assertFalse(self.recruit.hasEquipment(self.lua.table(), "medieval_archer"))
        # Non-numeric amounts do not satisfy the gate.
        self.assertFalse(self.recruit.hasEquipment(self.lua.table(bow="many"),
                                                   "medieval_archer"))

    # -- team stock resolution (the path the gadgets use) ---------------------

    def test_team_stock_resolves_nested_table_form(self):
        api = self._api("({ equipmentStock = { [0] = { sword = 2 }, [1] = { bow = 1 } } })")
        self.assertEqual(self.recruit.teamEquipmentStock(api, 0)["sword"], 2)
        self.assertEqual(self.recruit.teamEquipmentStock(api, 1)["bow"], 1)

    def test_team_stock_resolves_function_form(self):
        api = self._api(
            "({ equipmentStock = function(teamID)"
            " if teamID == 0 then return { sword = 5 } end return nil end })")
        self.assertEqual(self.recruit.teamEquipmentStock(api, 0)["sword"], 5)
        self.assertIsNone(self.recruit.teamEquipmentStock(api, 1))

    def test_team_stock_falls_back_to_flat_table(self):
        api = self._api("({ equipmentStock = { sword = 3 } })")
        self.assertEqual(self.recruit.teamEquipmentStock(api, 0)["sword"], 3)

    def test_team_stock_is_nil_without_api(self):
        self.assertIsNone(self.recruit.teamEquipmentStock(None, 0))
        self.assertIsNone(self.recruit.teamEquipmentStock(self.lua.table(), 0))

    def test_team_without_entry_blocks_gated_units(self):
        # A nested stock table with no row for the team resolves to the outer
        # table, which carries no equipment resource -> gated units are blocked.
        api = self._api("({ equipmentStock = { [0] = { sword = 1 } } })")
        stock = self.recruit.teamEquipmentStock(api, 7)
        self.assertFalse(self.recruit.hasEquipment(stock, "medieval_archer"))

    def test_gate_end_to_end_blocks_then_allows(self):
        empty = self._api("({ equipmentStock = { [0] = { sword = 0, bow = 0 } } })")
        stock = self.recruit.teamEquipmentStock(empty, 0)
        self.assertFalse(self.recruit.hasEquipment(stock, "medieval_cavalry"))
        self.assertFalse(self.recruit.hasEquipment(stock, "medieval_archer"))

        crafted = self._api("({ equipmentStock = { [0] = { sword = 1, bow = 0 } } })")
        stock = self.recruit.teamEquipmentStock(crafted, 0)
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_cavalry"))
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_catapult"))
        self.assertFalse(self.recruit.hasEquipment(stock, "medieval_archer"))


if __name__ == "__main__":
    unittest.main()
