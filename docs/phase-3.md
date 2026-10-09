# Phase 3: Logistics, Tech Tree & Fortifications

Phase 3 Slice 7 (supply bonuses and road-aware pathing) is implemented and verified end-to-end in
the Recoil headless engine. The focused Slice 7 suite passes 61 tests; the full suite passes 302
tests, and `python tests/check_lua_syntax.py` checks 44 Lua files with 0 errors. Slice 7 adds a pure supply
policy (`SUPPLY_RADIUS = 96.0`, `SUPPLY_BONUS_PER_ENDPOINT = 0.10`, `SUPPLY_BONUS_MAX = 0.50`) in
which only **road-connected** supply endpoints project supply, publishes the resulting bonus per
unit as rules params, applies it to outgoing damage, and makes villager destination choice
cost-based so road-connected drop-offs and nodes are preferred.

Phase 3 Slice 6 (road movement-speed enforcement) is implemented and verified.
The focused Slice 6 suite passes 26 tests. Slice 6 turns the
pre-existing road speed query into an actual movement modifier: eligible finished ground units
within `ROAD_PROXIMITY_RADIUS = 48.0` of a same-team road are set to
`base * ROAD_SPEED_MULT (1.5)` through `Spring.MoveCtrl.SetGroundMoveTypeData`, with a
documented observational (non-enforcing) rules-param fallback when the mutator is unavailable.
The engine speed API is real and now used: see `docs/engine-speed-api-evidence.md`. Slice 5
(road-network connectivity gameplay enforcement) added `BUILD_LINK_RADIUS = 64.0`
supply-endpoint placement gating plus per-team building connectivity tracking and query APIs.

## Pinned Upstream BAR Reference

- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`

## Scope and current behavior

1. **Road feature and speed query** — `medieval_road` is a feature, not a unit. It is non-blocking,
   costs `{ wood = 5, stone = 2 }`. `scripts/medieval_logistics.lua` exposes a query-only speed
   multiplier (`ROAD_SPEED_MULT = 1.5`, 48-elmo proximity radius). The query API itself does not
   change movement; Slice 6 (item 6) enforces the same policy through the engine speed mutator.
2. **Road graph (Slice 3)** — `scripts/medieval_road_graph.lua` is a pure module. It uses
   `LINK_RADIUS = 64.0` planar elmos: road nodes at or below that distance share an edge. The
   gadget tracks `{x, z}` road positions by team and recomputes graph state after road creation
   and removal.
3. **Technology upgrades** — Blacksmith research tracks `iron_swords`, `plate_armor`, and
   `masonry` through synced team rules and `GG.MedievalLogistics`.
4. **Fortifications** — `medieval_wall` and `medieval_tower` are available to villagers and have
   resource costs enforced by the logistics gadget.
5. **Building connectivity (Slice 5)** — supply-endpoint buildings (dropoff customparam:
   `medieval_town_center`, `medieval_granary`, `medieval_lumber_camp`) must lie within
   `BUILD_LINK_RADIUS = 64.0` planar elmos of a same-team road node at placement time. When the
   team has no roads yet, endpoints bootstrap freely (the rule does not gate the first
   settlement). Finished endpoints are tracked per team and re-tracked on transfer; the query
   APIs compute connectivity live from the current road graph, so road destruction immediately
   disconnects buildings.
6. **Road movement-speed enforcement (Slice 6)** — finished eligible ground units within
   `ROAD_PROXIMITY_RADIUS = 48.0` of a same-team road are set to `base * ROAD_SPEED_MULT = 1.5`
   and restored to their baseline `UnitDefs[id].speed` when off-road. Air/hover/transported units,
   builder-assist interactions, and per-slope effects are out of scope.

Speed and connectivity are now enforced in part, but this is not full logistics gameplay.
`AllowUnitCreation` gates unit creation and
unit costs; it does not provide a road-feature placement command. The villager currently has only
wall and tower fortification build options for this feature work. Roads are placed only by the
custom command (`CMD_BUILD_ROAD = 371922`), not by buildoptions.

## Architecture

- **Pure road graph**: `scripts/medieval_road_graph.lua` — no engine calls. Public functions:
  `planarDist`, `buildEdges`, `adjacency`, `componentCount`, `componentOf`, `isConnected`,
  `connectedToNetwork`, and `networkSummary`. Constant: `LINK_RADIUS = 64.0`.
- **Pure supply and pathing policy (Slice 7)**: `scripts/medieval_logistics.lua` also exports
  `supplyEndpointCount(buildings, roads, x, z, supplyRadius, linkRadius)` (counts only endpoints
  that are BOTH road-connected within `BUILD_LINK_RADIUS` and within `SUPPLY_RADIUS = 96.0`),
  `supplyBonus(count, perEndpoint, maxBonus)` (additive `0.10` per endpoint, clamped at `0.50`),
  `supplyState(...)` -> `{ count, bonus, multiplier, inSupply }`, `isInSupply(...)`,
  `isSupplyEligibleUnitDef(def)` (mobile units only: `def.canMove == true`; the engine's derived
  `isBuilding` is false/nil for static buildings here, so it cannot discriminate), and the pathing cost model
  `pathCostMultiplier(onRoad, targetSupplied)` / `pathCost(distance, onRoad, targetSupplied)` /
  `roadRoutePreferred(openCost, roadCost)` with `ROAD_PATH_COST_MULT = 0.75` and
  `UNSUPPLIED_PATH_COST_MULT = 1.5`. `scripts/medieval_gather.lua` adds `PATH_COST_UNSUPPLIED = 1.5`
  plus `pathCost(ux, uz, tx, tz, supplied)` and `bestCandidate(candidates, ux, uz)`.
- **Pure connectivity policy**: `scripts/medieval_logistics.lua` now exports
  `isBuildingConnected(roads, x, z, radius)` and `isSupplyEndpointConnected` (alias), plus
  `isSupplyEndpointDef(def)` which reads the `dropoff` customparam with engine-uppercase
  (`customParams`) and lowercase source (`customparams`) fallback and normalizes bool/number/
  string truth. `BUILD_LINK_RADIUS = 64.0`.
- **Pure speed policy (Slice 6)**: `scripts/medieval_logistics.lua` also exports
  `speedMultiplier(isOnRoad)` (`ROAD_SPEED_MULT = 1.5` when truthy, else `1.0`),
  `targetSpeed(baseSpeed, onRoad)` (returns `baseSpeed` untouched when it is not a number or is
  `<= 0`; otherwise `baseSpeed * speedMultiplier(onRoad == true)`), and
  `isEligibleSpeedUnitDef(def)` (`def ~= nil and def.canMove == true`; every static def sets
  `canMove = false` while the engine reports `isBuilding = false/nil` for them, so mobility is the
  reliable discriminator; villagers are builders but stay eligible).
- **Logistics gadget**: `luarules/gadgets/gadget_medieval_logistics.lua` tracks road feature
  lifecycle per team and exposes these graph queries through `GG.MedievalLogistics`:
  - `RoadNetworkSummary(teamID)` -> `{ nodes, edges, components, isolated, largest }`.
  - `RoadConnected(teamID, keyA, keyB)` -> whether two tracked road feature IDs share a component.
  - `PointOnRoadNetwork(teamID, x, z)` -> whether a point is within `LINK_RADIUS` of a road node.
  - Existing speed, research, damage, health, and road-count APIs remain available.
  - Slice 6 speed tracking: `speedMovers[teamID][unitID] = { base, onRoad, applied, source }`,
    where `base` is `UnitDefs[unitDefID].speed` (elmos/sec). A throttled scan runs every
    `SPEED_SCAN_INTERVAL = 15` frames (0.5 s at 30 fps) and recomputes `onRoad` with the existing
    point-on-road helper (48-elmo `ROAD_PROXIMITY_RADIUS`, not the 64-elmo road-graph
    `LINK_RADIUS`). Application order per mover:
    `Spring.MoveCtrl.SetGroundMoveTypeData(unitID, { maxSpeed = target, maxWantedSpeed = target })`
    via `pcall` -> `source = "mutator"` (enforcing); else
    `Spring.SetUnitRulesParam(unitID, "medieval_speed_target", target)` via `pcall` ->
    `source = "rules-param"` (**observational only**: the engine does not read this param, so no
    speed change happens); else `source = "none"`. No path ever errors.
  - `GetSpeedState(unitID)` -> the live `{ base, onRoad, applied, source }` table for a tracked
    mover, or `nil` when the unit is unknown/ineligible.
  - Slice 7 supply tracking: `supply[teamID][unitID] = { count, bonus, multiplier, inSupply }`,
    with `supplyBonusMovers[unitID] = { teamID, bonus }`. Finished non-building units are tracked;
    a shared `SUPPLY_SCAN_INTERVAL = 15` frame pass recomputes the state and publishes
    `medieval_supply_bonus`, `medieval_supply_mult`, and `medieval_in_supply` per unit via
    `Spring.SetUnitRulesParam`. `GetSupplyState(unitID)` computes live on first query.
  - Slice 7 damage enforcement: `UnitPreDamaged` multiplies outgoing damage by
    `1 + supplyBonus` for a supplied medieval attacker, after the `iron_swords` multiplier, so the
    two stack multiplicatively.
  - Slice 7 pathing: `luarules/gadgets/gadget_medieval_gather.lua` selects harvest nodes by
    `PointOnRoadNetwork` and drop-offs by `SupplyStateAt`, both through the pure `bestCandidate`
    cost model. With no roads every candidate carries the same penalty and nearest-wins behaviour
    is preserved.
- **Probe**: `luarules/gadgets/gadget_phase2_test_forces.lua` creates a three-node chain and an
  isolated node at frame 160, then logs summary and connectivity queries. It is a diagnostic probe,
  not a player command implementation.

## Historical Slice 1-7 counts

These are historical completion counts, not the current total:

- Slice 1: 131 tests passing.
- Slice 2: 144 tests passing.
- Slice 3: 172 tests passing (28 focused).
- Slice 4 focused tests: 25 passing.
- Slice 5 focused tests: 17 passing; full suite 214 passing.
- Slice 6 focused tests: 26 passing (`tests/test_phase3_slice6.py`).
- Slice 7 focused tests: 61 passing (`tests/test_phase3_slice7.py`).
- Current full suite: 302 passing.

## Verification

### Focused and full tests

```pwsh
python -m pytest tests/test_phase3_slice4.py -q
# 25 passed

