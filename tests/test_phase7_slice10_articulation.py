"""Phase 7 slice 10: skinned-mesh bone splitting tests.

Covers the articulation pipeline added to ``tools/assets/convert_0ad.py``:

1. ``parse_pmd`` returns the raw ``SVertexBlend`` payloads as ``blends``, one per
   vertex, so a skeletal hull's bone influences survive parsing.
2. ``parse_skeleton`` reads ``art/skeletons/<name>.xml`` from ``public.zip``, finds
   ``<standard_skeleton>`` and returns bone names in document order, lowercased and
   with the side marker normalised to ``_l``/``_r`` (46 bones for ``biped.xml``,
   49 for ``horse.xml``).
3. ``split_skinned_mesh`` partitions the hull by per-vertex dominant bone so each
   body part becomes its own named piece (``thigh_l``, ``leg_l``, ``arm_l``,
   ``chest``, ``hip``, ...), with faces re-indexed 0-based per piece.
4. ``resolve_model_pieces`` routes a skeletal actor through the splitter and a
   static hull straight to a single ``base`` piece.
"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

from tools.assets.convert_0ad import (
    BUILDINGS,
    DEFAULT_ARCHIVE,
    MESH_PREFIX,
    parse_pmd,
    parse_skeleton,
    resolve_model_pieces,
    split_skinned_mesh,
)

BIPED_XML = "art/skeletons/biped.xml"
HORSE_XML = "art/skeletons/horse.xml"
ARCHER_MESH = "skeletal/new/m_tunic_short.dae"
ARCHER_ACTOR = "art/actors/units/athenians/infantry_archer_a.xml"
HORSE_MESH = "skeletal/horse_tessalian.dae"
HORSE_ACTOR = "art/actors/units/athenians/cavalry_swordsman_a_m.xml"
# A static structure: no bones at all, so it must never be split.
HOUSE_ACTOR = BUILDINGS["medieval_house"]["actor"]
HOUSE_MESH = BUILDINGS["medieval_house"]["mesh"]

# Bones the slicer must isolate on a biped hull: biped.xml document order, with the
# side marker normalised, is the order the LUS scripts address pieces in.
EXPECTED_BIPED_PIECES = ("hip", "chest", "arm_l", "forearm_l", "thigh_l", "leg_l", "foot_l")

pytestmark = pytest.mark.skipif(
    not DEFAULT_ARCHIVE.is_file(),
    reason=f"0 A.D. archive not installed at {DEFAULT_ARCHIVE}",
)


@pytest.fixture(scope="module")
def archive():
    with zipfile.ZipFile(DEFAULT_ARCHIVE) as zf:
        yield zf


def _pmd(archive, want_mesh: str) -> dict:
    return parse_pmd(archive.read(MESH_PREFIX + want_mesh + ".cached.pmd"))


def _blend(*influences) -> bytes:
    """Build one 20-byte SVertexBlend: four u8 indices then four float weights."""
    indices = [255] * 4
    weights = [0.0] * 4
    for slot, (bone, weight) in enumerate(influences):
        indices[slot] = bone
        weights[slot] = weight
    return bytes(indices) + struct.pack("<4f", *weights)


def _synthetic(bone_count: int, blends, faces) -> dict:
    verts = len(blends)
    return {
        "positions": [(float(i), 0.0, 0.0) for i in range(verts)],
        "normals": [(0.0, 1.0, 0.0)] * verts,
        "uvs": [(0.0, 0.0)] * verts,
        "faces": faces,
        "bone_count": bone_count,
        "uv_sets": 1,
        "prop_count": 0,
        "prop_points": [],
        "bones": [(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)] * bone_count,
        "blends": blends,
    }


# --------------------------------------------------------------------------- #
# 1. parse_pmd carries blend data
# --------------------------------------------------------------------------- #


def test_parse_pmd_returns_blends(archive):
    """A skeletal PMD exposes one 20-byte blend record per vertex."""
    mesh = _pmd(archive, ARCHER_MESH)
    assert mesh["bone_count"] > 1
    assert len(mesh["blends"]) == len(mesh["positions"])
    assert all(len(blend) == 20 for blend in mesh["blends"])
    for blend in mesh["blends"]:
        weights = struct.unpack_from("<4f", blend, 4)
        assert all(0.0 <= weight <= 1.0 for weight in weights)
        for slot in range(4):
            bone = blend[slot]
            assert bone == 255 or bone < mesh["bone_count"]


def test_parse_pmd_blends_track_weights(archive):
    """Every skeletal vertex carries at least one real bone influence."""
    mesh = _pmd(archive, ARCHER_MESH)
    for blend in mesh["blends"]:
        indices = [blend[slot] for slot in range(4)]
        assert any(index != 255 for index in indices)


def test_parse_pmd_static_mesh_has_no_bones(archive):
    """A static hull still returns blends (all sentinels) rather than omitting them."""
    mesh = _pmd(archive, HOUSE_MESH)
    assert mesh["bone_count"] == 0
    assert len(mesh["blends"]) == len(mesh["positions"])


# --------------------------------------------------------------------------- #
# 2. parse_skeleton
# --------------------------------------------------------------------------- #


def test_parse_skeleton_biped_has_46_bones(archive):
    names = parse_skeleton(archive, BIPED_XML)
    assert len(names) == 46
    assert names[0] == "hip"
    assert "thigh_l" in names and "thigh_r" in names


def test_parse_skeleton_horse_has_49_bones(archive):
    names = parse_skeleton(archive, HORSE_XML)
    assert len(names) == 49
    assert names[0] == "root"


def test_parse_skeleton_preserves_document_order(archive):
    names = parse_skeleton(archive, BIPED_XML)
    assert names[:5] == ["hip", "spine", "spine1", "chest", "shoulder_l"]
    assert names.index("chest") < names.index("neck") < names.index("head")


def test_parse_skeleton_normalises_side_markers(archive):
    """Names are lowercased with the side marker unified to ``_l``/``_r``."""
    for xml in (BIPED_XML, HORSE_XML):
        names = parse_skeleton(archive, xml)
        assert all(name == name.lower() for name in names)
        assert not any(name.endswith("_L") or name.endswith("_R") for name in names)
    biped = parse_skeleton(archive, BIPED_XML)
    assert "shoulder_l" in biped and "shoulder_r" in biped
    assert "weapon_l" in biped and "weapon_r" in biped


def test_parse_skeleton_rejects_missing_standard_skeleton():
    """A document without <standard_skeleton> is rejected, not silently empty."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("art/skeletons/broken.xml", "<skeletons><skeleton/></skeletons>")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as zf:
        with pytest.raises(ValueError):
            parse_skeleton(zf, "art/skeletons/broken.xml")


