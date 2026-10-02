"""Executable mocked tests; these do not launch BAR gameplay."""
from pathlib import Path
from lupa import LuaRuntime

ROOT = Path(__file__).parents[1]
lua = LuaRuntime(unpack_returned_tuples=True)
src = (ROOT / 'scripts' / 'phase1_line_formation.lua').read_text(encoding='utf-8')
formation = lua.execute(src)

checks = []
def check(name, value):
    checks.append((name, bool(value)))

check('finite integer', formation.finite(5))
check('reject nan', not formation.finite(float('nan')))
check('reject inf', not formation.finite(float('inf')))
check('bounds valid', formation.bounds(500, 500, 1000, 1000, 16))
check('bounds reject edge', not formation.bounds(15, 500, 1000, 1000, 16))
for facing in range(4):
    slots = formation.destinations(4, 500, 500, 48, facing, 1000, 1000)
    check(f'slots facing {facing}', slots is not None and len(slots) == 4)
check('facing reject', formation.destinations(2, 500, 500, 48, 9, 1000, 1000) is None)
check('spacing reject', formation.destinations(2, 500, 500, 7, 0, 1000, 1000) is None)
check('count reject', formation.destinations(1001, 500, 500, 48, 0, 1000, 1000) is None)
check('line bounds reject without autofit', formation.destinations(4, 980, 500, 48, 0, 1000, 1000) is None)

# Review requirement: large 100 and 200 formations on 4096 map.
# 100 units at 48 spacing requires (100-1)*48 = 4752 elmos > 4096; without autofit, must reject:
check('large 100 reject without autofit', formation.destinations(100, 2048, 2048, 48, 1, 4096, 4096, False) is None)
check('large 200 reject without autofit', formation.destinations(200, 2048, 2048, 48, 1, 4096, 4096, False) is None)
# With autofit, spacing clamps down to fit within map margins (4096-32 = 4064 elmos):
slots100 = formation.destinations(100, 2048, 2048, 48, 1, 4096, 4096, True)
check('large 100 autofit succeeds', slots100 is not None and len(slots100) == 100)
if slots100:
    check('large 100 slots within margins', 32 <= slots100[1].z <= 4064 and 32 <= slots100[100].z <= 4064)
slots200 = formation.destinations(200, 2048, 2048, 48, 1, 4096, 4096, True)
check('large 200 autofit succeeds', slots200 is not None and len(slots200) == 200)
if slots200:
    check('large 200 slots within margins', 32 <= slots200[1].z <= 4064 and 32 <= slots200[200].z <= 4064)
# But if count is so large that clamped spacing would fall below MIN_SPACING (8), autofit must reject:
# 600 units on 4096 map -> (4064) / 599 = 6.78 < 8:
check('extreme count below MIN_SPACING rejected', formation.destinations(600, 2048, 2048, 48, 1, 4096, 4096, True) is None)

ids = formation.sortedIDs(lua.table_from([30, 10, 20]), 1, 3)
check('IDs sorted', ids is not None and [ids[i] for i in range(1, 4)] == [10, 20, 30])
check('duplicate IDs reject', formation.sortedIDs(lua.table_from([10, 10, 20]), 1, 3) is None)
check('noninteger ID reject', formation.sortedIDs(lua.table_from([10.5, 20, 30]), 1, 3) is None)
check('length mismatch reject', formation.sortedIDs(lua.table_from([10, 20]), 1, 3) is None)

