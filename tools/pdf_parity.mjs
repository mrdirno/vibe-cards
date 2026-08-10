/* Parity test: src/web/pdf.js must place ink exactly where src/pdfwriter.py does.
 *
 * This is the eval that guards the only thing in the web build that can ruin a
 * physical card. It is not a unit test of the JS in isolation — it diffs the JS
 * against the Python that has been measured against real printed output, so a
 * drift in either one fails here.
 *
 * It earned its place immediately: the first version of the port had 90° and
 * 270° swapped (sin(-90) is -1, not +1). Nothing on screen would have shown it;
 * the cards would have come out of the tray upside down.
 *
 *   node tools/pdf_parity.mjs        # from the repo root
 *
 * Exit 0 = identical. Exit 1 = a case diverged, printed below.
 */
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const require = createRequire(import.meta.url);
const PDF = require(path.join(root, 'src/web/pdf.js'));

// Real geometry: the two measured tray slots, the full page, and every rotation.
const CASES = [
  [3.82, 2.15, 85.6, 53.98, 120, 0],      // top slot, as shipped
  [3.82, 62.20, 85.6, 53.98, 120, 0],     // bottom slot
  [10, 20, 85.6, 53.98, 120, 90],
  [10, 20, 85.6, 53.98, 120, 180],
  [10, 20, 85.6, 53.98, 120, 270],
  [0, 0, 120, 120, 120, 0],               // full-bleed page
  [-2, -2, 85.6, 53.98, 120, 0],          // bleed off the top-left edge
];

const js = {
  mm_to_pt_1: PDF.fmt(PDF.mmToPt(1)),
  page120: PDF.fmt(PDF.mmToPt(120)),
  cases: CASES.map((c) => ({ args: c, m: PDF.placementMatrix(...c).map(PDF.fmt) })),
};

const py = JSON.parse(execFileSync('python3', ['-c', `
import sys, json
sys.path.insert(0, ${JSON.stringify(path.join(root, 'src'))})
import pdfwriter as P
cases = ${JSON.stringify(CASES)}
print(json.dumps({
  "mm_to_pt_1": P._fmt(P.mm_to_pt(1)),
  "page120": P._fmt(P.mm_to_pt(120)),
  "cases": [{"args": c, "m": [P._fmt(v) for v in P._placement_matrix(*c)]} for c in cases],
}))
`], { encoding: 'utf8' }));

let failed = 0;
if (js.mm_to_pt_1 !== py.mm_to_pt_1 || js.page120 !== py.page120) {
  console.log(`FAIL units: js ${js.mm_to_pt_1}/${js.page120} vs py ${py.mm_to_pt_1}/${py.page120}`);
  failed++;
}
js.cases.forEach((c, i) => {
  const p = py.cases[i];
  const same = c.m.join(' ') === p.m.join(' ');
  if (!same) failed++;
  console.log(`${same ? '  ok  ' : '  FAIL'} [${c.args.join(', ')}]  ${c.m.join(' ')}`);
  if (!same) console.log(`        pdfwriter.py -> ${p.m.join(' ')}`);
});

console.log(failed
  ? `\n${failed} case(s) diverged from pdfwriter.py — the web build would misplace ink.`
  : `\nAll ${js.cases.length} placements byte-identical to pdfwriter.py.`);
process.exit(failed ? 1 : 0);
