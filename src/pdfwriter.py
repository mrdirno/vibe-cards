#!/usr/bin/env python3
"""
pdfwriter.py — exact-geometry PDF emitter for Card Studio.

Its only job: put raster images at EXACT physical coordinates on an exact-size
page. Ink lands on real PVC cards based on this file, so every number here is
load-bearing.

Dependency policy
-----------------
Stdlib only for the JPEG path. PIL is imported LAZILY and ONLY for PNG decoding;
if PIL is absent, the PNG path raises a clear ImportError naming the JPEG
fallback rather than emitting a broken PDF.

Coordinate systems
------------------
Callers use SCREEN coordinates: origin at the page's TOP-LEFT, +x right,
+y DOWN, millimetres. PDF user space is the opposite: origin at the page's
BOTTOM-LEFT, +y UP, points (1 pt = 1/72 in).

    x_pt = x_mm * 72 / 25.4
    y_pt_bottom_of_rect = (page_h_mm - y_mm - h_mm) * 72 / 25.4
                          ^^^^^^^^^^^^^^^^^^^^^^^^
                          flip the axis, then step down past the rect's own
                          height because y_mm names the rect's TOP edge while
                          PDF wants its BOTTOM edge.

Rotation
--------
`rotate_deg` rotates the placed image CLOCKWISE as seen on the printed page
(same sense as CSS `transform: rotate(90deg)` and "rotate right" in image
tools), about the CENTRE of the placement rect. The image is first scaled to
fill w_mm x h_mm, then the whole placement is spun about that centre — so for
90/270 the on-page footprint becomes h_mm wide by w_mm tall, still centred on
the same point. Callers wanting the rotated art to stay inside the original
rect must swap w_mm/h_mm themselves.

Because PDF user space is y-up, a visually-clockwise rotation is a mathematical
NEGATIVE rotation there; the matrix below uses exact integer cos/sin (0, +/-1)
for the four legal angles, so no floating-point error enters the geometry.

Numeric precision
-----------------
Reals are emitted with 6 decimal places (trailing zeros stripped), i.e. a worst
case representation error of 5e-7 pt = 1.8e-7 mm — roughly 1/240 of a 600 dpi
device pixel (42 um). Six digits keeps us inside the PDF spec's conservative
real-precision guidance while being irrelevant at print scale.
"""

from __future__ import annotations

import hashlib
import time
import zlib
from io import BytesIO

__all__ = ["build_pdf", "PdfImageError", "mm_to_pt", "PT_PER_MM"]

MM_PER_IN = 25.4
PT_PER_IN = 72.0
PT_PER_MM = PT_PER_IN / MM_PER_IN  # 2.8346456692913385

_PIL_MISSING_MSG = (
    "PNG embedding requires Pillow (PIL), which is not importable in this "
    "interpreter. Either install Pillow (`python3 -m pip install Pillow`) or "
    "have the caller send the raster as a JPEG instead — pdfwriter's JPEG path "
    "is pure stdlib and needs no third-party module. Refusing to write a PDF "
    "with a missing or fabricated image."
)


class PdfImageError(ValueError):
    """An image cannot be embedded faithfully (wrong colour model, encoding, ...)."""


def mm_to_pt(mm: float) -> float:
    """Millimetres -> PDF points (1 pt = 1/72 inch)."""
    return mm * PT_PER_MM


# --------------------------------------------------------------------------
# low-level PDF token formatting
# --------------------------------------------------------------------------

def _fmt(v: float) -> str:
    """Format a number as a PDF real. No exponent notation (illegal in PDF)."""
    if v == int(v) and abs(v) < 1e9:
        return str(int(v))
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def _pdf_text_string(s: str) -> bytes:
    """Encode a text string. ASCII -> literal string; otherwise UTF-16BE + BOM."""
    try:
        raw = s.encode("ascii")
    except UnicodeEncodeError:
        raw = b"\xfe\xff" + s.encode("utf-16-be")
    esc = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + esc + b")"


def _pdf_date(ts: float) -> str:
    """PDF date string: D:YYYYMMDDHHmmSS+HH'mm'."""
    lt = time.localtime(ts)
    off = -(time.altzone if lt.tm_isdst and time.daylight else time.timezone)
    sign = "+" if off >= 0 else "-"
    off = abs(off)
    return (
        time.strftime("D:%Y%m%d%H%M%S", lt)
        + f"{sign}{off // 3600:02d}'{(off % 3600) // 60:02d}'"
    )


# --------------------------------------------------------------------------
# JPEG: parse just enough to describe the stream to the PDF reader
# --------------------------------------------------------------------------

