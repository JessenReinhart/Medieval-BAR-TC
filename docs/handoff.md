# Handoff: Medieval-BAR-TC (Phases 1–7 complete)

Date: 2026-10-13
Branch: `medieval-total-conversion`
Status: Phases 1–7 complete. **v0.7.0**. **1825 tests pass**, 81 Lua files clean (0 syntax errors), 6/6 engine probe verdicts PASS.

### Phase 5 Status by Slice

1. **Slice 1 — Victory/Defeat Engine (COMPLETE)**: `scripts/medieval_victory.lua` pure
   evaluator + `luarules/gadgets/gadget_medieval_victory.lua` (`GG.MedievalVictory`), conquest /
   tc_destruction / regicide (`medieval_king`) / surrender, `Spring.GameOver` wiring. 99 tests.
2. **Slice 2 — Medieval HUD (COMPLETE)**: `scripts/medieval_hud.lua` formatter + `gadget_medieval_hud.lua`
   synced publisher + `LuaUI/Widgets/gui_medieval_hud.lua` widget (modoption `medievalhud`, default on).
   95 tests.
3. **Slice 3 — Market & Trade (COMPLETE)**: `scripts/medieval_market.lua` elastic barter (no gold
   resource), `gadget_medieval_market.lua` (`GG.MedievalMarket`), `medieval_market` unit (haul hub).
   117 tests.
4. **Slice 4 — Garrisoning (COMPLETE)**: `scripts/medieval_garrison.lua` + `gadget_medieval_garrison.lua`
   (`GG.MedievalGarrison`), TC/tower transport fields (cap 10/4), shelter healing. 114 tests.
   _Deviation:_ TC cap = 10 (doc said 8); no `tower_arrow` weapondef.
5. **Slice 5 — Tactics & Single Damage Pipeline (COMPLETE)**: `scripts/medieval_tactics.lua` +
   `gadget_medieval_tactics.lua` now owns the sole `UnitPreDamaged`, composing
   `base × tech × supply × matrix × garrison × tactics` (charge/flank/brace/stance),
   `medieval_spearman` anti-cavalry. Logistics gadget's hook neutralized, displaced tests re-pointed.
   75 tests.
6. **Slice 6 — Integration Probe (COMPLETE)**: `gadget_phase5_slice6_integration_probe.lua` (layer 10)
   end-to-end skirmish to `tc_destruction`/`GameOver`, runner + startscript. 32 tests.

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
5. **Slice 5 — Transport & Hauler Units (COMPLETE)**:
   - Civilian hauler `medieval_cart` (`units/medieval_cart.lua`, LUS `scripts/medieval_cart.lua`, pop 0, non-military).
   - Pure-Lua hauler policy `scripts/medieval_haul.lua` (storage hub discovery, resource ordering, route selection pairing surplus to deficit).
   - Synced gadget `luarules/gadgets/gadget_medieval_hauling.lua` (cart/hub tracking, road-speed mutator enforcement, live haul jobs, `GG.MedievalEconomy.Transact` settlement, `HaulSummary`/`HaulRoute`/`HaulHubStock` on `GG.MedievalLogistics`).
   - Probe runner `tools/launch/run_phase2_slice5_probe.py` and probe stage in `luarules/gadgets/gadget_phase2_test_forces.lua` (f=1060–1260).
   - Headless probe PASS (f=1124–1200): `road-speed-verdict PASS` (`onroad=0.08 offroad=0.05 applied=22.50 expect=22.50 base=15.00 source=mutator`), `route-verdict PASS` (`from=medieval_lumber_camp to=medieval_blacksmith kind=wood amount=25`), `delivery-verdict PASS` (`before=0 after=25 amount=25 delivered=1`).
   - Probe fix: wood is pinned at `HAUL_WOOD_TARGET = 50` (mid-band) because production consumes ~2 wood/frame above the haul layer; the previous pin at 26 was read as 24 and missed the `HAUL_STEP = 25` floor.
   - 51 tests in `tests/test_phase4_slice5.py`.
6. **Slice 6 — Basic Medieval Skirmish AI (COMPLETE)**:
   - Pure-Lua policy `scripts/medieval_skirmish_ai.lua` (villager dispatch, house expansion, road stubs, recruitment, army march orders).
   - Synced gadget `luarules/gadgets/gadget_medieval_skirmish_ai.lua` (layer 5, modoption `skirmishai=1`, 30-frame cadence, `GG.MedievalSkirmishAI` API).
   - Dedicated probe gadget `luarules/gadgets/gadget_phase4_slice6_skirmish_probe.lua`, startscript `tools/launch/startscript_slice6.txt`, runner `tools/launch/run_phase2_slice6_probe.py`.
   - All five headless verdicts PASS: harvest, road, house, recruit, attack (f=60–180).
   - 90 tests in `tests/test_phase4_slice6.py`.

