return {
  medieval_knight = {
    -- Display name is prefixed with "Chivalric" to stay distinct from the Phase 1
    -- medieval_cavalry def, which already renders as "Knight".
    name = "Chivalric Knight",
    description = "Veteran mounted heavy cavalry, sworn and lance-armed (upgraded cavalry tier)",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 300,
    builder = false,
    buildTime = 80,
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
    maxDamage = 550,
    maxVelocity = 2.2,
    acceleration = 0.7,
    brakeRate = 0.55,
    turnRate = 1200,
    sightDistance = 450,
    -- `speed` mirrors maxVelocity at the repository's 15x convention
    -- (cavalry 3.6 -> 54, catapult 1.2 -> 18).
    speed = 33,
    mass = 520,
    upright = false,
    -- Reuses the base cavalry geometry/texture: no new 0ad assets exist for the
    -- upgraded tier, so the object and LUS are shared with medieval_cavalry.
    objectName = "0ad/medieval_cavalry.obj",
    script = "medieval_cavalry.lua",
    side = "MEDIEVAL",
    customparams = {
      resource_cost_food = 70,
      resource_cost_wood = 25,
      resource_cost_stone = 25,
      resource_cost_iron = 40,
      model_author = "Medieval-BAR-TC",
      unitgroup = "weapon",
      unit_role = "military",
      armor_class = "standard",
      tech_prereq = "chivalry",
      equipment_needed = "sword",
    },
    weapons = {
      {
        name = "lance",
        mainDir = {0,0,1},
        maxAngleDif = 300,
        onlyTargetCategory = "LAND",
        -- FX placeholder (no audio/CEG assets exist in this repo yet):
        --   soundstart = "<cavalry charge sfx>", soundhit = "<lance impact sfx>",
        --   explosionGenerator = "<charge impact CEG>"
        -- Keep as comment until a sounds/ dir and CEG generator names exist.
      },
    },
  },
}
