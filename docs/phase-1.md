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
- [ ] Headless match frame advancement past frame 30 to observe live unit spawn in-engine:
  - Investigated `GameStartDelay=0`, `AutohostPort=8452`, and `MODOPTIONS.debugcommands=1:forcestart|1200:quitforce;`.
  - Confirmed via runtime execution that Recoil headless stays at `f=-000001` (pregame setup) and does not advance simulation frames automatically with these parameters alone.
- [ ] Melee and ballistic combat exchange observed in engine
- [ ] Formation drag command preview verified in LuaUI
- [ ] 200-unit performance smoke run logged in live engine simulation
- [ ] Eliminate `NOWEAPON` explosion warnings in engine log via `gamedata/weapondefs.lua`

## Investigation Checkpoint

- Added an opt-in `GameSetup` readiness override and an experimental LuaUI ready widget. Neither advanced the tested headless runs; they are experiments, not a confirmed fix.
- `python tools/launch/run_gameprobe.py 15` reported `max-frame=-1` and zero `Phase 1:` messages. The process was terminated at the timeout; its exit code 1 is not evidence of a spontaneous engine crash.
- The log reported a LuaUI entry point but no ready-widget message. Client log output also showed a null LuaRules handle; reconcile that with earlier gadget-loading evidence before relying on gadget callins.
- Dedicated engine rejects `--write-dir`; the corrected probe uses `--isolation-dir`. It then returned `setup-script error`, without simulation frames.
- Startscript variants, autohost probes, and engine command exports remain diagnostic work only. Binary strings such as `SetPlayerReadyState` do not establish a supported console command or its calling signature.
- The requested investigation workflow was cancelled; no completed subagent findings are claimed.
- Next step: establish a loaded LuaRules handle and a supported client/server readiness mechanism, then verify frame-30 spawning, combat, and the 200-unit run. GUI formation preview also remains unverified.
- Engine binaries, maps, generated command dumps, caches, and isolated runtime game copies are excluded from Git.

