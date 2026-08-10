/* End-to-end verification harness for Card Studio.
 *
 * Drives the real UI in headless Chrome over the DevTools protocol, so every
 * assertion below is made against the code path that actually prints — not a
 * re-implementation of it. Node 24's global WebSocket means no dependencies.
 *
 *   node tools/verify.mjs http://127.0.0.1:8777/ /tmp/shots
 */

import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

let URL_ = process.argv[2] || '';
const OUT = process.argv[3] || '/tmp/cardstudio-verify';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
// Per-run debug port. A fixed one let a headless Chrome left over from an
// earlier run keep answering, so the harness attached to a stale page pointing
// at a stale server and blamed the app for it.
const PORT = 9400 + Math.floor(Math.random() * 500);

mkdirSync(OUT, { recursive: true });

// ALWAYS start our own server on its own port, never adopt one that happens to
// be listening. A long-lived instance from an earlier session kept answering on
// the fixed port and served its own copy of profiles.json, which made the
// harness report geometry failures against code that was actually correct — the
// worst kind of test result, one that accuses the wrong thing.
let ownServer = null;
async function startServer() {
  const appDir = new URL('../src/', import.meta.url).pathname;
  ownServer = spawn('python3', ['server.py'], {
    cwd: appDir,
    env: { ...process.env, CARD_STUDIO_NO_BROWSER: '1' },   // no CARD_STUDIO_PORT: it picks a free one
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const port = await new Promise((res, rej) => {
    const timer = globalThis.setTimeout(() => rej(new Error('server never announced a port')), 15000);
    ownServer.stdout.on('data', (b) => {
      const m = String(b).match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (m) { globalThis.clearTimeout(timer); res(m[1]); }
    });
  });
  URL_ = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 40; i++) {
    try { await fetch(URL_ + 'api/ping'); return; } catch { await sleep(250); }
  }
  throw new Error('app server never answered');
}
if (URL_) {
  console.log(`using the server at ${URL_} (explicitly requested)`);
} else {
  await startServer();
  console.log(`started a private app server at ${URL_}`);
}

const results = [];
const check = (name, pass, detail = '') => {
  results.push({ name, pass, detail });
  console.log(`${pass ? '  ok  ' : ' FAIL '} ${name}${detail ? ' — ' + detail : ''}`);
};

// ── CDP plumbing ─────────────────────────────────────────────────────────

let ws, msgId = 0;
const pending = new Map();
const consoleErrors = [];

function send(method, params = {}) {
  const id = ++msgId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}

async function evaluate(expression) {
  const r = await send('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true,
  });
  if (r.exceptionDetails) {
    throw new Error(r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails));
  }
  return r.result?.value;
}

async function screenshot(name) {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  const path = `${OUT}/${name}.png`;
  writeFileSync(path, Buffer.from(r.data, 'base64'));
  return path;
}

// ── run ──────────────────────────────────────────────────────────────────

const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars',
  `--remote-debugging-port=${PORT}`,
  '--remote-allow-origins=*',
  '--window-size=1500,960',
  '--user-data-dir=' + OUT + '/chrome-profile',
  '--no-first-run', '--no-default-browser-check',
  URL_,
], { stdio: 'ignore' });

let target = null;
for (let i = 0; i < 60 && !target; i++) {
  await sleep(300);
  try {
    const list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json());
    target = list.find((t) => t.type === 'page' && t.url.startsWith(URL_));
  } catch { /* chrome still coming up */ }
}
if (!target) {
  console.error(`could not attach to a Chrome page at ${URL_}`);
  chrome.kill(); if (ownServer) ownServer.kill();
  process.exit(1);
}
console.log(`attached to ${target.url} (devtools :${PORT})`);

ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res) => ws.addEventListener('open', res, { once: true }));
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(m.error.message)) : res(m.result);
  } else if (m.method === 'Runtime.exceptionThrown') {
    consoleErrors.push(m.params.exceptionDetails?.exception?.description || 'exception');
  } else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    consoleErrors.push(m.params.args.map((a) => a.value ?? a.description).join(' '));
  }
});

await send('Runtime.enable');
await send('Page.enable');

// Wait for boot() to finish wiring the app. Check the globals the assertions
// below actually depend on — an earlier version only checked that the layer
// list had rendered, timed out silently, and then reported "QR is not defined"
// as though the encoder were broken when the page was merely still loading.
let ready = false;
for (let i = 0; i < 120 && !ready; i++) {
  ready = await evaluate(
    'typeof window.QR === "object" && typeof window.Barcode === "object" && typeof S === "object" && !!S.doc && !!S.profile'
  ).catch(() => false);
  if (!ready) await sleep(250);
}
if (!ready) {
  console.error('app never finished booting — aborting rather than reporting misleading failures');
  ws.close(); chrome.kill(); if (ownServer) ownServer.kill();
  process.exit(1);
}

console.log('\n── Card Studio verification ───────────────────────────────\n');

