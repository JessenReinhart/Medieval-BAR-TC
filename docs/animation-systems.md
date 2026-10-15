# Animation Systems Reference — 0 A.D. vs BAR / Recoil

Reverse-engineering notes for the Phase 7 animation port. Proven facts carry file:line
evidence; inferences are marked.

---

## 1. The two models at a glance

| | 0 A.D. (Pyrogenesis) | BAR (Spring / Recoil) |
|---|---|---|
| Deformation | **Vertex skinning** (weighted bone palette) | **Rigid piece hierarchy** (per-piece T·R·S) |
| Skeleton | Joint tree, bind pose, inverse-bind matrices | Named pieces, parent-child transform chain |
| Motion data | `.dae` COLLADA → cached `.psa` keyframes | Lua `Turn`/`Move`/`Spin` over time |
| Interpolation | Per-joint quaternion + translation sampling | Piece anims, thread/Signal blending |
| Coordinate space | World space (Z-up-ish 0 A.D. convention) | Model/piece-local (Y-up) |

The fundamental mismatch this project must bridge: **Pyrogenesis animates a smooth
skinned mesh by per-bone quaternion keyframes; Recoil animates rigid pieces by
rotate/translate primitives.** There is no native skinned-vertex path in the standard
Spring piece renderer, so the bones must be decomposed into pieces (the "bone-as-piece"
approach already used here).

---

## 2. 0 A.D. animation system

### 2.1 Authority chain

0 A.D.'s **build pipeline** converts COLLADA source into cached binaries at
archive-build time; the shipped `public.zip` contains only the cached results:

```
art/meshes/*.dae            (COLLADA)      art/animation/**/*.dae
      │    PMDConvert.cpp (WritePMD v4)              │ PSAConvert.cpp
      ▼                                            ▼
*.dae.cached.pmd (mesh)                      *.dae.cached.psa (motion)
      └──────────────── public.zip ─────────────────┘
```

This repo does **not** parse DAE: `tools/assets/convert_0ad.py` reads the shipped
0 A.D. alpha 28 **PMD v4** meshes directly (docstring, `convert_0ad.py:1`), and
`tools/assets/parse_psa.py` reads the shipped cached **PSA** motion. Cross-checked
engine sources: `source/graphics/SkeletonAnimDef.cpp/.h`, `source/ps/FileIo.cpp`,
`source/collada/PMDConvert.cpp`, `source/collada/PSAConvert.cpp`.

### 2.2 COLLADA `.dae` (source, not shipped)

- Geometry: `<geometry>` / `<source>` / `<float_array>` + `<polylist>`.
- Joints: `<library_visual_scenes>` → `<node type="JOINT">` nested parent→child.
- Skinning: `<library_controllers>` → `<skin>` with `bind_shape_matrix`,
  `<joints>`, and `inverse-bind-matrices`. This is where real bone names live.

### 2.3 PSA container format (reverse engineered in `tools/assets/parse_psa.py`)

All little-endian. Outer container from `CFileUnpacker`/`CFilePacker`:

```
struct FileHeader {
    char magic[4];      // "PSSA"
    u32  version;       // CSkeletonAnimDef::FILE_VERSION == 1
    u32  payloadSize;   // bytes after this 12-byte header
}
```

Payload written by `CSkeletonAnimDef::Save` (see parse_psa.py for the full struct) is a
sequence of `PackString` length-prefixed fields plus per-frame joint transforms. Frames
store **quaternion rotations + translation vectors per joint**, keyed by joint name
order implied by the skeleton, at a fixed frame duration.

### 2.4 Mesh deformation in 0 A.D.

Weighted skinning: each vertex accumulates `Σ wᵢ · Mᵢ · v` over its influencing bones,
where `Mᵢ = bone_world · inverse_bindᵢ`. Palette/matrix skinning in the shader (or
dual-quaternion variants). This is fundamentally incompatible with Recoil's
rotate-about-piece-origin rigid model.

---

## 3. BAR / Spring / Recoil animation system

### 3.1 Architectural model

Named rigid pieces, one vertex buffer + one `T·R·S` per piece; **no skin weights**.
Render = rotate about piece origin, then translate. Repo OBJ pieces have `offset = 0`
→ pivot at model origin (reasons for the pivot hacks in `anim_player.lua`).

### 3.2 LUS primitives (`Spring.UnitScript`, from BAR research)

| API | Axis | Units |
|---|---|---|
| `Turn(p, axis, angle, speed)` | 1=x 2=y 3=z | radians, rad/s (destination is **absolute**) |
| `Move(p, axis, dist, speed)` | 1=x 2=y 3=z | elmo, elmo/s (destination is **absolute**) |
| `Spin(p, axis, speed[, accel])` | | rad/s, rad/s² |
| `StopSpin(p, axis[, decel])` | | rad/s² |
| `TurnNow` / `MoveNow` | | instant |
| `WaitForTurn` / `WaitForMove` | | bool "in flight" |

