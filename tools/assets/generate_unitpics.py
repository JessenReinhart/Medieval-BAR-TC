"""Generate the 22 dedicated medieval build pictures in ``unitpics/``.

Every unit def in ``units/*.lua`` needs its own training/construction-menu
picture. The Recoil engine resolves a buildpic with the following order
(``CUnitDrawerData::SetUnitDefImage``, verified against the engine sources):

    1. ``buildPic`` if the def sets it (loaded as ``unitpics/<buildPic>``),
    2. otherwise ``unitpics/<unitDef name>.{dds,png,pcx,bmp}``,
    3. otherwise a solid red dummy bitmap.

This repository ships no BAR buildpics (CC-BY-NC-ND forbids them), so the
pictures are generated here instead of being converted from an upstream
source. The art is original, deterministic and GPL-v2 like the rest of the
mod code: a dark gradient plate, a bronze frame and a per-unit glyph so the
22 entries are visually distinct at build-menu size.

Usage:
    python tools/assets/generate_unitpics.py [--size 128]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "unitpics"

# Palette: a dark wooden plate, a bronze frame and parchment-white glyphs.
BG_TOP = (44, 34, 26)
BG_BOTTOM = (16, 13, 11)
FRAME = (154, 120, 64)
FRAME_INNER = (92, 70, 40)
GLYPH = (234, 224, 200)
GLYPH_DIM = (176, 162, 138)

# Accents group the roster the same way the build menus do.
ACCENT_MILITARY = (168, 58, 46)
ACCENT_ECONOMY = (108, 132, 74)
ACCENT_BUILDING = (120, 124, 136)
ACCENT_ROYAL = (198, 160, 62)


def _bg(size: int) -> Image.Image:
    """Vertical gradient plate, drawn row by row (no numpy dependency)."""
    img = Image.new("RGB", (size, size), BG_BOTTOM)
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)
        )
        draw.line([(0, y), (size, y)], fill=color)
    return img


def _frame(draw: ImageDraw.ImageDraw, size: int, accent) -> None:
    """Bronze border with an accent corner notch, plus an inner hairline."""
    draw.rectangle([0, 0, size - 1, size - 1], outline=FRAME, width=max(2, size // 32))
    inset = max(4, size // 16)
    draw.rectangle(
        [inset, inset, size - 1 - inset, size - 1 - inset],
        outline=FRAME_INNER,
        width=1,
    )
    notch = max(6, size // 12)
    draw.polygon(
        [(size - 1 - notch, 0), (size - 1, 0), (size - 1, notch)],
        fill=accent,
    )
    draw.polygon(
        [(0, size - 1 - notch), (0, size - 1), (notch, size - 1)],
        fill=accent,
    )


# --------------------------------------------------------------------------
# Glyph primitives. Every helper draws inside a normalised 0..1 box so the
# same glyph renders correctly at any --size.
# --------------------------------------------------------------------------


def _p(size: int, x: float, y: float) -> tuple[float, float]:
    return (x * size, y * size)


def _w(size: int, frac: float) -> int:
    return max(1, int(round(size * frac)))


def glyph_sword(d, size, color=GLYPH):
    w = _w(size, 0.055)
    d.line([_p(size, 0.30, 0.76), _p(size, 0.70, 0.22)], fill=color, width=w)
    d.polygon(
        [_p(size, 0.70, 0.22), _p(size, 0.76, 0.14), _p(size, 0.78, 0.26)],
        fill=color,
    )
    d.line([_p(size, 0.36, 0.60), _p(size, 0.58, 0.72)], fill=color, width=w)
    d.line([_p(size, 0.24, 0.80), _p(size, 0.36, 0.88)], fill=GLYPH_DIM, width=_w(size, 0.04))


def glyph_spear(d, size, color=GLYPH):
    w = _w(size, 0.05)
    d.line([_p(size, 0.32, 0.88), _p(size, 0.66, 0.26)], fill=GLYPH_DIM, width=w)
    d.polygon(
        [_p(size, 0.66, 0.26), _p(size, 0.78, 0.10), _p(size, 0.74, 0.32)],
        fill=color,
    )


def glyph_bow(d, size, color=GLYPH):
    w = _w(size, 0.05)
    d.arc(
        [_p(size, 0.28, 0.16), _p(size, 0.74, 0.84)],
        start=280,
        end=80,
        fill=color,
        width=w,
    )
    d.line([_p(size, 0.66, 0.20), _p(size, 0.66, 0.80)], fill=GLYPH_DIM, width=_w(size, 0.025))
    d.line([_p(size, 0.30, 0.50), _p(size, 0.80, 0.50)], fill=color, width=_w(size, 0.035))
    d.polygon(
        [_p(size, 0.80, 0.50), _p(size, 0.70, 0.44), _p(size, 0.70, 0.56)],
        fill=color,
    )


def glyph_crossbow(d, size, color=GLYPH):
    w = _w(size, 0.05)
    d.arc(
        [_p(size, 0.20, 0.24), _p(size, 0.72, 0.72)],
        start=300,
        end=60,
        fill=color,
        width=w,
    )
    d.line([_p(size, 0.46, 0.30), _p(size, 0.46, 0.86)], fill=GLYPH_DIM, width=_w(size, 0.07))
    d.line([_p(size, 0.34, 0.42), _p(size, 0.58, 0.42)], fill=color, width=_w(size, 0.03))


def glyph_horse(d, size, color=GLYPH):
    # Head-and-neck silhouette; the mane is a second offset polygon.
    d.polygon(
        [
            _p(size, 0.34, 0.84),
            _p(size, 0.40, 0.56),
            _p(size, 0.52, 0.34),
            _p(size, 0.66, 0.22),
            _p(size, 0.78, 0.30),
            _p(size, 0.70, 0.38),
            _p(size, 0.60, 0.52),
            _p(size, 0.56, 0.84),
        ],
        fill=color,
    )
    d.polygon(
        [_p(size, 0.66, 0.22), _p(size, 0.74, 0.12), _p(size, 0.80, 0.22)],
        fill=GLYPH_DIM,
    )


def glyph_lance(d, size, color=GLYPH):
    glyph_horse(d, size, GLYPH_DIM)
    d.line([_p(size, 0.20, 0.74), _p(size, 0.86, 0.36)], fill=color, width=_w(size, 0.045))
    d.polygon(
        [_p(size, 0.86, 0.36), _p(size, 0.78, 0.32), _p(size, 0.80, 0.44)],
        fill=color,
    )


def glyph_catapult(d, size, color=GLYPH):
    w = _w(size, 0.045)
    d.line([_p(size, 0.20, 0.80), _p(size, 0.80, 0.80)], fill=GLYPH_DIM, width=_w(size, 0.07))
    d.line([_p(size, 0.32, 0.80), _p(size, 0.48, 0.34)], fill=color, width=w)
    d.line([_p(size, 0.48, 0.34), _p(size, 0.78, 0.20)], fill=color, width=w)
    d.ellipse([_p(size, 0.74, 0.12), _p(size, 0.88, 0.26)], fill=ACCENT_MILITARY)
    d.ellipse([_p(size, 0.28, 0.72), _p(size, 0.42, 0.86)], outline=color, width=w)
    d.ellipse([_p(size, 0.58, 0.72), _p(size, 0.72, 0.86)], outline=color, width=w)


def glyph_crown(d, size, color=ACCENT_ROYAL):
    d.polygon(
        [
            _p(size, 0.22, 0.68),
            _p(size, 0.22, 0.36),
            _p(size, 0.36, 0.52),
            _p(size, 0.50, 0.30),
            _p(size, 0.64, 0.52),
            _p(size, 0.78, 0.36),
            _p(size, 0.78, 0.68),
        ],
        fill=color,
    )
    d.rectangle([_p(size, 0.22, 0.68), _p(size, 0.78, 0.78)], fill=GLYPH_DIM)


def glyph_cart(d, size, color=GLYPH):
    w = _w(size, 0.04)
    d.rectangle([_p(size, 0.24, 0.42), _p(size, 0.76, 0.64)], outline=color, width=w)
    d.line([_p(size, 0.24, 0.52), _p(size, 0.76, 0.52)], fill=GLYPH_DIM, width=_w(size, 0.025))
    d.line([_p(size, 0.24, 0.46), _p(size, 0.10, 0.34)], fill=color, width=w)
    d.ellipse([_p(size, 0.28, 0.60), _p(size, 0.44, 0.76)], outline=color, width=w)
    d.ellipse([_p(size, 0.56, 0.60), _p(size, 0.72, 0.76)], outline=color, width=w)


def glyph_keep(d, size, color=GLYPH):
    w = _w(size, 0.04)
    d.rectangle([_p(size, 0.30, 0.42), _p(size, 0.70, 0.84)], fill=GLYPH_DIM)
    for i in range(3):
        x = 0.30 + i * 0.145
        d.rectangle([_p(size, x, 0.32), _p(size, x + 0.09, 0.44)], fill=color)
    d.rectangle([_p(size, 0.44, 0.60), _p(size, 0.56, 0.84)], fill=BG_BOTTOM)
    d.line([_p(size, 0.50, 0.32), _p(size, 0.50, 0.14)], fill=color, width=w)
    d.polygon(
        [_p(size, 0.50, 0.14), _p(size, 0.74, 0.20), _p(size, 0.50, 0.26)],
        fill=ACCENT_ROYAL,
    )


def glyph_tent(d, size, color=GLYPH):
    d.polygon(
        [_p(size, 0.50, 0.20), _p(size, 0.84, 0.80), _p(size, 0.16, 0.80)],
        fill=GLYPH_DIM,
    )
    d.polygon(
        [_p(size, 0.50, 0.20), _p(size, 0.62, 0.80), _p(size, 0.38, 0.80)],
        fill=BG_BOTTOM,
    )
    d.line([_p(size, 0.16, 0.80), _p(size, 0.84, 0.80)], fill=color, width=_w(size, 0.05))


def glyph_barn(d, size, color=GLYPH):
    d.rectangle([_p(size, 0.24, 0.46), _p(size, 0.76, 0.82)], fill=GLYPH_DIM)
    d.polygon(
        [_p(size, 0.18, 0.46), _p(size, 0.50, 0.20), _p(size, 0.82, 0.46)],
        fill=color,
    )
    d.rectangle([_p(size, 0.42, 0.60), _p(size, 0.58, 0.82)], fill=BG_BOTTOM)


def glyph_anvil(d, size, color=GLYPH):
    w = _w(size, 0.05)
    d.polygon(
        [
            _p(size, 0.22, 0.44),
            _p(size, 0.78, 0.44),
            _p(size, 0.66, 0.58),
            _p(size, 0.60, 0.58),
            _p(size, 0.60, 0.70),
            _p(size, 0.72, 0.78),
            _p(size, 0.28, 0.78),
            _p(size, 0.40, 0.70),
            _p(size, 0.40, 0.58),
            _p(size, 0.34, 0.58),
        ],
        fill=color,
    )
    d.line([_p(size, 0.58, 0.42), _p(size, 0.80, 0.20)], fill=GLYPH_DIM, width=w)
    d.rectangle([_p(size, 0.74, 0.14), _p(size, 0.88, 0.24)], fill=GLYPH_DIM)


def glyph_arrow(d, size, color=GLYPH):
    w = _w(size, 0.045)
    d.line([_p(size, 0.22, 0.80), _p(size, 0.78, 0.24)], fill=GLYPH_DIM, width=w)
    d.polygon(
        [_p(size, 0.80, 0.20), _p(size, 0.72, 0.26), _p(size, 0.86, 0.32)],
        fill=color,
    )
    for i in range(3):
        off = i * 0.07
        d.line(
            [_p(size, 0.22 + off, 0.80 - off), _p(size, 0.32 + off, 0.90 - off)],
            fill=color,
            width=_w(size, 0.03),
        )


def glyph_silo(d, size, color=GLYPH):
    w = _w(size, 0.045)
    d.rectangle([_p(size, 0.32, 0.30), _p(size, 0.68, 0.82)], outline=color, width=w)
    d.polygon(
        [_p(size, 0.28, 0.30), _p(size, 0.50, 0.14), _p(size, 0.72, 0.30)],
        fill=ACCENT_ECONOMY,
    )
    for i in range(3):
        y = 0.42 + i * 0.14
        d.line([_p(size, 0.32, y), _p(size, 0.68, y)], fill=GLYPH_DIM, width=_w(size, 0.02))


def glyph_house(d, size, color=GLYPH):
    d.rectangle([_p(size, 0.28, 0.48), _p(size, 0.72, 0.82)], fill=GLYPH_DIM)
    d.polygon(
        [_p(size, 0.20, 0.48), _p(size, 0.50, 0.22), _p(size, 0.80, 0.48)],
        fill=ACCENT_ECONOMY,
    )
    d.rectangle([_p(size, 0.44, 0.62), _p(size, 0.56, 0.82)], fill=BG_BOTTOM)
    d.rectangle([_p(size, 0.60, 0.56), _p(size, 0.68, 0.64)], fill=color)


def glyph_logs(d, size, color=GLYPH):
    for i in range(3):
        y = 0.56 + i * 0.10
        d.rectangle(
            [_p(size, 0.20, y), _p(size, 0.72, y + 0.08)],
            fill=GLYPH_DIM if i % 2 else color,
            outline=BG_BOTTOM,
        )
    d.line([_p(size, 0.62, 0.54), _p(size, 0.84, 0.28)], fill=color, width=_w(size, 0.05))
    d.polygon(
        [_p(size, 0.84, 0.28), _p(size, 0.72, 0.30), _p(size, 0.82, 0.16)],
        fill=GLYPH,
    )


def glyph_market(d, size, color=GLYPH):
    w = _w(size, 0.04)
    for i in range(4):
        x = 0.20 + i * 0.16
        # Alternating awning stripes: the market stall reads at build-menu size.
        shade = ACCENT_MILITARY if i % 2 else GLYPH_DIM
        d.rectangle([_p(size, x, 0.30), _p(size, x + 0.16, 0.44)], fill=shade)
    d.rectangle([_p(size, 0.24, 0.44), _p(size, 0.76, 0.62)], fill=GLYPH_DIM)
    d.line([_p(size, 0.24, 0.62), _p(size, 0.24, 0.82)], fill=color, width=w)
    d.line([_p(size, 0.76, 0.62), _p(size, 0.76, 0.82)], fill=color, width=w)
    d.ellipse([_p(size, 0.42, 0.66), _p(size, 0.58, 0.82)], fill=ACCENT_ROYAL)


def glyph_tower(d, size, color=GLYPH):
    d.rectangle([_p(size, 0.36, 0.34), _p(size, 0.64, 0.86)], fill=GLYPH_DIM)
    for i in range(2):
        x = 0.36 + i * 0.18
        d.rectangle([_p(size, x, 0.24), _p(size, x + 0.10, 0.36)], fill=color)
    d.rectangle([_p(size, 0.46, 0.54), _p(size, 0.54, 0.66)], fill=BG_BOTTOM)


def glyph_wall(d, size, color=GLYPH):
    d.rectangle([_p(size, 0.14, 0.46), _p(size, 0.86, 0.80)], fill=GLYPH_DIM)
    for i in range(4):
        x = 0.14 + i * 0.19
        d.rectangle([_p(size, x, 0.34), _p(size, x + 0.11, 0.48)], fill=color)
    for row in range(2):
        for i in range(3):
            x = 0.20 + i * 0.22 + (0.11 if row else 0.0)
            d.rectangle([_p(size, x, 0.54 + row * 0.14), _p(size, x + 0.10, 0.64 + row * 0.14)], fill=BG_BOTTOM)


def glyph_farm(d, size, color=GLYPH):
    w = _w(size, 0.035)
    for i in range(3):
        x = 0.30 + i * 0.20
        d.line([_p(size, x, 0.80), _p(size, x, 0.34)], fill=color, width=w)
        d.line([_p(size, x, 0.44), _p(size, x - 0.07, 0.34)], fill=GLYPH_DIM, width=w)
        d.line([_p(size, x, 0.44), _p(size, x + 0.07, 0.34)], fill=GLYPH_DIM, width=w)
    d.line([_p(size, 0.18, 0.82), _p(size, 0.82, 0.82)], fill=GLYPH_DIM, width=_w(size, 0.05))


# --------------------------------------------------------------------------
# Roster: unit def name -> (glyph, accent). Order is fixed so regenerating the
# pictures is byte-stable and the tests can assert the exact roster.
# --------------------------------------------------------------------------

ROSTER = (
    ("medieval_villager", glyph_farm, ACCENT_ECONOMY),
    ("medieval_cart", glyph_cart, ACCENT_ECONOMY),
    ("medieval_infantry", glyph_sword, ACCENT_MILITARY),
    ("medieval_men_at_arms", glyph_sword, ACCENT_BUILDING),
    ("medieval_spearman", glyph_spear, ACCENT_MILITARY),
    ("medieval_archer", glyph_bow, ACCENT_ECONOMY),
    ("medieval_crossbow", glyph_crossbow, ACCENT_BUILDING),
    ("medieval_cavalry", glyph_horse, ACCENT_MILITARY),
    ("medieval_knight", glyph_lance, ACCENT_MILITARY),
    ("medieval_catapult", glyph_catapult, ACCENT_BUILDING),
    ("medieval_king", glyph_crown, ACCENT_ROYAL),
    ("medieval_town_center", glyph_keep, ACCENT_ROYAL),
    ("medieval_barracks", glyph_tent, ACCENT_MILITARY),
    ("medieval_stables", glyph_barn, ACCENT_ECONOMY),
    ("medieval_blacksmith", glyph_anvil, ACCENT_BUILDING),
    ("medieval_fletcher", glyph_arrow, ACCENT_ECONOMY),
    ("medieval_granary", glyph_silo, ACCENT_ECONOMY),
    ("medieval_house", glyph_house, ACCENT_ECONOMY),
    ("medieval_lumber_camp", glyph_logs, ACCENT_ECONOMY),
    ("medieval_market", glyph_market, ACCENT_ROYAL),
    ("medieval_tower", glyph_tower, ACCENT_BUILDING),
    ("medieval_wall", glyph_wall, ACCENT_BUILDING),
)


def render(name: str, glyph, accent, size: int) -> Image.Image:
    img = _bg(size)
    draw = ImageDraw.Draw(img)
    _frame(draw, size, accent)
    glyph(draw, size)
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=128, help="square edge in pixels")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, glyph, accent in ROSTER:
        img = render(name, glyph, accent, args.size)
        img.save(args.out / f"{name}.png", format="PNG", optimize=True)
        print(f"wrote {args.out / (name + '.png')}")

    print(f"{len(ROSTER)} buildpics generated at {args.size}x{args.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
