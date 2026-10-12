-- Lua Unit Script (LUS) for Medieval Catapult (Siege Engine)
-- Uses 0ad model geometry (objects3d/0ad/medieval_catapult.obj, single piece "base")
-- The converted mesh is a static bind-pose hull: there is no separate arm or
-- turret piece, so every weapon call-in resolves to the "base" piece and the
-- Slice 4 arm animation degrades to the same root piece.
--
-- Siege dead zone: this engine build has no weapondef-level minimum-range tag
-- (`minRange` in gamedata/weapondefs.lua is reported as an unknown tag in
-- infolog), so the dead zone is enforced here instead. The catapult refuses to
-- aim at a target closer than MIN_RANGE elmos, which means it never fires
-- point-blank and stays vulnerable to melee units that close the distance.

local MIN_RANGE = 120

local base = piece "base"

-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- optPiece() resolves the optional sub-pieces of a rigged siege mesh and falls
-- back to the root "base" piece on the single-hull converted geometry, and
-- safeCall() keeps every transform best-effort.
local function optPiece(name)
	local ok, p = pcall(piece, name)
	if ok and p then return p end
	return nil
end

local arm = optPiece("arm") or base
local chassis = optPiece("torso") or base
local wheel = optPiece("wheel") or base

-- Spinning the root piece would tumble the whole engine, so wheel rotation is
-- only applied when the mesh really carries a separate wheel piece.
local hasWheel = wheel ~= base

local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

-- Creep/aim arm angle: the arm rests wound back and is drawn further back as
-- the engine takes up the shot.
local ARM_REST, ARM_DRAWN = 0.0, -0.55

local function restPose()
	safeCall(Turn, arm, x_axis, ARM_REST, 4)
	safeCall(Turn, chassis, x_axis, 0, 6)
	safeCall(Turn, chassis, z_axis, 0, 6)
	safeCall(Move, chassis, y_axis, 0, 6)
	safeCall(Turn, base, x_axis, 0, 6)
	safeCall(Turn, base, z_axis, 0, 6)
	safeCall(Move, base, y_axis, 0, 6)
end

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
	restPose()
end

-- == Locomotion: the engine lurches forward and the wheels creep ============
function script.StartMoving()
	Signal(SIG_MOVE)
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		if hasWheel then
			safeCall(Spin, wheel, x_axis, 1.5, 0)
		end
		while true do
			-- Slow siege-creep lurch: nose down, then level again.
			safeCall(Turn, chassis, x_axis, 0.05, 10)
			safeCall(Move, chassis, y_axis, 0.6, 12)
			Sleep(300)
			safeCall(Turn, chassis, x_axis, 0.0, 10)
			safeCall(Move, chassis, y_axis, 0.0, 12)
			Sleep(300)
		end
	end)
end

function script.StopMoving()
	Signal(SIG_MOVE)
	if hasWheel then
		safeCall(StopSpin, wheel, x_axis)
	end
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
	-- Winch the arm back onto the shot; the release is fired in FireWeapon1.
	safeCall(Turn, arm, x_axis, ARM_DRAWN, 8)
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
	-- Arm swing-and-stop: fling the arm past the stop, let the chassis absorb
	-- the recoil, then wind the arm back down to rest.
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		safeCall(Turn, arm, x_axis, 0.85, 2)
		safeCall(Turn, chassis, x_axis, 0.10, 4)
		Sleep(150)
		-- The stop arrests the arm; the whole engine rocks back on its wheels.
		safeCall(Turn, arm, x_axis, 0.62, 12)
		safeCall(Turn, base, x_axis, -0.07, 8)
		Sleep(260)
		safeCall(Turn, base, x_axis, 0, 8)
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
	if not targetBeyondDeadZone() then
		return false
	end
	publish("medieval_catapult_aiming", 1)
	safeCall(Turn, arm, x_axis, ARM_DRAWN, 8)
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
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		safeCall(Turn, arm, x_axis, 0.85, 2)
		safeCall(Turn, chassis, x_axis, 0.10, 4)
		Sleep(150)
		safeCall(Turn, arm, x_axis, 0.62, 12)
		safeCall(Turn, base, x_axis, -0.07, 8)
		Sleep(260)
		safeCall(Turn, base, x_axis, 0, 8)
		restPose()
	end)
end

-- == Defeat: the engine sheds an axle and slews onto its side ================
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	if hasWheel then
		safeCall(StopSpin, wheel, x_axis)
	end
	safeCall(Turn, arm, x_axis, -0.4, 4)
	Sleep(160)
	safeCall(Turn, base, z_axis, 0.95, 3)
	safeCall(Turn, chassis, z_axis, 0.95, 3)
	safeCall(Move, base, y_axis, -3.0, 2)
	safeCall(Move, chassis, y_axis, -3.0, 2)
	Sleep(320)
	return 1
end
