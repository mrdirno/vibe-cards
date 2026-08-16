#!/usr/bin/env python3
"""Take a card package built somewhere else and wire it into this system.

    python3 tools/intake_card.py <package-dir> --slug <slug> [--name "Nice Name"]

Prints one JSON object. Exit 0 on success, 1 on refusal.

WHAT IT DOES, and why each step exists — the failures are all real ones, hit
while integrating the first three packages by hand:

  1. Reads the package's `#vc-card` metadata block. Refuses without one.
  2. Points the card at its REAL page and burns a REAL QR. Every package so far
     arrived carrying `https://example.com/...` and a QR encoding it — a card
     that scans perfectly and goes nowhere. Fixed at the source, then
     re-rasterised, rather than pasting a QR image over the artwork.
     WHICH embedded image is the QR is now declared by the package rather than
     inferred by position — see `burn_qr`. The first four packages each carried
     exactly one PNG data URI, so "replace the first one" was right by accident
     four times; the fifth carries six (three images, each embedded twice) and
     the QR is the THIRD. Guessing there overwrites the front artwork and still
     exits ok, because the decode at step 6 reads the BACK face — a different
     element, which passes either way.
     (No line of prose here may START with "from" — `verify_contribution.sh`
     reads a leading `from ` as a newly added import and fails the gate.)
  3. Rasterises `[data-vc-face]` at 600 dpi through a headless browser.
     The faces have all rendered at the BLEED box (87.5 x 55.88) while
     DECLARING trim (85.6 x 53.98), so trim is derived by cropping 22 px per
     edge rather than by trusting the attribute. Declared is not measured.
  4. Writes `examples/<slug>/designs/` under the names the print path
     discovers. A file that misses that pattern is not rejected, it is
     silently invisible — see docs/INTEGRATING.md.
  5. Stages web copies for the Card Studio template and the published page.

It does NOT print, commit, push, or publish. Those stay decisions.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRIM = (2022, 1275)          # 85.6 x 53.98 mm at 600 dpi, truncated
BLEED = (2066, 1319)         # trim + 22 px per edge — NOT an independent
                             # conversion, which gives 2066x1320 and cannot
                             # centre a 1275-px trim box (45 is odd)
BORDER = 22
SITE_BASE = "https://mrdirno.github.io/vibe-cards"

# The QR burn-in, and how it is aimed. See burn_qr for the failure behind each.
PNG_DATA_URI = re.compile(r'data:image/png;base64,[A-Za-z0-9+/=]+')
IMG_TAG = re.compile(r'<img\b[^>]*>', re.I)
VC_QR_ATTR = re.compile(r'(?<![-\w])data-vc-qr(?![-\w])', re.I)

RASTER_JS = r"""
import { chromium } from '%(pw)s';
const [,, file, outdir] = process.argv;
const b = await chromium.launch();
// 600 dpi / 96 css dpi = 6.25 exactly
const p = await b.newPage({ viewport:{width:1200,height:900}, deviceScaleFactor:6.25 });
await p.goto('file://' + file, { waitUntil:'networkidle' });
await p.waitForTimeout(700);
const seen = new Set(); let n = 0;
for (const el of await p.$$('[data-vc-face]')) {
  const k = await el.getAttribute('data-vc-face');
  if (seen.has(k)) continue;            // packages have shipped duplicate
  seen.add(k);                          // face nodes (a preview + a print copy)
  await el.screenshot({ path: `${outdir}/face${++n}.png` });
}
console.log(JSON.stringify({ faces: n }));
await b.close();
"""


def find_playwright() -> str:
    """Find a playwright install anywhere plausible.

    The first version only looked one level deep under two roots, which meant
    the tool could not run at all when /Volumes/dual was unavailable and the
    only copy sat two levels down in a home directory. A rasteriser that works
    on exactly one volume is a rasteriser that stops when that volume does.
    """
    roots = [Path("/Volumes/dual"), Path.home(),
             Path.home() / ".npm" / "_npx"]
    for root in roots:
        if not root.is_dir():
            continue
        for depth in ("*", "*/*", "*/*/*"):
            for c in root.glob(f"{depth}/node_modules/playwright/index.mjs"):
                return str(c)
    raise SystemExit("playwright not found (checked /Volumes/dual, $HOME, npx cache)")


def burn_qr(html: str, qr_b64: str) -> tuple[str, dict]:
    """Replace the QR's data URI — the one the package MARKED, not the first one found.

    Returns (html, info); `info["error"]` set means nothing was replaced and the
    caller must refuse. `info["qr_target"]` names the path that ran, because the
    fallback below is the kind that has to announce itself.

    THE FAILURE. This was `re.subn(<png data uri>, ..., count=1)` — replace the
    first embedded PNG. That is a bet that the QR is the first image in the
    document. It won four times: packages one through four each carried exactly
    one PNG data URI (the fourth shipped five images, but four of them were
    JPEG, so one PNG). Package five carries SIX PNG data URIs — three images,
    each embedded twice, once in a face and once in an art strip — and in
    document order they run: front editorial artwork, blueprint artwork, QR. The
    QR is the third. First-match burns a 4.6 KB QR over 1.9 MB of front artwork
    and exits ok:true: the run's own `qr_matches_url` decodes the BACK face,
    which is a different element and still holds a real QR, so the check the
    tool was given to catch a wrong QR cannot see a destroyed front.

    So the target is declared, never positional:

      - MARKED — `<img data-vc-qr src="data:image/png;base64,...">`. Only the
        author knows which image is the QR; this is the one selector that does
        not guess. Every marked `<img>` is burned, not just the first: packages
        embed the same image twice (a screen copy and a print copy), and burning
        one of a pair leaves the two faces disagreeing about where the card goes.
      - UNMARKED and exactly one PNG — the old first-match behaviour, byte for
        byte, so packages one through four re-intake unchanged.
      - UNMARKED and more than one PNG — REFUSE. A guess here destroys artwork
        and reports success; a refusal costs the next author one attribute.

    A marker that is present but unusable also refuses rather than falling
    through to the guess — a misplaced marker means the author DID try to aim
    this, and silently ignoring their aim is the same defect wearing a hat.
    """
    payload = "data:image/png;base64," + qr_b64
    # A replacement FUNCTION, not a template string: nothing in the base64 is
    # read as a backslash escape or a \g group reference on the way in.
    repl = lambda _m: payload
    info = {"qr_replaced": 0, "qr_target": "none", "error": None,
            "png_data_uris": len(PNG_DATA_URI.findall(html))}

    marked = [m for m in IMG_TAG.finditer(html) if VC_QR_ATTR.search(m.group(0))]
    if marked:
        out, cursor = [], 0
        for m in marked:
            tag, hits = PNG_DATA_URI.subn(repl, m.group(0))
            out += [html[cursor:m.start()], tag]
            cursor = m.end()
            info["qr_replaced"] += hits
        out.append(html[cursor:])
        info["qr_target"] = "data-vc-qr"
        if info["qr_replaced"] == 0:
            # Marked, but the src is a file path, not an embedded image. Nothing
            # to burn: the rasteriser would load the package's placeholder QR
            # from disk and print it.
            info["error"] = (f"{len(marked)} element(s) marked data-vc-qr, none carrying an "
                             "embedded png data URI — the QR cannot be burned in. Inline the "
                             "QR as data:image/png;base64,... on the marked <img>.")
            return html, info
        return "".join(out), info

    if VC_QR_ATTR.search(html):
        info["qr_target"] = "data-vc-qr"
        info["error"] = ("found data-vc-qr in the document but not on an <img> tag. Put it on "
                         "the <img> itself: <img data-vc-qr src=\"data:image/png;base64,...\">.")
        return html, info

    if info["png_data_uris"] > 1:
        info["error"] = (f"{info['png_data_uris']} png data URIs and no element marked "
                         "data-vc-qr: cannot tell which one is the QR, and guessing the first "
                         "overwrites the artwork while still exiting ok. Mark the QR image: "
                         "<img data-vc-qr src=\"data:image/png;base64,...\">.")
        return html, info

    if "data:image/png;base64," in html:
        fixed, n = PNG_DATA_URI.subn(repl, html, count=1)
        info["qr_replaced"], info["qr_target"] = n, "first-data-uri"
        return fixed, info
    return html, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--slug", required=True, help="url path + example dir, e.g. tierra")
    ap.add_argument("--name", help="human name; defaults to the metadata title")
    ap.add_argument("--asset-prefix", help="filename prefix under src/web/cards/")
    a = ap.parse_args()

    pkg = Path(a.package).expanduser()
    html_path = pkg / "index.html"
    if not html_path.exists():
        print(json.dumps({"ok": False, "error": f"no index.html in {pkg}"}))
        return 1

    html = html_path.read_text()
    # The opening tag must be a <script>, not merely something carrying the id.
    # A package shipped its metadata in a <div id="vc-card">; the looser pattern
    # matched that div and then ran to the next </script> hundreds of lines
    # below, so json.loads died on "Extra data: line 1 column 602" — an error
    # about the parser, naming neither the element nor the fix.
    m = re.search(r'<script[^>]*\sid=["\']vc-card["\'][^>]*>(.*?)</script>', html, re.S)
    if not m:
        loose = re.search(r'<(\w+)[^>]*\sid=["\']vc-card["\']', html)
        if loose and loose.group(1).lower() != "script":
            print(json.dumps({"ok": False, "error":
                              f"#vc-card is a <{loose.group(1)}>, not a script. Put the "
                              "metadata in <script type=\"application/json\" id=\"vc-card\">"
                              " so it is data the page never renders."}))
            return 1
        print(json.dumps({"ok": False, "error": "no #vc-card metadata block"}))
        return 1
    meta = json.loads(m.group(1))
    name = a.name or meta.get("title", a.slug)
    prefix = a.asset_prefix or a.slug
    url = f"{SITE_BASE}/{a.slug}/"

    work = REPO / ".intake_tmp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()

    # --- the real QR, for the real page -----------------------------------
    qr_png = work / "qr.png"
    r = subprocess.run(["swift", str(REPO / "tools/make_qr.swift"),
                        "--text", url, "--out", str(qr_png), "--ec", "Q"],
                       capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0 or not qr_png.exists():
        print(json.dumps({"ok": False, "error": "QR generation failed",
                          "detail": r.stderr[:200]}))
        return 1

    qr_b64 = base64.b64encode(qr_png.read_bytes()).decode()
    fixed, qr = burn_qr(html, qr_b64)
    if qr["error"]:
        print(json.dumps({"ok": False, "error": qr["error"],
                          "qr_target": qr["qr_target"],
                          "png_data_uris": qr["png_data_uris"]}))
        return 1
    n_qr = qr["qr_replaced"]
    old_url = meta.get("url", "")
    n_url = 0
    if old_url:
        fixed, n_url = re.subn(re.escape(old_url), url, fixed)
    fixed_path = work / "fixed.html"
    fixed_path.write_text(fixed)

    # --- rasterise ---------------------------------------------------------
    js = work / "raster.mjs"
    js.write_text(RASTER_JS % {"pw": find_playwright()})
    r = subprocess.run(["node", str(js), str(fixed_path), str(work)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(json.dumps({"ok": False, "error": "rasterise failed",
                          "detail": r.stderr[-300:]}))
        return 1
    faces = json.loads(r.stdout.strip().splitlines()[-1])["faces"]
    if faces < 2:
        print(json.dumps({"ok": False, "error": f"expected 2 faces, found {faces}"}))
        return 1

    try:
        from PIL import Image
    except ImportError:
        print(json.dumps({"ok": False, "error": "Pillow required"}))
        return 1

    designs = REPO / "examples" / f"{a.slug}-card" / "designs"
    designs.mkdir(parents=True, exist_ok=True)
    web = REPO / "src/web/cards"
    web.mkdir(parents=True, exist_ok=True)
    site = REPO / "src/site" / a.slug
    site.mkdir(parents=True, exist_ok=True)

    written = []
    for i, face in enumerate(("front", "back"), start=1):
        src = work / f"face{i}.png"
        bleed = Image.open(src).convert("RGB").resize(BLEED, Image.LANCZOS)
        bp = designs / f"{face}_87.5x55.88mm_bleed_600dpi.png"
        bleed.save(bp)
        trim = bleed.crop((BORDER, BORDER, BLEED[0] - BORDER, BLEED[1] - BORDER))
        assert trim.size == TRIM, trim.size
        tp = designs / f"{face}_85.6x53.98mm_600dpi.png"
        trim.save(tp)
        shutil.copy(tp, web / f"{prefix}-{face}.png")
        small = trim.copy()
        small.thumbnail((1100, 1100), Image.LANCZOS)
        small.save(site / f"card-{face}.png", optimize=True)
        written += [str(bp.relative_to(REPO)), str(tp.relative_to(REPO))]

    # --- prove the QR survived the round trip ------------------------------
    # A MISSING DECODER MUST NOT LOOK LIKE A BAD QR. `tools/qrdecode` is a
    # compiled binary and is gitignored, so a fresh clone has only the .swift
    # source — and the first version of this reported qr_matches_url:false in
    # that case, which is indistinguishable from the QR actually pointing
    # somewhere wrong. Build it rather than shrug.
    decoded = None
    qrd = REPO / "tools/qrdecode"
    src = REPO / "tools/qrdecode.swift"
    if not qrd.exists() and src.exists():
        subprocess.run(["swiftc", "-O", str(src), "-o", str(qrd)],
                       capture_output=True, text=True, cwd=REPO)
    if not qrd.exists():
        print(json.dumps({"ok": False, "error": "cannot verify the QR: tools/qrdecode is "
                          "missing and could not be built from tools/qrdecode.swift. "
                          "Refusing to report an unverified QR as verified."}))
        return 1
    # BOTH faces, because which one carries the QR is the card's choice. This
    # read only the back, which is where the first four packages put it. The
    # fifth puts it on the front, and the back-only read then returned NO
    # BARCODE — the tool printed qr_matches_url:false NEXT TO ok:true and exited
    # 0. A gate that reports its own check failed and passes anyway is not a
    # gate. So: decode both, match on either, and refuse when neither matches.
    on_face = None
    for face in ("front", "back"):
        out = subprocess.run([str(qrd), str(designs / f"{face}_85.6x53.98mm_600dpi.png")],
                             capture_output=True, text=True).stdout
        mm = re.search(r"->\s*(\S+)", out)
        got = mm.group(1) if mm else None
        if got == url:
            decoded, on_face = got, face
            break
        if decoded is None:
            decoded = got or out.strip()[:80]

    if on_face is None:
        print(json.dumps({"ok": False, "id": meta.get("id"), "slug": a.slug, "url": url,
                          "qr_decodes_to": decoded, "qr_matches_url": False,
                          "error": "no face carries a QR that decodes to the card's own URL. "
                                   "The card would scan to somewhere else, or to nothing."}))
        return 1

    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({
        "ok": True, "id": meta.get("id"), "name": name, "slug": a.slug,
        "url": url, "qr_replaced": n_qr, "url_rewrites": n_url,
        # WHICH image was treated as the QR. "first-data-uri" is the positional
        # fallback, and it is reported because a fallback nobody can see is how
        # the front-artwork overwrite survived four intakes.
        "qr_target": qr["qr_target"], "png_data_uris": qr["png_data_uris"],
        "qr_decodes_to": decoded,
        "qr_matches_url": True,
        "qr_on_face": on_face,
        "written": written,
        "next": [f"src/site/{a.slug}/index.html still needs writing",
                 f"add TEMPLATES entries for cards/{prefix}-front.png and -back.png"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
