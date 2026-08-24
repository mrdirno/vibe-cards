#!/usr/bin/env python3
"""Draw the KUNAI-360 mark into front.svg, between MARK:BEGIN/MARK:END.

The mark is an OUTPUT, not a logo — the same rule the collage card set. It is the
housing's own top view, drawn from the constants in the product's generator,
kunai_360_onex_v4.py. Those constants are the product: the README over there says a
fit complaint becomes a number, not a remodel. So the card's picture is those numbers,
at card scale, and a holder with the generator repo can check every one.

The constants are EMBEDDED here (this example must rebuild from this repo alone),
each with the generator line it came from. --verify-against PATH re-parses the plain
`NAME = <number>` lines out of the real generator source and fails on any drift, so
the embedded copy cannot silently rot while the sibling repo is present. Offsets that
live inside expressions over there (e.g. `BODY_X1 - 52.0`) are embedded as the offset
number and are NOT re-parsed — named in VERIFIED/UNVERIFIED output so the limit of
the check is printed, not implied.

Two declared simplifications, because a 30 mm mark is not a CAD export: the blunted
tip is drawn flat at TIP_FLAT with no TIP_BEVEL rounding, and the ring butts the
handle end where the real mesh blends them. Everything else is the constants.

Stdlib only, like everything in this repo.
"""

import argparse
import re
import sys
from pathlib import Path

# ---- constants from kunai-360/generator/kunai_360_onex_v4.py (line numbers cited) --
# Plain-literal constants: --verify-against re-parses these by name.
LITERALS = {
    "CAM_L": 114.63,      # L86  body length
    "CAM_CL": 0.3,        # L89  width clearance per side
    "CAM_W": 48.0,        # L87  body width
    "WALL": 3.0,          # L100 side wall thickness
    "RING_OD": 28.0,      # L137 pommel ring outer diameter
    "RING_ID": 19.05,     # L138 3/4in finger hole
    "RLENS": 13.0,        # L144 lens opening radius
    "DISP_R": 10.5,       # L168 display window radius
    "MIDBTN_R": 7.0,      # L170 main button radius
    "SMBTN_R": 4.5,       # L172 small button radius
    "MIC_R": 1.35,        # L176 mic hole radius
    "BLADE_MAXW": 78.0,   # L155 blade max width
    "BLADE_LEN": 32.0,    # L156 blade point length above camera top
    "TIP_FLAT": 7.0,      # L158 blunted tip width (safety directive)
}
# Offsets embedded from inside expressions (NOT re-parsed by --verify-against):
OFFSETS = {
    "RING_GAP": 6.0,      # L141 BODY_X0 = RING_OD + 6.0
    "SHOULDER_OFF": 52.0, # L153 SHOULDER_X = BODY_X1 - 52.0
    "LENS_OFF": 23.25,    # L145 lens center, down from camera top
    "DISP_OFF": 52.75,    # L167 display center
    "MIDBTN_OFF": 75.75,  # L169 main button center
    "SMBTN_OFF": 93.45,   # L171 small button center
    "LED_OFF": 104.85,    # L173 LED slit center
    "MIC_OFF": 6.35,      # L175 mic hole center
    "LED_W": 7.0,         # L174 LED slot width (Y)
    "LED_L": 2.0,         # L174 LED slot height (X)
}


def geometry():
    c = {**LITERALS, **OFFSETS}
    body_x0 = c["RING_OD"] + c["RING_GAP"]
    body_x1 = body_x0 + c["CAM_L"] + 2 * c["CAM_CL"]
    length = body_x1 + c["BLADE_LEN"]
    grip_half = (c["CAM_W"] + 2 * c["CAM_CL"] + 2 * c["WALL"]) / 2.0
    shoulder_x = body_x1 - c["SHOULDER_OFF"]
    holes = [  # (center X from ring end, radius) on the +Z face centerline
        (body_x1 - c["MIC_OFF"], c["MIC_R"]),
        (body_x1 - c["LENS_OFF"], c["RLENS"]),
        (body_x1 - c["DISP_OFF"], c["DISP_R"]),
        (body_x1 - c["MIDBTN_OFF"], c["MIDBTN_R"]),
        (body_x1 - c["SMBTN_OFF"], c["SMBTN_R"]),
    ]
    led = (body_x1 - c["LED_OFF"], c["LED_L"], c["LED_W"])  # (center X, X-extent, Y-extent)
    return c, body_x1, length, grip_half, shoulder_x, holes, led


