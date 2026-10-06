# Handoff: Medieval-BAR-TC (Phase 2 Slice 1 -> Slice 2)

Date: 2026-10-06
Branch: `medieval-total-conversion` (clean, pushed to origin)
Last commit: `6a5271e8` Phase 2: implement 4-resource economy, housing, and gathering work cycles

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
   - Gathering state machine (`luarules/gadgets/gadget_medieval_gather.lua`, `scripts/medieval_gather.lua`) handling `CMD_GATHER` (371920) and `CMD_DELIVER` (371921), driving `move_node` -> `harvest` -> `move_drop` -> `deliver`.
   - Verified headless in-engine: 2 settlements, 10 villagers, 10 resource features, stats logged at frames 30..360+.
   - 53 pytest tests passing (`python -m pytest tests -q`).

## What's Next: Phase 2 Slice 2 (Production Chains & Military Recruitment)

The goal of Slice 2 is connecting the economy and villagers to the military forces created in Phase 1:

1. **Military Training Buildings (`units/`)**:
   - `medieval_barracks.lua`: Trains `medieval_infantry` (sword) and `medieval_archer` (bow). Costs Wood + Stone.
   - `medieval_stables.lua`: Trains `medieval_cavalry` (knight). Costs Wood + Stone.
   - `medieval_blacksmith.lua`: Crafts equipment / arms.

2. **Custom Resource Cost Interception (`luarules/gadgets/gadget_medieval_recruitment.lua`)**:
   - Intercept factory training orders and builder placements in `AllowUnitCreation` / `AllowUnitBuildStep`.
   - Validate discrete resource cost against `GG.MedievalEconomy.CanAfford(teamID, costs)`.
   - Atomically debit with `GG.MedievalEconomy.Transact(teamID, costs)`.
   - Block creation if unaffordable or if pop cap is reached (`GG.MedievalHousing.CanSupport`).

3. **Food Upkeep / Hunger Mechanism**:
   - Per-frame or periodic food consumption for standing army.
   - Training stalls or penalty debuff if food reaches 0.

4. **Engine Headless Verification**:
   - Headless test scenario: villager builds barracks -> discrete wood/stone debited -> barracks produces man-at-arms -> food/iron debited -> population increases from 5 to 6.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Run Phase 2 headless probe
python tools/launch/run_phase2_probe.py
python tools/launch/read_final_log.py

# 3. Read roadmap
cat docs/phase-2.md
```