# Frame markers that carry the image dimensions. Split by what DCTDecode can
# actually be trusted with downstream (printer RIPs, not just Preview).
_SOF_BASELINE = {0xC0, 0xC1}                    # baseline / extended sequential, Huffman
_SOF_PROGRESSIVE = {0xC2, 0xC6, 0xCA, 0xCE}     # progressive
_SOF_ARITHMETIC = {0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_SOF_LOSSLESS = {0xC3, 0xC5, 0xC7, 0xCB, 0xCF}  # lossless / differential
_SOF_ALL = _SOF_BASELINE | _SOF_PROGRESSIVE | _SOF_ARITHMETIC | _SOF_LOSSLESS
# Standalone markers: no length field follows them.
_STANDALONE = {0x01, 0xD8, 0xD9} | set(range(0xD0, 0xD8))


def _parse_jpeg(data: bytes) -> dict:
    """
    Scan JPEG markers for the SOF frame header and the Adobe APP14 transform.

    Returns {width, height, ncomp, precision, sof, adobe_transform}.
    Raises PdfImageError on anything we cannot embed with correct colour.
    """
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        raise PdfImageError("not a JPEG: missing SOI (FFD8) marker")

    i = 2
    adobe_transform = None
    n = len(data)
    while i < n:
        if data[i] != 0xFF:
            raise PdfImageError(f"corrupt JPEG: expected a marker at byte {i}")
        while i < n and data[i] == 0xFF:  # fill bytes are legal before a marker
            i += 1
        if i >= n:
            raise PdfImageError("corrupt JPEG: truncated marker")
        marker = data[i]
        i += 1

        if marker in _STANDALONE:
            if marker == 0xD9:
                break
            continue
        if i + 2 > n:
            raise PdfImageError("corrupt JPEG: truncated segment length")
        seglen = (data[i] << 8) | data[i + 1]
        if seglen < 2 or i + seglen > n:
            raise PdfImageError(f"corrupt JPEG: bad segment length {seglen} at byte {i}")
        seg = data[i + 2: i + seglen]

        if marker == 0xEE and seg[:5] == b"Adobe" and len(seg) >= 12:
            adobe_transform = seg[11]
        elif marker in _SOF_ALL:
            if len(seg) < 6:
                raise PdfImageError("corrupt JPEG: short SOF segment")
            precision = seg[0]
            height = (seg[1] << 8) | seg[2]
            width = (seg[3] << 8) | seg[4]
            ncomp = seg[5]
            return _validate_jpeg(marker, precision, width, height, ncomp, adobe_transform)
        elif marker == 0xDA:  # start of scan — SOF must have come first
            break
        i += seglen

    raise PdfImageError("corrupt JPEG: no SOF frame header found")


def _validate_jpeg(sof, precision, width, height, ncomp, adobe_transform) -> dict:
    """Reject every JPEG flavour that DCTDecode would render with wrong colour."""
    if sof in _SOF_LOSSLESS:
        raise PdfImageError(
            f"lossless/differential JPEG (SOF{sof - 0xC0}) cannot be embedded with "
            "/DCTDecode; re-encode as a baseline JPEG or send a PNG"
        )
    if sof in _SOF_ARITHMETIC:
        raise PdfImageError(
            f"arithmetic-coded JPEG (SOF{sof - 0xC0}) is not supported by /DCTDecode "
            "in most PDF consumers; re-encode as a baseline Huffman JPEG"
        )
    if sof in _SOF_PROGRESSIVE:
        raise PdfImageError(
            "progressive JPEG (SOF2) is outside the /DCTDecode baseline that print "
            "RIPs reliably decode; re-encode as a baseline JPEG "
            "(e.g. canvas.toBlob('image/jpeg') already emits baseline)"
        )
    if precision != 8:
        raise PdfImageError(
            f"{precision}-bit JPEG: /DCTDecode in PDF requires 8 bits per component"
        )
    if width <= 0 or height <= 0:
        raise PdfImageError(f"JPEG reports a degenerate size {width}x{height}")
    if ncomp == 4:
        kind = "YCCK" if adobe_transform == 2 else "CMYK"
        raise PdfImageError(
            f"4-component ({kind}) JPEG rejected: embedding it needs a /DeviceCMYK "
            "colour space and, for Adobe-written files, an inverted "
            "/Decode [1 0 1 0 1 0 1 0]; guessing either would print wrong colour on "
            "the card. Convert the image to RGB (or greyscale) and retry."
        )
    if ncomp not in (1, 3):
        raise PdfImageError(
            f"unsupported JPEG component count {ncomp}; only 1 (greyscale) and "
            "3 (YCbCr/RGB) can be embedded safely"
        )
    return {
        "width": width,
        "height": height,
        "ncomp": ncomp,
        "precision": precision,
        "sof": sof,
        # transform 0 on a 3-component file means the samples are RGB, not YCbCr.
        # The APP14 marker rides along inside the stream, so the reader gets this
        # right on its own; we only record it for diagnostics.
        "adobe_transform": adobe_transform,
    }


# --------------------------------------------------------------------------
# PNG: lossless re-encode as Flate (PIL only)
# --------------------------------------------------------------------------

def _decode_png(data: bytes) -> dict:
    """
    Decode a PNG to raw 8-bit RGB samples (plus an 8-bit alpha plane if the
    image actually uses transparency). Requires PIL.
    """
    try:
        from PIL import Image  # lazy: the JPEG path must stay dependency-free
    except ImportError as exc:  # pragma: no cover - exercised by the self-test
        raise ImportError(_PIL_MISSING_MSG) from exc

    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as exc:
        raise PdfImageError(f"PNG could not be decoded: {exc}") from exc
    if im.format != "PNG":
        raise PdfImageError(f"image declared format='png' but decoded as {im.format!r}")

    has_alpha = im.mode in ("RGBA", "LA", "PA", "La") or "transparency" in im.info
    alpha = None
    if has_alpha:
        rgba = im.convert("RGBA")
        a = rgba.getchannel("A")
        lo, _hi = a.getextrema()
        if lo < 255:  # fully-opaque alpha planes are pure overhead
            alpha = a.tobytes()
        rgb = rgba.convert("RGB").tobytes()  # drops A without compositing (SMask covers it)
    else:
        rgb = im.convert("RGB").tobytes()

    w, h = im.size
    if len(rgb) != w * h * 3:
        raise PdfImageError(f"PNG decode produced {len(rgb)} bytes, expected {w * h * 3}")
    return {"width": w, "height": h, "rgb": rgb, "alpha": alpha}


# --------------------------------------------------------------------------
# placement matrix
# --------------------------------------------------------------------------

# Exact cos/sin for the four legal angles, expressed in PDF (y-up) space for a
# rotation that reads CLOCKWISE on the printed page: theta_pdf = -rotate_deg.
_TRIG = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}


