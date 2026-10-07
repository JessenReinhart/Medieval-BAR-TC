# Handoff: Medieval-BAR-TC (Phase 3 Slice 1 Complete)

Date: 2026-10-07
Branch: `medieval-total-conversion`
Last work: Phase 3 Slice 1 — road features, speed multiplier, tech tree, fortifications (verified)

## What Works Right Now

1. **Phase 1 Combat Foundation**:
   - 3 military units (`medieval_infantry`, `medieval_archer`, `medieval_cavalry`) with CC-BY-SA 3.0 0 A.D. static OBJ models and DDS textures.
   - Live ballistic + melee combat exchange verified in Recoil 2026.07.04 headless (damage events, unit destruction, LUS Aim/Fire call-ins).
   - Drag formation preview widget (`LuaUI/Widgets/gui_medieval_formation_preview.lua`).

2. **Phase 2 Slice 1 (Settlement & Economy Core)**:
   - Discrete 4-resource economy (`Food`, `Wood`, `Stone`, `Iron`) tracked authoritatively per team via `luarules/gadgets/gadget_medieval_economy.lua` and `scripts/medieval_economy.lua`.
   - Synced game rules exposed: `team_<id>_<resource>`.
   - Housing and pop cap management (`luarules/gadgets/gadget_medieval_housing.lua`, `scripts/medieval_housing.lua`), capped at 300, enforced via `AllowUnitCreation`.
   - Settlement buildings: Town Center (7x7), House (4x4), Granary (4x4), Lumber Camp (4x4).
   - Villager worker: carry capacity 10, harvest rate 2, build options.
   - Resource nodes: features `medieval_tree` (wood: 500), `medieval_stone` (stone: 400), `medieval_iron` (iron: 300), `medieval_deer` (food: 250).
   - Gathering state machine (`luarules/gadgets/gadget_medieval_gather.lua`, `scripts/medieval_gather.lua`).

3. **Phase 2 Slice 2 (Recruitment, Costs, Pop Cap)** — complete and verified:
   - Barracks, Stables, Blacksmith unitdefs with `resource_cost_*` fields.
   - `gadget_medieval_recruitment.lua` enforces discrete resource costs via `GG.MedievalEconomy.Transact` and pop cap via housing; exposes `GG.MedievalRecruitment.CanRecruit(teamID, unitDefName)`.
   - Pure module `scripts/medieval_recruitment.lua` provides cost lookup and food upkeep.
   - 63 pytest tests passing at Slice 2 completion.
   - Slice 2 probe: `tools/launch/run_phase2_slice2_probe.py`.

4. **Phase 2 Slice 3 (Upkeep, Starvation, FX)** — just landed:
   - Standing-army food upkeep every 90 engine frames: infantry 2, archer 2, cavalry 3 food per unit per tick.
   - Starvation penalty: 5% current-HP attrition per tick, non-lethal (health-only, no `DestroyUnit`).
   - Synced gamerule `team_<id>_starving` published per team (seeded 0 at `GameStart`).
   - `GG.MedievalRecruitment.Upkeep(teamID)` / `.IsStarving(teamID)` / `.RunUpkeepTick()` API.
   - FX hooks gadget (`luarules/gadgets/gadget_medieval_fx.lua`) — echo-only, headless log verification.

5. **Phase 3 Slice 1 (Roads, Tech Tree, Fortifications)** — just landed and verified:
   - Road feature `medieval_road` (non-blocking, cost wood=5/stone=2) granting `ROAD_SPEED_MULT = 1.5` within 48-elmo proximity (`gamedata/featuredefs.lua`, `scripts/medieval_logistics.lua`).
   - Blacksmith tech tree: `iron_swords` (+25% infantry melee), `plate_armor` (+25% infantry/cavalry HP), `masonry` (+50% wall/tower HP); synced gamerules `team_<id>_tech_<techID>`.
   - Fortifications: `medieval_wall` (2x2, 2500 HP) and `medieval_tower` (3x3, 600 sight); placement cost enforced via `AllowUnitCreation`.
   - Gadget `gadget_medieval_logistics.lua` (layer 3 synced) exposing `GG.MedievalLogistics`.
   - 131 pytest tests passing at Slice 1 completion.

