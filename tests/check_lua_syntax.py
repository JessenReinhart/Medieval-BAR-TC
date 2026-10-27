from pathlib import Path

from lupa import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)

# Recursively scan every Lua source tree (including LuaUI/Widgets and
# scripts/animdata), skipping the engine write sandbox and .git.
EXCLUDE_PARTS = ("tools/runtime", ".git")
roots = [Path("scripts"), Path("units"), Path("gamedata"),
         Path("luarules"), Path("LuaUI"), Path("features")]
files = sorted(set(
    p for root in roots for p in root.rglob("*.lua")
    if not any(part in p.as_posix() for part in EXCLUDE_PARTS)
))
files += sorted(Path(".").glob("*.lua"))

bad = 0
for p in files:
    code = p.read_text(encoding="utf-8")
    lua.globals().c = code
    ret = lua.execute("local fn, err = load(c); return { fn = fn, err = err }")
    if ret["fn"] is None:
        bad += 1
        print("SYNTAX ERROR:", p, "->", ret["err"])
print(f"Checked {len(files)} lua files; {bad} errors found.")
assert bad == 0, "Syntax errors present"
