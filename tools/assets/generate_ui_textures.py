"""Generate authentic medieval/0 A.D./AoE style UI bitmap textures in ``bitmaps/ui/``.

Outputs:
    - ``bar_background.png``: 512x64 dark aged parchment/wood texture for top/bottom bars.
    - ``panel_border.png``: 128x128 ornamental antique bronze/stone border slice (9-slice compatible).
    - ``frame_corner.png``: 64x64 ornamental antique bronze/stone corner ornament.
    - ``icon_food.png``: 48x48 RGBA wheat sheaf / grain harvest icon.
    - ``icon_wood.png``: 48x48 RGBA chopped wood logs / axe icon.
    - ``icon_stone.png``: 48x48 RGBA stone block / quarry masonry icon.
    - ``icon_iron.png``: 48x48 RGBA iron ingot / anvil icon.
    - ``icon_pop.png``: 48x48 RGBA population helmet / peasant silhouette icon.
    - ``icon_idle.png``: 48x48 RGBA idle villager bell / sleeping worker indicator icon.
    - ``minimap_frame.png``: 256x256 circular/square medieval compass stone/bronze frame.

The art is deterministic, original, GPL-v2 compatible, and rendered via Pillow and NumPy.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "bitmaps" / "ui"

# Palette definitions matching 0 A.D. & AoE aesthetics
# Dark aged wood / parchment
WOOD_DARK = np.array([28, 20, 14], dtype=np.float32)
WOOD_MID = np.array([48, 36, 24], dtype=np.float32)
WOOD_LIGHT = np.array([72, 54, 36], dtype=np.float32)

# Antique Bronze / Gold
BRONZE_DARK = (52, 38, 22)
BRONZE_MID = (142, 108, 54)
BRONZE_LIGHT = (212, 178, 102)
BRONZE_HIGHLIGHT = (248, 224, 156)

# Stone / Slate
STONE_DARK = (42, 44, 46)
STONE_MID = (84, 88, 92)
STONE_LIGHT = (140, 144, 148)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def generate_bar_background(width: int = 512, height: int = 64) -> Image.Image:
    """Generate dark aged parchment & weathered oak panel texture."""
    # Base procedural wood grain + horizontal fiber
    np.random.seed(42)
    x = np.linspace(0, 1, width)
    y = np.linspace(0, 1, height)
    xx, yy = np.meshgrid(x, y)

    # Wood grain bands along X axis with high frequency streaks
    grain = (
        np.sin(yy * 32.0 + np.sin(xx * 8.0) * 0.8) * 0.15
        + np.sin(yy * 64.0) * 0.08
        + np.random.normal(0, 0.04, (height, width))
    )
    # Vignette at top and bottom edge
    edge_vignette = 1.0 - np.power(np.abs(yy - 0.5) * 2.0, 3.0) * 0.45
    # Bevel highlights at y=0..2 and shadow at y=height-3..height
    bevel = np.ones((height, width), dtype=np.float32)
    bevel[0:2, :] += 0.35
    bevel[-3:, :] -= 0.40

    intensity = (grain + 0.5) * edge_vignette * bevel
    intensity = np.clip(intensity, 0.0, 1.0)[:, :, np.newaxis]

    rgb = WOOD_DARK + (WOOD_LIGHT - WOOD_DARK) * intensity
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    # Alpha channel: opaque 245 with slight corner softening
    alpha = np.full((height, width), 245, dtype=np.uint8)
    rgba = np.dstack([rgb, alpha])
    img = Image.fromarray(rgba, "RGBA")

    # Add subtle ornamental trim lines (top golden bead, bottom dark groove)
    draw = ImageDraw.Draw(img)
    # Golden top inlay line
    draw.line([(0, 1), (width - 1, 1)], fill=(168, 132, 68, 220), width=1)
    draw.line([(0, 2), (width - 1, 2)], fill=(96, 72, 36, 180), width=1)
    # Bottom groove
    draw.line([(0, height - 2), (width - 1, height - 2)], fill=(16, 12, 8, 240), width=1)
    draw.line([(0, height - 1), (width - 1, height - 1)], fill=(64, 48, 28, 180), width=1)

    return img


def generate_panel_border(size: int = 128) -> Image.Image:
    """Generate 9-slice compatible ornamental antique bronze border frame."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer border dimensions
    b_width = 16
    # Outer dark stone rim
    draw.rectangle([0, 0, size - 1, size - 1], outline=STONE_DARK, width=2)
    # Bronze metallic relief
    for i in range(2, b_width - 2):
        t = (i - 2) / float(b_width - 4)
        # Highlight in center, darker edges
        if t < 0.4:
            c = tuple(int(BRONZE_DARK[j] + (BRONZE_LIGHT[j] - BRONZE_DARK[j]) * (t / 0.4)) for j in range(3))
        elif t < 0.6:
            c = BRONZE_HIGHLIGHT
        else:
            c = tuple(int(BRONZE_HIGHLIGHT[j] + (BRONZE_MID[j] - BRONZE_HIGHLIGHT[j]) * ((t - 0.6) / 0.4)) for j in range(3))
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline=(*c, 255), width=1)

    # Inner dark shadow groove
    draw.rectangle([b_width - 2, b_width - 2, size - b_width + 1, size - b_width + 1], outline=(18, 14, 10, 255), width=2)

    # Central area filled with semi-transparent aged parchment
    inner_box = [b_width, b_width, size - b_width - 1, size - b_width - 1]
    draw.rectangle(inner_box, fill=(28, 22, 16, 235))

    # Decorative corner studs/rivets in 4 corners
    stud_radius = 4
    for cx, cy in [(8, 8), (size - 9, 8), (8, size - 9), (size - 9, size - 9)]:
        draw.ellipse([cx - stud_radius, cy - stud_radius, cx + stud_radius, cy + stud_radius], fill=BRONZE_LIGHT, outline=BRONZE_DARK)
        draw.point((cx - 1, cy - 1), fill=(255, 245, 210))

    return img


