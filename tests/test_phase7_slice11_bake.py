"""Phase 7 slice 11: 0 A.D. skeletal-animation BAKE tests.

Covers ``tools/assets/convert_0ad_anim.py`` -- the step that turns the shipped
``*.dae.cached.psa`` clips into world-pose Lua data keyed by the same normalised
piece names slice 10 gave the OBJ ``o`` groups:

1. the PSA header (``PSSA``/version/payloadSize/name/frameTime/numKeys/numFrames)
   parses and the key block is exactly ``numKeys * numFrames * 28`` bytes;
2. the bone count aligns with the skeleton (46 biped, 49 horse) for every clip;
3. every catalogued clip exists in ``public.zip`` and has frames at 30 fps;
4. the world pose applies the OBJ export's 180-deg-Y yaw and uniform scale, and
   its translation matches what ``convert_0ad.render_obj`` writes for the same
   vertex;
5. the rotation is the LEFT Hamilton product ``Q_y180 * q`` -- verified against an
   independently built rotation matrix, not by re-calling the implementation;
6. bone -> piece normalisation is byte-identical to ``convert_0ad``'s chain, and
   ``split_skinned_mesh`` really names its OBJ group that way;
7. the emitted ``scripts/animdata/*.lua`` files carry only pieces the unit's model
   has (per ``tools/assets/0ad-manifest.json``), in bone order, and round-trip
   losslessly through a real Lua runtime.
"""

from __future__ import annotations

import math
import re
import struct
import zipfile

import pytest

from tools.assets import convert_0ad, parse_psa, read_psa_content
from tools.assets.convert_0ad_anim import (
    CLIPS_BIPED,
    CLIPS_HORSE,
    DEFAULT_MANIFEST,
    DEFAULT_OUT_DIR,
    EXPECTED_BONES,
    SKELETON_XML,
    UNITS,
    bake_clip,
    bake_unit,
    bone_piece_names,
    load_manifest,
    unit_piece_names,
)

ARCHIVE = parse_psa.DEFAULT_ZIP
BIPED_XML = SKELETON_XML["biped"]
HORSE_XML = SKELETON_XML["horse"]
# The locked OBJ export transform this bake must reproduce.
SCALE = convert_0ad.SCALE
# bone index 30 of biped.xml is thigh_l, addressed as the OBJ group "thigh_l".
THIGH_L_INDEX = 30

pytestmark = pytest.mark.skipif(
    not ARCHIVE.is_file(),
    reason=f"0 A.D. archive not installed at {ARCHIVE}",
)

ALL_CLIPS = {**{f"biped:{k}": v for k, v in CLIPS_BIPED.items()},
             **{f"horse:{k}": v for k, v in CLIPS_HORSE.items()}}


@pytest.fixture(scope="module")
def archive():
    with zipfile.ZipFile(ARCHIVE) as zf:
        yield zf


def _anim(archive, entry: str):
    return parse_psa.parse_psa(archive.read(entry), entry)


def _norm(q):
    """Unit quaternion: PSA keys are f32, so their stored norm drifts slightly."""
    length = math.sqrt(sum(component * component for component in q))
    return tuple(component / length for component in q)


def _quat_matrix(q):
    """3x3 rotation matrix from a Hamilton quaternion (x, y, z, w)."""
    x, y, z, w = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def _mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))


# 180 deg about Y: the exporter's yaw, i.e. (x, y, z) -> (-x, y, -z).
R_Y180 = ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))

CLIP_LINE = re.compile(r'^\["([A-Za-z0-9_]+)"\]=\{fps=([0-9.]+),frames=\{$')
PIECE_PAIR = re.compile(r'\["([A-Za-z0-9_]+)"\]=\{([^{}]*)\}')


def read_lua_animdata(path):
    """Parse a generated animdata module without a Lua runtime.

    Returns ``{clip: {"fps": float, "frames": [ {piece: (7 floats)} ]}}``.
    """
    clips = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("--") or line in ("return {", "}"):
            continue
        match = CLIP_LINE.match(line)
        if match:
            current = {"fps": float(match.group(2)), "frames": []}
            clips[match.group(1)] = current
            continue
        if line == "}},":
            current = None
            continue
        if current is not None and line.startswith('{["'):
            frame = {}
            for name, payload in PIECE_PAIR.findall(line):
                frame[name] = tuple(float(value) for value in payload.split(","))
            assert frame, f"unparsed frame line in {path.name}: {line[:80]}"
            current["frames"].append(frame)
    return clips


