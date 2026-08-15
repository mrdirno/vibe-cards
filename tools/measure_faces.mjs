/* Measure a card package's faces in millimetres, against the safe zone.
 *
 *     node tools/measure_faces.mjs <package>/index.html [--safe 3.95]
 *
 * Prints a table per face and exits 1 if anything visible sits inside the trim
 * margin. Reads only; it writes no files. Rasterising is tools/intake_card.py's
 * job and this does not duplicate it.
 *
 * WHY IT EXISTS. Every gate in this repo checked the card as a FILE — is the
 * PNG 2066x1319, does the QR decode, is the PDF placement right. None of them
 * looked at where the TYPE sits on the face, and that is where incoming
 * packages actually break. Card 003 arrived with three defects that every
 * existing gate passed:
 *
 *   1. a `.face-label` reading "Face 1 — Editorial / Forge" printed on the card
 *      itself — a preview annotation the generator left in the artwork;
 *   2. a dashed `.safe-zone` rectangle, the proofing guide, drawn INSIDE the
 *      face, so the guide would have printed along with the card;
 *   3. a caption 1.08 mm off the bottom edge, inside the 3.95 mm safe zone and
 *      set vertically at 3.8 pt, which a trim anywhere in tolerance clips.
 *
 * All three are invisible to a dimension check and obvious to a measurement.
 * The output is millimetres because that is the unit the cutter works in: "no
 * glyph is inside the trim margin" becomes a number rather than an impression.
 *
 * THE ONE ARITHMETIC TRAP, written down because it cost a rewrite. Chromium
 * lays CSS millimetres out at 96 dpi, so an 87.5 mm face is 330.71 CSS px, not
 * 2066. Copying a renderer that clips {width: 2066} onto a package authored in
 * mm runs the clip off the right edge of the viewport and returns whatever
 * width was left — 1443 px, in the first attempt here. Measure the element's
 * own box and derive the scale from it; never assume the grid.
 */
import { chromium } from '/Volumes/dual/persona500/node_modules/playwright/index.mjs';
import path from 'node:path';
import fs from 'node:fs';

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--'));
const safeArg = args.indexOf('--safe');
const SAFE = safeArg > -1 ? Number(args[safeArg + 1]) : 3.95;

if (!file) {
  console.error('usage: node tools/measure_faces.mjs <package>/index.html [--safe 3.95]');
  process.exit(2);
}
const PAGE = path.resolve(file);
if (!fs.existsSync(PAGE)) {
  console.error(`no such file: ${PAGE}`);
  process.exit(2);
}

const BLEED_W = 87.5, BLEED_H = 55.88;   // the card's own bleed box, in mm

const browser = await chromium.launch();
// Narrow on purpose. A card sheet is usually a centred flex row that wraps, and
// a wide viewport puts the second face past the middle of the page where its
// box origin stops being small. One face per row keeps the measurement simple.
const page = await browser.newPage({ viewport: { width: 560, height: 700 } });
await page.goto('file://' + PAGE, { waitUntil: 'networkidle' });

// Faces whose background is painted by a canvas animation are not ready at
// load. Give the first frame a moment rather than measure an empty card.
await page.waitForTimeout(700);

const faces = await page.$$('[data-vc-face]');
if (faces.length < 2) {
  console.error(`expected 2 faces, found ${faces.length}`);
  await browser.close();
  process.exit(2);
}

const seen = new Set();
const violations = [];

for (const el of faces) {
  const key = await el.getAttribute('data-vc-face');
  if (seen.has(key)) continue;            // packages ship duplicate face nodes
  seen.add(key);                          // (one for preview, one for print)

  const items = await el.evaluate((root, bleedW) => {
    const r0 = root.getBoundingClientRect();
    const pxmm = r0.width / bleedW;       // the face's own scale, measured
    const out = [];
    for (const n of root.querySelectorAll('*')) {
      if (n.tagName === 'IMG' || n.tagName === 'CANVAS' || n.tagName === 'SVG') continue;
      const own = [...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim().length);
      if (!own) continue;
      const cs = getComputedStyle(n);
      if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
      const r = n.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      out.push({
        cls: (typeof n.className === 'string' && n.className) || n.tagName,
        text: n.textContent.trim().replace(/\s+/g, ' ').slice(0, 44),
        x: (r.x - r0.x) / pxmm, y: (r.y - r0.y) / pxmm,
        r: (r.right - r0.x) / pxmm, b: (r.bottom - r0.y) / pxmm,
      });
    }
    return out;
  }, BLEED_W);

  console.log(`\n── ${key} ──  safe box x ${SAFE}..${(BLEED_W - SAFE).toFixed(2)}, `
    + `y ${SAFE}..${(BLEED_H - SAFE).toFixed(2)} mm`);
  for (const i of items) {
    const bad = [];
    if (i.x < SAFE - 0.01) bad.push(`left ${i.x.toFixed(2)}mm`);
    if (i.y < SAFE - 0.01) bad.push(`top ${i.y.toFixed(2)}mm`);
    if (i.r > BLEED_W - SAFE + 0.01) bad.push(`right ${(BLEED_W - i.r).toFixed(2)}mm from edge`);
    if (i.b > BLEED_H - SAFE + 0.01) bad.push(`bottom ${(BLEED_H - i.b).toFixed(2)}mm from edge`);
    if (bad.length) violations.push({ face: key, ...i, bad });
    console.log(`  ${bad.length ? '!' : ' '} ${i.x.toFixed(2).padStart(6)} ${i.y.toFixed(2).padStart(6)}`
      + ` → ${i.r.toFixed(2).padStart(6)} ${i.b.toFixed(2).padStart(6)}   `
      + `${String(i.cls).slice(0, 13).padEnd(13)} ${i.text}`);
  }
}

await browser.close();

console.log('\n── inside the trim margin ──');
if (!violations.length) console.log('  none');
for (const v of violations) console.log(`  ${v.face} .${v.cls}: ${v.bad.join('; ')}  «${v.text}»`);
process.exit(violations.length ? 1 : 0);
