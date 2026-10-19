-- Lua Unit Script (LUS) for Medieval Cavalry (Fast Melee / Charge)
-- Uses 0ad model geometry (objects3d/0ad/medieval_cavalry.obj, 43 per-bone pieces)
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- Phase 7 Slice 10 -- articulated quadruped horse plus mounted rider: a bone
--   chain (root / spine / neck / head / tail, fore and hind limb chains) driven
--   in a diagonal canter, with the rider animated on the saddle bone.
-- The exporter emits the bones but no "base" hull, so optPiece() binds each chain
-- to the emitted piece (the root falls back to spine) and safeCall() makes every
-- transform best-effort: this script also survives a single-hull mesh.
--
-- Threading contract (luarules/gadgets/unit_script.lua):
--   StartMoving / StopMoving are NOT thread-wrapped (spawn the loop with
--   StartThread); Create / Killed / AimWeapon / FireWeapon ARE thread-wrapped,
--   so Killed may Sleep in its body to hold the collapse.

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

-- Rigged horse skeleton, reconciled with the pieces the exporter actually emits
-- (objects3d/0ad/medieval_cavalry.obj: spine/spine1/spine2, neck/neck1/neck2,
-- head, shoulder/upperarm/arm/forearm/hand chains, femur/thigh/leg/shin/foot/
-- hoof chains, tail2..tail7, rider, helmet, weapon). Every bone falls back to the
-- resolved root hull when the mesh does not carry it, so an unknown bone name can
-- never raise from a transform.
local root = optPiece("root") or optPiece("spine") or base
local spine = optPiece("spine") or base
local neck = optPiece("neck") or base
local head = optPiece("head") or base
local tail = optPiece("tail_base") or optPiece("tail2") or optPiece("tail") or base
local l_femur = optPiece("l_femur") or optPiece("l_thigh") or base
local l_thigh = optPiece("l_thigh") or base
local l_leg = optPiece("l_leg") or optPiece("l_shin") or base
local l_shin = optPiece("l_shin") or base
local l_hoof = optPiece("l_hoof") or base
local r_femur = optPiece("r_femur") or optPiece("r_thigh") or base
local r_thigh = optPiece("r_thigh") or base  -- this exporter emits no r_thigh
local r_leg = optPiece("r_leg") or optPiece("r_shin") or base
local r_shin = optPiece("r_shin") or base
local r_hoof = optPiece("r_hoof") or base
local l_shoulder = optPiece("l_shoulder") or optPiece("l_arm") or base
local l_forearm = optPiece("l_forearm") or base
local r_shoulder = optPiece("r_shoulder") or optPiece("r_arm") or base
local r_forearm = optPiece("r_forearm") or base
-- The rider rides the saddle bone; rigs that spell that bone "torso" keep the
-- same mounted motion instead of dropping it to the hull.
local rider = optPiece("rider") or optPiece("torso") or base
local weapon = optPiece("weapon") or base

local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

-- Current clip name, declared here because the playback thread and the
-- StartMoving / StopMoving / FireWeapon / Killed call-ins all write it.
local currentClip = "idle"
local lastDrivenClip = nil

-- == Baked-clip playback (Phase 7 Slice 12) ==================================
-- scripts/animdata/medieval_cavalry.lua holds world-space pose frames for
-- walk / trot / gallop / idle / attack_melee / death. scripts/anim_player.lua
-- turns them into Turn/Move calls on the mesh's pieces.
--
-- Every baked channel belongs to the ANIMAL: the bake carries no rider
-- namespace (39 bones, all horse). The rider therefore stays on the procedural
-- rig below, which posts it against the horse's baked root motion, and the
-- mounted pose is driven by `gallop` -- the cavalry's only locomotion register.
-- Everything is pcall-wrapped: a build with no filesystem, no bake bundle or no
-- piece call-ins leaves animCtx nil and the procedural canter below takes over.
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
		local clips, cerr = loadModule("scripts/animdata/medieval_cavalry.lua")
		if type(clips) == "table" then
			animClips = clips
		else
			animFailReason = cerr or "clips load failed"
		end
	else
		animFailReason = perr or "anim_player load failed"
	end
