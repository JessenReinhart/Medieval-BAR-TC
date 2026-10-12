function gadget:GetInfo()
  return {
    name = "Phase 4 Slice 6 Skirmish AI Probe",
    desc = "Headless match probe verifying skirmish AI behaviors: harvest, road, house, recruit, attack",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 10,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}
local enabled = (mo.skirmishai == "1") or (mo.skirmishai == 1) or (mo.skirmishai == true)
if not enabled then return end

local spawned = false
local aiTeam = 1
local enemyTeam = 0
local probeDone = false
local verdicts = {}

local function spawnFeature(name, x, z)
  local def = FeatureDefNames and FeatureDefNames[name]
  if not def then return nil end
  local y = Spring.GetGroundHeight and Spring.GetGroundHeight(x, z) or 0
  return Spring.CreateFeature(def.id, x, y, z, 0)
end

function gadget:GameFrame(frame)
  if not spawned and frame >= 20 then
    spawned = true
    Spring.Echo(string.format("PHASE4 SKIRMISH probe setup starting at frame %d", frame))

    local tcDef = UnitDefNames and UnitDefNames["medieval_town_center"]
    local vilDef = UnitDefNames and UnitDefNames["medieval_villager"]
    local barDef = UnitDefNames and UnitDefNames["medieval_barracks"]
    local infDef = UnitDefNames and UnitDefNames["medieval_infantry"]

    -- 1. AI base: Team 1 at (2600, 3600)
    local cx, cz = 2600, 3600
    local cy = Spring.GetGroundHeight(cx, cz)
    if tcDef then
      Spring.CreateUnit(tcDef.id, cx, cy, cz, "south", aiTeam)
    end
    if barDef then
      local bx, bz = cx + 140, cz - 60
      Spring.CreateUnit(barDef.id, bx, Spring.GetGroundHeight(bx, bz), bz, "south", aiTeam)
    end
    if vilDef then
      for i = 1, 5 do
        local vx, vz = cx + (i - 3) * 32, cz + 64
        Spring.CreateUnit(vilDef.id, vx, Spring.GetGroundHeight(vx, vz), vz, "south", aiTeam)
      end
    end
    -- Seed one starting infantry so armyCount reaches threshold (2) when AI trains one unit
    if infDef then
      local ix, iz = cx + 64, cz + 64
      Spring.CreateUnit(infDef.id, ix, Spring.GetGroundHeight(ix, iz), iz, "south", aiTeam)
    end

    -- Harvest node features near AI base
    spawnFeature("medieval_tree", cx + 80, cz + 180)
    spawnFeature("medieval_tree", cx + 110, cz + 190)
    spawnFeature("medieval_stone", cx - 90, cz + 180)
    spawnFeature("medieval_iron", cx, cz + 220)

    -- Deposit starting economy reserves for AI team
    local econ = GG and GG.MedievalEconomy
    if econ and type(econ.Deposit) == "function" then
      econ.Deposit(aiTeam, "food", 200)
      econ.Deposit(aiTeam, "wood", 300)
      econ.Deposit(aiTeam, "stone", 150)
      econ.Deposit(aiTeam, "iron", 50)
    end

    -- 2. Enemy dummy target base: Team 0 at (3600, 4800)
    local ex, ez = 3600, 4800
    local ey = Spring.GetGroundHeight(ex, ez)
    if tcDef then
      Spring.CreateUnit(tcDef.id, ex, ey, ez, "south", enemyTeam)
    end

    -- Ensure AI is enabled on team 1 and disabled on team 0
    if GG and GG.MedievalSkirmishAI then
      GG.MedievalSkirmishAI.EnableTeam(aiTeam)
      GG.MedievalSkirmishAI.DisableTeam(enemyTeam)
    end

    Spring.Echo(string.format("PHASE4 SKIRMISH probe setup completed at frame %d", frame))
  end

  if not spawned or probeDone then return end

  local aiStats = GG and GG.MedievalSkirmishAI and GG.MedievalSkirmishAI.GetStats(aiTeam) or {}

  -- Harvest verdict at f=60
  if frame >= 60 and not verdicts.harvest then
    verdicts.harvest = true
    local gathers = aiStats.gathersAssigned or 0
    local ok = gathers >= 1
    Spring.Echo(string.format("PHASE4 SKIRMISH harvest-verdict %s f=%d team=%d gathers=%d", ok and "PASS" or "FAIL", frame, aiTeam, gathers))
  end

  -- Road verdict at f=90
  if frame >= 90 and not verdicts.road then
    verdicts.road = true
    local roads = aiStats.roadsBuilt or 0
    local count = GG and GG.MedievalLogistics and GG.MedievalLogistics.RoadCount and GG.MedievalLogistics.RoadCount(aiTeam) or 0
    local total = math.max(roads, count)
    local ok = total >= 1
    Spring.Echo(string.format("PHASE4 SKIRMISH road-verdict %s f=%d team=%d roads=%d", ok and "PASS" or "FAIL", frame, aiTeam, total))
  end

  -- House verdict at f=120
  if frame >= 120 and not verdicts.house then
    verdicts.house = true
    local houses = aiStats.housesBuilt or 0
    local ok = houses >= 1
    Spring.Echo(string.format("PHASE4 SKIRMISH house-verdict %s f=%d team=%d houses=%d", ok and "PASS" or "FAIL", frame, aiTeam, houses))
  end

  -- Recruit verdict at f=150
  if frame >= 150 and not verdicts.recruit then
    verdicts.recruit = true
    local recruited = aiStats.unitsRecruited or 0
    local ok = recruited >= 1
    Spring.Echo(string.format("PHASE4 SKIRMISH recruit-verdict %s f=%d team=%d recruited=%d", ok and "PASS" or "FAIL", frame, aiTeam, recruited))
  end

  -- Attack verdict at f=180
  if frame >= 180 and not verdicts.attack then
    verdicts.attack = true
    local attacks = aiStats.attacksOrdered or 0
    local ok = attacks >= 1
    Spring.Echo(string.format("PHASE4 SKIRMISH attack-verdict %s f=%d team=%d attacks=%d", ok and "PASS" or "FAIL", frame, aiTeam, attacks))
    probeDone = true
    Spring.Echo(string.format("PHASE4 SKIRMISH probe all stages evaluated at f=%d", frame))
  end
end
