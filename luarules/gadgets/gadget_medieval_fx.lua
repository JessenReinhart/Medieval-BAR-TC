function gadget:GetInfo()
  return {
    name = "Medieval FX Hooks",
    desc = "Lightweight audio/visual feedback hooks for medieval units, gated by the medievalaudio mod option",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 4,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

-- Mod option gate. Mirrors the helper the other medieval gadgets use: an
-- option counts as ON for 1/true/"1"/"true" and OFF for 0/false/"0"/"false".
-- A missing key (older modoptions.lua) falls back to `default`.
local function modOptionOn(key, default)
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  local v = mo[key]
  if v == nil then return default end
  return v == 1 or v == true or v == "1" or v == "true"
end

-- Phase 7 Slice 5: `medievalaudio` mutes the whole medieval sound set without
-- touching the synced log lines, so a headless probe still observes the same
-- training/destruction verdicts with audio disabled.
local AUDIO_ENABLED = modOptionOn("medievalaudio", true)

-- Published once so unsynced widgets can mirror the state instead of reading
-- modoptions themselves (UI isolation: widgets only read rules params).
local function publishOptionState()
  if Spring.SetGameRulesParam then
    Spring.SetGameRulesParam("medieval_audio", AUDIO_ENABLED and 1 or 0)
  end
end

-- Resolve the internal unit def name the same way the recruitment gadget does.
local function internalName(unitDefID)
  if not unitDefID then return nil end
  local def = UnitDefs and UnitDefs[unitDefID]
  if not def then return nil end
  return def.name
end

local function isMedievalUnit(name)
  if type(name) ~= "string" then return false end
  return string.find(name, "^medieval_") ~= nil
end

-- Single audio choke point: every PlaySoundFile in this gadget goes through
-- here, so the mod option cannot be bypassed by a new call site.
local function playSound(path, x, y, z)
  if not AUDIO_ENABLED then return false end
  if not (Spring and Spring.PlaySoundFile) then return false end
  if x and y and z then
    return pcall(Spring.PlaySoundFile, path, 1.0, x, y, z)
  else
    return pcall(Spring.PlaySoundFile, path)
  end
end

-- Monotonic frame source used for cooldown accounting. Frames advance on the
-- sim clock, so they are stable even when the OS wall-clock jumps (or when a
-- headless probe has no timer).
local function currentFrame()
  if Spring and Spring.GetGameFrame then
    local f = Spring.GetGameFrame()
    if type(f) == "number" then return f end
  end
  if Spring and Spring.GetGameSeconds then
    local s = Spring.GetGameSeconds()
    if type(s) == "number" then return math.floor(s * 30) end
  end
  return 0
end

-- Build a rate-limited sound trigger. Each trigger keeps its own last-played
-- frame; calls inside `cooldownSeconds` of the previous play are dropped so a
-- burst of game events cannot spam the audio device.
local function makeCooldownSound(path, cooldownSeconds)
  local cdFrames = math.max(1, math.floor((cooldownSeconds or 0) * 30))
  local lastPlayed = -math.huge
  return function(x, y, z)
    local f = currentFrame()
    if f - lastPlayed < cdFrames then return false end
    lastPlayed = f
    return playSound(path, x, y, z)
  end
end

-- Shared per-sound triggers. Gather is split by resource type so wood and
-- stone/iron have independent cooldowns (you can hear both kinds at once).
local woodChop = makeCooldownSound("sounds/economy/wood_chop.ogg", 1.2)
local stoneMine = makeCooldownSound("sounds/economy/stone_mine.ogg", 1.2)
local haulCart = makeCooldownSound("sounds/economy/haul_cart.ogg", 2.0)
local construct = makeCooldownSound("sounds/economy/construction.ogg", 2.0)

-- Under-attack is keyed per team so a coordinated push against several towns
-- alerts each base once, but a single base does not repeat the klaxon every
-- hit. ~10s per team.
local underAttackLast = {}
local UNDER_ATTACK_CD_FRAMES = math.floor(10 * 30)

local function PlayGather(resType, x, y, z)
  if resType == "wood" then
    return woodChop(x, y, z)
  elseif resType == "stone" or resType == "iron" then
    return stoneMine(x, y, z)
  end
  return false
end

local function PlayHaul(x, y, z)
  return haulCart(x, y, z)
end

local function PlayConstruct(x, y, z)
  return construct(x, y, z)
end

local function PlayUnderAttack(teamID, x, y, z)
  local f = currentFrame()
  local key = teamID or -1
  local last = underAttackLast[key]
  if last and (f - last < UNDER_ATTACK_CD_FRAMES) then
    return false
  end
  underAttackLast[key] = f
  return playSound("sounds/ui/alarm_under_attack.ogg", x, y, z)
end

function gadget:Initialize()
  publishOptionState()
end

function gadget:UnitCreated(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX trained unit %s team %s", tostring(unitID), tostring(teamID)))
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  local def = UnitDefs and UnitDefs[unitDefID]
  if def and (def.isFactory or (def.canMove == false and not def.isFactory)) then
    -- Building (factory or static structure) construction completed.
    playSound("sounds/ui/building_complete.ogg")
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID)
  local name = internalName(unitDefID)
  if not isMedievalUnit(name) then return end
  Spring.Echo(string.format("PHASE2 FX destroyed unit %s team %s", tostring(unitID), tostring(teamID)))
end

-- Exposed for the slice-5 tests and for any future gadget that wants to honour
-- the same switch without re-reading modoptions.
GG.MedievalFX = GG.MedievalFX or {}
GG.MedievalFX.audioEnabled = AUDIO_ENABLED
GG.MedievalFX.modOptionOn = modOptionOn
GG.MedievalFX.publishOptionState = publishOptionState
GG.MedievalFX.PlayGather = PlayGather
GG.MedievalFX.PlayHaul = PlayHaul
GG.MedievalFX.PlayConstruct = PlayConstruct
GG.MedievalFX.PlayUnderAttack = PlayUnderAttack
