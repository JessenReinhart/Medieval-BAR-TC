-- Pure policy module for the Medieval-BAR-TC main menu.
-- No engine globals (no synced/unsynced API calls).  Fully testable in bare LuaJIT or
-- Python lupa with standard Lua 5.1 math, strings, and tables.
--
-- Loadability contract: this file must stay loadable by a bare Lua 5.1/LuaJIT
-- interpreter with no engine services present, so it never pulls in a sibling
-- module.  A future unsynced widget or lobby will read the tables and call the
-- helpers below; the widget owns every engine side effect.
--
-- Responsibilities:
--   * Menu view definitions (MAIN, SKIRMISH, SETTINGS, CREDITS)
--   * Default configurations and settings tables
--   * State-machine helpers (newMenuState, setTab, toggleOpen,
--     updateSkirmishOption, updateSetting, validateConfig)
--   * Recoil [GAME] startscript generator (generateStartscript)
local M = {}

-- ---------------------------------------------------------------------------
-- Constants
-- ---------------------------------------------------------------------------

--- Valid tab names.
M.VALID_TABS = { "MAIN", "SKIRMISH", "SETTINGS", "CREDITS" }

--- Button list shown on the MAIN tab.  "RESUME" is conditionally present when
--- the player is already in-game.
M.MAIN_BUTTONS = { "SKIRMISH", "SETTINGS", "CREDITS", "RESUME", "QUIT" }

--- Available maps.
M.MAPS = {
  "Quicksilver Remake 1.24",
  "Procedural Random Map",
}

--- Available factions / civ names.
M.FACTIONS = { "Britons", "Franks", "Saracens", "Norse" }

--- Team-colour palette (index -> colour name).
M.TEAM_COLORS = {
  "Blue", "Red", "Green", "Yellow", "Purple", "Orange", "Teal", "White",
}

--- AI type choices.
M.AI_TYPES = { "SkirmishAI", "NullAI" }

--- AI difficulty levels.
M.AI_DIFFICULTIES = { "Easy", "Medium", "Hard" }

--- Game mode choices.
M.GAME_MODES = { "tc_destruction", "conquest", "regicide", "time_limit" }

--- Modoption toggle keys exposed in the skirmish screen.
M.MODOPTION_TOGGLES = {
  "medievalmapgen",
  "medievaltactics",
  "medievalmarket",
  "medievalgarrison",
}

--- Graphic quality presets for water / shadows / grass.
M.QUALITY_LEVELS = { "Low", "Medium", "High", "Ultra" }

--- Resolution presets.
M.RESOLUTIONS = {
  "1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3840x2160",
}

-- ---------------------------------------------------------------------------
-- Default tables
-- ---------------------------------------------------------------------------

--- Sensible default skirmish configuration.
M.DEFAULT_CONFIG = {
  mapName        = "Quicksilver Remake 1.24",
  myPlayerName   = "Player",
  playerColor    = "Blue",
  playerFaction  = "Britons",
  playerTeamID   = 0,
  numAI          = 1,
  aiType         = "NullAI",
  aiDifficulty   = "Medium",
  gameMode       = "tc_destruction",
  proceduralMap  = false,
  seed           = 0,
  density        = "normal",
  numTeams       = 2,
  -- Modoption toggles (all start enabled for a full-experience default).
  medievalmapgen    = true,
  medievaltactics   = true,
  medievalmarket    = true,
  medievalgarrison  = true,
}

--- Sensible default settings.
M.DEFAULT_SETTINGS = {
  masterVolume    = 80,
  musicVolume     = 60,
  sfxVolume       = 70,
  resolution      = "1920x1080",
  fullscreen      = true,
  waterQuality    = "High",
  shadows         = "High",
  grassDetail     = "Medium",
}

-- ---------------------------------------------------------------------------
-- Credits
-- ---------------------------------------------------------------------------

M.CREDITS_TEXT = [[
=== Medieval-BAR-TC ===

Lead Development & Design
  Medieval-BAR-TC Contributors

Art & Assets
  0 A.D. (Wildfire Games) -- CC-BY-SA 3.0
  Art assets converted via tools/assets/convert_0ad.py

Engine
  Recoil / Spring RTS Engine -- GPL-v2

Sound
  Freesound.org contributors -- CC-BY / CC0

License
  Code: GPL-v2
  Converted Assets: CC-BY-SA 3.0

Special Thanks
  BAR community, 0 A.D. community
]]

-- ---------------------------------------------------------------------------
-- Helpers (internal)
-- ---------------------------------------------------------------------------

--- Check whether *value* exists in a sequential table *list*.
local function contains(list, value)
  for i = 1, #list do
    if list[i] == value then return true end
  end
  return false
end

--- Shallow-copy a flat table (one level).
local function shallowCopy(t)
  local out = {}
  for k, v in pairs(t) do out[k] = v end
  return out
end

--- Clamp a number to [lo, hi].
local function clamp(n, lo, hi)
  if n < lo then return lo end
  if n > hi then return hi end
  return n
end