def generate_frame_corner(size: int = 64) -> Image.Image:
    """Generate ornamental corner bracket/boss for UI panels."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Filigree bracket pointing into the corner (top-left)
    # Outer decorative scroll
    points = [
        (4, 4), (size - 6, 4), (size - 14, 12), (18, 12),
        (12, 18), (12, size - 14), (4, size - 6)
    ]
    draw.polygon(points, fill=BRONZE_MID, outline=BRONZE_DARK)

    # Inner raised relief
    inner_pts = [
        (7, 7), (size - 18, 7), (size - 22, 10), (14, 10),
        (10, 14), (10, size - 22), (7, size - 18)
    ]
    draw.polygon(inner_pts, fill=BRONZE_HIGHLIGHT)

    # Central embossed gemstone / rivet boss
    bx, by = 14, 14
    r = 7
    draw.ellipse([bx - r, by - r, bx + r, by + r], fill=BRONZE_DARK, outline=(20, 15, 10))
    draw.ellipse([bx - r + 2, by - r + 2, bx + r - 2, by + r - 2], fill=BRONZE_LIGHT)
    draw.point((bx - 1, by - 1), fill=(255, 255, 230))

    # Corner filigree accents
    draw.arc([16, 16, size - 8, size - 8], start=180, end=270, fill=BRONZE_LIGHT, width=2)
    draw.arc([18, 18, size - 10, size - 10], start=180, end=270, fill=BRONZE_DARK, width=1)

    return img


def _create_icon_canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    return img, d


def _draw_icon_base_plate(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Draw circular/rounded antique bronze coin backing with dark core."""
    pad = 2
    box = [pad, pad, size - 1 - pad, size - 1 - pad]
    # Dark shadow rim
    draw.ellipse([box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1], fill=(12, 10, 8, 180))
    # Bronze outer bevel
    draw.ellipse(box, fill=BRONZE_DARK, outline=(18, 14, 10, 240))
    # Inner metallic ring
    draw.ellipse([box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2], outline=BRONZE_LIGHT)
    # Dark inner field for icon clarity
    draw.ellipse([box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3], fill=(22, 18, 14, 230))