end

-- The rider rides through the procedural rig, so non-bone props never enter
-- the bake binding below and cannot fight the mounted aim / fire pose.
local bakedNames = {}

local animCtx = nil
do
	if animPlayer and type(animClips) == "table" then
		local ctx = animPlayer.new()
		animPlayer.setClips(ctx, animClips)
		animPlayer.setPrimitives(ctx, Turn, Move)
		animPlayer.setSpeed(ctx, 14)
		animPlayer.bindRest(ctx, animClips.idle)

		-- Rigid bone-as-piece port: bind every exact bone name the idle frame
		-- carries to its own resolved piece (optPiece maps the 0 A.D. alias
		-- chain to the emitted piece). Each engine handle is bound once so
		-- spinal aliases sharing a piece cannot clobber one another, and props
		-- like rider / weapon -- which fall back to the hull but never appear
		-- in a frame -- can never hijack the root channel: they stay in
		-- REST_PIECES for the procedural canter / aim loops.
		local restFrame = (animClips.idle and animClips.idle.frames
			and animClips.idle.frames[1]) or {}
		local bound = 0
		local seen = {}
		for name, _ in pairs(restFrame) do
			local handle = optPiece(name)
			if handle and not seen[handle] then
				seen[handle] = true
				bakedNames[#bakedNames + 1] = name
				animPlayer.bindPiece(ctx, name, handle)
				bound = bound + 1
			end
		end
		-- Single-hull mesh: no bone name resolved to a piece, so pin the hull
		-- to the canonical root the procedural fallback still animates.
		if bound == 0 then
			animPlayer.bindPiece(ctx, "root", base)
		end
		animCtx = ctx
	end
end

-- One-time init diagnostic, logged once per unit at chunk scope: proves the
-- baked 0 A.D. clips initialised, or the procedural canter took over. Uses
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
			say(string.format("LUS ANIM cavalry %s driven=%d", clipName, driven))
		end
	end
	return driven, done
end

-- Exactly one playback thread per unit; StartMoving spawns it.
local animThreadLive = false
local isAttacking = false
local function startAnimThread()
	if not animCtx then return false end
	if not animThreadLive then
		animThreadLive = true
		StartThread(function()
			SetSignalMask(SIG_DEATH)
			while true do
				if not isAttacking then
					driveClip(currentClip, 33)
				end
				Sleep(1)
			end
		end)
	end
	return true
end

-- == Rest pose: every bone back to zero =====================================
local REST_PIECES = {
	base, root, spine, neck, head, tail,
	l_femur, l_thigh, l_leg, l_shin, l_hoof,
	r_femur, r_thigh, r_leg, r_shin, r_hoof,
	l_shoulder, l_forearm, r_shoulder, r_forearm,
	rider, weapon,
}

local function restPose()
	for i = 1, #REST_PIECES do
		local p = REST_PIECES[i]
		safeCall(Turn, p, x_axis, 0, 6)
		safeCall(Turn, p, y_axis, 0, 6)
		safeCall(Turn, p, z_axis, 0, 6)
		safeCall(Move, p, x_axis, 0, 6)
		safeCall(Move, p, y_axis, 0, 6)
		safeCall(Move, p, z_axis, 0, 6)
	end
	-- The rigid bone-as-piece bind drives spine1/spine2, neck1/neck2, belly,
	-- ears, upperarm/arm/hand, feet and tail3..7 as well, so clear them too or
	-- a stopped horse freezes mid-canter.
	for i = 1, #bakedNames do
		local p = optPiece(bakedNames[i])
		if p then
			safeCall(Turn, p, x_axis, 0, 6)
			safeCall(Turn, p, y_axis, 0, 6)
			safeCall(Turn, p, z_axis, 0, 6)
			safeCall(Move, p, x_axis, 0, 6)
			safeCall(Move, p, y_axis, 0, 6)
			safeCall(Move, p, z_axis, 0, 6)
		end
	end
end

local function clampAngle(value, limit)
	if type(value) ~= "number" then return 0 end
	if value > limit then return limit end
	if value < -limit then return -limit end
	return value
end

local function clampPitch(pitch)
	return clampAngle(pitch, 0.3)
end

local function clampHeading(heading)
	return clampAngle(heading, 1.2)
end

-- == Locomotion: diagonal canter ============================================
-- Four beats per stride. Beat 1 is diagonal pair A leading (left hind femur
-- forward with the right shoulder), beat 3 is the swapped diagonal pair B; the
-- even beats are the airborne suspension where the hooves gather under the hull.
-- `lift` is the hull's hoof clearance, `bob` the vertical travel of the body.
local GALLOP = {
	{
		-- pair A leads: left hind + right fore forward, right hind + left fore back
		pitch = 0.10, roll = 0.05, lift = 2.2, bob = 0.2, neck = 0.12, tail = 0.16,
		l_femur = 0.45, r_shoulder = 0.40, r_femur = -0.35, l_shoulder = -0.30,
		l_shin = 0.30, r_forearm = 0.28, r_shin = 0.16, l_forearm = 0.14,
	},
	{
		-- suspension: hull airborne, all four limbs fold under the body
		pitch = 0.02, roll = 0.0, lift = 1.0, bob = 0.6, neck = 0.03, tail = 0.0,
		l_femur = 0.05, r_shoulder = 0.05, r_femur = 0.05, l_shoulder = 0.05,
		l_shin = 0.36, r_forearm = 0.32, r_shin = 0.36, l_forearm = 0.32,
	},
	{
		-- pair B leads: right hind + left fore forward, left hind + right fore back
		pitch = -0.08, roll = -0.05, lift = 2.2, bob = 0.2, neck = -0.10, tail = -0.16,
		l_femur = -0.35, r_shoulder = -0.30, r_femur = 0.45, l_shoulder = 0.40,
		l_shin = 0.16, r_forearm = 0.14, r_shin = 0.30, l_forearm = 0.28,
	},
	{
		-- second suspension beat, mirrored
		pitch = 0.02, roll = 0.0, lift = 1.0, bob = 0.6, neck = 0.03, tail = 0.0,
		l_femur = 0.05, r_shoulder = 0.05, r_femur = 0.05, l_shoulder = 0.05,
		l_shin = 0.36, r_forearm = 0.32, r_shin = 0.36, l_forearm = 0.32,
	},
}

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

function script.StartMoving()
	Signal(SIG_MOVE)
	-- Primary: the baked `gallop` clip, driven by scripts/anim_player.lua on the
	-- playback thread -- the cavalry's locomotion register, and the only baked
	-- cycle whose stride matches the procedural canter below. Fallback: that
	-- procedural canter, used when the build ships no bake bundle or no player
	-- module. Note the rider is NOT in the bake, so it only posts on the
	-- procedural path; on the baked path it rides the saddle bone rigidly.
	currentClip = "gallop"
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		if startAnimThread() then return end
		local phase = 1
		while true do
			local beat = GALLOP[phase]
			-- Hull and spine: pitch/roll over the diagonal, then bob with the beat.
			safeCall(Turn, root, x_axis, beat.pitch, 8)
			safeCall(Turn, root, z_axis, beat.roll, 8)
			safeCall(Move, root, y_axis, beat.lift + beat.bob, 12)
			safeCall(Turn, spine, x_axis, beat.pitch * 0.5, 8)
			safeCall(Turn, spine, z_axis, beat.roll * 0.5, 8)
			safeCall(Move, spine, y_axis, beat.bob * 0.4, 12)
			-- Neck and tail counter-swing to balance the canter.
			safeCall(Turn, neck, x_axis, beat.neck, 8)
			safeCall(Turn, head, x_axis, -beat.neck * 0.5, 8)
			safeCall(Turn, tail, z_axis, beat.tail, 10)
			-- Diagonal pairs.
			safeCall(Turn, l_femur, x_axis, beat.l_femur, 10)
			safeCall(Turn, r_femur, x_axis, beat.r_femur, 10)
			safeCall(Turn, r_shoulder, x_axis, beat.r_shoulder, 10)
			safeCall(Turn, l_shoulder, x_axis, beat.l_shoulder, 10)
			-- Hocks and forearms fold so each hoof clears the ground.
			safeCall(Turn, l_leg, x_axis, beat.l_shin, 10)
			safeCall(Turn, r_leg, x_axis, beat.r_shin, 10)
			safeCall(Turn, r_forearm, x_axis, beat.r_forearm, 10)
			safeCall(Turn, l_forearm, x_axis, beat.l_forearm, 10)
			-- The rider posts with the hull and stays upright against the pitch.
			safeCall(Move, rider, y_axis, beat.bob * 0.5, 12)
			safeCall(Turn, rider, x_axis, -beat.pitch * 0.6, 8)
			phase = phase % #GALLOP + 1
			Sleep(150)
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

-- == Combat: rear the horse and slash with the sword ========================
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM cavalry w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- Slew the animal onto the aim line when procedural. In baked mode,
	-- root and neck are driven by baked frames, so only the rider aims
	-- to prevent fighting over bone channels.
	local yaw = clampHeading(heading)
	if not animCtx then
		safeCall(Turn, root, y_axis, yaw * 0.35, 6)
		safeCall(Turn, neck, y_axis, yaw * 0.20, 6)
		safeCall(Turn, rider, y_axis, yaw * 0.45, 6)
	else
		safeCall(Turn, rider, y_axis, yaw, 6)
	end
	safeCall(Turn, rider, x_axis, clampPitch(pitch) * 0.4 + 0.08, 5)
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
		-- Primary: the baked melee is a HORSE move (rear plus foreleg strike),
		-- so the rider's own slash would double up on it and is skipped on this
		-- path. It is a one-shot, but the clock is reset first so consecutive
		-- swings restart instead of holding on the last frame.
		if animCtx then
			isAttacking = true
			animPlayer.reset(animCtx)
			while true do
				local _driven, done = driveClip("attack_melee", 33)
				if done then break end
				Sleep(1)
			end
			animPlayer.reset(animCtx)
			isAttacking = false
			restPose()
			return
		end
		-- Rear: the hull pitches up, weight rocks onto the hocks and the front
		-- pair leaves the ground.
		safeCall(Turn, root, x_axis, -0.30, 8)
		safeCall(Move, root, y_axis, 1.4, 10)
		safeCall(Turn, l_shoulder, x_axis, -0.55, 9)
		safeCall(Turn, r_shoulder, x_axis, -0.55, 9)
		safeCall(Turn, l_forearm, x_axis, -0.35, 9)
		safeCall(Turn, r_forearm, x_axis, -0.35, 9)
		safeCall(Turn, l_femur, x_axis, 0.18, 9)
		safeCall(Turn, r_femur, x_axis, 0.18, 9)
		safeCall(Turn, neck, x_axis, 0.20, 8)
		-- Rider gathers the sword arm back over the shoulder.
		safeCall(Move, weapon, z_axis, -1.2, 12)
		safeCall(Turn, rider, y_axis, -0.22, 8)
		safeCall(Turn, rider, x_axis, -0.10, 8)
		Sleep(110)
		-- Slash: the blade sweeps down and across as the forelegs come back down.
		safeCall(Move, weapon, z_axis, 3.0, 24)
		safeCall(Turn, rider, y_axis, 0.34, 22)
		safeCall(Turn, rider, x_axis, 0.26, 22)
		safeCall(Turn, root, x_axis, 0.06, 12)
		safeCall(Move, root, y_axis, -0.2, 12)
		safeCall(Turn, l_shoulder, x_axis, 0.12, 12)
		safeCall(Turn, r_shoulder, x_axis, 0.12, 12)
		Sleep(120)
		safeCall(Turn, root, x_axis, -0.10, 10)
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
		say(string.format("LUS AIM cavalry w%d [unnum] heading=%.1f pitch=%.1f", weaponNum or 0, heading or 0, pitch or 0))
	end
	local yaw = clampHeading(heading)
	if not animCtx then
		safeCall(Turn, root, y_axis, yaw * 0.35, 6)
		safeCall(Turn, neck, y_axis, yaw * 0.20, 6)
		safeCall(Turn, rider, y_axis, yaw * 0.45, 6)
	else
		safeCall(Turn, rider, y_axis, yaw, 6)
	end
	safeCall(Turn, rider, x_axis, clampPitch(pitch) * 0.4 + 0.08, 5)
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
		-- Primary: the baked horse melee, as above.
		if animCtx then
			isAttacking = true
			animPlayer.reset(animCtx)
			while true do
				local _driven, done = driveClip("attack_melee", 33)
				if done then break end
				Sleep(1)
			end
			animPlayer.reset(animCtx)
			isAttacking = false
			restPose()
			return
		end
		safeCall(Turn, root, x_axis, -0.30, 8)
		safeCall(Move, root, y_axis, 1.4, 10)
		safeCall(Turn, l_shoulder, x_axis, -0.55, 9)
		safeCall(Turn, r_shoulder, x_axis, -0.55, 9)
		safeCall(Turn, l_forearm, x_axis, -0.35, 9)
		safeCall(Turn, r_forearm, x_axis, -0.35, 9)
		safeCall(Move, weapon, z_axis, -1.2, 12)
		safeCall(Turn, rider, y_axis, -0.22, 8)
		Sleep(110)
		safeCall(Move, weapon, z_axis, 3.0, 24)
		safeCall(Turn, rider, y_axis, 0.34, 22)
		safeCall(Turn, rider, x_axis, 0.26, 22)
		safeCall(Turn, root, x_axis, 0.06, 12)
		safeCall(Move, root, y_axis, -0.2, 12)
		Sleep(120)
		restPose()
	end)
