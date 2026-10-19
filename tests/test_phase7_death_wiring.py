"""Baked death-clip wiring for every articulated medieval unit.

Covers:
1. Each articulated LUS `Killed` call-in plays the baked `death` clip (not just
   the procedural tumble) and reports `PHASE7 DEATH ... baked=1` evidence.
2. The clip actually drives Turn/Move on real model pieces in a Lua sandbox.
3. Every unitdef that uses an articulated mesh + LUS is covered by the headless
   probe gadget and its runner.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
UNITS = ROOT / "units"
OBJECTS = ROOT / "objects3d" / "0ad"
GADGET = ROOT / "luarules" / "gadgets" / "gadget_phase7_death_probe.lua"
RUNNER = ROOT / "tools" / "launch" / "run_phase7_death_probe.py"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase7_death.txt"
FALLBACK_STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase7_death_fallback.txt"

# LUS file -> bare unit name used to exercise it in the sandbox
# (`medieval_<name>` is both the OBJ stem and the unitdef name).
ARTICULATED_SCRIPTS = {
    "medieval_infantry.lua": "infantry",
    "medieval_archer.lua": "archer",
    "medieval_villager.lua": "villager",
    "medieval_cavalry.lua": "cavalry",
}


def function_body(source: str, header: str) -> str:
    start = source.index(header)
    end = source.index("\nend", start)
    return source[start:end]


def obj_pieces(unit: str) -> set[str]:
    text = (OBJECTS / f"medieval_{unit}.obj").read_text(errors="ignore")
    return {line[2:].strip() for line in text.splitlines() if line.startswith("o ")}


SANDBOX = """
script = {}
turns, moves, echoes = {}, {}, {}

local sources = {}
function setSources(t) sources = t end
function include(path)
  local src = sources[path]
  if not src then error("not found: " .. tostring(path)) end
  return assert(load(src, "@" .. path))()
end

pieces = {}
function piece(name)
  if not pieces[name] then error("no piece: " .. tostring(name)) end
  return name
end