def test_parse_skeleton_rejects_absent_entry(archive):
    with pytest.raises(KeyError):
        parse_skeleton(archive, "art/skeletons/does_not_exist.xml")


# --------------------------------------------------------------------------- #
# 3. split_skinned_mesh
# --------------------------------------------------------------------------- #


def test_split_biped_mesh_produces_named_pieces(archive):
    """Every limb bone with weighted geometry becomes its own piece."""
    mesh = _pmd(archive, ARCHER_MESH)
    pieces = split_skinned_mesh(mesh, parse_skeleton(archive, BIPED_XML))
    names = [piece["name"] for piece in pieces]
    assert len(pieces) > 1
    for expected in EXPECTED_BIPED_PIECES:
        assert expected in names, f"missing piece {expected!r} in {names}"
    assert len(names) == len(set(names)), f"duplicate piece names: {names}"


def test_split_pieces_partition_the_hull(archive):
    """Splitting loses no triangle and never invents geometry."""
    mesh = _pmd(archive, ARCHER_MESH)
    pieces = split_skinned_mesh(mesh, parse_skeleton(archive, BIPED_XML))
    assert sum(len(piece["faces"]) for piece in pieces) == len(mesh["faces"])
    vertices = sum(len(piece["positions"]) for piece in pieces)
    # A vertex shared by two bones is copied into both pieces, never dropped.
    assert len(mesh["positions"]) <= vertices <= 3 * len(mesh["faces"])
    for piece in pieces:
        for face in piece["faces"]:
            assert len(face) == 3
            for index in face:
                assert 0 <= index < len(piece["positions"])
                assert 0 <= index < len(piece["normals"])
                assert 0 <= index < len(piece["uvs"])
        assert piece["positions"] and piece["normals"] and piece["uvs"]


def test_split_pieces_keep_their_own_geometry(archive):
    """A piece's vertices are the source vertices its faces referenced."""
    mesh = _pmd(archive, ARCHER_MESH)
    pieces = split_skinned_mesh(mesh, parse_skeleton(archive, BIPED_XML))
    for piece in pieces:
        for position in piece["positions"]:
            assert position in mesh["positions"]
    arm = next(piece for piece in pieces if piece["name"] == "arm_l")
    assert arm["faces"] and len(arm["positions"]) < len(mesh["positions"])


def test_split_horse_mesh_uses_horse_skeleton(archive):
    mesh = _pmd(archive, HORSE_MESH)
    pieces = split_skinned_mesh(mesh, parse_skeleton(archive, HORSE_XML))
    names = [piece["name"] for piece in pieces]
    for expected in ("head", "neck", "spine", "l_thigh", "l_hoof", "tail2"):
        assert expected in names, f"missing piece {expected!r} in {names}"


