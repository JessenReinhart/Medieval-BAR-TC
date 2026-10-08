# Handoff: Medieval-BAR-TC (Phase 3 Slice 4 road-build command landed; Phase 3 gameplay integration still open)

Date: 2026-10-08
Branch: `medieval-total-conversion`
Last work: Phase 3 Slice 4 — player-issued road placement via custom command `CMD_BUILD_ROAD = 371922`
with deferred `GameFrame` execution, plus `CanPlaceRoad` / `PlaceRoad` on `GG.MedievalLogistics`.

Scope note: Slice 4 places roads by command, not by buildoptions. Roads are FEATURES
(`gamedata/featuredefs.lua`, `medieval_road`), so unitdef buildoptions cannot place them and
`AllowUnitCreation` does not fire for them. Villager build options remain wall/tower only.
Movement-speed enforcement is DEFERRED pending a verified engine speed API.

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
   - Road feature `medieval_road` (non-blocking, cost wood=5/stone=2); query-only `ROAD_SPEED_MULT = 1.5` within 48-elmo proximity (`gamedata/featuredefs.lua`, `scripts/medieval_logistics.lua`). Querying this value does not change movement.
   - Blacksmith tech tree: `iron_swords` (+25% infantry melee), `plate_armor` (+25% infantry/cavalry HP), `masonry` (+50% wall/tower HP); synced gamerules `team_<id>_tech_<techID>`.
   - Fortifications: `medieval_wall` (2x2, 2500 HP) and `medieval_tower` (3x3, 600 sight); unit cost enforced via `AllowUnitCreation` (units, not road features).
   - Gadget `gadget_medieval_logistics.lua` (layer 3 synced) exposing `GG.MedievalLogistics`.
   - 131 pytest tests passing at Phase 3 Slice 1 completion (historical count).

6. **Phase 3 Slice 2 (Build Handling, Damage Scaling)** — complete and verified:
   - Road build handling: `isBuildable` / `roadBuildQueueValidation` in `scripts/medieval_logistics.lua`.
   - Wall/tower build options: `medieval_wall` / `medieval_tower` added to villager `buildoptions` (`units/medieval_villager.lua`); those buildoptions do not include roads. Slice 2 had no road command; Slice 4 adds a separate custom command.
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
   - Focused tests: 28 passing (`tests/test_phase3_slice3.py`). Historical full suite: 172 passing.

8. **Phase 3 Slice 4 (Player-issued Road Placement)** — implemented:
    - `CMD_BUILD_ROAD = 371922`, params `{x, z}`; villager-only validation in `AllowCommand`, intent consumed and executed in `GameFrame`.
    - Validation covers finite coordinates, available map bounds, 32-elmo spacing and stock affordability; cost wood=5/stone=2.
    - Execution revalidates, withdraws via `Transact`, creates the feature at ground height, and refunds via `Deposit` if creation fails. `Transact` is not itself a refund operation.
    - `GG.MedievalLogistics.CanPlaceRoad` / `.PlaceRoad` exposed. Roads are placed by command, not villager buildoptions.
    - Engine log lines 575-585 show order 371922 at frame 200, feature creation at frame 201 under
      team 0, and a `too_close` duplicate refusal with the count unchanged at 6.
    - 25 Slice 4 tests; full suite: **197 passed** (`python -m pytest tests -q`).

## How to Run the Slice 4 Tests and Probe

```pwsh
# Slice 4 (Phase 3) focused tests (25 new: pure placement validation + gadget wiring/execution checks)
python -m pytest tests/test_phase3_slice4.py -q

# Full suite (197 passing as of this slice)
python -m pytest tests -q

# Headless probe (syncs source into the SDD, runs the pinned Recoil headless engine)
python tools/launch/run_phase2_slice2_probe.py

# Inspect Phase 3 probe output (Slice 1 road/tech + Slice 2 damage + Slice 3 roadgraph + Slice 4 road-cmd)
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"
```

Note: there is no dedicated Slice 4 probe script; the road-cmd probe step lives in
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

## Observed Slice 4 log excerpts (from `tools/runtime/infolog.txt`)

Road-build command end-to-end (issuing team 0, ordered spot `(2600, 3700)`):

