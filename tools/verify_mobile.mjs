/**
 * THE MOBILE GATE — a page opened by tapping a card is opened on a phone.
 *
 *   node tools/verify_mobile.mjs [base-url]
 *   node tools/verify_mobile.mjs https://mrdirno.github.io/vibe-cards
 *
 * Every page in this project is reached one way: someone taps a printed card with
 * their phone. There is no desktop entry point, no search traffic, no homepage.
 * So "mobile friendly" is not a nice-to-have here, it is the only mode that exists,
 * and a defect that only appears at 320px is a defect on the actual product.
 *
 * ORIGIN, since ideas travel and credit should: the checks below are a fresh
 * implementation of the mobile-watertight gate that the Field Toolkit and Collage
 * Studio evolved in the nested-resonance-memory-archive. That gate is GPL-3.0 and
 * this repository is MIT, so none of its code is copied — what is inherited is the
 * reasoning, which is the valuable part anyway:
 *
 *   · Name the CULPRIT, not just the symptom. "Something overflows by 14px" costs
 *     an hour; ".deck at 14px over" costs a minute.
 *   · Exempt links that sit inline in a sentence from the 44px rule. WCAG 2.5.8
 *     does, and it is right to — a link inside a paragraph cannot be 44px without
 *     wrecking the prose. Without the exemption the gate reports every body link
 *     on every page, becomes noise, and a noisy gate is one people stop running.
 *   · Do not fake pinch-zoom. Pinch does not change the layout viewport, so
 *     resizing cannot simulate it and neither can spoofing visualViewport.scale —
 *     both measure nothing new, and a check that measures nothing new is worse
 *     than no check, because it reports green. Reproduce what ACTUALLY breaks in
 *     that family: a layout pinned in fixed px meeting text it did not budget for.
 *
 * WHAT IT MEASURES
 *   · horizontal overflow at four real phone widths, with the offending element
 *   · tap targets under 44px, split into hard (buttons, links you hit blind) and
 *     soft (fields you aim at deliberately) — collapsing them makes it unusable
 *   · the same overflow re-checked with the root font size bumped, the way the OS
 *     accessibility setting bumps it
 *   · the viewport meta itself: user-scalable=no is a page that cannot be zoomed,
 *     which is the same complaint one layer up
 *
 * Playwright is optional and is NOT a dependency of this project. Without it this
 * prints SKIPPED and exits 0 — and SKIPPED is not a pass, which the output says.
 */

import { readdirSync, existsSync, statSync } from 'fs';
import { fileURLToPath } from 'url';

const REPO = fileURLToPath(new URL('../', import.meta.url));

/* 320 is the smallest phone still in service, 360 the median Android, 390 the
 * current iPhone, 430 the largest. Watertight at all four is watertight. */
const WIDTHS = [320, 360, 390, 430];
const MIN_TAP = 44;
const FONT_BUMP = 22;   // px root, ~137% of 16 — a common accessibility setting

const args = process.argv.slice(2);
const BASE = (args.find(a => !a.startsWith('--')) || '').replace(/\/$/, '');

let chromium;
try {
  const req = (await import('module')).createRequire(import.meta.url);
  ({ chromium } = req('playwright'));
} catch {
  try {
    const req = (await import('module')).createRequire(
      '/Volumes/dual/nested-resonance-memory-archive/tools/collage-studio/package.json');
    ({ chromium } = req('playwright'));
  } catch { /* absent */ }
}

if (!chromium) {
  console.log('\nSKIPPED — playwright is not installed. This is NOT a pass.\n' +
              '  npm i -D playwright && npx playwright install chromium\n');
  process.exit(0);
}

/* Which pages? The BUILT artifact, because that is what deploys — the source has
 * markers in it that the builder substitutes, and measuring source would measure
 * a page nobody visits. */
function builtPages(dir) {
  const out = [];
  (function walk(d, rel) {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = d + '/' + e.name;
      if (e.isDirectory()) walk(p, rel + e.name + '/');
      else if (e.name.endsWith('.html')) out.push(rel + e.name);
    }
  })(dir, '');
  return out.sort();
}

