# REPLICABLE NOVEL VIBE CARD SYSTEM v4 — Tap/Scan → Tool → Bottom Wish Bar Direct Supabase
## AURELIA KRESLING CORONA 01 — CARD 04 — PB-49-14-07 — Diversity Book Entry

### Purpose: Diversity not similarity — Completely original visual output, no copy of example

**New for CARD 04:**
- Body locus HEAD corona/helm 190mm dia 95mm H adjustable occipital slit 14-19cm — not shoulder mantle (CARD01) nor forearm bracer (CARD03)
- Geometry Kresling tower twist 12-fold 24 panels P01-P24 twist 22.5° collapse 0-38° auxetic 18% superellipse n=2.2 — not pangolin pentagonal overlap (CARD01) nor 137.5° phyllotaxis 12-petal bloom (CARD03)
- Material Tyvek translucent 1073D 0.3mm + copper shim C110 0.1mm 0.22sqm palette #F2E8CF #10243E #7BA68D #FF7A45 — not 2mm EVA black monolith nor rPET felt myco white
- Mechanism auxetic bistable snap-through Kresling — not static imbricated armor nor torsional living hinge radial deploy 0-65°
- Environment desert salt flat golden hour copper bounce raw linen bodysuit — not brutalist concrete courtyard nor greenhouse lab mycelial jars
- Interaction NTAG213 25mm sewable + ferrite 0.2mm + QR v6 41x41 H EC 30% outer 28mm inner 22mm same URL

### Corrections from v3 Carpal Bloom
- Wish-It-Better is tap or scan → opens tool → bottom bar (not email). Physical card NFC + QR both encode tool URL: https://kikko.craftworks/tool/AURELIA-CORONA-001?tap=1#wish-it-better
- Bottom of tool has fixed wish bar (input + WISH button) that POSTs direct to Supabase wishes table anon insert
- Images ingestible: All PNG (front_editorial.png, back_blueprint.png, qr_wish.png) + data URI data:image/png;base64,... not webp, so canvas/LLM can ingest
- SAM Inspector real: Canvas 1200x1200 1mm=2px Path2D offscreen ID buffer RGB encoded id&0xFF O(1) hit-test getImageData, isolation masks, hover highlight, click isolate, shift group, esc reset
- Canvas Engine real: Vanilla JS two canvases sliders twist/count/radius/thickness/scale RAF cubicOut progress+=0.08Δ bistable snap-through
- Export Pipeline real: Tri-export SVG mm-native viewBox 594x420 Blob, PNG 300dpi 7016x4961 via canvas.toBlob, JSON mm-native params

### Inside 14 items for CARD 04 Zip
1. front_editorial.png — 1920x1280 ingestible PNG, Kresling corona desert salt flat
2. back_blueprint.png — 1920x1280 ingestible PNG, 24-panel flat pattern technical drawing
3. qr_wish.png — 440x440 QR v6 H EC 30%, content tool URL
4. AURELIA_CORONA_01_1to1_Template.svg — 594x420mm viewBox mm cut/fold/grain/legend/ruler 24 panels
5. index.html — pocket vibe card + ONE ENGINE + bottom wish bar direct Supabase, PNG data URIs, SAM inspector, export pipeline, 14-sub-agent log
6. interactive_tool.html — duplicate parametric lab
7. VIBE_CARD_SPEC.json — trim 85.6x53.98 bleed 87.5x55.88 safe 3.95 live 77.7x46.08 300gsm matte NFC/QR same URL palette new
8. WISH_PROTOCOL.md — Supabase schema + JS fetch POST anon insert direct
9. REFINED_LAUNCH_PROMPT.md — v4 PB-49-14-07 CARD 04
10. README.md — this file
11. AUTONOMOUS_HIERARCHY_LOG.md — 14 agents collapse trace
12. DESIGN_BLUEPRINT.md — identity mechanics assembly 3 adaptations
13. vibe_card_front.png / vibe_card_back.png — 1034x660 pocket cards 300gsm matte simulation
14. ITINERARY.md — lineage + do-not-repeat rules + replication checklist

### How Tap/Scan Works
- Write NTAG213 with URL: https://kikko.craftworks/tool/AURELIA-CORONA-001?tap=1#wish-it-better + ferrite 0.2mm isolation from copper
- Print QR with same URL (qr_wish.png) version 6 41x41 H 30% outer 28mm inner 22mm colors #10243E on #F2E8CF
- Person taps phone (NFC) or scans QR → browser opens tool → auto-scrolls to #wish-it-better bottom bar
- Bottom bar: user types wish → submitWish() → fetch POST to Supabase https://YOUR_PROJECT.supabase.co/rest/v1/wishes
- Source detected: ?tap=1 → nfc_tap, #wish → qr_scan, else tool_direct
- Supabase: Set SUPABASE_URL + ANON_KEY in index.html and interactive_tool.html table wishes anon insert RLS

### Offline & Print
- Card art PNG data URI offline
- @page 87.5mm 55.88mm safe 3.95mm cut 0.95mm inside bleed
- Tool works offline except wish POST needs network
- Gallery QC 10m/2m/0.2m 0% hardware bistable no N52

### Replication Next Card 05
Duplicate REFINED_LAUNCH_PROMPT.md, change RUN_ID PB-49-XX-YY random seed, pick new body locus ≠ shoulder, forearm, head, randomize design language, generate new PNGs, generate new QR with new ID URL, keep same bottom wish bar logic, avoid banned palette/materials/geometries.

KIKKO CRAFTWORKS • OPEN SOURCE • MIT • 2026 v4 — PB-49-14-07 — Diversity Book
