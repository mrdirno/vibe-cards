#!/usr/bin/env python3
"""Turn flat card artwork into a picture of the printed card.

    python3 tools/card_mockup.py ART.png OUT.png [--width 1100]
                                 [--bezel 1.0] [--corner 3.18] [--art-corner 1.6]

Flat artwork is a rectangle of ink. A printed CR-80 card is not: it has rounded
corners, and on inkjet PVC the printable area stops short of the edge, leaving a
white margin of card stock. Artwork shown as a plain rectangle reads as a
screenshot; the same artwork with its bezel and corners reads as an object.

Defaults are the real numbers. CR-80 corner radius is 3.18 mm. The 1.0 mm bezel
is the unprintable margin on the inkjet PVC stock this project targets — measure
your own stock and pass --bezel if it differs, because it is the one number that
varies by supplier.

Output is PNG with alpha, so the corners are transparent rather than white. A
white-cornered PNG on a dark page is the sliver of white that gives a composite
away.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("card_mockup.py needs Pillow (build-time only): pip install Pillow", file=sys.stderr)
    raise SystemExit(2)

CARD_W_MM, CARD_H_MM = 85.6, 53.98
DPI = 600
STOCK = (247, 247, 245, 255)      # PVC white, not paper white


def mm(v: float) -> int:
    return round(v / 25.4 * DPI)


def build(art_path: Path, width: int, bezel: float, corner: float, art_corner: float) -> Image.Image:
    src = Image.open(art_path).convert("RGB")
    cw, ch = mm(CARD_W_MM), mm(CARD_H_MM)
    b = mm(bezel)

    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    body_mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(body_mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=mm(corner), fill=255)
    card.paste(Image.new("RGBA", (cw, ch), STOCK), (0, 0), body_mask)

    aw, ah = cw - 2 * b, ch - 2 * b
    art = src.resize((aw, ah), Image.LANCZOS).convert("RGBA")
    art_mask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(art_mask).rounded_rectangle([0, 0, aw - 1, ah - 1], radius=mm(art_corner), fill=255)
    card.paste(art, (b, b), art_mask)

    return card.resize((width, round(ch * width / cw)), Image.LANCZOS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("art", type=Path, help="flat artwork, any size, CR-80 aspect")
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--bezel", type=float, default=1.0, help="unprintable margin, mm")
    ap.add_argument("--corner", type=float, default=3.18, help="card corner radius, mm")
    ap.add_argument("--art-corner", type=float, default=1.6, help="printed-area corner radius, mm")
    a = ap.parse_args(argv)

    if not a.art.exists():
        print(f"no such artwork: {a.art}", file=sys.stderr)
        return 1

    img = build(a.art, a.width, a.bezel, a.corner, a.art_corner)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out, "PNG", optimize=True)
    print(f"{a.out} {img.size} {a.out.stat().st_size / 1024:.0f} KB "
          f"(bezel {a.bezel} mm, corner {a.corner} mm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