def _placement_matrix(x_mm, y_mm, w_mm, h_mm, page_h_mm, rotate_deg):
    """
    Build the PDF `cm` matrix [a b c d e f] that maps the image XObject's unit
    square onto the requested rect, rotated about that rect's centre.

    Composition (applied right-to-left to a unit-square point):
        T(cx,cy) . R(-rotate) . T(-w/2,-h/2) . S(w,h)
    """
    cos_t, sin_t = _TRIG[rotate_deg]
    w = mm_to_pt(w_mm)
    h = mm_to_pt(h_mm)
    # Rect centre in PDF space: x straight across, y flipped about the page.
    cx = mm_to_pt(x_mm + w_mm / 2.0)
    cy = mm_to_pt(page_h_mm - (y_mm + h_mm / 2.0))

    a = w * cos_t
    b = w * sin_t
    c = -h * sin_t
    d = h * cos_t
    e = cx - (w / 2.0) * cos_t + (h / 2.0) * sin_t
    f = cy - (w / 2.0) * sin_t - (h / 2.0) * cos_t
    return (a, b, c, d, e, f)


# --------------------------------------------------------------------------
# builder
# --------------------------------------------------------------------------

def _stream_obj(dict_body: bytes, payload: bytes) -> bytes:
    """Serialise `<< ...dict... /Length n >> stream ... endstream`."""
    return (
        b"<< " + dict_body + b" /Length " + str(len(payload)).encode("ascii") + b" >>\n"
        b"stream\n" + payload + b"\nendstream"
    )


def _image_objects(spec, index, objs):
    """
    Append the XObject(s) for one placement to `objs` and return its object
    number. `objs` is 0-indexed; object numbers are index+1.
    """
    fmt = str(spec.get("format", "")).lower()
    data = spec.get("data")
    if not isinstance(data, (bytes, bytearray)):
        raise PdfImageError(f"images[{index}]: 'data' must be bytes, got {type(data).__name__}")
    data = bytes(data)

    if fmt in ("jpeg", "jpg"):
        info = _parse_jpeg(data)
        cs = b"/DeviceRGB" if info["ncomp"] == 3 else b"/DeviceGray"
        body = _stream_obj(
            b"/Type /XObject /Subtype /Image"
            b" /Width " + str(info["width"]).encode()
            + b" /Height " + str(info["height"]).encode()
            + b" /ColorSpace " + cs
            + b" /BitsPerComponent 8 /Filter /DCTDecode",
            data,  # embedded byte-for-byte: no recompression, no generation loss
        )
        objs.append(body)
        return len(objs)

    if fmt == "png":
        info = _decode_png(data)
        smask_ref = b""
        if info["alpha"] is not None:
            objs.append(_stream_obj(
                b"/Type /XObject /Subtype /Image"
                b" /Width " + str(info["width"]).encode()
                + b" /Height " + str(info["height"]).encode()
                + b" /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode",
                zlib.compress(info["alpha"], 9),
            ))
            smask_ref = b" /SMask " + str(len(objs)).encode() + b" 0 R"
        objs.append(_stream_obj(
            b"/Type /XObject /Subtype /Image"
            b" /Width " + str(info["width"]).encode()
            + b" /Height " + str(info["height"]).encode()
            + b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode"
            + smask_ref,
            zlib.compress(info["rgb"], 9),
        ))
        return len(objs)

    raise PdfImageError(f"images[{index}]: format must be 'jpeg' or 'png', got {fmt!r}")


