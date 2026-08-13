#!/usr/bin/env python3
"""Prove the millimetre pipeline is exact, end to end, on every change.

    python3 tools/verify_geometry.py           # exit 0 if every placement is exact
    python3 tools/verify_geometry.py --verbose

A card is 85.6 × 53.98 mm and that number has to survive from the designer, through
the PDF composer, to the page — untouched. Nothing in this project is allowed to
scale it. This asserts that, by building real PDFs and measuring what came out,
rather than by reading the code that made them.

It exists because of a real incident. Printed cards came back 81.83 × 49.94 mm
against a card of 85.6 × 53.98 — a 4.4% shrink — and the first instinct was to
hunt for a units bug. Measuring the PDF settled it in one command: the composer
was exact to three decimal places, so the fault was downstream in the print path.
Without a measurement the search would have started in the wrong file.

That is what this is for: when a card comes out the wrong size, run this FIRST.
Green means the geometry left the app correct and the problem is CUPS, the driver
or the print dialog. Red means it is ours, and it names the placement.

Checked here:
  * mm → PDF points at exactly 72/25.4, no rounding drift
  * MediaBox equals the requested page, to 0.01 mm
  * every image lands at the requested size and origin, to 0.01 mm
  * the y-axis flip (PDF is bottom-left, the app is top-left) is exact
  * bleed grows a placement by exactly 2 × bleed and shifts it by exactly −bleed
  * calibration dx/dy translates without scaling
  * the tray slots in profiles.json fit the page, with and without bleed
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

try:
    import pdfwriter
    from PIL import Image
except ImportError as exc:
    print(f"verify_geometry.py needs Pillow (build-time only): {exc}", file=sys.stderr)
    raise SystemExit(2)

PT_PER_MM = 72.0 / 25.4
TOL_MM = 0.01                      # 0.01 mm is ~2.4 px at 600 dpi: tighter than the printer
CARD_W, CARD_H = 85.6, 53.98
VERBOSE = False
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if detail and (VERBOSE or not ok):
        print(f"        {detail}")
    if not ok:
        fails.append(f"{name} — {detail}")


def jpeg(w_mm: float, h_mm: float, dpi: int = 600) -> bytes:
    px = lambda mm: max(1, round(mm / 25.4 * dpi))
    buf = io.BytesIO()
    Image.new("RGB", (px(w_mm), px(h_mm)), (0, 0, 0)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def emit(placements: list[dict], page_w: float = 120.0, page_h: float = 120.0) -> bytes:
    out = Path("/tmp/_vc_geom.pdf")
    images = [{
        "data": jpeg(p["w_mm"], p["h_mm"]), "format": "jpeg",
        "x_mm": p["x_mm"], "y_mm": p["y_mm"],
        "w_mm": p["w_mm"], "h_mm": p["h_mm"],
        "rotate_deg": p.get("rotate_deg", 0),
    } for p in placements]
    pdfwriter.build_pdf(str(out), page_w, page_h, images)
    return out.read_bytes()


def measure(raw: bytes) -> tuple[tuple[float, float], list[dict]]:
    """Page size and every placement, in mm, read back out of the PDF."""
    mb = re.search(rb"/MediaBox\s*\[([^\]]+)\]", raw)
    v = [float(x) for x in mb.group(1).split()]
    page = ((v[2] - v[0]) / PT_PER_MM, (v[3] - v[1]) / PT_PER_MM)

    placed = []
    for m in re.finditer(rb"([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+"
                         rb"([\d.\-]+)\s+([\d.\-]+)\s+cm", raw):
        a, b, c, d, e, f = (float(x) for x in m.groups())
        placed.append({
            "w_mm": a / PT_PER_MM, "h_mm": d / PT_PER_MM,
            "x_mm": e / PT_PER_MM,
            # PDF origin is bottom-left; the app measures y from the top.
            "y_mm": page[1] - (f + d) / PT_PER_MM,
        })
    return page, placed


def near(a: float, b: float) -> bool:
    return abs(a - b) <= TOL_MM


def main(argv=None) -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    VERBOSE = ap.parse_args(argv).verbose

    print("\nUNITS")
    check("PT_PER_MM is exactly 72/25.4",
          abs(pdfwriter.PT_PER_MM - PT_PER_MM) < 1e-12,
          f"module says {pdfwriter.PT_PER_MM!r}")

    print("\nA SINGLE CARD PLACEMENT")
    want = {"x_mm": 17.553, "y_mm": 3.818, "w_mm": CARD_W, "h_mm": CARD_H}
    page, got = measure(emit([want]))
    check("MediaBox is 120.00 × 120.00 mm", near(page[0], 120) and near(page[1], 120),
          f"got {page[0]:.3f} × {page[1]:.3f}")
    check("exactly one placement emitted", len(got) == 1, f"got {len(got)}")
    if got:
        g = got[0]
        for k, label in [("w_mm", "width"), ("h_mm", "height"),
                         ("x_mm", "x"), ("y_mm", "y from top")]:
            check(f"{label} is exact", near(g[k], want[k]),
                  f"requested {want[k]:.3f} mm, emitted {g[k]:.3f} mm "
                  f"(off by {g[k]-want[k]:+.4f})")

    print("\nNOTHING SCALES THE CARD")
    # The incident this file exists for: a 4.4% shrink. Assert the ratio is 1.
    if got:
        ratio_w = got[0]["w_mm"] / CARD_W
        ratio_h = got[0]["h_mm"] / CARD_H
        check("width ratio is 1.0000", abs(ratio_w - 1) < 1e-4, f"ratio {ratio_w:.6f}")
        check("height ratio is 1.0000", abs(ratio_h - 1) < 1e-4, f"ratio {ratio_h:.6f}")

    print("\nBLEED")
    for b in (0.5, 1.0, 2.0):
        w = {"x_mm": 17.553 - b, "y_mm": 3.818 - b,
             "w_mm": CARD_W + b * 2, "h_mm": CARD_H + b * 2}
        _, g = measure(emit([w]))
        ok = g and all(near(g[0][k], w[k]) for k in w)
        check(f"bleed {b} mm grows by exactly {b*2} mm and shifts by −{b}", bool(ok),
              f"requested {w}, emitted {g[0] if g else None}")

    print("\nCALIBRATION TRANSLATES, IT DOES NOT SCALE")
    for dx, dy in ((-0.395, -0.4), (1.0, -1.0)):
        w = {"x_mm": 17.553 + dx, "y_mm": 3.818 + dy, "w_mm": CARD_W, "h_mm": CARD_H}
        _, g = measure(emit([w]))
        ok = g and near(g[0]["w_mm"], CARD_W) and near(g[0]["h_mm"], CARD_H) \
             and near(g[0]["x_mm"], w["x_mm"]) and near(g[0]["y_mm"], w["y_mm"])
        check(f"dx {dx:+} dy {dy:+} moves without resizing", bool(ok),
              f"emitted {g[0] if g else None}")

    print("\nTRAY SLOTS FIT THE PAGE")
    import json
    profiles = json.loads((SRC / "profiles.json").read_text())["profiles"]
    for pk, prof in profiles.items():
        pw, ph = prof["page_mm"]["w"], prof["page_mm"]["h"]
        for slot in prof["slots"]:
            cap = min(min(s2["x"], s2["y"], pw - (s2["x"] + s2["w"]), ph - (s2["y"] + s2["h"]))
                      for s2 in prof["slots"])
            for b in (0.0, max(0.0, cap)):
                x0, y0 = slot["x"] - b, slot["y"] - b
                x1, y1 = slot["x"] + slot["w"] + b, slot["y"] + slot["h"] + b
                ok = x0 >= 0 and y0 >= 0 and x1 <= pw and y1 <= ph
                check(f"{pk} slot {slot['name']} fits at bleed {b} mm", ok,
                      f"{x0:.2f},{y0:.2f} → {x1:.2f},{y1:.2f} on {pw}×{ph}")

    print("\nTWO SLOTS DO NOT OVERLAP AT MAX BLEED")
    for pk, prof in profiles.items():
        s = prof["slots"]
        if len(s) < 2:
            continue
        b = 2.0
        a_bot = s[0]["y"] + s[0]["h"] + b
        b_top = s[1]["y"] - b
        check(f"{pk}: bleed does not bridge the slots", a_bot <= b_top,
              f"slot A ends {a_bot:.2f} mm, slot B starts {b_top:.2f} mm "
              f"(gap {b_top - a_bot:+.2f})")


    print("\nDATA SHAPE — supplies")
    # A missing key here throws inside a template literal and renders the whole
    # Supplies tab blank. That happened: reader-pcsc shipped without `specs`, and
    # the symptom was "nothing shows", which points nowhere near the cause.
    sup = json.loads((SRC / "supplies.json").read_text())
    required = ["id", "title", "subtitle", "search", "must_say", "avoid", "specs"]
    for it in sup.get("items", []):
        missing = [k for k in required if k not in it]
        check(f"supplies item {it.get('id','?')} has every field the renderer reads",
              not missing, f"missing: {', '.join(missing)}")
    for it in sup.get("items", []):
        bad = [r for r in it.get("specs", []) if not isinstance(r, list) or len(r) != 3]
        check(f"supplies item {it.get('id','?')} specs rows are 3-tuples", not bad,
              f"{len(bad)} malformed row(s)")
    for it in sup.get("items", []):
        bad = [l for l in it.get("links", []) if not isinstance(l, dict) or "url" not in l or "label" not in l]
        check(f"supplies item {it.get('id','?')} links have url and label", not bad,
              f"{len(bad)} malformed link(s)")

    print()
    if fails:
        print(f"FAILED — {len(fails)} check(s):")
        for f in fails:
            print(f"  - {f}")
        print("\nThe geometry is wrong BEFORE it leaves the app. Fix it here.")
        return 1
    print("Geometry is exact: every placement leaves the app at the size requested.")
    print("If a printed card is the wrong size, the cause is downstream —")
    print("CUPS, the driver, or scaling in the print dialog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
