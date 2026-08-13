# Founder card — the worked example

A real card, printed and carried. Copy it and change the details.

```
front   photo, name, role, domain
back    project name, what it is, the URL, a QR
chip    the same URL as the QR, plus the card's identity in plain text
```

Tap it or scan it and you land in the same place. That is the only rule the two
halves have to obey.

## Files

```
designs/   front.svg, back.svg — edit these
           *_600dpi.png at trim (85.6 × 53.98) and bleed (87.5 × 55.88)
specs/     card_spec.json — geometry, safe zone, QR placement
           placement_coordinates.json
print/     single cards at trim and bleed, plus 120 × 120 mm tray layouts
assets/    the 24 mm avatar the front SVG references, and the QR at three levels
```

`print/tray_120x120_combo_front-top_back-bottom.pdf` prints both faces in one pass on a
two-slot tray. The other two do one face on both slots, for double-sided runs where you
flip the stock between passes.

## Making it yours

1. Replace `assets/headshot_circle_24mm.png` — 24 mm circle, transparent outside.
2. Edit the text in `designs/front.svg` and `designs/back.svg`.
3. Generate your QR for your own URL:
   ```bash
   swift tools/make_qr.swift --text "https://your-project" --out examples/founder-card/assets/qr.png --ec Q
   ```
4. Write the chip with the same URL:
   ```bash
   cd src && python3 nfcio.py write --url "https://your-project" \
       --epitaph "vc1|YOUR-ID-001|Your Project|2026-08|MIT|vibe-cards"
   ```
5. Print `print/tray_120x120_combo_front-top_back-bottom.pdf` at 100% scale. **Do not
   let the print dialog fit-to-page** — that is the one setting that ruins a card, and
   it is on by default in most drivers.

## Geometry that matters

| | |
|---|---|
| Trim | 85.6 × 53.98 mm (CR-80) |
| Bleed | 87.5 × 55.88 mm (0.95 mm per edge) |
| Safe zone | keep text ≥ 3 mm inside the trim |
| QR | 21 mm on a 25 mm white patch |
| Tray | 120 × 120 mm, slots at y = 3.818 and 63.868 mm |

The QR is 21 mm because below roughly 17 mm a phone camera starts failing at normal
distance, and it sits on a white patch because a QR needs light/dark contrast — printed
straight onto black or onto foil, it will not scan.

## Known: both faces sit high

Measured on the 600 dpi renders: front content spans 9.2–36.5 mm, leaving 17.5 mm empty
at the bottom against 9.2 mm at the top. Back spans 11.0–39.5 mm, 14.5 mm against 11.0 mm.
Moving the front block down ~4.1 mm and the back down ~1.8 mm centres both.
