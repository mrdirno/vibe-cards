/**
 * THE REACHABILITY GATE — a control that is on the screen is not the same as a
 * control you can use.
 *
 *   node tools/verify_phone_reach.mjs [base-url]
 *   node tools/verify_phone_reach.mjs https://mrdirno.github.io/vibe-cards
 *
 * tools/verify_mobile.mjs already measures the page at rest: overflow, tap
 * target size, the viewport meta. Everything it checks was green on /studio/
 * while two of the app's own controls did nothing on a phone, because both
 * defects live in state that gate never enters — a panel is only wrong once it
 * is OPENED.
 *
 *   · "Start from a template" focused a <select> that sits in the Card block of
 *     the left rail. On a phone that rail is a sheet, down by default, so the
 *     select was inside a display:none subtree: focus() landed on nothing,
 *     showPicker() threw InvalidStateError, and the .is-pinged fallback animated
 *     a border with no pixels behind it. Measured 0x0 in both engines.
 *   · "Wish it better" opens a popover anchored `right:0` to a wrapper the width
 *     of its own button. That is correct on a desktop bar pinned to the right
 *     edge and wrong here: at 390px the panel's left edge was at -186.
 *
 * Both were reported from a phone, 95 minutes apart, as "nothing happens" and
 * "opens off the viewable window". Neither is visible to a static sweep, and
 * neither is visible to a screenshot either — the second cut of the fix put the
 * Send button on screen and underneath the dock. So the assertions here are
 * about REACHING things:
 *
 *   A  tapping the empty state's template button leaves the picker on screen
 *   B  the wish popover is fully inside the viewport
 *   C  so is the Open menu — same geometry, same defect, reached less often
 *   D  neither one makes the page scroll sideways
 *   E  Send answers elementFromPoint, so the tap that submits a wish is not
 *      swallowed by the dock or by a raised rail's scrim
 *
 * E is the one that earns this file. A rect inside the viewport is necessary and
 * is not sufficient; the only honest question is whether the person's finger
 * reaches the element or something on top of it.
 *
 * WebKit first, because the original defect is a Safari one — showPicker() does
 * not exist there — and Chromium alone would have shown a working picker on a
 * screen where nobody has Chromium. Chromium runs too: the popover half fails on
 * both, and a check that passes on one engine has measured one engine.
 *
 * Playwright is optional and is NOT a dependency of this project. Without it
 * this prints SKIPPED and exits 0 — and SKIPPED is not a pass, which the output
 * says.
 */

import { createServer } from 'http';
import { readFileSync, existsSync, statSync } from 'fs';
import { extname, join } from 'path';
import { fileURLToPath } from 'url';

const REPO = fileURLToPath(new URL('../', import.meta.url));
const SITE = REPO + '_site_mobile';

/* The same four widths verify_mobile.mjs uses, for the same reason: 320 is the
 * smallest phone still in service, 390 the current iPhone, 430 the largest. */
const WIDTHS = [320, 360, 390, 430];
const BASE = (process.argv.slice(2).find((a) => !a.startsWith('--')) || '').replace(/\/$/, '');

let pw;
try {
  const req = (await import('module')).createRequire(import.meta.url);
  pw = req('playwright');
} catch {
  console.log('\nSKIPPED — playwright is not installed, so nothing was measured.');
  console.log('  npm i -D playwright && npx playwright install chromium webkit');
  process.exit(0);
}

let origin, server = null;
if (BASE) {
  origin = BASE;
} else {
  if (!existsSync(SITE)) {
    console.log(`\nNo built site at ${SITE}.\n  python3 tools/build_site.py _site_mobile\n`);
    process.exit(1);
  }
  /* Over http, never file://. The studio boots against a backend and a file://
   * page has a null origin; verify_mobile.mjs records what that cost — years of
   * green reports measuring a page that had not started. */
  const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
                 '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml',
                 '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2' };
  server = createServer((req, res) => {
    let p = join(SITE, decodeURIComponent(req.url.split('?')[0]));
    if (existsSync(p) && statSync(p).isDirectory()) p = join(p, 'index.html');
    if (!existsSync(p)) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'content-type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(readFileSync(p));
  });
  await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
  origin = `http://127.0.0.1:${server.address().port}`;
}

/* Runs INSIDE the page. `visible` accepts position:fixed explicitly — a fixed
 * element has no offsetParent and is on screen, and treating that as hidden is
 * how a correct sheet would be reported as a bug. */
const RECT = (sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { missing: false, hidden: !!el.hidden,
           visible: !!el.offsetParent || getComputedStyle(el).position === 'fixed',
           left: Math.round(r.left), right: Math.round(r.right),
           top: Math.round(r.top), bottom: Math.round(r.bottom),
           w: Math.round(r.width), h: Math.round(r.height),
           vw: document.documentElement.clientWidth, vh: window.innerHeight,
           sheet: document.body.dataset.sheet || '(none)' };
};
const HIT = (sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { top: Math.round(r.top), h: Math.round(r.height),
           on: hit ? (hit.id || hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).trim().split(/\s+/)[0] : '')) : null,
           ok: !!hit && (hit === el || el.contains(hit)) };
};
const inside = (r) => r && r.left >= -0.5 && r.right <= r.vw + 0.5 && r.top >= -0.5 && r.bottom <= r.vh + 0.5;

