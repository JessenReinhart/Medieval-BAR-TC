return {
  medieval_fletcher = {
    name = "Fletcher",
    description = "Crafts bows and arrows for the settlement's ranged troops.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_fletcher.png",
    iconType = "medieval_economy_building",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 80,
    builder = false,
    buildTime = 55, -- Phase 6 Slice 3: old 45 -> 55 (craft timer: paces fletcher construction against the 30-frame bow craft cadence)
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    isFactory = true,
    footprintX = 4,
    footprintZ = 4,
    maxDamage = 1500,
    sightDistance = 400,
    mass = 450,
    upright = true,
    objectName = "0ad/medieval_fletcher.obj",
    side = "MEDIEVAL",
    buildoptions = {},
    customparams = {
      crafting = "bow",
      resource_cost_wood = 90, -- Phase 6 Slice 3: old 80 -> 90 (bow = wood 5 + iron 1 is wood-heavy; raise the wood cost to slow early fletcher spam)
      resource_cost_iron = 20,
      model_author = "Medieval-BAR-TC",
    },
  },
}
