#!/usr/bin/env python3
"""Compose AUREA-LATTICE-002 — card 002 of COMPOUND CRAFT — into one offline HTML.

Sibling of examples/manis-card/tools/build_card.py. Read that one first: the
geometry reasoning, the reason the face box is stated in device pixels, and the
data-URI requirement are all explained there and are identical here. What
follows is only what differs for card 002.

WHAT DIFFERS, AND WHY.

  THE FRONT IS MIRRORED. Card 001 is white and red type on near-black with the
  photograph on the right. Two cards in one book that share a layout read as one
  card printed twice, so 002 puts the photograph on the LEFT and sets near-black
  type on the bone field the object is actually made of. Same system, same
  grid, same safe zone — different card. The amber is not decoration either: it
  is the colour of the bead stops at the fan ribs in the photograph.

  THE QR COVERS NO DRAWING AT ALL, which card 001 could not manage. Card 001's
  plan fills its sheet, so its QR had to be measured into the one gap that cost
  no panel number. This sheet has its 12 nets in a band (source y 220-1008,
  measured, not guessed) with its legend and title block outside them. Cropping
  to the nets leaves 18 mm of card below the drawing, so the QR and the spec sit
  in a paper band under it and nothing is obscured. Better outcome, and it came
  from the sheet's layout rather than from any cleverness here.

NUMBERS ON THE CARD COME OFF THE DRAWING. Every figure printed on either face is
read from back_blueprint.png's own title block and assembly notes: 12 panels,
P01-P12, A2 420 x 594 mm, 1:1, tolerance +/-0.2 mm, 12.0 mm T-lock dovetail tab
into a 12.4 mm slot, assemble clockwise P01 -> P12. The 78 g and the washi-lam
material name come from VIBE_CARD_SPEC.json, which is why the card says
"washi-laminate or craft board" — the drawing says craft cardboard and the spec
says washi-lam, and printing one of them alone would make the card disagree with
one of its own sources.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ASSETS = PROJ / "assets"
OUT = PROJ / "package" / "index.html"

# ── identity ────────────────────────────────────────────────────────────────
# CARD_URL is rewritten by intake wherever it appears, so it appears in the
# metadata and nowhere it should not.
CARD_ID = "AUREA-LATTICE-002"
TITLE = "Aurea Lattice 02"
SLUG = "aurea"
CARD_URL = "https://mrdirno.github.io/vibe-cards/aurea/"
BOOK = "COMPOUND CRAFT — Book 1"
BOOK_URL = "https://mrdirno.github.io/vibe-cards/compound-craft/"
BOOK_INDEX = 2
LICENSE = "CC-BY-NC-4.0"
TOOL = "vibe-cards"
RUN_ID = "PB-48-14-09"
EPITAPH = "vc1|AUREA-LATTICE-002|Aurea Lattice 02|2026-08|CC-BY-NC-4.0|vibe-cards"

# ── palette ─────────────────────────────────────────────────────────────────
# The package's own, with bone and amber promoted: 001 owns red-on-black, and
# these two are the object's actual colours — washi paper and the bead stops.
INK = "#0a0a0a"
BONE = "#FAF7F2"
AMBER = "#D98E3B"
STONE = "#6E6A63"
RULE = "#DCD5C9"

# ── print geometry ─────────────────────────────────────────────────────────
# Identical to card 001, and for the reasons written there: bleed is trim plus
# 22 px per edge, so the pixel grid is the truth and the millimetre names are
# nominal. Chromium floors a screenshot clip to whole CSS pixels before scaling,
# so the face box is sized in device pixels and everything inside it in mm.
DPI = 600
BLEED_PX_W, BLEED_PX_H = 2066, 1319
PX_PER_MM = DPI / 25.4
BLEED_W = BLEED_PX_W / PX_PER_MM               # 87.4573 mm
BLEED_H = BLEED_PX_H / PX_PER_MM               # 55.8165 mm
SAFE = 3.95                                     # mm in from the bleed edge

SANS = '-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif'
MONO = "ui-monospace, Menlo, monospace"


def mm(v: float) -> str:
    return f"calc({v:.4g} * var(--mm))"


# ── front photograph ────────────────────────────────────────────────────────
# 1600 x 1600 SQUARE. A full-height band 39.4 mm wide on a 55.8165 mm card wants
# aspect 0.7059, which is 1129 source px of the 1600. Taking that window from
# x=150 keeps the whole fan (its left rib starts near x 178) and the hinged cuff,
# and gives up the right of the hand, which carries no object.
PH_W, PH_H = 1600, 1600
PH_BAND_W = 39.4
PH_CROP_X, PH_CROP_W = 150, 1129
PH_S = PH_BAND_W / PH_CROP_W                    # mm per source px
PH_IMG_W, PH_IMG_H = PH_W * PH_S, PH_H * PH_S
PH_LEFT, PH_TOP = -PH_CROP_X * PH_S, 0.0

# ── back blueprint ──────────────────────────────────────────────────────────
# 1920 x 1280. Content bands measured off the ink, not eyeballed:
#     36-140   title block and sheet info
#     143-179  scale / material line
#     220-495  panels P01-P04
#     496-719  panels P05-P08
#     721-1008 panels P09-P12
#     1037-1212 legend, calibration ruler, assembly notes
# The 12 nets are therefore y 220-1008 and the ink spans x 50-1875. Cropping to
# exactly that puts all twelve panels on the card at full width and leaves the
# lower band free, which is where the QR and the spec go.
BP_W, BP_H = 1920, 1280
BP_CROP_X, BP_CROP_W = 50, 1825
BP_CROP_Y, BP_CROP_H = 220, 788
BP_S = BLEED_W / BP_CROP_W                      # mm per source px
BP_IMG_W, BP_IMG_H = BP_W * BP_S, BP_H * BP_S
BP_LEFT, BP_TOP = -BP_CROP_X * BP_S, -BP_CROP_Y * BP_S
BAND_TOP = BP_CROP_H * BP_S                     # where the nets end, in mm

# ── back QR ─────────────────────────────────────────────────────────────────
# In the paper band, so it covers no part of the drawing. Sized to sit wholly
# inside the safe zone with its own quiet margin.
# The band is BLEED_H - BAND_TOP = 18.05 mm and it has to hold three things
# without any of them touching: the spec block on the left, the QR on the right,
# and the footer along the bottom. The first layout put all three in the same
# 18 mm with no width limits and produced two collisions — the caption sat on top
# of the MATERIAL line and the footer ran underneath the QR. Everything below is
# therefore a COLUMN with a stated right edge, not a free-floating absolute.
# The band runs BAND_TOP..BLEED_H, but only BAND_TOP..SAFE_BOTTOM is usable:
# everything below SAFE_BOTTOM is inside the trim margin and gets cut off. The
# second layout put the caption at 51.96 mm and the footer's baseline lower
# still, both past the 51.87 mm line — the card looked right on screen and would
# have printed with its licence line shaved. Every y below is stated against
# SAFE_BOTTOM for that reason, and the footer is positioned from the TOP rather
# than the bottom so it cannot drift into the margin.
BAND_H = BLEED_H - BAND_TOP                     # 18.05 mm
SAFE_BOTTOM = BLEED_H - SAFE                    # 51.87 mm — nothing may pass this
QR_MM = 11.8
QR_RIGHT = SAFE
QR_TOP = BAND_TOP + 1.2                         # bottom lands at 50.76, clear
COL_R = BLEED_W - (QR_RIGHT + QR_MM + 3.0)      # right edge of the LEFT column
SPEC_TOP = BAND_TOP + 2.0                       # 3 lines at ~2.8 mm end near 48.2
FOOT_TOP = SAFE_BOTTOM - 2.6                    # one line, wholly inside the safe box


def data_uri(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


FRONT_URI = data_uri(ASSETS / "front_editorial.png")
BACK_URI = data_uri(ASSETS / "back_blueprint.png")
QR_URI = data_uri(ASSETS / "qr_placeholder.png")

META = {
    "spec": "vc2",
    "id": CARD_ID,
    "title": TITLE,
    "url": CARD_URL,
    "license": LICENSE,
    "tool": TOOL,
    "book": BOOK,
    "book_index": BOOK_INDEX,
    "run_id": RUN_ID,
    "epitaph": EPITAPH,
    # The rule this states is docs/CARDS.md §8, amended twice on 2026-08-15. The
    # test is who an image DEPICTS, never how it was made — so what matters here
    # is not that a model produced it but that there is no face and no
    # identifiable person in it, which is a claim about the picture.
    "provenance": (
        "The front image is a generated render. It shows a forearm and a hand "
        "wearing the assembled bracer — no face, and no identifiable person. "
        "The back is the 1:1 fabrication template (drawing ORI-WCB-012 rev 01); "
        "where the render and the sheet disagree, the sheet is right."
    ),
}

CSS = f"""
  /* One CSS pixel is one device dot at 600 dpi, exactly as card 001 does it.
     The face box is therefore the bleed grid in raw device px, and intake's
     6.25x render supersamples down to it rather than resampling up. */
  :root {{ --mm: {PX_PER_MM:.6f}px; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#7c7a75; padding:24px; font-family:{SANS}; }}
  .face {{
    position:relative; overflow:hidden; background:{BONE};
    width:{BLEED_PX_W}px; height:{BLEED_PX_H}px;
    margin:0 0 24px 0;
  }}
  .ph {{ position:absolute; left:0; top:0; width:{mm(PH_BAND_W)}; height:100%; overflow:hidden; }}
  .ph img {{ position:absolute; width:{mm(PH_IMG_W)}; height:{mm(PH_IMG_H)};
             left:{mm(PH_LEFT)}; top:{mm(PH_TOP)}; }}
  /* The type never sits on the photograph; this only softens the seam so the
     eye does not read a hard vertical line between two bright fields. */
  .seam {{ position:absolute; top:0; height:100%; left:{mm(PH_BAND_W - 5)}; width:{mm(5)};
           background:linear-gradient(90deg, rgba(250,247,242,0), {BONE}); }}
  .type {{ position:absolute; left:{mm(PH_BAND_W + 3.4)}; top:{mm(SAFE)};
           right:{mm(SAFE)}; bottom:{mm(SAFE)}; }}
  .rule {{ width:{mm(7)}; height:{mm(0.55)}; background:{AMBER}; }}
  .kick {{ margin-top:{mm(2.0)}; font-size:{mm(2.05)}; letter-spacing:{mm(0.28)};
           font-weight:700; color:{STONE}; text-transform:uppercase; }}
  .t {{ font-weight:800; letter-spacing:{mm(-0.22)}; line-height:0.94;
        font-size:{mm(8.4)}; color:{INK}; }}
  .t .a {{ color:{AMBER}; }}
  .t .n {{ color:{STONE}; }}
  .facts {{ position:absolute; left:0; bottom:{mm(6.6)}; font-size:{mm(2.4)};
            line-height:1.42; color:{INK}; font-weight:500; }}
  .bk {{ position:absolute; left:0; bottom:{mm(3.3)}; font-size:{mm(1.85)};
         letter-spacing:{mm(0.16)}; font-weight:700; color:{STONE}; }}
  .id {{ position:absolute; left:0; bottom:0; font-family:{MONO};
         font-size:{mm(2.0)}; color:{INK}; }}

  .bp {{ position:absolute; left:0; top:0; width:100%; height:{mm(BAND_TOP)}; overflow:hidden; background:#fff; }}
  .bp img {{ position:absolute; width:{mm(BP_IMG_W)}; height:{mm(BP_IMG_H)};
             left:{mm(BP_LEFT)}; top:{mm(BP_TOP)}; }}
  .band {{ position:absolute; left:0; right:0; top:{mm(BAND_TOP)}; bottom:0; background:{BONE};
           border-top:{mm(0.35)} solid {RULE}; }}
  .qr {{ position:absolute; right:{mm(QR_RIGHT)}; top:{mm(QR_TOP)};
         width:{mm(QR_MM)}; height:{mm(QR_MM)}; background:#fff;
         border:{mm(0.3)} solid {INK}; padding:{mm(0.5)}; }}
  .qr img {{ width:100%; height:100%; display:block; image-rendering:pixelated; }}
  .spec {{ position:absolute; left:{mm(SAFE)}; top:{mm(SPEC_TOP)};
           width:{mm(COL_R - SAFE)};
           font-family:{MONO}; font-size:{mm(1.78)}; line-height:1.58; color:{INK}; }}
  .spec b {{ color:{AMBER}; font-weight:700; }}
  /* One line, from the top, width-capped: it wrapped once and broke the licence
     across two lines with the second one in the trim margin. */
  .foot {{ position:absolute; left:{mm(SAFE)}; top:{mm(FOOT_TOP)};
           width:{mm(COL_R - SAFE)}; font-family:{MONO}; white-space:nowrap;
           font-size:{mm(1.62)}; color:{STONE}; }}
"""

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{TITLE} — {CARD_ID}</title>
<style>{CSS}</style></head>
<body>

<section data-vc-face="front" class="face">
  <div class="ph"><img src="{FRONT_URI}" alt=""></div>
  <div class="seam"></div>
  <div class="type">
    <div class="rule"></div>
    <div class="kick">Deployable wrist canopy</div>
    <div class="t" style="margin-top:{mm(2.6)}">AUREA<br><span class="a">LATTICE</span><br><span class="n">02</span></div>
    <div class="facts">12 panels &middot; 12&thinsp;mm T-lock tabs<br>one A2 sheet &middot; 78&thinsp;g &middot; no hardware</div>
    <div class="bk">COMPOUND CRAFT &middot; BOOK ONE</div>
    <div class="id">{CARD_ID}</div>
  </div>
</section>

<section data-vc-face="back" class="face">
  <div class="bp"><img src="{BACK_URI}" alt=""></div>
  <div class="band"></div>
  <div class="spec">
    <b>MATERIAL</b>&nbsp; 2&thinsp;mm washi-laminate or craft board<br>
    <b>SHEET</b>&nbsp;&nbsp;&nbsp;&nbsp; A2 420 &times; 594&thinsp;mm &middot; 1:1 &middot; &plusmn;0.2&thinsp;mm<br>
    <b>T-LOCK</b>&nbsp;&nbsp;&nbsp; 12.4&thinsp;mm slot, 12.0&thinsp;mm tab &middot; P01 &rarr; P12 clockwise
  </div>
  <div class="qr"><img data-vc-qr src="{QR_URI}" alt=""></div>
  <div class="foot">{CARD_ID} &middot; CARD 002 &middot; CC BY-NC 4.0 &middot; scan for the full sheet</div>
</section>

<script type="application/json" id="vc-card">
{json.dumps(META, indent=2)}
</script>
</body></html>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML)
print(json.dumps({"ok": True, "out": str(OUT), "bytes": len(HTML),
                  "band_top_mm": round(BAND_TOP, 3),
                  "qr_top_mm": round(QR_TOP, 3)}))
