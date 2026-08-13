#!/usr/bin/env python3
"""Draw the supply illustrations for the Supplies tab.

    python3 tools/make_supply_art.py            # → src/web/supplies/*.svg

Six things get bought to use this app, and until now the tab described them in
about nine hundred words. Nobody reads nine hundred words to buy a $17 pack of
cards. A picture answers "which one is this" in the time it takes to look.

Why drawn and not photographed: a product photo belongs to whoever took it, and
the listings these point at change their photos without warning. Drawing them
means the art ships with the repo, has no licence attached, costs about 2 KB each,
and stays correct when a vendor swaps their thumbnail.

Why SVG: one file serves the phone and the desktop app at every size, and the
palette is CSS variables, so it follows the app's theme instead of fighting it.

Parametric where it matters. A 125 kHz antenna really does have many more turns
than a 13.56 MHz one — about 100 versus 5 — because the coil has to resonate at a
hundredth of the frequency. Drawing both from one function with `turns` as the
argument keeps that difference true rather than decorative.
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "src" / "web" / "supplies"

# The card is drawn at its real aspect, 85.6 : 53.98. Everything else is drawn
# next to a card, so a reader that looks card-sized on screen is card-sized in life.
CARD_W, CARD_H = 85.6, 53.98
VIEW_W, VIEW_H = 160.0, 108.0

# currentColor for anything structural, so a tile inherits the theme. Fixed hues
# only where the real object has one: copper is copper.
INK = "currentColor"
COPPER = "#b87333"
CYAN = "#4aa3c7"


def head(w: float = VIEW_W, h: float = VIEW_H) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" '
            f'fill="none" stroke-linecap="round" stroke-linejoin="round" '
            f'role="img">')


def card_body(x: float, y: float, w: float, h: float, fill: str = "#f4f3ef",
              op: float = 1.0, stroke: str = "#0000001f") -> str:
    """A CR-80 outline. Corner radius scales with the drawing so it stays 3.18 mm."""
    r = 3.18 * (w / CARD_W)
    return (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:.2f}" '
            f'fill="{fill}" fill-opacity="{op:g}" stroke="{stroke}" stroke-width=".7"/>')


def antenna(x: float, y: float, w: float, h: float, turns: int,
            colour: str = COPPER) -> str:
    """The embedded coil, drawn as a rounded rectangular spiral.

    Real inlay antennas are exactly this shape: concentric rounded rectangles
    hugging the card edge, because the loop wants maximum enclosed area. Turns
    are drawn down to a legible count — a true 100-turn 125 kHz coil would be a
    grey smudge at 160 px, so the high-frequency card draws few and the
    low-frequency card draws many, which is the distinction that matters.
    """
    out, gap = [], 1.5
    for i in range(turns):
        ix, iy = x + i * gap, y + i * gap
        iw, ih = w - i * gap * 2, h - i * gap * 2
        if iw <= 6 or ih <= 6:
            break
        out.append(f'<rect x="{ix:g}" y="{iy:g}" width="{iw:g}" height="{ih:g}" '
                   f'rx="{max(1, 3 - i * .3):.1f}" stroke="{colour}" '
                   f'stroke-opacity=".55" stroke-width=".6"/>')
    return "".join(out)


def chip(cx: float, cy: float, s: float = 7.0) -> str:
    """The die. Small, square, off to one side — where it actually sits."""
    return (f'<rect x="{cx - s/2:g}" y="{cy - s/2:g}" width="{s:g}" height="{s:g}" '
            f'rx="1" fill="{INK}" fill-opacity=".7"/>'
            f'<rect x="{cx - s/2 + 1.6:g}" y="{cy - s/2 + 1.6:g}" '
            f'width="{s - 3.2:g}" height="{s - 3.2:g}" rx=".5" '
            f'fill="{COPPER}" fill-opacity=".8"/>')


def wave(cx: float, cy: float, n: int = 3, r0: float = 5.0, colour: str = CYAN) -> str:
    """The contactless arc. Points up and right, away from the reader face."""
    out = []
    for i in range(n):
        r = r0 + i * 4.5
        out.append(f'<path d="M {cx:g} {cy - r:g} A {r:g} {r:g} 0 0 1 '
                   f'{cx + r * 0.707:.2f} {cy - r * 0.707:.2f}" '
                   f'stroke="{colour}" stroke-opacity="{0.9 - i * 0.2:.2f}" '
                   f'stroke-width="1.6"/>')
    return "".join(out)


# ── the six ───────────────────────────────────────────────────────────────────

def art_card_stack(turns: int, accent: str, label: str) -> str:
    """A pack of cards: two behind, one in front with its coil showing."""
    w, h = 118.0, 74.4                      # a card at 1.38× so it fills the tile
    x, y = 20.0, 16.0
    s = [head()]
    for i, (dx, dy, op) in enumerate([(-9, 9, .30), (-4.5, 4.5, .55)]):
        s.append(card_body(x + dx, y + dy, w, h, "#e8e7e2", op))
    s.append(card_body(x, y, w, h))
    s.append(f'<g>{antenna(x + 7, y + 7, w - 14, h - 14, turns, accent)}</g>')
    s.append(chip(x + w - 20, y + 15))
    s.append(f'<text x="{x + 10:g}" y="{y + h - 9:g}" font-family="ui-monospace,monospace" '
             f'font-size="7" fill="{INK}" fill-opacity=".45">{label}</text>')
    s.append("</svg>")
    return "".join(s)


def art_reader_pcsc() -> str:
    """ACR122U: a slab with a big contactless zone, a card lying on it, USB out the back."""
    s = [head()]
    s.append('<path d="M 26 74 L 34 40 L 128 40 L 136 74 Z" fill="#26262c" '
             'stroke="#ffffff22" stroke-width=".8"/>')            # body, seen from above
    s.append('<ellipse cx="81" cy="57" rx="30" ry="11" fill="#000" fill-opacity=".35"/>')
    s.append(card_body(56, 26, 62, 39, "#f4f3ef", .96))            # card on the pad
    s.append(antenna(61, 31, 52, 29, 4, COPPER))
    s.append(wave(44, 46, 3, 5, CYAN))
    s.append('<rect x="76" y="74" width="10" height="6" rx="1" fill="#26262c"/>')
    s.append('<path d="M 81 80 C 81 92 96 92 96 100" stroke="' + INK +
             '" stroke-opacity=".35" stroke-width="2"/>')          # USB tail
    s.append('<circle cx="112" cy="46" r="1.8" fill="#5fd08a"/>')  # status LED
    s.append("</svg>")
    return "".join(s)


def art_reader_dual() -> str:
    """The keyboard-wedge dual reader: smaller, two frequencies, no write."""
    s = [head()]
    s.append('<rect x="40" y="34" width="80" height="46" rx="6" fill="#26262c" '
             'stroke="#ffffff22" stroke-width=".8"/>')
    s.append('<rect x="48" y="42" width="64" height="30" rx="3" fill="#1a1a1f"/>')
    s.append(wave(66, 60, 2, 5, CYAN))
    s.append(wave(96, 60, 2, 5, COPPER))
    s.append('<text x="80" y="90" font-family="ui-monospace,monospace" font-size="7.5" '
             f'text-anchor="middle" fill="{INK}" fill-opacity=".5">125k + 13.56M</text>')
    s.append('<path d="M 80 34 C 80 22 96 22 96 12" stroke="' + INK +
             '" stroke-opacity=".35" stroke-width="2"/>')
    s.append("</svg>")
    return "".join(s)


def art_pvc_plain() -> str:
    """Blank stock. No coil — that IS the product."""
    w, h = 112.0, 70.6
    s = [head()]
    for dx, dy, op in [(-10, 10, .25), (-5, 5, .5)]:
        s.append(card_body(24 + dx, 18 + dy, w, h, "#e8e7e2", op))
    s.append(card_body(24, 18, w, h))
    s.append(f'<text x="80" y="58" font-family="ui-monospace,monospace" font-size="8" '
             f'text-anchor="middle" fill="{INK}" fill-opacity=".35">CR-80 · 30 mil</text>')
    s.append("</svg>")
    return "".join(s)


def art_tray() -> str:
    """The Canon MP tray, two card wells, seen from above."""
    s = [head()]
    s.append('<rect x="18" y="10" width="124" height="88" rx="5" fill="#1e1e23" '
             'stroke="#ffffff22" stroke-width=".9"/>')
    for i, ty in enumerate((20.0, 57.0)):
        s.append(f'<rect x="30" y="{ty:g}" width="100" height="31" rx="2.2" '
                 f'fill="#0e0e12" stroke="#ffffff18" stroke-width=".7"/>')
        if i == 0:
            s.append(card_body(31.5, ty + 1.5, 97, 28, "#f4f3ef", .92))
    s.append('<circle cx="140" cy="54" r="2.2" fill="' + INK + '" fill-opacity=".3"/>')
    s.append("</svg>")
    return "".join(s)


ART = {
    # 13.56 MHz: about five turns of a wide trace. Phone-readable.
    "nfc":         lambda: art_card_stack(5, COPPER, "NTAG215 · 13.56 MHz"),
    # 125 kHz: a hundred turns of hair-fine wire. No phone will ever read it.
    "rfid-125":    lambda: art_card_stack(14, CYAN, "EM4100 · 125 kHz"),
    "reader-pcsc": art_reader_pcsc,
    "reader-dual": art_reader_dual,
    "pvc-plain":   art_pvc_plain,
    "tray":        art_tray,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)

    a.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for key, fn in ART.items():
        p = a.out / f"{key}.svg"
        p.write_text(fn())
        total += p.stat().st_size
        print(f"  {p.relative_to(REPO)}  {p.stat().st_size / 1024:.1f} KB")
    print(f"{len(ART)} illustrations, {total / 1024:.1f} KB total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
