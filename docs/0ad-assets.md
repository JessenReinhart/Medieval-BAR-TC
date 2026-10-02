# 0 A.D. Asset Integration Guide (Phase 1)

This document describes the binary layout, extraction pipeline, licensing, and limitations of 0 A.D. (Wildfire Games) meshes and textures converted for Medieval-BAR-TC on the Recoil RTS engine.

## Upstream Sources & Binary Specification

- Upstream Source Repository: [0 A.D. Git Mirror](https://github.com/0ad/0ad)
- Verified Reference Implementation:
  - [`source/collada/PMDConvert.cpp`](https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/collada/PMDConvert.cpp) (PMD export layout)
  - [`source/graphics/ModelDef.cpp`](https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/graphics/ModelDef.cpp) (PMD loading and skinning routines)
  - [`source/ps/FileIo.cpp`](https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/ps/FileIo.cpp) (CFilePacker / CFileUnpacker wire structure)

### PMD v4 File Layout

Binary PMD files start with a 12-byte `FileHeader`:
1. `magic[4]`: ASCII `PSMD`
2. `version_le`: `uint32` = 4
3. `payloadSize_le`: `uint32` = total byte length minus 12

Followed by sequential little-endian packed streams:
1. `vertexCount`: `uint32`
2. `numUVSets`: `uint32`
3. Per-vertex records (`vertexCount` entries, 52 bytes each when `numUVSets == 1`):
   - `coords`: 3x `float32` (X, Y, Z in world-space bind pose)
   - `norm`: 3x `float32` (X, Y, Z normal)
   - `uv`: 2x `float32` per UV set (U, V)
   - `blend`: `SVertexBlend` (4x `uint8` bone indices, 4x `float32` weights)
4. `faceCount`: `uint32`
5. Per-face records (`faceCount` entries):
   - `indices`: 3x `uint16` vertex indices (0-indexed)
6. `boneCount`: `uint32`
7. Per-bone records (`boneCount` entries, 28 bytes each):
   - `translation`: 3x `float32`
   - `rotation`: 4x `float32` (quaternion)
8. `numPropPoints`: `uint32`
9. Per-prop records:
   - `nameLen`: `uint32`
   - `name`: ASCII bytes
   - `position`: 3x `float32`
   - `rotation`: 4x `float32` (quaternion)
   - `boneIndex`: `uint8` (0xFF for root/unboned)

## Converter Implementation

Script: `tools/assets/convert_0ad.py`
Output Manifest: `tools/assets/0ad-manifest.json`

### Pipeline Operations

1. Reads selected entries from authorized local archive `public.zip` (selective extraction only; no unzipping or modifying the 0 A.D. installation).
2. Verifies actor XML configurations and resolves exact mesh and texture bindings:
   - `medieval_archer` -> Actor `art/actors/units/athenians/infantry_archer_a.xml` -> Mesh `art/meshes/skeletal/new/m_tunic_short.dae.cached.pmd` + Texture `art/textures/skins/skeletal/hele/tunic_03_psiloi_01.png.cached.dds`
   - `medieval_infantry` -> Actor `art/actors/units/athenians/infantry_spearman_a.xml` -> Mesh `art/meshes/skeletal/new/m_armor_tunic_short.dae.cached.pmd` + Texture `art/textures/skins/skeletal/athen/linothorax_01_01.png.cached.dds`
   - `medieval_cavalry` -> Actor `art/actors/units/athenians/cavalry_swordsman_a_m.xml` + Variant `art/variants/quadraped/horse/brown.xml` -> Mesh `art/meshes/skeletal/horse_tessalian.dae.cached.pmd` + Texture `art/textures/skins/skeletal/horse_brown.png.cached.dds`
3. Parses binary PMD strictly: validates `PSMD` header, payload length, finite float bounds, vertex blend weights, bone indices, and face index ranges. Trailing garbage or malformed offsets raise `PMDError`.
4. Converts positions, normals, and UVs to Wavefront `.obj` static bind-pose geometry:
   - Uniform scaling factor: `8.0` (maps ~3.85m human to ~30.8 units and ~5.55m horse to ~44.4 units).
   - Coordinates: Y-up preserved.
   - UV coordinates: V flipped `1 - v` to match Wavefront OBJ conventions.
   - Root piece: `o base` and `g base` with 1-based `f v/vt/vn` triples, guaranteeing compatibility with Lua unit animation scripts querying `piece('base')`.
5. Emits model-side metadata `.lua` files in `objects3d/0ad/` defining `{ tex1 = "0ad/<unit>.dds" }` for direct texture binding by Recoil's Assimp model loader (`rts/Rendering/Models/AssParser.cpp`).
6. Extracts exact archive `art/LICENSE.txt` into `licenses/0ad-art.txt` and records source entry SHA-256 hashes in `tools/assets/0ad-manifest.json`.

## Licensing & Attribution

- Mesh and texture assets are Copyright (C) Wildfire Games.
- Licensed under the **Creative Commons Attribution-ShareAlike 3.0 Unported (CC-BY-SA 3.0)** license.
- Exact license text is preserved at `licenses/0ad-art.txt`.
- BAR assets remain prohibited (CC-BY-NC-ND 4.0); unit defs will bind to these CC-BY-SA 3.0 assets in Phase 2.

## Known Limitations (Phase 1)

1. **Static Unanimated Bind-Pose Geometry**:
   - Meshes represent the default Collada/PMD rest bind-pose.
   - Recoil skeletal bone hierarchies and skinning are unsupported for PMD models; bone transform arrays and vertex skin weights are intentionally discarded during OBJ export.
2. **Prop Attachments**:
   - Composite actor props (weapons, helmets, shields, heads, riders) defined via `<prop attachpoint="...">` require skeletal bone transform resolution. Phase 1 outputs clean single-mesh base hulls without attached sub-pieces.
   - Unit scripts and engine calls cannot use `AttachUnitPiece` on unboned static OBJ roots without multi-piece hierarchies.
3. **Materials & Normal Maps**:
   - Phase 1 binds diffuse `tex1` via `.lua` metadata. Normal maps (`normTex`) and specular maps (`specTex`) are not combined into S3O multi-channel packs.
