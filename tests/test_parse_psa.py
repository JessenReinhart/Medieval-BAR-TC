"""Tests for tools/assets/parse_psa.py (0 A.D. .dae.cached.psa reader).

The synthetic test runs everywhere; the archive tests skip when the local
0 A.D. installation (public.zip) is not present.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "assets"))

import parse_psa as P  # noqa: E402

ARCHIVE = P.DEFAULT_ZIP
needs_archive = pytest.mark.skipif(
    not ARCHIVE.is_file(), reason=f"0 A.D. public.zip not found at {ARCHIVE}"
)


def build_pssa(frame_time=33.3333, num_keys=3, num_frames=2, name="", keys=None):
    """Serialize a minimal PSSA buffer the way CSkeletonAnimDef::Save does."""
    if keys is None:
        keys = [float(i) / 10 for i in range(P.FLOATS_PER_KEY * num_keys * num_frames)]
    payload = struct.pack("<I", len(name)) + name.encode()
    payload += struct.pack("<fII", frame_time, num_keys, num_frames)
    payload += struct.pack("<%df" % len(keys), *keys)
    return b"PSSA" + struct.pack("<II", 1, len(payload)) + payload


def test_roundtrip_header_fields():
    data = build_pssa(num_keys=4, num_frames=5)
    anim = P.parse_psa(data, "synthetic.psa")
    assert anim.version == 1
    assert anim.payload_size == len(data) - P.HEADER_SIZE
    assert anim.name_field == ""
    assert anim.bone_count == 4
    assert anim.num_frames == 5
    assert anim.frame_time == pytest.approx(33.3333, rel=1e-6)
    assert anim.duration_ms == pytest.approx(5 * 33.3333, rel=1e-6)
    assert anim.fps == pytest.approx(30.0, rel=1e-3)


def test_key_indexing_is_frame_major():
    # key(frame, bone) == keys[frame * num_keys + bone]
    floats = []
    for frame in range(3):
        for bone in range(2):
            floats += [frame * 100 + bone] * 3      # translation
            floats += [0.0, 0.0, 0.0, 1.0]          # identity quaternion xyzw
    anim = P.parse_psa(build_pssa(num_keys=2, num_frames=3, keys=floats))
    assert anim.key(0, 0).translation == (0.0, 0.0, 0.0)
    assert anim.key(0, 1).translation == (1.0, 1.0, 1.0)
    assert anim.key(2, 1).translation == (201.0, 201.0, 201.0)
    assert anim.key(1, 0).rotation == (0.0, 0.0, 0.0, 1.0)
    assert anim.key(1, 0).rotation_norm == pytest.approx(1.0)


def test_legacy_name_field_is_consumed():
    anim = P.parse_psa(build_pssa(name="legacy"))
    assert anim.name_field == "legacy"


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda d: b"PSA\x00" + d[4:], "bad magic"),
        (lambda d: d[:4] + struct.pack("<I", 0) + d[8:], "unsupported version"),
        (lambda d: d[:8] + struct.pack("<I", len(d)) + d[12:], "payloadSize"),
        # keep payloadSize honest but claim more bones than the file can hold
        (lambda d: d[:20] + struct.pack("<I", 99) + d[24:], "key block size mismatch"),
        (lambda d: d[:6], "truncated"),
    ],
)
def test_malformed_inputs_raise(mutate, match):
    with pytest.raises(P.PSAParseError, match=match):
        P.parse_psa(mutate(build_pssa()), "broken.psa")


def test_key_accessor_bounds():
    anim = P.parse_psa(build_pssa(num_keys=2, num_frames=2))
    with pytest.raises(IndexError):
        anim.key(2, 0)
    with pytest.raises(IndexError):
        anim.key(0, 2)


@needs_archive
def test_archive_resolution_and_listing():
    with P.open_archive(ARCHIVE) as zf:
        entries = P.list_entries(zf)
        assert len(entries) == 1220
        assert all(e.startswith("art/animation/") for e in entries)
        exact = "art/animation/biped/citizen/walk_relax_m.dae.cached.psa"
        assert P.resolve_entry(zf, exact) == exact
        # unique basename resolves
        assert P.resolve_entry(zf, "walk_relax_m.dae.cached.psa") == exact
        anim = P.parse_psa(zf.read(exact), exact)
        assert anim.num_keys == 46
        with pytest.raises(SystemExit):
            P.resolve_entry(zf, "art/animation/does/not/exist.dae.cached.psa")


@needs_archive
def test_every_archive_entry_parses_exactly():
    with P.open_archive(ARCHIVE) as zf:
        for name in P.list_entries(zf):
            anim = P.parse_psa(zf.read(name), name)
            assert anim.version == 1
            assert anim.bone_count > 0
            assert anim.num_frames > 0
            assert anim.frame_time == pytest.approx(33.3333, rel=1e-4)