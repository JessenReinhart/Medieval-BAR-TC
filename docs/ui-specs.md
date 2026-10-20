# Medieval-BAR-TC UI Specifications & Asset Guidelines

## Overview

This document specifies the UI layout, texture assets, color palette, material
language, and typography standards for the medieval RTS interface inspired by
**0 A.D. (Wildfire Games)** and **Age of Empires II: Definitive Edition**.

All textures reside under `bitmaps/ui/` in clean RGBA format suitable for
direct OpenGL blitting via Recoil/Spring LuaUI (`gl.Texture`, `gl.TexRect`).
Every texture is 100% procedural art produced deterministically by
`tools/assets/generate_ui_textures.py` (Pillow + NumPy, pinned seeds). This is
GPL-v2 safe: no proprietary or CC-BY-NC-ND assets are used.

> **Material language (canonical):** *aged oak* (warm dark wood grain + gold
> bead inlay), *chiseled stone* (cool slate ashlar with mortar seams), and
> *antique bronze* (desaturated brass with verdigris accents). These three
> materials recur across `bar_background`, `panel_border`, `frame_corner`, and
> `minimap_frame` so the whole interface reads as one coherent set.

---

## 1. Texture Catalog & Specifications

### 1.1 Structural Surfaces

| File Path | Dimensions | Format | Usage & Description |
|-----------|------------|--------|---------------------|
| `bitmaps/ui/bar_background.png` | 512 x 64 px | RGBA 8-bit | Horizontal aged-oak plate with top/bottom gold bead rail and groove shadow. The bead repeat is 7 px per unit, so it tiles naturally when the bar is stretched wide or rendered at 52–56 px tall. Used for the top resource bar (`gui_medieval_hud.lua`) and bottom command deck (`gui_medieval_bottom_panel.lua`). |
| `bitmaps/ui/panel_border.png` | 128 x 128 px | RGBA 8-bit | 9-slice compatible oak/bronze/stone border frame (16 px rim) with square bronze rivet bosses at the corners. Used for modal dialogs, selection info cards, and tooltips. |
| `bitmaps/ui/frame_corner.png` | 64 x 64 px | RGBA 8-bit | Ornamental bronze/dark-stone corner bracket with a verdigris leaf finial. Blitted at outer panel corners for a manuscript/reliquary feel. |
| `bitmaps/ui/minimap_frame.png` | 256 x 256 px | RGBA 8-bit | Thick chiseled-stone frame **fill** (26 px band) with rounded bevels, bronze inner bearing inlay, and four N/S/E/W bronze cardinal medallions at edge midpoints. The center is punched transparent for the minimap viewport. **No round corner pocket circles.** |

### 1.2 Resource / Status Icons (64 x 64 px source)

These are drawn as **bold, high-contrast silhouettes** — heavy dark ink outline,
bright saturated fill, and a baked soft drop shadow — so they stay legible when
downscaled to 28–32 px on screen.

| File Path | Dimensions | Glyph |
|-----------|------------|-------|
| `bitmaps/ui/icon_food.png` | 64 x 64 px | Wheat sheaf / grain stalk: three curving ears with plump kernels, tied stalk bundle. |
| `bitmaps/ui/icon_wood.png` | 64 x 64 px | Two stacked cut logs (round end-grain faces) with a broadaxe. |
| `bitmaps/ui/icon_stone.png` | 64 x 64 px | Stacked cut masonry blocks (ashlar pyramid with bevel/chisel highlights). |
| `bitmaps/ui/icon_iron.png` | 64 x 64 px | Blacksmith's anvil: horn, polished face, narrow waist, flanged foot. |
| `bitmaps/ui/icon_pop.png` | 64 x 64 px | Peasant cottage silhouette: pitched roof, wall, arched door, window. |
| `bitmaps/ui/icon_idle.png` | 64 x 64 px | Town bell on timber yoke with clapper and vibration rings. |

### 1.3 Command Icons (32 x 32 px source)

Command icons use the same bold silhouette + dark outline + drop shadow style,
all legible at 24–28 px button sizes.

| File Path | Dimensions | Glyph |
|-----------|------------|-------|
| `bitmaps/ui/command_stop.png` | 32 x 32 px | Red octagonal stop badge with ivory diagonal cross. |
| `bitmaps/ui/command_move.png` | 32 x 32 px | Forward directional arrow / spearhead with fletching. |
| `bitmaps/ui/command_attack.png` | 32 x 32 px | Crossed broadswords with gold crossguards and pommels. |
| `bitmaps/ui/command_patrol.png` | 32 x 32 px | S-curve waypoint route with two heraldic flags. |
| `bitmaps/ui/command_hold.png` | 32 x 32 px | Kite/heater shield with central bronze umbo (hold ground). |
| `bitmaps/ui/command_stance.png` | 32 x 32 px | Shield with two stacked formation chevrons. |
| `bitmaps/ui/command_garrison.png` | 32 x 32 px | Fortified keep with battlements and a downward shelter arrow. |
| `bitmaps/ui/command_repair.png` | 32 x 32 px | Crossed mason's hammer and chisel. |

---

## 2. UV Mapping & 9-Slice Slicing Guides

### 2.1 Panel Border (`panel_border.png`) 9-Slice Coordinates

`panel_border.png` is 128x128 px. The border rim thickness is **16 px**:

- **Corner size:** 16 x 16 px (UV: `[0.0, 0.125]` and `[0.875, 1.0]`)
- **Top / Bottom Edge:** UV `u ∈ [0.125, 0.875]`, `v ∈ [0.0, 0.125]` (Top) / `v ∈ [0.875, 1.0]` (Bottom)
- **Left / Right Edge:** UV `u ∈ [0.0, 0.125]` (Left) / `u ∈ [0.875, 1.0]` (Right), `v ∈ [0.125, 0.875]`
- **Center Fill:** UV `u ∈ [0.125, 0.875]`, `v ∈ [0.125, 0.875]` (warm aged-oak panel fill)