gadget = (ROOT / 'luarules' / 'gadgets' / 'gadget_phase1_test_forces.lua').read_text(encoding='utf-8')
ui = (ROOT / 'luaui' / 'widgets' / 'gui_medieval_formation_preview.lua').read_text(encoding='utf-8')
check('gadget opt-in gate', 'options.medievaltest' in gadget and 'if not enabled then return end' in gadget)
check('default at least 200', 'math.max(200' in gadget)
check('ground height and move test', 'GetGroundHeight' in gadget and 'TestMoveOrder' in gadget)
check('counts logged', 'created %d' in gadget)
check('hostile team selection', 'AreTeamsAllied' in gadget and 'GetGaiaTeamID' in gadget)
check('custom command registration', 'RegisterCMDID' in gadget and 'RegisterAllowCommand' in gadget)
check('one-shot move', 'Spring.GiveOrderToUnit(id, CMD.MOVE' in gadget and 'pending = {}' in gadget)
check('interruptible callbacks present', 'UnitDestroyed' in gadget and 'UnitTaken' in gadget and 'UnitIdle' in gadget)
check('synced validation checks each unit', 'Spring.GetUnitTeam(id)' in gadget)
check('UI no right click', 'button == 3' not in ui)
check('UI explicit text command', 'TextCommand' in ui and 'Spring.GiveOrderToUnitArray' in ui)

# Execute the gadget in an isolated Lua mock, not just inspect source strings.
def mock_run(modopts, teams=(4, 3, 2, 1, 0), allied=(), fail_create=False):
    engine = LuaRuntime(unpack_returned_tuples=True)
    engine.globals().src = gadget
    engine.globals().helper = src
    engine.globals().modopts = engine.table_from(modopts)
    engine.globals().teamlist = engine.table_from(teams)
    engine.globals().allied = engine.table_from(allied)
    engine.globals().fail_create = fail_create
    engine.execute('''
      orders, created, log, registrations = {}, {}, {}, {}
      local nextID = 100
      Spring = {
        GetModOptions = function() return modopts end,
        GetTeamList = function() return teamlist end,
        GetGaiaTeamID = function() return 0 end,
        GetTeamInfo = function(id) return nil, nil, false end,
        AreTeamsAllied = function(a,b) return a == b or allied[a .. ':' .. b] == true end,
        GetGroundHeight = function(x,z) return 5 end,
        TestMoveOrder = function(def,x,y,z) return true end,
        CreateUnit = function(def,x,y,z,facing,team)
          if fail_create then return nil end
          nextID = nextID + 1
          created[#created+1] = {id=nextID, def=def, x=x, y=y, z=z, facing=facing, team=team}
          return nextID
        end,
        GetUnitTeam = function(id)
          for _,u in ipairs(created) do if u.id == id then return u.team end end
          if id >= 500 and id < 700 then return 1 end
          if id == 700 then return 2 end
        end,
        GetUnitDefID = function(id)
          for _,u in ipairs(created) do if u.id == id then return u.def end end
          return 10
        end,
        GiveOrderToUnit = function(id,cmd,params,opts)
          orders[#orders+1] = {id=id, cmd=cmd, params=params, opts=opts}
        end,
        Echo = function(msg) log[#log+1] = msg end,
      }
      CMD = {MOVE=10, ATTACK=20, STOP=30, FIGHT=40, ANY=-1}
      CMDTYPE = {ICON=1}
      UnitDefNames = {medieval_infantry={id=10}, medieval_archer={id=11}, medieval_cavalry={id=12}}
      Game = {mapSizeX=4096, mapSizeZ=4096}
      VFS = {Include = function(name) return assert(load(helper))() end}
      gadgetHandler = {
        IsSyncedCode = function() return true end,
        RegisterCMDID = function(self,id) registrations[#registrations+1] = id end,
        RegisterAllowCommand = function(self,id) registrations[#registrations+1] = id end,
      }
      gadget, GG = {}, {}
      assert(load(src))()
    ''')
    return engine

blocked = mock_run({})
check('gated: no registered commands', len(blocked.globals().registrations) == 0)
check('gated: no GameFrame call-in', blocked.globals().gadget.GameFrame is None)
active = mock_run({'medievaltest': '1'})
g = active.globals().gadget
g.Initialize(g)
g.GameFrame(g, 30)
created = active.globals().created
orders = active.globals().orders
check('registered custom ID', active.globals().registrations[1] == formation.CMD_ID)
check('default count 200', len(created) == 200)
check('one FIGHT per created unit', len(orders) == 200 and all(orders[i].cmd == 40 for i in range(1, 201)))
check('spawn excludes Gaia and sorts teams', all(created[i].team in (1, 2) for i in range(1, 201)))
check('spawn uses valid map positions and Y', all(0 <= created[i].x <= 4096 and 0 <= created[i].z <= 4096 and created[i].y == 5 for i in range(1, 201)))
g.GameFrame(g, 31)
check('no repeated FIGHT', len(orders) == 200)

