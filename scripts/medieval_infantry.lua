-- Lua Unit Script (LUS) for Medieval Infantry (Melee)
-- Uses 0ad model geometry (objects3d/0ad/medieval_infantry.obj).
--
-- Phase 7 Slice 4 -- procedural piece animation & motion dynamics.
-- The converted 0 A.D. mesh is a bind-pose hull that only exposes the sub-pieces
-- the converter recovered, so every bone is resolved through optPiece(): the
-- canonical humanoid bone is probed first, then the 0 A.D. alias the OBJ actually
-- carries, and finally the resolved root hull (this OBJ has no "base" piece, so
-- `base` binds to the hip bone). Every transform goes through
-- safeCall(), so the script also survives an engine build without the piece
-- animation call-ins.
--
-- Threading contract (see luarules/gadgets/unit_script.lua):
--   * StartMoving / StopMoving are NOT thread-wrapped -> the stride loop has to be
--     spawned with StartThread, and StopMoving may only Signal + reset the pose.
--   * Create / Killed / AimWeapon / FireWeapon ARE thread-wrapped -> Killed may
--     Sleep in its own body, which is what makes the engine wait for the tumble.

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
local head = optPiece("head") or base
local thigh_l = optPiece("thigh_l") or optPiece("l_thigh") or optPiece("greave_07_l") or optPiece("l_leg") or base
local leg_l = optPiece("leg_l") or optPiece("l_leg") or optPiece("greave_07_l") or base
local foot_l = optPiece("foot_l") or optPiece("l_foot") or base
local thigh_r = optPiece("thigh_r") or optPiece("r_thigh") or optPiece("greave_07_r") or optPiece("r_leg") or base
local leg_r = optPiece("leg_r") or optPiece("r_leg") or optPiece("greave_07_r") or base
local foot_r = optPiece("foot_r") or optPiece("r_foot") or base
local arm_l = optPiece("arm_l") or optPiece("l_arm") or optPiece("arm") or base
local forearm_l = optPiece("forearm_l") or optPiece("l_forearm") or optPiece("l_arm") or optPiece("arm") or base
local arm_r = optPiece("arm_r") or optPiece("r_arm") or optPiece("arm") or base
local forearm_r = optPiece("forearm_r") or optPiece("r_forearm") or optPiece("r_arm") or optPiece("arm") or base
local weapon = optPiece("weapon") or base
local shield = optPiece("shield") or base

-- Distinct resolved pieces only: on a single-hull mesh every bone *is* `base`,
-- so deduping keeps the rest pose at one piece instead of sixteen copies.
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

-- Piece transforms are best-effort: a missing call-in must never break a callin.
local function safeCall(fn, ...)
	if type(fn) ~= "function" then return false end
	return (pcall(fn, ...))
end

-- One signal mask per animation channel, so a loop cancels only its own work.
local SIG_MOVE, SIG_ATTACK, SIG_DEATH = 1, 2, 4

-- Current clip name, declared here because the playback thread and the
-- StartMoving/StopMoving call-ins both write it.
local currentClip = "idle"

-- == Baked-clip playback (Phase 7 Slice 12) ==================================
-- scripts/animdata/medieval_infantry.lua holds world-space pose frames for
-- walk / run / idle / attack_melee / build / death. scripts/anim_player.lua
-- turns them into Turn/Move calls on the mesh's pieces.
--
-- Loaded through the unit-script include() API (seeded by
-- luarules/gadgets/unit_script.lua), which resolves paths against scripts/ and
-- runs the chunk in THIS unit's environment. No VFS here: a VFS chunk would
-- execute in the wrong environment and leave animCtx nil. Everything is
-- pcall-wrapped: a build with no bake bundle or no piece call-ins leaves
-- animCtx nil and the procedural stride below takes over.
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
		local clips, cerr = loadModule("scripts/animdata/medieval_infantry.lua")
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

		-- Bind each distinct resolved handle, preferring the bone whose bake
		-- owns it and falling back to the root bone so a single-hull mesh still
		-- animates rather than standing frozen.
		local restFrame = (animClips.idle and animClips.idle.frames
			and animClips.idle.frames[1]) or {}
		local seen = {}
		for i = 1, #PARTS do
			local handle = PARTS[i]
			if handle and not seen[handle] then
				seen[handle] = true
				local name = "hip"
				for candidate in pairs(restFrame) do
					if optPiece(candidate) == handle then
						name = candidate
						break
					end
				end
				animPlayer.bindPiece(ctx, name, handle)
			end
		end
		animCtx = ctx
	end
