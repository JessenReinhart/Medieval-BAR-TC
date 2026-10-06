function gadget:GetInfo()
  return {
    name = "Phase 1 WeaponState Probe (unsynced)",
    desc = "Opt-in unsynced observer: raw weapon-state signatures during combat",
    author = "Medieval-BAR-TC",
    license = "GPL-v2",
    layer = 500,
    enabled = true,
  }
end

if gadgetHandler:IsSyncedCode() then return end
local options = Spring.GetModOptions() or {}
local enabled = options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1"
if not enabled then return end

local function val2str(v, depth)
  depth = depth or 0
  local tv = type(v)
  if v == nil then return "nil" end
  if tv == "boolean" then return v and "true" or "false" end
  if tv == "number" or tv == "string" then return tostring(v) end
  if tv == "table" then
    if depth > 1 then return "table:" .. tostring(v) end
    local keys, n = {}, 0
    for k in pairs(v) do n = n + 1; keys[n] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local parts = {}
    for i, k in ipairs(keys) do
      if i <= 14 then
        parts[#parts + 1] = tostring(k) .. "=" .. val2str(v[k], depth + 1)
      end
    end
    return "{" .. table.concat(parts, ",") .. (n > 14 and ",..." or "") .. "}"
  end
  return tostring(v)
end

local function packStr(p)
  local parts = {}
  for i = 1, p.n do
    parts[i] = val2str(p[i])
  end
  return table.concat(parts, "|")
end

local function callRaw(fn, ...)
  return packStr(table.pack(pcall(fn, ...)))
end

local function hasWeaponTarget(uid)
  local ok, a = pcall(Spring.GetUnitWeaponTarget, uid, 1)
  if not ok or a == nil or a == false then return false end
  if type(a) == "number" then return a > 0 end
  return true
end

-- Prefer units that CURRENTLY hold a weapon target (the fighting close pairs),
-- topping up with any unit of that def only after targeters are exhausted.
local function sampleUnits(defName, max)
  local targeters, others = {}, {}
  local all = Spring.GetAllUnits() or {}
  for _, uid in ipairs(all) do
    local udid = Spring.GetUnitDefID(uid)
    if udid and UnitDefs[udid] and UnitDefs[udid].name == defName then
      if hasWeaponTarget(uid) then
        if #targeters < max then targeters[#targeters + 1] = uid end
      elseif #others < max then
        others[#others + 1] = uid
      end
    end
  end
  local out = {}
  for _, uid in ipairs(targeters) do
    out[#out + 1] = uid
  end
  local i = 1
  while #out < max and i <= #others do
    out[#out + 1] = others[i]
    i = i + 1
  end
  return out
end

local WSTATE_FIELDS = {
  "range", "reloadTime", "reloadtime", "reloadState", "reloadstate",
  "reloaded", "ready", "accuracy", "sprayAngle", "haveTarget", "angleGood",
  "ammo", "shots", "salvoLeft", "weaponDef", "mainDir", "maxAngleDif",
  "projectileSpeed", "targetable",
}

local function dumpWeapon(frame, defName, uid, wnum)
  local stPack = table.pack(pcall(Spring.GetUnitWeaponState, uid, wnum))
  -- Label the raw scalars from the 2-arg generic getter: s0=pcall-ok, s1..sN = unnamed returns.
  local scalarParts = {}
  for i = 1, stPack.n do
    scalarParts[i] = "s" .. (i - 1) .. "=" .. val2str(stPack[i])
  end
  -- Authoritative target for the 3-arg test-range read (engine requires a targetID).
  local tgtOk, tgtA, tgtB = pcall(Spring.GetUnitWeaponTarget, uid, wnum)
  local targetID = 0
  if tgtOk then
    if type(tgtB) == "number" and tgtB > 0 then
      targetID = tgtB
    elseif type(tgtA) == "number" and tgtA > 0 then
      targetID = tgtA
    end
  end
  local range, reload = "nil", "nil"
  local stOk, st = stPack[1], stPack[2]
  if stOk and type(st) == "table" then
    range = val2str(st.range)
    reload = val2str(st.reloadState)
  elseif not stOk then
    range = "CALLFAIL:" .. tostring(st)
    reload = "CALLFAIL:" .. tostring(st)
  end
  Spring.Echo(string.format(
    "WSTATE f=%d def=%s unit=%d wnum=%d canFire=%s range=%s reload=%s los=%s testRange=%s tgt=%s state=%s scalars=%s",
    frame, defName, uid, wnum,
    callRaw(Spring.GetUnitWeaponCanFire, uid, wnum),
    range,
    reload,
    callRaw(Spring.GetUnitWeaponHaveFreeLineOfFire, uid, wnum),
    callRaw(Spring.GetUnitWeaponTestRange, uid, wnum, targetID),
    tostring(targetID),
    packStr(stPack),
    table.concat(scalarParts, " ")))
  -- Authoritative 3-arg field reads: reveal valid field names AND live values in one shot.
  local fparts = {}
  for _, f in ipairs(WSTATE_FIELDS) do
    fparts[#fparts + 1] = f .. "=" .. callRaw(Spring.GetUnitWeaponState, uid, wnum, f)
  end
  Spring.Echo(string.format("WSTATE3 f=%d def=%s unit=%d wnum=%d %s",
    frame, defName, uid, wnum, table.concat(fparts, " ")))
  -- Resolve GetUnitWeaponHaveFreeLineOfFire's real signature: it returned VOID
  -- for the 2-arg (uid,wnum) shape. Try several arg shapes and echo each raw return.
  Spring.Echo(string.format("LOSX f=%d def=%s unit=%d shape=%s raw=%s",
    frame, defName, uid, "1", callRaw(Spring.GetUnitWeaponHaveFreeLineOfFire, uid, wnum)))
  Spring.Echo(string.format("LOSX f=%d def=%s unit=%d shape=%s raw=%s",
    frame, defName, uid, "1,0", callRaw(Spring.GetUnitWeaponHaveFreeLineOfFire, uid, wnum, 0)))
  Spring.Echo(string.format("LOSX f=%d def=%s unit=%d shape=%s raw=%s",
    frame, defName, uid, "1,true", callRaw(Spring.GetUnitWeaponHaveFreeLineOfFire, uid, wnum, true)))
  -- Salvo + dam/vec field reads (pcall-echo via 3-arg getter), plus the raw packed
  -- GetUnitWeaponDamages / GetUnitWeaponVectors returns.
  Spring.Echo(string.format("SALVO f=%d def=%s unit=%d salvoSize=%s salvoLeft=%s salvoDelay=%s pps=%s rs=%s rt=%s rng=%s acc=%s spA=%s",
    frame, defName, uid,
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "salvoSize"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "salvoLeft"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "salvoDelay"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "projectilesPerShot"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "reloadState"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "reloadTime"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "range"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "accuracy"),
    callRaw(Spring.GetUnitWeaponState, uid, wnum, "sprayAngle")))
  Spring.Echo(string.format("WDAM f=%d def=%s unit=%d %s",
    frame, defName, uid, callRaw(Spring.GetUnitWeaponDamages, uid, wnum)))
  Spring.Echo(string.format("WVEC f=%d def=%s unit=%d %s",
    frame, defName, uid, callRaw(Spring.GetUnitWeaponVectors, uid, wnum)))
end

local defsWanted = { medieval_infantry = true, medieval_archer = true }

function gadget:GameFrame(frame)
  if frame > 360 or frame % 60 ~= 0 then return end
  for defName in pairs(defsWanted) do
    for _, uid in ipairs(sampleUnits(defName, 4)) do
      dumpWeapon(frame, defName, uid, 1)
    end
  end
end