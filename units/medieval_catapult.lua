return {
  medieval_catapult = {
    name = "Catapult",
    description = "Siege engine firing heavy stones at long range",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 170,
    builder = false,
    buildTime = 90,
    canMove = true,
    canAttack = true,
    canFight = true,
    canPatrol = true,
    canGuard = true,
    -- TANK3 is the repository's 3x3 vehicle move def; BOT2 declares a 2x2
    -- footprint and would contradict footprintX/footprintZ = 3 below.
    movementclass = "TANK3",
    footprintX = 3,
    footprintZ = 3,
    maxDamage = 600,
    maxVelocity = 1.2,
    acceleration = 0.15,
    brakeRate = 0.3,
    turnRate = 300,
    sightDistance = 500,
    speed = 18,
    mass = 800,
    upright = true,
    objectName = "0ad/medieval_catapult.obj",
    script = "medieval_catapult.lua",
    side = "MEDIEVAL",
    customparams = {
      resource_cost_wood = 120,
      resource_cost_stone = 40,
      resource_cost_iron = 10,
      model_author = "Medieval-BAR-TC",
      unitgroup = "weapon",
    },
    weapons = {
      {
        name = "catapult",
        mainDir = {0,0,1},
        -- Full traverse: the lithobolos sits on a turntable, so the weapon arc must
        -- not constrain it. A narrow arc combined with an unconditional LUS
        -- AimWeapon1 `return true` lets the engine fire while the barrel still
        -- points off-axis, and the rock then lands nowhere near the target.
        maxAngleDif = 360,
        onlyTargetCategory = "LAND",
        -- FX placeholder (no audio/CEG assets exist in this repo yet):
        --   soundstart = "<catapult release sfx>", soundhit = "<stone impact sfx>",
        --   explosionGenerator = "<stone hit CEG>"
        -- Keep as comment until a sounds/ dir and CEG generator names exist.
      },
    },
  },
}
