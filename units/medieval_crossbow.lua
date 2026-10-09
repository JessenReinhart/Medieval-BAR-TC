return {
  medieval_crossbow = {
    name = "Crossbowman",
    description = "Veteran ranged infantry firing armour-piercing bolts (upgraded archer tier)",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 140,
    builder = false,
    buildTime = 50,
    canMove = true,
    canAttack = true,
    canFight = true,
    canPatrol = true,
    canGuard = true,
    movementclass = "BOT2",
    footprintX = 2,
    footprintZ = 2,
    maxDamage = 160,
    maxVelocity = 1.2,
    acceleration = 0.4,
    brakeRate = 0.4,
    turnRate = 900,
    sightDistance = 500,
    -- `speed` mirrors maxVelocity at the repository's 15x convention
    -- (archer 1.9 -> 28, cavalry 3.6 -> 54).
    speed = 18,
    mass = 160,
    upright = true,
    -- Reuses the base archer geometry/texture: no new 0ad assets exist for the
    -- upgraded tier, so the object and LUS are shared with medieval_archer.
    objectName = "0ad/medieval_archer.obj",
    script = "medieval_archer.lua",
    side = "MEDIEVAL",
    customparams = {
      resource_cost_food = 35,
      resource_cost_wood = 45,
      resource_cost_stone = 5,
      resource_cost_iron = 10,
      model_author = "Medieval-BAR-TC",
      unitgroup = "weapon",
      unit_role = "military",
      armor_class = "standard",
      tech_prereq = "crossbow_tech",
      equipment_needed = "bow",
    },
    weapons = {
      {
        -- The upgraded tier keeps the base "longbow" weapon def name so the
        -- shared medieval_archer LUS and weapondefs entry stay valid.
        name = "longbow",
        mainDir = {0,0,1},
        maxAngleDif = 300,
        onlyTargetCategory = "LAND",
        -- FX placeholder (no audio/CEG assets exist in this repo yet):
        --   soundstart = "<crossbow release sfx>", soundhit = "<bolt impact sfx>",
        --   explosionGenerator = "<bolt hit CEG>"
        -- Keep as comment until a sounds/ dir and CEG generator names exist.
      },
    },
  },
}
