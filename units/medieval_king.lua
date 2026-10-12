return {
  medieval_king = {
    -- Deliberately the internal def name rather than a title-cased label: the
    -- regicide objective is keyed on this string (scripts/medieval_victory.lua
    -- REGICIDE_KING_DEF), so the display name and the objective identity are
    -- kept identical and cannot drift.
    name = "medieval_king",
    description = "The settlement's sovereign: unarmoured, armed only with a dagger, but the realm itself under the regicide objective.",
    -- Phase 7 Slice 5: dedicated build-menu picture and radar/minimap icon.
    buildpic = "medieval_king.png",
    iconType = "medieval_royal",
    category = "LAND",
    buildCostEnergy = 0,
    buildCostMetal = 0,
    builder = false,
    buildTime = 60,
    canMove = true,
    -- A weak dagger, deliberately: the king is an objective, not a combat unit.
    canAttack = true,
    canFight = true,
    canPatrol = true,
    canGuard = true,
    movementclass = "BOT2",
    footprintX = 2,
    footprintZ = 2,
    -- High health so the king is a durable objective rather than a one-shot kill,
    -- while still being far cheaper to bring down than a Town Center (3000).
    maxDamage = 1200,
    maxVelocity = 1.9,
    acceleration = 0.45,
    brakeRate = 0.5,
    turnRate = 1000,
    -- Phase 6 Slice 4: sight 400 -> 500. The sovereign is the regicide objective;
    -- broader awareness helps it spot threats (maxDamage 1200 is a Phase-5 pin,
    -- left unchanged).
    sightDistance = 500,
    -- Follows the repo convention speed == maxVelocity * 15 (cf. medieval_villager).
    speed = 28,
    mass = 180,
    upright = true,
    -- Phase 7 Slice 3: the king now has a dedicated converted 0 A.D. mesh
    -- (objects3d/0ad/medieval_king.obj, from the Cunobelin hero actor), so the
    -- former infantry-body reuse is gone. The LUS stays medieval_infantry.lua:
    -- animation is Phase 7 Slice 4 scope, not asset scope.
    objectName = "0ad/medieval_king.obj",
    script = "medieval_infantry.lua",
    side = "MEDIEVAL",
    customparams = {
      model_author = "Medieval-BAR-TC",
      unitgroup = "weapon",
      unit_role = "king",
      armor_class = "standard",
      -- Consumed by scripts/medieval_victory.lua (REGICIDE_KING_DEF) and by the
      -- victory gadget's king registration. The classification itself is keyed
      -- on the def NAME above, so a rename here would break regicide.
      victory_objective = "king",
      resource_cost_food = 0,
      resource_cost_wood = 0,
      resource_cost_stone = 0,
      resource_cost_iron = 0,
    },
    weapons = {
      {
        name = "dagger",
        mainDir = {0,0,1},
        maxAngleDif = 300,
        onlyTargetCategory = "LAND",
        soundStart = "sword_swing",
        soundHit = "dagger_hit",
        -- Phase 7 Slice 2: the dagger shares the melee impact FX.
        explosionGenerator = "custom:melee_hit_fx",
      },
    },
  },
}
