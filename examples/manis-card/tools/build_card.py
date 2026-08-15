#!/usr/bin/env python3
"""Compose MANIS-CUIRASS-001 — card 001 of COMPOUND CRAFT — into one offline HTML.

WHY A BUILD SCRIPT AND NOT A HAND-WRITTEN PAGE. Both source images have to be
base64 data URIs: the raster runs from file:// with the network off, and a
missing image is not a degraded card, it is a blank one. Nobody hand-maintains
5 MB of base64. Everything else here — the crop windows, the safe-zone maths —
is arithmetic that wants to be read as arithmetic, next to the numbers it uses.

GEOMETRY, AND WHY THE CARD IS SIZED IN PIXELS.
The bleed raster is 2066 x 1319 px, and that is NOT 87.5 mm x 600/25.4 computed
independently (that gives 2066 x 1320, and 1320 - 1275 = 45 cannot centre the
trim box — docs/INTEGRATING.md §2). Bleed is trim + 22 px per edge, so the grid
is the truth and 87.5 x 55.88 mm is the nominal name for it.

That matters here because Chromium CANNOT emit 2066 px from an element sized in
CSS mm. It floors a screenshot clip to whole CSS pixels before scaling, so at
deviceScaleFactor 6.25 the only reachable widths either side of the target are
330*6.25 = 2063 and 331*6.25 = 2069. Measured, not reasoned — see the probe in
the build log. So the face box is stated in device pixels at dpi=1 scale, and
every dimension INSIDE it is written in millimetres against `--mm`, which is
one CSS pixel per 1/600 inch. Change DPI at the top and the whole card rescales;
nothing here is resolution-dependent except the one integer that has to be.

WHY THE COMPOSITION IS REBUILT RATHER THAN PASSED THROUGH. The arriving package
put its kicker underneath a circular photo inset, ran that inset off the right
edge, reduced the 14-panel plan to a 16 mm circle of noise, and spent the back
on its own build log. The assets and the palette are good and are kept. The
layout is not, and is not.
"""
from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ASSETS = PROJ / "assets"
OUT = PROJ / "package" / "index.html"

# ── identity ────────────────────────────────────────────────────────────────
# Every one of these strings is read by something. CARD_URL especially: intake
# rewrites every occurrence of it in the document, so it appears in the metadata
# and the QR payload and nowhere else.
CARD_ID = "MANIS-CUIRASS-001"
TITLE = "Manis Cuirass 01"
SLUG = "manis"
CARD_URL = "https://mrdirno.github.io/vibe-cards/manis/"
BOOK = "COMPOUND CRAFT — Book 1"
BOOK_URL = "https://mrdirno.github.io/vibe-cards/compound-craft/"
BOOK_INDEX = 1
LICENSE = "CC-BY-NC-4.0"
TOOL = "vibe-cards"
RUN_ID = "PB-47-92-12"
EPITAPH = "vc1|MANIS-CUIRASS-001|Manis Cuirass 01|2026-08|CC-BY-NC-4.0|vibe-cards"

# The live well, copied from src/site/tierra/index.html. The anon key is public
# by design: RLS lets it INSERT one fresh row and nothing else.
WELL = "https://fxjucjvfmklbpapretzr.supabase.co/rest/v1/vibe_card_wishes"
WELL_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
    "ImZ4anVjanZmbWtsYnBhcHJldHpyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg2OTQwNzUs"
    "ImV4cCI6MjA4NDI3MDA3NX0.UVQm1A4okSvej0UJLiKetiFuB4H9Prjv4rYcnGYVBYs"
)

# ── palette (the package's own) ─────────────────────────────────────────────
INK = "#0a0a0a"
RED = "#C1272D"
CONCRETE = "#C4C2BE"
PAPER = "#fafaf8"

# ── print geometry ─────────────────────────────────────────────────────────
DPI = 600
BLEED_PX_W, BLEED_PX_H = 2066, 1319          # trim 2022x1275 + 22 px per edge
PX_PER_MM = DPI / 25.4                        # 23.6220472…
BLEED_W = BLEED_PX_W / PX_PER_MM              # 87.4573 mm — the grid's real width
BLEED_H = BLEED_PX_H / PX_PER_MM              # 55.8165 mm
SAFE = 3.95                                   # mm in from the bleed edge

