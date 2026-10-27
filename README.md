# Medieval-BAR-TC

A medieval total conversion for the [Recoil](https://github.com/beyond-all-reason/spring) RTS engine,
built from BAR GPL code without BAR's restricted CC-BY-NC-ND art assets. Art is converted from
0 A.D. under CC-BY-SA 3.0.

## Current status

**Phases 1–7 complete.** The project now covers the full medieval loop:

- **Phase 1–5:** Combat & units, housing/military recruitment, logistics/roads/supply,
  siege ballistics & production chains, and the five victory conditions, market, garrison,
  tactics, and single authoritative damage pipeline.
- **Phase 6:** Balance pass and integration hardening (see `docs/phase-6.md`).
- **Phase 7:** Audio landscape, projectile/impact FX, unique 3D mesh + texture coverage for
  all 22 units and buildings, lightweight LUS piece animation, build icons/minimap symbols,
  and UI polish (see `docs/phase-7.md`).

**v0.7.0** marks the complete total conversion. Verification gate (current): **1825 tests
passing** and the headless integration probe emitting **6/6 PASS** verdicts — see "Local
verification" below.

Map scope remains **Quicksilver Remake 1.24**.

## Project structure

- `units/`: 22 medieval units and buildings (combat, economy, buildings, king, cart).
- `scripts/`: LUS unit scripts (procedural stride/swing/death motion) and pure-policy logic
  modules (economy, gather, haul, housing, tactics, damage types, skirmish AI).
- `luarules/gadgets/`: Synced gadgets — the medieval economy, logistics, market, garrison,
  tactics, victory, HUD publisher, gather, and FX wiring.
- `LuaUI/Widgets/`: Unsynced HUD and build-icon widgets.
- `gamedata/`: Weapon definitions, custom explosion generators (CEG), sounds, and icon types.
- `sounds/`: CC-BY-SA 3.0 0 A.D. weapon/economy/UI audio (see `tools/assets/0ad-sound-manifest.json`).
- `objects3d/0ad/`: Converted static 0 A.D. meshes (`.obj`) and their texture-map scripts (`.lua`).
- `unittextures/0ad/`: Converted 0 A.D. `.dds` textures.
- `bitmaps/`: Build-menu and radar/minimap icons.
- `tools/assets/`: 0 A.D. conversion tooling and SHA-256 provenance manifests.
- `tools/launch/`: Headless/GUI launchers, startscripts, and diagnostic probes.
- `tests/`: Pure-Lua/Python verification (unit defs, assets, policy modules, LUS animation).

## Licensing

Code is GPL-v2; see `LICENSE.md`. Art attribution and license references are in
`CREDITS.md` and `licenses/0ad-art.txt`.

Converted 0 A.D. meshes, textures, and audio are CC-BY-SA 3.0. Every asset's provenance is
tracked in `tools/assets/0ad-manifest.json` and `tools/assets/0ad-sound-manifest.json`.

BAR's CC-BY-NC-ND models, textures, and animations are not bundled or referenced by unit
definitions. Reused BAR GPL code is pinned to upstream commit
`c7eaa46992959435c6d3332e28e1169e1ddd43a6`. This repository declares no BAR content dependency.

## Prerequisites

- **Windows** and a copy of the Recoil `2026.07.04` engine downloaded to
  `tools/engine/recoil_2026.07.04/` (contains `spring.exe` and `spring-headless.exe`).
- The map `quicksilver_remake_1.24.sd7` placed at `tools/runtime/maps/quicksilver_remake_1.24.sd7`
  (the launchers auto-copy it if you already have it elsewhere on disk).
- **Python 3.10+** with `lupa` and `pytest` for verification only.

Engine binaries, maps, and the generated `tools/runtime/*` write sandbox are excluded from Git.

## How to launch the game

The fastest path uses the checked-in launchers, which first mirror the repository into an
isolated game directory (`tools/runtime/games/Medieval-BAR-TC.sdd`) so the runtime sandbox is
always in sync with the source tree.

### Windowed interactive game (human vs NullAI)

```pwsh
# From the repository root:
./tools/launch/launch-game.ps1
```

or equivalently:

```pwsh
python tools/launch/launch_game.py
```

This launches `spring.exe` with `tools/launch/startscript_play.txt`: you play Team 0 on
Quicksilver Remake, NullAI on Team 1, with the economy/HUD, market, garrison, tactics,
victory, audio, and build icons all enabled. The engine opens a normal interactive window.

### Headless simulation (CI probe)

```pwsh
python tools/launch/launch_game.py --headless
```

Uses `spring-headless.exe` with `--isolation` and the play startscript. It is a smoke run,
not an interactive match; use the dedicated probe below for a deterministic verdict.

### Manual launch (no helper script)

1. Mirror the source into the runtime game directory:
   ```pwsh
   & robocopy . tools/runtime/games/Medieval-BAR-TC.sdd /MIR /XD .git tools /XF .gitignore
   ```
2. Ensure `tools/runtime/maps/quicksilver_remake_1.24.sd7` exists.
3. Start the engine:
   ```pwsh
   & tools/engine/recoil_2026.07.04/spring.exe --write-dir tools/runtime tools/runtime/script.txt
   ```
   Copy a playable startscript (e.g. `tools/launch/startscript_play.txt`) to
   `tools/runtime/script.txt` first.

### Match options

`modoptions.lua` gates each subsystem. Flip them in the startscript's `[MODOPTIONS]` block,
or in the in-game lobby:

| Option | Default | Purpose |
| --- | --- | --- |
| `medievalvictory` | 0 | Victory/defeat engine |
| `victorymode` | `tc_destruction` | `conquest` / `tc_destruction` / `regicide` / `surrender` |
| `medievalhud` | 1 | Economy status HUD |
| `medievalmarket` | 0 | Market, barter, cart trade routes |
| `medievalgarrison` | 0 | Garrison shelter + healing |
| `medievaltactics` | 0 | Charges, bracing, flanking, stances |
| `medievalaudio` | 1 | Weapon/economy/UI sound set |
| `medievalbuildicons` | 1 | Build-menu pictures and minimap icons |

## Local verification

Install Python dependencies `lupa` and `pytest`, then run:

```pwsh
# 1. Lua syntax check (0 errors expected)
python tests/check_lua_syntax.py

# 2. Full pytest suite (1825 tests)
python -m pytest tests -q

# 3. Headless skirmish integration probe (expects "6/6 PASS" verdicts)
python tools/launch/run_phase5_slice6_probe.py

# 4. Death-clip probe (expects both baked and procedural modes to pass)
python tools/launch/run_phase7_death_probe.py
```

The unit tests do not establish in-engine visual acceptance; the headless probe exercises
the full live simulation (settlement spawn, economy flow, combat, town-center destruction,
and game-over) against the Recoil engine and harvests PASS verdicts from its infolog.