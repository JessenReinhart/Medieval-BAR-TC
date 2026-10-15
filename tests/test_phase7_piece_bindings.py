"""Regression tests for Phase 7 piece bindings across the four medieval unit scripts.

Covers:
(3) The four medieval unit scripts bind baked idle bones without a hip/root
    fallback overwrite, and every baked idle bone whose name has a matching
    OBJ piece gets bound.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OBJECTS = ROOT / "objects3d" / "0ad"

UNITS = ["archer", "cavalry", "infantry", "villager"]


def get_obj_pieces(unit: str) -> set[str]:
    obj_path = OBJECTS / f"medieval_{unit}.obj"
    return set(
        line[2:].strip()
        for line in obj_path.read_text(errors="ignore").splitlines()
        if line.startswith("o ")
    )


def execute_unit_script(unit: str, script_src: str | None = None, player_src: str | None = None):
    if script_src is None:
        script_src = (SCRIPTS / f"medieval_{unit}.lua").read_text(encoding="utf-8")
    if player_src is None:
        player_src = (SCRIPTS / "anim_player.lua").read_text(encoding="utf-8")

    lua = LuaRuntime(unpack_returned_tuples=True)
    obj_pieces = get_obj_pieces(unit)
    lua.globals().AVAILABLE = lua.table_from({p: True for p in obj_pieces})

    animdata_src = (SCRIPTS / "animdata" / f"medieval_{unit}.lua").read_text(encoding="utf-8")
    sources = lua.table_from({
        "anim_player.lua": player_src,
        f"animdata/medieval_{unit}.lua": animdata_src,
    })
    lua.globals()._sources = sources

    lua.execute(
        """
        script = {}
        function include(path)
            local s = _sources[path]
            if not s then error("not found: " .. tostring(path)) end
            local chunk = assert(load(s, "@" .. path))
            return chunk()
        end
        function piece(...)
            local names = { ... }
            local out = {}
            for i = 1, #names do
                local n = names[i]
                if not AVAILABLE[n] then error("no piece: " .. tostring(n)) end
                out[i] = n
            end
            return table.unpack(out)
        end
        Turn = function() end
        Move = function() end
        unitID = 1
        Spring = { Echo = function() end }
        bound_calls = {}
        bound_pieces = {}
        local real_include = include
        function include(path)
            local mod = real_include(path)
            if path == "anim_player.lua" then
                local real_bind = mod.bindPiece
                mod.bindPiece = function(ctx, name, handle)
                    table.insert(bound_calls, { name = name, handle = handle })
                    bound_pieces[name] = handle
                    return real_bind(ctx, name, handle)
                end
            end
            return mod
        end
        """
    )
    lua.execute(script_src)
    calls = [(c["name"], c["handle"]) for c in lua.globals().bound_calls.values()]
    bound = dict(lua.globals().bound_pieces)
    return bound, calls


def get_matching_idle_bones(unit: str) -> set[str]:
    obj_pieces = get_obj_pieces(unit)
    lua = LuaRuntime(unpack_returned_tuples=True)
    anim_src = (SCRIPTS / "animdata" / f"medieval_{unit}.lua").read_text(encoding="utf-8")
    clips = lua.execute(anim_src)
    idle_frame = clips.idle.frames[1]
    return set(k for k in idle_frame.keys() if k in obj_pieces)


class TestPieceBindings:
    @pytest.mark.parametrize("unit", UNITS)
    def test_no_hip_or_root_fallback_overwrite(self, unit: str):
        matching_bones = get_matching_idle_bones(unit)
        bound, calls = execute_unit_script(unit)

        hip_calls = [h for n, h in calls if n == "hip"]
        root_calls = [h for n, h in calls if n == "root"]

        if "hip" in matching_bones:
            assert bound.get("hip") == "hip", f"{unit}: hip overwritten by {bound.get('hip')}"
            assert len(hip_calls) == 1, f"{unit}: hip bound multiple times: {hip_calls}"
        else:
            assert len(hip_calls) == 0, f"{unit}: unexpected hip binding: {hip_calls}"

        if "root" in matching_bones:
            assert bound.get("root") == "root", f"{unit}: root overwritten by {bound.get('root')}"
            assert len(root_calls) == 1, f"{unit}: root bound multiple times: {root_calls}"
        else:
            assert len(root_calls) == 0, f"{unit}: unexpected root binding: {root_calls}"

    @pytest.mark.parametrize("unit", UNITS)
    def test_every_matching_baked_idle_bone_is_bound(self, unit: str):
        matching_bones = get_matching_idle_bones(unit)
        bound, _calls = execute_unit_script(unit)

        missing = matching_bones - set(bound.keys())
        assert not missing, f"{unit}: matching idle bones missing from binding: {sorted(missing)}"

        for bone in matching_bones:
            assert bound[bone] == bone, f"{unit}: bone {bone} bound to {bound[bone]}, expected {bone}"