### Test & Syntax Counts

- `python tests/check_lua_syntax.py` -> 59 lua files, 0 errors.
- `python -m pytest tests -q` -> 582 passed in 1.96s.

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

## What's Next: Phase 6 (Balance Pass & Content Polish)

- Phase 5 is complete (Slices 1–6). Remaining work is a balance-tuning and polish pass, not new
  subsystems: see `docs/phase-5.md` "Scope boundaries" (lines 373) for the explicit out-of-scope list.
- Outstanding Phase 5 follow-ups (recorded deviations, do not silently change):
  - `docs/phase-5.md` Slice 4 text still says TC cap 8 and a `tower_arrow` weapondef; implementation
    ships TC cap 10 and no tower weapon (flagged by the Slice 4 agent).
  - Slice 2 `popLine` uses `"Pop: 12/40"` (colon) per the task spec, overriding doc line 133's
    colon-less `"Pop 12/40"`.
  - Slice 6 end-to-end headless integration probe (`python tools/launch/run_phase5_slice6_probe.py`)
    executed against `tools/engine/recoil_2026.07.04/spring-headless.exe`: **ALL 6 VERDICTS PASSED**
    (`settlement-start`, `economy-flow`, `military-engagement`, `tc-destroyed`, `victory-gameover`,
    `probe-complete`).

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q
python tests/check_lua_syntax.py

# 2. Phase 5 focused tests
python -m pytest tests/test_phase5_slice1.py tests/test_phase5_slice6.py -q

# 3. Re-run headless match probe
python tools/launch/run_phase5_slice6_probe.py
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE5 INTEGRATION"

