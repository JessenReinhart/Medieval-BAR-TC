"""Extract selected 0 A.D. alpha 28 PMD meshes and cached DDS textures.

Only Python's standard library is required. PMD layout follows 0ad/0ad
source/collada/PMDConvert.cpp::WritePMD (version 4) and
source/ps/FileIo.cpp::FileHeader. No skeleton animation is exported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = Path.home() / "AppData/Local/0 A.D. Empires Ascendant/binaries/data/mods/public/public.zip"
MESH_PREFIX = "art/meshes/"
SKIN_PREFIX = "art/textures/skins/"
# 0 A.D. actors live in art/actors/, but a <variant file="..."> indirection and a
# prop's own <prop actor="..."> both resolve relative to a prefix that varies per
# document, so every reference is tried against both roots.
ACTOR_PREFIX = "art/actors/"
VARIANT_PREFIX = "art/variants/"
# Per-unit source selection. `actor` is the exact archive path of the actor XML that
# declares the mesh/baseTex pair, so every unit's provenance is verifiable in the
# manifest. Each entry is checked against the actor text before conversion.
UNITS = {
    "medieval_archer": {
        "actor": "art/actors/units/athenians/infantry_archer_a.xml",
        "mesh": "skeletal/new/m_tunic_short.dae",
        "texture": "skeletal/hele/tunic_03_psiloi_01.png",
    },
    "medieval_infantry": {
        "actor": "art/actors/units/athenians/infantry_spearman_a.xml",
        "mesh": "skeletal/new/m_armor_tunic_short.dae",
        "texture": "skeletal/athen/linothorax_01_01.png",
    },
    "medieval_cavalry": {
        "actor": "art/actors/units/athenians/cavalry_swordsman_a_m.xml",
        "variant": "art/variants/quadraped/horse/brown.xml",
        "mesh": "skeletal/horse_tessalian.dae",
        "texture": "skeletal/horse_brown.png",
    },
    # Phase 4 Slice 1 siege engine: the Hellenic lithobolos (stone-throwing catapult).
    # Static structural mesh; the actor's mechanical idle/attack PSAs are not exported.
    "medieval_catapult": {
        "actor": "art/actors/units/hellenes/siege_rock.xml",
        "mesh": "structural/hele_lithobolos.dae",
        "texture": "structural/hele_siege.dds",
    },
    # Phase 7 Slice 3: dedicated infantry variants so the Villager, Spearman and
    # King stop recycling the generic hoplite body. Celtic (Briton) actors are the
    # closest authentic 0 A.D. analogue of a medieval levy, and each entry keeps a
    # distinct mesh/texture pair so no two units render identically.
    "medieval_villager": {
        "actor": "art/actors/units/britons/citizen_male.xml",
        "mesh": "skeletal/new/m_tunic_short.dae",
        "texture": "skeletal/germ/tunic_pants_01_01.png",
    },
    "medieval_spearman": {
        "actor": "art/actors/units/britons/infantry_spearman_a.xml",
        "mesh": "skeletal/new/m_pants_tunic_long.dae",
        "texture": "skeletal/celt/tunic_01_01.png",
    },
    "medieval_king": {
        "actor": "art/actors/units/britons/hero_infantry_swordsman_cunobelin.xml",
        "mesh": "skeletal/new/m_armor_pants_tunic_long.dae",
        "texture": "skeletal/celt/druid_02.png",
    },
}
# Phase 7 Slice 3: dedicated building meshes. The Briton (Celtic) structure set is
# the authentic 0 A.D. match for timber-and-thatch medieval settlement buildings:
# each actor declares one structural mesh plus one structural baseTex, so a single
# static OBJ per building replaces the placeholder recycling of the infantry body.
BUILDINGS = {
    "medieval_town_center": {
        "actor": "art/actors/structures/britons/civic_centre.xml",
        "mesh": "structural/brit_civic_centre_struct1.dae",
        "texture": "structural/brit_struct_1.png",
    },
    "medieval_house": {
        "actor": "art/actors/structures/britons/house.xml",
        "mesh": "structural/brit_house_01.dae",
        "texture": "structural/brit_struct_1.png",
    },
    "medieval_barracks": {
        "actor": "art/actors/structures/britons/barracks.xml",
        "mesh": "structural/brit_barracks_struct.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_stables": {
        "actor": "art/actors/structures/britons/stable.xml",
        "mesh": "structural/brit_stable.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_granary": {
        "actor": "art/actors/structures/britons/farmstead.xml",
        "mesh": "structural/celt_farmstead.dae",
        "texture": "structural/brit_struct_1.png",
    },
    "medieval_lumber_camp": {
        "actor": "art/actors/structures/britons/storehouse.xml",
        "mesh": "structural/brit_storehouse.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_market": {
        "actor": "art/actors/structures/britons/market.xml",
        "mesh": "structural/brit_market_struct_1.dae",
        "texture": "structural/brit_struct_1.png",
    },
    "medieval_blacksmith": {
        "actor": "art/actors/structures/britons/blacksmith.xml",
        "mesh": "structural/brit_blacksmith.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_fletcher": {
        "actor": "art/actors/structures/britons/range.xml",
        "mesh": "structural/brit_range.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_tower": {
        "actor": "art/actors/structures/britons/scout_tower.xml",
        "mesh": "structural/brit_scout_tower_struct.dae",
        "texture": "structural/brit_struct.png",
    },
    "medieval_wall": {
        "actor": "art/actors/structures/britons/wall_medium.xml",
        "mesh": "structural/brit_wall_medium.dae",
        "texture": "structural/brit_struct.png",
    },
}
MODELS = {**UNITS, **BUILDINGS}
# Deterministic conversion order: units first, then buildings, both in declaration
# order, so the manifest and the CLI report are stable across runs.
_MODEL_ORDER = [(name, "unit") for name in UNITS] + [(name, "building") for name in BUILDINGS]
# 0 A.D. PMD is Y-up, matches Recoil's unit-space up axis. 0 A.D. model
# heights are ~3.85 (human) and ~5.55 (horse); 8 gives ~31 and ~44 units.
SCALE = 8.0
MAX_VERTICES = 65535  # PMD faces contain 16-bit indices
MAX_FACES = 1_000_000
MAX_UV_SETS = 16
MAX_BONES = 255
MAX_PROP_POINTS = 65535


class PMDError(ValueError):
    """Truncated, corrupt or unsupported PMD v4 file."""


class Cursor:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, size: int) -> bytes:
        if size < 0 or size > len(self.data) - self.pos:
            raise PMDError(f"truncated PMD at offset {self.pos}; need {size} bytes")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def count(self, maximum: int, name: str) -> int:
        value = self.unpack("<I")[0]
        if value > maximum:
            raise PMDError(f"{name} count {value} exceeds limit {maximum}")
        return value


def _finite(values, name: str) -> None:
    if not all(math.isfinite(x) for x in values):
        raise PMDError(f"non-finite {name}")


# --------------------------------------------------------------------------- #
# Actor <props> resolution.
#
# A 0 A.D. actor is composite: one root <mesh> plus any number of <props>, each a
# reference to another actor attached at a named prop point of the parent mesh.
# Heads, helmets, weapons, shields and building roofs/palisades all arrive this
# way, which is why a root-mesh-only conversion loses them.
# --------------------------------------------------------------------------- #


def _strip_ns(tag: str) -> str:
    return tag.rpartition("}")[2]


def _children(node, tag: str) -> list:
    return [c for c in node if _strip_ns(c.tag) == tag]


def _stable_rng(seed_text: str) -> random.Random:
    """Seeded RNG whose stream does not depend on PYTHONHASHSEED."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# Actor documents that only describe behaviour (animation sets, death poses) or