const SITE = REPO + '_site_mobile';
let pages, origin, server = null;
if (BASE) {
  origin = BASE;
  pages = ['/', '/gt/', '/studio/'];
} else {
  if (!existsSync(SITE)) {
    console.log(`\nNo built site at ${SITE}.\n  python3 tools/build_site.py _site_mobile\n`);
    process.exit(1);
  }
  /* SERVED OVER HTTP, NOT file://, AND THIS IS NOT A DETAIL.
   *
   * This gate read the built artifact off disk for its whole life, which is
   * correct for the node pages -- they are static documents and file:// renders
   * them exactly as a server would. It is NOT correct for /studio/, which is an
   * application: it boots by fetching its own profiles and capabilities, and
   * under file:// every one of those requests is a cross-origin request to a
   * null origin and fails. Measured:
   *
   *     file://   canvas 0x0    body 780px    0 view tabs
   *     http://   canvas 374x255  body 1116px   4 view tabs
   *
   * So for years this gate reported /studio/ watertight at all four widths while
   * measuring a page that had never assembled. Nothing overflowed because
   * nothing had been laid out; every tap target passed because there were no tap
   * targets. The moment it was served properly the same page failed on a 34px
   * control and on an entire landmark nothing could scroll to.
   *
   * A green check on a page that never rendered is worse than no check, which is
   * this file's own rule from its header, applied to the file itself.
   *
   * node:http and node:fs, so this stays a zero-dependency gate. Port 0 lets the
   * OS pick, so two runs cannot collide. */
  const { createServer } = await import('node:http');
  const { readFileSync } = await import('node:fs');
  const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css',
                  '.json':'application/json', '.png':'image/png', '.webp':'image/webp',
                  '.svg':'image/svg+xml', '.txt':'text/plain', '.md':'text/markdown' };
  server = createServer((req, res) => {
    // Query and hash are not path. Decode once, then refuse any path that still
    // climbs -- this serves a directory to a browser and nothing else.
    let rel = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
    if (rel.includes('..')) { res.writeHead(400); return res.end('no'); }
    if (rel.endsWith('/')) rel += 'index.html';
    try {
      const body = readFileSync(SITE + rel);
      const dot = rel.lastIndexOf('.');
      res.writeHead(200, { 'content-type': TYPES[rel.slice(dot)] || 'application/octet-stream' });
      res.end(body);
    } catch { res.writeHead(404); res.end('not found'); }
  });
  await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
  origin = `http://127.0.0.1:${server.address().port}`;
  pages = builtPages(SITE).map(p => '/' + p);
}

/* Runs INSIDE the page. Returns findings and never throws — a gate that dies on
 * one page tells you nothing about the others. */
