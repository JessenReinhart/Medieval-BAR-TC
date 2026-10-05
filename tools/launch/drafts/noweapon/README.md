# NOWEAPON warning — diagnosis and fix

## Evidence (verbatim from `tools/runtime/infolog.txt`)

Line 241, during the `Loading Weapon Definitions` load phase:

```text
[t=00:00:01.255814][f=-000001] Warning: WeaponDefs: Unknown tag "explodeas" in "noweapon"
```

This is the only `NOWEAPON`-scoped warning in the log (case-insensitive search).
The log's complete `Warning:` set is exactly four lines; the other three are
unrelated (UDP loopback, SMF splat texture, groundFX atlas) and are not in scope.

## Root cause

`gamedata/weapondefs.lua` declares a placeholder weapon with an invalid tag:

```lua
NOWEAPON = {
  name = "Placeholder Weapon",
  weaponType = "Cannon",
  explodeAs = "default",   -- <-- line 5, THE BUG
  range = 0,
  reloadtime = 0,
  turret = false,
  damage = {default = 0},
},
```

- The Recoil/Spring WeaponDef parser case-normalizes keys, so `explodeAs`
  becomes `explodeas`, which it then fails to match against any known WeaponDef
  tag ("noweapon" is the same case-normalized weapon name).
- `explodeAs` (UnitDef tag) selects a *unit death-explosion* class. It is not a
  valid **WeaponDef** tag, so placing it inside a weapon def is a category
  error. The engine warns and discards the tag.
- `explosions.lua`'s `default = { usedefaultexplosions = true }` entry is
  unrelated to the warning; it was the (invalid) reference target of
  `explodeAs`, but the warning is about the WeaponDef tag, not the explosion
  table. `explosions.lua` needs no change.
- No unit file references `NOWEAPON`, `explodeas`, `explodeasnapalm`, or
  `deathexplosion`. The three units (`medieval_infantry`, `medieval_archer`,
  `medieval_cavalry`) declare their own inline `weaponDefs` (SWORD / LONGBOW /
  LANCE) with only valid tags and reference them via `weapons = { { def = ... } }`.
  See `unit-files-patch-notes.md`.

### Minimal fix

Delete the single invalid line from the NOWEAPON weapon def. The placeholder is
`range = 0`, `reloadtime = 0`, `damage = { default = 0 }`, so it produces no
projectile and needs no explosion association. (If a weapon impact visual is
ever desired, the correct WeaponDef tag is `explosionGenerator = "<CEG name>"`.)

## Files written

| Draft file | Purpose |
|---|---|
| `weapondefs.lua.draft` | Corrected `gamedata/weapondefs.lua` (drops `explodeAs`) |
| `unit-files-patch-notes.md` | Audit result: no unit-file change needed |
| `README.md` | This document |

## Application steps

1. Replace `C:\tmp\bar-tc-repo\gamedata\weapondefs.lua` with the content of
   `tools\launch\drafts\noweapon\weapondefs.lua.draft`
   (i.e. delete line 5, `explodeAs = "default",`).
2. No changes to `gamedata\explosions.lua` and no changes to any file under
   `units\`.
3. Re-run the headless launch:
   ```pwsh
   & tools/engine/recoil_2026.07.04/spring-headless.exe --isolation --write-dir tools/runtime tools/launch/startscript.txt
   ```

## Verification signal

After applying the fix, the following log pattern **must disappear** from the
next engine run's `tools/runtime/infolog.txt`:

```text
Warning: WeaponDefs: Unknown tag "explodeas" in "noweapon"
```

Confirm with:

```pwsh
Select-String -Path C:\tmp\bar-tc-repo\tools\runtime\infolog.txt -Pattern 'NOWEAPON' -SimpleMatch
# expect: no matching lines
```