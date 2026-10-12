return {
  medieval_town_center = {
    name = "Town Center",
    description = "Seat of the settlement; a drop-off point for all resources and the source of new villagers.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_town_center.png",
    iconType = "medieval_royal",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 300,
    builder = false,
    buildTime = 90,
    canMove = false,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    isFactory = true,
    -- Phase 5 Slice 4 garrison shelter. The engine transport primitive is the
    -- native garrisoning lever: a loaded unit leaves the map, so it cannot be
    -- hit directly, and the synced garrison gadget adds slow healing on top.
    -- transportCapacity mirrors scripts/medieval_garrison.lua GARRISON_CAP.
    isTransport = true,
    transportCapacity = 10,
    transportSize = 1,
    transportMass = 50,
    transportUnloadMethod = 0,
    loadingRadius = 96,
    unloadSpread = 48,
    canLoad = true,
    canUnload = true,
    allowUnload = true,
    movementclass = "BOT2",
    footprintX = 7,
    footprintZ = 7,
    maxDamage = 3000,
    yardspeed = 1.0,
    sightDistance = 500,
    mass = 1000,
    upright = true,
    objectName = "0ad/medieval_town_center.obj",
    side = "MEDIEVAL",
    buildoptions = {
      "medieval_villager",
    },
    customparams = {
      model_author = "Medieval-BAR-TC",
      dropoff = true,
      dropoff_radius = 128,
      pop_provided = 10,
    },
  },
}