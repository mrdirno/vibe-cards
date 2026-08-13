#!/usr/bin/env python3
"""Measure an exported PDF and say whether it will print what the screen promised.

    python3 tools/verify_print_export.py CARD.pdf
    python3 tools/verify_print_export.py CARD.pdf --margin 1.885,2.02
    python3 tools/verify_print_export.py CARD.pdf --margin 1.885,2.02 --bleed 1.0

`verify_geometry.py` proves the composer places a card at exactly 85.6 × 53.98 mm.
It cannot see INSIDE the placed image, and that is where the last bug lived: the
white margin was drawn on the preview canvas and never on the exported raster, so
every measurement passed while the printed card had ink to the very edge. The
geometry was right and the pixels were wrong.

So this opens the images the PDF actually carries and measures the ink:

  * page size and every placement, in mm
  * each raster's real resolution, and whether it matches the placement
  * the white band around each raster — where it starts, how wide it is on all
    four edges, measured at several points per edge so a rounded corner or a
    single stray pixel cannot pass for a band

Run it on any PDF the app exported, including one a user sends back. The point of
measuring the artifact rather than reading the code is that the artifact is what
went through the printer.

A caution the tool prints for itself: a white band cannot be detected against
white artwork. When the artwork near an edge is already white, this reports
INCONCLUSIVE rather than passing — an unfalsifiable check that always says yes is
worse than no check.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("verify_print_export.py needs Pillow: pip install Pillow", file=sys.stderr)
    raise SystemExit(2)

PT_PER_MM = 72.0 / 25.4
CARD_W, CARD_H = 85.6, 53.98
WHITE_MIN = 244          # PVC white is 247; anything at or above this is "no ink"
TOL_MM = 0.15            # a raster edge is quantised by its own pixel grid

fails: list[str] = []
warns: list[str] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    tag = "PASS" if ok else ("WARN" if ok is None else "FAIL")
    print(f"  {tag}  {name}")
    if detail and ok is not True:
        print(f"        {detail}")
    if ok is False:
        fails.append(f"{name} — {detail}")
    elif ok is None:
        warns.append(f"{name} — {detail}")


def placements(raw: bytes) -> tuple[tuple[float, float], list[dict]]:
    mb = re.search(rb"/MediaBox\s*\[([^\]]+)\]", raw)
    v = [float(x) for x in mb.group(1).split()]
    page = ((v[2] - v[0]) / PT_PER_MM, (v[3] - v[1]) / PT_PER_MM)
    out = []
    for m in re.finditer(rb"([\d.\-]+) ([\d.\-]+) ([\d.\-]+) ([\d.\-]+) "
                         rb"([\d.\-]+) ([\d.\-]+) cm", raw):
        a, b, c, d, e, f = (float(x) for x in m.groups())
        out.append({"w_mm": a / PT_PER_MM, "h_mm": d / PT_PER_MM,
                    "x_mm": e / PT_PER_MM,
                    "y_mm": page[1] - (f + d) / PT_PER_MM})
    return page, out


def rasters(raw: bytes) -> list[Image.Image]:
    """Every JPEG the file carries. Card art is always a photo-grade stream."""
    imgs = []
    for m in re.finditer(rb"\xff\xd8\xff", raw):
        s = m.start()
        e = raw.find(b"\xff\xd9", s)
        if e < 0 or e - s < 5000:
            continue
        try:
            imgs.append(Image.open(io.BytesIO(raw[s:e + 2])).convert("RGB"))
        except Exception:
            pass
    return imgs


def white_band(im: Image.Image, side: str, mm_per_px: float) -> tuple[float, float, bool]:
    """(where the white starts, how wide it is, was the artwork underneath white).

    Sampled at five positions along the edge and reduced by MEDIAN, not by a
    single centre line. One line through a light element reads as a band; a
    median of five does not. The corners are skipped — the card is round there,
    and a rounded corner legitimately carries more white than a straight edge.
    """
    w, h = im.size
    px = im.load()
    starts, widths, all_white = [], [], []

    for frac in (0.25, 0.375, 0.5, 0.625, 0.75):
        if side in ("left", "right"):
            y = int(h * frac)
            walk = [(x, y) for x in (range(w) if side == "left" else range(w - 1, -1, -1))]
        else:
            x = int(w * frac)
            walk = [(x, y) for y in (range(h) if side == "top" else range(h - 1, -1, -1))]

        limit = min(len(walk), int(12 / mm_per_px))     # never look past 12 mm in
        start, run, seen_ink = None, 0, False
        for i in range(limit):
            p = px[walk[i]]
            is_white = min(p) >= WHITE_MIN
            if is_white:
                if start is None:
                    start = i
                run += 1
            elif start is not None:
                break                                    # band ended
            else:
                seen_ink = True
        starts.append((start or 0) * mm_per_px)
        widths.append(run * mm_per_px)
        all_white.append(not seen_ink and run >= limit - 1)

    med = lambda v: sorted(v)[len(v) // 2]
    return med(starts), med(widths), all(all_white)


def corner_white(im: Image.Image, corner: str, mm_per_px: float) -> tuple[float, bool]:
    """How far the white runs along the corner's diagonal, and was it already white.

    Corners get their own check because the edge scan structurally cannot see
    them: it samples between 25% and 75% along each edge, on purpose, since a
    rounded corner legitimately carries more white than a straight edge. That
    blind spot hid a real bug — the band was drawn as a rounded rect on the
    card's outline, so the four nubs outside the curve kept their artwork and
    printed as dark wedges at the extreme corners. Four edge scans passed.
    """
    w, h = im.size
    px = im.load()
    dx, dy = {"TL": (1, 1), "TR": (-1, 1), "BL": (1, -1), "BR": (-1, -1)}[corner]
    x0 = 0 if dx > 0 else w - 1
    y0 = 0 if dy > 0 else h - 1

    limit = min(w, h, int(12 / mm_per_px))
    run = 0
    for i in range(limit):
        if min(px[x0 + dx * i, y0 + dy * i]) < WHITE_MIN:
            break
        run += 1
    return run * mm_per_px, run >= limit - 1


def ink_reach(im: Image.Image, mm_per_px: float) -> dict:
    """How far in from each edge the first ink appears.

    For the calibration target this is the whole ballgame. Its registration marks
    sit AT the card edge on purpose — that is what makes them able to report
    alignment — and the card tells you to read the lowest tick you can still see.
    Paint a white frame over it and the low ticks vanish silently: the target
    still looks like a valid target, it just answers a different question. A
    1.885 mm frame moved the first visible ink to 4.91 mm from the top edge, so
    the reading would have been off by about five millimetres, and the only
    symptom is a wasted card and a worse calibration than you started with.
    """
    w, h = im.size
    px = im.load()
    INK = 128
    out = {}
    limit = min(w // 2, h // 2, int(15 / mm_per_px))

    # The WHOLE edge, not five sample points along it. The first version sampled
    # at 20-80% of each side and reported 4.9 mm on a target that had ink at
    # 0.0 mm — because this target's edge marks are the corner L and the tick
    # rows, which live near the ENDS of an edge, and the 5 mm inset frame is all
    # there is across the middle. The question is "does any ink reach this edge",
    # so the answer is a minimum over the edge, not a median of the middle.
    for side in ("left", "right", "top", "bottom"):
        best = None
        span = h if side in ("left", "right") else w
        for k in range(0, span, 3):
            for i in range(limit):
                pt = ((i, k) if side == "left" else
                      (w - 1 - i, k) if side == "right" else
                      (k, i) if side == "top" else (k, h - 1 - i))
                if min(px[pt]) < INK:
                    d = i * mm_per_px
                    best = d if best is None else min(best, d)
                    break
            if best == 0.0:
                break                                   # cannot do better
        out[side] = best
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--margin", default="",
                    help="expected white band as X,Y in mm (e.g. 1.885,2.02); "
                         "omit to only REPORT what is there")
    ap.add_argument("--bleed", type=float, default=0.0,
                    help="mm of artwork printed past the card edge")
    ap.add_argument("--expect-ink-within", type=float, default=None, metavar="MM",
                    help="assert ink reaches within MM of every edge. Use on the "
                         "calibration target, whose registration marks sit AT the "
                         "card edge and must never be painted over.")
    a = ap.parse_args(argv)

    if not a.pdf.exists():
        print(f"no such file: {a.pdf}", file=sys.stderr)
        return 2
    raw = a.pdf.read_bytes()

    want = None
    if a.margin:
        mx, _, my = a.margin.partition(",")
        want = (float(mx), float(my or mx))

    print(f"\n{a.pdf.name}  {len(raw)/1024:.0f} KB")

    page, place = placements(raw)
    print("\nPAGE AND PLACEMENT")
    print(f"  MediaBox {page[0]:.3f} × {page[1]:.3f} mm, {len(place)} placement(s)")
    exp_w, exp_h = CARD_W + a.bleed * 2, CARD_H + a.bleed * 2
    for i, p in enumerate(place):
        ok = abs(p["w_mm"] - exp_w) <= 0.01 and abs(p["h_mm"] - exp_h) <= 0.01
        check(f"placement {i+1} is {exp_w:.2f} × {exp_h:.2f} mm", ok,
              f"got {p['w_mm']:.3f} × {p['h_mm']:.3f} at "
              f"x={p['x_mm']:.3f} y_top={p['y_mm']:.3f}")

    imgs = rasters(raw)
    print(f"\nRASTERS  ({len(imgs)} found)")
    if not imgs:
        check("the PDF carries card artwork", False, "no JPEG stream over 5 KB")
        return 1

    for i, im in enumerate(imgs):
        w, h = im.size
        target = place[i] if i < len(place) else place[0]
        mm_per_px = target["w_mm"] / w
        dpi = 25.4 / mm_per_px
        print(f"\n  raster {i+1}: {w}×{h} px → {dpi:.0f} dpi "
              f"({target['w_mm']:.2f} × {target['h_mm']:.2f} mm)")
        check(f"raster {i+1} aspect matches its placement",
              abs((w / h) - (target["w_mm"] / target["h_mm"])) < 0.01,
              f"raster {w/h:.4f} vs placement {target['w_mm']/target['h_mm']:.4f}")

        for side in ("left", "right", "top", "bottom"):
            start, width, blank = white_band(im, side, mm_per_px)
            exp = a.bleed if want else None
            expw = (want[0] if side in ("left", "right") else want[1]) if want else None

            if want is None:
                print(f"        {side:<6} white starts {start:.2f} mm in, "
                      f"{width:.2f} mm wide")
                continue
            if blank:
                check(f"raster {i+1} {side} margin", None,
                      "artwork at this edge is white, so a white band is "
                      "indistinguishable from no band — INCONCLUSIVE, redo with "
                      "a dark background")
                continue
            ok = abs(start - exp) <= TOL_MM and abs(width - expw) <= TOL_MM
            check(f"raster {i+1} {side} margin is {expw:.3f} mm at {exp:.2f} mm in", ok,
                  f"measured {width:.3f} mm starting {start:.3f} mm from the edge "
                  f"(off by {width-expw:+.3f} / {start-exp:+.3f})")

    if a.expect_ink_within is not None:
        print("\nINK REACHES THE EDGE")
        for i, im in enumerate(imgs):
            target = place[i] if i < len(place) else place[0]
            reach = ink_reach(im, target["w_mm"] / im.size[0])
            for side, got in reach.items():
                check(f"raster {i+1} {side}: ink within {a.expect_ink_within:.2f} mm",
                      got is not None and got <= a.expect_ink_within + TOL_MM,
                      "no ink found at all" if got is None else
                      f"first ink {got:.3f} mm from the edge "
                      f"(over by {got - a.expect_ink_within:+.3f}) — something is "
                      f"painting over marks that must stay visible")

    print()
    if fails:
        print(f"FAILED — {len(fails)} check(s):")
        for f in fails:
            print(f"  - {f}")
        return 1
    if warns:
        print(f"INCONCLUSIVE — {len(warns)} check(s) could not be decided:")
        for w_ in warns:
            print(f"  - {w_}")
        return 3
    print("The exported PDF carries the ink the screen promised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