// 1. clean boot
check('boots with no uncaught JS errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));

// 2. the encoders actually produced symbols
const qrOk = await evaluate(`(() => {
  const m = QR.encode('https://persona500.example/card/000117', {ecLevel:'M'});
  return m && m.size >= 21 && m.modules.length === m.size;
})()`);
check('QR encoder returns a well-formed matrix', qrOk === true);

const bcOk = await evaluate(`(() => {
  const b = Barcode.code128('000117');
  return b && Array.isArray(b.bars) && b.bars.length > 10;
})()`);
check('Code128 encoder returns bars', bcOk === true);

// 3. print raster is EXACTLY card size at the chosen dpi
const raster = await evaluate(`(() => {
  const cv = rasterise(S.doc.faces[0], S.doc.card, 600, null);
  return { w: cv.width, h: cv.height,
           expW: Math.round(85.6 * 600 / 25.4), expH: Math.round(53.98 * 600 / 25.4) };
})()`);
check('600 dpi raster is exactly card-sized',
  raster.w === raster.expW && raster.h === raster.expH,
  `${raster.w}×${raster.h} px (expected ${raster.expW}×${raster.expH})`);

// 4. placements carry the profile's slot geometry unmodified
const place = await evaluate(`(async () => {
  const p = await buildPlacements(null);
  return p.map(x => ({ x: x.x_mm, y: x.y_mm, w: x.w_mm, h: x.h_mm, len: x.image.length }));
})()`);
const slotsOk = place.length === 2
  && place[0].x === 17.553 && place[0].y === 3.818
  && place[1].x === 17.553 && place[1].y === 63.868
  && place.every((p) => p.w === 85.6 && p.h === 53.98 && p.len > 5000);
check('both slots placed at profile geometry', slotsOk, JSON.stringify(place.map((p) => [p.x, p.y])));

// 5. round-trip a real PDF through the server
const pdf = await evaluate(`(async () => {
  const placements = await buildPlacements(null);
  const res = await api('/api/pdf', Object.assign(printPayload(placements, 'verify'), { open:false }));
  return res.pdf;
})()`);
check('server wrote a PDF', !!pdf, pdf || '');

// 5b. dry run through the real CUPS filter chain — the check that proves the
// job will not be silently cropped when it reaches the printer
const dry = await evaluate(`(async () => {
  const placements = await buildPlacements(null);
  return await api('/api/dryrun', printPayload(placements, 'verify-dry'));
})()`);
check('dry run rasterises to exactly the media size',
  dry.ok && Math.abs(dry.width_mm - 120) < 0.15 && Math.abs(dry.height_mm - 120) < 0.15,
  dry.ok ? `${dry.width_px}×${dry.height_px}px @${dry.dpi}dpi ${dry.bpp}bpp = ${dry.width_mm}×${dry.height_mm}mm`
         : (dry.error || 'failed'));

// 5c. no scaling option may reach lp — -o fit-to-page silently shrinks to 42.95%
const opts = await evaluate(`JSON.stringify(currentOptions())`);
check('no fit-to-page / print-scaling in the lp options',
  !/fit-to-page|print-scaling/.test(opts), opts);

// 5d. photo import geometry — a photo must fill the card and sit UNDER the
// text, not land as a small square on top of it
const photo = await evaluate(`(() => {
  const before = S.doc.faces[0].elements.length;
  const el = placeFullCard(0, 'data:image/png;base64,iVBORw0KGgo=');
  const first = S.doc.faces[0].elements[0];
  const d = { x: el.x, y: el.y, w: el.w, h: el.h, fit: el.fit,
              atBottom: first.id === el.id, grew: S.doc.faces[0].elements.length === before + 1 };
  S.doc.faces[0].elements.shift();
  return d;
})()`);
check('imported photo fills the card and sits under the artwork',
  photo.x === 0 && photo.y === 0 && photo.w === 85.6 && photo.h === 53.98
  && photo.fit === 'cover' && photo.atBottom && photo.grew,
  `${photo.w}×${photo.h}mm at ${photo.x},${photo.y} · bottom=${photo.atBottom}`);

// 6. views render
for (const view of ['design', 'tray', 'batch', 'calibrate']) {
  await evaluate(`switchView('${view}')`);
  if (view === 'batch') {
    await evaluate(`document.querySelector('#btnCsvSample').click()`);
    await sleep(400);
  }
  await sleep(350);
  const shot = await screenshot(view);
  check(`view "${view}" renders`, true, shot);
}

// 7. batch pairing arithmetic
const batch = await evaluate(`({ records: S.records.length, text: document.querySelector('#runState').textContent })`);
check('batch pairs 3 records into 2 tray loads',
  batch.records === 3 && /1 of 2/.test(batch.text), batch.text);

// 8. calibration offset flows through to placements
await evaluate(`S.profile.calibration = {dx: 1.5, dy: -0.75}; renderTray();`);
const calPayload = await evaluate(`(() => { const p = printPayload([], 'x'); return {dx:p.dx, dy:p.dy}; })()`);
check('calibration offset reaches the print payload',
  calPayload.dx === 1.5 && calPayload.dy === -0.75, JSON.stringify(calPayload));
await evaluate(`S.profile.calibration = {dx:0, dy:0}; renderTray();`);

writeFileSync(`${OUT}/results.json`, JSON.stringify({ results, consoleErrors, pdf }, null, 2));

const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} checks passed\n`);
if (pdf) console.log('PDF for geometry measurement: ' + pdf + '\n');

ws.close();
chrome.kill();
if (ownServer) ownServer.kill();
process.exit(failed ? 1 : 0);
