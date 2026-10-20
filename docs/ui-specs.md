# Medieval-BAR-TC UI Specifications & Asset Guidelines

## Overview
This document specifies the UI layout, texture assets, font styling, and dimension standards for the medieval RTS interface inspired by **0 A.D. (Wildfire Games)** and **Age of Empires II: Definitive Edition**.

All textures reside under `bitmaps/ui/` in clean RGBA format (power-of-two dimensions or standard GL aspect ratios) suitable for direct OpenGL blitting via Recoil/Spring LuaUI (`gl.Texture`, `gl.TexRect`).

---

## 1. Texture Catalog & Specifications

| File Path | Dimensions | Format | Usage & Description |
|-----------|------------|--------|---------------------|
| `bitmaps/ui/bar_background.png` | 512 x 64 px | RGBA 8-bit | Horizontal weathered oak / aged parchment plate with top golden inlay bead and bottom shadow groove. Used for top resource bar (`gui_medieval_hud.lua`) and bottom command deck (`gui_medieval_bottom_panel.lua`). |
| `bitmaps/ui/panel_border.png` | 128 x 128 px | RGBA 8-bit | 9-slice compatible antique bronze and chiseled stone border frame with 4 corner studs. Used for modal dialogs, selection info cards, and tooltips. |
| `bitmaps/ui/frame_corner.png` | 64 x 64 px | RGBA 8-bit | Ornamental antique bronze corner bracket and filigree boss. Blitted at outer panel corners to give an authentic medieval manuscript feel. |
| `bitmaps/ui/minimap_frame.png` | 256 x 256 px | RGBA 8-bit | Circular/square medieval stone compass frame with bronze cardinal pointers (N/S/E/W) and decorative corner bosses. Has a transparent center viewport for Recoil minimap rendering. |
| `bitmaps/ui/icon_food.png` | 48 x 48 px | RGBA 8-bit | Golden wheat sheaf on dark bronze plate. Used in top resource bar for Food stockpile. |
| `bitmaps/ui/icon_wood.png` | 48 x 48 px | RGBA 8-bit | Chopped logs and forester's iron axe on dark bronze plate. Used for Wood stockpile. |
| `bitmaps/ui/icon_stone.png` | 48 x 48 px | RGBA 8-bit | Cut ashlar masonry blocks on dark bronze plate. Used for Stone stockpile. |
| `bitmaps/ui/icon_iron.png` | 48 x 48 px | RGBA 8-bit | Heavy blacksmith's anvil and iron bar on dark bronze plate. Used for Iron stockpile. |
| `bitmaps/ui/icon_pop.png` | 48 x 48 px | RGBA 8-bit | Norman kettle-hat / conical pot-helm soldier on dark bronze plate. Used for Population status readout (`Pop: <current>/<cap>`). |
| `bitmaps/ui/icon_idle.png` | 48 x 48 px | RGBA 8-bit | Medieval bronze bell with alert badge on dark plate. Used for idle villager count and click-to-cycle button. |

---

## 2. UV Mapping & 9-Slice Slicing Guides

### 2.1 Panel Border (`panel_border.png`) 9-Slice Coordinates
`panel_border.png` is 128x128 px. The border rim thickness is **16 px**:
- **Corner size:** 16 x 16 px (UV: `[0.0, 0.125]` and `[0.875, 1.0]`)
- **Top / Bottom Edge:** UV `u ∈ [0.125, 0.875]`, `v ∈ [0.0, 0.125]` (Top) / `v ∈ [0.875, 1.0]` (Bottom)
- **Left / Right Edge:** UV `u ∈ [0.0, 0.125]` (Left) / `u ∈ [0.875, 1.0]` (Right), `v ∈ [0.125, 0.875]`
- **Center Fill:** UV `u ∈ [0.125, 0.875]`, `v ∈ [0.125, 0.875]` (Dark aged parchment fill)