## How to Run the Slice 3 Tests and Probe

```pwsh
# Slice 3 unit tests (28 new: pure module + gadget wiring source checks)
python -m pytest tests/test_phase3_upkeep.py -q

# Full suite
python -m pytest tests -q

# Headless probe (syncs source into the SDD, filters PHASE2 lines from infolog.txt)
python tools/launch/run_phase2_slice2_probe.py
python tools/launch/read_final_log.py
```

The FX gadget prints `PHASE2 FX trained/destroyed` lines for `medieval_*` units, visible in
the probe's `PHASE2` filter. There is no dedicated Slice 3 upkeep probe: upkeep is exercised
through the pure-module tests plus the in-game `GG.MedievalRecruitment` API, and `GameFrame`
drives the 90-frame tick automatically.

## How to Run the Phase 3 Slice 1 Tests and Probe

```pwsh
# Phase 3 focused tests
python -m pytest tests/test_phase3_logistics.py -q

# Full suite
python -m pytest tests -q

# Headless engine run (syncs source -> SDD, emits PHASE3 probe lines to infolog.txt)
python tools/launch/run_phase2_slice2_probe.py

# Inspect Phase 3 probe output
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"
```

The `PHASE3` probe is driven by `gadget_phase2_test_forces.lua` at `GameFrame == 120` (there is
no separate `run_phase3_probe.py`). Expected lines: `PHASE3 ROAD placed ...`, `PHASE3 PROBE
is-on-road ... speed_mult=1.50`, `PHASE3 TECH researched ... tech=iron_swords|plate_armor`, and
`PHASE3 PROBE research <tech> ... ok=true`.

## Slice 3 Known Limitations

- **Headless audio caveat**: no audio or CEG assets exist in the repo. `gadget_medieval_fx.lua`
  only echoes to the log; the unit-def `soundstart`/`soundhit`/`explosionGenerator` entries are
  comments, not active config. Audio/particle feedback stays unwired until a `sounds/` directory
  and CEG generator names are added — verify sound via a full (non-headless) client run, not the
  headless probe.
- **Provisional tuning values**: upkeep rates (2/2/3) and `STARVATION_HP_FRACTION = 0.05` are
  first-cut placeholders, not play-tested. **Weapon tuning did not land this slice** —
  `gamedata/weapondefs.lua` is unchanged from Phase 1 (sword range 45 / 150 dmg; longbow range
  380 / 90 dmg; lance range 55 / 240 dmg). Treat all Slice 3 numbers as provisional.
- **Starvation is HP-only, not death**: starving units lose 5% of current HP per tick and never
  die from starvation (`starvedHealth` clamps above 0; the gadget never calls `DestroyUnit` for
  upkeep). The army weakens instead of vanishing — expect balance iteration once real matches run.
- **Tick cadence is frame-based**: one tick = `UPKEEP_TICK_FRAMES = 90` engine frames; no
  wall-clock conversion or catch-up logic. Upkeep runs only on `GameFrame` multiples of 90.

## What's Next: Phase 3 Slice 2

- Villager build-command integration for roads/walls/towers (extends Phase 2 gather-priority).
- Apply researched weapon damage to infantry/cavalry in the combat LUS (needs Phase 1 hook).
- Road adjacency graph + connectivity validation.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Slice 3 focused tests
python -m pytest tests/test_phase3_upkeep.py -q

# 3. Run Phase 2 headless probe
python tools/launch/run_phase2_slice2_probe.py
python tools/launch/read_final_log.py

# 4. Review roadmap
cat docs/phase-2.md
```