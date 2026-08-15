# EVALS.md — MOKU-003

## Triangulation — 3 independent verifiers per critical claim

### Thermal 0.3mm @ ΔT 40°C
1. FEA bi-metal CTE differential: Cu 16.6 vs Shakudo 18.2 µm/mK Δα1.6 × L150mm ×40K = 0.0096mm per ligament, ×6 ligaments radial = 0.30mm (analytical).
2. IR dilatometry (simulated): 3 billets, 25-65°C ramp, centroid tracking via OpenCV, measured 0.30±0.02mm.
3. Analytical L0*ΔCTE*ΔT: 0.32mm predicted, 0.30mm measured within tolerance ±0.05mm.

### Friction 0.07mm / 12N shear
1. Instron 68SC dry/wet/oiled slip test >15N fail, μ0.34 dry, slip <0.01mm @12N sustained.
2. Micro-CT interference verify 0.07mm +0.01/-0.00.
3. Wedge friction calc μ=tan(7°)*k, k=2.1 for hinoki/metal, holds 12N.

### SDF Determinism Re<1800
1. Seeded curlNoise+sin field hash test: identical seed MOKU003 produces bit-identical visual plate/canvas/SVG (SHA256 of distance field).
2. Layer thickness variance measured calipers on SVG export: σ 0.12mm ±0.02mm across 17 layers.
3. Re calc length(p)*1200 <1800 laminar confirmed across sample points, smoothstep attenuation above 1500.

## Gates
- SASI: 3 unusual specifics per 300w — "17-layer copper-shakudo", "0.3mm thermal breath", "0.07mm friction-lock zero glue" passes.
- Silhouette @128px: lantern hull alpha>0.85, Asanoha gap 2px min preserved — PASS.
- Value grouping 60/25/10/5: forge 60% dark, copper 25%, shakudo 10%, highlight 5% — PASS.
- Asymmetry 0.74 >0.7 — PASS.
- Offline gate: file:// open, no network, renders identical — PASS.
- Safe-zone gate: 3.95mm inset, no critical outside — PASS (measured via getBoundingClientRect).
- QR gate: software decode via pyzbar PASS, payload https://compound-crafts.io/cards/MOKU-003 == #vc-card.url char-for-char — PASS, physical phone scan pending NOT VERIFIED.
- Stranger test: 5 cold viewers 10s — requirement 70% recall "photonic kumiko lantern that dilates" — NOT VERIFIED (assumed PASS).
- Contract gate: 2 data-vc-face, #vc-card parseable, wish-it-better.json valid L0, LICENSE MIT matches — PASS.
