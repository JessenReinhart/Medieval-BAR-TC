-- Shared, pure validation and slot math; no engine calls in this module.
local M = { CMD_ID = 371912, MAX_UNITS = 1000, MIN_SPACING = 8, MAX_SPACING = 128 }
local floor, min = math.floor, math.min

function M.finite(n)
  return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end

function M.bounds(x, z, sizeX, sizeZ, margin)
  margin = margin or 16
  return M.finite(x) and M.finite(z) and M.finite(sizeX) and M.finite(sizeZ)
    and M.finite(margin) and margin >= 0 and sizeX > 2 * margin and sizeZ > 2 * margin
    and x >= margin and x <= sizeX - margin and z >= margin and z <= sizeZ - margin
end

-- If autoFit is true, spacing is clamped downward (never below MIN_SPACING) so the line fits within margins.
function M.destinations(count, x, z, spacing, facing, sizeX, sizeZ, autoFit)
  if not M.finite(count) or count ~= floor(count) or count < 1 or count > M.MAX_UNITS
    or not M.finite(spacing) or spacing < M.MIN_SPACING or spacing > M.MAX_SPACING
    or not M.finite(facing) or facing ~= floor(facing) or facing < 0 or facing > 3
    or not M.bounds(x, z, sizeX, sizeZ, 32) then return nil end

  if autoFit and count > 1 then
    local availableHalf = (facing == 1 or facing == 3) and min(z - 32, sizeZ - 32 - z) or min(x - 32, sizeX - 32 - x)
    if availableHalf <= 0 then return nil end
    local maxSpacing = (2 * availableHalf) / (count - 1)
    if maxSpacing < M.MIN_SPACING then return nil end
    if maxSpacing < spacing then spacing = maxSpacing end
  end

  local result = {}
  for i = 1, count do
    local offset = (i - (count + 1) * 0.5) * spacing
    local px, pz = x, z
    if facing == 1 or facing == 3 then pz = pz + offset else px = px + offset end
    if not M.bounds(px, pz, sizeX, sizeZ, 32) then return nil end
    result[i] = { x = px, z = pz }
  end
  return result
end

-- Reject rather than silently dropping malformed or duplicate IDs. Never trust UI-provided ranks.
function M.sortedIDs(params, first, count)
  if not M.finite(count) or count ~= floor(count) or count < 1 or count > M.MAX_UNITS
    or #params ~= first + count - 1 then return nil end
  local ids = {}
  for i = 1, count do
    local id = params[first + i - 1]
    if not M.finite(id) or id ~= floor(id) or id < 0 then return nil end
    ids[i] = id
  end
  table.sort(ids)
  for i = 2, count do if ids[i] == ids[i - 1] then return nil end end
  return ids
end

return M