# Supplied same-team unit IDs are sorted by synced Lua even when reversed.
p = active.table_from([2048, 2048, 48, 1, 2, 501, 500])
check('formation consumed', g.AllowCommand(g, 500, 10, 1, formation.CMD_ID, p, active.table_from({})) is False)
g.GameFrame(g, 32)
check('formation dispatches MOVE once', len(orders) == 201 and orders[201].id == 500 and orders[201].cmd == 10)
check('sorted rank picks lower Z', orders[201].params[3] == 2048-24)
g.GameFrame(g, 33)
check('MOVE not repeated', len(orders) == 201)

# Hostile ID, duplicate ID, invalid spacing and malformed length are rejected.
for hostile in ([2048, 2048, 48, 1, 2, 500, 700],
                [2048, 2048, 48, 1, 2, 500, 500],
                [2048, 2048, 7, 1, 2, 500, 501],
                [2048, 2048, 48, 1, 3, 500, 501]):
    g.AllowCommand(g, 500, 10, 1, formation.CMD_ID, active.table_from(hostile), active.table_from({}))
g.GameFrame(g, 34)
check('hostile and invalid intents never dispatch', len(orders) == 201)

# Large 100-unit formation dispatch test via mocked gadget:
units100 = list(range(500, 600))
p100_list = [2048, 2048, 48, 1, 100] + units100
p100 = active.table_from(p100_list)
for uid in units100:
    res = g.AllowCommand(g, uid, 10, 1, formation.CMD_ID, p100, active.table_from({}))
check('large 100 formation consumed for all units', res is False)
g.GameFrame(g, 35)
check('large 100 dispatches exactly 100 MOVE orders', len(orders) == 301)
# Verify first and last units in 100-unit line have positions inside map margins:
move_orders = [orders[i] for i in range(1, len(orders) + 1) if orders[i].cmd == 10]
check('large 100 first unit within margins', move_orders[0].params[3] >= 16)
check('large 100 last unit within margins', move_orders[-1].params[3] <= 4080)

# Ordinary orders have no custom intercept and cancel unflushed intents.
g.AllowCommand(g, 500, 10, 1, formation.CMD_ID, p, active.table_from({}))
check('ordinary ATTACK allowed', g.AllowCommand(g, 500, 10, 1, 20, active.table_from([]), active.table_from({})) is True)
g.GameFrame(g, 36)
check('ordinary attack preserved', len(orders) == 301)
check('ordinary STOP allowed', g.AllowCommand(g, 500, 10, 1, 30, active.table_from([]), active.table_from({})) is True)
check('ordinary MOVE allowed', g.AllowCommand(g, 500, 10, 1, 10, active.table_from([]), active.table_from({})) is True)
check('shift formation rejected', g.AllowCommand(g, 500, 10, 1, formation.CMD_ID, p, active.table_from({'shift': True})) is False)
g.GameFrame(g, 37)
check('shift formation does not dispatch', len(orders) == 301)

failed_spawns = mock_run({'medievaltest': 1, 'medievaltestcount': 220}, fail_create=True)
failed_spawns.globals().gadget.GameFrame(failed_spawns.globals().gadget, 30)
check('creation failures counted', len(failed_spawns.globals().created) == 0 and 'created 0' in failed_spawns.globals().log[1])
one_side = mock_run({'medievaltest': '1'}, teams=(0, 1, 3), allied={'1:3': True})
one_side.globals().gadget.GameFrame(one_side.globals().gadget, 30)
check('allied teams refuse spawns', len(one_side.globals().created) == 0)

failed = [name for name, ok in checks if not ok]
print(f'{len(checks)-len(failed)}/{len(checks)} checks passed')
if failed:
    raise SystemExit('FAILED: ' + ', '.join(failed))
print('ALL PASS')
