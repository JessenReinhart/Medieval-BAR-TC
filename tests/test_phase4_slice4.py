"""
Phase-4 Slice 4 tests: military upgrades & veteran tiers.

Covers three layers, each against the real repository files:

1. `units/medieval_men_at_arms.lua`, `units/medieval_crossbow.lua` and
   `units/medieval_knight.lua` — identity, the `customparams` tags that bind
   each veteran tier to its tech (`tech_prereq`), its armor class and its
   equipment kind, the discrete `resource_cost_*` costs mirrored by
   `scripts/medieval_recruitment.lua` COSTS, and the housing population each
   tier consumes.
2. Tech unlock policy — `scripts/medieval_recruitment.lua`
   (TECH_PREREQ / techPrereqFor / hasTech) and
   `scripts/medieval_logistics.lua` (TECHS.unlocks / techUnlockPrereq /
   isUnitUnlocked) plus the live gate in
   `luarules/gadgets/gadget_medieval_recruitment.lua`
   (GG.MedievalRecruitment.CanRecruit and AllowUnitCreation): a veteran tier is
   refused while its tech is locked and permitted once the tech is researched
   AND the equipment stock is available.
3. Damage multiplier stacking — `scripts/medieval_logistics.lua`
   damageMultiplier plus the `UnitPreDamaged` path in
   `luarules/gadgets/gadget_medieval_logistics.lua`: a researched tech
   (veteran_infantry 1.15, crossbow_tech 1.15, chivalry 1.20) scales the base
   damage and stacks multiplicatively with the Slice 7 supply bonus
   (1.10 * 1.15 = 1.265) and with the Slice 2 damage-type matrix.

Each test boots its OWN fresh Lua runtime (no shared setUpClass state).
"""

import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
UNITS_DIR = ROOT / "units"
SCRIPTS_DIR = ROOT / "scripts"

MEN_AT_ARMS_PATH = UNITS_DIR / "medieval_men_at_arms.lua"
CROSSBOW_PATH = UNITS_DIR / "medieval_crossbow.lua"
KNIGHT_PATH = UNITS_DIR / "medieval_knight.lua"
RECRUITMENT_PATH = SCRIPTS_DIR / "medieval_recruitment.lua"
LOGISTICS_PATH = SCRIPTS_DIR / "medieval_logistics.lua"
HOUSING_PATH = SCRIPTS_DIR / "medieval_housing.lua"
RECRUIT_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_recruitment.lua"
LOGISTICS_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_logistics.lua"

# Veteran tier -> (unitdef file, internal def name, tech prereq, equipment kind)
VETERAN_TIERS = (
    (MEN_AT_ARMS_PATH, "medieval_men_at_arms", "veteran_infantry", "sword"),
    (CROSSBOW_PATH, "medieval_crossbow", "crossbow_tech", "bow"),
    (KNIGHT_PATH, "medieval_knight", "chivalry", "sword"),
)

# Expected damage bonus each unlock tech contributes to its veteran tier.
TECH_DAMAGE_MULT = {
    "veteran_infantry": 1.15,
    "crossbow_tech": 1.15,
    "chivalry": 1.20,
}

BONUS_PER_ENDPOINT = 0.10

# UnitDef / WeaponDef ids used by the gadget harness stubs.
INFANTRY, ARCHER, CAVALRY = 1, 2, 3
MEN_AT_ARMS, CROSSBOW, KNIGHT = 4, 5, 6
GRANARY, WALL = 7, 8
SWORD_WPN, LONGBOW_WPN, LANCE_WPN = 10, 11, 12
ROAD_FDEF = 20


