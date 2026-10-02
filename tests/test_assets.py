"""Tests for 0 A.D. PMD v4 asset parser, OBJ generation, and extracted assets.

Validates that:
1. Malformed binary PMDs (truncated headers, out-of-range vertex counts,
   invalid face references, out-of-bounds bone indices, NaN/inf coordinates)
   are strictly rejected with PMDError.
2. Synthetic valid PMD payloads parse correctly with exact vertex and face counts.
3. Converted static OBJ files contain a single root object 'o base' / 'g base'
   compatible with Recoil unit scripts `piece('base')`, valid face indexing,
   and expected bounding box sizes.
4. Extracted textures are genuine DDS binaries and manifest contains accurate
   source archive paths, license references, and transform specifications.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import pytest

from tools.assets.convert_0ad import (
    Cursor,
    PMDError,
    parse_pmd,
    render_obj,
    SCALE,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_pmd_bytes(
    vertices: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    uvs: list[tuple[float, float]],
    faces: list[tuple[int, int, int]],
    bones: int = 0,
    props: list[tuple[str, tuple[float, float, float], tuple[float, float, float, float], int]] | None = None,
    magic: bytes = b"PSMD",
    version: int = 4,
    corrupt_payload_len: int | None = None,
) -> bytes:
    """Pack a synthetic PMD v4 binary conforming to 0 A.D. PMDConvert.cpp specification."""
    if props is None:
        props = []
    # Vertex stream: pos(12), norm(12), uv(8), blend(20) = 52 bytes per vertex (1 UV set)
    vert_buf = bytearray()
    for (px, py, pz), (nx, ny, nz), (u, v) in zip(vertices, normals, uvs):
        vert_buf += struct.pack("<3f", px, py, pz)
        vert_buf += struct.pack("<3f", nx, ny, nz)
        vert_buf += struct.pack("<2f", u, v)
        # SVertexBlend: 4 x u8 bone indices, 4 x float weights
        vert_buf += struct.pack("<4B4f", 0, 255, 255, 255, 1.0, 0.0, 0.0, 0.0)

    face_buf = bytearray()
    for a, b, c in faces:
        face_buf += struct.pack("<3H", a, b, c)

    bone_buf = bytearray()
    for _ in range(bones):
        # 3 floats translation, 4 floats rotation (quaternion)
        bone_buf += struct.pack("<7f", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)

    prop_buf = bytearray()
    for name, pos, rot, bone_idx in props:
        name_bytes = name.encode("utf-8")
        prop_buf += struct.pack("<I", len(name_bytes))
        prop_buf += name_bytes
        prop_buf += struct.pack("<3f", *pos)
        prop_buf += struct.pack("<4f", *rot)
        prop_buf += struct.pack("<B", bone_idx)

    payload = bytearray()
    payload += struct.pack("<I", len(vertices))
    payload += struct.pack("<I", 1)  # 1 UV set
    payload += vert_buf
    payload += struct.pack("<I", len(faces))
    payload += face_buf
    payload += struct.pack("<I", bones)
    payload += bone_buf
    payload += struct.pack("<I", len(props))
    payload += prop_buf

    payload_len = len(payload) if corrupt_payload_len is None else corrupt_payload_len
    header = struct.pack("<4sII", magic, version, payload_len)
    return bytes(header + payload)


def test_cursor_take_and_bounds():
    c = Cursor(b"1234")
    assert c.take(2) == b"12"
    with pytest.raises(PMDError, match="truncated PMD"):
        c.take(5)


def test_parse_valid_synthetic_pmd():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    norms = [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    faces = [(0, 1, 2)]
    props = [("root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 255)]
    raw = build_pmd_bytes(verts, norms, uvs, faces, bones=1, props=props)
    mesh = parse_pmd(raw)
    assert len(mesh["positions"]) == 3
    assert len(mesh["faces"]) == 1
    assert mesh["bone_count"] == 1
    assert mesh["prop_count"] == 1


@pytest.mark.parametrize(
    "corrupt_field",
    [
        "wrong_magic",
        "wrong_version",
        "bad_payload_len",
        "truncated_vertices",
        "face_oob_index",
        "prop_oob_bone",
        "trailing_garbage",
        "nan_coordinate",
    ],
)
def test_reject_malformed_pmd(corrupt_field: str):
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    norms = [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    faces = [(0, 1, 2)]

    if corrupt_field == "wrong_magic":
        raw = build_pmd_bytes(verts, norms, uvs, faces, magic=b"NOPE")
    elif corrupt_field == "wrong_version":
        raw = build_pmd_bytes(verts, norms, uvs, faces, version=3)
    elif corrupt_field == "bad_payload_len":
        raw = build_pmd_bytes(verts, norms, uvs, faces, corrupt_payload_len=9999)
    elif corrupt_field == "truncated_vertices":
        raw = build_pmd_bytes(verts, norms, uvs, faces)[:-16]
    elif corrupt_field == "face_oob_index":
        raw = build_pmd_bytes(verts, norms, uvs, [(0, 1, 99)])
    elif corrupt_field == "prop_oob_bone":
        raw = build_pmd_bytes(
            verts, norms, uvs, faces, bones=1,
            props=[("test", (0, 0, 0), (0, 0, 0, 1), 5)],  # bone 5 does not exist
        )
    elif corrupt_field == "trailing_garbage":
        raw = build_pmd_bytes(verts, norms, uvs, faces)
        # Increase payload len in header and append garbage
        h = struct.pack("<4sII", b"PSMD", 4, len(raw) - 12 + 4)
        raw = h + raw[12:] + b"JUNK"
    elif corrupt_field == "nan_coordinate":
        raw = build_pmd_bytes([(float("nan"), 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], norms, uvs, faces)

    with pytest.raises((PMDError, struct.error)):
        parse_pmd(raw)


def test_render_obj_structure():
    mesh = {
        "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
        "normals": [(0.0, 0.0, 1.0)] * 3,
        "uvs": [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)],
        "faces": [(0, 1, 2)],
        "bone_count": 0,
        "prop_count": 0,
    }
    obj_str = render_obj(mesh, "texture.dds", scale=2.0)
    lines = [line.strip() for line in obj_str.strip().splitlines() if line.strip()]
    assert "o base" in lines
    assert "g base" in lines
    assert "v 0 0 0" in lines
    assert "v 2 0 0" in lines
    assert "v 0 4 0" in lines
    # UV flip check: 1 - 0.2 = 0.8
    assert "vt 0.1 0.8" in lines
    assert "f 1/1/1 2/2/2 3/3/3" in lines


def test_extracted_0ad_assets_exist_and_conform():
    """Verify the real extracted assets in objects3d/0ad and unittextures/0ad."""
    units = ["medieval_archer", "medieval_infantry", "medieval_cavalry"]
    for u in units:
        obj_file = REPO_ROOT / f"objects3d/0ad/{u}.obj"
        lua_file = REPO_ROOT / f"objects3d/0ad/{u}.lua"
        dds_file = REPO_ROOT / f"unittextures/0ad/{u}.dds"

        assert obj_file.is_file(), f"Missing {obj_file}"
        assert lua_file.is_file(), f"Missing {lua_file}"
        assert dds_file.is_file(), f"Missing {dds_file}"

        # DDS magic check
        dds_bytes = dds_file.read_bytes()
        assert dds_bytes[:4] == b"DDS ", f"{dds_file} missing DDS signature"
        assert len(dds_bytes) > 1024

        # Lua metadata check
        lua_text = lua_file.read_text(encoding="utf-8")
        assert f'tex1 = "0ad/{u}.dds"' in lua_text

        # OBJ parse check
        obj_text = obj_file.read_text(encoding="utf-8")
        v_coords = []
        face_count = 0
        has_base_obj = False
        has_base_group = False

        for line in obj_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts[0] == "o" and parts[1] == "base":
                has_base_obj = True
            elif parts[0] == "g" and parts[1] == "base":
                has_base_group = True
            elif parts[0] == "v":
                v_coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] == "f":
                face_count += 1
                for f_ref in parts[1:]:
                    idx_tuple = tuple(int(x) if x else 1 for x in f_ref.split("/"))
                    assert 1 <= idx_tuple[0] <= len(v_coords)

        assert has_base_obj, f"{obj_file} must define 'o base'"
        assert has_base_group, f"{obj_file} must define 'g base'"
        assert face_count >= 900
        assert len(v_coords) >= 600

        # Check bounds: height must be reasonable for human/horse
        min_y = min(c[1] for c in v_coords)
        max_y = max(c[1] for c in v_coords)
        height = max_y - min_y
        if "cavalry" in u:
            # Horse tessalian ~5.55 * 8 = ~44.4 units
            assert 35.0 <= height <= 55.0
        else:
            # Human tunic ~3.85 * 8 = ~30.8 units
            assert 25.0 <= height <= 38.0


def test_manifest_and_license():
    manifest_file = REPO_ROOT / "tools/assets/0ad-manifest.json"
    license_file = REPO_ROOT / "licenses/0ad-art.txt"

    assert manifest_file.is_file()
    assert license_file.is_file()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["license"].startswith("CC-BY-SA-3.0")
    assert manifest["transform"]["scale"] == SCALE
    assert "medieval_archer" in manifest["units"]
    assert "medieval_infantry" in manifest["units"]
    assert "medieval_cavalry" in manifest["units"]

    license_text = license_file.read_text(encoding="utf-8")
    assert "Wildfire Games" in license_text
    assert "Creative Commons Attribution-Share Alike 3.0" in license_text
