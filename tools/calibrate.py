#!/usr/bin/env python3
"""Turn four measured margins into a calibration offset and a real bezel.

    python3 tools/calibrate.py --top 2.42 --bottom 1.62 --left 2.28 --right 1.49

Print a card, measure the white margin on each of the four edges with calipers,
and pass them in millimetres. Two different numbers come out, and conflating them
is the mistake this script exists to prevent:

  OFFSET   how far the print landed from centre. Fixable — it is the calibration
           nudge, and it makes the four margins equal.

  BEZEL    how much margin is left once it IS centred. Not fixable. It is the
           area the printer cannot reach, and the only cure is to design inside
           it. Measuring it is the point: guessing it is how content gets clipped.

Sign convention matches the app's nudge pad: +x moves the print right, +y moves
it down.
"""

from __future__ import annotations

import argparse
import json

CARD_W, CARD_H = 85.6, 53.98      # CR-80


def solve(top: float, bottom: float, left: float, right: float,
          card_w: float = CARD_W, card_h: float = CARD_H) -> dict:
    printed_w = card_w - left - right
    printed_h = card_h - top - bottom

    # Centred margins are half of what is left over.
    centred_x = (card_w - printed_w) / 2
    centred_y = (card_h - printed_h) / 2

    # A larger LEFT margin means the print sat too far right, so the nudge is
    # negative. Same logic vertically with TOP.
    dx = -(left - centred_x)
    dy = -(top - centred_y)

    return {
        "measured": {"top": top, "bottom": bottom, "left": left, "right": right},
        "printed_area_mm": {"w": round(printed_w, 3), "h": round(printed_h, 3)},
        "offset_mm": {"x": round(left - centred_x, 3), "y": round(top - centred_y, 3)},
        "calibration_mm": {"dx": round(dx, 3), "dy": round(dy, 3)},
        "bezel_mm": {"x": round(centred_x, 3), "y": round(centred_y, 3),
                     "max": round(max(centred_x, centred_y), 3)},
        "after": {"top": round(centred_y, 3), "bottom": round(centred_y, 3),
                  "left": round(centred_x, 3), "right": round(centred_x, 3)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for edge in ("top", "bottom", "left", "right"):
        ap.add_argument(f"--{edge}", type=float, required=True, help=f"{edge} white margin, mm")
    ap.add_argument("--card-w", type=float, default=CARD_W)
    ap.add_argument("--card-h", type=float, default=CARD_H)
    ap.add_argument("--json", action="store_true", help="machine-readable only")
    a = ap.parse_args(argv)

    r = solve(a.top, a.bottom, a.left, a.right, a.card_w, a.card_h)
    if a.json:
        print(json.dumps(r, indent=2))
        return 0

    m, c, b = r["measured"], r["calibration_mm"], r["bezel_mm"]
    print(f"\n  measured      top {m['top']}  bottom {m['bottom']}  left {m['left']}  right {m['right']}  (mm)")
    print(f"  printed area  {r['printed_area_mm']['w']} x {r['printed_area_mm']['h']} mm")
    print(f"  off centre    x {r['offset_mm']['x']:+.3f}  y {r['offset_mm']['y']:+.3f} mm")
    print(f"\n  CALIBRATION   dx {c['dx']:+.3f}   dy {c['dy']:+.3f} mm"
          f"   ({'left' if c['dx'] < 0 else 'right'} {abs(c['dx']):.3f}, "
          f"{'up' if c['dy'] < 0 else 'down'} {abs(c['dy']):.3f})")
    print(f"  after that    all four margins become "
          f"{b['x']:.3f} mm horizontal, {b['y']:.3f} mm vertical")
    print(f"\n  BEZEL         {b['max']:.3f} mm — the printer cannot reach this, "
          f"calibration will not change it.")
    print(f"                Keep content inside it or it is cut off.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
