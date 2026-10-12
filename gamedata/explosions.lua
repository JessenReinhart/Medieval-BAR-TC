-- Custom Explosion Generator (CEG) definitions for Medieval-BAR-TC.
--
-- Phase 7 Slice 2: Combat FX, Projectiles & Visual Impact.
--
-- ---------------------------------------------------------------------------
-- How this file is loaded (verified against the bundled engine build)
-- ---------------------------------------------------------------------------
-- The engine parses CEGs through `gamedata/explosions.lua`. The mod's copy of
-- that path shadows the engine's own copy, so this file *is* the entry point:
-- its return value must be a `CEG name -> spawn table` map. Each spawn table
-- maps a spawn name to a projectile-class config, and the engine parses every
-- field against the reflected member list of the class named in `class`.
--
-- The engine's base copy of this file builds the same map by scanning
-- `gamedata/explosions/` and `effects/`; returning a static table is an
-- equally valid implementation of that contract, and keeps the whole medieval
-- impact set in one reviewable place.
--
-- Weapon defs reference these by name as `explosionGenerator = "custom:<name>"`
-- (the `custom:` prefix is required; the engine logs
-- `no CEG named "<x>" (forgot the "custom:" prefix?)` otherwise).
--
-- ---------------------------------------------------------------------------
-- Field-name provenance (important)
-- ---------------------------------------------------------------------------
-- The engine does NOT accept the widely-copied legacy CEG vocabulary. Field
-- names here were taken from the reflected member lists embedded in the
-- bundled `spring-headless.exe`, per spawn class:
--
--   CSimpleParticleSystem  pos speed useAirLos alwaysVisible
--                          emitVector emitMul gravity colorMap texture airdrag
--                          particleLife particleLifeSpread numParticles
--                          particleSpeed particleSpeedSpread
--                          particleSize particleSizeSpread
--                          emitRot emitRotSpread directional sizeGrowth sizeMod
--   CDirtProjectile        pos speed useAirLos alwaysVisible
--                          alpha alphaFalloff size sizeExpansion slowdown
--                          color texture
--   CStandardGroundFlash   pos size depthTest depthMask flashSize flashAlpha
--                          circleGrowth circleAlpha color side1 side2
--                          circleSize flashAge flashAgeSpeed circleAlphaDec
--                          ttl texture sizeGrowth alpha fade normal colorMap
--
-- Consequences that shape the configs below:
--   * `count` is NOT a valid field: the particle count field is `numParticles`.
--   * `life` / `size` / `speed` / `spread` are NOT CSimpleParticleSystem
--     fields: the real names are `particleLife`, `particleSize`,
--     `particleSpeed` and the `*Spread` variants.
--   * `ttl` is NOT registered on CSimpleParticleSystem or CDirtProjectile;
--     particle lifetime there is controlled by `particleLife`. `ttl` IS valid
--     on CStandardGroundFlash and is used below.
--   * `graysmoke` is not a texture this install ships. Only engine-provided
--     textures are used: `smoke`, `flare`, `explofade`.
--
-- ---------------------------------------------------------------------------
-- Design intent: lightweight
-- ---------------------------------------------------------------------------
-- Medieval combat is low-explosive, so these are short dust / splinter / spark
-- / crater puffs, not Hollywood explosions. Particle counts are small
-- (3-14) and lifetimes short (6-22 frames) because a packed melee line can
-- fire an impact every few frames per unit; several of these overlap on screen
-- at once. No light sources and no long trails.
--
-- This table is data-only: no `Spring.*` / `VFS.*` globals, so bare Lua 5.1
-- (LuaJIT) can execute it in the test suite.

