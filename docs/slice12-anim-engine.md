# Phase 7 Slice 12 — LUS Animation Playback Engine

> **Deliverables:** `scripts/anim_player.lua` (playback module),
> `scripts/medieval_infantry.lua` (prototype wiring),
> `tests/test_phase7_slice12_anim.py`, and the pivot investigation below.

---

## 1. Investigation: piece pivot behaviour in the Spring / Recoil OBJ loader

All findings are from `beyond-all-reason/RecoilEngine@master` — the engine this
repo ships as `tools/engine/recoil_2026.07.04`. Files formerly under
`beyond-all-reason/spring` were moved during the Recoil rename
(`AssimpModel.cpp`/`ObjPiece` → `rts/Rendering/Models/AssParser.cpp`; the old
standalone `OBJModel.cpp` no longer exists).

### 1.1 Where the rotation happens

```cpp
// rts/Rendering/Models/3DModelPiece.cpp:206-220
Transform S3DModelPiece::ComposeTransform(const float3& t, const float3& r, float s) const
{
    //   ORDER MATTERS (T(baked + script) * R(baked) * R(script) * S(baked))
    Transform tra;
    tra.t = t;
    if (bakedTransform.has_value())
        tra *= bakedTransform.value();
    tra *= Transform(CQuaternion::FromEulerYPRNeg(-r), ZeroVector, s);
    return tra;
}
```

```cpp
// rts/System/Transform.hpp:81-85
inline float3 Transform::operator*(const float3& v) const
{
    // Scale, Rotate, Translate
    return r.Rotate(v * s) + t;
}
```

Vertices are **rotated first, then translated** by the piece translation. The
rotation therefore always happens about the **piece-local origin**. It is never
about a joint and never about the model origin — unless the piece origin *is*
the model origin.

### 1.2 Where the pivot is

```cpp
// rts/Rendering/Models/AssParser.cpp:213-216
piece->offset = pieceTable.GetFloat3("offset", aiVectorToFloat3(aiTransVec));
piece->offset.x = pieceTable.GetFloat("offsetx", piece->offset.x);
// ... y, z
```

The pivot is the Assimp node translation (`aiTransVec`), overridable by
`offset` / `offsetx` / `offsety` / `offsetz` metadata. Vertices are **not**
rewritten by the loader: `AssParser` does not request
`aiProcess_PreTransformVertices` (lines 51-62), so vertices stay node-local and
the node translation is applied as the `T` above rather than baked in.

### 1.3 What that means for *this* repo's OBJ

`objects3d/0ad/*.obj` is emitted by `tools/assets/convert_0ad.py` as plain
`o <name>` groups with **no node transforms at all** — every vertex is already in
one model-space frame:

```
o hip
usemtl hip
v 0 20.6386395 -1.50343204
...
```

So every piece's Assimp node translation is the identity and **every piece
offset is 0**. The pivot of every piece is therefore the model origin
`(0, 0, 0)`.

This is exactly the failure mode the slice was asked to check for. Measured on
`objects3d/0ad/medieval_infantry.obj`:

| piece | vertex distance from origin |
|---|---|
| `hip` | ~17 elmo |
| `head` | ~30 elmo |
| `hand_r` | ~19 elmo |
| `foot_l` | ~3.6 elmo |

Calling `Turn(hand_r, 1, θ)` alone swings the hand **around the feet**. The
rotation must be paired with a translation; supplying that translation is what
`scripts/anim_player.lua` does.

### 1.4 Turn()/Move() semantics

```cpp
// rts/Sim/Units/Scripts/UnitScript.cpp:523-543
void CUnitScript::MoveNow(int piece, int axis, float destination)
{
    float3 pos = p->GetPosition();
    float3 ofs = p->original->offset;
    const float newValue = ofs[axis] + destination;   // RELATIVE to the offset
    ...
}
// :546-565
void CUnitScript::TurnNow(int piece, int axis, float destination)
{
    rot[axis] = ClampRad(destination);                // ABSOLUTE angle
    ...
}
```

* `Move(piece, axis, d)` sets `pos[axis] = offset[axis] + d` — `d` is a delta.
* `Turn(piece, axis, a)` sets `rot[axis] = a` — `a` is absolute.

Axis constants are **1 = x, 2 = y, 3 = z**, not bit flags
(`rts/Sim/Units/Scripts/LuaUnitScript.cpp:109`, `ParseAxis` at :1135-1147), which
matches the `x_axis`/`y_axis`/`z_axis` this repo already defines in
`luarules/gadgets/unit_script.lua`.

