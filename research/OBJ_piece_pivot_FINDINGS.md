# Spring/Recoil OBJ & S3O piece ROTATION PIVOT — authoritative findings

Repo used: `beyond-all-reason/RecoilEngine` branch `master` (this is BAR's engine, binary `recoil_2026.07.04`).
Note: the repo formerly named `beyond-all-reason/spring` is now `RecoilEngine`. The file layout has been
refactored vs old upstream Spring, so the paths the question references have moved:

| old/upstream path (question)         | current RecoilEngine path                              |
|--------------------------------------|--------------------------------------------------------|
| `rts/Rendering/Models/AssimpModel.cpp` (AssimpModelLoader / ObjPiece) | `rts/Rendering/Models/AssParser.cpp/.h` (`SAssPiece`, `SPseudoAssPiece`) |
| `rts/Rendering/Models/OBJModel / S3O` | OBJ removed → Assimp (`AssParser`); S3O → `S3OParser.cpp/.h` |
| `rts/Lua/LuaUnitScript.cpp` (Turn/Move/PieceTransform/GetPieceMatrix) | `rts/Sim/Units/Scripts/LuaUnitScript.cpp` + `UnitScript.cpp`; matrix building → `rts/Rendering/Models/LocalModelPiece.cpp` + `3DModelPiece.cpp` |
| `rts/Rendering/Models/ModelPiece` / GetModelPiece / GetPiecePos | `S3DModelPiece` (`3DModelPiece.hpp/.cpp`), `LocalModelPiece` (`LocalModelPiece.hpp/.cpp`) |

`PieceTransform`/`GetPieceMatrix` (the old function names) no longer exist. Their role is now
`S3DModelPiece::ComposeTransform()` and `LocalModelPiece::GetModelSpaceMatrix()`.

Raw URLs: `https://raw.githubusercontent.com/beyond-all-reason/RecoilEngine/master/<path>`
Blob URLs: `https://github.com/beyond-all-reason/RecoilEngine/blob/master/<path>#Lxx`

---

## 1. Assimp/OBJ piece parenting — root piece vs. model root (piece 0)

**There is always a root piece (the Assimp `mRootNode`), and every non-root piece is attached either to a
named parent (from piece metadata `parent`) or, if it has no named parent, directly to the root piece.**

`AssParser.cpp` `LoadPiece()` (lines ~992–1048):
```cpp
SAssPiece* CAssParser::LoadPiece(model, pieceNode, scene, modelTable, skipList, pieceMap, parentMap, optRotation)
{
    if (pieceNode->mParent == nullptr) {          // scene->mRootNode
        model->AddPiece(piece);                    // root piece added first (piece 0)
    }
    ...
    LoadPieceTransformations(piece, model, pieceNode, pieceTable, optRotation);
    LoadPieceGeometry(piece, model, pieceNode, scene);
    SetPieceParentName(piece, model, pieceNode, pieceTable, parentMap);
    ...
    for (i = 0; i < pieceNode->mNumChildren; ++i)
        LoadPiece(model, pieceNode->mChildren[i], ...);   // recursive
    pieceMap[piece->name] = piece;
}
```

`AssParser.cpp` `BuildPieceHierarchy()` (lines 1052–1096) — this is the decisive code:
```cpp
// Because of metadata overrides we don't know the true hierarchy until all pieces have been loaded
void CAssParser::BuildPieceHierarchy(S3DModel* model, ModelPieceMap& pieceMap, const ParentNameMap& parentMap)
{
    for (auto it = pieceMap.cbegin(); it != pieceMap.cend(); ++it) {
        SAssPiece* piece = static_cast<SAssPiece*>(it->second);
        if (piece == model->GetRootPiece()) { assert(piece->parent == nullptr); continue; }

        const auto parentNameIt = parentMap.find(piece->name);
        if (parentNameIt != parentMap.end()) {            // has a named parent
            const std::string& parentName = parentNameIt->second;
            const auto pieceIt = pieceMap.find(parentName);
            if (pieceIt != pieceMap.end()) {
                piece->parent = pieceIt->second;          // re-parent under the named piece
                piece->parent->children.push_back(piece);
            } else {
                LOG_SL(... "Missing piece '%s' declared as parent of '%s'." ...);
            }
            continue;
        }
        // piece with no named parent that isn't the root (orphaned) -> link to the root piece
        if ((piece->parent = model->GetRootPiece()) == nullptr) { ... }
        else { piece->parent->children.push_back(piece); }
    }
    model->FlattenPieceTree(model->GetRootPiece());
}
```

Answer: pieces are **parented into a tree rooted at one root piece (piece 0 = `mRootNode`)**. Sub-pieces can
form deeper hierarchies only if the model's `pieces` metadata supplies a `parent` field; otherwise every
piece is a direct child of the root. Confirmed by the recursive `LoadPiece` + the two branches in
`BuildPieceHierarchy`.

---

## 2. Offset / "center" handling and the rotation origin

### S3O (`S3OParser.cpp`, lines 104–185)
- The S3O per-piece offset is read verbatim from the file (no subtraction):
```cpp
piece->offset.x = fp->xoffset;   // lines 125-127
piece->offset.y = fp->yoffset;
piece->offset.z = fp->zoffset;
```
- Vertices are read raw — **no offset subtraction** in the loader:
```cpp
sv.pos = float3(v->xpos, v->ypos, v->zpos);   // line 140
```
- `goffset` accumulates parent translation; model bounds are `goffset + piece-local min/max`:
```cpp
piece->goffset = piece->offset + ((parent != NULL)? parent->goffset: ZeroVector);   // line 163
...
model->mins = float3::min(piece->goffset + piece->mins, model->mins);              // lines 169-170
model->maxs = float3::max(piece->goffset + piece->maxs, model->maxs);
```
`SetMinMaxExtends()` (lines 187–194) computes `mins/maxs` from the **raw** `v.pos`. Because the model bounds
need `goffset + piece.mins`, the S3O vertex positions are stored **piece-LOCAL, already relative to the
piece offset**. The exporter (Upspring) is expected to place vertices relative to the piece anchor; the
engine applies the offset as a translation at draw time and does **not** subtract it from the vertices.

### OBJ — now loaded by Assimp (`AssParser.cpp`), the old `OBJModel.cpp` is gone
`.obj` is whitelisted for the Assimp parser — `IModelParser.cpp` lines 48–100:
```cpp
static bool CheckAssimpWhitelist(const char* aiExt) {
    constexpr std::array<const char*, 5> whitelist = { "3ds", "dae", "lwo", "obj", "blend" };
    ...
}
// 3do -> g3DOParser ; s3o -> gS3OParser ; gltf/glb -> gGLTFParser ;
// obj (and other whitelisted) -> gAssParser
```
`AssParser.cpp` `LoadPieceTransformations` (lines 182–259):
```cpp
pieceNode->mTransformation.Decompose(aiScaleVec, aiRotateQuat, aiTransVec);          // line 195
...
piece->offset = pieceTable.GetFloat3("offset", aiVectorToFloat3(aiTransVec));        // line 213
piece->offset.x = pieceTable.GetFloat("offsetx", piece->offset.x);                   // 214-216
...
auto Quat = CQuaternion(aiRotateQuat.x, aiRotateQuat.y, aiRotateQuat.z, aiRotateQuat.w);
if (optRotation) Quat = (*optRotation) * Quat;                                       // 254-256
Transform bakedTransform(CQuaternion::FromEulerYPRNeg(-bakedRotAngles) * Quat, ZeroVector, 1.0f); // 258
piece->SetBakedTransform(bakedTransform);
```
Comment at lines 247–252 states Assimp order is `Translate * Rotate * Scale * v`, with translation split into
`<offset>` and scale into `<scales>`, so the baked part reduces to a rotation.

Also for `s3ocompat` models the whole root is pre-rotated 180° about Y (lines 610–612):
```cpp
const auto rootPieceRot = CQuaternion(0, 1, 0, 0); // rotate 180 around Y
LoadPiece(&model, scene->mRootNode, scene, modelTable, meshNames, pieceMap, parentMap, &rootPieceRot);
```

`LoadPieceGeometry` uses the raw Assimp mesh vertices (line 866) and `ASS_POSTPROCESS_OPTIONS`
(lines 51–62) does **not** include `aiProcess_PreTransformVertices`, so OBJ vertex data stays in node-local
space. The piece's `offset` = the OBJ node's translation (overridable with `offset`/`offsetx/y/z` metadata).

> UNCONFIRMED (historical): the pure-old upstream `OBJModel.cpp`/`OBJPiece` loader is removed in RecoilEngine
> master and I could not retrieve its source (`spring/spring` tags 91.0/96.0/98.0 have no
> `rts/Rendering/Models/OBJModel.cpp`). Its exact "subtract center from vertices" behavior is NOT verified here.
> For the engine this mod actually runs, OBJ = Assimp with the behavior above.

---

## 3. Lua Unit Script Turn/Move/TurnNow — axis order and exact composition

### Script side (no matrix math here; it only mutates a `float3 rot` / `float3 pos`)
`LuaUnitScript.cpp::Turn/Move` (lines 1584–1636) parse `axis = ParseAxis(L,_,2)` and dispatch:
```cpp
const int piece = luaL_checkint(L, 1) - 1;      // 1-based piece -> 0-based
const int axis  = ParseAxis(L, __func__, 2);
const float dest  = luaL_checkfloat(L, 3);
const float speed = luaL_optfloat(L, 4, 0.0f);  // speed == 0 -> TurnNow
if (speed == 0.0f) activeScript->TurnNow(piece, axis, dest);
else               activeScript->Turn(piece, axis, speed, dest);
```
`ParseAxis` (lines 1135–1147): `axis = lua_toint(L,index) - 1; if (axis<0 || axis>2) error`. **1=x, 2=y, 3=z.**

`UnitScript.cpp`:
- `TurnNow` (546–565): `rot = p->GetRotation(); rot[axis] = ClampRad(destination); p->SetRotation(rot);`
- `Turn` (504–508) → `AddAnim(ATurn, piece, axis, fabs(speed), ClampRad(dest), 0)`.
- `TickTurnAnim` (311–320): `rot[ai.axis] = TurnToward(rot[ai.axis], ai.dest, speed/tickRate)` (shortest-path).
- `TickSpinAnim` (322–331): `rot[ai.axis] = DoSpin(...)`.
- `Move` (511–515) → `AddAnim(AMove, ...)`; `MoveNow` (523–543) and `AddAnim` (379–453) add the rest offset:
```cpp
// AddAnim, lines 388-395
if (type == AMove) {
    destf = p->original->offset[axis] + dest;    // <-- Move dest is RELATIVE to the piece offset
} else {
    destf = mix(dest, ClampRad(dest), type == ATurn);
}
```
```cpp
// MoveNow, lines 532-541
float3 pos = p->GetPosition();
float3 ofs = p->original->offset;
const float newValue = ofs[axis] + destination;  // absolute pos = offset + script dest
pos[axis] = newValue;
p->SetPosition(pos);
```
So **Move destination is an offset relative to the piece's rest `offset`**; **Turn destination is an absolute
angle on that axis** (no offset added). `GetPieceTranslation` returns `pos - offset` (LuaUnitScript.cpp:1907),
confirming the invariant.

### Matrix composition (authoritative) — `3DModelPiece.cpp::ComposeTransform` (lines 206–220)
```cpp
Transform S3DModelPiece::ComposeTransform(const float3& t, const float3& r, float s) const
{
    // NOTE:
    //   ORDER MATTERS (T(baked + script) * R(baked) * R(script) * S(baked))
    Transform tra;
    tra.t = t;
    if (bakedTransform.has_value())
        tra *= bakedTransform.value();
    tra *= Transform(CQuaternion::FromEulerYPRNeg(-r), ZeroVector, s);
    return tra;
}
```
`LocalModelPiece.cpp` (lines 62, 185–198, 210–243):
```cpp
pos = piece->offset;                                   // rest position = the piece offset (line 62)
...
modelSpaceTra = pTra * pieceSpaceTra;                  // parent chain (lines 187/194/215/239)
// pieceSpaceTra = CalcPieceSpaceTransform(pos, rot, scale) = ComposeTransform(pos, rot, scale)
```
`LocalModelPiece::Draw()` (lines 270–275) applies it:
```cpp
glPushMatrix();
glMultMatrixf(GetModelSpaceMatrix());   // = modelSpaceTra.ToMatrix()
original->DrawElements();               // raw (piece-local) vertices
glPopMatrix();
```

### Axis order — `FromEulerYPR` = `RotateEulerYXZ`
`System/Quaternion.h` (lines 45–53):
```cpp
// Euler angles, also known as RotateEulerXYZ
static CQuaternion FromEulerPYR(const float3& angles);
// Euler angles, also known as RotateEulerYXZ, produces the same rotation as CMatrix44f::RotateEulerYXZ()
static CQuaternion FromEulerYPRNeg(const float3& angles) { return FromEulerYPR(-angles); };
static CQuaternion FromEulerYPR(const float3& angles);
```
`System/Matrix44f.h` (lines 43–50, 127–129):
```cpp
CMatrix44f& RotateX(float angle); // (pitch) angle in radians
CMatrix44f& RotateY(float angle); // (  yaw) angle in radians
CMatrix44f& RotateZ(float angle); // ( roll) angle in radians
CMatrix44f& RotateEulerXYZ(const float3& angles); // executes Rotate{X,Y,Z}
CMatrix44f& RotateEulerYXZ(const float3& angles); // executes Rotate{Y,X,Z}
...
    ANGLE_P = 0,   // pitch = x
    ANGLE_Y = 1,   // yaw   = y
    ANGLE_R = 2,   // roll  = z
```
`System/Matrix44f.cpp::RotateEulerYXZ` (lines 272–279):
```cpp
// rotate around Y first, X second, Z third (R=R(Z)*R(X)*R(Y))
if (angles[ANGLE_Y] != 0.0f) { RotateY(angles[ANGLE_Y]); }
if (angles[ANGLE_P] != 0.0f) { RotateX(angles[ANGLE_P]); }
if (angles[ANGLE_R] != 0.0f) { RotateZ(angles[ANGLE_R]); }
```
`FromEulerYPR` (Quaternion.cpp:48–68) builds the quaternion from `angles[P]`, `angles[Y]`, `angles[R]` with
the same `R = R(roll)·R(pitch)·R(yaw)` relative layout.

**Resulting composition, per piece:**
```
modelSpace = parent · T(pos) · R(baked) · R(script) · S(scale)
pos  = offset + (Move dest per axis)          // translation applied FIRST
R(script) = FromEulerYPRNeg(-rot) ≡ FromEulerYPR(rot)   // note double negation in the call
          = RotateEulerYXZ(rot) = Rz(rot.z=roll) · Rx(rot.x=pitch) · Ry(rot.y=yaw)
```
i.e. the three per-axis turns combine as **yaw (Y) first, then pitch (X), then roll (Z)**, acting on the
left of the vector: `v' = T·Rz·Rx·Ry·v` (yaw applies first to the vertex). There is no per-call ordering —
`Turn()` just sets one component of `rot`; the final rotation is a single Euler build from all three.

---

## 4. Vertices: model space vs. piece-local

**Vertices are stored piece-LOCAL relative to the pivot, and the piece's rest position (`offset`) is applied
as a translation in the matrix — not baked into (and not subtracted from) the vertices.**

Evidence:
- `LocalModelPiece` field comment (`LocalModelPiece.hpp:106–108`):
```cpp
float3 pos;   // translation relative to parent LMP, *INITIALLY* equal to original->offset
float3 rot;   // orientation relative to parent LMP, in radians (updated by scripts)
float scale;  // uniform scaling
```
- Constructor `pos = piece->offset;` (`LocalModelPiece.cpp:62`).
- Draw path multiplies the local vertex data by `GetModelSpaceMatrix()` (`LocalModelPiece.cpp:270–275`).
- S3O bounds use `goffset + localMinMax` (`S3OParser.cpp:169–170`) ⇒ vertices already piece-local.
- Assimp keeps vertices in node-local space (no `aiProcess_PreTransformVertices`, `AssParser.cpp:51–62`,
  raw copy at `:866`), and the node translation becomes `offset` (`:213`).

So for OBJ the **rotation origin / pivot = the OBJ node's own origin** (its translation = `offset`), because
the mesh data is authored in that node's local frame. For S3O the pivot = the file's per-piece `offset`.

---

## 5. Axis constants and sign/handedness

- **Values: 1 = x, 2 = y, 3 = z** (1-based; NOT 1/2/4). Engine header comment (`LuaUnitScript.cpp:109`)
  "all axes are 1 based, so 1 = x, 2 = y, 3 = z"; `ParseAxis` enforces `axis-1 ∈ {0,1,2}`; wiki
  Animation-LuaCallouts: "axis: number (1 = x axis, 2 = y axis, 3 = z axis)". (The 1/2/4 bitmask is a
  COB/`get`-thread convention, not LUS axis args.)
- **Component mapping** (`Matrix44f.h:127–129` + `:43–45`): `rot.x = pitch`, `rot.y = yaw`, `rot.z = roll`.
- **Handedness:** Spring unit models (SolidObjects) are **LEFT-handed**. `System/Matrix44f.cpp:700–719`:
```cpp
// NOTE:
//   this assumes a RIGHT-handed coordinate system, but
//   in Spring all SolidObjects use LEFT-handed systems
//   instead
```
- **Sign/direction:** `ComposeTransform` passes `FromEulerYPRNeg(-r)`, and since
  `FromEulerYPRNeg(a) ≡ FromEulerYPR(-a)`, this reduces to `FromEulerYPR(r)` — i.e. the authored `rot` is
  applied verbatim as the YPR/YXZ Euler rotation in the left-handed object frame (the `Neg`+-`-r` pair cancel;
  see `3DModelPiece.cpp:218` + `Quaternion.h:51`). Community-facing direction: wiki says `Turn` "Always uses the
  shortest angular [path]; if at exactly 180 degrees opposite, will go counter-clockwise", and `Move` "X axis is
  mirrored compared to BOS/COB scripts" (matching `LuaUnitScript.cpp:110–112`). For negative/positive rotation
  direction per software, modellers override per-piece via the `rotAxisSigns` metadata key (see §6).

---

## 6. Known caveat — rotating around the piece pivot vs. the model origin

Primary sources:
- **Engine:** For both S3O and Assimp/OBJ, rotation is about the piece's own pivot (its `offset`; for OBJ the
  OBJ node origin), because vertices are piece-local and the matrix is `T(offset)·R·...` before drawing
  (`LocalModelPiece.cpp:62,185–198,210–243,270–275`). Rotating a piece does **not** rotate about the model
  origin unless that piece's `offset` is `(0,0,0)`.
