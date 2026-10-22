-- Pure procedural map generation for Medieval-BAR-TC.
-- No Spring.*, VFS.*, or GG.* globals — standard Lua 5.1 math and tables only.
local M = {}

local floor = math.floor
local sqrt  = math.sqrt
local pi    = math.pi
local cos   = math.cos
local sin   = math.sin

---------------------------------------------------------------------------
-- Constants
---------------------------------------------------------------------------

M.FEATURES = {
  TREE  = "medieval_tree",
  STONE = "medieval_stone",
  IRON  = "medieval_iron",
  DEER  = "medieval_deer",
}

M.DENSITY_SCALES = { sparse = 0.6, normal = 1.0, dense = 1.6 }

M.START_POCKET = {
  -- Guaranteed home economy: 8 trees (150-350 elmos), 1-2 stone nodes,
  -- 1 deer herd (3 deer) for hunting food, and START_EXCLUSION_RADIUS (100)
  -- so nothing spawns on top of the Town Center. Iron is wilderness-only.
  { name = "medieval_tree",  count =  8, minRadius = 150, maxRadius = 350 },
  { name = "medieval_stone", count =  2, minRadius = 180, maxRadius = 380 },
  { name = "medieval_deer",  count =  3, minRadius = 160, maxRadius = 360 },
}

-- Minimum distances between features by type to prevent mesh overlap.
-- Tree spacing is 16 for denser jungle clumps.
local MIN_DIST = {
  medieval_tree  = 16,
  medieval_stone = 36,
  medieval_iron  = 36,
  medieval_deer  = 30,
}

-- Exclusion zone around each start position (no features at all).
local START_EXCLUSION_RADIUS = 100

-- Map-edge margin.
local EDGE_MARGIN = 128

---------------------------------------------------------------------------
-- Deterministic PRNG — LCG (Numerical Recipes)
---------------------------------------------------------------------------
-- Portable LCG that fits in Lua 5.1 doubles (52-bit mantissa > 32-bit state).
-- Period 2^32, passes most statistical tests, and is very fast.
-- state(n+1) = (a * state(n) + c) mod m
-- a = 1664525, c = 1013904223, m = 2^32

local LCG_A = 1664525
local LCG_C = 1013904223
local LCG_M = 4294967296  -- 2^32

