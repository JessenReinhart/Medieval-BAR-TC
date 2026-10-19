-- Phase 7 headless probe: baked death-clip wiring.
--
-- Spawns one unit per articulated unitdef, kills each one, and lets the LUS
-- `Killed` call-in run. Every articulated script emits its own evidence line
-- from that call-in:
--
--   PHASE7 DEATH unit=<id> clip=death baked=1 driven=<pieces>
--   PHASE7 DEATH unit=<id> clip=procedural baked=0
--
-- `baked=1 driven>0` proves the scripts/animdata `death` clip reached the
-- engine's Turn/Move primitives for real pieces; `baked=0` means the script
-- fell back to the procedural tumble (no bake bundle or no player module).
--
-- This gadget only spawns and destroys; it never asserts. The runner
-- (tools/launch/run_phase7_death_probe.py) harvests both its own
-- PHASE7 DEATH PROBE lines and the LUS PHASE7 DEATH lines from infolog.txt.
--
-- Gated on `medievalanimprobe` so a normal match is untouched.

function gadget:GetInfo()
  return {
    name = "Phase 7 Death Animation Probe",
    desc = "Spawns and kills one unit per articulated LUS to verify the baked death clip in headless runs",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 10,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local options = Spring.GetModOptions() or {}
local enabled = options.medievalanimprobe == true
  or options.medievalanimprobe == 1
  or options.medievalanimprobe == "1"
  or options.medievalanimprobe == "true"
if not enabled then return end

-- Frames (30 fps). The death clip is 36 frames (~1.2 s), so the report frame
-- leaves room for the full one-shot plus the engine's death-script wait.
local SPAWN_FRAME = 20
local KILL_FRAME = 40
local KILLS_PER_GROUP = 3
local KILL_GROUP_GAP = 40
local REPORT_FRAME = 260

-- Flat lane reused by the Phase 4 haul probe (heightmap ~90 elmos, no
-- features, documented flat range x 3500..3820 / z 4350..4950). Units are laid
-- out in rows of five so every spawn stays inside that range.
local LANE_X, LANE_Z = 3500, 4500
local LANE_STEP = 60
local ROW_WIDTH = 5

-- Every unit whose unitdef points at an articulated LUS (and therefore at a
-- bone-split 0 A.D. mesh). Several defs share a script and a bake:
--   medieval_infantry.lua  <- infantry, spearman, men_at_arms, king
--   medieval_archer.lua    <- archer, crossbow
--   medieval_villager.lua  <- villager
--   medieval_cavalry.lua   <- cavalry, knight
local UNITS = {
  "medieval_infantry",
  "medieval_spearman",
  "medieval_men_at_arms",
  "medieval_king",
  "medieval_archer",
  "medieval_crossbow",
  "medieval_villager",
  "medieval_cavalry",
  "medieval_knight",
}

local ids = {}
local spawnedCount = 0

local function spawnOne(index, defName)
  local def = UnitDefNames and UnitDefNames[defName]
  if not def then
    Spring.Echo("PHASE7 DEATH PROBE missing-def def=" .. defName)
    return
  end
  local column = (index - 1) % ROW_WIDTH
  local row = math.floor((index - 1) / ROW_WIDTH)
  local x = LANE_X + column * LANE_STEP
  local z = LANE_Z + row * LANE_STEP
  local y = Spring.GetGroundHeight(x, z)
  local ok, unitID = pcall(Spring.CreateUnit, def.id, x, y, z, "south", 0)
  if not ok or not unitID then
    Spring.Echo(string.format("PHASE7 DEATH PROBE spawn-failed def=%s ok=%s",
      defName, tostring(ok)))
    return
  end
  ids[index] = unitID
  spawnedCount = spawnedCount + 1
  Spring.Echo(string.format("PHASE7 DEATH PROBE spawned def=%s unit=%s at=(%d,%d)",
    defName, tostring(unitID), x, z))
end

-- The recruitment gadget charges each unit's discrete cost on UnitFinished
-- and tears the unit down if the team cannot pay, so an unfunded probe would
-- silently lose its later spawns. Fund team 0 before the first spawn.
local function fundTeam(teamID)
  local economy = GG and GG.MedievalEconomy
  if not (economy and economy.Deposit) then return end
  for _, resource in ipairs({ "food", "wood", "stone", "iron" }) do
    economy.Deposit(teamID, resource, 100000)
  end
end

function gadget:GameFrame(frame)
  if frame == SPAWN_FRAME then
    fundTeam(0)
    for i = 1, #UNITS do
      spawnOne(i, UNITS[i])
    end
    Spring.Echo(string.format("PHASE7 DEATH PROBE spawn-summary requested=%d spawned=%d",
      #UNITS, spawnedCount))
  elseif frame >= KILL_FRAME
      and (frame - KILL_FRAME) % KILL_GROUP_GAP == 0
      and frame < KILL_FRAME + KILL_GROUP_GAP * math.ceil(#UNITS / KILLS_PER_GROUP) then
    -- Kill in groups of three: one death clip is ~36 frames, so spacing the
    -- groups keeps each `Killed` evidence line attributable to its own units
    -- and stops nine death threads from interleaving their logs.
    local group = math.floor((frame - KILL_FRAME) / KILL_GROUP_GAP)
    local first = group * KILLS_PER_GROUP + 1
    local last = math.min(first + KILLS_PER_GROUP - 1, #UNITS)
    for i = first, last do
      local unitID = ids[i]
      if unitID then
        -- Lethal damage, not DestroyUnit: a plain destroy removes the unit
        -- without running the LUS `Killed` call-in, so the death clip would
        -- never be exercised. AddUnitDamage goes through the normal death
        -- pipeline (Killed + SetDeathScriptFinished).
        local valid = Spring.ValidUnitID(unitID)
        local health = valid and select(1, Spring.GetUnitHealth(unitID)) or "-"
        local ok = pcall(Spring.AddUnitDamage, unitID, 1000000, 0, -1, 0)
        Spring.Echo(string.format("PHASE7 DEATH PROBE kill def=%s unit=%s ok=%s pre-valid=%s pre-health=%s",
          UNITS[i], tostring(unitID), tostring(ok), tostring(valid), tostring(health)))
      end
    end
  elseif frame == REPORT_FRAME then
    for i = 1, #UNITS do
      local unitID = ids[i]
      local valid = unitID and Spring.ValidUnitID(unitID) or false
      local health = valid and select(1, Spring.GetUnitHealth(unitID)) or "-"
      Spring.Echo(string.format("PHASE7 DEATH PROBE state def=%s unit=%s valid=%s health=%s",
        UNITS[i], tostring(unitID), tostring(valid), tostring(health)))
    end
    Spring.Echo(string.format("PHASE7 DEATH PROBE complete requested=%d spawned=%d",
      #UNITS, spawnedCount))
  end
end
