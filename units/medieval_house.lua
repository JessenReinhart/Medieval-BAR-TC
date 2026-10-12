return {
  medieval_house = {
    name = "Peasant House",
    description = "Provides residential living space for the settlement, supporting +5 population.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_house.png",
    iconType = "medieval_economy_building",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 60,
    builder = false,
    -- Phase 6 Slice 1: buildTime 30->25; villager #1 appears at frame 20, so the
    -- house completes at 20+25 = 45 frames, inside the 90-frame opening.
    buildTime = 25,
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    footprintX = 4,
    footprintZ = 4,
    maxDamage = 800,
    sightDistance = 300,
    mass = 300,
    upright = true,
    objectName = "0ad/medieval_house.obj",
    side = "MEDIEVAL",
    customparams = {
      model_author = "Medieval-BAR-TC",
      pop_provided = 5,
      resource_cost_wood = 60,
    },
  },
}