# carry no mesh at all; their content is never the bind-pose look of the model.
_SKIP_DOCUMENT = re.compile(r"(^|/)(biped|quadraped|particle|projectile)/")


def _pick_variant(group):
    """Choose one <variant> from a <group>, deterministically.

    A group is a 0 A.D. randomisation slot: exactly one variant is live at a time.
    The first variant wins, except that one explicitly named Base/default is
    preferred, so a given model always converts to the same head/weapon/roof.
    """
    variants = _children(group, "variant")
    if not variants:
        return None
    for variant in variants:
        if (variant.get("name") or "").strip().lower() in ("base", "default"):
            return variant
    return variants[0]


def _variant_file_ref(variant) -> str:
    reference = (variant.get("file") or "").strip()
    if not reference or _SKIP_DOCUMENT.search(reference):
        return ""
    return reference


def _selected_variants(document) -> list:
    """Flatten one actor/variant document into its live <variant> elements.

    Handles the three document shapes 0 A.D. uses: <actor> (groups of variants),
    a bare <variant> (a variant file), and <qualitylevels> (per-quality actors,
    of which the highest-quality actor with no ``quality`` attribute is live).
    """
    tag = _strip_ns(document.tag)
    if tag == "variant":
        return [document]
    if tag == "qualitylevels":
        actors = _children(document, "actor")
        if not actors:
            return []
        plain = [a for a in actors if not (a.get("quality") or "").strip()]
        return _selected_variants(plain[-1] if plain else actors[-1])
    if tag != "actor":
        return []
    selected = []
    for group in _children(document, "group"):
        variant = _pick_variant(group)
        if variant is not None:
            selected.append(variant)
    return selected


def _variant_meshes(variant) -> list:
    meshes = []
    for node in _children(variant, "mesh"):
        if node.text and node.text.strip():
            meshes.append(node.text.strip())
    return meshes


def _collect_parts(variant) -> list:
    """Extract the <prop> references declared directly on one <variant>."""
    parts = []
    for holder in _children(variant, "props"):
        for prop in _children(holder, "prop"):
            reference = (prop.get("actor") or "").strip()
            if not reference:
                continue  # particle / colour-only prop: no geometry to merge
            parts.append(((prop.get("attachpoint") or "").strip(), reference))
    return parts


# --------------------------------------------------------------------------- #
# Placement maths: a prop point is expressed in the bind pose of the bone it
# rides, so the model-space matrix is bone * prop-point.
# --------------------------------------------------------------------------- #


def _mat_identity() -> tuple:
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def _mat_mul(a: tuple, b: tuple) -> tuple:
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4))
                 for r in range(4))


def _mat_from_quat(qx, qy, qz, qw) -> tuple:
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if not math.isfinite(norm) or norm < 1e-8:
        raise PMDError("degenerate quaternion in prop transform")
    qx, qy, qz, qw = qx / norm, qy / norm, qz / norm, qw / norm
    return ((1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw), 0.0),
            (2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw), 0.0),
            (2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy), 0.0),
            (0.0, 0.0, 0.0, 1.0))


def _mat_from_quat_trans(qx, qy, qz, qw, tx, ty, tz) -> tuple:
    rows = [list(row) for row in _mat_from_quat(qx, qy, qz, qw)]
    rows[0][3], rows[1][3], rows[2][3] = tx, ty, tz
    return tuple(tuple(row) for row in rows)