end

-- One-time init diagnostic, logged once per unit at chunk scope: proves the
-- baked 0 A.D. clips initialised, or the procedural stride took over. Uses
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

-- Back to the bind pose: also the standing stance after a stop.
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

-- Clamp an aim pitch so a steep target never tips the model over.
local function clampLean(pitch)
	local lean = pitch or 0
	if type(lean) ~= "number" then return 0 end
	if lean > 0.3 then return 0.3 end
	if lean < -0.3 then return -0.3 end
	return lean
end

-- Clamp the chest twist: infantry face their target, they do not spin on it.
local function clampYaw(heading)
	local yaw = heading or 0
	if type(yaw) ~= "number" then return 0 end
	if yaw > 0.6 then return 0.6 end
	if yaw < -0.6 then return -0.6 end
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

-- The player hands back {piece, axis, value, speed} rows; safeCall applies each
-- so an engine without the piece call-ins degrades to a static model.
local animTurnSlots, animMoveSlots = {}, {}
local animFrames = 0


-- Player slot callbacks, bound once. The driver drains these into safeCall.
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
	for i = #animTurnSlots, 1, -1 do animTurnSlots[i] = nil end
	for i = #animMoveSlots, 1, -1 do animMoveSlots[i] = nil end

	local driven = animPlayer.emit(animCtx, clipName, animPlayer.elapsed(animCtx, clipName))
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
			say(string.format("LUS ANIM infantry %s driven=%d", clipName, driven))
		end
	end
	return driven
end

-- Exactly one playback thread per unit; StartMoving spawns it.
local animThreadLive = false
local function startAnimThread()
	if not animCtx or animThreadLive then return false end
	animThreadLive = true
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		while true do
			driveClip(currentClip, 33)
			Sleep(1)
		end
	end)
	return true
end

