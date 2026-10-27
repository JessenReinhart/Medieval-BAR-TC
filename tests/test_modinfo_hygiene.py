"""Hygiene tests for mod metadata and documentation freshness.

Verifies:
- modinfo.lua declares version "0.7.0" and not the stale "0.2.0-phase2"
- modinfo.lua has all required keys: name, shortName, version, description,
  author, license, game
- README.md has no stale test-count references ("1620 tests", "1114 tests",
  "1195 tests")
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODINFO_PATH = ROOT / "modinfo.lua"
README_PATH = ROOT / "README.md"

REQUIRED_KEYS = ("name", "shortName", "version", "description", "author", "license", "game")
STALE_TEST_COUNTS = ("1620 tests", "1114 tests", "1195 tests")


def _load_modinfo_source() -> str:
    assert MODINFO_PATH.is_file(), f"Missing {MODINFO_PATH}"
    return MODINFO_PATH.read_text(encoding="utf-8")


def _get_modinfo_field(src: str, field: str) -> object:
    import re

    m = re.search(rf'^\s*{re.escape(field)}\s*=\s*(.*?),?$', src, re.MULTILINE)
    return m.group(1) if m else None


def _get_modinfo_with_lupa() -> dict:
    try:
        from lupa import LuaRuntime
    except ImportError:
        return {}

    lua = LuaRuntime(unpack_returned_tuples=True)
    result = lua.execute(MODINFO_PATH.read_text(encoding="utf-8"))
    data = {}
    for key in REQUIRED_KEYS + ("version",):
        try:
            value = result[key]
        except Exception:
            value = None
        data[key] = value
    return data


class TestModinfoVersion:
    def test_version_is_0_7_0_with_lupa(self):
        data = _get_modinfo_with_lupa()
        if data:
            assert data["version"] == "0.7.0", f'Expected version "0.7.0", got {data["version"]!r}'
        else:
            src = _load_modinfo_source()
            assert 'version = "0.7.0"' in src

    def test_version_is_0_7_0_regex(self):
        src = _load_modinfo_source()
        raw = _get_modinfo_field(src, "version")
        assert raw is not None, "Missing version field in modinfo.lua"
        assert 'version = "0.7.0"' in raw or raw == '"0.7.0"'

    def test_version_not_stale(self):
        src = _load_modinfo_source()
        assert "0.2.0-phase2" not in src, "modinfo.lua still contains stale version 0.2.0-phase2"

    def test_no_stale_version_string_anywhere(self):
        src = _load_modinfo_source()
        assert '"0.2.0-phase2"' not in src


class TestModinfoRequiredKeys:
    def test_required_keys_present(self):
        data = _get_modinfo_with_lupa()
        src = _load_modinfo_source()
        for key in REQUIRED_KEYS:
            if data:
                assert data.get(key) is not None, f"modinfo.lua missing required key: {key}"
                assert data.get(key) != "", f"modinfo.lua key {key!r} is an empty string"
            else:
                assert f"{key} =" in src, f"modinfo.lua missing required key: {key}"

    def test_name_key(self):
        data = _get_modinfo_with_lupa()
        if data:
            assert data["name"] == "Medieval BAR Total Conversion"

    def test_short_name_key(self):
        data = _get_modinfo_with_lupa()
        if data:
            assert data["shortName"] == "MedBAR"

    def test_game_key(self):
        data = _get_modinfo_with_lupa()
        if data:
            assert data["game"] == "Medieval BAR Total Conversion"


class TestReadmeFreshness:
    def test_no_stale_test_counts(self):
        readme = README_PATH.read_text(encoding="utf-8")
        for stale in STALE_TEST_COUNTS:
            assert stale not in readme, f"README.md contains stale reference: {stale!r}"
