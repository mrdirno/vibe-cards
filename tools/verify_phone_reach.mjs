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
 *   F  the face chip says which side of the card is showing, and flipping it
 *      changes the PIXELS on the canvas, not just its own label
 *   G  and a tap on the card does the same thing, which is what a card does
 *   H  a FINGER can move an element on the card — Chromium only, see below
 *   I  on the landing page, one slide per CARD rather than one per side, and a tap
 *      turns the card over
 *   J  and the card does NOT turn over when the gesture was not a tap — a pinch, a
 *      swipe, or a pinch begun mid-drag. Chromium only, same reason as H.
 *   K  nor when the pointer is a MOUSE in a narrow window
 *
 * E is the one that earns this file. A rect inside the viewport is necessary and
 * is not sufficient; the only honest question is whether the person's finger
 * reaches the element or something on top of it.
 *
 * F and G are the same argument applied to state rather than geometry. The
 * report that asked for them ("the page should be half card then half features
 * … tapping it shows the rear") was half already true: the sheet stops at 42dvh
 * so the card stays above it. The other half had no implementation at all — the
 * front/back control is #faceSeg, which lives in the Card sheet, so a phone user
 * could not see which side was on screen, let alone change it, without opening a
 * panel over the card. Both assertions compare the canvas bitmap before and
 * after, because a chip reading "Back" over a canvas still drawing the front is
 * exactly the class of failure this file exists to catch.
 *
 * H IS DECLARED PARTIAL AND RUNS ON CHROMIUM ONLY. A drag by finger needs real
 * touch input, and Playwright's touchscreen can tap but not drag — the only route
 * is CDP's Input.dispatchTouchEvent, which exists for Chromium and not for WebKit.
 * A TouchEvent dispatched from JavaScript is not a substitute: it is untrusted, so
 * the browser generates no pointer events from it and the check would measure the
 * harness. So H prints "skip" on WebKit and says why, because a check that quietly
 * runs on half the engines reads as a check that ran.
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

/* The same two-step lookup verify_mobile.mjs uses, and for the same reason: this
 * repo has no node_modules on purpose (stdlib only, no install step), so a local
 * install is tried first and a sibling checkout that HAS playwright is tried second.
 * Without the fallback this file skipped while verify_mobile.mjs beside it measured,
 * on the same machine, in the same run — which is how a gate ends up silently absent
 * from the only script that decides work is finished. */
let pw;
for (const from of [import.meta.url,
                    '/Volumes/dual/nested-resonance-memory-archive/tools/collage-studio/package.json',
                    '/Volumes/dual/persona500/package.json']) {
  try {
    pw = (await import('module')).createRequire(from)('playwright');
    break;
  } catch { /* try the next one */ }
}
if (!pw) {
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

/* WHAT THE CARD ACTUALLY LOOKS LIKE RIGHT NOW, as one number. A label is a claim
 * about the canvas; this is the canvas. Cheap 32-bit rolling hash of the PNG the
 * canvas exports — the comparison only ever asks "same or different", so the hash
 * quality that matters is that identical states agree, which byte-identical PNGs
 * do. Wrapped because toDataURL throws on a canvas tainted by a cross-origin
 * image, and a thrown harness is not a finding about the app. */
const SHOT = () => {
  const c = document.querySelector('#canvas');
  if (!c) return { err: 'no canvas' };
  try {
    const u = c.toDataURL('image/png');
    let h = 0;
    for (let i = 0; i < u.length; i++) h = (h * 31 + u.charCodeAt(i)) | 0;
    return { h, n: u.length, w: c.width, h2: c.height };
  } catch (e) { return { err: String(e.message).slice(0, 60) }; }
};
/* The centre of the CARD, not of the canvas: the canvas carries the mm rulers and
 * the bench padding as well, and "tap the card" has to mean the card. 85.6 x 53.98
 * is CR-80, and the card is drawn centred in the canvas below the rulers, so the
 * midpoint of the drawn card is what the tap needs. Returned in viewport
 * coordinates for page.touchscreen. */
const CARD_MID = () => {
  const c = document.querySelector('#canvas');
  if (!c) return null;
  const r = c.getBoundingClientRect();
  const RULER = 20, PAD = 16;             // app.js's own constants
  const x = r.left + RULER + (r.width - RULER - PAD) / 2;
  const y = r.top + RULER + (r.height - RULER - PAD) / 2;
  const on = document.elementFromPoint(x, y);
  return { x, y, on: on ? (on.id || on.tagName.toLowerCase()) : null };
};

/* Where to put the finger for H. This one asks the app for its own geometry, which
 * the rest of this file deliberately does not do — it is aiming, not asserting. The
 * verdict below is taken from the canvas bitmap and from the X readout a person can
 * see in the Properties panel; this only works out where the element is drawn so
 * the drag starts on it. app.js is a classic script, so its top-level declarations
 * are on the global object. */
const ELEM_MID = () => {
  const cv = document.querySelector('#canvas');
  if (!cv || typeof canvasGeom !== 'function' || typeof S !== 'object' || !S.doc) return null;
  const el = S.doc.faces[S.face].elements[0];
  if (!el) return { err: 'no element on this face' };
  const g = canvasGeom(), r = cv.getBoundingClientRect();
  return {
    x: r.left + g.ox + (el.x + el.w / 2) * g.p,
    y: r.top + g.oy + (el.y + el.h / 2) * g.p,
    mmPerPx: 1 / g.p,
  };
};
/* THE LANDING PAGE'S DECKS, counted and read. Two numbers per deck: how many
 * slides it holds and how many dots its pager has. One dot is one CARD — the page
 * says so — so slides above dots means a card is spending two slides on its two
 * sides, which is the "you save Realestate" half of the report, as a number.
 * Then which FACE is showing — asked as "is it drawn", not as an opacity. The first
 * cut of this read getComputedStyle().opacity and reported [1,1] for a card that
 * was turning over correctly, because opacity is still 1 on a display:none element
 * and the turn is a display swap (the backs keep loading="lazy" that way, so they
 * cost nothing until somebody asks for one). getClientRects() is empty for anything
 * with no box, whatever put it there, which is the question a reader is asking. */
const DECKS = () => Array.from(document.querySelectorAll('.rack')).map((rack) => {
  const deck = rack.querySelector('.deck'), dots = rack.querySelector('.dots');
  const first = deck && deck.querySelector('.card');
  const faces = first ? Array.from(first.querySelectorAll('img.face')) : [];
  /* DOES EACH CARD FIT ITS SLIDE. This is the measurement no gate in this repo was
   * making, and the hole it left is worth stating: verify_mobile.mjs measures
   * DOCUMENT overflow, and all of this happens INSIDE a scroll container that is
   * supposed to be wider than the screen, so the deck absorbed it silently.
   * Longer captions plus white-space:nowrap on a flex item whose min-width was still
   * `auto` made 10 of 12 cards render up to 128px (45%) wider than their slide at
   * 320px — artwork off both edges of the phone — and every check was green. */
  let over = 0, worst = 0, slide = 0;
  if (deck) {
    const cs = getComputedStyle(deck);
    slide = deck.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    deck.querySelectorAll('.card').forEach((c) => {
      const d = c.getBoundingClientRect().width - slide;
      if (d > 0.5) { over++; worst = Math.max(worst, d); }
    });
  }
  /* EVERY CARD, NOT THE FIRST ONE, and its two srcs COMPARED. This returned the
   * first card of each rack and threw the srcs away, and a mutation pass walked
   * straight through the hole three separate ways, each time with the run printing
   * "the gallery gives one slide per card": strip the turn-inputs from the second
   * rack only (7 of 12 cards unflippable), kill the flip for that rack in CSS, or
   * point every back at its own front so turning a card shows the identical image.
   * A check that samples one item out of twelve is a check on one item, and it must
   * say which twelve it looked at. */
  const cards = deck ? Array.from(deck.querySelectorAll('.card')).map((c) => {
    const f = Array.from(c.querySelectorAll('img.face'));
    return {
      faces: f.length,
      shown: f.map((x) => x.getClientRects().length > 0),
      srcs: f.map((x) => (x.getAttribute('src') || '').split('/').slice(-2).join('/')),
    };
  }) : [];
  return {
    slides: deck ? deck.children.length : 0,
    dots: dots ? dots.children.length : 0,
    facesOnFirstCard: faces.length,
    shown: faces.map((f) => f.getClientRects().length > 0),
    srcs: faces.map((f) => (f.getAttribute('src') || '').split('/').slice(-2).join('/')),
    cards,
    slideW: Math.round(slide * 100) / 100,
    oversize: over,
    worstOver: Math.round(worst * 100) / 100,
  };
});
/* CR-80, so a sanity clamp can say "still somewhere on the card" without asking the
 * page. ISO/IEC 7810 ID-1, the same numbers app.js's CARD holds. */
const S_CARD = { w: 85.6, h: 53.98 };
/* The X the PERSON sees, in mm, out of the Properties panel — not out of S. */
const INSP_X = () => {
  const inp = document.querySelector('#inspector [data-k="x"]');
  return inp ? parseFloat(inp.value) : null;
};

const engines = [['webkit', pw.webkit], ['chromium', pw.chromium]];
const fails = [];
/* Named, and printed at the end. A check that did not run is not a check that
 * passed, and the only way that stays true is if the skip is as visible as a pass. */
const skipped = [];
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

      /* ── F, G — the card's other side ──────────────────────────────────────
       * Reload first. A to E leave popovers open and a sheet raised, and a raised
       * sheet puts .sheet-scrim over the canvas on purpose, so a tap test run in
       * that state would be measuring the scrim. Nothing persists the document
       * (boot() opens blank; only the bleed slider is in localStorage), so a
       * reload is a clean card. */
      await page.reload({ waitUntil: 'load' });
      await page.waitForTimeout(1100);

      /* One element, on the front only, added the way a phone user adds one. Two
       * blank faces are the same pixels, so without this the flip could not be
       * proved by looking — which is the whole point of F. */
      await page.locator('.dock-btn[data-sheet="add"]').click();
      await page.waitForTimeout(300);
      await page.locator('.tool[data-add="text"]').click();
      await page.waitForTimeout(250);
      await page.locator('.dock-btn[data-sheet="add"]').click();   // put the sheet away
      await page.waitForTimeout(320);

      const chip = await page.evaluate(RECT, '#faceChip');
      const chipHit = await page.evaluate(HIT, '#faceChip');

      /* G's FIRST CLAUSE, and it has to run here, before F takes its baseline.
       * Adding an element selects it, and a tap with something selected must mean
       * deselect and nothing else — the flip may never fire while you are working
       * on an element. So: tap the card now, and the label must still say Front.
       * It also leaves the front with no selection handles drawn, which is what F
       * needs as its baseline; without this step F's "flip there and back" compared
       * a front WITH handles against a front without them, called the difference a
       * failure, and it was right to. */
      const mid0 = await page.evaluate(CARD_MID);
      const sel0 = await page.evaluate(SHOT);
      let gHeld = null, labelHeld = null;
      if (mid0 && mid0.on === 'canvas' && !sel0.err) {
        await page.touchscreen.tap(mid0.x, mid0.y);
        await page.waitForTimeout(320);
        labelHeld = await page.locator('#faceChip').innerText().catch(() => null);
        const after = await page.evaluate(SHOT);
        gHeld = /front/i.test(labelHeld || '') && after.h !== sel0.h;
      }

      const front0 = await page.evaluate(SHOT);
      let fOK = !!chip && chip.visible && chip.h >= 44 && inside(chip) && !!chipHit && chipHit.ok && !front0.err;
      let flipped = null, back = null, front1 = null, label0 = null, label1 = null;
      if (fOK) {
        label0 = await page.locator('#faceChip').innerText();
        await page.locator('#faceChip').tap();
        await page.waitForTimeout(320);
        back = await page.evaluate(SHOT);
        label1 = await page.locator('#faceChip').innerText();
        await page.locator('#faceChip').tap();
        await page.waitForTimeout(320);
        front1 = await page.evaluate(SHOT);
        // Different from the front, and back to byte-identical after flipping home.
        flipped = back.h !== front0.h && front1.h === front0.h;
        fOK = flipped && /front/i.test(label0) && /back/i.test(label1);
      }
      bits.push(`F ${fOK ? 'ok' : 'FAIL'}`);
      if (!fOK) {
        fails.push(`${name} @${W}px: the face chip does not report and flip the card's side — ` + (
          !chip ? '#faceChip is not in the page'
          : !chip.visible ? `#faceChip is not visible (sheet=${chip.sheet})`
          : chip.h < 44 ? `#faceChip is ${chip.h}px tall, under the 44px tap target`
          : !inside(chip) ? `#faceChip is outside the viewport — L${chip.left} R${chip.right} T${chip.top} B${chip.bottom} in ${W}x844`
          : !chipHit?.ok ? `the tap on #faceChip lands on "${chipHit?.on}"`
          : front0.err ? `canvas unreadable — ${front0.err}`
          : flipped === false ? `the canvas did not change: front=${front0.h} back=${back?.h} home=${front1?.h}`
          : `the label went "${label0}" then "${label1}"`));
      }

      /* G — the gesture the physical card has. A tap that hits no element with
       * nothing selected is the one gesture in this editor that means nothing, so
       * it is the one that was free to give a meaning. F left the selection empty
       * (changing face clears it), so a single tap is enough here; with something
       * selected the same tap deselects first, on purpose — it must never fire
       * while you are working on an element.
       *
       * IT ASSERTS AN IDENTITY, NOT A DIFFERENCE, and that is the whole check. The
       * first cut asked "did the canvas change after the tap" and PASSED against
       * the deployed app, which has no flip in it at all: an element was still
       * selected, so the tap cleared the selection, the handles stopped being
       * drawn, and the bitmap duly changed. Measured on both engines at all four
       * widths before a line of the fix existed — a green G for the wrong reason.
       * So the tap must land on the image F already established is the BACK, and
       * the state before it must be the image F established is the front with
       * nothing selected. Two known pictures, and the tap has to move between
       * them. When F fails there is no known back and G is not measurable — it
       * reports that rather than inventing a verdict. */
      const mid = await page.evaluate(CARD_MID);
      const gPre = await page.evaluate(SHOT);
      let gOK = fOK && gHeld === true && !!mid && mid.on === 'canvas' && !gPre.err && gPre.h === front1?.h;
      let gPost = null, gRuler = null;
      if (gOK) {
        /* OFF THE CARD FIRST. The gesture is named "tap the card" and the code bounds
         * it to the card's own millimetres, and nothing asserted that: deleting the
         * bounds test left this check green, because it only ever tapped the middle.
         * The mm ruler strip is part of the same canvas and is not the card, so a tap
         * there must do nothing at all. CARD_MID's own maths gives its corner. */
        const ruler = await page.evaluate(() => {
          const cv = document.querySelector('#canvas'); const r = cv.getBoundingClientRect();
          return { x: r.left + 4, y: r.top + 4 };
        });
        await page.touchscreen.tap(ruler.x, ruler.y);
        await page.waitForTimeout(300);
        gRuler = await page.evaluate(SHOT);
        if (gRuler.h !== gPre.h) { gOK = false; }
      }
      if (gOK) {
        await page.touchscreen.tap(mid.x, mid.y);
        await page.waitForTimeout(320);
        gPost = await page.evaluate(SHOT);
        gOK = gPost.h === back.h;
      }
      bits.push(`G ${gOK ? 'ok' : 'FAIL'}`);
      if (!gOK) {
        /* gHeld IS TESTED FIRST, and the order is the finding. It is measured before F
         * takes its baseline, so the defect it names — a tap flipping the card while
         * an element is selected — also corrupts F, F fails first, and this message
         * used to blame F for it. A reader was told the chip was broken while the chip
         * was fine. The earlier and more specific fact goes first. */
        fails.push(`${name} @${W}px: tapping the card does not show its other side — ` + (
          gHeld === false ? `a tap flipped the card while an element was selected (label went "${labelHeld}"), which it must never do`
          : !fOK ? 'F did not establish what the back looks like, so this is not measurable'
          : gHeld === null ? "the card's middle was not tappable for the deselect step"
          : gRuler && gRuler.h !== gPre.h ? 'a tap on the mm ruler turned the card over — the gesture is bounded to the card, not the canvas'
          : !mid ? 'no canvas'
          : mid.on !== 'canvas' ? `the tap at the card's middle lands on "${mid.on}"`
          : gPre.err ? `canvas unreadable — ${gPre.err}`
          : gPre.h !== front1?.h ? `the card was not on the front with nothing selected (${gPre.h} vs ${front1?.h})`
          : `the canvas did not become the back (${gPost?.h}, back is ${back?.h})`));
      }

      /* ── H — can a finger move the artwork ────────────────────────────────
       * The defect this was written for, measured on the deployed build at 390x844:
       * six touch-drag variants (fast, slow, long-press-then-drag, 12px, diagonal,
       * wide contact radius) each moved the element 0.00 mm, while the identical
       * drag driven by the mouse API moved it 21.27 mm. The element was selected
       * the whole time — selection worked, which is why nothing looked wrong — and
       * the canvas received 66 touchmoves and 0 mousemoves. A browser synthesises
       * mouse events for a tap and stops the moment it decides a gesture is a
       * drag, so an editor listening for mousemove is an editor a finger cannot
       * use. G is left on the back by its own tap, so flip home first. */
      let hOK = null, dx0 = null, dx1 = null, hPre = null, hPost = null, hWhy = '';
      if (name !== 'chromium') {
        hWhy = 'no CDP on this engine, so no real touch drag is possible';
      } else if (!fOK) {
        hWhy = 'F failed, so the card was not in a known state';
      } else {
        /* READ the face, do not assume it. This used to tap the chip once, on the
         * assumption that G had left the card on the back — so when G regressed, this
         * tap moved the card TO the back, ELEM_MID found the empty face, and H
         * degraded from `ok` to `skip` on all four widths. Not a false pass, but the
         * one assertion covering the whole pointer-event rewrite quietly stopped
         * running exactly when something else broke. */
        for (let i = 0; i < 2; i++) {
          const lab = await page.locator('#faceChip').innerText().catch(() => '');
          if (/front/i.test(lab)) break;
          await page.locator('#faceChip').tap();
          await page.waitForTimeout(320);
        }
        const at = await page.evaluate(ELEM_MID);
        if (!at || at.err) {
          hWhy = at?.err || 'could not locate the element on screen';
        } else {
          await page.touchscreen.tap(at.x, at.y);        // select it by finger
          await page.waitForTimeout(300);
          dx0 = await page.evaluate(INSP_X);
          hPre = await page.evaluate(SHOT);
          const cdp = await ctx.newCDPSession(page);
          const D = 60, STEPS = 10;
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: at.x, y: at.y }] });
          for (let i = 1; i <= STEPS; i++) {
            await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: at.x + (D * i) / STEPS, y: at.y }] });
            await page.waitForTimeout(16);
          }
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
          await page.waitForTimeout(320);
          dx1 = await page.evaluate(INSP_X);
          hPost = await page.evaluate(SHOT);
          const want = D * at.mmPerPx;
          const moved = (dx1 ?? 0) - (dx0 ?? 0);
          // Within 1.5mm: the element snaps to guides, so the landing is near the
          // finger rather than exactly under it, and that is correct behaviour.
          hOK = dx0 != null && dx1 != null && Math.abs(moved - want) <= 1.5 && hPost.h !== hPre.h;
          if (!hOK) hWhy = `X went ${dx0} -> ${dx1} mm, wanted about ${want.toFixed(2)} mm; canvas ${hPre.h === hPost.h ? 'did NOT repaint' : 'repainted'}`;
        }
      }
      bits.push(`H ${hOK === true ? 'ok' : hOK === false ? 'FAIL' : 'skip'}`);
      if (hOK === false) fails.push(`${name} @${W}px: a finger cannot move an element on the card — ${hWhy}`);
      if (hOK === null) skipped.push(`${name} @${W}px H: ${hWhy}`);

      /* ── J — the flip must not fire when the gesture was not a tap ─────────
       * F and G prove the card turns over. They were BOTH GREEN, on both engines at
       * all four widths, while every one of these was true — which is the useful
       * lesson about them: a gate that only proves a feature works says nothing
       * about how it misfires, and "it works" is the half that gets tested.
       *   Each clause below is a defect that was reproduced before it was fixed:
       *   J1 a pinch-zoom on the card face turned it over, because the flip was
       *      wired to pointerdown and the first finger of a pinch is a pointerdown.
       *      That defeats the reason the canvas permits pinch-zoom at all.
       *   J2 the flip was a press, not a tap: a finger that landed, slid 120px away
       *      and lifted had already turned the card at the moment it touched down.
       *   J3 a pinch begun mid-drag delivered no pointercancel for the dragging
       *      finger, so the element followed the ZOOM — measured x 6 -> 62.72 mm,
       *      y 8 -> 162.85 mm on a card 53.98 mm tall, in an app with no undo.
       * Chromium only: real multi-touch needs CDP, exactly as H does. */
      let jOK = null, jWhy = '', jRows = [];
      if (name !== 'chromium') {
        jWhy = 'no CDP on this engine, so no real pinch or swipe is possible';
      } else {
        await page.reload({ waitUntil: 'load' });
        await page.waitForTimeout(1100);
        await page.locator('.dock-btn[data-sheet="add"]').click();
        await page.waitForTimeout(280);
        await page.locator('.tool[data-add="text"]').click();
        await page.waitForTimeout(220);
        await page.locator('.dock-btn[data-sheet="add"]').click();
        await page.waitForTimeout(300);

        const cdp = await ctx.newCDPSession(page);
        const label = () => page.locator('#faceChip').innerText().catch(() => '(none)');
        const mid = await page.evaluate(CARD_MID);
        const xy = () => page.evaluate(() => {
          const q = (k) => { const i = document.querySelector(`#inspector [data-k="${k}"]`); return i ? parseFloat(i.value) : null; };
          return { x: q('x'), y: q('y') };
        });

        /* THE PINCH RUNS LAST, and finding that out is worth the comment. Run first,
         * it leaves the page zoomed to 1.5 — and a tap coordinate computed from
         * getBoundingClientRect is a LAYOUT coordinate, which no longer lands where
         * the element is drawn once the visual viewport is scaled. J3's own tap then
         * missed the element, the Properties fields read null, and J3 failed at 320
         * and 360px for a reason that was entirely the harness's. Order the clauses
         * so the one that changes the viewport is the one nothing follows.
         *   J3 also has to run while NOTHING is selected for J2 to mean anything: a
         * swipe with an element selected could not flip the card in any case, so a
         * green J2 in that state would be measuring the selection guard, not the tap
         * recogniser. Hence the deselecting tap between them. */
        // J3 — a pinch begun mid-drag must not carry the artwork with the zoom. The
        // element goes back where the drag started, because a pinch is never a move.
        const at = await page.evaluate(ELEM_MID);
        let before = null, after = null;
        if (at && !at.err) {
          await page.touchscreen.tap(at.x, at.y);           // select it
          await page.waitForTimeout(280);
          before = await xy();
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: at.x, y: at.y, id: 0 }] });
          for (let i = 1; i <= 3; i++) {
            await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: at.x + 10 * i, y: at.y, id: 0 }] });
            await page.waitForTimeout(14);
          }
          // second finger lands, then both move — a pinch, mid-drag
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: at.x + 30, y: at.y, id: 0 }, { x: at.x + 130, y: at.y + 80, id: 1 }] });
          for (let i = 1; i <= 5; i++) {
            await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [
              { x: at.x + 30 - 5 * i, y: at.y - 5 * i, id: 0 }, { x: at.x + 130 + 12 * i, y: at.y + 80 + 10 * i, id: 1 }] });
            await page.waitForTimeout(14);
          }
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
          await page.waitForTimeout(420);
          after = await xy();
        }
        jRows.push(`J3 pinch mid-drag: ${JSON.stringify(before)} -> ${JSON.stringify(after)}`);

        /* AND J3's OWN GESTURE ZOOMS THE PAGE TOO, which is the point of it: two
         * fingers moving apart over a canvas that permits pinch-zoom is a zoom. So
         * the scale is reset here, and the tap target is re-read before each clause
         * from the live layout, rather than reusing a coordinate measured before any
         * of this. Without the reset, Chrome's pinch synthesiser refused the next
         * clause outright — "Position out of bounds" — because it computes two finger
         * paths outward from the point and they fell off a viewport that was no
         * longer the size the coordinate assumed. */
        const resetZoom = async () => {
          try { await cdp.send('Emulation.setPageScaleFactor', { pageScaleFactor: 1 }); } catch { /* best effort */ }
          await page.waitForTimeout(220);
        };
        await resetZoom();

        // put the selection away, so J2 tests the tap recogniser and not the
        // "never while something is selected" guard
        const mid2 = await page.evaluate(CARD_MID);
        await page.touchscreen.tap(mid2.x, mid2.y);
        await page.waitForTimeout(320);
        const l0 = await label();

        // J2 — a swipe is not a tap. Down, 120px up, lift.
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: mid2.x, y: mid2.y }] });
        for (let i = 1; i <= 8; i++) {
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: mid2.x, y: mid2.y - 15 * i }] });
          await page.waitForTimeout(14);
        }
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        await page.waitForTimeout(420);
        const l1 = await label();
        jRows.push(`J2 swipe: "${l0}" -> "${l1}"`);

        // J1 — pinch over the card. Chrome's own gesture synthesiser, so the browser
        // classifies it as a pinch exactly as it would for two real fingers. LAST,
        // because it leaves the viewport scaled — see above.
        await resetZoom();
        const mid3 = await page.evaluate(CARD_MID);
        await cdp.send('Input.synthesizePinchGesture',
          { x: Math.round(mid3.x), y: Math.round(mid3.y), scaleFactor: 1.5, relativeSpeed: 600, gestureSourceType: 'touch' });
        await page.waitForTimeout(500);
        const l2 = await label();
        jRows.push(`J1 pinch: "${l1}" -> "${l2}"`);
        await resetZoom();

        const card = S_CARD;   // 85.6 x 53.98, CR-80
        const onCard = (p) => p && p.x != null && p.y != null
          && p.x >= -card.w && p.x <= card.w && p.y >= -card.h && p.y <= card.h;
        jOK = /front/i.test(l0) && /front/i.test(l1) && /front/i.test(l2)
          && !!before && !!after && after.x === before.x && after.y === before.y && onCard(after);
        if (!jOK) jWhy = jRows.join(' | ');
      }
      bits.push(`J ${jOK === true ? 'ok' : jOK === false ? 'FAIL' : 'skip'}`);
      if (jOK === false) fails.push(`${name} @${W}px: a gesture that was not a tap changed the card — ${jWhy}`);
      if (jOK === null) skipped.push(`${name} @${W}px J: ${jWhy}`);

      /* ── I — the landing page's card gallery ──────────────────────────────
       * The other half of the same report, on the page it was left from: "the page
       * should be half card then half features that way you can see the card at
       * least … tapping it shows the rear … that way you save Realestate".
       * Measured before the change: 12 cards spread over 24 slides in two decks
       * (10 slides / 5 dots, and 14 / 7), every back a slide of its own, so a
       * thumb crossed two screens per card and the page was twice as long as the
       * thing it shows. The pager already counted a card as ONE (its dots are per
       * card, and it derives faces-per-dot from the DOM), so the deck disagreeing
       * with its own pager is the defect stated exactly.
       * How "which side is showing" is read is recorded on DECKS itself, where the
       * reasoning lives; do not restate it here, because the first version of this
       * sentence said "opacity" and stayed after the code stopped using it. */
      await page.goto(origin + '/', { waitUntil: 'load' });
      await page.waitForTimeout(700);
      const decks = await page.evaluate(DECKS);
      const nCards = decks.reduce((n, d) => n + d.cards.length, 0);
      let iOK = decks.length > 0 && decks.every((d) => d.slides === d.dots && d.dots > 0)
        && decks.every((d) => d.cards.length > 0 && d.cards.every((c) => c.faces === 2))
        && decks.every((d) => d.oversize === 0)
        // Two faces are no use if they are the same picture. This is the clause a
        // mutation pass defeated by pointing every back at its own front.
        && decks.every((d) => d.cards.every((c) => c.srcs[0] && c.srcs[1] && c.srcs[0] !== c.srcs[1]));
      let flipA = null, flipB = null, badFlip = [];
      if (iOK) {
        /* EVERY CARD IN EVERY RACK. Tapping one of twelve is a measurement of one of
         * twelve, and it was: the second rack's flip could be dead — all seven of its
         * backs unreachable — with this printing "ok". */
        for (let r = 0; r < decks.length; r++) {
          const cards = page.locator('.rack').nth(r).locator('.deck .card');
          const n = await cards.count();
          for (let c = 0; c < n; c++) {
            const el = cards.nth(c);
            await el.scrollIntoViewIfNeeded().catch(() => {});
            const pre = (await page.evaluate(DECKS))[r].cards[c].shown;
            await el.tap();
            await page.waitForTimeout(160);
            const post = (await page.evaluate(DECKS))[r].cards[c].shown;
            if (r === 0 && c === 0) { flipA = pre; flipB = post; }
            const turned = pre[0] === true && pre[1] === false && post[0] === false && post[1] === true;
            if (!turned) badFlip.push(`rack${r} card${c} ${JSON.stringify(pre)}->${JSON.stringify(post)}`);
          }
        }
        iOK = badFlip.length === 0;
      }
      bits.push(`I ${iOK ? 'ok' : 'FAIL'}`);
      if (!iOK) {
        const shape = decks.map((d) => `${d.slides} slide(s)/${d.dots} dot(s), ${d.cards.length} card(s), ${d.oversize} oversize`).join('; ');
        const sameSrc = decks.flatMap((d, r) => d.cards
          .map((c, i) => (c.srcs[0] && c.srcs[1] && c.srcs[0] !== c.srcs[1]) ? null : `rack${r} card${i} ${JSON.stringify(c.srcs)}`)
          .filter(Boolean));
        fails.push(`${name} @${W}px: the card gallery does not turn a card over — ` + (
          !decks.length ? 'no .rack on the landing page'
          : !decks.every((d) => d.slides === d.dots && d.dots > 0) ? `a card is still spending a slide per side — ${shape}`
          : !decks.every((d) => d.cards.length > 0 && d.cards.every((c) => c.faces === 2)) ? `a card does not carry both its faces — ${shape}`
          : !decks.every((d) => d.oversize === 0) ? `a card is WIDER than its slide, so the artwork runs off the screen — `
              + decks.map((d) => `${d.oversize} card(s) over a ${d.slideW}px slide, worst by ${d.worstOver}px`).join('; ')
          : sameSrc.length ? `a card's two faces are the same image, so turning it shows nothing new — ${sameSrc.join('; ')}`
          : `${badFlip.length} of ${nCards} card(s) did not turn over — ${badFlip.slice(0, 4).join('; ')}`));
      }

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

