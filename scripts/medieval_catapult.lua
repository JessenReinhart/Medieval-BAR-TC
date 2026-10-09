-- Lua Unit Script (LUS) for Medieval Catapult (Siege Engine)
-- Uses 0ad model geometry (objects3d/0ad/medieval_catapult.obj, single piece "base")
-- The converted mesh is a static bind-pose hull: there is no separate arm or
-- turret piece, so every weapon call-in resolves to the "base" piece.
--
-- Siege dead zone: this engine build has no weapondef-level minimum-range tag
-- (`minRange` in gamedata/weapondefs.lua is reported as an unknown tag in
-- infolog), so the dead zone is enforced here instead. The catapult refuses to
-- aim at a target closer than MIN_RANGE elmos, which means it never fires
-- point-blank and stays vulnerable to melee units that close the distance.

local MIN_RANGE = 120

local base = piece "base"

-- Distance in elmos from this unit to its current weapon-1 target, or nil when
-- the target cannot be observed (no target, or an unsupported engine call).
local function weaponTargetDistance()
	if type(Spring.GetUnitWeaponTarget) ~= "function"
		or type(Spring.GetUnitPosition) ~= "function" then
		return nil
	end
	local ok, a, b = pcall(Spring.GetUnitWeaponTarget, unitID, 1)
	if not ok then return nil end
	-- Documented shape is (targetType, targetID); accept the id in either slot.
	local targetID = nil
	if type(b) == "number" and b > 0 then targetID = b
	elseif type(a) == "number" and a > 0 then targetID = a end
	if not targetID then return nil end
	local pok, ux, _, uz = pcall(Spring.GetUnitPosition, unitID)
	if not pok or type(ux) ~= "number" or type(uz) ~= "number" then return nil end
	local tok, tx, _, tz = pcall(Spring.GetUnitPosition, targetID)
	if not tok or type(tx) ~= "number" or type(tz) ~= "number" then return nil end
	local dx, dz = tx - ux, tz - uz
	return math.sqrt(dx * dx + dz * dz)
end

-- true when the target is far enough away to be worth shooting at. An
-- unobservable target is treated as in range so combat never silently stalls.
local function targetBeyondDeadZone()
	local distance = weaponTargetDistance()
	if distance == nil then return true end
	return distance >= MIN_RANGE
end

function script.Create()
end

function script.AimFromWeapon1()
	return base
end

function script.QueryWeapon1()
	return base
end

local aimEchoes, fireEchoes = 0, 0
local function say(msg)
	pcall(function()
		if Spring and Spring.Echo then Spring.Echo(msg) else print(msg) end
	end)
end

-- Publish the aim/fire lifecycle as unit rules params. Spring.Echo alone is only
-- visible in the log; a rules param lets a synced probe read the state back
-- deterministically without depending on weapon-state API shapes that vary
-- between engine builds.
local function publish(param, value)
	pcall(function()
		if Spring and Spring.SetUnitRulesParam then
			Spring.SetUnitRulesParam(unitID, param, value)
		end
	end)
end

function script.AimWeapon1(heading, pitch)
	if not targetBeyondDeadZone() then
		publish("medieval_catapult_aiming", 0)
		if aimEchoes < 5 then
			aimEchoes = aimEchoes + 1
			say(string.format("LUS AIM catapult w1 HOLD target inside dead zone %d", MIN_RANGE))
		end
		return false
	end
	publish("medieval_catapult_aiming", 1)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM catapult w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	return true
end

function script.FireWeapon1()
	publish("medieval_catapult_fired", 1)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE catapult w1")
	end
end

function script.AimFromWeapon(weaponNum)
	return base
end

function script.QueryWeapon(weaponNum)
	return base
end

function script.AimWeapon(weaponNum, heading, pitch)
	if not targetBeyondDeadZone() then
		return false
	end
	publish("medieval_catapult_aiming", 1)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM catapult w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	return true
end

function script.FireWeapon(weaponNum)
	publish("medieval_catapult_fired", 1)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say(string.format("LUS FIRE catapult w%d [unnum]", weaponNum or 0))
	end
end

function script.Killed(recentDamage, maxHealth)
	return 1
end
