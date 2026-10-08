# Handoff: Medieval-BAR-TC (Phase 3 Slice 3 query API landed; Phase 3 gameplay integration still open)

Date: 2026-10-08
Branch: `medieval-total-conversion`
Last work: Phase 3 Slice 3 — road adjacency/connectivity query API (`scripts/medieval_road_graph.lua`, `LINK_RADIUS = 64.0`) plus `RoadNetworkSummary` / `RoadConnected` / `PointOnRoadNetwork` on `GG.MedievalLogistics`.

Scope note: Slice 3 is a query API only. It is not enforced logistics gameplay. `AllowUnitCreation`
gates unit creation (and unit affordability), not road-feature placement. Villagers only expose
wall/tower build options here; there is no villager road command yet.

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
   - 63 pytest tests passing at Phase 2 Slice 2 completion (historical count).
   - Probe: `tools/launch/run_phase2_slice2_probe.py`.

4. **Phase 2 Slice 3 (Upkeep, Starvation, FX)** — complete and verified:
   - Standing-army food upkeep every 90 engine frames: infantry 2, archer 2, cavalry 3 food per unit per tick.
   - Starvation penalty: 5% current-HP attrition per tick, non-lethal (health-only, no `DestroyUnit`).
   - Synced gamerule `team_<id>_starving` published per team (seeded 0 at `GameStart`).
   - `GG.MedievalRecruitment.Upkeep(teamID)` / `.IsStarving(teamID)` / `.RunUpkeepTick()` API.
   - FX hooks gadget (`luarules/gadgets/gadget_medieval_fx.lua`) — echo-only, headless log verification.

5. **Phase 3 Slice 1 (Roads, Tech Tree, Fortifications)** — complete and verified:
   - Road feature `medieval_road` (non-blocking, cost wood=5/stone=2) granting `ROAD_SPEED_MULT = 1.5` within 48-elmo proximity (`gamedata/featuredefs.lua`, `scripts/medieval_logistics.lua`).
   - Blacksmith tech tree: `iron_swords` (+25% infantry melee), `plate_armor` (+25% infantry/cavalry HP), `masonry` (+50% wall/tower HP); synced gamerules `team_<id>_tech_<techID>`.
   - Fortifications: `medieval_wall` (2x2, 2500 HP) and `medieval_tower` (3x3, 600 sight); unit cost enforced via `AllowUnitCreation` (units, not road features).
   - Gadget `gadget_medieval_logistics.lua` (layer 3 synced) exposing `GG.MedievalLogistics`.
   - 131 pytest tests passing at Phase 3 Slice 1 completion (historical count).

6. **Phase 3 Slice 2 (Build Handling, Damage Scaling)** — complete and verified:
   - Road build handling: `isBuildable` / `roadBuildQueueValidation` in `scripts/medieval_logistics.lua`.
   - Wall/tower build options: `medieval_wall` / `medieval_tower` added to villager `buildoptions` (`units/medieval_villager.lua`); those villager build options are the only road-adjacent build entries, and there is no road command.
   - `UnitPreDamaged` damage scaling: researched `iron_swords` (+25% infantry melee) applied via `logistics.scaledDamage`; echoes `PHASE3 DAMAGE`.
   - 144 pytest tests passing at Phase 3 Slice 2 completion (historical count).

7. **Phase 3 Slice 3 (Road Adjacency/Connectivity Query API)** — implemented and verified:
   - Pure module `scripts/medieval_road_graph.lua` with `LINK_RADIUS = 64.0` planar elmos and no engine calls.
   - Public graph functions: `planarDist`, `buildEdges`, `adjacency`, `componentCount`, `componentOf`, `isConnected`, `connectedToNetwork`, `networkSummary`.
   - `GG.MedievalLogistics` query API:
     - `RoadNetworkSummary(teamID)` -> `{ nodes, edges, components, isolated, largest }`.
     - `RoadConnected(teamID, keyA, keyB)` -> shared connected component between two tracked road feature IDs.
     - `PointOnRoadNetwork(teamID, x, z)` -> point within `LINK_RADIUS` of any tracked road node.
   - Road lifecycle tracking remains team-isolated and updates on `FeatureCreated`/`FeatureDestroyed`.
   - Probe step at frame 160 builds a 3-road chain plus an isolated road and echoes graph queries.
   - Focused tests: 28 passing (`tests/test_phase3_slice3.py`). Current full suite: 172 passing.

## How to Run the Slice 3 Tests and Probe

```pwsh
# Slice 3 (Phase 3) focused tests (28 new: pure graph module + gadget wiring/behavior checks)
python -m pytest tests/test_phase3_slice3.py -q

# Full suite (172 passing as of this slice)
python -m pytest tests -q

# Headless probe (syncs source into the SDD, runs the pinned Recoil headless engine)
python tools/launch/run_phase2_slice2_probe.py

# Inspect Phase 3 probe output (Slice 1 road/tech + Slice 2 damage + Slice 3 roadgraph)
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"
```

