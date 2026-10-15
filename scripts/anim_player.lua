-- Spring LUS animation playback engine.
--
-- Plays the baked 0 A.D. world-pose clips in scripts/animdata/*.lua by driving
-- Turn()/Move() on the model's named pieces. A prototype wiring lives in
-- scripts/medieval_infantry.lua.
--
-- ============================================================================
-- PIECE PIVOT BEHAVIOUR (investigated against RecoilEngine master -- the engine
-- this repo ships as tools/engine/recoil_2026.07.04)
-- ============================================================================
--
-- 1. Every piece's vertices are stored at their bind pose and the piece
--    transform is applied around the piece-local origin:
--
--      rts/System/Transform.hpp      operator*(v) -> r.Rotate(v * s) + t
--                                    vertices rotate FIRST, then translate
--      rts/Rendering/Models/3DModelPiece.cpp:206-220
--                                    T(baked+script) * R(baked) * R(script) * S
--
--    So Turn() ALWAYS rotates about the piece's own origin, never about a
--    joint, and it never about the model origin unless that origin happens to
--    be the piece origin.
--
-- 2. For an OBJ the piece origin is the Assimp node translation:
--
--      rts/Rendering/Models/AssParser.cpp:213-216  piece->offset = aiTransVec
--
--    objects3d/0ad/*.obj carries no node transforms (plain `o <name>` groups,
--    all vertices in one model-space frame), so every offset is 0 and the
--    pivot of every piece is the model origin (0,0,0).
--
-- 3. Consequences, measured on objects3d/0ad/medieval_infantry.obj:
--    a hand vertex sits ~19 elmo from the origin, so rotating the hand piece
--    about (0,0,0) swings it far away from the wrist. The compensation is a
--    translation and this module supplies it (call it the PIVOT TERM):
--
--      rigid pose wanted:   v' = t_k + R (v - t_0)
--      engine renders:      v' = M v + (offset + d)
--      with offset = 0, M = R and  d = t_k - R t_0
--
--    At k = 0 that collapses to d = 0, so the rest frame is a no-op.
--    Omitting the pivot term (moving by t_k - t_0) is off by up to
--    ~26 elmo on hand/finger pieces -- see tests/test_phase7_slice12_anim.py.
--
-- 4. Axis meaning of the Turn() vector (rts/Lua/LuaUnitScript.cpp:109 and
--    rts/System/Matrix44f.cpp:272-279): the engine builds
--
--      CQuaternion::FromEulerYPRNeg(-r)  ==  FromEulerYPR(r)  (signs cancel)
--      FromEulerYPR == RotateEulerYXZ    ==  Rz(rz) Rx(rx) Ry(ry)
--
--    i.e. yaw (axis 2) applied first, then pitch (axis 1), then roll (axis 3).
--    lus_angles() below inverts exactly that composition.
--
-- ============================================================================
-- VERIFICATION
-- ============================================================================
-- The whole pipeline was proven offline against the real OBJ and the real bake
-- (all clip frames, all pieces, every sampled vertex): the engine render of the
-- emitted Turn/Move values equals the rigid pose t_k + R (v - t_0) to 1.4e-14
-- elmo, and the joint maps to itself to 1.8e-15. The same invariants are
-- re-checked in pure Lua by tests/test_phase7_slice12_anim.py.
--
-- ============================================================================
-- API
-- ============================================================================
--   local player = VFS.Include("scripts/anim_player.lua")
--   local ctx = player.new()
--   player.setClips(ctx, VFS.Include("scripts/animdata/<unit>.lua"))
--   player.setPrimitives(ctx, Turn, Move)      -- resolved at call time
--   player.setSpeed(ctx, 10)                   -- rad/s and elmo/s
--   player.bindPiece(ctx, "hip", piece("hip")) -- name -> engine piece handle
--   player.bindRest(ctx, clip)                 -- rest pose = clip frame 1
--   player.setPivot(ctx, pieceHandle, t0)      -- optional: override the pivot
--
--   player.emit(ctx, "walk", elapsedMs)        -- drive one frame
--   player.advance(ctx, dtMs)                  -- advance the playback clock
--
-- The module is pure: no Spring.* call, no VFS.*, no global reads. It is
-- loadable in a bare Lua interpreter, which is what the pytest suite does.

local anim_player = {}

-- Lua 5.3 renamed math.atan2 to math.atan (and Lua 5.4 dropped the old name
-- entirely), while the engine and this repo's test interpreter differ in which
-- they provide. Use whichever exists.
local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end

-- Turn()/Move() angle and distance units per second, and the per-call minimum.
anim_player.DEFAULT_SPEED = 12

-- Clips that never finish; everything else is one-shot.
local LOOPING = {
	walk = true,
	run = true,
	idle = true,
	gallop = true,
	trot = true,
}

-- ---------------------------------------------------------------------------
-- Small vector / quaternion / matrix helpers (3x3 forward-mapped tables).
-- ---------------------------------------------------------------------------

local function mat_apply(m, v)
	return m[1][1] * v[1] + m[1][2] * v[2] + m[1][3] * v[3],
		m[2][1] * v[1] + m[2][2] * v[2] + m[2][3] * v[3],
		m[3][1] * v[1] + m[3][2] * v[2] + m[3][3] * v[3]
end

-- Rotation matrix of a unit quaternion {x, y, z, w}, rows (v' = M v).
local function quat_matrix(q)
	local x, y, z, w = q[1], q[2], q[3], q[4]
	local xx, yy, zz = x * x, y * y, z * z
	local xy, xz, yz = x * y, x * z, y * z
	local xw, yw, zw = x * w, y * w, z * w
	return {
		{ 1 - 2 * (yy + zz), 2 * (xy - zw), 2 * (xz + yw) },
		{ 2 * (xy + zw), 1 - 2 * (xx + zz), 2 * (yz - xw) },
		{ 2 * (xz - yw), 2 * (yz + xw), 1 - 2 * (xx + yy) },
	}
end

-- M = Rz(rz) Rx(rx) Ry(ry): the engine's RotateEulerYXZ, Y first.
local function euler_matrix(rx, ry, rz)
	local cx, sx = math.cos(rx), math.sin(rx)
	local cy, sy = math.cos(ry), math.sin(ry)
	local cz, sz = math.cos(rz), math.sin(rz)
	return {
		{ cz * cy - sz * sx * sy, -sz * cx, cz * sy + sz * sx * cy },
		{ sz * cy + cz * sx * sy, cz * cx, sz * sy - cz * sx * cy },
		{ -cx * sy, sx, cx * cy },
	}
end

-- Exact inverse of euler_matrix(). Each angle reads from entries that carry no
-- other angle, so there is no order ambiguity.
function anim_player.angles(M)
	local sx = M[3][2]
	if sx > 1 then sx = 1 elseif sx < -1 then sx = -1 end
	local rx = math.asin(sx)
	local cx = math.sqrt(1 - sx * sx)
	if cx < 1e-12 then
		return rx, 0, 0 -- gimbal lock: fold yaw into roll
	end
	return rx, atan2(-M[3][1], M[3][3]), atan2(-M[1][2], M[2][2])
end

-- Relative rotation q_k * conj(q_0), normalised.
local function quat_relative(qk, q0)
	local ax, ay, az, ar = qk[1], qk[2], qk[3], qk[4]
	local bx, by, bz, br = -q0[1], -q0[2], -q0[3], q0[4]
	local x = ar * bx + ax * br + ay * bz - az * by
	local y = ar * by - ax * bz + ay * br + az * bx
	local z = ar * bz + ax * by - ay * bx + az * br
	local w = ar * br - ax * bx - ay * by - az * bz
	local n = math.sqrt(x * x + y * y + z * z + w * w)
	if n <= 0 then return { 0, 0, 0, 1 } end
	return { x / n, y / n, z / n, w / n }
end

anim_player.quatMatrix = quat_matrix
anim_player.eulerMatrix = euler_matrix
anim_player.relative = quat_relative

-- ---------------------------------------------------------------------------
-- Frames.
-- ---------------------------------------------------------------------------

-- animdata stores every piece as {tx, ty, tz, qx, qy, qz, qw} on one flat row.
-- Validate that shape once so a malformed bake fails loudly at bind time rather
-- than silently animating to garbage.
local function frame_is_wellformed(frame)
	if type(frame) ~= "table" then return false, "frame is not a table" end
	for name, v in pairs(frame) do
		if type(name) ~= "string" then return false, "piece key is not a string" end
		if type(v) ~= "table" or #v ~= 7 then
			return false, "piece '" .. name .. "' is not a 7-element {t,q} row"
		end
	end
	return true
end

anim_player.frameIsWellformed = frame_is_wellformed

-- Sample a clip at `ms` milliseconds. Looping clips wrap; one-shot clips clamp
-- on the last frame and report `done`. Sampling is absolute in `ms`, so a
-- dropped or repeated call can never accumulate drift.
function anim_player.sample(clip, ms, looping)
	local frames = clip and clip.frames
	if not frames or #frames == 0 then return nil, 0, true end
	local fps = clip.fps or 30
	-- Lua arrays are 1-based: frame advance n is frames[n + 1].
	local advance = math.floor((ms / 1000) * fps)
	local idx, done
	if looping then
		idx = (advance % #frames) + 1
		done = false
	else
		if advance >= #frames then
			idx = #frames
			done = true
		else
			idx = advance + 1
			done = false
		end
	end
	return frames[idx], idx, done
end

anim_player.isLooping = function(name) return LOOPING[name] == true end

-- ---------------------------------------------------------------------------
-- Playback context.
-- ---------------------------------------------------------------------------

function anim_player.new()
	return {
		clips = {},
		pieces = {},   -- piece name -> engine piece handle
		rest = {},     -- piece name -> {t = {x,y,z}, q = {x,y,z,w}}
		pivots = {},   -- engine piece handle -> {x, y, z} (defaults to rest t)
		restClip = nil,
		speed = anim_player.DEFAULT_SPEED,
		clock = {},    -- clip name -> elapsed milliseconds
	}
end

function anim_player.setClips(ctx, clips)
	assert(type(clips) == "table", "anim_player: clips table expected")
	ctx.clips = clips
	return ctx
end

-- Turn/Move are read from the caller every frame: unit scripts resolve them at
-- call time so a stubbed or absent engine call-in degrades instead of crashing.
function anim_player.setPrimitives(ctx, turnFn, moveFn)
	ctx.turn = turnFn
	ctx.move = moveFn
	return ctx
end

function anim_player.setSpeed(ctx, speed)
	if type(speed) == "number" and speed > 0 then ctx.speed = speed end
	return ctx
end

function anim_player.bindPiece(ctx, name, handle)
	if handle then ctx.pieces[name] = handle end
	return ctx
end

-- Rest pose = frame 1 of the given clip (idle frame 1 == the bind pose).
function anim_player.bindRest(ctx, clip)
	local frame = clip and clip.frames and clip.frames[1]
	if not frame then return ctx end
	local ok, why = frame_is_wellformed(frame)
	if not ok then return ctx, why end
	ctx.rest = {}
	ctx.restClip = clip
	for name, v in pairs(frame) do
		ctx.rest[name] = {
			t = { v[1], v[2], v[3] },
			q = { v[4], v[5], v[6], v[7] },
		}
	end
	return ctx
end

-- Override the pivot a piece rotates about. Defaults to the piece's rest
-- translation, which is the bone joint the bake places the piece at.
function anim_player.setPivot(ctx, handle, t)
	if handle and type(t) == "table" and #t == 3 then
		ctx.pivots[handle] = { t[1], t[2], t[3] }
	end
	return ctx
end

function anim_player.reset(ctx)
	ctx.clock = {}
	return ctx
end

-- Playback clock in milliseconds for one clip, wrapping for loops and holding
-- at the end for one-shots.
function anim_player.advance(ctx, dtMs)
	for name, ms in pairs(ctx.clock) do
		ctx.clock[name] = ms + dtMs
	end
	return ctx
end

function anim_player.elapsed(ctx, name)
	return ctx.clock[name] or 0
end

-- ---------------------------------------------------------------------------
-- Emit one frame.
--
-- For every piece the model exposes, sample the clip, compute
--
--     R  = relative rotation (unit quaternion -> matrix)
--     rx, ry, rz = anim_player.angles(R)      engine's YXZ decomposition
--     d  = t_k - R t_0                        includes the pivot term
--
-- and drive the piece. Returns the number of pieces driven plus the per-call
-- completion flag for one-shot clips.
-- ---------------------------------------------------------------------------
-- Compute the absolute per-piece targets for one frame. Returns
--   targets = { [handle] = {rx, ry, rz, dx, dy, dz} }
-- where (rx, ry, rz) are the engine YXZ euler angles and (dx, dy, dz) the
-- pivot-term translation such that the engine renders the rigid bone pose
-- t_k + R (v - t_0). Pure: no primitive calls, no state mutation.
function anim_player.frameTargets(ctx, clipName, ms)
	local clip = ctx.clips[clipName]
	if not clip or not clip.frames or #clip.frames == 0 then return nil, 0, true end

	local looping = anim_player.isLooping(clipName)
	local frame, _idx, done = anim_player.sample(clip, ms, looping)
	if not frame then return nil, 0, true end

	local targets = {}
	local driven = 0

	for name, v in pairs(frame) do
		local handle = ctx.pieces[name]
		local rest = ctx.rest[name]
		if handle and rest then
			local qRel = quat_relative({ v[4], v[5], v[6], v[7] }, rest.q)
			local R = quat_matrix(qRel)
			local rx, ry, rz = anim_player.angles(R)

			-- Rebuild R from the emitted angles so the pivot term uses exactly
			-- the rotation the engine will apply, not the ideal one.
			R = euler_matrix(rx, ry, rz)

			local t0 = ctx.pivots[handle] or rest.t
			local dx = v[1] - (R[1][1] * t0[1] + R[1][2] * t0[2] + R[1][3] * t0[3])
			local dy = v[2] - (R[2][1] * t0[1] + R[2][2] * t0[2] + R[2][3] * t0[3])
			local dz = v[3] - (R[3][1] * t0[1] + R[3][2] * t0[2] + R[3][3] * t0[3])

			targets[handle] = { rx, ry, rz, dx, dy, dz }
			driven = driven + 1
		end
	end

	return targets, driven, done
end

-- Emit one frame as ABSOLUTE Turn()/Move() destinations. Verified by
-- test_emit_is_frame_absolute_not_cumulative: a given ms always yields the same
-- values. Spring's Move(p,axis,destination,speed) / Turn(p,axis,destination,
-- speed) animate the piece TO that absolute destination, so only absolute
-- sampling is correct.
function anim_player.emit(ctx, clipName, ms)
	ctx.clock[clipName] = ms
	local targets, driven, done = anim_player.frameTargets(ctx, clipName, ms)
	if not targets then return 0, true end

	local turn, move = ctx.turn, ctx.move
	local speed = ctx.speed
	for handle, t in pairs(targets) do
		if turn then
			turn(handle, 1, t[1], speed)
			turn(handle, 2, t[2], speed)
			turn(handle, 3, t[3], speed)
		end
		if move then
			move(handle, 1, t[4], speed)
			move(handle, 2, t[5], speed)
			move(handle, 3, t[6], speed)
		end
	end

	return driven, done
end

-- Convenience: advance the clock and emit in one call.
function anim_player.step(ctx, clipName, dtMs)
	ctx.clock[clipName] = (ctx.clock[clipName] or 0) + dtMs
	return anim_player.emit(ctx, clipName, ctx.clock[clipName])
end

return anim_player
