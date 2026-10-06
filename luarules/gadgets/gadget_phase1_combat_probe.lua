function gadget:GetInfo()
  return { name = "Phase 1 Combat Probe", desc = "Opt-in observer: damage, deaths, and per-frame front status",
    author = "Medieval-BAR-TC", license = "GPL-v2", layer = 1000, enabled = true }
end

if not gadgetHandler:IsSyncedCode() then return end
local options = Spring.GetModOptions() or {}
local enabled = options.medievaltest == true or options.medievaltest == 1 or options.medievaltest == "1"
if not enabled then return end

local damageCount = 0
local damageLogged = 0
local damageMaxLogs = 10
local destroyed = 0
local destroyedMaxLogs = 20

local function teamStats(teamID)
  local count, health = 0, 0
  for _, uid in ipairs(Spring.GetTeamUnits(teamID) or {}) do
    local hp = Spring.GetUnitHealth(uid)
    if hp and hp > 0 then count = count + 1; health = health + hp end
  end
  return count, health
end

local function minInterTeam(a, b)
  local ua, ub = Spring.GetTeamUnits(a) or {}, Spring.GetTeamUnits(b) or {}
  if #ua == 0 or #ub == 0 then return nil end
  local pos = Spring.GetUnitPosition
  local best
  for _, na in ipairs(ua) do
    local xa, _, za = pos(na)
    if xa then
      for _, nb in ipairs(ub) do
        local xb, _, zb = pos(nb)
        if xb then
          local dx, dz = xa - xb, za - zb
          local d = math.sqrt(dx * dx + dz * dz)
          if not best or d < best then best = d end
        end
      end
    end
  end
  return best
end

local function teamPair()
  local list = Spring.GetTeamList()
  table.sort(list)
  local gaia = Spring.GetGaiaTeamID()
  for i, a in ipairs(list) do
    local _, _, deadA = Spring.GetTeamInfo(a, false)
    if a ~= gaia and not deadA then
      for j = i + 1, #list do
        local b = list[j]
        local _, _, deadB = Spring.GetTeamInfo(b, false)
        if b ~= gaia and not deadB and not Spring.AreTeamsAllied(a, b) then return a, b end
      end
    end
  end
end

local closeSpawned = false
local closePairs = {}
local detailLogs = 0
local detailMaxLogs = 10

