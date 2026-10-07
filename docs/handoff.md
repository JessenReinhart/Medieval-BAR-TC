# Handoff: Medieval-BAR-TC (Phase 2 Slice 2 -> Slice 3)

Date: 2026-10-07
Branch: `medieval-total-conversion`
Last work: Phase 2 Slice 2 — military recruitment, building costs, and pop‑cap enforcement

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

## What's Next: Phase 2 Slice 3 (Combat Integration & Audio/Visual Polish)

Slice 2 is now **complete and verified**:
- Barracks, Stables, Blacksmith unitdefs with `resource_cost_*` fields.
- `gadget_medieval_recruitment.lua` enforces discrete resource costs via `GG.MedievalEconomy.Transact` and pop‑cap via housing.
- Pure recruitment module `scripts/medieval_recruitment.lua` provides cost lookup and food upkeep.
- 63 pytest tests pass (`python -m pytest tests -q`).
- Live headless verification shows atomic debits, successful infantry spawn, and correct `CanRecruit` block when food is insufficient.

**Slice 3 roadmap**:
1. Weapon animation and sound tuning for infantry, archer, and cavalry.
2. Visual effects: arrow trails, melee impact particles, gathering sounds.
3. Full‑match end‑to‑end simulation from settlement founding to army clash.
4. Optional AI scripting for tactical unit behavior.

## How to Resume in a New Session

```pwsh
# 1. Verify environment and tests
git status
python -m pytest tests -q

# 2. Run Phase 2 headless probe (Slice 2)
python tools/launch/run_phase2_probe.py
python tools/launch/read_final_log.py

# 3. Review roadmap
cat docs/phase-2.md
```
