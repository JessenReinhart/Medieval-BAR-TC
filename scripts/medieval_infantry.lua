-- Lua Unit Script (LUS) for Medieval Infantry (Melee)
-- Uses 0ad model geometry (objects3d/0ad/medieval_infantry.obj, single piece "base")

local base = piece "base"

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

function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM infantry w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	return true
end

function script.FireWeapon1()
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE infantry w1")
	end
end

function script.AimFromWeapon(weaponNum)
	return base
end

function script.QueryWeapon(weaponNum)
	return base
end

function script.AimWeapon(weaponNum, heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM infantry w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	return true
end

function script.FireWeapon(weaponNum)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say(string.format("LUS FIRE infantry w%d [unnum]", weaponNum or 0))
	end
end

function script.Killed(recentDamage, maxHealth)
	return 1
end