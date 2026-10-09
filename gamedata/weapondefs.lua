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
    customparams = {
      damage_class = "siege",
    },
  },
}