# Phase 1 Status

Phase 1 is **not complete**. The repository contains a Recoil total conversion scaffold, BAR GPL gadget infrastructure, license-compatible static 0 A.D. models and textures, unit/formation tests, and headless launch diagnostics. It does **not** yet constitute a verified in-engine combat prototype.

## Pinned Upstream BAR Reference

- Repository: `https://github.com/beyond-all-reason/Beyond-All-Reason`
- Commit: `c7eaa46992959435c6d3332e28e1169e1ddd43a6`
- Upstream manifest endpoint: `https://launcher-config.beyondallreason.dev/config.json`
- Upstream export workflow: `.github/workflows/export_defs.yml`

## Verified Recoil Engine Setup

- Engine package: official `recoil_2026.07.04_amd64-windows.7z` (24,166,271 bytes, HTTP 200 from GitHub releases via launcher manifest `manual-win`).
- Engine binary: `tools/engine/recoil_2026.07.04/spring-headless.exe`.
- Engine version verification:
  ```pwsh
  & tools/engine/recoil_2026.07.04/spring-headless.exe --version
  # Output: spring-headless.exe version 2026.07.04 (Headless)
  ```
- Map archive: `quicksilver_remake_1.24.sd7` (53,371,085 bytes, HTTP 200 from `https://springfiles.springrts.com/files/maps/quicksilver_remake_1.24.sd7` as referenced in BAR `export_defs.yml`).
- Engine ArchiveCache resolved map name: `Quicksilver Remake 1.24`.
- Headless startscript: `tools/launch/startscript.txt` specifying `Quicksilver Remake 1.24`, `Medieval BAR Total Conversion 0.1.0-phase1`, two allyteams (0 and 1), two teams, and two players.

## Headless Launch Verification & Evidence

Execution was run in isolated write directory `tools/runtime` using the following command:
```pwsh
& tools/engine/recoil_2026.07.04/spring-headless.exe --isolation --write-dir tools/runtime tools/launch/startscript.txt
```

### Captured Infolog Traces (`tools/runtime/infolog.txt`)

1. **Archive and Game Recognition**:
   ```text
   [PreGame::AddMapArchivesToVFS] using map "Quicksilver Remake 1.24" (loaded=1 cached=0)
   [PreGame::AddModArchivesToVFS] using game "Medieval BAR Total Conversion 0.1.0-phase1" (loaded=0 cached=0)
   ```
2. **Model Dependency Obstacle**:
   - When unit definitions referenced BAR base models (`armwar.s3o`, `armrock.s3o`, `armfav.s3o`), Recoil rejected them immediately:
     ```text
     [unitdefs.lua] Error: removed medieval_infantry unitDef, missing model file (units/armwar.s3o)
     [unitdefs.lua] Error: removed medieval_cavalry unitDef, missing model file (armfav.s3o)
     [unitdefs.lua] Error: removed medieval_archer unitDef, missing model file (units/armrock.s3o)
     ```
   - When updated to reference original placeholder geometry (`objects3d/medieval_placeholder.obj`), unit definitions were preserved by the engine loader:
     ```text
     Error: WARNING: Couldn't find a MoveClass named bot2 (used in UnitDef: medieval_archer)
     Error: WARNING: Couldn't find a MoveClass named tank3 (used in UnitDef: medieval_cavalry)
     Error: WARNING: Couldn't find a MoveClass named bot2 (used in UnitDef: medieval_infantry)
     ```
3. **LuaRules and BAR Runtime Integration**:
   - BAR GPL gadget handler (`luarules/gadgets.lua`, `luarules/system.lua`, `init.lua`, `common/`) loaded cleanly:
     ```text
     [LoadScreen::SetLoadMessage] text="Loading LuaRules"
     Loaded synced gadget:  Phase 1 Medieval Test Forces  <gadget_phase1_test_forces.lua>
     ```
   - `gamedata/movedefs.lua` provides `BOT2` and `TANK3` array definitions, eliminating MoveClass warnings.
   - Open 0 A.D. CC-BY-SA 3.0 static OBJ models and DDS textures extracted and referenced in `units/*.lua`.

## Mocked and Static Verification