def generate_icon_food(size: int = 48) -> Image.Image:
    """Food icon: Golden wheat sheaf / bundle of grain."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    # Wheat stalks curving outward
    GOLD_DEEP = (186, 134, 32)
    GOLD_BRIGHT = (248, 206, 64)
    GOLD_LIGHT = (255, 240, 160)

    center_x = s // 2
    base_y = int(s * 0.78)

    # Tied ribbon at bottom
    draw.rectangle([center_x - int(s * 0.08), base_y - int(s * 0.06), center_x + int(s * 0.08), base_y], fill=(160, 40, 32), outline=(90, 20, 16))

    # Grains along 3 stalks (left, center, right)
    for stalk_angle, stalk_x_off in [(-0.25, -s * 0.12), (0.0, 0.0), (0.25, s * 0.12)]:
        # Draw curved stem
        stem_pts = [
            (center_x, base_y),
            (center_x + stalk_x_off * 0.6, s * 0.52),
            (center_x + stalk_x_off, s * 0.24)
        ]
        draw.line(stem_pts, fill=GOLD_DEEP, width=max(2, int(s * 0.035)))

        # Grains on stalk
        top_y = s * 0.24
        for k in range(5):
            gy = top_y + k * (s * 0.08)
            gx = center_x + stalk_x_off * (0.3 + 0.7 * (1.0 - k / 5.0))
            # Left grain
            draw.ellipse([gx - s * 0.07, gy - s * 0.035, gx - s * 0.005, gy + s * 0.035], fill=GOLD_BRIGHT, outline=GOLD_DEEP)
            draw.point((int(gx - s * 0.04), int(gy)), fill=GOLD_LIGHT)
            # Right grain
            draw.ellipse([gx + s * 0.005, gy - s * 0.035, gx + s * 0.07, gy + s * 0.035], fill=GOLD_BRIGHT, outline=GOLD_DEEP)
            draw.point((int(gx + s * 0.04), int(gy)), fill=GOLD_LIGHT)

    # Top grain tip
    draw.ellipse([center_x - s * 0.03, s * 0.16, center_x + s * 0.03, s * 0.24], fill=GOLD_LIGHT, outline=GOLD_DEEP)

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_icon_wood(size: int = 48) -> Image.Image:
    """Wood icon: Chopped logs and forester's iron axe."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    # Log stack
    LOG_BARK = (78, 52, 32)
    LOG_WOOD = (194, 154, 102)
    LOG_RING = (144, 108, 68)

    # Bottom log
    bx1, by1 = int(s * 0.22), int(s * 0.58)
    bx2, by2 = int(s * 0.76), int(s * 0.78)
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=int(s * 0.08), fill=LOG_BARK, outline=(40, 26, 16))
    # Cut end face (circle)
    end_x, end_y = bx1 + int(s * 0.08), (by1 + by2) // 2
    er = int(s * 0.09)
    draw.ellipse([end_x - er, end_y - er, end_x + er, end_y + er], fill=LOG_WOOD, outline=LOG_BARK)
    draw.ellipse([end_x - er // 2, end_y - er // 2, end_x + er // 2, end_y + er // 2], outline=LOG_RING)

    # Axe handle (diagonal)
    handle_start = (int(s * 0.28), int(s * 0.78))
    handle_end = (int(s * 0.72), int(s * 0.22))
    draw.line([handle_start, handle_end], fill=(160, 115, 68), width=int(s * 0.07))
    draw.line([handle_start, handle_end], fill=(80, 50, 28), width=int(s * 0.02))

    # Axe head (steel blade)
    blade_pts = [
        (int(s * 0.62), int(s * 0.20)),
        (int(s * 0.82), int(s * 0.18)),
        (int(s * 0.86), int(s * 0.38)),
        (int(s * 0.68), int(s * 0.35)),
    ]
    draw.polygon(blade_pts, fill=(180, 190, 200), outline=(80, 85, 95))
    # Sharp edge highlight
    draw.line([(int(s * 0.82), int(s * 0.18)), (int(s * 0.86), int(s * 0.38))], fill=(245, 250, 255), width=max(2, int(s * 0.02)))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_icon_stone(size: int = 48) -> Image.Image:
    """Stone icon: Cut masonry blocks with chiseled facets."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    # Ashlar masonry block (isometric perspective)
    # Top face
    top_face = [
        (int(s * 0.50), int(s * 0.22)),
        (int(s * 0.76), int(s * 0.36)),
        (int(s * 0.50), int(s * 0.48)),
        (int(s * 0.24), int(s * 0.36))
    ]
    draw.polygon(top_face, fill=(175, 180, 185), outline=(90, 95, 100))

    # Left face
    left_face = [
        (int(s * 0.24), int(s * 0.36)),
        (int(s * 0.50), int(s * 0.48)),
        (int(s * 0.50), int(s * 0.74)),
        (int(s * 0.24), int(s * 0.62))
    ]
    draw.polygon(left_face, fill=(110, 115, 120), outline=(60, 65, 70))

    # Right face
    right_face = [
        (int(s * 0.50), int(s * 0.48)),
        (int(s * 0.76), int(s * 0.36)),
        (int(s * 0.76), int(s * 0.62)),
        (int(s * 0.50), int(s * 0.74))
    ]
    draw.polygon(right_face, fill=(140, 145, 150), outline=(70, 75, 80))

    # Stone chisel cracks/chiseled lines
    draw.line([(int(s * 0.36), int(s * 0.44)), (int(s * 0.42), int(s * 0.58))], fill=(80, 85, 90), width=max(1, int(s * 0.015)))
    draw.line([(int(s * 0.60), int(s * 0.45)), (int(s * 0.64), int(s * 0.55))], fill=(100, 105, 110), width=max(1, int(s * 0.015)))

    # Smaller secondary stone at bottom-left
    s_top = [(int(s * 0.18), int(s * 0.64)), (int(s * 0.34), int(s * 0.60)), (int(s * 0.32), int(s * 0.72)), (int(s * 0.16), int(s * 0.76))]
    draw.polygon(s_top, fill=(150, 155, 160), outline=(80, 85, 90))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_icon_iron(size: int = 48) -> Image.Image:
    """Iron icon: Heavy blacksmith's anvil and iron ingot."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    # Anvil silhouette: flat top horn pointing left, block body, flared foot
    # Horn (left horn, flat face, right step)
    horn = [
        (int(s * 0.20), int(s * 0.36)),  # Horn tip
        (int(s * 0.36), int(s * 0.34)),
        (int(s * 0.76), int(s * 0.34)),  # Top face
        (int(s * 0.78), int(s * 0.44)),
        (int(s * 0.66), int(s * 0.48)),  # Waist right
        (int(s * 0.72), int(s * 0.70)),  # Foot right
        (int(s * 0.28), int(s * 0.70)),  # Foot left
        (int(s * 0.36), int(s * 0.48)),  # Waist left
    ]
    # Dark steel base
    draw.polygon(horn, fill=(75, 82, 92), outline=(35, 40, 48))

    # Top struck face highlight
    face_pts = [
        (int(s * 0.34), int(s * 0.34)),
        (int(s * 0.76), int(s * 0.34)),
        (int(s * 0.74), int(s * 0.40)),
        (int(s * 0.35), int(s * 0.40))
    ]
    draw.polygon(face_pts, fill=(185, 198, 212), outline=(100, 110, 124))

    # Glowing heat streak or forge spark on top
    draw.line([(int(s * 0.50), int(s * 0.36)), (int(s * 0.58), int(s * 0.36))], fill=(255, 230, 180), width=max(2, int(s * 0.025)))

    # Ingot bar below anvil
    ingot = [
        (int(s * 0.32), int(s * 0.73)),
        (int(s * 0.68), int(s * 0.73)),
        (int(s * 0.64), int(s * 0.81)),
        (int(s * 0.36), int(s * 0.81))
    ]
    draw.polygon(ingot, fill=(130, 140, 155), outline=(50, 55, 65))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_icon_pop(size: int = 48) -> Image.Image:
    """Population icon: Medieval pot-helm / soldier silhouette."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    cx = s // 2

    # Shoulder armor / tunic base
    shoulders = [
        (int(s * 0.18), int(s * 0.82)),
        (int(s * 0.34), int(s * 0.62)),
        (int(s * 0.66), int(s * 0.62)),
        (int(s * 0.82), int(s * 0.82)),
    ]
    draw.polygon(shoulders, fill=(90, 75, 55), outline=(45, 35, 25))

    # Norman conical helmet / kettle hat
    # Brim
    draw.ellipse([int(s * 0.24), int(s * 0.48), int(s * 0.76), int(s * 0.58)], fill=(150, 160, 172), outline=(65, 72, 82))
    # Dome
    dome = [
        (int(s * 0.28), int(s * 0.52)),
        (cx, int(s * 0.20)),
        (int(s * 0.72), int(s * 0.52))
    ]
    draw.polygon(dome, fill=(175, 185, 198), outline=(65, 72, 82))
    # Nasal guard
    draw.rectangle([cx - int(s * 0.03), int(s * 0.50), cx + int(s * 0.03), int(s * 0.66)], fill=(120, 130, 142), outline=(55, 60, 70))

    # Helmet specular crest
    draw.line([(cx - 1, int(s * 0.24)), (cx - 1, int(s * 0.50))], fill=(240, 245, 255), width=max(2, int(s * 0.03)))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_icon_idle(size: int = 48) -> Image.Image:
    """Idle villager icon: Medieval warning bell with idle exclamation mark."""
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _draw_icon_base_plate(draw, s)

    cx = s // 2
    cy = int(s * 0.48)

    # Bronze church / town bell
    # Bell mount loop
    draw.arc([cx - int(s * 0.07), cy - int(s * 0.28), cx + int(s * 0.07), cy - int(s * 0.14)], start=0, end=360, fill=(140, 105, 50), width=max(2, int(s * 0.04)))

    # Bell body
    bell_pts = [
        (cx - int(s * 0.10), cy - int(s * 0.16)),
        (cx + int(s * 0.10), cy - int(s * 0.16)),
        (cx + int(s * 0.22), cy + int(s * 0.18)),
        (cx - int(s * 0.22), cy + int(s * 0.18))
    ]
    draw.polygon(bell_pts, fill=(215, 168, 64), outline=(110, 80, 30))

    # Flared lip
    draw.ellipse([cx - int(s * 0.25), cy + int(s * 0.14), cx + int(s * 0.25), cy + int(s * 0.24)], fill=(235, 190, 85), outline=(110, 80, 30))

    # Clapper
    draw.ellipse([cx - int(s * 0.05), cy + int(s * 0.20), cx + int(s * 0.05), cy + int(s * 0.30)], fill=(75, 50, 20))

    # Zzz sleep indicator or alert badge in top-right
    badge_x, badge_y = int(s * 0.72), int(s * 0.28)
    draw.ellipse([badge_x - int(s * 0.12), badge_y - int(s * 0.12), badge_x + int(s * 0.12), badge_y + int(s * 0.12)], fill=(210, 48, 36), outline=(90, 18, 12))
    # Exclamation mark inside badge
    draw.line([(badge_x, badge_y - int(s * 0.07)), (badge_x, badge_y + int(s * 0.01))], fill=(255, 255, 240), width=max(2, int(s * 0.035)))
    draw.point((badge_x, badge_y + int(s * 0.06)), fill=(255, 255, 240))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_minimap_frame(size: int = 256) -> Image.Image:
    """Generate ornamental medieval compass/stone style border for minimap widget."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 8
    box = [margin, margin, size - 1 - margin, size - 1 - margin]

    # Outer aged masonry square frame
    draw.rounded_rectangle(box, radius=12, fill=(26, 22, 18, 240), outline=STONE_DARK, width=4)
    # Inner bronze ring inlay
    draw.rounded_rectangle([box[0] + 4, box[1] + 4, box[2] - 4, box[3] - 4], radius=9, outline=BRONZE_MID, width=2)
    draw.rounded_rectangle([box[0] + 7, box[1] + 7, box[2] - 7, box[3] - 7], radius=7, outline=(15, 12, 10, 255), width=2)

    # 4 Corner bosses / compass rose brackets
    corner_r = 14
    for cx, cy in [
        (margin + 6, margin + 6),
        (size - margin - 7, margin + 6),
        (margin + 6, size - margin - 7),
        (size - margin - 7, size - margin - 7)
    ]:
        draw.ellipse([cx - corner_r, cy - corner_r, cx + corner_r, cy + corner_r], fill=BRONZE_DARK, outline=(20, 15, 10))
        draw.ellipse([cx - corner_r + 3, cy - corner_r + 3, cx + corner_r - 3, cy + corner_r - 3], fill=BRONZE_MID, outline=BRONZE_LIGHT)
        # Gem/rivet center
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=BRONZE_HIGHLIGHT)

    # Compass cardinal indicators (N, S, E, W marks on frame edges)
    mid = size // 2
    # North pointer
    draw.polygon([(mid, margin - 2), (mid - 6, margin + 7), (mid + 6, margin + 7)], fill=BRONZE_HIGHLIGHT, outline=BRONZE_DARK)
    # South pointer
    draw.polygon([(mid, size - margin + 2), (mid - 6, size - margin - 7), (mid + 6, size - margin - 7)], fill=BRONZE_MID, outline=BRONZE_DARK)
    # West pointer
    draw.polygon([(margin - 2, mid), (margin + 7, mid - 6), (margin + 7, mid + 6)], fill=BRONZE_MID, outline=BRONZE_DARK)
    # East pointer
    draw.polygon([(size - margin + 2, mid), (size - margin - 7, mid - 6), (size - margin - 7, mid + 6)], fill=BRONZE_MID, outline=BRONZE_DARK)

    # Punch out transparent center for minimap viewport (leaving clear space for Spring minimap rendering)
    # Viewport region from margin+12 to size - margin - 13
    vp = (margin + 10, margin + 10, size - margin - 11, size - margin - 11)
    # Draw hollow cutout in RGBA
    center_clear = Image.new("RGBA", (vp[2] - vp[0] + 1, vp[3] - vp[1] + 1), (0, 0, 0, 0))
    img.paste(center_clear, (vp[0], vp[1]))

    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR, help="Destination directory for textures")
    parser.add_argument("--icon-size", type=int, default=48, help="Size of resource icons (px)")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    _ensure_dir(out_dir)

    print(f"Generating UI textures into {out_dir}...")

    # 1. Bar background
    bar = generate_bar_background(512, 64)
    bar.save(out_dir / "bar_background.png")
    print("  -> bar_background.png (512x64)")

    # 2. Panel border & frame corner
    border = generate_panel_border(128)
    border.save(out_dir / "panel_border.png")
    print("  -> panel_border.png (128x128)")

    corner = generate_frame_corner(64)
    corner.save(out_dir / "frame_corner.png")
    print("  -> frame_corner.png (64x64)")

    # 3. Resource & status icons
    icon_gens = [
        ("icon_food.png", generate_icon_food),
        ("icon_wood.png", generate_icon_wood),
        ("icon_stone.png", generate_icon_stone),
        ("icon_iron.png", generate_icon_iron),
        ("icon_pop.png", generate_icon_pop),
        ("icon_idle.png", generate_icon_idle),
    ]

    for fname, gen in icon_gens:
        ico = gen(args.icon_size)
        ico.save(out_dir / fname)
        print(f"  -> {fname} ({args.icon_size}x{args.icon_size})")

    # 4. Minimap frame
    minimap = generate_minimap_frame(256)
    minimap.save(out_dir / "minimap_frame.png")
    print("  -> minimap_frame.png (256x256)")

    print("UI texture generation complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
