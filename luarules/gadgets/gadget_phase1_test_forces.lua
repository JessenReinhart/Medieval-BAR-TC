function gadget:GetInfo()
  return { name = "Phase 1 Medieval Test Forces", desc = "Opt-in spawns and synced formation intent",
    author = "Medieval-BAR-TC", license = "GPL-v2", layer = 0, enabled = true }
end

if not gadgetHandler:IsSyncedCode() then return end
local options = Spring.GetModOptions() or {}
local enabled = options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1"
if not enabled then return end

local formation = VFS.Include("scripts/phase1_line_formation.lua")
local pending, spawned = {}, false
local names = { "medieval_infantry", "medieval_archer", "medieval_cavalry" }
local allowedDefs = {}
for _, name in ipairs(names) do
  if UnitDefNames[name] then allowedDefs[UnitDefNames[name].id] = true end
end

local function validGround(defID, x, z)
  if not formation.bounds(x, z, Game.mapSizeX, Game.mapSizeZ, 32) then return end
  local y = Spring.GetGroundHeight(x, z)
  -- Dry, passable, unoccupied ground only. Never force spawns into water or cliffs.
  if formation.finite(y) and y >= 0 and Spring.TestMoveOrder(defID, x, y, z) then return y end
end

local function teams()
  local list = Spring.GetTeamList()
  table.sort(list)
  local gaia = Spring.GetGaiaTeamID()
  for i, a in ipairs(list) do
    local _, _, deadA = Spring.GetTeamInfo(a, false)
    if a ~= gaia and not deadA then
      for j = i + 1, #list do
        local b = list[j]
        local _, _, deadB = Spring.GetTeamInfo(b, false)
        if b ~= gaia and not deadB and not Spring.AreTeamsAllied(a, b) then return a, b end
      end
    end
  end
end

local function spawnForces()
  local a, b = teams()
  if not a then Spring.Echo("Phase 1: need two live non-Gaia, non-allied teams; spawned 0") return end
  for _, name in ipairs(names) do
    if not UnitDefNames[name] then Spring.Echo("Phase 1: missing " .. name .. "; spawned 0") return end
  end
  local count = tonumber(options.medievaltestcount) or 200
  if not formation.finite(count) then count = 200 end
  count = math.max(200, math.min(1000, math.floor(count)))
  local forces, teamIDs = { {}, {} }, { a, b }
  -- Map-relative, separated halves. Fixed 64-elmo grid avoids overlap and bounds work.
  -- Scan is bounded; unsuitable maps legitimately produce fewer than requested units.
  for side = 1, 2 do
    local want = side == 1 and math.floor(count / 2) or math.ceil(count / 2)
    local x0, x1 = Game.mapSizeX * (side == 1 and 0.10 or 0.60), Game.mapSizeX * (side == 1 and 0.40 or 0.90)
    for x = x0, x1, 64 do
      if #forces[side] >= want then break end
      for z = Game.mapSizeZ * 0.10, Game.mapSizeZ * 0.90, 64 do
        if #forces[side] >= want then break end
        local defID = UnitDefNames[names[(#forces[side] % 3) + 1]].id
        local y = validGround(defID, x, z)
        if y then
          local id = Spring.CreateUnit(defID, x, y, z, side == 1 and "east" or "west", teamIDs[side])
          if id then forces[side][#forces[side] + 1] = { id = id, x = x, y = y, z = z } end
        end
      end
    end
  end
  for side = 1, 2 do
    local enemy = forces[3 - side][1]
    if enemy then
      for _, unit in ipairs(forces[side]) do
        Spring.GiveOrderToUnit(unit.id, CMD.FIGHT, { enemy.x, enemy.y, enemy.z }, 0)
      end
    end
  end
  Spring.Echo(string.format("Phase 1: requested %d; created %d (team %d: %d, team %d: %d)",
    count, #forces[1] + #forces[2], a, #forces[1], b, #forces[2]))
end

-- Wire format: x, z, spacing, cardinal facing 0..3, count, unit IDs.
-- IDs only establish ranks. Each engine-authorized command can move ONLY its receiver.
local function destination(unitID, unitDefID, teamID, p)
  if not allowedDefs[unitDefID] or type(p) ~= "table" or #p > formation.MAX_UNITS + 5 then return end
  local count = p[5]
  local ids = formation.sortedIDs(p, 6, count)
  if not ids then return end
  local rank
  for i, id in ipairs(ids) do
    if Spring.GetUnitTeam(id) ~= teamID or not allowedDefs[Spring.GetUnitDefID(id)] then return end
    if id == unitID then rank = i end
  end
  if not rank then return end
  -- Pass autoFit=true so formations cleanly clamp spacing when map margins require it.
  local slots = formation.destinations(count, p[1], p[2], p[3], p[4], Game.mapSizeX, Game.mapSizeZ, true)
  if not slots then return end
  local slot = slots[rank]
  local y = validGround(unitDefID, slot.x, slot.z)
  if y then return { slot.x, y, slot.z } end
end

-- Force pregame readiness in headless/test mode so the match starts without a
-- lobby or GUI ready-up. This is opt-in via medievaltest modoption.
function gadget:GameSetup(state, ready, playerStates)
  if enabled then return true, true end
  return false, ready
end

function gadget:Initialize()
  -- Pinned BAR cmd_manual_launch.lua and gadgets.lua register custom IDs this way.
  gadgetHandler:RegisterCMDID(formation.CMD_ID)
  gadgetHandler:RegisterAllowCommand(CMD.ANY)
end

function gadget:AllowCommand(unitID, unitDefID, teamID, cmdID, params, opts)
  if cmdID ~= formation.CMD_ID then
    -- A later ordinary order always wins over an unflushed formation request.
    pending[unitID] = nil
    return true
  end
  -- Phase 1 is an immediate command, not a queue editor. Reject shift/insert modifiers.
  if opts and ((opts.coded and opts.coded ~= 0) or opts.shift or opts.alt or opts.ctrl or opts.right or opts.internal) then return false end
  local target = destination(unitID, unitDefID, teamID, params)
  if target then pending[unitID] = { target = target, team = teamID, def = unitDefID } end
  return false -- consume custom command; never leave unknown commands in the engine queue
end

-- Interruptible: subsequent user actions (stop, move, attack, death, transfer) cancel formation.
function gadget:UnitDestroyed(unitID) pending[unitID] = nil end
function gadget:UnitTaken(unitID) pending[unitID] = nil end
function gadget:UnitIdle(unitID) pending[unitID] = nil end

function gadget:GameFrame(frame)
  if not spawned and frame >= 30 then spawned = true; spawnForces() end
  -- One-shot deferred dispatch avoids GiveOrder recursion within AllowCommand.
  local ids = {}
  for id in pairs(pending) do ids[#ids + 1] = id end
  table.sort(ids)
  local dispatch = pending
  pending = {}
  for _, id in ipairs(ids) do
    local order = dispatch[id]
    if Spring.GetUnitTeam(id) == order.team and Spring.GetUnitDefID(id) == order.def then
      Spring.GiveOrderToUnit(id, CMD.MOVE, order.target, 0)
    end
  end
end
