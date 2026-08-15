#!/usr/bin/env python3
"""Compose CARPAL-BLOOM-002 — from COMPOUND CRAFT — into one offline HTML.

THIS CARD HAS NO NUMBER, AND THAT IS DELIBERATE. It was built for Compound Craft
slot 003 and MOKU-003 took that slot on the owner's instruction, so this file
names the book it came from and never a position in it. The number used to live
here in three places — a BOOK_INDEX constant, a book_index key in the #vc-card
island, and the literal "CARD 003" in the printed strap line — and it had already
been deleted by hand from the shipped package, which is the state that matters:
a generator that still holds a reverted claim will quietly write it back on the
next run, and nobody re-reads a file they only ever execute. The ink on the cards
already printed still reads CARD 003. That is not fixable and is not hidden — the
page at src/site/bloom/index.html says so in plain words instead.

Third sibling of examples/manis-card/tools/build_card.py. The geometry reasoning
is written there and is identical here; only the differences are below.

THE FRONT IS A THIRD LAYOUT, ON PURPOSE. 001 is a dark field with the photograph
on the right; 002 is a bone field with it on the left. A third card built either
way would make the book read as one card printed three times, so this one runs
the photograph FULL BLEED and sets its type on a scrim over the dark left third
of the frame. It also happens to be the right call for this particular picture:
the bloom is the whole point of the object, it is centred and symmetrical, and
any band crop cuts petals off.

WHY A SCRIM AND NOT JUST WHITE TYPE. The left of the frame is a forearm against
concrete — mid-grey, not dark, and its luminance varies along the arm. White
type straight onto it is legible in the render and marginal in print, where ink
gain closes the gap. The scrim is a horizontal gradient, opaque enough at the
left edge to guarantee contrast and gone by the time it reaches the bloom, so it
never touches the object.

NUMBERS COME OFF THE DRAWING. 14 panels (12 lanceolate petal shields + 2 cuff
bands), A2 594 x 420 mm at 1:1, T-lock tab 12.0 mm into a 12.4 mm slot, +0.4 mm
clearance, tolerance +/-0.2 mm, phyllotaxis spiral at the golden angle 137.5
degrees, cuff length 180 mm. All read from back_blueprint.png's own title block,
specification panel and notes.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ASSETS = PROJ / "assets"
OUT = PROJ / "package" / "index.html"

CARD_ID = "CARPAL-BLOOM-002"
TITLE = "Carpal Bloom 03"
SLUG = "bloom"
CARD_URL = "https://mrdirno.github.io/vibe-cards/bloom/"
BOOK = "COMPOUND CRAFT — Book 1"
BOOK_URL = "https://mrdirno.github.io/vibe-cards/compound-craft/"
LICENSE = "CC-BY-NC-4.0"
TOOL = "vibe-cards"
RUN_ID = "PB-48-93-13"
EPITAPH = "vc1|CARPAL-BLOOM-002|Carpal Bloom 03|2026-08|CC-BY-NC-4.0|vibe-cards"

# ── palette ─────────────────────────────────────────────────────────────────
# The spec's myco_white and myco_grey, with a sage accent taken from nothing in
# the spec because the spec reuses 001's red and 001 owns it. Sage is the one
# note that reads as fungal rather than graphic, and it holds against the
# cream gills without competing with them.
INK = "#0a0a0a"
MYCO = "#E8E6DF"
MYCO_GREY = "#C4C2BE"
SAGE = "#A9BCA4"

DPI = 600
BLEED_PX_W, BLEED_PX_H = 2066, 1319
PX_PER_MM = DPI / 25.4
BLEED_W = BLEED_PX_W / PX_PER_MM
BLEED_H = BLEED_PX_H / PX_PER_MM
SAFE = 3.95
SAFE_BOTTOM = BLEED_H - SAFE

SANS = '-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif'
MONO = "ui-monospace, Menlo, monospace"


def mm(v: float) -> str:
    return f"calc({v:.4g} * var(--mm))"


# ── front photograph, full bleed ────────────────────────────────────────────
# 1920 x 1280 (aspect 1.500) into a 2066 x 1319 frame (aspect 1.566). Matching
# the WIDTH gives 1377 px of height for a 1319 px box, so 58 px is surplus.
# Taking it all off the BOTTOM rather than centring: the bloom sits above centre
# and the lower strip is jars on a shelf, which is the part worth losing.
PH_W, PH_H = 1920, 1280
PH_S = BLEED_W / PH_W                            # mm per source px, width-matched
PH_IMG_W, PH_IMG_H = PH_W * PH_S, PH_H * PH_S    # 87.457 x 58.30 mm
PH_TOP = 0.0

# ── back blueprint ──────────────────────────────────────────────────────────
# Content bands measured off the ink:
#     26-44     sheet strip (A2 / 1:1 / print at 100%)
#     71-148    title block and drawing number
#     174-829   the 14-panel layout — the part worth putting on a card
#     837-938   T-lock callouts under the petal columns
#     958-1215  notes, legend, calibration ruler, specifications, title block
# Cropping to 174-938 keeps every panel AND the T-lock dimension callouts that
# sit directly beneath them, and drops the paragraph blocks that turn to mush.
BP_W, BP_H = 1920, 1280
BP_CROP_X, BP_CROP_W = 70, 1780
BP_CROP_Y, BP_CROP_H = 174, 764
BP_S = BLEED_W / BP_CROP_W
BP_IMG_W, BP_IMG_H = BP_W * BP_S, BP_H * BP_S
BP_LEFT, BP_TOP = -BP_CROP_X * BP_S, -BP_CROP_Y * BP_S
BAND_TOP = BP_CROP_H * BP_S

QR_MM = 11.8
QR_RIGHT = SAFE
QR_TOP = BAND_TOP + 1.2
COL_R = BLEED_W - (QR_RIGHT + QR_MM + 3.0)
SPEC_TOP = BAND_TOP + 2.0
FOOT_TOP = SAFE_BOTTOM - 2.6


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
    "run_id": RUN_ID,
    "epitaph": EPITAPH,
    "provenance": (
        "The front image is a generated render. It shows a forearm and part of a "
        "torso wearing the bloomed bracer — no face, and no identifiable person. "
        "The back is a reduced drawing of the A2 cutting sheet (drawing "
        "PHB-14P-FP-001 rev A), not a 1:1 template — at 85.6 mm it cannot be one, "
        "and it draws the petals as a family, so its panel names and circled "
        "numbers repeat rather than running 1 to 12. Cut from the sheet, not from "
        "the card; where the card and the sheet disagree, the sheet is right."
    ),
}

CSS = f"""
  :root {{ --mm: {PX_PER_MM:.6f}px; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#7c7a75; padding:24px; font-family:{SANS}; }}
  .face {{ position:relative; overflow:hidden; background:{MYCO};
           width:{BLEED_PX_W}px; height:{BLEED_PX_H}px; margin:0 0 24px 0; }}

  .ph {{ position:absolute; inset:0; overflow:hidden; }}
  .ph img {{ position:absolute; left:0; top:{mm(PH_TOP)};
             width:{mm(PH_IMG_W)}; height:{mm(PH_IMG_H)}; }}
  /* Opaque at the left edge, gone before it reaches the bloom. */
  .scrim {{ position:absolute; left:0; top:0; bottom:0; width:{mm(52)};
            background:linear-gradient(90deg, rgba(8,10,9,.90) 0%,
                                        rgba(8,10,9,.80) 34%,
                                        rgba(8,10,9,.42) 66%,
                                        rgba(8,10,9,0) 100%); }}
  .type {{ position:absolute; left:{mm(SAFE)}; top:{mm(SAFE)}; bottom:{mm(SAFE)};
           width:{mm(40)}; }}
  .rule {{ width:{mm(7)}; height:{mm(0.55)}; background:{SAGE}; }}
  .kick {{ margin-top:{mm(2.0)}; font-size:{mm(2.0)}; letter-spacing:{mm(0.26)};
           font-weight:700; color:{MYCO_GREY}; text-transform:uppercase; }}
  .t {{ margin-top:{mm(2.4)}; font-weight:800; letter-spacing:{mm(-0.2)};
        line-height:0.94; font-size:{mm(7.8)}; color:{MYCO}; }}
  .t .a {{ color:{SAGE}; }}
  .t .n {{ color:{MYCO_GREY}; }}
  .facts {{ position:absolute; left:0; bottom:{mm(6.4)}; font-size:{mm(2.3)};
            line-height:1.42; color:{MYCO}; font-weight:500; }}
  .bk {{ position:absolute; left:0; bottom:{mm(3.2)}; font-size:{mm(1.8)};
         letter-spacing:{mm(0.15)}; font-weight:700; color:{MYCO_GREY}; }}
  .id {{ position:absolute; left:0; bottom:0; font-family:{MONO};
         font-size:{mm(1.95)}; color:{MYCO}; }}

  .bp {{ position:absolute; left:0; top:0; width:100%; height:{mm(BAND_TOP)};
         overflow:hidden; background:#fff; }}
  .bp img {{ position:absolute; width:{mm(BP_IMG_W)}; height:{mm(BP_IMG_H)};
             left:{mm(BP_LEFT)}; top:{mm(BP_TOP)}; }}
  .band {{ position:absolute; left:0; right:0; top:{mm(BAND_TOP)}; bottom:0;
           background:{MYCO}; border-top:{mm(0.35)} solid {MYCO_GREY}; }}
  .qr {{ position:absolute; right:{mm(QR_RIGHT)}; top:{mm(QR_TOP)};
         width:{mm(QR_MM)}; height:{mm(QR_MM)}; background:#fff;
         border:{mm(0.3)} solid {INK}; padding:{mm(0.5)}; }}
  .qr img {{ width:100%; height:100%; display:block; image-rendering:pixelated; }}
  .spec {{ position:absolute; left:{mm(SAFE)}; top:{mm(SPEC_TOP)};
           width:{mm(COL_R - SAFE)}; font-family:{MONO};
           font-size:{mm(1.78)}; line-height:1.58; color:{INK}; }}
  .spec b {{ color:#7C8F78; font-weight:700; }}
  .foot {{ position:absolute; left:{mm(SAFE)}; top:{mm(FOOT_TOP)};
           width:{mm(COL_R - SAFE)}; font-family:{MONO}; white-space:nowrap;
           font-size:{mm(1.62)}; color:#6E6A63; }}
"""

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{TITLE} — {CARD_ID}</title>
<style>{CSS}</style></head>
<body>

<section data-vc-face="front" class="face">
  <div class="ph"><img src="{FRONT_URI}" alt=""></div>
  <div class="scrim"></div>
  <div class="type">
    <div class="rule"></div>
    <div class="kick">Phyllotaxis forearm bracer</div>
    <div class="t">CARPAL<br><span class="a">BLOOM</span><br><span class="n">03</span></div>
    <div class="facts">14 panels &middot; 12 petals &middot; golden angle<br>one A2 sheet &middot; no hardware</div>
    <div class="bk">COMPOUND CRAFT &middot; BOOK ONE</div>
    <div class="id">{CARD_ID}</div>
  </div>
</section>

<section data-vc-face="back" class="face">
  <div class="bp"><img src="{BACK_URI}" alt=""></div>
  <div class="band"></div>
  <div class="spec">
    <b>MATERIAL</b>&nbsp; 250&ndash;300&thinsp;gsm card or 1.2&thinsp;mm rPET felt<br>
    <b>SHEET</b>&nbsp;&nbsp;&nbsp;&nbsp; A2 594 &times; 420&thinsp;mm &middot; 1:1 &middot; &plusmn;0.2&thinsp;mm<br>
    <b>T-LOCK</b>&nbsp;&nbsp;&nbsp; 12.4&thinsp;mm slot, 12.0&thinsp;mm tab &middot; spiral 137.5&deg;
  </div>
  <div class="qr"><img data-vc-qr src="{QR_URI}" alt=""></div>
  <div class="foot">{CARD_ID} &middot; CC BY-NC 4.0 &middot; scan for the full sheet</div>
</section>

<script type="application/json" id="vc-card">
{json.dumps(META, indent=2)}
</script>
</body></html>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML)
print(json.dumps({"ok": True, "out": str(OUT), "bytes": len(HTML),
                  "band_top_mm": round(BAND_TOP, 3)}))
