#!/usr/bin/env python3
"""Turn a make_qr.swift PNG into SVG geometry, in place, inside a card design.

    python3 tools/qr_to_svg.py --png <qr.png> --x 55.4 --y 14.99 --size 24 \
                               [--into <design.svg>] [--quiet-fill "#FFFFFF"]

Prints one JSON object on stdout. Exit 0 on success, 1 on refusal.

WHY THIS EXISTS, in three failures that all cost a render:

  1. `<image href="../assets/qr.png">` SILENTLY DROPS THE QR. librsvg refuses to
     load a referenced file that sits above the SVG's own directory, and it does
     not warn — the white patch renders, the code does not, and the card looks
     finished. The existing founder-card SVGs carry exactly that reference, so
     they render correctly only under a rasteriser that allows it. Geometry has
     no such policy: there is no second file to fail to load.

  2. A RASTER QR IS RESAMPLED BY WHATEVER DRAWS IT. make_qr.swift goes to real
     trouble to land every module on a whole pixel with interpolation disabled,
     and then an <image> placed at 24 mm inside a 600-dpi render hands that grid
     to the rasteriser's own scaler at a non-integer ratio. Grey module edges are
     the single most common reason a printed code will not scan, which is the
     failure make_qr.swift's own header warns about — reintroduced one layer up.
     Rects cannot go grey.

  3. A CARD IS PRINTED ONCE. Vector modules stay exact through the PDF composer
     and out to any DPI the printer wants, and they separate cleanly if the code
     is ever run as a spot colour.

The PNG stays in assets/ and stays the source of truth: this reads it rather than
re-encoding the URL, so the ink is provably the same code that make_qr.swift
generated and verified by decoding. Re-encoding here would create a second
generator, and two generators of the same URL is exactly how a card ends up
carrying a code nobody checked.

IDEMPOTENT BY MARKER. With --into, the block between `<!-- QR:BEGIN -->` and
`<!-- QR:END -->` is replaced. Regenerating after a URL change is one command,
and it cannot leave two codes stacked on one patch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BEGIN = "<!-- QR:BEGIN -->"
END = "<!-- QR:END -->"


def die(msg: str) -> "None":
    print(json.dumps({"ok": False, "error": msg}))
    raise SystemExit(1)


def read_grid(png: Path) -> tuple[list[list[bool]], int, int]:
    """Recover the module grid from the rendered PNG.

    The module size is DERIVED, never assumed: make_qr.swift picks its own
    integer scale to land near the requested pixel width, so hardcoding one
    would silently mis-read any code generated at a different --px. The
    top-left finder pattern is 7 modules of solid dark by specification, and it
    is the first dark run on the first dark row — so that run divided by 7 is
    the scale, measured off the very artifact being converted.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment, not logic
        die(f"needs Pillow (build-time only): {exc}")
    im = Image.open(png).convert("RGBA")
    w, h = im.size
    px = im.load()

    def dark(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        # Alpha counts: --transparent writes the light modules as transparent,
        # so "not dark" cannot be read from RGB alone.
        return a > 127 and (r + g + b) / 3 < 128

    xs = [x for x in range(w) for y in (h // 2,) if dark(x, y)]
    rows = [y for y in range(h) if any(dark(x, y) for x in range(0, w, max(1, w // 64)))]
    cols = [x for x in range(w) if any(dark(x, y) for y in range(0, h, max(1, h // 64)))]
    if not rows or not cols:
        die("no dark modules found — is this a QR PNG from tools/make_qr.swift?")
    x0, x1, y0, y1 = min(cols), max(cols), min(rows), max(rows)

    run = 0
    while x0 + run <= x1 and dark(x0 + run, y0):
        run += 1
    if run < 7 or run % 7:
        die(f"top-left finder run is {run}px, which is not 7 whole modules — "
            "this does not look like an unscaled make_qr.swift grid")
    scale = run // 7
    side = (x1 - x0 + 1)
    if side % scale or (y1 - y0 + 1) != side:
        die(f"dark area is {side}x{y1 - y0 + 1}px at {scale}px/module — not a square whole grid")
    n = side // scale
    grid = [[dark(x0 + c * scale + scale // 2, y0 + r * scale + scale // 2)
             for c in range(n)] for r in range(n)]
    return grid, n, scale


def to_path(grid: list[list[bool]], n: int) -> str:
    """One <path> of horizontal runs, in a 0..n module coordinate system.

    Runs rather than one rect per module: a version-4 code is 33x33, and the
    difference between ~1100 rects and ~250 subpaths is the difference between a
    design file a person can open and one they cannot.
    """
    out = []
    for r in range(n):
        c = 0
        while c < n:
            if grid[r][c]:
                start = c
                while c < n and grid[r][c]:
                    c += 1
                out.append(f"M{start} {r}h{c - start}v1h-{c - start}z")
            else:
                c += 1
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", required=True, type=Path)
    # THE GEOMETRY IS THE CODE ALONE. read_grid() bounds the DARK modules, so the
    # quiet zone make_qr.swift baked into the PNG is not in this grid and not in
    # these millimetres. That is deliberate: the quiet zone on a card is the white
    # patch under the code, which is drawn by the design and sized in the design's
    # own coordinates. Reporting quiet_needed_mm below is what keeps the two
    # honest — a patch too small for its code is the failure this trades for.
    ap.add_argument("--x", required=True, type=float, help="mm, left edge of the dark grid (quiet zone NOT included)")
    ap.add_argument("--y", required=True, type=float, help="mm, top edge, same convention")
    ap.add_argument("--size", required=True, type=float, help="mm, width of the dark grid (quiet zone NOT included)")
    ap.add_argument("--dark", default="#000000")
    ap.add_argument("--into", type=Path, help="design SVG carrying QR:BEGIN/QR:END markers")
    a = ap.parse_args()

    if not a.png.is_file():
        die(f"no such PNG: {a.png}")
    grid, n, scale = read_grid(a.png)
    module_mm = a.size / n
    # 0.4 mm is make_qr.swift's own floor (it reports min_print_mm from it), and
    # it is the number that decides whether a phone reads this across a room.
    if module_mm < 0.4:
        die(f"{a.size} mm over {n} modules is {module_mm:.3f} mm per module, under the 0.4 mm print floor")

    unit = a.size / n
    body = (f'{BEGIN}\n'
            f'  <g transform="translate({a.x} {a.y}) scale({unit:.6f})" shape-rendering="crispEdges">\n'
            f'    <path d="{to_path(grid, n)}" fill="{a.dark}"/>\n'
            f'  </g>\n'
            f'  {END}')

    written = None
    if a.into:
        if not a.into.is_file():
            die(f"no such SVG: {a.into}")
        text = a.into.read_text(encoding="utf-8")
        i, j = text.find(BEGIN), text.find(END)
        if i < 0 or j < 0 or j < i:
            die(f"{a.into} has no {BEGIN} ... {END} block to replace")
        a.into.write_text(text[:i] + body + text[j + len(END):], encoding="utf-8")
        written = str(a.into)
    else:
        print(body, file=sys.stderr)

    print(json.dumps({"ok": True, "png": str(a.png), "modules": n, "source_scale_px": scale,
                      "size_mm": a.size, "module_mm": round(module_mm, 4),
                      "min_size_mm": round(0.4 * n, 2),
                      # The design owes the code this much light on every side.
                      "quiet_needed_mm": round(4 * module_mm, 3),
                      "into": written}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