local explosions = {

  ------------------------------------------------------------------------------
  -- arrow_hit_fx -- longbow arrow impact.
  --
  -- A small tan dust puff plus a few wooden splinters kicked back out. No
  -- spark and no crater: an arrow thuds into dirt, a shield or a body, it does
  -- not gouge the terrain.
  ------------------------------------------------------------------------------
  arrow_hit_fx = {
    -- Main dust puff: low, expands as it fades.
    dust = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 3, 0 },
      emitVector         = { 0, 1, 0 },
      emitRot            = 70,
      emitRotSpread      = 30,
      numParticles       = 6,
      particleSpeed      = 2.2,
      particleSpeedSpread = 1.4,
      particleLife       = 12,
      particleLifeSpread = 5,
      particleSize       = 2.4,
      particleSizeSpread = 0.8,
      sizeGrowth         = 0.35,
      gravity            = -0.06,
      airdrag            = 0.94,
      texture            = 'smoke',
      colorMap           = {
        { 0.72, 0.66, 0.50, 0.75 },
        { 0.55, 0.50, 0.40, 0.00 },
      },
      useAirLos          = false,
    },
    -- Splinters: darker and heavier, pulled down by gravity.
    splinter = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 4, 0 },
      emitVector         = { 0, 0.6, 0 },
      emitRot            = 55,
      emitRotSpread      = 40,
      numParticles       = 3,
      particleSpeed      = 3.4,
      particleSpeedSpread = 1.8,
      particleLife       = 16,
      particleLifeSpread = 6,
      particleSize       = 1.1,
      particleSizeSpread = 0.4,
      sizeGrowth         = -0.02,
      gravity            = -0.22,
      airdrag            = 0.97,
      texture            = 'smoke',
      colorMap           = {
        { 0.42, 0.30, 0.18, 0.90 },
        { 0.30, 0.22, 0.13, 0.00 },
      },
      useAirLos          = false,
    },
  },

  ------------------------------------------------------------------------------
  -- bolt_hit_fx -- crossbow bolt / armour impact.
  --
  -- Sharper and brighter than an arrow: a tight spark cone off metal plus a
  -- thin grey puff. Sparks use negative sizeGrowth and heavy gravity so they
  -- arc and die like real sparks instead of floating.
  ------------------------------------------------------------------------------
  bolt_hit_fx = {
    spark = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 6, 0 },
      emitVector         = { 0, 0.8, 0 },
      emitRot            = 45,
      emitRotSpread      = 45,
      numParticles       = 10,
      particleSpeed      = 6.5,
      particleSpeedSpread = 3.5,
      particleLife       = 8,
      particleLifeSpread = 4,
      particleSize       = 0.8,
      particleSizeSpread = 0.3,
      sizeGrowth         = -0.05,
      gravity            = -0.35,
      airdrag            = 0.90,
      texture            = 'flare',
      colorMap           = {
        { 1.00, 0.92, 0.60, 1.00 },
        { 0.95, 0.45, 0.10, 0.00 },
      },
      useAirLos          = false,
    },
    dust = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 3, 0 },
      emitVector         = { 0, 1, 0 },
      emitRot            = 80,
      emitRotSpread      = 25,
      numParticles       = 4,
      particleSpeed      = 1.6,
      particleSpeedSpread = 0.9,
      particleLife       = 10,
      particleLifeSpread = 4,
      particleSize       = 1.8,
      particleSizeSpread = 0.6,
      sizeGrowth         = 0.28,
      gravity            = -0.04,
      airdrag            = 0.95,
      texture            = 'smoke',
      colorMap           = {
        { 0.62, 0.62, 0.60, 0.55 },
        { 0.45, 0.45, 0.44, 0.00 },
      },
      useAirLos          = false,
    },
  },

  ------------------------------------------------------------------------------
  -- stone_hit_fx -- catapult boulder impact.
  --
  -- The heavy one, and the only medieval weapon that should visibly scar the
  -- ground. A radial debris spray thrown outward, a rising grey dust cloud, and
  -- a short-lived ground flash that reads as the crater's first frame.
  --
  -- CDirtProjectile is used for the settling dirt cloud because it is the
  -- engine's dirt class; its member list is small and fully verified above.
  ------------------------------------------------------------------------------
  stone_hit_fx = {
    -- Thrown dirt clods.
    debris = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 6, 0 },
      emitVector         = { 0, 1, 0 },
      emitRot            = 35,
      emitRotSpread      = 55,
      numParticles       = 14,
      particleSpeed      = 5.0,
      particleSpeedSpread = 3.0,
      particleLife       = 22,
      particleLifeSpread = 10,
      particleSize       = 1.6,
      particleSizeSpread = 0.7,
      sizeGrowth         = -0.04,
      gravity            = -0.45,
      airdrag            = 0.95,
      texture            = 'smoke',
      colorMap           = {
        { 0.40, 0.33, 0.24, 0.95 },
        { 0.26, 0.22, 0.17, 0.00 },
      },
      useAirLos          = false,
    },
    -- Dust cloud: wider, slower, longer-lived than the rest of this file.
    dust = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 4, 0 },
      emitVector         = { 0, 1, 0 },
      emitRot            = 60,
      emitRotSpread      = 30,
      numParticles       = 8,
      particleSpeed      = 2.6,
      particleSpeedSpread = 1.6,
      particleLife       = 24,
      particleLifeSpread = 10,
      particleSize       = 4.5,
      particleSizeSpread = 1.5,
      sizeGrowth         = 0.75,
      gravity            = -0.02,
      airdrag            = 0.93,
      texture            = 'smoke',
      colorMap           = {
        { 0.58, 0.54, 0.46, 0.60 },
        { 0.44, 0.42, 0.37, 0.00 },
      },
      useAirLos          = false,
    },
    -- Settling dirt: the ground-hugging layer that lingers after the debris.
    dirt = {
      class        = 'CDirtProjectile',
      pos          = { 0, 2, 0 },
      speed        = { 0, 1.5, 0 },
      size         = 8.0,
      sizeExpansion = 1.6,
      alpha        = 0.70,
      alphaFalloff = 0.045,
      slowdown     = 0.96,
      texture      = 'explofade',
      color        = { 0.46, 0.38, 0.28 },
      useAirLos    = false,
    },
    -- Crater flash: a brief ring at the impact point.
    groundflash = {
      class          = 'CStandardGroundFlash',
      pos            = { 0, 1, 0 },
      ttl            = 14,
      size           = 8.0,
      sizeGrowth     = 0.0,
      flashSize      = 46.0,
      flashAlpha     = 0.28,
      circleSize     = 22.0,
      circleGrowth   = 3.0,
      circleAlpha    = 0.35,
      circleAlphaDec = 0.03,
      color          = { 0.55, 0.45, 0.30 },
      -- Ground flashes draw from the engine's `groundfx` atlas, whose member
      -- names are `groundflash` / `groundring` / `seismic`.
      texture        = 'groundflash',
    },
  },

  ------------------------------------------------------------------------------
  -- melee_hit_fx -- sword / lance / dagger contact.
  --
  -- Read at a glance in a packed melee: one bright spark burst for steel on
  -- steel, one short dark-red fleck burst for a hit that draws blood, and a
  -- very short low dust scuff at foot level. Deliberately the cheapest
  -- generator here, because melee lines generate impacts constantly.
  ------------------------------------------------------------------------------
  melee_hit_fx = {
    -- Steel-on-steel sparks.
    spark = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 10, 0 },
      emitVector         = { 0, 0.7, 0 },
      emitRot            = 50,
      emitRotSpread      = 45,
      numParticles       = 8,
      particleSpeed      = 5.5,
      particleSpeedSpread = 3.0,
      particleLife       = 7,
      particleLifeSpread = 3,
      particleSize       = 0.7,
      particleSizeSpread = 0.25,
      sizeGrowth         = -0.04,
      gravity            = -0.32,
      airdrag            = 0.90,
      texture            = 'flare',
      colorMap           = {
        { 1.00, 0.90, 0.55, 1.00 },
        { 0.92, 0.40, 0.08, 0.00 },
      },
      useAirLos          = false,
    },
    -- Blood / flesh flecks: short, dark, no glow.
    fleck = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 9, 0 },
      emitVector         = { 0, 0.8, 0 },
      emitRot            = 40,
      emitRotSpread      = 35,
      numParticles       = 5,
      particleSpeed      = 2.4,
      particleSpeedSpread = 1.4,
      particleLife       = 10,
      particleLifeSpread = 4,
      particleSize       = 0.9,
      particleSizeSpread = 0.3,
      sizeGrowth         = -0.03,
      gravity            = -0.28,
      airdrag            = 0.96,
      texture            = 'smoke',
      colorMap           = {
        { 0.48, 0.08, 0.06, 0.85 },
        { 0.28, 0.05, 0.04, 0.00 },
      },
      useAirLos          = false,
    },
    -- Ground scuff: dust kicked up at the feet of a shoving melee.
    scuff = {
      class              = 'CSimpleParticleSystem',
      pos                = { 0, 1, 0 },
      emitVector         = { 0, 1, 0 },
      emitRot            = 85,
      emitRotSpread      = 20,
      numParticles       = 4,
      particleSpeed      = 1.3,
      particleSpeedSpread = 0.8,
      particleLife       = 9,
      particleLifeSpread = 3,
      particleSize       = 2.0,
      particleSizeSpread = 0.7,
      sizeGrowth         = 0.30,
      gravity            = -0.03,
      airdrag            = 0.95,
      texture            = 'smoke',
      colorMap           = {
        { 0.66, 0.62, 0.54, 0.45 },
        { 0.50, 0.47, 0.42, 0.00 },
      },
      useAirLos          = false,
    },
  },

  ------------------------------------------------------------------------------
  -- default -- retained from the original scaffold.
  --
  -- Unit defs that do not name a specific death explosion still reference this
  -- name, so the entry is kept to avoid dangling `explodeAs = "default"`
  -- references.
  ------------------------------------------------------------------------------
  default = {
    usedefaultexplosions = true,
  },

}

return explosions
