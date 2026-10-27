#!/usr/bin/env python3
"""Phase 7 slice 11: bake 0 A.D. PSA skeletal animation into Lua world-pose data.

Where ``tools/assets/convert_0ad.py`` exports the *bind-pose* geometry and splits a
skinned hull into named OBJ ``o`` pieces, this tool exports the *motion*: for every
clip it samples each bone's WORLD (root-relative) pose straight out of the shipped
``*.dae.cached.psa`` and writes a Lua table keyed by the SAME normalised piece name
slice 10 emitted.

Locked math (source-verified, reused verbatim -- not re-derived here):

* Layout: 12-byte FileHeader (``PSSA``, ver=1, payloadLen), PackString(name),
  f32 frameTime (ms), u32 numKeys (== bone count), u32 numFrames, then
  ``numFrames * numKeys`` records of 28 bytes = tx,ty,tz (f32) + qx,qy,qz,qw
  (f32, quaternion x,y,z,w).  Dense frame-major:
  ``key(frame, bone) = keys[frame * numKeys + bone]``.  Parsing lives in
  :mod:`tools.assets.parse_psa`.
* BOTH translation and rotation are WORLD / ROOT-RELATIVE, so no FK walk is
  needed: ``CSkeletonAnimDef::BuildBoneMatrices`` rebuilds each world matrix
  directly from the key.
* The OBJ export applied a yaw of +180 deg about Y (``x -> -x``, ``z -> -z``) and a
  uniform scale (``convert_0ad.SCALE == 8.0``).  The identical rigid transform is
  applied to the world pose:
      ``t' = 8 * (-tx, ty, -tz)``
      ``q' = Q_y180 * q``  with ``Q_y180 = (x=0, y=1, z=0, w=0)``  (Hamilton product,
      left-multiplied because it is a global rotation).
  That is exactly :func:`tools.assets.read_psa_content.world_pose`, which this
  module calls with ``scale=convert_0ad.SCALE`` so there is one implementation.
* Bone index in the PSA == document order of ``<bone>`` in
  ``art/skeletons/biped.xml`` (46) / ``horse.xml`` (49).  Names are normalised with
  ``convert_0ad.parse_skeleton`` (side marker unified to ``_l``/``_r``, lowercased)
  and then ``convert_0ad._sanitize`` -- the exact chain ``split_skinned_mesh`` uses,
  so bone -> piece names match the slice-10 OBJ groups.

Only bones that survive as a real piece of the unit's model are baked; the piece
list comes from ``tools/assets/0ad-manifest.json``.

Stdlib only.  No Spring/Recoil runtime is required.

    python tools/assets/convert_0ad_anim.py
    python tools/assets/convert_0ad_anim.py --archive <public.zip> --out-dir scripts/animdata
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from pathlib import Path

# --- allow ``python tools/assets/convert_0ad_anim.py`` from anywhere ---------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.assets import convert_0ad, parse_psa, read_psa_content  # noqa: E402

# --------------------------------------------------------------------------- #
# clip catalogue
# --------------------------------------------------------------------------- #
# Paths below are exact entries inside public.zip, discovered by listing the
# archive (``python -c "..."`` over ``zf.namelist()``) and then confirmed by
# parsing each header.  Do not guess: re-list before changing.
CLIPS_BIPED = {
    "walk": "art/animation/biped/citizen/walk_relax_m.dae.cached.psa",
    "run": "art/animation/biped/citizen/run.dae.cached.psa",
    "idle": "art/animation/biped/citizen/idle_relax_m.dae.cached.psa",
    "attack_melee": ("art/animation/biped/infantry/swordsman/"
                     "attack_melee_shield_01.dae.cached.psa"),
    "build": "art/animation/biped/citizen/build.dae.cached.psa",
    "death": "art/animation/biped/infantry/death_a.dae.cached.psa",
}

CLIPS_HORSE = {
    "walk": "art/animation/quadraped/horse_walk.dae.cached.psa",
    "trot": "art/animation/quadraped/horse_trot.dae.cached.psa",
    "gallop": "art/animation/quadraped/horse_gallop.dae.cached.psa",
    "idle": "art/animation/quadraped/horse_idle_01.dae.cached.psa",
    "attack_melee": "art/animation/quadraped/horse_attack_01.dae.cached.psa",
    "death": "art/animation/quadraped/horse_death.dae.cached.psa",
}

SKELETON_XML = {
    "biped": convert_0ad.SKELETON_BIPED,   # art/skeletons/biped.xml  -> 46 bones
    "horse": convert_0ad.SKELETON_HORSE,   # art/skeletons/horse.xml  -> 49 bones
}

# Guard rails for the locked layout: a mismatch means the archive changed under us.
EXPECTED_BONES = {"biped": 46, "horse": 49}

# unit -> (skeleton key, clip table).  Infantry/archer/villager/spearman all ride
# the biped skeleton and therefore share the biped clip set; the cavalry file bakes
# the MOUNT's horse clips (the manifest's cavalry pieces are the horse's).
UNITS = {
    "medieval_infantry": ("biped", CLIPS_BIPED),
    "medieval_archer": ("biped", CLIPS_BIPED),
    "medieval_villager": ("biped", CLIPS_BIPED),
    "medieval_spearman": ("biped", CLIPS_BIPED),
    "medieval_cavalry": ("horse", CLIPS_HORSE),
}

DEFAULT_MANIFEST = _REPO_ROOT / "tools" / "assets" / "0ad-manifest.json"
DEFAULT_OUT_DIR = _REPO_ROOT / "scripts" / "animdata"

# <!-- generated by tools/assets/convert_0ad_anim.py --> banner every file carries.
BANNER = "0 A.D. world-pose animation bake -- phase 7 slice 11"

# Lua numerals: ``123``, ``1.5``, ``.5``, ``1e-05``, ``-0.0``.  ``inf``/``nan`` never
# pass, so a degenerate key can never smuggle a non-numeral into generated Lua.
_LUA_NUMBER = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


class BakeError(Exception):
    """Raised when the archive, the skeleton or the manifest contradicts the bake."""


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #
def format_number(value: float) -> str:
    """Shortest decimal that round-trips the ORIGINAL double (lossless), as Lua.

    ``repr`` of a float is the shortest string that re-parses to the identical
    double, so no precision is dropped.  Negative zero is collapsed to ``0.0``:
    it is numerically identical and keeps the emitted text canonical.
    """
    number = float(value)
    if not math.isfinite(number):
        raise BakeError(f"refusing to bake non-finite value {value!r}")
    if number == 0.0:
        return "0.0"
    text = repr(number)
    if not _LUA_NUMBER.match(text):
        text = f"{number:.17g}"
        if not _LUA_NUMBER.match(text):
            raise BakeError(f"cannot express {value!r} as a Lua numeral")
    return text


def clean_fps(fps: float) -> float:
    """Snap the f32 frameTime drift out of a frame rate.

    ``frameTime`` is stored as f32 milliseconds, so an authored 30 fps round-trips
    as 33.33333206176758 ms and ``1000 / frameTime`` lands on 30.00000114440922.
    Rounding to a microhertz keeps the authored rate without inventing precision.
    """
    if not math.isfinite(fps):
        raise BakeError(f"non-finite frame rate {fps!r}")
    nearest = round(float(fps))
    if abs(float(fps) - nearest) <= 1e-3:
        return float(nearest)
    return round(float(fps), 3)


def _fmt_frame(piece_names, values) -> str:
    """One frame as a single Lua line: ``{["hip"]={..},["spine"]={..}}``."""
    parts = []
    for index, name in enumerate(piece_names):
        base = index * 7
        nums = ",".join(format_number(component) for component in values[base:base + 7])
        parts.append(f'["{name}"]={{{nums}}}')
    return "{" + ",".join(parts) + "}"


# --------------------------------------------------------------------------- #
# data extraction
# --------------------------------------------------------------------------- #
def bone_piece_names(zf: zipfile.ZipFile, xml_path: str) -> list[str]:
    """``art/skeletons/<name>.xml`` bone names mapped to slice-10 piece names.

    ``parse_skeleton`` already lowercases and unifies ``_L``/``_R`` to ``_l``/``_r``;
    ``_sanitize`` is what :func:`convert_0ad.split_skinned_mesh` applies before the
    name becomes an OBJ ``o`` group, so the round trip is identical.
    """
    names = convert_0ad.parse_skeleton(zf, xml_path)
    return [convert_0ad._sanitize(name) for name in names]


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise BakeError(f"manifest not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def unit_piece_names(manifest: dict, unit: str) -> list[str]:
    """The piece names ``convert_0ad`` actually emitted for ``unit``, in order."""
    units = manifest.get("units", {})
    if unit not in units:
        raise BakeError(f"manifest has no unit {unit!r}")
    pieces = units[unit].get("pieces") or []
    if not pieces:
        raise BakeError(f"manifest unit {unit!r} lists no pieces")
    return list(pieces)


def bake_clip(
    zf: zipfile.ZipFile,
    entry: str,
    bone_pieces: list[str],
    keep: set[str] | None,
    scale: float,
) -> dict:
    """Bake one PSA entry into ``{"fps": ..., "frames": [ [float x 7 x bones] ]}``."""
    try:
        raw = zf.read(entry)
    except KeyError:
        # Suffix match, so a clip moved to another nation folder still resolves.
        resolved = parse_psa.resolve_entry(zf, entry)
        raw = zf.read(resolved)
        entry = resolved
    anim = parse_psa.parse_psa(raw, entry)

    if len(bone_pieces) != anim.num_keys:
        raise BakeError(
            f"{entry}: {anim.num_keys} keys but the skeleton names "
            f"{len(bone_pieces)} bones"
        )

    # bone index -> emitted piece name (or None when the hull has no such piece)
    selected = []
    for bone, name in enumerate(bone_pieces):
        if keep is None or name in keep:
            selected.append((bone, name))

    duplicated = len({name for _, name in selected}) != len(selected)
    if duplicated:
        raise BakeError(f"{entry}: piece names collide after normalisation")

    frames = []
    for frame in range(anim.num_frames):
        values = []
        for bone, _name in selected:
            key = anim.key(frame, bone)
            values.extend(read_psa_content.world_pose(key, scale))
        frames.append(values)

    return {
        "entry": entry,
        "fps": clean_fps(anim.fps),
        "num_frames": anim.num_frames,
        "num_keys": anim.num_keys,
        "piece_names": [name for _, name in selected],
        "frames": frames,
    }


def bake_unit(
    zf: zipfile.ZipFile,
    unit: str,
    manifest: dict,
    scale: float = convert_0ad.SCALE,
) -> dict:
    """Bake every clip of ``unit``, filtered to the pieces its model really owns."""
    skeleton, clips = UNITS[unit]
    xml_path = SKELETON_XML[skeleton]
    bone_pieces = bone_piece_names(zf, xml_path)

    expected = EXPECTED_BONES[skeleton]
    if len(bone_pieces) != expected:
        raise BakeError(
            f"{xml_path}: {len(bone_pieces)} bones, expected {expected}"
        )

    keep = set(unit_piece_names(manifest, unit))
    baked = {clip: bake_clip(zf, entry, bone_pieces, keep, scale)
             for clip, entry in clips.items()}
    return {"unit": unit, "skeleton": skeleton, "xml": xml_path, "clips": baked}


# --------------------------------------------------------------------------- #
# Lua emission
# --------------------------------------------------------------------------- #
def render_lua(baked: dict) -> str:
    """Render one unit's bake as a compact, loadable Lua module."""
    lines = [
        f"-- {BANNER}",
        "-- License: CC-BY-SA 3.0 (Wildfire Games, 0 A.D. Empires Ascendant; see licenses/0ad-art.txt)",
        "-- Generated by tools/assets/convert_0ad_anim.py -- do not edit by hand.",
        f"-- unit: {baked['unit']}   skeleton: {baked['xml']}",
        "-- Format: clip = { fps = <frames per second>,"
        " frames = { { [piece] = { tx,ty,tz,qx,qy,qz,qw }, ... }, ... } }",
        "-- One generated line per frame; bones follow the skeleton's document order.",
        "-- Clip sources:",
    ]
    for clip, data in baked["clips"].items():
        lines.append(f"--   {clip:<13} <- {data['entry']}"
                     f"  ({data['num_frames']} frames @ {data['fps']:g} fps,"
                     f" {len(data['piece_names'])} pieces)")
    lines.append("return {")

    for clip, data in baked["clips"].items():
        fps = data["fps"]
        fps_text = str(int(round(fps))) if float(fps).is_integer() else format_number(fps)
        lines.append(f'["{clip}"]={{fps={fps_text},frames={{')
        for values in data["frames"]:
            lines.append(_fmt_frame(data["piece_names"], values) + ",")
        lines.append("}},")

    lines.append("}")
    return "\n".join(lines) + "\n"


