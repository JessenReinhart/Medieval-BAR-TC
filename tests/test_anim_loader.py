"""Phase 7 slice 12 regression: the baked-clip loader must use the unit-script
include() API, not VFS.Include.

The original loader read ``_G["VFS"]`` / ``vfs["Include"]``, which returns an
unexecuted chunk in the wrong environment inside a unit script, so ``animCtx``
stayed nil and the procedural loops silently took over. This module locks in:

1. every unit script binds ``include`` (``local inc = include``) and no longer
   references VFS in executable code;
2. every unit script carries the one-time per-unit init diagnostic; and
3. the loader's path contract -- ``include(relpath)`` where ``relpath`` is
   scripts/-relative -- returns a real Lua table for both ``anim_player.lua``
   and each ``animdata/*.lua`` module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

UNIT_SCRIPTS = [
    SCRIPTS / "medieval_infantry.lua",
    SCRIPTS / "medieval_archer.lua",
    SCRIPTS / "medieval_villager.lua",
    SCRIPTS / "medieval_cavalry.lua",
]

ANIMDATA = {
    "medieval_infantry": "medieval_infantry.lua",
    "medieval_archer": "medieval_archer.lua",
    "medieval_villager": "medieval_villager.lua",
    "medieval_cavalry": "medieval_cavalry.lua",
}


def _code_only(source: str) -> str:
    """Strip Lua comments and string literals, leaving executable tokens only."""
    source = re.sub(r"--\[\[.*?\]\]", " ", source, flags=re.S)
    source = re.sub(r"--[^\n]*", " ", source)
    source = re.sub(r'"(?:\\.|[^"\\])*"', '""', source)
    source = re.sub(r"'(?:\\.|[^'\\])*'", "''", source)
    return source


# --------------------------------------------------------------------------- #
# Loader uses include(), not VFS
# --------------------------------------------------------------------------- #
class TestLoaderUsesInclude:
    @pytest.mark.parametrize("path", UNIT_SCRIPTS, ids=lambda p: p.name)
    def test_loader_binds_include(self, path: Path):
        code = _code_only(path.read_text(encoding="utf-8"))
        assert re.search(r"local\s+inc\s*=\s*include", code), (
            f"{path.name} does not bind the unit-script include()"
        )

    @pytest.mark.parametrize("path", UNIT_SCRIPTS, ids=lambda p: p.name)
    def test_loader_rejects_vfs(self, path: Path):
        code = _code_only(path.read_text(encoding="utf-8"))
        for bad in (
            '_G["VFS"]',
            "_G['VFS']",
            'vfs["Include"]',
            "vfs['Include']",
            "VFS.Include",
        ):
            assert bad not in code, f"{path.name} still reaches for VFS ({bad!r})"

    @pytest.mark.parametrize("path", UNIT_SCRIPTS, ids=lambda p: p.name)
    def test_init_diagnostic_present(self, path: Path):
        src = path.read_text(encoding="utf-8")
        assert "MEDIEVAL ANIM baked init" in src, (
            f"{path.name} missing success diagnostic"
        )
        assert "MEDIEVAL ANIM fallback" in src, (
            f"{path.name} missing fallback diagnostic"
        )


# --------------------------------------------------------------------------- #
# The include(path) contract, exercised with the real files
# --------------------------------------------------------------------------- #
class TestIncludeContract:
    """loadModule strips a leading ``scripts/`` prefix and calls
    ``include(relpath)``; include() then loads ``scripts/<relpath>`` and returns
    the chunk's return value. This proves both modules come back as tables under
    the exact path contract the loader relies on.
    """

    @staticmethod
    def _include_lua() -> LuaRuntime:
        lua = LuaRuntime(unpack_returned_tuples=True)
        sources = lua.table()
        sources["anim_player.lua"] = (SCRIPTS / "anim_player.lua").read_text(
            encoding="utf-8"
        )
        for _unit, filename in ANIMDATA.items():
            sources[f"animdata/{filename}"] = (
                SCRIPTS / "animdata" / filename
            ).read_text(encoding="utf-8")
        lua.globals()._sources = sources
        lua.execute(
            """
            function include(path)
              local src = _sources[path]
              if not src then return nil end
              local chunk, err = load(src, "@" .. path)
              if not chunk then error(err, 0) end
              return chunk()
            end
            """
        )
        return lua

    def test_anim_player_loads_as_table(self):
        lua = self._include_lua()
        lua.execute("player = include('anim_player.lua')")
        assert lua.eval("type(player) == 'table'"), "anim_player.lua not a table"
        for name in (
            "new",
            "setClips",
            "setPrimitives",
            "setSpeed",
            "bindPiece",
            "bindRest",
            "emit",
            "step",
            "sample",
            "elapsed",
        ):
            assert lua.eval(f"player.{name} ~= nil"), f"anim_player.{name} missing"

    @pytest.mark.parametrize("unit", sorted(ANIMDATA), ids=lambda u: u)
    def test_animdata_loads_with_expected_clips(self, unit: str):
        lua = self._include_lua()
        lua.execute(f"clips = include('animdata/{ANIMDATA[unit]}')")
        assert lua.eval("type(clips) == 'table'"), f"{unit} animdata not a table"
        assert lua.eval("clips.idle ~= nil"), f"{unit} animdata missing idle clip"
        assert lua.eval(
            "clips.idle.frames ~= nil"
        ), f"{unit} animdata idle clip missing frames"
        lua.execute("_n = 0; for _ in pairs(clips) do _n = _n + 1 end")
        n = lua.globals()._n
        assert n == 6, f"{unit} animdata has {n} clips, expected 6"