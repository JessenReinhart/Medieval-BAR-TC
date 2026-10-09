function gadget:GetInfo()
  return {
    name = "Phase 2 Settlement and Economy Test Forces",
    desc = "Spawns Town Centers, resource nodes, and villagers under phase2test modoption",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 50,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local options = Spring.GetModOptions() or {}
local enabled = options.phase2test == true or options.phase2test == 1 or options.phase2test == "1"
if not enabled then return end

local spawned = false
local assignmentPending = {}
local trackedVillager = nil
-- Slice 4 road-build command probe state: open spot far from existing probe
-- roads (frame-120 road at 2608,3584; frame-160 chain at 2608..2728,3884 and
-- isolated road at 2908,4184).
local ROAD_PROBE_X, ROAD_PROBE_Z = 2600, 3700
local roadProbe = nil
local buildingProbe = nil
-- Slice 6 road movement-speed probe state.
local speedProbe = nil
-- Slice 7 supply + road-aware pathing probe state.
local supplyProbe = nil
local gatherProbe = nil
-- Slice 8 (Phase 4 Slice 1) siege catapult probe state.
local siegeProbe = nil
-- Phase 4 Slice 2 damage-matrix probe state (siege 3x + melee 0.25x vs wall).
local dmatrixMeleeProbe = nil
local dmatrixSiegeDone = false
local dmatrixMeleeSpawned = false
local dmatrixMeleeVerdictDone = false
-- Phase 4 Slice 3 production-chain probe state (blacksmith/fletcher crafting and
-- the equipment-gated recruit check).
local craftProbe = nil
-- Phase 4 Slice 4 military-upgrade probe state (chivalry tech gate -> knight
-- recruit gate -> +20% knight damage multiplier).
local upgradeProbe = nil
-- Phase 4 Slice 5 hauler probe state (cart road-speed pair -> live haul route ->
-- sink-hub delivery ledger).
local haulProbe = nil

-- Slice 5 lane geometry. x 3500..3820 / z 4350..4950 is flat (heightmap
-- 89.8..90.4) and the map feature map is empty there, so no earlier slice
-- shares the lane. The lumber camp sits 40 elmos from a road node because
-- AllowUnitCreation only admits a supply endpoint within BUILD_LINK_RADIUS (64)
-- of a same-team road.
local HAUL_ROAD_X = 3620
local HAUL_ROAD_Z0, HAUL_ROAD_Z1, HAUL_ROAD_STEP = 4700, 4900, 40
local HAUL_SOURCE_X, HAUL_SOURCE_Z = 3660, 4780 -- medieval_lumber_camp (wood source)
local HAUL_SINK_X, HAUL_SINK_Z = 3660, 4700     -- medieval_blacksmith (wood sink)
local HAUL_CART_X, HAUL_CART_Z = 3700, 4560     -- 80 elmos off the lane
local HAUL_OFFROAD_X, HAUL_OFFROAD_Z = 3700, 4560
local HAUL_OFFROAD_END_X, HAUL_OFFROAD_END_Z = 3700, 4260
local HAUL_ONROAD_X, HAUL_ONROAD_Z = 3620, 4900
local HAUL_ONROAD_END_X, HAUL_ONROAD_END_Z = 3620, 4700
local HAUL_HUB_OFFSET = 48 -- elmos; inside the hauling gadget's 64-elmo arrival radius
local HAUL_WOOD_TARGET = 26 -- bottom of the policy's deficit band [HAUL_STEP=25, DEFICIT_THRESHOLD=80)
local HAUL_CUSHION_WOOD = 300 -- above DEFICIT_THRESHOLD: holds the policy idle during Phase A
local HAUL_LEG_FRAMES = 30 -- both speed legs are sampled this long after their move order

local function roadProbeSnapshot(teamID)
  local api = GG and GG.MedievalLogistics
  if not api or type(api.RoadCount) ~= "function"
      or type(Spring.GetGameRulesParam) ~= "function"
      or type(Spring.GetAllFeatures) ~= "function"
      or type(Spring.GetFeatureDefID) ~= "function"
      or type(Spring.GetFeaturePosition) ~= "function"
      or type(Spring.GetFeatureTeam) ~= "function" then
    return nil, "missing count/balance/feature observation API"
  end
  local roadDef = FeatureDefNames and FeatureDefNames.medieval_road
  if not roadDef then return nil, "missing medieval_road FeatureDef" end
  local wood = Spring.GetGameRulesParam(string.format("team_%d_wood", teamID))
  local stone = Spring.GetGameRulesParam(string.format("team_%d_stone", teamID))
  if type(wood) ~= "number" or type(stone) ~= "number" then
    return nil, "missing numeric wood/stone balances"
  end
  local snapshot = { count = api.RoadCount(teamID), wood = wood, stone = stone, features = {}, probeRoads = 0 }
  if type(snapshot.count) ~= "number" then return nil, "missing numeric road count" end
  for _, fid in ipairs(Spring.GetAllFeatures() or {}) do
    if Spring.GetFeatureDefID(fid) == roadDef.id then
      local x, _, z = Spring.GetFeaturePosition(fid)
      if x and z and math.abs(x - ROAD_PROBE_X) < 1 and math.abs(z - ROAD_PROBE_Z) < 1 then
        snapshot.features[fid] = Spring.GetFeatureTeam(fid)
        snapshot.probeRoads = snapshot.probeRoads + 1
      end
    end
  end
  return snapshot
end

-- Slice 6 helper: format the enforced speed state of one tracked mover.
-- Returns a human-readable fragment plus the raw state table (nil when the
-- unit is untracked or the API is unavailable).
local function speedStateText(unitID)
  local api = GG and GG.MedievalLogistics
  if not (api and type(api.GetSpeedState) == "function") then
    return "SKIPPED missing GetSpeedState API", nil
  end
  local state = api.GetSpeedState(unitID)
  if type(state) ~= "table" then
    return "UNTRACKED", nil
  end
  return string.format("onRoad=%s base=%.2f applied=%.2f source=%s",
    tostring(state.onRoad), state.base or -1, state.applied or -1, tostring(state.source)), state
end

-- Slice 6 helper: horizontal velocity magnitude in elmos/sec, or nil when the
-- engine call is unavailable.
local function speedUnitVelocity(unitID)
  if type(Spring.GetUnitVelocity) ~= "function" then return nil end
  local ok, vx, _, vz = pcall(Spring.GetUnitVelocity, unitID)
  if not ok or type(vx) ~= "number" or type(vz) ~= "number" then return nil end
  return math.sqrt(vx * vx + vz * vz)
end

local function speedNear(value, expected)
  return type(value) == "number" and math.abs(value - expected) < 0.01
end

local function opposingTeams()
  local list = Spring.GetTeamList() or {}
  table.sort(list)
  local gaia = Spring.GetGaiaTeamID()
  for i, a in ipairs(list) do
    local _, _, deadA = Spring.GetTeamInfo(a, false)
    if a ~= gaia and not deadA then
      for j = i + 1, #list do
        local b = list[j]
        local _, _, deadB = Spring.GetTeamInfo(b, false)
        if b ~= gaia and not deadB and not Spring.AreTeamsAllied(a, b) then
          return a, b
        end
      end
    end
  end
end

local function spawnSettlement(teamID, cx, cz)
  local tcDef = UnitDefNames["medieval_town_center"]
  local vilDef = UnitDefNames["medieval_villager"]
  local houseDef = UnitDefNames["medieval_house"]
  local granaryDef = UnitDefNames["medieval_granary"]
  local campDef = UnitDefNames["medieval_lumber_camp"]

  if not (tcDef and vilDef and houseDef and granaryDef and campDef) then
    Spring.Echo("PHASE2 PROBE: missing required unit defs; aborting settlement spawn")
    return
  end

  local tcY = Spring.GetGroundHeight(cx, cz)
  local tcID = Spring.CreateUnit(tcDef.id, cx, tcY, cz, "south", teamID)
  Spring.Echo(string.format("PHASE2 PROBE: spawned Town Center id=%s for team=%d at (%d, %d)", tostring(tcID), teamID, cx, cz))

  -- Houses
  for i = 1, 2 do
    local hx = cx + (i == 1 and -120 or 120)
    local hz = cz - 80
    local hy = Spring.GetGroundHeight(hx, hz)
    local hid = Spring.CreateUnit(houseDef.id, hx, hy, hz, "south", teamID)
    Spring.Echo(string.format("PHASE2 PROBE: spawned House #%d id=%s team=%d", i, tostring(hid), teamID))
  end

  -- Granary + Lumber Camp
  local gy = Spring.GetGroundHeight(cx - 140, cz + 60)
  local gid = Spring.CreateUnit(granaryDef.id, cx - 140, gy, cz + 60, "south", teamID)
  local cy = Spring.GetGroundHeight(cx + 140, cz + 60)
  local cid = Spring.CreateUnit(campDef.id, cx + 140, cy, cz + 60, "south", teamID)
  Spring.Echo(string.format("PHASE2 PROBE: spawned Granary=%s Camp=%s team=%d", tostring(gid), tostring(cid), teamID))

  -- Villagers (5 units)
  local villagers = {}
  for i = 1, 5 do
    local vx = cx + (i - 3) * 32
    local vz = cz + 64
    local vy = Spring.GetGroundHeight(vx, vz)
    local vid = Spring.CreateUnit(vilDef.id, vx, vy, vz, "south", teamID)
    if vid then
      villagers[#villagers + 1] = vid
      Spring.Echo(string.format("PHASE2 PROBE: spawned Villager #%d id=%d team=%d", i, vid, teamID))
    end
  end

  -- Resource node features nearby
  local nodeFeatures = {
    { def = "medieval_tree",  dx = 80,  dz = 180 },
    { def = "medieval_tree",  dx = 110, dz = 190 },
    { def = "medieval_stone", dx = -90, dz = 180 },
    { def = "medieval_iron",  dx = 0,   dz = 220 },
    { def = "medieval_deer",  dx = -150, dz = 160 },
  }
  for _, nf in ipairs(nodeFeatures) do
    local fdef = FeatureDefNames and FeatureDefNames[nf.def]
    if fdef then
      local fx = cx + nf.dx
      local fz = cz + nf.dz
      local fy = Spring.GetGroundHeight(fx, fz)
      local fid = Spring.CreateFeature(fdef.id, fx, fy, fz, 0)
      Spring.Echo(string.format("PHASE2 PROBE: spawned Feature %s id=%s at (%d, %d)", nf.def, tostring(fid), fx, fz))
    else
      Spring.Echo(string.format("PHASE2 PROBE: FeatureDef %s not found", nf.def))
    end
  end

  -- Assign all villagers to gather on frame 32
  if #villagers > 0 then
    for _, vid in ipairs(villagers) do
      assignmentPending[#assignmentPending + 1] = vid
    end
  end
end

-- Slice 8 helper: defensive health read so a missing/unsupported engine call can
-- never nil-dereference the probe (returns nil instead of raising).
local function siegeTargetHealth(unitID)
  if type(Spring.GetUnitHealth) ~= "function" then return nil end
  local ok, health = pcall(Spring.GetUnitHealth, unitID)
  if not ok or type(health) ~= "number" then return nil end
  return health
end

-- Read back a rules param published by scripts/medieval_catapult.lua. These are the
-- authoritative aim/fire signals: only the LUS call-ins can set them, so a non-nil
-- value proves the engine dispatched into the catapult's unit script.
local function siegeLusParam(unitID, name)
  if type(Spring.GetUnitRulesParam) ~= "function" then return nil end
  local ok, value = pcall(Spring.GetUnitRulesParam, unitID, name)
  if not ok then return nil end
  return value
end

-- Phase 4 Slice 3 helper: read the equipment stock published by
-- gadget_production_chains.lua as GG.MedievalLogistics.equipmentStock[team][kind].
-- Returns nil when nothing has been published for that team, which the probe
-- reports distinctly from a real 0 so a missing producer cannot look like an
-- empty stock.
local function equipmentStockOf(teamID, kind)
  local api = GG and GG.MedievalLogistics
  local stock = api and api.equipmentStock
  if type(stock) ~= "table" then return nil end
  local team = stock[teamID]
  if type(team) ~= "table" then return nil end
  local amount = tonumber(team[kind])
  if not amount or amount ~= amount then return nil end
  return amount
end

-- Phase 4 Slice 3 helper: read the real recruitment gate. CanRecruit covers pop
-- cap, equipment stock and resource cost, so the probe observes the gate the
-- game actually enforces; the logistics equipment-only rule is the fallback when
-- the recruitment gadget is not loaded. nil means the gate is not observable.
local function recruitGateAllows(teamID, defName)
  local recruitment = GG and GG.MedievalRecruitment
  if recruitment and type(recruitment.CanRecruit) == "function" then
    local ok, allowed = pcall(recruitment.CanRecruit, teamID, defName)
    if ok then return allowed and true or false end
  end
  local api = GG and GG.MedievalLogistics
  if api and type(api.UnitCanRecruit) == "function" then
    local ok, allowed = pcall(api.UnitCanRecruit, teamID, defName)
    if ok then return allowed and true or false end
  end
  return nil
end

-- ---------------------------------------------------------------------------
-- Phase 4 Slice 5 helpers: transport & hauler probe support.
-- ---------------------------------------------------------------------------

-- Force one resource of a team pool to an exact value. The haul policy reads the
-- shared pool on every scan and only routes while a resource sits inside the
-- deficit band [HAUL_STEP, DEFICIT_THRESHOLD), so live gather/production would
-- otherwise make the band a moving target. Returns the settled value, or nil
-- when the economy API is unavailable.
local function pinStock(teamID, resource, target)
  local econ = GG and GG.MedievalEconomy
  if not (econ and type(econ.GetResource) == "function") then return nil end
  local cur = econ.GetResource(teamID, resource)
  if type(cur) ~= "number" then return nil end
  local delta = target - math.floor(cur)
  if delta > 0 and type(econ.Deposit) == "function" then
    econ.Deposit(teamID, resource, delta)
  elseif delta < 0 and type(econ.Withdraw) == "function" then
    econ.Withdraw(teamID, resource, -delta)
  end
  return econ.GetResource(teamID, resource)
end

-- Resolve a hub unit id to its UnitDef name so the route verdict can assert the
-- source/sink ROLES the policy actually chose instead of hard-coding engine ids.
local function unitDefNameOf(unitID)
  if type(unitID) ~= "number" or type(Spring.GetUnitDefID) ~= "function" then return nil end
  local defID = Spring.GetUnitDefID(unitID)
  local def = defID and UnitDefs and UnitDefs[defID]
  return def and def.name
end

-- Per-hub storage ledger written by the hauling gadget when a haul completes.
-- The team pool is shared (a same-team hub->hub haul conserves it), so this
-- ledger is the only per-hub "stock" a haul moves; the hauling gadget exposes it
-- read-only through GG.MedievalLogistics.HaulHubStock.
local function haulHubStock(teamID, hubID, resource)
  local api = GG and GG.MedievalLogistics
  if not (api and type(api.HaulHubStock) == "function") then return nil end
  local ok, value = pcall(api.HaulHubStock, teamID, hubID, resource)
  if not ok then return nil end
  return value
end

-- Reposition a probe unit without pathing so the haul state machine can be
-- driven inside the frame budget. Same technique the Slice 6 road-speed restore
-- step already uses on a mobile unit; the gadget's own arrival checks still gate
-- every phase change, so a reposition is not itself a delivery.
local function placeUnit(unitID, x, z)
  if type(Spring.SetUnitPosition) ~= "function" then return false end
  local ok = pcall(Spring.SetUnitPosition, unitID, x, Spring.GetGroundHeight(x, z), z)
  return ok
end

-- Snapshot one mover's enforced speed state into plain scalars. The table
-- GetSpeedState returns is the LIVE synced entry, which the logistics gadget
-- rewrites in place on every scan, so holding the table would make the off-road
-- sample silently read the on-road values at verdict time.
local function snapshotSpeedState(unitID)
  local text, state = speedStateText(unitID)
  if not state then return text, nil end
  return text, {
    onRoad = state.onRoad,
    base = state.base,
    applied = state.applied,
    source = state.source,
  }
end

-- Phase 4 Slice 2 raw weapon base damage, documented in gamedata/weapondefs.lua
-- (catapult 500, sword 150). These are the "baseline" values the damage matrix
-- multiplies: siege x3.0 vs fortification, melee x0.25 vs fortification.
local CATAPULT_BASE_DAMAGE = 500
local SWORD_BASE_DAMAGE = 150

function gadget:GameFrame(frame)
  if frame == 32 and #assignmentPending > 0 and GG and GG.MedievalGather then
    trackedVillager = assignmentPending[1]
    for _, unitID in ipairs(assignmentPending) do
      GG.MedievalGather.AssignGather(unitID, nil)
      Spring.Echo(string.format("PHASE2 PROBE: assigned villager %d to initial gather cycle", unitID))
    end
    assignmentPending = {}
  end
  if not spawned and frame >= 30 then
    spawned = true
    local a, b = opposingTeams()
    if a and b then
      local mx, mz = Game.mapSizeX, Game.mapSizeZ
      spawnSettlement(a, mx * 0.35, mz * 0.5)
      spawnSettlement(b, mx * 0.65, mz * 0.5)
      Spring.Echo(string.format("PHASE2 PROBE: Settlements spawned on frame %d for teams %d and %d", frame, a, b))
    else
      Spring.Echo("PHASE2 PROBE: Missing two opposing teams; settlement spawn skipped")
    end
  end

  -- Diagnostic periodic log
  if frame % 30 == 0 and spawned then
    local a, b = opposingTeams()
    if a and GG and GG.MedievalGather and trackedVillager then
      local j = GG.MedievalGather.GetJob(trackedVillager)
      if j then
        Spring.Echo(string.format("PHASE2 GATHER JOB f=%d vid=%d state=%s res=%s carried=%.1f node=%s",
          frame, trackedVillager, tostring(j.state), tostring(j.resource), j.carried or 0, tostring(j.nodeID)))
      end
    end
  end
  if frame == 60 and spawned and GG and GG.MedievalEconomy then
    local a, b = opposingTeams()
    if a then
      local food0 = Spring.GetGameRulesParam(string.format("team_%d_food", a)) or "?"
      local wood0 = Spring.GetGameRulesParam(string.format("team_%d_wood", a)) or "?"
      local stone0 = Spring.GetGameRulesParam(string.format("team_%d_stone", a)) or "?"
      Spring.Echo(string.format("PHASE2 PROBE SLICE2 START f=%d team=%d food=%s wood=%s stone=%s", frame, a, tostring(food0), tostring(wood0), tostring(stone0)))
      local okPlace = GG.MedievalEconomy.CanAfford(a, { wood = 150, stone = 100 })
      Spring.Echo(string.format("PHASE2 PROBE SLICE2 barracks-affordable=%s team=%d", tostring(okPlace), a))
      if okPlace then
        local okTx = GG.MedievalEconomy.Transact(a, { wood = 150, stone = 100 })
        Spring.Echo(string.format("PHASE2 PROBE SLICE2 barracks-placed team=%d wood=150 stone=100 tx=%s", a, tostring(okTx)))
        -- Spawn the barracks live in engine so UnitFinished call-in triggers
        local barDef = UnitDefNames["medieval_barracks"]
        if barDef then
          local bx, bz = 2508 + 120, 3584
          local by = Spring.GetGroundHeight(bx, bz)
          local barID = Spring.CreateUnit(barDef.id, bx, by, bz, "south", a)
          Spring.Echo(string.format("PHASE2 PROBE SLICE2 spawned barracks id=%s team=%d", tostring(barID), a))
        end
      end
      -- Deposit 50 food so the test team can afford to recruit infantry.
      GG.MedievalEconomy.Deposit(a, "food", 50)
      -- Spawn infantry live; gadget_medieval_recruitment charges the discrete
      -- cost at UnitFinished (the real production path). Do NOT pre-transact
      -- here or the spawn double-charges and gets destroyed.
      local infDef = UnitDefNames["medieval_infantry"]
      if infDef then
        local ix, iz = 2508 + 150, 3584
        local iy = Spring.GetGroundHeight(ix, iz)
        local infID = Spring.CreateUnit(infDef.id, ix, iy, iz, "south", a)
        Spring.Echo(string.format("PHASE2 PROBE SLICE2 spawned infantry id=%s team=%d", tostring(infID), a))
      end
      if GG.MedievalRecruitment then
        local can = GG.MedievalRecruitment.CanRecruit(a, "medieval_infantry")
        Spring.Echo(string.format("PHASE2 PROBE SLICE2 can-recruit-infantry=%s team=%d", tostring(can), a))
      end
    end
  end
  if frame == 120 and spawned and GG and GG.MedievalEconomy and GG.MedievalLogistics then
    local a, b = opposingTeams()
    if a then
      -- Deposit construction + research resources for the Phase 3 verification steps.
      GG.MedievalEconomy.Deposit(a, "wood", 300)
      GG.MedievalEconomy.Deposit(a, "stone", 300)
      GG.MedievalEconomy.Deposit(a, "iron", 300)
      Spring.Echo(string.format("PHASE3 PROBE deposit team=%d wood=300 stone=300 iron=300", a))

      -- Road creation.
      local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
      if roadDef then
        local rx, rz = 2508 + 100, 3584
        local ry = Spring.GetGroundHeight(rx, rz)
        local fid = Spring.CreateFeature(roadDef.id, rx, ry, rz, 0, a)
        Spring.Echo(string.format("PHASE3 PROBE road-create ftr=%s team=%d at=(%d, %d)", tostring(fid), a, rx, rz))
        Spring.Echo(string.format("PHASE3 PROBE road-count team=%d count=%d", a, GG.MedievalLogistics.RoadCount(a)))

        -- is-on-road check: spawn a probe villager on the road and query the speed multiplier API.
        local vilDef = UnitDefNames["medieval_villager"]
        if vilDef then
          local pid = Spring.CreateUnit(vilDef.id, rx, ry, rz, "south", a)
          if pid then
            local onRoad = GG.MedievalLogistics.IsOnRoad(a, pid)
            local mult = GG.MedievalLogistics.GetSpeedMultiplier(a, pid)
            Spring.Echo(string.format("PHASE3 PROBE is-on-road team=%d unit=%d on_road=%s speed_mult=%.2f", a, pid, tostring(onRoad), mult))
          end
        end
      else
        Spring.Echo("PHASE3 PROBE road-create missing medieval_road FeatureDef")
      end

      -- Tech research: iron_swords (no prereq; cost wood 50 + iron 100).
      local okSwords, reasonSwords = GG.MedievalLogistics.Research(a, "iron_swords")
      Spring.Echo(string.format("PHASE3 PROBE research iron_swords team=%d ok=%s reason=%s", a, tostring(okSwords), tostring(reasonSwords)))
      Spring.Echo(string.format("PHASE3 PROBE param team_%d_tech_iron_swords = %s", a, tostring(Spring.GetGameRulesParam(string.format("team_%d_tech_iron_swords", a)))))
      Spring.Echo(string.format("PHASE3 PROBE is-researched iron_swords team=%d = %s", a, tostring(GG.MedievalLogistics.IsResearched(a, "iron_swords"))))

      -- Tech prereq unlock: plate_armor requires iron_swords (cost iron 150).
      local okArmor, reasonArmor = GG.MedievalLogistics.Research(a, "plate_armor")
      Spring.Echo(string.format("PHASE3 PROBE research plate_armor team=%d ok=%s reason=%s", a, tostring(okArmor), tostring(reasonArmor)))
      Spring.Echo(string.format("PHASE3 PROBE param team_%d_tech_plate_armor = %s", a, tostring(Spring.GetGameRulesParam(string.format("team_%d_tech_plate_armor", a)))))
      Spring.Echo(string.format("PHASE3 PROBE is-researched plate_armor team=%d = %s", a, tostring(GG.MedievalLogistics.IsResearched(a, "plate_armor"))))
    end
  end
  -- Phase 3 probe slice 2: melee damage scaling and villager fortification build options.
  if frame == 140 and spawned and GG and GG.MedievalEconomy and GG.MedievalLogistics then
    local a, b = opposingTeams()
    if a and b then
      local infDef = UnitDefNames["medieval_infantry"]
      if infDef then
        -- Fund both teams first so the recruitment UnitFinished charge does not
        -- destroy the freshly spawned infantry (min cost: food 30 wood 20 stone 10 iron 5).
        for _, t in ipairs({ a, b }) do
          GG.MedievalEconomy.Deposit(t, "food", 100)
          GG.MedievalEconomy.Deposit(t, "wood", 100)
          GG.MedievalEconomy.Deposit(t, "stone", 100)
          GG.MedievalEconomy.Deposit(t, "iron", 100)
        end

        local ax, az = 2508 + 200, 3584
        local bx, bz = ax + 40, az
        local atkID = Spring.CreateUnit(infDef.id, ax, Spring.GetGroundHeight(ax, az), az, "south", a)
        local defID = Spring.CreateUnit(infDef.id, bx, Spring.GetGroundHeight(bx, bz), bz, "north", b)
        Spring.Echo(string.format("PHASE3 PROBE melee-spawn attacker=%s team=%d defender=%s team=%d", tostring(atkID), a, tostring(defID), b))

        -- Ensure iron_swords is researched for the attacker so the +25% infantry
        -- melee bonus applies in UnitPreDamaged.
        if not GG.MedievalLogistics.IsResearched(a, "iron_swords") then
          GG.MedievalLogistics.Research(a, "iron_swords")
        end
        local mult = GG.MedievalLogistics.DamageMultiplier(a, "medieval_infantry")
        local base = 150 -- sword weapon damage from gamedata/weapondefs.lua
        local scaled = base * mult
        Spring.Echo(string.format("PHASE3 PROBE damage-scaling verified base=%.1f scaled=%.1f", base, scaled))

        -- Exercise UnitPreDamaged: scripted damage plus a real melee attack order.
        if atkID and defID then
          Spring.AddUnitDamage(defID, base, 0, atkID, -1)
          Spring.GiveOrderToUnit(atkID, CMD.ATTACK, { defID }, {})
        end
      else
        Spring.Echo("PHASE3 PROBE melee-spawn missing medieval_infantry def")
      end

      -- Villager build options: confirm wall + tower fortifications are buildable.
      local hasWall, hasTower = false, false
      local vilDef = UnitDefNames["medieval_villager"]
      if vilDef then
        for _, opt in pairs(vilDef.buildOptions or {}) do
          local nm = nil
          if type(opt) == "number" then
            nm = UnitDefs and UnitDefs[opt] and UnitDefs[opt].name
          elseif type(opt) == "string" then
            nm = opt
          end
          if nm == "medieval_wall" then hasWall = true end
          if nm == "medieval_tower" then hasTower = true end
        end
      end
      Spring.Echo(string.format("PHASE3 PROBE villager-buildopts wall=%s tower=%s", hasWall and "t" or "f", hasTower and "t" or "f"))
    end
  end
  -- Phase 3 probe slice 4: road-build custom command (371922) end-to-end.
  -- State for the deferred-execution probe; AllowCommand defers the actual
  -- road placement to the next GameFrame, so verification runs at frame+1.
  if frame == 200 and spawned and GG and GG.MedievalEconomy then
    local api = GG.MedievalLogistics
    local a = 0
    -- Fund the team (road cost: wood 5, stone 2) using the deposit pattern.
    GG.MedievalEconomy.Deposit(a, "food", 100)
    GG.MedievalEconomy.Deposit(a, "wood", 100)
    GG.MedievalEconomy.Deposit(a, "stone", 100)
    GG.MedievalEconomy.Deposit(a, "iron", 100)
    local canAfford = api and api.CanPlaceRoad and api.CanPlaceRoad(a, ROAD_PROBE_X, ROAD_PROBE_Z)
    Spring.Echo(string.format("PHASE3 PROBE road-cmd precheck team=%d canPlace=%s", a, tostring(canAfford)))

    local baseline, baselineErr = roadProbeSnapshot(a)
    if baseline then
      Spring.Echo(string.format("PHASE3 PROBE road-cmd baseline team=%d RoadCount=%d wood=%d stone=%d probeRoads=%d",
        a, baseline.count, baseline.wood, baseline.stone, baseline.probeRoads))
    else
      Spring.Echo(string.format("PHASE3 PROBE road-cmd baseline UNAVAILABLE team=%d reason=%s", a, tostring(baselineErr)))
    end

    -- Reuse the tracked villager, else spawn a fresh one on open ground.
    local vilDef = UnitDefNames["medieval_villager"]
    local vid = nil
    if vilDef and trackedVillager and Spring.ValidUnitID(trackedVillager)
        and Spring.GetUnitDefID(trackedVillager) == vilDef.id
        and Spring.GetUnitTeam(trackedVillager) == a then
      vid = trackedVillager
    elseif vilDef then
      local vx, vz = 2508 + 300, 3584 - 200
      local vy = Spring.GetGroundHeight(vx, vz)
      vid = Spring.CreateUnit(vilDef.id, vx, vy, vz, "south", a)
      Spring.Echo(string.format("PHASE3 PROBE road-cmd spawned villager id=%s team=%d", tostring(vid), a))
    end
    if vid and api then
      -- Verify command descriptor attached if Spring.GetUnitCmdDescs available
      if type(Spring.GetUnitCmdDescs) == "function" then
        local foundDesc = false
        local descs = Spring.GetUnitCmdDescs(vid) or {}
        for _, desc in pairs(descs) do
          if type(desc) == "table" and desc.id == 371922 then
            foundDesc = true
            break
          end
        end
        Spring.Echo(string.format("PHASE3 PROBE road-cmd cmddesc unit=%d cmd=371922 found=%s", vid, tostring(foundDesc)))
      else
        Spring.Echo("PHASE3 PROBE road-cmd cmddesc Spring.GetUnitCmdDescs unavailable")
      end

      Spring.GiveOrderToUnit(vid, 371922, { ROAD_PROBE_X, ROAD_PROBE_Z }, {})
      Spring.Echo(string.format("PHASE3 PROBE road-cmd order1 sent unit=%d team=%d cmd=371922 at=(%d, %d)",
        vid, a, ROAD_PROBE_X, ROAD_PROBE_Z))
      roadProbe = { team = a, unit = vid, baseline = baseline, stage = "ordered" }
    else
      Spring.Echo(string.format("PHASE3 PROBE road-cmd SKIPPED no villager team=%d", a))
    end
  end
  if roadProbe and roadProbe.stage == "ordered" and frame >= 202 then
    local api = GG and GG.MedievalLogistics
    local a = roadProbe.team
    if not api then
      Spring.Echo("PHASE3 PROBE road-cmd SKIPPED missing MedievalLogistics API")
      roadProbe = nil
    else
      local snap1, snapErr1 = roadProbeSnapshot(a)
      local base = roadProbe.baseline
      if not snap1 or not base then
        Spring.Echo(string.format("PHASE3 PROBE road-cmd post1 observation failed: snap=%s base=%s err=%s",
          tostring(snap1 ~= nil), tostring(base ~= nil), tostring(snapErr1)))
      else
        local countDelta = snap1.count - base.count
        local woodDelta = base.wood - snap1.wood
        local stoneDelta = base.stone - snap1.stone
        local probeRoads = snap1.probeRoads
        local passCount = (countDelta == 1)
        local passCost = (woodDelta == 5 and stoneDelta == 2)
        local passOwner = false
        for fid, fteam in pairs(snap1.features) do
          if fteam == a then
            passOwner = true
            break
          end
        end
        local passOrder1 = passCount and passCost and passOwner and (probeRoads >= 1)
        Spring.Echo(string.format("PHASE3 PROBE road-cmd order1-verdict f=%d team=%d %s (countDelta=%d pass=%s, cost woodDelta=%d stoneDelta=%d pass=%s, ownerTeam=%s pass=%s, probeRoads=%d)",
          frame, a, passOrder1 and "PASS" or "FAIL",
          countDelta, tostring(passCount),
          woodDelta, stoneDelta, tostring(passCost),
          tostring(a), tostring(passOwner),
          probeRoads))
      end

      local count = api.RoadCount and api.RoadCount(a) or -1
      Spring.Echo(string.format("PHASE3 PROBE road-cmd summary team=%d RoadCount=%d", a, count))
      local s = api.RoadNetworkSummary and api.RoadNetworkSummary(a)
      if s then
        Spring.Echo(string.format("PHASE3 PROBE road-cmd roadgraph team=%d nodes=%d edges=%d components=%d isolated=%d largest=%d",
          a, s.nodes, s.edges, s.components, s.isolated, s.largest))
      else
        Spring.Echo(string.format("PHASE3 PROBE road-cmd roadgraph team=%d UNAVAILABLE", a))
      end

      local ok2 = api.CanPlaceRoad and api.CanPlaceRoad(a, ROAD_PROBE_X, ROAD_PROBE_Z)
      Spring.Echo(string.format("PHASE3 PROBE road-cmd retry-precheck team=%d canPlace=%s (expect false)", a, tostring(ok2)))
      if roadProbe.unit and Spring.ValidUnitID(roadProbe.unit) then
        Spring.GiveOrderToUnit(roadProbe.unit, 371922, { ROAD_PROBE_X, ROAD_PROBE_Z }, {})
        Spring.Echo(string.format("PHASE3 PROBE road-cmd order2 sent unit=%d team=%d cmd=371922 at=(%d, %d) (expect refusal)",
          roadProbe.unit, a, ROAD_PROBE_X, ROAD_PROBE_Z))
      end
      roadProbe.post1 = snap1
      roadProbe.stage = "retried"
    end
  end
  if roadProbe and roadProbe.stage == "retried" and frame >= 204 then
    local a = roadProbe.team
    local snap2, snapErr2 = roadProbeSnapshot(a)
    local post1 = roadProbe.post1
    if not snap2 or not post1 then
      Spring.Echo(string.format("PHASE3 PROBE road-cmd post2 observation failed: snap=%s post1=%s err=%s",
        tostring(snap2 ~= nil), tostring(post1 ~= nil), tostring(snapErr2)))
    else
      local countDelta2 = snap2.count - post1.count
      local woodDelta2 = post1.wood - snap2.wood
      local stoneDelta2 = post1.stone - snap2.stone
      local probeRoadsDelta = snap2.probeRoads - post1.probeRoads
      local passNoExtraCount = (countDelta2 == 0)
      local passNoExtraCost = (woodDelta2 == 0 and stoneDelta2 == 0)
      local passDuplicateRejected = passNoExtraCount and passNoExtraCost and (probeRoadsDelta == 0)
      Spring.Echo(string.format("PHASE3 PROBE road-cmd order2-verdict f=%d team=%d %s (extraCount=%d pass=%s, extraWood=%d extraStone=%d pass=%s, extraProbeRoads=%d)",
        frame, a, passDuplicateRejected and "PASS" or "FAIL",
        countDelta2, tostring(passNoExtraCount),
        woodDelta2, stoneDelta2, tostring(passNoExtraCost),
        probeRoadsDelta))
    end
    roadProbe = nil
  end

  -- Phase 3 probe slice 3: road adjacency graph and connectivity validation.
  if frame == 160 and spawned then
    local api = GG and GG.MedievalLogistics
    if not api or type(api.RoadNetworkSummary) ~= "function"
        or type(api.RoadConnected) ~= "function"
        or type(api.PointOnRoadNetwork) ~= "function" then
      Spring.Echo("PHASE3 PROBE roadgraph SKIPPED missing road graph API")
      return
    end
    local a = opposingTeams()
    if a then
      local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
      if roadDef then
        -- Chain of three roads spaced 60 elmos apart (within LINK_RADIUS = 64)
        -- plus one isolated road far away, so the graph has two components.
        local ids = {}
        for i = 1, 3 do
          local rx, rz = 2508 + 100 + (i - 1) * 60, 3584 + 300
          local ry = Spring.GetGroundHeight(rx, rz)
          local fid = Spring.CreateFeature(roadDef.id, rx, ry, rz, 0, a)
          ids[i] = fid
          if fid then
            Spring.Echo(string.format("PHASE3 PROBE roadgraph-create chain#%d ftr=%s team=%d at=(%d, %d)", i, tostring(fid), a, rx, rz))
          else
            Spring.Echo(string.format("PHASE3 PROBE roadgraph-create chain#%d FAILED team=%d at=(%d, %d)", i, a, rx, rz))
          end
        end
        local ix, iz = 2508 + 400, 3584 + 600
        local iy = Spring.GetGroundHeight(ix, iz)
        local isoID = Spring.CreateFeature(roadDef.id, ix, iy, iz, 0, a)
        Spring.Echo(string.format("PHASE3 PROBE roadgraph-create isolated ftr=%s team=%d at=(%d, %d)", tostring(isoID), a, ix, iz))

        local s = GG.MedievalLogistics.RoadNetworkSummary(a)
        if s then
          Spring.Echo(string.format("PHASE3 PROBE roadgraph nodes=%d edges=%d components=%d isolated=%d largest=%d",
            s.nodes, s.edges, s.components, s.isolated, s.largest))
        end
        Spring.Echo(string.format("PHASE3 PROBE roadgraph connected-first-last=%s",
          tostring(GG.MedievalLogistics.RoadConnected(a, ids[1], ids[3]))))
        Spring.Echo(string.format("PHASE3 PROBE roadgraph connected-chain-isolated=%s",
          tostring(GG.MedievalLogistics.RoadConnected(a, ids[1], isoID))))
        Spring.Echo(string.format("PHASE3 PROBE roadgraph point-on-network=%s",
          tostring(GG.MedievalLogistics.PointOnRoadNetwork(a, 2508 + 100 + 60, 3584 + 300))))
        Spring.Echo(string.format("PHASE3 PROBE roadgraph point-off-network=%s",
          tostring(GG.MedievalLogistics.PointOnRoadNetwork(a, 2508 + 900, 3584 + 900))))
      else
        Spring.Echo("PHASE3 PROBE roadgraph missing medieval_road FeatureDef")
      end
    end
  end
  -- Phase 3 probe slice 5: building connectivity enforcement.
  -- Team `a` already owns roads from the slice-3 block: a chain at
  -- (2608..2728, 3884) and an isolated node at (2908, 4184).
  if frame == 220 and spawned then
    local api = GG and GG.MedievalLogistics
    if not api or type(api.BuildingConnected) ~= "function"
        or type(api.BuildingConnectivitySummary) ~= "function" then
      Spring.Echo("PHASE3 PROBE building-connectivity SKIPPED missing building API")
    else
      local a, b = opposingTeams()
      if a then
        local granaryDef = UnitDefNames and UnitDefNames["medieval_granary"]
        if granaryDef then
          local before = api.BuildingConnectivitySummary(a)
          if before then
            Spring.Echo(string.format("PHASE3 PROBE building-connectivity baseline team=%d total=%d connected=%d disconnected=%d",
              a, before.total or -1, before.connected or -1, before.disconnected or -1))
          end
          -- Connected endpoint: 40 elmos from the chain road at (2608, 3884).
          local nx, nz = 2648, 3884
          local ny = Spring.GetGroundHeight(nx, nz)
          local nearID = Spring.CreateUnit(granaryDef.id, nx, ny, nz, "south", a)
          -- Disconnected endpoint: far from every team road.
          local fx, fz = 4200, 4200
          local fy = Spring.GetGroundHeight(fx, fz)
          local farID = Spring.CreateUnit(granaryDef.id, fx, fy, fz, "south", a)
          Spring.Echo(string.format("PHASE3 PROBE building-connectivity spawned near=%s far=%s team=%d",
            tostring(nearID), tostring(farID), a))
          if nearID and farID then
            local passNear = api.BuildingConnected(a, nearID) == true
            local passFar = api.BuildingConnected(a, farID) == false
            local passIsolation = (b == nil) or (api.BuildingConnected(b, nearID) == false)
            local after = api.BuildingConnectivitySummary(a)
            local passSummary = false
            if before and after then
              passSummary = (after.total == before.total + 2)
                and (after.connected == before.connected + 1)
                and (after.disconnected == before.disconnected + 1)
            end
            Spring.Echo(string.format("PHASE3 PROBE building-connectivity near-verdict f=%d team=%d %s (unit=%d connected=%s)",
              frame, a, passNear and "PASS" or "FAIL", nearID, tostring(api.BuildingConnected(a, nearID))))
            Spring.Echo(string.format("PHASE3 PROBE building-connectivity far-verdict f=%d team=%d %s (unit=%d connected=%s)",
              frame, a, passFar and "PASS" or "FAIL", farID, tostring(api.BuildingConnected(a, farID))))
            Spring.Echo(string.format("PHASE3 PROBE building-connectivity isolation-verdict f=%d otherTeam=%s %s (otherTeamSeesNear=%s)",
              frame, tostring(b), passIsolation and "PASS" or "FAIL",
              tostring(b and api.BuildingConnected(b, nearID))))
            if after then
              Spring.Echo(string.format("PHASE3 PROBE building-connectivity summary team=%d total=%d connected=%d disconnected=%d %s",
                a, after.total or -1, after.connected or -1, after.disconnected or -1,
                passSummary and "PASS" or "FAIL"))
            end
            buildingProbe = { team = a, far = farID, stage = "placed" }
          else
            Spring.Echo(string.format("PHASE3 PROBE building-connectivity SPAWN-FAILED team=%d near=%s far=%s", a, tostring(nearID), tostring(farID)))
          end
        else
          Spring.Echo("PHASE3 PROBE building-connectivity missing medieval_granary UnitDef")
        end
      end
    end
  end
  if buildingProbe and buildingProbe.stage == "placed" and frame >= 224 then
    if Spring.ValidUnitID(buildingProbe.far) then
      Spring.DestroyUnit(buildingProbe.far)
      Spring.Echo(string.format("PHASE3 PROBE building-connectivity destroyed far unit=%d team=%d", buildingProbe.far, buildingProbe.team))
    end
    buildingProbe.stage = "destroyed"
  end
  if buildingProbe and buildingProbe.stage == "destroyed" and frame >= 228 then
    local api = GG and GG.MedievalLogistics
    local a = buildingProbe.team
    if api and api.BuildingConnectivitySummary then
      local final = api.BuildingConnectivitySummary(a)
      if final then
        -- Settlement baseline is unknown here; the far unit was the only unit
        -- this probe created, so require: no disconnected endpoint remains
        -- that this probe introduced (the far granary is gone).
        Spring.Echo(string.format("PHASE3 PROBE building-connectivity post-destroy team=%d total=%d connected=%d disconnected=%d (far unit removed)",
          a, final.total or -1, final.connected or -1, final.disconnected or -1))
      end
    end
    buildingProbe = nil
  end
  -- Phase 3 probe slice 6: road movement-speed enforcement (synced mutator).
  -- Team `a` owns the slice-3 chain at (2608..2728, 3884); this block extends it
  -- east with three more nodes so the on-road walker has a real runway.
  if frame == 238 and spawned then
    local api = GG and GG.MedievalLogistics
    local a = opposingTeams()
    local vilDef = UnitDefNames and UnitDefNames["medieval_villager"]
    if not (api and type(api.GetSpeedState) == "function") then
      Spring.Echo("PHASE3 PROBE road-speed SKIPPED missing GetSpeedState API")
    elseif not a then
      Spring.Echo("PHASE3 PROBE road-speed SKIPPED no opposing team")
    elseif not vilDef then
      Spring.Echo("PHASE3 PROBE road-speed SKIPPED missing medieval_villager UnitDef")
    else
      local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
      if roadDef and type(Spring.CreateFeature) == "function" then
        for i = 1, 3 do
          local rx, rz = 2788 + (i - 1) * 60, 3884
          local ry = Spring.GetGroundHeight(rx, rz)
          local fid = Spring.CreateFeature(roadDef.id, rx, ry, rz, 0, a)
          Spring.Echo(string.format("PHASE3 PROBE road-speed road-extend#%d ftr=%s team=%d at=(%d, %d)",
            i, tostring(fid), a, rx, rz))
        end
      end
      -- The first extension road is at (2788, 3884); start within 48 elmos.
      local ax, az = 2788, 3884
      local bx, bz = 4300, 4200
      local aid = Spring.CreateUnit(vilDef.id, ax, Spring.GetGroundHeight(ax, az), az, "south", a)
      local bid = Spring.CreateUnit(vilDef.id, bx, Spring.GetGroundHeight(bx, bz), bz, "south", a)
      Spring.Echo(string.format("PHASE3 PROBE road-speed spawned A=%s B=%s team=%d A_at=(%d, %d) B_at=(%d, %d)",
        tostring(aid), tostring(bid), a, ax, az, bx, bz))
      if aid and bid then
        speedProbe = { team = a, a = aid, b = bid, stage = "spawned" }
      else
        Spring.Echo(string.format("PHASE3 PROBE road-speed SPAWN-FAILED A=%s B=%s", tostring(aid), tostring(bid)))
      end
    end
  end

  -- ~2 frames later: state check for both walkers.
  if speedProbe and speedProbe.stage == "spawned" and frame >= 242 then
    local aid, bid = speedProbe.a, speedProbe.b
    local aText, aState = speedStateText(aid)
    local bText, bState = speedStateText(bid)
    Spring.Echo(string.format("PHASE3 PROBE road-speed state-a f=%d unit=%d %s", frame, aid, aText))
    Spring.Echo(string.format("PHASE3 PROBE road-speed state-b f=%d unit=%d %s", frame, bid, bText))
    if aState and bState then
      local aBase, bBase = aState.base, bState.base
      local aExp = aBase * 1.5
      local passOnRoad = (aState.onRoad == true) and (bState.onRoad == false)
      local passApplied = speedNear(aState.applied, aExp) and speedNear(bState.applied, bBase)
      local passSource = (aState.source == "mutator") or (aState.source == "rules-param")
      Spring.Echo(string.format("PHASE3 PROBE road-speed onroad-verdict f=%d %s (A onRoad=%s expect=true, B onRoad=%s expect=false)",
        frame, passOnRoad and "PASS" or "FAIL", tostring(aState.onRoad), tostring(bState.onRoad)))
      Spring.Echo(string.format("PHASE3 PROBE road-speed applied-verdict f=%d %s (A applied=%.2f expect=%.2f, B applied=%.2f expect=%.2f)",
        frame, passApplied and "PASS" or "FAIL", aState.applied or -1, aExp, bState.applied or -1, bBase))
      Spring.Echo(string.format("PHASE3 PROBE road-speed source-verdict f=%d %s (A source=%s expect=mutator|rules-param)",
        frame, passSource and "PASS" or "FAIL", tostring(aState.source)))
      if aState.source ~= "mutator" then
        Spring.Echo(string.format("PHASE3 PROBE road-speed source-note f=%d A source=%s (MoveCtrl mutator unavailable; non-enforcing fallback)",
          frame, tostring(aState.source)))
      end
    else
      Spring.Echo(string.format("PHASE3 PROBE road-speed state-verdict f=%d SKIPPED (aState=%s bState=%s)",
        frame, tostring(aState ~= nil), tostring(bState ~= nil)))
    end
    speedProbe.stage = "checked"
  end

  -- Long move orders so both walk: A east along the extended chain, B over open ground.
  if speedProbe and speedProbe.stage == "checked" and frame >= 244 then
    local ax, az = 3400, 3884
    local bx, bz = 4600, 4200
    if type(Spring.GiveOrderToUnit) == "function" then
      pcall(Spring.GiveOrderToUnit, speedProbe.a, CMD.MOVE, { ax, Spring.GetGroundHeight(ax, az), az }, {})
      pcall(Spring.GiveOrderToUnit, speedProbe.b, CMD.MOVE, { bx, Spring.GetGroundHeight(bx, bz), bz }, {})
      Spring.Echo(string.format("PHASE3 PROBE road-speed move-order f=%d A=%d -> (%d, %d) B=%d -> (%d, %d)",
        frame, speedProbe.a, ax, az, speedProbe.b, bx, bz))
    else
      Spring.Echo("PHASE3 PROBE road-speed move-order SKIPPED Spring.GiveOrderToUnit unavailable")
    end
    speedProbe.stage = "walking"
  end

  -- Mid-walk velocity evidence (soft: state checks own the verdict).
  if speedProbe and speedProbe.stage == "walking" and frame >= 274 then
    local velA = speedUnitVelocity(speedProbe.a)
    local velB = speedUnitVelocity(speedProbe.b)
    local posA, posB = "?", "?"
    if type(Spring.GetUnitPosition) == "function" then
      local ax, _, az = Spring.GetUnitPosition(speedProbe.a)
      local bx, _, bz = Spring.GetUnitPosition(speedProbe.b)
      if ax and az then posA = string.format("(%d, %d)", ax, az) end
      if bx and bz then posB = string.format("(%d, %d)", bx, bz) end
    end
    if velA and velB then
      local note = "EVIDENCE"
      if velA > velB then note = "PASS(soft)" end
      if velA <= 0.01 and velB <= 0.01 then note = "STUCK" end
      Spring.Echo(string.format("PHASE3 PROBE road-speed velocity f=%d A=%d velA=%.2f posA=%s B=%d velB=%.2f posB=%s delta=%.2f %s",
        frame, speedProbe.a, velA, posA, speedProbe.b, velB, posB, velA - velB, note))
    else
      Spring.Echo(string.format("PHASE3 PROBE road-speed velocity f=%d SKIPPED (velA=%s velB=%s)",
        frame, tostring(velA), tostring(velB)))
    end
    speedProbe.velA = velA
    speedProbe.velB = velB
    speedProbe.stage = "measured"
  end

  -- Restoration: take A off the road, then let the next scan restore the baseline.
  if speedProbe and speedProbe.stage == "measured" and frame >= 298 then
    local ax, az = 3600, 4200
    local mode = "none"
    if type(Spring.SetUnitPosition) == "function" then
      local ok = pcall(Spring.SetUnitPosition, speedProbe.a, ax, Spring.GetGroundHeight(ax, az), az)
      if ok then mode = "set-position" end
    end
    if mode == "none" and type(Spring.GiveOrderToUnit) == "function" then
      pcall(Spring.GiveOrderToUnit, speedProbe.a, CMD.MOVE, { ax, Spring.GetGroundHeight(ax, az), az }, {})
      mode = "move-order"
    end
    if mode == "none" then
      Spring.Echo("PHASE3 PROBE road-speed restore SKIPPED no SetUnitPosition/GiveOrderToUnit")
    end
    Spring.Echo(string.format("PHASE3 PROBE road-speed restore f=%d A=%d -> (%d, %d) mode=%s", frame, speedProbe.a, ax, az, mode))
    speedProbe.restoreMode = mode
    speedProbe.stage = "restored"
  end

  if speedProbe and speedProbe.stage == "restored" and frame >= 302 then
    local aid = speedProbe.a
    local aText, aState = speedStateText(aid)
    Spring.Echo(string.format("PHASE3 PROBE road-speed restore-state f=%d unit=%d %s", frame, aid, aText))
    if aState then
      local passOffRoad = (aState.onRoad == false)
      local passBase = speedNear(aState.applied, aState.base)
      Spring.Echo(string.format("PHASE3 PROBE road-speed restore-verdict f=%d %s (onRoad=%s expect=false pass=%s, applied=%.2f expect=%.2f pass=%s, mode=%s)",
        frame, (passOffRoad and passBase) and "PASS" or "FAIL",
        tostring(aState.onRoad), tostring(passOffRoad),
        aState.applied or -1, aState.base or -1, tostring(passBase),
        tostring(speedProbe.restoreMode)))
    else
      Spring.Echo(string.format("PHASE3 PROBE road-speed restore-verdict f=%d SKIPPED (state unavailable)", frame))
    end
    local vA, vB = speedProbe.velA, speedProbe.velB
    local velNote = "unavailable"
    if vA and vB then
      if vA > vB then velNote = "PASS(soft) velA>velB"
      elseif vA <= 0.01 and vB <= 0.01 then velNote = "STUCK both stationary"
      else velNote = string.format("EVIDENCE velA=%.2f velB=%.2f", vA, vB) end
    end
    Spring.Echo(string.format("PHASE3 PROBE road-speed summary f=%d team=%d A=%d B=%d velocity=%s",
      frame, speedProbe.team, speedProbe.a, speedProbe.b, velNote))
    speedProbe = nil
  end

  -- -------------------------------------------------------------------------
  -- Phase 3 probe slice 7: supply bonuses, road-aware pathing, and damage.
  -- Uses an isolated region (6000, 6000) so settlement/probe state from earlier
  -- slices cannot bias these verdicts. Target SELECTION is the only thing the
  -- gather gadget implements (no waypoint routing); the probe therefore asserts
  -- the selected target id, not any routed path.
  -- -------------------------------------------------------------------------

  -- Def-shape evidence: print the actual engine fields the eligibility check
  -- keys on, proving buildings must be discriminated by `canMove`, not the
  -- unreliable derived `isBuilding`.
  if frame == 320 and spawned then
    local gd = UnitDefNames and UnitDefNames["medieval_granary"] and UnitDefs and UnitDefs[UnitDefNames["medieval_granary"].id]
    local idf = UnitDefNames and UnitDefNames["medieval_infantry"] and UnitDefs and UnitDefs[UnitDefNames["medieval_infantry"].id]
    if gd and idf then
      Spring.Echo(string.format("PHASE3 PROBE supply def-shape granary.isBuilding=%s granary.canMove=%s granary.speed=%s | infantry.isBuilding=%s infantry.canMove=%s infantry.speed=%s",
        tostring(gd.isBuilding), tostring(gd.canMove), tostring(gd.speed),
        tostring(idf.isBuilding), tostring(idf.canMove), tostring(idf.speed)))
    end
  end

  if frame == 322 and spawned then
    local api = GG and GG.MedievalLogistics
    local a, b = opposingTeams()
    local granaryDef = UnitDefNames and UnitDefNames["medieval_granary"]
    local infDef = UnitDefNames and UnitDefNames["medieval_infantry"]
    local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
    if not (api and type(api.SupplyStateAt) == "function" and type(api.SupplyEndpointCountAt) == "function"
        and type(api.SupplyBonus) == "function" and type(api.Research) == "function"
        and type(api.IsResearched) == "function" and type(api.DamageMultiplier) == "function") then
      Spring.Echo("PHASE3 PROBE supply SKIPPED missing MedievalLogistics supply API")
    elseif not (a and b) then
      Spring.Echo("PHASE3 PROBE supply SKIPPED no opposing teams")
    elseif not (granaryDef and infDef and roadDef) then
      Spring.Echo("PHASE3 PROBE supply SKIPPED missing granary/infantry/road defs")
    else
      local ry = Spring.GetGroundHeight(6000, 6000)
      local road = Spring.CreateFeature(roadDef.id, 6000, ry, 6000, 0, a)
      local gy = Spring.GetGroundHeight(6000, 6000)
      local endpoint = Spring.CreateUnit(granaryDef.id, 6000, gy, 6000, "south", a)
      local sy = Spring.GetGroundHeight(6050, 6000)
      local supplied = Spring.CreateUnit(infDef.id, 6050, sy, 6000, "south", a)
      local iy = Spring.GetGroundHeight(6060, 6000)
      local isolated = Spring.CreateUnit(infDef.id, 6060, iy, 6000, "south", b)
      local fy = Spring.GetGroundHeight(6400, 6400)
      local far = Spring.CreateUnit(infDef.id, 6400, fy, 6400, "south", a)
      if road and endpoint and supplied and isolated and far then
        supplyProbe = { team = a, enemy = b, road = road, endpoint = endpoint,
          supplied = supplied, isolated = isolated, far = far, stage = "setup" }
        Spring.Echo(string.format("PHASE3 PROBE supply setup f=%d team=%d enemy=%d road=%s endpoint=%s supplied=%s isolated=%s far=%s",
          frame, a, b, tostring(road), tostring(endpoint), tostring(supplied), tostring(isolated), tostring(far)))
      else
        Spring.Echo(string.format("PHASE3 PROBE supply SPAWN-FAILED f=%d road=%s endpoint=%s supplied=%s isolated=%s far=%s",
          frame, tostring(road), tostring(endpoint), tostring(supplied), tostring(isolated), tostring(far)))
      end
    end
  end

  if supplyProbe and supplyProbe.stage == "setup" and frame >= 326 then
    local api = GG.MedievalLogistics
    local a, b = supplyProbe.team, supplyProbe.enemy
    local suppliedSt = api.SupplyStateAt(a, 6050, 6000)
    local unsuppliedSt = api.SupplyStateAt(a, 6400, 6400)
    local isolatedSt = api.SupplyStateAt(b, 6060, 6000)
    local endCount = api.SupplyEndpointCountAt(a, 6050, 6000)
    local passSupplied = suppliedSt ~= nil and suppliedSt.inSupply == true and suppliedSt.count >= 1
    local passUnsupplied = unsuppliedSt ~= nil and unsuppliedSt.inSupply ~= true
    local passIsolated = isolatedSt ~= nil and isolatedSt.inSupply ~= true
    local passCount = type(endCount) == "number" and endCount >= 1
    Spring.Echo(string.format("PHASE3 PROBE supply supplied-verdict f=%d %s (inSupply=%s count=%s endpointCount=%s)",
      frame, passSupplied and "PASS" or "FAIL", tostring(suppliedSt and suppliedSt.inSupply),
      tostring(suppliedSt and suppliedSt.count), tostring(endCount)))
    Spring.Echo(string.format("PHASE3 PROBE supply unsupplied-verdict f=%d %s (far inSupply=%s)",
      frame, passUnsupplied and "PASS" or "FAIL", tostring(unsuppliedSt and unsuppliedSt.inSupply)))
    Spring.Echo(string.format("PHASE3 PROBE supply team-isolation-verdict f=%d %s (enemy inSupply=%s)",
      frame, passIsolated and "PASS" or "FAIL", tostring(isolatedSt and isolatedSt.inSupply)))
    Spring.Echo(string.format("PHASE3 PROBE supply endpoint-count-verdict f=%d %s (count=%s expect>=1)",
      frame, passCount and "PASS" or "FAIL", tostring(endCount)))
    supplyProbe.stage = "state-sampled"
  end

  if supplyProbe and supplyProbe.stage == "state-sampled" and frame >= 330 then
    local api = GG.MedievalLogistics
    local econ = GG and GG.MedievalEconomy
    local a = supplyProbe.team
    if econ and type(econ.Deposit) == "function" then
      econ.Deposit(a, "wood", 200)
      econ.Deposit(a, "iron", 300)
    end
    local ok = api.Research(a, "iron_swords")
    local researched = api.IsResearched(a, "iron_swords") == true
    local techMult = api.DamageMultiplier(a, "medieval_infantry")
    local bonus = api.SupplyBonus(supplyProbe.supplied)
    local passTech = researched and type(techMult) == "number" and math.abs(techMult - 1.25) < 0.001
    local passBonus = type(bonus) == "number" and bonus > 0
    Spring.Echo(string.format("PHASE3 PROBE supply damage-tech verdict f=%d %s (ok=%s researched=%s mult=%.3f)",
      frame, passTech and "PASS" or "FAIL", tostring(ok), tostring(researched), tostring(techMult)))
    Spring.Echo(string.format("PHASE3 PROBE supply damage-bonus verdict f=%d %s (SupplyBonus=%.3f expect>0)",
      frame, passBonus and "PASS" or "FAIL", tostring(bonus)))
    local combined = (type(techMult) == "number" and techMult or 1.0) * (1.0 + (type(bonus) == "number" and bonus or 0))
    Spring.Echo(string.format("PHASE3 PROBE supply damage-stack f=%d team=%d tech=%.3f supply=%.3f combined=%.4f (UnitPreDamaged multiplies these two)",
      frame, a, type(techMult) == "number" and techMult or -1, type(bonus) == "number" and bonus or -1, combined))
    -- Real attack (soft evidence only): supplied + iron_swords attacker ordered
    -- onto an enemy target; the logistics gadget then logs the actual scaled
    -- damage lines ("PHASE3 DAMAGE"/"PHASE3 SUPPLY damage") in UnitPreDamaged.
    local tx, tz = 6080, 6000
    local ty = Spring.GetGroundHeight(tx, tz)
    local target = Spring.CreateUnit(UnitDefNames["medieval_infantry"].id, tx, ty, tz, "south", supplyProbe.enemy)
    if target and type(Spring.GiveOrderToUnit) == "function" and CMD and CMD.ATTACK then
      pcall(Spring.GiveOrderToUnit, supplyProbe.supplied, CMD.ATTACK, { target }, {})
      Spring.Echo(string.format("PHASE3 PROBE supply damage-attack-order f=%d attacker=%s target=%s (real UnitPreDamaged path; end-to-end evidence in PHASE3 DAMAGE/SUPPLY damage lines)",
        frame, tostring(supplyProbe.supplied), tostring(target)))
    else
      Spring.Echo(string.format("PHASE3 PROBE supply damage-attack-order SKIPPED f=%d target=%s attackAPI=%s", frame, tostring(target), tostring(type(Spring.GiveOrderToUnit))))
    end
    supplyProbe.target = target
    supplyProbe.techMult = techMult
    supplyProbe.supplyBonusValue = bonus
    supplyProbe.stage = "damage-sampled"
  end

  -- Restoration: destroy the endpoint's only road, then confirm supply drops
  -- on a LATER frame. Spring defers FeatureDestroyed (and the logistics graph
  -- update) past the current GameFrame, so the state is re-read a few frames
  -- after the DestroyFeature call.
  if supplyProbe and supplyProbe.stage == "damage-sampled" and frame >= 350 then
    local removed = false
    if type(Spring.DestroyFeature) == "function" then
      local ok = pcall(Spring.DestroyFeature, supplyProbe.road)
      removed = ok
    end
    Spring.Echo(string.format("PHASE3 PROBE supply road-removal f=%d road=%s team=%d destroyPcall=%s", frame, tostring(supplyProbe.road), supplyProbe.team, tostring(removed)))
    supplyProbe.stage = "road-removed"
  end

  if supplyProbe and supplyProbe.stage == "road-removed" and frame >= 354 then
    local api = GG.MedievalLogistics
    local a = supplyProbe.team
    local after = api.SupplyStateAt(a, 6050, 6000)
    local pass = after ~= nil and after.inSupply ~= true
    Spring.Echo(string.format("PHASE3 PROBE supply restoration-verdict f=%d %s (after road removal inSupply=%s count=%s)",
      frame, pass and "PASS" or "FAIL", tostring(after and after.inSupply), tostring(after and after.count)))
    supplyProbe = nil
  end

  if frame == 340 and spawned then
    local gather = GG and GG.MedievalGather
    local api = GG and GG.MedievalLogistics
    local a = opposingTeams()
    local vilDef = UnitDefNames and UnitDefNames["medieval_villager"]
    local treeDef = FeatureDefNames and FeatureDefNames["medieval_tree"]
    local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
    if not (gather and type(gather.AssignGather) == "function" and type(gather.GetJob) == "function") then
      Spring.Echo("PHASE3 PROBE gather SKIPPED missing MedievalGather.AssignGather/GetJob")
    elseif not (api and type(api.PointOnRoadNetwork) == "function") then
      Spring.Echo("PHASE3 PROBE gather SKIPPED missing MedievalLogistics.PointOnRoadNetwork")
    elseif not (a and vilDef and treeDef and roadDef) then
      Spring.Echo("PHASE3 PROBE gather SKIPPED missing villager/tree/road defs")
    else
      -- Safe map region between the two settlements (confirmed unit-safe by the
      -- Slice 5 building probe at (4200,4200) and Slice 6 at (4300,4200)),
      -- laid out so a road-connected tree at 150 elmos beats a nearer (110 elmo)
      -- off-network tree: 150 < 110 * PATH_COST_UNSUPPLIED (165).
      -- Fund the villager's recruitment food cost first: gadget_medieval_recruitment
      -- tears the unit down in UnitFinished when the team cannot afford it.
      local econ = GG and GG.MedievalEconomy
      if econ and type(econ.Deposit) == "function" then
        econ.Deposit(a, "food", 150)
      end
      local ry = Spring.GetGroundHeight(4000, 4950)
      local road = Spring.CreateFeature(roadDef.id, 4000, ry, 4950, 0, a)
      local n1y = Spring.GetGroundHeight(4110, 4800)
      local near = Spring.CreateFeature(treeDef.id, 4110, n1y, 4800, 0)
      local n2y = Spring.GetGroundHeight(4000, 4950)
      local far = Spring.CreateFeature(treeDef.id, 4000, n2y, 4950, 0)
      local vy = Spring.GetGroundHeight(4000, 4800)
      local villager = Spring.CreateUnit(vilDef.id, 4000, vy, 4800, "south", a)
      if road and near and far and villager then
        gatherProbe = { team = a, villager = villager, near = near, far = far, road = road }
        Spring.Echo(string.format("PHASE3 PROBE gather setup f=%d team=%d villager=%s near=%s far=%s road=%s",
          frame, a, tostring(villager), tostring(near), tostring(far), tostring(road)))
      else
        Spring.Echo(string.format("PHASE3 PROBE gather SPAWN-FAILED f=%d road=%s near=%s far=%s villager=%s",
          frame, tostring(road), tostring(near), tostring(far), tostring(villager)))
      end
    end
  end

  if gatherProbe and frame >= 345 then
    local gather = GG.MedievalGather
    local remNear = gather.NodeRemaining(gatherProbe.near)
    local remFar = gather.NodeRemaining(gatherProbe.far)
    local ok = gather.AssignGather(gatherProbe.villager, nil)
    local job = gather.GetJob(gatherProbe.villager)
    local picked = job and job.nodeID
    local pass = ok == true and picked == gatherProbe.far
    Spring.Echo(string.format("PHASE3 PROBE gather selection-verdict f=%d %s (ok=%s picked=%s expect_far=%s near=%s remNear=%s remFar=%s; target selection only, no waypoint routing)",
      frame, pass and "PASS" or "FAIL", tostring(ok), tostring(picked), tostring(gatherProbe.far), tostring(gatherProbe.near), tostring(remNear), tostring(remFar)))
    gatherProbe = nil
  end

  -- ===================== Slice 8: Phase 4 Slice 1 siege catapult =====================
  -- Spawns a friendly medieval_catapult and an enemy medieval_wall 300 elmos east
  -- (between minRange 120 and range 550), orders an attack, then samples the weapon
  -- state and the target's health. Every stage is pcall-guarded and nil-checked.
  if frame == 360 and spawned then
    local a, b = opposingTeams()
    local catDef = UnitDefNames and UnitDefNames["medieval_catapult"]
    local wallDef = UnitDefNames and UnitDefNames["medieval_wall"]
    if not (a and b) then
      Spring.Echo("PHASE4 PROBE catapult SKIPPED no opposing teams")
    elseif not catDef then
      Spring.Echo("PHASE4 PROBE catapult SKIPPED missing medieval_catapult UnitDef")
    elseif not wallDef then
      Spring.Echo("PHASE4 PROBE catapult SKIPPED missing medieval_wall UnitDef")
    else
      -- gadget_medieval_recruitment charges the discrete cost at UnitFinished and
      -- destroys the unit when the team cannot pay; fund it before spawning.
      local econ = GG and GG.MedievalEconomy
      if econ and type(econ.Deposit) == "function" then
        econ.Deposit(a, "wood", 200)
        econ.Deposit(a, "stone", 120)
        econ.Deposit(a, "iron", 60)
      end
      local cx, cz = 5200, 5200
      local tx, tz = 5500, 5200
      local cy = Spring.GetGroundHeight(cx, cz)
      local ty = Spring.GetGroundHeight(tx, tz)
      -- Facing "east" pre-aligns the turret with the target 300 elmos east.
      local cat = Spring.CreateUnit(catDef.id, cx, cy, cz, "east", a)
      local wall = Spring.CreateUnit(wallDef.id, tx, ty, tz, "south", b)
      if not (cat and wall) then
        Spring.Echo(string.format("PHASE4 PROBE catapult SPAWN-FAILED f=%d catapult=%s target=%s",
          frame, tostring(cat), tostring(wall)))
      else
        local hp0 = siegeTargetHealth(wall)
        local ordered = false
        if type(Spring.GiveOrderToUnit) == "function" and CMD and CMD.ATTACK then
          ordered = pcall(Spring.GiveOrderToUnit, cat, CMD.ATTACK, { wall }, {}) and true or false
        end
        siegeProbe = { team = a, enemy = b, catapult = cat, target = wall,
                       hp0 = hp0, stage = "ordered" }
        Spring.Echo(string.format("PHASE4 PROBE catapult spawned f=%d team=%d id=%s target=%s enemy=%d hp0=%s dist=300",
          frame, a, tostring(cat), tostring(wall), b, tostring(hp0)))
        Spring.Echo(string.format("PHASE4 PROBE catapult spawn-verdict f=%d %s (id=%s target=%s hp0=%s)",
          frame, (cat and wall and type(hp0) == "number" and hp0 > 0) and "PASS" or "FAIL",
          tostring(cat), tostring(wall), tostring(hp0)))
        Spring.Echo(string.format("PHASE4 PROBE catapult attack-order f=%d %s (giveOrderAPI=%s)",
          frame, ordered and "PASS" or "FAIL", tostring(type(Spring.GiveOrderToUnit))))
      end
    end
  end

  -- Aim evidence at f=380: the LUS publishes its aim state as a unit rules param,
  -- which is readable in synced code regardless of weapon-state API shape. The
  -- "aiming" flag can only be set from script.AimWeapon1, so a 1 proves the engine
  -- called into the catapult's unit script.
  if siegeProbe and siegeProbe.stage == "ordered" and frame >= 380 then
    local aiming = siegeLusParam(siegeProbe.catapult, "medieval_catapult_aiming")
    siegeProbe.stage = "aimed"
    siegeProbe.aiming = aiming
    Spring.Echo(string.format("PHASE4 PROBE catapult aim f=%d lusAimingParam=%s selfHp=%s",
      frame, tostring(aiming), tostring(siegeTargetHealth(siegeProbe.catapult))))
    Spring.Echo(string.format("PHASE4 PROBE catapult aim-verdict f=%d %s (LUS AimWeapon1 ran, aiming=%s expect=1)",
      frame, (tonumber(aiming) == 1) and "PASS" or "FAIL", tostring(aiming)))
  end

  -- Pre-fire health trace: confirms the catapult survives its own launch and
  -- pins the frame at which the first shot actually leaves the engine.
  if siegeProbe and siegeProbe.stage == "aimed" and frame >= 500 and not siegeProbe.preFireLogged then
    siegeProbe.preFireLogged = true
    Spring.Echo(string.format("PHASE4 PROBE catapult pre-fire f=%d selfHp=%s targetHp=%s",
      frame, tostring(siegeTargetHealth(siegeProbe.catapult)),
      tostring(siegeTargetHealth(siegeProbe.target))))
  end

  -- Fire evidence at f=540: the first shot leaves the engine at ~f=502 (5.0s
  -- reload from spawn at f=360), so this samples after the shot and after the
  -- 350-velocity rock has reached the wall 300 elmos away.
  if siegeProbe and siegeProbe.stage == "aimed" and frame >= 540 then
    local firedParam = siegeLusParam(siegeProbe.catapult, "medieval_catapult_fired")
    local hp = siegeTargetHealth(siegeProbe.target)
    local selfHp = siegeTargetHealth(siegeProbe.catapult)
    local dealt = 0
    if type(siegeProbe.hp0) == "number" and type(hp) == "number" then
      dealt = siegeProbe.hp0 - hp
    end
    local fired = tonumber(firedParam) == 1
    siegeProbe.stage = "fired"
    Spring.Echo(string.format("PHASE4 PROBE catapult fire f=%d lusFiredParam=%s selfHp=%s targetHp=%s hp0=%s dealt=%.1f",
      frame, tostring(firedParam), tostring(selfHp), tostring(hp), tostring(siegeProbe.hp0), dealt))
    Spring.Echo(string.format("PHASE4 PROBE catapult fire-verdict f=%d %s (LUS FireWeapon1 ran, fired=%s)",
      frame, fired and "PASS" or "FAIL", tostring(firedParam)))
    -- The launcher must survive its own shot (noSelfDamage + no muzzle piece).
    Spring.Echo(string.format("PHASE4 PROBE catapult self-damage-verdict f=%d %s (selfHp=%s)",
      frame, (type(selfHp) == "number" and selfHp > 0) and "PASS" or "FAIL", tostring(selfHp)))
  end

  -- Damage evidence: the wall must have lost health to the catapult's rock.
  if siegeProbe and siegeProbe.stage == "fired" and frame >= 570 then
    local hp = siegeTargetHealth(siegeProbe.target)
    local dealt = 0
    if type(siegeProbe.hp0) == "number" and type(hp) == "number" then
      dealt = siegeProbe.hp0 - hp
    end
    Spring.Echo(string.format("PHASE4 PROBE catapult damage-verdict f=%d %s (dealt=%.1f expect>0 hp0=%s hp=%s)",
      frame, dealt > 0 and "PASS" or "FAIL", dealt, tostring(siegeProbe.hp0), tostring(hp)))
    siegeProbe.stage = "done"
  end

  -- ============ Phase 4 Slice 2: damage-type matrix (siege 3x, melee 0.25x) ============
  -- Siege: reuse Slice 1's catapult hit on its wall (siegeProbe). Sample at f=470,
  -- after the first rock lands (~f=386) and before the second launches (~f=511), so
  -- exactly one 3x hit is measured (2500 -> ~1150). dealt >= 2.2x base proves 3x,
  -- not the 1x a non-matrix engine would apply.
  if siegeProbe and not dmatrixSiegeDone and frame >= 470 then
    dmatrixSiegeDone = true
    local hp = siegeTargetHealth(siegeProbe.target)
    local dealt = 0
    if type(siegeProbe.hp0) == "number" and type(hp) == "number" then
      dealt = siegeProbe.hp0 - hp
    end
    local api = GG and GG.MedievalLogistics
    local apiMult = (api and type(api.DamageTypeMultiplier) == "function")
      and api.DamageTypeMultiplier("siege", "fortification") or 0
    local base = CATAPULT_BASE_DAMAGE
    local pass = (dealt >= 2.2 * base) and math.abs(apiMult - 3.0) < 0.001
    Spring.Echo(string.format("PHASE4 DMATRIX siege-vs-wall %s f=%d dealt=%.1f base=%.1f mult=%.2f matrix=%.2f hp0=%s hp=%s",
      pass and "PASS" or "FAIL", frame, dealt, base, dealt / base, apiMult,
      tostring(siegeProbe.hp0), tostring(hp)))
  end

  -- Melee: spawn a fresh enemy wall in the proven z=5200 lane (cast of Slice 1's
  -- wall, outside the catapult's 550 range) plus an adjacent infantry (melee),
  -- then sample ~2 sword swings so dealt (~75) stays below the raw base 150.
  if not dmatrixMeleeSpawned and frame == 480 and spawned then
    dmatrixMeleeSpawned = true
    local a, b = opposingTeams()
    local infDef = UnitDefNames and UnitDefNames["medieval_infantry"]
    local wallDef = UnitDefNames and UnitDefNames["medieval_wall"]
    if not (a and b and infDef and wallDef) then
      Spring.Echo("PHASE4 DMATRIX melee SKIPPED missing infantry/wall UnitDef or teams")
    else
      local wx, wz = 5850, 5200
      local ix, iz = 5880, 5200
      local wy = Spring.GetGroundHeight(wx, wz)
      local iy = Spring.GetGroundHeight(ix, iz)
      local wall = Spring.CreateUnit(wallDef.id, wx, wy, wz, "south", b)
      local inf = Spring.CreateUnit(infDef.id, ix, iy, iz, "south", a)
      if not (wall and inf) then
        Spring.Echo(string.format("PHASE4 DMATRIX melee SPAWN-FAILED f=%d inf=%s wall=%s", frame, tostring(inf), tostring(wall)))
      else
        if type(Spring.GiveOrderToUnit) == "function" and CMD and CMD.ATTACK then
          pcall(Spring.GiveOrderToUnit, inf, CMD.ATTACK, { wall }, {})
        end
        dmatrixMeleeProbe = { attacker = inf, target = wall, hp0 = siegeTargetHealth(wall) }
        Spring.Echo(string.format("PHASE4 DMATRIX melee-setup f=%d infantry=%s wall=%s hp0=%s",
          frame, tostring(inf), tostring(wall), tostring(dmatrixMeleeProbe.hp0)))
      end
    end
  end

  -- Melee verdict (f=540): reduced damage vs the sword's base 150.
  if dmatrixMeleeProbe and not dmatrixMeleeVerdictDone and frame >= 540 then
    dmatrixMeleeVerdictDone = true
    local hp = siegeTargetHealth(dmatrixMeleeProbe.target)
    local dealt = 0
    if type(dmatrixMeleeProbe.hp0) == "number" and type(hp) == "number" then
      dealt = dmatrixMeleeProbe.hp0 - hp
    end
    local api = GG and GG.MedievalLogistics
    local apiMult = (api and type(api.DamageTypeMultiplier) == "function")
      and api.DamageTypeMultiplier("melee", "fortification") or 0
    local base = SWORD_BASE_DAMAGE
    local pass = (dealt > 0) and (dealt < base) and math.abs(apiMult - 0.25) < 0.001
    Spring.Echo(string.format("PHASE4 DMATRIX melee-vs-wall %s f=%d dealt=%.1f base=%.1f ratio=%.2f matrix=%.2f hp0=%s hp=%s",
      pass and "PASS" or "FAIL", frame, dealt, base, dealt / base, apiMult,
      tostring(dmatrixMeleeProbe.hp0), tostring(hp)))
  end

  -- ==================== Phase 4 Slice 3: production chains (blacksmith/fletcher) ====================
  -- Spawns a blacksmith and a fletcher for the probe team in the isolated region
  -- south of the Slice 1/2 lane (5200..5880, 5200), then lets the production-chains
  -- gadget craft on its own 30-frame cadence: sword from the blacksmith, bow from
  -- the fletcher, each paid out of the team's iron/wood by MedievalEconomy. The
  -- team is funded first because the crafting transaction must succeed.
  -- The recruit gate is sampled twice on the real gate
  -- (GG.MedievalRecruitment.CanRecruit): once while sword stock is still 0 and
  -- once after crafting has filled it, so the equipment gate must flip.
  if frame == 620 and spawned and not craftProbe then
    local a = opposingTeams()
    local smithDef = UnitDefNames and UnitDefNames["medieval_blacksmith"]
    local fletcherDef = UnitDefNames and UnitDefNames["medieval_fletcher"]
    local api = GG and GG.MedievalLogistics
    if not a then
      Spring.Echo("PHASE4 CRAFT SKIPPED no probe team")
    elseif not (smithDef and fletcherDef) then
      Spring.Echo("PHASE4 CRAFT SKIPPED missing medieval_blacksmith/medieval_fletcher UnitDef")
    elseif not (api and type(api.equipmentStock) == "table") then
      Spring.Echo("PHASE4 CRAFT SKIPPED missing GG.MedievalLogistics.equipmentStock")
    else
      -- Fund the recipes (sword: iron 5 + wood 2; bow: wood 5 + iron 1 per craft)
      -- and the blacksmith/fletcher build costs, then keep food positive so the
      -- recruit gate's other clauses do not mask the equipment result.
      local econ = GG and GG.MedievalEconomy
      if econ and type(econ.Deposit) == "function" then
        econ.Deposit(a, "iron", 200)
        econ.Deposit(a, "wood", 200)
        econ.Deposit(a, "food", 200)
      end
      local sx, sz = 5200, 6000
      local fx, fz = 5320, 6000
      local smith = Spring.CreateUnit(smithDef.id, sx, Spring.GetGroundHeight(sx, sz), sz, "south", a)
      local fletcher = Spring.CreateUnit(fletcherDef.id, fx, Spring.GetGroundHeight(fx, fz), fz, "south", a)
      local sword0 = equipmentStockOf(a, "sword")
      local bow0 = equipmentStockOf(a, "bow")
      local highTier0 = recruitGateAllows(a, "medieval_cavalry")
      craftProbe = {
        team = a, blacksmith = smith, fletcher = fletcher,
        sword0 = sword0, bow0 = bow0,
        -- nil when the gate is not observable; a boolean is the expected shape.
        highTier0 = highTier0, stage = "spawned",
      }
      Spring.Echo(string.format("PHASE4 CRAFT setup f=%d team=%d blacksmith=%s fletcher=%s sword0=%s bow0=%s",
        frame, a, tostring(smith), tostring(fletcher), tostring(sword0), tostring(bow0)))
      Spring.Echo(string.format("PHASE4 CRAFT gate-baseline f=%d cavalry-can-recruit=%s (expect false at 0 sword stock)",
        frame, tostring(highTier0)))
    end
  end

  -- Craft verdicts at f=860: the crafting cadence is one transaction per crafter
  -- per 30 frames, so 8 seconds is ~16 attempts, far more than the 2 sword / 1 bow
  -- the recipes need. Stock is read back through the published table, which is the
  -- same source the recruit gate consumes.
  if craftProbe and craftProbe.stage == "spawned" and frame >= 860 then
    craftProbe.stage = "crafted"
    local sword = equipmentStockOf(craftProbe.team, "sword")
    local bow = equipmentStockOf(craftProbe.team, "bow")
    craftProbe.sword = sword
    craftProbe.bow = bow
    local swordPass = type(sword) == "number" and sword > 0
    local bowPass = type(bow) == "number" and bow > 0
    Spring.Echo(string.format("PHASE4 CRAFT stock f=%d team=%d sword=%s bow=%s",
      frame, craftProbe.team, tostring(sword), tostring(bow)))
    Spring.Echo(string.format("PHASE4 CRAFT sword-vs-verdict %s f=%d stock=%s expect>0 blacksmith=%s",
      swordPass and "PASS" or "FAIL", frame, tostring(sword), tostring(craftProbe.blacksmith)))
    Spring.Echo(string.format("PHASE4 CRAFT bow-vs-verdict %s f=%d stock=%s expect>0 fletcher=%s",
      bowPass and "PASS" or "FAIL", frame, tostring(bow), tostring(craftProbe.fletcher)))
  end

  -- Recruit-gate verdict at f=880: a sword-gated high-tier unit (cavalry) must have
  -- been blocked at 0 stock and allowed once the blacksmith filled it. Both samples
  -- come from the live gate, not from a re-derived rule.
  if craftProbe and craftProbe.stage == "crafted" and frame >= 880 then
    craftProbe.stage = "done"
    local allowed = recruitGateAllows(craftProbe.team, "medieval_cavalry")
    local blockedBefore = craftProbe.highTier0 == false
    local allowedAfter = allowed == true
    local pass = blockedBefore and allowedAfter
    Spring.Echo(string.format("PHASE4 CRAFT recruit-gate-verdict %s f=%d before(sword=%s)=%s after(sword=%s)=%s unit=medieval_cavalry",
      pass and "PASS" or "FAIL", frame, tostring(craftProbe.sword0), tostring(craftProbe.highTier0),
      tostring(craftProbe.sword), tostring(allowed)))
  end

  -- Phase 4 Slice 4 military-upgrade probe. Stage 1 (f=920) records the tech-gate
  -- baseline: the Chivalric Knight is equipment-gated on a sword (which the Slice 3
  -- blacksmith has already stocked) and tech-gated on chivalry (not yet researched),
  -- so the live gate must refuse it. Stage 2 (f=950) unlocks chivalry through the
  -- real API, stage 3 (f=990) re-reads the same gate and stage 4 (f=1030) reads the
  -- damage multiplier the logistics registry folds from the researched tech.
  if frame >= 920 and spawned and not upgradeProbe then
    local a = opposingTeams()
    local knightDef = UnitDefNames and UnitDefNames["medieval_knight"]
    local api = GG and GG.MedievalLogistics
    if not a then
      upgradeProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 UPGRADE SKIPPED no probe team")
    elseif not knightDef then
      upgradeProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 UPGRADE SKIPPED missing medieval_knight UnitDef")
    elseif not (api and type(api.UnlockTech) == "function"
        and type(api.IsTechUnlocked) == "function"
        and type(api.DamageMultiplier) == "function") then
      upgradeProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 UPGRADE SKIPPED missing MedievalLogistics tech API")
    else
      -- Fund every cost clause (knight: food 70/wood 25/stone 25/iron 40) so the
      -- gate verdict can only be produced by the tech clause.
      local econ = GG and GG.MedievalEconomy
      if econ and type(econ.Deposit) == "function" then
        econ.Deposit(a, "food", 300)
        econ.Deposit(a, "wood", 300)
        econ.Deposit(a, "stone", 300)
        econ.Deposit(a, "iron", 300)
      end
      local sword = equipmentStockOf(a, "sword")
      upgradeProbe = {
        team = a, stage = "armed", baselineFrame = 920,
        sword = sword, baseline = nil, unlocked = nil, allowed = nil, mult = nil,
      }
      if not (type(sword) == "number" and sword > 0) then
        -- Slice 3 did not run: seed the equipment clause through the real crafting
        -- path (a blacksmith in the isolated craft lane) and give it 40 frames
        -- before the baseline sample.
        local smithDef = UnitDefNames and UnitDefNames["medieval_blacksmith"]
        if smithDef then
          local sx, sz = 5440, 6000
          local smith = Spring.CreateUnit(smithDef.id, sx, Spring.GetGroundHeight(sx, sz), sz, "south", a)
          upgradeProbe.stage = "seeding"
          upgradeProbe.baselineFrame = 960
          Spring.Echo(string.format("PHASE4 UPGRADE setup seeding-sword-blacksmith f=%d blacksmith=%s",
            frame, tostring(smith)))
        end
      end
      Spring.Echo(string.format("PHASE4 UPGRADE setup f=%d team=%d knight=%s tech=chivalry sword=%s stage=%s",
        frame, a, tostring(knightDef.id), tostring(upgradeProbe.sword), upgradeProbe.stage))
    end
  end

  -- Baseline verdict: blocked while chivalry is locked, with sword stock present so
  -- the equipment clause cannot be what refuses the unit.
  if upgradeProbe and (upgradeProbe.stage == "armed" or upgradeProbe.stage == "seeding")
      and frame >= upgradeProbe.baselineFrame then
    local sword = equipmentStockOf(upgradeProbe.team, "sword")
    upgradeProbe.sword = sword
    local blocked = recruitGateAllows(upgradeProbe.team, "medieval_knight")
    if upgradeProbe.stage == "seeding" and not (type(sword) == "number" and sword > 0)
        and frame < 1000 then
      -- The seeded blacksmith has not crafted yet; retry shortly instead of
      -- publishing a verdict whose equipment clause was never satisfied.
      upgradeProbe.baselineFrame = frame + 10
    else
      upgradeProbe.stage = "baseline"
      upgradeProbe.baseline = blocked
      upgradeProbe.unlockFrame = frame + 30
      local armed = type(sword) == "number" and sword > 0
      local pass = blocked == false and armed
      Spring.Echo(string.format("PHASE4 UPGRADE tech-gate-baseline %s f=%d knight-can-recruit=%s sword-stock=%s",
        pass and "PASS" or "FAIL", frame, tostring(blocked), tostring(sword)))
    end
  end

  -- Tech unlock verdict: research chivalry for the probe team through the public
  -- logistics API, then confirm the registry reports the tech as unlocked.
  if upgradeProbe and upgradeProbe.stage == "baseline" and frame >= upgradeProbe.unlockFrame then
    upgradeProbe.stage = "unlocked"
    upgradeProbe.gateFrame = frame + 40
    upgradeProbe.damageFrame = frame + 80
    local api = GG.MedievalLogistics
    local ok, reason = api.UnlockTech(upgradeProbe.team, "chivalry")
    local isUnlocked = api.IsTechUnlocked(upgradeProbe.team, "chivalry") == true
    upgradeProbe.unlocked = isUnlocked
    local pass = isUnlocked
    Spring.Echo(string.format("PHASE4 UPGRADE tech-unlock %s f=%d chivalry-unlocked=%s ok=%s reason=%s",
      pass and "PASS" or "FAIL", frame, tostring(isUnlocked), tostring(ok), tostring(reason)))
  end

  -- Recruit-gate verdict: the same live gate must now allow the knight. Both samples
  -- come from GG.MedievalRecruitment.CanRecruit, not from a re-derived rule.
  if upgradeProbe and upgradeProbe.stage == "unlocked" and frame >= upgradeProbe.gateFrame then
    upgradeProbe.stage = "gated"
    local allowed = recruitGateAllows(upgradeProbe.team, "medieval_knight")
    upgradeProbe.allowed = allowed
    local pass = upgradeProbe.baseline == false and allowed == true
    Spring.Echo(string.format("PHASE4 UPGRADE recruit-gate-verdict %s f=%d knight-can-recruit=%s before=%s tech=chivalry",
      pass and "PASS" or "FAIL", frame, tostring(allowed), tostring(upgradeProbe.baseline)))
  end

  -- Damage-multiplier verdict: chivalry's damage_mult entry for medieval_knight is
  -- 1.20, and the knight carries no other researched damage tech, so the folded
  -- multiplier must be exactly 1.20.
  if upgradeProbe and upgradeProbe.stage == "gated" and frame >= upgradeProbe.damageFrame then
    upgradeProbe.stage = "done"
    local api = GG.MedievalLogistics
    local mult = api.DamageMultiplier(upgradeProbe.team, "medieval_knight")
    upgradeProbe.mult = mult
    local pass = type(mult) == "number" and math.abs(mult - 1.20) < 0.001
    Spring.Echo(string.format("PHASE4 UPGRADE damage-mult-verdict %s f=%d mult=%s expect=1.20 unit=medieval_knight",
      pass and "PASS" or "FAIL", frame, tostring(mult)))
  end

  -- -------------------------------------------------------------------------
  -- Phase 4 Slice 5: transport & hauler units (frames 1060..1200).
  --
  -- Phase A (f=1060..1124) measures the cart's road-speed integration in an
  -- isolated lane (x 3500..3820 / z 4250..4950: heightmap span < 1 elmo, empty
  -- map feature map, >800 elmos from every earlier probe road). Two storage hubs
  -- are spawned there - a lumber camp (dedicated wood SOURCE) and a blacksmith
  -- (wood SINK / demand) - plus one medieval_cart.
  --
  -- Phase B (f=1128..1140) leaves the team pool in the haul policy's deficit band
  -- [HAUL_STEP, DEFICIT_THRESHOLD) = [25, 80) for wood. That IS what "fund one hub
  -- with a surplus, leave the other at a deficit" means in this total conversion:
  -- the stockpile is per-TEAM, so a hub's surplus/deficit is a role projection
  -- over that one pool (scripts/medieval_haul.lua header). The policy then assigns
  -- the live route, read back through GG.MedievalLogistics.HaulRoute.
  --
  -- Phase C (f=1140..1200) drives that route: the cart is placed at the chosen
  -- source hub, the state machine advances to "to_sink", then to the sink, where
  -- the gadget's own completeHaul writes the delivery into its per-hub ledger.
  -- -------------------------------------------------------------------------
  if frame == 1060 and spawned and not haulProbe then
    local api = GG and GG.MedievalLogistics
    local econ = GG and GG.MedievalEconomy
    local a = opposingTeams()
    local campDef = UnitDefNames and UnitDefNames["medieval_lumber_camp"]
    local smithDef = UnitDefNames and UnitDefNames["medieval_blacksmith"]
    local cartDef = UnitDefNames and UnitDefNames["medieval_cart"]
    local roadDef = FeatureDefNames and FeatureDefNames["medieval_road"]
    if not a then
      haulProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 HAUL SKIPPED no probe team")
    elseif not (campDef and smithDef and cartDef) then
      haulProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 HAUL SKIPPED missing lumber_camp/blacksmith/cart UnitDef")
    elseif not roadDef then
      haulProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 HAUL SKIPPED missing medieval_road FeatureDef")
    elseif not (api and type(api.GetSpeedState) == "function"
        and type(api.HaulRoute) == "function" and type(api.HaulSummary) == "function"
        and type(api.HaulHubStock) == "function") then
      haulProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 HAUL SKIPPED missing haul/speed API (need GetSpeedState, HaulRoute, HaulSummary, HaulHubStock)")
    elseif not (econ and type(econ.GetResource) == "function"
        and type(econ.Deposit) == "function" and type(econ.Withdraw) == "function") then
      haulProbe = { stage = "skipped" }
      Spring.Echo("PHASE4 HAUL SKIPPED missing economy API (need GetResource/Deposit/Withdraw)")
    else
      -- Roads first: AllowUnitCreation admits a supply endpoint only within
      -- BUILD_LINK_RADIUS (64) of a same-team road node.
      local roads = {}
      for rz = HAUL_ROAD_Z0, HAUL_ROAD_Z1, HAUL_ROAD_STEP do
        local ry = Spring.GetGroundHeight(HAUL_ROAD_X, rz)
        local fid = Spring.CreateFeature(roadDef.id, HAUL_ROAD_X, ry, rz, 0, a)
        roads[#roads + 1] = fid
      end
      local cy = Spring.GetGroundHeight(HAUL_SOURCE_X, HAUL_SOURCE_Z)
      local camp = Spring.CreateUnit(campDef.id, HAUL_SOURCE_X, cy, HAUL_SOURCE_Z, "south", a)
      local sy = Spring.GetGroundHeight(HAUL_SINK_X, HAUL_SINK_Z)
      local smith = Spring.CreateUnit(smithDef.id, HAUL_SINK_X, sy, HAUL_SINK_Z, "south", a)
      local ky = Spring.GetGroundHeight(HAUL_CART_X, HAUL_CART_Z)
      local cart = Spring.CreateUnit(cartDef.id, HAUL_CART_X, ky, HAUL_CART_Z, "south", a)
      -- The policy breaks ties by (hub profile rank, unit id), so the settlement
      -- camp/TC and the Slice 3 blacksmith - all spawned far earlier and therefore
      -- lower-id - would win the wood route over the two hubs just created here.
      -- Every earlier verdict is already published (the last Slice 4 sample is
      -- f=1030), so retiring those competing hubs makes this stage's route
      -- deterministic without invalidating an earlier slice. The route verdict
      -- below still asserts the exact probe endpoints, so a failed retirement
      -- shows up as a FAIL rather than silently exercising someone else's hubs.
      local retired = 0
      if type(Spring.GetAllUnits) == "function" and type(Spring.GetUnitTeam) == "function"
          and type(Spring.DestroyUnit) == "function" then
        for _, unitID in ipairs(Spring.GetAllUnits() or {}) do
          if Spring.GetUnitTeam(unitID) == a
              and unitID ~= camp and unitID ~= smith and unitID ~= cart then
            local name = unitDefNameOf(unitID)
            if name == "medieval_town_center" or name == "medieval_granary"
                or name == "medieval_lumber_camp" or name == "medieval_blacksmith"
                or name == "medieval_fletcher" then
              Spring.DestroyUnit(unitID, false, true)
              retired = retired + 1
            end
          end
        end
      end
      -- Surplus: keep the pool above DEFICIT_THRESHOLD (80) so the haul policy
      -- stays idle while Phase A measures road speed.
      local wood0 = pinStock(a, "wood", HAUL_CUSHION_WOOD)
      haulProbe = {
        team = a, camp = camp, smith = smith, cart = cart, roads = roads,
        wood0 = wood0, stage = "spawned",
      }
      Spring.Echo(string.format("PHASE4 HAUL setup f=%d team=%d cart=%s source=%s sink=%s roads=%d retired-hubs=%d wood=%s lane=(%d, %d..%d)",
        frame, a, tostring(cart), tostring(camp), tostring(smith), #roads, retired, tostring(wood0),
        HAUL_ROAD_X, HAUL_ROAD_Z0, HAUL_ROAD_Z1))
    end
  end

  -- Hold the pool above DEFICIT_THRESHOLD while the speed legs run, so the haul
  -- scan cannot assign a route mid-measurement (live gathering keeps depositing
  -- wood, so this is re-pinned every frame rather than set once).
  if haulProbe and (haulProbe.stage == "spawned" or haulProbe.stage == "offroad"
      or haulProbe.stage == "onroad") then
    pinStock(haulProbe.team, "wood", HAUL_CUSHION_WOOD)
  end

  -- Off-road leg: the cart starts (and stays) >48 elmos from every road node -
  -- the nearest is the x=3620 lane, 80 elmos east - so the Slice 6 mutator must
  -- leave it at its base speed while it runs south over open ground.
  if haulProbe and haulProbe.stage == "spawned" and frame >= 1064 then
    local cart = haulProbe.cart
    local moved = false
    if type(Spring.GiveOrderToUnit) == "function" then
      local ok = pcall(Spring.GiveOrderToUnit, cart, CMD.MOVE,
        { HAUL_OFFROAD_END_X, Spring.GetGroundHeight(HAUL_OFFROAD_END_X, HAUL_OFFROAD_END_Z), HAUL_OFFROAD_END_Z }, {})
      moved = ok
    end
    placeUnit(cart, HAUL_OFFROAD_X, HAUL_OFFROAD_Z)
    haulProbe.offroadFrame = frame + HAUL_LEG_FRAMES
    haulProbe.stage = "offroad"
    Spring.Echo(string.format("PHASE4 HAUL offroad-leg f=%d cart=%s at=(%d, %d) -> (%d, %d) moveOrder=%s",
      frame, tostring(cart), HAUL_OFFROAD_X, HAUL_OFFROAD_Z,
      HAUL_OFFROAD_END_X, HAUL_OFFROAD_END_Z, tostring(moved)))
  end

  if haulProbe and haulProbe.stage == "offroad" and frame >= haulProbe.offroadFrame then
    local cart = haulProbe.cart
    haulProbe.offroadVel = speedUnitVelocity(cart)
    local text, state = snapshotSpeedState(cart)
    haulProbe.offroadState = state
    Spring.Echo(string.format("PHASE4 HAUL offroad-state f=%d cart=%s %s vel=%.2f",
      frame, tostring(cart), text, haulProbe.offroadVel or -1))
    -- On-road leg: start exactly on a lane node and run along the lane, so the
    -- cart is within ROAD_PROXIMITY_RADIUS (48) of a node for the whole run.
    if type(Spring.GiveOrderToUnit) == "function" then
      pcall(Spring.GiveOrderToUnit, cart, CMD.MOVE,
        { HAUL_ONROAD_END_X, Spring.GetGroundHeight(HAUL_ONROAD_END_X, HAUL_ONROAD_END_Z), HAUL_ONROAD_END_Z }, {})
    end
    placeUnit(cart, HAUL_ONROAD_X, HAUL_ONROAD_Z)
    haulProbe.onroadFrame = frame + HAUL_LEG_FRAMES
    haulProbe.stage = "onroad"
    Spring.Echo(string.format("PHASE4 HAUL onroad-leg f=%d cart=%s at=(%d, %d) -> (%d, %d)",
      frame, tostring(cart), HAUL_ONROAD_X, HAUL_ONROAD_Z,
      HAUL_ONROAD_END_X, HAUL_ONROAD_END_Z))
  end

  -- Road-speed verdict: both legs are sampled exactly HAUL_LEG_FRAMES after their
  -- move order, so the velocity comparison is like-for-like. The enforced state
  -- (base/applied/source) is read through the same Slice 6 helper the earlier
  -- road-speed probe uses, and the boost must be exactly ROAD_SPEED_MULT (1.5).
  if haulProbe and haulProbe.stage == "onroad" and frame >= haulProbe.onroadFrame then
    local cart = haulProbe.cart
    local onVel = speedUnitVelocity(cart)
    local text, onState = snapshotSpeedState(cart)
    local offVel, offState = haulProbe.offroadVel, haulProbe.offroadState
    Spring.Echo(string.format("PHASE4 HAUL onroad-state f=%d cart=%s %s vel=%.2f",
      frame, tostring(cart), text, onVel or -1))
    if onState and offState and type(onVel) == "number" and type(offVel) == "number" then
      local base = offState.base or -1
      local expected = base * 1.5
      local passOnRoad = offState.onRoad == false and onState.onRoad == true
      local passApplied = speedNear(offState.applied, base) and speedNear(onState.applied, expected)
      local passVel = onVel > offVel + 0.01
      local pass = passOnRoad and passApplied and passVel
      Spring.Echo(string.format("PHASE4 HAUL road-speed-verdict %s f=%d onroad=%.2f offroad=%.2f (onRoad=%s offRoad=%s applied=%.2f expect=%.2f base=%.2f source=%s state-ok=%s applied-ok=%s)",
        pass and "PASS" or "FAIL", frame, onVel, offVel, tostring(onState.onRoad), tostring(offState.onRoad),
        onState.applied or -1, expected, base, tostring(onState.source), tostring(passOnRoad), tostring(passApplied)))
      haulProbe.speedPass = pass
    else
      Spring.Echo(string.format("PHASE4 HAUL road-speed-verdict FAIL f=%d onroad=%s offroad=%s (state-ok=false onState=%s offState=%s)",
        frame, tostring(onVel), tostring(offVel), tostring(onState ~= nil), tostring(offState ~= nil)))
      haulProbe.speedPass = false
    end
    haulProbe.deficitFrame = frame + 4
    haulProbe.stage = "speed-done"
  end

  -- Deficit trigger: wood enters the band [25, 80). Pinned every frame because
  -- the shared pool keeps moving under gather/production, and the haul scan runs
  -- at frame%30==0 BEFORE this gadget (layer 4 < layer 50), so the value pinned
  -- on the previous frame is the one the scan reads.
  if haulProbe and haulProbe.stage == "speed-done" and frame >= haulProbe.deficitFrame then
    pinStock(haulProbe.team, "wood", HAUL_WOOD_TARGET)
    haulProbe.stage = "deficit"
    haulProbe.deficitSeen = frame
    Spring.Echo(string.format("PHASE4 HAUL deficit-trigger f=%d team=%d wood=%s target=%d band=[%d, %d)",
      frame, haulProbe.team, tostring(pinStock(haulProbe.team, "wood", HAUL_WOOD_TARGET)),
      HAUL_WOOD_TARGET, 25, 80))
  end

  if haulProbe and haulProbe.stage == "deficit" then
    local woodNow = pinStock(haulProbe.team, "wood", HAUL_WOOD_TARGET)
    local api = GG.MedievalLogistics
    if frame % 30 == 0 then
      local s = api.HaulSummary(haulProbe.team)
      Spring.Echo(string.format("PHASE4 HAUL diag f=%d wood=%s carts=%s hubs=%s assigned=%s delivered=%s",
        frame, tostring(woodNow), tostring(s and s.carts), tostring(s and s.hubs),
        tostring(s and s.routesAssigned), tostring(s and s.delivered)))
    end
    local route = api.HaulRoute(haulProbe.team, haulProbe.cart)
    if route then
      -- Freeze further assignments (pool back above the threshold) while the
      -- in-flight job finishes, so exactly one delivery lands in the ledger.
      pinStock(haulProbe.team, "wood", HAUL_CUSHION_WOOD)
      haulProbe.route = route
      haulProbe.before = haulHubStock(haulProbe.team, route.to, route.resource) or 0
      local fromName = unitDefNameOf(route.from)
      local toName = unitDefNameOf(route.to)
      -- Assert both the exact probe endpoints (so a stray hub cannot be what got
      -- exercised) and the ROLES the policy must produce: the source is the
      -- dedicated wood dropoff, the sink the wood-demanding blacksmith.
      local passFrom = route.from == haulProbe.camp and fromName == "medieval_lumber_camp"
      local passTo = route.to == haulProbe.smith and toName == "medieval_blacksmith"
      local passKind = route.resource == "wood"
      local passAmount = route.amount == 25
      local passDistinct = route.from ~= route.to
      local pass = passFrom and passTo and passKind and passAmount and passDistinct
      Spring.Echo(string.format("PHASE4 HAUL route-verdict %s f=%d from=%s to=%s kind=%s amount=%s (fromRole=%s toRole=%s expect-from=%s expect-to=%s)",
        pass and "PASS" or "FAIL", frame, tostring(route.from), tostring(route.to),
        tostring(route.resource), tostring(route.amount), tostring(fromName), tostring(toName),
        tostring(haulProbe.camp), tostring(haulProbe.smith)))
      -- Park the cart just inside the source hub's 64-elmo arrival radius but
      -- clear of its footprint, so the state machine advances without the engine
      -- resolving a collision against the building.
      local fx, _, fz = Spring.GetUnitPosition(route.from)
      placeUnit(haulProbe.cart, fx + HAUL_HUB_OFFSET, fz)
      haulProbe.sinkFrame = frame + 30
      haulProbe.deadlineFrame = frame + 120
      haulProbe.stage = "to-source"
    elseif frame >= haulProbe.deficitSeen + 60 then
      Spring.Echo(string.format("PHASE4 HAUL route-verdict FAIL f=%d from=? to=? kind=? amount=0 (no route assigned within 60 frames of the deficit trigger)",
        frame))
      haulProbe.stage = "done"
    end
  end

  -- Advance the cart to the sink hub so the gadget's own arrival check fires.
  if haulProbe and haulProbe.stage == "to-source" and frame >= haulProbe.sinkFrame then
    local route = haulProbe.route
    local x, _, z = Spring.GetUnitPosition(route.to)
    if x and z then
      placeUnit(haulProbe.cart, x + HAUL_HUB_OFFSET, z)
      haulProbe.stage = "to-sink"
      Spring.Echo(string.format("PHASE4 HAUL to-sink f=%d cart=%s sink=%s at=(%d, %d)",
        frame, tostring(haulProbe.cart), tostring(route.to), x + HAUL_HUB_OFFSET, z))
    else
      Spring.Echo(string.format("PHASE4 HAUL to-sink SKIPPED f=%d sink=%s (no position; hub gone)",
        frame, tostring(route.to)))
      haulProbe.stage = "to-sink"
    end
  end

  -- Delivery verdict: completeHaul writes hubDelivered[team][route.to]
  -- [route.resource] += route.amount, so the sink hub's stock must rise by
  -- exactly the transferred amount. Polled rather than sampled once because the
  -- gadget's arrival check runs on its own 30-frame scan cadence, so the exact
  -- completion frame depends on where the route landed in that cadence.
  if haulProbe and haulProbe.stage == "to-sink" then
    local route = haulProbe.route
    local before = haulProbe.before or 0
    local after = haulHubStock(haulProbe.team, route.to, route.resource)
    local summary = GG.MedievalLogistics.HaulSummary(haulProbe.team)
    local delivered = summary and summary.delivered or 0
    local settled = type(after) == "number" and after == before + route.amount and delivered >= 1
    if settled or frame >= haulProbe.deadlineFrame then
      local pass = settled
      Spring.Echo(string.format("PHASE4 HAUL delivery-verdict %s f=%d before=%s after=%s (hub=%s kind=%s amount=%s delivered=%s)",
        pass and "PASS" or "FAIL", frame, tostring(before), tostring(after),
        tostring(route.to), tostring(route.resource), tostring(route.amount), tostring(delivered)))
      haulProbe.stage = "done"
    end
  end

  if frame % 90 == 0 and spawned then
    local a, b = opposingTeams()
    if a then
      local food = Spring.GetGameRulesParam(string.format("team_%d_food", a)) or "?"
      local wood = Spring.GetGameRulesParam(string.format("team_%d_wood", a)) or "?"
      local pop = Spring.GetGameRulesParam(string.format("team_%d_population", a)) or "?"
      local cap = Spring.GetGameRulesParam(string.format("team_%d_pop_cap", a)) or "?"
      Spring.Echo(string.format("PHASE2 PROBE STATS f=%d team=%d Food=%s Wood=%s Pop=%s Cap=%s",
        frame, a, tostring(food), tostring(wood), tostring(pop), tostring(cap)))
    end
  end
end