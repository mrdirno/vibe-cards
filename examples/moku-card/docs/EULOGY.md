# EULOGY.md — MOKU-003 Kills & SCARs

**Role 08 REAPER — No sentiment, only structural learning.**

## Kill 01 — Mystical Energy Without Units
- **Trigger:** Copy containing "aura", "resonance" without J/K/N or measurable.
- **Root Cause:** Non-falsifiable axiom violates L1 falsifiable world laws.
- **SCAR:** All claims must include unit + tolerance (e.g., 0.3mm±0.05mm @40°C, 12N shear, Re<1800). Linter regex `/(aura|chi|energy)/i` fails if no number within 20 chars.
- **Eulogy:** Died as vague; reborn as thermal differential.

## Kill 02 — Placeholder QR (4/4 historical)
- **Trigger:** QR payload `example.com`, `mailto:`, `.example` TLD.
- **Root Cause:** Generator produced perfect QR that pointed nowhere (LEARNINGS.md 4/4).
- **SCAR:** Enforce `qr_payload == vc-card.url` char-for-char via `pyzbar` decode on finished PNG + fetch attempt. Build fails if mismatch. Payload here: `https://compound-crafts.io/cards/MOKU-003` verified.
- **Eulogy:** Beautiful scan to nowhere → verified scan to live forge.

## Kill 03 — PNG File Request (0/4 delivered historically)
- **Trigger:** TARGET earlier asked for 4 PNGs at exact px; 0/4 delivered.
- **Root Cause:** Language model cannot raster deterministically; receiver has headless 600dpi rasterizer.
- **SCAR:** Generator delivers ONE HTML file contract-exact; PNGs derived downstream from `[data-vc-face]`. No PNG in zip from generator.
- **Eulogy:** Died as binary request; reborn as HTML contract.

## Kill 04 — External CDN
- **Trigger:** `https://cdn.jsdelivr`, `unpkg`, `fonts.googleapis`.
- **Root Cause:** Self-contained gate fails offline, font metrics drift, safe-zone violation unseen.
- **SCAR:** CSP `default-src 'none'` scanner blocks `https://`, `//fonts`. All images/fonts/scripts inlined as data: with correct MIME. System font stack only.
- **Eulogy:** Died as network dependency; reborn as 926-byte data URI.

## Kill 05 — Generic Asanoha Without SDF Warp
- **Trigger:** Uniform 60° hemp without laminar distortion.
- **Root Cause:** Fails SDF-Physics Mathematical Ground Truth (Mandatory) and SASI 3 specifics per 300w.
- **SCAR:** Forced warp `p' = p + curlNoise(p*0.018)*2.1*sin(layerIndex*0.73+dot)*1.4mm` at Re=1650±150, σ=0.12mm across 17 layers. Kernel isomorphic: plate/canvas/SVG call same `laminarWarp()`.
- **Eulogy:** Died as decorative; reborn as flow-formed.

## Kill 06 — 33px Buttons (Historical 33/42 vs 44px floor)
- **Trigger:** Button hitbox <44px.
- **Root Cause:** Bonus artifact skipped gates, shipped broken (LEARNINGS.md 3.3).
- **SCAR:** All interactive targets min 44×44px, 8px gap. Lint checks `getBoundingClientRect()`. FrictionLock 0.07mm analog: unpressable ≠ precision.
- **Eulogy:** Died as tiny tap; reborn as 12N hold.

**Organism SCAR Promotion:** 3 recurrences of QR placeholder (4/4) → promoted to Law candidate: "A QR that scans is not a QR that works — payload must resolve to intended URL."

**Total Kills:** 6. No sentiment. All compiled into lint rules in `tools/intake_card.py`.

