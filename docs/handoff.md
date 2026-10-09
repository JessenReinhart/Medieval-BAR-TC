# Handoff: Medieval-BAR-TC (Phase 4 Slices 1–4 complete; Slice 5 in-progress savepoint)

Date: 2026-10-09
Branch: `medieval-total-conversion`
Status: Wrapped up for the day; 492 tests pass, 56 Lua files clean; all committed and pushed.

### Phase 4 Status by Slice

1. **Slice 1 — Siege Warfare Core (COMPLETE, commit `a09cf28` / merged prior)**:
   - `medieval_catapult` unit (0 A.D. lithobolos OBJ/DDS), ballistic arc, AoE crush damage, aim-dead-zone LUS. Headless probe PASS (f=360–570).
2. **Slice 2 — Damage Types & Fortification Destruction (COMPLETE, commit `bc2191e`)**:
   - `scripts/medieval_damage_types.lua` matrix (siege 3.0x vs fort, melee/ranged 0.25x vs fort). Weapon and armor class tags. Headless probe PASS (f=570–600).
3. **Slice 3 — Production Chains (COMPLETE, commit `28370ba`)**:
   - `medieval_blacksmith` and `medieval_fletcher` crafting buildings.
   - `luarules/gadgets/gadget_production_chains.lua` converts iron+wood into swords and bows.
   - Recruitment gating: cavalry/catapult require sword stock > 0, archer requires bow stock > 0.
   - Headless probe PASS (f=620–880). 30 tests in `tests/test_phase4_slice3.py`.
4. **Slice 4 — Military Upgrades & Veteran Tiers (COMPLETE, commit `333923e`)**:
   - 3 advanced unit tiers: `medieval_men_at_arms`, `medieval_crossbow`, `medieval_knight`.
   - Tech tree registry in `scripts/medieval_logistics.lua`: `veteran_infantry`, `crossbow_tech`, `chivalry`.
   - Tech prerequisite gating on recruitment + multiplicative damage scaling stacking with supply bonus.
   - Headless probe PASS (f=920–1030). 63 tests in `tests/test_phase4_slice4.py`.
5. **Slice 5 — Transport & Hauler Units (IN-PROGRESS SAVEPOINT)**:
   - Civilian hauler `medieval_cart` (`units/medieval_cart.lua`, LUS `scripts/medieval_cart.lua`, pop 0, non-military).
   - Pure-Lua hauler policy `scripts/medieval_haul.lua` (storage hub discovery, resource ordering, route selection pairing surplus to deficit).
   - Synced gadget `luarules/gadgets/gadget_medieval_hauling.lua` (cart tracking, road-speed mutator enforcement, live haul jobs, `GG.MedievalEconomy.Transact` settlement).
   - Probe runner `tools/launch/run_phase2_slice5_probe.py` and probe stage in `luarules/gadgets/gadget_phase2_test_forces.lua` (f=1060–1260).
   - VERIFIED: road-speed mutator PASS (`onroad=0.08`, `offroad=0.05`, 1.50x target).
   - REMAINING: live hub deficit trigger window in probe needs fine-tuning so `route-verdict` and `delivery-verdict` complete cleanly.
   - 51 tests in `tests/test_phase4_slice5.py`.
6. **Slice 6 — Basic Medieval Skirmish AI (NEXT)**:
   - Full automated skirmish match probe planned.

### Test & Syntax Counts

- `python tests/check_lua_syntax.py` -> 56 lua files, 0 errors.
- `python -m pytest tests -q` -> 492 passed in 1.15s.

Previous work: Phase 4 Slice 1 — siege warfare core. New `medieval_catapult` unit built from the
0 A.D. Hellenic lithobolos (982 verts / 556 tris), a slow heavy `catapult` weapon def (range 550,
reloadtime 5.0, velocity 350, damage 500, AoE 48), a LUS with a 120-elmo aim dead zone, and a
headless probe stage (frames 360-570) reporting six deterministic `PASS` verdicts.

Earlier work: Phase 3 Slice 7 — supply bonuses and road-aware pathing. Finished mobile units
(`def.canMove == true`) within `SUPPLY_RADIUS = 96.0` of a **road-connected** supply endpoint gain
an additive bonus (`0.10` per endpoint, capped at `0.50`), published per unit as rules params and
applied to outgoing damage in `UnitPreDamaged`. Villager node/drop-off selection is cost-based and
prefers road-connected targets.

