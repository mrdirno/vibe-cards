#!/usr/bin/env python3
"""
make_icon.py — procedural macOS app icon for Card Studio.

Draws an RFID / PVC ID card (rounded corners, brass EMV-style contact chip,
contactless arcs, faint RFID antenna trace) on the macOS-convention rounded
square ground, renders it supersampled, downsamples with LANCZOS, and emits
assets/AppIcon.icns via /usr/bin/iconutil.

Everything is drawn procedurally: no external image assets, no network, no
fonts required for the icon itself. Pillow is a BUILD-TIME dependency only —
the shipped app consumes the committed .icns and never imports this module.

Two masters are rendered because one drawing does not serve both ends of the
size range: the "full" master carries the antenna trace, embossed data bars and
three arcs; the "low" master (used for 64px and below) drops those, enlarges the
chip and thickens the arcs so the silhouette survives at 16x16.

Usage:
    python3 make_icon.py                      # AppIcon.icns + 512px preview
    python3 make_icon.py --contact sheet.png  # small-size legibility proof sheet
    python3 make_icon.py --png 32=/tmp/i32.png
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - build-time guard
    Image = None

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

# ---------------------------------------------------------------------------
# Palette + geometry. Tune the icon from here; the drawing code below is
# parameterised off these constants and off the real CR-80 aspect ratio.
# ---------------------------------------------------------------------------

CR80_ASPECT = 85.60 / 53.98  # the card Card Studio actually prints

# Ground: deep azure -> midnight navy, lit from the top-left.
GROUND_STOPS = [(0.00, "#3E6BF2"), (0.42, "#2039A6"), (1.00, "#0A1030")]
GROUND_ANGLE = 38  # ~top-left -> bottom-right

# Card face: white PVC with a cool shadow side.
CARD_STOPS = [(0.00, "#FFFFFF"), (0.46, "#EDF2FA"), (1.00, "#BCC9DF")]
CARD_ANGLE = 28

# Contact chip: polished brass.
CHIP_STOPS = [(0.00, "#FFF1C8"), (0.38, "#E9BC55"), (0.74, "#C48C2C"), (1.00, "#8E5F14")]
CHIP_TRACE = (110, 70, 12, 190)  # engraved contact pattern
CHIP_RIM = (255, 246, 214, 150)

ARC_COLOR = (26, 60, 168, 255)  # contactless waves — indigo, echoes the ground
ANTENNA_COLOR = (150, 168, 196, 120)  # RFID inlay trace, deliberately faint
BAR_COLOR = (139, 155, 182, 165)  # embossed name / number bars

# The two masters are separate DESIGNS, not one design at two resolutions.
# "low" shrinks the card so clear ground survives on every side (at 16px an
# edge-to-edge card erases the rounded-square silhouette), enlarges the chip,
# thickens the arcs to two, and lightens the shadow so it cannot eat the ground.
#   card    fraction of the canvas taken by the card's width
#   tilt    degrees CCW; the right edge rides up
#   shadow  multiplier on the card's drop-shadow opacity
#   arcs    contactless arc radii, as fractions of the card height
#   arc_w   arc stroke width, fraction of card height
#   chip    (width, height) as fractions of (card width, card height)
#   cluster vertical centre of the chip+arcs group, fraction of card height
#   trim    draw the fine detail: antenna trace + embossed data bars
DETAIL = {
    "full": dict(card=0.635, tilt=11.0, shadow=1.00, arcs=(0.19, 0.29, 0.39),
                 arc_w=0.036, chip=(0.210, 0.292), cluster=0.435, trim=True),
    "low": dict(card=0.550, tilt=8.0, shadow=0.72, arcs=(0.24, 0.375),
                arc_w=0.064, chip=(0.260, 0.360), cluster=0.500, trim=False),
}

# Master render sizes. Both are >=4x the largest target they serve
# (4096 -> 1024 = 4x supersample, 1024 -> 64 = 16x).
MASTERS = {"full": 4096, "low": 1024}
LOW_DETAIL_MAX_PX = 64  # 16, 32 and 64 px come off the simplified master

# Apple's rounded-square grid: an 824x824 body on a 1024x1024 canvas.
GROUND_INSET = 100.0 / 1024.0
SQUIRCLE_N = 5.0  # superellipse exponent ~ the continuous-corner shape

ICONSET_ENTRIES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


# ---------------------------------------------------------------------------
# Small drawing utilities
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Shipped designs. `--design NAME` builds the icon from assets/icons/NAME.png
# instead of drawing one; the procedural path below still works and is what
# `--design procedural` selects.
#
# The default is studio_gradient because it is the only one that survives 16x16,
# which is the size macOS uses in list views and the size that decides whether an
# icon is findable in a full Dock. Rendered at 16/32/64/128 side by side, the
# white-card designs disappear against a light background and the detailed ones
# turn to mush; a coloured ground with one shape on it does not.
#
# It also replaced a drawing of a card with a brass EMV contact chip on it, which
# read as a credit card. This app prints ID and RFID cards.
# ---------------------------------------------------------------------------
DESIGNS = ["studio_gradient", "holo_card", "dual_tray", "ink_chip", "kunai",
           "reader_puck", "procedural"]
DEFAULT_DESIGN = "studio_gradient"
ICON_DIR = ASSETS / "icons"


def masters_from_png(name: str):
    """Load a shipped design and use it for every size.

    One image for all sizes, unlike the procedural path which draws a separate
    low-detail master for 64px and below. These designs are already simple enough
    to hold at 16px -- that is why this one was chosen -- so a second master would
    be a different picture for no gain.
    """
    src = ICON_DIR / f"{name}.png"
    if not src.exists():
        raise SystemExit(f"no such design: {name}\navailable: {', '.join(DESIGNS)}")
    im = Image.open(src).convert("RGBA")
    if im.width != im.height:
        side = min(im.width, im.height)
        left, top = (im.width - side) // 2, (im.height - side) // 2
        im = im.crop((left, top, left + side, top + side))
    return {"full": im, "low": im}


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _ramp(stops, n: int):
    """Interpolate multi-stop colours into an n-entry list of RGB tuples."""
    stops = sorted(((float(p), _rgb(c)) for p, c in stops), key=lambda s: s[0])
    out = []
    seg = 0
    for i in range(n):
        t = i / (n - 1)
        while seg < len(stops) - 2 and t > stops[seg + 1][0]:
            seg += 1
        p0, c0 = stops[seg]
        p1, c1 = stops[seg + 1]
        f = 0.0 if p1 <= p0 else min(1.0, max(0.0, (t - p0) / (p1 - p0)))
        out.append(tuple(round(a + (b - a) * f) for a, b in zip(c0, c1)))
    return out


def linear_gradient(w: int, h: int, stops, angle: float) -> Image.Image:
    """RGB linear gradient. angle 0 = top->bottom, +90 = left->right,
    +45 = top-left->bottom-right (verified empirically against PIL's rotate).

    Built at a capped working resolution and scaled up: a linear ramp is exactly
    reconstructed by bicubic upscaling, so this costs nothing in quality and
    keeps the 4096px master cheap.
    """
    work = min(max(w, h), 1024)
    ww = max(2, round(w * work / max(w, h)))
    wh = max(2, round(h * work / max(w, h)))

    n = 512
    ramp = Image.new("RGB", (1, n))
    ramp.putdata(_ramp(stops, n))

    d = int(math.hypot(ww, wh)) + 4
    g = ramp.resize((d, d), Image.BICUBIC).rotate(angle, resample=Image.BICUBIC, expand=True)
    gw, gh = g.size
    left, top = (gw - ww) // 2, (gh - wh) // 2
    g = g.crop((left, top, left + ww, top + wh))
    return g if (ww, wh) == (w, h) else g.resize((w, h), Image.BICUBIC)


def radial_falloff(w: int, h: int, cx: float, cy: float, radius: float) -> Image.Image:
    """L mask, 255 at (cx, cy) fading to 0 at `radius` px. Coordinates in px."""
    d = max(2, int(radius * 2))
    disc = ImageChops.invert(Image.radial_gradient("L").resize((d, d), Image.BICUBIC))
    out = Image.new("L", (w, h), 0)
    out.paste(disc, (round(cx - radius), round(cy - radius)))
    return out


def squircle_points(cx: float, cy: float, half: float, n: float, steps: int = 1024):
    """Superellipse |x/a|^n + |y/a|^n = 1 — the macOS continuous-corner shape."""
    e = 2.0 / n
    pts = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        x = math.copysign(abs(ct) ** e, ct)
        y = math.copysign(abs(st) ** e, st)
        pts.append((cx + half * x, cy + half * y))
    return pts


def round_arc(draw: ImageDraw.ImageDraw, cx, cy, r, a0, a1, width, fill):
    """Arc with round caps. `r` is the stroke CENTRELINE radius.

    PIL's arc() thickens inward from the bounding box, so the bbox is expanded
    by width/2 and the caps are centred on the centreline — placing caps at the
    bbox radius instead leaves them detached, reading as stray dots.
    """
    w = max(1, int(round(width)))
    ro = r + w / 2.0
    draw.arc((cx - ro, cy - ro, cx + ro, cy + ro), a0, a1, fill=fill, width=w)
    cap = w / 2.0
    for ang in (a0, a1):
        px = cx + r * math.cos(math.radians(ang))
        py = cy + r * math.sin(math.radians(ang))
        draw.ellipse((px - cap, py - cap, px + cap, py + cap), fill=fill)


def tinted(size, color, mask: Image.Image) -> Image.Image:
    """RGBA layer of a flat colour showing through `mask`."""
    layer = Image.new("RGBA", size, color[:3] + (0,))
    solid = Image.new("L", size, color[3] if len(color) > 3 else 255)
    layer.putalpha(ImageChops.multiply(solid, mask))
    return layer


def edge_ramp(w: int, h: int, top_value: int, reach: float) -> Image.Image:
    """L ramp: `top_value` at y=0 decaying to 0 by y = reach*h. Used to fade a
    rim highlight so only the lit top edge of a shape catches light."""
    n = 256
    strip = Image.new("L", (1, n))
    cut = max(1, int(n * reach))
    strip.putdata([max(0, round(top_value * (1 - i / cut))) if i < cut else 0 for i in range(n)])
    return strip.resize((w, h), Image.BICUBIC)


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------


def draw_card(cw: int, ch: int, detail: str) -> Image.Image:
    """The card face, axis-aligned, in a tight cw x ch RGBA canvas."""
    spec = DETAIL[detail]
    low = detail == "low"
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    # Body -----------------------------------------------------------------
    radius = 0.052 * cw
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=radius, fill=255)
    body = linear_gradient(cw, ch, CARD_STOPS, CARD_ANGLE).convert("RGBA")
    body.putalpha(mask)
    card.alpha_composite(body)

    ink = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)

    # RFID antenna inlay: a single trace just inside the border, hinting at the
    # coil in a real inlay. Two concentric traces read as a certificate frame.
    if spec["trim"]:
        inset = 0.072 * ch
        d.rounded_rectangle(
            (inset, inset, cw - 1 - inset, ch - 1 - inset),
            radius=radius * 0.72,
            outline=ANTENNA_COLOR,
            width=max(1, round(0.0085 * ch)),
        )

    # Contact chip ----------------------------------------------------------
    chip_w = spec["chip"][0] * cw
    chip_h = spec["chip"][1] * ch
    chip_x = 0.100 * cw
    # Sit the cluster above centre at full detail so it balances the data bars
    # below it; with no bars drawn, the low master centres it instead.
    chip_y = spec["cluster"] * ch - chip_h / 2

    # Contactless arcs, radiating from just right of the chip and sharing its
    # centreline so chip + waves read as one cluster rather than two objects.
    ax = chip_x + chip_w * 1.32
    ay = chip_y + chip_h / 2
    for r in spec["arcs"]:
        round_arc(d, ax, ay, r * ch, -52, 52, spec["arc_w"] * ch, ARC_COLOR)

    # Embossed data bars, full detail only.
    if spec["trim"]:
        bh = 0.050 * ch
        for y, wfrac in ((0.720, 0.315), (0.822, 0.195)):
            by = y * ch
            d.rounded_rectangle(
                (0.100 * cw, by, 0.100 * cw + wfrac * cw, by + bh),
                radius=bh / 2,
                fill=BAR_COLOR,
            )

    card.alpha_composite(ink)
    card.alpha_composite(draw_chip(round(chip_w), round(chip_h), low), (round(chip_x), round(chip_y)))

    # Lighting: bright top edge, soft shaded bottom edge --------------------
    lw = max(2, round(0.012 * ch))
    rim = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(rim).rounded_rectangle(
        (lw / 2, lw / 2, cw - 1 - lw / 2, ch - 1 - lw / 2), radius=radius, outline=255, width=lw
    )
    card.alpha_composite(tinted((cw, ch), (255, 255, 255, 255), ImageChops.multiply(rim, edge_ramp(cw, ch, 235, 0.30))))
    bottom = ImageChops.multiply(rim, ImageChops.invert(edge_ramp(cw, ch, 255, 1.0)))
    card.alpha_composite(tinted((cw, ch), (28, 44, 92, 90), bottom))

    # Hard-clip to the rounded body so nothing bleeds past the corners.
    card.putalpha(ImageChops.multiply(card.split()[3], mask))
    return card


def draw_chip(w: int, h: int, low: bool) -> Image.Image:
    """Brass EMV-style contact module: gradient plate + engraved pad pattern."""
    chip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    radius = 0.20 * min(w, h)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    plate = linear_gradient(w, h, CHIP_STOPS, 30).convert("RGBA")
    plate.putalpha(mask)
    chip.alpha_composite(plate)

    # Engraved contact layout: a central core pad with four spokes running out
    # to the plate edges. Full-height crossing lines instead read as a '#'.
    ink = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)
    lw = max(1, round((0.075 if low else 0.058) * min(w, h)))
    cl, cr, ct, cb = 0.29 * w, 0.71 * w, 0.31 * h, 0.69 * h
    d.rounded_rectangle((cl, ct, cr, cb), radius=0.09 * w, outline=CHIP_TRACE, width=lw)
    d.line((0.08 * w, h / 2, cl, h / 2), fill=CHIP_TRACE, width=lw)  # west
    d.line((cr, h / 2, 0.92 * w, h / 2), fill=CHIP_TRACE, width=lw)  # east
    d.line((w / 2, 0.07 * h, w / 2, ct), fill=CHIP_TRACE, width=lw)  # north
    d.line((w / 2, cb, w / 2, 0.93 * h), fill=CHIP_TRACE, width=lw)  # south
    chip.alpha_composite(ink)

    # Thin polished rim so the plate separates from the white card.
    rim = Image.new("L", (w, h), 0)
    ImageDraw.Draw(rim).rounded_rectangle(
        (lw / 2, lw / 2, w - 1 - lw / 2, h - 1 - lw / 2), radius=radius, outline=255, width=max(1, lw // 2)
    )
    chip.alpha_composite(tinted((w, h), CHIP_RIM, ImageChops.multiply(rim, edge_ramp(w, h, 255, 0.45))))

    chip.putalpha(ImageChops.multiply(chip.split()[3], mask))
    return chip


# ---------------------------------------------------------------------------
# The master render
# ---------------------------------------------------------------------------


def build_master(res: int, detail: str) -> Image.Image:
    """Full icon at `res` px square, RGBA, transparent outside the ground."""
    spec = DETAIL[detail]
    S = res
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Ground silhouette -----------------------------------------------------
    inset = GROUND_INSET * S
    half = (S - 2 * inset) / 2.0
    gmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(gmask).polygon(squircle_points(S / 2, S / 2, half, SQUIRCLE_N, 1440), fill=255)

    # Drop shadow beneath the whole icon (macOS icons bake in a soft one).
    shadow = Image.new("L", (S, S), 0)
    shadow.paste(gmask, (0, round(0.014 * S)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(0.020 * S))
    base.alpha_composite(tinted((S, S), (5, 10, 30, 120), shadow))

    # Ground fill + lighting -------------------------------------------------
    ground = linear_gradient(S, S, GROUND_STOPS, GROUND_ANGLE).convert("RGBA")
    ground.putalpha(gmask)
    glow = radial_falloff(S, S, 0.30 * S, 0.16 * S, 0.72 * S)
    ground.alpha_composite(tinted((S, S), (150, 190, 255, 70), ImageChops.multiply(glow, gmask)))
    vignette = ImageChops.invert(radial_falloff(S, S, S / 2, 0.46 * S, 0.80 * S))
    ground.alpha_composite(tinted((S, S), (4, 8, 26, 110), ImageChops.multiply(vignette, gmask)))
    base.alpha_composite(ground)

    # Card + its shadow, clipped to the ground -------------------------------
    cw = round(spec["card"] * S)
    ch = round(cw / CR80_ASPECT)
    card = draw_card(cw, ch, detail).rotate(spec["tilt"], resample=Image.BICUBIC, expand=True)
    px = round(S / 2 - card.width / 2)
    py = round(S * 0.497 - card.height / 2)

    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    alpha = Image.new("L", (S, S), 0)
    alpha.paste(card.split()[3], (px, py))
    # Two-part shadow: a broad ambient pool plus a tighter contact shadow.
    for blur, dy, op in ((0.045 * S, 0.045 * S, 130), (0.013 * S, 0.014 * S, 120)):
        off = Image.new("L", (S, S), 0)
        off.paste(alpha, (0, round(dy)))
        col = (3, 8, 28, round(op * spec["shadow"]))
        layer.alpha_composite(tinted((S, S), col, off.filter(ImageFilter.GaussianBlur(blur))))
    layer.alpha_composite(card, (px, py))
    layer.putalpha(ImageChops.multiply(layer.split()[3], gmask))
    base.alpha_composite(layer)

    # Ground rim highlight, drawn last so it stays crisp over the card.
    rw = max(2, round(0.0045 * S))
    rim = Image.new("L", (S, S), 0)
    pts = squircle_points(S / 2, S / 2, half - rw / 2, SQUIRCLE_N, 1440)
    ImageDraw.Draw(rim).line(pts + [pts[0]], fill=255, width=rw, joint="curve")
    rim = ImageChops.multiply(ImageChops.multiply(rim, gmask), edge_ramp(S, S, 190, 0.40))
    base.alpha_composite(tinted((S, S), (255, 255, 255, 255), rim))

    return base


def render(masters: dict[str, Image.Image], px: int) -> Image.Image:
    """Downsample the appropriate master to `px` with LANCZOS."""
    key = "low" if px <= LOW_DETAIL_MAX_PX else "full"
    return masters[key].resize((px, px), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def build_iconset(masters, iconset: Path) -> None:
    if iconset.exists():
        shutil.rmtree(iconset)  # idempotent: never merge into a stale iconset
    iconset.mkdir(parents=True)
    cache: dict[int, Image.Image] = {}
    for name, px in ICONSET_ENTRIES:
        if px not in cache:
            cache[px] = render(masters, px)
        cache[px].save(iconset / name, "PNG")


def run_iconutil(iconset: Path, icns: Path) -> None:
    icns.parent.mkdir(parents=True, exist_ok=True)
    if icns.exists():
        icns.unlink()
    subprocess.run(
        ["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        check=True,
        capture_output=True,
    )


def contact_sheet(masters, path: Path, sizes=(16, 32, 64, 128)) -> None:
    """Nearest-neighbour blow-up of the small sizes — the only honest way to
    judge whether the silhouette survives downsampling."""
    cell, pad, label = 256, 22, 20
    sheet = Image.new("RGBA", (len(sizes) * (cell + pad) + pad, cell + label + 2 * pad), (245, 246, 249, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, px in enumerate(sizes):
        x = pad + i * (cell + pad)
        img = render(masters, px)
        sheet.alpha_composite(img.resize((cell, cell), Image.NEAREST), (x, pad))
        draw.text((x, pad + cell + 5), f"{px}x{px}", fill=(40, 46, 60, 255), font=font)
    sheet.convert("RGB").save(path, "PNG")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate Card Studio's AppIcon.icns")
    ap.add_argument("--out", type=Path, default=ASSETS / "AppIcon.icns")
    ap.add_argument("--iconset", type=Path, default=None, help="default: <out>.iconset next to --out")
    ap.add_argument("--preview", type=Path, default=ASSETS / "icon_preview.png")
    ap.add_argument("--preview-size", type=int, default=512)
    ap.add_argument("--contact", type=Path, default=None, help="write a small-size proof sheet")
    ap.add_argument("--png", action="append", default=[], metavar="SIZE=PATH", help="extra PNG dump, repeatable")
    ap.add_argument("--keep-iconset", action="store_true", help="leave the .iconset dir on disk")
    ap.add_argument("--design", default=DEFAULT_DESIGN,
                    help=f"which icon to build ({', '.join(DESIGNS)}); default {DEFAULT_DESIGN}")
    ap.add_argument("--list", action="store_true", help="print the available designs and exit")
    args = ap.parse_args(argv)

    if Image is None:
        print("make_icon.py needs Pillow (build-time only): pip install Pillow", file=sys.stderr)
        return 2
    if not Path("/usr/bin/iconutil").exists():
        print("make_icon.py needs macOS /usr/bin/iconutil", file=sys.stderr)
        return 2

    if args.list:
        for d in DESIGNS:
            print(f"{d}{'  (default)' if d == DEFAULT_DESIGN else ''}")
        return 0

    if args.design == "procedural":
        masters = {}
        for detail, res in MASTERS.items():
            print(f"rendering {detail} master at {res}x{res} ...", flush=True)
            masters[detail] = build_master(res, detail)
    else:
        print(f"using design {args.design} ...", flush=True)
        masters = masters_from_png(args.design)

    iconset = args.iconset or args.out.with_suffix(".iconset")
    build_iconset(masters, iconset)
    run_iconutil(iconset, args.out)
    if not args.keep_iconset:
        shutil.rmtree(iconset)

    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        render(masters, args.preview_size).save(args.preview, "PNG")
    if args.contact:
        contact_sheet(masters, args.contact)
    for spec in args.png:
        size, _, path = spec.partition("=")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        render(masters, int(size)).save(p, "PNG")

    print(f"wrote {args.out} ({args.out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