```text
[t=00:00:09.350537][f=0000200] PHASE3 PROBE road-cmd precheck team=0 canPlace=true
[t=00:00:09.350624][f=0000200] PHASE3 PROBE road-cmd order1 sent unit=3375 team=0 cmd=371922 at=(2600, 3700)
[t=00:00:09.382353][f=0000201] PHASE3 ROAD placed ftr=23800 team=0 x=2600 z=3700
[t=00:00:09.382410][f=0000201] PHASE3 ROADGRAPH team=0 nodes=6 edges=2 components=4 isolated=3 largest=3
[t=00:00:09.382437][f=0000201] PHASE3 PROBE road-cmd placed team=0 reason=ok ftr=23800 x=2600 z=3700
[t=00:00:09.382467][f=0000201] PHASE3 PROBE road-cmd summary team=0 RoadCount=6
[t=00:00:09.382495][f=0000201] PHASE3 PROBE road-cmd roadgraph team=0 nodes=6 edges=2 components=4 isolated=3 largest=3
[t=00:00:09.382514][f=0000201] PHASE3 PROBE road-cmd retry-precheck team=0 canPlace=false (expect false)
[t=00:00:09.382541][f=0000201] PHASE3 PROBE road-cmd refused team=0 reason=too_close
[t=00:00:09.382552][f=0000201] PHASE3 PROBE road-cmd order2 sent unit=3375 team=0 cmd=371922 at=(2600, 3700) (expect refusal)
[t=00:00:09.382566][f=0000201] PHASE3 PROBE road-cmd final team=0 RoadCount=6 (expect unchanged)
```

These lines establish team-0 tracking, next-frame placement, and duplicate refusal with count 6.
They do not contain before/after wood and stone measurements. Resource withdrawal follows the
reviewed `Transact` path and harness tests; exact engine resource deltas are not measured here.

## Slice 4 Known Limitations

- **Roads are placed by command, not buildoptions**: roads are FEATURES (`gamedata/featuredefs.lua`,
  `medieval_road`), so unitdef buildoptions cannot place them and `AllowUnitCreation` does not fire
  for them. The command path (`CMD_BUILD_ROAD = 371922`) is the only player-issued placement route.
- **Movement-speed enforcement is DEFERRED**: no verified engine speed-mutator API has been
  identified. A partial `.engine-src` extraction shows no `SetUnitSpeed` / `SpeedMod` style mutator
  hits, but a partial extraction cannot prove API absence — the full engine source has not been
  searched. No velocity changes are claimed; speed remains a query-only multiplier via
  `GG.MedievalLogistics.GetSpeedMultiplier`, and the query does not change movement.
- **Feature ownership is fixed, not verified universally**: `Spring.CreateFeature` now receives
  `heading=0` and the issuing `teamID` as the sixth argument, and the fresh log shows
  `PHASE3 ROAD placed ftr=23800 team=0` with `RoadCount=6` for team 0. Spacing refusal
  (`too_close`) and the unchanged count are engine-verified in this run as well. The earlier
  team-2 mis-attribution is resolved for this probe map and team layout; other team counts or
  allocations have not been re-run.
- **Descriptor and coordinate paths**: the villager carries a `CMDTYPE.ICON_MAP` descriptor
  (`Build Road`, action `buildroad`) inserted via `Spring.InsertUnitCmdDesc`. The UI click path can
  deliver `{x, y, z}`; the probe and public API use `{x, z}`. `AllowCommand` reads only the first
  two params as `(x, z)` and ignores a third, so both forms place at ground height of `(x, z)`.
- **Construction timing**: `GameFrame` executes the queued intent on the next frame after
  `AllowCommand`; the road feature appears instantly with no travel or build time.
- **Spacing and land scope**: `ROAD_PLACEMENT_MIN_SPACING = 32.0` is enforced per issuing team
  against that team's tracked roads only; another team's roads do not block placement. The check is
  planar `{x, z}` distance plus map bounds (`off_map`); buildable or land-flagged terrain is not
  additionally restricted.

## What's Next: Phase 3 gameplay integration (pending design)

- Movement-speed enforcement pending a verified engine speed API; connectivity gameplay
  enforcement remains open. Do not assume Phase 3 is complete.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Slice 4 focused tests
python -m pytest tests/test_phase3_slice4.py -q

# 3. Run the headless probe and inspect Phase 3 output
python tools/launch/run_phase2_slice2_probe.py
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"

# 4. Review roadmap
cat docs/phase-3.md
```