# 4. Review roadmap (Phase 6 is the balance pass)
cat docs/phase-5.md
cat docs/handoff.md
```

## Phase 6 (balance pass) — COMPLETE

Spec: `docs/phase-6.md` (5 slices, disjoint file ownership, verification gate).

| Slice | Scope | Status |
| --- | --- | --- |
| 1 | Economic pacing (villager/house costs & build times) | COMPLETE — 26 tests |
| 2 | Combat matrix & counter-matchups | COMPLETE — 22 tests, numbers already balanced |
| 3 | Logistics/hauling/craft pacing (blacksmith/fletcher) | COMPLETE — 11 tests |
| 4 | Skirmish-AI pacing & reactive strategy | COMPLETE — 18 tests |
| 5 | Content polish (modoptions/descriptions/HUD) + final verification | COMPLETE — 4 tests |

Phase 6 tuning decisions:
- Villager `buildCostMetal` 50→40, `buildTime` 25→20, `resource_cost_food` 50→40; house `buildTime` 30→25 (4 villagers + 1 house ≤ 90 frames, no food stall).
- Blacksmith `buildTime` 50→60, `resource_cost_iron` 50→80; fletcher `buildTime` 45→55, `resource_cost_wood` 80→90.
- Skirmish AI: `HOUSE_POP_BUFFER` 2→3, `GATHER_TARGETS.food` 100→110; added reactive counter-recruit (`ROLE_OF`/`COUNTER_RECRUIT`/`counterRecruit`). Tower 1500→1800 HP / 600→700 sight; wall 2500→2800 HP; king 400→500 sight.
- Veteran-tier HP inversion fixed: men_at_arms 350→1600 (>infantry 1200), knight 550→2900 (>cavalry 2200), crossbow 160→1000 (>archer 750).
- Combat matrix, haul/logistics constants, market constants: verified balanced on paper, left pinned by existing suite.
- Dropped `(Phase 1 prototype placeholder)` from infantry/archer/cavalry descriptions.
- Modoptions probe toggles renamed to player-facing names (Victory Conditions / Market & Trade / Garrisoning / Combat Tactics).

Final gate (all green):
- `python tests/check_lua_syntax.py` → 77 files, 0 errors.
- `python -m pytest tests -q` → **1195 passed** (1114 baseline + 81 new).
- `python tools/launch/run_phase5_slice6_probe.py` → 6/6 PASS (settlement-start f=40, economy-flow f=100, military-engagement f=160, tc-destroyed f=260, victory-gameover f=300, probe-complete f=300; winner=1 reason=tc_destruction).

## Phase 7 (Asset Conversion, Audio, FX & Polish) — COMPLETE (2026-10-12)

Spec: `docs/phase-7.md` (6 slices).
User confirmed decisions:
- Priority order: "Feel" fastest (Sound, UI/UX, projectile FX).
- Animation fidelity: Lightweight procedural/piece animation in LUS (`scripts/*.lua`).
- Map: Retain Quicksilver Remake (no dedicated map in this phase).

| Slice | Scope | Status |
| --- | --- | --- |
| 1 | Audio Pipeline & Combat/Economy Soundscape | COMPLETE — 6 tests |
| 2 | Combat FX, Projectiles & Visual Impact | COMPLETE — 25 tests |
| 3 | Full Static Model & Texture Coverage (22 units/buildings) | COMPLETE — 30 tests |
| 4 | Lightweight LUS Piece Animation & Motion Dynamics | COMPLETE — 116 tests |
| 5 | Minimap, Build Icons & UI Polish | COMPLETE — 44 tests |
| 6 | Integration Probe & Final Verification Gate | COMPLETE (2026-10-12) — gate only |

### Phase 7 Slice 5 — Minimap, Build Icons & UI Polish (COMPLETE)

Engine contract verified against `beyond-all-reason/RecoilEngine` sources before writing
anything (`.engine-src/` only holds the game-side files):

- `UnitDef.cpp`: `buildPicName = udTable.GetString("buildPic", "")` and
  `iconName = udTable.GetString("iconType", "default")`.
- `UnitDrawerData.cpp::SetUnitDefImage`: an empty `buildPic` resolves
  `unitpics/<unitdef name>.{dds,png,pcx,bmp}`; a set `buildPic` resolves
  `unitpics/<buildPic>`; a miss falls back to a solid red dummy bitmap.
- `IconHandler.cpp::LoadIcons` reads `gamedata/icontypes.lua` and parses only
  `bitmap`, `size`, `distance`, `radiusAdjust`, `u0/v0/u1/v1`, `drawOrder`.
  Missing/unknown `iconType` degrades to the `default` type
  (`GetIconIdxOrDefault`), which the engine builds from
  `bitmaps/defaultradardot.png` (white RGB + alpha symbol, tinted with team colour).

Delivered:

- `tools/assets/generate_unitpics.py` → 22 distinct 128×128 PNGs in `unitpics/`
  (original GPL-v2 art; BAR buildpics are CC-BY-NC-ND and cannot be reused).
- `tools/assets/generate_minimap_icons.py` + `gamedata/icontypes.lua` → 11 themed
  radar icon types (swords/spear/bow/horse/shield/hammer/cart/crown/tent/storehouse/tower)
  as 64×64 white-on-transparent PNGs in `bitmaps/icons/`.
- Every `units/*.lua` def now sets `buildpic = "<unitdef>.png"` and a thematic `iconType`.
- `modoptions.lua`: `medievalaudio` (Medieval Combat & Economy Audio, default on) and
  `medievalbuildicons` (Medieval Build Icons, default on).
- `luarules/gadgets/gadget_medieval_fx.lua` routes every `Spring.PlaySoundFile` through one
  `medievalaudio`-gated choke point, publishes `medieval_audio` as a game rules param, and
  leaves the `PHASE2 FX` synced log lines untouched so probes still see them when muted.
- `LuaUI/Widgets/gui_medieval_build_icons.lua` restores plain `default` radar dots when
  `medievalbuildicons` is off (guarded with `pcall`; no-op while the option is on).
- `tests/test_phase7_slice5.py` — 44 tests.

Deviations: the spec's `LuaUI/Widgets/gui_medieval_hud.lua` entry is not where the icon
switch belongs; the HUD widget is untouched and the new option is owned by a dedicated
widget instead.

### Phase 7 Slice 6 — Final Integration Probe & Verification Gate (COMPLETE, 2026-10-12)

Phase 7 is closed. No new subsystem or test module was added in this slice; it is a pure
regression gate over the whole repository. The spec's `tests/test_phase7_slice6.py` was
not created — the existing suite already covers every Slice 1–5 artifact, so the gate
re-runs it plus the headless integration probe.

Gate results (2026-10-12):

- `python tests/check_lua_syntax.py` → `Checked 79 lua files; 0 errors found.`
- `python -m pytest tests -q` → **1416 passed** in 7.28s (1195 Phase 6 baseline + 221
  Phase 7: Slice 1 = 6, Slice 2 = 25, Slice 3 = 30, Slice 4 = 116, Slice 5 = 44).
- `python tools/launch/run_phase5_slice6_probe.py` → **6/6 PASS**. Verbatim engine log:

```
[t=00:00:04.432126][f=0000020] PHASE5 INTEGRATION setup starting f=20
[t=00:00:04.437437][f=0000020] PHASE5 INTEGRATION setup done f=20 tc0=550
[t=00:00:05.090828][f=0000040] PHASE5 INTEGRATION settlement-start PASS f=40 ally0-tcs=3 ally1-tcs=3 ally0-units=3 ally1-units=14 ally0-stock=1070 ally1-stock=818
[t=00:00:07.096417][f=0000100] PHASE5 INTEGRATION economy-flow PASS f=100 live0=true live1=true pulse=true src=live food0=290 food1=66
[t=00:00:09.089902][f=0000160] PHASE5 INTEGRATION military-engagement PASS f=160 damage=false attacks=15 src=observed
[t=00:00:12.431200][f=0000260] PHASE5 INTEGRATION scripted TC destruction ally0-tc=550
[t=00:00:12.431229][f=0000260] PHASE5 INTEGRATION tc-destroyed PASS f=260 src=live
[t=00:00:13.768367][f=0000300] PHASE5 INTEGRATION victory-gameover PASS winner=1 reason=tc_destruction f=300
[t=00:00:13.768395][f=0000300] PHASE5 INTEGRATION probe-complete PASS f=300 gameover-frame=n/a
```

Runner summary: `SLICE 6 INTEGRATION PROBE: ALL VERDICTS PASSED`.

Note: the engine still does not exit on `quitforce`; the runner reports
`Engine timed out after budget (expected; headless quitforce does not terminate this build)`
and harvests verdicts from `tools/runtime/infolog.txt`. This is the documented behaviour
in `AGENTS.md`, not a regression.

### Phase 7 Slice 9 — Asset Pipeline Refinement & LUS Animation Enhancement (integration verification, 2026-10-12)

Follow-up to Slices 3–4, delivered by two parallel agents and closed with a full
integration verification:

- **Asset pipeline** — target scope: teamcolor alpha-zero, prop/head/roof merge,
  multi-piece OBJ, and a regenerated `tools/assets/0ad-manifest.json` (18 models:
  13 units + 6 buildings, each with `obj`/`tex1`/`bounds`/`faces`/`vertices` provenance).
- **LUS animation enhancement** — procedural piece animation in `scripts/*.lua`
  (`medieval_infantry` / `medieval_archer` / `medieval_cavalry` / `medieval_villager` /
  `medieval_cart` / `medieval_catapult`), each built on a single `piece "base"` with
  `optPiece()` probing for optional sub-pieces (head/roof/shield) and falling back to
  the root piece.
- **Test coverage** — `tests/test_assets.py` (13), `tests/test_phase7_slice3.py` (30),
  `tests/test_phase7_slice4.py` (116), `tests/test_phase7_slice5.py` (44).

Verification (this session):

- `python tests/check_lua_syntax.py` → `Checked 79 lua files; 0 errors found.`
- `python -m pytest tests -q` → **1416 passed** in ~10s (test count unchanged from the
  Slice 6 gate: no new top-level test module was added).
- `python tools/launch/run_phase5_slice6_probe.py` → **6/6 PASS** (settlement-start,
  economy-flow, military-engagement, tc-destroyed, victory-gameover, probe-complete).
- GUI smoke test → `Get-Process spring` confirmed running; `tools/runtime/infolog.txt`
  shows **0** `.obj`/`.dds`/model load failures.

Fix applied during smoke test: `LuaUI/Widgets/gui_medieval_hud.lua` read the starvation
blink from `Spring.GetTimer()`, which Recoil exposes as a userdata (not a number), so
`DrawScreen()` raised `attempt to perform arithmetic on a userdata value` and the engine
removed the widget. Replaced both call sites with `Spring.GetGameSeconds()` and updated
the `Spring` mock in `tests/test_phase5_slice2.py` (95 tests still pass; full suite still
1416). Re-launch confirmed the widget error is gone.

Verification gap (RESOLVED 2026-10-13): the two targeted asset refinements are now
applied in `tools/assets/convert_0ad.py` and the outputs regenerated. The converter now
(1) zeroes `tex1` alpha on every converted DDS — Recoil's shader samples `tex1` alpha as
the team-color mask, so zeroing it removes the solid-blue team-color blob while preserving
the RGB bytes verbatim (DXT1 sources rewrapped as DXT5), (2) merges prop/head/roof into
named pieces via `resolve_model_pieces`, and (3) emits a multi-piece OBJ (`o`/`g`/`usemtl`
block per piece) via `render_obj`. `tools/assets/0ad-manifest.json` was regenerated: 18
models (7 units + 11 buildings), each recording `pieces`/`props_resolved`/`tex1`/`bounds`
with `props_ignored = 0` for every model. The earlier "medieval units will not show team
color" statement no longer applies — team color is deliberately neutralised by the
alpha-zero pass, so models render in their true diffuse colors.

Known non-fatal log noise (pre-existing, documented in slice-7 evidence): missing COB
scripts for the static settlement units (`could not load COB script scripts/medieval_*.cob`),
`feature_s11n.lua:186 SetFeatureMoveCtrl` in the base s11n lib, and missing Quicksilver
scar decals. None reference `.obj`/`.dds` and the models load clean.

### Phase 7 Slice 9 — Follow-up: Asset Pipeline Applied + Full Integration Verification (2026-10-13)

The slice-9 asset pipeline is now applied end-to-end (previously landed as code but not
yet reflected in the converter). `tools/assets/convert_0ad.py` + regenerated outputs:

- **Team-color alpha-zero** — `zero_dds_alpha()` zeroes every texel's alpha in each
  converted DDS (Recoil reads `tex1` alpha as the team-color mask); DXT1 sources are
  rewrapped as DXT5 to express "opaque RGB, zero alpha"; RGB bytes preserved verbatim.
- **Prop/head/roof merge** — `resolve_model_pieces()` resolves actor `<props>` into named
  pieces; every model now reports `props_ignored = 0` (blacksmith resolves 108 props into
  41 pieces; archer 8 → 7 pieces; villager head merged).
- **Multi-piece OBJ export** — `render_obj()` emits one `o`/`usemtl` block per piece (the
  `g` group line was dropped: a matching `g` makes Assimp duplicate each mesh into `xx00`
  twins, so LUS animates the wrong half). `optPiece()` no longer always falls back to
  `base`; infantry/archer/cavalry now animate the real `weapon` piece.
- **Manifest** — `tools/assets/0ad-manifest.json` regenerated: 18 models (7 units +
  11 buildings) with `pieces`/`props_resolved`/`tex1`/`bounds` provenance.
- **Tests** — `tests/test_phase7_slice9_rendering_fixes.py` (78 tests) covers three
  regressions: CCW winding/normal agreement (backface culling), DXT5 texture loading +
  zeroed alpha, and LUS animation syntax/call-in lifecycles. Experimental slice-9 test
  drafts were removed in favour of this consolidated file.

Full integration verification (this session, 2026-10-13):

- `python tests/check_lua_syntax.py` → `Checked 79 lua files; 0 errors found.`
- `python -m pytest tests -q` → **1494 passed** in ~11s (Phase 6 baseline + Phase 7 +
  slice-9 rendering fixes).
- `python tools/launch/run_phase5_slice6_probe.py` → **6/6 PASS** (settlement-start,
  economy-flow, military-engagement, tc-destroyed, victory-gameover, probe-complete).
- GUI smoke test → `spring.exe` running; `infolog.txt` shows no `.obj`/`.dds`/`.tex1`/
  `.lua` load failures and no `props`/`piece`/`tex2`/`teamcolor` warnings (only the
  pre-existing missing-COB and `feature_s11n` noise recorded above).

### Phase 7 Slice 10 — Skeletal Articulation: Bone-Split Meshes + Whole-Body LUS Rigs (2026-10-13)

Skeletal hulls were previously exported as one static OBJ piece, so the LUS rigs could
only rotate the whole model. Slice 10 consumes the 0 A.D. PMD vertex blend weights to
split each skinned mesh along its bones, and drives the resulting parts as a real
whole-body rig.

**Bone splitting in `tools/assets/convert_0ad.py`**

- `parse_pmd` now returns the raw `SVertexBlend` payloads as `blends` — one 20-byte
  record per vertex (4 bone indices + 4 float weights) — so per-vertex influences
  survive parsing instead of being discarded. Indices are bounds-checked against
  `bone_count` (`>= bone_count` raises `PMDError`); the `255` "no bone" sentinel is
  preserved.
- `parse_skeleton(zf, xml_path)` reads `art/skeletons/<name>.xml` from `public.zip`,
  locates `<standard_skeleton>`, and returns bone names in document order, lowercased
  with the side marker normalised to `_l`/`_r`. Standard skeletons used:
  `biped.xml` (46 bones), `horse.xml` (49 bones), `bovidae_skeleton.xml`.
- `_primary_bones` / `_dominant_bone` resolve the highest-weight influence per face;
  `split_skinned_mesh` partitions the hull into one named piece per dominant bone, with
  faces re-indexed 0-based inside each piece. Vertices naming no bone stay in a `base`
  piece, so a split model keeps both its named parts and the root piece the LUS scripts
  anchor on. Unskinned hulls (`bone_count <= 1` or no blends) return `base` unchanged.
- `_skeleton_for(actor_path, want_mesh)` routes an actor to its skeleton — `horse`
  tested first (every horse mesh also lives under `skeletal/`), then `skeletal/` →
  `biped.xml`, then `bovidae`/`cattle`/`cow`/`bull` → `bovidae_skeleton.xml`; static
  hulls return `""`.
- `resolve_model_pieces` routes skeletal actors through the splitter and static hulls
  straight to a single `base` piece.

**Articulated multi-piece OBJ models** (regenerated `objects3d/0ad/*.obj` +
`tools/assets/0ad-manifest.json`, `props_ignored = 0` everywhere):

| Model | Pieces | Skeleton |
| --- | --- | --- |
| `medieval_villager` | 23 | `biped.xml` |
| `medieval_spearman` | 25 | `biped.xml` |
| `medieval_infantry` | 28 | `biped.xml` |
| `medieval_archer` | 28 | `biped.xml` |
| `medieval_king` | 28 | `biped.xml` |
| `medieval_cavalry` (horse + rider) | 43 | `horse.xml` |

Piece names come straight from the skeleton, so the LUS scripts address real anatomy
rather than merged blobs: bipeds expose `hip`, `spine`, `chest`, `neck`, `head`,
`shoulder_l/r`, `arm_l/r`, `forearm_l/r`, `hand_l/r`, `finger_l/r`, `fingertip_l/r`,
`thigh_l/r`, `leg_l/r` (shin), `foot_l/r`, plus resolved props (`helmet`, `weapon`,
`shield`, quivers, greaves, `cape_hd_hoplite`). Cavalry exposes the quadruped chain
`spine`/`spine1`/`spine2`, `neck`/`neck1`/`neck2`, `head`, `l/r_ear`,
`l/r_shoulder`, `l/r_upperarm`, `l/r_arm`, `l/r_forearm`, `l/r_hand`, `l/r_femur`,
`l/r_thigh`, `l/r_leg`, `l/r_shin`, `l/r_hoof`, `l/r_hoof_back`, `belly`,
`tail2..tail7`, plus a mounted `rider` piece with its own `helmet`/`weapon`.
Buildings remain static contexts: single `base` hull plus prop merges.

**Whole-body LUS rigs (`scripts/medieval_*.lua`)**

- Humanoid walk/attack rigs (`medieval_infantry`, `medieval_archer`,
  `medieval_villager`, `medieval_cavalry` rider) animate the split pieces: contact and
  passing poses turn `thigh_l/r`, `leg_l/r`, `foot_l/r`, counter-swing `arm_l/r` /
  `forearm_l/r`, and lean `chest` / twist `spine` over a `Move` bob on `hip`. Walk
  cycles run under `script.StartMoving`/`StopMoving` with `SIG_MOVE` masking; combat
  thrust and aim pitch under `SIG_ATTACK` via `script.AimWeapon*` / `script.FireWeapon*`.
- `medieval_cavalry` drives a quadruped 4-beat gait: the `GALLOP` table holds four
  beats per stride (`pitch`/`roll`/`lift`/`bob`/`neck`/`tail`) — beat 1 puts diagonal
  pair A forward (left hind femur with right shoulder), beat 3 the mirrored pair B, and
  the even beats are the airborne suspension where the hooves gather under the hull.
  The hull bobs on `root`, with `spine`, `neck`, tail chain and `rider` following.
- Every bone reference goes through `optPiece()` and falls back to `base`, so a model
  that failed to split still animates instead of erroring.

**Tests** — `tests/test_phase7_slice10_articulation.py` (**21 tests**): `parse_pmd`
blend payloads (`blends` length == positions, 20-byte records, weight range, index
bounds, sentinel tracking, static meshes with `bone_count == 0`); `parse_skeleton`
(46 bones for `biped.xml`, 49 for `horse.xml`, document order preserved, side-marker
normalisation, rejection of a missing standard skeleton and an absent entry, horse
skeleton selection, unskinned fallback); `split_skinned_mesh` (named pieces, hull
partition, per-piece geometry, sentinel influences, dominant-bone face assignment,
unweighted faces → `base`, unknown bone-index sanitisation); `resolve_model_pieces`
routing (skeletal actor, cavalry actor, static hull kept whole).

Verification (Phase 7 Slice 10):

- `python tests/check_lua_syntax.py` → `Checked 79 lua files; 0 errors found.`
- `python -m pytest tests -q` → **1515 passed** in ~7s.
- `python -m pytest tests/test_phase7_slice10_articulation.py -q` → **21 passed**.

### Phase 7 Slice 11 — 0 A.D. Skeletal Animation Port & Baked-Keyframe Player (2026-10-13)

Ported native 0 A.D. skeletal animations into Recoil LUS by parsing the shipped binary `.dae.cached.psa` format, baking root-relative keyframe tracks with coordinate corrections matching the OBJ converter, and playing them via a dedicated pure Lua player module.

**Binary PSA format (`.dae.cached.psa`) & Parser tools**

- Parsed 0 A.D. binary `.dae.cached.psa` files (`PSSA` magic, version 1): 12-byte `FileHeader`, empty legacy name string, f32 `frameTime` (ms), u32 `numKeys` (= bone count), u32 `numFrames`, followed by dense frame-major 28-byte keys (`tx, ty, tz` f32 translation + `qx, qy, qz, qw` quaternion rotation).
- Translation AND rotation are world/root-relative (decomposed at COLLADA -> PSA import; no parent FK needed at runtime).
- Added `tools/assets/parse_psa.py`: binary reader and archive extractor (all 1220 PSA files in `public.zip` parse cleanly).
- Added `tools/assets/read_psa_content.py`: validates world-pose proof against skeleton bones, verifies Y-180 yaw and scale=8 coordinate corrections.
- Added `tools/assets/convert_0ad_anim.py`: bakes extracted animation clips into compact Lua tables under `scripts/animdata/`.

**Bake coordinate correction & generated clip datasets**

- Bake correction matches the OBJ export rigid transform: `t' = 8 * (-tx, ty, -tz)` and `q' = (0, 1, 0, 0)` left-multiplied (left Hamilton product `Q_y180 * q`).
- Emits `scripts/animdata/*.lua` per unit with normalized piece names aligned with `0ad-manifest.json` and bone order:
  - Bipeds (`medieval_infantry.lua`, `medieval_archer.lua`, `medieval_villager.lua`, `medieval_spearman.lua`): 25 pieces; clips `walk`, `run`, `idle`, `attack_melee`, `build`, `death`.
  - Cavalry (`medieval_cavalry.lua`): 39 horse pieces; clips `walk`, `trot`, `gallop`, `idle`, `attack_melee`, `death`.

**Recoil engine piece pivot findings (`research/OBJ_piece_pivot_FINDINGS.md`)**

- Recoil OBJ pieces loaded via Assimp have no node transforms; therefore, `Turn` rotates strictly about the piece-local origin (which collapses to model origin `(0, 0, 0)` for unoffset OBJ groups).
- `Move` and `Turn` destinations are absolute relative to the piece's rest transform (`destination` argument in `Spring.UnitScript.Move` / `Turn`).
- Verified in engine source (`rts/Sim/Misc/Transform.hpp`, `rts/Rendering/Models/3DModelPiece.cpp`, `rts/Rendering/Models/AssParser.cpp`, Spring LUS reference). Reference: `research/OBJ_piece_pivot_FINDINGS.md`.

**Pure-module player (`scripts/anim_player.lua`) & LUS integration**

- `scripts/anim_player.lua`: pure-module baked-keyframe player (`q_rel = q_k * conj(q0)`; `Turn` and `Move` both take absolute destinations; the combined term `d = t_k - R * t0` supplies the piece-local-origin pivot compensation and is fed straight into `Move`).
- Wired into `scripts/medieval_infantry.lua`, `scripts/medieval_archer.lua`, `scripts/medieval_villager.lua`, and `scripts/medieval_cavalry.lua`; spearman and king share `scripts/medieval_infantry.lua`.

**Tests & verification**

- `tests/test_parse_psa.py` (**11 tests**): PSA header/payload deserialization, key counts, frame-major indexing.
- `tests/test_phase7_slice11_bake.py` (**10 tests**): bone count alignment (46 biped, 49 horse), clip catalog completeness, Y-180 yaw + scale=8 rigid transforms, Hamilton quaternion math, bone name normalization, manifest round-tripping.
- `tests/test_phase7_slice12_anim.py` (**30 tests**): piece pivot invariants, rigid pose verification (`d = t_k - R * t0`), Euler angle inverse conventions (`anim_player.angles` vs `anim_player.eulerMatrix`), looping/one-shot frame sampling.
- Full pytest suite: **1566 passed** in ~6s.
- Lua syntax check: `python tests/check_lua_syntax.py` → **80 files, 0 errors**.
- Headless integration probe: all verdicts PASS (6/6).

**Next:** Phase 7 is the final planned phase in `docs/phase-7.md`; the roadmap is complete
through Phase 7. Any further work is a new phase (balance/content or map authoring) and
should get its own spec document.

### Phase 7 Slice 12 follow-up — Emit-Mode Regression Fixed (2026-10-15)

- **Symptom:** after switching the baked-keyframe player to emit per-frame *deltas*, the
  in-game walk loop stopped moving (models collapsed toward rest).
- **Root cause:** Recoil/Spring `Move`/`Turn` take an **absolute `destination`** (relative
  to rest), not an incremental delta. Feeding frame-to-frame deltas placed pieces at tiny
  near-zero absolute offsets instead of the baked pose. Reference: Spring LUS docs
  (`Spring.UnitScript.Move(piece, axis, destination[, speed])`).
- **Fix:** reverted `scripts/anim_player.lua` to absolute `emit`, removed the incremental
  `emitFrame` and its `lastEmit`/`lastClip` delta state; kept the pure `frameTargets`
  split. All four LUS wiring scripts returned to `animPlayer.emit(...)`.
- **Verification:** `tests/test_phase7_slice12_anim.py` + `tests/test_phase7_piece_bindings.py`
  40 passed; `check_lua_syntax.py` 0 errors; windowed launch shows
  `infantry walk driven=25` / `archer walk driven=25` per frame (walk restored).
- **Open (unchanged from the audit):** the "Rayman detach/explode" was a piece-wiring issue
  (hip-binding collision, unbound groups), not accumulate-vs-absolute; `driven=25` confirms
  all 25 baked bones bind. If detachment persists at runtime, trace handle→bone pose mapping,
  not the emit mode.

### Phase 7 Slice 12 follow-up — Baked Death Clips Verified In-Engine (2026-10-19)

The baked `death` clip was already wired into `script.Killed` for all four articulated
LUS scripts in Slice 11, but nothing proved it ran. This pass makes it observable and
verifies every articulated unitdef against the live engine.

- **Diagnostics (`scripts/medieval_infantry.lua`, `medieval_archer.lua`,
  `medieval_villager.lua`, `medieval_cavalry.lua`):** the baked `Killed` branch now sums
  the pieces driven across the one-shot and emits
  `PHASE7 DEATH unit=<id> clip=death baked=1 driven=<piece-frames>`; the procedural
  fallback emits `PHASE7 DEATH unit=<id> clip=procedural baked=0`. Unit scripts stay
  pure LUS (no `UnitDefs` / `GG.` / `VFS.` tokens); the probe correlates unit IDs to
  unitdefs through its own spawn lines.
- **Probe gadget** `luarules/gadgets/gadget_phase7_death_probe.lua`, gated on the new
  `medievalanimprobe` modoption (default off). It funds team 0 before spawning (the
  recruitment gadget tears down unitdefs the team cannot pay for), spawns all nine
  articulated defs in rows on the flat haul lane, kills them in staggered groups with
  `Spring.AddUnitDamage` (a plain `DestroyUnit` skips `Killed`), and reports lifecycle
  state at frame 260.
- **Runner** `tools/launch/run_phase7_death_probe.py` + `startscript_phase7_death.txt`.
- **Coverage:** infantry, spearman, men-at-arms, king (`medieval_infantry.lua`);
  archer, crossbow (`medieval_archer.lua`); villager; cavalry, knight
  (`medieval_cavalry.lua`).
- **Tests:** `tests/test_phase7_death_wiring.py` (21) covers the source contract, a Lua
  sandbox that asserts the death clip drives Turn/Move on real piece names, and probe
  coverage/runner parity.

Engine result (9/9 PASS, `driven` = piece-frames over the one-shot):

```text
PHASE7 DEATH unit=16909 clip=death baked=1 driven=950   # infantry
PHASE7 DEATH unit=24324 clip=death baked=1 driven=912   # spearman
PHASE7 DEATH unit=9848  clip=death baked=1 driven=950   # men-at-arms
PHASE7 DEATH unit=25734 clip=death baked=1 driven=950   # king
PHASE7 DEATH unit=23744 clip=death baked=1 driven=950   # archer
PHASE7 DEATH unit=4961  clip=death baked=1 driven=950   # crossbow
PHASE7 DEATH unit=27521 clip=death baked=1 driven=874   # villager
PHASE7 DEATH unit=12086 clip=death baked=1 driven=1482  # cavalry
PHASE7 DEATH unit=10614 clip=death baked=1 driven=1482  # knight
```

Verification: `python -m pytest tests -q` → **1614 passed**;
`python tests/check_lua_syntax.py` → **81 files, 0 errors**;
`python tools/launch/run_phase7_death_probe.py` → **ALL VERDICTS PASSED**.

### Phase 7 Slice 12 follow-up — Procedural Fallback Verified In-Engine (2026-10-19)

The death probe now verifies both animation paths.

- **Hook:** each articulated LUS `Killed` calls `forceProceduralFallback()`, which reads the
  `medieval_force_procedural_death` unit rule behind a `pcall`. A normal match (rule unset)
  and a bare-Lua harness both keep playing the baked clip; when the probe sets the rule the
  baked branch is skipped and the procedural tumble runs, emitting
  `PHASE7 DEATH unit=<id> clip=procedural baked=0`.
- **Modoption:** `medievalanimfallback` (default off). With `medievalanimprobe=1` the probe
  gadget sets the per-unit rule before the lethal damage on every spawn.
- **Startscript:** `tools/launch/startscript_phase7_death_fallback.txt`.
- **Runner:** `run_phase7_death_probe.py` now runs both modes in one invocation, prints a
  verdict per mode, and exits non-zero if either mode fails.

Engine result: baked 9/9 PASS, procedural 9/9 PASS (`PHASE7 DEATH PROBE: ALL MODES PASSED`).

Verification: `python -m pytest tests -q` -> **1825 passed**;
`python tests/check_lua_syntax.py` -> **81 files, 0 errors**;
`python tools/launch/run_phase7_death_probe.py` -> **both modes PASS**.