function M.newRNG(seed)
  if type(seed) ~= "number" then seed = 1 end
  seed = floor(seed) % LCG_M
  if seed < 0 then seed = seed + LCG_M end

  local state = seed

  local rng = {}

  -- Advance state and return raw integer in [0, 2^32-1].
  local function nextInt()
    state = (LCG_A * state + LCG_C) % LCG_M
    return state
  end

  --- Returns a float in [0, 1).
  function rng.random()
    return nextInt() / LCG_M
  end

  --- Returns an integer in [min, max] inclusive.
  function rng.randomInt(min, max)
    if type(min) ~= "number" or type(max) ~= "number" then return 0 end
    min = floor(min)
    max = floor(max)
    if min > max then min, max = max, min end
    local range = max - min + 1
    return min + floor(rng.random() * range)
  end

  --- Returns a random element from a non-empty table (array part).
  function rng.randomChoice(tbl)
    if type(tbl) ~= "table" or #tbl == 0 then return nil end
    return tbl[rng.randomInt(1, #tbl)]
  end

  return rng
end

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

local function dist2(ax, az, bx, bz)
  local dx = ax - bx
  local dz = az - bz
  return sqrt(dx * dx + dz * dz)
end

local function inBounds(x, z, sizeX, sizeZ)
  return x >= EDGE_MARGIN and x <= sizeX - EDGE_MARGIN
     and z >= EDGE_MARGIN and z <= sizeZ - EDGE_MARGIN
end

-- Check if a position is inside any start exclusion zone.
local function inExclusionZone(x, z, startPositions)
  for i = 1, #startPositions do
    local sp = startPositions[i]
    if dist2(x, z, sp.x, sp.z) < START_EXCLUSION_RADIUS then
      return true
    end
  end
  return false
end

-- Check minimum spacing against already-placed features of the same type.
local function tooClose(x, z, name, placed)
  local minD = MIN_DIST[name] or 24
  for i = 1, #placed do
    local f = placed[i]
    if f.name == name and dist2(x, z, f.x, f.z) < minD then
      return true
    end
  end
  return false
end

---------------------------------------------------------------------------
-- Pocket placement (guaranteed resources near each start)
---------------------------------------------------------------------------

local function placeStartPockets(rng, startPositions, sizeX, sizeZ, placed)
  local pockets = {}
  for si = 1, #startPositions do
    local sp = startPositions[si]
    local pocket = { x = sp.x, z = sp.z, features = {} }
    for _, def in ipairs(M.START_POCKET) do
      for _ = 1, def.count do
        -- Try up to 30 times to find a valid spot.
        local tries = 0
        local ok = false
        while tries < 30 and not ok do
          tries = tries + 1
          local angle  = rng.random() * 2 * pi
          local radius = def.minRadius + rng.random() * (def.maxRadius - def.minRadius)
          local fx = sp.x + cos(angle) * radius
          local fz = sp.z + sin(angle) * radius
          fx = floor(fx + 0.5)
          fz = floor(fz + 0.5)
          if inBounds(fx, fz, sizeX, sizeZ)
             and not inExclusionZone(fx, fz, startPositions)
             and not tooClose(fx, fz, def.name, placed) then
            local heading = rng.random() * 2 * pi
            local feat = { name = def.name, x = fx, z = fz, heading = heading }
            placed[#placed + 1] = feat
            pocket.features[#pocket.features + 1] = feat
            ok = true
          end
        end
      end
    end
    pockets[#pockets + 1] = pocket
  end
  return pockets
end

---------------------------------------------------------------------------
-- Metal-spot mine placement (map-authored resource spots)
---------------------------------------------------------------------------

-- When the gadget supplies metal-spot anchors read from the map's metal map,
-- the mines are placed on those anchored positions instead of being sprayed
-- randomly. Each anchor receives a 2-3 node vein; veins alternate stone/iron
-- so the map's natural ore fields spread both strategic minerals.
local SPOT_VEIN_MIN = 2
local SPOT_VEIN_MAX = 3
local SPOT_JITTER  = 40

local function placeSpotMines(rng, spots, startPositions, sizeX, sizeZ, placed)
  if type(spots) ~= "table" then return end
  for i = 1, #spots do
    local spot = spots[i]
    if type(spot) == "table" and type(spot.x) == "number" and type(spot.z) == "number" then
      -- Alternate the mined mineral across spots; index 1 starts with iron.
      local name = (i % 2 == 1) and "medieval_iron" or "medieval_stone"
      local count = rng.randomInt(SPOT_VEIN_MIN, SPOT_VEIN_MAX)
      for _ = 1, count do
        local tries = 0
        local ok = false
        while tries < 20 and not ok do
          tries = tries + 1
          local angle  = rng.random() * 2 * pi
          local radius = rng.random() * SPOT_JITTER
          local fx = floor(spot.x + cos(angle) * radius + 0.5)
          local fz = floor(spot.z + sin(angle) * radius + 0.5)
          if inBounds(fx, fz, sizeX, sizeZ)
             and not inExclusionZone(fx, fz, startPositions)
             and not tooClose(fx, fz, name, placed) then
            placed[#placed + 1] = {
              name = name,
              x = fx,
              z = fz,
              heading = rng.random() * 2 * pi,
            }
            ok = true
          end
        end
      end
    end
  end
end

---------------------------------------------------------------------------
-- Wilderness cluster placement
---------------------------------------------------------------------------

-- Cluster templates: { name, clusterMin, clusterMax, jitter }
-- Balance pass: trees form dense jungle groves (16-32 trees per clump with tight 28-elmo jitter);
-- stone forms small outcrops; iron is scarce (1-3 nodes); deer roam in scattered herds.
-- The stone/iron wilderness templates only run in legacy mode (no metal-spot
-- anchors): when real map ore spots exist they are replaced by placeSpotMines.
local WILDERNESS_TEMPLATES = {
  { name = "medieval_tree",  clusterMin = 18, clusterMax = 36, jitter = 32 },
  { name = "medieval_stone", clusterMin = 2,  clusterMax = 4,  jitter = 46 },
  { name = "medieval_iron",  clusterMin = 1,  clusterMax = 3,  jitter = 80 },
  { name = "medieval_deer",  clusterMin = 3,  clusterMax = 5,  jitter = 44 },
}

-- How many clusters per 4096×4096 at normal density, per type.
-- Tree cluster density increased to 28 so maps have abundant jungle clumps.
local CLUSTERS_PER_4096 = {
  medieval_tree  = 28,
  medieval_stone = 8,
  medieval_iron  = 3,
  medieval_deer  = 6,
}

local function placeWilderness(rng, startPositions, sizeX, sizeZ, densityScale, placed, hasAnchoredMines)
  local areaRatio = (sizeX * sizeZ) / (4096 * 4096)

  for _, tmpl in ipairs(WILDERNESS_TEMPLATES) do
    -- Skip generic stone/iron scattering when spots are already anchored
    if not (hasAnchoredMines and (tmpl.name == "medieval_stone" or tmpl.name == "medieval_iron")) then
      local baseCount = CLUSTERS_PER_4096[tmpl.name] or 6
      local numClusters = floor(baseCount * areaRatio * densityScale + 0.5)
      if numClusters < 1 then numClusters = 1 end

      for _ = 1, numClusters do
        -- Pick a cluster center.
        local cx = EDGE_MARGIN + rng.random() * (sizeX - 2 * EDGE_MARGIN)
        local cz = EDGE_MARGIN + rng.random() * (sizeZ - 2 * EDGE_MARGIN)
        cx = floor(cx + 0.5)
        cz = floor(cz + 0.5)

        -- Skip cluster if center is in an exclusion zone.
        if not inExclusionZone(cx, cz, startPositions) then
          local count = rng.randomInt(tmpl.clusterMin, tmpl.clusterMax)
          for _ = 1, count do
            local tries = 0
            local ok = false
            while tries < 20 and not ok do
              tries = tries + 1
              local angle  = rng.random() * 2 * pi
              local radius = rng.random() * tmpl.jitter
              local fx = cx + cos(angle) * radius
              local fz = cz + sin(angle) * radius
              fx = floor(fx + 0.5)
              fz = floor(fz + 0.5)
              if inBounds(fx, fz, sizeX, sizeZ)
                 and not inExclusionZone(fx, fz, startPositions)
                 and not tooClose(fx, fz, tmpl.name, placed) then
                local heading = rng.random() * 2 * pi
                placed[#placed + 1] = { name = tmpl.name, x = fx, z = fz, heading = heading }
                ok = true
              end
            end
          end
        end
      end
    end
  end
end

---------------------------------------------------------------------------
-- Main generation function
---------------------------------------------------------------------------

function M.generate(opts)
  if type(opts) ~= "table" then opts = {} end

  local mapSizeX = (type(opts.mapSizeX) == "number" and opts.mapSizeX > 0)
                      and floor(opts.mapSizeX) or 4096
  local mapSizeZ = (type(opts.mapSizeZ) == "number" and opts.mapSizeZ > 0)
                      and floor(opts.mapSizeZ) or 4096
  local seed     = (type(opts.seed) == "number") and floor(opts.seed) or 1
  local density  = (type(opts.density) == "string" and M.DENSITY_SCALES[opts.density])
                      and opts.density or "normal"

  local startPositions = {}
  if type(opts.startPositions) == "table" then
    for i = 1, #opts.startPositions do
      local sp = opts.startPositions[i]
      if type(sp) == "table" and type(sp.x) == "number" and type(sp.z) == "number" then
        startPositions[#startPositions + 1] = { x = sp.x, z = sp.z }
      end
    end
  end

  local metalSpots = {}
  if type(opts.metalSpots) == "table" then
    for i = 1, #opts.metalSpots do
      local s = opts.metalSpots[i]
      if type(s) == "table" and type(s.x) == "number" and type(s.z) == "number" then
        metalSpots[#metalSpots + 1] = { x = s.x, z = s.z }
      end
    end
  end

  local rng = M.newRNG(seed)
  local densityScale = M.DENSITY_SCALES[density]

  local placed = {}

  -- Phase 1: start pockets.
  local startPockets = placeStartPockets(rng, startPositions, mapSizeX, mapSizeZ, placed)

  -- Phase 2: metal-spot anchored mines (stone and iron on map spots).
  local hasAnchoredMines = #metalSpots > 0
  if hasAnchoredMines then
    placeSpotMines(rng, metalSpots, startPositions, mapSizeX, mapSizeZ, placed)
  end

  -- Phase 3: wilderness clusters (trees and deer; and legacy mines if unanchored).
  placeWilderness(rng, startPositions, mapSizeX, mapSizeZ, densityScale, placed, hasAnchoredMines)

  return {
    seed         = seed,
    mapSizeX     = mapSizeX,
    mapSizeZ     = mapSizeZ,
    density      = density,
    features     = placed,
    startPockets = startPockets,
    metalSpots   = metalSpots,
  }
end

return M