def _mat_apply(m: tuple, v) -> tuple:
    x, y, z = v
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def _mat_apply_dir(m: tuple, v) -> tuple:
    x, y, z = v
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z,
            m[1][0] * x + m[1][1] * y + m[1][2] * z,
            m[2][0] * x + m[2][1] * y + m[2][2] * z)


def prop_point_matrix(mesh: dict, name: str):
    """Model-space matrix of the named prop point, or None when absent.

    Prop points carry a bone index; the stored translation/quaternion are relative
    to that bone's bind pose, so the bone transform has to be composed in front.
    """
    for point in mesh.get("prop_points", ()):
        if point["name"] != name:
            continue
        local = _mat_from_quat_trans(point["qx"], point["qy"], point["qz"], point["qw"],
                                     point["tx"], point["ty"], point["tz"])
        bone = point["bone"]
        if bone == 255:
            return local
        bx, by, bz, bqx, bqy, bqz, bqw = mesh["bones"][bone]
        bone_mat = _mat_from_quat_trans(bqx, bqy, bqz, bqw, bx, by, bz)
        return _mat_mul(bone_mat, local)
    return None


def parse_pmd(data: bytes) -> dict:
    """Read exactly one PSMD v4 payload, rejecting invalid offsets and indices."""
    c = Cursor(data)
    magic, version, payload_size = c.unpack("<4sII")
    if magic != b"PSMD" or version != 4 or payload_size != len(data) - 12:
        raise PMDError("invalid PSMD v4 header or payload length")
    count = c.count(MAX_VERTICES, "vertex")
    uv_count = c.count(MAX_UV_SETS, "UV set")
    if not count or not uv_count:
        raise PMDError("PMD must contain vertices and at least one UV set")
    vertices = []
    normals = []
    uvs = []
    blends = []
    for _ in range(count):
        position = c.unpack("<3f")
        normal = c.unpack("<3f")
        _finite(position, "position")
        _finite(normal, "normal")
        uv = c.unpack("<2f")
        _finite(uv, "UV")
        for _ in range(uv_count - 1):
            _finite(c.unpack("<2f"), "UV")
        blend_bytes = c.take(20)  # SVertexBlend: four u8 indices + four floats (weights)
        weights = struct.unpack_from('<4f', blend_bytes, 4)
        _finite(weights, 'blend weights')
        if any(w < 0 or w > 1 for w in weights):
            raise PMDError('invalid blend weights')
        blends.append(blend_bytes)
        vertices.append(position)
        normals.append(normal)
        uvs.append(uv)
    face_count = c.count(MAX_FACES, "face")
    if not face_count:
        raise PMDError("PMD has no faces")
    faces = []
    for _ in range(face_count):
        face = c.unpack("<3H")
        if any(index >= count for index in face):
            raise PMDError(f"face references vertex outside 0..{count - 1}")
        faces.append(face)
    bone_count = c.count(MAX_BONES, "bone")
    bone_transforms = []
    if bone_count:
        for b_raw in blends:
            for b_idx in b_raw[:4]:
                if b_idx != 255 and b_idx >= bone_count:
                    raise PMDError(f"vertex blend references bone {b_idx} >= {bone_count}")
    for _ in range(bone_count):
        bt = c.unpack("<7f")
        _finite(bt, "bone transform")  # translation + quaternion
        bone_transforms.append(bt)
    prop_count = c.count(MAX_PROP_POINTS, "prop point")
    # 0 A.D. actors attach their <props> to these named prop points, so the raw
    # bind-pose transform of each point has to survive parsing: it is the only way
    # to place a head/weapon/roof mesh in the parent's local space.
    prop_points = []
    for _ in range(prop_count):
        name_length = c.count(len(data), "prop name length")
        raw_name = c.take(name_length)
        tx, ty, tz, qx, qy, qz, qw = c.unpack("<7f")
        _finite((tx, ty, tz, qx, qy, qz, qw), "prop transform")
        bone = c.unpack("<B")[0]
        if bone != 255 and bone >= bone_count:
            raise PMDError("prop references missing bone")
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PMDError(f"undecodable prop point name: {exc}") from exc
        prop_points.append({"name": name, "tx": tx, "ty": ty, "tz": tz,
                            "qx": qx, "qy": qy, "qz": qz, "qw": qw, "bone": bone})
    if c.pos != len(data):
        raise PMDError(f"trailing bytes at offset {c.pos}")
    return {"positions": vertices, "normals": normals, "uvs": uvs,
            "faces": faces, "bone_count": bone_count, "uv_sets": uv_count,
            "prop_count": prop_count, "prop_points": prop_points,
            "bones": bone_transforms, "blends": blends}