-- == Locomotion: baked `walk` clip, procedural stride as the fallback ========
-- == Locomotion ==============================================================
-- Primary: the baked `walk` clip, driven by scripts/anim_player.lua on the
-- playback thread. Fallback: the procedural cadence inlined below, used when
-- the build ships no bake bundle or no player module. StartMoving is not
-- thread-wrapped by the framework, so it spawns its own loop here.
function script.StartMoving()
	Signal(SIG_MOVE)
	currentClip = "walk"
	StartThread(function()
		SetSignalMask(SIG_MOVE)
		if startAnimThread() then return end
		while true do
	safeCall(Turn, thigh_l, x_axis, 0.40, 8)
	safeCall(Turn, leg_l, x_axis, -0.26, 8)
	safeCall(Turn, foot_l, x_axis, 0.12, 8)
	safeCall(Turn, thigh_r, x_axis, -0.40, 8)
	safeCall(Turn, leg_r, x_axis, -0.04, 8)
	safeCall(Turn, foot_r, x_axis, 0.06, 8)
	safeCall(Turn, arm_l, x_axis, -0.32, 8)
	safeCall(Turn, forearm_l, x_axis, -0.12, 8)
	safeCall(Turn, arm_r, x_axis, 0.32, 8)
	safeCall(Turn, forearm_r, x_axis, -0.22, 8)
	safeCall(Turn, chest, x_axis, 0.06, 8)
	safeCall(Turn, spine, z_axis, 0.05, 8)
	safeCall(Move, hip, y_axis, 0.8, 8)
	Sleep(140)
	safeCall(Turn, thigh_l, x_axis, 0.02, 8)
	safeCall(Turn, leg_l, x_axis, -0.06, 8)
	safeCall(Turn, foot_l, x_axis, 0.0, 8)
	safeCall(Turn, thigh_r, x_axis, -0.02, 8)
	safeCall(Turn, leg_r, x_axis, -0.10, 8)
	safeCall(Turn, foot_r, x_axis, -0.04, 8)
	safeCall(Turn, arm_l, x_axis, 0.0, 8)
	safeCall(Turn, forearm_l, x_axis, -0.06, 8)
	safeCall(Turn, arm_r, x_axis, 0.0, 8)
	safeCall(Turn, forearm_r, x_axis, -0.1, 8)
	safeCall(Turn, chest, x_axis, 0.0, 8)
	safeCall(Turn, spine, z_axis, 0.0, 8)
	safeCall(Move, hip, y_axis, 0.0, 8)
	Sleep(140)
	safeCall(Turn, thigh_l, x_axis, -0.40, 8)
	safeCall(Turn, leg_l, x_axis, -0.04, 8)
	safeCall(Turn, foot_l, x_axis, 0.06, 8)
	safeCall(Turn, thigh_r, x_axis, 0.40, 8)
	safeCall(Turn, leg_r, x_axis, -0.26, 8)
	safeCall(Turn, foot_r, x_axis, 0.12, 8)
	safeCall(Turn, arm_l, x_axis, 0.32, 8)
	safeCall(Turn, forearm_l, x_axis, -0.22, 8)
	safeCall(Turn, arm_r, x_axis, -0.32, 8)
	safeCall(Turn, forearm_r, x_axis, -0.12, 8)
	safeCall(Turn, chest, x_axis, -0.06, 8)
	safeCall(Turn, spine, z_axis, -0.05, 8)
	safeCall(Move, hip, y_axis, 0.8, 8)
	Sleep(140)
	safeCall(Turn, thigh_l, x_axis, -0.02, 8)
	safeCall(Turn, leg_l, x_axis, -0.10, 8)
	safeCall(Turn, foot_l, x_axis, -0.04, 8)
	safeCall(Turn, thigh_r, x_axis, 0.02, 8)
	safeCall(Turn, leg_r, x_axis, -0.06, 8)
	safeCall(Turn, foot_r, x_axis, 0.0, 8)
	safeCall(Turn, arm_l, x_axis, 0.0, 8)
	safeCall(Turn, forearm_l, x_axis, -0.1, 8)
	safeCall(Turn, arm_r, x_axis, 0.0, 8)
	safeCall(Turn, forearm_r, x_axis, -0.06, 8)
	safeCall(Turn, chest, x_axis, 0.0, 8)
	safeCall(Turn, spine, z_axis, 0.0, 8)
	safeCall(Move, hip, y_axis, 0.0, 8)
	Sleep(140)
		end
	end)
end

-- StopMoving is not thread-wrapped, so it may only Signal and reset the pose;
-- the playback thread picks up `idle` on its next tick.
function script.StopMoving()
	Signal(SIG_MOVE)
	currentClip = "idle"
	restPose()
end

