# Open Archive card design

A paired print-only template for https://persona500.com/open-archive/. The
back carries that readable address. No physical card ID, chip, NFC payload,
or QR has been allocated. Choosing this template does not program a card.

Open Card Studio with `?template=pair:open-archive-front`, or choose
**Cards in the network → Open Archive / Vincent van Gogh**. Both faces load.
The single faces remain available under **One face at a time**.

The four `designs/` PNGs follow docs/INTEGRATING.md: 2022×1275 trim and
2066×1319 bleed at 600 dpi. Bleed extends each edge 22 px; its center is the exact
trim raster. The standard renderer applies the selected frame and bleed once.
Use the current tray profile to export PDF; no tray or printer geometry is
baked into the design. No printing or chip write was used for verification.

Source SVG faces and the raw institutional record are in `assets/`.
`specs/card_spec.json` records geometry and hashes. The original SVG face
front includes a viewport crop of the reviewed, otherwise uncropped museum
image. The Met Open Access / CC0 applies to that image; see root NOTICE and
`src/web/cards/open-archive-provenance.json` for image/source hashes and URLs.
Aldrin Payopay / Persona500 designed the layout.

This is a manual, bounded print-only intake. The generic intake_card.py
rewrites the URL to its own Pages namespace and generates a QR; neither
action belongs to this canonical external-page design. No intake script or
security behavior was changed.

Verification: build with `./build_app.sh <scratch-folder>` and run the bundle's
server using an isolated SUPPORT/DESIGNS/OUTPUT fixture. With optional
Playwright installed, run:

```sh
node tools/verify_open_archive_template.mjs http://127.0.0.1:PORT/ /tmp/open-archive-proof
python3 tools/verify_print_export.py /tmp/open-archive-proof/chromium-front-back-tray.pdf --margin 0.66
```

Pass the fixture's actual chosen frame dimensions to `--margin`. The 0.66 mm
frame is the default fixture, not a required print margin. Hardware printing,
real PVC registration, NFC and actual iOS Safari are outside this test;
Playwright WebKit is an engine test.
