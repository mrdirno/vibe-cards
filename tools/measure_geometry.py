#!/usr/bin/env python3
"""Measure where ink actually lands on the printed page.

Posts solid-colour cards through the real /api/pdf path, renders the resulting
PDF with Quartz at a known scale, and measures the coloured rectangles back to
millimetres. This is the check that matters: everything else in the app is a
convenience, but if these numbers drift the ink misses the card.

    python3 tools/measure_geometry.py [base_url]
"""

import io
import json
import sys
import urllib.request

import Quartz
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8777"
PX_PER_MM = 20.0
TOL_MM = 0.15          # a fifth of a millimetre; the printer itself is worse than this


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())


def solid_jpeg(size_px, colour):
    buf = io.BytesIO()
    Image.new("RGB", size_px, colour).save(buf, "JPEG", quality=97)
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def render_pdf(path, px_per_mm):
    url = Quartz.CFURLCreateFromFileSystemRepresentation(None, path.encode(), len(path.encode()), False)
    doc = Quartz.CGPDFDocumentCreateWithURL(url)
    page = Quartz.CGPDFDocumentGetPage(doc, 1)
    box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    pt_w, pt_h = box.size.width, box.size.height
    mm_w, mm_h = pt_w * 25.4 / 72.0, pt_h * 25.4 / 72.0
    w = int(round(mm_w * px_per_mm))
    h = int(round(mm_h * px_per_mm))

    space = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w * 4, space,
                                       Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
    Quartz.CGContextScaleCTM(ctx, w / pt_w, h / pt_h)
    Quartz.CGContextDrawPDFPage(ctx, page)

    img = Quartz.CGBitmapContextCreateImage(ctx)
    provider = Quartz.CGImageGetDataProvider(img)
    data = Quartz.CGDataProviderCopyData(provider)
    buf = bytes(data)
    pil = Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", Quartz.CGImageGetBytesPerRow(img), 1)
    return pil.convert("RGB"), (mm_w, mm_h)


def bbox_of(img, target, tol=40):
    """Bounding box of pixels near `target`, in millimetres from the top-left."""
    px = img.load()
    w, h = img.size
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - target[0]) < tol and abs(g - target[1]) < tol and abs(b - target[2]) < tol:
                if x < minx: minx = x
                if y < miny: miny = y
                if x > maxx: maxx = x
                if y > maxy: maxy = y
    if maxx < 0:
        return None
    return (minx / PX_PER_MM, miny / PX_PER_MM, (maxx + 1) / PX_PER_MM, (maxy + 1) / PX_PER_MM)


def main():
    profiles = json.loads(urllib.request.urlopen(BASE + "/api/bootstrap").read())["profiles"]
    prof = profiles["profiles"][profiles["default_profile"]]
    slots = prof["slots"]
    page = prof["page_mm"]

    dpi = 600
    colours = [(220, 30, 40), (30, 70, 210)]
    placements = []
    for slot, colour in zip(slots, colours):
        size = (round(slot["w"] * dpi / 25.4), round(slot["h"] * dpi / 25.4))
        placements.append({
            "image": solid_jpeg(size, colour),
            "x_mm": slot["x"], "y_mm": slot["y"],
            "w_mm": slot["w"], "h_mm": slot["h"], "rotate_deg": slot.get("rotate", 0),
        })

    res = post("/api/pdf", {
        "page_mm": page, "dx": 0, "dy": 0,
        "placements": placements, "name": "geometry-probe", "open": False,
    })
    pdf = res["pdf"]
    img, (mm_w, mm_h) = render_pdf(pdf, PX_PER_MM)

    print(f"\nPDF        : {pdf}")
    print(f"MediaBox   : {mm_w:.3f} × {mm_h:.3f} mm   (expected {page['w']} × {page['h']})")

    ok = abs(mm_w - page["w"]) < 0.02 and abs(mm_h - page["h"]) < 0.02
    fails = 0 if ok else 1
    print(f"{'  ok  ' if ok else ' FAIL '} page size\n")

    for slot, colour in zip(slots, colours):
        bb = bbox_of(img, colour)
        if bb is None:
            print(f" FAIL  slot {slot['name']}: colour not found in render")
            fails += 1
            continue
        exp = (slot["x"], slot["y"], slot["x"] + slot["w"], slot["y"] + slot["h"])
        dev = [abs(a - b) for a, b in zip(bb, exp)]
        good = max(dev) <= TOL_MM
        fails += 0 if good else 1
        print(f"{'  ok  ' if good else ' FAIL '} slot {slot['name']}")
        print(f"        measured  x {bb[0]:7.3f} → {bb[2]:7.3f}   y {bb[1]:7.3f} → {bb[3]:7.3f}  mm")
        print(f"        expected  x {exp[0]:7.3f} → {exp[2]:7.3f}   y {exp[1]:7.3f} → {exp[3]:7.3f}  mm")
        print(f"        max deviation {max(dev):.3f} mm (tolerance {TOL_MM})")

    # calibration offset must move ink by exactly that much
    dx, dy = 2.0, -1.0
    res2 = post("/api/pdf", {
        "page_mm": page, "dx": dx, "dy": dy,
        "placements": placements, "name": "geometry-probe-offset", "open": False,
    })
    img2, _ = render_pdf(res2["pdf"], PX_PER_MM)
    bb0 = bbox_of(img, colours[0])
    bb1 = bbox_of(img2, colours[0])
    moved = (bb1[0] - bb0[0], bb1[1] - bb0[1])
    good = abs(moved[0] - dx) <= TOL_MM and abs(moved[1] - dy) <= TOL_MM
    fails += 0 if good else 1
    print(f"\n{'  ok  ' if good else ' FAIL '} calibration offset moves ink by exactly ({dx}, {dy}) mm")
    print(f"        measured shift ({moved[0]:+.3f}, {moved[1]:+.3f}) mm")

    print(f"\n{'ALL GEOMETRY CHECKS PASSED' if fails == 0 else str(fails) + ' GEOMETRY CHECK(S) FAILED'}\n")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