def write_unit(baked: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{baked['unit']}.lua"
    path.write_text(render_lua(baked), encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def generate(
    archive: Path = parse_psa.DEFAULT_ZIP,
    manifest_path: Path = DEFAULT_MANIFEST,
    out_dir: Path = DEFAULT_OUT_DIR,
    units=None,
) -> list:
    """Bake and write every requested unit; returns the written paths."""
    if not archive.is_file():
        raise BakeError(f"0 A.D. archive not found: {archive}")
    manifest = load_manifest(manifest_path)
    written = []
    with zipfile.ZipFile(archive) as zf:
        for unit in (units or list(UNITS)):
            baked = bake_unit(zf, unit, manifest)
            written.append(write_unit(baked, out_dir))
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, default=parse_psa.DEFAULT_ZIP,
                        help="0 A.D. public.zip holding the *.dae.cached.psa clips")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--unit", action="append", dest="units",
                        help="bake only this unit (repeatable)")
    args = parser.parse_args(argv)

    if not args.archive.is_file():
        print(f"archive not found: {args.archive}", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    print(f"archive  : {args.archive}")
    print(f"manifest : {args.manifest}")

    with zipfile.ZipFile(args.archive) as zf:
        for unit in (args.units or list(UNITS)):
            baked = bake_unit(zf, unit, manifest)
            path = write_unit(baked, args.out_dir)
            pieces = None
            for data in baked["clips"].values():
                pieces = data["piece_names"]
            print(f"\n{unit}  [{baked['skeleton']}] -> {path}")
            print(f"  pieces ({len(pieces)}): {', '.join(pieces)}")
            for clip, data in baked["clips"].items():
                print(f"  {clip:<13} {data['num_frames']:>4} frames"
                      f"  {data['fps']:g} fps  <- {data['entry']}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BakeError as exc:
        print(f"bake failed: {exc}", file=sys.stderr)
        sys.exit(1)