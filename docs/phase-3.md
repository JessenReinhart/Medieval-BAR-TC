# Phase 3: Logistics, Tech Tree & Fortifications

Phase 3 implementation **Slice 1 complete and verified** — full test suite green, headless
engine probe confirms road placement, speed multiplier echo, and tech unlocks.

## Pinned Upstream BAR Reference
- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`

## Scope
1. **Road network** — `medieval_road` is a **feature** (`gamedata/featuredefs.lua`), not a
   unit: `blocking=false`, `crushable=false`, `destructable=false`, cost
   `{ wood = 5, stone = 2 }`, placed by villagers. Grants `ROAD_SPEED_MULT = 1.5` to any
   unit within `ROAD_PROXIMITY_RADIUS = 48` elmos of a road feature. The gadget tracks road
   features per team (`roads[teamID][featureID] = {x, z}`) for future connectivity validation.
2. **Technology upgrades** — Blacksmith research unlocks three techs:
   - `iron_swords` — +25% infantry melee damage (cost `{ wood = 50, iron = 100 }`, no prereq).
   - `plate_armor` — +25% infantry & cavalry max HP (cost `{ iron = 150 }`, prereq `iron_swords`).
   - `masonry` — +50% wall & tower HP (cost `{ stone = 150, wood = 50 }`, no prereq).
   Each team tracks unlocks via synced gamerules `team_<id>_tech_<techID>` and
   `GG.MedievalLogistics`.
3. **Fortifications** — placeable `medieval_wall` (2x2, maxDamage 2500, cost
   `{ wood = 10, stone = 40 }`) and `medieval_tower` (3x3, maxDamage 1500, sightDistance 600,
   cost `{ wood = 20, stone = 50 }`). Walls/towers are military and do not affect pop cap;
   cost is enforced at placement via `AllowUnitCreation`. Out of slice-1 scope: no enemy AI
   targeting changes.

## Architecture
- **Pure module**: `scripts/medieval_logistics.lua` — no engine calls; exposes
  `getCost`, `getTech`, `canResearch`, `applyUnlock`, `isPositionOnRoad`, `speedMultiplier`,
  `damageMultiplier`, `healthMultiplier`, plus constants `ROAD_SPEED_MULT = 1.5`,
  `ROAD_PROXIMITY_RADIUS = 48.0`, `COSTS`, `TECHS`.
- **Gadget**: `luarules/gadgets/gadget_medieval_logistics.lua` (layer 3, synced) —
  `FeatureCreated`/`FeatureDestroyed` track road features per team; `UnitFinished` applies
  researched health/damage multipliers; `AllowUnitCreation` validates fortification costs.
- **Synced Game Rules**: `team_<id>_tech_<techID>` for `iron_swords`, `plate_armor`, `masonry`.
- **Public API**: `GG.MedievalLogistics`:
  - `GetSpeedMultiplier(teamID, unitID)` -> 1.5 on road, else 1.0; `IsOnRoad(teamID, unitID)`;
    `RoadCount(teamID)`.
  - `CanResearch(teamID, techID)`, `Research(teamID, techID)` (atomic, charges resources via
    `GG.MedievalEconomy.Transact`), `IsResearched(teamID, techID)`.
  - `DamageMultiplier(teamID, unitName)`, `HealthMultiplier(teamID, unitName)`.
- **Costs**: `medieval_road { wood = 5, stone = 2 }`,
  `medieval_wall { wood = 10, stone = 40 }`, `medieval_tower { wood = 20, stone = 50 }`.

## Surface Area (allowed edits)
- `scripts/medieval_logistics.lua` (new)
- `luarules/gadgets/gadget_medieval_logistics.lua` (new)
- `gamedata/featuredefs.lua` (`medieval_road` feature)
- `units/medieval_wall.lua`, `units/medieval_tower.lua` (new)
- `tests/test_phase3_logistics.py` (new)
- `docs/phase-3.md`, `docs/handoff.md`

## Verification

### Test suite
```
$ python -m pytest tests -q
131 passed in 0.78s
```

### Headless engine probe
No separate `run_phase3_probe.py` was created; the `PHASE3` steps are driven by
`gadget_phase2_test_forces.lua` at `GameFrame == 120` during the headless Phase 2 run.
Verified excerpt from `tools/runtime/infolog.txt`:

```
[t=00:00:05.480374][f=-000001] Loaded synced gadget:  Medieval Logistics, Tech & Fortifications  <gadget_medieval_logistics.lua>
[t=00:00:09.755144][f=0000120] PHASE3 PROBE deposit team=0 wood=300 stone=300 iron=300
[t=00:00:09.755206][f=0000120] PHASE3 ROAD placed ftr=10676 team=0 x=2608 z=3584
[t=00:00:09.755252][f=0000120] PHASE3 PROBE road-create ftr=10676 team=0 at=(2608, 3584)
[t=00:00:09.755264][f=0000120] PHASE3 PROBE road-count team=0 count=1
[t=00:00:09.755521][f=0000120] PHASE3 PROBE is-on-road team=0 unit=2968 on_road=true speed_mult=1.50
[t=00:00:09.755548][f=0000120] PHASE3 TECH researched team=0 tech=iron_swords
[t=00:00:09.755559][f=0000120] PHASE3 PROBE research iron_swords team=0 ok=true reason=nil
[t=00:00:09.755951][f=0000120] PHASE3 PROBE param team_0_tech_iron_swords = 1
[t=00:00:09.755970][f=0000120] PHASE3 PROBE is-researched iron_swords team=0 = true
[t=00:00:09.756003][f=0000120] PHASE3 TECH researched team=0 tech=plate_armor
[t=00:00:09.756016][f=0000120] PHASE3 PROBE research plate_armor team=0 ok=true reason=nil
[t=00:00:09.756687][f=0000120] PHASE3 PROBE param team_0_tech_plate_armor = 1
[t=00:00:09.756717][f=0000120] PHASE3 PROBE is-researched plate_armor team=0 = true
```

`speed_mult=1.50` matches `ROAD_SPEED_MULT = 1.5` exactly (the earlier plan's value `2` was
superseded).

## Slice 1 Roadmap
- [x] Pure module `scripts/medieval_logistics.lua`.
- [x] Gadget wiring (auto-discovered from `luarules/gadgets/`).
- [x] Road feature def + wall/tower unit defs.
- [x] Probe block (in `gadget_phase2_test_forces.lua`) + tests.
- [ ] Villager build command integration (needs Phase 2 gather-priority extension).
- [ ] Weapon upgrade application in combat LUS (needs Phase 1 hook).