-- ---------------------------------------------------------------------------
-- State Machine
-- ---------------------------------------------------------------------------

--- Create a fresh menu state table.
--- @return table  Menu state with activeTab, skirmishConfig, settingsConfig, isOpen.
function M.newMenuState()
  return {
    activeTab      = "MAIN",
    skirmishConfig = shallowCopy(M.DEFAULT_CONFIG),
    settingsConfig = shallowCopy(M.DEFAULT_SETTINGS),
    isOpen         = true,
  }
end

--- Set the active tab.
--- @param state table  Menu state from newMenuState().
--- @param tabName string  One of M.VALID_TABS.
--- @return boolean ok  True if the tab was set, false on invalid name.
function M.setTab(state, tabName)
  if not contains(M.VALID_TABS, tabName) then
    return false
  end
  state.activeTab = tabName
  return true
end

--- Toggle isOpen on the state (open <-> closed).
--- @param state table
function M.toggleOpen(state)
  state.isOpen = not state.isOpen
end

--- Update a single skirmish config key.
--- @param state table
--- @param key   string
--- @param value any
--- @return boolean ok
function M.updateSkirmishOption(state, key, value)
  if state.skirmishConfig[key] == nil and M.DEFAULT_CONFIG[key] == nil then
    return false
  end
  state.skirmishConfig[key] = value
  return true
end

--- Update a single settings key.
--- @param state table
--- @param key   string
--- @param value any
--- @return boolean ok
function M.updateSetting(state, key, value)
  if state.settingsConfig[key] == nil and M.DEFAULT_SETTINGS[key] == nil then
    return false
  end
  if (key == "masterVolume" or key == "musicVolume" or key == "sfxVolume") and type(value) == "number" then
    value = clamp(value, 0, 100)
  end
  state.settingsConfig[key] = value
  return true
end

-- ---------------------------------------------------------------------------
-- Validation
-- ---------------------------------------------------------------------------

--- Validate a skirmish config table before launching.
--- @param config table  A config table (same shape as DEFAULT_CONFIG).
--- @return boolean isValid
--- @return string|nil errorMsg  Nil when valid.
function M.validateConfig(config)
  if type(config) ~= "table" then
    return false, "config must be a table"
  end

  -- mapName
  if type(config.mapName) ~= "string" or config.mapName == "" then
    return false, "mapName must be a non-empty string"
  end

  -- myPlayerName
  if type(config.myPlayerName) ~= "string" or config.myPlayerName == "" then
    return false, "myPlayerName must be a non-empty string"
  end

  -- numTeams
  if type(config.numTeams) ~= "number" then
    return false, "numTeams must be a number"
  end
  if config.numTeams < 2 or config.numTeams > 4 then
    return false, "numTeams must be between 2 and 4"
  end

  -- aiType
  if not contains(M.AI_TYPES, config.aiType) then
    return false, "aiType must be 'SkirmishAI' or 'NullAI'"
  end

  -- victoryMode (gameMode key in startscript context)
  local vm = config.victoryMode or config.gameMode
  if vm and not contains(M.GAME_MODES, vm) then
    return false, "victoryMode must be one of: tc_destruction, conquest, regicide, time_limit"
  end

  -- numAI
  if config.numAI ~= nil then
    if type(config.numAI) ~= "number" then
      return false, "numAI must be a number"
    end
    if config.numAI < 1 or config.numAI > 3 then
      return false, "numAI must be between 1 and 3"
    end
  end

  -- proceduralMap
  if config.proceduralMap ~= nil and type(config.proceduralMap) ~= "boolean" then
    return false, "proceduralMap must be a boolean"
  end

  -- seed
  if config.seed ~= nil and type(config.seed) ~= "number" then
    return false, "seed must be a number"
  end

  -- density
  if config.density ~= nil then
    if not contains({"sparse", "normal", "dense"}, config.density) then
      return false, "density must be 'sparse', 'normal', or 'dense'"
    end
  end

  return true, nil
end

-- ---------------------------------------------------------------------------
-- Menu view queries (pure data for a future widget to consume)
-- ---------------------------------------------------------------------------

