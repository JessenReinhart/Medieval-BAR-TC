from pathlib import Path
t = Path('tools/runtime/infolog.txt').read_text(encoding='utf-8', errors='replace')
lines = t.splitlines()
print(f"Total infolog lines: {len(lines)}")
for l in lines[-120:]:
    if any(k in l for k in ['PHASE2', 'Error:', 'LUA_ERR', 'GameFrame']):
        print(l)