const engines = [['webkit', pw.webkit], ['chromium', pw.chromium]];
const fails = [];
let ran = 0;

console.log(`\nPHONE REACHABILITY — ${origin}/studio/`);

for (const [name, engine] of engines) {
  let browser;
  try { browser = await engine.launch(); }
  catch (e) { console.log(`  ${name.padEnd(9)} unavailable — ${String(e.message).split('\n')[0]}`); continue; }

  for (const W of WIDTHS) {
    /* isMobile + hasTouch so `(pointer: coarse)` matches — the query a fix hangs
     * off. A narrow desktop window is not a phone. */
    const ctx = await browser.newContext({ viewport: { width: W, height: 844 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    const bits = [];
    try {
      await page.goto(origin + '/studio/', { waitUntil: 'load' });
      await page.waitForTimeout(1100);

      // A — the empty state's template button must land you on the picker.
      await page.locator('#ceTemplate').click();
      await page.waitForTimeout(450);
      const a = await page.evaluate(RECT, '#templateSel');
      const aOK = a && a.visible && a.w > 0 && a.h > 0 && a.top >= 0 && a.bottom <= a.vh + 0.5;
      bits.push(`A ${aOK ? 'ok' : 'FAIL'}`);
      if (!aOK) fails.push(`${name} @${W}px: "Start from a template" leaves #templateSel unreachable — ${a ? `${a.w}x${a.h} at y=${a.top}, sheet=${a.sheet}` : 'element missing'}`);

      /* The Card sheet is left UP on purpose. Tapping Wish with a rail raised is
       * a real path and it is the one where the rail's scrim covers Send. */

      // B — the wish popover, fully inside the viewport.
      await page.locator('#btnWish').click();
      await page.waitForTimeout(350);
      const b = await page.evaluate(RECT, '#wishPop');
      const bOK = b && !b.hidden && inside(b);
      bits.push(`B ${bOK ? 'ok' : 'FAIL'}`);
      if (!bOK) fails.push(`${name} @${W}px: #wishPop outside the viewport — L${b?.left} R${b?.right} T${b?.top} B${b?.bottom} in ${W}x844`);

      // E — and Send actually receives the tap.
      const e = await page.evaluate(HIT, '#wishSend');
      bits.push(`E ${e && e.ok ? 'ok' : 'FAIL'}`);
      if (!e || !e.ok) fails.push(`${name} @${W}px: #wishSend is covered — the tap lands on "${e?.on}" (button at y=${e?.top})`);

      const d1 = await page.evaluate(() => document.documentElement.scrollWidth);

      // C — the Open menu is the same geometry and was the same defect.
      await page.locator('#btnWish').click();
      await page.waitForTimeout(200);
      await page.locator('#btnOpen').click();
      await page.waitForTimeout(350);
      const c = await page.evaluate(RECT, '#openMenu');
      const cOK = c && (c.hidden || inside(c));
      bits.push(`C ${cOK ? 'ok' : 'FAIL'}`);
      if (!cOK) fails.push(`${name} @${W}px: #openMenu outside the viewport — L${c?.left} R${c?.right} T${c?.top} B${c?.bottom} in ${W}x844`);

      // D — no sideways scroll in either open state.
      const d2 = await page.evaluate(() => document.documentElement.scrollWidth);
      const dOK = d1 <= W + 0.5 && d2 <= W + 0.5;
      bits.push(`D ${dOK ? 'ok' : 'FAIL'}`);
      if (!dOK) fails.push(`${name} @${W}px: horizontal scroll with a panel open (${d1}/${d2} > ${W})`);

      ran++;
      console.log(`  ${name.padEnd(9)} @${String(W).padStart(3)}px  ${bits.join('  ')}`);
    } catch (err) {
      fails.push(`${name} @${W}px: harness error — ${String(err.message).split('\n')[0]}`);
      console.log(`  ${name.padEnd(9)} @${String(W).padStart(3)}px  ERROR`);
    }
    await ctx.close();
  }
  await browser.close();
}

if (server) server.close();

if (!ran) {
  console.log('\nSKIPPED — no browser engine ran, so nothing was measured.');
  process.exit(0);
}
if (fails.length) {
  console.log(`\n${fails.length} finding(s):`);
  for (const f of fails) console.log('  - ' + f);
  process.exit(1);
}
console.log(`\nReachable at ${WIDTHS.join(', ')}px — the picker opens, both panels land inside the screen, and Send takes the tap.`);