--- Return the list of buttons for the MAIN tab.
--- @param inGame boolean  Whether the player is already in-game.
--- @return table  Ordered list of button label strings.
function M.getMainButtons(inGame)
  local btns = {}
  for _, b in ipairs(M.MAIN_BUTTONS) do
    if b == "RESUME" then
      if inGame then btns[#btns + 1] = b end
    else
      btns[#btns + 1] = b
    end
  end
  return btns
end

-- ---------------------------------------------------------------------------
-- Startscript Generator
-- ---------------------------------------------------------------------------

--- Generate a Recoil [GAME] { ... } startscript string from a config table.
---
--- Expected config keys:
---   mapName        (string)
---   myPlayerName   (string)
---   numTeams       (number 2-4)
---   aiType         (string "SkirmishAI" or "NullAI")
---   victoryMode    (string)
---   proceduralMap  (bool)
---   seed           (number)
---   density        (string)
---
--- Optional keys used when present in config:
---   numAI          (number 1-3, defaults to numTeams-1)
---   aiDifficulty   (string, defaults to "Medium")
---   gameMode       (alias for victoryMode when victoryMode absent)
---   medievalmapgen, medievaltactics, medievalmarket, medievalgarrison (bool)
---
--- @param config table
--- @return string  A complete [GAME]{...} startscript block.
function M.generateStartscript(config)
  local lines = {}
  local function L(s) lines[#lines + 1] = s end

  -- Resolve optional / aliased keys.
  local victoryMode  = config.victoryMode or config.gameMode or "tc_destruction"
  local numTeams     = config.numTeams or 2
  local numAI        = config.numAI or (numTeams - 1)
  local aiType       = config.aiType or "NullAI"
  local aiDiff       = config.aiDifficulty or "Medium"
  local playerName   = config.myPlayerName or "Player"
  local mapName      = config.mapName or "Quicksilver Remake 1.24"
  local procMap      = config.proceduralMap
  local seed         = config.seed or 0
  local density      = config.density or "normal"

  -- Clamp values.
  numTeams = clamp(numTeams, 2, 4)
  numAI    = clamp(numAI, 1, 3)

  -- Ensure we do not have more AIs than teams allow (player occupies team 0).
  if numAI > numTeams - 1 then
    numAI = numTeams - 1
  end

  -- Start positions: spread evenly on a 8192x8192 default map grid.
  local mapSize = 8192
  local positions = {}
  local totalSlots = numAI + 1  -- player + AIs
  for i = 0, totalSlots - 1 do
    local frac = (i + 0.5) / totalSlots
    positions[i] = {
      x = math.floor(mapSize * frac),
      z = math.floor(mapSize * 0.5),
    }
  end

  -- ----- Header -----
  L("[GAME]")
  L("{")
  L("\tHostIP=127.0.0.1;")
  L("\tMapName=" .. mapName .. ";")
  L("\tGameType=Medieval BAR Total Conversion 0.2.0-phase2;")
  L("\tStartPosType=0;")
  L("\tGameStartDelay=0;")
  L("\tIsHost=1;")
  L("\tMyPlayerName=" .. playerName .. ";")
  L("\tRecordDemo=0;")

  -- ----- ALLYTEAM blocks -----
  for i = 0, numTeams - 1 do
    L("\t[ALLYTEAM" .. i .. "]")
    L("\t{")
    L("\t\tNumAllies=0;")
    L("\t}")
  end

  -- ----- TEAM blocks -----
  -- Team 0 is the human player, teams 1..numAI are AI opponents.
  for i = 0, numAI do
    local allyTeam = i
    if allyTeam >= numTeams then allyTeam = numTeams - 1 end
    L("\t[TEAM" .. i .. "]")
    L("\t{")
    L("\t\tTeamLeader=0;")
    L("\t\tAllyTeam=" .. allyTeam .. ";")
    if positions[i] then
      L("\t\tStartPosX=" .. positions[i].x .. ";")
      L("\t\tStartPosZ=" .. positions[i].z .. ";")
    end
    L("\t}")
  end

  -- ----- PLAYER0 (human) -----
  L("\t[PLAYER0]")
  L("\t{")
  L("\t\tName=" .. playerName .. ";")
  L("\t\tTeam=0;")
  L("\t\tSpectator=0;")
  L("\t\tReady=1;")
  L("\t\tStartPosReady=1;")
  L("\t}")

  -- ----- AI blocks -----
  for i = 0, numAI - 1 do
    L("\t[AI" .. i .. "]")
    L("\t{")
    L("\t\tName=Bot" .. (i + 1) .. ";")
    L("\t\tShortName=" .. aiType .. ";")
    L("\t\tTeam=" .. (i + 1) .. ";")
    L("\t\tHost=0;")
    L("\t}")
  end

  -- ----- MODOPTIONS -----
  L("\t[MODOPTIONS]")
  L("\t{")
  L("\t\tdeathmode=neverend;")
  L("\t\tvictorymode=" .. victoryMode .. ";")
  L("\t\tmedievalvictory=1;")
  L("\t\tskirmishai=1;")
  L("\t\tmedievalhud=1;")
  L("\t\tmedievalaudio=1;")
  L("\t\tmedievalbuildicons=1;")
  L("\t\tmedievalbottompanel=1;")
  L("\t\tmedievalminimap=1;")

  -- Modoption toggles from config.
  for _, key in ipairs(M.MODOPTION_TOGGLES) do
    local val = config[key]
    if val == nil then val = true end  -- default enabled
    L("\t\t" .. key .. "=" .. (val and "1" or "0") .. ";")
  end

  -- Procedural map options.
  if procMap then
    L("\t\tmedievalmapgenseed=" .. math.floor(seed) .. ";")
    L("\t\tmedievalmapdensity=" .. density .. ";")
  end

  -- AI difficulty as a custom modoption for the skirmish-AI gadget to read.
  L("\t\taidifficulty=" .. string.lower(aiDiff) .. ";")

  L("\t}")
  L("}")

  return table.concat(lines, "\n")
end

return M
