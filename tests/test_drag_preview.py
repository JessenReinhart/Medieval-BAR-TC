"""Lupa-based mocked verification of the drag formation preview widget.

No engine, no GL: Spring/gl/VFS/UnitDefNames/Game are mocked in Lua, while the
real scripts/phase1_line_formation.lua module is loaded so formation.CMD_ID and
formation.finite are exercised for real. The widget source is executed against
those globals, and the mouse call-ins are driven to assert GiveOrderToUnitArray
receives exactly the expected formation command.
"""
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).parents[1]
FORMATION_SRC = (ROOT / 'scripts' / 'phase1_line_formation.lua').read_text(encoding='utf-8')
WIDGET_SRC = (ROOT / 'LuaUI' / 'Widgets' / 'gui_medieval_formation_preview.lua').read_text(encoding='utf-8')


SETUP = """
widget = {}
calls = {}

local function ground_for(x, y)
  -- Deterministic screen->ground mapping: x*10 / y*10.
  return "ground", { x = x * 10, y = 0, z = y * 10 }
end

Spring = {
  GetModOptions = function() return { medievaltest = 1 } end,
  GetSpectatingState = function() return false end,
  GetSelectedUnits = function() return { 1, 2, 3, 4 } end,
  GetUnitTeam = function(id) return 0 end,
  GetUnitDefID = function(id) return 1 end,
  GetMyTeamID = function() return 0 end,
  TraceScreenRay = function(x, y) return ground_for(x, y) end,
  GiveOrderToUnitArray = function(ids, cmd, params, opts)
    calls[#calls + 1] = { ids = ids, cmd = cmd, params = params, opts = opts }
  end,
  Echo = function() end,
  GetGroundHeight = function(x, z) return 0 end,
}

UnitDefNames = {
  medieval_infantry = { id = 1 },
  medieval_archer = { id = 2 },
  medieval_cavalry = { id = 3 },
}

gl = {
  Color = function() end,
  DrawGroundCircle = function() end,
  Shape = function() end,
  Vertex = function() end,
  LINES = 1,
}

Game = { mapSizeX = 8192, mapSizeZ = 8192 }

VFS = { Include = function(name) return assert(load(formation_src))() end }

assert(load(widget_src))()
"""


def _boot():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().formation_src = FORMATION_SRC
    lua.globals().widget_src = WIDGET_SRC
    lua.execute(SETUP)
    return lua


def test_drag_preview_issues_formation_command():
    lua = _boot()
    g = lua.globals()
    w = g.widget
    formation = lua.execute(FORMATION_SRC)

    # press starts the drag, move extends it, release issues the command
    assert w.MousePress(w, 100, 100, 1) is True
    assert w.MouseMove(w, 200, 150, 100, 50, 1) is True
    assert w.MouseRelease(w, 200, 150, 1) is True

    calls = g.calls
    assert len(calls) == 1, f"expected exactly 1 order, got {len(calls)}"
    rec = calls[1]

    assert rec.cmd == formation.CMD_ID
    assert rec.opts == 0

    ids = [rec.ids[i] for i in range(1, 5)]
    assert ids == [1, 2, 3, 4]

    p = rec.params
    # x/z from dragEndGround == TraceScreenRay(200,150) -> {x=2000,z=1500}
    assert p[1] == 2000
    assert p[2] == 1500
    # spacing fixed at 48
    assert p[3] == 48
    # facing: gdx=2000-1000=1000, gdz=1500-1000=500 -> X-dominant, gdx>=0 -> 0
    assert p[4] == 0
    # count == #selected (4)
    assert p[5] == 4
    # payload unit ids {1,2,3,4}
    assert [p[i] for i in range(6, 10)] == [1, 2, 3, 4]

    # Second case dragging along Z: press(100,100) -> move(120,200) -> end {1200,2000}.
    assert w.MousePress(w, 100, 100, 1) is True
    assert w.MouseMove(w, 120, 200, 20, 100, 1) is True
    assert w.MouseRelease(w, 120, 200, 1) is True

    assert len(calls) == 2, f"expected exactly 2 orders, got {len(calls)}"
    p2 = calls[2].params
    assert p2[1] == 1200
    assert p2[2] == 2000
    # gdx=200, gdz=1000 -> Z-dominant, gdz>=0 -> 1
    assert p2[4] == 1
    assert p2[5] == 4
    assert [p2[i] for i in range(6, 10)] == [1, 2, 3, 4]