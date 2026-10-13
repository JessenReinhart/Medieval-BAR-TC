#!/usr/bin/env python3
"""Proof: reconstruct the per-bone WORLD pose from a 0 A.D. ``*.dae.cached.psa``
skeletal animation, apply the 180-deg-Y export correction, and print a table.

This is the math that ``CSkeletonAnimDef::BuildBoneMatrices`` performs at render
time, run independently of the Spring/Recoil engine, on the real shipped data.

Source-verified semantics (see README-level comments in the report):
  * A PSA key is a ``CBoneState``: 3 x f32 translation + 4 x f32 quaternion
    (x, y, z, w).  Dense and frame-major: key(frame,bone) = keys[frame*numKeys+bone].
  * BOTH fields are ROOT-RELATIVE (world).  The COLLADA->PSA converter
    (``source/collada/PSAConvert.cpp``) samples ``joint->CalculateWorldTransform()``
    (the full parent chain) and decomposes it with ``decomp_affine``, so the
    quaternion is the accumulated WORLD rotation, not a parent-relative one and
    the translation is the world position of the bone.
  * ``CSkeletonAnimDef::BuildBoneMatrices`` rebuilds the world matrix WITHOUT any
    parent accumulation::

        matrices[i] = QuatToMatrix(q_i)   // 3x3 = q_i
        matrices[i].Translate(t_i)        // [ R_i | t_i ]

    so ``M_i = [ R_i | t_i ]`` where R_i = q_i and t_i is world position.

  * The OBJ export (``tools/assets/convert_0ad.py``) already applied a uniform
    yaw of 180deg about Y (x -> -x, z -> -z) plus uniform scale=8.  To make the
    animated pose land on the same mesh, apply the SAME rigid transform to the
    world pose::

        t' = R_y180 * t            == (-t.x,  t.y, -t.z)
        q' = Q_y180 ** q           ==  Q_y180 (left) x q,  Q_y180 = (0,1,0,0)

    (left-multiply because it is a GLOBAL world rotation applied to every bone's
    already-world rotation).  The uniform scale=8 is a single extra multiply on
    translation only -- pass --scale 8.0 to fold it in.

Stdlib only: zipfile + struct + math + xml.etree.  No Spring/Recoil runtime.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# --- allow ``python tools/assets/read_psa_content.py`` from anywhere ---------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.assets import parse_psa  # noqa: E402


# --------------------------------------------------------------------------- #
# quaternion maths (Hamilton (x,y,z,w), right-handed; matches 0 A.D. CQuaternion)
# --------------------------------------------------------------------------- #
def _q_mul(a: tuple, b: tuple) -> tuple:
    """Hamilton product a ⊗ b for quaternions given as (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _q_norm(q: tuple) -> tuple:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0.0:
        return q
    return tuple(c / n for c in q)


_Q_Y180 = (0.0, 1.0, 0.0, 0.0)  # 180 deg about Y


def world_pose(key: "parse_psa.Key", scale: float = 1.0):
    """Return (world_x, world_y, world_z, qx, qy, qz, qw) for one key.

    The key is already world space (root-relative translation + world rotation).
    We left-multiply the rotation by Q_y180 and rotate the translation by the
    same 180-deg-Y, mirroring the OBJ export yaw.  ``scale`` folds in the OBJ's
    uniform export scale (8.0 for Recoil), translation-only.
    """
    tx, ty, tz = key.translation
    q = _q_norm(_q_mul(_Q_Y180, key.rotation))
    return (-tx * scale, ty * scale, -tz * scale) + q


# --------------------------------------------------------------------------- #
# bone names: same rule as convert_0ad.parse_skeleton (document order of <bone>)
# --------------------------------------------------------------------------- #
def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise_bone_name(raw: str) -> str:
    return raw.replace("_L", "_l").replace("_R", "_r").lower()


def parse_skeleton_names(zf: zipfile.ZipFile, xml_path: str) -> list:
    doc = ET.fromstring(zf.read(xml_path).decode("utf-8-sig"))
    standard = next(n for n in doc.iter() if _strip_ns(n.tag) == "standard_skeleton")
    names = []
    for bone in standard.iter("bone"):
        raw = bone.get("name")
        if raw:
            names.append(_normalise_bone_name(raw))
    return names


# --------------------------------------------------------------------------- #
def print_table(anim, names, frame, tag, scale=1.0):
    qty = anim.num_keys
    print(f"\n== {tag} @ frame {frame}/{anim.num_frames} "
          f"(t={frame * anim.frame_time:.1f}ms, scale={scale:g}) ==")
    print(f"   bone_count={qty} names={len(names)}")
    best_bone = None
    for b in range(qty):
        name = names[b] if b < len(names) else f"bone[{b}]"
        key = anim.key(frame, b)
        wx, wy, wz, qx, qy, qz, qw = world_pose(key, scale)
        print(f"   {name:<14} "
              f"world=({wx: .4f}, {wy: .4f}, {wz: .4f}) "
              f"q=({qx: .6f}, {qy: .6f}, {qz: .6f}, {qw: .6f})")
        if name == "hip" or name == "spine":
            if best_bone is None:
                best_bone = (name, wy)
    return best_bone


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=parse_psa.DEFAULT_ZIP)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="uniform OBJ export scale to fold into translation (Recoil=8.0)")
    ap.add_argument("--frame0", type=int, default=0)
    ap.add_argument("--frame1", type=int, default=None,
                    help="second frame (default: numFrames//2)")
    args = ap.parse_args()

    jobs = [
        ("walk_relax_m.dae.cached.psa", "art/skeletons/biped.xml", "BIPED walk_relax_m"),
        ("horse_walk.dae.cached.psa", "art/skeletons/horse.xml", "HORSE horse_walk"),
    ]

    if not args.archive.is_file():
        print(f"archive not found: {args.archive}", file=sys.stderr)
        return 2

    with zipfile.ZipFile(args.archive) as zf:
        for wanted, xml_path, tag in jobs:
            entry = parse_psa.resolve_entry(zf, wanted)
            raw = zf.read(entry)
            print(f"\n{tag}: {entry}  ({len(raw)} bytes)")
            anim = parse_psa.parse_psa(raw, entry)

            names = parse_skeleton_names(zf, xml_path)
            if len(names) != anim.num_keys:
                print(f"   !! name count {len(names)} != numKeys {anim.num_keys}",
                      file=sys.stderr)

            f1 = args.frame1 if args.frame1 is not None else anim.num_frames // 2
            hi0 = print_table(anim, names, args.frame0, tag, args.scale)
            hi1 = print_table(anim, names, f1, tag, args.scale)
            if hi0:
                print(f"   [sanity] {hi0[0]} world_y @ frame0 = {hi0[1]:.4f} "
                      f"(0 A.D. world metres at scale {args.scale:g}; "
                      f"Y-180 does not touch y)")

    return 0


if __name__ == "__main__":
    sys.exit(main())