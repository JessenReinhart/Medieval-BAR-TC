return {
  noweapon = {
    name = "Placeholder Weapon",
    weaponType = "Cannon",
    range = 0,
    reloadtime = 0,
    turret = false,
    damage = {default = 0},
  },
  sword = {
    name = "Broadsword",
    weaponType = "Melee",
    range = 45,
    reloadtime = 1.2,
    turret = false,
    weaponVelocity = 1000,
    tolerance = 10000,
    damage = {default = 150},
    areaOfEffect = 8,
    craterBoost = 0,
    craterMult = 0,
    waterWeapon = true,
    soundStart = "sword_swing",
    soundHit = "sword_hit",
    -- Phase 7 Slice 2: steel sparks + blood flecks + a low ground scuff.
    explosionGenerator = "custom:melee_hit_fx",
    customparams = {
      damage_class = "melee",
    },
  },
  longbow = {
    name = "Longbow",
    weaponType = "Cannon",
    range = 380,
    reloadtime = 2.0,
    turret = true,
    tolerance = 8000,
    damage = {default = 90},
    areaOfEffect = 12,
    craterBoost = 0,
    craterMult = 0,
    weaponVelocity = 400,
    myGravity = 0.5,
    heightBoostFactor = 1.2,
    -- Phase 7 Slice 2 projectile readability. No arrow mesh exists in
    -- objects3d/0ad (only the four converted 0 A.D. unit meshes), so the arrow
    -- is drawn as the engine's 2D sprite. `size` sets that sprite's on-screen
    -- size and `rgbColor` tints it fletching-brown; `smokeTrail = false` keeps
    -- it clean — a single arrow should not drag a smoke ribbon behind it.
    size = 2.0,
    rgbColor = {0.55, 0.42, 0.25},
    smokeTrail = false,
    soundStart = "bow_shoot",
    soundHit = "arrow_hit",
    -- Phase 7 Slice 2: dust + wood splinters where the arrow lands.
    explosionGenerator = "custom:arrow_hit_fx",
    customparams = {
      damage_class = "ranged",
    },
  },
  lance = {
    name = "Heavy Lance",
    weaponType = "Melee",
    range = 55,
    reloadtime = 1.5,
    turret = false,
    weaponVelocity = 1000,
    tolerance = 10000,
    damage = {default = 240},
    areaOfEffect = 16,
    craterBoost = 0,
    craterMult = 0,
    waterWeapon = true,
    soundStart = "lance_charge",
    soundHit = "lance_hit",
    -- Phase 7 Slice 2: lance impacts read as a melee hit, not a projectile one.
    explosionGenerator = "custom:melee_hit_fx",
    customparams = {
      damage_class = "melee",
    },
  },
  -- Phase 5 Slice 1 regicide objective: the king's ceremonial dagger. The king
  -- is an objective, not a fighter, so this is deliberately the weakest weapon in
  -- the repository (sword 150, lance 240, longbow 90, catapult 500) — it exists
  -- so the def is not unarmed (an unarmed unit cannot be ordered to attack and
  -- the engine warns on a missing weapondef) without making the king a threat.
  dagger = {
    name = "Ceremonial Dagger",
    weaponType = "Melee",
    range = 30,
    reloadtime = 2.5,
    turret = false,
    weaponVelocity = 1000,
    tolerance = 10000,
    damage = {default = 40},
    areaOfEffect = 4,
    craterBoost = 0,
    craterMult = 0,
    waterWeapon = true,
    soundStart = "sword_swing",
    soundHit = "dagger_hit",
    -- Phase 7 Slice 2: the king's dagger still lands a melee impact effect.
    explosionGenerator = "custom:melee_hit_fx",
    customparams = {
      damage_class = "melee",
    },
  },
  -- Phase 4 Slice 1 siege engine: slow, heavy, ballistic, with a dead zone
  -- (minRange) so the catapult cannot defend itself at melee distance.
  --
  -- `minRange` is kept here as the authoritative design value, but this engine
  -- build does not implement a weapondef-level minimum-range tag: it logs
  -- `Warning: WeaponDefs: Unknown tag "minrange" in "catapult"` at load and
  -- ignores it. scripts/medieval_catapult.lua enforces the same 120-elmo dead
  -- zone in AimWeapon1/AimWeapon instead (see that file's MIN_RANGE).
  --
  -- `noSelfDamage` is required: the converted 0 A.D. mesh has no muzzle piece,
  -- so the rock launches from the unit origin and its own 48-elmo AoE would
  -- otherwise destroy the launcher on the first shot.
  --
  -- `myGravity` deviates from the original 0.6 design value. In this engine
  -- `myGravity` is elmos/frame^2, and the ballistic reach of a Cannon weapon is
  -- v^2 / g = 350^2 / 0.6 = 136 / 0.6 ~= 227 elmos, which is far short of the
  -- 550-elmo range below. The solver then produces a degenerate flat shot that
  -- spawns under the terrain and dies on the first frame (verified in-engine:
  -- projectile at y=89.7 against ground height 90.3). 0.2 is the engine default
  -- and gives v^2 / g = 136 / 0.2 = 680 elmos, which covers range 550 with a
  -- real arc while keeping the heavy, slow feel of a siege engine.
  catapult = {
    name = "Catapult Rock",
    weaponType = "Cannon",
    range = 550,
    minRange = 120,
    reloadtime = 5.0,
    turret = true,
    tolerance = 8000,
    weaponVelocity = 350,
    myGravity = 0.2,
    heightBoostFactor = 1.5,
    damage = {default = 500},
    areaOfEffect = 48,
    edgeEffectiveness = 0.5,
    noSelfDamage = true,
    craterBoost = 0,
    craterMult = 0,
    -- Phase 7 Slice 2 projectile readability. Same constraint as the longbow:
    -- no boulder mesh ships, so the rock is a 2D sprite. It is bigger, grey and
    -- darker than an arrow, and it keeps the engine's smoke ribbon on because a
    -- tumbling siege rock genuinely reads better with a trail than without.
    size = 5.0,
    rgbColor = {0.42, 0.40, 0.36},
    smokeTrail = true,
    soundStart = "catapult_shoot",
    soundHit = "catapult_hit",
    -- Phase 7 Slice 2: the only weapon that scars the ground — debris, dust
    -- cloud, settling dirt and a brief crater flash.
    explosionGenerator = "custom:stone_hit_fx",
    customparams = {
      damage_class = "siege",
    },
  },
}