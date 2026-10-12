# Phase 7: Asset Conversion, Polish & Game Feel Specification

> **Status: COMPLETE (2026-10-12).** Phase 7 bridges Medieval-BAR-TC from a mechanically
> verified prototype into a responsive, cohesive medieval RTS experience. Focus: audio
> landscape, projectile FX, complete 3D model coverage, lightweight procedural piece
> animations, and UI feel. Map scope remains Quicksilver Remake.
>
> Final gate: 79 Lua files / 0 syntax errors, **1416 pytest tests passed**, headless
> integration probe **6/6 PASS**.

---

## Architectural Objectives

1. **"Feel" First — Audio & FX Foundation:**
   - Complete combat and economy soundscape: weapon strikes, bow twangs, catapult thuds, tree chopping, stone mining, building construction, and unit response acknowledgments.
   - Distinct projectile visuals and impact effects for arrows, bolts, and catapult stones.
2. **Complete 3D Mesh & Texture Coverage:**
   - Eliminate placeholder recycling across all 22 units and buildings.
   - Buildings must look like authentic historical medieval structures (Town Center, Houses, Barracks, Stables, Granary, Lumber Camp, Market, Blacksmith, Fletcher, Tower, Wall).
   - Dedicated distinct soldier models for Men-at-Arms, Spearmen, Knights, Crossbowmen, Villagers, and King.
   - Extract strictly from 0 A.D. (`public.zip`) under CC-BY-SA 3.0 with SHA-256 manifest tracking.
3. **Lightweight LUS Animation & Motion Dynamics:**
   - Implement fluid RTS-distance piece and procedural animations in Lua Unit Scripts (`scripts/*.lua`):
     - **Locomotion:** Stride bobbing, torso pitch, horse gallop tilt for cavalry/carts.
     - **Combat:** Attack lunges, bow draw/release recoil, catapult arm fling, and weapon aim pitch.
     - **Defeat:** Death tumble / collapse rather than static freezing.
4. **Clean Asset Provenance & Gating:**
   - All sounds and models gated cleanly; sound effects volume modoption in `modoptions.lua`.
   - Python-based verification suites for asset manifest, sound references, and unitdef bindings.
5. **No Regressions:**
   - Maintain 100% green status across all 1416 tests and the 6-verdict headless integration probe.

---

## Slices Breakdown

### Slice 1: Audio Pipeline & Combat/Economy Soundscape
- **Focus:** Extract audio clips from 0 A.D. and wire them into Spring engine defs.
- **Scope:**
  - Weapons: Melee swing/clash, spear thrust, bow draw/release, crossbow release, stone fling.
  - Impacts: Flesh, shield block, stone hit, wood hit.
  - Economy: Wood chopping, stone pickaxe clinking, construction hammering.
  - UI / Alerts: Town Center alarm, unit trained, building complete, resource alert.
- **Files:**
  - `tools/assets/convert_0ad.py` (add sound extraction & manifest generation).
  - `gamedata/sounds.lua` or `sounds.tdf` / sound defs in `units/*.lua` weapons.
  - `tests/test_phase7_slice1.py`.
- **Status:** COMPLETE — 6 tests.

### Slice 2: Combat FX, Projectiles & Visual Impact
- **Focus:** Clear visual readability for ranged combat and impacts.
- **Scope:**
  - Projectile model/texture assignments: flying arrow, crossbow bolt, tumbling boulder.
  - Custom CEG (Custom Explosion Generator) or Spring particle effects for ground impacts, dust, and wood splinters.
  - Selection decals and clear team-color accents.
- **Files:**
  - `gamedata/explosions/*.lua` or `gamedata/resources.lua`.
  - `units/medieval_archer.lua`, `units/medieval_crossbow.lua`, `units/medieval_catapult.lua`, `units/medieval_tower.lua`.
  - `tests/test_phase7_slice2.py`.
- **Status:** COMPLETE — 25 tests.