- **Wiki — Assimp page** (`.../wiki/Assimp.md`): Assimp axis conventions differ between DCC tools; Spring
  exposes per-piece workaround keys:
  - root: `"xaxis"`, `"yaxis"`, `"zaxis"` (float3) — set global model orientation;
  - all pieces: `"rotAxisSigns"` (float3) — "determines direction of script-applied rotations around each axis",
    and `"rotAxisMap"` (`0=XYZ` or `3=XZY`, "determines coordinate conversion").
  These are the documented knobs for the exact pivot/axis/sign mismatch you'd hit when an OBJ is authored in
  Blender (Z-up, right-handed) vs. Spring (Y-up, left-handed). URL:
  https://github.com/beyond-all-reason/springrts_engine_wiki_mirror/wiki/Assimp
- **Wiki — Animation-LuaCallouts**: confirms axis = 1/2/3, radians, Move X mirrored vs COB. URL:
  https://raw.githubusercontent.com/wiki/beyond-all-reason/springrts_engine_wiki_mirror/Animation-LuaCallouts.md
- **Mantis issue 3552 "Y and Z axes are swapped for assimp"** documents the classic axis-swap gotcha:
  https://springrts.com/mantis/view.php?id=3552 (title captured via search; full body could not be fetched
  this session — springrts.com was unreachable from here).
