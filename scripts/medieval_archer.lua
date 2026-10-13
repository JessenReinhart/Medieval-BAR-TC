-- Lua Unit Script (LUS) for Medieval Archer (Ballistic)
-- Uses 0ad model geometry (objects3d/0ad/medieval_archer.obj).
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted 0 A.D. mesh exposes per-bone pieces (hip/spine/chest/..., head,
-- helmet, weapon, quiver, shield) and no "base" hull, so every bone is resolved
-- through optPiece(): the canonical humanoid bone is probed first, then the 0 A.D.
-- alias the OBJ actually carries, and finally the resolved root hull (the hip).
-- safeCall() keeps each transform best-effort, so the script still
-- runs on an engine build without the piece animation call-ins.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (loop must be spawned with
--   StartThread); Create / Killed / AimWeapon / FireWeapon ARE, so Killed can
--   Sleep in its own body to hold the model in its death tumble.

-- Optional sub-pieces. `piece()` raises for an unknown name, so probe with pcall.
local function optPiece(name)
	local ok, p = pcall(piece, name)
	if ok and p then return p end
	return nil
end

-- Root hull. The converted OBJ is articulated (per-bone pieces, no "base" hull),
-- so probe the bones the exporter actually emits, then the engine root name.
local base = optPiece("base") or optPiece("hip") or optPiece("root") or optPiece("spine")
if not base then
	base = optPiece("$$$___magic___$$$.")  -- Recoil model root; nil if not exposed
end

-- == Articulated humanoid rig ================================================
-- canonical bone -> alias the 0 A.D. OBJ may carry -> root hull.
local hip = optPiece("hip") or optPiece("torso") or base
local spine = optPiece("spine") or optPiece("torso") or base
local chest = optPiece("chest") or optPiece("torso") or base
local head = optPiece("head") or optPiece("helmet") or base
local thigh_l = optPiece("thigh_l") or optPiece("l_thigh") or optPiece("l_leg") or base
local leg_l = optPiece("leg_l") or optPiece("l_leg") or base
local foot_l = optPiece("foot_l") or optPiece("l_foot") or base
local thigh_r = optPiece("thigh_r") or optPiece("r_thigh") or optPiece("r_leg") or base
local leg_r = optPiece("leg_r") or optPiece("r_leg") or base
local foot_r = optPiece("foot_r") or optPiece("r_foot") or base
local arm_l = optPiece("arm_l") or optPiece("l_arm") or optPiece("arm") or base
local forearm_l = optPiece("forearm_l") or optPiece("l_forearm") or optPiece("l_arm") or optPiece("arm") or base
local arm_r = optPiece("arm_r") or optPiece("r_arm") or optPiece("arm") or base
local forearm_r = optPiece("forearm_r") or optPiece("r_forearm") or optPiece("r_arm") or optPiece("arm") or base
-- The bow is the weapon piece the converter isolates on the archer hull.
local weapon = optPiece("weapon") or base
local shield = optPiece("shield") or base

