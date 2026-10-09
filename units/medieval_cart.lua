return {
  medieval_cart = {
    name = "Supply Cart",
    description = "Slow two-wheeled wagon that hauls bulk resources for the settlement. Unarmed civilian; it cannot gather, fight, or build.",
    category = "LAND",
    buildCostEnergy = 0,
    -- Mirrors customparams.resource_cost_wood, the convention used by the
    -- wood-only settlement buildings (see units/medieval_house.lua).
    buildCostMetal = 60,
    builder = false,
    buildTime = 35,
    canMove = true,
    canAttack = false,
    canFight = false,
    canPatrol = false,
    canGuard = false,
    -- TANK3 is the repository's 3x3 wheeled/vehicle move def (gamedata/movedefs.lua):
    -- slopeMod MODERATE with maxslope SLOPE.MINIMUM / 1.5, i.e. the worse slope
    -- handling of the two available defs. That plus the low maxVelocity is what
    -- makes the cart slow off-road. BOT2 would declare a 2x2 footprint and let it
    -- climb slopes the cart should not manage.
    movementclass = "TANK3",
    footprintX = 3,
    footprintZ = 3,
    maxDamage = 220,
    maxVelocity = 1.0,
    acceleration = 0.2,
    brakeRate = 0.3,
    turnRate = 400,
    sightDistance = 300,
    -- Follows the repo convention speed == maxVelocity * 15 (cf. medieval_catapult).
    speed = 15,
    mass = 400,
    upright = true,
    -- Art reuse: objects3d/0ad contains only medieval_archer, medieval_infantry,
    -- medieval_cavalry, and medieval_catapult (OBJ + texture-map .lua each). There
    -- is no cart or wagon mesh, so the cart reuses the catapult's wheeled carriage
    -- OBJ; the engine also picks up the sibling objects3d/0ad/medieval_catapult.lua
    -- texture map from the OBJ path, so no new asset files are added.
    objectName = "0ad/medieval_catapult.obj",
    script = "medieval_cart.lua",
    side = "MEDIEVAL",
    customparams = {
      model_author = "Medieval-BAR-TC",
      unit_role = "hauler",
      unitgroup = "civilian",
      carry_capacity = 400,
      -- No equipment gate. Lua drops nil-valued keys, so the absence of this key
      -- from the assembled table IS the "equipment_needed = nil" contract; it is
      -- named here so readers do not mistake the omission for an oversight.
      equipment_needed = nil,
      resource_cost_food = 0,
      resource_cost_wood = 60,
      resource_cost_stone = 0,
      resource_cost_iron = 10,
    },
  },
}
