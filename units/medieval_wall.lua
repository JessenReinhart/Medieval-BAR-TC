return {
  medieval_wall = {
    name = "Stone Wall",
    description = "Defensive stone wall that blocks enemy movement and protects the settlement.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_wall.png",
    iconType = "medieval_defense",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 50,
    builder = false,
    buildTime = 45,
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    footprintX = 2,
    footprintZ = 2,
    -- Phase 6 Slice 4: HP 2500 -> 2800. Stone walls meaningfully gate a breach
    -- (still below the Town Center's 3000, per the king def hierarchy note).
    maxDamage = 2800,
    mass = 400,
    upright = true,
    objectName = "0ad/medieval_wall.obj",
    side = "MEDIEVAL",
    customparams = {
      model_author = "Medieval-BAR-TC",
      resource_cost_wood = 10,
      resource_cost_stone = 40,
      armor_class = "fortification",
    },
  },
}