# --------------------------------------------------------------------------- #
# 1. header
# --------------------------------------------------------------------------- #
def test_psa_header_parses_and_matches_locked_layout(archive):
    entry = CLIPS_BIPED["walk"]
    raw = archive.read(entry)
    assert raw[:4] == b"PSSA"

    version, payload = struct.unpack_from("<II", raw, 4)
    assert version == 1
    assert payload == len(raw) - 12, "payloadLen must be file size - FileHeader"

    anim = parse_psa.parse_psa(raw, entry)
    assert anim.name_field == ""
    assert anim.num_keys > 0 and anim.num_frames > 0
    assert anim.frame_time == pytest.approx(1000.0 / 30.0, abs=1e-3)
    assert anim.fps == pytest.approx(30.0, abs=1e-3)
    expected = parse_psa.KEY_SIZE * anim.num_keys * anim.num_frames
    assert len(anim._key_block) == expected, "28-byte dense frame-major key block"
    # FileHeader(12) + PackString(len-prefix 4 + name) + frameTime/numKeys/numFrames(12)
    assert expected == len(raw) - 12 - 4 - len(anim.name_field) - 12

    # frame-major addressing: key(frame, bone) == keys[frame * numKeys + bone]
    first = anim.key(0, 0)
    assert anim.key(0, 0) == first
    assert anim.key(1, 0) != first or anim.num_keys == 1
    assert anim.key(anim.num_frames - 1, anim.num_keys - 1) is not None


# --------------------------------------------------------------------------- #
# 2. bone-count alignment
# --------------------------------------------------------------------------- #
def test_skeleton_bone_counts_align_with_psa_keys(archive):
    biped = convert_0ad.parse_skeleton(archive, BIPED_XML)
    horse = convert_0ad.parse_skeleton(archive, HORSE_XML)
    assert len(biped) == 46
    assert len(horse) == 49

    for key, entry in ALL_CLIPS.items():
        anim = _anim(archive, entry)
        skeleton = "biped" if key.startswith("biped:") else "horse"
        assert anim.num_keys == EXPECTED_BONES[skeleton], (
            f"{key}: {anim.num_keys} PSA keys for a {skeleton} skeleton"
        )
        assert anim.num_keys == len(biped if skeleton == "biped" else horse)


# --------------------------------------------------------------------------- #
# 3. clip catalogue is real and non-empty
# --------------------------------------------------------------------------- #
def test_every_catalogue_clip_exists_and_has_frames(archive):
    names = set(archive.namelist())
    for key, entry in ALL_CLIPS.items():
        assert entry in names, f"{key}: {entry} is not in public.zip"
        anim = _anim(archive, entry)
        assert anim.num_frames > 0, f"{key} has no frames"
        assert anim.fps == pytest.approx(30.0, abs=1e-3), f"{key} is not 30 fps"
        assert len(anim._key_block) == (parse_psa.KEY_SIZE * anim.num_keys
                                        * anim.num_frames)


# --------------------------------------------------------------------------- #
# 4. Y-180 correction sign + scale, cross-checked against the OBJ exporter
# --------------------------------------------------------------------------- #
def test_world_pose_applies_y180_yaw_and_scale(archive):
    anim = _anim(archive, CLIPS_BIPED["walk"])
    key = anim.key(0, 0)
    assert key.tx != 0.0 and key.tz != 0.0, "need a bone offset to see the yaw"

    wx, wy, wz, qx, qy, qz, qw = read_psa_content.world_pose(key, SCALE)
    assert wx == -key.tx * SCALE, "x must be flipped and scaled"
    assert wz == -key.tz * SCALE, "z must be flipped and scaled"
    assert wy == key.ty * SCALE, "y is untouched by a yaw about Y"
    assert (wx, wy, wz) != (key.tx * SCALE, key.ty * SCALE, key.tz * SCALE)
    assert math.hypot(qx, qy, qz, qw) == pytest.approx(1.0, abs=1e-9)

    # Same rigid transform the slice-10 OBJ writer emits for that same vertex.
    mesh = {"name": "hip", "positions": [key.translation],
            "normals": [(0.0, 1.0, 0.0)], "uvs": [(0.0, 0.0)], "faces": []}
    obj = convert_0ad.render_obj(mesh, "t", scale=SCALE)
    vertex = next(line for line in obj.splitlines() if line.startswith("v "))
    ox, oy, oz = (float(part) for part in vertex.split()[1:4])
    assert (ox, oy, oz) == pytest.approx((wx, wy, wz), rel=1e-7)