end

-- Headless probe hook: when the death probe sets this unit rule, skip the baked
-- clip and exercise the procedural collapse. Guarded so a harness without the
-- rules-param API (or a normal match, where the rule is unset) plays the bake.
local function forceProceduralFallback()
	local ok, value = pcall(function()
		return Spring.GetUnitRulesParam(unitID, "medieval_force_procedural_death")
	end)
	return ok and (value == 1 or value == "1" or value == true)
end

-- == Defeat: the horse breaks down and the rider is thrown ==================
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	-- Primary: the baked `death` one-shot (horse only -- the rider is not in the
	-- bake), held on its last frame while the engine waits out the thread.
	-- Fallback: the procedural collapse below, which also throws the rider.
	if animCtx and not forceProceduralFallback() then
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
	-- Rear one last time, then go over sideways onto the flank.
	safeCall(Turn, root, x_axis, -0.35, 4)
	safeCall(Turn, neck, x_axis, -0.30, 4)
	safeCall(Move, root, y_axis, 0.8, 4)
	Sleep(170)
	safeCall(Turn, root, z_axis, 1.55, 3)
	safeCall(Move, root, y_axis, -2.6, 2)
	-- Legs sprawl: the near pair folds under the body, the far pair kicks out.
	safeCall(Turn, l_femur, z_axis, 0.55, 4)
	safeCall(Turn, r_femur, z_axis, -0.45, 4)
	safeCall(Turn, l_shoulder, z_axis, 0.50, 4)
	safeCall(Turn, r_shoulder, z_axis, -0.40, 4)
	safeCall(Turn, spine, z_axis, 0.25, 5)
	safeCall(Turn, tail, z_axis, -0.35, 5)
	-- The rider is thrown clear of the saddle.
	safeCall(Turn, rider, z_axis, 0.90, 4)
	safeCall(Move, rider, y_axis, -0.6, 4)
	Sleep(240)
	safeCall(Turn, head, x_axis, 0.40, 5)
	Sleep(120)
	return 1
end