Scope note: Slice 4 places roads by command, not by buildoptions. Roads are FEATURES
(`gamedata/featuredefs.lua`, `medieval_road`), so unitdef buildoptions cannot place them and
`AllowUnitCreation` does not fire for them. Villager build options remain wall/tower only.
Movement-speed enforcement (Slice 6), supply bonuses, and pathing integration (Slice 7) are
implemented and verified (see `docs/slice7-probe-evidence.md`).

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
   - Road feature `medieval_road` (non-blocking, cost wood=5/stone=2); query-only `ROAD_SPEED_MULT = 1.5` within 48-elmo proximity (`gamedata/featuredefs.lua`, `scripts/medieval_logistics.lua`). Querying this value does not change movement; Slice 6 enforces the same 1.5 policy through the engine speed mutator.
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

9. **Phase 3 Slice 5 (Building Connectivity Enforcement)** — implemented:
    - `BUILD_LINK_RADIUS = 64.0` supply-endpoint placement gating plus `BuildingConnected` / `BuildingConnectivitySummary`.
    - 17 Slice 5 tests; full suite: **214 passed**.

10. **Phase 3 Slice 6 (Road Movement-Speed Enforcement)** — implemented:
    - Pure policy in `scripts/medieval_logistics.lua`: `speedMultiplier`, `targetSpeed`, `isEligibleSpeedUnitDef`.
    - Gadget tracking of eligible finished units per team; 15-frame throttled scan; `Spring.MoveCtrl.SetGroundMoveTypeData` application with an observational `SetUnitRulesParam` fallback.
    - `GG.MedievalLogistics.GetSpeedState(unitID)`.
    - 26 Slice 6 tests; full suite: **240 passed**; Lua syntax clean (44 files, 0 errors).

