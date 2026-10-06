# Medieval-BAR-TC

A medieval total conversion prototype for the Recoil RTS engine, using BAR GPL code without BAR's restricted art assets.

## Current status

Phase 1 is **complete**. The repository contains a Recoil total conversion scaffold, BAR GPL gadget infrastructure, license-compatible static 0 A.D. models and textures, unit/formation tests, and a verified in-engine headless simulation with live combat exchange (spawn, movement, target acquisition, C++ weapon aim, ballistic arrow flight, melee strikes, damage events, and unit destruction). See [Phase 1 status](docs/phase-1.md) for evidence and details.

## Project structure

- `units/`: Infantry, archer, and cavalry definitions.
- `scripts/`: Unit scripts and line-formation math.
- `luarules/`: BAR GPL gadget handler and opt-in test forces gadget.
- `luaui/widgets/`: Formation preview and experimental test readiness widget.
- `gamedata/`: Movement, weapon, and explosion definitions.
- `objects3d/0ad/`, `unittextures/0ad/`: Converted static art.
- `tools/assets/`: Asset conversion tooling and provenance manifest.
- `tools/launch/`: Headless launcher, startscript, and diagnostic probes.
- `tests/`: Formation mocks, asset parser tests, and unit/license validation.
- `docs/city-building-design.md`: Future city-building design.

## Licensing

Code is GPL-v2; see `LICENSE.md`. Art attribution and license references are in `CREDITS.md` and `licenses/0ad-art.txt`.

BAR's CC-BY-NC-ND models, textures, and animations are not bundled or referenced by unit definitions. Reused BAR GPL code is pinned to upstream commit `c7eaa46992959435c6d3332e28e1169e1ddd43a6`. This repository does not declare a BAR content dependency.

## Local verification

Install Python dependencies `lupa` and `pytest`, then run:

```pwsh
python tests/test_phase1.py
python -m pytest tests -q
```

These checks do not establish in-engine combat acceptance.

## Headless diagnostics

The local setup uses official Recoil `2026.07.04` and map `Quicksilver Remake 1.24`. Engine binaries and map downloads are excluded from Git.

Place the engine in `tools/engine/recoil_2026.07.04/` and `quicksilver_remake_1.24.sd7` in `tools/runtime/maps/`, then run from the repository root:

```pwsh
./tools/launch/run-headless.ps1
# Alternate isolated diagnostic probe:
python tools/launch/run_gameprobe.py 15
```

Readiness probes are experiments, not a working unattended match launcher. Generated runtime directories and logs are excluded from Git.
