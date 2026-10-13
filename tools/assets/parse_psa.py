#!/usr/bin/env python3
"""Reader for 0 A.D. cached skeletal animation files (``*.dae.cached.psa``).

Pure standard library (zipfile + struct + math).  No external dependencies.

FORMAT (reverse engineered from the shipped game data, cross-checked against
``source/graphics/SkeletonAnimDef.cpp`` and ``source/ps/FileIo.cpp`` of 0ad/0ad)

All integers are little-endian.  The container header comes from
``CFileUnpacker``/``CFilePacker`` (``source/ps/FileIo.cpp``)::

    struct FileHeader {
        char magic[4];      // "PSSA"
        u32  version;       // CSkeletonAnimDef::FILE_VERSION == 1
        u32  payloadSize;   // bytes that follow this 12-byte header
    };

The payload written by ``CSkeletonAnimDef::Save`` is::

    PackString("")         -> u32 length, then `length` raw bytes
                              (legacy field, ALWAYS empty in shipped data)
    PackRaw(&m_FrameTime)  -> f32  frame time in milliseconds (33.3333 == 30 fps)
    PackSize(m_NumKeys)    -> u32  keys per frame == number of skeleton bones
    PackSize(m_NumFrames)  -> u32  number of frames
    PackRaw(m_Keys)        -> m_NumKeys * m_NumFrames raw key records

A key record is ``CBoneState`` (``source/graphics/SkeletonAnimDef.h``)::

    struct CBoneState {          // 28 bytes, no padding
        CVector3D   m_Translation;   // 3 x f32: tx, ty, tz
        CQuaternion m_Rotation;      // CVector3D m_V + f32 m_W
                                     // => rx, ry, rz, rw  (x,y,z,w order!)
    };

Notes / documented findings
---------------------------
* Magic is ``PSSA`` (not ``PSA``); version 1 is the only version in game data.
* Keys are DENSE: every bone has a key in every frame, stored frame-major,
  i.e. ``key(frame, bone) == keys[frame * numKeys + bone]``.
* There is NO scale channel and NO bone hierarchy in the file: the record is
  translation + quaternion only.  BOTH are ROOT-RELATIVE (world space): the
  FK parent-chain accumulation happens at COLLADA->PSA import time in
  ``source/collada/PSAConvert.cpp`` (``joint->CalculateWorldTransform()`` +
  ``decomp_affine``), so ``BuildBoneMatrices`` rebuilds each bone's world
  matrix ``[R | t]`` with no parent loop -- the quaternion is the WORLD
  rotation, not a parent-relative one.
* Bone names are NOT stored in ``.psa`` (nor in the sibling ``.pmd``, whose
  bones are raw bind-pose ``CBoneState`` records).  The single string in the
  payload is the legacy always-empty animation name.  Real bone names only
  exist in the original COLLADA (``.dae``) sources, which are not shipped in
  ``public.zip``; synthetic labels ``bone[NNN]`` are used unless ``--names``
  supplies a list.

Usage
-----
    python tools/assets/parse_psa.py --list --grep citizen/walk
    python tools/assets/parse_psa.py --entry art/animation/biped/citizen/walk_relax_m.dae.cached.psa
    python tools/assets/parse_psa.py --entry walk_relax_m --frames 0 --json
    python tools/assets/parse_psa.py --check-all
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"PSSA"
EXPECTED_VERSION = 1
HEADER_SIZE = 12        # magic(4) + version(4) + payloadSize(4)
KEY_SIZE = 28           # 7 x f32
FLOATS_PER_KEY = 7
DEFAULT_ZIP = (
    Path.home()
    / "AppData/Local/0 A.D. Empires Ascendant/binaries/data/mods/public/public.zip"
)


class PSAParseError(Exception):
    """Raised when an entry is not a well-formed PSSA animation."""


# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Key:
    """One bone state: translation (x,y,z) + rotation quaternion (x,y,z,w)."""

    tx: float
    ty: float
    tz: float
    rx: float
    ry: float
    rz: float
    rw: float

    @property
    def translation(self) -> tuple[float, float, float]:
        return (self.tx, self.ty, self.tz)

    @property
    def rotation(self) -> tuple[float, float, float, float]:
        return (self.rx, self.ry, self.rz, self.rw)

    @property
    def rotation_norm(self) -> float:
        return math.sqrt(self.rx * self.rx + self.ry * self.ry
                         + self.rz * self.rz + self.rw * self.rw)


class SkeletonAnim:
    """Parsed ``.dae.cached.psa`` animation definition."""

    def __init__(
        self,
        entry: str,
        version: int,
        payload_size: int,
        name_field: str,
        frame_time: float,
        num_keys: int,
        num_frames: int,
        key_block: bytes,
    ) -> None:
        self.entry = entry
        self.version = version
        self.payload_size = payload_size
        self.name_field = name_field
        self.frame_time = frame_time          # ms per frame
        self.num_keys = num_keys              # == bone count
        self.num_frames = num_frames
        self._key_block = key_block
        self._floats = struct.unpack(
            "<%df" % (FLOATS_PER_KEY * num_keys * num_frames), key_block
        ) if num_keys and num_frames else ()

    # -- accessors ---------------------------------------------------------- #
    @property
    def bone_count(self) -> int:
        return self.num_keys

    @property
    def duration_ms(self) -> float:
        return self.num_frames * self.frame_time

    @property
    def fps(self) -> float:
        return 1000.0 / self.frame_time if self.frame_time else float("inf")

    def key(self, frame: int, bone: int) -> Key:
        if not 0 <= frame < self.num_frames:
            raise IndexError(f"frame {frame} out of range 0..{self.num_frames - 1}")
        if not 0 <= bone < self.num_keys:
            raise IndexError(f"bone {bone} out of range 0..{self.num_keys - 1}")
        i = (frame * self.num_keys + bone) * FLOATS_PER_KEY
        return Key(*self._floats[i:i + FLOATS_PER_KEY])

    def keys_of_bone(self, bone: int, frames: int | None = None):
        limit = self.num_frames if frames in (None, 0) else min(frames, self.num_frames)
        return [(f, self.key(f, bone)) for f in range(limit)]

    # -- diagnostics -------------------------------------------------------- #
    def key_stats(self) -> dict:
        """Quaternion-normalisation and translation-extent sanity check."""
        if not self._floats:
            return {}
        norms = []
        mins = [math.inf] * 3
        maxs = [-math.inf] * 3
        for i in range(0, len(self._floats), FLOATS_PER_KEY):
            tx, ty, tz, rx, ry, rz, rw = self._floats[i:i + FLOATS_PER_KEY]
            norms.append(math.sqrt(rx * rx + ry * ry + rz * rz + rw * rw))
            for axis, value in enumerate((tx, ty, tz)):
                mins[axis] = min(mins[axis], value)
                maxs[axis] = max(maxs[axis], value)
        return {
            "quat_norm_min": min(norms),
            "quat_norm_max": max(norms),
            "quat_norm_mean": sum(norms) / len(norms),
            "translation_min": tuple(mins),
            "translation_max": tuple(maxs),
        }


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def parse_psa(data: bytes, entry: str = "<memory>") -> SkeletonAnim:
    """Parse raw ``.dae.cached.psa`` bytes into a :class:`SkeletonAnim`."""
    if len(data) < HEADER_SIZE:
        raise PSAParseError(f"{entry}: truncated file ({len(data)} bytes)")

    magic = data[:4]
    if magic != MAGIC:
        raise PSAParseError(
            f"{entry}: bad magic {magic!r} (expected {MAGIC!r})"
        )

    version, payload_size = struct.unpack_from("<II", data, 4)
    if version < EXPECTED_VERSION:
        raise PSAParseError(f"{entry}: unsupported version {version}")
    if payload_size != len(data) - HEADER_SIZE:
        raise PSAParseError(
            f"{entry}: header payloadSize {payload_size} != "
            f"file size - {HEADER_SIZE} ({len(data) - HEADER_SIZE})"
        )

    off = HEADER_SIZE
    (name_len,) = struct.unpack_from("<I", data, off)
    off += 4
    if off + name_len > len(data):
        raise PSAParseError(f"{entry}: name string overruns file")
    name_field = data[off:off + name_len].decode("utf-8", "replace")
    off += name_len

    if off + 12 > len(data):
        raise PSAParseError(f"{entry}: truncated payload header")
    (frame_time,) = struct.unpack_from("<f", data, off)
    off += 4
    num_keys, num_frames = struct.unpack_from("<II", data, off)
    off += 8

    expected = off + num_keys * num_frames * KEY_SIZE
    if expected != len(data):
        raise PSAParseError(
            f"{entry}: key block size mismatch - expected {expected} bytes "
            f"({num_keys} keys x {num_frames} frames x {KEY_SIZE}), file has {len(data)}"
        )

    return SkeletonAnim(
        entry=entry,
        version=version,
        payload_size=payload_size,
        name_field=name_field,
        frame_time=frame_time,
        num_keys=num_keys,
        num_frames=num_frames,
        key_block=data[off:expected],
    )


def open_archive(path: Path) -> zipfile.ZipFile:
    if not path.is_file():
        raise SystemExit(f"archive not found: {path}")
    return zipfile.ZipFile(path)


def list_entries(zf: zipfile.ZipFile) -> list[str]:
    return [n for n in zf.namelist() if n.endswith(".dae.cached.psa")]


def resolve_entry(zf: zipfile.ZipFile, wanted: str) -> str:
    """Exact name, else unique suffix match, else a helpful error."""
    names = list_entries(zf)
    if wanted in names:
        return wanted
    canon = wanted.replace("\\", "/").lstrip("/")
    hits = [n for n in names if n == canon or n.endswith("/" + canon)
            or Path(n).name == Path(canon).name]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(
            f"ambiguous entry {wanted!r}; candidates:\n  " + "\n  ".join(hits[:10])
        )
    close = difflib.get_close_matches(canon, names, n=5, cutoff=0.6)
    hint = ("\n  did you mean:\n    " + "\n    ".join(close)) if close else ""
    raise SystemExit(f"entry not found in archive: {wanted}{hint}")


def check_all(zf: zipfile.ZipFile, verbose: bool = False) -> int:
    """Validate every entry's header; returns the number of failures."""
    names = list_entries(zf)
    bad = 0
    bones_seen: dict[int, int] = {}
    for name in names:
        info = zf.getinfo(name)
        with zf.open(name) as fh:
            head = fh.read(HEADER_SIZE)
        try:
            if head[:4] != MAGIC:
                raise PSAParseError(f"bad magic {head[:4]!r}")
            version, payload_size = struct.unpack_from("<II", head, 4)
            if version != EXPECTED_VERSION:
                raise PSAParseError(f"version {version}")
            if payload_size != info.file_size - HEADER_SIZE:
                raise PSAParseError(
                    f"payloadSize {payload_size} != {info.file_size - HEADER_SIZE}"
                )
        except PSAParseError as exc:
            bad += 1
            print(f"FAIL {name}: {exc}")
            continue
        if verbose:
            print(f"ok   {name}  {info.file_size} bytes")
    print(f"\nchecked {len(names)} .dae.cached.psa entries, {bad} failed")
    return bad


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def bone_labels(anim: SkeletonAnim, names: list[str] | None) -> list[str]:
    width = max(3, len(str(anim.num_keys - 1)))
    out = []
    for i in range(anim.num_keys):
        if names and i < len(names):
            out.append(names[i])
        else:
            out.append(f"bone[{i:0{width}d}]")
    return out


