# Print geometry — what is measured, and what was wrong

A card is 85.6 × 53.98 mm. Nothing in this project may scale it.

Run these in order when a printed card is wrong:

```bash
python3 tools/verify_geometry.py                        # is the PLACEMENT right?
python3 tools/verify_print_export.py CARD.pdf           # what INK is in it?
python3 tools/verify_print_export.py CARD.pdf --margin 1.0,1.0 [--bleed 1.0]
python3 tools/verify_print_export.py CALIB.pdf --expect-ink-within 0.3
```

The first proves the composer. The rest open the images the PDF actually carries,
because that is where every real failure has lived.

---

## The one that took four weeks: there was never a scale factor

Printed cards measured **81.83 × 49.94 mm** against a card of 85.6 × 53.98. That
looks like a 4.4 % shrink, so the search went looking for a scale — fit-to-page,
PPD ImageableArea, a units bug, a MediaBox mismatch. All of it was clean, and the
search kept going anyway.

**The arithmetic that ends it, before any code is read:**

| | white lost | as a fraction |
|---|---|---|
| across | 3.770 mm on 85.6 | 4.40 % |
| down | 4.040 mm on 53.98 | 7.48 % |

One scale factor cannot be two percentages. Any isotropic scale, about any fixed
point, forces `white_across / white_down = 85.6 / 53.98 = 1.586`. The measured
ratio was `3.770 / 4.040 = 0.933`. **Not a scale.** A constant band on every edge,
and a constant band comes from something additive.

**It was in the artwork.** Decoding the PDFs the app actually sent:

| PDF | placement | white frame *inside* the raster | ink on card |
|---|---|---|---|
| `20260810-165423` | 85.600 × 53.980 mm @ (17.553, 3.818) | L 1.86 R 1.86 T 1.86 B 1.91 | **81.88 × 50.21** |
| `20260811-174328` | 85.600 × 53.980 mm @ (17.553, 3.818) | L 1.95 R 1.91 T 1.86 B 1.78 | **81.75 × 50.34** |
| `20260812-201921` (full bleed) | identical | 0.00 all four | **85.60 × 53.98** |

The calipers read 81.83 × 49.94. The artwork's own frame accounts for it to within
0.05 mm. The placement was exact the whole time, on every one of them.

### Then the app started enforcing the measurement error

`tools/calibrate.py` was pointed at one of those prints and asked "how much can
the printer not reach?" It assigns the whole symmetric residual to the printer
**by construction** — it has no way to see that the design contributed white. Out
came 1.885 × 2.02 mm, which went into the app as `BEZEL_X`/`BEZEL_Y`, drove the
safe-zone guide, and defaulted a "Margin" toggle to ON.

At that point the loop closes: artwork white was measured, promoted to printer
physics, and then printed onto every subsequent card as a white frame. Measured on
the shipped rasteriser with a pure black full-bleed background:

```
margin ON  (the default)   ink 81.788 × 49.911 mm
margin OFF                 ink 85.598 × 53.975 mm
the calipers               81.83  × 49.94
```

The app reproduced the original symptom to 0.04 mm, from software, on every card,
whatever the artwork did.

### What the printer actually costs you

Ask the device instead of a card. `media-col-database` reports margins per media
size, in hundredths of a millimetre; for this tray's 120 × 120:

```
media-size={x-dimension=12000 y-dimension=12000}
  media-top-margin=10  media-bottom-margin=10
  media-left-margin=10 media-right-margin=10       → 0.1 mm all round
```

The residual left after removing the artwork's own frame agrees: 0.02 mm per edge
across, 0.14 mm down. So the true unreachable band is **~0.1 mm, not 1.9 mm** —
the earlier note that the PPD's 0.17 % was "a small part of a 4.4 % loss" had it
backwards. It was essentially the whole printer contribution.

`server.py: device_margins()` now asks at boot and the app adopts the answer. A
caliper measures the *outcome* of a pipeline and cannot attribute it. The printer
reports its own limit.

