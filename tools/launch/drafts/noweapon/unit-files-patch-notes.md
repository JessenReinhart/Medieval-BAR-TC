# Unit-file patch notes — NOWEAPON warning

## Verdict: no unit-file changes required

The three unit defs were audited for weapon/explosion references:

- `units/medieval_infantry.lua`
  - `weapons = { { def = "SWORD", onlyTargetCategory = "LAND" } }` (weapon reference)
  - `weaponDefs = { SWORD = { ... } }` (inline def: name, areaOfEffect, craterBoost,
    craterMult, damage, range, reloadtime, turret, weaponType, waterWeapon)
- `units/medieval_archer.lua`
  - `weapons = { { def = "LONGBOW", onlyTargetCategory = "LAND" } }`
  - `weaponDefs = { LONGBOW = { ... } }` (adds weaponVelocity, myGravity,
    heightBoostFactor; all valid WeaponDef tags)
- `units/medieval_cavalry.lua`
  - `weapons = { { def = "LANCE", onlyTargetCategory = "LAND" } }`
  - `weaponDefs = { LANCE = { ... } }` (same tag set as SWORD)

None of the unit files reference `NOWEAPON`, `explodeas`, `explodeasnapalm`,
`deathexplosion`, or any explosion field. All inline weapon tags are valid
WeaponDef tags. **No unit-file edits are needed.**

The `NOWEAPON` def is global, declared only in `gamedata/weapondefs.lua`, and
used by no unit. The warning originates entirely inside that file.