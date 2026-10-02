# Credits and Attribution
=======================

## Project Origin & Mod Code
- Medieval Total Conversion (MedBAR) developed for Beyond All Reason on the Recoil RTS engine.
- Game code, unit configuration definitions, scripts, and automation test suites are licensed under the GNU General Public License v2 (GPL-2.0-only).

## Third-Party & Upstream BAR Asset Policy Compliance
- 0 A.D. low-poly unit models (infantry, archer, cavalry) and textures sourced from Wildfire Games' 0 A.D. repository under CC-BY-SA 3.0.

- **Pinned Upstream BAR Commit:** `c7eaa46992959435c6d3332e28e1169e1ddd43a6`
- **Upstream License Policy Check:** As documented in Beyond All Reason's `license_general.txt` and `LICENSE.md`:
  > *"The usage of any CC-BY-NC-ND licensed content from Beyond All Reason (BAR) as a dependency is not permitted, under the no-derivatives clause."*
  > *"All other models and textures are under the CC-BY-NC-ND 4.0 license (c) Beherith (mysterme@gmail.com)... This license does not permit any derivative work, which includes, but is not limited to: mods, mutators, repackaging, and taking any artwork and including it or its derivative in any other game, or distribution outside of BAR."*
- Models authored by Beherith, Mr Bob, Kaiser, FireStorm, Flaka, etc. are CC-BY-NC-ND 4.0 and are **strictly forbidden** from being imported, referenced, or used as mod dependencies.
- Models authored by Cremuss are CC-BY-SA 4.0. However, exhaustive inspection of BAR land unit definitions confirms zero Cremuss models exist for infantry, melee, archer, or cavalry units (Cremuss models are limited to factory structures such as `armlab`).

## Prototype Placeholder Geometry & Scripts
- All unit definitions in `units/` reference original, local Phase 1 placeholder geometry:
  - `objects3d/medieval_placeholder.obj` (with `medieval_placeholder.mtl`): Original low-poly placeholder geometry created for Medieval-BAR-TC under GPL-2.0-only / CC0.
  - `scripts/medieval_infantry.lua`, `scripts/medieval_archer.lua`, `scripts/medieval_cavalry.lua`: Original Lua Unit Scripts (LUS) created for Medieval-BAR-TC under GPL-2.0-only.
- **Zero** CC-BY-NC-ND BAR 3D models (`armwar.s3o`, `armrock.s3o`, `armfav.s3o`), COB scripts, or sound assets are referenced or distributed by this repository.
