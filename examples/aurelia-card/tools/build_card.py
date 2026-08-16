#!/usr/bin/env python3
"""Compose AURELIA-CORONA-005 — card 005 of COMPOUND CRAFT — into one offline HTML.

    python3 examples/aurelia-card/tools/build_card.py

Fourth sibling of examples/manis-card/tools/build_card.py. The geometry reasoning
is written there and is identical here; only the differences are below.

THE DROP SHIPPED FACES TOO SMALL TO PRINT. Its vibe_card_front.png and
vibe_card_back.png are 1034x660. A card face at 600 dpi is 2022x1275 at trim, so
those are 51% of the size they need to be, and no amount of upscaling puts detail
back. What the drop DOES carry is the underlying artwork at usable size —
front_editorial.png and back_blueprint.png, both 1920x1280 — so the faces are
composed here instead, the same way card 003's were.

THE TAP MARK'S BOX IS LEFT EMPTY, and that is the whole reason this file lays the
front out the way it does. Card Studio composites the mark at x 68.3, y 36.7 mm,
10.3 mm square, on every card front in this system — the reprint templates depend
on it never moving. On the bleed sheet that is x 69.25-79.55, y 37.65-47.95. The
QR sits at a right edge of 67 mm, which leaves 2.25 mm of clearance, and the
description block ends at 43.75 mm, which leaves 2.25 mm on the other side.
tools/verify_geometry.py fails the build if the mark is missing or moved.

BOTH IMAGES ARE 3:2 AND THE FACE IS 1.5858, so neither fits without a decision.
  FRONT: object-fit cover. Filling 87.5 mm of width scales the 1280 px height to
  58.33 mm against a 55.88 mm face, so 2.45 mm is lost — 1.22 mm off the top and
  the same off the bottom. Checked against the image: the corona's highest point
  sits about 3.5% down and the subject's shoulders run off the bottom edge
  already, so nothing that carries meaning is cut.
  BACK: NOT cover. It is a dimensioned drawing whose title sits at the very top
  and whose calibration ruler sits at the very bottom, and cover would clip both —
  a fabrication drawing that has lost its scale check is worse than no drawing.
  So the drawing is contained in the upper 47 mm and the remaining strip carries
  the id and the address, which is also where the honest sentence goes: this face
  is a REDUCED view, and the 1:1 file lives at the address printed on it.

THE PANEL NUMBERS IN THE SUPPLIED DRAWING ARE WRONG and the card does not repeat
them. Read left to right it runs P01, P03, P04 … P09, P09 … P16, P16 … P21, P23,
P24: twenty-four labels, but P02, P15, P18 and P22 are missing and P09 and P16
each appear twice. The panel COUNT is right and the geometry is right; the
numbering is not, so nothing on this card cites a panel by number and the card
page says so plainly.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ASSETS = PROJ / "assets"
OUT = PROJ / "package" / "index.html"

CARD_ID = "AURELIA-CORONA-005"
TITLE = "Aurelia Kresling Corona 05"
SLUG = "aurelia"
CARD_URL = "https://mrdirno.github.io/vibe-cards/aurelia/"
BOOK = "COMPOUND CRAFT — Book 1"
BOOK_INDEX = 5
BOOK_URL = "https://mrdirno.github.io/vibe-cards/compound-craft/"
LICENSE = "MIT"
TOOL = "vibe-cards"
RUN_ID = "PB-49-14-07"
EPITAPH = f"vc1|{CARD_ID}|{TITLE}|2026-08|{LICENSE}|{TOOL}"

# The drop's own palette, kept because it is the object's.
BONE = "#F2E8CF"
NAVY = "#10243E"
SAGE = "#7BA68D"
COPPER = "#FF7A45"

# A 1x1 transparent PNG. tools/intake_card.py generates the real QR for the slug
# and burns it into the element marked data-vc-qr, so what sits here never ships
# — but it must be a valid PNG data URI or the burn has nothing to replace.
QR_PLACEHOLDER = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

SANS = '-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif'
MONO = "ui-monospace, Menlo, monospace"


def data_uri(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def back_uri() -> str:
    """The blueprint with its own headline cropped off.

    The supplied drawing is headed "AURELIA - KRESLING CORONA - 01". That 01 is
    the number the generator minted, and this card is 005 — so the finished card
    would have carried one number on the front and a different one across the top
    of the back, which is exactly the defect that had to be fixed on card 004.
    The headline is the top 5.8% of the image and nothing else lives there: the
    two subtitle lines below it, the legend, the drawing, the ruler and the title
    block all survive. The card's own strip carries the identity instead.

    Pillow is optional in this repo, so a machine without it still builds — it
    just gets the uncropped drawing, and says so rather than failing quietly.
    """
    src = ASSETS / "back_blueprint.png"
    try:
        from PIL import Image
    except ImportError:
        print("  note: Pillow missing — shipping the drawing with its own 01 headline")
        return data_uri(src)
    im = Image.open(src)
    im = im.crop((0, int(im.height * 0.058), im.width, im.height))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> int:
    front = data_uri(ASSETS / "front_editorial.png")
    back = back_uri()

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE} — {CARD_ID}</title>

<script type="application/json" id="vc-card">
{{
  "spec":       "vc1",
  "id":         "{CARD_ID}",
  "title":      "{TITLE}",
  "date":       "2026-08",
  "license":    "{LICENSE}",
  "tool":       "{TOOL}",
  "url":        "{CARD_URL}",
  "book":       "{BOOK}",
  "book_index": {BOOK_INDEX},
  "book_url":   "{BOOK_URL}",
  "run_id":     "{RUN_ID}",
  "epitaph":    "{EPITAPH}",
  "provenance": "The front image is a generated render. It shows a woman's face. No such person exists and nobody was photographed — an image model made it. The back is a reduced view of the A2 cutting sheet, not a 1:1 template; at 85.6 mm it cannot be one."
}}
</script>

<style>
  *{{box-sizing:border-box}}
  body{{margin:0;background:#15181c;font-family:{SANS};
       display:flex;flex-direction:column;align-items:center;gap:10mm;padding:10mm}}

  /* The face is the bleed sheet. Everything inside is positioned from its edges
     in millimetres, because that is the unit the cutter works in. */
  .card-face{{
    width:87.5mm; height:55.88mm; position:relative; overflow:hidden;
    flex-shrink:0; background:{NAVY};
    box-shadow:0 8px 32px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.06);
  }}
  .bg{{position:absolute; inset:0; width:100%; height:100%; display:block}}

  /* ── front ───────────────────────────────────────────────────────────── */
  /* The scrim is a horizontal gradient, opaque at the left edge and gone before
     it reaches the subject. The salt flat behind the type is bright and its
     luminance varies along the frame, so white type straight onto it is legible
     in a render and marginal in print, where ink gain closes the gap. */
  .scrim{{position:absolute; inset:0;
    background:linear-gradient(90deg, rgba(16,36,62,.92) 0%, rgba(16,36,62,.86) 30%,
                                      rgba(16,36,62,.45) 46%, rgba(16,36,62,0) 60%)}}
  .title{{position:absolute; left:4.8mm; top:6.4mm; width:40mm;
    font-family:ui-serif,Georgia,serif; font-weight:800; font-size:9pt;
    line-height:.98; letter-spacing:-.02em; color:{BONE}}}
  .title .n{{display:block; margin-top:.6mm; color:{COPPER}}}
  .sub{{position:absolute; left:4.8mm; top:20.4mm; width:50mm;
    font:600 4.4pt {MONO}; letter-spacing:.14em; color:rgba(242,232,207,.82);
    text-transform:uppercase}}
  .desc{{position:absolute; left:4.8mm; bottom:5.2mm; width:38mm;
    font-size:5.1pt; line-height:1.36; color:rgba(242,232,207,.95)}}
  .meta{{position:absolute; right:5.2mm; top:7.2mm; text-align:right;
    font:500 4.2pt {MONO}; line-height:1.55; color:rgba(255,255,255,.9);
    text-shadow:0 1px 6px rgba(0,0,0,.85)}}

  /* The QR's right edge lands at 67mm on the bleed sheet. See the module
     docstring: the 10.3mm box at x 69.25-79.55 belongs to the tap mark. */
  .qr{{position:absolute; right:20.5mm; bottom:4.8mm;
    width:21mm; height:21mm; background:#fff; padding:1.2mm; border-radius:1mm;
    box-shadow:0 2px 12px rgba(0,0,0,.4); display:flex}}
  .qr img{{width:100%; height:100%; display:block; image-rendering:pixelated}}

  /* ── back ────────────────────────────────────────────────────────────── */
  .sheet{{position:absolute; left:0; right:0; top:0; height:47mm;
    background:#fff; display:flex; align-items:center; justify-content:center}}
  .sheet img{{max-width:100%; max-height:100%; object-fit:contain; display:block}}
  /* padding-bottom, not centring. The strip runs to the sheet edge because the
     colour has to bleed, but its TEXT must clear the 3.95mm safe zone — centred
     in the full 8.88mm it sat 2.85mm off the edge and a trim in tolerance cuts
     it. Measured by tools/measure_faces.mjs, not by eye. */
  .strip{{position:absolute; left:0; right:0; bottom:0; height:8.88mm;
    background:{NAVY}; color:{BONE};
    display:flex; align-items:center; justify-content:space-between;
    padding:0 4.8mm 2.6mm; font:500 4.1pt {MONO}; letter-spacing:.05em;
    white-space:nowrap; gap:3mm}}
  .strip b{{font-weight:700; letter-spacing:.14em}}
  .strip .mid{{color:rgba(242,232,207,.72); letter-spacing:.02em; text-transform:none}}
</style>
</head>
<body>

<section class="card-face" data-vc-face="front"
         data-vc-trim-mm="85.6x53.98" data-vc-bleed-mm="87.5x55.88"
         aria-label="Front of the card: a folded crown worn on a salt flat, and a QR code that opens its page">
  <img class="bg" src="{front}" alt="" style="object-fit:cover;object-position:50% 45%">
  <div class="scrim"></div>
  <div class="title">AURELIA<br>KRESLING<br>CORONA<span class="n">05</span></div>
  <div class="sub">{CARD_ID} &middot; no glue</div>
  <div class="meta">24 panels<br>folds flat<br>opens to 38&deg;<br>one A2 sheet</div>
  <div class="desc">A crown you fold from one flat sheet. Twenty-four triangles
     twist into a tower that collapses flat and springs open on your head.</div>
  <div class="qr"><img data-vc-qr src="data:image/png;base64,{QR_PLACEHOLDER}"
       alt="QR code that opens this card's page"></div>
</section>

<section class="card-face" data-vc-face="back"
         data-vc-trim-mm="85.6x53.98" data-vc-bleed-mm="87.5x55.88"
         aria-label="Back of the card: a reduced view of the A2 cutting sheet, with its own legend and ruler">
  <div class="sheet"><img src="{back}" alt=""></div>
  <div class="strip">
    <b>{CARD_ID}</b>
    <span>reduced view &middot; 1:1 sheet at the address on the front</span>
  </div>
</section>

</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f'{{"ok": true, "out": "{OUT}", "bytes": {len(doc)}}}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
