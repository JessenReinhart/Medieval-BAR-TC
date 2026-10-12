return {
  medieval_blacksmith = {
    name = "Blacksmith",
    description = "Crafts equipment and arms for the settlement.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_blacksmith.png",
    iconType = "medieval_economy_building",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 100,
    builder = false,
    buildTime = 60, -- Phase 6 Slice 3: old 50 -> 60 (craft timer: a smith takes longer than its 30-frame sword cadence to stand up, so production buildings cannot be front-loaded faster than they produce)
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    isFactory = true,
    footprintX = 5,
    footprintZ = 5,
    maxDamage = 2000,
    sightDistance = 400,
    mass = 600,
    upright = true,
    objectName = "0ad/medieval_blacksmith.obj",
    side = "MEDIEVAL",
    buildoptions = {},
    customparams = {
      crafting = "sword",
      resource_cost_wood = 100,
      resource_cost_iron = 80, -- Phase 6 Slice 3: old 50 -> 80 (sword = iron 5 + wood 2 is iron-heavy; skew the smith build cost toward iron to match its sink profile)
      model_author = "Medieval-BAR-TC",
    },
  },
}