Note: there is no dedicated Slice 3 (Phase 3) probe script; the roadgraph probe step lives in
`gadget_phase2_test_forces.lua` and runs inside the existing headless Phase 2 probe.

## Engine startup caveats (observed, not fixed)

The checked-in `tools/runtime/infolog.txt` is from a headless run and contains these startup
conditions. They are runtime-environment caveats, not proof of subsystem success:

- SMF splat-detail texture fallback: `Invalid SMF splatDetailTex maps/irrelevant.tga. Creating fallback texture`.
- `Error: Could not finalize groundFX texture atlas. Use fewer/smaller textures.`
- Missing font: `[RmlUi] Failed to load font face from Fonts/FreeMonoBold.ttf`.
- Missing feature def followed by a Lua error: `could not find FeatureDef "ad0_senegal_2"` and
  `libs/s11n/feature_s11n.lua:186: bad argument #1 to 'SetFeatureMoveCtrl' (number expected, got nil)`.
- Missing COB scripts for settlement units (`medieval_town_center`, `medieval_house`,
  `medieval_granary`, `medieval_lumber_camp`) — expected, since these use Lua scripts.
- Loopback socket warning: normal for a local headless probe.

## Observed Slice 3 log excerpts (from `tools/runtime/infolog.txt`)

Initial road creation and graph state:

```text
[t=00:00:06.463575][f=0000120] PHASE3 ROAD placed ftr=21063 team=0 x=2608 z=3584
[t=00:00:06.463642][f=0000120] PHASE3 ROADGRAPH team=0 nodes=1 edges=0 components=1 isolated=1 largest=1
```

Graph build-up and connectivity queries:

```text
[t=00:00:07.780112][f=0000160] PHASE3 PROBE roadgraph nodes=5 edges=2 components=3 isolated=2 largest=3
[t=00:00:07.780172][f=0000160] PHASE3 PROBE roadgraph connected-first-last=true
[t=00:00:07.780206][f=0000160] PHASE3 PROBE roadgraph connected-chain-isolated=false
[t=00:00:07.780232][f=0000160] PHASE3 PROBE roadgraph point-on-network=true
[t=00:00:07.780254][f=0000160] PHASE3 PROBE roadgraph point-off-network=false
```

Bridge-removal echo observed in the focused gadget harness (`tests/test_phase3_slice3.py`), which
verifies the chain splits into two isolated nodes after removing the middle road. This exact line
is not present in the current checked-in `infolog.txt`, so it is not claimed as an engine-run
observation:

```text
PHASE3 ROAD removed ftr=102 team=0
```

## Slice 3 Known Limitations

- **Query API, not gameplay**: Slice 3 adds graph queries and lifecycle tracking only. There is no
  player-issued road placement, no villager road build option, and no connectivity-based gameplay
  enforcement yet.
- **Headless audio caveat**: no audio or CEG assets exist in the repo. `gadget_medieval_fx.lua`
  only echoes to the log; unit-def `soundstart`/`soundhit`/`explosionGenerator` entries are
  comments. Verify sound via a full (non-headless) client run, not the headless probe.
- **Provisional tuning values**: upkeep rates (2/2/3), `STARVATION_HP_FRACTION = 0.05`, and road
  cost/speed values are first-cut placeholders, not play-tested. Weapon tuning remains unchanged
  from Phase 1 (sword range 45 / 150 dmg; longbow range 380 / 90 dmg; lance range 55 / 240 dmg).
- **Starvation is HP-only, not death**: starving units lose 5% current HP per tick and never die
  from starvation (`starvedHealth` clamps above 0; no `DestroyUnit` for upkeep).
- **Tick cadence is frame-based**: one tick = `UPKEEP_TICK_FRAMES = 90` engine frames; no
  wall-clock conversion or catch-up logic.
- **Bridge-removal evidence is unit-test-only**: the checked-in engine log has no
  `PHASE3 ROAD removed` line; do not cite engine evidence for destruction splitting until a probe
  step removes a road feature and a fresh `infolog.txt` is captured.

## What's Next: Phase 3 gameplay integration (pending design)

- Player-issued road placement and connectivity gameplay integration. This is a design decision,
  not an implementation task yet; do not assume Phase 3 is complete.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Slice 3 focused tests
python -m pytest tests/test_phase3_slice3.py -q

# 3. Run the headless probe and inspect Phase 3 output
python tools/launch/run_phase2_slice2_probe.py
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"

# 4. Review roadmap
cat docs/phase-3.md
```
