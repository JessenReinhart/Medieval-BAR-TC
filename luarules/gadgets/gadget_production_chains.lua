function gadget:GetInfo()
  return {
    name = "Medieval Production Chains",
    desc = "Blacksmith/Fletcher crafting: consume team iron+wood to build equipment stock",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local DEBUG_LOG = true

-- Crafting cadence: one transaction attempt per crafter per ~1 second (30 frames).
local CRAFT_INTERVAL = 30

-- Per-kind recipe + producing unit. Costs are deliberately small so a single
-- blacksmith/fletcher can sustain a slow trickle of equipment from a stocked
-- team economy. Kind names match the `crafting` customparam on the unitdefs.
local CRAFT_KINDS = {
  bow = {
    unitName = "medieval_fletcher",
    cost = { wood = 5, iron = 1 },
  },
  sword = {
    unitName = "medieval_blacksmith",
    cost = { iron = 5, wood = 2 },
  },
}

-- Fixed iteration order (not pairs) so craft order and echo output are
-- deterministic across runs and engine hash orders.
local KIND_ORDER = { "bow", "sword" }

-- Synced state:
-- crafterUnits[teamID][kind][unitID] = true
-- equipmentStock[teamID][kind] = count (alias of GG.MedievalLogistics.equipmentStock)
local crafterUnits = {}
local equipmentStock = {}

local function echo(fmt, ...)
  if DEBUG_LOG and Spring and Spring.Echo then
    Spring.Echo(string.format(fmt, ...))
  end
end

local function ensureApi()
  GG = GG or {}
  GG.MedievalLogistics = GG.MedievalLogistics or {}
  GG.MedievalLogistics.equipmentStock = GG.MedievalLogistics.equipmentStock or {}
  equipmentStock = GG.MedievalLogistics.equipmentStock
  GG.MedievalLogistics.CraftingStock = function(teamID, kind)
    local stock = equipmentStock[teamID]
    if not stock then return kind and 0 or {} end
    if kind == nil then return stock end
    return stock[kind] or 0
  end
  return GG.MedievalLogistics
end

local function initTeam(teamID)
  crafterUnits[teamID] = crafterUnits[teamID] or {}
  equipmentStock[teamID] = equipmentStock[teamID] or {}
end

-- Resolve the crafted kind for a unitdef, preferring the runtime customparam and
-- falling back to the unitdef name so stub harnesses without customParams work.
local function kindForDef(unitDefID)
  local def = UnitDefs and UnitDefs[unitDefID]
  if def then
    local cp = def.customParams or def.customparams
    if cp and cp.crafting then return cp.crafting end
    for kind, spec in pairs(CRAFT_KINDS) do
      if def.name == spec.unitName then return kind end
    end
  end
  return nil
end

local function addCrafter(unitID, unitDefID, teamID)
  local kind = kindForDef(unitDefID)
  if not kind or not CRAFT_KINDS[kind] then return end
  initTeam(teamID)
  crafterUnits[teamID][kind] = crafterUnits[teamID][kind] or {}
  crafterUnits[teamID][kind][unitID] = true
end

local function removeCrafter(unitID)
  for teamID, kinds in pairs(crafterUnits) do
    for kind, units in pairs(kinds) do
      if units[unitID] then
        units[unitID] = nil
        return teamID, kind
      end
    end
  end
  return nil, nil
end

local function bumpStock(teamID, kind)
  initTeam(teamID)
  local stock = equipmentStock[teamID]
  stock[kind] = (stock[kind] or 0) + 1
  return stock[kind]
end

-- One craft attempt per producing unit per tick. Transactions go through
-- GG.MedievalEconomy so a concurrent spend cannot overdraw the stockpile; the
-- first unaffordable crafter stops the kind for this tick (deterministic).
local function craftKind(teamID, kind)
  local units = crafterUnits[teamID] and crafterUnits[teamID][kind]
  if not units then return end

  local ids = {}
  for unitID in pairs(units) do ids[#ids + 1] = unitID end
  if #ids == 0 then return end
  table.sort(ids)

  local economy = GG and GG.MedievalEconomy
  if not economy or not economy.Transact then return end

  local cost = CRAFT_KINDS[kind].cost
  for _, unitID in ipairs(ids) do
    if not economy.Transact(teamID, cost) then return end
    local stock = bumpStock(teamID, kind)
    echo("PHASE4 CRAFT kind=%s team=%d stock=%d", kind, teamID, stock)
  end
end

function gadget:Initialize()
  crafterUnits = {}
  ensureApi()
  equipmentStock = GG.MedievalLogistics.equipmentStock

  for _, teamID in ipairs(Spring.GetTeamList and Spring.GetTeamList() or {}) do
    initTeam(teamID)
  end
  for _, unitID in ipairs(Spring.GetAllUnits and Spring.GetAllUnits() or {}) do
    local unitDefID = Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
    local teamID = Spring.GetUnitTeam and Spring.GetUnitTeam(unitID)
    if unitDefID and teamID then addCrafter(unitID, unitDefID, teamID) end
  end
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  addCrafter(unitID, unitDefID, teamID)
end

function gadget:UnitDestroyed(unitID)
  removeCrafter(unitID)
end

function gadget:UnitTaken(unitID)
  removeCrafter(unitID)
end

function gadget:UnitGiven(unitID, unitDefID, newTeam)
  addCrafter(unitID, unitDefID, newTeam)
end

function gadget:TeamDied(teamID)
  crafterUnits[teamID] = nil
  equipmentStock[teamID] = nil
end

function gadget:GameFrame(frame)
  if frame % CRAFT_INTERVAL ~= 0 then return end
  ensureApi()
  local teams = Spring.GetTeamList and Spring.GetTeamList() or {}
  for _, teamID in ipairs(teams) do
    if crafterUnits[teamID] then
      for _, kind in ipairs(KIND_ORDER) do
        craftKind(teamID, kind)
      end
    end
  end
end
