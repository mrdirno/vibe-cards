/* Prove the assembled Pages artifact is complete and self-contained.
 *
 * The failure this exists to catch is the quiet one: a Pages deploy that
 * publishes a directory missing a file the app fetches at runtime. Everything
 * goes green — the workflow, the deploy, the HTTP 200 on the landing page — and
 * the site is dead the moment the app boots, or worse, dead only when the user
 * clicks Download. So the check is derived from what the files ACTUALLY
 * reference, never from a hand-maintained list that drifts.
 *
 *   node tools/verify_pages_artifact.mjs _site
 */
import fs from 'node:fs';
import path from 'node:path';

const site = process.argv[2] || '_site';
const fail = [];
const ok = (m) => console.log(`  ok   ${m}`);
const bad = (m) => { fail.push(m); console.log(`  FAIL ${m}`); };

if (!fs.existsSync(site)) {
  console.error(`${site} does not exist — run the assemble step first.`);
  process.exit(1);
}

const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');

// Case matters on the Pages filesystem and does not on the macOS dev one, so
// existsSync() is not enough — a wrong-case reference passes locally and 404s
// live. Compare against the real directory entries.
const entries = new Set();
(function walk(dir, prefix = '') {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${e.name}` : e.name;
    if (e.isDirectory()) walk(path.join(dir, e.name), rel);
    else entries.add(rel);
  }
})(site);

// 1. Every href/src the HTML references must exist, byte-for-byte by name.
const refs = [...html.matchAll(/(?:src|href)="([^"#?][^"]*)"/g)]
  .map((m) => m[1])
  .filter((u) => !/^(https?:|data:|mailto:|\/\/)/.test(u));
for (const ref of refs) {
  if (entries.has(ref)) ok(`referenced ${ref}`);
  else bad(`index.html references "${ref}" — not in the artifact (check case too)`);
}

// The artifact now holds TWO documents: the landing page at the root, and the
// designer under /studio/. They share the reference and self-containment rules and
// nothing else — a page with no scripts cannot be asked about script order, and
// demanding backend.js of it fails on a file it has no reason to own.
const isApp = /<script src="/.test(html);
console.log(`  --   document type: ${isApp ? 'app (designer)' : 'page (landing)'}`);

// 2. Files fetched from JS at runtime. These have no tag to derive from, so they
//    are extracted from the adapter's own fetch() calls rather than listed here.
const backend = isApp ? fs.readFileSync(path.join(site, 'backend.js'), 'utf8') : '';
if (isApp) {
const fetched = [...backend.matchAll(/fetch\('([^']+)'\)/g)]
  .map((m) => m[1])
  .filter((u) => !u.startsWith('/api/') && !/^https?:/.test(u));
if (!fetched.length) bad('no runtime fetch() targets found in backend.js — the extractor is broken, not the artifact');
for (const f of fetched) {
  if (entries.has(f)) ok(`runtime fetch ${f}`);
  else bad(`backend.js fetches "${f}" at runtime — not in the artifact`);
}
}

// 3. No root-absolute paths: the site is served from a project subpath
//    (/vibe-cards/), so a leading slash resolves against the account root.
const abs = [...html.matchAll(/(?:src|href|action)="(\/[^/][^"]*)"/g)].map((m) => m[1]);
if (abs.length) bad(`root-absolute path(s) in index.html — will 404 under the project subpath: ${abs.join(', ')}`);
else ok('no root-absolute paths');
if (/<base\s/i.test(html)) bad('<base> tag present — it would break the desktop build, which serves this same file from /');
else ok('no <base> tag');

// 4. The web build must carry no server-only artifacts.
if (html.includes('__CS_SESSION_TOKEN__')) {
  bad('index.html still carries the session-token placeholder — it is meaningless without a server and must be stripped for the web build');
} else ok('no session-token placeholder');
if (isApp) {
if (entries.has('backend-static.js')) bad('backend-static.js still present — the assemble step should have renamed it to backend.js');
else ok('backend renamed');
if (!/name:\s*'web'/.test(backend)) bad('backend.js is not the web adapter — the desktop one got published');
else ok('backend.js is the web adapter');

// 5. Script order: pdf.js and backend.js must both execute before app.js.
//    app.js calls boot() at top level and boot() immediately calls the backend.
const order = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
const iPdf = order.indexOf('pdf.js'), iBack = order.indexOf('backend.js'), iApp = order.indexOf('app.js');
if (iPdf === -1 || iBack === -1 || iApp === -1) bad(`missing a script tag: pdf.js=${iPdf} backend.js=${iBack} app.js=${iApp}`);
else if (!(iPdf < iBack && iBack < iApp)) bad(`script order must be pdf.js < backend.js < app.js, got ${order.join(', ')}`);
else ok('script order: pdf.js, backend.js, app.js');
if (/<script[^>]+\b(defer|type="module")/.test(html)) {
  bad('a defer/module script tag would silently reorder execution and kill boot()');
} else ok('no defer/module tags');
}

// 6. Self-contained: no third-party SUBRESOURCE.
//    The distinction matters now that one of these documents is a landing page. A
//    third-party <script src>, <img src> or stylesheet is a dependency: it can be
//    slow, tracked, blocked, or gone, and the page breaks with it. A link to a repo
//    is a NAVIGATION — the whole point of a landing page — and banning it would ban
//    the links the card exists to hand people. So: subresources must be local,
//    anchors may go anywhere.
const subresources = [
  ...[...html.matchAll(/<[^>]+\ssrc="(https?:\/\/[^"]+)"/g)].map((m) => m[1]),
  ...[...html.matchAll(/<link\b[^>]*\shref="(https?:\/\/[^"]+)"/g)].map((m) => m[1]),
];
if (subresources.length) bad(`external subresource(s) — the page would depend on a third party: ${subresources.join(', ')}`);
else ok('no external subresources');

console.log(fail.length ? `\n${fail.length} problem(s) — the deploy would be green over a dead site.`
                        : `\nArtifact complete: ${entries.size} files, all references resolve.`);
process.exit(fail.length ? 1 : 0);
