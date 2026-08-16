# KAZE-KIRI-007 — Wind-Cut Collar
Card 007 of BOOK 1: THE COMPOUND CRAFTS.

A neck collar cut from one sheet that snaps open with a twist and locks without glue.

## What it is
One A2 sheet of 0.26 mm Tyvek plus washi plus copper. 12 triangulated units in a ring. Kresling is a fold that makes a tube twist as it collapses. Miura is a fold that packs flat and opens with one pull. This collar uses both.

- Flat: 439.82 mm circumference (π×140) by 85 mm tall. 12 units, base 36.65 mm each.
- Deployed: Inner diameter 140 mm, height 85 mm, stands off neck 12 mm for air flow.
- Lock: 3 wedge tabs. No glue, no hardware.
- Hinge: Living hinge that is also the joint, 0.3 mm remaining.
- Vent: 12 slits spaced 137.5 degrees (golden angle) so no two align.

Front of card is the collar's own surface at full bleed, drawn by its own rule. Two colours only: washi warm #EAE0C8 and near-black #0E1116. Stripes are Kresling shear: x_warp = x + A·sin(k·y). Every band different, whole thing one object. Tap box x 68.3–78.6, y 36.7–47.0 mm left as flat washi.

Back of card is fabrication face: scaled flat pattern, cut and fold vectors distinguished by colour and dash, 3 tabs, 12 slits, 20 mm ruler, legend, QR 21 mm on white patch with quiet zone 4 modules.

## How to run it
Open index.html directly from disk. No network. No build. System fonts only, images as data URIs with correct MIME.

- Card faces: two sections with data-vc-face="1" and "2", each 87.5×55.88 mm bleed, 85.6×53.98 mm trim. Trim offset 0.95 mm per edge. Safe inset 3.95 mm from bleed.
- Live surface: sliders for shear A, band width w, frequency k, twist angle. Updates front canvas (2066×1319, 600 dpi) and interactive canvas (1200×680).
- Component inspector: click triangle to isolate, masks are real SVG. Emits VibeBus signals.
- Export: Download 1:1 SVG (real size + ruler), clean cut paths, parametric JSON. All generated from same kernel as canvas. Files open in browser.
- VibeBus: window.VibeBus emits CV and component signals for daisy-chaining with other cards.

## How to wish it better
Use the form on the page. Categories: TOLERANCE_ADJUSTMENT, CULTURAL_PROVENANCE, MATERIAL_FORMULA, AI_PROMPT_REFINEMENT, NEW_FEATURE.

Payload goes to Supabase table vibe_card_wishes:
card_id, book_id, crafter_name, wish_category, proposal, suggested_parameters, status, created_at

Endpoint and key are left as WISH_ENDPOINT_PENDING and WISH_KEY_PENDING per hard contract. Do not invent URL. Form shows failure when endpoint pending and queues in localStorage per protocol.

Mail fallback: wish-it-better.json contains mailto as account-free route.

## Compounding — entry fee
Uses:
- tab-and-slot solver from MANIS-CUIRASS-001
- card-back layout from AUREA-LATTICE-002
- safe-zone measurement check from MOKU-003
- living-hinge that is also joint + golden-angle spacing from CARPAL-BLOOM-004
- Kresling twist from AURELIA-CORONA-005
- one-motion deploy from ZARIA-HALO-006

Provides:
- kresling-miura-compound solver: Takes N, D, H, twist, thickness and outputs flat-foldable Kresling-Miura pattern with tab positions, fold angles, flat-foldability check. Implemented as window.KreslingMiuraSolver in index.html and verified on produced SVG.

## Files
- index.html: page and both card faces, self-contained
- KAZE-KIRI-007_1to1.svg: cutting file, real size, with ruler, cut/fold distinguished
- README.md: this file
- CAPABILITIES.md: what was probed, had, did not have
- LICENSE: MIT
- wish-it-better.json: network manifest
- FREEZE_MANIFEST.json, AUTHORSHIP.md, EULOGY.md per framework

## ASSUMPTIONS
- Material 0.26 mm Tyvek + washi + copper laminates without delamination at 0.4 mm fold radius. Assumed based on Tyvek data sheet, not measured on this exact laminate.
- Laser kiss cut for living hinge leaves 0.3 mm. Assumed achievable on 40W CO2 at 15% power, 300 mm/s. No physical cut tested.
- Tab clearance 0.15 mm works for 0.26 mm material. Calculation: slot = thickness + 0.2 mm = 0.46 mm. Assumed.
- QR payload CARD_URL_PENDING will be replaced on intake burn-in. Left as literal per hard contract.

## NOT VERIFIED
- No physical prototype cut or folded. All tolerances are calculations measured on SVG file.
- No Instron slip test, no micro-CT, no wash test.
- No phone scan test on printed card at 600 dpi, only software decode of QR data URI. Print contrast not measured.
- No offline gate on paper stock, only file offline open from disk.
- Luminance under tap box measured on canvas pixels (224/255), not on printed card with spectrophotometer.
- Solar thin-film integration and acoustic baffle claims are adaptations, not tested.
