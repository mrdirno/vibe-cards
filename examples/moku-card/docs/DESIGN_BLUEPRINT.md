# DESIGN BLUEPRINT & MECHANICS — MOKU-003

## Identity
Mokume Photonic Lattice — 17-layer Cu/Shakudo billet flow-formed by SDF laminar turbulence into Asanoha kumiko lantern, photonic caustics, thermal breathing.

## Mechanical Principles
- **SDF_LaminarWarp:** f(p)=p+curlNoise(p*0.8)*A+sin(p*3.2)*0.15, A=Re/1800*0.8mm, Re clamped <1800 via smoothstep(1500,1800). Deterministic hash seed MOKU003. Variance σ 0.12mm across 17 layers enforced not post-process.
- **ThermoDilatantCell:** Bi-metal leaf Cu 16.6 vs Shakudo 18.2 µm/mK, Δα1.6 µm/mK, L150mm, ΔT40K → 0.0096mm per ligament, accumulated 6 ligaments radial → 0.30mm aperture. Photonic lux mod 40%.
- **FrictionLockKumiko:** 0.07mm [0.05-0.09] interference, 7° wedge draft, μ0.34 dry hinoki/metal, 12N shear, zero adhesive. Kerf compensation 0.08mm.

## Structural Tolerances
Layer ±0.02mm, cell pitch ±0.1mm, interference +0.01/-0.0mm, dilation ±0.05mm @40°C, Re <1800.

## Assembly
1. Stack 17× 0.9mm C110 + 0.6mm Shakudo 98Cu2Au, 120×90mm.
2. Cold-forge 20T hydraulic 65% reduction → 0.8mm sheet 25.5→8.9mm? Actually 25.5mm billet → 0.8mm final (85% reduction for sheet).
3. Anneal 450°C 22min grain <45µm.
4. Etch ferric chloride 30% 8min reveal contrast.
5. Laser cut Asanoha 0.8mm, kerf 0.08mm compensation in SVG.
6. File wedge 54.5° end-grain, dry fit.
7. Heat test 200W halogen @150mm → ΔT40°C → caliper.

## Three Non-Obvious Adaptations
1. **Daylight louver:** Scale cell 36mm, 34 layers, 0.6mm @60°C passive solar breath, modulates interior lux 40% without electronics, Re 1650 maintains laminar flow.
2. **Wearable cuff:** 6 cells wrist, body ΔT12°C → 0.09mm micro-vent, skin-safe zero glue, 12N holds daily wear.
3. **Acoustic metamaterial:** Same geometry in 3mm Al, SDF warp tunes bandgap 1.2-2.4kHz, friction-lock avoids weld distortion affecting Q factor.

## Fabrication Export
SVG cut white 0.18mm, score red dashed 1.2/0.8 0.15mm, tabs copper, calibration 10mm bar.

## VibeBus Interlock
Consumes CV_SOURCE (0-5V) → warp amplitude. Provides PHOTONIC_MOD → LENS-004 caustic projector, CYMA-009 resonator.

## Material Gauge
Final 0.8mm sheet recommended for laser, 120×90×110mm assembled lantern.