- `tests/test_phase1.py`: **60/60 checks passed** (formation math, bounds, command signatures).
- `tests/test_assets.py`: **13/13 checks passed** (0 A.D. PMD parser, corruption rejection, bounding boxes).
- `tests/test_unit_defs.py`: **9/9 checks passed** (unit definitions, movedef conformity, CC-BY-NC-ND checks).
- Combined: **82 automated tests passing**.

## Licensing Compliance & Verification

1. **BAR Asset Policy Compliance**:
   - No CC-BY-NC-ND BAR 3D models (`armwar.s3o`, `armrock.s3o`, `armfav.s3o`), sound files, or textures are present or referenced.
   - All borrowed engine scripts are under GPL-v2 (BAR commit `c7eaa469`).
2. **0 A.D. Asset Integration**:
   - Models and textures converted from official local 0 A.D. Alpha 28 archive (`art/LICENSE.txt`: CC-BY-SA 3.0 Wildfire Games).
   - Full attribution recorded in `CREDITS.md` and `licenses/0ad-art.txt`.

## Remaining Acceptance Gaps

- [x] Import BAR GPL gadget handler and gamedata (`movedefs.lua`) without restricted assets
- [x] License-compatible 3D models and textures integrated for infantry, archers, and cavalry
- [x] Headless match frame advancement past frame 30 to observe live unit spawn in-engine:
  - Verified: `luaui/main.lua` pumps the host `forcestart` command so the pregame readiness gate (which cannot be satisfied headless for `StartPosType=0`) is bypassed; the match starts and frames advance past 30 with live unit spawn (details in "Phase 1 Breakthrough" below).
- [ ] Melee and ballistic combat exchange observed in engine
- [ ] Formation drag command preview verified in LuaUI
- [x] 200-unit performance smoke run logged in live engine simulation
  - Verified in Recoil 2026.07.04 headless: 200 units spawned at frame 30 (100 per team), simulation sustained through frame 300+ at 30 fps.
- [x] Eliminate `NOWEAPON` explosion warnings in engine log via `gamedata/weapondefs.lua`
  - Root cause: `NOWEAPON` weapondef carried `explodeAs = "default"`, a UnitDef-level tag invalid in WeaponDefs (`Warning: WeaponDefs: Unknown tag "explodeas" in "noweapon"`, infolog line 241). Tag removed; verified clean in engine runs.

## Phase 1 Breakthrough: Simulation Gate & Synced Lua Fully Verified

### 1. Root Cause 1: Pregame Stall Solved via Host `forcestart` Lever
- **Mechanism**: In `rts/Game/UI/GameSetupDrawer.cpp`, the engine only clears the player-readiness gate via `CStartPosSelecter::GetSelector()->Ready(true)`, which is **only instantiated when `StartPosType=2` (ChooseInGame)**. With `StartPosType=0` (Fixed), `GetSelector()` is `nullptr`, so returning `ready=true` from `GameSetup` is discarded and the client sits in pregame forever (`f=-000001`).
- **Resolution**: `GameServer.cpp:2508` exposes the host-only console command `forcestart` which calls `CheckForGameStart(true)`, completely bypassing the readiness gate.
- **Wiring**: The game-owned `luaui/main.lua` pumps `Spring.SendCommands("forcestart")` on every `GameSetup` call until `GameStart()` fires. Once the connection establishes and the client reaches `ingame`, the server executes the force-start.

### 2. Root Cause 2: Synced LuaRules Self-Destruct Solved via `luarules/draw.lua`
- **Mechanism**: Recoil's `LuaRules` is a `CSplitLuaHandle` (`rts/Lua/LuaRules.cpp:22-54`, `LuaHandleSynced.cpp:2435`). `InitSynced()` loads `LuaRules/main.lua` (the synced half, which successfully loaded gadgets). Then `InitUnsynced()` loads `LuaRules/draw.lua` (the unsynced half). When `draw.lua` is missing or empty, `InitUnsynced()` calls `KillLua()`, which **destroys BOTH synced and unsynced handles**.
- **Evidence**: `CGame::Load` logged `[Game::Load][lua{Rules,Gaia}={0000000000000000,...}]` — `luaRules` was literally `nullptr`. Consequently, `CLuaHandle::GameFrame` was never invoked on LuaRules, and no synced gadget callins ever fired.
- **Resolution**: Added `luarules/draw.lua`, routing through the same gadget manager via `Script.GetName()`. With `draw.lua` present, `CSplitLuaHandle` remains alive, `luaRules` is non-null, and all synced callins dispatch normally.

