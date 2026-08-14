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
    m = re.search(r'id=["\']vc-card["\'][^>]*>(.*?)</script>', html, re.S)
    if not m:
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
    fixed = html
    n_qr = 0
    if "data:image/png;base64," in fixed:
        fixed, n_qr = re.subn(r'data:image/png;base64,[A-Za-z0-9+/=]+',
                              "data:image/png;base64," + qr_b64, fixed, count=1)
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
    if qrd.exists():
        out = subprocess.run([str(qrd), str(designs / "back_85.6x53.98mm_600dpi.png")],
                             capture_output=True, text=True).stdout
        mm = re.search(r"->\s*(\S+)", out)
        decoded = mm.group(1) if mm else out.strip()[:80]

    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({
        "ok": True, "id": meta.get("id"), "name": name, "slug": a.slug,
        "url": url, "qr_replaced": n_qr, "url_rewrites": n_url,
        "qr_decodes_to": decoded,
        "qr_matches_url": decoded == url,
        "written": written,
        "next": [f"src/site/{a.slug}/index.html still needs writing",
                 f"add TEMPLATES entries for cards/{prefix}-front.png and -back.png"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
