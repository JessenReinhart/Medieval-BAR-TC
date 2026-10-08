# Phase 3: Logistics, Tech Tree & Fortifications

Phase 3 Slice 3 (road adjacency/connectivity query API) is implemented and verified. The current
focused Slice 3 suite passes 28 tests; the full suite passes 172 tests. This slice does not complete
Phase 3 gameplay integration: it adds graph queries and lifecycle tracking, not player-issued road
placement or enforced logistics gameplay.

## Pinned Upstream BAR Reference

- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`

## Scope and current behavior

1. **Road feature and speed query** — `medieval_road` is a feature, not a unit. It is non-blocking,
   costs `{ wood = 5, stone = 2 }`, and contributes `ROAD_SPEED_MULT = 1.5` within the existing
   48-elmo road-proximity radius.
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
wall and tower fortification build options for this feature work. There is no villager road command.
Player-issued road placement and connectivity gameplay integration is the next design scope.

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
- Slice 3 focused tests: 28 passing.
- Current full suite: 172 passing.

## Verification

### Focused and full tests

```pwsh
python -m pytest tests/test_phase3_slice3.py -q
# 28 passed

python -m pytest tests -q
# 172 passed
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
[t=00:00:06.463575][f=0000120] PHASE3 ROAD placed ftr=21063 team=0 x=2608 z=3584
[t=00:00:06.463642][f=0000120] PHASE3 ROADGRAPH team=0 nodes=1 edges=0 components=1 isolated=1 largest=1
```

Observed graph query results from the same log:

```text
[t=00:00:07.780112][f=0000160] PHASE3 PROBE roadgraph nodes=5 edges=2 components=3 isolated=2 largest=3
[t=00:00:07.780172][f=0000160] PHASE3 PROBE roadgraph connected-first-last=true
[t=00:00:07.780206][f=0000160] PHASE3 PROBE roadgraph connected-chain-isolated=false
[t=00:00:07.780232][f=0000160] PHASE3 PROBE roadgraph point-on-network=true
[t=00:00:07.780254][f=0000160] PHASE3 PROBE roadgraph point-off-network=false
```

Bridge-removal behavior is covered by the focused Lua gadget harness, which observed this exact
removal echo and recomputed the chain as two isolated nodes. No corresponding bridge-removal line
is present in the checked-in engine `infolog.txt`, so it is not claimed as an engine log result:

```text
PHASE3 ROAD removed ftr=102 team=0
```

## Slice roadmap

### Slice 1 — roads, tech tree, fortifications

- [x] Pure logistics module, road feature, tech rules, wall/tower definitions, gadget wiring.
- [x] Initial headless probe and logistics tests.

### Slice 2 — build handling and damage scaling

- [x] Resource validation and damage scaling tests.
- [x] Villager wall/tower build options.
- [x] Corrected scope: `AllowUnitCreation` is a unit-creation gate; it is not a road-feature
      command or road-feature placement implementation. Villagers do not have a road command.

### Slice 3 — road adjacency/connectivity queries

- [x] Pure graph API with `LINK_RADIUS = 64.0`.
- [x] Team-isolated road tracking on feature create/destroy.
- [x] `RoadNetworkSummary`, `RoadConnected`, and `PointOnRoadNetwork` on
      `GG.MedievalLogistics`.
- [x] Probe for initial graph state, chain connectivity, isolated-node rejection, and point queries.
- [x] Focused 28 tests and full 172-test verification.

## Next scope

Player-issued road placement and connectivity gameplay integration remains pending design. Do not
claim the entire Phase 3 is complete from this Slice 3 query API work.
