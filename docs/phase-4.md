# Phase 4: Siege, Production & Advanced Military

Phase 4 builds on Phase 3 (logistics, tech tree, fortifications, road speed, supply).
All art reuses CC-BY-SA 3.0 0 A.D. static assets via `tools/assets/convert_0ad.py`.
Code is GPL-v2; see `LICENSE.md` and `licenses/0ad-art.txt`.

## Slices

### Slice 1 — Siege Warfare Core (complete)
- New siege unit: `medieval_catapult` (0 A.D. static OBJ + DDS, converted by the asset tool).
- Siege weapon def: high crush damage, low rate of fire, min range, ballistic arc, AoE.
- Aim-dead-zone behavior via LUS script (the engine build has no `minRange` tag).
- Probe: siege unit fires on target, damage lands, target destroyed.
- Tests: `tests/test_phase4_slice1.py` (unitdef/weapondef validation, damage policy).

#### Slice 1 results

Art conversion (`python tools/assets/convert_0ad.py`):

```
medieval_catapult: 982 vertices, 556 triangles; objects3d/0ad/medieval_catapult.obj
```

| Output | Source entry in `public.zip` |
| --- | --- |
| `objects3d/0ad/medieval_catapult.obj` | `art/meshes/structural/hele_lithobolos.dae.cached.pmd` |
| `objects3d/0ad/medieval_catapult.lua` | (generated `tex1` metadata) |
| `unittextures/0ad/medieval_catapult.dds` | `art/textures/skins/structural/hele_siege.dds.cached.dds` |
| actor provenance | `art/actors/units/hellenes/siege_rock.xml` |

`tools/assets/convert_0ad.py` now stores the full actor archive path per unit (the
previous `ACTOR_PREFIX` hard-coded the Athenians directory) and records post-scale
OBJ bounds in `tools/assets/0ad-manifest.json`, so the lithobolos' larger hull
(~54 x 80 x 120 units) is visible in provenance instead of silently accepted.

New files:

| File | Purpose |
| --- | --- |
| `units/medieval_catapult.lua` | Unitdef: `Catapult`, LAND, TANK3, 3x3, 600 HP, speed 18 / maxVelocity 1.2, costs wood 120 / stone 40 / iron 10, weapon `catapult` |
| `gamedata/weapondefs.lua` (`catapult`) | `Catapult Rock`, Cannon, range 550, reloadtime 5.0, velocity 350, damage 500, AoE 48 @ 0.5 edge |
| `scripts/medieval_catapult.lua` | LUS: `AimWeapon1`/`FireWeapon1`/`AimFromWeapon1`/`QueryWeapon1` (+ unnumbered forms), all on piece `base` |
| `tests/test_phase4_slice1.py` | 28 tests |
| `luarules/gadgets/gadget_phase2_test_forces.lua` | Slice 8 probe (frames 360-570) |

Three defects were found and fixed by in-engine evidence, not by inspection:

1. **`minRange` is not an engine tag.** The engine logs
   `Warning: WeaponDefs: Unknown tag "minrange" in "catapult"` and ignores it, so the
   dead zone is enforced in `scripts/medieval_catapult.lua` (`MIN_RANGE = 120`);
   `AimWeapon1`/`AimWeapon` return `false` inside 120 elmos. `minRange` is kept in
   `gamedata/weapondefs.lua` as the authoritative design value, documented as ignored.
2. **The ballistic reach was shorter than the range.** `myGravity` is elmos/frame²,
   so reach is `v² / g = 350² / 0.6 ≈ 227` elmos against a 550-elmo range. The solver
   produced a degenerate flat shot that spawned *under the terrain* (projectile at
   `y=89.7` against ground height `90.3`) and died on the next frame, dealing zero
   damage. `myGravity` is now `0.2` (engine default), giving reach `≈ 680` elmos.
3. **The weapon arc was too narrow.** `maxAngleDif = 60` with the unit spawned facing
   east put the wall ~90° off-axis; combined with the LUS returning `true`
   unconditionally the engine fired anyway, so the rock flew off-target. The
   lithobolos sits on a turntable, so `maxAngleDif` is now `360`.

`noSelfDamage = true` is also required: the converted mesh has no muzzle piece, so the
rock launches from the unit origin and its own 48-elmo AoE would otherwise destroy the
launcher on the first shot (observed: catapult destroyed one frame after firing).

#### Slice 1 headless probe evidence

`python tools/launch/run_phase2_slice2_probe.py` → `tools/runtime/infolog.txt`
(git-ignored, regenerated each run). Probe stages live in
`luarules/gadgets/gadget_phase2_test_forces.lua` after Slice 7 (frames 360-570).

