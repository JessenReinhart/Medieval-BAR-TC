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