const MEASURE = (MIN_TAP) => {
  const out = { overflow: null, hard: [], soft: [], stranded: [] };
  const de = document.documentElement;
  const vw = de.clientWidth;

  if (de.scrollWidth > vw + 0.5) {
    let worst = null;
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.left >= vw) continue;                      // wholly off-screen, not the cause
      const over = Math.round(r.right - vw);
      if (over <= 0) continue;
      let depth = 0;
      for (let e = el; e.parentElement; e = e.parentElement) depth++;
      if (!worst || over > worst.over || (over === worst.over && depth > worst.depth)) {
        const cls = (el.className && typeof el.className === 'string')
          ? '.' + el.className.trim().split(/\s+/).join('.') : '';
        worst = { over, depth, sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls };
      }
    }
    out.overflow = { by: Math.round(de.scrollWidth - vw), culprit: worst };
  }

  const seen = new Set();
  for (const el of document.querySelectorAll(
    'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button]')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    // WCAG 2.5.8 inline-in-a-sentence exemption. See the header for why.
    if (el.tagName === 'A' && cs.display === 'inline' && el.closest('p, li, figcaption, footer, .note, .lede')) continue;
    const lab = el.closest('label');
    const box = (lab && lab.getBoundingClientRect().height >= r.height) ? lab.getBoundingClientRect() : r;
    const short = Math.min(box.width, box.height);
    if (short >= MIN_TAP - 0.5) continue;
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\s+/)[0] : '';
    const sel = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls;
    const key = sel + '|' + Math.round(short);
    if (seen.has(key)) continue;
    seen.add(key);
    const hit = { sel, short: Math.round(short * 10) / 10, text: (el.textContent || '').trim().slice(0, 28) };
    // Hit blind vs aimed at. Collapsing these makes the gate unrunnable.
    const soft = /^(input|select|textarea)$/.test(el.tagName.toLowerCase())
      && !/^(checkbox|radio|button|submit)$/.test(el.type || '');
    (soft ? out.soft : out.hard).push(hit);
  }

  /* STRANDED CONTROLS — a control that is off the screen and that NO scroll can
   * bring back. This is the check that was missing, and the omission had a
   * price: Card Studio's whole Properties panel sat at y=1099 on an 844px phone
   * under html,body{overflow:hidden}, a finger dragged across the page moved it
   * 0px, and this gate reported the page watertight at all four widths. It was
   * telling the truth about what it measured. Nothing overflowed sideways and
   * every one of those unreachable buttons was a compliant 44px.
   *
   * Overflow and tap size both ask "is this control WELL FORMED". Neither asks
   * "can a person GET to it", and on a phone that is the question that decides
   * whether a feature exists at all.
   *
   * Off-screen is not the fault; unreachable is. A closed drawer, an inactive
   * tab panel, a menu waiting to open are all off-screen by design and all fine.
   * What separates them is that something can bring them back. So the test is
   * the ancestor walk, not the rectangle: if any ancestor scrolls, or the root
   * scrolls, the control is reachable and this says nothing.
   *
   * display:none and visibility:hidden are skipped, which is also the honest way
   * to park a panel off-screen — hidden from the pointer AND from the tab order.
   * A drawer that is merely translated away is still tabbable, so it would be
   * reported here, and that report would be correct. */
  const scrolls = (n, cs) =>
    (/(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 1) ||
    (/(auto|scroll)/.test(cs.overflowX) && n.scrollWidth > n.clientWidth + 1);
  const bd = document.body;
  const rootScrolls =
    (de.scrollHeight > de.clientHeight + 1 && !/hidden|clip/.test(getComputedStyle(de).overflowY)) ||
    (bd.scrollHeight > bd.clientHeight + 1 && !/hidden|clip/.test(getComputedStyle(bd).overflowY));
  const vh = de.clientHeight;
  const strandedSeen = new Set();
  /* Landmarks as well as controls, because the first version of this check found
   * nothing on the page that motivated it. Card Studio's Properties panel is an
   * <aside> that is EMPTY until an element is selected -- it holds one sentence
   * of placeholder text and not a single button -- so a control-only sweep
   * correctly reported zero stranded controls on a panel that was completely
   * unreachable. The unreachable unit was the region, not a widget inside it.
   * A whole landmark parked past the fold with nothing able to scroll to it is
   * the defect whether or not it happens to be populated at that moment. */
  for (const el of document.querySelectorAll(
    'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button],' +
    'aside, nav, main, form, [role=region]')) {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.hidden) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    // A landmark has to be big enough to be worth reporting; a control of any
    // size counts, because you were meant to be able to press it.
    const isLandmark = /^(aside|nav|main|form)$/.test(el.tagName.toLowerCase());
    if (isLandmark && r.height < 40) continue;
    if (r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0) continue;   // on screen
    let reachable = rootScrolls;
    for (let n = el.parentElement; n && !reachable; n = n.parentElement) {
      if (scrolls(n, getComputedStyle(n))) reachable = true;
    }
    if (reachable) continue;
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\s+/)[0] : '';
    const sel = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls;
    if (strandedSeen.has(sel)) continue;
    strandedSeen.add(sel);
    out.stranded.push({ sel, top: Math.round(r.top), text: (el.textContent || '').trim().slice(0, 28) });
  }
  return out;
};

const fails = [];
const warns = [];
const browser = await chromium.launch();