function Turn(p, axis, value, speed) turns[#turns + 1] = { p = p, a = axis, v = value } end
function Move(p, axis, value, speed) moves[#moves + 1] = { p = p, a = axis, v = value } end

function StartThread(fn) return fn() end
function Signal() end
function SetSignalMask() end
function Sleep() end

x_axis, y_axis, z_axis = 1, 2, 3
unitID = 42
rules = {}
Spring = {
  Echo = function(msg) echoes[#echoes + 1] = msg end,
  GetUnitRulesParam = function(id, key) return rules[key] end,
}
"""


def run_killed(unit: str, force_fallback: bool = False):
    source = (SCRIPTS / f"medieval_{unit}.lua").read_text(encoding="utf-8")
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SANDBOX)

    pieces = lua.table_from({name: True for name in obj_pieces(unit)})
    lua.globals().pieces = pieces

    sources = {
        "anim_player.lua": (SCRIPTS / "anim_player.lua").read_text(encoding="utf-8"),
        f"animdata/medieval_{unit}.lua": (
            SCRIPTS / "animdata" / f"medieval_{unit}.lua"
        ).read_text(encoding="utf-8"),
    }
    lua.globals().setSources(lua.table_from(sources))
    lua.execute(source)
    if force_fallback:
        lua.execute("rules['medieval_force_procedural_death'] = 1")

    result = lua.eval("script.Killed(500, 100)")
    return lua, result


@pytest.mark.parametrize("script_name", sorted(ARTICULATED_SCRIPTS))
class TestDeathCallInContract:
    def test_killed_plays_the_baked_death_clip_before_the_fallback(self, script_name):
        source = (SCRIPTS / script_name).read_text(encoding="utf-8")
        body = function_body(source, "function script.Killed(")

        baked = body.index('driveClip("death"')
        assert "if animCtx and not forceProceduralFallback() then" in body[:baked], (
            f"{script_name}: the death clip must be the primary path inside `if animCtx`"
        )
        # The procedural tumble follows the baked branch.
        fallback = body.index("safeCall(Turn")
        assert baked < fallback, (
            f"{script_name}: the baked death clip must run before the procedural fallback"
        )
        assert "return 1" in body

    def test_killed_reports_baked_and_fallback_evidence(self, script_name):
        source = (SCRIPTS / script_name).read_text(encoding="utf-8")
        body = function_body(source, "function script.Killed(")
        assert "PHASE7 DEATH" in body
        assert "baked=1" in body and "driven=" in body
        assert "baked=0" in body
        # The script stays a pure LUS: no unit-def / gadget side channels.
        for token in ("UnitDefs", "GG.", "VFS.", "gadgetHandler"):
            assert token not in source, f"{script_name} must stay pure LUS ({token})"


@pytest.mark.parametrize("script_name", sorted(ARTICULATED_SCRIPTS))
class TestBakedDeathPlayback:
    def test_death_clip_drives_real_pieces(self, script_name):
        unit = ARTICULATED_SCRIPTS[script_name]
        lua, result = run_killed(unit)

        assert result == 1, "Killed must return the wreck level to the engine"

        turns = lua.globals().turns
        moves = lua.globals().moves
        assert len(turns) > 0, f"{unit}: the baked death clip drove no Turn calls"
        assert len(moves) > 0, f"{unit}: the baked death clip drove no Move calls"

        driven_pieces = {turns[i].p for i in range(1, len(turns) + 1)}
        assert len(driven_pieces) > 3, (
            f"{unit}: death animation must move a whole-body rig, got {driven_pieces}"
        )
        assert any(abs(turns[i].v) > 1e-6 for i in range(1, len(turns) + 1)), (
            f"{unit}: every death Turn was zero (rest pose, clip not sampled)"
        )
        assert any(abs(moves[i].v) > 1e-6 for i in range(1, len(moves) + 1)), (
            f"{unit}: every death Move was zero (pivot term not emitted)"
        )

    def test_forced_fallback_skips_the_bake(self, script_name):
        unit = ARTICULATED_SCRIPTS[script_name]
        lua, result = run_killed(unit, force_fallback=True)

        assert result == 1, "the procedural fallback must still return the wreck level"
        echoes = [lua.globals().echoes[i] for i in range(1, len(lua.globals().echoes) + 1)]
        death_lines = [line for line in echoes if line.startswith("PHASE7 DEATH ")]
        assert death_lines, f"{unit}: fallback emitted no PHASE7 DEATH evidence"
        assert all("baked=0" in line for line in death_lines), (
            f"{unit}: forced fallback still reported a baked clip"
        )
        assert not any("baked=1" in line for line in death_lines)

        turns = lua.globals().turns
        assert len(turns) > 0, f"{unit}: the procedural death drove no Turn calls"
        assert any(abs(turns[i].v) > 1e-6 for i in range(1, len(turns) + 1)), (
            f"{unit}: the procedural death produced only rest-pose values"
        )

    def test_death_evidence_line_is_baked_with_driven_pieces(self, script_name):
        unit = ARTICULATED_SCRIPTS[script_name]
        lua, _ = run_killed(unit)

        echoes = [lua.globals().echoes[i] for i in range(1, len(lua.globals().echoes) + 1)]
        death_lines = [line for line in echoes if line.startswith("PHASE7 DEATH ")]
        assert death_lines, f"{unit}: Killed emitted no PHASE7 DEATH evidence line"

        line = death_lines[0]
        assert "unit=42" in line
        assert "baked=1" in line, f"{unit}: fell back to the procedural death"
        driven = int(re.search(r"driven=(\d+)", line).group(1))
        assert driven >= 20, f"{unit}: death clip drove only {driven} piece-frames"


def articulated_unitdefs() -> set[str]:
    """Unitdefs whose unit script is articulated AND whose mesh has >1 piece."""
    found = set()
    for unit_file in UNITS.glob("medieval_*.lua"):
        text = unit_file.read_text(encoding="utf-8")
        script = re.search(r'script\s*=\s*"medieval_([a-z_]+)\.lua"', text)
        obj = re.search(r'objectName\s*=\s*"0ad/medieval_([a-z_]+)\.obj"', text)
        if not script or not obj:
            continue
        if f"medieval_{script.group(1)}.lua" not in ARTICULATED_SCRIPTS:
            continue
        pieces = obj_pieces(obj.group(1))
        if len(pieces) > 1:
            found.add(unit_file.stem)
    return found


def probe_unit_list() -> list[str]:
    text = GADGET.read_text(encoding="utf-8")
    block = text.split("local UNITS = {", 1)[1].split("}", 1)[0]
    return re.findall(r'"(medieval_[a-z_]+)"', block)


class TestProbeCoverage:
    def test_every_articulated_unitdef_is_probed(self):
        expected = articulated_unitdefs()
        assert expected, "no articulated unitdefs detected"
        assert set(probe_unit_list()) == expected, (
            "the death probe must cover every articulated unitdef"
        )

    def test_runner_checks_the_same_units(self):
        text = RUNNER.read_text(encoding="utf-8")
        block = text.split("UNITS = [", 1)[1].split("]", 1)[0]
        runner_units = re.findall(r'"(medieval_[a-z_]+)"', block)
        assert set(runner_units) == set(probe_unit_list())

    def test_gadget_is_gated_and_kills_via_the_normal_damage_pipeline(self):
        text = GADGET.read_text(encoding="utf-8")
        assert "medievalanimprobe" in text
        # DestroyUnit skips the LUS Killed call-in, so the probe must use damage.
        assert "Spring.AddUnitDamage" in text
        assert "Spring.DestroyUnit" not in text
        # The recruitment gadget tears down units the team cannot pay for, so
        # the probe must fund the team before spawning or later spawns vanish.
        assert "GG.MedievalEconomy" in text
        assert "Deposit" in text
        # Fallback mode is driven by a per-unit rule the LUS reads in Killed.
        assert "medievalanimfallback" in text
        assert "medieval_force_procedural_death" in text
        assert "SetUnitRulesParam" in text

    def test_startscript_enables_the_probe(self):
        text = STARTSCRIPT.read_text(encoding="utf-8")
        assert "medievalanimprobe=1" in text
        assert "medievaltest=0" in text
        assert "medievalanimfallback" not in text

    def test_fallback_startscript_enables_the_fallback_mode(self):
        assert FALLBACK_STARTSCRIPT.exists()
        text = FALLBACK_STARTSCRIPT.read_text(encoding="utf-8")
        assert "medievalanimprobe=1" in text
        assert "medievalanimfallback=1" in text

    def test_runner_verifies_both_modes(self):
        text = RUNNER.read_text(encoding="utf-8")
        assert "startscript_phase7_death.txt" in text
        assert "startscript_phase7_death_fallback.txt" in text
        assert "procedural" in text
        assert "expect_baked" in text

    def test_modoption_exists_and_defaults_off(self):
        text = (ROOT / "modoptions.lua").read_text(encoding="utf-8")
        for key in ("medievalanimprobe", "medievalanimfallback"):
            assert f'key = "{key}"' in text
        probe_block = text.split('key = "medievalanimprobe"', 1)[1].split("},", 1)[0]
        assert "def = false" in probe_block
        fallback_block = text.split('key = "medievalanimfallback"', 1)[1].split("},", 1)[0]
        assert "def = false" in fallback_block
