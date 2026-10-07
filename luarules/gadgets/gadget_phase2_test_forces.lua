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