def build_pdf(out_path, page_w_mm, page_h_mm, images, *, title=None) -> str:
    """
    Write a single-page PDF of exactly page_w_mm x page_h_mm with `images`
    placed at exact physical coordinates. Returns out_path.

    images: list of dicts
        data        raw JPEG or PNG file bytes
        format      "jpeg" | "png"
        x_mm, y_mm  TOP-LEFT corner of the placement rect, from the page's TOP-LEFT
        w_mm, h_mm  placement rect size
        rotate_deg  0 | 90 | 180 | 270, clockwise about the rect centre (default 0)

    Images are drawn in list order (later entries paint over earlier ones).
    Placements may extend past the page edge; the reader clips them (bleed).
    """
    if page_w_mm <= 0 or page_h_mm <= 0:
        raise ValueError(f"page must be positive, got {page_w_mm}x{page_h_mm} mm")

    page_w_pt = mm_to_pt(page_w_mm)
    page_h_pt = mm_to_pt(page_h_mm)

    # Objects 1..4 are reserved for catalog / pages / page / contents so the
    # page tree reads naturally; images follow.
    objs: list = [None, None, None, None]
    xobject_entries: list[bytes] = []
    content = bytearray()

    for idx, spec in enumerate(images):
        for key in ("data", "format", "x_mm", "y_mm", "w_mm", "h_mm"):
            if key not in spec:
                raise PdfImageError(f"images[{idx}]: missing required key {key!r}")
        w_mm, h_mm = float(spec["w_mm"]), float(spec["h_mm"])
        if w_mm <= 0 or h_mm <= 0:
            raise PdfImageError(f"images[{idx}]: w_mm/h_mm must be positive, got {w_mm}x{h_mm}")
        rot = int(spec.get("rotate_deg", 0) or 0) % 360
        if rot not in _TRIG:
            raise PdfImageError(
                f"images[{idx}]: rotate_deg must be 0, 90, 180 or 270, got {spec.get('rotate_deg')!r}"
            )

        num = _image_objects(spec, idx, objs)
        name = f"/Im{idx}".encode("ascii")
        xobject_entries.append(name + b" " + str(num).encode() + b" 0 R")

        a, b, c, d, e, f = _placement_matrix(
            float(spec["x_mm"]), float(spec["y_mm"]), w_mm, h_mm, page_h_mm, rot
        )
        content += (
            b"q\n"
            + " ".join(_fmt(v) for v in (a, b, c, d, e, f)).encode("ascii")
            + b" cm\n" + name + b" Do\nQ\n"
        )

    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objs[2] = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
        + _fmt(page_w_pt).encode() + b" " + _fmt(page_h_pt).encode() + b"]"
        b" /Resources << /XObject << " + b" ".join(xobject_entries) + b" >>"
        b" /ProcSet [/PDF /ImageB /ImageC /ImageI] >>"
        b" /Contents 4 0 R >>"
    )
    objs[3] = _stream_obj(b"", bytes(content))

    info = b"/Producer (Card Studio pdfwriter) /CreationDate " \
        + _pdf_text_string(_pdf_date(time.time()))
    if title:
        info += b" /Title " + _pdf_text_string(str(title))
    objs.append(b"<< " + info + b" >>")
    info_num = len(objs)

    # ---- serialise, recording byte offsets for the xref table ----
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")  # binary comment: marks non-ASCII content
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(n).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"

    doc_id = hashlib.md5(bytes(out) + str(out_path).encode("utf-8", "replace")).hexdigest()
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"  # each entry is exactly 20 bytes, free head included
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (
        b"trailer\n<< /Size " + str(len(objs) + 1).encode()
        + b" /Root 1 0 R /Info " + str(info_num).encode() + b" 0 R"
        b" /ID [<" + doc_id.encode() + b"> <" + doc_id.encode() + b">] >>\n"
        b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    )

    # Cheap insurance against ever shipping a file that triggers a repair
    # prompt: every recorded offset must actually land on its object header.
    for n, off in enumerate(offsets, start=1):
        head = f"{n} 0 obj".encode("ascii")
        if bytes(out[off:off + len(head)]) != head:
            raise AssertionError(f"xref offset {off} does not point at object {n}")

    with open(out_path, "wb") as fh:
        fh.write(out)
    return out_path


# ==========================================================================
# self-test — builds real PDFs, rasterises them, and MEASURES the result in
# pixels. Run: python3 pdfwriter.py
#
# Two rasterisers are used deliberately:
#   qlmanage  (macOS built-in, always present) — proves the file is valid and
#             renders, and bounds the geometry to ~0.5 mm. Its thumbnail
#             pipeline draws embedded rasters ~0.3% oversized; that error is
#             CONSTANT IN MM across a 4x resolution sweep (8.3 -> 33.3 px/mm),
#             so it is the instrument's error, not the PDF's.
#   pdftoppm  (poppler; dev machine only, NOT a runtime dependency) — the
#             precision oracle. Its residual HALVES as resolution doubles,
#             i.e. it is pure 1-pixel quantisation and the true error is 0.
# Skipping poppler is allowed; skipping qlmanage is not.
#
# Edge convention: a measured edge is the index of the first pixel of the new
# colour class, so the true edge lies within 1 px of it. Tolerances include
# that quantisation term explicitly.
# ==========================================================================

