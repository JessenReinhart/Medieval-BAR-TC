-- Lua Unit Script (LUS) for Medieval Archer (Ballistic)
-- Uses 0ad model geometry (objects3d/0ad/medieval_archer.obj, single piece "base")
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- Single-hull mesh: optPiece() falls back to the root "base" piece for every
-- animated part, and safeCall() keeps each transform best-effort so the script
-- still runs on an engine build without piece animation call-ins.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (loop must be spawned with
--   StartThread); Create / Killed / AimWeapon / FireWeapon ARE, so Killed can
--   Sleep in its own body to hold the model in its death tumble.

local base = piece "base"

local function optPiece(name)
	local ok, p = pcall(piece, name)
	if ok and p then return p end
	return nil
end

local torso = optPiece("torso") or base
local weapon = optPiece("weapon") or base

local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

-- Lighter, quicker gait than the melee infantry: archers jog at range.
local STRIDE = {
	{ pitch = 0.035, roll = 0.03, lift = 0.7 },
	{ pitch = 0.0, roll = 0.0, lift = 0.0 },
	{ pitch = 0.035, roll = -0.03, lift = 0.7 },
	{ pitch = 0.0, roll = 0.0, lift = 0.0 },
}

local function restPose()
	safeCall(Turn, torso, x_axis, 0, 6)
	safeCall(Turn, torso, z_axis, 0, 6)
	safeCall(Move, torso, y_axis, 0, 6)
	safeCall(Turn, base, x_axis, 0, 6)
	safeCall(Turn, base, z_axis, 0, 6)
	safeCall(Move, base, y_axis, 0, 6)
end

local function clampLean(pitch)
	local lean = pitch or 0
	if type(lean) ~= "number" then return 0 end
	if lean > 0.3 then return 0.3 end
	if lean < -0.3 then return -0.3 end
	return lean
end

function script.Create()
	restPose()
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

-- == Locomotion: jog bob with a shallow torso roll ==========================
function script.StartMoving()
	Signal(SIG_MOVE)
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		local phase = 1
		while true do
			local step = STRIDE[phase]
			safeCall(Turn, torso, x_axis, step.pitch, 6)
			safeCall(Turn, torso, z_axis, step.roll, 6)
			safeCall(Move, torso, y_axis, step.lift, 8)
			phase = phase % #STRIDE + 1
			Sleep(120)
		end
	end)
end

function script.StopMoving()
	Signal(SIG_MOVE)
	restPose()
end

-- == Combat: bow draw then release ==========================================
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM archer w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- Raise the torso onto the aim line while the bow is held.
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.6, 5)
	return true
end

function script.FireWeapon1()
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE archer w1")
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		-- Draw: pull the bow arm back and pitch the torso up.
		safeCall(Move, weapon, z_axis, -1.6, 16)
		safeCall(Turn, torso, x_axis, -0.12, 12)
		Sleep(140)
		-- Release: snap forward past the rest pose, then settle.
		safeCall(Move, weapon, z_axis, 1.2, 30)
		safeCall(Turn, torso, x_axis, 0.14, 30)
		Sleep(90)
		restPose()
	end)
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
		say(string.format("LUS AIM archer w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.6, 5)
	return true
end

function script.FireWeapon(weaponNum)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say(string.format("LUS FIRE archer w%d [unnum]", weaponNum or 0))
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		safeCall(Move, weapon, z_axis, -1.6, 16)
		safeCall(Turn, torso, x_axis, -0.12, 12)
		Sleep(140)
		safeCall(Move, weapon, z_axis, 1.2, 30)
		safeCall(Turn, torso, x_axis, 0.14, 30)
		Sleep(90)
		restPose()
	end)
end

-- == Defeat: fall backward off the aim line ==================================
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	safeCall(Turn, base, x_axis, -1.35, 3)
	safeCall(Turn, torso, x_axis, -1.35, 3)
	safeCall(Move, base, y_axis, -1.2, 2)
	safeCall(Move, torso, y_axis, -1.2, 2)
	Sleep(360)
	safeCall(Turn, base, z_axis, 0.5, 2)
	safeCall(Turn, torso, z_axis, 0.5, 2)
	Sleep(240)
	return 1
end
