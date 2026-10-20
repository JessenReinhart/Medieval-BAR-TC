"""Generate AAA medieval UI bitmap textures in ``bitmaps/ui/``.

All art is deterministic (pinned seeds), 100% procedural, and GPL-v2 compatible
(Pillow + NumPy only). No proprietary or CC-BY-NC-ND assets are used.

Material language (aged oak + chiseled stone + antique bronze) is shared across:
    - ``bar_background.png``  512x64  horizontal aged-oak top/bottom bar with
                                      gold bead inlay, usable tiled at ~52-56px.
    - ``panel_border.png``    128x128 9-slice compatible oak/bronze/stone rim.
    - ``frame_corner.png``     64x64  ornamental bronze/stone corner boss.
    - ``icon_*.png``           64x64  BOLD, high-contrast silhouette resource
                                      icons (dark outline, bright fill, baked
                                      drop shadow) that survive 28-32px blits.
    - ``command_*.png``        32x32  command button icons in the same bold
                                      silhouette language.
    - ``minimap_frame.png``   256x256 thick CHISELED-STONE frame fill with
                                      rounded bevels and N/S/E/W bronze
                                      medallions (no pocket circles).

Usage:
    python tools/assets/generate_ui_textures.py
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "bitmaps" / "ui"

# ---------------------------------------------------------------------------
# Palette (documented in docs/ui-specs.md). Hex values are canonical.
# ---------------------------------------------------------------------------
HEX = {
    # Aged oak
    "oak_dark":    "#1c140d",
    "oak_mid":     "#382a18",
    "oak_light":   "#523c24",
    "oak_hi":      "#6c5030",
    # Chiseled stone
    "stone_dark":  "#2c2a28",
    "stone_mid":   "#4e4a46",
    "stone_light": "#807870",
    "stone_hi":    "#a89a92",
    "mortar":      "#1e1c1a",
    # Antique bronze
    "bronze_dark": "#2e2012",
    "bronze_mid":  "#8a6432",
    "bronze_light":"#d0a860",
    "bronze_hi":   "#fae0a0",
    "verdigris":   "#587860",
    # Glyph / icon language
    "ink":         "#100c0a",
    "ivory":       "#e8dcc0",
    "blood":       "#a63a2a",
    "blood_hi":    "#d84834",
    "steel":       "#b8c0c8",
    "steel_hi":    "#e4ecf4",
    "wheat":       "#e8b83c",
    "wheat_hi":    "#f6d878",
    "wood_bark":   "#4c321c",
    "wood_face":   "#cf9e5a",
    "wood_ring":   "#8c582c",
}


def _rgb(name: str) -> tuple[int, int, int]:
    h = HEX[name].lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


INK = _rgb("ink")
SHADOW_FILL = (10, 8, 6, 210)

# Supersampling factor for icons: draw large, then LANCZOS-downscale.
SS = 4


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _V(v: float, s: int) -> int:
    """Fraction of s -> integer pixel coordinate."""
    return int(round(v * s))


def _P(seq, s: int):
    """[(fx, fy), ...] -> list of integer (x, y) at scale s."""
    return [(_V(x, s), _V(y, s)) for x, y in seq]


def _B(box, s: int):
    """[fx0, fy0, fx1, fy1] -> list of integer [x0, y0, x1, y1] at scale s."""
    return [_V(box[0], s), _V(box[1], s), _V(box[2], s), _V(box[3], s)]


def _wood_texture(w: int, h: int, seed: int):
    """Return an (h, w, 3) uint8 aged-oak RGB array."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    x = xx.astype(np.float32) / w
    y = yy.astype(np.float32) / h

    grain = (
        np.sin(y * 26.0 + np.sin(x * 9.0) * 0.9) * 0.16
        + np.sin(y * 71.0) * 0.07
        + np.sin(x * 3.0 + y * 5.0) * 0.03
        + rng.normal(0.0, 0.035, (h, w))
    )
    vign = 1.0 - 0.45 * np.abs(y - 0.5) ** 1.6
    shade = 0.5 + grain * vign
    shade = np.clip(shade, 0.0, 1.0)[..., None]

    dark = np.array(_rgb("oak_dark"), dtype=np.float32)
    mid = np.array(_rgb("oak_mid"), dtype=np.float32)
    light = np.array(_rgb("oak_light"), dtype=np.float32)

    rgb = np.where(
        shade < 0.5,
        dark + (mid - dark) * (shade * 2.0),
        mid + (light - mid) * ((shade - 0.5) * 2.0),
    )
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _stone_texture(w: int, h: int, seed: int, block: int = 24):
    """Return an (h, w, 3) uint8 chiseled-stone RGB array."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]

    nbx = int(math.ceil(w / block)) + 1
    nby = int(math.ceil(h / block)) + 1
    cell = rng.uniform(-0.08, 0.08, (nby, nbx))
    cv = np.repeat(np.repeat(cell, block, axis=0), block, axis=1)[:h, :w]

    noise = rng.normal(0.0, 0.045, (h, w))
    chisel = 0.5 + 0.5 * np.sin((xx * 0.75) + (yy * 0.28)) * 0.06

    mortar = (
        ((xx % block) < 1.2) | ((yy % block) < 1.2)
    ).astype(np.float32)

    shade = 0.5 + noise + cv + chisel - mortar * 0.38
    shade = np.clip(shade, 0.0, 1.0)[..., None]

    dark = np.array(_rgb("stone_dark"), dtype=np.float32)
    mid = np.array(_rgb("stone_mid"), dtype=np.float32)
    light = np.array(_rgb("stone_light"), dtype=np.float32)

    rgb = np.where(
        shade < 0.5,
        dark + (mid - dark) * (shade * 2.0),
        mid + (light - mid) * ((shade - 0.5) * 2.0),
    )
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _render_icon(size: int, glyph_fn, colors: dict) -> Image.Image:
    """Draw a glyph on a transparent canvas, bake a soft drop shadow, and
    downscale LANCZOS. glyph_fn(draw, s, C, OW, OUTLINE)."""
    s = size * SS
    ow = max(3, int(s * 0.038))

    # ---- drop shadow (uniform silhouette, blurred, offset) ----
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sc = {k: (12, 10, 8, 200) for k in colors}
    glyph_fn(sd, s, sc, ow, (12, 10, 8, 200))
    blur_r = max(2, int(round(s * 0.032)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_r))

    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ox, oy = int(s * 0.035), int(s * 0.045)
    canvas.paste(shadow, (ox, oy), shadow)

    # ---- real glyph: bright fill + heavy dark outline ----
    glyph = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    glyph_fn(gd, s, colors, ow, INK)
    canvas.alpha_composite(glyph)

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# Bar / panel / frame surfaces
# ---------------------------------------------------------------------------

def generate_bar_background(width: int = 512, height: int = 64) -> Image.Image:
    """512x64 aged-oak bar with gold bead inlay, designed to tile wide."""
    w, h = width, height
    rgb = _wood_texture(w, h, seed=42)

    yy, xx = np.mgrid[0:h, 0:w]
    x = xx.astype(np.float32) / w
    y = yy.astype(np.float32) / h
    sheen = (np.sin(x * 12.0 + y * 3.0) * 0.5 + 0.5) * 0.08
    sheen_a = (
        sheen[..., None].astype(np.float32)
        * np.array(_rgb("oak_hi"), dtype=np.float32)
    )
    rgb = np.clip(rgb.astype(np.float32) + sheen_a, 0, 255).astype(np.uint8)

    alpha = np.full((h, w), 250, dtype=np.uint8)
    img = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)

    # Top and bottom bronze bead rails (scales naturally as a repeating bead).
    bead_hi, bead_mid, bead_dark = (
        _rgb("bronze_hi"),
        _rgb("bronze_light"),
        _rgb("bronze_dark"),
    )
    for ybase in (3, h - 9):
        for bx in range(2, w - 4, 7):
            d.ellipse([bx, ybase, bx + 5, ybase + 5], fill=bead_dark)
            d.ellipse([bx + 1, ybase + 1, bx + 4, ybase + 4], fill=bead_mid)
            d.point((bx + 2, ybase + 2), fill=bead_hi)

    # Rail grooves flanking the beads.
    d.line([(0, 0), (w - 1, 0)], fill=_rgb("oak_hi"), width=1)
    d.line([(0, 1), (w - 1, 1)], fill=_rgb("bronze_mid"), width=1)
    d.line([(0, h - 1), (w - 1, h - 1)], fill=_rgb("oak_dark"), width=1)
    d.line([(0, 10), (w - 1, 10)], fill=(20, 14, 9, 230), width=1)
    d.line([(0, h - 11), (w - 1, h - 11)], fill=(20, 14, 9, 230), width=1)
    return img


def generate_panel_border(size: int = 128) -> Image.Image:
    """128x128 9-slice compatible ornamental antique bronze & stone border."""
    w = h = size
    rgb = _wood_texture(w, h, seed=1337)
    alpha = np.full((h, w), 255, dtype=np.uint8)
    img = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)

    band = 16
    for i in range(4):
        inset = i
        col = _rgb("stone_dark" if i < 2 else "stone_light")
        d.rectangle([inset, inset, w - 1 - inset, h - 1 - inset], outline=col, width=1)

    d.rectangle([5, 5, w - 6, h - 6], outline=_rgb("bronze_mid"), width=2)
    d.rectangle([7, 7, w - 8, h - 8], outline=_rgb("bronze_dark"), width=1)
    d.rectangle([band - 2, band - 2, w - band + 1, h - band + 1],
                outline=(16, 12, 8, 220), width=1)

    # Center fill: warm oak panel tint
    d.rectangle([band, band, w - 1 - band, h - 1 - band], fill=(42, 32, 22, 100))

    # Corner rivet bosses (chiseled square bronze accents)
    for cx, cy in ((band - 3, band - 3), (w - band + 2, band - 3),
                   (band - 3, h - band + 2), (w - band + 2, h - band + 2)):
        d.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], fill=_rgb("bronze_mid"))
        d.point((cx, cy), fill=_rgb("bronze_hi"))
    return img


def generate_frame_corner(size: int = 64) -> Image.Image:
    """Ornamental 64x64 bronze/stone corner boss."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ox, oy = 4, 4

    # Stone backing bracket
    d.polygon([(ox, s - oy), (ox, oy), (s - ox, oy), (s - ox, oy + 8),
               (ox + 8, oy + 8), (ox + 8, s - oy)],
              fill=_rgb("stone_mid"), outline=_rgb("stone_dark"), width=2)
    d.polygon([(ox, s - oy), (ox, oy), (ox + 8, oy + 8), (ox + 8, s - oy - 10)],
              fill=_rgb("stone_light"), outline=_rgb("stone_dark"), width=1)

    # Bronze filigree scroll
    d.line([(ox + 6, s - oy - 4), (s // 2 - 2, s // 2 + 4)], fill=_rgb("bronze_mid"), width=4)
    d.line([(s // 2 - 4, s // 2 + 4), (s - ox - 4, ox + 10)], fill=_rgb("bronze_mid"), width=4)
    d.line([(ox + 8, s - oy - 6), (s // 2 - 2, s // 2 + 4)], fill=_rgb("bronze_hi"), width=1)

    # Leaf finial
    d.ellipse([s // 2 - 5, s // 2 - 1, s // 2 + 5, s // 2 + 9],
              fill=_rgb("verdigris"), outline=_rgb("bronze_dark"), width=1)
    return img


# ---------------------------------------------------------------------------
# Resource / status icons (64x64 source)
# ---------------------------------------------------------------------------

def _glyph_food(d, s, C, ow, O):
    """Wheat sheaf / grain stalk: 3 curving ears + tied stalk bundle."""
    tie = (0.50, 0.58)

    # Bottom flare of cut stalks
    for fx in (0.36, 0.43, 0.50, 0.57, 0.64):
        d.line(_P([tie, (fx, 0.90)], s), fill=O, width=ow + 2)
        d.line(_P([tie, (fx, 0.90)], s), fill=C["wheat"], width=max(1, ow))

    # Three grain ears: left, center, right
    ears = [
        (-0.24, [(0.46, 0.44), (0.34, 0.28), (0.24, 0.12)]),
        (0.00,  [(0.50, 0.40), (0.50, 0.24), (0.50, 0.08)]),
        (0.24,  [(0.54, 0.44), (0.66, 0.28), (0.76, 0.12)]),
    ]

    for lean, pts in ears:
        full_pts = [tie] + pts
        d.line(_P(full_pts, s), fill=O, width=ow + 2)
        d.line(_P(full_pts, s), fill=C["wheat_hi"], width=max(1, ow))
        # Grain kernels along the stalk
        for pt in pts:
            px, py = pt
            for kdx in (-0.05, 0.05):
                box = [px + kdx - 0.045, py - 0.055, px + kdx + 0.045, py + 0.055]
                d.ellipse(_B(box, s), fill=C["wheat"], outline=O, width=max(1, ow - 1))
                d.ellipse(_B([box[0] + 0.01, box[1] + 0.01, box[2] - 0.01, box[3] - 0.02], s),
                          fill=C["wheat_hi"])

    # Binding band around the sheaf
    band_box = [0.38, 0.54, 0.62, 0.63]
    d.rounded_rectangle(_B(band_box, s), radius=_V(0.02, s), fill=C["wheat_hi"], outline=O, width=ow)
    d.line(_P([(0.40, 0.58), (0.60, 0.58)], s), fill=O, width=max(1, ow - 1))


def _glyph_wood(d, s, C, ow, O):
    """Stacked logs + broadaxe."""
    # Bottom log
    d.rounded_rectangle(_B([0.10, 0.56, 0.88, 0.76], s), radius=_V(0.05, s),
                        fill=C["bark"], outline=O, width=ow)
    # Bottom log face
    d.ellipse(_B([0.10, 0.56, 0.28, 0.76], s), fill=C["wood"], outline=O, width=ow)
    d.ellipse(_B([0.14, 0.60, 0.24, 0.72], s), outline=C["ring"], width=max(1, ow - 1))

    # Top log
    d.rounded_rectangle(_B([0.18, 0.38, 0.84, 0.56], s), radius=_V(0.05, s),
                        fill=C["bark"], outline=O, width=ow)
    # Top log face
    d.ellipse(_B([0.18, 0.38, 0.34, 0.56], s), fill=C["wood"], outline=O, width=ow)
    d.ellipse(_B([0.21, 0.41, 0.31, 0.53], s), outline=C["ring"], width=max(1, ow - 1))

    # Axe handle (diagonal)
    d.line(_P([(0.30, 0.86), (0.72, 0.16)], s), fill=O, width=ow + 4)
    d.line(_P([(0.30, 0.86), (0.72, 0.16)], s), fill=C["haft"], width=max(2, ow + 1))

    # Axe head (heavy steel blade)
    blade = [(0.62, 0.14), (0.88, 0.10), (0.92, 0.36), (0.70, 0.30)]
    d.polygon(_P(blade, s), fill=C["steel"], outline=O, width=ow)
    d.line(_P([(0.68, 0.18), (0.86, 0.14)], s), fill=C["steel_hi"], width=max(1, ow - 1))


def _glyph_stone(d, s, C, ow, O):
    """Stacked cut masonry blocks (sturdy 3-block ashlar pyramid)."""
    # Two foundation blocks
    b1 = [0.12, 0.54, 0.48, 0.82]
    b2 = [0.52, 0.54, 0.88, 0.82]
    # One keystone centered on top
    b3 = [0.26, 0.22, 0.74, 0.52]

    for b in (b1, b2, b3):
        d.rounded_rectangle(_B(b, s), radius=_V(0.025, s), fill=C["block"], outline=O, width=ow)
        # Bevel highlight on top edge
        d.line(_P([(b[0] + 0.02, b[1] + 0.02), (b[2] - 0.02, b[1] + 0.02)], s),
               fill=C["block_hi"], width=max(1, ow - 1))
        # Bevel highlight on left edge
        d.line(_P([(b[0] + 0.02, b[1] + 0.02), (b[0] + 0.02, b[3] - 0.02)], s),
               fill=C["block_hi"], width=max(1, ow - 1))
        # Chisel dressing marks
        my = (b[1] + b[3]) / 2
        d.line(_P([(b[0] + 0.08, my), (b[2] - 0.08, my)], s),
               fill=C["block_hi"], width=max(1, ow - 2))


def _glyph_iron(d, s, C, ow, O):
    """Blacksmith's anvil (pointed horn, flat face, flanged base)."""
    # Horn (left triangle)
    horn = [(0.10, 0.34), (0.28, 0.24), (0.28, 0.42)]
    d.polygon(_P(horn, s), fill=C["steel"], outline=O, width=ow)

    # Face plate (flat polished striking surface)
    d.rectangle(_B([0.26, 0.22, 0.86, 0.38], s), fill=C["steel"], outline=O, width=ow)
    # Bright polished face highlight
    d.line(_P([(0.28, 0.25), (0.84, 0.25)], s), fill=C["steel_hi"], width=max(2, ow - 1))

    # Waist (narrow central pillar)
    waist = [(0.36, 0.38), (0.72, 0.38), (0.68, 0.58), (0.40, 0.58)]
    d.polygon(_P(waist, s), fill=C["iron"], outline=O, width=ow)

    # Base footing (heavy stepped flanged foot)
    base = [(0.26, 0.58), (0.78, 0.58), (0.90, 0.82), (0.16, 0.82)]
    d.polygon(_P(base, s), fill=C["steel"], outline=O, width=ow)
    d.line(_P([(0.20, 0.78), (0.86, 0.78)], s), fill=C["steel_hi"], width=max(1, ow - 2))


def _glyph_pop(d, s, C, ow, O):
    """Peasant cottage / house silhouette (pitched roof, door, window)."""
    # Pitched roof (eaves extend beyond walls)
    roof = [(0.12, 0.44), (0.50, 0.12), (0.88, 0.44)]
    d.polygon(_P(roof, s), fill=C["roof"], outline=O, width=ow)
    d.line(_P([(0.14, 0.42), (0.50, 0.14), (0.86, 0.42)], s), fill=C["roof_hi"], width=max(1, ow - 1))

    # Cottage body
    d.rectangle(_B([0.22, 0.42, 0.78, 0.84], s), fill=C["wall"], outline=O, width=ow)

    # Arched doorway
    d.rectangle(_B([0.38, 0.56, 0.56, 0.84], s), fill=C["door"], outline=O, width=ow)
    d.ellipse(_B([0.38, 0.48, 0.56, 0.62], s), fill=C["door"], outline=O, width=ow)

    # Glass window
    d.rectangle(_B([0.62, 0.52, 0.72, 0.64], s), fill=C["window"], outline=O, width=max(1, ow - 1))


def _glyph_idle(d, s, C, ow, O):
    """Medieval town / church bell (yoke beam, bell body, clapper)."""
    # Timber yoke / mounting bracket
    d.rounded_rectangle(_B([0.32, 0.12, 0.68, 0.24], s), radius=_V(0.03, s),
                        fill=C["wood"], outline=O, width=ow)

    # Clapper hanging below
    d.line(_P([(0.50, 0.60), (0.50, 0.84)], s), fill=O, width=ow + 2)
    d.ellipse(_B([0.44, 0.76, 0.56, 0.88], s), fill=C["bronze_hi"], outline=O, width=ow)

    # Bell body
    bell = [(0.38, 0.24), (0.62, 0.24), (0.76, 0.64), (0.24, 0.64)]
    d.polygon(_P(bell, s), fill=C["bronze"], outline=O, width=ow)

    # Flared bell rim / lip
    d.rounded_rectangle(_B([0.20, 0.62, 0.80, 0.72], s), radius=_V(0.03, s),
                        fill=C["bronze"], outline=O, width=ow)
    d.line(_P([(0.24, 0.64), (0.76, 0.64)], s), fill=C["bronze_hi"], width=max(2, ow - 1))

    # Sound vibration rings
    for side in (-1, 1):
        cx = 0.50 + side * 0.38
        d.arc(_B([cx - 0.08, 0.52, cx + 0.08, 0.72], s),
              start=90 - side * 60, end=90 + side * 60, fill=C["bronze_hi"], width=max(1, ow - 1))


# ---------------------------------------------------------------------------
# Command icons (32x32 source)
# ---------------------------------------------------------------------------

def _glyph_stop(d, s, C, ow, O):
    """Octagonal red stop heraldic shield with bold ivory X."""
    pts = []
    for i in range(8):
        a = math.radians(22.5 + i * 45.0)
        pts.append((0.50 + 0.42 * math.cos(a), 0.50 + 0.42 * math.sin(a)))
    d.polygon(_P(pts, s), fill=C["fill"], outline=O, width=ow)

    # Inner bevel highlight
    inner_pts = []
    for i in range(8):
        a = math.radians(22.5 + i * 45.0)
        inner_pts.append((0.50 + 0.36 * math.cos(a), 0.50 + 0.36 * math.sin(a)))
    d.polygon(_P(inner_pts, s), outline=C["hi"], width=max(1, ow - 2))

    # Bold diagonal cross (X)
    d.line(_P([(0.30, 0.30), (0.70, 0.70)], s), fill=O, width=ow + 4)
    d.line(_P([(0.70, 0.30), (0.30, 0.70)], s), fill=O, width=ow + 4)
    d.line(_P([(0.30, 0.30), (0.70, 0.70)], s), fill=C["hi"], width=max(2, ow))
    d.line(_P([(0.70, 0.30), (0.30, 0.70)], s), fill=C["hi"], width=max(2, ow))


def _glyph_move(d, s, C, ow, O):
    """Forward arrow / directional spearhead (upper-right 45 deg)."""
    # Shaft
    d.line(_P([(0.22, 0.78), (0.64, 0.36)], s), fill=O, width=ow + 5)
    d.line(_P([(0.22, 0.78), (0.64, 0.36)], s), fill=C["fill"], width=max(3, ow + 1))
    d.line(_P([(0.24, 0.76), (0.62, 0.38)], s), fill=C["hi"], width=max(1, ow - 1))

    # Large arrowhead
    head = [(0.50, 0.22), (0.86, 0.14), (0.78, 0.50), (0.66, 0.38)]
    d.polygon(_P(head, s), fill=C["fill"], outline=O, width=ow)
    d.line(_P([(0.66, 0.38), (0.84, 0.16)], s), fill=C["hi"], width=max(1, ow - 1))

    # Fletching at tail
    d.polygon(_P([(0.16, 0.84), (0.28, 0.84), (0.22, 0.72)], s), fill=C["fill"], outline=O, width=ow)
    d.polygon(_P([(0.16, 0.84), (0.16, 0.72), (0.28, 0.78)], s), fill=C["fill"], outline=O, width=ow)


def _glyph_attack(d, s, C, ow, O):
    """Crossed broadswords (razor-sharp blades + gold crossguards)."""
    for flip in (1, -1):
        x0, y0 = (0.24, 0.76) if flip == 1 else (0.76, 0.76)
        x1, y1 = (0.76, 0.24) if flip == 1 else (0.24, 0.24)
        # Blade
        d.line(_P([(x0, y0), (x1, y1)], s), fill=O, width=ow + 4)
        d.line(_P([(x0, y0), (x1, y1)], s), fill=C["blade"], width=max(2, ow + 1))
        d.line(_P([(x0, y0), (x1, y1)], s), fill=C["hi"], width=max(1, ow - 1))

        # Crossguard
        gx = (x0 * 2 + x1) / 3
        gy = (y0 * 2 + y1) / 3
        dx, dy = (0.10, -0.10) if flip == 1 else (0.10, 0.10)
        d.line(_P([(gx - dx, gy - dy), (gx + dx, gy + dy)], s), fill=O, width=ow + 2)
        d.line(_P([(gx - dx, gy - dy), (gx + dx, gy + dy)], s), fill=C["guard"], width=max(1, ow))

        # Pommel
        d.ellipse(_B([x0 - 0.05, y0 - 0.05, x0 + 0.05, y0 + 0.05], s),
                  fill=C["guard"], outline=O, width=max(1, ow - 1))


def _glyph_patrol(d, s, C, ow, O):
    """Heraldic flags on a waypoint route with circular patrol arrows."""
    # S-curve route path
    pts = [(0.20, 0.78), (0.40, 0.52), (0.60, 0.52), (0.80, 0.26)]
    d.line(_P(pts, s), fill=O, width=ow + 3)
    d.line(_P(pts, s), fill=C["path"], width=max(2, ow))

    # Start waypoint flag
    d.line(_P([(0.20, 0.56), (0.20, 0.82)], s), fill=O, width=ow + 1)
    d.polygon(_P([(0.20, 0.56), (0.38, 0.63), (0.20, 0.70)], s), fill=C["flag"], outline=O, width=ow)

    # End waypoint flag
    d.line(_P([(0.80, 0.08), (0.80, 0.34)], s), fill=O, width=ow + 1)
    d.polygon(_P([(0.80, 0.08), (0.96, 0.15), (0.80, 0.22)], s), fill=C["flag"], outline=O, width=ow)


def _glyph_hold(d, s, C, ow, O):
    """Medieval heater/kite shield with steel umbo/boss (hold ground)."""
    shield = [
        (0.50, 0.10),
        (0.82, 0.18),
        (0.82, 0.54),
        (0.50, 0.90),
        (0.18, 0.54),
        (0.18, 0.18),
    ]
    d.polygon(_P(shield, s), fill=C["fill"], outline=O, width=ow)

    # Inner bevel rim
    inner_shield = [
        (0.50, 0.16),
        (0.76, 0.22),
        (0.76, 0.52),
        (0.50, 0.82),
        (0.24, 0.52),
        (0.24, 0.22),
    ]
    d.polygon(_P(inner_shield, s), outline=C["hi"], width=max(1, ow - 1))

    # Center bronze umbo/boss
    d.ellipse(_B([0.40, 0.38, 0.60, 0.58], s), fill=C["boss"], outline=O, width=ow)
    d.point((_V(0.48, s), _V(0.46, s)), fill=C["hi"])

    # Spine reinforcement
    d.line(_P([(0.50, 0.12), (0.50, 0.38)], s), fill=C["hi"], width=max(1, ow - 1))
    d.line(_P([(0.50, 0.58), (0.50, 0.86)], s), fill=C["hi"], width=max(1, ow - 1))


def _glyph_stance(d, s, C, ow, O):
    """Rank formation chevrons inside a battle shield."""
    shield = [
        (0.50, 0.10),
        (0.84, 0.20),
        (0.84, 0.54),
        (0.50, 0.90),
        (0.16, 0.54),
        (0.16, 0.20),
    ]
    d.polygon(_P(shield, s), fill=C["fill"], outline=O, width=ow)

    # Two stacked chevrons indicating tactical stance
    for y_off in (-0.08, 0.12):
        c_pts = [
            (0.28, 0.44 + y_off),
            (0.50, 0.28 + y_off),
            (0.72, 0.44 + y_off),
            (0.66, 0.48 + y_off),
            (0.50, 0.36 + y_off),
            (0.34, 0.48 + y_off),
        ]
        d.polygon(_P(c_pts, s), fill=C["chev"], outline=O, width=max(1, ow - 1))


def _glyph_garrison(d, s, C, ow, O):
    """Fortified keep tower with downward sheltering entrance arrow."""
    # Tower battlements / roof
    crenels = [
        (0.22, 0.22), (0.34, 0.22), (0.34, 0.28),
        (0.44, 0.28), (0.44, 0.22), (0.56, 0.22),
        (0.56, 0.28), (0.66, 0.28), (0.66, 0.22),
        (0.78, 0.22), (0.78, 0.36), (0.22, 0.36),
    ]
    d.polygon(_P(crenels, s), fill=C["wall"], outline=O, width=ow)

    # Tower body
    d.rectangle(_B([0.24, 0.36, 0.76, 0.86], s), fill=C["wall"], outline=O, width=ow)

    # Dark portcullis / arched door
    d.rectangle(_B([0.38, 0.58, 0.62, 0.86], s), fill=C["door"], outline=O, width=ow)
    d.ellipse(_B([0.38, 0.50, 0.62, 0.66], s), fill=C["door"], outline=O, width=ow)

    # Downward garrison arrow pointing into the door
    arr = [
        (0.44, 0.36), (0.56, 0.36), (0.56, 0.48),
        (0.64, 0.48), (0.50, 0.62), (0.36, 0.48), (0.44, 0.48),
    ]
    d.polygon(_P(arr, s), fill=C["arrow"], outline=O, width=ow)


def _glyph_repair(d, s, C, ow, O):
    """Crossed mason's hammer and pick / chisel."""
    # Hammer haft
    d.line(_P([(0.24, 0.82), (0.72, 0.24)], s), fill=O, width=ow + 4)
    d.line(_P([(0.24, 0.82), (0.72, 0.24)], s), fill=C["haft"], width=max(2, ow + 1))

    # Hammer head (steel block)
    d.rectangle(_B([0.60, 0.14, 0.86, 0.34], s), fill=C["head"], outline=O, width=ow)
    d.line(_P([(0.62, 0.16), (0.84, 0.16)], s), fill=C["hi"], width=max(1, ow - 1))

    # Chisel haft & blade (crossing the hammer)
    d.line(_P([(0.76, 0.82), (0.28, 0.24)], s), fill=O, width=ow + 4)
    d.line(_P([(0.76, 0.82), (0.28, 0.24)], s), fill=C["haft"], width=max(2, ow + 1))

    # Chisel steel head
    chisel_pts = [(0.22, 0.18), (0.34, 0.18), (0.30, 0.30), (0.24, 0.30)]
    d.polygon(_P(chisel_pts, s), fill=C["head"], outline=O, width=ow)


def _glyph_guard(d, s, C, ow, O):
    """Kite shield with vigilant eye / crest for Guard command."""
    shield = [
        (0.50, 0.12),
        (0.82, 0.20),
        (0.82, 0.52),
        (0.50, 0.88),
        (0.18, 0.52),
        (0.18, 0.20),
    ]
    d.polygon(_P(shield, s), fill=C["fill"], outline=O, width=ow)
    # Inner border
    inner_shield = [
        (0.50, 0.18),
        (0.76, 0.25),
        (0.76, 0.50),
        (0.50, 0.82),
        (0.24, 0.50),
        (0.24, 0.25),
    ]
    d.polygon(_P(inner_shield, s), outline=C["hi"], width=max(1, ow - 1))
    # Eye of vigilance (guard ward)
    d.ellipse(_B([0.34, 0.38, 0.66, 0.58], s), fill=C["eye"], outline=O, width=ow - 1)
    d.ellipse(_B([0.44, 0.42, 0.56, 0.54], s), fill=O)


def _glyph_wait(d, s, C, ow, O):
    """Antique bronze hourglass with sand for Wait command."""
    # Hourglass glass bulbs (top & bottom triangles)
    top_bulb = [(0.28, 0.22), (0.72, 0.22), (0.50, 0.50)]
    bot_bulb = [(0.50, 0.50), (0.72, 0.78), (0.28, 0.78)]
    d.polygon(_P(top_bulb, s), fill=C["glass"], outline=O, width=ow)
    d.polygon(_P(bot_bulb, s), fill=C["glass"], outline=O, width=ow)

    # Sand
    d.polygon(_P([(0.36, 0.26), (0.64, 0.26), (0.50, 0.44)], s), fill=C["sand"])
    d.polygon(_P([(0.44, 0.62), (0.56, 0.62), (0.66, 0.76), (0.34, 0.76)], s), fill=C["sand"])

    # Bronze frame caps (top & bottom bars)
    d.rounded_rectangle(_B([0.22, 0.16, 0.78, 0.24], s), radius=int(s*0.03), fill=C["frame"], outline=O, width=ow)
    d.rounded_rectangle(_B([0.22, 0.76, 0.78, 0.84], s), radius=int(s*0.03), fill=C["frame"], outline=O, width=ow)
    # Side pillars
    d.line(_P([(0.26, 0.24), (0.26, 0.76)], s), fill=C["frame"], width=max(2, ow))
    d.line(_P([(0.74, 0.24), (0.74, 0.76)], s), fill=C["frame"], width=max(2, ow))


# ---------------------------------------------------------------------------
# Minimap frame (thick stone fill, no pocket circles)
# ---------------------------------------------------------------------------

def generate_minimap_frame(size: int = 256) -> Image.Image:
    """256x256 chiseled-stone frame FILL with rounded bevels and cardinal
    medallions. Transparent viewport in the center."""
    w = h = size
    margin = 10
    band = 26
    outer_radius = 16
    inner_radius = 10

    stone = _stone_texture(w, h, seed=2024, block=26)
    alpha = np.full((h, w), 255, dtype=np.uint8)
    img = Image.fromarray(np.dstack([stone, alpha]).astype(np.uint8), "RGBA")

    # Frame mask: outer rounded rect minus inner viewport rounded rect
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([margin, margin, w - 1 - margin, h - 1 - margin],
                         radius=outer_radius, fill=255)
    vp = [margin + band, margin + band, w - 1 - margin - band, h - 1 - margin - band]
    md.rounded_rectangle(vp, radius=inner_radius, fill=0)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)

    # Outer bevel: highlight top-left, shadow bottom-right
    d.rounded_rectangle([margin, margin, w - 1 - margin, h - 1 - margin],
                        radius=outer_radius, outline=_rgb("stone_hi"), width=3)
    d.rounded_rectangle([margin + 2, margin + 2, w - 3 - margin, h - 3 - margin],
                        radius=outer_radius - 2, outline=_rgb("stone_dark"), width=1)

    # Inner bevel around the viewport
    d.rounded_rectangle(vp, radius=inner_radius, outline=_rgb("stone_dark"), width=3)
    d.rounded_rectangle([vp[0] + 2, vp[1] + 2, vp[2] - 2, vp[3] - 2],
                        radius=inner_radius - 2, outline=_rgb("stone_hi"), width=1)

    # Bronze bearing inlay inside the stone, hugging the viewport
    d.rounded_rectangle([vp[0] - 5, vp[1] - 5, vp[2] + 5, vp[3] + 5],
                        radius=inner_radius + 2, outline=_rgb("bronze_mid"), width=2)

    mid = size // 2
    # N/S/E/W bronze cardinal medallions (edge midpoints)
    medallion_r = 9
    for cx, cy in ((mid, margin + 3), (mid, size - margin - 4),
                   (margin + 3, mid), (size - margin - 4, mid)):
        d.ellipse([cx - medallion_r, cy - medallion_r, cx + medallion_r, cy + medallion_r],
                  fill=_rgb("bronze_dark"), outline=_rgb("bronze_hi"), width=1)
        d.ellipse([cx - medallion_r + 2, cy - medallion_r + 2,
                   cx + medallion_r - 2, cy + medallion_r - 2],
                  fill=_rgb("bronze_mid"))
        d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=_rgb("bronze_hi"))

    # Cardinal pointer triangles (N bright, others mid)
    n_half = 6
    d.polygon([(mid, margin - 2), (mid - n_half, margin + 6), (mid + n_half, margin + 6)],
              fill=_rgb("bronze_hi"), outline=_rgb("bronze_dark"))
    d.polygon([(mid, size - margin + 1), (mid - n_half, size - margin - 7),
               (mid + n_half, size - margin - 7)],
              fill=_rgb("bronze_mid"), outline=_rgb("bronze_dark"))
    d.polygon([(margin - 2, mid), (margin + 6, mid - n_half), (margin + 6, mid + n_half)],
              fill=_rgb("bronze_mid"), outline=_rgb("bronze_dark"))
    d.polygon([(size - margin + 1, mid), (size - margin - 7, mid - n_half),
               (size - margin - 7, mid + n_half)],
              fill=_rgb("bronze_mid"), outline=_rgb("bronze_dark"))

    return img


# ---------------------------------------------------------------------------
# Registry / main
# ---------------------------------------------------------------------------

RESOURCE_ICONS = (
    ("icon_food.png", _glyph_food, {
        "wheat": _rgb("wheat"), "wheat_hi": _rgb("wheat_hi"),
    }),
    ("icon_wood.png", _glyph_wood, {
        "bark": _rgb("wood_bark"), "wood": _rgb("wood_face"), "ring": _rgb("wood_ring"),
        "haft": (150, 108, 60), "steel": _rgb("steel"), "steel_hi": _rgb("steel_hi"),
    }),
    ("icon_stone.png", _glyph_stone, {
        "block": _rgb("stone_light"), "block_hi": _rgb("stone_hi"),
    }),
    ("icon_iron.png", _glyph_iron, {
        "steel": _rgb("steel"), "iron": (70, 76, 82), "steel_hi": _rgb("steel_hi"),
    }),
    ("icon_pop.png", _glyph_pop, {
        "roof": (156, 72, 38), "roof_hi": (212, 114, 76), "wall": _rgb("ivory"),
        "door": (68, 40, 22), "window": (118, 152, 172),
    }),
    ("icon_idle.png", _glyph_idle, {
        "wood": (96, 68, 42), "bronze": _rgb("bronze_light"), "bronze_hi": _rgb("bronze_hi"),
    }),
)

COMMAND_ICONS = (
    ("command_stop.png", _glyph_stop, {
        "fill": _rgb("blood"), "hi": _rgb("ivory"),
    }),
    ("command_move.png", _glyph_move, {
        "fill": _rgb("ivory"), "hi": _rgb("bronze_hi"),
    }),
    ("command_attack.png", _glyph_attack, {
        "blade": _rgb("steel"), "guard": _rgb("bronze_mid"), "hi": _rgb("steel_hi"),
    }),
    ("command_patrol.png", _glyph_patrol, {
        "path": _rgb("ivory"), "flag": _rgb("bronze_light"),
    }),
    ("command_hold.png", _glyph_hold, {
        "fill": (118, 98, 72), "hi": _rgb("ivory"), "boss": _rgb("bronze_light"),
    }),
    ("command_stance.png", _glyph_stance, {
        "fill": (118, 98, 72), "chev": _rgb("bronze_light"),
    }),
    ("command_garrison.png", _glyph_garrison, {
        "wall": _rgb("stone_light"), "door": (40, 34, 28), "arrow": _rgb("bronze_light"),
    }),
    ("command_repair.png", _glyph_repair, {
        "haft": (150, 108, 60), "head": _rgb("steel"), "hi": _rgb("steel_hi"),
    }),
    ("command_guard.png", _glyph_guard, {
        "fill": (118, 98, 72), "hi": _rgb("ivory"), "eye": _rgb("bronze_light"),
    }),
    ("command_wait.png", _glyph_wait, {
        "glass": (180, 170, 150), "sand": (212, 178, 102),
        "frame": _rgb("bronze_mid"),
    }),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR,
                        help="Destination directory for textures")
    parser.add_argument("--resource-size", type=int, default=64,
                        help="Source size of resource icons (px)")
    parser.add_argument("--command-size", type=int, default=32,
                        help="Source size of command icons (px)")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    _ensure_dir(out_dir)
    print(f"Generating UI textures into {out_dir} ...")

    emitted = []

    bar = generate_bar_background(512, 64)
    bar.save(out_dir / "bar_background.png")
    emitted.append(("bar_background.png", bar.size))
    print(f"  -> bar_background.png {bar.size[0]}x{bar.size[1]}")

    panel = generate_panel_border(128)
    panel.save(out_dir / "panel_border.png")
    emitted.append(("panel_border.png", panel.size))
    print(f"  -> panel_border.png {panel.size[0]}x{panel.size[1]}")

    corner = generate_frame_corner(64)
    corner.save(out_dir / "frame_corner.png")
    emitted.append(("frame_corner.png", corner.size))
    print(f"  -> frame_corner.png {corner.size[0]}x{corner.size[1]}")

    for fname, glyph, colors in RESOURCE_ICONS:
        img = _render_icon(args.resource_size, glyph, colors)
        img.save(out_dir / fname)
        emitted.append((fname, img.size))
        print(f"  -> {fname} {img.size[0]}x{img.size[1]}")

    for fname, glyph, colors in COMMAND_ICONS:
        img = _render_icon(args.command_size, glyph, colors)
        img.save(out_dir / fname)
        emitted.append((fname, img.size))
        print(f"  -> {fname} {img.size[0]}x{img.size[1]}")

    minimap = generate_minimap_frame(256)
    minimap.save(out_dir / "minimap_frame.png")
    emitted.append(("minimap_frame.png", minimap.size))
    print(f"  -> minimap_frame.png {minimap.size[0]}x{minimap.size[1]}")

    # Verification: every expected file exists on disk
    missing = [fname for fname, _ in emitted if not (out_dir / fname).exists()]
    if missing:
        print(f"ERROR: missing output files: {missing}")
        return 1

    print(f"UI texture generation complete! {len(emitted)} files emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())