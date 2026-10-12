-- Lua Unit Script (LUS) for Medieval Infantry (Melee)
-- Uses 0ad model geometry (objects3d/0ad/medieval_infantry.obj, single piece "base")
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted 0 A.D. mesh is a single bind-pose hull, so every animated part is
-- resolved through optPiece(): a real sub-piece is used when the mesh carries one
-- and the root "base" piece is used when it does not. Every transform goes through
-- safeCall(), so the script also survives an engine build without the piece
-- animation call-ins.
--
-- Threading contract (see luarules/gadgets/unit_script.lua):
--   * StartMoving / StopMoving are NOT thread-wrapped -> the stride loop has to be
--     spawned with StartThread, and StopMoving may only Signal + reset the pose.
--   * Create / Killed / AimWeapon / FireWeapon ARE thread-wrapped -> Killed may
--     Sleep in its own body, which is what makes the engine wait for the tumble.

local base = piece "base"

-- Optional sub-pieces. `piece()` raises for an unknown name, so probe with pcall.
local function optPiece(name)
	local ok, p = pcall(piece, name)
	if ok and p then return p end
	return nil
end

local torso = optPiece("torso") or base
local weapon = optPiece("weapon") or base

-- Piece transforms are best-effort: a missing call-in must never break a callin.
local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

-- One signal mask per animation channel, so a loop cancels only its own work.
local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

-- Stride cycle: pitch / roll / lift per footfall, replayed while the unit walks.
local STRIDE = {
	{ pitch = 0.05, roll = 0.045, lift = 1.0 },
	{ pitch = 0.0, roll = 0.0, lift = 0.0 },
	{ pitch = 0.05, roll = -0.045, lift = 1.0 },
	{ pitch = 0.0, roll = 0.0, lift = 0.0 },
}

-- Back to the bind pose: also the standing stance after a stop.
local function restPose()
	safeCall(Turn, torso, x_axis, 0, 6)
	safeCall(Turn, torso, z_axis, 0, 6)
	safeCall(Move, torso, y_axis, 0, 6)
	safeCall(Turn, base, x_axis, 0, 6)
	safeCall(Turn, base, z_axis, 0, 6)
	safeCall(Move, base, y_axis, 0, 6)
end

-- Clamp an aim pitch so a steep target never tips the model over.
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

-- == Locomotion: stride bob, torso roll, forward lean ========================
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
			Sleep(140)
		end
	end)
end

function script.StopMoving()
	Signal(SIG_MOVE)
	restPose()
end

-- == Combat: aim pitch follow + melee thrust recoil ==========================
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM infantry w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- Lean into the swing; the stride loop owns the same piece while walking and
	-- the last writer of the frame wins, so both stay smooth.
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.5, 4)
	return true
end

function script.FireWeapon1()
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE infantry w1")
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		-- Wind-up, thrust, recover.
		safeCall(Turn, torso, x_axis, 0.22, 14)
		safeCall(Move, weapon, z_axis, 2.2, 20)
		Sleep(90)
		safeCall(Turn, torso, x_axis, -0.06, 10)
		safeCall(Move, weapon, z_axis, -0.4, 14)
		Sleep(110)
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
		say(string.format("LUS AIM infantry w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	safeCall(Turn, torso, x_axis, clampLean(pitch) * 0.5, 4)
	return true
end

function script.FireWeapon(weaponNum)
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say(string.format("LUS FIRE infantry w%d [unnum]", weaponNum or 0))
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		safeCall(Turn, torso, x_axis, 0.22, 14)
		safeCall(Move, weapon, z_axis, 2.2, 20)
		Sleep(90)
		safeCall(Turn, torso, x_axis, -0.06, 10)
		safeCall(Move, weapon, z_axis, -0.4, 14)
		Sleep(110)
		restPose()
	end)
end

-- == Defeat: topple sideways onto the ground, then settle ====================
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	safeCall(Turn, base, z_axis, 1.35, 3)
	safeCall(Turn, torso, z_axis, 1.35, 3)
	safeCall(Move, base, y_axis, -1.5, 2)
	safeCall(Move, torso, y_axis, -1.5, 2)
	Sleep(360)
	safeCall(Turn, base, x_axis, 0.7, 2)
	safeCall(Turn, torso, x_axis, 0.7, 2)
	Sleep(240)
	return 1
end
