# KUNAI-360 card — KUNAI-001

The last listed project whose card existed only as a sentence.

```
front   the housing's own top view, drawn from the generator's constants
back    the URL in full, and a QR that decodes to exactly it
chip    a prose-grade row exists in the registry; no tag has ever been read back
```

`network.json`'s `shape` block names five parts every project has — repo, site, manifest,
wish, card. KUNAI-001 had a chip row derived from a sentence ("NEVER read back from the
tag", its own evidence field says) and no ink anywhere: no design files in this repo, no
QR row, nothing decodable. This is the ink. The chip row stays exactly as honest as it
was — writing a tag needs a tag on the reader, not a repo.

The QR does not print the redirector. KUNAI-001's chip prose claims
`persona500.com/c/KUNAI-001`, and that table answers 200 for slugs it has never heard of
by falling through to a different project's site — the collage card documents the trade.
What is printed here is `https://mrdirno.github.io/kunai-360/`, which resolves without a
lookup.

## Rebuild it, exactly

Run from the repo root. Every step is checkable, and step 5 is the one that matters.

```bash
# 1. the code — ONE generator, which verifies by decoding its own output
swift tools/make_qr.swift \
  --text "https://mrdirno.github.io/kunai-360/" \
  --out examples/kunai-card/assets/KUNAI-001_qr_on-white.png --ec M --px 2048

# 2. the mark — the housing's top view, from the product's own constants.
#    With the kunai-360 repo present, drift against the real generator is a failure:
python3 examples/kunai-card/tools/gen_mark.py \
  --verify-against ../kunai-360/generator/kunai_360_onex_v4.py \
  --into examples/kunai-card/designs/front.svg
#    (without that repo, drop the flag — the constants are embedded, each with the
#    generator line it came from)

# 3. the code as GEOMETRY, read back out of that PNG rather than re-encoded.
#    22 mm, not the collage card's 24: this symbol is 29 modules and qr_to_svg.py
#    reports quiet_needed 3.034 mm — 24 mm needed 3.31 and the 30 mm patch only has
#    3.0 to give; at 22 the margins are 4.0 and the module is 0.7586, still ~1.9x
#    the 0.4 mm print floor. The tool's report decided this, not taste.
python3 tools/qr_to_svg.py \
  --png examples/kunai-card/assets/KUNAI-001_qr_on-white.png \
  --x 55.6 --y 15.99 --size 22 \
  --into examples/kunai-card/designs/back.svg

# 4. rasterise at BLEED, then DERIVE trim by cropping 22 px per edge
cd examples/kunai-card/designs
for f in front back; do
  rsvg-convert -w 2066 -h 1319 -o ${f}_87.5x55.88mm_bleed_600dpi.png $f.svg
done
python3 -c "
from PIL import Image
for f in ('front','back'):
    b = Image.open(f'{f}_87.5x55.88mm_bleed_600dpi.png'); assert b.size == (2066,1319)
    b.crop((22,22,2044,1297)).save(f'{f}_85.6x53.98mm_600dpi.png')"

# 5. prove the ink says what the registry says it says
cd ../../..
./tools/qrdecode examples/kunai-card/designs/back_85.6x53.98mm_600dpi.png
./tools/qrdecode examples/kunai-card/designs/back_87.5x55.88mm_bleed_600dpi.png
./tools/qrdecode examples/kunai-card/assets/KUNAI-001_qr_on-white.png
```

All three decodes must print `https://mrdirno.github.io/kunai-360/` and nothing else.

One rasteriser note the collage card did not need: the type is Menlo (the first
installed name in the deployed page's own mono stack), and Menlo is wider than the
Helvetica the earlier cards used — the first render of this back ran the wish line
under the QR patch. Lines on this face wrap at ~26 characters. If you touch the copy,
re-render and look at the PNG, not the SVG.
