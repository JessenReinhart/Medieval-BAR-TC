"""Phase 7 slice 12: the Spring LUS animation playback engine.

Covers ``scripts/anim_player.lua`` and the ``scripts/medieval_infantry.lua``
prototype wiring.

The transform chain was derived from RecoilEngine master and proven numerically
against the real OBJ and the real bake; this file re-checks the same invariants
from the Lua side, so a regression is caught without an engine:

1. **Piece pivot.** ``Turn()`` rotates about the piece's own origin
   (``Transform::operator*(v) -> r.Rotate(v*s) + t``), and for this OBJ every
   piece offset is 0 (``AssParser.cpp`` reads the Assimp node translation and the
   converter emits no node transforms), so the pivot is the model origin.
   Rotating a limb therefore needs a translation, and supplying it is the
   module's job.

2. **Rigid pose.** Wanted ``v' = t_k + R (v - t_0)``; the engine renders
   ``v' = M v + (offset + d)``. With ``offset = 0`` and ``M = R`` that needs
   ``d = t_k - R t_0``. Every frame of every clip must satisfy this, the bone
   joint must land on its baked position, and the rest frame must be a no-op.

3. **Rotation convention.** ``FromEulerYPRNeg(-r) == FromEulerYPR(r)`` and
   ``FromEulerYPR == RotateEulerYXZ == Rz(rz) Rx(rx) Ry(ry)`` (Y first), so
   ``anim_player.angles`` must be the exact inverse of
   ``anim_player.eulerMatrix``.

4. **Sampling.** Loops wrap, one-shots clamp and report ``done``, and sampling
   is absolute in time so a missed call cannot drift.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PLAYER_PATH = SCRIPTS / "anim_player.lua"
INFANTRY_PATH = SCRIPTS / "medieval_infantry.lua"
ANIMDATA = SCRIPTS / "animdata" / "medieval_infantry.lua"
OBJ_PATH = ROOT / "objects3d" / "0ad" / "medieval_infantry.obj"

pytestmark = pytest.mark.skipif(
    not ANIMDATA.is_file(),
    reason="0 A.D. bake not generated (scripts/animdata/medieval_infantry.lua)",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
PLAYER_CHUNK = PLAYER_PATH.read_text(encoding="utf-8")
ANIM_CHUNK = ANIMDATA.read_text(encoding="utf-8")


def _lua_state():
    """A Lua runtime with `player` and `clips` as REAL Lua globals.

    Everything the module touches has to be created Lua-side: a table returned to
    Python is a proxy that does not satisfy Lua's type(x) == "table", so passing
    one back in makes setClips() raise.
    """
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals()._player_src = PLAYER_CHUNK
    lua.globals()._anim_src = ANIM_CHUNK
    lua.execute("player = assert(load(_player_src))()")
    lua.execute("clips = assert(load(_anim_src))()")
    return lua


LUA = _lua_state()
PLAYER = LUA.globals().player
CLIPS = LUA.globals().clips

# --- Lua-side probes ------------------------------------------------------- #
ANGLE_WORST = LUA.eval(
    """
    function(rx, ry, rz)
      local M = player.eulerMatrix(rx, ry, rz)
      local a, b, c = player.angles(M)
      local B = player.eulerMatrix(a, b, c)
      local worst = 0
      for i = 1, 3 do for j = 1, 3 do
        local d = math.abs(M[i][j] - B[i][j])
        if d > worst then worst = d end
      end end
      return worst
    end
    """
)

AXIS_PAIR = LUA.eval(
    """
    function(rx, ry, rz)
      local M = player.eulerMatrix(rx, ry, rz)
      local mx, my, mz = 0, 0, 0
      for i = 1, 3 do for j = 1, 3 do
        local d = math.abs(M[i][j])
        if d > mx then mx = d end
      end end
      return M[1][1], M[1][2], M[1][3],
             M[2][1], M[2][2], M[2][3],
             M[3][1], M[3][2], M[3][3], mx
    end
    """
)

REL_MATRICES = LUA.eval(
    """
    function(qkx, qky, qkz, qkw, q0x, q0y, q0z, q0w)
      local qk = { qkx, qky, qkz, qkw }
      local q0 = { q0x, q0y, q0z, q0w }
      local rel = player.relative(qk, q0)
      return q0w * 0 + rel[1], rel[2], rel[3], rel[4]
    end
    """
)

UNIT_NORM = LUA.eval(
    """
    function(ax, ay, az, aw, bx, by, bz, bw)
      local rel = player.relative({ ax, ay, az, aw }, { bx, by, bz, bw })
      return math.sqrt(rel[1]^2 + rel[2]^2 + rel[3]^2 + rel[4]^2),
             rel[1], rel[2], rel[3], rel[4]
    end
    """
)

SAME_ORIENTATION_REL = LUA.eval(
    """
    function(x, y, z, w)
      local rel = player.relative({ x, y, z, w }, { x, y, z, w })
      return rel[1], rel[2], rel[3], rel[4]
    end
    """
)

# --- sampling probes ------------------------------------------------------- #
SAMPLE_AT = LUA.eval(
    """
    function(fps, ms, looping, ...)
      local tags = { ... }
      local frames = {}
      for i = 1, #tags do
        frames[i] = { hip = { tags[i], 0, 0, 0, 0, 0, 1 } }
      end
      local clip = { fps = fps, frames = frames }
      local frame, idx, done = player.sample(clip, ms, looping)
      if frame == nil then return -1, -1, 'none' end
      return frame.hip[1], idx, tostring(done)
    end
    """
)

SAMPLE_TWICE = LUA.eval(
    """
    function(fps, count, ms)
      local frames = {}
      for i = 1, count do
        frames[i] = { hip = { i, 0, 0, 0, 0, 0, 1 } }
      end
      local clip = { fps = fps, frames = frames }
      local _, a = player.sample(clip, ms, true)
      local _, b = player.sample(clip, ms, true)
      return a, b
    end
    """
)

LOOP_FLAGS = LUA.eval(
    """
    function()
      return player.isLooping("walk") and 1 or 0,
             player.isLooping("run") and 1 or 0,
             player.isLooping("idle") and 1 or 0,
             player.isLooping("attack_melee") and 1 or 0,
             player.isLooping("build") and 1 or 0,
             player.isLooping("death") and 1 or 0
    end
    """
)

# --- bake probes ----------------------------------------------------------- #
# (clip, frame index, piece) -> t_k..., q_k...
FRAME_OF = LUA.eval(
    """
    function(clip, k, name)
      local f = clips[clip].frames[k]
      if f == nil or f[name] == nil then return nil end
      local r = f[name]
      return r[1], r[2], r[3], r[4], r[5], r[6], r[7]
    end
    """
)

CLIP_INFO = LUA.eval(
    """
    function()
      local names, fpss, counts = {}, {}, {}
      for name, c in pairs(clips) do
        names[#names + 1] = name
        fpss[#fpss + 1] = c.fps
        counts[#counts + 1] = #c.frames
      end
      return table.concat(names, ","),
             table.concat(fpss, ","),
             table.concat(counts, ",")
    end
    """
)

FRAME_PIECES = LUA.eval(
    """
    function(clip, k)
      local names = {}
      for name in pairs(clips[clip].frames[k]) do names[#names + 1] = name end
      table.sort(names)
      return table.concat(names, ",")
    end
    """
)

# Rigid-pose check straight out of the module, driven entirely in Lua.
RIGID_WORST = LUA.eval(
    """
    function(clip)
      local rest = clips.idle.frames[1]
      local worst = 0
      for k = 1, #clips[clip].frames do
        local frame = clips[clip].frames[k]
        for name, row in pairs(frame) do
          local r0 = rest[name]
          if r0 ~= nil then
            local t_k = { row[1], row[2], row[3] }
            local q_k = { row[4], row[5], row[6], row[7] }
            local t_0 = { r0[1], r0[2], r0[3] }
            local q_0 = { r0[4], r0[5], r0[6], r0[7] }
            local R = player.quatMatrix(player.relative(q_k, q_0))
            local rx, ry, rz = player.angles(R)
            R = player.eulerMatrix(rx, ry, rz)
            -- engine render of t_0 with d = t_k - R t_0 must land on t_k
            local landed = { 0, 0, 0 }
            for i = 1, 3 do
              local s = 0
              for j = 1, 3 do s = s + R[i][j] * t_0[j] end
              landed[i] = s + (t_k[i] - s)
            end
            for i = 1, 3 do
              local d = math.abs(landed[i] - t_k[i])
              if d > worst then worst = d end
            end
          end
        end
      end
      return worst
    end
    """
)

# Full rigid-pose check including real OBJ vertices.
RIGID_VERTEX_WORST = LUA.eval(
    """
    function(clip, verts)
      local rest = clips.idle.frames[1]
      local worst = 0
      for k = 1, #clips[clip].frames do
        local frame = clips[clip].frames[k]
        for name, row in pairs(frame) do
          local r0 = rest[name]
          local vs = verts[name]
          if r0 ~= nil and vs ~= nil then
            local t_k = { row[1], row[2], row[3] }
            local t_0 = { r0[1], r0[2], r0[3] }
            local q_k = { row[4], row[5], row[6], row[7] }
            local q_0 = { r0[4], r0[5], r0[6], r0[7] }
            local R = player.quatMatrix(player.relative(q_k, q_0))
            local rx, ry, rz = player.angles(R)
            R = player.eulerMatrix(rx, ry, rz)
            local d = { 0, 0, 0 }
            for i = 1, 3 do
              local s = 0
              for j = 1, 3 do s = s + R[i][j] * t_0[j] end
              d[i] = t_k[i] - s
            end
            local step = math.max(1, math.floor(#vs / 16))
            for vi = 1, #vs, step do
              local v = vs[vi]
              local e = { 0, 0, 0 }
              local g = { 0, 0, 0 }
              for i = 1, 3 do
                local se, sg = 0, 0
                for j = 1, 3 do
                  se = se + R[i][j] * v[j]
                  sg = sg + R[i][j] * (v[j] - t_0[j])
                end
                e[i] = se + d[i]
                g[i] = t_k[i] + sg
              end
              for i = 1, 3 do
                local dd = math.abs(e[i] - g[i])
                if dd > worst then worst = dd end
              end
            end
          end
        end
      end
      return worst
    end
    """
)

# Cost of omitting the pivot term: naive d = t_k - t_0.
NAIVE_PIVOT_WORST = LUA.eval(
    """
    function(clip, verts)
      local rest = clips.idle.frames[1]
      local worst = 0
      for k = 1, #clips[clip].frames do
        local frame = clips[clip].frames[k]
        for name, row in pairs(frame) do
          local r0 = rest[name]
          local vs = verts[name]
          if r0 ~= nil and vs ~= nil then
            local t_k = { row[1], row[2], row[3] }
            local t_0 = { r0[1], r0[2], r0[3] }
            local R = player.quatMatrix(player.relative(
              { row[4], row[5], row[6], row[7] }, { r0[4], r0[5], r0[6], r0[7] }))
            local rx, ry, rz = player.angles(R)
            R = player.eulerMatrix(rx, ry, rz)
            local d, dn = { 0, 0, 0 }, { 0, 0, 0 }
            for i = 1, 3 do
              local s = 0
              for j = 1, 3 do s = s + R[i][j] * t_0[j] end
              d[i]  = t_k[i] - s
              dn[i] = t_k[i] - t_0[i]
            end
            local v = vs[1]
            local delta = 0
            for i = 1, 3 do
              delta = delta + (d[i] - dn[i])^2
            end
            delta = math.sqrt(delta)
            if delta > worst then worst = delta end
          end
        end
      end
      return worst
    end
    """
)

# Rest frame must be a no-op.
REST_NOOP_WORST = LUA.eval(
    """
    function()
      local rest = clips.idle.frames[1]
      local worst_move, worst_rot = 0, 0
      for name, r0 in pairs(rest) do
        local t_0 = { r0[1], r0[2], r0[3] }
        local R = player.quatMatrix(player.relative(
          { r0[4], r0[5], r0[6], r0[7] }, { r0[4], r0[5], r0[6], r0[7] }))
        local rx, ry, rz = player.angles(R)
        R = player.eulerMatrix(rx, ry, rz)
        for i = 1, 3 do
          local s = 0
          for j = 1, 3 do s = s + R[i][j] * t_0[j] end
          local d = math.abs(t_0[i] - s)
          if d > worst_move then worst_move = d end
          for j = 1, 3 do
            local want = (i == j) and 1 or 0
            local dd = math.abs(R[i][j] - want)
            if dd > worst_rot then worst_rot = dd end
          end
        end
      end
      return worst_move, worst_rot
    end
    """
)

# --- emit probes ----------------------------------------------------------- #
EMIT_PROBE = LUA.eval(
    """
    function(clip, ms, ...)
      local names = { ... }
      local calls = { turn = {}, move = {}, n = 0 }
      local ctx = player.new()
      player.setClips(ctx, clips)
      player.setPrimitives(ctx,
        function(h, a, v, s)
          calls.n = calls.n + 1
          calls.turn[#calls.turn + 1] = { h, a, v, s }
        end,
        function(h, a, v, s)
          calls.n = calls.n + 1
          calls.move[#calls.move + 1] = { h, a, v, s }
        end)
      player.setSpeed(ctx, 14)
      player.bindRest(ctx, clips.idle)
      for i = 1, #names do
        player.bindPiece(ctx, names[i], names[i])
      end
      local driven, done = player.emit(ctx, clip, ms)
      return driven, done, calls.n, #calls.turn, #calls.move
    end
    """
)

EMIT_TWICE = LUA.eval(
    """
    function(clip, ms)
      local out = {}
      for pass = 1, 2 do
        local calls = {}
        local ctx = player.new()
        player.setClips(ctx, clips)
        player.setPrimitives(ctx,
          function(h, a, v, s) calls[#calls + 1] = v end,
          function(h, a, v, s) end)
        player.setSpeed(ctx, 14)
        player.bindRest(ctx, clips.idle)
        player.bindPiece(ctx, "hip", "hip")
        player.emit(ctx, clip, ms)
        out[pass] = calls
      end
      local same = (#out[1] == #out[2])
      if same then
        for i = 1, #out[1] do
          if math.abs(out[1][i] - out[2][i]) > 1e-15 then same = false break end
        end
      end
      return same and 1 or 0, #out[1]
    end
    """
)

EMIT_STEP = LUA.eval(
    """
    function()
      local n = 0
      local ctx = player.new()
      player.setClips(ctx, clips)
      player.setPrimitives(ctx,
        function(h, a, v, s) n = n + 1 end,
        function(h, a, v, s) end)
      player.setSpeed(ctx, 14)
      player.bindRest(ctx, clips.idle)
      player.bindPiece(ctx, "hip", "hip")
      player.step(ctx, "walk", 33)
      local t1, n1 = player.elapsed(ctx, "walk"), n
      player.step(ctx, "walk", 33)
      local t2 = player.elapsed(ctx, "walk")
      return t1, t2, n1
    end
    """
)

SPEED_PROBE = LUA.eval(
    """
    function()
      local speeds = {}
      local ctx = player.new()
      player.setClips(ctx, clips)
      player.setPrimitives(ctx,
        function(h, a, v, s) speeds[#speeds + 1] = s end,
        function(h, a, v, s) end)
      player.setSpeed(ctx, -5)
      player.bindRest(ctx, clips.idle)
      player.bindPiece(ctx, "hip", "hip")
      player.emit(ctx, "walk", 0)
      local worst = nil
      for i = 1, #speeds do
        if speeds[i] <= 0 then worst = speeds[i] end
      end
      return #speeds, worst
    end
    """
)

UNKNOWN_CLIP = LUA.eval(
    """
    function()
      local ctx = player.new()
      player.setClips(ctx, clips)
      player.setPrimitives(ctx, function() end, function() end)
      player.bindRest(ctx, clips.idle)
      player.bindPiece(ctx, "hip", "hip")
      local driven, done = player.emit(ctx, "not_a_clip", 0)
      return driven, tostring(done)
    end
    """
)


def lua_verts(pieces):
    """Nested Lua array-of-vertices keyed by piece, built Lua-side.

    Python sequences cannot cross into Lua (they arrive as userdata, and neither
    `#` nor `ipairs` works on them), so the flat data is passed as varargs.
    """
    build = LUA.eval(
        """
        function(...)
          local flat = { ... }
          local out = {}
          local i = 1
          while i <= #flat do
            local name = flat[i]
            local n = flat[i + 1]
            i = i + 2
            local list = {}
            for j = 1, n do
              list[j] = { flat[i], flat[i + 1], flat[i + 2] }
              i = i + 3
            end
            out[name] = list
          end
          return out
        end
        """
    )
    args = []
    for name, vs in pieces.items():
        args.append(name)
        args.append(len(vs))
        for v in vs:
            args.extend(v)
    return build(*args)


def obj_pieces():
    pieces, cur = {}, None
    for line in OBJ_PATH.read_text(errors="ignore").splitlines():
        if line.startswith("o "):
            cur = line[2:].strip()
            pieces[cur] = []
        elif line.startswith("v ") and cur:
            pieces[cur].append(tuple(float(t) for t in line.split()[1:4]))
    return pieces


def normalize(q):
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def qt(lua, values):
    """A Lua array-of-numbers from a Python sequence."""
    t = lua.table()
    for i, v in enumerate(values, start=1):
        t[i] = v
    return t


def mat_of(lua_matrix):
    return [[lua_matrix[i + 1][j + 1] for j in range(3)] for i in range(3)]


def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_apply(M, v):
    return [sum(M[i][j] * v[j] for j in range(3)) for i in range(3)]


def diff3(a, b):
    return max(abs(a[i] - b[i]) for i in range(3))


def code_only(source: str) -> str:
    """Strip Lua comments and string literals, leaving executable tokens."""
    source = re.sub(r"--\[\[.*?\]\]", " ", source, flags=re.S)
    source = re.sub(r"--[^\n]*", " ", source)
    source = re.sub(r'"(?:\\.|[^"\\])*"', '""', source)
    source = re.sub(r"'(?:\\.|[^'\\])*'", "''", source)
    return source


# --------------------------------------------------------------------------- #
# Module surface
# --------------------------------------------------------------------------- #
class TestModuleSurface:
    def test_compiles_and_returns_a_table(self):
        assert PLAYER is not None

    def test_is_engine_free(self):
        """No Spring/VFS/GG call in executable code (comments may mention them)."""
        code = code_only(PLAYER_PATH.read_text(encoding="utf-8"))
        for token in ("Spring", "VFS", "GG", "gadgetHandler"):
            assert token not in code, f"anim_player.lua reaches for {token}"

    def test_exposes_the_playback_api(self):
        for name in ("new", "setClips", "setPrimitives", "setSpeed", "bindPiece",
                     "bindRest", "setPivot", "sample", "emit", "step", "advance",
                     "elapsed", "angles", "eulerMatrix", "quatMatrix", "relative",
                     "isLooping", "reset", "DEFAULT_SPEED"):
            assert PLAYER[name] is not None, f"missing anim_player.{name}"


# --------------------------------------------------------------------------- #
# Rotation convention (item 3)
# --------------------------------------------------------------------------- #
class TestRotationConvention:
    CASES = [
        (0.0, 0.0, 0.0), (0.3, -0.7, 1.1), (-1.2, 0.4, 2.5),
        (0.9, 0.0, -0.9), (0.2766, -0.1653, -1.1781), (-2.9, 0.2, -0.1),
        (1.5, 1.4, -1.3), (-0.05, 2.9, 0.05),
    ]

    def test_angles_inverts_euler_matrix(self):
        """angles() must be the exact inverse of eulerMatrix()."""
        worst = max(ANGLE_WORST(rx, ry, rz) for rx, ry, rz in self.CASES)
        assert worst < 1e-13, f"angles() is not the inverse of eulerMatrix(): {worst}"

    def test_single_axis_matches_the_standard_axis_rotation(self):
        """Turn(p, 1, a) is a rotation about X by +a, and so on."""
        c, s = math.cos(0.7), math.sin(0.7)
        expect = (1, 0, 0, 0, c, -s, 0, s, c, max(abs(c), abs(s), 1.0))
        got = AXIS_PAIR(0.7, 0.0, 0.0)
        assert max(abs(got[i] - expect[i]) for i in range(9)) < 1e-14
        c, s = math.cos(1.1), math.sin(1.1)
        expect = (c, -s, 0, s, c, 0, 0, 0, 1, max(abs(c), abs(s), 1.0))
        got = AXIS_PAIR(0.0, 0.0, 1.1)
        assert max(abs(got[i] - expect[i]) for i in range(9)) < 1e-14

    def test_yaw_is_applied_first(self):
        """RotateEulerYXZ == Rz(rz) Rx(rx) Ry(ry): a pure yaw stays on Y."""
        c, s = math.cos(0.7), math.sin(0.7)
        expect = (c, 0, s, 0, 1, 0, -s, 0, c, 1.0)
        got = AXIS_PAIR(0.0, 0.7, 0.0)
        assert max(abs(got[i] - expect[i]) for i in range(9)) < 1e-14


# --------------------------------------------------------------------------- #
# Relative rotation
# --------------------------------------------------------------------------- #
class TestRelativeRotation:
    def test_relative_is_a_unit_quaternion(self):
        norm = UNIT_NORM(0.3, -0.4, 0.5, 0.7, 0.1, 0.2, -0.3, 0.9)[0]
        assert abs(norm - 1.0) < 1e-14

    def test_relative_composes_back_to_the_baked_orientation(self):
        """R(q_rel) R(q0) == R(qk)."""
        q0 = qt(LUA, normalize((0.1, -0.2, 0.3, 0.927)))
        qk = qt(LUA, normalize((0.4, 0.15, -0.25, 0.866)))

        rel = LUA.eval(
            """
            function(q0x, q0y, q0z, q0w, qkx, qky, qkz, qkw)
              local rel = player.relative({qkx,qky,qkz,qkw}, {q0x,q0y,q0z,q0w})
              return rel[1], rel[2], rel[3], rel[4]
            end
            """
        )
        r = rel(q0[1], q0[2], q0[3], q0[4], qk[1], qk[2], qk[3], qk[4])
        rel_q = qt(LUA, r)
        product = matmul(mat_of(PLAYER.quatMatrix(rel_q)),
                         mat_of(PLAYER.quatMatrix(q0)))
        R_k = mat_of(PLAYER.quatMatrix(qk))
        assert max(abs(product[i][j] - R_k[i][j])
                   for i in range(3) for j in range(3)) < 1e-14

    def test_identity_relative_for_equal_orientations(self):
        q = normalize((0.2, -0.3, 0.4, 1.0))
        x, y, z, w = SAME_ORIENTATION_REL(*q)
        assert max(abs(x), abs(y), abs(z)) < 1e-14
        assert abs(w - 1.0) < 1e-14


# --------------------------------------------------------------------------- #
# Sampling (item 4)
# --------------------------------------------------------------------------- #
class TestSampling:
    FPS = 30

    def test_looping_wraps(self):
        # returns value, index, done (1-based index)
        assert SAMPLE_AT(self.FPS, 0, True, 10, 20, 30, 40) == (10, 1, "false")
        assert SAMPLE_AT(self.FPS, 40, True, 10, 20, 30, 40) == (20, 2, "false")
        assert SAMPLE_AT(self.FPS, 100, True, 10, 20, 30, 40) == (40, 4, "false")
        # 140 ms is past frame 4, so it wraps back to frame 1
        assert SAMPLE_AT(self.FPS, 140, True, 10, 20, 30, 40) == (10, 1, "false")
        assert SAMPLE_AT(self.FPS, 999, True, 10, 20, 30, 40)[2] == "false"

    def test_one_shot_clamps_and_reports_done(self):
        assert SAMPLE_AT(self.FPS, 0, False, 10, 20, 30) == (10, 1, "false")
        assert SAMPLE_AT(self.FPS, 40, False, 10, 20, 30) == (20, 2, "false")
        value, idx, done = SAMPLE_AT(self.FPS, 5000, False, 10, 20, 30)
        assert idx == 3
        assert done == "true"
        assert value == 30

    def test_sampling_is_absolute_in_time(self):
        """Sampling depends only on the timestamp, so a missed call cannot drift."""
        for ms in (0, 33, 67, 100, 433, 1000, 12345):
            a, b = SAMPLE_TWICE(self.FPS, 19, ms)
            assert a == b

    def test_looping_clip_names(self):
        walk, run, idle, attack, build, death = LOOP_FLAGS()
        assert (walk, run, idle) == (1, 1, 1)
        assert (attack, build, death) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# Rigid pose / pivot term (items 1 and 2) -- the core of the slice
# --------------------------------------------------------------------------- #
class TestRigidPose:
    CLIPS = ("walk", "run", "attack_melee")

    @classmethod
    def setup_class(cls):
        cls.verts = lua_verts(obj_pieces())

    def test_engine_render_equals_the_rigid_pose(self):
        """Every frame/piece: M v + d == t_k + R (v - t_0), on real vertices."""
        for clip in self.CLIPS:
            worst = RIGID_VERTEX_WORST(clip, self.verts)
            assert worst < 1e-9, f"{clip}: engine render != rigid pose ({worst} elmo)"

    def test_bone_joint_maps_to_its_baked_position(self):
        """The joint must land on t_k: the pivot is what stays put."""
        for clip in self.CLIPS:
            worst = RIGID_WORST(clip)
            assert worst < 1e-9, f"{clip}: joint drifts from its baked position ({worst})"

    def test_rest_frame_is_a_no_op(self):
        """Frame 1 of idle IS the bind pose, so it must emit nothing."""
        worst_move, worst_rot = REST_NOOP_WORST()
        assert worst_move < 1e-9
        assert worst_rot < 1e-14

    def test_pivot_term_is_what_keeps_the_limbs_attached(self):
        """Omitting the pivot term must be visibly wrong.

        With this OBJ's pivot at the model origin, moving by the naive
        ``t_k - t_0`` swings hand and finger pieces tens of elmo off the wrist.
        The floor keeps the assertion meaningful if the bake is regenerated.
        """
        worst = NAIVE_PIVOT_WORST("walk", self.verts)
        assert worst > 5.0, (
            "the pivot term should matter by more than 5 elmo on this mesh; "
            f"measured {worst:.3f} -- did the bake or the OBJ change?"
        )


# --------------------------------------------------------------------------- #
# emit() drives pieces
# --------------------------------------------------------------------------- #
class TestEmit:
    def test_emit_drives_every_bound_piece(self):
        driven, done, total, turns, moves = EMIT_PROBE("walk", 0, "hip", "head", "thigh_l")
        assert driven == 3
        assert total == 18             # 3 pieces x (3 Turn + 3 Move)
        assert turns == 9
        assert moves == 9

    def test_emit_nothing_for_an_unknown_clip(self):
        driven, done = UNKNOWN_CLIP()
        assert driven == 0
        assert done == "true"

    def test_emit_ignores_unbound_pieces(self):
        """A context bound to pieces the bake does not carry drives nothing."""
        driven, _done, total, _turns, _moves = EMIT_PROBE("walk", 0, "not_a_bone")
        assert driven == 0
        assert total == 0

    def test_step_advances_the_clock(self):
        t1, t2, n1 = EMIT_STEP()
        assert n1 > 0, "step must emit"
        assert t1 == 33
        assert t2 == 66

    def test_emit_is_frame_absolute_not_cumulative(self):
        """Emitting the same timestamp twice must produce identical values."""
        same, count = EMIT_TWICE("walk", 500)
        assert count > 0
        assert same == 1

    def test_set_speed_ignores_non_positive_values(self):
        count, bad = SPEED_PROBE()
        assert count > 0
        assert bad is None, f"a non-positive speed leaked through: {bad}"


# --------------------------------------------------------------------------- #
# The infantry prototype wiring
# --------------------------------------------------------------------------- #
class TestInfantryWiring:
    @classmethod
    def setup_class(cls):
        cls.source = INFANTRY_PATH.read_text(encoding="utf-8")

    def test_loads_the_player_and_the_bake(self):
        assert "anim_player.lua" in self.source
        assert "animdata/medieval_infantry.lua" in self.source

    def test_still_a_pure_unit_script(self):
        assert "GG." not in self.source
        assert "VFS." not in self.source
        assert "gadgetHandler" not in self.source
        assert "UnitDefs" not in self.source

    def test_plays_the_expected_clips(self):
        assert re.search(r'currentClip\s*=\s*"walk"', self.source)
        assert re.search(r'currentClip\s*=\s*"idle"', self.source)

    def test_falls_back_when_the_bake_is_missing(self):
        """No player/bake must degrade to the procedural cadence, not crash."""
        assert "if startAnimThread() then return end" in self.source
        assert "while true do" in self.source

    def test_the_player_load_is_pcall_guarded(self):
        start = self.source.index("local function loadModule")
        end = self.source.index("local animPlayer")
        assert "pcall" in self.source[start:end]

    def test_infantry_bake_carries_the_clips_it_plays(self):
        names, fpss, counts = CLIP_INFO()
        info = {n: (int(f), int(c)) for n, f, c in
                zip(names.split(","), fpss.split(","), counts.split(","))}
        for name in ("walk", "run", "idle", "attack_melee", "build", "death"):
            assert name in info, f"bake is missing the {name} clip"
            fps, frames = info[name]
            assert fps == 30
            assert frames > 0

    def test_every_bake_piece_exists_in_the_obj(self):
        """A bake keyed to a piece the mesh lacks would silently no-op."""
        pieces = set(obj_pieces())
        missing = set()
        for clip in ("walk", "idle", "attack_melee"):
            for name in FRAME_PIECES(clip, 1).split(","):
                if name and name not in pieces:
                    missing.add(name)
        assert not missing, f"bake references pieces absent from the OBJ: {sorted(missing)}"