Euler order for `Turn(rx,ry,rz)`: **yaw(2) → pitch(1) → roll(3)** = `Rz(rz)·Rx(rx)·Ry(ry)`.

### 3.3 Framework (`luarules/gadgets/unit_script.lua`)

- Coroutine threads; `Sleep(ms)` = `floor(ms/33)` frames bucketed into `sleepers[frame]`,
  drained by `GameFrame`.
- `WaitForTurn`/`Move` gate on engine native, yield only if an anim is running, resume
  from injected `TurnFinished`/`MoveFinished`/`ScaleFinished` callins.
- `Signal`/`SetSignalMask` = bitmask preemption.
- Long callins (`Create/Killed/AimWeapon/FireWeapon`) are thread-wrapped;
  `StartMoving`/`StopMoving` are **not** thread-wrapped (stride loop must spawn its own thread).

### 3.4 Clip player (`scripts/anim_player.lua`)

Pure-Lua; absolute-ms sampler; relative quaternion `q_k·conj(q0)` → matrix → exact euler
inverse; rebuilds `R` from emitted angles; emits `d = v_k − R·t0` plus
`Turn(axis, rx/ry/rz)` per piece. 30 fps bake from 0 A.D. PSA.

### 3.5 Trade-offs

Simple, deterministic, cache-friendly, zero shader cost, desync-safe — at the price of:
no weighted skinning, faceted joint motion, no true blending (thread race + signal
preemption instead), per-piece pivot hacks.

---

## 4. Integration gap audit (proven, file:line)

The math pipeline (`parse_psa.py` → `read_psa_content.world_pose` →
`convert_0ad_anim` bake → `anim_player.lua`) is **internally consistent**:

- OBJ yaw = `(-x, y, -z)*8` (`tools/assets/convert_0ad.py:453`).
- `world_pose` = `(-tx*8, ty*8, -tz*8)` + `Q_y180 ⊗ q`
  (`tools/assets/read_psa_content.py:90-92`).

The real defects are in **LUS piece wiring**:

### 4.1 Weapon clobbers the `hip` binding → pelvis never animates

`scripts/medieval_infantry.lua:146-159` binds each handle by scanning `idle.frames[1]`
keys; the fallback is hardcoded `name = "hip"` (line 150), and `bindPiece` overwrites
unconditionally (`scripts/anim_player.lua:245-248`).

- `weapon` is in `PARTS` (`medieval_infantry.lua:49,60`) and is a real OBJ piece
  (`objects3d/0ad/medieval_infantry.obj:4239`).
- `weapon` is **not** in the bake (`scripts/animdata/medieval_infantry.lua` header says
  "25 pieces"; no `["weapon"]` key). Same for `greave_07_l/r`.
- So the weapon handle finds no `restFrame` key → `name` stays `"hip"` →
  `bindPiece(ctx,"hip", weaponHandle)` overwrites the real hip binding.

Result: `ctx.pieces["hip"]` = weapon handle; the **weapon** is driven with the **hip**
world pose, and the real pelvis is driven by nothing → flailing detached weapon,
frozen pelvis.

### 4.2 Twelve pieces never bound → frozen

`PARTS` (`medieval_infantry.lua:57-61`) lists 16 handles (hip, spine, chest, head,
thigh, leg, foot, arm, forearm, weapon, shield — l/r pairs). Omitted but present in the
OBJ: `shoulder_l/r`, `hand_l/r`, `finger_l/r`, `fingertip_l/r`, `neck`, `greave_07_r/l`,
`helmet`. These remain at their default pose and never move.

### 4.3 Two unverified upstream assumptions

Marked as inference pending runtime confirmation; the loader simply emitting
`clips=6` (the recent "fix") proves module initialization only, not correct motion.

---

## 5. Recommended next steps (prioritized)

1. **Fix the hip-binding collision** — never fall back to `"hip"` for pieces with no
   baked channel; bind only pieces that exist in `idle.frames[1]`, and leave
   non-animated pieces (weapon, shield, helmet, greaves) at their authored rest pose.
2. **Complete the piece/bone name map** — reconcile the "25 pieces" in the bake against
   the OBJ face groups, and make `PARTS` cover every OBJ group (shoulder, hand, finger,
   neck, helmet, greaves) so nothing freezes.
3. **Runtime visual verification** — emit a per-unit one-time pose snapshot (driven
   piece handle → joint name + channel coverage) and diff against the baked rest pose,
   rather than relying on `clips=6` alone.
