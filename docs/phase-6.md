# Phase 6: Balance Pass, Pacing & Content Polish Specification

> **Status: COMPLETE & PROBE-VERIFIED.** Phase 6 is complete. All 5 slices landed,
> verified across 1195 passing tests (+81 new Phase 6 tests over the 1114 Phase 5 baseline),
> 77 Lua files syntax-clean, and all 6 headless engine probe verdicts PASS at
> frames 40 / 100 / 160 / 260 / 300 / 300.

---

## Architectural Objectives

1. **Deterministic balance parameters.** Every tuned coefficient is documented, bounded, and
   kept in pure policy modules (`scripts/medieval_*.lua`) or unit defs so tests can verify
   the numbers without launching the engine.
2. **Counter matrix must stay closed.** The four-way counter loop must hold after tuning:
   - Cavalry counters Ranged (speed + charge burst).
   - Spearman counters Cavalry (brace + anti-cavalry factor).
   - Infantry counters Spearman (armor + sustained melee DPS).
   - Ranged counters Infantry (range kiting before contact).
   - Siege counters Fortifications (fortification damage multiplier).
3. **Smooth economic ramp.** Settlement pacing: early build-up → expansion → fortified clash.
   Resource sinks and market elasticity keep all four resources nonzero and tradable.
4. **No regressions.** Keep all 1,114 existing tests green; each slice adds a focused suite
   `tests/test_phase6_sliceN.py`.

---

## Slices Breakdown

### Slice 1: Economic Pacing & Production Build-Costs
- **Owned files only:**
  - `scripts/medieval_economy.lua` (STARTING_RESERVES currently `{food=200, wood=200, stone=100, iron=50}`, MAX_STOCKPILE)
  - `scripts/medieval_gather.lua` (HARVEST_RATE=2, CARRY_CAPACITY=10, NODE_CAPACITY_BY_TYPE, dropoff/path costs)
  - `scripts/medieval_market.lua` (elastic barter rates and recovery bands — read it before editing)
  - `units/medieval_villager.lua`, `units/medieval_house.lua`, `units/medieval_granary.lua`,
    `units/medieval_lumber_camp.lua`, `units/medieval_town_center.lua`, `units/medieval_cart.lua`
    (buildCostMetal, buildTime, customparams.resource_cost_* / carry_capacity / harvest_rate / pop_provided)
- **Goal:** a legible early-game ramp — a player can afford ~4 villagers and 1 house within the
  first 90 sim-frames of the headless probe, and food does not idle-starve the settlement.
- **Do NOT** touch `scripts/medieval_housing.lua` (population cap math) here — that is verified
  in the existing suite; only adjust the *per-building pop_provided / costs* in unit defs if needed.
- Add/extend `tests/test_phase6_slice1.py`.

### Slice 2: Combat Stats & Counter-Matrix Verification
- **Owned files only:**
  - `scripts/medieval_damage_types.lua` (MATRIX multipliers — read the inline table first)
  - `scripts/medieval_tactics.lua` (CHARGE_DMG_MULT_MAX=1.6, BRACE_DMG_REDUCTION=0.5,
    BRACE_BONUS_VS_CAVALRY=1.25, flank front/side/rear factors, stance factors — read actuals)
  - `units/medieval_infantry.lua`, `medieval_spearman.lua`, `medieval_archer.lua`,
    `medieval_crossbow.lua`, `medieval_cavalry.lua`, `medieval_knight.lua`,
    `medieval_men_at_arms.lua`, `medieval_catapult.lua` (maxDamage, buildCostMetal, buildTime,
    maxVelocity, weapon ranges/cooldowns if present, mass)
- **Goal:** verify by test that each counter wins its intended matchup (e.g. spearman kills an
  equal-cost cavalry squad faster than cavalry kills spearman) and that the four-way loop is
  closed. Tune HP/speed/cost/damage only as needed to make those counter assertions true.
- Add/extend `tests/test_phase6_slice2.py`.

### Slice 3: Logistics, Hauling & Production-Flow Calibration
- **Owned files only:**
  - `scripts/medieval_haul.lua` (HAUL_STEP=25, DEFICIT_THRESHOLD=80, CART_CAPACITY=400, hub order)
  - `scripts/medieval_logistics.lua` (supply tracking, road speed multiplier, decay — read first)
  - `scripts/medieval_recruitment.lua` (UPKEEP costs, build/recruit timing)
  - `units/medieval_blacksmith.lua`, `units/medieval_fletcher.lua` (craft timers / costs)
- **Goal:** hauling keeps wood/iron flowing to crafting sinks without oscillation; road-vs-offroad
  speed difference is meaningful but not crippling. Crafting paces military recruitment so a
  player cannot flood units faster than ~1 per 30 frames per production building in early game.
- Add/extend `tests/test_phase6_slice3.py`.

### Slice 4: Skirmish-AI Pacing & Reactive Strategy
- **Owned files only:**
  - `scripts/medieval_skirmish_ai.lua` (build order, cost thresholds, threat/reaction logic)
  - `units/medieval_tower.lua`, `units/medieval_king.lua` (AI-adjacent defensive/victory units)
  - `units/medieval_wall.lua`
- **Goal:** the AI reaches a defensible base with a small mixed army by the probe's
  `military-engagement` frame and does not stall on housing or food. Add a
  `computeRatios`-style test that shows the AI recruits the counter to the opponent's majority
  unit type.
- Add/extend `tests/test_phase6_slice4.py`.

### Slice 5: Tooltips, Modoptions Help, HUD Text & Final Verification
- **Owned files only:**
  - `modoptions.lua` (name/desc/help text — no key renames, no default changes)
  - `units/*.lua` `name`/`description` strings (cosmetic only)
  - `scripts/medieval_hud.lua` + `LuaUI/Widgets/gui_medieval_hud.lua` (label text/format only —
    do NOT change the `"Pop: x/y"` colon format which is a recorded Phase 5 deviation)
  - `tools/launch/run_phase5_slice6_probe.py` only if a docstring/label needs to reflect Phase 6
- **Goal:** consistent, player-facing text; no stale "Phase 1 placeholder" descriptions; HUD
  labels are readable. Then run the full verification gate below and record results in
  `docs/phase-6.md` status banner.
- Add/extend `tests/test_phase6_slice5.py` only if a text/format assertion is worth pinning.

---

## Verification Gate (run after all slices)

```pwsh
python tests/check_lua_syntax.py        # must be 0 errors
python -m pytest tests -q               # all green, no regressions
python tools/launch/run_phase5_slice6_probe.py   # 6/6 PASS verdicts still emitted
```

---

## Scope boundaries (out of scope)

- No new art/assets; no new unit types; no new resources (still food/wood/stone/iron).
- No multiplayer netplay/lobby balance or latency work.
- No changes to the single-damage-pipeline composition order in
  `luarules/gadgets/gadget_medieval_tactics.lua`.
- No silent changes to the recorded Phase 5 deviations (TC cap 10, no `tower_arrow`, `"Pop: x/y"`).