-- == Combat: aim pitch follow + melee thrust recoil ==========================
function script.AimWeapon1(heading, pitch)
	if aimEchoes < 5 then
		aimEchoes = aimEchoes + 1
		say(string.format("LUS AIM infantry w1 heading=%.1f pitch=%.1f", heading or 0, pitch or 0))
	end
	-- Chest and spine carry the aim; the stride loop owns the same pieces while
	-- walking and the last writer of the frame wins, so both stay smooth.
	local lean = clampLean(pitch)
	local yaw = clampYaw(heading)
	safeCall(Turn, spine, x_axis, lean * 0.4, 5)
	safeCall(Turn, chest, x_axis, lean * 0.6, 5)
	safeCall(Turn, chest, y_axis, yaw, 5)
	safeCall(Turn, head, y_axis, yaw * 0.5, 5)
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
		-- Primary: play the baked melee swing. It is a one-shot, but the clock
		-- is reset first so consecutive swings restart instead of holding on
		-- the last frame.
		if animCtx then
			animPlayer.reset(animCtx)
			while true do
				local _driven, done = driveClip("attack_melee", 33)
				if done then break end
				Sleep(1)
			end
			animPlayer.reset(animCtx)
			restPose()
			return
		end
		-- Wind-up: cock the spear back, twist the chest off the target line.
		safeCall(Turn, chest, z_axis, -0.26, 12)
		safeCall(Turn, arm_r, x_axis, -0.5, 12)
		safeCall(Turn, forearm_r, x_axis, -0.42, 12)
		safeCall(Turn, arm_l, x_axis, 0.2, 12)
		safeCall(Move, weapon, z_axis, -0.6, 14)
		Sleep(110)
		-- Thrust: drive the weapon through, chest twists into the strike.
		safeCall(Turn, chest, z_axis, 0.3, 20)
		safeCall(Turn, arm_r, x_axis, 0.55, 20)
		safeCall(Turn, forearm_r, x_axis, 0.15, 20)
		safeCall(Turn, hip, x_axis, 0.16, 18)
		safeCall(Turn, thigh_l, x_axis, 0.28, 18)
		safeCall(Move, weapon, z_axis, 2.2, 22)
		Sleep(90)
		-- Recover.
		safeCall(Turn, chest, z_axis, -0.06, 10)
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
	local lean = clampLean(pitch)
	local yaw = clampYaw(heading)
	safeCall(Turn, spine, x_axis, lean * 0.4, 4)
	safeCall(Turn, chest, x_axis, lean * 0.6, 4)
	safeCall(Turn, chest, y_axis, yaw, 4)
	safeCall(Turn, head, y_axis, yaw * 0.5, 4)
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
		safeCall(Turn, chest, z_axis, -0.26, 12)
		safeCall(Turn, arm_r, x_axis, -0.5, 12)
		safeCall(Turn, arm_l, x_axis, 0.2, 12)
		safeCall(Move, weapon, z_axis, -0.6, 14)
		Sleep(110)
		safeCall(Turn, chest, z_axis, 0.3, 20)
		safeCall(Turn, arm_r, x_axis, 0.55, 20)
		safeCall(Turn, hip, x_axis, 0.16, 18)
		safeCall(Move, weapon, z_axis, 2.2, 22)
		Sleep(90)
		safeCall(Move, weapon, z_axis, -0.4, 14)
		Sleep(110)
		restPose()
	end)
end

-- == Defeat: buckle at the knees, then topple sideways onto the ground ========
function script.Killed(recentDamage, maxHealth)
	Signal(SIG_MOVE)
	Signal(SIG_ATTACK)
	Signal(SIG_DEATH)
	SetSignalMask(SIG_DEATH)
	-- Buckle: knees fold, the torso pitches over and rolls off the aim line.
	safeCall(Turn, thigh_l, x_axis, 0.55, 3)
	safeCall(Turn, thigh_r, x_axis, 0.45, 3)
	safeCall(Turn, leg_l, x_axis, -0.9, 3)
	safeCall(Turn, leg_r, x_axis, -0.8, 3)
	safeCall(Turn, hip, x_axis, 1.3, 3)
	safeCall(Turn, hip, z_axis, 0.55, 3)
	safeCall(Turn, chest, x_axis, 0.4, 3)
	safeCall(Turn, head, x_axis, 0.5, 4)
	safeCall(Turn, arm_l, x_axis, -0.8, 3)
	safeCall(Turn, arm_r, x_axis, 0.9, 3)
	safeCall(Turn, forearm_l, x_axis, -0.5, 3)
	safeCall(Turn, forearm_r, x_axis, -0.6, 3)
	safeCall(Move, hip, y_axis, -1.5, 2)
	Sleep(360)
	-- Settle flat: the limbs collapse and the hull comes to rest.
	safeCall(Turn, hip, x_axis, 1.5, 2)
	safeCall(Turn, hip, z_axis, 0.7, 2)
	safeCall(Turn, chest, x_axis, 0.15, 2)
	safeCall(Turn, arm_l, x_axis, -0.2, 2)
	safeCall(Turn, arm_r, x_axis, 0.25, 2)
	safeCall(Move, hip, y_axis, -1.8, 2)
	Sleep(240)
	return 1
end