console.log(`\nMOBILE GATE — ${origin}`);
for (const page of pages) {
  const url = origin + page;
  console.log(`\n${page}`);
  for (const w of WIDTHS) {
    /* A REAL touch device, not a narrow desktop window. isMobile+hasTouch make
     * `(pointer: coarse)` match, which is the query a fix should hang off — a
     * mouse at 400px genuinely does not need 44px targets, and forcing them there
     * would wreck a dense desktop UI to fix a phone problem. */
    const ctx = await browser.newContext({
      viewport: { width: w, height: 780 }, deviceScaleFactor: 2,
      isMobile: true, hasTouch: true,
    });
    const p = await ctx.newPage();
    try {
      const res = await p.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
      if (res && res.status() >= 400) { fails.push(`${page} @${w}: HTTP ${res.status()}`); await ctx.close(); continue; }
    } catch (e) {
      fails.push(`${page} @${w}: ${e.message.split('\n')[0]}`); await ctx.close(); continue;
    }
    await p.waitForTimeout(250);

    const m = await p.evaluate(MEASURE, MIN_TAP);
    const bits = [];
    if (m.overflow) {
      const c = m.overflow.culprit;
      fails.push(`${page} @${w}px: overflows by ${m.overflow.by}px — ${c ? c.sel : 'culprit not found'}`);
      bits.push(`OVERFLOW ${m.overflow.by}px (${c ? c.sel : '?'})`);
    }
    for (const t of m.hard) {
      fails.push(`${page} @${w}px: tap target ${t.sel} is ${t.short}px ("${t.text}") — needs ${MIN_TAP}`);
    }
    if (m.hard.length) bits.push(`${m.hard.length} tap target(s) < ${MIN_TAP}px`);
    for (const t of m.stranded) {
      fails.push(`${page} @${w}px: ${t.sel} ("${t.text}") sits at y=${t.top} on a ${
        780}px screen and NOTHING scrolls to it — the control is on the page and out of reach`);
    }
    if (m.stranded.length) bits.push(`${m.stranded.length} unreachable control(s)`);
    for (const t of m.soft) warns.push(`${page} @${w}px: field ${t.sel} is ${t.short}px`);

    // The text-bump family: fixed-px layout meeting text it did not budget for.
    await p.addStyleTag({ content: `html{font-size:${FONT_BUMP}px}` });
    await p.waitForTimeout(150);
    const b = await p.evaluate(MEASURE, MIN_TAP);
    if (b.overflow && !m.overflow) {
      const c = b.overflow.culprit;
      fails.push(`${page} @${w}px with ${FONT_BUMP}px text: overflows by ${b.overflow.by}px — ${c ? c.sel : '?'}`);
      bits.push(`OVERFLOW when text is bumped (${c ? c.sel : '?'})`);
    }

    console.log(`  ${w}px  ${bits.length ? '✗ ' + bits.join(' · ') : '✓'}`);
    await ctx.close();
  }

  // The viewport meta, once per page — it does not vary by width.
  const ctx = await browser.newContext({ viewport: { width: 390, height: 780 } });
  const p = await ctx.newPage();
  try {
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    const vp = await p.evaluate(() => {
      const m = document.querySelector('meta[name=viewport]');
      return m ? m.getAttribute('content') : null;
    });
    if (!vp) fails.push(`${page}: no viewport meta — the page will render at desktop width and be zoomed out`);
    else if (/user-scalable\s*=\s*no|maximum-scale\s*=\s*1\b/.test(vp))
      fails.push(`${page}: viewport blocks zoom (${vp}) — a reader who needs to zoom cannot`);
  } catch { /* already reported above */ }
  await ctx.close();
}
await browser.close();
// Closed on every exit path below, or node keeps the process alive on the
// listening socket and the gate hangs instead of reporting.
if (server) server.close();

console.log('');
if (fails.length) {
  console.log(`FAILED — ${fails.length}:`);
  for (const f of fails) console.log('  - ' + f);
  if (warns.length) console.log(`\n${warns.length} soft (fields, reported not fatal)`);
  process.exit(1);
}
if (warns.length) {
  console.log(`${warns.length} soft finding(s):`);
  for (const w of warns) console.log('  - ' + w);
}
console.log(`Watertight at ${WIDTHS.join(', ')}px — no overflow, every blind tap target >= ${MIN_TAP}px.`);
