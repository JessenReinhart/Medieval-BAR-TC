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

-- Current clip name, declared here because the playback thread and the
-- StartMoving / StopMoving / FireWeapon / Killed call-ins all write it.
local currentClip = "idle"
local lastDrivenClip = nil
-- Set while a one-shot (attack_melee / death) is playing so the persistent
-- walk playback loop pauses instead of overwriting the same pieces.
local animOneShot = false

-- == Baked-clip playback (Phase 7 Slice 12) ==================================
-- scripts/animdata/medieval_archer.lua holds world-space pose frames for
-- walk / run / idle / attack_melee / build / death. scripts/anim_player.lua
-- turns them into Turn/Move calls on the mesh's pieces.
--
-- The bake ships no dedicated ranged or bow clip, so `attack_melee` stands in
-- for the shot: it is the only strike-shaped one-shot in the file. Everything
-- is pcall-wrapped: a build with no filesystem, no bake bundle or no piece
-- call-ins leaves animCtx nil and the procedural cadence below takes over.
local function loadModule(path)
	local inc = include
	if type(inc) ~= "function" then
		return nil, "include unavailable"
	end
	-- include() resolves paths against scripts/ and runs the chunk in this
	-- unit's environment, so drop the scripts/ prefix the callers carry. The
	-- old VFS loader is gone: a VFS chunk executes in the wrong environment.
	local rel = type(path) == "string" and path:gsub("^scripts[/\\]", "") or path
	local ok, value = pcall(inc, rel)
	if not ok then
		return nil, tostring(value)
	end
	if type(value) ~= "table" then
		return nil, "module returned " .. type(value)
	end
	return value
end

local animPlayer, animClips = nil, nil
local animFailReason = nil
do
	local mod, perr = loadModule("scripts/anim_player.lua")
	if type(mod) == "table" then
		animPlayer = mod
		local clips, cerr = loadModule("scripts/animdata/medieval_archer.lua")
		if type(clips) == "table" then
			animClips = clips
		else
			animFailReason = cerr or "clips load failed"
		end
	else
		animFailReason = perr or "anim_player load failed"
	end
end

local animCtx = nil
do
	if animPlayer and type(animClips) == "table" then
		local ctx = animPlayer.new()
		animPlayer.setClips(ctx, animClips)
		animPlayer.setPrimitives(ctx, Turn, Move)
		animPlayer.setSpeed(ctx, 14)
		animPlayer.bindRest(ctx, animClips.idle)

		-- Bind each baked bone name to its exact piece only: one handle per
		-- name and no hull/hip fallback overwrite. Bones the bake names but the
		-- OBJ lacks are skipped, so weapon/shield/greave/helmet can never be
		-- mapped onto hip, and every named bone the static PARTS list omits
		-- (shoulders, neck, hands, fingers, fingertips, helmet) is covered.
		local restFrame = (animClips.idle and animClips.idle.frames
			and animClips.idle.frames[1]) or {}
		local boundAny = false
		for name in pairs(restFrame) do
			local handle = optPiece(name)
			if handle then
				animPlayer.bindPiece(ctx, name, handle)
				boundAny = true
			end
		end
		if not boundAny and base then
			-- Old single-hull fallback: no baked joint piece resolved, so
			-- drive the root hull from the hip channel once.
			animPlayer.bindPiece(ctx, "hip", base)
		end
		animCtx = ctx
	end
end

-- One-time init diagnostic, logged once per unit at chunk scope: proves the
-- baked 0 A.D. clips initialised, or the procedural cadence took over. Uses
-- Spring.Echo when present and no-ops in a bare-Lua test harness.
do
	local spring = type(Spring) == "table" and Spring or nil
	if spring and type(spring.Echo) == "function" then
		if animCtx then
			local n = 0
			for _ in pairs(animClips) do n = n + 1 end
			spring.Echo("MEDIEVAL ANIM baked init unit=" .. tostring(unitID) .. " clips=" .. n)
		else
			spring.Echo("MEDIEVAL ANIM fallback unit=" .. tostring(unitID) .. " reason=" .. tostring(animFailReason or "none"))
		end
	end
end

-- Player slot callbacks, bound once. The driver drains these into safeCall.
local animTurnSlots, animMoveSlots = {}, {}
local animFrames = 0

local function say(msg)
	pcall(function()
		if Spring and Spring.Echo then Spring.Echo(msg) else print(msg) end
	end)
end