_TEST_DIR = ("/private/tmp/claude-501/-Volumes-dual--vault/"
             "3c441f21-9287-4c94-8dc2-35ae9290c7c7/scratchpad/pdftest")
_POPPLER = "/opt/homebrew/bin/pdftoppm"

# Page + card geometry under test (Canon TS702a disc tray: 120x120 mm, 2x CR-80).
PAGE = 120.0
CARD_W, CARD_H = 85.60, 53.98
CARD_X = round((PAGE - CARD_W) / 2.0, 2)   # 17.20 (rounded only to keep the log readable)
CARD_A_Y = 4.00
CARD_B_Y = PAGE - CARD_H - 4.00         # 62.02

# Marker centres inside a card, normalised (u across width, v down from top).
# Two markers at non-symmetric spots pin down all 8 dihedral orientations, so
# a rotation error AND a mirror error are both detectable.
MARK_YELLOW = (0.12, 0.18)
MARK_CYAN = (0.85, 0.30)
COL_A = (200, 32, 48)      # crimson card -> JPEG / DCTDecode
COL_B = (24, 148, 72)      # green card   -> PNG  / FlateDecode
COL_YELLOW = (255, 225, 0)
COL_CYAN = (0, 190, 220)


def _make_card(fill):
    """Render one 600 dpi test card: 1 mm black border + two asymmetric markers."""
    from PIL import Image, ImageDraw
    px = lambda mm: int(round(mm / 25.4 * 600))
    w, h = px(CARD_W), px(CARD_H)
    im = Image.new("RGB", (w, h), fill)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=(0, 0, 0), width=px(1.0))
    for (u, v), col, side in ((MARK_YELLOW, COL_YELLOW, 8.0), (MARK_CYAN, COL_CYAN, 6.0)):
        s = px(side) // 2
        cx, cy = int(round(u * w)), int(round(v * h))
        d.rectangle([cx - s, cy - s, cx + s, cy + s], fill=col)
    return im


def _encode(im, fmt):
    buf = BytesIO()
    if fmt == "jpeg":
        im.save(buf, "JPEG", quality=95, subsampling=0, progressive=False)
    else:
        im.save(buf, "PNG")
    return buf.getvalue()


# ---- mask helpers: PIL C ops only, no per-pixel Python over full rasters ----

def _mask_ink(img, white=235):
    """Mask of pixels that are NOT near-white (i.e. ink)."""
    from PIL import ImageChops
    ch = [c.point(lambda v: 255 if v <= white else 0) for c in img.split()[:3]]
    return ImageChops.lighter(ImageChops.lighter(ch[0], ch[1]), ch[2])   # OR


def _mask_colour(img, col, tol=70):
    """Mask of pixels within `tol` of `col` on every channel."""
    from PIL import Image, ImageChops
    diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, col))
    ch = [c.point(lambda v: 255 if v <= tol else 0) for c in diff.split()]
    return ImageChops.darker(ImageChops.darker(ch[0], ch[1]), ch[2])     # AND


def _bbox_in(mask, window):
    """
    getbbox() inside `window`, returned in whole-image pixel coords as
    (x0, y0, x1, y1) with x1/y1 EXCLUSIVE — i.e. x0 is the first ink pixel and
    x1 is the first pixel past the ink, matching the edge convention above.

    Raises if the box touches the window border: that means the window clipped
    the feature and the number would be a measurement artefact, not geometry.
    (This exact failure produced a bogus '-4.000 mm' reading during bring-up.)
    """
    bb = mask.crop(window).getbbox()
    if bb is None:
        raise AssertionError(f"no ink found in window {window}")
    x0, y0, x1, y1 = bb[0] + window[0], bb[1] + window[1], bb[2] + window[0], bb[3] + window[1]
    if x0 <= window[0] or y0 <= window[1] or x1 >= window[2] or y1 >= window[3]:
        raise AssertionError(
            f"feature bbox {(x0, y0, x1, y1)} touches window {window}: measurement clipped"
        )
    return x0, y0, x1, y1


def _centroid(mask):
    """
    Centroid of a mask, in pixels, as (cx, cy, n). Loops only inside the bbox.
    A centroid is used rather than the bbox centre because it averages away the
    soft, resampled edge of a marker instead of latching onto one stray pixel.
    """
    bb = mask.getbbox()
    if bb is None:
        return None, None, 0
    px = mask.load()
    sx = sy = n = 0
    for y in range(bb[1], bb[3]):
        for x in range(bb[0], bb[2]):
            if px[x, y]:
                sx += x; sy += y; n += 1
    return (sx / n, sy / n, n) if n else (None, None, 0)


# ---- rasterisers -----------------------------------------------------------