### The lesson worth more than the fix

**A number fitted from an outcome must never become an input.** The calibration
was circular — measure the result, call it a cause, then enforce it — and circular
measurements are self-confirming, so nothing downstream can catch them. If a
constant came from measuring your own output, it needs an independent source
before anything is allowed to act on it.

---

## Three more the same audit surfaced

**The frame was preview-only.** `drawBezel()` was called by the design canvas and
the tray preview, never by `rasterise()`. So when the frame was *wanted*, it did
not export. Both directions of the same conflation: one setting was doing
"printer constraint" and "design choice" at once. They are separate now —
`DEVICE_MARGIN_*` warns and is never painted, `S.frame` paints and is off by
default.

**The frame missed the corners.** Fixed, the band was drawn as a rounded rect on
the card's outline, which leaves the four nubs — outside the curve, inside the
bounding box — carrying artwork. Invisible on screen, where the preview is clipped
to the same curve; a dark wedge at each corner in the export, which does not clip.
The band is bounded by the raster now. Four edge scans had passed, because an edge
scan samples along edges and a corner is not on one.

**The calibration target was being masked.** It renders through the same
rasteriser, so the frame painted over tick 0, tick 1 and the corner L — the exact
marks the card instructs you to read. Measured: a 1.885 mm frame moves the first
visible ink to **4.911 mm** from the top edge. You would read the lowest visible
tick, enter a number about 5 mm wrong, and spend a card discovering it. The frame
is an explicit argument now and the calibration path passes `null`; a renderer
that reads global state cannot be called safely from a context needing different
state.

**Bleed never reached the elements.** Only the document background grew; elements
were translated. `defaults('image')` creates every added image at exactly
`x:0 y:0 w:card.w h:card.h`, so a full-card photo is card-sized inside an
oversized canvas and the entire bleed ring is background. Element ink measured
85.556 mm at bleed 0, 1 **and** 2 mm. You would enable bleed, get ink on the tray,
wipe the tray, and print an identical card. `bledElement()` now grows images and
unstroked rects, only on the edges they already touch — never text, QR or barcode,
because growing a full-card QR pushes its quiet zone off the card and it silently
stops scanning.

---

## What is clean — do not look here again

- **`src/pdfwriter.py` / `compose_pdf()`** — exact. `242.645669 0 0 153.014173
  49.756535 176.32063 cm` = 85.600000 × 53.980000 mm at (17.553000, 3.818000),
  MediaBox 120.000000 mm, ratio 0.999999999. The poppler residual halves as dpi
  doubles (0.0403 → 0.0192 → 0.0086 mm), which is edge quantisation, so the true
  error is zero.
- **CUPS** — `fitToPage=0`, `Drawing unscaled page.`, `scaled rect == docMediaBox`.
  Fiducials 100.000 mm apart printed 100.012 mm (0.012 %). `number-up=1` in both
  `lpoptions` and the live job. No fit-to-page, no print-scaling, no stored
  defaults.

## Margin and bleed are opposite answers, not companions

Ink cannot reach the very edge, by about 0.1 mm. Two ways out:

- **White frame** — stop short deliberately. Costs the edge of the design. A style
  choice, off by default.
- **Bleed** — print past the card, flood the tray. Costs tray cleaning.

Using both gives you both costs and neither benefit — ink on the tray *and* a
white ring on the card. The UI allows it; nothing recommends it.

## Measured constants

| What | Value | Source |
|---|---|---|
| Card | 85.6 × 53.98 mm | ISO/IEC 7810 ID-1 |
| Corner radius | 3.18 mm | ISO/IEC 7810 ID-1 |
| Unreachable band | **0.1 mm** | the printer, over IPP `media-col-database` |
| Aldrin's calibration | dx −0.395, dy −0.400 mm | tray centring; unaffected by the above |
| Safe zone | 4 mm | design convention, not a measurement |

`1.885 × 2.02 mm` appears nowhere as a printer constant any more. If you see it
again, it came back from a caliper.