do
	if animPlayer then
		-- Rebuild the primitive set against the collector tables.
		local ctx = animCtx
		if ctx then
			animPlayer.setPrimitives(ctx,
				function(handle, axis, value, speed)
					animTurnSlots[#animTurnSlots + 1] = { handle, axis, value, speed }
				end,
				function(handle, axis, value, speed)
					animMoveSlots[#animMoveSlots + 1] = { handle, axis, value, speed }
				end)
		end
	end
end

local function driveClip(clipName, dtMs)
	if not animCtx then return 0 end
	-- The player keeps one shared clock, so a clip's timeline only resets when
	-- the switch actually changes clip; restarting a one-shot from zero would
	-- otherwise rewind the loop it was layered on top of.
	if lastDrivenClip ~= clipName then
		animPlayer.reset(animCtx)
		lastDrivenClip = clipName
	elseif animPlayer.elapsed(animCtx, clipName) > 100000 then
		animPlayer.reset(animCtx)  -- wrap the accumulating clock, never diverge
	end
	for i = #animTurnSlots, 1, -1 do animTurnSlots[i] = nil end
	for i = #animMoveSlots, 1, -1 do animMoveSlots[i] = nil end

	local driven, done = animPlayer.emit(animCtx, clipName, animPlayer.elapsed(animCtx, clipName))
	for i = 1, #animTurnSlots do
		local s = animTurnSlots[i]
		safeCall(Turn, s[1], s[2], s[3], s[4])
	end
	for i = 1, #animMoveSlots do
		local s = animMoveSlots[i]
		safeCall(Move, s[1], s[2], s[3], s[4])
	end
	animPlayer.advance(animCtx, dtMs)

	if driven > 0 then
		animFrames = animFrames + 1
		if animFrames <= 5 then
			say(string.format("LUS ANIM archer %s driven=%d", clipName, driven))
		end
	end
	return driven, done
end

-- One playback thread per unit; StartMoving spawns it. Signal(SIG_MOVE) inside
-- StartMoving/StopMoving already cancels any prior loop, so at most one survives;
-- dropping the liveness flag lets the baked walk respawn after a stop.
local function startAnimThread()
	if not animCtx then return false end
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		while true do
			if not animOneShot then
				driveClip(currentClip, 33)
			end
			Sleep(1)
		end
	end)
	return true
end

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
	if animCtx and animCtx.pieces then
		for _, p in pairs(animCtx.pieces) do
			safeCall(Turn, p, x_axis, 0, 6)
			safeCall(Turn, p, y_axis, 0, 6)
			safeCall(Turn, p, z_axis, 0, 6)
			safeCall(Move, p, x_axis, 0, 6)
			safeCall(Move, p, y_axis, 0, 6)
			safeCall(Move, p, z_axis, 0, 6)
		end
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
	-- Primary: the baked `walk` clip, driven by scripts/anim_player.lua on the
	-- playback thread. Fallback: the procedural cadence below, used when the
	-- build ships no bake bundle or no player module. StartMoving is not
	-- thread-wrapped by the framework, so it spawns its own loop here.
	currentClip = "walk"
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		if startAnimThread() then return end
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
	-- StopMoving is not thread-wrapped, so it may only Signal and reset the
	-- pose; the playback thread picks up `idle` on its next tick.
	currentClip = "idle"
	restPose()
end

-- == Combat: bow draw then release ==========================================
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM archer w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- Raise the torso onto the aim line while the bow is held. In baked mode
	-- the playback thread already drives those pieces, so the procedural
	-- lean/yaw stays off to avoid two writers fighting over the same channels.
	if not animCtx then
		local lean = clampLean(pitch)
		local yaw = clampYaw(heading)
		safeCall(Turn, spine, x_axis, lean * 0.4, 5)
		safeCall(Turn, chest, x_axis, lean * 0.6, 5)
		safeCall(Turn, chest, y_axis, yaw, 5)
		safeCall(Turn, head, y_axis, yaw * 0.4, 5)
	end
	return true
end

-- Primary: play the baked melee swing (the stand-in for the shot, as the bake
-- carries no ranged clip). It is a one-shot, but the clock is reset first so
-- consecutive shots restart instead of holding on the last frame.
-- Fallback: the procedural draw / release cadence below.
function script.FireWeapon1()
	if fireEchoes < 3 then
		fireEchoes = fireEchoes + 1
		say("LUS FIRE archer w1")
	end
	Signal(SIG_ATTACK)
	StartThread(function()
		SetSignalMask(SIG_ATTACK)
		if animCtx then
			animOneShot = true
			animPlayer.reset(animCtx)
			while true do
				local _driven, done = driveClip("attack_melee", 33)
				if done then break end
				Sleep(1)
			end
			animPlayer.reset(animCtx)
			restPose()
			animOneShot = false
			return
		end
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
	-- In baked mode the playback thread already drives the chest/spine/head, so
	-- the procedural lean/yaw must stay off to avoid two writers fighting.
	if not animCtx then
		local lean = clampLean(pitch)
		local yaw = clampYaw(heading)
		safeCall(Turn, spine, x_axis, lean * 0.4, 5)
		safeCall(Turn, chest, x_axis, lean * 0.6, 5)
		safeCall(Turn, chest, y_axis, yaw, 5)
		safeCall(Turn, head, y_axis, yaw * 0.4, 5)
	end
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
		if animCtx then
			animOneShot = true
			animPlayer.reset(animCtx)
			while true do
				local _driven, done = driveClip("attack_melee", 33)
				if done then break end
				Sleep(1)
			end
			animPlayer.reset(animCtx)
			restPose()
			animOneShot = false
			return
		end
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
	-- Primary: the baked `death` one-shot, held on its last frame while the
	-- engine waits out the thread. Fallback: the procedural tumble below.
	if animCtx then
		animPlayer.reset(animCtx)
		local drivenTotal = 0
		while true do
			local driven, done = driveClip("death", 33)
			drivenTotal = drivenTotal + (driven or 0)
			if done then break end
			Sleep(1)
		end
		say(string.format("PHASE7 DEATH unit=%s clip=death baked=1 driven=%d",
			tostring(unitID), drivenTotal))
		return 1
	end
	say(string.format("PHASE7 DEATH unit=%s clip=procedural baked=0",
		tostring(unitID)))
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