11. **Phase 3 Slice 7 (Supply Bonuses and Road-Aware Pathing)** — implemented:
    - Pure supply policy in `scripts/medieval_logistics.lua`: `SUPPLY_RADIUS = 96.0`,
      `SUPPLY_BONUS_PER_ENDPOINT = 0.10`, `SUPPLY_BONUS_MAX = 0.50`, `supplyEndpointCount`,
      `supplyBonus`, `supplyState`, `isInSupply`, `isSupplyEligibleUnitDef` (mobile units only:
      `def.canMove == true`; the engine's derived `isBuilding` is false/nil for static buildings).
      Only endpoints that are
      themselves road-connected (`BUILD_LINK_RADIUS = 64.0`) project supply, so road destruction
      drops the bonus immediately.
    - Gadget: finished non-building units tracked per team; a shared 15-frame scan recomputes state
      and publishes `medieval_supply_bonus`, `medieval_supply_mult`, `medieval_in_supply`.
      `UnitPreDamaged` scales a supplied medieval attacker's outgoing damage by `1 + bonus`, after
      the `iron_swords` multiplier.
    - APIs: `GetSupplyState`, `SupplyBonus`, `InSupply`, `SupplyStateAt`, `SupplyEndpointCountAt`,
      `SupplySummary`, `PathCostMultiplier`, `PathCost`, `RoadRoutePreferred`.
    - Pure pathing policy: `ROAD_PATH_COST_MULT = 0.75`, `UNSUPPLIED_PATH_COST_MULT = 1.5`,
      `pathCostMultiplier`, `pathCost`, `roadRoutePreferred`; `scripts/medieval_gather.lua` adds
      `PATH_COST_UNSUPPLIED = 1.5`, `pathCost`, and `bestCandidate`.
    - Gather gadget pathing: node selection uses `PointOnRoadNetwork`, drop-off selection uses
      `SupplyStateAt`; with no roads all candidates share one penalty and nearest-wins is preserved.
    - Fixed a latent `local`-ordering bug: `nearestDropoff` referenced `dropoffs`/`allowsResource`
      before their declarations, so both were nil globals and every delivery selection raised on
      `pairs(nil)`. The declarations are now hoisted above the function.
    - 61 Slice 7 tests (`tests/test_phase3_slice7.py`); full suite: **302 passed**; Lua syntax clean
      (44 files, 0 errors). Live-engine probe evidence landed: see `docs/slice7-probe-evidence.md`.

12. **Phase 4 Slice 1 (Siege Warfare Core)** — implemented and verified:
    - New `medieval_catapult` unitdef: `Catapult`, LAND, `movementclass = "TANK3"` (the repo's 3x3
      vehicle move def; `BOT2` declares a 2x2 footprint and would contradict `footprintX/Z = 3`),
      600 HP, `speed = 18`, `maxVelocity = 1.2`, costs wood 120 / stone 40 / iron 10.
    - Art from the 0 A.D. Hellenic lithobolos: `objects3d/0ad/medieval_catapult.obj` (982 verts /
      556 tris), `unittextures/0ad/medieval_catapult.dds`. `tools/assets/convert_0ad.py` now records
      the full actor archive path per unit (the old `ACTOR_PREFIX` hard-coded Athenians) and stores
      post-scale OBJ bounds in the manifest.
    - `gamedata/weapondefs.lua` `catapult`: Cannon, range 550, `minRange = 120`, reloadtime 5.0,
      velocity 350, `myGravity = 0.2`, `heightBoostFactor = 1.5`, damage 500, AoE 48 @ 0.5 edge,
      `noSelfDamage = true`.
    - `scripts/medieval_catapult.lua` LUS: `AimWeapon1`/`FireWeapon1`/`AimFromWeapon1`/`QueryWeapon1`
      plus the unnumbered forms, all resolving to the single `base` piece, with a 120-elmo aim dead
      zone and aim/fire rules params for the probe.
    - Three engine-verified defects found and fixed (details in `docs/phase-4.md`): `minRange` is not
      a Recoil tag (`Unknown tag "minrange"` — dead zone moved into the LUS); `myGravity = 0.6` gave
      a ballistic reach of only `350^2/0.6 ~= 227` elmos against a 550 range, so the shot spawned
      under the terrain and dealt zero damage; `maxAngleDif = 60` combined with an unconditional LUS
      `return true` let the engine fire off-axis. `noSelfDamage` is required because the converted
      mesh has no muzzle piece and the 48-elmo AoE would destroy the launcher on the first shot.
    - 28 Slice 1 tests (`tests/test_phase4_slice1.py`); full suite: **330 passed**; Lua syntax clean
      (46 files, 0 errors). Live-engine probe: six deterministic `PASS` verdicts at frames 360-570.

## How to Run the Slice 6 and Slice 7 Tests and Probe

```pwsh
# Slice 7 (Phase 3) focused tests (61: pure supply policy + pathing cost + damage scaling + gather pathing)
python -m pytest tests/test_phase3_slice7.py -q

# Slice 6 (Phase 3) focused tests (26: pure speed policy + gadget tracking/apply/lifecycle)
python -m pytest tests/test_phase3_slice6.py -q

# Slice 5 (Phase 3) focused tests (17)
python -m pytest tests/test_phase3_slice5.py -q

# Full suite (330 passing as of Phase 4 Slice 1)
python -m pytest tests -q

# Phase 4 Slice 1 (siege catapult) focused tests (28)
python -m pytest tests/test_phase4_slice1.py -q

# Lua syntax check (46 files, expect 0 errors)
python tests/check_lua_syntax.py

# Headless probe (syncs source into the SDD, runs the pinned Recoil headless engine)
python tools/launch/run_phase2_slice2_probe.py

# Inspect Phase 3 probe output (Slice 1 road/tech + Slice 2 damage + Slice 3 roadgraph + Slice 4 road-cmd + Slice 5 building-connectivity + Slice 6 road-speed)
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"

# Inspect Phase 4 Slice 1 probe output (siege catapult spawn/aim/fire/damage verdicts)
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE4"
```

Note: there is no dedicated Slice 4, Slice 5, or Slice 6 probe script; those probe steps live in
`gadget_phase2_test_forces.lua` and run inside the existing headless Phase 2 probe.

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
- **Movement-speed enforcement was DEFERRED at Slice 4** — now **superseded by Slice 6**, which
  enforces the multiplier through the verified `Spring.MoveCtrl.SetGroundMoveTypeData`. At Slice 4
  no verified engine speed-mutator API had been identified: a partial `.engine-src` extraction
  showed no `SetUnitSpeed` / `SpeedMod` style mutator hits, but a partial extraction cannot prove API
  absence. At that time speed remained a query-only multiplier via
  `GG.MedievalLogistics.GetSpeedMultiplier`.
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

## Phase 3 Slice 5 (building connectivity enforcement) — implemented:

- **Rule**: supply-endpoint buildings (`medieval_town_center`, `medieval_granary`,
  `medieval_lumber_camp`, via `dropoff` customparam with casing/truth normalization) must lie
  within `BUILD_LINK_RADIUS = 64.0` planar elmos of a same-team road node when placed through
  `AllowUnitCreation`. Teams with no roads bootstrap freely (the rule never gates the first
  settlement); nil coordinates bypass the gate (no placement context).
- **Tracking**: finished endpoints tracked per team (`buildings[teamID]`), removed on
  `UnitDestroyed`/`UnitTaken`, re-tracked under the receiving team on `UnitGiven`.
- **APIs**: `GG.MedievalLogistics.BuildingConnected(teamID, unitID)` (live computation from the
  current road graph; road destruction disconnects immediately) and
  `BuildingConnectivitySummary(teamID)` -> `{ total, connected, disconnected }`.
- **Tests**: 17 focused (`tests/test_phase3_slice5.py`, real Lua harness: buildings are units,
  roads are features); full suite **214 passed**; Lua syntax clean (44 files).
- **Engine probe** (`tools/runtime/infolog.txt`, frames 220-228):
  ```text
  [f=0000220] PHASE3 PROBE building-connectivity baseline team=0 total=2 connected=0 disconnected=2
  [f=0000220] PHASE3 PROBE building-connectivity near-verdict f=220 team=0 PASS (unit=29462 connected=true)
  [f=0000220] PHASE3 PROBE building-connectivity far-verdict f=220 team=0 PASS (unit=5320 connected=false)
  [f=0000220] PHASE3 PROBE building-connectivity isolation-verdict f=220 otherTeam=1 PASS (otherTeamSeesNear=false)
  [f=0000220] PHASE3 PROBE building-connectivity summary team=0 total=4 connected=1 disconnected=3 PASS
  [f=0000224] PHASE3 PROBE building-connectivity destroyed far unit=5320 team=0
  [f=0000228] PHASE3 PROBE building-connectivity post-destroy team=0 total=3 connected=1 disconnected=2 (far unit removed)
  ```
- **Speed API verdict (corrected)**: the pinned engine (`2026.07.04`) does expose
  `Spring.MoveCtrl.SetGroundMoveTypeData` (`maxSpeed`, `maxWantedSpeed`, …) and `SetMoveDef`;
  see `docs/engine-speed-api-evidence.md`. Slice 5 does not use the mutator; Slice 6 does.

## Phase 3 Slice 6 (road movement-speed enforcement) — implemented:

- **Rule**: eligible finished ground units within `ROAD_PROXIMITY_RADIUS = 48.0` planar elmos of a
  **same-team** road move at `base * ROAD_SPEED_MULT = 1.5`, where `base` is
  `UnitDefs[unitDefID].speed` in elmos/sec. Off-road, the unit is restored to its baseline `base`.
  The 48-elmo proximity radius is used deliberately, not the 64-elmo road-graph `LINK_RADIUS`
  (which would over-report units as on-road).
- **Pure policy** (`scripts/medieval_logistics.lua`, no engine calls): `speedMultiplier(onRoad)`
  (`ROAD_SPEED_MULT` or `1.0`), `targetSpeed(baseSpeed, onRoad)` (returns `baseSpeed` untouched when
  it is not a number or `<= 0`; otherwise `baseSpeed * speedMultiplier(onRoad == true)`), and
  `isEligibleSpeedUnitDef(def)` (`def ~= nil and def.canMove == true`; every static def sets
  `canMove = false` and the engine reports `isBuilding = false/nil` for them;
  villagers are builders but stay eligible).
- **Tracking**: `speedMovers[teamID][unitID] = { base, onRoad, applied, source }`. Eligibility via
  the pure `isEligibleSpeedUnitDef`; units with an unknown base are never tracked (`reason=no_base`).
  `onRoad` reuses the existing point-on-road helper — no new distance math.
- **Throttle and application**: scan every `SPEED_SCAN_INTERVAL = 15` frames (0.5 s at 30 fps) in
  `GameFrame`, and write only when `target ~= state.applied`. Application order:
  `pcall Spring.MoveCtrl.SetGroundMoveTypeData(unitID, { maxSpeed = target, maxWantedSpeed = target })`
  -> `source = "mutator"` (enforcing); else
  `pcall Spring.SetUnitRulesParam(unitID, "medieval_speed_target", target)` -> `source = "rules-param"`
  (**observational only, non-enforcing**: the engine does not read that param, so no speed change
  occurs); else `source = "none"`. No path errors.
- **Lifecycle**: `UnitFinished` tracks eligible units; `UnitDestroyed`/`UnitTaken` remove;
  `UnitGiven` removes and re-tracks under the receiving team.
- **API**: `GG.MedievalLogistics.GetSpeedState(unitID)` -> live `{ base, onRoad, applied, source }`,
  or `nil` for unknown/ineligible units. Existing APIs are unchanged.
- **Out of scope** (documented, not implemented): air/hover and transported units, builder-assist
  interactions, per-slope effects.
- **Tests**: 26 focused (`tests/test_phase3_slice6.py`); full suite **240 passed**; Lua syntax clean
  (44 files, 0 errors).
- **Engine probe** (`tools/runtime/infolog.txt`, frames 238-302, `source=mutator`):
  ```text
  [f=0000242] PHASE3 PROBE road-speed state-a f=242 unit=14749 onRoad=true base=28.00 applied=42.00 source=mutator
  [f=0000242] PHASE3 PROBE road-speed state-b f=242 unit=8772 onRoad=false base=28.00 applied=28.00 source=none
  [f=0000242] PHASE3 PROBE road-speed onroad-verdict f=242 PASS (A onRoad=true expect=true, B onRoad=false expect=false)
  [f=0000242] PHASE3 PROBE road-speed applied-verdict f=242 PASS (A applied=42.00 expect=42.00, B applied=28.00 expect=28.00)
  [f=0000242] PHASE3 PROBE road-speed source-verdict f=242 PASS (A source=mutator expect=mutator|rules-param)
  [f=0000274] PHASE3 PROBE road-speed velocity f=274 A=14749 velA=1.45 posA=(2822, 3886) B=8772 velB=0.98 posB=(4314, 4201) delta=0.47 PASS(soft)
  [f=0000302] PHASE3 PROBE road-speed restore-state f=302 unit=14749 onRoad=false base=28.00 applied=28.00 source=mutator
  [f=0000302] PHASE3 PROBE road-speed restore-verdict f=302 PASS (onRoad=false expect=false pass=true, applied=28.00 expect=28.00 pass=true, mode=set-position)
  ```
  The mutator path was taken (`source=mutator`, `applied=42.00 = 28 * 1.5`), not the rules-param
  fallback. The velocity check is soft by design (`PASS(soft)`); the hard verdicts are the state and
  restore checks. No Lua errors occur inside the probe window.

## What's Next: Phase 4 Slice 3 (Production Chains: Blacksmith & Fletcher)

- Phase 4 Slice 2 (damage types & fortification destruction) is **implemented and verified in
  Recoil**: 18 new tests (`tests/test_phase4_slice2.py`; full suite 348), Lua syntax clean (47
  files, 0 errors), and two deterministic `PASS` verdicts from the headless probe:
  `PHASE4 DMATRIX siege-vs-wall PASS` (dealt=1353.5, matrix=3.00) and
  `PHASE4 DMATRIX melee-vs-wall PASS` (dealt=84.6, matrix=0.25). See `docs/phase-4.md`.
- Slice 3 adds production chains: `medieval_blacksmith` converts Iron → weapon equipment and
  `medieval_fletcher` converts Wood → bow equipment, gating high-tier recruitment on equipment
  stock (not just food/pop).
- Probe note for Slice 3+ (carried forward): `medieval_catapult` has a 5.0 s reload (150 frames)
  and the engine applies a full initial reload at creation, so a spawned catapult's first shot
  lands ~142 frames later. Budget slow-weapon probe windows accordingly.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Phase 4 focused tests
python -m pytest tests/test_phase4_slice1.py tests/test_phase4_slice2.py -q

# 3. Run the headless probe and inspect Phase 3 / Phase 4 output
python tools/launch/run_phase2_slice2_probe.py
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3"
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE4 DMATRIX"

# 4. Review roadmap
cat docs/phase-4.md
```