SANS = '-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif'
MONO = "ui-monospace, Menlo, monospace"


def mm(v: float) -> str:
    """Millimetres, as CSS. One place converts, so one place can be wrong."""
    return f"calc({v:.4g} * var(--mm))"


# ── front photograph: crop window, in source pixels ─────────────────────────
# 21c21fa8a1ef.png is 1280x1920 PORTRAIT and the card is landscape. Cropping it
# to landscape decapitates the subject, so it gets a full-height band instead
# and the card is split. The window below keeps the head (y 265-740) and the
# whole mantle (y 745-1570) with headroom above and torso below; it trims 100 px
# of the left shoulder tip, which is the edge that sits under the type-side
# gradient anyway.
PH_W, PH_H = 1280, 1920
PH_BAND_W = 39.4                              # mm — 45% of the card width
PH_CROP_X, PH_CROP_W = 100, 1110              # source px
PH_S = PH_BAND_W / PH_CROP_W                  # mm per source px
PH_CROP_Y = 115
PH_IMG_W, PH_IMG_H = PH_W * PH_S, PH_H * PH_S
PH_LEFT, PH_TOP = -PH_CROP_X * PH_S, -PH_CROP_Y * PH_S
PH_BAND_X = BLEED_W - PH_BAND_W               # left edge of the photo band

# ── back blueprint: crop window, in source pixels ───────────────────────────
# aacfa0f88731.png is 1920x1280. Its 14 nets occupy x 60-1900, y 125-1005; above
# that is its own header and below it the legend, notes, ruler and title block —
# all of which reduce to grey mush at card size. The window is exactly the nets,
# at full card width so nothing is cropped: all 14 panels are on the card.
BP_W, BP_H = 1920, 1280
BP_CROP_X, BP_CROP_W = 60, 1840
BP_CROP_Y = 125
BP_S = 87.5 / BP_CROP_W                       # mm per source px (87.5 = bleed off both edges)
BP_IMG_W, BP_IMG_H = BP_W * BP_S, BP_H * BP_S
BP_LEFT, BP_TOP = -BP_CROP_X * BP_S, -BP_CROP_Y * BP_S
# The nets are 880 source px tall, and the image is already offset by BP_TOP, so
# the card-y where they end is simply their own height in mm. (Adding BP_CROP_Y
# again here was a bug: it pushed the paper band 6 mm down over the drawing.)
BAND_TOP = 880 * BP_S                         # where the nets end == where paper starts

# ── back QR block ──────────────────────────────────────────────────────────
# 41 modules + a 4-module quiet zone = 49. Rendered at 10 device px per module
# so `image-rendering: pixelated` lands on near-integer module edges instead of
# resampling a QR, which is the one image where softening costs a scan.
QR_MODULES = 49
QR_MM = QR_MODULES * 10 / PX_PER_MM           # 20.74 mm
QR_PAD = 1.1
QR_PANEL_W = QR_MM + 2 * QR_PAD
QR_CAP_TOP = QR_PAD + QR_MM + 0.86
QR_PANEL_H = QR_CAP_TOP + 5.85 + QR_PAD


