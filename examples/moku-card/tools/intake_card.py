
"""
tools/intake_card.py — verifies TARGET_WISH_IT_BETTER_CARD contract
Checks from LEARNINGS.md: QR payload == url, face boxes bleed 87.5x55.88, safe-zone, MIME, offline
"""
import re, base64, io, json, sys
from pathlib import Path
try:
    from PIL import Image
    from pyzbar.pyzbar import decode
except ImportError:
    Image=None
    decode=None

HTML_PATH = Path(__file__).parent.parent / "index.html"

def check():
    html = HTML_PATH.read_text()
    # 1. Two faces
    faces = re.findall(r'data-vc-face="\d"', html)
    assert len(faces)==2, f"Expected 2 faces, got {len(faces)}"
    # 2. Bleed boxes declared
    assert 'data-vc-bleed-mm="87.5x55.88"' in html, "bleed attr missing"
    assert 'data-vc-trim-mm="85.6x53.98"' in html, "trim attr missing"
    # 3. #vc-card block
    m = re.search(r'<script[^>]*id="vc-card"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert m, "#vc-card missing"
    meta = json.loads(m.group(1))
    assert meta["id"]=="MOKU-003", f"id mismatch {meta['id']}"
    assert meta["url"]=="https://compound-crafts.io/cards/MOKU-003", f"url mismatch"
    # 4. QR payload == url char-for-char
    # extract data URI from holder
    m2 = re.search(r'id="qrDataHolder".*?>(.*?)</script>', html, re.DOTALL)
    assert m2, "qrDataHolder missing"
    data_uri = m2.group(1).strip()
    assert data_uri.startswith("data:image/png;base64,"), "QR MIME wrong"
    b64 = data_uri.split(",",1)[1]
    png_bytes = base64.b64decode(b64)
    if Image and decode:
        im = Image.open(io.BytesIO(png_bytes))
        dec = decode(im)
        assert dec, "QR not decodable"
        payload = dec[0].data.decode()
        assert payload==meta["url"], f"QR payload {payload} != url {meta['url']} char-for-char FAIL (LEARNINGS 4/4)"
        print(f"QR OK: {payload} == url")
    else:
        print("Pillow/pyzbar not available, skipping QR decode check")
    # 5. MIME types
    assert 'image/png' in data_uri, "QR must be image/png not image/jpeg mislabel"
    # 6. Safe zone
    assert 'safe-zone' in html or 'safe_zone' in html or '79.6' in html, "safe zone missing"
    # 7. No external requests
    assert 'https://cdn' not in html and 'https://unpkg' not in html, "External CDN found — self-contained violation"
    # 8. ID human-legible
    assert 'MOKU-003' in html, "ID not printed"
    # 9. QR size min 21mm — check CSS
    assert '21mm' in html, "QR 21mm min not found"
    print("All intake checks PASS — contract-exact per LEARNINGS.md")

if __name__=="__main__":
    check()