/* ── K — a MOUSE in a narrow window must not turn the card over ─────────────────
 * Its own pass, because every context above is isMobile+hasTouch and this defect only
 * exists without them. It needs no phone: it is a desktop browser someone has made
 * narrow, which is an ordinary thing to do and not a rare one on a laptop.
 *
 * WHAT WENT WRONG, and it is a reasoning bug rather than a typo. The flip was gated
 * on "is the face chip on screen", argued as: the chip is display:none above 820px,
 * so the chip being visible IS being in the phone shell — put the question to the
 * stylesheet rather than copying a breakpoint into JavaScript. The trouble is that
 * the phone shell is two stylesheet decisions, not one: the chip appears under
 * `max-width: 820px`, the touch behaviour under `pointer: coarse`, and those two do
 * not agree about what a phone is. Measured with a real mouse and no touch at all:
 * at 819px a plain left click on the card background turned it over, in a build
 * where #faceSeg is also hidden, so nothing on screen said what had happened.
 *
 * The layout question and the input question are different questions. The chip is a
 * control the layout hid something else to make room for, so it stays width-gated.
 * The flip is a finger gesture, so it is gated on the pointer that made it. */
if (ran) {
  const MOUSE_WIDTHS = [1400, 900, 819, 700];
  for (const [name, engine] of engines) {
    let browser;
    try { browser = await engine.launch(); } catch { continue; }
    for (const W of MOUSE_WIDTHS) {
      const ctx = await browser.newContext({ viewport: { width: W, height: 900 } });  // a mouse: no isMobile, no hasTouch
      const page = await ctx.newPage();
      try {
        await page.goto(origin + '/studio/', { waitUntil: 'load' });
        await page.waitForTimeout(1000);
        const before = await page.evaluate(() => {
          const c = document.querySelector('#faceChip'), s = document.querySelector('#faceSeg .seg-btn.is-on');
          return { chip: c && c.offsetParent ? c.textContent.trim() : null, seg: s ? s.textContent.trim() : null };
        });
        const mid = await page.evaluate(CARD_MID);
        if (!mid || mid.on !== 'canvas') { console.log(`  K ${name.padEnd(9)} @${W}px  skip — the card's middle is covered by "${mid?.on}"`); await ctx.close(); continue; }
        await page.mouse.click(mid.x, mid.y);
        await page.waitForTimeout(350);
        const after = await page.evaluate(() => {
          const c = document.querySelector('#faceChip'), s = document.querySelector('#faceSeg .seg-btn.is-on');
          return { chip: c && c.offsetParent ? c.textContent.trim() : null, seg: s ? s.textContent.trim() : null };
        });
        const shown = (o) => o.chip || o.seg;     // whichever control this width shows
        const held = shown(before) === shown(after);
        console.log(`  K ${name.padEnd(9)} @${String(W).padStart(4)}px  ${held ? 'ok' : 'FAIL'}  (${shown(before)} -> ${shown(after)}${before.chip ? ', chip visible' : ''})`);
        if (!held) fails.push(`${name} @${W}px with a MOUSE: clicking the card turned it over (${shown(before)} -> ${shown(after)}) — the flip is a finger gesture and must be gated on the pointer, not on the window width`);
      } catch (err) {
        fails.push(`${name} @${W}px K: harness error — ${String(err.message).split('\n')[0]}`);
      }
      await ctx.close();
    }
    await browser.close();
  }
}

if (server) server.close();

if (!ran) {
  console.log('\nSKIPPED — no browser engine ran, so nothing was measured.');
  process.exit(0);
}
if (skipped.length) {
  console.log(`\n${skipped.length} check(s) NOT MEASURED — not the same as passed:`);
  for (const s of skipped) console.log('  · ' + s);
}
if (fails.length) {
  console.log(`\n${fails.length} finding(s):`);
  for (const f of fails) console.log('  - ' + f);
  process.exit(1);
}
console.log(`\nReachable at ${WIDTHS.join(', ')}px — the picker opens, both panels land inside the screen, Send takes the tap, a finger can turn the card over and move what is on it, and the gallery gives one slide per card.`);
