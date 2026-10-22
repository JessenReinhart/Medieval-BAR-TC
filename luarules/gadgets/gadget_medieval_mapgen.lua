-- Synced procedural map generation: spawns wilderness resource nodes (trees,
-- stone, iron, deer) plus "fair" starting clusters around each team's start
-- position at match start.
--
-- All placement math lives in scripts/medieval_mapgen.lua (pure Lua, no Spring
-- or VFS globals); this gadget owns modoption gating, the Spring.* side effects
-- (reading map size and start positions, creating features) and the one-shot
-- generated flag.

function gadget:GetInfo()
  return {
    name = "Medieval Procedural Map Generator",
    desc = "Spawns procedural resource nodes (trees, stone, iron, deer) at match start",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 2,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

-- ---------------------------------------------------------------------------
-- Modoption gating
-- ---------------------------------------------------------------------------

local options = Spring.GetModOptions and Spring.GetModOptions() or {}

local enabledValue = options.medievalmapgen
if not (enabledValue == "1" or enabledValue == 1 or enabledValue == true) then
  return
end

local mapgen = VFS.Include("scripts/medieval_mapgen.lua")

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Collect x/z start positions for every team that has one. Teams without a
-- start position (gaia, spectators, dead teams) are naturally skipped.
local function collectStartPositions()
  local starts = {}
  local teams = Spring.GetTeamList and Spring.GetTeamList() or {}
  for _, teamID in ipairs(teams) do
    local sx, _, sz = Spring.GetTeamStartPosition(teamID)
    if sx and sz then
      starts[#starts + 1] = { x = sx, z = sz }
    end
  end
  return starts
end

-- Resolve the seed: a configured non-zero seed is authoritative; otherwise
-- derive one from the current sim frame, falling back to wall-clock time and
-- then to math.random.
local function resolveSeed()
  local seed = tonumber(options.medievalmapgenseed)
  if seed and seed ~= 0 then
    return seed
  end
  local frame = Spring.GetGameFrame and Spring.GetGameFrame() or 0
  if frame and frame > 0 then
    return frame
  end
  -- `os` is unavailable inside the synced Lua sandbox; use the engine's synced
  -- RNG as the final fallback so every client derives the same seed.
  return math.floor(math.random() * 2147483647)
end

-- ---------------------------------------------------------------------------
-- Generation (one-shot)
-- ---------------------------------------------------------------------------

local generated = false

function gadget:GameStart()
  if generated then return end
  generated = true

  local sizeX = Game.mapSizeX
  local sizeZ = Game.mapSizeZ
  local seed = resolveSeed()
  local density = options.medievalmapdensity or "normal"
  local startPositions = collectStartPositions()

  local result = mapgen.generate({
    mapSizeX = sizeX,
    mapSizeZ = sizeZ,
    seed = seed,
    density = density,
    startPositions = startPositions,
  })

  for _, f in ipairs(result.features or {}) do
    local groundY = Spring.GetGroundHeight(f.x, f.z)
    Spring.CreateFeature(f.name, f.x, groundY, f.z, f.heading or 0)
  end

  Spring.Echo(string.format(
    "medieval_mapgen: spawned %d features (seed=%d, density=%s, map=%dx%d, starts=%d)",
    #result.features, result.seed or seed, result.density or density, sizeX, sizeZ, #startPositions
  ))
  Spring.SetGameRulesParam("medieval_mapgen_features", #result.features)
end