def _qlmanage(pdf_path, px_per_mm):
    """macOS built-in. Returns (RGB image, px_per_mm, thumb path)."""
    import glob, os, subprocess
    from PIL import Image
    size = int(round(PAGE * px_per_mm))
    outdir = os.path.join(_TEST_DIR, "thumbs")
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.basename(pdf_path)
    for old in glob.glob(os.path.join(outdir, stem + "*")):
        os.remove(old)
    r = subprocess.run(["/usr/bin/qlmanage", "-t", "-s", str(size), "-o", outdir, pdf_path],
                       capture_output=True, text=True)
    hits = sorted(glob.glob(os.path.join(outdir, stem + "*.png")))
    if not hits:
        raise AssertionError(f"qlmanage produced no thumbnail (PDF unreadable?)\n"
                             f"stdout={r.stdout}\nstderr={r.stderr}")
    img = Image.open(hits[0])
    if img.size != (size, size):
        raise AssertionError(f"thumbnail is {img.size}, expected {(size, size)}")
    # Verified during bring-up with a full-page calibration image: qlmanage maps
    # the page onto the whole thumbnail. Re-assert it so a future macOS that adds
    # a shadow/border fails loudly instead of silently shifting every measurement.
    if img.mode == "RGBA":
        a = img.getchannel("A")
        if a.getextrema()[0] < 255:
            box = a.point(lambda v: 255 if v > 8 else 0).getbbox()
            if box != (0, 0, size, size):
                raise AssertionError(f"thumbnail page box {box} != full image; "
                                     "qlmanage now pads/decorates the page")
    return img.convert("RGB"), px_per_mm, hits[0]


def _poppler(pdf_path, px_per_mm):
    """Independent precision oracle; returns None when poppler is absent."""
    import os, subprocess
    from PIL import Image
    if not os.path.exists(_POPPLER):
        return None
    dpi = px_per_mm * 25.4
    if abs(dpi - round(dpi)) > 1e-9:
        raise ValueError(f"px_per_mm {px_per_mm} does not map to an integer dpi")
    stem = os.path.join(_TEST_DIR, "pop_" + os.path.basename(pdf_path)[:-4])
    subprocess.run([_POPPLER, "-r", str(int(round(dpi))), "-png", "-singlefile",
                    pdf_path, stem], capture_output=True, check=True)
    img = Image.open(stem + ".png")
    exp = int(round(PAGE * px_per_mm))
    if img.size != (exp, exp):
        raise AssertionError(f"poppler raster {img.size}, expected {(exp, exp)}")
    return img.convert("RGB"), px_per_mm, stem + ".png"


def _rotate_pt(px_mm, py_mm, rect, deg):
    """Where a card-local point lands after rotating the placement CW about its centre."""
    x, y, w, h = rect
    cx, cy = x + w / 2.0, y + h / 2.0
    dx, dy = px_mm - cx, py_mm - cy
    if deg == 0:   return (cx + dx, cy + dy)
    if deg == 90:  return (cx - dy, cy + dx)   # screen y is DOWN: right -> down is CW
    if deg == 180: return (cx - dx, cy - dy)
    return (cx + dy, cy - dx)                  # 270