def format_anim(anim: SkeletonAnim, bones: int, frames: int,
                names: list[str] | None) -> str:
    stats = anim.key_stats()
    labels = bone_labels(anim, names)
    total = anim.num_keys * anim.num_frames
    lines = [
        f"entry            : {anim.entry}",
        f"magic            : {MAGIC.decode()}",
        f"version          : {anim.version}",
        f"payload size     : {anim.payload_size} bytes (file size - {HEADER_SIZE})",
        f"name field       : {anim.name_field!r} (legacy PackString; bone names are"
        " NOT stored in .psa/.pmd)",
        f"frame time       : {anim.frame_time:.4f} ms  ({anim.fps:.2f} fps)",
        f"bone count       : {anim.num_keys}",
        f"frame count      : {anim.num_frames}",
        f"duration         : {anim.duration_ms:.2f} ms",
        f"keys             : {anim.num_keys} bones x {anim.num_frames} frames = "
        f"{total} records x {KEY_SIZE} bytes = {total * KEY_SIZE} bytes",
        "key layout       : dense, frame-major  key(frame,bone) = "
        "keys[frame*numKeys + bone]",
        "key record       : <f32 tx, ty, tz  |  f32 rx, ry, rz, rw>  "
        "(translation xyz, rotation quaternion xyzw, no scale)",
        f"bone labels      : {labels[0]} .. {labels[-1]}"
        + ("  (from --names)" if names else "  (synthetic)"),
    ]
    if stats:
        lines.append(
            "sanity           : |q| in [{:.6f}, {:.6f}] mean {:.6f}; "
            "translation bbox [{:.4f}, {:.4f}] x [{:.4f}, {:.4f}] x [{:.4f}, {:.4f}]".format(
                stats["quat_norm_min"], stats["quat_norm_max"], stats["quat_norm_mean"],
                stats["translation_min"][0], stats["translation_max"][0],
                stats["translation_min"][1], stats["translation_max"][1],
                stats["translation_min"][2], stats["translation_max"][2],
            )
        )

    shown_bones = min(bones, anim.num_keys)
    shown_frames = anim.num_frames if frames in (None, 0) else min(frames, anim.num_frames)
    lines.append("")
    lines.append(
        f"--- first {shown_bones} bone(s), frames 0..{shown_frames - 1} "
        f"of {anim.num_frames} ---"
    )
    for bone in range(shown_bones):
        lines.append(f"{labels[bone]}:")
        for frame, key in anim.keys_of_bone(bone, shown_frames):
            lines.append(
                "  frame {:>4}  t=({: .6f},{: .6f},{: .6f})  "
                "q=({: .6f},{: .6f},{: .6f},{: .6f})  |q|={:.6f}".format(
                    frame, *key.translation, *key.rotation, key.rotation_norm
                )
            )
        if shown_frames < anim.num_frames:
            lines.append(
                f"  ... {anim.num_frames - shown_frames} more frames "
                "(use --frames 0 for all)"
            )
    if shown_bones < anim.num_keys:
        lines.append(f"... {anim.num_keys - shown_bones} more bones "
                     "(use --bones N for more)")
    return "\n".join(lines)


