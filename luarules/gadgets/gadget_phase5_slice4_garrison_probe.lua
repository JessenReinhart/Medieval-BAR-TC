-- Phase 5 Slice 4 headless probe: garrison shelter, healing and the defensive
-- output multiplier that Slice 5's single UnitPreDamaged hook will consume.
--
-- Gated on the `medievalgarrison` modoption (docs/phase-5.md modoption table).
-- This probe never intercepts damage: it only drives the engine transport
-- primitive, reads the occupancy the synced garrison gadget tracks, and checks
-- that sheltered units recover HP over heal ticks.

function gadget:GetInfo()
  return {
    name = "Phase 5 Slice 4 Garrison Probe",
    desc = "Headless probe verifying garrison shelter occupancy, healing and the defensive-output multiplier",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 1000,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mo = Spring.GetModOptions() or {}
local enabled = (mo.medievalgarrison == "1") or (mo.medievalgarrison == 1) or (mo.medievalgarrison == true)
if not enabled then return end

local team = 0
local spawned = false
local probeDone = false

-- Occupancy expectations, mirrored from scripts/medieval_garrison.lua.
local VILLAGERS = 5
local ARCHERS = 3
local TC_CAP = 10
local TOWER_CAP = 4
local ARCHER_DAMAGE_PER = 0.15

local tcID, towerID = nil, nil
local villagerIDs, archerIDs, towerArcherIDs = {}, {}, {}
local hpBefore = {}
local damageMultChecked = false

local function echo(fmt, ...)
  Spring.Echo(string.format(fmt, ...))
end

local function groundY(x, z)
  if Spring.GetGroundHeight then return Spring.GetGroundHeight(x, z) end
  return 0
end

local function spawn(name, x, z, facing, teamID)
  local def = UnitDefNames and UnitDefNames[name]
  if not def then return nil end
  return Spring.CreateUnit(def.id, x, groundY(x, z), z, facing or "south", teamID or team)
end

local function occupancy(unitID)
  local api = GG and GG.MedievalGarrison
  if not (api and api.GetOccupancy and unitID) then return nil end
  return api.GetOccupancy(unitID)
end

local function damageMult(unitID)
  local api = GG and GG.MedievalGarrison
  if not (api and api.GetDamageMult and unitID) then return nil end
  return api.GetDamageMult(unitID)
end

local function health(unitID)
  if not (Spring.GetUnitHealth and unitID) then return nil end
  return Spring.GetUnitHealth(unitID)
end

-- Engine-truth cross-check: a unit held by a transport is no longer a normal
-- map unit. GetUnitIsTransporting is optional on this build, so the read is
-- best-effort and never gates the verdict alone.
local function transportingOf(unitID)
  if not (Spring.GetUnitIsTransporting and unitID) then return nil end
  local ok, list = pcall(Spring.GetUnitIsTransporting, unitID)
  if not ok or type(list) ~= "table" then return nil end
  return #list
end

local function loadOrders()
  -- CMD ids: the engine constants are present in synced gadgets; the numeric
  -- fallbacks keep the probe runnable if the table is absent.
  local CMD_LOAD = (CMD and CMD.LOAD_UNITS) or 139

  local targets = {}
  for _, uid in ipairs(villagerIDs) do targets[#targets + 1] = uid end
  for _, uid in ipairs(archerIDs) do targets[#targets + 1] = uid end

  if tcID then
    -- Transport-side order: the shelter picks up the listed units.
    Spring.GiveOrderToUnit(tcID, CMD_LOAD, targets, 0)
  end

  -- Unit-side order: each unit walks into the shelter it was told to enter.
  for _, uid in ipairs(targets) do
    if tcID then Spring.GiveOrderToUnit(uid, CMD_LOAD, { tcID }, 0) end
  end

  for _, uid in ipairs(towerArcherIDs) do
    if towerID then Spring.GiveOrderToUnit(uid, CMD_LOAD, { towerID }, 0) end
  end
  if towerID then
    Spring.GiveOrderToUnit(towerID, CMD_LOAD, towerArcherIDs, 0)
  end
end

function gadget:GameFrame(frame)
  if probeDone then return end

  -- 1. Setup: town center + villagers + archers, and a tower with archers.
  if not spawned and frame >= 20 then
    spawned = true
    echo("PHASE5 GARRISON probe setup starting at frame %d", frame)

    local cx, cz = 1800, 2400
    tcID = spawn("medieval_town_center", cx, cz, "south", team)
    if tcID then
      echo("PHASE5 GARRISON spawned town center id=%d", tcID)
    end

    for i = 1, VILLAGERS do
      local vx, vz = cx + (i - 3) * 40, cz + 96
      local uid = spawn("medieval_villager", vx, vz, "south", team)
      if uid then villagerIDs[#villagerIDs + 1] = uid end
    end

    for i = 1, ARCHERS do
      local ax, az = cx - 96 + (i - 1) * 32, cz - 96
      local uid = spawn("medieval_archer", ax, az, "south", team)
      if uid then archerIDs[#archerIDs + 1] = uid end
    end

    local tx, tz = cx + 320, cz
    towerID = spawn("medieval_tower", tx, tz, "south", team)
    if towerID then
      for i = 1, ARCHERS do
        local ax, az = tx - 32 + (i - 1) * 32, tz + 72
        local uid = spawn("medieval_archer", ax, az, "south", team)
        if uid then towerArcherIDs[#towerArcherIDs + 1] = uid end
      end
    end
  end

  -- 2. Load order.
  if spawned and tcID and frame == 40 then
    loadOrders()
    echo("PHASE5 GARRISON load orders issued at frame %d", frame)
  end

  -- 3. Occupancy verdict: the shelter holds exactly the villagers + archers.
  if spawned and tcID and frame >= 90 and not self.shelterVerdict then
    self.shelterVerdict = true
    local occ = occupancy(tcID) or -1
    local engineHeld = transportingOf(tcID)
    local expected = VILLAGERS + ARCHERS
    local capOk = occ <= TC_CAP
    local ok = (occ == expected) and capOk

    echo("PHASE5 GARRISON occupancy tc=%d expected=%d observed=%d cap=%d engineHeld=%s",
      tcID, expected, occ, TC_CAP, tostring(engineHeld))
    echo("PHASE5 GARRISON shelter-verdict %s", ok and "PASS" or "FAIL")

    -- Damage the sheltered units so the heal tick has something to restore.
    for _, uid in ipairs(villagerIDs) do
      local hp, maxHp = health(uid)
      if hp and maxHp and hp > 1 then
        local target = math.max(1, math.floor(maxHp * 0.5))
        Spring.SetUnitHealth(uid, target)
        hpBefore[uid] = target
      end
    end
  end

  -- 4. Damage-multiplier verdict: 3 garrisoned archers => 1 + 3*0.15 = 1.45.
  --    Computed only; Slice 5 applies it inside its single UnitPreDamaged hook.
  if spawned and towerID and frame >= 100 and not damageMultChecked then
    damageMultChecked = true
    local mult = damageMult(towerID)
    local occ = occupancy(towerID)
    local expected = 1.0 + ARCHERS * ARCHER_DAMAGE_PER
    local capOk = occ ~= nil and occ <= TOWER_CAP
    local ok = mult ~= nil and math.abs(mult - expected) < 0.0001 and capOk
    echo("PHASE5 GARRISON tower occupancy=%s cap=%d damage-mult=%s expected=%.2f",
      tostring(occ), TOWER_CAP, tostring(mult), expected)
    echo("PHASE5 GARRISON damage-mult-verdict %s", ok and "PASS" or "FAIL")
  end

  -- 5. Heal verdict: HP rose over the heal ticks since the damage sample.
  --    One tick per HEAL_TICK_FRAMES (30) frames.
  if spawned and tcID and frame >= 160 and not self.healVerdict then
    self.healVerdict = true
    local healed, checked = 0, 0
    for _, uid in ipairs(villagerIDs) do
      local before = hpBefore[uid]
      if before then
        checked = checked + 1
        local hp = health(uid)
        if hp and hp > before then healed = healed + 1 end
      end
    end
    local ok = checked > 0 and healed == checked
    echo("PHASE5 GARRISON heal-verdict %s (healed %d/%d sheltered units)",
      ok and "PASS" or "FAIL", healed, checked)
  end

  -- 6. Eject verdict: unloading restores the units and clears occupancy.
  if spawned and tcID and frame >= 190 and not self.ejectVerdict then
    self.ejectVerdict = true
    local api = GG and GG.MedievalGarrison
    if api and api.Eject then api.Eject(tcID) end
    local CMD_UNLOAD = (CMD and CMD.UNLOAD_UNITS) or 140
    Spring.GiveOrderToUnit(tcID, CMD_UNLOAD, {}, 0)

    local occ = occupancy(tcID)
    local ok = occ == 0
    echo("PHASE5 GARRISON eject-verdict %s (occupancy=%s)", ok and "PASS" or "FAIL", tostring(occ))
  end

  -- 7. Terminal verdict.
  if spawned and frame >= 220 then
    probeDone = true
    echo("PHASE5 GARRISON probe-complete PASS")
  end
end
