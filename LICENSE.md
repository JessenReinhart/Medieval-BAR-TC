# LICENSE

This repository is released under the following terms. Individual files may carry more specific license notices.

## 1. Game Code (Mod Logic, Unit Definitions, Gadgets, Widgets, Scripts)
The Medieval-BAR-TC mod code and original placeholder geometry are licensed under:

    GNU General Public License, version 2 (GPL-2.0-only)
    See https://www.gnu.org/licenses/old-licenses/gpl-2.0.html

This includes:
- `units/*.lua`
- `scripts/*.lua` (original Lua Unit Scripts)
- `objects3d/*.obj`, `objects3d/*.mtl` (original placeholder geometry)
- `gamedata/*.lua`, `luarules/*`, `luaui/*`, `tools/*`, test suites

The Recoil Engine (upon which Beyond All Reason runs) requires all game code to be compatible with GPL v2 or later: https://github.com/beyond-all-reason/RecoilEngine

## 2. Upstream Beyond All Reason (BAR) Assets
This repository contains **no** BAR art assets. BAR's upstream licensing is reproduced here for reference and compliance.

Per BAR `license_general.txt` and `LICENSE.md` (pinned commit `c7eaa46992959435c6d3332e28e1169e1ddd43a6`):

- **Code:** BAR game code is released under the GPL v2 license.
- **Models by Cremuss:** released under the **CC-BY-SA 4.0** license.
- **All other models & textures** (FireStorm, Beherith, Mr Bob, Kaiser, KaiserJ, PtaQ, Flaka, Floris, etc.): released under the **CC-BY-NC-ND 4.0** license:
  > This license does not permit any derivative work, which includes, but is not limited to: mods, mutators, repackaging, and taking any artwork and including it or its derivative in any other game, or distribution outside of BAR.
- **All animations:** CC-BY-NC-ND 4.0 (c) Beherith.
- **Other Artwork:** see `license_bitmaps.txt`, `license_unitpics.txt`, `license_icons.txt`; otherwise all rights reserved.

The usage of any CC-BY-NC-ND licensed content from Beyond All Reason (BAR) as a dependency is not permitted, under the no-derivatives clause. Medieval-BAR-TC therefore uses only original placeholder geometry and scripts for the Phase 1 prototype.

## 3. Test suites under this project
Licensed under GPL-2.0-only, matching the mod code they validate.