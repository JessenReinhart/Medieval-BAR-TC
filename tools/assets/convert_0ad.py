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
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = Path.home() / "AppData/Local/0 A.D. Empires Ascendant/binaries/data/mods/public/public.zip"
MESH_PREFIX = "art/meshes/"
SKIN_PREFIX = "art/textures/skins/"
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
}
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
    if bone_count:
        for b_raw in blends:
            for b_idx in b_raw[:4]:
                if b_idx != 255 and b_idx >= bone_count:
                    raise PMDError(f"vertex blend references bone {b_idx} >= {bone_count}")
    for _ in range(bone_count):
        _finite(c.unpack("<7f"), "bone transform")  # translation + quaternion
    prop_count = c.count(MAX_PROP_POINTS, "prop point")
    for _ in range(prop_count):
        name_length = c.count(len(data), "prop name length")
        c.take(name_length)
        _finite(c.unpack("<7f"), "prop transform")
        bone = c.unpack("<B")[0]
        if bone != 255 and bone >= bone_count:
            raise PMDError("prop references missing bone")
    if c.pos != len(data):
        raise PMDError(f"trailing bytes at offset {c.pos}")
    return {"positions": vertices, "normals": normals, "uvs": uvs,
            "faces": faces, "bone_count": bone_count, "uv_sets": uv_count,
            "prop_count": prop_count}


def render_obj(mesh: dict, texture_name: str, scale: float = SCALE) -> str:
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be positive and finite")
    lines = ["# Static bind-pose geometry from 0 A.D. PSMD v4",
             "# Y-up, original orientation, uniform scale 8; no skinning or attachments",
             "o base", "g base", "usemtl base"]
    for x, y, z in mesh["positions"]:
        lines.append(f"v {x * scale:.9g} {y * scale:.9g} {z * scale:.9g}")
    for u, v in mesh["uvs"]:
        lines.append(f"vt {u:.9g} {1 - v:.9g}")  # 0 A.D. and OBJ vertical UV origin differ
    for x, y, z in mesh["normals"]:
        lines.append(f"vn {x:.9g} {y:.9g} {z:.9g}")
    for a, b, c in mesh["faces"]:
        # OBJ references are one-based; identical UV and normal indices.
        lines.append("f " + " ".join(f"{i + 1}/{i + 1}/{i + 1}" for i in (a, b, c)))
    return "\n".join(lines) + "\n"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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
                      "uv": "v -> 1-v for OBJ", "pose": "PMD v4 bind-pose positions; no skinning"},
        "entries": {}, "units": {},
    }
    with zipfile.ZipFile(archive) as zf:
        def source(entry: str) -> bytes:
            data = zf.read(entry)  # exact entry; no archive-wide extraction
            manifest["entries"][entry] = {"sha256": _sha256(data), "bytes": len(data)}
            return data

        license_bytes = source("art/LICENSE.txt")
        (output_docs / "0ad-art.txt").write_bytes(license_bytes)
        for unit, choice in UNITS.items():
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
            mesh = parse_pmd(source(mesh_path))
            texture = source(texture_path)
            if texture[:4] != b"DDS ":
                raise ValueError(f"{texture_path} is not DDS")
            texture_name = unit + ".dds"
            (output_textures / texture_name).write_bytes(texture)
            obj_path = output_meshes / (unit + ".obj")
            obj_path.write_text(render_obj(mesh, texture_name), encoding="utf-8", newline="\n")
            # Recoil Assimp reads OBJ model-side metadata and resolves tex1 in unittextures/.
            (output_meshes / (unit + ".lua")).write_text(
                f'return {{ tex1 = "0ad/{texture_name}" }}\n', encoding="utf-8", newline="\n")
            manifest["units"][unit] = {
                "actor": actor_path, "mesh": mesh_path, "texture": texture_path,
                "obj": obj_path.relative_to(root).as_posix(),
                "tex1": f"0ad/{texture_name}",
                "vertices": len(mesh["positions"]), "faces": len(mesh["faces"]),
                "bones_ignored": mesh["bone_count"], "props_ignored": mesh["prop_count"],
                # Post-scale OBJ-space extents, so oversized/short sources are visible
                # in provenance instead of being silently accepted.
                "bounds": {axis: [round(min(p[i] for p in mesh["positions"]) * SCALE, 3),
                                 round(max(p[i] for p in mesh["positions"]) * SCALE, 3)]
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
    for name, unit in result["units"].items():
        print(f"{name}: {unit['vertices']} vertices, {unit['faces']} triangles; {unit['obj']}")
    print("Manifest: tools/assets/0ad-manifest.json")