### 2.2 Bar Background (`bar_background.png`) Tiling / Stretching

- Source size: 512 x 64 px.
- The top/bottom bead rail has a 7 px repeat and the wood grain is horizontal,
  so the texture can be stretched or GL_REPEAT-tiled without artifacts.
- **Recommended on-screen heights (top resource bar): 52–56 px.** The bar was
  previously rendered at 26 px and read as too short; use 52–56 px so the gold
  bead inlay reads cleanly.
- Bottom command deck: keep the same horizontal texture, stretched to
  recommended 120–160 px tall.

### 2.3 Minimap Frame (`minimap_frame.png`)

- 256 x 256 px; outer margin 10 px, frame band 26 px thick.
- Transparent viewport is the inner rounded rectangle from 36 px to 220 px.
- The bronze cardinal medallions sit on edge midpoints (not corners). No
  billiard-pocket circles anywhere.

---

## 3. UI Color Palette & Typography

### 3.1 Canonical Material Palette (hex)

These exact hex values are used by the generator and should be matched in any
Lua-drawn overlay for visual cohesion.

**Aged Oak**

| Role | Hex |
|------|-----|
| Oak dark | `#1c140d` |
| Oak mid | `#382a18` |
| Oak light | `#523c24` |
| Oak highlight | `#6c5030` |

**Chiseled Stone**

| Role | Hex |
|------|-----|
| Stone dark | `#2c2a28` |
| Stone mid | `#4e4a46` |
| Stone light | `#807870` |
| Stone highlight | `#a89a92` |
| Mortar | `#1e1c1a` |

**Antique Bronze**

| Role | Hex |
|------|-----|
| Bronze dark | `#2e2012` |
| Bronze mid | `#8a6432` |
| Bronze light | `#d0a860` |
| Bronze highlight | `#fae0a0` |
| Verdigris accent | `#587860` |

**Glyph / Icon Language**

| Role | Hex |
|------|-----|
| Ink outline | `#100c0a` |
| Ivory fill | `#e8dcc0` |
| Blood (stop) | `#a63a2a` |
| Steel | `#b8c0c8` |
| Wheat gold | `#e8b83c` (highlight `#f6d878`) |

### 3.2 Functional HUD Colors (RGBA Normalized)

- **Text Normal / Parchment:** `{ 0.92, 0.88, 0.80, 1.00 }` (`#EAE0CC`)
- **Antique Gold accent:** `{ 0.98, 0.85, 0.63, 1.00 }` (`#FAD9A0`)
- **Bronze bevel:** `{ 0.54, 0.39, 0.20, 1.00 }` (`#8A6432`)
- **Stockpile OK (green-gold):** `{ 0.55, 0.85, 0.35, 1.00 }`
- **Stockpile Low / Warning:** `{ 1.00, 0.75, 0.20, 1.00 }`
- **Stockpile Critical / Starvation:** `{ 1.00, 0.25, 0.20, 1.00 }`
- **Idle Worker Cyan:** `{ 0.75, 0.85, 1.00, 1.00 }`

### 3.3 Typography Guidelines

Recommended type feel: **serif / blackletter-adjacent** (medieval manuscript),
with strong x-height and small-caps numerals. Fall back to FreeSerif or a
blackletter webfont where available.

- **Top HUD resource numbers:** 14–16 px, serif/blackletter, drop shadow
  offset `(1, -1)` with `{ 0, 0, 0, 0.8 }`, parchment fill `#EAE0CC`.
- **Unit / Building titles:** 16–18 px, gold tint `#FAD9A0`, bold.
- **Stat readouts (HP/Armor/Damage):** 12–13 px, off-white `#E0DED1`.
- **Victory / Defeat banners:** 28–32 px, centered, serif small-caps with dark
  ink outline `#100C0A`.

---

## 4. Layout Architecture for Downstream Tasks

### Top Bar (`gui_medieval_hud.lua`)

- Spans top edge: `x = 0` to `viewSizeX`, top resource bar height **52–56 px**.
- Background texture: `bitmaps/ui/bar_background.png`.
- Left-to-right flow:
  1. Food Icon (`icon_food.png`, 28x28) + stockpile text.
  2. Wood Icon (`icon_wood.png`) + stockpile text.
  3. Stone Icon (`icon_stone.png`) + stockpile text.
  4. Iron Icon (`icon_iron.png`) + stockpile text.
  5. Pop Icon (`icon_pop.png`) + `"Pop: <curr>/<cap>"` text.
  6. Idle Icon (`icon_idle.png`) + idle villager count button.
  7. Starvation / warning alert indicator.

### Bottom Command Panel (`gui_medieval_bottom_panel.lua`)

- Centered at screen bottom or spanning bottom edge: `y = 0` to `140 px`.
- Left: selected unit portrait in ornamental frame (`panel_border.png`).
- Center: unit name, HP bar, armor, attack, formation status.
- Right: 3x4 command/build grid using `command_*.png` icons (28x28 blit).

### Minimap Panel (`gui_medieval_minimap.lua`)

- Anchored bottom-right/bottom-left (e.g. 220 x 220 px).
- Border overlay: `bitmaps/ui/minimap_frame.png` (thick stone fill, cardinal
  medallions) blitted over the Spring minimap rectangle.

---

## 5. Generator Script

The texture files are deterministically produced by:

```pwsh
python tools/assets/generate_ui_textures.py
```

Deterministic seeds are pinned per generator; icons are supersampled 4x and
LANCZOS-downscaled for crisp silhouettes. License: GPL-v2 compatible, 100%
original programmatic art.