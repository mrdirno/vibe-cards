# AV Field Toolkit card — AV-TOOLKIT-001

The first card in this repo for a project that is **not** this repo.

```
front   the toolkit's own lockup, its own palette, and nothing countable
back    the URL in full, and a QR that decodes to exactly it
chip    not written yet — no tag has been read back, so no chip row exists
```

`network.json`'s `shape` block names five parts every project has — repo, site, manifest,
wish, card. AV-TOOLKIT-001 had four. It had a `redirector` row, and the cards block's own
`_surfaces` note says a redirector is a destination that *exists*, not evidence that any
card carries it. This is the card.

## Rebuild it, exactly

Run from the repo root. Every step is checkable, and step 4 is the one that matters.

```bash
# 1. the code — ONE generator, which verifies by decoding its own output
swift tools/make_qr.swift \
  --text "https://mrdirno.github.io/nested-resonance-memory-archive/av/" \
  --out examples/av-toolkit-card/assets/AV-TOOLKIT-001_qr_on-white.png --ec M --px 2048

# 2. the code as GEOMETRY, read back out of that PNG rather than re-encoded
python3 tools/qr_to_svg.py \
  --png examples/av-toolkit-card/assets/AV-TOOLKIT-001_qr_on-white.png \
  --x 56.4 --y 15.99 --size 22 \
  --into examples/av-toolkit-card/designs/back.svg

# 3. rasterise at BLEED, then DERIVE trim by cropping 22 px per edge
cd examples/av-toolkit-card/designs
for f in front back; do
  rsvg-convert -w 2066 -h 1319 -o ${f}_87.5x55.88mm_bleed_600dpi.png $f.svg
done
python3 -c "
from PIL import Image
for f in ('front','back'):
    b = Image.open(f'{f}_87.5x55.88mm_bleed_600dpi.png'); assert b.size == (2066,1319)
    b.crop((22,22,2044,1297)).save(f'{f}_85.6x53.98mm_600dpi.png')"

# 4. prove the ink says what the registry says it says
cd ../../..
./tools/qrdecode examples/av-toolkit-card/designs/back_85.6x53.98mm_600dpi.png
python3 tools/verify_geometry.py | grep -i av-toolkit
```

Step 3 is the only step with no gate behind it, so it carries the trap: **render at bleed
and crop down, never the reverse.** 87.5 × 55.88 mm converted independently at 600 dpi
gives 2066 × 1320, and an odd 45-px difference cannot centre a 1275-px trim box. Cropping
also makes the 22-px registration true by construction rather than by arithmetic.

## Three things that cost a render each

**librsvg silently drops an `href` above the SVG's own directory.** The founder card's
`../assets/qr.png` renders as an empty white patch here — no warning, and the card looks
finished. That is why step 2 exists: geometry has no second file to fail to load.

**XML comments cannot contain `--`.** Which is every flag of the command above, so the
command lives in this file and not beside the block it generates. Pasted into the SVG it
is a parse error, and a parse error means the face does not render at all.

**`--size` is the dark grid, not the patch.** `qr_to_svg.py` bounds the dark modules, so
the quiet zone is *not* in that number — it is the white rectangle underneath, drawn by
the design. The tool reports `quiet_needed_mm`; the design owes at least that much light
on every side. Here: 2.667 needed, 3.0 given.

## What the numbers are, and how they were measured

| | |
|---|---|
| Trim / bleed | 85.6 × 53.98 mm · 87.5 × 55.88 mm (2022 × 1275 · 2066 × 1319 px) |
| URL | 61 bytes → QR version 4, 33 modules, EC M |
| Code | 22 mm → 0.667 mm per module, against a 0.4 mm print floor |
| Patch | 28 mm white, 3.0 mm of quiet on every side |
| Ink clearance | every glyph ≥ 4 mm inside trim; only the background and the accent bar bleed |
| Decode floor | **180 px** |

The decode floor is the narrowest capture *of the whole card* that still reads through
`tools/qrdecode`, stepping down 10 px at a time. The control run in the same command is
the card that actually ships today — `examples/founder-card` — which fails at 260 px.
Same 33 modules; 1 mm more code and hard vector edges buy the rest.

## Palette

Not chosen here. Every colour is read out of the toolkit's own runtime config,
`av/trade.js`, which also states how the wordmark is set: `brandLead` plain, `brandTail`
bold in the accent. The card renders the lockup the way the product renders it, rather
than inventing a second identity for the same thing.

## Why nothing countable is printed

The toolkit is a standing expansion programme — the tool count goes up, the trade count
goes up. Ink is as permanent as a chip, so a number set in it starts decaying the day it
dries. The front carries what survives growth and nothing else. For the same reason the
URL is printed unshortened rather than as a `persona500.com/c/` slug: that table answers
200 for slugs it has never heard of by falling through to a different project's site, so
a card carrying an unmapped slug looks perfectly healthy to every check that reads a
status code and lands its holder on the wrong page.

## Before printing

Read `docs/PRINT_GEOMETRY.md`, and do not let the print dialog fit-to-page — it is on by
default in most drivers and it is the one setting that ruins a card. Printing is
irreversible; the rehearsal on plain paper costs nothing.

If a chip is ever written for this card, write the **same URL** the QR carries, then
record a `chip` row in `network.json` from the write journal — `src/nfcio.py write` emits
one JSON object per write with a verified read-back flag, so the row is derived from a
physical truth rather than from this sentence.
