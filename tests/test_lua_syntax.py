from pathlib import Path
import unittest
from lupa import LuaRuntime

ROOT = Path(__file__).parents[1]

class TestLuaSyntaxAllFiles(unittest.TestCase):
    def test_all_lua_files_compile(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        files = sorted(set(
            list((ROOT / 'scripts').glob('*.lua')) +
            list((ROOT / 'units').glob('*.lua')) +
            list((ROOT / 'gamedata').glob('*.lua')) +
            list((ROOT / 'luarules' / 'gadgets').glob('*.lua')) +
            list((ROOT / 'LuaUI' / 'Widgets').glob('*.lua')) +
            list(ROOT.glob('*.lua'))
        ))
        for p in files:
            code = p.read_text(encoding='utf-8')
            lua.globals().c = code
            ret = lua.execute('local fn, err = load(c); return { fn = fn, err = err }')
            self.assertIsNotNone(ret['fn'], f"Lua compile failure in {p.relative_to(ROOT)}: {ret['err']}")

if __name__ == '__main__':
    unittest.main()