# --------------------------------------------------------------------------- #
# 5. quaternion is LEFT-multiplied by Q_y180
# --------------------------------------------------------------------------- #
def test_world_pose_left_multiplies_y180_quaternion(archive):
    assert read_psa_content._Q_Y180 == (0.0, 1.0, 0.0, 0.0)

    # identity rotation -> the pure 180-deg-Y rotation
    assert read_psa_content.world_pose(
        parse_psa.Key(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0), SCALE
    )[3:] == pytest.approx((0.0, 1.0, 0.0, 0.0), abs=1e-12)

    # 90 deg about Y left-multiplied by 180 deg about Y == (0, cos45, 0, -sin45)
    s = c = math.sqrt(0.5)
    assert read_psa_content.world_pose(
        parse_psa.Key(0.0, 0.0, 0.0, 0.0, s, 0.0, c), SCALE
    )[3:] == pytest.approx((0.0, c, 0.0, -s), abs=1e-12)

    # order matters for a rotation that is not about Y alone
    q = (0.1, 0.2, 0.3, 0.9)
    assert read_psa_content._q_mul(read_psa_content._Q_Y180, q) != \
        read_psa_content._q_mul(q, read_psa_content._Q_Y180)

    # semantically: R(q') == R_y180 * R(q), i.e. a global world rotation
    anim = _anim(archive, CLIPS_HORSE["gallop"])
    for bone in (0, 7, 20, 48):
        key = anim.key(0, bone)
        q_prime = read_psa_content.world_pose(key, SCALE)[3:]
        assert math.hypot(*q_prime) == pytest.approx(1.0, abs=1e-9)
        expected = _mat_mul(R_Y180, _quat_matrix(_norm(key.rotation)))
        actual = _quat_matrix(q_prime)
        for row in range(3):
            assert actual[row] == pytest.approx(expected[row], abs=1e-9)


# --------------------------------------------------------------------------- #
# 6. piece-name normalisation matches convert_0ad exactly
# --------------------------------------------------------------------------- #
def test_piece_name_normalisation_matches_convert_0ad(archive):
    for xml_path in (BIPED_XML, HORSE_XML):
        raw_names = convert_0ad.parse_skeleton(archive, xml_path)
        expected = [convert_0ad._sanitize(name) for name in raw_names]
        assert bone_piece_names(archive, xml_path) == expected
        # ... and the same rule read_psa_content uses for its dump.
        assert expected == [convert_0ad._sanitize(name) for name
                            in read_psa_content.parse_skeleton_names(archive, xml_path)]

    biped_pieces = bone_piece_names(archive, BIPED_XML)
    assert biped_pieces[0] == "hip"
    assert biped_pieces[THIGH_L_INDEX] == "thigh_l"
    assert {"thigh_l", "leg_l", "foot_l", "chest", "neck"} <= set(biped_pieces)

    # A sliced biped mesh must name its thigh_l group exactly our bone[30] name.
    blends = [bytes([THIGH_L_INDEX, 255, 255, 255])
              + struct.pack("<4f", 1.0, 0.0, 0.0, 0.0)] * 3
    mesh = {
        "positions": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        "normals": [(0.0, 1.0, 0.0)] * 3,
        "uvs": [(0.0, 0.0)] * 3,
        "faces": [(0, 1, 2)],
        "bone_count": len(biped_pieces),
        "blends": blends,
    }
    pieces = convert_0ad.split_skinned_mesh(mesh, biped_pieces)
    assert [piece["name"] for piece in pieces] == [biped_pieces[THIGH_L_INDEX]]