### Slice 3: Full Static Model & Texture Coverage
- **Focus:** Replace all 18 reused models with dedicated 0 A.D. meshes.
- **Scope:**
  - Convert buildings: Civic center, house, farmstead/granary, lumber camp, market, barracks, stables, forge, defensive tower, stone wall.
  - Convert units: Male/female peasant worker, Greek/Roman/Celtic armored swordsman (Men-at-Arms), heavy spearman, armored cavalry (Knight), king/general.
  - Update all `units/*.lua` `objectName` references.
- **Files:**
  - `tools/assets/convert_0ad.py` & `tools/assets/0ad-manifest.json`.
  - `objects3d/0ad/*.obj`, `unittextures/0ad/*.dds`.
  - `units/*.lua`.
  - `tests/test_phase7_slice3.py`.
- **Status:** COMPLETE — 30 tests.

### Slice 4: Lightweight LUS Piece Animation & Motion Dynamics
- **Focus:** Make units move and fight naturally at RTS camera distance.
- **Scope:**
  - Pure procedural/piece transformations in Lua Unit Scripts (`scripts/*.lua`):
    - `StartMoving` / `StopMoving` cadence loops (tilt, bob, stride roll).
    - `AimWeapon` / `FireWeapon` recoil and strike animation timing.
    - `Killed` death collapse sequence.
  - Catapult arm swing-and-stop release cycle.
- **Files:**
  - `scripts/medieval_infantry.lua`, `scripts/medieval_archer.lua`, `scripts/medieval_cavalry.lua`, `scripts/medieval_catapult.lua`, `scripts/medieval_villager.lua`, `scripts/medieval_cart.lua`.
  - `tests/test_phase7_slice4.py`.
- **Status:** COMPLETE — 116 tests.

### Slice 5: Minimap, Build Icons & UI Polish
- **Focus:** Visual clarity in the interface.
- **Scope:**
  - 22 dedicated build icons for unit training and building construction menus.
  - Unit radar/minimap icons (swords for melee, bow for ranged, horse for cavalry, shield for siege).
  - Cursor set check and modoptions audio toggles.
- **Files:**
  - `unitpics/*.png` (generated by `tools/assets/generate_unitpics.py`).
  - `bitmaps/icons/*.png` + `gamedata/icontypes.lua` (generated by `tools/assets/generate_minimap_icons.py`).
  - `units/*.lua` (`buildpic` + `iconType`).
  - `LuaUI/Widgets/gui_medieval_build_icons.lua`.
  - `luarules/gadgets/gadget_medieval_fx.lua`.
  - `modoptions.lua`.
  - `tests/test_phase7_slice5.py`.
- **Status:** COMPLETE — 44 tests.

### Slice 6: Final Integration Probe & Verification Gate
- **Focus:** Regression testing and end-to-end match validation.
- **Scope:**
  - Full syntax and unit test verification.
  - Run headless skirmish probe to ensure new assets, sounds, and animations cause no crashes or timing drifts.
- **Files:**
  - `tools/launch/run_phase5_slice6_probe.py`.
  - `docs/phase-7.md`, `docs/handoff.md`.
- **Status:** COMPLETE (2026-10-12) — verification gate only; no new test module
  (the spec's `tests/test_phase7_slice6.py` is not required, the gate re-runs the
  existing suite plus the headless probe).

**Verified 2026-10-12:**
- `python tests/check_lua_syntax.py` → `Checked 79 lua files; 0 errors found.`
- `python -m pytest tests -q` → **1416 passed** in 7.28s.
- `python tools/launch/run_phase5_slice6_probe.py` → 6/6 PASS:
  `settlement-start` f=40, `economy-flow` f=100, `military-engagement` f=160,
  `tc-destroyed` f=260, `victory-gameover` f=300 (`winner=1 reason=tc_destruction`),
  `probe-complete` f=300 → `SLICE 6 INTEGRATION PROBE: ALL VERDICTS PASSED`.

---

## Verification Gate

```pwsh
python tests/check_lua_syntax.py                 # 0 errors (79 files)
python -m pytest tests -q                        # 1416 passed
python tools/launch/run_phase5_slice6_probe.py    # 6/6 PASS verdicts in engine probe
```