### 1.5 Rotation order and sign

```cpp
// rts/System/Quaternion.h:50-53
static CQuaternion FromEulerYPRNeg(const float3& angles) { return FromEulerYPR(-angles); }
// Euler angles, also known as RotateEulerYXZ
static CQuaternion FromEulerYPR(const float3& angles);
```

```cpp
// rts/System/Matrix44f.cpp:272-279
CMatrix44f& CMatrix44f::RotateEulerYXZ(const float3& angles)
{
    // rotate around Y first, X second, Z third (R=R(Z)*R(X)*R(Y))
    if (angles[ANGLE_Y] != 0.0f) { RotateY(angles[ANGLE_Y]); }
    if (angles[ANGLE_P] != 0.0f) { RotateX(angles[ANGLE_P]); }
    if (angles[ANGLE_R] != 0.0f) { RotateZ(angles[ANGLE_R]); }
    return *this;
}
```

Two things follow.

1. **The two minus signs cancel.** `ComposeTransform` calls
   `FromEulerYPRNeg(-r)`, and `FromEulerYPRNeg(x) == FromEulerYPR(-x)`, so the
   script rotation quaternion is exactly `FromEulerYPR(r)`.
2. **The order is Y → X → Z**, i.e. `R = Rz(rz) · Rx(rx) · Ry(ry)`. With
   `ANGLE_P = 0` (pitch/x), `ANGLE_Y = 1` (yaw/y), `ANGLE_R = 2` (roll/z), the
   `Turn()` vector is `(rx, ry, rz) = (pitch, yaw, roll)`.

`anim_player.eulerMatrix` reproduces this exactly; `anim_player.angles` is its
exact inverse.

---

## 2. The transform the player emits

The engine renders a piece as

```
v' = M v + (offset + d)          M = Rz(rz) Rx(rx) Ry(ry),  offset = 0
```

The rigid pose a baked clip describes is "rotate the piece about its own bone
joint and move that joint to where the bake puts it":

```
v' = t_k + R (v - t_0)           t_0 = rest translation (idle frame 1)
                                 t_k = baked translation at frame k
```

Matching the two gives the whole recipe:

```
R  = rotation matrix of the relative unit quaternion  q_rel = q_k · conj(q_0)
rx, ry, rz = angles(R)           the exact inverse of eulerMatrix
d  = t_k - R t_0                 the frame translation AND the pivot term
```

* At `k = 0` (idle frame 1) this collapses to `d = 0`, identity rotation — the
  rest frame is a no-op.
* No separate "pivot compensation" term is needed: because the joint position
  parameterises the rotation *and* the translation, `t_k - R t_0` is
  simultaneously the bone motion and the offset that keeps the piece attached.
* **Omitting the pivot part** (using the naive `t_k - t_0`) is off by up to
  **26 elmo** on `fingertip_l`, 16.9 on `hand_r`, 11.2 on `thigh_l` — the limbs
  visibly detach. This is asserted as a floor in
  `tests/test_phase7_slice12_anim.py::TestRigidPose::test_pivot_term_is_what_keeps_the_limbs_attached`.

### Verification

Derivation was checked offline against the real OBJ and the real bake, over every
frame of every clip and every sampled vertex:

| property | measured |
|---|---|
| `quatMatrix(q_axis)` vs `Rot_x/Rot_y/Rot_z` | 1.1e-16 |
| `R(q_rel) · R(q_0) == R(q_k)` | 2.2e-16 |
| `eulerMatrix(angles(M)) == M`, 50k random rotations | 2.5e-15 |
| bone joint `t_0` maps to `t_k` under the emitted Turn/Move | 1.8e-15 |
| **engine render == rigid pose, all walk frames** | **1.4e-14 elmo** |
| rest frame emits zero | 1.6e-15 |
| naive `t_k - t_0` (pivot term omitted) | 26.06 elmo |

Confirmed a second time from the Lua module itself, over every frame of
`walk` / `run` / `attack_melee` and real OBJ vertices, against an independent
Python rebuild of the same matrices:

| property | measured |
|---|---|
| module angles rebuild the engine matrix (`Rz Rx Ry`) | 7.8e-15 |
| engine render == rigid pose on real OBJ vertices | 1.4e-14 elmo |

One real bug was caught by these tests: `sample()` used a 0-based index for the
looping branch, so **every looping clip returned `nil`** and `emit` silently drove
nothing. Fixed to `(advance % #frames) + 1`.

---

## 3. `scripts/anim_player.lua`