# --------------------------------------------------------------------------- #
# 7. baked frames track PSA bone order and the world_pose transform
# --------------------------------------------------------------------------- #
def test_baked_frames_track_psa_bone_order(archive):
    entry = CLIPS_BIPED["run"]
    anim = _anim(archive, entry)
    names = bone_piece_names(archive, BIPED_XML)
    baked = bake_clip(archive, entry, names, keep=None, scale=SCALE)

    assert baked["num_keys"] == anim.num_keys
    assert len(baked["frames"]) == anim.num_frames
    assert all(len(row) == anim.num_keys * 7 for row in baked["frames"])

    for frame in (0, anim.num_frames // 2, anim.num_frames - 1):
        for bone in (0, THIGH_L_INDEX, anim.num_keys - 1):
            want = read_psa_content.world_pose(anim.key(frame, bone), SCALE)
            got = tuple(baked["frames"][frame][bone * 7:bone * 7 + 7])
            assert got == pytest.approx(want, abs=0.0), (
                f"frame {frame} bone {bone} is not the locked world pose"
            )


# --------------------------------------------------------------------------- #
# 8. emitted animdata only carries pieces the unit's model has
# --------------------------------------------------------------------------- #
def test_emitted_animdata_pieces_exist_in_manifest(archive):
    manifest = load_manifest(DEFAULT_MANIFEST)
    assert set(UNITS) <= set(manifest["units"])

    for unit, (skeleton, clips) in UNITS.items():
        path = DEFAULT_OUT_DIR / f"{unit}.lua"
        assert path.is_file(), f"{path} was not generated"
        emitted = read_lua_animdata(path)

        assert list(emitted) == list(clips), "clip catalogue drifted"
        model_pieces = set(unit_piece_names(manifest, unit))
        bones = bone_piece_names(archive, SKELETON_XML[skeleton])
        keep = [name for name in bones if name in model_pieces]

        for clip, data in emitted.items():
            assert data["fps"] == 30.0, f"{unit}/{clip}: expected 30 fps"
            assert data["frames"], f"{unit}/{clip} has no frames"
            names_in_frame = list(data["frames"][0])
            assert names_in_frame == keep, f"{unit}/{clip} piece set drifted"
            for frame in data["frames"]:
                assert set(frame) == model_pieces & set(names_in_frame)
                for piece, values in frame.items():
                    assert piece in model_pieces, f"{piece} is not a {unit} piece"
                    assert len(values) == 7
                    for value in values:
                        assert math.isfinite(value)


# --------------------------------------------------------------------------- #
# 9. emitted files match the PSA frame counts and round-trip through Lua
# --------------------------------------------------------------------------- #
def test_emitted_animdata_frame_counts_match_psa(archive):
    for unit, (_skeleton, clips) in UNITS.items():
        emitted = read_lua_animdata(DEFAULT_OUT_DIR / f"{unit}.lua")
        for clip, entry in clips.items():
            anim = _anim(archive, entry)
            assert len(emitted[clip]["frames"]) == anim.num_frames, (
                f"{unit}/{clip}: emitted frames != PSA numFrames"
            )


def test_emitted_animdata_loads_in_lua_lossless(archive):
    lua_runtime = pytest.importorskip("lupa").LuaRuntime(unpack_returned_tuples=True)
    manifest = load_manifest(DEFAULT_MANIFEST)

    for unit in UNITS:
        path = DEFAULT_OUT_DIR / f"{unit}.lua"
        table = lua_runtime.execute(path.read_text(encoding="utf-8"))
        baked = bake_unit(archive, unit, manifest)

        for clip, data in baked["clips"].items():
            frames = table[clip]["frames"]
            assert len(frames) == len(data["frames"])
            assert int(table[clip]["fps"]) == 30
            for frame_index in (0, len(data["frames"]) - 1):
                lua_frame = frames[frame_index + 1]  # Lua tables are 1-based
                for position, piece in enumerate(data["piece_names"]):
                    expected = data["frames"][frame_index][position * 7:
                                                           position * 7 + 7]
                    got = tuple(lua_frame[piece][i + 1] for i in range(7))
                    assert got == tuple(expected), (
                        f"{unit}/{clip} frame {frame_index} {piece}: "
                        "Lua round-trip is not lossless"
                    )