def _lua_to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists."""
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class TestSlice4VeteranUnitDefs(unittest.TestCase):
    """Veteran-tier datadefs: identity, tech tags, costs and pop consumption."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.recruit = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))
        self.housing = self.lua.execute(HOUSING_PATH.read_text(encoding="utf-8"))
        self.defs = {}
        for path, name, _tech, _equip in VETERAN_TIERS:
            table = self.lua.execute(path.read_text(encoding="utf-8"))
            self.defs[name] = _lua_to_py(self.lua, table[name])

    # -- identity -------------------------------------------------------------

    def test_men_at_arms_identity(self):
        def_ = self.defs["medieval_men_at_arms"]
        self.assertEqual(def_["name"], "Veteran Man-at-Arms")
        self.assertEqual(def_["category"], "LAND")
        self.assertTrue(def_["canMove"])
        self.assertTrue(def_["canAttack"])
        self.assertFalse(def_["builder"])
        self.assertEqual(def_["side"], "MEDIEVAL")

    def test_crossbow_identity(self):
        def_ = self.defs["medieval_crossbow"]
        self.assertEqual(def_["name"], "Crossbowman")
        self.assertEqual(def_["category"], "LAND")
        self.assertTrue(def_["canMove"])
        self.assertTrue(def_["canAttack"])
        self.assertFalse(def_["builder"])
        self.assertEqual(def_["side"], "MEDIEVAL")

    def test_knight_identity(self):
        def_ = self.defs["medieval_knight"]
        self.assertEqual(def_["name"], "Chivalric Knight")
        self.assertEqual(def_["category"], "LAND")
        self.assertTrue(def_["canMove"])
        self.assertTrue(def_["canAttack"])
        self.assertFalse(def_["builder"])
        self.assertEqual(def_["side"], "MEDIEVAL")

    def test_display_names_stay_distinct_from_phase1_tiers(self):
        # The veteran tiers reuse the Phase 1 art/scripts, so their display names
        # must not collide with the base defs they upgrade from.
        names = {name: self.defs[name]["name"] for _p, name, _t, _e in VETERAN_TIERS}
        self.assertEqual(len(set(names.values())), 3)
        self.assertNotIn("Man-at-Arms", names.values())
        self.assertNotIn("Knight", names.values())

    # -- customparams ---------------------------------------------------------

    def test_tech_prereq_customparams(self):
        for _path, name, tech, _equip in VETERAN_TIERS:
            cp = self.defs[name]["customparams"]
            self.assertEqual(cp["tech_prereq"], tech)
            self.assertEqual(self.recruit.techPrereqFor(name), tech)

    def test_armor_class_is_standard_for_every_veteran_tier(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            cp = self.defs[name]["customparams"]
            self.assertEqual(cp["armor_class"], "standard")

    def test_role_customparams_are_military(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            cp = self.defs[name]["customparams"]
            self.assertEqual(cp["unit_role"], "military")
            self.assertEqual(cp["unitgroup"], "weapon")
            self.assertEqual(cp["model_author"], "Medieval-BAR-TC")

    def test_equipment_needed_matches_recruitment_gate(self):
        for _path, name, _tech, equip in VETERAN_TIERS:
            cp = self.defs[name]["customparams"]
            self.assertEqual(cp["equipment_needed"], equip)
            self.assertEqual(self.recruit.equipmentFor(name), equip)

    # -- costs ----------------------------------------------------------------

    def test_discrete_resource_costs_mirror_recruitment(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            cp = self.defs[name]["customparams"]
            cost = self.recruit.getCost(name)
            self.assertIsNotNone(cost)
            for resource in ("food", "wood", "stone", "iron"):
                self.assertEqual(cost[resource], cp["resource_cost_" + resource])

    def test_costs_are_energy_free_and_metal_priced(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            def_ = self.defs[name]
            self.assertEqual(def_["buildCostEnergy"], 0)
            self.assertGreater(def_["buildCostMetal"], 0)

    def test_veteran_tiers_cost_more_metal_than_their_base_tier(self):
        pairs = (
            ("medieval_men_at_arms", "medieval_infantry", 100),
            ("medieval_crossbow", "medieval_archer", 90),
            ("medieval_knight", "medieval_cavalry", 220),
        )
        for veteran, base, base_metal in pairs:
            self.assertGreater(self.defs[veteran]["buildCostMetal"], base_metal)
            self.assertGreater(self.defs[veteran]["maxDamage"], 0)
            self.assertGreater(self.defs[veteran]["buildTime"], 0)

    def test_knight_is_the_most_expensive_veteran_tier(self):
        metals = {name: self.defs[name]["buildCostMetal"] for _p, name, _t, _e in VETERAN_TIERS}
        self.assertEqual(max(metals, key=metals.get), "medieval_knight")
        self.assertGreater(metals["medieval_knight"], metals["medieval_men_at_arms"])
        self.assertGreater(metals["medieval_men_at_arms"], metals["medieval_crossbow"])

    # -- housing / population -------------------------------------------------

    def test_housing_population_consumption(self):
        self.assertEqual(self.housing.unitConsumesPop("medieval_men_at_arms"), 1)
        self.assertEqual(self.housing.unitConsumesPop("medieval_crossbow"), 1)
        # The mounted noble retinue takes two population slots.
        self.assertEqual(self.housing.unitConsumesPop("medieval_knight"), 2)

    def test_knight_two_slot_cost_is_enforced_by_the_pop_cap(self):
        cap = self.housing.computeCap(self.lua.table(medieval_town_center=1, medieval_house=2))
        self.assertEqual(cap, 30)
        self.assertTrue(self.housing.canSupport(28, cap, 2))
        self.assertFalse(self.housing.canSupport(29, cap, 2))
        # The foot tiers only need one slot.
        self.assertTrue(self.housing.canSupport(29, cap, 1))

    def test_veteran_tiers_pay_military_upkeep(self):
        self.assertTrue(self.recruit.isMilitary("medieval_men_at_arms"))
        self.assertTrue(self.recruit.isMilitary("medieval_crossbow"))
        self.assertTrue(self.recruit.isMilitary("medieval_knight"))
        self.assertEqual(self.recruit.upkeepFor("medieval_men_at_arms"), 3)
        self.assertEqual(self.recruit.upkeepFor("medieval_crossbow"), 3)
        self.assertEqual(self.recruit.upkeepFor("medieval_knight"), 4)

    # -- movement / art -------------------------------------------------------

    def test_movementclass_agrees_with_footprint(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            def_ = self.defs[name]
            if def_["footprintX"] == 3:
                self.assertEqual(def_["movementclass"], "TANK3")
                self.assertEqual(def_["footprintZ"], 3)
            else:
                self.assertEqual(def_["movementclass"], "BOT2")
                self.assertEqual((def_["footprintX"], def_["footprintZ"]), (2, 2))

    def test_speed_follows_the_15x_velocity_convention(self):
        self.assertEqual(self.defs["medieval_men_at_arms"]["speed"], 20)
        self.assertEqual(self.defs["medieval_crossbow"]["speed"], 18)
        self.assertEqual(self.defs["medieval_knight"]["speed"], 33)
        for _path, name, _tech, _equip in VETERAN_TIERS:
            def_ = self.defs[name]
            self.assertAlmostEqual(def_["speed"], def_["maxVelocity"] * 15, delta=1)

    def test_reuses_base_tier_art_and_script(self):
        expected = {
            "medieval_men_at_arms": ("0ad/medieval_infantry.obj", "medieval_infantry.lua"),
            "medieval_crossbow": ("0ad/medieval_archer.obj", "medieval_archer.lua"),
            "medieval_knight": ("0ad/medieval_cavalry.obj", "medieval_cavalry.lua"),
        }
        for name, (obj, script) in expected.items():
            def_ = self.defs[name]
            self.assertEqual(def_["objectName"], obj)
            self.assertEqual(def_["script"], script)
            self.assertTrue((ROOT / "objects3d" / obj).is_file())
            self.assertTrue((SCRIPTS_DIR / script).is_file())

    def test_weapon_tables_are_present(self):
        self.assertEqual(len(self.defs["medieval_men_at_arms"]["weapons"]), 1)
        self.assertEqual(self.defs["medieval_men_at_arms"]["weapons"][0]["name"], "sword")
        self.assertEqual(self.defs["medieval_crossbow"]["weapons"][0]["name"], "longbow")
        self.assertEqual(self.defs["medieval_knight"]["weapons"][0]["name"], "lance")


class TestSlice4TechUnlockPolicy(unittest.TestCase):
    """Pure tech-gate policy in the recruitment + logistics modules."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.recruit = self.lua.execute(RECRUITMENT_PATH.read_text(encoding="utf-8"))
        self.logistics = self.lua.execute(LOGISTICS_PATH.read_text(encoding="utf-8"))

    # -- prerequisite table ---------------------------------------------------

    def test_tech_prereq_table(self):
        for _path, name, tech, _equip in VETERAN_TIERS:
            self.assertEqual(self.recruit.techPrereqFor(name), tech)

    def test_ungated_units_have_no_tech_prereq(self):
        self.assertIsNone(self.recruit.techPrereqFor("medieval_infantry"))
        self.assertIsNone(self.recruit.techPrereqFor("medieval_villager"))
        self.assertIsNone(self.recruit.techPrereqFor(None))
        self.assertIsNone(self.recruit.techPrereqFor(42))

    def test_recruitment_prereqs_match_the_logistics_tech_registry(self):
        # TECH_PREREQ is duplicated in the recruitment module to stay
        # dependency-free; it must still agree with TECHS[*].unlocks.
        for _path, name, tech, _equip in VETERAN_TIERS:
            self.assertEqual(self.logistics.techUnlockPrereq(name), tech)
            self.assertTrue(self.logistics.TECHS[tech].unlocks[name])
            self.assertIsNone(self.logistics.TECHS[tech].prereq)

    # -- locked / unlocked ----------------------------------------------------

    def test_has_tech_blocks_when_registry_is_missing(self):
        # Fail closed: an unpublished unlocked-tech set must never leak a tier.
        self.assertFalse(self.recruit.hasTech(None, "medieval_knight"))
        self.assertFalse(self.recruit.hasTech("chivalry", "medieval_men_at_arms"))

    def test_has_tech_blocks_while_locked(self):
        for _path, name, _tech, _equip in VETERAN_TIERS:
            self.assertFalse(self.recruit.hasTech(self.lua.table(), name))

    def test_has_tech_allows_once_unlocked(self):
        for _path, name, tech, _equip in VETERAN_TIERS:
            unlocked = self.lua.table(**{tech: True})
            self.assertTrue(self.recruit.hasTech(unlocked, name))

    def test_has_tech_ignores_unrelated_techs(self):
        unlocked = self.lua.table(chivalry=True)
        self.assertTrue(self.recruit.hasTech(unlocked, "medieval_knight"))
        self.assertFalse(self.recruit.hasTech(unlocked, "medieval_men_at_arms"))
        self.assertFalse(self.recruit.hasTech(unlocked, "medieval_crossbow"))

    def test_is_unit_unlocked_mirrors_the_recruitment_gate(self):
        unlocked = self.lua.table(veteran_infantry=True)
        self.assertTrue(self.logistics.isUnitUnlocked(unlocked, "medieval_men_at_arms"))
        self.assertFalse(self.logistics.isUnitUnlocked(unlocked, "medieval_crossbow"))
        # Ungated units always pass.
        self.assertTrue(self.logistics.isUnitUnlocked(unlocked, "medieval_infantry"))
        self.assertTrue(self.logistics.isUnitUnlocked(unlocked, "medieval_villager"))

    # -- tech + equipment are independent clauses -----------------------------

    def test_tech_unlocked_without_equipment_is_still_blocked(self):
        unlocked = self.lua.table(chivalry=True)
        self.assertTrue(self.recruit.hasTech(unlocked, "medieval_knight"))
        self.assertFalse(self.recruit.hasEquipment(self.lua.table(), "medieval_knight"))

    def test_equipment_stocked_without_tech_is_still_blocked(self):
        stock = self.lua.table(sword=3)
        self.assertTrue(self.recruit.hasEquipment(stock, "medieval_knight"))
        self.assertFalse(self.recruit.hasTech(self.lua.table(), "medieval_knight"))

    def test_recruitment_requires_tech_and_equipment_together(self):
        unlocked = self.lua.table(veteran_infantry=True, crossbow_tech=True, chivalry=True)
        stock = self.lua.table(sword=1, bow=1)
        for _path, name, _tech, _equip in VETERAN_TIERS:
            self.assertTrue(self.recruit.hasTech(unlocked, name))
            self.assertTrue(self.recruit.hasEquipment(stock, name))

    def test_equipment_kinds_of_the_veteran_tiers(self):
        self.assertEqual(self.recruit.equipmentFor("medieval_men_at_arms"), "sword")
        self.assertEqual(self.recruit.equipmentFor("medieval_knight"), "sword")
        self.assertEqual(self.recruit.equipmentFor("medieval_crossbow"), "bow")
        # A bow stock alone cannot arm the sword tiers.
        self.assertFalse(self.recruit.hasEquipment(self.lua.table(bow=5),
                                                   "medieval_men_at_arms"))


class TestSlice4DamageStacking(unittest.TestCase):
    """Real gadget behaviour: tech * supply * matrix on the damage path."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = LOGISTICS_GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.INFANTRY = INFANTRY
        g.ARCHER = ARCHER
        g.CAVALRY = CAVALRY
        g.MEN_AT_ARMS = MEN_AT_ARMS
        g.CROSSBOW = CROSSBOW
        g.KNIGHT = KNIGHT
        g.GRANARY = GRANARY
        g.WALL = WALL
        g.SWORD_WPN = SWORD_WPN
        g.LONGBOW_WPN = LONGBOW_WPN
        g.LANCE_WPN = LANCE_WPN
        g.ROAD_FDEF = ROAD_FDEF
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        GAME_RULES = {}
        FEATURES = {}
        UNITS = {}
        RULES_PARAMS = {}
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
          [INFANTRY]    = { name = "medieval_infantry", canMove = true, speed = 32 },
          [ARCHER]      = { name = "medieval_archer", canMove = true, speed = 28 },
          [CAVALRY]     = { name = "medieval_cavalry", canMove = true, speed = 54 },
          [MEN_AT_ARMS] = { name = "medieval_men_at_arms", canMove = true, speed = 20,
                            customParams = { armor_class = "standard",
                                             tech_prereq = "veteran_infantry",
                                             equipment_needed = "sword" } },
          [CROSSBOW]    = { name = "medieval_crossbow", canMove = true, speed = 18,
                            customParams = { armor_class = "standard",
                                             tech_prereq = "crossbow_tech",
                                             equipment_needed = "bow" } },
          [KNIGHT]      = { name = "medieval_knight", canMove = true, speed = 33,
                            customParams = { armor_class = "standard",
                                             tech_prereq = "chivalry",
                                             equipment_needed = "sword" } },
          [GRANARY]     = { name = "medieval_granary", canMove = false,
                            customParams = { dropoff = true } },
          [WALL]        = { name = "medieval_wall", canMove = false,
                            customParams = { armor_class = "fortification" } },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        WeaponDefs = {
          [SWORD_WPN]   = { name = "Broadsword", customParams = { damage_class = "melee" } },
          [LONGBOW_WPN] = { name = "Longbow", customParams = { damage_class = "ranged" } },
          [LANCE_WPN]   = { name = "Heavy Lance", customParams = { damage_class = "melee" } },
        }
        WeaponDefNames = {}
        for id, def in pairs(WeaponDefs) do WeaponDefNames[def.name] = { id = id } end

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

        -- A nil stockpile report skips the affordability clause, so Research only
        -- exercises the tech registry (unlock bookkeeping + Transact).
        GG.MedievalEconomy = {
          GetStockpiles = function() return nil end,
          Transact = function(teamID, costs) return true end,
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
        function FireInitialize() gadget:Initialize() end
        function FireUnitFinished(id, defID, team)
          local u = UNITS[id]
          if u then u.progress = 1 end
          gadget:UnitFinished(id, defID or (u and u.defID), team or (u and u.team))
        end
        function FireGameFrame(frame) gadget:GameFrame(frame) end
        function FireUnitPreDamaged(defender, damage, attacker, weaponDefID)
          local attackerDefID = attacker and UNITS[attacker] and UNITS[attacker].defID or nil
          local attackerTeam = attacker and UNITS[attacker] and UNITS[attacker].team or nil
          return gadget:UnitPreDamaged(
            defender, UNITS[defender] and UNITS[defender].defID, UNITS[defender] and UNITS[defender].team,
            damage, false, weaponDefID, nil, attacker, attackerDefID, attackerTeam)
        end
        function EchoLines() return ECHO_LINES end

        assert(load(GADGET_SRC, "@gadget_medieval_logistics.lua", "t", _G))()
        """)
        self._g("FireInitialize")()

    def _g(self, name):
        return self.lua.globals()[name]

    def _api(self):
        return self._g("GG").MedievalLogistics

    def _research(self, team, tech):
        return self._api().Research(team, tech)

    def _place_road(self, team, x, z):
        return self._g("Spring").CreateFeature("medieval_road", float(x), 0.0, float(z), 0, team)

    def _finish_unit(self, unit_id, def_id, team, x, z):
        self._g("PlaceUnit")(unit_id, def_id, float(x), float(z), team, 1)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _finish_building(self, unit_id, def_id, team, x, z):
        self._g("PlaceBuilding")(unit_id, def_id, float(x), float(z), team)
        self._g("FireUnitFinished")(unit_id, def_id, team)

    def _supply_setup(self, attacker_id, attacker_def, team=0):
        """Road + granary endpoint + the attacker inside the supply radius."""
        self._place_road(team, 1000, 1000)
        self._finish_building(attacker_id + 500, GRANARY, team, 1000.0, 1000.0)
        self._finish_unit(attacker_id, attacker_def, team, 1050.0, 1000.0)
        self._g("FireGameFrame")(15)

    # -- registry-derived multipliers -----------------------------------------

    def test_damage_multiplier_per_veteran_tech(self):
        # One fresh team per tech so the multipliers cannot contaminate each other.
        cases = (
            (0, "veteran_infantry", "medieval_men_at_arms"),
            (1, "crossbow_tech", "medieval_crossbow"),
            (2, "chivalry", "medieval_knight"),
        )
        for team, tech, unit_name in cases:
            self.assertTrue(self._research(team, tech))
            self.assertAlmostEqual(self._api().DamageMultiplier(team, unit_name),
                                   TECH_DAMAGE_MULT[tech])

    def test_tech_also_boosts_the_base_tier_it_upgrades(self):
        self._research(0, "veteran_infantry")
        self._research(1, "chivalry")
        api = self._api()
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_infantry"), 1.15)
        self.assertAlmostEqual(api.DamageMultiplier(1, "medieval_cavalry"), 1.20)

    def test_tech_multiplier_does_not_leak_across_units(self):
        self._research(0, "veteran_infantry")
        api = self._api()
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_men_at_arms"), 1.15)
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_archer"), 1.0)
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_crossbow"), 1.0)
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_knight"), 1.0)

    def test_no_tech_is_an_identity_multiplier(self):
        api = self._api()
        for _path, name, _tech, _equip in VETERAN_TIERS:
            self.assertAlmostEqual(api.DamageMultiplier(0, name), 1.0)
            self.assertAlmostEqual(api.DamageMultiplier(7, name), 1.0)
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_unknown_unit"), 1.0)

    # -- UnitPreDamaged: tech only --------------------------------------------

    def test_men_at_arms_tech_damage(self):
        self._research(0, "veteran_infantry")
        self._finish_unit(201, MEN_AT_ARMS, 0, 5000.0, 5000.0)
        self._finish_unit(202, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(202, 100.0, 201, SWORD_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.15)
        echoes = list(self._g("EchoLines")().values())
        self.assertTrue(any("tech_mult=1.15" in e for e in echoes), echoes)

    def test_crossbow_tech_damage(self):
        self._research(0, "crossbow_tech")
        self._finish_unit(211, CROSSBOW, 0, 5000.0, 5000.0)
        self._finish_unit(212, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(212, 100.0, 211, LONGBOW_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.15)

    def test_knight_chivalry_damage(self):
        self._research(0, "chivalry")
        self._finish_unit(221, KNIGHT, 0, 5000.0, 5000.0)
        self._finish_unit(222, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(222, 100.0, 221, LANCE_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.20)

    # -- UnitPreDamaged: supply only ------------------------------------------

    def test_supply_bonus_alone_scales_damage(self):
        self._supply_setup(231, MEN_AT_ARMS)
        api = self._api()
        self.assertAlmostEqual(api.SupplyBonus(231), BONUS_PER_ENDPOINT)
        self.assertTrue(api.InSupply(231))
        self._finish_unit(232, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(232, 100.0, 231, SWORD_WPN)
        self.assertAlmostEqual(damage, 100.0 * (1.0 + BONUS_PER_ENDPOINT))

    def test_unsupplied_attacker_gets_no_supply_bonus(self):
        self._research(0, "chivalry")
        self._finish_unit(241, KNIGHT, 0, 5000.0, 5000.0)
        self._finish_unit(242, ARCHER, 1, 5400.0, 5400.0)
        self.assertAlmostEqual(self._api().SupplyBonus(241), 0.0)
        damage, _ = self._g("FireUnitPreDamaged")(242, 100.0, 241, LANCE_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.20)

    def test_supply_bonus_api_is_zero_for_untracked_units(self):
        self.assertAlmostEqual(self._api().SupplyBonus(9999), 0.0)
        self.assertIsNone(self._api().GetSupplyState(9999))
        self.assertFalse(self._api().InSupply(9999))

    # -- UnitPreDamaged: tech * supply stacking --------------------------------

    def test_supply_and_tech_stack_multiplicatively(self):
        # veteran_infantry 1.15 (men-at-arms) * supply 1.10 = 1.265.
        self._research(0, "veteran_infantry")
        self._supply_setup(251, MEN_AT_ARMS)
        self._finish_unit(252, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(252, 100.0, 251, SWORD_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.15 * (1.0 + BONUS_PER_ENDPOINT))
        self.assertAlmostEqual(damage, 126.5)

    def test_crossbow_tech_and_supply_stack_multiplicatively(self):
        self._research(0, "crossbow_tech")
        self._supply_setup(261, CROSSBOW)
        self._finish_unit(262, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(262, 100.0, 261, LONGBOW_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.15 * (1.0 + BONUS_PER_ENDPOINT))

    def test_chivalry_and_supply_stack_multiplicatively(self):
        self._research(0, "chivalry")
        self._supply_setup(271, KNIGHT)
        self._finish_unit(272, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(272, 100.0, 271, LANCE_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.20 * (1.0 + BONUS_PER_ENDPOINT))

    def test_two_researched_techs_stack_multiplicatively(self):
        # iron_swords 1.25 * veteran_infantry 1.15 on medieval_infantry.
        self._research(0, "iron_swords")
        self._research(0, "veteran_infantry")
        api = self._api()
        self.assertAlmostEqual(api.DamageMultiplier(0, "medieval_infantry"), 1.25 * 1.15)
        self._finish_unit(281, INFANTRY, 0, 5000.0, 5000.0)
        self._finish_unit(282, ARCHER, 1, 5400.0, 5400.0)
        damage, _ = self._g("FireUnitPreDamaged")(282, 100.0, 281, SWORD_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.25 * 1.15)

    def test_tech_supply_and_matrix_stack_multiplicatively(self):
        # men-at-arms (1.15, supplied 1.10) vs wall (melee -> fortification 0.25):
        # final = base * 1.15 * 1.10 * 0.25.
        self._research(0, "veteran_infantry")
        self._supply_setup(291, MEN_AT_ARMS)
        self._finish_building(292, WALL, 1, 2000.0, 2000.0)
        self.assertAlmostEqual(self._api().DamageTypeMultiplier("melee", "fortification"), 0.25)
        damage, _ = self._g("FireUnitPreDamaged")(292, 100.0, 291, SWORD_WPN)
        self.assertAlmostEqual(damage, 100.0 * 1.15 * (1.0 + BONUS_PER_ENDPOINT) * 0.25)

    def test_stack_order_is_irrelevant_but_supply_is_reported_separately(self):
        self._research(0, "veteran_infantry")
        self._supply_setup(301, MEN_AT_ARMS)
        self._finish_unit(302, ARCHER, 1, 5400.0, 5400.0)
        self._g("FireUnitPreDamaged")(302, 100.0, 301, SWORD_WPN)
        # The supply scan publishes its own factor, so the two bonuses stay
        # independently observable on the damage path.
        echoes = [e for e in self._g("EchoLines")().values()]
        self.assertTrue(any("PHASE3 SUPPLY damage" in e for e in echoes))
        self.assertTrue(any("tech_mult=1.15" in e for e in echoes))


class TestSlice4RecruitmentGate(unittest.TestCase):
    """Live gate in gadget_medieval_recruitment.lua: tech AND equipment."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.GADGET_SRC = RECRUIT_GADGET_PATH.read_text(encoding="utf-8")
        g.ROOT_PATH = str(ROOT).replace("\\", "/")
        g.INFANTRY = INFANTRY
        g.MEN_AT_ARMS = MEN_AT_ARMS
        g.CROSSBOW = CROSSBOW
        g.KNIGHT = KNIGHT
        self.lua.execute(r"""
        -- Engine stubs ---------------------------------------------------------
        ECHO_LINES = {}
        DESTROYED = {}
        UNLOCKED = {}
        EQUIPMENT_STOCK = {}
        POP = {}
        CAP = {}
        TEAM_LIST = {0, 1}
        gadget = {}
        gadgetHandler = { IsSyncedCode = function() return true end }
        GG = {}

        UnitDefs = {
          [INFANTRY]    = { name = "medieval_infantry",
                            customParams = { resource_cost_food = 30, resource_cost_wood = 20,
                                             resource_cost_stone = 10, resource_cost_iron = 5 } },
          [MEN_AT_ARMS] = { name = "medieval_men_at_arms",
                            customParams = { resource_cost_food = 45, resource_cost_wood = 25,
                                             resource_cost_stone = 15, resource_cost_iron = 15 } },
          [CROSSBOW]    = { name = "medieval_crossbow",
                            customParams = { resource_cost_food = 35, resource_cost_wood = 45,
                                             resource_cost_stone = 5, resource_cost_iron = 10 } },
          [KNIGHT]      = { name = "medieval_knight",
                            customParams = { resource_cost_food = 70, resource_cost_wood = 25,
                                             resource_cost_stone = 25, resource_cost_iron = 40 } },
        }
        UnitDefNames = {}
        for id, def in pairs(UnitDefs) do UnitDefNames[def.name] = { id = id } end

        Spring = {
          Echo = function(fmt, ...)
            local ok, msg = pcall(string.format, fmt, ...)
            table.insert(ECHO_LINES, ok and msg or tostring(fmt))
          end,
          GetTeamList = function() return TEAM_LIST end,
          GetTeamUnits = function() return {} end,
          GetUnitDefID = function(id) return nil end,
          GetUnitHealth = function(id) return 100 end,
          SetGameRulesParam = function(k, v) GAME_RULES = GAME_RULES or {}; GAME_RULES[k] = v end,
          SetUnitHealth = function(id, hp) return true end,
          DestroyUnit = function(id) table.insert(DESTROYED, id) end,
        }

        VFS = {
          Include = function(path)
            local fh = assert(io.open(ROOT_PATH .. "/" .. path, "r"))
            local src = fh:read("*a")
            fh:close()
            return assert(load(src, "@" .. path, "t", _G))()
          end,
        }

        -- The tech prerequisite registry is the real logistics module, so the
        -- harness exercises the same TECHS[*].unlocks mapping the game uses.
        local logistics = VFS.Include("scripts/medieval_logistics.lua")
        GG.MedievalLogistics = {
          equipmentStock = EQUIPMENT_STOCK,
          TechUnlockPrereq = function(unitName) return logistics.techUnlockPrereq(unitName) end,
          IsTechUnlocked = function(teamID, techID)
            return UNLOCKED[teamID] and UNLOCKED[teamID][techID] == true
          end,
        }
        GG.MedievalHousing = {
          GetPopulation = function(teamID) return POP[teamID] or 0 end,
          GetCap = function(teamID) return CAP[teamID] or 100 end,
        }
        GG.MedievalEconomy = {
          CanAfford = function(teamID, costs) return true end,
          Transact = function(teamID, costs) return true end,
        }

        -- Harness helpers ------------------------------------------------------
        function Unlock(team, tech)
          UNLOCKED[team] = UNLOCKED[team] or {}
          UNLOCKED[team][tech] = true
        end
        function SetEquipment(team, resource, amount)
          EQUIPMENT_STOCK[team] = EQUIPMENT_STOCK[team] or {}
          EQUIPMENT_STOCK[team][resource] = amount
        end
        function SetPop(team, current, cap)
          POP[team] = current
          CAP[team] = cap
        end
        function CanRecruit(team, name)
          return GG.MedievalRecruitment.CanRecruit(team, name) and true or false
        end
        function FireAllowUnitCreation(defID, team)
          return gadget:AllowUnitCreation(defID, nil, team, 0, 0, 0, 0) and true or false
        end
        function StripTechAPI()
          GG.MedievalLogistics.IsTechUnlocked = nil
          GG.MedievalLogistics.IsResearched = nil
          GG.MedievalLogistics.TechUnlockPrereq = nil
        end

        assert(load(GADGET_SRC, "@gadget_medieval_recruitment.lua", "t", _G))()
        """)

    def _g(self, name):
        return self.lua.globals()[name]

    def _unlock(self, team, tech):
        self._g("Unlock")(team, tech)

    def _equip(self, team, resource, amount):
        self._g("SetEquipment")(team, resource, amount)

    def _can_recruit(self, team, name):
        return self._g("CanRecruit")(team, name)

    # -- locked -> blocked ----------------------------------------------------

    def test_knight_blocked_while_chivalry_locked(self):
        # Sword stock present, so only the tech clause can refuse the unit.
        self._equip(0, "sword", 3)
        self.assertFalse(self._can_recruit(0, "medieval_knight"))

    def test_men_at_arms_blocked_while_veteran_infantry_locked(self):
        self._equip(0, "sword", 3)
        self.assertFalse(self._can_recruit(0, "medieval_men_at_arms"))

    def test_crossbow_blocked_while_crossbow_tech_locked(self):
        self._equip(0, "bow", 3)
        self.assertFalse(self._can_recruit(0, "medieval_crossbow"))

    # -- unlocked -> permitted (with stock) -----------------------------------

    def test_knight_allowed_once_chivalry_researched(self):
        self._equip(0, "sword", 1)
        self.assertFalse(self._can_recruit(0, "medieval_knight"))
        self._unlock(0, "chivalry")
        self.assertTrue(self._can_recruit(0, "medieval_knight"))

    def test_men_at_arms_allowed_once_veteran_infantry_researched(self):
        self._equip(0, "sword", 1)
        self._unlock(0, "veteran_infantry")
        self.assertTrue(self._can_recruit(0, "medieval_men_at_arms"))

    def test_crossbow_allowed_once_crossbow_tech_researched(self):
        self._equip(0, "bow", 1)
        self._unlock(0, "crossbow_tech")
        self.assertTrue(self._can_recruit(0, "medieval_crossbow"))

    # -- equipment clause still applies after unlock --------------------------

    def test_unlocked_tech_without_equipment_stays_blocked(self):
        self._unlock(0, "chivalry")
        self.assertFalse(self._can_recruit(0, "medieval_knight"))
        self._equip(0, "sword", 1)
        self.assertTrue(self._can_recruit(0, "medieval_knight"))

    def test_wrong_equipment_kind_does_not_satisfy_the_gate(self):
        self._unlock(0, "veteran_infantry")
        self._equip(0, "bow", 5)
        self.assertFalse(self._can_recruit(0, "medieval_men_at_arms"))

    def test_wrong_tech_does_not_unlock_a_tier(self):
        self._equip(0, "sword", 5)
        self._equip(0, "bow", 5)
        self._unlock(0, "crossbow_tech")
        self.assertTrue(self._can_recruit(0, "medieval_crossbow"))
        self.assertFalse(self._can_recruit(0, "medieval_men_at_arms"))
        self.assertFalse(self._can_recruit(0, "medieval_knight"))

    def test_gate_is_per_team(self):
        self._equip(0, "sword", 5)
        self._equip(1, "sword", 5)
        self._unlock(1, "chivalry")
        self.assertTrue(self._can_recruit(1, "medieval_knight"))
        self.assertFalse(self._can_recruit(0, "medieval_knight"))

    # -- ungated units --------------------------------------------------------

    def test_base_tier_units_stay_ungated(self):
        self.assertTrue(self._can_recruit(0, "medieval_infantry"))

    def test_unknown_unit_is_refused(self):
        self.assertFalse(self._can_recruit(0, "medieval_not_a_unit"))

    # -- AllowUnitCreation mirrors the gate -----------------------------------

    def test_allow_unit_creation_blocks_locked_tier(self):
        self._equip(0, "sword", 2)
        self.assertFalse(self._g("FireAllowUnitCreation")(KNIGHT, 0))
        self._unlock(0, "chivalry")
        self.assertTrue(self._g("FireAllowUnitCreation")(KNIGHT, 0))

    def test_allow_unit_creation_permits_the_ungated_base_tier(self):
        self.assertTrue(self._g("FireAllowUnitCreation")(INFANTRY, 0))

    def test_missing_tech_registry_fails_closed(self):
        # No IsTechUnlocked/IsResearched/TechUnlockPrereq published: the gate must
        # refuse the tier even though the equipment clause is satisfied.
        self._equip(0, "sword", 5)
        self._unlock(0, "chivalry")
        self.assertTrue(self._can_recruit(0, "medieval_knight"))
        self._g("StripTechAPI")()
        self.assertFalse(self._can_recruit(0, "medieval_knight"))
        self.assertFalse(self._g("FireAllowUnitCreation")(KNIGHT, 0))

    def test_pop_cap_does_not_gate_the_two_slot_knight(self):
        # The knight costs 2 pop, so the flat 1-pop gate in the recruitment gadget
        # does not apply to it; the tech + equipment clauses decide alone.
        self._g("SetPop")(0, 99, 100)
        self._equip(0, "sword", 1)
        self.assertFalse(self._can_recruit(0, "medieval_knight"))
        self._unlock(0, "chivalry")
        self.assertTrue(self._can_recruit(0, "medieval_knight"))


if __name__ == "__main__":
    unittest.main()