def _selftest():
    import os, sys
    # The SELF-TEST needs Pillow and the app does not. Every runtime use of PIL in
    # this file is guarded (HAS_PIL) with a working fallback; this harness renders
    # 600 dpi test cards and measures the PDF back, which is Pillow end to end.
    # Said here, once, instead of an ImportError halfway through section [1] —
    # and it exits 2 (skipped), never 0, so a machine without Pillow cannot read
    # "no failures" off a test that did not run.
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("pdfwriter self-test SKIPPED: it renders and measures test cards with Pillow "
              "(pip install pillow). The app itself runs without it.")
        return 2
    os.makedirs(_TEST_DIR, exist_ok=True)
    fails = []
    worst = {}

    def check(tag, name, measured, expected, tol):
        d = measured - expected
        ok = abs(d) <= tol
        worst[tag] = max(worst.get(tag, 0.0), abs(d))
        print(f"      {'PASS' if ok else 'FAIL'}  {name:<26} measured {measured:8.3f} mm  "
              f"expected {expected:8.3f}  delta {d:+6.3f}  (tol {tol:.2f})")
        if not ok:
            fails.append(f"{tag}:{name}")

    print("=" * 92)
    print("Card Studio pdfwriter self-test")
    print("=" * 92)

    card_a = _encode(_make_card(COL_A), "jpeg")
    card_b = _encode(_make_card(COL_B), "png")
    print(f"[1] test rasters @600 dpi, {CARD_W}x{CARD_H} mm: "
          f"card A JPEG {len(card_a)} B (DCTDecode), card B PNG {len(card_b)} B (FlateDecode)")

    # ---- geometry.pdf ---------------------------------------------------
    geom = os.path.join(_TEST_DIR, "geometry.pdf")
    build_pdf(geom, PAGE, PAGE, [
        {"data": card_a, "format": "jpeg", "x_mm": CARD_X, "y_mm": CARD_A_Y,
         "w_mm": CARD_W, "h_mm": CARD_H},
        {"data": card_b, "format": "png", "x_mm": CARD_X, "y_mm": CARD_B_Y,
         "w_mm": CARD_W, "h_mm": CARD_H},
    ], title="Card Studio geometry proof")
    raw = open(geom, "rb").read()
    print(f"[2] wrote {geom} ({len(raw)} bytes)")

    # structural proof: re-parse our own xref from the bytes and follow it
    xref_pos = int(raw[raw.rindex(b"startxref"):].split(b"\n")[1])
    head = raw[xref_pos:xref_pos + 40].split(b"\n")
    count = int(head[1].split()[1])
    ents = raw[xref_pos + len(head[0]) + len(head[1]) + 2:][:20 * count]
    bad = []
    for n in range(1, count):
        e = ents[20 * n:20 * n + 20]
        if len(e) != 20 or e[17:20] != b"n \n":
            bad.append((n, "malformed entry"))
        elif not raw[int(e[:10]):].startswith(f"{n} 0 obj".encode()):
            bad.append((n, int(e[:10])))
    mb = raw[raw.index(b"/MediaBox"):].split(b"]")[0] + b"]"
    exp_mb = f"/MediaBox [0 0 {_fmt(mm_to_pt(PAGE))} {_fmt(mm_to_pt(PAGE))}]"
    print(f"    xref: {count - 1} objects, 20-byte entries, "
          f"{'ALL offsets resolve to their object header' if not bad else f'BROKEN {bad}'}")
    print(f"    {mb.decode()}   expected {exp_mb}   "
          f"({'match' if mb.decode() == exp_mb else 'MISMATCH'})")
    print(f"    startxref -> {xref_pos}, file ends with %%EOF: {raw[-6:] == b'%%EOF' + bytes([10])}")
    if bad:
        fails.append("xref offsets")
    if mb.decode() != exp_mb:
        fails.append("MediaBox")
    if raw[-6:] != b"%%EOF\n":
        fails.append("trailer EOF")

    # ---- measure placement with both rasterisers -------------------------
    print("[3] placement geometry")
    for rname, raster, tol in (("qlmanage", _qlmanage(geom, 2000 / PAGE), 0.50),
                               ("pdftoppm", _poppler(geom, 20.0), 0.10)):
        if raster is None:
            print(f"  -- {rname}: NOT INSTALLED, skipped (qlmanage result stands alone)")
            continue
        img, ppm, path = raster
        print(f"  -- {rname}  {img.size[0]}x{img.size[1]} px  ({ppm:.4f} px/mm)  "
              f"tol {tol} mm  [{os.path.basename(path)}]")
        ink = _mask_ink(img)
        for label, colour, cy_mm in (("A jpeg", COL_A, CARD_A_Y), ("B png", COL_B, CARD_B_Y)):
            # Window = expected rect +/- 1.5 mm. Smaller than the 4.04 mm inter-card
            # gap, so the neighbouring card can never leak in; _bbox_in raises if
            # the true edge falls outside anyway.
            pad = 1.5
            win = tuple(int(round(v * ppm)) for v in
                        (CARD_X - pad, cy_mm - pad, CARD_X + CARD_W + pad, cy_mm + CARD_H + pad))
            x0, y0, x1, y1 = _bbox_in(ink, win)   # outer edge of the 1 mm black border
            print(f"    card {label}: border bbox px ({x0},{y0})-({x1},{y1})")
            check(rname, f"{label} left",   x0 / ppm, CARD_X,          tol)
            check(rname, f"{label} top",    y0 / ppm, cy_mm,           tol)
            check(rname, f"{label} right",  x1 / ppm, CARD_X + CARD_W, tol)
            check(rname, f"{label} bottom", y1 / ppm, cy_mm + CARD_H,  tol)
            n = _mask_colour(img.crop(win), colour).getbbox()
            ok = n is not None
            print(f"      {'PASS' if ok else 'FAIL'}  fill colour {colour} found in this rect "
                  f"(guards against swapped placements)")
            if not ok:
                fails.append(f"{rname}:{label} fill")

    # ---- rotation -------------------------------------------------------
    # Centre the card so the 90/270 footprint (h x w) still fits on the page.
    rect = (CARD_X, round((PAGE - CARD_H) / 2.0, 2), CARD_W, CARD_H)
    print(f"[4] rotation — single card at rect {rect} mm; rotate_deg is CLOCKWISE on the page")
    for deg in (0, 90, 180, 270):
        p = os.path.join(_TEST_DIR, f"rot{deg}.pdf")
        build_pdf(p, PAGE, PAGE, [{"data": card_a, "format": "jpeg", "x_mm": rect[0],
                                   "y_mm": rect[1], "w_mm": rect[2], "h_mm": rect[3],
                                   "rotate_deg": deg}], title=f"rotate {deg}")
        for rname, raster, tol in (("qlmanage", _qlmanage(p, 10.0), 0.50),
                                   ("pdftoppm", _poppler(p, 10.0), 0.15)):
            if raster is None:
                continue
            img, ppm, _ = raster
            # Footprint check: 90/270 must swap the on-page width and height.
            bb = _mask_ink(img).getbbox()
            fw, fh = (bb[2] - bb[0]) / ppm, (bb[3] - bb[1]) / ppm
            ew, eh = (CARD_W, CARD_H) if deg in (0, 180) else (CARD_H, CARD_W)
            print(f"  rotate_deg={deg:3d} [{rname}] footprint {fw:.2f} x {fh:.2f} mm "
                  f"(expected {ew} x {eh})")
            check(rname, f"{deg}deg footprint w", fw, ew, tol)
            check(rname, f"{deg}deg footprint h", fh, eh, tol)
            for mname, mcol, (u, v) in (("yellow", COL_YELLOW, MARK_YELLOW),
                                        ("cyan", COL_CYAN, MARK_CYAN)):
                ex, ey = _rotate_pt(rect[0] + u * rect[2], rect[1] + v * rect[3], rect, deg)
                cx, cy, n = _centroid(_mask_colour(img, mcol))
                if n < 50:
                    fails.append(f"{rname}:{deg} {mname} missing")
                    print(f"      FAIL  {mname} marker not found ({n} px)")
                    continue
                check(rname, f"{deg}deg {mname} x", cx / ppm, ex, tol)
                check(rname, f"{deg}deg {mname} y", cy / ppm, ey, tol)

    # ---- error / edge paths ---------------------------------------------
    print("[5] error and edge paths")
    from PIL import Image as _I

    def expect_raise(name, fn, exc, needle):
        try:
            fn()
        except exc as e:
            ok = needle in str(e)
            print(f"    {'PASS' if ok else 'FAIL'}  {name}: {str(e)[:66]}...")
            if not ok:
                fails.append(name)
            return
        except Exception as e:
            print(f"    FAIL  {name}: raised {type(e).__name__} instead of {exc.__name__}: {e}")
        else:
            print(f"    FAIL  {name}: no exception raised")
        fails.append(name)

    b = BytesIO(); _I.new("CMYK", (40, 30), (0, 0, 0, 200)).save(b, "JPEG")
    expect_raise("CMYK JPEG rejected", lambda: _parse_jpeg(b.getvalue()),
                 PdfImageError, "DeviceCMYK")
    b2 = BytesIO(); _I.new("RGB", (40, 30), (9, 9, 9)).save(b2, "JPEG", progressive=True)
    expect_raise("progressive JPEG rejected", lambda: _parse_jpeg(b2.getvalue()),
                 PdfImageError, "baseline")
    expect_raise("truncated JPEG rejected", lambda: _parse_jpeg(b"\xff\xd8\xff"),
                 PdfImageError, "JPEG")
    expect_raise("bad rotate_deg rejected",
                 lambda: build_pdf(os.path.join(_TEST_DIR, "bad.pdf"), 50, 50,
                                   [{"data": card_a, "format": "jpeg", "x_mm": 0, "y_mm": 0,
                                     "w_mm": 10, "h_mm": 10, "rotate_deg": 45}]),
                 PdfImageError, "rotate_deg")

    g = BytesIO(); _I.new("L", (40, 30), 128).save(g, "JPEG")
    build_pdf(os.path.join(_TEST_DIR, "grey.pdf"), 50, 50,
              [{"data": g.getvalue(), "format": "jpeg", "x_mm": 5, "y_mm": 5,
                "w_mm": 40, "h_mm": 30}])
    ok = b"/DeviceGray" in open(os.path.join(_TEST_DIR, "grey.pdf"), "rb").read()
    print(f"    {'PASS' if ok else 'FAIL'}  1-component JPEG embedded as /DeviceGray")
    fails.extend([] if ok else ["greyscale JPEG"])

    a = BytesIO(); _I.new("RGBA", (40, 30), (255, 0, 0, 128)).save(a, "PNG")
    build_pdf(os.path.join(_TEST_DIR, "alpha.pdf"), 50, 50,
              [{"data": a.getvalue(), "format": "png", "x_mm": 5, "y_mm": 5,
                "w_mm": 40, "h_mm": 30}])
    ok = b"/SMask" in open(os.path.join(_TEST_DIR, "alpha.pdf"), "rb").read()
    print(f"    {'PASS' if ok else 'FAIL'}  transparent PNG carries an /SMask")
    fails.extend([] if ok else ["PNG alpha"])

    # PIL-absent PNG path: block the import for real, then read the message.
    class _Block:
        def find_spec(self, name, path=None, target=None):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("blocked for test")
    saved = {k: v for k, v in sys.modules.items() if k == "PIL" or k.startswith("PIL.")}
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, _Block())
    try:
        expect_raise("PIL-absent PNG raises actionable ImportError",
                     lambda: _decode_png(b"\x89PNG\r\n\x1a\n"), ImportError, "JPEG")
    finally:
        sys.meta_path.pop(0)
        sys.modules.update(saved)

    print("=" * 92)
    for tag, w in sorted(worst.items()):
        print(f"worst absolute error, {tag:<9}: {w:.3f} mm")
    print(f"RESULT: {'ALL CHECKS PASSED' if not fails else 'FAILURES -> ' + ', '.join(fails)}")
    print("=" * 92)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
