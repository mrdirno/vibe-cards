/* Rasterise both faces and MEASURE them, because looking is not enough on its own.
 *
 * Chromium floors a screenshot clip to whole CSS pixels before applying the
 * device scale factor, so an element sized in CSS mm can never emit 2066 px at
 * dsf 6.25 — only 330*6.25 = 2063 or 331*6.25 = 2069. The face box is therefore
 * the bleed grid in device pixels at dsf 1, and the clip is that same integer.
 *
 * The measurement pass is the point: it reports every text box in millimetres
 * against the 3.95 mm safe zone and against the left edge of the photo band, so
 * "no glyph overlaps the image" is a number, not an impression.
 */
import { chromium } from '/Volumes/dual/persona500/node_modules/playwright/index.mjs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, '..', 'package', 'index.html');
const OUTDIR = process.argv[2] || path.join(HERE, '..', 'designs_preview');

const W = 2066, H = 1319, DPI = 600, PXMM = DPI / 25.4, SAFE = 3.95;

const browser = await chromium.launch();
// Tall enough for both faces to be inside the viewport: a clip that reaches past
// it silently returns a short image (the back came back 2066x201 once), which is
// the kind of failure that looks like a render bug and is a viewport bug.
const page = await browser.newPage({ viewport: { width: 2200, height: 2900 }, deviceScaleFactor: 1 });
await page.goto('file://' + PAGE, { waitUntil: 'networkidle' });

const report = { faces: [], violations: [] };

for (const which of ['front', 'back']) {
  const el = await page.$(`[data-vc-face="${which}"]`);
  const box = await el.boundingBox();
  await page.screenshot({
    path: path.join(OUTDIR, `${which}_87.5x55.88mm_bleed_600dpi.png`),
    clip: { x: Math.round(box.x), y: Math.round(box.y), width: W, height: H },
  });

  // Every leaf element that carries visible text, in mm relative to the face.
  const items = await el.evaluate((root, safe) => {
    const r0 = root.getBoundingClientRect();
    const pxmm = r0.width / 87.4607;   // face width in mm on the 600 dpi grid
    const out = [];
    for (const n of root.querySelectorAll('*')) {
      if (n.tagName === 'IMG') continue;
      const hasOwnText = [...n.childNodes].some(
        c => c.nodeType === 3 && c.textContent.trim().length);
      if (!hasOwnText) continue;
      const r = n.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      out.push({
        cls: n.className || n.tagName,
        text: n.textContent.trim().replace(/\s+/g, ' ').slice(0, 46),
        x: (r.x - r0.x) / pxmm, y: (r.y - r0.y) / pxmm,
        r: (r.right - r0.x) / pxmm, b: (r.bottom - r0.y) / pxmm,
      });
    }
    return out;
  }, SAFE);

  const wmm = W / PXMM, hmm = H / PXMM;
  const bandX = wmm - 39.4;                      // photo band left edge, front only
  for (const it of items) {
    const bad = [];
    if (it.x < SAFE - 0.01) bad.push(`left ${it.x.toFixed(2)}mm`);
    if (it.y < SAFE - 0.01) bad.push(`top ${it.y.toFixed(2)}mm`);
    if (it.r > wmm - SAFE + 0.01) bad.push(`right ${(wmm - it.r).toFixed(2)}mm from edge`);
    if (it.b > hmm - SAFE + 0.01) bad.push(`bottom ${(hmm - it.b).toFixed(2)}mm from edge`);
    if (which === 'front' && it.r > bandX) bad.push(`OVERLAPS PHOTO by ${(it.r - bandX).toFixed(2)}mm`);
    if (bad.length) report.violations.push({ face: which, ...it, bad });
  }
  report.faces.push({ face: which, items });
}

await browser.close();

for (const f of report.faces) {
  console.log(`\n── ${f.face} ──  (safe box x ${SAFE}..${(W / PXMM - SAFE).toFixed(2)}, y ${SAFE}..${(H / PXMM - SAFE).toFixed(2)} mm)`);
  for (const i of f.items) {
    console.log(`  ${i.x.toFixed(2).padStart(6)} ${i.y.toFixed(2).padStart(6)}  →`
      + ` ${i.r.toFixed(2).padStart(6)} ${i.b.toFixed(2).padStart(6)}   ${String(i.cls).padEnd(8)} ${i.text}`);
  }
}
console.log('\n── violations ──');
if (!report.violations.length) console.log('  none');
for (const v of report.violations) console.log(`  ${v.face} .${v.cls}: ${v.bad.join('; ')}  «${v.text}»`);
process.exit(report.violations.length ? 1 : 0);
