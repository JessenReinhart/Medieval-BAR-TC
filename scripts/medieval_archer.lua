-- Lua Unit Script (LUS) for Medieval Archer (Ballistic)
-- Uses local original placeholder geometry (objects3d/medieval_placeholder.obj)

local base = piece "base"
local torso = piece "torso"
local weaponMount = piece "weapon_mount"

function script.Create()
end

function script.AimFromWeapon1()
	return torso
end

function script.QueryWeapon1()
	return weaponMount
end

function script.AimWeapon1(heading, pitch)
	return true
end

function script.FireWeapon1()
end

function script.Killed(recentDamage, maxHealth)
	return 1
end