- **BAR side `unit_script.lua`**: the LUS framework gadget is
  `cont/base/springcontent/LuaGadgets/Gadgets/unit_script.lua` (RecoilEngine) and
  `luarules/gadgets/unit_script.lua` (Beyond-All-Reason game repo). It defines no `x_axis/y_axis/z_axis`
  constants — it passes the raw integer axis straight to `Spring.UnitScript.*` (so 1/2/3 applies).

Practical implication for the mod: an OBJ piece rotates about its **object origin** as exported (typically a
Blender "empty"/object origin). To get a piece rotating about its hinge, author each piece as its own object
with its origin at the hinge. The old S3O rule — pivot = that piece's `offset` — is the same concept.

---

## Concrete snippet index (file : lines)

- `rts/Rendering/Models/3DModelPiece.cpp` : 197–220 (SetPieceTransform / ComposeTransform — the axis order)
- `rts/Rendering/Models/3DModelPiece.hpp` : 108–116 (bposeTransform, offset, goffset, scale)
- `rts/Rendering/Models/LocalModelPiece.cpp` : 62 (pos=offset), 180–198 & 210–243 (matrix recursion), 246–257 (CalcPieceSpaceTransform)
- `rts/Rendering/Models/LocalModelPiece.hpp` : 100–133 (pos/rot/scale fields + comments)
- `rts/Rendering/Models/AssParser.cpp` : 51–62 (postprocess: no PreTransformVertices), 182–259 (offset/rot/bake), 992–1049 (LoadPiece), 1052–1096 (BuildPieceHierarchy)
- `rts/Rendering/Models/S3OParser.cpp` : 104–185 (offset, raw verts, goffset, bounds)
- `rts/Rendering/Models/IModelParser.cpp` : 48–100 (obj → Assimp)
- `rts/Sim/Units/Scripts/LuaUnitScript.cpp` : 107–112 (axis/radian notes), 1135–1147 (ParseAxis), 1534–1646 (Turn/Move/Spin/Scale), 1900–1927 (GetPieceTranslation/Rotation)
- `rts/Sim/Units/Scripts/UnitScript.cpp` : 301–331 (TickMoveAnim/TickTurnAnim/TickSpinAnim), 379–453 (AddAnim offset+dest), 504–565 (Turn/Move/MoveNow/TurnNow)
- `rts/System/Quaternion.h` : 45–56 (FromEulerYPR/PYR + Neg), `rts/System/Quaternion.cpp` : 23–68 (build order)
- `rts/System/Matrix44f.h` : 43–50, 127–129 (ANGLE_P/Y/R), `rts/System/Matrix44f.cpp` : 263–279 (RotateEulerXYZ/YXZ), 700–720 (left-handed note)
- `rts/System/Transform.hpp` : 9–86 (T·R·S, `operator*` = Scale→Rotate→Translate)