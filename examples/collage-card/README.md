# Collage Studio card — COLLAGE-001

The last listed project that had no card.

```
front   a partition the product itself would produce, and the seed that makes it
back    the URL in full, and a QR that decodes to exactly it
chip    not written yet — no tag has been read back, so no chip row exists
```

`network.json`'s `shape` block names five parts every project has — repo, site, manifest,
wish, card. COLLAGE-001 had four. It had a `redirector` row, and the cards block's own
`_surfaces` note says a redirector is a destination that *exists*, not evidence that any
card carries it. This is the card. With it, every listed project has one.

## Rebuild it, exactly

Run from the repo root. Every step is checkable, and step 5 is the one that matters.

```bash
# 1. the code — ONE generator, which verifies by decoding its own output
swift tools/make_qr.swift \
  --text "https://mrdirno.github.io/nested-resonance-memory-archive/collage/" \
  --out examples/collage-card/assets/COLLAGE-001_qr_on-white.png --ec M --px 2048

# 2. the mark — a real partition, from the seed printed on the card
python3 examples/collage-card/tools/gen_mark.py \
  --x 51.6 --y 11.99 --w 30 --h 30 --seed 20260814 --depth 6 \
  --into examples/collage-card/designs/front.svg

# 3. the code as GEOMETRY, read back out of that PNG rather than re-encoded
python3 tools/qr_to_svg.py \
  --png examples/collage-card/assets/COLLAGE-001_qr_on-white.png \
  --x 54.6 --y 14.99 --size 24 \
  --into examples/collage-card/designs/back.svg

# 4. rasterise at BLEED, then DERIVE trim by cropping 22 px per edge
cd examples/collage-card/designs
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
./tools/qrdecode examples/collage-card/designs/back_85.6x53.98mm_600dpi.png
python3 tools/verify_geometry.py | grep -i collage
```

Step 4 is the only step with no gate behind it, so it carries the trap: **render at bleed
and crop down, never the reverse.** 87.5 × 55.88 mm converted independently at 600 dpi
gives 2066 × 1320, and an odd 45-px difference cannot centre a 1275-px trim box.

## The mark is an output, not a logo

Collage Studio's whole mechanic is that a composition is a partition of a canvas that
re-rolls from a seed. Drawing a logo for it would have invented a second identity for a
product that already has one, so the mark is an actual partition, and the seed that
produced it is printed underneath. `gen_mark.py` uses **mulberry32** — the same PRNG the
deployed bundle ships — so the seed reproduces the cells rather than gesturing at them.

mulberry32 is by Tommy Ettinger and is public domain. It is attributed in `gen_mark.py`
because the shipped bundle does not attribute it, and that omission is recorded in this
network's own registry entry for COLLAGE-001. Reproducing an omission silently while
citing it publicly is the cheapest kind of hypocrisy.

The mark occupies exactly the rectangle the QR occupies on the back. Turn the card over
and the partition becomes the code.

## Four things that cost a render each

**XML comments cannot contain `--`.** The AV card documents this trap and it still caught
this file on its first render: a comment explaining that the palette comes from the CSS
custom properties `--void` and `--surface-0..4` is a parse error, and a parse error means
the face does not render *at all*. The property names are spelled out in words instead.

**Nothing measures a glyph against a rectangle.** Both faces shipped their first render
with copy running into the mark and into the QR patch. Build, splice and decode were all
green — the collision is invisible to every gate in this repo, because no gate compares
text extents to anything. It was caught by opening the rendered PNG. Read the artifact.

**Tone by recursion depth is not tone.** The mark's first version coloured cells by their
depth, which put nearly all of them in the two darkest surfaces on a near-black ground. It
read as texture on screen and would have printed as a muddy block on PVC. The product
crops *photographs* into these cells, so the mark has to carry a photograph's range.

**`--size` is the dark grid, not the patch.** `qr_to_svg.py` bounds the dark modules, so
the quiet zone is *not* in that number — it is the white rectangle underneath, drawn by
the design. Here: 2.595 mm needed, 3.0 given.

## What the numbers are, and how they were measured

| | |
|---|---|
| Trim / bleed | 85.6 × 53.98 mm · 87.5 × 55.88 mm (2022 × 1275 · 2066 × 1319 px) |
| URL | 66 bytes → QR version 5, 37 modules, EC M |
| Code | 24 mm → 0.649 mm per module, against a 0.4 mm print floor |
| Patch | 30 mm white, 3.0 mm of quiet on every side |
| Mark | 44 cells, smallest edge 1.635 mm, floor 1.6 mm |
| Ink clearance | every glyph ≥ 4 mm inside trim and ≥ 4 mm clear of the patch |
| Decode floor | **190 px** |

The decode floor is the narrowest capture *of the whole card* that still reads through
`tools/qrdecode`, stepping down 10 px at a time. Two controls ran in the same command:
`examples/av-toolkit-card` floors at 180 px, and `examples/founder-card` at 270 px — which
independently confirms that card's README, since it records failing at 260. Four more
modules cost 10 px against the AV card, despite 2 mm more code.

## Palette and name

Neither is chosen here.

Every colour is read out of the product's own **deployed** stylesheet,
`collage/assets/index-59fbad44.css`. Deployed and not the repo copy on purpose: the live
page loads `index-59fbad44.css` while the repo tree at HEAD carries `index-7caf51d4.css`,
so the two are not the same bytes, and only one of them is what a holder's browser opens.

The card says **Collage Studio** because `collage/credits.json` — a file the maintainer
serves publicly — opens *"Collage Studio — Wall of Wishes"*, and the source lives at
`tools/collage-studio/`. The bundle's `<title>` and PWA manifest both say *Smart Crop
GenArt Studio*, and the string "Collage Studio" appears **zero** times in the shipped JS.
Both names are real; the maintainer's own voice wins the ink, because a card is permanent
and a build title is not.

## Why nothing countable is printed

The wall of wishes grows and the tool grows. Ink is as permanent as a chip, so a number
set in it starts decaying the day it dries.

For the same reason the URL is printed unshortened rather than as a `persona500.com/c/`
slug: that table answers 200 for slugs it has never heard of by falling through to a
different project's site, so a card carrying an unmapped slug looks perfectly healthy to
every check that reads a status code and lands its holder on the wrong page. What is
printed here resolves without a lookup.

## Before printing

Read `docs/PRINT_GEOMETRY.md`, and do not let the print dialog fit-to-page — it is on by
default in most drivers and it is the one setting that ruins a card. Printing is
irreversible; the rehearsal on plain paper costs nothing.

If a chip is ever written for this card, write the **same URL** the QR carries, then
record a `chip` row in `network.json` from the write journal — `src/nfcio.py write` emits
one JSON object per write with a verified read-back flag, so the row is derived from a
physical truth rather than from this sentence.
