--------------------------------------------------------------------------------
-- BAR move definitions adapted from c7eaa46992959435c6d3332e28e1169e1ddd43a6.
-- Recoil expects an array of move-def records, not a name-keyed table.
--------------------------------------------------------------------------------
local CRUSH = { SMALL = 15, MEDIUM = 30 }
local DEPTH = { MAX_SHALLOW = 20 }
local SLOPE = { MINIMUM = 27, DIFFICULT = 54 }
local SLOPE_MOD = { MODERATE = 18, MINIMUM = 4 }
return {
  { name = "BOT2", crushstrength = CRUSH.SMALL, footprintx = 2, footprintz = 2, maxslope = SLOPE.DIFFICULT / 1.5, maxwaterdepth = DEPTH.MAX_SHALLOW, slopeMod = SLOPE_MOD.MINIMUM, allowRawMovement = true, allowTerrainCollisions = false, heatmapping = true },
  { name = "TANK3", crushstrength = CRUSH.MEDIUM + 5, footprintx = 3, footprintz = 3, maxslope = SLOPE.MINIMUM / 1.5, maxwaterdepth = DEPTH.MAX_SHALLOW, slopeMod = SLOPE_MOD.MODERATE, allowRawMovement = true, allowTerrainCollisions = false, heatmapping = true },
}