def render_obj(mesh, texture_name: str, scale: float = SCALE) -> str:
    """Write one multi-piece OBJ.

    ``mesh`` is either a single parsed PMD dict (legacy single-piece call) or a
    list of piece dicts as produced by :func:`resolve_model_pieces`. Every piece
    becomes its own ``o``/``usemtl`` block so Recoil exposes it as a named
    piece that the LUS scripts can address, while all pieces share one material
    and therefore one texture lookup (``tex1``).
    """
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be positive and finite")
    pieces = [{"name": "base", **mesh}] if isinstance(mesh, dict) else list(mesh)
    if not pieces:
        raise ValueError("a model must export at least one piece")
    lines = ["# Static bind-pose geometry from 0 A.D. PSMD v4",
             "# Y-up, yawed 180 about Y so 0 A.D. -Z facing maps to Recoil +Z forward,",
             "# uniform scale 8; props merged at bind pose",
             f"# {len(pieces)} piece(s): " + ", ".join(piece["name"] for piece in pieces)]
    v_base = vt_base = vn_base = 0
    for piece in pieces:
        name = piece["name"]
        # Only `o` is emitted: a matching `g` makes Assimp create a second,
        # identically-named mesh per piece, which Recoil uniquifies into `xx00`
        # twins and leaves scripts animating the wrong half.
        lines += [f"o {name}", f"usemtl {name}"]
        for x, y, z in piece["positions"]:
            lines.append(f"v {-x * scale + 0.0:.9g} {y * scale:.9g} {-z * scale + 0.0:.9g}")
        for u, v in piece["uvs"]:
            lines.append(f"vt {u:.9g} {1 - v:.9g}")  # 0 A.D. and OBJ vertical UV origin differ
        for x, y, z in piece["normals"]:
            lines.append(f"vn {-x + 0.0:.9g} {y:.9g} {-z + 0.0:.9g}")
        for a, b, c in piece["faces"]:
            # OBJ references are one-based and run across the whole file, so each
            # piece is offset by everything already written.
            # 0 A.D. PMD stores faces wound CLOCKWISE relative to Recoil's
            # CCW-front convention (the geometric normal points opposite the
            # stored vertex normals). Reordering (a, c, b) reverses the winding
            # so front faces and lighting normals agree, fixing backface culling.
            lines.append("f " + " ".join(
                f"{v_base + i + 1}/{vt_base + i + 1}/{vn_base + i + 1}" for i in (a, c, b)))
        v_base += len(piece["positions"])
        vt_base += len(piece["uvs"])
        vn_base += len(piece["normals"])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Piece assembly: resolve an actor into the named pieces of one OBJ.
# --------------------------------------------------------------------------- #

# 0 A.D. attachpoints that name a body part the LUS scripts already probe. Any
# other attachpoint keeps its own sanitised name so nothing is silently merged.
_ATTACH_PIECE = {
    "head": "head",
    "helmet": "helmet",
    "shield": "shield",
    "shield_arm": "shield",
    "rider": "rider",
    "weapon": "weapon",
    "weapon_r": "weapon",
    "weapon_l": "weapon",
    "weapon_bow": "weapon",
    "torso": "torso",
    "arm": "arm",
    "wheel": "wheel",
    "axle": "axle",
}

MAX_PROP_DEPTH = 6


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").lower()
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "p_" + cleaned
    return cleaned


