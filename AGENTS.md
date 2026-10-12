# AGENTS.md — Developer and AI Agent Guide

## Project Overview

**Medieval-BAR-TC** is a standalone medieval total conversion RTS mod for the Recoil / Spring engine.
- Replaces modern/sci-fi BAR mechanics with historical medieval systems: resource gathering (Food, Wood, Stone, Iron), housing & population caps, road networks, supply lines, siege ballistics, production chains, garrisoning, melee tactical combat (charges, bracing, flanking), and multiple victory conditions.
- Uses CC-BY-SA 3.0 0 A.D. conversions (`tools/assets/convert_0ad.py`) and custom Lua. No proprietary or CC-BY-NC-ND BAR assets.
- License: GPL-v2 (code) and CC-BY-SA 3.0 (converted assets).

---

## Architectural Principles

1. **Pure Policy, Synced Side Effects:**
   - Decision logic, tables, and pure math live in `scripts/medieval_*.lua` without `Spring.*` or `VFS.*` globals. These modules are testable with bare Python / LuaJIT.
   - Side effects, `Spring.*` callins, and `GG.*` exports live in synced gadgets under `luarules/gadgets/gadget_medieval_*.lua`.
2. **Single Authoritative Damage Pipeline:**
   - Outgoing and incoming combat damage calculations are strictly consolidated in `luarules/gadgets/gadget_medieval_tactics.lua`.
   - It owns the sole `UnitPreDamaged` hook in the game, composing:
     `damage = base * tech_mult * supply_mult * matrix_mult * garrison_mult * tactics_mult`.
   - Never register a second `UnitPreDamaged` in any other gadget.
3. **UI Isolation:**
   - Unsynced HUD and widgets live in `LuaUI/Widgets/` (e.g. `gui_medieval_hud.lua`).
   - UI widgets must only read game state via `Spring.GetTeamRulesParam` / `Spring.GetGameRulesParam` published by gadgets.
4. **Mod Options Gating:**
   - Modular subsystems are gated by options in `modoptions.lua` (`medievalvictory`, `medievalhud`, `medievalmarket`, `medievalgarrison`, `medievaltactics`, `skirmishai`).

---

## Recoil / Spring Engine & Headless Runtime

- **Engine Binary Location:** `tools/engine/recoil_2026.07.04/spring-headless.exe`
  *(Note: Do not look for engine binaries in `tools/runtime/`; runtime is the engine's write sandbox).*
- **Runtime Directory:** `tools/runtime/`
- **Game Sync Directory:** `tools/runtime/games/Medieval-BAR-TC.sdd`
- **Headless Launch Invocation:**
  `tools/engine/recoil_2026.07.04/spring-headless.exe --isolation --write-dir tools/runtime <startscript>`

---

## Testing & Verification Commands

Always run verification before ending turns or committing:

```pwsh
# 1. Syntax check across all repo Lua files (must be 0 errors)
python tests/check_lua_syntax.py

# 2. Run full pytest suite (currently 1114 tests)
python -m pytest tests -q

# 3. Run individual slice test suites
python -m pytest tests/test_phase5_slice1.py tests/test_phase5_slice6.py -q

# 4. Run headless skirmish integration probe
python tools/launch/run_phase5_slice6_probe.py
```

---

## Project Status & Key Documents

- **Phase 1–5 Complete:**
  - Phase 1: Prototype medieval combat & units.
  - Phase 2: Housing, military recruitment, skirmish AI.
  - Phase 3: Logistics, roads, supply networks, fortifications.
  - Phase 4: Siege ballistics, damage types, production chains, veteran upgrades, cart hauling.
  - Phase 5: Victory/defeat conditions, medieval status HUD, market barter, garrison shelter/healing, tactical formations/charges/bracing, single damage pipeline, and automated integration match probe.
- **Next: Phase 6:** Balance pass, polish, and final tuning (no new major subsystems).
- **Core Docs:**
  - `docs/handoff.md`: Active session handoff guide, recent commit records, and resume notes.
  - `docs/phase-5.md`: Phase 5 specification and completed slice breakdown.

---

## Key Conventions & Known Gotchas

- **Town Center Garrison Capacity:** Town Center holds 10 units (`transportCapacity = 10`), Towers hold 4.
- **HUD Formatting:** Population HUD string is formatted as `"Pop: <current>/<cap>"` (with colon).
- **Engine Process Termination:** The headless build does not always reliably terminate on `quitforce`. Probe runners handle process timeout gracefully and check `infolog.txt` for emitted PASS verdicts.