```
PHASE4 PROBE catapult spawned f=360 team=0 id=3328 target=22643 enemy=1 hp0=2500 dist=300
PHASE4 PROBE catapult spawn-verdict f=360 PASS (id=3328 target=22643 hp0=2500)
PHASE4 PROBE catapult attack-order f=360 PASS (giveOrderAPI=function)
PHASE4 PROBE catapult aim f=380 lusAimingParam=1 selfHp=600
PHASE4 PROBE catapult aim-verdict f=380 PASS (LUS AimWeapon1 ran, aiming=1 expect=1)
PHASE4 PROBE catapult pre-fire f=500 selfHp=602.21759 targetHp=2048.82227
PHASE4 PROBE catapult fire f=540 lusFiredParam=1 selfHp=604.395691 targetHp=1598.63135 hp0=2500 dealt=901.4
PHASE4 PROBE catapult fire-verdict f=540 PASS (LUS FireWeapon1 ran, fired=1)
PHASE4 PROBE catapult self-damage-verdict f=540 PASS (selfHp=604.395691)
PHASE4 PROBE catapult damage-verdict f=570 PASS (dealt=901.4 expect>0 hp0=2500 hp=1598.63135)
```

Six deterministic `PASS` verdicts. Engine reached frame 2520 (startscript quit raised
from frame 600 to 720 so the 5.0 s reload, which delays the first shot to ~f=502, is
covered inside the run).

Probe timing note: `reloadtime = 5.0` is 150 frames and the engine applies a full
initial reload at creation, so the first shot leaves at ~f=502 after a spawn at f=360.
Pre-fire stages sample at f=380/f=500 and post-fire stages at f=540/f=570. An earlier
draft sampled at f=390 and reported `FAIL` purely because the catapult had not fired yet.

Aim and fire verdicts read unit rules params (`medieval_catapult_aiming`,
`medieval_catapult_fired`) published by the LUS, because `Spring.GetUnitWeaponState` /
`GetUnitWeaponTarget` / `GetUnitWeaponTestRange` return no usable values for this unit
in this engine build (`GetUnitWeaponTarget` reports `targetType=1` with a nil target id).
Only `script.AimWeapon1` / `script.FireWeapon1` can set those params, so a `1` is proof
the engine dispatched into the catapult's unit script. Target health loss is the
independent, engine-side damage evidence.

#### Slice 1 test count

```
python tests/check_lua_syntax.py   -> Checked 46 lua files; 0 errors found.
python -m pytest tests -q          -> 330 passed
```

`tests/test_phase4_slice1.py` contributes 28 tests (unitdef fields and cost, footprint/
movementclass agreement, weapon table, weapondef range/reload/ballistics/damage/AoE,
LUS compile and call-in exports, dead-zone enforcement, rules-param contract, art asset
and manifest provenance, economy/upkeep/pop integration, license safety).

### Slice 2 — Damage Types & Fortification Destruction
- Damage-type matrix: `siege` vs `fortification` (walls/towers take heavy siege damage,
  resist normal melee); melee vs standard units unchanged.
- Walls/towers become meaningfully destructible by siege; block pathing as today.
- Tests: damage matrix policy + gadget pre-damage scaling.

### Slice 3 — Production Chains: Blacksmith & Fletcher
- `medieval_blacksmith` (exists as a unitdef shell; add crafting behavior) converts
  Iron → weapon equipment; `medieval_fletcher` converts Wood → bow equipment.
- High-tier military recruitment gated on equipment stock, not just food/pop.
- Tests: crafting state machine + recruitment gating.

### Slice 4 — Military Upgrades & Veteran Tiers
- Tech-tree research unlocks advanced variants (crossbow, men-at-arms, knight).
- Stats scale via existing `GG.MedievalLogistics` damage multipliers and new tech IDs.
- Tests: unlock policy + damage stacking with supply bonus.

### Slice 5 — Transport & Hauler Units
- `medieval_cart` with high carry capacity; road-dependent speed via Slice 6 (Phase 3)
  mutator; auto-haul between storage hubs when local deficit exists.
- Tests: haul policy + road-speed integration.

### Slice 6 — Basic Medieval Skirmish AI
- Lua skirmish AI: place houses, harvest, connect endpoints with roads, train military,
  attack. Automated match probe produces PASS/FAIL evidence.

## Verification conventions (unchanged from Phase 3)
- `python -m pytest tests -q` (scoped; never bare `python -m pytest -q`).
- `python tests/check_lua_syntax.py`.
- `python tools/launch/run_phase2_slice2_probe.py` headless probe; per-slice deterministic
  `PASS` verdicts; evidence versioned under `docs/` (runtime `infolog.txt` is git-ignored).

## Probe run budget

The headless sim runs well below realtime (~16 frames/s observed). Slice 1's first catapult shot
does not leave until ~f=502 because `reloadtime = 5.0` (150 frames) and the engine applies a full
initial reload at creation. `tools/launch/startscript_phase2.txt` therefore quits at frame 720
(raised from 600) and `tools/launch/run_phase2_slice2_probe.py` allows 90 s of wall clock, so the
f=570 damage verdict is reached inside a single run. Later slices with slow weapons must budget the
same way.

## Out of scope for Phase 4
- Multiplayer balance pass (post-Phase 4).
- Air/hover and transported-unit movement classes.
- Per-slope speed effects.