### 2.2 Bar Background (`bar_background.png`) Tiling / Stretching
- Width: 512 px, Height: 64 px.
- For HUD bars spanning screen width $W$:
  - UV $U_{min} = 0.0$, $U_{max} = 1.0$ (stretched) or $U_{max} = W / 512.0$ (repeated along X with `GL_REPEAT`).
  - Top resource bar height: recommended 24–32 px.
  - Bottom command deck height: recommended 120–160 px.

---

## 3. UI Color Palette & Typography

Matching historical RTS conventions (0 A.D., AoE II DE):

### 3.1 Color Swatches (RGBA Normalized)
- **Parchment White / Text Normal:** `{ 0.92, 0.88, 0.80, 1.00 }` (`#EAE0CC`)
- **Antique Gold / Highlights:** `{ 0.98, 0.82, 0.35, 1.00 }` (`#FAD259`)
- **Bronze Frame / Bevel:** `{ 0.60, 0.46, 0.24, 1.00 }` (`#99753D`)
- **Aged Wood Dark / Panel BG:** `{ 0.11, 0.08, 0.06, 0.94 }` (`#1C140E`)
- **Stockpile OK (Greenish Gold):** `{ 0.55, 0.85, 0.35, 1.00 }`
- **Stockpile Low / Warning:** `{ 1.00, 0.75, 0.20, 1.00 }`
- **Stockpile Critical / Starvation Alert:** `{ 1.00, 0.25, 0.20, 1.00 }`
- **Idle Worker Cyan:** `{ 0.75, 0.85, 1.00, 1.00 }`

### 3.2 Typography Guidelines
- **Primary Engine Font:** Default FreeSans / medieval serif font loaded by Spring LuaUI.
- **Top HUD Resource Numbers:** Size 12–14 px, drop shadow offset `(1, -1)` with color `{ 0, 0, 0, 0.8 }`.
- **Unit / Building Titles:** Size 14–16 px, bold/gold tint `{ 0.98, 0.82, 0.35 }`.
- **Stat Readouts (HP, Armor, Damage):** Size 11–12 px, off-white `{ 0.88, 0.86, 0.82 }`.
- **Victory / Defeat Banners:** Size 28–32 px, centered, bold with dark outline.

---

## 4. Layout Architecture for Downstream Tasks

### Top Bar (`task-2` / `gui_medieval_hud.lua`):
- Spans top edge: `x = 0` to `viewSizeX`, `y = viewSizeY - 26` to `viewSizeY`.
- Background texture: `bitmaps/ui/bar_background.png`.
- Left-to-right flow:
  1. Food Icon (`bitmaps/ui/icon_food.png`, 18x18 or 20x20) + Stockpile text.
  2. Wood Icon (`bitmaps/ui/icon_wood.png`) + Stockpile text.
  3. Stone Icon (`bitmaps/ui/icon_stone.png`) + Stockpile text.
  4. Iron Icon (`bitmaps/ui/icon_iron.png`) + Stockpile text.
  5. Pop Icon (`bitmaps/ui/icon_pop.png`) + `"Pop: <curr>/<cap>"` text.
  6. Idle Icon (`bitmaps/ui/icon_idle.png`) + Idle villager count button.
  7. Starvation / Warning alert indicator.

### Bottom Command Panel (`task-3` / `gui_medieval_bottom_panel.lua`):
- Centered at screen bottom or spanning bottom edge: `y = 0` to `140 px`.
- Left: Selected unit portrait (`unitpics/<unitDef>.png`) in ornamental frame (`panel_border.png`).
- Center: Unit name, health bar (red/green), armor types, attack damage, and formation status.
- Right: 3x4 command / building grid with stone border slots.

### Minimap Panel (`task-4` / `gui_medieval_minimap.lua`):
- Anchored at bottom-right or bottom-left (e.g. 220 x 220 px).
- Border overlay: `bitmaps/ui/minimap_frame.png` blitted over Spring minimap rectangle.

---

## 5. Generator Script
The texture files are deterministically produced by:
```pwsh
python tools/assets/generate_ui_textures.py
```
License: GPL-v2 compatible, 100% original programmatic art.