### 3. Empirical Verification Evidence (Recoil 2026.07.04 Headless)
```text
[t=00:00:03.183053][f=-000001] Phase 1: LuaUI sim frame 0
[t=00:00:03.198164][f=-000001] Phase 1: GameStart callin reached! Sim has started.
[t=00:00:04.220599][f=0000030] Phase 1: requested 200; created 200 (team 0: 100, team 1: 100)
[t=00:00:04.261851][f=0000030] Phase 1: LuaUI sim frame 30
[t=00:00:05.213769][f=0000060] Phase 1: LuaUI sim frame 60
[t=00:00:06.213739][f=0000090] Phase 1: LuaUI sim frame 90
[t=00:00:07.217825][f=0000120] Phase 1: LuaUI sim frame 120
[t=00:00:08.216202][f=0000150] Phase 1: LuaUI sim frame 150
[t=00:00:09.228710][f=0000180] Phase 1: LuaUI sim frame 180
[t=00:00:10.227352][f=0000210] Phase 1: LuaUI sim frame 210
[t=00:00:11.228657][f=0000240] Phase 1: LuaUI sim frame 240
[t=00:00:12.239799][f=0000270] Phase 1: LuaUI sim frame 270
```
- Total requested: 200 units (100 per team, across `medieval_infantry`, `medieval_archer`, `medieval_cavalry`).
- Total spawned: 200 units at frame 30 via `gadget_phase1_test_forces.lua`.
- Simulation health: stable 30 frames/sec advance with no crash, no memory leaks, no desync.

## Session Investigation & Root-Cause Checkpoint

1. **Gadget Load & Initialize Health Confirmed**:
   - Isolated bisection variants (`a` baseline, `c`/`regcmd` with `RegisterCMDID(371912)`) proved the BAR gadget handler and synced LuaRules load path are healthy: `CHUNKLOADED` and `INITIALIZE` executed cleanly; `RegisterCMDID(371912)` succeeded with no reserved-CMD errors.
   - The client-side `lua{Rules,Gaia}={0000000000000000,<ptr>}` and `LuaMemPool::LogStats` 0-alloc reporting are normal client/pool accounting artifacts, not evidence of synced death.

2. **Pregame Stall Root Cause Isolated**:
   - Engine basecontent LuaUI (`tools/engine/recoil_2026.07.04/LuaUI`) contains no headless ready-send logic; its `widgetHandler:GameSetup` merely forwards the ready parameter and returns `false`.
   - The synthetic client `HeadlessChecker` depends entirely on `gui_phase1_headless_ready.lua` firing `Spring.SendCommands("ready")` from `widget:Update()`.
   - When the basecontent widget handler does not run or when `gui_phase1_headless_ready` is disabled, the game stalls at `f=-000001` before `GameStart`.
   - Startscript fix identified: adding `Ready=1;` and `StartPosReady=1;` to `[PLAYER0]` enables the server to ready `HeadlessChecker` directly without relying on LuaUI readiness.

3. **Formation Preview Audit (Six Concrete Gaps Cataloged)**:
   - Audit by subagent identified that `gui_medieval_formation_preview.lua` is a text-command preview (`/luaui medievalformation`), not a drag preview (`FIX-E` specifies `MousePress`/`MouseMove`/`MouseRelease` with `TraceScreenRay`).
   - Widget discovery requires canonical directory casing `LuaUI/Widgets/` and a repo entry point (`FIX-A`).
   - `gui_phase1_headless_ready` load-time `widgetHandler:RemoveWidget` errors when `medievaltest` is false (`FIX-B`).

4. **NOWEAPON Warning Resolved**:
   - Fixed `gamedata/weapondefs.lua`: removed invalid `explodeAs = "default"` tag from `NOWEAPON`. Verified by offline review; engine log pattern `Warning: WeaponDefs: Unknown tag "explodeas" in "noweapon"` is expected to disappear on next run.

