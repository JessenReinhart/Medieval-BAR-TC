from pathlib import Path
t = Path('tools/runtime/infolog.txt').read_text(encoding='utf-8', errors='replace')
for line in t.splitlines():
    if any(k in line for k in ['PHASE2', 'gadget_phase2', 'LuaRules', 'LUA_ERR', 'Error:', 'using game', 'GameStart']):
        print(line)
