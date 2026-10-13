-- Lua Unit Script (LUS) for Medieval Cavalry (Fast Melee / Charge)
-- Uses 0ad model geometry (objects3d/0ad/medieval_cavalry.obj, single piece "base")
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted mesh is a single hull, so optPiece() degrades to the root "base"
-- piece and safeCall() makes every transform best-effort.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (spawn the loop with
--   StartThread); Create / Killed / AimWeapon / FireWeapon ARE thread-wrapped,
--   so Killed may Sleep in its body to hold the collapse.

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

-- Gallop: a deeper, slower rock than the infantry stride, plus a lift on the
-- beat where the horse is airborne.
local GALLOP = {
	{ pitch = 0.09, roll = 0.06, lift = 2.0 },
	{ pitch = 0.0, roll = 0.0, lift = 0.6 },
	{ pitch = -0.07, roll = -0.06, lift = 0.0 },
	{ pitch = 0.0, roll = 0.0, lift = 0.6 },
}

local function restPose()
	safeCall(Turn, torso, x_axis, 0, 6)
	safeCall(Turn, torso, z_axis, 0, 6)
	safeCall(Move, torso, y_axis, 0, 6)
	safeCall(Turn, base, x_axis, 0, 6)
	safeCall(Turn, base, z_axis, 0, 6)
	safeCall(Move, base, y_axis, 0, 6)
	safeCall(Move, weapon, z_axis, 0, 6)  -- retract the weapon after a swing
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

-- == Locomotion: gallop rock, roll and airborne lift ========================
function script.StartMoving()
	Signal(SIG_MOVE)
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		local phase = 1
		while true do
			local beat = GALLOP[phase]
			safeCall(Turn, torso, x_axis, beat.pitch, 6)
			safeCall(Turn, torso, z_axis, beat.roll, 6)
			safeCall(Move, torso, y_axis, beat.lift, 10)
			phase = phase % #GALLOP + 1
			Sleep(160)
		end
	end)
end

function script.StopMoving()
	Signal(SIG_MOVE)
	restPose()
end

-- == Combat: lowered lance on the aim line, couched thrust on fire ==========
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM cavalry w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- A couched lance sits low: bias the torso forward rather than onto the
	-- raw aim pitch.
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.4 + 0.08, 5)
	return true
end

function script.FireWeapon1()
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE cavalry w1")
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		-- Gather, drive the lance through, then settle back into the saddle.
		safeCall(Move, weapon, z_axis, -1.2, 12)
		safeCall(Turn, torso, x_axis, -0.10, 10)
		Sleep(100)
		safeCall(Move, weapon, z_axis, 3.0, 24)
		safeCall(Turn, torso, x_axis, 0.26, 24)
		Sleep(120)
		safeCall(Turn, base, x_axis, -0.12, 10)
		Sleep(80)
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
		say(string.format("LUS AIM cavalry w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.4 + 0.08, 5)
	return true
end

function script.FireWeapon(weaponNum)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say(string.format("LUS FIRE cavalry w%d [unnum]", weaponNum or 0))
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		safeCall(Move, weapon, z_axis, -1.2, 12)
		safeCall(Turn, torso, x_axis, -0.10, 10)
		Sleep(100)
		safeCall(Move, weapon, z_axis, 3.0, 24)
		safeCall(Turn, torso, x_axis, 0.26, 24)
		Sleep(120)
		safeCall(Turn, base, x_axis, -0.12, 10)
		Sleep(80)
		restPose()
	end)
end

-- == Defeat: horse breaks down and the rider rolls off ======================
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	-- Rear up first, then go over sideways onto the ground.
	safeCall(Turn, base, x_axis, -0.35, 4)
	safeCall(Turn, torso, x_axis, -0.35, 4)
	Sleep(180)
	safeCall(Turn, base, z_axis, 1.5, 3)
	safeCall(Turn, torso, z_axis, 1.6, 3)
	safeCall(Move, base, y_axis, -3.0, 2)
	safeCall(Move, torso, y_axis, -3.0, 2)
	Sleep(380)
	return 1
end
