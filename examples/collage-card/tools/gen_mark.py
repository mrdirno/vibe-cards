#!/usr/bin/env python3
"""Draw COLLAGE-001's mark: a recursive subdivision, seeded, spliced into front.svg.

WHY A GENERATOR AND NOT A LOGO. Collage Studio's whole mechanic is that a
composition is a partition of a canvas that re-rolls from a seed. A drawn logo
would be a second identity invented for a product that already has one. So the
mark IS an output of the thing the card advertises, and the seed is printed on
the card beside it — anyone holding it can reproduce these exact cells.

WHY mulberry32. The deployed bundle's seeded-reroll PRNG is mulberry32, so the
same seed reaches the same cells here as it would there. It is ported below
rather than imported because this repo is Python-stdlib-only, and it is
attributed because the shipped bundle does not attribute it — that omission is
recorded in this network's own registry entry for COLLAGE-001, and reproducing
it silently while citing it publicly would be the cheapest kind of hypocrisy.
  mulberry32 is by Tommy Ettinger, public domain (CC0), from the same
  bit-mixing family as splitmix32. https://gist.github.com/tommyettinger

NOT DECORATIVE — LOAD-BEARING FOR PRINT. Cells are axis-aligned rects with no
stroke and no gaps, so the rasteriser cannot leave hairline seams between them
(a 0.1 mm white seam at 600 dpi is 2.4 px and reads as a scratch on PVC). Depth
is capped so no cell falls under MIN_CELL_MM; a cell thinner than the inkjet's
dot pitch prints as a smear, not a line.
"""
import argparse
import re
from pathlib import Path

# Read out of the product's own shipped stylesheet (assets/index-59fbad44.css)
# and its index.html, never chosen here — the same rule the AV card followed
# against av/trade.js. The dark surface tokens AND the light grey scale in the
# same file, plus the violet the page carries inline.
VOID = "#030405"

# TONE IS DRAWN, NOT DERIVED FROM DEPTH, and the first version got this wrong in
# a way only the rendered artifact showed. Mapping tone to recursion depth put
# every cell in the two darkest surfaces, on a #030405 ground: on screen it read
# as a subtle texture, and on an inkjet over PVC that is a muddy near-black block
# with a few violet chips floating in it. The product crops PHOTOGRAPHS into
# these cells, so the mark has to carry a photograph's tonal range or it is not
# showing what the product does. The ramp below spans the stylesheet's own
# surfaces AND its own grey scale, dark to light, and each cell draws from it —
# which is also why the ramp is walked by the seeded stream rather than by depth.
RAMP = ["#16191b", "#1f2427", "#2b3134", "#545B5B", "#838B8B", "#A9B0B0"]
ACCENT = "#7C3AED"

MIN_CELL_MM = 1.6   # below this an inkjet cell on PVC stops being a shape


def mulberry32(seed: int):
    """Tommy Ettinger's mulberry32, CC0 — the PRNG the deployed bundle ships.

    Ported with explicit 32-bit masking because Python ints do not wrap. Every
    `& 0xFFFFFFFF` here corresponds to JavaScript's implicit `|0` / `>>> 0`,
    and dropping one silently changes the sequence rather than raising.
    """
    a = seed & 0xFFFFFFFF

    def rnd() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = (t ^ (t >> 15)) & 0xFFFFFFFF
        t = (t * (1 | a)) & 0xFFFFFFFF
        u = (t + ((t ^ (t >> 7)) * (61 | t))) & 0xFFFFFFFF
        t = (u ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rnd


def subdivide(x, y, w, h, depth, rnd, out, max_depth):
    """Split along the longer axis, at a ratio that is never near the middle.

    A near-even split reads as a grid, which is the one composition this
    product is not. The 0.32..0.68 clamp is what keeps the cells looking
    chosen rather than ruled.
    """
    too_small = min(w, h) < MIN_CELL_MM * 2
    if depth >= max_depth or too_small or (depth >= 2 and rnd() < 0.16):
        out.append((x, y, w, h, depth))
        return
    r = 0.32 + rnd() * 0.36
    if w >= h:
        cut = w * r
        if min(cut, w - cut) < MIN_CELL_MM:
            out.append((x, y, w, h, depth))
            return
        subdivide(x, y, cut, h, depth + 1, rnd, out, max_depth)
        subdivide(x + cut, y, w - cut, h, depth + 1, rnd, out, max_depth)
    else:
        cut = h * r
        if min(cut, h - cut) < MIN_CELL_MM:
            out.append((x, y, w, h, depth))
            return
        subdivide(x, y, w, cut, depth + 1, rnd, out, max_depth)
        subdivide(x, y + cut, w, h - cut, depth + 1, rnd, out, max_depth)


def render(x, y, w, h, seed, max_depth=6):
    rnd = mulberry32(seed)
    cells = []
    subdivide(x, y, w, h, 0, rnd, cells, max_depth)
    # Accent on one cell in eight, and tone drawn from the ramp for the rest.
    # Both draws come from the SAME seeded stream that cut the cells, so the
    # printed seed reproduces the colours as well as the geometry — a seed that
    # only reproduced half the mark would be the more embarrassing kind of claim.
    parts = []
    for cx, cy, cw, ch, d in cells:
        fill = ACCENT if rnd() < 0.125 else RAMP[min(int(rnd() * len(RAMP)),
                                                     len(RAMP) - 1)]
        parts.append(
            f'    <rect x="{cx:.3f}" y="{cy:.3f}" width="{cw:.3f}" '
            f'height="{ch:.3f}" fill="{fill}"/>'
        )
    return cells, "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, required=True, help="mm, left edge")
    ap.add_argument("--y", type=float, required=True, help="mm, top edge")
    ap.add_argument("--w", type=float, required=True, help="mm")
    ap.add_argument("--h", type=float, required=True, help="mm")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--into", type=Path, help="SVG carrying MARK:BEGIN/MARK:END")
    a = ap.parse_args()

    cells, block = render(a.x, a.y, a.w, a.h, a.seed, a.depth)
    smallest = min(min(c[2], c[3]) for c in cells)
    print(f"cells={len(cells)} smallest_edge_mm={smallest:.3f} "
          f"min_allowed={MIN_CELL_MM} seed={a.seed}")
    if smallest < MIN_CELL_MM:
        print("FAIL: a cell is under the print floor")
        return 1

    if a.into:
        svg = a.into.read_text()
        new = re.sub(
            r"(<!-- MARK:BEGIN -->).*?(<!-- MARK:END -->)",
            lambda _: "<!-- MARK:BEGIN -->\n" + block + "\n  <!-- MARK:END -->",
            svg, flags=re.S,
        )
        if new == svg:
            print("FAIL: MARK:BEGIN/MARK:END markers not found — nothing spliced")
            return 1
        a.into.write_text(new)
        print(f"spliced {len(cells)} cells into {a.into}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
