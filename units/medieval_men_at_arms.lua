return {
  medieval_men_at_arms = {
    -- Display name is prefixed with "Veteran" to stay distinct from the Phase 1
    -- medieval_infantry def, which already renders as "Man-at-Arms".
    name = "Veteran Man-at-Arms",
    description = "Veteran heavy melee infantry, drilled and plate-armoured (upgraded infantry tier)",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 150,
    builder = false,
    buildTime = 55,
    canMove = true,
    canAttack = true,
    canFight = true,
    canPatrol = true,
    canGuard = true,
    movementclass = "BOT2",
    footprintX = 2,
    footprintZ = 2,
    maxDamage = 350,
    maxVelocity = 1.3,
    acceleration = 0.45,
    brakeRate = 0.45,
    turnRate = 1000,
    sightDistance = 380,
    -- `speed` mirrors maxVelocity at the repository's 15x convention
    -- (infantry 2.1 -> 32, archer 1.9 -> 28, cavalry 3.6 -> 54).
    speed = 20,
    mass = 260,
    upright = true,
    -- Reuses the base infantry geometry/texture: no new 0ad assets exist for the
    -- upgraded tier, so the object and LUS are shared with medieval_infantry.
    objectName = "0ad/medieval_infantry.obj",
    script = "medieval_infantry.lua",
    side = "MEDIEVAL",
    customparams = {
      resource_cost_food = 45,
      resource_cost_wood = 25,
      resource_cost_stone = 15,
      resource_cost_iron = 15,
      model_author = "Medieval-BAR-TC",
      unitgroup = "weapon",
      unit_role = "military",
      armor_class = "standard",
      tech_prereq = "veteran_infantry",
      equipment_needed = "sword",
    },
    weapons = {
      {
        name = "sword",
        mainDir = {0,0,1},
        maxAngleDif = 300,
        onlyTargetCategory = "LAND",
        -- FX placeholder (no audio/CEG assets exist in this repo yet):
        --   soundstart = "<melee swing sfx>", soundhit = "<melee impact sfx>",
        --   explosionGenerator = "<melee hit CEG>"
        -- Keep as comment until a sounds/ dir and CEG generator names exist.
      },
    },
  },
}
