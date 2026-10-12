"""Generate the medieval radar/minimap icon set in ``bitmaps/icons/``.

The engine loads ``gamedata/icontypes.lua`` at boot
(``CIconHandler::LoadIcons``) and every UnitDef names one of those types via
``iconType`` (``UnitDef.cpp``: ``iconName = udTable.GetString("iconType",
"default")``). The named bitmap is the unit's radar blip and the sprite drawn
in place of the 3D mesh when the camera zooms out.

Icons follow the engine's own convention (``bitmaps/defaultradardot.png`` in
``base/spring/bitmaps.sdz``): an RGBA bitmap whose RGB is plain white so the
renderer can modulate it with the owner's team colour, and whose alpha channel
carries the symbol. The art here is original and GPL-v2; nothing is copied
from BAR (whose assets are CC-BY-NC-ND).

Usage:
    python tools/assets/generate_minimap_icons.py [--size 64]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "bitmaps" / "icons"

SUPERSAMPLE = 4
# Glyphs are drawn into a single-channel ("L") mask: 255 paints the symbol,
# 0 punches a hole in it. The white RGB is added afterwards so resampling can
# never bleed a grey fringe into the team-colour tint.
WHITE = 255
CUTOUT = 0

# icon type name -> (glyph function, human description)
# The name is the exact string UnitDefs put in `iconType` and the key used in
# gamedata/icontypes.lua.


def _p(size: float, x: float, y: float):
    return (x * size, y * size)


def _w(size: float, frac: float) -> int:
    return max(1, int(round(size * frac)))


def glyph_melee(d: ImageDraw.ImageDraw, s: float) -> None:
    """Crossed swords: every melee infantry weapon."""
    w = _w(s, 0.085)
    d.line([_p(s, 0.22, 0.82), _p(s, 0.80, 0.18)], fill=WHITE, width=w)
    d.line([_p(s, 0.78, 0.82), _p(s, 0.20, 0.18)], fill=WHITE, width=w)
    for x, y, dx in ((0.80, 0.18, 1), (0.20, 0.18, -1)):
        d.polygon(
            [
                _p(s, x, y),
                _p(s, x - 0.10 * dx, y + 0.04),
                _p(s, x - 0.03 * dx, y + 0.12),
            ],
            fill=WHITE,
        )
    d.line([_p(s, 0.30, 0.70), _p(s, 0.46, 0.78)], fill=WHITE, width=_w(s, 0.06))
    d.line([_p(s, 0.70, 0.70), _p(s, 0.54, 0.78)], fill=WHITE, width=_w(s, 0.06))


def glyph_spear(d: ImageDraw.ImageDraw, s: float) -> None:
    """Spear with a pennant: the anti-cavalry brace line."""
    d.line([_p(s, 0.26, 0.86), _p(s, 0.72, 0.20)], fill=WHITE, width=_w(s, 0.07))
    d.polygon(
        [_p(s, 0.74, 0.16), _p(s, 0.88, 0.10), _p(s, 0.80, 0.30)],
        fill=WHITE,
    )
    d.polygon(
        [_p(s, 0.52, 0.34), _p(s, 0.70, 0.30), _p(s, 0.54, 0.50)],
        fill=WHITE,
    )


def glyph_ranged(d: ImageDraw.ImageDraw, s: float) -> None:
    """Bow and arrow: longbow and crossbow lines."""
    d.arc(
        [_p(s, 0.16, 0.12), _p(s, 0.72, 0.88)],
        start=290,
        end=70,
        fill=WHITE,
        width=_w(s, 0.075),
    )
    d.line([_p(s, 0.62, 0.16), _p(s, 0.62, 0.84)], fill=WHITE, width=_w(s, 0.04))
    d.line([_p(s, 0.22, 0.50), _p(s, 0.84, 0.50)], fill=WHITE, width=_w(s, 0.06))
    d.polygon(
        [_p(s, 0.90, 0.50), _p(s, 0.76, 0.42), _p(s, 0.76, 0.58)],
        fill=WHITE,
    )


def glyph_cavalry(d: ImageDraw.ImageDraw, s: float) -> None:
    """Horse head: cavalry and knights."""
    d.polygon(
        [
            _p(s, 0.30, 0.88),
            _p(s, 0.34, 0.56),
            _p(s, 0.48, 0.32),
            _p(s, 0.64, 0.18),
            _p(s, 0.80, 0.28),
            _p(s, 0.68, 0.38),
            _p(s, 0.58, 0.54),
            _p(s, 0.56, 0.88),
        ],
        fill=WHITE,
    )
    d.polygon([_p(s, 0.62, 0.18), _p(s, 0.72, 0.06), _p(s, 0.80, 0.18)], fill=WHITE)
    d.ellipse([_p(s, 0.70, 0.28), _p(s, 0.76, 0.34)], fill=CUTOUT)


def glyph_siege(d: ImageDraw.ImageDraw, s: float) -> None:
    """Shield: the slow, heavily armoured siege train."""
    d.polygon(
        [
            _p(s, 0.50, 0.10),
            _p(s, 0.86, 0.24),
            _p(s, 0.84, 0.56),
            _p(s, 0.50, 0.90),
            _p(s, 0.16, 0.56),
            _p(s, 0.14, 0.24),
        ],
        fill=WHITE,
    )
    d.line([_p(s, 0.50, 0.20), _p(s, 0.50, 0.80)], fill=CUTOUT, width=_w(s, 0.07))
    d.line([_p(s, 0.22, 0.38), _p(s, 0.78, 0.38)], fill=CUTOUT, width=_w(s, 0.07))


def glyph_builder(d: ImageDraw.ImageDraw, s: float) -> None:
    """Hammer: villagers and any future builder unit."""
    d.rectangle(
        [_p(s, 0.16, 0.16), _p(s, 0.66, 0.34)], fill=WHITE
    )
    d.polygon([_p(s, 0.66, 0.14), _p(s, 0.86, 0.26), _p(s, 0.66, 0.38)], fill=WHITE)
    d.line([_p(s, 0.44, 0.34), _p(s, 0.34, 0.88)], fill=WHITE, width=_w(s, 0.11))


def glyph_supply(d: ImageDraw.ImageDraw, s: float) -> None:
    """Handcart: the supply cart and future haulers."""
    d.rectangle([_p(s, 0.20, 0.34), _p(s, 0.82, 0.58)], outline=WHITE, width=_w(s, 0.07))
    d.line([_p(s, 0.20, 0.46), _p(s, 0.82, 0.46)], fill=WHITE, width=_w(s, 0.04))
    d.line([_p(s, 0.20, 0.38), _p(s, 0.06, 0.24)], fill=WHITE, width=_w(s, 0.06))
    d.ellipse([_p(s, 0.24, 0.54), _p(s, 0.46, 0.76)], outline=WHITE, width=_w(s, 0.06))
    d.ellipse([_p(s, 0.56, 0.54), _p(s, 0.78, 0.76)], outline=WHITE, width=_w(s, 0.06))


def glyph_royal(d: ImageDraw.ImageDraw, s: float) -> None:
    """Crown: the King and the Town Center."""
    d.polygon(
        [
            _p(s, 0.14, 0.66),
            _p(s, 0.14, 0.28),
            _p(s, 0.32, 0.48),
            _p(s, 0.50, 0.20),
            _p(s, 0.68, 0.48),
            _p(s, 0.86, 0.28),
            _p(s, 0.86, 0.66),
        ],
        fill=WHITE,
    )
    d.rectangle([_p(s, 0.14, 0.66), _p(s, 0.86, 0.80)], fill=WHITE)


def glyph_military_building(d: ImageDraw.ImageDraw, s: float) -> None:
    """Tent: Barracks and Stables."""
    d.polygon(
        [_p(s, 0.50, 0.14), _p(s, 0.90, 0.84), _p(s, 0.10, 0.84)],
        fill=WHITE,
    )
    d.polygon(
        [_p(s, 0.50, 0.14), _p(s, 0.66, 0.84), _p(s, 0.34, 0.84)],
        fill=CUTOUT,
    )
    d.line([_p(s, 0.08, 0.86), _p(s, 0.92, 0.86)], fill=WHITE, width=_w(s, 0.08))


def glyph_economy_building(d: ImageDraw.ImageDraw, s: float) -> None:
    """Roofed storehouse: Granary, House, Lumber Camp, Market, Blacksmith, Fletcher."""
    d.rectangle([_p(s, 0.20, 0.46), _p(s, 0.80, 0.86)], fill=WHITE)
    d.polygon(
        [_p(s, 0.10, 0.46), _p(s, 0.50, 0.14), _p(s, 0.90, 0.46)],
        fill=WHITE,
    )
    d.rectangle([_p(s, 0.40, 0.62), _p(s, 0.60, 0.86)], fill=CUTOUT)


def glyph_defense(d: ImageDraw.ImageDraw, s: float) -> None:
    """Crenellated tower: Watchtower and Stone Wall."""
    d.rectangle([_p(s, 0.30, 0.34), _p(s, 0.70, 0.88)], fill=WHITE)
    for i in range(2):
        x = 0.30 + i * 0.24
        d.rectangle([_p(s, x, 0.18), _p(s, x + 0.16, 0.36)], fill=WHITE)
    d.rectangle([_p(s, 0.44, 0.56), _p(s, 0.56, 0.70)], fill=CUTOUT)


ICON_TYPES = (
    ("medieval_melee", glyph_melee, "Crossed swords: melee infantry"),
    ("medieval_spear", glyph_spear, "Pennanted spear: anti-cavalry spearmen"),
    ("medieval_ranged", glyph_ranged, "Bow and arrow: longbow and crossbow"),
    ("medieval_cavalry", glyph_cavalry, "Horse head: cavalry and knights"),
    ("medieval_siege", glyph_siege, "Shield: the siege train"),
    ("medieval_builder", glyph_builder, "Hammer: villagers and builders"),
    ("medieval_supply", glyph_supply, "Handcart: supply carts"),
    ("medieval_royal", glyph_royal, "Crown: King and Town Center"),
    ("medieval_military_building", glyph_military_building, "Tent: Barracks and Stables"),
    ("medieval_economy_building", glyph_economy_building, "Storehouse: economy buildings"),
    ("medieval_defense", glyph_defense, "Tower: Watchtower and Stone Wall"),
)


def render(glyph, size: int) -> Image.Image:
    """Draw the glyph at ``SUPERSAMPLE``x and box-downscale for clean edges.

    Only the alpha channel is resampled; RGB stays exactly white so the engine
    can modulate the icon with the owner's team colour (the convention used by
    ``bitmaps/defaultradardot.png``). Resampling the RGB too would leave grey
    fringes on the anti-aliased edges.
    """
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    glyph(ImageDraw.Draw(mask), float(big))
    mask = mask.resize((size, size), Image.LANCZOS)

    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    img.putalpha(mask)
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=64, help="square edge in pixels")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, glyph, _desc in ICON_TYPES:
        img = render(glyph, args.size)
        img.save(args.out / f"{name}.png", format="PNG", optimize=True)
        print(f"wrote {args.out / (name + '.png')}")

    print(f"{len(ICON_TYPES)} radar icons generated at {args.size}x{args.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