def build_path(box_x, box_y, box_size):
    """One evenodd path, product X mapped up the card (blade up), centered in the box."""
    c, body_x1, length, grip_half, shoulder_x, holes, led = geometry()
    s = box_size / length
    cx = box_x + box_size / 2.0

    def pt(px, py):  # product (along, across) -> card mm
        return (round(cx + py * s, 3), round(box_y + box_size - px * s, 3))

    d = []
    # silhouette: handle end -> shoulder -> blade peak -> blunt tip, mirrored
    ring_end = c["RING_OD"]
    right = [
        pt(ring_end, grip_half),
        pt(shoulder_x, grip_half),
        pt(body_x1, c["BLADE_MAXW"] / 2.0),
        pt(length, c["TIP_FLAT"] / 2.0),
    ]
    left = [pt(x, -y) for (x, y) in [
        (length, c["TIP_FLAT"] / 2.0),
        (body_x1, c["BLADE_MAXW"] / 2.0),
        (shoulder_x, grip_half),
        (ring_end, grip_half),
    ]]
    d.append("M" + " L".join(f"{x} {y}" for x, y in right + left) + " Z")

    def circle(px, r):
        (x, y) = pt(px, 0)
        rr = round(r * s, 3)
        # two arcs make a subpath circle; evenodd punches it out of the silhouette
        d.append(
            f"M{round(x - rr, 3)} {y} "
            f"A{rr} {rr} 0 1 0 {round(x + rr, 3)} {y} "
            f"A{rr} {rr} 0 1 0 {round(x - rr, 3)} {y} Z"
        )

    # pommel ring: annulus below the handle (outer circle + finger hole)
    ring_c = c["RING_OD"] / 2.0
    (rx, ry) = pt(ring_c, 0)
    for r in (c["RING_OD"] / 2.0, c["RING_ID"] / 2.0):
        rr = round(r * s, 3)
        d.append(
            f"M{round(rx - rr, 3)} {ry} "
            f"A{rr} {rr} 0 1 0 {round(rx + rr, 3)} {ry} "
            f"A{rr} {rr} 0 1 0 {round(rx - rr, 3)} {ry} Z"
        )

    for (px, r) in holes:
        circle(px, r)

    (lx, l_along, l_across) = led
    (x0, y0) = pt(lx + l_along / 2.0, -l_across / 2.0)
    (x1, y1) = pt(lx - l_along / 2.0, l_across / 2.0)
    d.append(f"M{x0} {y0} L{x1} {y0} L{x1} {y1} L{x0} {y1} Z")

    return " ".join(d)


def verify_against(path):
    src = Path(path).read_text()
    bad, seen = [], []
    for name, want in LITERALS.items():
        m = re.search(rf"^{name}\s*=\s*([0-9.]+)", src, re.M)
        if not m:
            bad.append(f"{name}: not found as a plain literal")
        elif abs(float(m.group(1)) - want) > 1e-9:
            bad.append(f"{name}: generator says {m.group(1)}, embedded {want}")
        else:
            seen.append(name)
    print(f"VERIFIED {len(seen)}/{len(LITERALS)} literals against {path}")
    print(f"UNVERIFIED (inside expressions, embedded only): {', '.join(sorted(OFFSETS))}")
    if bad:
        print("DRIFT:")
        for b in bad:
            print("  " + b)
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=51.6)
    ap.add_argument("--y", type=float, default=11.99)
    ap.add_argument("--size", type=float, default=30.0)
    ap.add_argument("--fill", default="#c9d4da")
    ap.add_argument("--into", type=Path, help="SVG carrying MARK:BEGIN/MARK:END")
    ap.add_argument("--verify-against", type=Path,
                    help="kunai_360_onex_v4.py — fail on drift from the embedded literals")
    a = ap.parse_args()

    if a.verify_against:
        if not verify_against(a.verify_against):
            sys.exit(1)

    d = build_path(a.x, a.y, a.size)
    block = (f'  <path d="{d}" fill="{a.fill}" fill-rule="evenodd"/>')

    if not a.into:
        print(block)
        return
    svg = a.into.read_text()
    new, n = re.subn(
        r"(<!-- MARK:BEGIN -->).*?(<!-- MARK:END -->)",
        lambda _: "<!-- MARK:BEGIN -->\n" + block + "\n  <!-- MARK:END -->",
        svg, flags=re.S,
    )
    if n != 1:
        print("FAIL: MARK:BEGIN/MARK:END markers not found — nothing spliced")
        sys.exit(1)
    a.into.write_text(new)
    print(f"spliced mark into {a.into}")


if __name__ == "__main__":
    main()
