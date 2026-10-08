-- Shared, pure medieval road adjacency and connectivity graph math; no engine calls in this module.
local M = {
  LINK_RADIUS = 64.0, -- two road features are adjacent when within this planar distance
}

local huge = math.huge

-- Finite number check: rejects nil, non-numbers, NaN, and infinities.
local function finiteNum(n)
  return type(n) == "number" and n == n and n ~= huge and n ~= -huge
end

-- Planar distance between (ax, az) and (bx, bz); math.huge on non-number input.
function M.planarDist(ax, az, bx, bz)
  if not finiteNum(ax) or not finiteNum(az) or not finiteNum(bx) or not finiteNum(bz) then
    return huge
  end
  local dx = ax - bx
  local dz = az - bz
  return math.sqrt(dx * dx + dz * dz)
end

-- Radius sanity: fall back to the default link radius on anything unusable.
local function normRadius(radius)
  if finiteNum(radius) and radius >= 0 then return radius end
  return M.LINK_RADIUS
end

-- A node entry is valid only when it is a table with finite numeric x/z.
local function validEntry(entry)
  return type(entry) == "table" and finiteNum(entry.x) and finiteNum(entry.z)
end

-- Collect the valid (key, x, z) nodes from a roads table; invalid entries are skipped.
local function collectNodes(roads)
  local nodes = {}
  if type(roads) ~= "table" then return nodes end
  for key, entry in pairs(roads) do
    if validEntry(entry) then
      nodes[#nodes + 1] = { key = key, x = entry.x, z = entry.z }
    end
  end
  return nodes
end

-- Build undirected edges for node pairs within radius, canonically oriented
-- (a before b by tostring) and sorted by (tostring(a), tostring(b)).
local function buildEdgesFromNodes(nodes, radius)
  local r2 = radius * radius
  local edges = {}
  for i = 1, #nodes do
    for j = i + 1, #nodes do
      local dx = nodes[i].x - nodes[j].x
      local dz = nodes[i].z - nodes[j].z
      local d2 = dx * dx + dz * dz
      if d2 <= r2 then
        local a, b = nodes[i].key, nodes[j].key
        if tostring(a) > tostring(b) then a, b = b, a end
        edges[#edges + 1] = { a = a, b = b, dist = math.sqrt(d2) }
      end
    end
  end
  table.sort(edges, function(x, y)
    local xa, ya = tostring(x.a), tostring(y.a)
    if xa ~= ya then return xa < ya end
    return tostring(x.b) < tostring(y.b)
  end)
  return edges
end

-- Union-find over the valid nodes joined by the given edges.
-- Returns a parent map (fully path-compressed) and a key -> index map.
local function buildUF(nodes, edges)
  local n = #nodes
  local parent, rank, idx = {}, {}, {}
  for i = 1, n do
    parent[i] = i
    rank[i] = 1
    idx[nodes[i].key] = i
  end
  local function find(i)
    local root = i
    while parent[root] ~= root do root = parent[root] end
    while parent[i] ~= i do
      local nxt = parent[i]
      parent[i] = root
      i = nxt
    end
    return root
  end
  for _, e in ipairs(edges) do
    local ia, ib = idx[e.a], idx[e.b]
    if ia and ib then
      local ra, rb = find(ia), find(ib)
      if ra ~= rb then
        if rank[ra] < rank[rb] then ra, rb = rb, ra end
        parent[rb] = ra
        rank[ra] = rank[ra] + rank[rb]
      end
    end
  end
  for i = 1, n do parent[i] = find(i) end
  return parent, idx
end

-- Analyze a roads table once: nodes, edges, UF parent map, key index,
-- component sizes, and per-node degree.
local function analyze(roads, radius)
  local nodes = collectNodes(roads)
  local edges = buildEdgesFromNodes(nodes, normRadius(radius))
  local parent, idx = buildUF(nodes, edges)
  local sizes, deg = {}, {}
  for i = 1, #nodes do deg[i] = 0 end
  for _, e in ipairs(edges) do
    deg[idx[e.a]] = deg[idx[e.a]] + 1
    deg[idx[e.b]] = deg[idx[e.b]] + 1
  end
  for i = 1, #nodes do
    local r = parent[i]
    sizes[r] = (sizes[r] or 0) + 1
  end
  return nodes, edges, parent, idx, sizes, deg
end

-- Array of edges { a, b, dist } linking road nodes within radius, sorted deterministically.
function M.buildEdges(roads, radius)
  local nodes = collectNodes(roads)
  return buildEdgesFromNodes(nodes, normRadius(radius))
end

-- key -> { [neighbourKey] = dist }; isolated valid nodes map to an empty table.
function M.adjacency(roads, radius)
  local nodes, edges = analyze(roads, radius)
  local adj = {}
  for i = 1, #nodes do adj[nodes[i].key] = {} end
  for _, e in ipairs(edges) do
    adj[e.a][e.b] = e.dist
    adj[e.b][e.a] = e.dist
  end
  return adj
end

-- Number of connected components; each isolated valid node counts as its own component.
function M.componentCount(roads, radius)
  local _, _, parent = analyze(roads, radius)
  local count = 0
  for i = 1, #parent do
    if parent[i] == i then count = count + 1 end
  end
  return count
end

-- Array of keys in the same connected component as `key`, sorted by tostring; {} when absent.
function M.componentOf(roads, key, radius)
  local out = {}
  local nodes, _, parent, idx = analyze(roads, radius)
  local i = idx[key]
  if not i then return out end
  local root = parent[i]
  for j = 1, #nodes do
    if parent[j] == root then out[#out + 1] = nodes[j].key end
  end
  table.sort(out, function(a, b) return tostring(a) < tostring(b) end)
  return out
end

-- True when both keys exist and share a component; false when either key is absent.
function M.isConnected(roads, keyA, keyB, radius)
  local _, _, parent, idx = analyze(roads, radius)
  local ia, ib = idx[keyA], idx[keyB]
  if not ia or not ib then return false end
  return parent[ia] == parent[ib]
end

-- True when the planar point (x, z) lies within radius of at least one valid road node.
function M.connectedToNetwork(roads, x, z, radius)
  if not finiteNum(x) or not finiteNum(z) then return false end
  local nodes = collectNodes(roads)
  local r = normRadius(radius)
  local r2 = r * r
  for i = 1, #nodes do
    local dx = x - nodes[i].x
    local dz = z - nodes[i].z
    if dx * dx + dz * dz <= r2 then return true end
  end
  return false
end

-- Aggregate network statistics: nodes, edges, components, isolated, largest.
function M.networkSummary(roads, radius)
  local nodes, edges, parent, _, sizes, deg = analyze(roads, radius)
  local components, isolated, largest = 0, 0, 0
  for i = 1, #nodes do
    if deg[i] == 0 then isolated = isolated + 1 end
  end
  for _, sz in pairs(sizes) do
    components = components + 1
    if sz > largest then largest = sz end
  end
  return {
    nodes = #nodes,
    edges = #edges,
    components = components,
    isolated = isolated,
    largest = largest,
  }
end

return M
