# AUTHORSHIP.md — MOKU-003

**Human Author Intent (2-4 sentences):**
Build a mokume-gane photonic kumiko lantern that breathes light with heat — 17 alternating copper + shakudo layers flow-formed by laminar SDF turbulence, Asanoha cells dilating 0.3mm at ΔT 40°C, friction-lock 0.07mm zero glue. Editorial forge aesthetic, Apple-grade simplicity, deterministic kernel isomorphic across visual plate, live canvas, and SVG export. Must be gallery-quality wearable/structure, next-level aesthetics, functional tech.

**Human Selections, Arrangements, Edits (concrete):**
- Selected 17-layer count, Cu C110 + Shakudo 98Cu2Au chemistry, 0.9mm/0.6mm thickness, 65% reduction, 0.8mm final sheet.
- Selected Asanoha hemp-leaf geometry, 21mm nominal cell (18-24mm parametric), 23 cells on blueprint, 0.07mm interference +0.01/-0.0, 7° wedge draft, 12N shear target.
- Arranged front face: billet anchor 32%x68%y 38% frame, lantern 62%x45%y 54%, dark forge #0A0E0F, copper emissive 2200K, caustics.
- Arranged back face: cut solid white 0.18mm, score red dashed 0.15mm 1.2/0.8, tabs copper #B87333, 10mm calibration bar 0.5mm ticks.
- Edited SDF kernel formula to `f(p)=p+curlNoise(p*0.8)*A+sin(p*3.2)*0.15` with Re clamped <1800, seed MOKU003, variance σ 0.12mm.
- Edited thermal numbers: Cu 16.6 µm/mK (ASM Handbook verified) vs Shakudo 18.2 estimated, Δα1.6 → 0.3mm dilation.
- Selected URL `https://compound-crafts.io/cards/MOKU-003` as QR payload, verified char-for-char equality with #vc-card.url.
- Selected MIT license, SPDX match.

**AI Portions (disclosed):**
- Generated SDF noise implementation (hash2, noise2, curlNoise) deterministic.
- Generated Canvas2D rendering loops, Asanoha grid math, mask isolation via destination-out composite.
- Generated SVG cut path export, 4K displacement PNG export, print template 600dpi.
- Generated QR PNG via python qrcode library (deterministic payload).
- Generated python tools: generate_lattice.py, sdf_laminar.py, export_4k.py, intake_card.py.
- Generated VibeBus protocol embedding, Wish It Better fetch logic + offline queue.
- Generated hierarchy log and blueprint mechanics prose from genome.

**Copyright Evidence Layer:**
Human creative direction and selections are original and documented above. AI portions are tool-assisted generation under human orchestration per EU AI Act Art 50 marking: `{"ai_generated": true, "card": "MOKU-003", "visible_mark": "AI-generated MOKU-003 lower-right 5%"}`. Prompts alone do not qualify as authorship; human arrangements and edits above constitute authorship.

**License:** MIT — see LICENSE file, matches vc-card.license.