local function spawnClosePair(defName, teamA, teamB, x, z, gap)
  local def = UnitDefNames[defName]
  if not def then return end
  local yA = Spring.GetGroundHeight(x, z)
  local yB = Spring.GetGroundHeight(x + gap, z)
  local idA = Spring.CreateUnit(def.id, x, yA, z, "east", teamA)
  local idB = Spring.CreateUnit(def.id, x + gap, yB, z, "west", teamB)
  if idA and idB then
    Spring.GiveOrderToUnit(idA, CMD.ATTACK, { idB }, 0)
    Spring.GiveOrderToUnit(idB, CMD.ATTACK, { idA }, 0)
    Spring.GiveOrderToUnit(idA, CMD.FIRE_STATE, { 2 }, 0)
    Spring.GiveOrderToUnit(idB, CMD.FIRE_STATE, { 2 }, 0)
    closePairs[#closePairs + 1] = { defName = defName, idA = idA, idB = idB, x = x, z = z, gap = gap }
    Spring.Echo(string.format("COMBAT PROBE close pair %s A=%d B=%d gap=%d at %d,%d", defName, idA, idB, gap, x, z))
  end
end

local function logCloseDetail(frame)
  local p0 = closePairs[1]
  if p0 then
    local okD, descs = pcall(Spring.GetUnitCmdDescs, p0.idA)
    local canAtt = "?"
    if okD and type(descs) == "table" then
      canAtt = "false"
      for i = 1, #descs do
        local cd = descs[i]
        if type(cd) == "table" and cd.id == CMD.ATTACK then canAtt = "true" break end
      end
    end
    Spring.Echo(string.format("COMBAT CMDDESC f=%d unit=%d cmddesc.attack=%s", frame, p0.idA, canAtt))
  end
  for pi, p in ipairs(closePairs) do
    for _, uid in ipairs({ p.idA, p.idB }) do
      local tgt = "nil"
      local ok, res = pcall(Spring.GetUnitWeaponTarget, uid, 1)
      if ok then tgt = tostring(res) end
      local reload, rng = "call-fail", "call-fail"
      local ok2, st = pcall(Spring.GetUnitWeaponState, uid, 1)
      if ok2 and type(st) == "table" then
        reload = tostring(st.reloadState)
        rng = tostring(st.range)
      end
      local attack = "call-fail"
      local ok3, cmds = pcall(Spring.GetUnitCommands, uid)
      if ok3 and type(cmds) == "table" then
        attack = "false"
        for i = 1, #cmds do
          local c = cmds[i]
          if type(c) == "table" and c.id == CMD.ATTACK then attack = "true" break end
        end
      end
      local proj = "?"
      local ok4, pv = pcall(Spring.GetProjectilesInRectangle, p.x - 60, p.z - 60, p.x + p.gap + 60, p.z + 60)
      if ok4 and type(pv) == "number" then proj = tostring(pv) end
      Spring.Echo(string.format("COMBAT DETAIL f=%d pair=%s unit=%d tgt=%s reload=%s range=%s attack=%s proj=%s",
        frame, p.defName, uid, tgt, reload, rng, attack, proj))
    end
  end
end

function gadget:Initialize()
  local a, b = teamPair()
  if a then
    Spring.Echo(string.format("COMBAT PROBE init teams=%s,%s", tostring(a), tostring(b)))
  else
    Spring.Echo("COMBAT PROBE init no opposing teams")
  end
  -- Diagnostic: confirm weapon defs are registered and attached to unit defs.
  local ok = pcall(function()
    local names = {}
    for i = 0, 15 do
      local wd = WeaponDefs[i]
      if wd then names[#names + 1] = tostring(wd.name) end
    end
    Spring.Echo("COMBAT PROBE WeaponDefs [" .. table.concat(names, ",") .. "]")
    for _, dn in ipairs({ "medieval_infantry", "medieval_archer", "medieval_cavalry" }) do
      local ud = UnitDefNames and UnitDefNames[dn]
      if ud then
        local parts = { "def=" .. dn }
        local wes = ud.weapons
        if wes and type(wes) == "table" then
          for i = 1, #wes do
            local w = wes[i]
            if type(w) == "table" then
              local wdt = w.weaponDef
              local nm = "?"
              if type(wdt) == "number" then nm = tostring(WeaponDefs[wdt] and WeaponDefs[wdt].name or "?") end
              if type(wdt) == "table" or type(wdt) == "userdata" then nm = tostring(wdt.name or "?") end
              parts[#parts + 1] = string.format("w%d=%s(def=%s,wd=%s)", i, tostring(w.name or nm), tostring(w.def), tostring(wdt))
            else
              parts[#parts + 1] = string.format("w%d=%s", i, tostring(w))
            end
          end
        else
          parts[#parts + 1] = "weapons=" .. tostring(wes)
        end
        Spring.Echo("COMBAT PROBE " .. table.concat(parts, " "))
      end
    end
  end)
  if not ok then Spring.Echo("COMBAT PROBE weapon dump failed") end
  -- Ask the engine to watch the three real weapon types so AimWeapon/FireWeapon
  -- events are raised for them (Recoil may not raise LUS aim/fire otherwise).
  do
    local watchNames = { sword = true, longbow = true, lance = true }
    for wd = 0, 31 do
      local def = WeaponDefs[wd]
      if def and watchNames[def.name] then
        local okW = pcall(Script.SetWatchWeapon, wd, true)
        Spring.Echo(string.format("WATCH SETWATCHWEAPON wd=%d name=%s ok=%s",
          wd, tostring(def.name), tostring(okW)))
      end
    end
  end
end

local watchCheckLogs = 0
local watchTargetLogs = 0

local function tostr(v)
  if v == nil then return "nil" end
  if type(v) == "boolean" then return v and "true" or "false" end
  return tostring(v)
end

-- Engine dispatch order (LuaHandleSynced.cpp:1824-1834): attackerID, targetID, weaponNum(1-based), weaponDefID [, priority]
function gadget:AllowWeaponTargetCheck(attackerID, attackerWeaponNum, attackerWeaponDefID)
  if watchCheckLogs < 6 then
    watchCheckLogs = watchCheckLogs + 1
    Spring.Echo(string.format("WATCH TGT attacker=%s target=%s wn=%s wd=%s kind=CHECK",
      tostr(attackerID), "nil", tostr(attackerWeaponNum), tostr(attackerWeaponDefID)))
  end
  return true
end

function gadget:AllowWeaponTarget(attackerID, targetID, attackerWeaponNum, attackerWeaponDefID, targetPriority)
  if watchTargetLogs < 6 then
    watchTargetLogs = watchTargetLogs + 1
    Spring.Echo(string.format("WATCH TGT attacker=%s target=%s wn=%s wd=%s kind=TARGET prio=%s",
      tostr(attackerID), tostr(targetID), tostr(attackerWeaponNum), tostr(attackerWeaponDefID), tostr(targetPriority)))
  end
  return true, targetPriority
end

function gadget:UnitDamaged(unitID, unitDefID, unitTeam, damage, paralyzer, weaponDefID, attackerID, attackerDefID, attackerTeam)
  if not damage or damage <= 0 then return end
  damageCount = damageCount + 1
  if damageLogged < damageMaxLogs then
    damageLogged = damageLogged + 1
    local attacker = "nil"
    if attackerID then
      local ad = attackerDefID and UnitDefs[attackerDefID] and UnitDefs[attackerDefID].name or "?"
      attacker = string.format("%d(%s,t%d)", attackerID, ad, tostring(attackerTeam))
    end
    local ud = unitDefID and UnitDefs[unitDefID] and UnitDefs[unitDefID].name or "?"
    Spring.Echo(string.format("COMBAT PROBE UnitDamaged #%d unit=%d(%s,t%d) dmg=%.1f attacker=%s weapon=%s",
      damageCount, unitID, ud, tostring(unitTeam), damage, attacker, tostring(weaponDefID)))
  end
end

function gadget:UnitDestroyed(unitID, unitDefID, teamID, attackerID, attackerDefID, attackerTeam)
  destroyed = destroyed + 1
  if destroyed <= destroyedMaxLogs then
    local attacker = "nil"
    if attackerID then
      local ad = attackerDefID and UnitDefs[attackerDefID] and UnitDefs[attackerDefID].name or "?"
      attacker = string.format("%d(%s,t%d)", attackerID, ad, tostring(attackerTeam))
    end
    local ud = unitDefID and UnitDefs[unitDefID] and UnitDefs[unitDefID].name or "?"
    Spring.Echo(string.format("COMBAT PROBE UnitDestroyed #%d unit=%d(%s,t%d) attacker=%s",
      destroyed, unitID, ud, tostring(teamID), attacker))
  end
end

function gadget:GameFrame(frame)
  if not closeSpawned and frame >= 120
     and UnitDefNames.medieval_infantry and UnitDefNames.medieval_archer then
    closeSpawned = true
    local a, b = teamPair()
    if a and b then
      -- Deterministic in-range combat: sword pair inside SWORD range 45 and
      -- longbow pair inside LONGBOW range 380, mutually attacking. Guarantees
      -- damage and a kill well before the 25 s / 750-frame window closes.
      spawnClosePair("medieval_infantry", a, b, 5200, 3584, 40)
      spawnClosePair("medieval_archer", a, b, 5560, 3584, 160)
    end
  end
  if frame % 30 == 0 and #closePairs > 0 and detailLogs < detailMaxLogs then
    detailLogs = detailLogs + 1
    logCloseDetail(frame)
  end
  if frame % 60 ~= 0 then return end
  local a, b = teamPair()
  if not a then Spring.Echo(string.format("COMBAT PROBE frame=%d total=0 damaged=%d destroyed=%d", frame, damageCount, destroyed)) return end
  local ca, ha = teamStats(a)
  local cb, hb = teamStats(b)
  local minD = minInterTeam(a, b)
  Spring.Echo(string.format("COMBAT PROBE frame=%d teamsA=%d teamsB=%d healthA=%d healthB=%d minDist=%s damaged=%d destroyed=%d",
    frame, ca, cb, math.floor(ha), math.floor(hb), minD and string.format("%.1f", minD) or "nil", damageCount, destroyed))
end