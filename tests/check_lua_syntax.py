from pathlib import Path
from lupa import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
files = sorted(set(
    list(Path('scripts').glob('*.lua')) +
    list(Path('units').glob('*.lua')) +
    list(Path('gamedata').glob('*.lua')) +
    list(Path('luarules/gadgets').glob('*.lua')) +
    list(Path('.').glob('*.lua'))
))
bad = 0
for p in files:
    code = p.read_text(encoding='utf-8')
    lua.globals().c = code
    ret = lua.execute('local fn, err = load(c); return { fn = fn, err = err }')
    if ret['fn'] is None:
        bad += 1
        print('SYNTAX ERROR:', p, '->', ret['err'])
print(f'Checked {len(files)} lua files; {bad} errors found.')
assert bad == 0, 'Syntax errors present'