def _mesh_basename(mesh_path: str) -> str:
    base = mesh_path.rsplit("/", 1)[-1]
    for suffix in (".dae", ".pmd", ".cached"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _piece_name(attachpoint: str, mesh_path: str) -> str:
    """Name the piece a resolved mesh becomes.

    Body-part attachpoints map onto the names the LUS scripts probe; a building's
    roof or palisade is recognised from its own mesh name; every other prop is
    named after its own mesh, so unrelated building props stay individually
    addressable rather than being folded into ``base``.
    """
    low = _mesh_basename(mesh_path).lower()
    if "roof" in low:
        return "roof"
    if "palisade" in low or "wall" in low:
        return "wall"
    mapped = _ATTACH_PIECE.get(attachpoint.strip().lower())
    if mapped:
        return mapped
    # Generic attachpoints such as ``root``/``props`` carry unrelated building
    # props, so those are named after their own mesh instead of being folded
    # together into one piece.
    return _sanitize(_mesh_basename(mesh_path))


# --- Bone splitting ------------------------------------------------------------ #
# A 0 A.D. skeletal mesh is one PSMD hull whose vertices carry up to four weighted
# bone influences. Exporting it as a single OBJ piece gives the LUS scripts nothing
# to animate, so the hull is partitioned per dominant bone: every triangle goes to
# the bone its vertices vote for, and each resulting piece becomes a named OBJ
# ``o`` block that Recoil exposes to ``piece "thigh_l"``-style lookups.

SKELETON_PREFIX = "art/skeletons/"
SKELETON_HORSE = SKELETON_PREFIX + "horse.xml"
SKELETON_BIPED = SKELETON_PREFIX + "biped.xml"
SKELETON_BOVIDAE = SKELETON_PREFIX + "bovidae_skeleton.xml"
# SVertexBlend stores four u8 indices followed by four float weights; index 255 is
# the "no influence" sentinel.
BLEND_NONE = 255


def _normalise_bone_name(raw: str) -> str:
    """Lowercase a skeleton bone name and unify its side marker to ``_l``/``_r``."""
    name = raw.replace("_L", "_l").replace("_R", "_r")
    return name.lower()


def parse_skeleton(zf: zipfile.ZipFile, xml_path: str) -> list:
    """Read ``art/skeletons/<name>.xml`` and return its bone names in document order."""
    document = ET.fromstring(zf.read(xml_path).decode("utf-8-sig"))
    standard = next((node for node in document.iter() if _strip_ns(node.tag) == "standard_skeleton"), None)
    if standard is None:
        raise ValueError(f"{xml_path} has no <standard_skeleton>")
    names = []
    for bone in standard.iter("bone"):
        raw = bone.get("name")
        if not raw:
            raise ValueError(f"{xml_path} has an unnamed <bone>")
        names.append(_normalise_bone_name(raw))
    if not names:
        raise ValueError(f"{xml_path} declares no bones")
    return names


def _primary_bones(mesh: dict) -> list:
    """Index of the heaviest bone influence per vertex, or ``BLEND_NONE``."""
    primaries = []
    for blend in mesh["blends"]:
        weights = struct.unpack_from("<4f", blend, 4)
        best_bone, best_weight = BLEND_NONE, -1.0
        for slot in range(4):
            bone = blend[slot]
            if bone == BLEND_NONE:
                continue
            if weights[slot] > best_weight:
                best_bone, best_weight = bone, weights[slot]
        primaries.append(best_bone)
    return primaries


def _dominant_bone(face, primaries) -> int:
    """Bone owning a triangle: majority vote over its vertices, ties to the lowest."""
    votes = {}
    for vertex in face:
        bone = primaries[vertex]
        if bone == BLEND_NONE:
            continue
        votes[bone] = votes.get(bone, 0) + 1
    if not votes:
        return BLEND_NONE
    return max(votes, key=lambda bone: (votes[bone], -bone))


def split_skinned_mesh(mesh: dict, bone_names: list) -> list:
    """Partition a parsed PMD into one piece per dominant bone.

    Returns ``[{"name": "base", **mesh}]`` unchanged when the hull is unskinned or
    carries no blend data. Faces whose vertices name no bone at all stay together
    in a ``base`` piece, which is also the anchor the LUS scripts expect, so a
    split model keeps both its named parts and its root piece.
    """
    if mesh.get("bone_count", 0) <= 1 or not mesh.get("blends"):
        return [{"name": "base", **mesh}]
    primaries = _primary_bones(mesh)
    faces_by_bone = {}
    for face in mesh["faces"]:
        faces_by_bone.setdefault(_dominant_bone(face, primaries), []).append(face)
    pieces = []
    for bone in sorted(faces_by_bone):
        bone_faces = faces_by_bone[bone]
        if bone == BLEND_NONE:
            piece_name = "base"
        elif bone < len(bone_names):
            piece_name = bone_names[bone]
        else:
            piece_name = f"bone_{bone}"
        piece_name = _sanitize(piece_name)
        remap = {}
        positions, normals, uvs, indices = [], [], [], []
        for face in bone_faces:
            triangle = []
            for vertex in face:
                if vertex not in remap:
                    remap[vertex] = len(positions)
                    positions.append(mesh["positions"][vertex])
                    normals.append(mesh["normals"][vertex])
                    uvs.append(mesh["uvs"][vertex])
                triangle.append(remap[vertex])
            indices.append(tuple(triangle))
        pieces.append({"name": piece_name, "positions": positions, "normals": normals,
                       "uvs": uvs, "faces": indices})
    return pieces or [{"name": "base", **mesh}]


def _skeleton_for(actor_path: str, want_mesh: str) -> str:
    """Skeleton XML governing a model, or ``""`` when it is a static hull.

    Horse is tested first because every horse mesh also lives under ``skeletal/``.
    """
    haystack = f"{actor_path} {want_mesh}".lower()
    if "horse" in haystack:
        return SKELETON_HORSE
    if "skeletal" in haystack:
        return SKELETON_BIPED
    if any(token in haystack for token in ("bovidae", "cattle", "cow", "bull")):
        return SKELETON_BOVIDAE
    return ""


class _MergeContext:
    """Collects merged pieces plus the warnings an unattended run must not hide."""

    def __init__(self) -> None:
        self.pieces = []
        self.warnings = []
        self.resolved = 0
        self.skipped = []
        self.visited = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def add(self, name: str, mesh: dict, matrix, source: str) -> None:
        positions = [_mat_apply(matrix, p) for p in mesh["positions"]]
        normals = [_mat_apply_dir(matrix, n) for n in mesh["normals"]]
        existing = next((piece for piece in self.pieces if piece["name"] == name), None)
        if existing is None:
            self.pieces.append({"name": name, "positions": positions, "normals": normals,
                                "uvs": list(mesh["uvs"]), "faces": list(mesh["faces"]),
                                "sources": [source]})
            return
        offset = len(existing["positions"])
        existing["positions"].extend(positions)
        existing["normals"].extend(normals)
        existing["uvs"].extend(mesh["uvs"])
        existing["faces"].extend(tuple(i + offset for i in face) for face in mesh["faces"])
        existing["sources"].append(source)


def _attach_matrix(host_mesh: dict, attachpoint: str, ctx: _MergeContext, reference: str):
    """Model-space matrix for ``attachpoint`` on ``host_mesh``.

    A prop with no matching prop point falls back to identity so the model still
    builds, but the miss is recorded because it means a prop sits at the origin.
    """
    matrix = prop_point_matrix(host_mesh, attachpoint)
    if matrix is None:
        ctx.warn(f"no prop point {attachpoint!r} on mesh hosting {reference}; using identity")
        return _mat_identity()
    return matrix


def _actor_document(zf: zipfile.ZipFile, reference: str, ctx: _MergeContext):
    """Read a prop actor/variant XML, trying both archive roots."""
    for prefix in (ACTOR_PREFIX, VARIANT_PREFIX):
        try:
            raw = zf.read(prefix + reference)
        except KeyError:
            continue
        try:
            return ET.fromstring(raw.decode("utf-8-sig"))
        except ET.ParseError as exc:
            ctx.warn(f"malformed prop actor {reference}: {exc}")
            return None
    ctx.warn(f"unresolved prop actor {reference}")
    ctx.skipped.append(reference)
    return None


def _merge_actor(zf: zipfile.ZipFile, reference: str, matrix, host_mesh: dict,
                 attachpoint: str, ctx: _MergeContext, depth: int = 1) -> None:
    """Recursively merge one prop actor and every prop nested inside it.

    A prop actor's geometry may arrive directly as a <mesh> or through a
    <variant file="..."> indirection, and its nested props attach to *that* mesh,
    not to the parent host. A nested prop keeps its own contract name (a rider's
    head becomes ``head``), while props with no contract name inherit the
    enclosing piece, so a shield's handgrip stays part of ``shield``.
    """
    if depth > MAX_PROP_DEPTH:
        ctx.warn(f"prop nesting deeper than {MAX_PROP_DEPTH} at {reference}")
        return
    document = _actor_document(zf, reference, ctx)
    if document is None:
        return
    ctx.visited.append(reference)
    variants = _selected_variants(document)

    # Pass 1: merge this actor's own geometry and remember the mesh carrying the
    # prop points its children attach to.
    self_host = None
    piece = None
    for variant in variants:
        variant_ref = _variant_file_ref(variant)
        if variant_ref:
            _merge_actor(zf, variant_ref, matrix, host_mesh, attachpoint, ctx, depth + 1)
            if self_host is None:
                self_host = _first_prop_mesh(zf, variant_ref, ctx)
        for mesh_path in _variant_meshes(variant):
            pmd_path = MESH_PREFIX + mesh_path + ".cached.pmd"
            try:
                mesh = parse_pmd(zf.read(pmd_path))
            except KeyError:
                ctx.warn(f"missing cached mesh {pmd_path}")
                ctx.skipped.append(reference)
                continue
            if piece is None:
                piece = _piece_name(attachpoint, mesh_path)
            ctx.add(piece, mesh, matrix, pmd_path)
            ctx.resolved += 1
            if self_host is None:
                self_host = mesh

    # Pass 2: attach every nested prop to this actor's own mesh when it has one.
    attach_host = self_host if self_host is not None else host_mesh
    for variant in variants:
        for child_point, child in _collect_parts(variant):
            # A child that names a contract piece (head/weapon/shield) takes that
            # name; anything else stays part of the piece it was attached to.
            inherited = (_ATTACH_PIECE.get(child_point.strip().lower())
                         if _ATTACH_PIECE.get(child_point.strip().lower()) else attachpoint)
            child_matrix = _mat_mul(matrix, _attach_matrix(attach_host, child_point, ctx, child))
            _merge_actor(zf, child, child_matrix, attach_host, inherited, ctx, depth + 1)


def _first_prop_mesh(zf: zipfile.ZipFile, reference: str, ctx: _MergeContext, depth: int = 1):
    """Return the first mesh a referenced actor contributes, without merging it."""
    if depth > MAX_PROP_DEPTH:
        return None
    document = _actor_document(zf, reference, ctx)
    if document is None:
        return None
    for variant in _selected_variants(document):
        variant_ref = _variant_file_ref(variant)
        if variant_ref:
            found = _first_prop_mesh(zf, variant_ref, ctx, depth + 1)
            if found is not None:
                return found
        for mesh_path in _variant_meshes(variant):
            try:
                return parse_pmd(zf.read(MESH_PREFIX + mesh_path + ".cached.pmd"))
            except KeyError:
                ctx.warn(f"missing cached mesh {MESH_PREFIX + mesh_path}.cached.pmd")
    return None


def resolve_model_pieces(zf: zipfile.ZipFile, actor_path: str, want_mesh: str) -> tuple:
    """Resolve an actor into (pieces, warnings, resolved, skipped).

    ``base`` is always first and always present. Every <props> reference reachable
    from the actor's live variants is merged in, each placed by the prop point it
    is attached to, in PMD space and before the OBJ scale is applied.
    """
    document = ET.fromstring(zf.read(actor_path).decode("utf-8-sig"))
    variants = _selected_variants(document)
    root_pmd = None
    root_path = MESH_PREFIX + want_mesh + ".cached.pmd"
    for variant in variants:
        if want_mesh in _variant_meshes(variant):
            root_pmd = parse_pmd(zf.read(root_path))
            break
    if root_pmd is None:
        raise ValueError(f"{actor_path} has no variant selecting mesh {want_mesh}")
    ctx = _MergeContext()
    # A skinned hull is split per dominant bone so the LUS scripts get real pieces
    # to animate; a static hull (or one whose skeleton is unavailable) stays whole.
    pieces = None
    skeleton = _skeleton_for(actor_path, want_mesh)
    if skeleton:
        try:
            pieces = split_skinned_mesh(root_pmd, parse_skeleton(zf, skeleton))
        except (KeyError, ValueError) as exc:
            ctx.warn(f"{skeleton} unavailable for {root_path}: {exc}")
    for piece in pieces or [{"name": "base", **root_pmd}]:
        ctx.add(piece["name"], piece, _mat_identity(), root_path)
    for variant in variants:
        meshes = _variant_meshes(variant)
        if meshes and want_mesh not in meshes:
            continue  # an alternative structural variant of the same actor
        variant_ref = _variant_file_ref(variant)
        if variant_ref:
            _merge_actor(zf, variant_ref, _mat_identity(), root_pmd, "", ctx)
        for attachpoint, reference in _collect_parts(variant):
            matrix = _attach_matrix(root_pmd, attachpoint, ctx, reference)
            _merge_actor(zf, reference, matrix, root_pmd, attachpoint, ctx)
    return ctx.pieces, ctx.warnings, ctx.resolved, ctx.skipped


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --- Team-color neutralisation -------------------------------------------------
# Recoil's model shader samples tex1's ALPHA channel as the team-color mask
# (alpha 255 => 100% team color). The 0 A.D. diffuse textures carry no team-color
# masks and are fully opaque, so every converted model would otherwise render as a
# solid blue team-color blob. Zeroing alpha everywhere removes team coloring while
# preserving the RGB color bytes exactly.
DDS_MAGIC = b"DDS "
DDS_HEADER_SIZE = 128  # magic (4) + DDS_HEADER (124)
# Offsets are absolute in the file, i.e. 4 (magic) + the DDS_HEADER field offset.
DDS_HEIGHT_OFFSET = 4 + 8
DDS_WIDTH_OFFSET = 4 + 12
DDS_PITCH_OFFSET = 4 + 16  # DDS_HEADER.dwPitchOrLinearSize
DDS_MIPMAP_OFFSET = 4 + 24  # DDS_HEADER.dwMipMapCount
DDS_PIXELFORMAT_OFFSET = 4 + 72  # ddspf.dwSize
DDS_PF_FLAGS_OFFSET = DDS_PIXELFORMAT_OFFSET + 4
DDS_FOURCC_OFFSET = DDS_PIXELFORMAT_OFFSET + 8
_DDPF_FOURCC = 0x4
_DDPF_ALPHAPIXELS = 0x1


def _dds_fourcc(data: bytes) -> str:
    """Return the DDS pixel-format FOURCC (``DXT1``/``DXT5``/...), or '' if absent."""
    if len(data) < DDS_HEADER_SIZE or data[:4] != DDS_MAGIC:
        raise ValueError("not a DDS file")
    return data[DDS_FOURCC_OFFSET:DDS_FOURCC_OFFSET + 4].decode("ascii", "replace")


def _dds_mip_count(data: bytes) -> int:
    return struct.unpack_from("<I", data, DDS_MIPMAP_OFFSET)[0] or 1


def _dds_level_sizes(width: int, height: int, block_bytes: int) -> list[int]:
    """Byte size of every mip level down to 1x1, in DXT block units."""
    sizes = []
    w, h = max(width, 1), max(height, 1)
    while True:
        sizes.append(max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block_bytes)
        if w == 1 and h == 1:
            return sizes
        w, h = max(1, w // 2), max(1, h // 2)


def zero_dds_alpha(data: bytes) -> bytes:
    """Return ``data`` with every texel's alpha forced to 0, RGB bytes untouched.

    DXT5 (BC3) blocks are 16 bytes: the 8 leading bytes are the alpha block, so
    they are zeroed and the colour bytes at offsets 8..15 are copied verbatim.

    DXT1 (BC1) blocks are 8 bytes of colour-interpolation data with an implicit
    1-bit alpha (the ``c0 <= c1`` 3-colour mode reserves one index for fully
    transparent black). That mode cannot express "opaque RGB, zero alpha", so the
    texture is rewrapped as DXT5: the FOURCC becomes ``DXT5``, the pitch and DDPF
    flags are fixed up, and each block becomes 8 zero alpha bytes followed by the
    original 8 colour bytes - the colour endpoints and interpolation indices are
    preserved verbatim and the 1-bit alpha interpretation is bypassed entirely.

    All mip levels are covered; every other header field and all trailing bytes
    are preserved.
    """
    if len(data) < DDS_HEADER_SIZE or data[:4] != DDS_MAGIC:
        raise ValueError("not a DDS file")
    fourcc = _dds_fourcc(data)
    if fourcc not in ("DXT1", "DXT5"):
        raise ValueError(f"unsupported DDS pixel format {fourcc!r}; expected DXT1 or DXT5")

    width = struct.unpack_from("<I", data, DDS_WIDTH_OFFSET)[0]
    height = struct.unpack_from("<I", data, DDS_HEIGHT_OFFSET)[0]
    if width == 0 or height == 0:
        raise ValueError("DDS header declares a zero dimension")
    mips = _dds_mip_count(data)
    levels = _dds_level_sizes(width, height, 8 if fourcc == "DXT1" else 16)[:mips]
    expected = sum(levels)
    body = data[DDS_HEADER_SIZE:]
    if len(body) != expected:
        raise ValueError(
            f"DDS payload is {len(body)} bytes but the {fourcc} header implies {expected}"
        )

    out = bytearray(data)
    if fourcc == "DXT5":
        for base in range(0, len(body), 16):
            start = DDS_HEADER_SIZE + base
            out[start:start + 8] = b"\x00" * 8
    else:
        # DXT1 -> DXT5 rewrap: 8 colour bytes become the second half of a 16-byte block.
        out[DDS_FOURCC_OFFSET:DDS_FOURCC_OFFSET + 4] = b"DXT5"
        flags = struct.unpack_from("<I", data, DDS_PF_FLAGS_OFFSET)[0]
        struct.pack_into("<I", out, DDS_PF_FLAGS_OFFSET,
                         flags | _DDPF_FOURCC | _DDPF_ALPHAPIXELS)
        # DXT5 stores 16 bytes per block, so the top-level linear size doubles.
        struct.pack_into("<I", out, DDS_PITCH_OFFSET, levels[0] * 2)
        converted = bytearray()
        for base in range(0, len(body), 8):
            converted += b"\x00" * 8 + body[base:base + 8]
        out[DDS_HEADER_SIZE:] = converted
    return bytes(out)


def _archive_sha256(path: Path, chunk: int = 16 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def build(archive: Path = DEFAULT_ARCHIVE, root: Path = ROOT) -> dict:
    output_meshes = root / "objects3d/0ad"
    output_textures = root / "unittextures/0ad"
    output_docs = root / "licenses"
    output_meshes.mkdir(parents=True, exist_ok=True)
    output_textures.mkdir(parents=True, exist_ok=True)
    output_docs.mkdir(parents=True, exist_ok=True)
    manifest = {
        "archive": str(archive), "archive_sha256": _archive_sha256(archive),  # entry hashes avoid hashing multi-GB archive
        "source": "0 A.D. alpha 28 public.zip",
        "format_sources": [
            "https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/collada/PMDConvert.cpp",
            "https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/graphics/ModelDef.cpp",
            "https://github.com/0ad/0ad/blob/61a3b9507d974084e6badb88a0826bd89a6d5b8b/source/ps/FileIo.cpp",
        ],
        "license": "CC-BY-SA-3.0, Wildfire Games; see licenses/0ad-art.txt",
        "transform": {"axes": "Y-up unchanged", "scale": SCALE, "translation": [0, 0, 0],
                      "uv": "v -> 1-v for OBJ",
                      "pose": "PMD v4 bind-pose positions; no skinning",
                      "props": "actor <props> merged at their prop points (bone bind pose * prop local)",
                      # 0 A.D. diffuses carry no team-color mask, so tex1 alpha is zeroed
                      # everywhere to stop Recoil rendering units as solid team color.
                      "texture_alpha": "texel alpha zeroed (DXT1 rewrapped as DXT5); RGB bytes preserved"},
        "entries": {}, "units": {}, "buildings": {},
    }
    with zipfile.ZipFile(archive) as zf:
        def source(entry: str) -> bytes:
            data = zf.read(entry)  # exact entry; no archive-wide extraction
            manifest["entries"][entry] = {"sha256": _sha256(data), "bytes": len(data)}
            return data

        license_bytes = source("art/LICENSE.txt")
        (output_docs / "0ad-art.txt").write_bytes(license_bytes)
        for model, kind in _MODEL_ORDER:
            choice = MODELS[model]
            actor_path = choice["actor"]  # full archive path, recorded verbatim in the manifest
            actor = source(actor_path).decode("utf-8-sig")
            if f"<mesh>{choice['mesh']}</mesh>" not in actor:
                raise ValueError(f"{actor_path} does not select requested mesh")
            if "variant" in choice:
                variant_path = choice["variant"]
                variant = source(variant_path).decode("utf-8-sig")
                if f'file="{choice["texture"]}" name="baseTex"' not in variant:
                    raise ValueError(f"{variant_path} does not select requested baseTex")
                if "brown.xml" not in actor:
                    raise ValueError(f"{actor_path} does not include brown variant")
            elif f'file="{choice["texture"]}" name="baseTex"' not in actor:
                raise ValueError(f"{actor_path} does not select requested baseTex")
            mesh_path = MESH_PREFIX + choice["mesh"] + ".cached.pmd"
            texture_path = SKIN_PREFIX + choice["texture"] + ".cached.dds"
            root_mesh = parse_pmd(source(mesh_path))
            # Resolve the actor's <props> so heads, weapons, shields and building
            # roofs/palisades are merged at their prop points instead of dropped.
            pieces, warnings, resolved, unresolved = resolve_model_pieces(
                zf, actor_path, choice["mesh"])
            for message in warnings:
                print(f"WARNING {model}: {message}")
            raw_texture = source(texture_path)
            if raw_texture[:4] != b"DDS ":
                raise ValueError(f"{texture_path} is not DDS")
            texture_name = model + ".dds"
            # Zero every texel's alpha before the bytes are written, so the manifest
            # records the POST-transform digest: the on-disk DDS and its recorded
            # sha256/bytes can never disagree about the team-color fix.
            texture = zero_dds_alpha(raw_texture)
            manifest["entries"][texture_path] = {"sha256": _sha256(texture), "bytes": len(texture)}
            (output_textures / texture_name).write_bytes(texture)
            obj_path = output_meshes / (model + ".obj")
            obj_path.write_text(render_obj(pieces, texture_name), encoding="utf-8", newline="\n")
            # Recoil Assimp reads OBJ model-side metadata and resolves tex1 in unittextures/.
            (output_meshes / (model + ".lua")).write_text(
                f'return {{ tex1 = "0ad/{texture_name}" }}\n', encoding="utf-8", newline="\n")
            all_positions = [(-p[0], p[1], -p[2]) for piece in pieces for p in piece["positions"]]
            manifest["units" if kind == "unit" else "buildings"][model] = {
                "actor": actor_path, "mesh": mesh_path, "texture": texture_path,
                "obj": obj_path.relative_to(root).as_posix(),
                "tex1": f"0ad/{texture_name}",
                "pieces": [piece["name"] for piece in pieces],
                "vertices": sum(len(piece["positions"]) for piece in pieces),
                "faces": sum(len(piece["faces"]) for piece in pieces),
                "bones_ignored": root_mesh["bone_count"], "props_ignored": len(unresolved),
                "props_resolved": resolved,
                # Post-scale OBJ-space extents over every merged piece, so
                # oversized/short sources are visible in provenance instead of
                # being silently accepted.
                "bounds": {axis: [round(min(p[i] for p in all_positions) * SCALE, 3),
                                 round(max(p[i] for p in all_positions) * SCALE, 3)]
                           for i, axis in enumerate("xyz")},
            }
    path = root / "tools/assets/0ad-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = build(args.archive, args.root)
    for group in ("units", "buildings"):
        for name, model in result[group].items():
            print(f"{name}: {model['vertices']} vertices, {model['faces']} triangles; {model['obj']}")
    print("Manifest: tools/assets/0ad-manifest.json")
