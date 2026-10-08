# Phase 3: Logistics, Tech Tree & Fortifications

Phase 3 Slice 4 (player-issued road placement command) is implemented and verified. The focused
Slice 4 suite passes 25 tests; the full suite passes 197 tests. Slice 4 adds the custom
`CMD_BUILD_ROAD` (371922) command with deferred economy transaction and feature creation. It does
not complete Phase 3 gameplay integration: movement-speed enforcement is DEFERRED pending a
verified engine speed API, and connectivity gameplay enforcement remains open.

## Pinned Upstream BAR Reference

- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`

## Scope and current behavior

1. **Road feature and speed query** — `medieval_road` is a feature, not a unit. It is non-blocking,
   costs `{ wood = 5, stone = 2 }`. `scripts/medieval_logistics.lua` exposes a query-only speed
   multiplier (`ROAD_SPEED_MULT = 1.5`, 48-elmo proximity radius). The query API does **not** change
   unit movement; no engine speed mutator is applied.
2. **Road graph (Slice 3)** — `scripts/medieval_road_graph.lua` is a pure module. It uses
   `LINK_RADIUS = 64.0` planar elmos: road nodes at or below that distance share an edge. The
   gadget tracks `{x, z}` road positions by team and recomputes graph state after road creation
   and removal.
3. **Technology upgrades** — Blacksmith research tracks `iron_swords`, `plate_armor`, and
   `masonry` through synced team rules and `GG.MedievalLogistics`.
4. **Fortifications** — `medieval_wall` and `medieval_tower` are available to villagers and have
   resource costs enforced by the logistics gadget.

This is a query API, not enforced logistics gameplay. `AllowUnitCreation` gates unit creation and
unit costs; it does not provide a road-feature placement command. The villager currently has only
wall and tower fortification build options for this feature work. Roads are placed only by the
custom command (`CMD_BUILD_ROAD = 371922`), not by buildoptions.

## Architecture

- **Pure road graph**: `scripts/medieval_road_graph.lua` — no engine calls. Public functions:
  `planarDist`, `buildEdges`, `adjacency`, `componentCount`, `componentOf`, `isConnected`,
  `connectedToNetwork`, and `networkSummary`. Constant: `LINK_RADIUS = 64.0`.
- **Logistics gadget**: `luarules/gadgets/gadget_medieval_logistics.lua` tracks road feature
  lifecycle per team and exposes these graph queries through `GG.MedievalLogistics`:
  - `RoadNetworkSummary(teamID)` -> `{ nodes, edges, components, isolated, largest }`.
  - `RoadConnected(teamID, keyA, keyB)` -> whether two tracked road feature IDs share a component.
  - `PointOnRoadNetwork(teamID, x, z)` -> whether a point is within `LINK_RADIUS` of a road node.
  - Existing speed, research, damage, health, and road-count APIs remain available.
- **Probe**: `luarules/gadgets/gadget_phase2_test_forces.lua` creates a three-node chain and an
  isolated node at frame 160, then logs summary and connectivity queries. It is a diagnostic probe,
  not a player command implementation.

## Historical Slice 1 and Slice 2 counts

These are historical completion counts, not the current total:

- Slice 1: 131 tests passing.
- Slice 2: 144 tests passing.
- Slice 3: 172 tests passing (28 focused).
- Slice 4 focused tests: 25 passing.
- Current full suite: 197 passing.

## Verification

### Focused and full tests

```pwsh
python -m pytest tests/test_phase3_slice4.py -q
# 25 passed

python -m pytest tests -q
# 197 passed
```

### Headless engine probe

The existing probe script syncs source into the SDD and launches the pinned Recoil headless
executable. It is not a clean engine-start signal: the checked-in `tools/runtime/infolog.txt`
contains startup caveats including a fallback SMF splat-detail texture, groundFX texture-atlas
failure, missing `Fonts/FreeMonoBold.ttf`, a missing `ad0_senegal_2` feature followed by a
`SetFeatureMoveCtrl` Lua call error, and missing COB scripts for several settlement units. Treat
those as runtime-environment caveats, not as successful subsystem evidence.

Run the existing probe and inspect the exact checked-in log:

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
- [x] Movement-speed enforcement is **DEFERRED**: no verified engine speed-mutator API has been
      identified. A partial `.engine-src` extraction shows no `SetUnitSpeed` / `SpeedMod` style
      mutator hits, but a partial extraction cannot prove API absence — the full engine source has
      not been searched. `GG.MedievalLogistics.GetSpeedMultiplier` and `IsOnRoad` remain query-only;
      the query multiplier does not change movement. No direct engine velocity changes are claimed.
- [x] Focused 25 tests (`tests/test_phase3_slice4.py`) and full 197-test suite passing.

## Next scope

Movement-speed enforcement and end-to-end connectivity gameplay integration remain open. Do not claim
Phase 3 is complete from Slice 4 road-build command work.
