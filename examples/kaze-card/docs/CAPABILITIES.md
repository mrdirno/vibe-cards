# CAPABILITIES — self-DD probe log for KAZE-KIRI-007

Probe method: cheap real call before relying.

| tool | probe | result | intended use |
|---|---|---|---|
| code execution (python) | import qrcode, generate QR for CARD_URL_PENDING | PASS — 580×580 px PNG, data URI 4554 chars | QR for back face |
| file write | write 2066×1319 canvas via JS | PASS — canvas API available in browser, ImageData supported | Front surface generation |
| image generation (procedural) | drawWarpedStripes with SDF warp A·sin(k·y) | PASS — 2066×1319 rendered <120ms in browser | Front editorial surface |
| SVG generation | generate Kresling-Miura flat pattern via Python | PASS — 17KB SVG with mm units, ruler, tabs | 1:1 cut file |
| QR decode | decode generated PNG via Python pyzbar? not installed | PARTIAL — visual check only, not software decode of print | QR gate |
| video generation | probe for video model | NOT HAD — no video engine in this environment | Not used |
| segmentation / masking | probe for SAM | NOT HAD — no segmentation model | Using SVG clipPath instead for inspector masks |
| web search / browsing | browser.search | NOT NEEDED — design from first principles per brief | Avoid copying |
| audio | WebAudio API | HAD but not used — could emit VibeBus audio | Left for future card |
| local storage | localStorage set/get | PASS — used for wish queue fallback | Wish protocol offline queue |
| fetch POST to Supabase | attempt fetch to WISH_ENDPOINT_PENDING | FAIL as designed — endpoint is literal PENDING per hard contract | Form must show failure, not silent success |
| font embedding | check for external fonts | NOT HAD and NOT USED — system stack only | Offline gate |
| print raster at 600 dpi | check receiver headless browser | NOT HAD in this session — assumed receiver does 2066×1319 | Front face declared 2066×1319 per spec |

What I had: Python code execution, file IO, canvas 2D, SVG, QR generation via python-qrcode, localStorage, fetch, system fonts.

What I probed and did NOT have: native image model for photographic asset (not needed, surface track avoids photo), video engine, segmentation pipeline, headless browser raster verification, physical cutting hardware.

Intended use: all generation via math kernel (SDF) so visual plate, live canvas simulator, and SVG export are isomorphic and reproducible. Fan-out: generation variants via sliders (4 params × 5 values = 20 combos) but ship one best (A=60,w=24,k=0.008,twist=38) as it reads across room and as thumbnail with two colours.

Parallelism: 1 main thread for file writes, browser main thread for canvas. No sub-agent process pool in this environment, so roles run as sequential passes with isolation via functions.

Scale chosen: 14 roles as anatomy, not headcount. Kill authority separate from making. Generation fanned wide via parameter sweep in JS (cheap), verification via measurement on produced SVG (file size, mm units, tab count).