def png_gray(rows: list[bytes], w: int, h: int) -> bytes:
    """8-bit greyscale PNG, stdlib only.

    Written here rather than via Pillow because this repo is Python-stdlib-only
    (CLAUDE.md) and a QR is nine lines of zlib, not a dependency.
    """
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def build_qr(payload: str, scale: int = 12) -> tuple[bytes, int]:
    """A QR that encodes the real card URL.

    NOT a placeholder. Four of the first four arriving packages shipped a QR
    pointing at example.com (docs/INTEGRATING.md §5.5); intake will overwrite
    this one, but if it does not, the card still works. `qrcode` is optional in
    the Pillow sense — absent, we fall back to the bundled PNG and say so.
    """
    try:
        import qrcode  # optional; matrix only, never its image writer
    except ImportError:
        return (ASSETS / "qr_fallback.png").read_bytes(), 0

    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                      box_size=1, border=4)
    q.add_data(payload)
    q.make(fit=True)
    m = q.get_matrix()
    n = len(m)
    rows = [bytes(bytearray(
        0 if m[y // scale][x // scale] else 255 for x in range(n * scale)
    )) for y in range(n * scale)]
    return png_gray(rows, n * scale, n * scale), n


def data_uri(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


META = {
    "spec": "vc1",
    "id": CARD_ID,
    "title": TITLE,
    "slug": SLUG,
    "url": CARD_URL,
    "qr_payload": CARD_URL,
    "license": LICENSE,
    "license_note": "The design and artwork are CC BY-NC 4.0. Repository code stays MIT.",
    "tool": TOOL,
    "book": BOOK,
    "book_index": BOOK_INDEX,
    "book_url": BOOK_URL,
    "run_id": RUN_ID,
    "epitaph": EPITAPH,
    "date": "2026-08",
    "object": {
        "name": "Kikko Manis Monolith",
        "kind": "14-panel modular pangolin-scale shoulder mantle / cuirass collar",
        "material": "2 mm EVA foam, craft cardboard or fiberboard",
        "sheet": "A2 · 594 x 420 mm",
        "panels": 14, "tabs": 32, "slots": 32,
        "joint": "12.4 mm slot / 12 mm tab T-lock dovetail",
        "scale": "1:1, millimetres",
        "material_area_m2": 0.6,
        "assembly_order": "P01 -> P14",
        "hardware": "none — tabs lock dry; adhesive only after a dry fit",
        "legend": ("solid black = cut line; dashed red = fold/score (valley fold 180 deg); "
                   "circled numbers = edge-match index; arrows = grain direction"),
    },
    "geometry": {
        "trim_mm": {"w": 85.6, "h": 53.98},
        "bleed_mm": {"w": 87.5, "h": 55.88},
        "bleed_px_600dpi": {"w": BLEED_PX_W, "h": BLEED_PX_H},
        "safe_zone_mm_from_bleed": SAFE,
        "note": ("Bleed is trim + 22 px per edge at 600 dpi, not an independent "
                 "mm conversion; the pixel grid is the truth."),
    },
    "palette": {"ink": INK, "red": RED, "concrete": CONCRETE, "paper": PAPER},
    "provenance": {
        "front_image": (
            "AI-GENERATED SYNTHETIC RENDER. The figure on the front is wholly "
            "synthetic — it depicts no real person, and no likeness of any "
            "identifiable individual is used or implied. Declared rather than "
            "removed, because you cannot tell a synthetic face from a real one "
            "by looking, which makes an undeclared one indistinguishable from a "
            "consent failure."
        ),
        "back_image": (
            "The object's own 1:1 fabrication template: 14 numbered panel nets "
            "P01-P14, red dashed fold/score lines, edge-match indices, legend, "
            "spec block and a 10 cm calibration ruler. Reproduced as drawn."
        ),
        "synthetic_imagery": True,
        "depicts_real_person": False,
        "inherited_from": (
            "REPLICABLE_NOVEL_VIBE_CARD (KIKKO CRAFTWORKS, run PB-47-92-12) — "
            "object, blueprint, editorial render and palette. The composition, "
            "geometry and wish route are rebuilt here."
        ),
        "composed_by": "vibe-cards examples/manis-card/tools/build_card.py",
        "qr_encoder": "python-qrcode (matrix only); PNG written with stdlib zlib",
    },
    "wish_channel": WELL,
}

# ── the two spec blocks, written out here so the strings are reviewable ─────
FRONT_KICKER = "14-PANEL SHOULDER MANTLE"
FRONT_SPEC = ["14 panels · 32 T-lock tabs", "0.6 m² · no glue, no hardware"]
FRONT_BOOK = "COMPOUND CRAFT · BOOK ONE"

BACK_SPEC = [
    ("MATERIAL", "2 mm EVA foam or craft board · 1:1 scale, millimetres"),
    ("SHEET", "A2 594 × 420 mm · 14 panels · 32 tabs / 32 slots · 0.6 m²"),
    ("T-LOCK", "12.4 mm slot, 12 mm tab, dovetail · assemble P01 → P14"),
]
BACK_CAPTION = "Scan for the full-size cutting template — and ask for it better."
BACK_BOOKLINE = "COMPOUND CRAFT · BOOK ONE · CARD 001"


def css() -> str:
    return f"""
:root {{
  /* One CSS pixel per 1/600 inch. Every length below is millimetres against
     this token, so the card is resolution-independent in the only sense that
     survives contact with a rasteriser: change DPI, everything rescales. */
  --mm: {PX_PER_MM:.6f}px;
  --ink: {INK}; --red: {RED}; --concrete: {CONCRETE}; --paper: {PAPER};
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #6f7275; font: 400 16px {SANS}; -webkit-font-smoothing: antialiased; }}

/* The face box is the bleed grid in device pixels; see the module docstring.
   Nothing else in the document is sized in px. */
.face {{
  position: relative; overflow: hidden;
  width: {BLEED_PX_W}px; height: {BLEED_PX_H}px;
  font-family: {SANS};
}}
.face img {{ display: block; }}

/* ── FRONT ────────────────────────────────────────────────────────────── */
.front {{ background: var(--ink); }}
.ph {{ position: absolute; top: 0; right: 0; bottom: 0;
       width: {mm(PH_BAND_W)}; overflow: hidden; }}
.ph img {{ position: absolute;
           width: {mm(PH_IMG_W)}; height: {mm(PH_IMG_H)};
           left: {mm(PH_LEFT)}; top: {mm(PH_TOP)}; }}
/* The type never reaches the photograph — it stops {(PH_BAND_X - 44.0):.2f} mm short of it.
   This gradient is not a collision fix, it is so the black field and the
   photograph's own dark left edge read as one surface instead of a seam. */
.ph::after {{ content: ""; position: absolute; inset: 0 auto 0 0;
  width: {mm(16)};
  background: linear-gradient(90deg, {INK} 0%, rgba(10,10,10,.72) 34%, rgba(10,10,10,0) 100%); }}

.ftype {{ position: absolute; left: {mm(6)}; top: 0; width: {mm(38)}; height: 100%; }}
.rule {{ position: absolute; top: {mm(5.9)}; left: 0;
         width: {mm(6.4)}; height: {mm(0.5)}; background: var(--red); }}
.kicker {{ position: absolute; top: {mm(8.0)}; left: 0; right: 0;
  font-size: {mm(1.95)}; font-weight: 600; letter-spacing: .14em;
  text-transform: uppercase; color: var(--concrete); }}
.title {{ position: absolute; top: {mm(12.9)}; left: 0; right: 0;
  font-size: {mm(8.4)}; font-weight: 800; line-height: .90;
  letter-spacing: -.022em; color: var(--paper); }}
.title .r {{ color: var(--red); }}
.title .n {{ color: var(--concrete); }}
.fspec {{ position: absolute; top: {mm(38.6)}; left: 0; right: 0;
  font-size: {mm(2.1)}; line-height: 1.35; color: var(--concrete); }}
.fbook {{ position: absolute; top: {mm(45.6)}; left: 0; right: 0;
  font-size: {mm(1.72)}; font-weight: 600; letter-spacing: .10em;
  color: var(--concrete); opacity: .62; }}
/* The ID is the record that outlives the URL, so it is printed, not linked.
   Concrete on the black field rather than #0a0a0a, which would be invisible —
   "in ink" is about it being on the card, not about the hex. */
.fid {{ position: absolute; top: {mm(48.6)}; left: 0; right: 0;
  font-family: {MONO}; font-size: {mm(2.05)}; letter-spacing: .02em;
  color: var(--concrete); }}

/* ── BACK ─────────────────────────────────────────────────────────────── */
.back {{ background: var(--paper); }}
.bp {{ position: absolute; left: 0; top: 0; right: 0;
       height: {mm(BAND_TOP)}; overflow: hidden; }}
.bp img {{ position: absolute;
           width: {mm(BP_IMG_W)}; height: {mm(BP_IMG_H)};
           left: {mm(BP_LEFT)}; top: {mm(BP_TOP)}; }}

/* Title block. A drawing sheet carries one in a corner; this one carries the
   scan. It sits over the upper right of the plan, which is the one region that
   costs a partial net rather than a whole one. */
.qrblock {{ position: absolute; top: {mm(4.2)}; right: {mm(SAFE)};
  width: {mm(QR_PANEL_W)}; height: {mm(QR_PANEL_H)};
  background: #fff; border: {mm(0.25)} solid var(--ink); }}
.qrblock img {{ position: absolute; top: {mm(QR_PAD)}; left: {mm(QR_PAD)};
  width: {mm(QR_MM)}; height: {mm(QR_MM)}; image-rendering: pixelated; }}
.qrcap {{ position: absolute; top: {mm(QR_CAP_TOP)}; left: {mm(QR_PAD)};
  width: {mm(QR_MM)}; font-size: {mm(1.5)}; line-height: 1.30;
  color: var(--ink); }}

.band {{ position: absolute; left: 0; right: 0; bottom: 0; top: {mm(BAND_TOP)};
  background: var(--paper); border-top: {mm(0.25)} solid var(--ink); }}
.bspec {{ position: absolute; top: {mm(1.05)}; left: {mm(5.6)}; width: {mm(77.8)};
  font-family: {MONO}; font-size: {mm(1.72)}; line-height: 1.22; color: var(--ink); }}
.bspec b {{ font-weight: 700; color: var(--red); }}
.bfoot {{ position: absolute; top: {mm(7.85)}; left: {mm(5.6)}; width: {mm(77.8)};
  display: flex; justify-content: space-between; align-items: baseline;
  font-family: {MONO}; font-size: {mm(1.62)}; color: var(--ink); }}
.bfoot .mid {{ letter-spacing: .04em; opacity: .72; }}
.bfoot .rt {{ opacity: .72; }}

/* ── page chrome (never inside a face) ────────────────────────────────── */
.stage {{ padding: 40px; display: flex; flex-direction: column; gap: 40px;
          align-items: flex-start; }}
.shot {{ box-shadow: 0 18px 60px rgba(0,0,0,.45); }}
.page {{ max-width: 760px; margin: 0 auto 80px; padding: 0 24px; color: #f2f1ee;
         font-size: 15px; line-height: 1.55; }}
.page h1 {{ font-size: 20px; letter-spacing: .02em; margin-bottom: 6px; }}
.page p {{ margin: 10px 0; color: #d8d6d2; }}
.page textarea {{ width: 100%; min-height: 84px; padding: 10px; border-radius: 4px;
  border: 1px solid #9a9c9e; background: #fbfbf9; color: #111; font: inherit; }}
.page button {{ margin-top: 10px; padding: 10px 18px; border: 0; border-radius: 4px;
  background: {RED}; color: #fff; font: 600 15px {SANS}; cursor: pointer; }}
.page .said {{ font-weight: 600; }}
"""


def html() -> str:
    qr_png, qr_n = build_qr(CARD_URL)
    front = data_uri((ASSETS / "front_editorial.png").read_bytes())
    back = data_uri((ASSETS / "back_blueprint.png").read_bytes())
    qr = data_uri(qr_png)

    fspec = "<br>".join(FRONT_SPEC)
    bspec = "<br>".join(f"<b>{k}</b>&nbsp;&nbsp;{v}" for k, v in BACK_SPEC)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE} — {CARD_ID}</title>
<script type="application/json" id="vc-card">
{json.dumps(META, indent=2, ensure_ascii=False)}
</script>
<style>{css()}</style>
</head>
<body>

<div class="stage">

  <section class="face front shot" data-vc-face="front">
    <div class="ph"><img src="{front}" alt=""></div>
    <div class="ftype">
      <div class="rule"></div>
      <div class="kicker">{FRONT_KICKER}</div>
      <div class="title">MANIS<br><span class="r">CUIRASS</span><br><span class="n">01</span></div>
      <div class="fspec">{fspec}</div>
      <div class="fbook">{FRONT_BOOK}</div>
      <div class="fid">{CARD_ID}</div>
    </div>
  </section>

  <section class="face back shot" data-vc-face="back">
    <div class="bp"><img src="{back}" alt=""></div>
    <div class="qrblock">
      <img src="{qr}" alt="" data-vc-qr>
      <div class="qrcap">{BACK_CAPTION}</div>
    </div>
    <div class="band">
      <div class="bspec">{bspec}</div>
      <div class="bfoot">
        <span>{CARD_ID}</span>
        <span class="mid">{BACK_BOOKLINE}</span>
        <span class="rt">CC BY-NC 4.0</span>
      </div>
    </div>
  </section>

</div>

<!-- Page chrome. A wish bar is a PAGE feature, not a card feature: it is
     outside both [data-vc-face] elements on purpose, and touches neither. -->
<div class="page">
  <h1>{TITLE}</h1>
  <p>A 14-panel shoulder mantle you cut from 2&nbsp;mm foam or craft board and
     lock together with tabs. No glue, no hardware. The template is 1:1 — print
     it, check the ruler measures 100&nbsp;mm, and cut.</p>
  <h2 style="font-size:16px;margin-top:22px">Want it changed?</h2>
  <p>Another size, a left-handed strut, a version that fits a child. Say what
     would make it better.</p>
  <label for="wish" style="position:absolute;left:-9999px">Your wish</label>
  <textarea id="wish" placeholder="I&#39;d love it if&hellip;"></textarea>
  <button id="send" type="button" data-wish-well>Send my wish</button>
  <p class="said" id="said" hidden></p>
  <p style="font-size:13px;color:#b9b7b3">No account, no email, nothing to sign
     up for. {CARD_ID} · {BOOK} · CC BY-NC 4.0</p>
</div>

<script>
/* THE WISHING WELL — the live queue, copied from src/site/tierra/index.html.
   The anon key is public by design: row-level security lets it INSERT one fresh
   row and nothing else. It cannot read the queue, edit, delete or forge a
   status. Not a mailto: an inbox is not a queue. */
(function () {{
  var WELL = "{WELL}",
      KEY = "{WELL_KEY}";
  var t = document.getElementById('wish'), b = document.getElementById('send'),
      say = document.getElementById('said');
  if (!t || !b) return;
  var label = b.textContent;
  b.addEventListener('click', function (ev) {{
    ev.preventDefault();
    var text = (t.value || '').trim();
    if (text.length < 2) {{ t.focus(); return; }}
    b.disabled = true; b.textContent = "Sending\\u2026";
    fetch(WELL, {{
      method: 'POST',
      headers: {{ 'apikey': KEY, 'Authorization': 'Bearer ' + KEY,
                 'Content-Type': 'application/json', 'Prefer': 'return=minimal' }},
      body: JSON.stringify({{ card_id: "{CARD_ID}", wish: text, kind: 'improve',
                             lang: "en", page_url: location.href }})
    }}).then(function (r) {{
      if (!r.ok) throw new Error(r.status);
      t.value = ''; b.textContent = label; b.disabled = false;
      if (say) {{ say.textContent = "Got it. Thank you \\u2014 we read these."; say.hidden = false; }}
    }}).catch(function () {{
      b.textContent = label; b.disabled = false;
      if (say) {{ say.textContent = "That didn't send. Try again."; say.hidden = false; }}
    }});
  }});
}})();
</script>
</body>
</html>
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = html()
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT}  {len(doc)/1e6:.2f} MB")
    print(f"  face box      {BLEED_PX_W} x {BLEED_PX_H} px  "
          f"({BLEED_W:.4f} x {BLEED_H:.4f} mm at {DPI} dpi)")
    print(f"  safe zone     {SAFE} mm from bleed  -> "
          f"x {SAFE:.2f}..{BLEED_W-SAFE:.2f}, y {SAFE:.2f}..{BLEED_H-SAFE:.2f} mm")
    print(f"  photo band    x {PH_BAND_X:.2f}..{BLEED_W:.2f} mm "
          f"({PH_BAND_W/BLEED_W*100:.0f}% of width); type stops at 44.00 mm")
    print(f"  photo window  src x {PH_CROP_X}..{PH_CROP_X+PH_CROP_W}, "
          f"y {PH_CROP_Y}..{PH_CROP_Y+round(BLEED_H/PH_S)} of {PH_W}x{PH_H}")
    print(f"  plan window   src x {BP_CROP_X}..{BP_CROP_X+BP_CROP_W}, "
          f"y {BP_CROP_Y}..{BP_CROP_Y+880} of {BP_W}x{BP_H}  (all 14 nets)")
    print(f"  paper band    top {BAND_TOP:.2f} mm")
    print(f"  qr            {QR_MM:.2f} mm in a {QR_PANEL_W:.2f} x {QR_PANEL_H:.2f} mm block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
