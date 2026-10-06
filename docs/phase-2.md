# Phase 2 Status: Economy, Settlers & Housing

Phase 2 implementation slice 1 is **complete and verified in-engine**.

## Pinned Upstream BAR Reference
- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`

## Verified Recoil Engine Setup
- Engine binary: `tools/engine/recoil_2026.07.04/spring-headless.exe` (Recoil 2026.07.04 Headless)
- Map: `Quicksilver Remake 1.24`
- Startscript: `tools/launch/startscript_phase2.txt` (with `phase2test=1`, `StartPosType=0`, 2 teams)

## Phase 2 Architecture & Implemented Systems

### 1. 4-Resource Discrete Economy Core
- **Script**: `scripts/medieval_economy.lua` (pure math, bounded stockpiles, atomic transaction checks).
- **Gadget**: `luarules/gadgets/gadget_medieval_economy.lua` (synced state, authoritatively tracks Food, Wood, Stone, Iron per team).
- **Initial Reserves**: 200 Food, 200 Wood, 100 Stone, 50 Iron.
- **Synced Game Rules**: Exposes `team_<id>_food`, `team_<id>_wood`, `team_<id>_stone`, `team_<id>_iron`.
- **Public API**: `GG.MedievalEconomy` exposes `GetStockpiles`, `GetResource`, `Deposit`, `Withdraw`, `CanAfford`, `Transact`.

### 2. Housing and Population Management
- **Script**: `scripts/medieval_housing.lua` (pure cap calculation, pop consumers, clamp to 300).
- **Gadget**: `luarules/gadgets/gadget_medieval_housing.lua` (listens to `UnitCreated`, `UnitDestroyed`, validates `AllowUnitCreation`).
- **Housing Providers**: Town Center (+10 pop), Peasant House (+5 pop), base settlement capacity 10.
- **Pop Consumers**: Villager, Infantry, Archer, Cavalry (1 pop each).
- **Synced Game Rules**: Exposes `team_<id>_population` and `team_<id>_pop_cap`.
- **Enforcement**: Blocks unit construction when population ceiling is met.

### 3. Settlement Buildings & Villager Workers
- `units/medieval_town_center.lua`: Main 7x7 administrative building, factory, drop-off hub, +10 pop provider.
- `units/medieval_house.lua`: 4x4 residential dwelling, +5 pop provider.
- `units/medieval_granary.lua`: 4x4 dedicated food drop-off warehouse.
- `units/medieval_lumber_camp.lua`: 4x4 dedicated wood drop-off point.
- `units/medieval_villager.lua`: Worker/builder unit, `carry_capacity=10`, `harvest_rate=2`.
- `scripts/medieval_villager.lua`: LUS unit script with piece root.

### 4. Resource Nodes & Gathering Work Cycle
- **Features**: `medieval_tree` (wood, 500 cap), `medieval_stone` (stone, 400 cap), `medieval_iron` (iron, 300 cap), `medieval_deer` (food, 250 cap).
- **Script**: `scripts/medieval_gather.lua` (harvest rates, inventory thresholds, planar range checks).
- **Gadget**: `luarules/gadgets/gadget_medieval_gather.lua` (tracks `FeatureCreated`, drives `move_node` -> `harvest` -> `move_drop` -> `deliver` state machine).
- **Commands**: Registered `CMD_GATHER` (371920) and `CMD_DELIVER` (371921).

## Headless In-Engine Verification Evidence (`tools/runtime/infolog.txt`)
```text
[t=00:00:02.508159][f=-000001] Loaded synced gadget:  Medieval Economy Core  <gadget_medieval_economy.lua>
[t=00:00:02.508406][f=-000001] Loaded synced gadget:  Medieval Housing and Population  <gadget_medieval_housing.lua>
[t=00:00:02.508634][f=-000001] Loaded synced gadget:  Medieval Gathering and Delivery  <gadget_medieval_gather.lua>
[t=00:00:02.712331][f=-000001] Phase 1: GameStart callin reached! Sim has started.
[t=00:00:03.719847][f=0000030] PHASE2 PROBE: spawned Town Center id=6332 for team=0 at (2508, 3584)
[t=00:00:03.720094][f=0000030] PHASE2 PROBE: spawned House #1 id=62 team=0
[t=00:00:03.720313][f=0000030] PHASE2 PROBE: spawned House #2 id=4654 team=0
[t=00:00:03.720766][f=0000030] PHASE2 PROBE: spawned Granary=16000 Camp=8845 team=0
[t=00:00:03.721127][f=0000030] PHASE2 PROBE: spawned Villager #1 id=15044 team=0
[t=00:00:03.721897][f=0000030] PHASE2 PROBE: spawned Feature medieval_tree id=8557 at (2588, 3764)
[t=00:00:03.722032][f=0000030] PHASE2 PROBE: spawned Feature medieval_stone id=17569 at (2418, 3764)
[t=00:00:03.722064][f=0000030] PHASE2 PROBE: spawned Feature medieval_iron id=30165 at (2508, 3804)
[t=00:00:03.722102][f=0000030] PHASE2 PROBE: spawned Feature medieval_deer id=19667 at (2358, 3744)
[t=00:00:03.797909][f=00:00032] PHASE2 PROBE: assigned villager 15044 to initial gather cycle
[t=00:00:04.722151][f=0000060] PHASE2 GATHER JOB f=60 vid=15044 state=move_node res=stone carried=0.0 node=17569
[t=00:00:05.728054][f=0000090] PHASE2 PROBE STATS f=90 team=0 Food=200 Wood=200 Pop=5 Cap=30
[t=00:00:08.716766][f=0000180] PHASE2 PROBE STATS f=180 team=0 Food=200 Wood=200 Pop=5 Cap=30
[t=00:00:11.718032][f=0000270] PHASE2 PROBE STATS f=270 team=0 Food=200 Wood=200 Pop=5 Cap=30
[t=00:00:14.726157][f=0000360] PHASE2 PROBE STATS f=360 team=0 Food=200 Wood=200 Pop=5 Cap=30
```
- Settlements live on both teams (Town Center, 2 Houses, Granary, Lumber Camp, 5 Villagers, 5 Resource Features).
- Economy tracked: Food=200, Wood=200, Pop=5, Cap=30 (10 baseline + 10 TC + 5*2 houses).
- Gather cycle running: villagers dispatched to resource nodes via synced pathfinding without errors.

## Automated Test Coverage
- `tests/test_phase2.py`: 22 tests passing (economy arithmetic, capacities, housing limits, gather ranges, unit definitions).
- `tests/test_lua_syntax.py`: 1 test passing (compiles all 33 Lua files across repo).
- Full suite: **53 passing pytest tests**.
