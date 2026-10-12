-- Synced medieval garrison: engine-transport shelter for Town Centers and
-- Towers. Units loaded into a shelter leave the map (the engine transport
-- primitive already stops them being hit directly), and this gadget adds the
-- slow deterministic recovery the design calls for.
--
-- Scope boundary (docs/phase-5.md, architectural goal 2): this gadget does NOT
-- implement UnitPreDamaged and never intercepts damage. The per-garrison
-- defensive-output multiplier is only *computed* here (via
-- scripts/medieval_garrison.lua) and exposed through GG.MedievalGarrison for
-- Slice 5's single authoritative UnitPreDamaged hook to apply. Garrison
-- scaling therefore can never double-apply.
--
-- All "how much" math lives in scripts/medieval_garrison.lua; this gadget owns
-- modoption gating, occupancy tracking, the GG surface and every engine call.

function gadget:GetInfo()
  return {
    name = "Medieval Garrison",
    desc = "Town Center / Tower garrison shelter: occupancy tracking, slow healing and the defensive-output multiplier published for the Slice 5 damage pipeline",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 5,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local garrison = VFS.Include("scripts/medieval_garrison.lua")

-- The `medievalgarrison` modoption gates the Slice 4 probe
-- (gadget_phase5_slice4_garrison_probe.lua), per the modoption table in
-- docs/phase-5.md. The shelter itself is core gameplay and therefore always
-- active; when the option is set this gadget also announces itself so a probe
-- log shows both halves of the slice ran.
local function modOptionOn(key)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[key]
  return v == 1 or v == true or v == "1" or v == "true"
end

local GARRISON_ENABLED = modOptionOn("medievalgarrison")

-- Shelter def names -> transport capacity, straight from the pure policy module
-- so the gadget and the tests cannot drift from units/*.lua transportCapacity.
local SHELTER_CAP = garrison.GARRISON_CAP

-- Synced state ----------------------------------------------------------------
-- occupancy[transportID] = { team = teamID, count = n, units = { [unitID] = true } }
-- carriedBy[unitID] = transportID (reverse index for UnitDestroyed)
local occupancy = {}
local carriedBy = {}

local function initShelter(transportID, teamID)
  if not occupancy[transportID] then
    occupancy[transportID] = { team = teamID, count = 0, units = {} }
  end
  return occupancy[transportID]
end

local function occupancyOf(transportID)
  local occ = transportID and occupancy[transportID]
  return occ and occ.count or 0
end

local function capacityOf(transportID)
  if not transportID then return 0 end
  local defID = Spring.GetUnitDefID and Spring.GetUnitDefID(transportID)
  local def = defID and UnitDefs and UnitDefs[defID]
  local name = def and def.name
  if not name then return 0 end
  return SHELTER_CAP[name] or 0
end

-- Best effort: a rules param is a read-out, never a sim input, so a missing
-- SetGameRulesParam on an older build must not break occupancy tracking.
local function syncParams(teamID)
  if not (Spring and Spring.SetGameRulesParam and teamID) then return end
  local total, bonus = 0, 1.0
  for _, occ in pairs(occupancy) do
    if occ.team == teamID then
      total = total + occ.count
      local b = garrison.garrison_damage_multiplier(occ.count)
      if b > bonus then bonus = b end
    end
  end
  Spring.SetGameRulesParam(string.format("team_%d_garrison", teamID), total)
  Spring.SetGameRulesParam(string.format("team_%d_garrison_bonus", teamID), bonus)
end

-- Is a hostile unit standing inside the shelter's siege radius? A besieged
-- shelter stops mending its occupants (garrison.shelterState handles the gate).
local function isEnemyNear(transportID, teamID)
  if not (Spring and Spring.GetUnitPosition and Spring.GetUnitsInCylinder) then
    return false
  end
  local x, _, z = Spring.GetUnitPosition(transportID)
  if not x then return false end
  local near = Spring.GetUnitsInCylinder(x, z, garrison.BESIEGE_RADIUS) or {}
  for _, uid in ipairs(near) do
    local otherTeam = Spring.GetUnitTeam and Spring.GetUnitTeam(uid)
    if otherTeam and otherTeam ~= teamID then
      local allied = Spring.AreTeamsAllied and Spring.AreTeamsAllied(otherTeam, teamID)
      if not allied then return true end
    end
  end
  return false
end

local function shelterStateOf(transportID)
  local occ = transportID and occupancy[transportID]
  if not occ then
    return garrison.shelterState(0, 0, false)
  end
  local enemyNear = isEnemyNear(transportID, occ.team)
  return garrison.shelterState(occ.count, capacityOf(transportID), enemyNear)
end

-- Registration -----------------------------------------------------------------

local function registerOccupant(unitID, transportID, unitTeam)
  if not (unitID and transportID) then return false end
  if occupancy[transportID] and occupancy[transportID].units[unitID] then return false end
  local occ = initShelter(transportID, unitTeam)
  occ.units[unitID] = true
  occ.count = occ.count + 1
  carriedBy[unitID] = transportID
  syncParams(occ.team)
  return true
end

local function unregisterOccupant(unitID)
  local transportID = unitID and carriedBy[unitID]
  if not transportID then return false end
  carriedBy[unitID] = nil
  local occ = occupancy[transportID]
  if occ then
    occ.units[unitID] = nil
    if occ.count > 0 then occ.count = occ.count - 1 end
    syncParams(occ.team)
  end
  return true
end

-- Healing ----------------------------------------------------------------------

local function healTick()
  if not (Spring and Spring.GetUnitHealth and Spring.SetUnitHealth) then return end
  for transportID, occ in pairs(occupancy) do
    if occ.count > 0 then
      local state = shelterStateOf(transportID)
      if state.heal > 0 then
        for unitID in pairs(occ.units) do
          -- Called directly (never through an `and` guard, which would truncate
          -- the two-value return to one).
          local hp, maxHp = Spring.GetUnitHealth(unitID)
          if hp and maxHp and hp > 0 and hp < maxHp then
            local newHp = hp + state.heal
            if newHp > maxHp then newHp = maxHp end
            Spring.SetUnitHealth(unitID, newHp)
          end
        end
      end
    end
  end
end

-- Callins ----------------------------------------------------------------------

function gadget:Initialize()
  GG = GG or {}
  GG.MedievalGarrison = GG.MedievalGarrison or {}

  if GARRISON_ENABLED and Spring.Echo then
    Spring.Echo("PHASE5 GARRISON gadget active (medievalgarrison=1)")
  end

  -- Additive export: never reassign the whole table, a sibling slice may have
  -- already contributed fields.
  GG.MedievalGarrison.Occupy = function(transportID, unitID, unitTeam)
    return registerOccupant(unitID, transportID, unitTeam)
  end

  GG.MedievalGarrison.Eject = function(transportID)
    local occ = transportID and occupancy[transportID]
    local count = occ and occ.count or 0
    if count > 0 and Spring.GiveOrderToUnit and CMD and CMD.UNLOAD_UNITS then
      Spring.GiveOrderToUnit(transportID, CMD.UNLOAD_UNITS, {}, 0)
    end
    return count
  end

  GG.MedievalGarrison.GetOccupancy = function(transportID)
    return occupancyOf(transportID)
  end

  GG.MedievalGarrison.GetCapacity = function(transportID)
    return capacityOf(transportID)
  end

  GG.MedievalGarrison.GetDamageMult = function(transportID)
    return garrison.garrison_damage_multiplier(occupancyOf(transportID))
  end

  GG.MedievalGarrison.GetShelterState = function(transportID)
    return shelterStateOf(transportID)
  end

  GG.MedievalGarrison.IsGarrisonable = function(unitDef)
    return garrison.garrisonAllowed(unitDef)
  end

  GG.MedievalGarrison.SHELTER_CAP = SHELTER_CAP
  GG.MedievalGarrison.HEAL_TICK_FRAMES = garrison.HEAL_TICK_FRAMES
end

function gadget:UnitLoaded(unitID, unitDefID, unitTeam, transportID, transportTeam)
  if not transportID then return end
  -- Only shelters track occupancy; every other transport is somebody else's.
  if capacityOf(transportID) <= 0 then return end
  registerOccupant(unitID, transportID, transportTeam or unitTeam)
end

function gadget:UnitUnloaded(unitID, unitDefID, unitTeam, transportID, transportTeam)
  unregisterOccupant(unitID)
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  -- A destroyed shelter drops its whole ledger; a destroyed occupant is removed
  -- from whichever shelter held it.
  if occupancy[unitID] then
    local team = occupancy[unitID].team
    for unit in pairs(occupancy[unitID].units) do
      carriedBy[unit] = nil
    end
    occupancy[unitID] = nil
    syncParams(team)
  end
  unregisterOccupant(unitID)
end

function gadget:TeamDied(teamID)
  for transportID, occ in pairs(occupancy) do
    if occ.team == teamID then
      for unit in pairs(occ.units) do
        carriedBy[unit] = nil
      end
      occupancy[transportID] = nil
    end
  end
end

function gadget:GameFrame(frame)
  if frame % garrison.HEAL_TICK_FRAMES == 0 then
    healTick()
  end
end