def test_split_falls_back_on_unskinned_mesh(archive):
    """A single-bone or blend-less hull is exported whole as ``base``."""
    mesh = _pmd(archive, HOUSE_MESH)
    pieces = split_skinned_mesh(mesh, [])
    assert len(pieces) == 1
    assert pieces[0]["name"] == "base"
    assert pieces[0]["faces"] == mesh["faces"]

    static = _synthetic(1, [_blend((0, 1.0))], [(0, 0, 0)])
    assert [piece["name"] for piece in split_skinned_mesh(static, ["hip"])] == ["base"]

    no_blends = _synthetic(2, [], [])
    no_blends["bones"] = [tuple(), tuple()]
    assert [piece["name"] for piece in split_skinned_mesh(no_blends, ["hip", "chest"])] == ["base"]


def test_split_ignores_sentinel_influences():
    """Bone 255 never wins the primary-bone vote, however heavy its weight."""
    mesh = _synthetic(
        3,
        [
            _blend((0, 0.9), (255, 1.0)),
            _blend((0, 0.6), (1, 0.4)),
            _blend((1, 0.9), (255, 1.0)),
        ],
        [(0, 1, 2)],
    )
    pieces = split_skinned_mesh(mesh, ["hip", "chest", "head"])
    assert [piece["name"] for piece in pieces] == ["hip"]  # 2 votes for 0, 1 for 1
    assert pieces[0]["faces"] == [(0, 1, 2)]


def test_split_face_goes_to_dominant_bone():
    """Each triangle lands in one piece, and the pieces re-index from zero."""
    mesh = _synthetic(
        2,
        [_blend((0, 1.0)), _blend((0, 1.0)), _blend((1, 1.0)), _blend((1, 1.0))],
        [(0, 1, 2), (2, 3, 0), (2, 3, 1)],
    )
    pieces = {piece["name"]: piece for piece in split_skinned_mesh(mesh, ["hip", "chest"])}
    assert set(pieces) == {"hip", "chest"}
    assert len(pieces["hip"]["faces"]) == 1  # (0,1,2): two 0-votes vs one 1-vote
    assert len(pieces["chest"]["faces"]) == 2
    for name, piece in pieces.items():
        used = {index for face in piece["faces"] for index in face}
        assert used == set(range(len(piece["positions"]))), name


def test_split_keeps_unweighted_faces_as_base():
    """Triangles with no bone influence survive in the ``base`` anchor piece."""
    mesh = _synthetic(
        2,
        [_blend((0, 1.0)), _blend((255, 1.0)), _blend((255, 1.0)), _blend((255, 1.0))],
        [(0, 1, 2), (1, 2, 3)],
    )
    pieces = {piece["name"]: piece for piece in split_skinned_mesh(mesh, ["hip", "chest"])}
    assert set(pieces) == {"base", "hip"}
    assert len(pieces["base"]["faces"]) == 1
    assert len(pieces["hip"]["faces"]) == 1


def test_split_sanitises_unknown_bone_indices():
    """An out-of-range bone index degrades to a sanitised ``bone_<n>`` name."""
    mesh = _synthetic(4, [_blend((3, 1.0))] * 3, [(0, 1, 2)])  # bone 3 is beyond the skeleton
    pieces = split_skinned_mesh(mesh, ["hip", "chest"])
    assert [piece["name"] for piece in pieces] == ["bone_3"]


# --------------------------------------------------------------------------- #
# 4. resolve_model_pieces integration
# --------------------------------------------------------------------------- #


def test_resolve_model_pieces_splits_skeletal_actor(archive):
    pieces, _warnings, _resolved, _skipped = resolve_model_pieces(archive, ARCHER_ACTOR, ARCHER_MESH)
    names = [piece["name"] for piece in pieces]
    assert len(names) > 1
    for expected in ("hip", "chest", "arm_l", "thigh_l", "leg_l"):
        assert expected in names, f"missing piece {expected!r} in {names}"


def test_resolve_model_pieces_splits_cavalry_actor(archive):
    pieces, _warnings, _resolved, _skipped = resolve_model_pieces(archive, HORSE_ACTOR, HORSE_MESH)
    names = [piece["name"] for piece in pieces]
    for expected in ("head", "spine", "l_thigh", "l_hoof"):
        assert expected in names, f"missing piece {expected!r} in {names}"


def test_resolve_model_pieces_keeps_static_hull_whole(archive):
    pieces, _warnings, _resolved, _skipped = resolve_model_pieces(
        archive, HOUSE_ACTOR, HOUSE_MESH
    )
    assert len(pieces) >= 1
    assert pieces[0]["name"] == "base"