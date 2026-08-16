#!/usr/bin/env python3
"""Prove the millimetre pipeline is exact, end to end, on every change.

    python3 tools/verify_geometry.py           # exit 0 if every placement is exact
    python3 tools/verify_geometry.py --verbose

A card is 85.6 × 53.98 mm and that number has to survive from the designer, through
the PDF composer, to the page — untouched. Nothing in this project is allowed to
scale it. This asserts that, by building real PDFs and measuring what came out,
rather than by reading the code that made them.

It exists because of a real incident. Printed cards came back 81.83 × 49.94 mm
against a card of 85.6 × 53.98 — a 4.4% shrink — and the first instinct was to
hunt for a units bug. Measuring the PDF settled it in one command: the composer
was exact to three decimal places, so the fault was downstream in the print path.
Without a measurement the search would have started in the wrong file.

That is what this is for: when a card comes out the wrong size, run this FIRST.
Green means the geometry left the app correct and the problem is CUPS, the driver
or the print dialog. Red means it is ours, and it names the placement.

Checked here:
  * mm → PDF points at exactly 72/25.4, no rounding drift
  * MediaBox equals the requested page, to 0.01 mm
  * every image lands at the requested size and origin, to 0.01 mm
  * the y-axis flip (PDF is bottom-left, the app is top-left) is exact
  * bleed grows a placement by exactly 2 × bleed and shifts it by exactly −bleed
  * calibration dx/dy translates without scaling
  * the tray slots in profiles.json fit the page, with and without bleed
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

try:
    import pdfwriter
    from PIL import Image
except ImportError as exc:
    print(f"verify_geometry.py needs Pillow (build-time only): {exc}", file=sys.stderr)
    raise SystemExit(2)

PT_PER_MM = 72.0 / 25.4
TOL_MM = 0.01                      # 0.01 mm is ~2.4 px at 600 dpi: tighter than the printer
CARD_W, CARD_H = 85.6, 53.98
VERBOSE = False
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if detail and (VERBOSE or not ok):
        print(f"        {detail}")
    if not ok:
        fails.append(f"{name} — {detail}")


def jpeg(w_mm: float, h_mm: float, dpi: int = 600) -> bytes:
    px = lambda mm: max(1, round(mm / 25.4 * dpi))
    buf = io.BytesIO()
    Image.new("RGB", (px(w_mm), px(h_mm)), (0, 0, 0)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def emit(placements: list[dict], page_w: float = 120.0, page_h: float = 120.0) -> bytes:
    out = Path("/tmp/_vc_geom.pdf")
    images = [{
        "data": jpeg(p["w_mm"], p["h_mm"]), "format": "jpeg",
        "x_mm": p["x_mm"], "y_mm": p["y_mm"],
        "w_mm": p["w_mm"], "h_mm": p["h_mm"],
        "rotate_deg": p.get("rotate_deg", 0),
    } for p in placements]
    pdfwriter.build_pdf(str(out), page_w, page_h, images)
    return out.read_bytes()


def measure(raw: bytes) -> tuple[tuple[float, float], list[dict]]:
    """Page size and every placement, in mm, read back out of the PDF."""
    mb = re.search(rb"/MediaBox\s*\[([^\]]+)\]", raw)
    v = [float(x) for x in mb.group(1).split()]
    page = ((v[2] - v[0]) / PT_PER_MM, (v[3] - v[1]) / PT_PER_MM)

    placed = []
    for m in re.finditer(rb"([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+"
                         rb"([\d.\-]+)\s+([\d.\-]+)\s+cm", raw):
        a, b, c, d, e, f = (float(x) for x in m.groups())
        placed.append({
            "w_mm": a / PT_PER_MM, "h_mm": d / PT_PER_MM,
            "x_mm": e / PT_PER_MM,
            # PDF origin is bottom-left; the app measures y from the top.
            "y_mm": page[1] - (f + d) / PT_PER_MM,
        })
    return page, placed


def near(a: float, b: float) -> bool:
    return abs(a - b) <= TOL_MM


def main(argv=None) -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    VERBOSE = ap.parse_args(argv).verbose

    print("\nUNITS")
    check("PT_PER_MM is exactly 72/25.4",
          abs(pdfwriter.PT_PER_MM - PT_PER_MM) < 1e-12,
          f"module says {pdfwriter.PT_PER_MM!r}")

    print("\nA SINGLE CARD PLACEMENT")
    want = {"x_mm": 17.553, "y_mm": 3.818, "w_mm": CARD_W, "h_mm": CARD_H}
    page, got = measure(emit([want]))
    check("MediaBox is 120.00 × 120.00 mm", near(page[0], 120) and near(page[1], 120),
          f"got {page[0]:.3f} × {page[1]:.3f}")
    check("exactly one placement emitted", len(got) == 1, f"got {len(got)}")
    if got:
        g = got[0]
        for k, label in [("w_mm", "width"), ("h_mm", "height"),
                         ("x_mm", "x"), ("y_mm", "y from top")]:
            check(f"{label} is exact", near(g[k], want[k]),
                  f"requested {want[k]:.3f} mm, emitted {g[k]:.3f} mm "
                  f"(off by {g[k]-want[k]:+.4f})")

    print("\nNOTHING SCALES THE CARD")
    # The incident this file exists for: a 4.4% shrink. Assert the ratio is 1.
    if got:
        ratio_w = got[0]["w_mm"] / CARD_W
        ratio_h = got[0]["h_mm"] / CARD_H
        check("width ratio is 1.0000", abs(ratio_w - 1) < 1e-4, f"ratio {ratio_w:.6f}")
        check("height ratio is 1.0000", abs(ratio_h - 1) < 1e-4, f"ratio {ratio_h:.6f}")

    print("\nBLEED")
    for b in (0.5, 1.0, 2.0):
        w = {"x_mm": 17.553 - b, "y_mm": 3.818 - b,
             "w_mm": CARD_W + b * 2, "h_mm": CARD_H + b * 2}
        _, g = measure(emit([w]))
        ok = g and all(near(g[0][k], w[k]) for k in w)
        check(f"bleed {b} mm grows by exactly {b*2} mm and shifts by −{b}", bool(ok),
              f"requested {w}, emitted {g[0] if g else None}")

    print("\nCALIBRATION TRANSLATES, IT DOES NOT SCALE")
    for dx, dy in ((-0.395, -0.4), (1.0, -1.0)):
        w = {"x_mm": 17.553 + dx, "y_mm": 3.818 + dy, "w_mm": CARD_W, "h_mm": CARD_H}
        _, g = measure(emit([w]))
        ok = g and near(g[0]["w_mm"], CARD_W) and near(g[0]["h_mm"], CARD_H) \
             and near(g[0]["x_mm"], w["x_mm"]) and near(g[0]["y_mm"], w["y_mm"])
        check(f"dx {dx:+} dy {dy:+} moves without resizing", bool(ok),
              f"emitted {g[0] if g else None}")

    print("\nTRAY SLOTS FIT THE PAGE")
    import json
    profiles = json.loads((SRC / "profiles.json").read_text())["profiles"]
    for pk, prof in profiles.items():
        pw, ph = prof["page_mm"]["w"], prof["page_mm"]["h"]
        for slot in prof["slots"]:
            cap = min(min(s2["x"], s2["y"], pw - (s2["x"] + s2["w"]), ph - (s2["y"] + s2["h"]))
                      for s2 in prof["slots"])
            for b in (0.0, max(0.0, cap)):
                x0, y0 = slot["x"] - b, slot["y"] - b
                x1, y1 = slot["x"] + slot["w"] + b, slot["y"] + slot["h"] + b
                ok = x0 >= 0 and y0 >= 0 and x1 <= pw and y1 <= ph
                check(f"{pk} slot {slot['name']} fits at bleed {b} mm", ok,
                      f"{x0:.2f},{y0:.2f} → {x1:.2f},{y1:.2f} on {pw}×{ph}")

    print("\nTWO SLOTS DO NOT OVERLAP AT MAX BLEED")
    for pk, prof in profiles.items():
        s = prof["slots"]
        if len(s) < 2:
            continue
        b = 2.0
        a_bot = s[0]["y"] + s[0]["h"] + b
        b_top = s[1]["y"] - b
        check(f"{pk}: bleed does not bridge the slots", a_bot <= b_top,
              f"slot A ends {a_bot:.2f} mm, slot B starts {b_top:.2f} mm "
              f"(gap {b_top - a_bot:+.2f})")


    print("\nDATA SHAPE — supplies")
    # A missing key here throws inside a template literal and renders the whole
    # Supplies tab blank. That happened: reader-pcsc shipped without `specs`, and
    # the symptom was "nothing shows", which points nowhere near the cause.
    sup = json.loads((SRC / "supplies.json").read_text())
    required = ["id", "title", "subtitle", "search", "must_say", "avoid", "specs",
                "blurb", "price", "need", "art"]
    for it in sup.get("items", []):
        missing = [k for k in required if k not in it]
        check(f"supplies item {it.get('id','?')} has every field the renderer reads",
              not missing, f"missing: {', '.join(missing)}")
    for it in sup.get("items", []):
        bad = [r for r in it.get("specs", []) if not isinstance(r, list) or len(r) != 3]
        check(f"supplies item {it.get('id','?')} specs rows are 3-tuples", not bad,
              f"{len(bad)} malformed row(s)")
    for it in sup.get("items", []):
        bad = [l for l in it.get("links", []) if not isinstance(l, dict) or "url" not in l or "label" not in l]
        check(f"supplies item {it.get('id','?')} links have url and label", not bad,
              f"{len(bad)} malformed link(s)")
    # An <img src> that 404s is a broken tile, and a broken tile is invisible in
    # review because the alt text is empty by design. .gitignore has silently
    # withheld a referenced asset three times in this repo, so the reference is
    # checked against the disk rather than trusted.
    for it in sup.get("items", []):
        art = SRC / "web" / it.get("art", "")
        check(f"supplies item {it.get('id','?')} illustration exists on disk",
              bool(it.get("art")) and art.is_file(),
              f"{it.get('art')!r} not found — run tools/make_supply_art.py")

    # ON DISK IS NOT THE SAME AS SHIPPED. .gitignore has now silently withheld a
    # referenced asset four times — founder.png, globe.webp, card-front.png and
    # these drawings — and it never fails locally, because locally the file is
    # right there. It fails for everyone else, as a 404, with nothing raised at
    # build time. So the question is not "does it exist" but "will it leave this
    # machine".
    import subprocess
    for it in sup.get("items", []):
        rel = f"src/web/{it.get('art','')}"
        ignored = subprocess.run(["git", "check-ignore", "-q", rel],
                                 cwd=REPO, capture_output=True).returncode == 0
        check(f"supplies item {it.get('id','?')} illustration is not gitignored",
              not ignored,
              f"{rel} matches a .gitignore rule — it works here and 404s for "
              f"every clone. Add a negation next to the rule that catches it.")

    print("\nDATA SHAPE — template artwork")
    # Every image a TEMPLATE references, checked the same two ways: on disk, and
    # not gitignored. A template whose image is missing builds a blank card and
    # raises nothing — the failure is a card that prints white, discovered on PVC.
    # The gitignore half is not theoretical: a blanket *.jpg / *.svg rule has now
    # silently withheld referenced artwork five separate times in this repo.
    app = (SRC / "web" / "app.js").read_text(errors="replace")
    srcs = sorted(set(re.findall(r"src:\s*'(templates/[^']+)'", app)))
    check("templates reference at least one image", bool(srcs),
          "no `src: 'templates/...'` found — did the registry move?")
    for rel in srcs:
        f = SRC / "web" / rel
        check(f"template art {rel} exists", f.is_file(), "missing on disk")
        ignored = subprocess.run(["git", "check-ignore", "-q", f"src/web/{rel}"],
                                 cwd=REPO, capture_output=True).returncode == 0
        check(f"template art {rel} is not gitignored", not ignored,
              "matches a .gitignore rule — the template will build a BLANK card "
              "for every clone, and nothing will raise")
        if f.is_file():
            im = Image.open(f)
            ar = im.width / im.height
            # Cover-fit crops rather than stretches, so a wrong aspect is not a
            # distortion — it is silently lost artwork at two edges.
            check(f"template art {rel} is CR-80 aspect", abs(ar - CARD_W / CARD_H) < 0.02,
                  f"{im.width}x{im.height} = {ar:.4f} vs {CARD_W/CARD_H:.4f}; "
                  f"cover-fit will crop {abs(1 - ar/(CARD_W/CARD_H))*100:.1f}% off two edges")

    print("\nEVERY CARD'S FRONT CARRIES THE TAP MARK, IN THE ONE PLACE IT LIVES")
    # A card is printed AND programmed, and the mark is the only thing on it that
    # says so. Without it the card is a picture: a person has no reason to put
    # their phone anywhere near it, which makes the chip a feature nobody uses.
    #
    # It went missing on the fifth card and nobody noticed for a day. That card's
    # QR sat in the corner the mark belongs in, so the mark was skipped and a
    # code comment said a reprint template could put one on the back instead. It
    # never did. The card shipped with no mark on either face — the only one in
    # the system — and the owner had to report it more than once, because nothing
    # here could tell a face that had never had the mark from one that was not
    # supposed to. That is what this check is: the difference, stated once.
    #
    # THE POSITION IS PART OF THE CHECK, not decoration. The reprint templates at
    # the top of app.js exist to add the mark to cards already printed without
    # one, and their whole promise is that a reprinted card and a fresh one are
    # indistinguishable. That holds only while every front puts it in the same
    # 10.3 mm box. A mark present but moved is a reprint that lands twice.
    TAP = (68.3, 36.7, 10.3, 10.3)
    entry = re.compile(
        r"'([a-z0-9-]+)':\s*\{.*?src:\s*'cards/([a-z0-9-]+)-(front|back)\.png'(.*?)\n  \},",
        re.S)
    faces = {}
    for m in entry.finditer(app):
        faces.setdefault(m.group(2), {})[m.group(3)] = m.group(0)
    check("the template registry lists at least one card face", bool(faces),
          "no `src: 'cards/<name>-<face>.png'` found — did the registry move?")
    for prefix in sorted(faces):
        front = faces[prefix].get("front")
        if front is None:
            check(f"card {prefix} has a front template", False,
                  "only a back is registered, so nothing can carry the mark")
            continue
        mark = re.search(r"x:\s*([\d.]+),\s*y:\s*([\d.]+),\s*w:\s*([\d.]+),\s*h:\s*([\d.]+),"
                         r"\s*src:\s*'marks/tap-[a-z]+\.png'", front)
        if not mark:
            check(f"card {prefix} front carries a tap mark", False,
                  "no `marks/tap-*.png` element. Every other front has one at "
                  f"x {TAP[0]} y {TAP[1]}. If the artwork occupies that box, move "
                  "the artwork — the mark's position is what the reprint "
                  "templates promise, and it is the only thing telling a person "
                  "this card is tappable.")
            continue
        got = tuple(round(float(g), 2) for g in mark.groups())
        check(f"card {prefix} front tap mark is at {TAP[0]}, {TAP[1]} mm", got == TAP,
              f"found at x {got[0]} y {got[1]} w {got[2]} h {got[3]} — a reprint "
              f"adds the mark at {TAP[0]}, {TAP[1]}, so this card would get two")

    print("\nEVERY RECORDED CARD'S QR DECODES TO THE DESTINATION THE REGISTRY RECORDS")
    # A card whose QR does not decode is a dead card, and it cannot be judged by
    # eye — the version this replaced looked like a perfectly good QR and was
    # ~18 modules across, which no QR version is. Decoded through the system
    # barcode detector, because that is the same class of reader a phone uses.
    #
    # THE EXPECTED URL USED TO BE A LITERAL HERE, FOR ONE CARD. It is now read
    # from network.json's cards block, for all of them, and the direction of that
    # dependency is the point. That block is what a scheduled sweep fetches to
    # prove each destination still resolves — but resolving proves only that the
    # URL someone TYPED into the record is alive. It says nothing about whether
    # the card in someone's pocket carries that URL. Decoding the shipped artifact
    # is the only thing that closes the loop, so the record cannot quietly drift
    # away from the ink while every online check stays green.
    import subprocess
    dec = REPO / "tools" / "qrdecode"
    rows = [r for r in json.loads((SRC / "site" / "network.json").read_text())
                          .get("cards", {}).get("destinations", [])
            if r.get("surface") == "qr" and r.get("artifact")]
    check("the registry records at least one card QR to check", bool(rows),
          "cards.destinations has no qr row carrying an artifact path")

    def decoded_urls(path: Path) -> list[str]:
        """Every URL the system detector finds in one image, exactly as printed.

        SUBSTRING MATCHING WAS THE BUG. The first draft asked `row_url in out`,
        and the founder card's recorded destination is the bare site root —
        which is a prefix of every other card's URL in this repo. Swap the
        founder back for the tierra back and the assertion still passed on
        tierra's ink. An exact comparison is the only one that can catch the
        swap this block exists to catch.
        """
        out = subprocess.run([str(dec), str(path)], capture_output=True, text=True).stdout
        return [ln.split(" -> ", 1)[1].strip() for ln in out.splitlines() if " -> " in ln]

    if not dec.is_file() and sys.platform == "darwin":
        # BUILD IT RATHER THAN FAIL THE CLONE. tools/qrdecode is gitignored — it is
        # a Mach-O binary, which does not belong in a repo — so it is absent from
        # EVERY fresh checkout, and making its absence a plain failure turned this
        # project's own front door red for every new contributor and agent, under a
        # headline that blamed the geometry pipeline. The source is right there and
        # the build is one command, so run it. If the build fails, that is a real
        # and accurately-named failure.
        r = subprocess.run(["swiftc", str(REPO / "tools" / "qrdecode.swift"), "-o", str(dec)],
                           capture_output=True, text=True)
        if not dec.is_file():
            print(f"  --    building the QR decoder failed: {(r.stderr or 'swiftc not found').strip()[:160]}")

    if not dec.is_file():
        # THIS BRANCH USED TO PRINT "This is NOT a pass" AND THEN EXIT 0, so
        # verify_contribution.sh printed a green tick over every card QR assertion
        # below — twenty of them today — and the words were unreachable from the
        # gate's own transcript. On macOS the decoder builds from source in this
        # repo, so reaching here means the build itself failed: a real failure.
        # Elsewhere it CANNOT exist (qrdecode.swift imports Vision and AppKit), so
        # the honest output is a named non-pass that does not accuse a Linux
        # contributor of breaking something — and the marker below is what the
        # caller greps so it cannot print a tick.
        if sys.platform == "darwin":
            check("the QR decoder builds (swiftc tools/qrdecode.swift -o tools/qrdecode)", False,
                  "it did not, so every card QR assertion below would silently not run")
        else:
            print("  QR-DECODE-DID-NOT-RUN  qrdecode needs macOS Vision/AppKit; no card QR was read on this platform")
            print("        This is NOT a pass — it is the absence of one.")
    else:
        # WHICH FILES GET CHECKED, AND THE ONE THIS DELIBERATELY DOES NOT.
        # A row names ONE artifact, but a card ships several: the trim and bleed
        # exports beside it, and the copy published under src/site/<slug>/ that
        # the website actually serves. Checking only the named file inherits, one
        # level down, exactly the blindness the cards block was built to remove —
        # so each row's siblings are checked against THAT ROW's url. Not against
        # "some url in the registry": that weaker rule passes when one card's back
        # is replaced by another card's back, which is the failure being hunted.
        #   src/web/templates/ is excluded from sibling expansion on purpose — two
        # different cards share that one directory, so co-location there does not
        # imply a common card, and a guessed grouping would assert something nobody
        # measured. Those files are counted in the coverage line instead.
        seen: set[Path] = set()
        for r in rows:
            # `artifact` is a string OR a list of strings, because a card's ink
            # ships from more than one path: the examples/ design AND the copy the
            # designer app serves out of src/web/cards/. Six such copies sat in no
            # row at all, so nothing asserted they still carried their own card's
            # destination — a regeneration could point one at another card and the
            # gate would not have looked.
            #   The alternative was six NEW rows, one per copy, which reaches the
            # same coverage number and is strictly worse: each row is checked only
            # against its own ink, so duplicating the url into a second row deletes
            # the cross-copy identity assertion. Measured on a seeded swap of two
            # cards' app-served backs — extra rows: 31/31 and 0 failures, fully
            # green over the swap; one row with both paths: 2 failures. Same number,
            # opposite property. So the copies go on the SAME row, and the url stays
            # written once per card.
            paths = r["artifact"] if isinstance(r["artifact"], list) else [r["artifact"]]
            named = [REPO / p for p in paths]
            art = named[0]
            label = f"{r['card']}/{paths[0].split('/')[-1]}"
            missing = [str(p.relative_to(REPO)) for p in named if not p.is_file()]
            if missing:
                check(f"{label} exists to test", False,
                      f"missing — the registry names {', '.join(missing)}, which is not here")
                continue
            group = list(named)
            # THE WHOLE CARD DIRECTORY, not just the folder the row points into.
            # A card's folder can hold designs/, assets/ and print/ (the founder
            # card holds all three; the others ship designs/ alone) — and print/ is
            # where the PDF that physically goes on the printer lives, which is the
            # one artifact a wrong QR reaches a human through. Scoping the group to
            # the row's own folder checked the design and skipped the thing that
            # gets printed.
            #   KNOWN LIMIT, stated rather than papered over: a sibling that has
            # LOST its QR entirely passes, because `elif found:` cannot tell it
            # from a card front that legitimately carries none, and no field
            # records which faces are supposed to have one.
            card_dir = next((a for a in art.parents if a.parent == REPO / "examples"), None)
            if card_dir is not None:
                group += sorted(p for p in card_dir.rglob("*")
                                if p != art and p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".pdf"))
            slug = [s for s in str(r.get("url") or "").split("/") if s][-1:] if r.get("url") else []
            if slug and not str(art).startswith(str(SRC / "site")):
                group += sorted(p for p in (SRC / "site" / slug[0]).glob("card-*")
                                if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
            for p in group:
                seen.add(p)
                found = decoded_urls(p)
                rel = p.relative_to(REPO)
                if r.get("url"):
                    # SET equality, not list equality: a tray sheet is multi-up, so
                    # tray_120x120_back-both.pdf legitimately decodes the SAME url
                    # twice. Requiring one hit failed a correct artifact. What must
                    # hold is that every QR on the sheet points at this card and at
                    # least one exists — which still catches the swap that motivated
                    # dropping substring matching, since another card's url differs.
                    good = bool(found) and set(found) == {r["url"]}
                    if p in named:
                        # Every NAMED path gets the strong assertion, not just the
                        # first: a named copy that has lost its QR entirely FAILS
                        # here, where a merely-inferred sibling falls to the `elif
                        # found:` branch below and cannot be told from a card front.
                        # Naming a copy is what buys it that, and it is the reason
                        # to name them rather than infer a fourth directory.
                        check(f"{r['card']}/{p.name} QR decodes to {r['url']}", good,
                              f"decoder said: {found or '(no barcode)'}")
                    elif found:
                        # A sibling with no QR is not a failure — a card front
                        # legitimately carries none. A sibling with the WRONG QR is.
                        check(f"{rel} carries {r['card']}'s destination", good,
                              f"same card, different ink: {sorted(set(found))}")
                else:
                    # A null url is a claim too — "this design carries no QR at all" —
                    # and it goes stale the moment someone adds one. Asserting the
                    # absence is what keeps the record honest in both directions.
                    check(f"{label} carries no QR, as the registry records", not found,
                          f"the registry records no destination here, but the decoder found: {found}")
        # COUNT IS NOT COVERAGE, so say the denominator out loud. Reported and not
        # failed: whether a bare QR asset or a shared template is a "card artifact"
        # is a call the registry has not made, and a gate must not invent it. What
        # it must not do is stay quiet — the version of this block that carried the
        # heading below and nothing else decoded eight artifacts and read, to anyone
        # skimming its output, as though it had checked every card.
        # src/web/cards/ IS IN THIS LIST BECAUSE IT WAS THE ONE MISSING. It holds
        # the card backs the designer app itself serves and prints — the artifact
        # closest to a real user — and leaving it out of the pool meant swapping two
        # of them was invisible to the check AND absent from the denominator the
        # line below prints. A coverage number whose blind spot is excluded from
        # its own denominator is the failure this line exists to name, committed by
        # the line itself.
        pool = sorted({p for base in ("examples", "src/site", "src/web/templates", "src/web/cards")
                       for p in (REPO / base).rglob("*")
                       if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".pdf")})
        bearing = [p for p in pool if decoded_urls(p)]
        missed = [str(p.relative_to(REPO)) for p in bearing if p not in seen]
        # NOW IT FAILS, AND THE REASON IT DIDN'T HAS EXPIRED. The paragraph above
        # declined to fail because "whether a bare QR asset or a shared template is
        # a card artifact is a call the registry has not made." That was true while
        # six files sat unbound. It is not true now: every QR-bearing file in the
        # pool is named by a row, so the registry HAS made the call for all of them,
        # and the next unbound file will be one somebody just added.
        #   Reporting-only was also self-erasing. The honest reading of "25/31" was
        # "six files nothing watches"; the moment it saturates, a printed 31/31
        # stops prompting anyone to ask, and quietly reads 31/32 the day an image
        # lands. A number with nothing behind it decays exactly when it looks best.
        #   What this does NOT mean, said out loud because "31/31" invites the
        # opposite reading: coverage counts BINDING, not correctness. A registry can
        # be fully bound and still record the wrong destination — the seeded-swap
        # control prints 31/31 alongside two failures. Correctness is the PASS lines
        # above; this line only says nothing is unwatched. And it is enforced only
        # where the decoder runs: qrdecode needs macOS Vision/AppKit, no CI workflow
        # invokes verify_contribution.sh, so on any other platform the branch above
        # prints QR-DECODE-DID-NOT-RUN and this assertion is never made at all.
        # THE NUMERATOR AND THE DENOMINATOR ARE THE SAME EXPRESSION. This headline
        # prints len(bearing) twice, so it reads "52/52" on the very run that FAILS
        # with ten unbound files listed underneath it — a line that says full
        # coverage on the run where coverage did not hold. It is the exact defect
        # the paragraph above warns about ("a number with nothing behind it decays
        # exactly when it looks best"), committed by the line that warns about it.
        # The bound count is len(bearing) - len(missed).
        #   Left standing rather than fixed in passing, because the number is not
        # what decides the outcome — `not missed` is — and a silent edit to the one
        # line a reader trusts most deserves its own change with its own check.
        # Whoever fixes it: seed one unbound QR file first and watch the numerator
        # move. A coverage number that has never been seen to go down has never
        # been shown to be a measurement.
        check(f"QR coverage: {len(bearing)}/{len(bearing)} QR-bearing shipped artifact(s) bound to a registry row",
              not missed,
              f"not bound, so nothing would notice if their destination changed: {', '.join(missed)}")

    print()
    if fails:
        print(f"FAILED — {len(fails)} check(s):")
        for f in fails:
            print(f"  - {f}")
        print("\nThe geometry is wrong BEFORE it leaves the app. Fix it here.")
        return 1
    print("Geometry is exact: every placement leaves the app at the size requested.")
    print("If a printed card is the wrong size, the cause is downstream —")
    print("CUPS, the driver, or scaling in the print dialog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
