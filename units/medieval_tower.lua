return {
  medieval_tower = {
    name = "Watchtower",
    description = "Elevated watchtower providing long sight range over the surrounding area.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_tower.png",
    iconType = "medieval_defense",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 60,
    builder = false,
    buildTime = 60,
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    footprintX = 3,
    footprintZ = 3,
    -- Phase 5 Slice 4 garrison shelter (4 slots, vs the Town Center's 10).
    -- transportCapacity mirrors scripts/medieval_garrison.lua GARRISON_CAP.
    isTransport = true,
    transportCapacity = 4,
    transportSize = 1,
    transportMass = 50,
    transportUnloadMethod = 0,
    loadingRadius = 80,
    unloadSpread = 32,
    canLoad = true,
    canUnload = true,
    allowUnload = true,
    -- Phase 6 Slice 4: HP 1500 -> 1800, sight 600 -> 700. A sturdier, longer-
    -- sighted watchtower makes the AI's forward post defensible (still under
    -- the stone wall's HP and the Town Center's 3000).
    maxDamage = 1800,
    sightDistance = 700,
    mass = 500,
    upright = true,
    objectName = "0ad/medieval_tower.obj",
    side = "MEDIEVAL",
    customparams = {
      model_author = "Medieval-BAR-TC",
      resource_cost_wood = 20,
      resource_cost_stone = 50,
      armor_class = "fortification",
    },
  },
}