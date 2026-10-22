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

-- Collect map-authored metal spots by flood-filling the metal map. Every
-- contiguous positive-metal blob becomes one anchor; Quicksilver's 166.4-amount
-- MetalMap spots each occupy a compact texel patch. Texture-space texels convert
-- to world-space by multiplying by mapSize / metalMapSize.
local function collectMetalSpots()
  if not Spring.GetMetalMapSize or not Spring.GetMetalAmount then
    return nil
  end

  local mw, mh = Spring.GetMetalMapSize()
  -- Recoil exposes the metal map as a single square dimension.
  if not mw or mw <= 0 then return nil end
  if not mh or mh <= 0 then mh = mw end

  local mapSizeX = Game.mapSizeX
  local mapSizeZ = Game.mapSizeZ
  local scaleX = mapSizeX / mw
  local scaleZ = mapSizeZ / mh
  local visited = {}
  local spots = {}

  for gz = 0, mh - 1 do
    for gx = 0, mw - 1 do
      local value = Spring.GetMetalAmount(gx, gz)
      if value and value > 0 then
        local key = gx * 65536 + gz
        if not visited[key] then
          -- BFS over the 4-neighbourhood. Explicit head index avoids the O(n^2)
          -- table.remove() cost over large 448x448 metal maps.
          local queue = {{ gx, gz }}
          visited[key] = true
          local head = 1
          local sumX, sumZ, area = 0, 0, 0
          while head <= #queue do
            local cell = queue[head]
            head = head + 1
            local cx, cz = cell[1], cell[2]
            sumX = sumX + cx
            sumZ = sumZ + cz
            area = area + 1
            for _, d in ipairs({ {-1, 0}, { 1, 0 }, {0, -1}, {0, 1} }) do
              local nx, nz = cx + d[1], cz + d[2]
              if nx >= 0 and nx < mw and nz >= 0 and nz < mh then
                local nkey = nx * 65536 + nz
                if not visited[nkey] then
                  local nvalue = Spring.GetMetalAmount(nx, nz)
                  if nvalue and nvalue > 0 then
                    visited[nkey] = true
                    queue[#queue + 1] = { nx, nz }
                  end
                end
              end
            end
          end
          -- Centre the anchor on the blob's mean texel, then convert to world.
          spots[#spots + 1] = {
            x = math.floor((sumX / area + 0.5) * scaleX + 0.5),
            z = math.floor((sumZ / area + 0.5) * scaleZ + 0.5),
          }
        end
      end
    end
  end
  return spots
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
  local metalSpots = collectMetalSpots()

  local result = mapgen.generate({
    mapSizeX = sizeX,
    mapSizeZ = sizeZ,
    seed = seed,
    density = density,
    startPositions = startPositions,
    metalSpots = metalSpots,
  })

  for _, f in ipairs(result.features or {}) do
    local groundY = Spring.GetGroundHeight(f.x, f.z)
    Spring.CreateFeature(f.name, f.x, groundY, f.z, f.heading or 0)
  end

  Spring.Echo(string.format(
    "medieval_mapgen: spawned %d features (seed=%d, density=%s, map=%dx%d, starts=%d)",
    #result.features, result.seed or seed, result.density or density, sizeX, sizeZ, #startPositions
  ))
  Spring.Echo(string.format(
    "medieval_mapgen: anchored mines on %d map metal spots",
    type(metalSpots) == "table" and #metalSpots or 0
  ))
  Spring.SetGameRulesParam("medieval_mapgen_features", #result.features)
end