-- Distinct resolved pieces only: on a single-hull mesh every bone *is* `base`.
local PARTS = {}
do
	local seen = {}
	local list = {
		hip, spine, chest, head,
		thigh_l, leg_l, foot_l, thigh_r, leg_r, foot_r,
		arm_l, forearm_l, arm_r, forearm_r, weapon, shield,
	}
	for i = 1, #list do
		local p = list[i]
		if p and not seen[p] then
			seen[p] = true
			PARTS[#PARTS + 1] = p
		end
	end
end

local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

local function restPose()
	for i = 1, #PARTS do
		local p = PARTS[i]
		safeCall(Turn, p, x_axis, 0, 6)
		safeCall(Turn, p, y_axis, 0, 6)
		safeCall(Turn, p, z_axis, 0, 6)
		safeCall(Move, p, x_axis, 0, 6)
		safeCall(Move, p, y_axis, 0, 6)
		safeCall(Move, p, z_axis, 0, 6)
	end
end

local function clampLean(pitch)
	local lean = pitch or 0
	if type(lean) ~= "number" then return 0 end
	if lean > 0.3 then return 0.3 end
	if lean < -0.3 then return -0.3 end
	return lean
end

-- Archers traverse further than a melee line, but the chest still only twists.
local function clampYaw(heading)
	local yaw = heading or 0
	if type(yaw) ~= "number" then return 0 end
	if yaw > 0.7 then return 0.7 end
	if yaw < -0.7 then return -0.7 end
	return yaw
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

-- == Locomotion: light jog with a shallow torso roll =========================
-- Lighter and quicker than the melee stride: shorter thigh swing, lower bob.
function script.StartMoving()
	Signal(SIG_MOVE)
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		while true do
			-- Left contact: left thigh forward, bow arm counter-swings.
			safeCall(Turn, thigh_l, x_axis, 0.32, 8)
			safeCall(Turn, leg_l, x_axis, -0.20, 8)
			safeCall(Turn, foot_l, x_axis, 0.10, 8)
			safeCall(Turn, thigh_r, x_axis, -0.32, 8)
			safeCall(Turn, leg_r, x_axis, -0.03, 8)
			safeCall(Turn, foot_r, x_axis, 0.05, 8)
			safeCall(Turn, arm_l, x_axis, -0.22, 8)
			safeCall(Turn, forearm_l, x_axis, -0.10, 8)
			safeCall(Turn, arm_r, x_axis, 0.22, 8)
			safeCall(Turn, forearm_r, x_axis, -0.16, 8)
			safeCall(Turn, chest, x_axis, 0.05, 8)
			safeCall(Turn, spine, z_axis, 0.04, 8)
			safeCall(Move, hip, y_axis, 0.7, 8)
			Sleep(120)
			-- Passing pose.
			safeCall(Turn, thigh_l, x_axis, 0.02, 8)
			safeCall(Turn, leg_l, x_axis, -0.05, 8)
			safeCall(Turn, foot_l, x_axis, 0.0, 8)
			safeCall(Turn, thigh_r, x_axis, -0.02, 8)
			safeCall(Turn, leg_r, x_axis, -0.08, 8)
			safeCall(Turn, foot_r, x_axis, -0.03, 8)
			safeCall(Turn, arm_l, x_axis, 0.0, 8)
			safeCall(Turn, forearm_l, x_axis, -0.04, 8)
			safeCall(Turn, arm_r, x_axis, 0.0, 8)
			safeCall(Turn, forearm_r, x_axis, -0.04, 8)
			safeCall(Turn, chest, x_axis, 0.0, 8)
			safeCall(Turn, spine, z_axis, 0.0, 8)
			safeCall(Move, hip, y_axis, 0.0, 8)
			Sleep(120)
			-- Right contact: mirror.
			safeCall(Turn, thigh_l, x_axis, -0.32, 8)
			safeCall(Turn, leg_l, x_axis, -0.03, 8)
			safeCall(Turn, foot_l, x_axis, 0.05, 8)
			safeCall(Turn, thigh_r, x_axis, 0.32, 8)
			safeCall(Turn, leg_r, x_axis, -0.20, 8)
			safeCall(Turn, foot_r, x_axis, 0.10, 8)
			safeCall(Turn, arm_l, x_axis, 0.22, 8)
			safeCall(Turn, forearm_l, x_axis, -0.16, 8)
			safeCall(Turn, arm_r, x_axis, -0.22, 8)
			safeCall(Turn, forearm_r, x_axis, -0.10, 8)
			safeCall(Turn, chest, x_axis, 0.05, 8)
			safeCall(Turn, spine, z_axis, -0.04, 8)
			safeCall(Move, hip, y_axis, 0.7, 8)
			Sleep(120)
			-- Passing pose again.
			safeCall(Turn, thigh_l, x_axis, -0.02, 8)
			safeCall(Turn, leg_l, x_axis, -0.08, 8)
			safeCall(Turn, foot_l, x_axis, -0.03, 8)
			safeCall(Turn, thigh_r, x_axis, 0.02, 8)
			safeCall(Turn, leg_r, x_axis, -0.05, 8)
			safeCall(Turn, foot_r, x_axis, 0.0, 8)
			safeCall(Turn, arm_l, x_axis, 0.0, 8)
			safeCall(Turn, forearm_l, x_axis, -0.04, 8)
			safeCall(Turn, arm_r, x_axis, 0.0, 8)
			safeCall(Turn, forearm_r, x_axis, -0.04, 8)
			safeCall(Turn, chest, x_axis, 0.0, 8)
			safeCall(Turn, spine, z_axis, 0.0, 8)
			safeCall(Move, hip, y_axis, 0.0, 8)
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
	local lean = clampLean(pitch)
	local yaw = clampYaw(heading)
	safeCall(Turn, spine, x_axis, lean * 0.4, 5)
	safeCall(Turn, chest, x_axis, lean * 0.6, 5)
	safeCall(Turn, chest, y_axis, yaw, 5)
	safeCall(Turn, head, y_axis, yaw * 0.4, 5)
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
		-- Draw: bow arm extends forward, draw hand pulls the string back.
		safeCall(Turn, arm_l, x_axis, 0.45, 14)
		safeCall(Turn, forearm_l, x_axis, 0.12, 14)
		safeCall(Turn, arm_r, x_axis, -0.5, 14)
		safeCall(Turn, forearm_r, x_axis, -0.7, 14)
		safeCall(Turn, chest, x_axis, -0.12, 12)
		safeCall(Move, weapon, z_axis, -1.6, 16)
		Sleep(140)
		-- Release: snap the draw hand forward past the rest pose, then settle.
		safeCall(Turn, arm_r, x_axis, 0.18, 30)
		safeCall(Turn, forearm_r, x_axis, 0.22, 30)
		safeCall(Turn, chest, x_axis, 0.14, 30)
		safeCall(Move, weapon, z_axis, 1.2, 30)
		Sleep(90)
		-- Recoil: the bow drops back onto the aim line.
		safeCall(Turn, arm_l, x_axis, 0.1, 12)
		Sleep(70)
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
	local lean = clampLean(pitch)
	local yaw = clampYaw(heading)
	safeCall(Turn, spine, x_axis, lean * 0.4, 5)
	safeCall(Turn, chest, x_axis, lean * 0.6, 5)
	safeCall(Turn, chest, y_axis, yaw, 5)
	safeCall(Turn, head, y_axis, yaw * 0.4, 5)
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
		safeCall(Turn, arm_l, x_axis, 0.45, 14)
		safeCall(Turn, arm_r, x_axis, -0.5, 14)
		safeCall(Turn, forearm_r, x_axis, -0.7, 14)
		safeCall(Move, weapon, z_axis, -1.6, 16)
		Sleep(140)
		safeCall(Turn, arm_r, x_axis, 0.18, 30)
		safeCall(Move, weapon, z_axis, 1.2, 30)
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
	-- Buckle backwards: the bow arm goes slack and the legs fold under the body.
	safeCall(Turn, thigh_l, x_axis, -0.4, 3)
	safeCall(Turn, thigh_r, x_axis, -0.5, 3)
	safeCall(Turn, leg_l, x_axis, -0.8, 3)
	safeCall(Turn, leg_r, x_axis, -0.7, 3)
	safeCall(Turn, hip, x_axis, -1.35, 3)
	safeCall(Turn, hip, z_axis, 0.5, 3)
	safeCall(Turn, chest, x_axis, -0.35, 3)
	safeCall(Turn, head, x_axis, -0.4, 4)
	safeCall(Turn, arm_l, x_axis, -0.6, 3)
	safeCall(Turn, arm_r, x_axis, 0.7, 3)
	safeCall(Move, hip, y_axis, -1.2, 2)
	safeCall(Move, weapon, z_axis, -0.8, 3)
	Sleep(360)
	-- Settle: the limbs collapse flat and the wreck comes to rest.
	safeCall(Turn, hip, x_axis, -1.5, 2)
	safeCall(Turn, hip, z_axis, 0.65, 2)
	safeCall(Turn, chest, x_axis, -0.15, 2)
	safeCall(Turn, arm_l, x_axis, -0.25, 2)
	safeCall(Turn, arm_r, x_axis, 0.3, 2)
	safeCall(Move, hip, y_axis, -1.5, 2)
	Sleep(240)
	return 1
end