A pure Lua module: no `Spring.*`, no `VFS.*`, no global reads. It is loadable in a
bare interpreter, which is what the pytest suite does.

`math.atan2` was removed in Lua 5.3 (renamed `math.atan(y, x)`, and the old name
dropped entirely in 5.4). The engine and this repo's `lupa` interpreter expose
different names, so the module resolves it once at load:

```lua
local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
```

```lua
local player = VFS.Include("scripts/anim_player.lua")   -- returns an unexecuted chunk
local ctx = player.new()
player.setClips(ctx, animData)
player.setPrimitives(ctx, Turn, Move)   -- resolved per call, not captured
player.setSpeed(ctx, 14)                -- rad/s and elmo/s
player.bindRest(ctx, animData.idle)     -- rest pose = idle frame 1
player.bindPiece(ctx, "hip", handle)
player.emit(ctx, "walk", elapsedMs)     -- drive one frame
player.advance(ctx, dtMs)               -- advance the clock
```

| function | purpose |
|---|---|
| `new()` | fresh playback context |
| `setClips(ctx, clips)` | the `scripts/animdata/*.lua` table |
| `setPrimitives(ctx, turn, move)` | the engine call-ins; re-read every frame so a stub or a missing call-in degrades instead of crashing |
| `setSpeed(ctx, s)` | Turn/Move speed; non-positive values are ignored |
| `bindPiece(ctx, name, handle)` | bake bone name → engine piece handle |
| `bindRest(ctx, clip)` | rest pose, defaults to idle frame 1 |
| `setPivot(ctx, handle, t)` | override the pivot; defaults to the piece's rest translation |
| `emit(ctx, clip, ms)` | emit one frame; returns `driven, done` |
| `step(ctx, clip, dtMs)` | advance the clock and emit |
| `sample(clip, ms, looping)` | frame lookup; loops wrap, one-shots clamp and report `done` |
| `angles(M)` / `eulerMatrix(rx,ry,rz)` | the engine's rotation order and its exact inverse |
| `quatMatrix(q)` / `relative(qk, q0)` | rotation matrix and `q_k · conj(q_0)` |

Sampling is **absolute in time**: `emit(ctx, clip, ms)` depends only on `ms`, so a
dropped or duplicated call cannot accumulate drift.

Unbaked pieces (`weapon`, `shield`, `greave_07_l/r` in this unit — the bake
carries 25 bones, the OBJ 28 pieces) simply stay at their rest pose.

---

## 4. Prototype wiring in `scripts/medieval_infantry.lua`

* Loads `scripts/anim_player.lua` and `scripts/animdata/medieval_infantry.lua`
  through a pcall-guarded helper. The virtual filesystem is looked up by name
  (`_G["VFS"]`) so the script keeps the Slice 4 contract of containing no `VFS.`
  token, and a build without it simply leaves `animCtx` nil.
* Binds every distinct resolved handle to the bone whose bake owns it, falling
  back to the root bone so a single-hull mesh still animates.
* `StartMoving` — spawns one playback thread that follows `currentClip`, and
  **falls back to the original procedural stride** when there is no bake.
* `StopMoving` — signals and switches `currentClip` to `idle`.
* `FireWeapon1` — plays the baked `attack_melee` clip as a one-shot (resetting
  the clock first so consecutive swings restart), then rests; falls back to the
  hand-authored thrust.
* `Killed` — unchanged; the death tumble still holds the wreck level.

### Caveats / follow-ups

* **The attack clip is one-shot and unblended.** Switching from `walk` to
  `attack_melee` jumps to a different root translation. A blend layer (cross-fade
  over ~100 ms, offsetting `t_0` by the outgoing pose) is the natural next step.
* **`Killed` does not yet play the `death` clip.** The call-in is thread-wrapped
  and returns `1` after a `Sleep`, so wiring it is straightforward, but the
  existing slice 4 contract was left intact deliberately.
* **`idle` only plays on the next tick after a stop.** `StopMoving` may not
  `Sleep`, so the playback thread picks the clip up one frame later.
* **Root motion is applied.** The bake is absolute world-pose, so the walk/run
  clips carry their own root translation. If the engine also drives the unit
  forward, the two can fight; clamping or stripping the root piece's translation
  (`setPivot` + a per-clip flag) is the lever if that shows up in game.
* **Only `medieval_infantry` is wired.** `medieval_archer`, `medieval_villager`,
  `medieval_spearman` and `medieval_cavalry` have bakes under
  `scripts/animdata/` and the same loader pattern applies.