def anim_as_json(anim: SkeletonAnim, bones: int, frames: int,
                 names: list[str] | None) -> dict:
    labels = bone_labels(anim, names)
    shown = min(bones, anim.num_keys)
    shown_frames = anim.num_frames if frames in (None, 0) else min(frames, anim.num_frames)
    return {
        "entry": anim.entry,
        "magic": MAGIC.decode(),
        "version": anim.version,
        "payload_size": anim.payload_size,
        "name_field": anim.name_field,
        "frame_time_ms": anim.frame_time,
        "fps": anim.fps,
        "bone_count": anim.num_keys,
        "frame_count": anim.num_frames,
        "duration_ms": anim.duration_ms,
        "key_size": KEY_SIZE,
        "layout": "dense frame-major; key(frame,bone)=keys[frame*numKeys+bone]",
        "stats": anim.key_stats(),
        "bones": [
            {
                "index": b,
                "label": labels[b],
                "keys": [
                    {
                        "frame": f,
                        "t": list(k.translation),
                        "q_xyzw": list(k.rotation),
                    }
                    for f, k in anim.keys_of_bone(b, shown_frames)
                ],
            }
            for b in range(shown)
        ],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="parse_psa.py",
        description="Read 0 A.D. .dae.cached.psa skeletal animation files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage\n-----\n", 1)[-1],
    )
    p.add_argument("--zip", type=Path, default=DEFAULT_ZIP,
                   help=f"public.zip path (default: {DEFAULT_ZIP})")
    p.add_argument("--entry", action="append", default=[],
                   help="entry name inside the zip (exact or unique suffix); repeatable")
    p.add_argument("--list", action="store_true", help="list .dae.cached.psa entries")
    p.add_argument("--grep", help="substring filter for --list")
    p.add_argument("--limit", type=int, default=0,
                   help="max entries to list (0 = all)")
    p.add_argument("--bones", type=int, default=3,
                   help="how many bones to print (default 3)")
    p.add_argument("--frames", type=int, default=8,
                   help="how many frames per bone to print (0 = all, default 8)")
    p.add_argument("--names", type=Path,
                   help="text file with one bone name per line (PSA stores none)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--check-all", action="store_true",
                   help="validate headers of every .psa in the archive")
    p.add_argument("--verbose", action="store_true", help="per-entry output with --check-all")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    names: list[str] | None = None
    if args.names:
        names = [ln.strip() for ln in args.names.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]

    with open_archive(args.zip) as zf:
        if args.check_all:
            return 1 if check_all(zf, args.verbose) else 0

        if args.list:
            entries = list_entries(zf)
            if args.grep:
                needle = args.grep.replace("\\", "/").lower()
                entries = [n for n in entries if needle in n.lower()]
            if args.limit:
                entries = entries[:args.limit]
            for name in entries:
                print(f"{zf.getinfo(name).file_size:>9} {name}")
            print(f"# {len(entries)} entry(ies)")
            if not args.entry:
                return 0

        if not args.entry:
            build_parser().print_help()
            return 2

        for wanted in args.entry:
            name = resolve_entry(zf, wanted)
            anim = parse_psa(zf.read(name), name)
            if args.json:
                print(json.dumps(anim_as_json(anim, args.bones, args.frames, names),
                                 indent=2))
            else:
                print(format_anim(anim, args.bones, args.frames, names))
                print()
    return 0


if __name__ == "__main__":
    sys.exit(main())