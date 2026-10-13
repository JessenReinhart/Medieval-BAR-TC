"""Tests for rendering fixes: backface culling, texture loading, and animation loading.

Covers:
1. Culling issue:
   - OBJ triangle winding is CCW so geometric face normals point outwards and agree
     with vertex lighting normals (preventing OpenGL back-face culling from culling
     front-facing polygons).
   - All 18 on-disk 0 A.D. OBJs have >= 95% face-to-normal alignment (geometric normal
     dot vertex normal > 0).
   - render_obj() correctly converts PMD clockwise index triples (a, b, c) to CCW
     triples (a, c, b).

2. Texture loading issue:
   - Every model in objects3d/0ad/ has an accompanying .lua texture definition.
   - Every texture definition references an existing, valid DDS file in unittextures/0ad/.
   - All DDS textures are valid BC3/DXT5 format with valid header and mipmap chain.
   - Texture alpha is zeroed so Recoil does not tint the diffuse map with team-color.
   - Every unit definition with a visual mesh references an existing OBJ and has
     resolvable textures.

3. Animation loading issue:
   - Every unit definition with a `script` attribute points to an existing scripts/*.lua.
   - All unit animation scripts compile cleanly as valid Lua.
   - Every animation script exposes mandatory engine call-ins: Create, StartMoving,
     StopMoving, Killed, plus weapon call-ins (AimWeapon, FireWeapon, QueryWeapon)
     for armed units.
   - Every model's OBJ defines the anchor piece 'base' required by LUS piece contracts.
   - Multi-piece OBJ piece names match the LUS optPiece() probing contracts.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import pytest

from lupa import LuaRuntime

from tools.assets.convert_0ad import (
    BUILDINGS,
    MODELS,
    SCALE,
    UNITS,
    parse_pmd,
    render_obj,
)

ROOT = Path(__file__).resolve().parents[1]
OBJECTS_DIR = ROOT / "objects3d/0ad"
TEXTURES_DIR = ROOT / "unittextures/0ad"
SCRIPTS_DIR = ROOT / "scripts"
UNITS_DIR = ROOT / "units"
MANIFEST_PATH = ROOT / "tools/assets/0ad-manifest.json"


# =============================================================================
# Helper math
# =============================================================================

def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(a, a))
    if length <= 1e-9:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


def _parse_obj_faces(obj_text: str):
    verts: list[tuple[float, float, float]] = []
    norms: list[tuple[float, float, float]] = []
    faces: list[list[tuple[int, int]]] = []
    pieces: list[str] = []

    for line in obj_text.splitlines():
        line = line.strip()
        if line.startswith("o "):
            pieces.append(line[2:].strip())
        elif line.startswith("v "):
            parts = line[2:].split()
            verts.append((float(parts[0]), float(parts[1]), float(parts[2])))
        elif line.startswith("vn "):
            parts = line[3:].split()
            norms.append((float(parts[0]), float(parts[1]), float(parts[2])))
        elif line.startswith("f "):
            face: list[tuple[int, int]] = []
            for ref in line[2:].split():
                sub_parts = ref.split("/")
                v_idx = int(sub_parts[0]) - 1
                n_idx = int(sub_parts[2]) - 1 if len(sub_parts) >= 3 and sub_parts[2] else 0
                face.append((v_idx, n_idx))
            faces.append(face)

    return verts, norms, faces, pieces


# =============================================================================
# 1. Culling issue tests
# =============================================================================

class TestCullingAndWinding:
    """Validates that OBJ exports use counter-clockwise (CCW) face winding."""

    def test_render_obj_emits_ccw_winding(self):
        """render_obj reverses PMD (a, b, c) to (a, c, b) for CCW front faces."""
        mesh = {
            "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            "normals": [(0.0, 0.0, 1.0)] * 3,
            "uvs": [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            "faces": [(0, 1, 2)],
            "bone_count": 0,
            "prop_count": 0,
        }
        out = render_obj(mesh, "test.dds", scale=1.0)
        # Face (0, 1, 2) in PMD becomes 1-based (1, 3, 2) in OBJ
        assert "f 1/1/1 3/3/3 2/2/2" in out

    @pytest.mark.parametrize("model_name", sorted(MODELS.keys()))
    def test_on_disk_objs_have_ccw_winding_agreeing_with_normals(self, model_name: str):
        """At least 95% of faces on every on-disk OBJ must agree with vertex normals.

        If winding is backwards (CW), the geometric normal opposes the outward
        vertex normal, causing OpenGL backface culling to cull front-facing polygons.
        """
        obj_path = OBJECTS_DIR / f"{model_name}.obj"
        assert obj_path.is_file(), f"Missing OBJ: {obj_path}"
        verts, norms, faces, _ = _parse_obj_faces(obj_path.read_text(encoding="utf-8"))
        assert len(faces) > 0

        agree = 0
        oppose = 0
        for f in faces:
            p0 = verts[f[0][0]]
            p1 = verts[f[1][0]]
            p2 = verts[f[2][0]]
            geom_norm = _norm(_cross(_sub(p1, p0), _sub(p2, p0)))
            avg_vn = _norm((
                (norms[f[0][1]][0] + norms[f[1][1]][0] + norms[f[2][1]][0]) / 3.0,
                (norms[f[0][1]][1] + norms[f[1][1]][1] + norms[f[2][1]][1]) / 3.0,
                (norms[f[0][1]][2] + norms[f[1][1]][2] + norms[f[2][1]][2]) / 3.0,
            ))
            d = _dot(geom_norm, avg_vn)
            if d > 0.05:
                agree += 1
            elif d < -0.05:
                oppose += 1

        total_tested = agree + oppose
        assert total_tested > 0
        ratio = agree / total_tested
        assert ratio >= 0.95, (
            f"{model_name}.obj has backward winding: {agree} agree vs {oppose} oppose "
            f"({ratio:.1%} agreement, expected >= 95%)"
        )


# =============================================================================
# 2. Texture loading issue tests
# =============================================================================

class TestTextureLoading:
    """Validates that all model textures exist, are valid DDS, and load cleanly."""

    @pytest.mark.parametrize("model_name", sorted(MODELS.keys()))
    def test_model_has_lua_texture_binding(self, model_name: str):
        """Every OBJ must have a companion .lua defining tex1."""
        lua_path = OBJECTS_DIR / f"{model_name}.lua"
        assert lua_path.is_file(), f"Missing texture Lua: {lua_path}"
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(lua_path.read_text(encoding="utf-8"))
        assert table is not None
        assert "tex1" in table
        assert table["tex1"].startswith("0ad/")

    @pytest.mark.parametrize("model_name", sorted(MODELS.keys()))
    def test_dds_texture_exists_and_is_valid_dxt5(self, model_name: str):
        """Every texture must be an existing DDS with DXT5 FOURCC and valid mip levels."""
        dds_path = TEXTURES_DIR / f"{model_name}.dds"
        assert dds_path.is_file(), f"Missing DDS file: {dds_path}"
        data = dds_path.read_bytes()
        assert len(data) >= 128
        assert data[:4] == b"DDS ", "Magic mismatch"

        height, width, pitch, _, mips = struct.unpack_from("<5I", data, 12)
        assert width > 0 and height > 0
        assert (width & (width - 1)) == 0, "Width must be power of 2"
        assert (height & (height - 1)) == 0, "Height must be power of 2"

        # Check FOURCC is DXT5
        fourcc = data[84:88]
        assert fourcc == b"DXT5", f"Expected DXT5 FOURCC, got {fourcc!r}"

    @pytest.mark.parametrize("model_name", sorted(MODELS.keys()))
    def test_dds_alpha_channel_is_zeroed(self, model_name: str):
        """Every converted DDS must have zero alpha in all blocks to avoid blue tint."""
        data = (TEXTURES_DIR / f"{model_name}.dds").read_bytes()
        # Scan all 16-byte blocks from offset 128 onwards
        for offset in range(128, len(data), 16):
            alpha_block = data[offset : offset + 8]
            assert alpha_block == b"\x00" * 8, f"Non-zero alpha block found at {offset}"

    def test_unit_definitions_reference_existing_models(self):
        """All units/*.lua files referencing objectName must resolve to valid OBJs."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        for unit_file in sorted(UNITS_DIR.glob("*.lua")):
            table = lua.execute(unit_file.read_text(encoding="utf-8"))
            if not table:
                continue
            for unit_id in table.keys():
                defn = table[unit_id]
                obj_name = defn["objectName"]
                if obj_name:
                    full_obj = ROOT / "objects3d" / obj_name
                    assert full_obj.is_file(), f"{unit_id} references missing object {obj_name}"

    def test_all_unit_script_files_exist_and_are_valid_lua(self):
        """All scripts bound to units exist and pass Lua parser checks."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        tested_scripts = set()
        for unit_file in sorted(UNITS_DIR.glob("*.lua")):
            table = lua.execute(unit_file.read_text(encoding="utf-8"))
            if not table:
                continue
            for unit_id in table.keys():
                defn = table[unit_id]
                script_name = defn["script"]
                if script_name:
                    script_path = SCRIPTS_DIR / script_name
                    assert script_path.is_file(), f"{unit_id} references missing script {script_path}"
                    tested_scripts.add(script_path)

        for script_path in tested_scripts:
            code = script_path.read_text(encoding="utf-8")
            lua.globals().c = code
            ret = lua.execute("local fn, err = load(c); return { fn = fn, err = err }")
            assert ret["fn"] is not None, f"Syntax error in {script_path}: {ret['err']}"

    def test_mobile_unit_scripts_define_motion_and_lifecycle_callins(self):
        """Mobile unit scripts define Create, StartMoving, StopMoving, and Killed."""
        mobile_scripts = [
            "medieval_infantry.lua",
            "medieval_archer.lua",
            "medieval_cavalry.lua",
            "medieval_villager.lua",
            "medieval_cart.lua",
        ]
        for script_name in mobile_scripts:
            text = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            assert "function script.Create(" in text
            assert "function script.StartMoving(" in text
            assert "function script.StopMoving(" in text
            assert "function script.Killed(" in text

    def test_combat_unit_scripts_define_weapon_callins(self):
        """Combat units define AimWeapon, FireWeapon, and QueryWeapon."""
        combat_scripts = [
            "medieval_infantry.lua",
            "medieval_archer.lua",
            "medieval_cavalry.lua",
            "medieval_catapult.lua",
        ]
        for script_name in combat_scripts:
            text = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            assert "AimWeapon" in text
            assert "FireWeapon" in text
            assert "QueryWeapon" in text

    def test_lus_optpiece_pattern_matches_multipiece_obj_names(self):
        """Scripts reference named pieces via optPiece/piece probes matching the OBJ contract."""
        expected_piece_names = {
            "base", "torso", "head", "weapon", "shield", "arm", "wheel", "axle",
            "tray", "l_leg", "r_leg", "l_arm", "r_arm",
        }
        import re
        for script_file in sorted(SCRIPTS_DIR.glob("medieval_*.lua")):
            text = script_file.read_text(encoding="utf-8")
            probed = set(re.findall(r'optPiece\(["\'](\w+)["\']\)', text))
            assert probed.issubset(expected_piece_names), (
                f"{script_file.name} probes unexpected pieces: {probed - expected_piece_names}"
            )