python -m pytest tests/test_phase3_slice7.py -q
# 61 passed

python -m pytest tests/test_phase3_slice6.py -q
# 27 passed

python -m pytest tests -q
# 302 passed

python tests/check_lua_syntax.py
# Checked 44 lua files; 0 errors found.
```

### Headless engine probe

The existing probe script syncs source into the SDD and launches the pinned Recoil headless
executable. It is not a clean engine-start signal: the runtime log
`tools/runtime/infolog.txt` is **regenerated by each run and git-ignored** (not checked in), and
contains startup caveats including a fallback SMF splat-detail texture, groundFX texture-atlas
failure, missing `Fonts/FreeMonoBold.ttf`, a missing `ad0_senegal_2` feature followed by a
`SetFeatureMoveCtrl` Lua call error, and missing COB scripts for several settlement units. Treat
those as runtime-environment caveats, not as successful subsystem evidence.

Run the existing probe and inspect the freshly generated log:

```pwsh
python tools/launch/run_phase2_slice2_probe.py
Select-String -Path tools/runtime/infolog.txt -Pattern "PHASE3|ROADGRAPH|Error|Warning"
```

Observed initial road creation and graph state in `tools/runtime/infolog.txt`:

```text
[t=00:00:06.684162][f=0000120] PHASE3 ROAD placed ftr=15992 team=0 x=2608 z=3584
[t=00:00:06.684246][f=0000120] PHASE3 ROADGRAPH team=0 nodes=1 edges=0 components=1 isolated=1 largest=1
```

Observed graph query results from the same log:

```text
[t=00:00:08.030778][f=0000160] PHASE3 PROBE roadgraph nodes=5 edges=2 components=3 isolated=2 largest=3
[t=00:00:08.030804][f=0000160] PHASE3 PROBE roadgraph connected-first-last=true
[t=00:00:08.030826][f=0000160] PHASE3 PROBE roadgraph connected-chain-isolated=false
[t=00:00:08.030841][f=0000160] PHASE3 PROBE roadgraph point-on-network=true
[t=00:00:08.030853][f=0000160] PHASE3 PROBE roadgraph point-off-network=false
```

Bridge-removal behavior is covered by the focused Lua gadget harness, which observed this exact
removal echo and recomputed the chain as two isolated nodes. No corresponding bridge-removal line
is present in the checked-in engine `infolog.txt`, so it is not claimed as an engine log result:

```text
PHASE3 ROAD removed ftr=102 team=0
```

Observed Slice 4 road-build command end-to-end in `tools/runtime/infolog.txt` (frames 200-201; the
issuing team is team 0, the ordered spot is `(2600, 3700)`):

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

The same run retried a second order at the same spot and the engine refused it with `too_close`; the
road count stayed at 6 and the road was attributed to team 0 throughout (`ftr=23800 team=0`). This
matches the spacing-refusal path already covered by the focused Lua harness.

Observed Slice 6 road movement-speed enforcement end-to-end in `tools/runtime/infolog.txt` (probe
steps at frames 238-302; max simulated frame this run was 450). Unit A (`43`) is spawned on the
road chain, unit B (`28360`) off-road. These are the verbatim `road-speed` lines (the run emitted 15
`road-speed` lines in total; the set below is all of them):

```text
[t=00:00:10.518886][f=0000238] PHASE3 PROBE road-speed road-extend#1 ftr=25323 team=0 at=(2788, 3884)
[t=00:00:10.519017][f=0000238] PHASE3 PROBE road-speed road-extend#2 ftr=11042 team=0 at=(2848, 3884)
[t=00:00:10.519080][f=0000238] PHASE3 PROBE road-speed road-extend#3 ftr=29641 team=0 at=(2908, 3884)
[t=00:00:10.519422][f=0000238] PHASE3 PROBE road-speed spawned A=43 B=28360 team=0 A_at=(2788, 3884) B_at=(4300, 4200)
[t=00:00:10.643868][f=0000242] PHASE3 PROBE road-speed state-a f=242 unit=43 onRoad=true base=28.00 applied=42.00 source=mutator
[t=00:00:10.643934][f=0000242] PHASE3 PROBE road-speed state-b f=242 unit=28360 onRoad=false base=28.00 applied=28.00 source=none
[t=00:00:10.643980][f=0000242] PHASE3 PROBE road-speed onroad-verdict f=242 PASS (A onRoad=true expect=true, B onRoad=false expect=false)
[t=00:00:10.643992][f=0000242] PHASE3 PROBE road-speed applied-verdict f=242 PASS (A applied=42.00 expect=42.00, B applied=28.00 expect=28.00)
[t=00:00:10.644039][f=0000242] PHASE3 PROBE road-speed source-verdict f=242 PASS (A source=mutator expect=mutator|rules-param)
[t=00:00:10.720267][f=0000244] PHASE3 PROBE road-speed move-order f=244 A=43 -> (3400, 3884) B=28360 -> (4600, 4200)
[t=00:00:11.709138][f=0000274] PHASE3 PROBE road-speed velocity f=274 A=43 velA=1.45 posA=(2810, 3886) B=28360 velB=0.98 posB=(4314, 4201) delta=0.47 PASS(soft)
[t=00:00:12.520132][f=0000298] PHASE3 PROBE road-speed restore f=298 A=43 -> (3600, 4200) mode=set-position
[t=00:00:12.642040][f=0000302] PHASE3 PROBE road-speed restore-state f=302 unit=43 onRoad=false base=28.00 applied=28.00 source=mutator
[t=00:00:12.642117][f=0000302] PHASE3 PROBE road-speed restore-verdict f=302 PASS (onRoad=false expect=false pass=true, applied=28.00 expect=28.00 pass=true, mode=set-position)
[t=00:00:12.642152][f=0000302] PHASE3 PROBE road-speed summary f=302 team=0 A=43 B=28360 velocity=PASS(soft) velA>velB
```

What these lines support: on-road unit A reports `onRoad=true`, `base=28.00`, `applied=42.00`
(= 28 * 1.5), `source=mutator` — the engine mutator path was taken, not the rules-param fallback.
Off-road unit B reports `onRoad=false`, `applied=28.00` (baseline restored), and is untracked for
speed (`source=none`, because its state never changed from the baseline). After A is moved off-road
at frame 298, the frame-302 scan restores it to `applied=28.00` with `onRoad=false`. The velocity
check is soft by design (`PASS(soft)`, velA 1.45 > velB 0.98); the hard verdicts are the state and
restore checks. No Lua errors occur inside the probe window f=238-302; the only two
`Lua error|SCRIPT ERROR` matches in the log are the pre-existing pre-game
`feature_s11n.lua:186 SetFeatureMoveCtrl` errors at `f=-000001`.

## Slice roadmap

### Slice 1 — roads, tech tree, fortifications

- [x] Pure logistics module, road feature, tech rules, wall/tower definitions, gadget wiring.
- [x] Initial headless probe and logistics tests.

### Slice 2 — build handling and damage scaling

- [x] Resource validation and damage scaling tests.
- [x] Villager wall/tower build options.
- [x] Corrected scope: `AllowUnitCreation` is a unit-creation gate; it is not a road-feature
      command or road-feature placement implementation. Slice 2 did not add a road command; Slice 4 does.

### Slice 3 — road adjacency/connectivity queries

- [x] Pure graph API with `LINK_RADIUS = 64.0`.
- [x] Team-isolated road tracking on feature create/destroy.
- [x] `RoadNetworkSummary`, `RoadConnected`, and `PointOnRoadNetwork` on
      `GG.MedievalLogistics`.
- [x] Probe for initial graph state, chain connectivity, isolated-node rejection, and point queries.
- [x] Focused 28 tests and full 172-test verification.

### Slice 4 — player-issued road placement command

- [x] Pure road placement validation in `scripts/medieval_logistics.lua`:
      `ROAD_PLACEMENT_MIN_SPACING = 32.0`, `canPlaceRoad(x, z, existingRoads, stock, minSpacing)`.
- [x] Custom road-build command ID `CMD_BUILD_ROAD = 371922` registered via `RegisterCMDID` and
      intercepted via `gadgetHandler:RegisterAllowCommand(CMD.ANY)`.
- [x] `AllowCommand` validates issuer is a `medieval_villager`, rejects modifier queueing (`shift`,
      `alt`, `ctrl`, `right`), validates spacing (`ROAD_PLACEMENT_MIN_SPACING = 32`), map bounds,
      and resource affordability (`wood = 5, stone = 2`), then consumes order and queues intent into
      `pendingRoadBuilds`.
- [x] Deferred execution on `GameFrame`: charges resources via `GG.MedievalEconomy.Transact` and
      places the road feature via `Spring.CreateFeature("medieval_road", x, y, z, 0, teamID)` —
      heading 0, issuing team as the sixth argument. Construction is instant on the next frame; the
      feature appears without travel or build time. On placement failure, refunds cost via `Deposit`.
- [x] Command descriptor and coordinate path: the villager gets a `CMDTYPE.ICON_MAP` descriptor
      (`Build Road`, action `buildroad`) via `Spring.InsertUnitCmdDesc`. The UI click path can
      deliver `{x, y, z}`; the probe/API path sends `{x, z}`. `AllowCommand` reads only `params[1]`
      and `params[2]` as `(x, z)` and ignores any third component, so both forms resolve to ground
      placement at `(x, z)`.
- [x] Spacing and land scope: `ROAD_PLACEMENT_MIN_SPACING = 32.0` is enforced per issuing team
      against that team's tracked roads only; another team's roads do not block placement. The check
      is planar `{x, z}` distance plus map-bounds (`off_map`); it does not restrict to buildable or
      land-flagged terrain, so steep or impassable tiles are not excluded beyond the bounds check.
- [x] Public API additions on `GG.MedievalLogistics`: `CanPlaceRoad(teamID, x, z)` and
      `PlaceRoad(teamID, unitID, x, z)`.
- [x] Movement-speed enforcement was **DEFERRED** at Slice 4 (no verified engine speed-mutator API
      at the time; a partial `.engine-src` extraction showed no `SetUnitSpeed` / `SpeedMod` style
      mutator hits, and a partial extraction cannot prove API absence). **Superseded by Slice 6**,
      which uses the verified `Spring.MoveCtrl.SetGroundMoveTypeData`. At Slice 4,
      `GG.MedievalLogistics.GetSpeedMultiplier` and `IsOnRoad` remained query-only.
- [x] Focused 25 tests (`tests/test_phase3_slice4.py`) and full 197-test suite passing.

### Slice 5 — building connectivity enforcement

- [x] Pure connectivity policy in `scripts/medieval_logistics.lua`: `isBuildingConnected`,
  `isSupplyEndpointConnected` (alias), `isSupplyEndpointDef`, `BUILD_LINK_RADIUS = 64.0`.
- [x] Supply-endpoint placement gating in `AllowUnitCreation`; teams with no roads bootstrap freely.
- [x] Per-team endpoint tracking with re-track on transfer; `BuildingConnected` and
  `BuildingConnectivitySummary` on `GG.MedievalLogistics`.
- [x] Focused 17 tests (`tests/test_phase3_slice5.py`) and full 214-test suite passing.

### Slice 6 — road movement-speed enforcement

- [x] Rule: eligible finished ground units within `ROAD_PROXIMITY_RADIUS = 48.0` of a **same-team**
  road move at `base * ROAD_SPEED_MULT = 1.5`; off-road they return to their baseline
  `UnitDefs[unitDefID].speed` (elmos/sec). The 48-elmo proximity radius is used, not the 64-elmo
  road-graph `LINK_RADIUS` (which would over-report units as on-road).
- [x] Pure API in `scripts/medieval_logistics.lua` (no engine calls):
  `speedMultiplier(onRoad)` -> `ROAD_SPEED_MULT` or `1.0`;
  `targetSpeed(baseSpeed, onRoad)` -> returns `baseSpeed` untouched when it is not a number or is
  `<= 0`, otherwise `baseSpeed * speedMultiplier(onRoad == true)`;
  `isEligibleSpeedUnitDef(def)` -> `def ~= nil and def.canMove == true and def.isBuilding ~= true`
  (villagers are builders but stay eligible).
- [x] Gadget tracking: `speedMovers[teamID][unitID] = { base, onRoad, applied, source }`. Eligibility
  via the pure `isEligibleSpeedUnitDef`; `base` read from `UnitDefs[unitDefID].speed`. Units with an
  unknown base are never tracked (`reason=no_base`).
- [x] Throttled scan every `SPEED_SCAN_INTERVAL = 15` frames (0.5 s at 30 fps) in `GameFrame`,
  reusing the existing point-on-road helper rather than new distance math.
- [x] Application: `pcall Spring.MoveCtrl.SetGroundMoveTypeData(unitID, { maxSpeed = target,
  maxWantedSpeed = target })` -> `source = "mutator"`; if `MoveCtrl` is missing or the pcall fails,
  `pcall Spring.SetUnitRulesParam(unitID, "medieval_speed_target", target)` -> `source =
  "rules-param"`, which is **observational only and non-enforcing** (the engine does not read that
  param, so no speed change occurs); if neither is available -> `source = "none"`. Never crashes.
  Writes only when `target ~= state.applied`.
- [x] Lifecycle: `UnitFinished` tracks eligible units; `UnitDestroyed` and `UnitTaken` remove;
  `UnitGiven` removes and re-tracks under the receiving team.
- [x] Public API: `GG.MedievalLogistics.GetSpeedState(unitID)` -> live
  `{ base, onRoad, applied, source }` table, or `nil` for unknown/ineligible units. Existing APIs
  (`GetSpeedMultiplier`, `IsOnRoad`, `CanPlaceRoad`, `PlaceRoad`, connectivity queries) unchanged.
- [x] Out of scope (documented, not implemented): air/hover and transported units, builder-assist
  interactions, and per-slope effects.
- [x] Focused 26 tests (`tests/test_phase3_slice6.py`) and full 240-test suite passing; Lua syntax
  clean (44 files, 0 errors).
- [x] Probe evidence (frames 238-302, `source=mutator`): see the Slice 6 excerpt in the Verification
  section above.

## Next scope

Phase 3 connectivity gameplay effects are implemented and now verified in the live Recoil headless
engine: road movement-speed enforcement (Slice 6) and supply bonuses + road-aware pathing (Slice 7)
both carry deterministic `PASS` probe evidence (see `docs/slice7-probe-evidence.md`). Remaining
Phase 3 work is gameplay balancing and any higher-slice features, not verification of Slice 7.

### Slice 7 — supply bonuses and road-aware pathing

- [x] Pure supply policy in `scripts/medieval_logistics.lua`: `SUPPLY_RADIUS = 96.0`,
      `SUPPLY_BONUS_PER_ENDPOINT = 0.10`, `SUPPLY_BONUS_MAX = 0.50`, `supplyEndpointCount`,
      `supplyBonus`, `supplyState`, `isInSupply`, `isSupplyEligibleUnitDef`.
- [x] Only road-connected endpoints project supply; destroying a road removes the bonus on the next
      scan. Supply is per team.
- [x] Pure pathing policy: `pathCostMultiplier`, `pathCost`, `roadRoutePreferred`
      (`ROAD_PATH_COST_MULT = 0.75`, `UNSUPPLIED_PATH_COST_MULT = 1.5`), plus
      `PATH_COST_UNSUPPLIED`, `pathCost`, and `bestCandidate` in `scripts/medieval_gather.lua`.
- [x] Gadget tracking with a shared `SUPPLY_SCAN_INTERVAL = 15` frame pass; lifecycle removal on
      `UnitDestroyed`/`UnitTaken` and re-track on `UnitGiven`.
- [x] Rules-param publication (`medieval_supply_bonus`, `medieval_supply_mult`,
      `medieval_in_supply`) and damage application in `UnitPreDamaged`.
- [x] Public APIs: `GetSupplyState`, `SupplyBonus`, `InSupply`, `SupplyStateAt`,
      `SupplyEndpointCountAt`, `SupplySummary`, `PathCostMultiplier`, `PathCost`,
      `RoadRoutePreferred`.
- [x] Gather-gadget pathing: node selection uses `PointOnRoadNetwork`, drop-off selection uses
      `SupplyStateAt`; no-road behaviour is unchanged.
- [x] Fixed a latent `local`-ordering bug in `gadget_medieval_gather.lua`: `nearestDropoff`
      referenced `dropoffs`/`allowsResource` before their declarations, so both resolved to nil
      globals and every delivery selection raised on `pairs(nil)`.
- [x] Focused 61 tests (`tests/test_phase3_slice7.py`) and full 302-test suite passing; Lua syntax
      clean (44 files, 0 errors). Adds Initialize-reset coverage, engine-shaped defs
      (`canMove`-based eligibility), a real non-medieval attacker test, and explicit wrapper tests
      for `SupplyEndpointCountAt` / `PathCostMultiplier` / `PathCost` / `RoadRoutePreferred`.
- [x] Engine probe evidence for the supply path (deterministic `PASS`): see
      `docs/slice7-probe-evidence.md` and the Slice 7 excerpt below.
