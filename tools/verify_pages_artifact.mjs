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
 *   node tools/verify_pages_artifact.mjs _site --network-registry   # curation passes only
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// --network-registry is OPT-IN and never part of the deploy gate: it fetches
// hosts this repo does not control, and a deploy that a third party's hiccup
// can block is a coupling, not a check. --registry exists for the rehearsal
// harness to point at a fixture; production runs never pass it.
let site = '_site', netMode = false, registryOverride = null;
{
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--network-registry') netMode = true;
    else if (argv[i] === '--registry') {
      registryOverride = argv[++i];
      // A forgotten value must die here, not degrade: eating the next flag once
      // disabled the network gate while exiting green, and a trailing --registry
      // fell back to the REAL registry — so a fixture rehearsal would have
      // quietly fetched the four production hosts.
      if (registryOverride === undefined || registryOverride.startsWith('--')) {
        console.error('--registry needs a path argument — refusing to guess which registry you meant');
        process.exit(2);
      }
    }
    else site = argv[i];
  }
}
const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
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

// 1. Every href/src EVERY document references must exist, byte-for-byte by name.
//
// This read only the ROOT index.html until 2026-08-15, and the gap was the exact
// shape of the failure at the top of this file: the card pages under /gt/, /tierra/,
// /raices/, /nica/, /sala/ and /lab/ are the surfaces a printed chip OPENS, their URLs
// can never change, and every asset they named was unchecked. A page could reference a
// renamed file and ship green — the same class as KUNAI-001 pointing at a 404 for weeks
// because nothing swept it. Found by moving 1.14 MB of base64 out of gt/index.html and
// noticing that nothing in this repo would have caught the new reference being wrong.
//
// Refs in a SUB-document resolve against ITS OWN directory, which is the whole reason
// this could not just be a second call on the same code: `../studio/templates/x.jpg`
// from gt/ is `studio/templates/x.jpg` in the artifact, and comparing the raw string
// would fail a correct reference and pass an incorrect one. Two shapes are refused
// outright rather than normalised:
//   · a leading `/` — root-absolute is a 404 on a PROJECT Pages site served under
//     /vibe-cards/, and it resolves locally, so it is the reference most likely to pass
//     a dev machine and die live. (The sibling archive repo's deploy gate refuses the
//     same shape under /collage/, arrived at independently.)
//   · anything that climbs out of the artifact root.
// EVERY .html, not every index.html. The first version of this check read index.html
// documents only, which is the SAME assumption check 8 below writes down as one of its
// two known limits — "a project surface named credits.html would go unchecked" — and a
// sibling project on this very network is living that defect right now: the archive's
// /collage/ Wall of Wishes has no credits.html while /av/ does. A check that inherits
// the limitation it is meant to close is not a check.
const docs = [...entries].filter((e) => e.endsWith('.html')).sort();
let refsChecked = 0;
for (const rel of docs) {
  const dir = path.posix.dirname(rel) === '.' ? '' : path.posix.dirname(rel);
  const doc = rel === 'index.html' ? html : fs.readFileSync(path.join(site, rel), 'utf8');
  // Quotes both ways, attribute name either case, and the ref may carry a fragment or a
  // query. All three were false negatives or false positives on this check's first run,
  // found by an adversarial lane that seeded each shape and watched the gate stay green
  // (src='missing.png', HREF="missing.png") or go red on something alive ("../gt/#wish",
  // "../studio/index.html?v=2"). The fragment is the browser's business and the query is
  // the server's; neither is part of the path that has to exist in the artifact.
  // The lookbehind is load-bearing: without it `data-src="…"` is read as a reference, and
  // a templating attribute becomes a deploy failure. KNOWN LIMITS, named rather than left
  // for the next reader to discover (§2 E4): srcset, <video poster>, <meta content>
  // (og:image — all six surfaces ship a RELATIVE one today, which is wrong for Open Graph
  // and unread by anything here), and CSS url() in a style attribute or an inline <style>
  // are all invisible to this check. Each is a real reference a page can 404 on.
  const refs = [...doc.matchAll(/(?<![\w-])(?:src|href)\s*=\s*("([^"]*)"|'([^']*)')/gi)]
    .map((m) => (m[2] !== undefined ? m[2] : m[3]))
    .map((u) => u.replace(/[#?].*$/, '').trim())
    .filter((u) => u && !/^(https?:|data:|mailto:|tel:|sms:|javascript:|\/\/)/i.test(u));
  for (const ref of refs) {
    if (ref.startsWith('/')) {
      bad(`${rel} references "${ref}" — root-absolute, which 404s under /vibe-cards/`);
      continue;
    }
    // A DIRECTORY link is answered with that directory's index.html, with or without the
    // trailing slash — Pages 301s `/studio` to `/studio/` and serves the same document.
    // Resolving these as filenames failed two correct references on this check's first
    // run and a third on its second, which is the reminder that a new gate's first duty
    // is to be right about the artifact it measures, not to be strict about it.
    let resolved = path.posix.normalize(path.posix.join(dir, ref));
    if (resolved === '.' || resolved === './') resolved = 'index.html';
    if (!entries.has(resolved) && entries.has(path.posix.join(resolved, 'index.html'))) {
      resolved = path.posix.join(resolved, 'index.html');
    }
    refsChecked++;
    if (resolved.startsWith('..')) bad(`${rel} references "${ref}" — climbs out of the artifact`);
    else if (entries.has(resolved)) ok(`${rel} → ${resolved}`);
    else bad(`${rel} references "${ref}" (→ ${resolved}) — not in the artifact (check case too)`);
  }
}

// 1b. WHAT A CARD PAGE WEIGHS, printed for every surface and capped for all of them.
//
// A chip opens exactly one URL and that URL can never change, so the only thing that
// can ever be improved is what sits behind it — and the first thing behind it is how
// much of it has to arrive before a person sees anything. gt/index.html shipped
// 1,191,962 bytes over the wire until 2026-08-15, of which 1,137,469 were two base64
// PNGs of the card the reader was already holding: 96.6% of the document ahead of the
// first archive entry and 99.8% ahead of the wish button, paid on a phone in Guatemala.
// Nothing here measured that, so nothing noticed it for as long as it was true.
//
// The ceiling is on the DOCUMENT, not the page: images referenced as files stream in
// parallel and do not block the text, which is the entire difference the gt fix made.
// RAW bytes, deliberately: gzip ratios across these ten documents span 1.35x to 3.52x,
// and the loosest is gt's own shape (1.59x — 58% of it is already-compressed inline
// woff2), so a gzipped cap would be 2.6x looser for exactly the pages that inline the
// most. Raw is also what has to be parsed. 320 KB is chosen for what it protects, not
// for what passes, and every surface prints its number so the ceiling is a floor under
// attention rather than a pass/fail nobody reads.
//
// WHAT IT DOES NOT MEASURE, said plainly because it is the maneuver this very commit
// performed: referenced asset bytes. A page can pass at 14 KB and point at 500 KB of
// PNGs, and five of the six card pages do — raices ships 566,068 first-paint bytes,
// lab 494,821, nica 405,743. Moving bytes out of the document is a real improvement
// (text renders first) and it is not the same as removing them.
const DOC_CEILING = 320 * 1024;
// THE ONE EXEMPTION, named rather than tuned around. raices/garden/index.html is a React
// bundle carrying two JPEGs as string constants at 4284x5712 and 3024x4032 — 3.99 MB of
// image in a 5.53 MB document, for photographs a phone shows a few hundred pixels wide.
// This comment first called them "camera originals" and that did not reproduce: a marker
// walk finds JFIF and ICC only, zero EXIF tags, so they were stripped and re-encoded
// already. It also claimed extraction would publish the artwork at NEW hotlinkable URLs,
// and that is wrong too — NOTICE withholds src/site/raices/card-{front,back}.png as the
// same child's paintings and the site already serves them standalone (356,803 and 204,035
// bytes, 200 against a control). Both corrections came from a lane asked what nobody had
// looked for, and they are kept here rather than quietly edited out, because an exemption
// resting on two claims that do not reproduce is worth less than no exemption at all.
// WHAT SURVIVES, and it is enough: either route — extracting these particular photographs
// or downscaling them — changes how a child's paintings are published, on a page no card
// points at, in a repo whose rule is that public is an instruction and never an inference.
// That is the owner's call to make deliberately, not an agent's to take as a side effect
// of a different fix at four in the morning. Bounded below so it cannot grow into furniture.
// An exemption keyed on a NAME is unbounded, and unbounded is how a debt becomes
// furniture: the first version of this let that file grow to 15 MB and still exit 0.
// Every exemption carries the byte count it was granted at, and grants nothing above it.
const OVERWEIGHT_EXEMPT = new Map([
  ['raices/garden/index.html', {
    max: 5_600_000,
    why: 'two full-resolution JPEGs inside a React bundle; either fix changes how a child\'s paintings are published, so it is the owner\'s call (2026-08-15, granted at 5,531,164 B)',
  }],
]);
console.log(`  --   ${refsChecked} references resolved across ${docs.length} documents`);
for (const rel of docs) {
  const bytes = fs.statSync(path.join(site, rel)).size;
  const kb = (bytes / 1024).toFixed(1);
  const exempt = OVERWEIGHT_EXEMPT.get(rel);
  if (bytes <= DOC_CEILING) ok(`${rel} document ${kb} KB`);
  else if (exempt && bytes <= exempt.max) {
    console.log(`  --   ${rel} document ${bytes.toLocaleString('en-US')} B — OVER the `
      + `${DOC_CEILING / 1024} KB ceiling, exempt up to ${exempt.max.toLocaleString('en-US')} B: ${exempt.why}`);
  } else if (exempt) {
    bad(`${rel} is ${bytes.toLocaleString('en-US')} B — its exemption stops at `
      + `${exempt.max.toLocaleString('en-US')} B. An exemption is a record of a measured debt, not a `
      + `licence to grow it. Re-measure and re-argue it, or close it.`);
  } else {
    // Exact bytes, not KB: at one byte over, (bytes/1024).toFixed(1) prints the ceiling
    // it just failed, and a FAIL message that reads "320.0 KB is over the 320 KB ceiling"
    // is read as a rounding bug and dismissed.
    bad(`${rel} is ${bytes.toLocaleString('en-US')} B — over the ${DOC_CEILING / 1024} KB ceiling for a page a chip opens. `
      + `Reference big images as files instead of inlining them; a data: URI is paid before the `
      + `first word renders. If it genuinely cannot be split, name it in OVERWEIGHT_EXEMPT with `
      + `the reason, so the debt is printed on every run instead of disappearing.`);
  }
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
// EVERY document, for the reason /gt/ embeds its typefaces: "the linked version sent the
// IP of everyone who taps this card to a third party, and this page is handed to people by
// name." That rule is about the pages a CHIP OPENS, and this check read the root index.html
// only — so a <link href="https://fonts.googleapis.com/…"> on tierra/index.html passed
// green, on the exact surface the rule was written for. Found 2026-08-15 by a lane asked
// what nobody had looked for, the same night check 1 was widened and this one was not:
// extending one check and leaving its neighbour narrow is how a rail becomes decorative.
// A <link> IS NOT AUTOMATICALLY A SUBRESOURCE. This failed every `<link
// rel="canonical" href="https://mrdirno.github.io/vibe-cards/aurea/">` — a card
// page declaring its own address, which fetches nothing at all and cannot leak
// anyone's IP to anyone. The rule it was enforcing is about requests the browser
// makes on load; canonical, alternate, author and licence are metadata and make
// none. So the test is the `rel`, not the protocol: a link fails when it names a
// rel that FETCHES, or when it names no rel at all and so cannot be judged.
// Widening a check until it fails correct pages is the same defect as leaving it
// narrow — both end with the rail switched off.
const FETCHING_REL = /\b(stylesheet|icon|manifest|preload|modulepreload|prefetch|preconnect|dns-prefetch|prerender|mask-icon|apple-touch-icon)\b/i;
for (const rel of docs) {
  const doc = rel === 'index.html' ? html : fs.readFileSync(path.join(site, rel), 'utf8');
  const subresources = [
    ...[...doc.matchAll(/<[^>]+\ssrc\s*=\s*["'](https?:)?\/\/[^"']+["']/gi)].map((m) => m[0]),
    ...[...doc.matchAll(/<link\b[^>]*\shref\s*=\s*["'](https?:)?\/\/[^"']+["']/gi)]
      .map((m) => m[0])
      .filter((tag) => {
        const r = tag.match(/\srel\s*=\s*["']([^"']*)["']/i);
        return !r || FETCHING_REL.test(r[1]);
      }),
  ].map((t) => (t.match(/["']((?:https?:)?\/\/[^"']+)["']/) || [, t])[1]);
  if (subresources.length) {
    bad(`${rel}: external subresource(s) — the page would depend on a third party: ${subresources.join(', ')}`);
  } else ok(`${rel}: no external subresources`);
}

// 7. The manifest, at the well-known path.
//    This is the only named path in this file, and it breaks the rule at the top
//    on purpose. Every other check is DERIVED from what the files reference —
//    and nothing references this one, because a well-known path has no referrer.
//    That is what "well-known" means: a machine is expected to guess it. So the
//    derivation that catches every other missing asset is structurally blind
//    here, which is exactly how the seed project came to publish a landing page
//    whose manifest 404s while every gate stayed green and a 13-lane adversarial
//    panel passed the criterion by reading the repo instead of the site.
//    Landing page only — /studio/ is an app, not a project surface.
// 7b. The standard itself, at the URL a card hands out — same blindness, same
//     class, third instance. This check exists because the reasoning above is
//     GENERAL and was applied only to the file that prompted it: a well-known
//     path has no referrer, so nothing derived can see it missing. The manifest
//     got a check the day it 404'd, OFL.txt got a build-time copy the day it
//     404'd, and WISH_IT_BETTER.md — the document whose adoption IS membership
//     in this network — was 404 on this host the whole time, with the landing
//     page's only route to it pointing off-site to github.com.
//     Byte-identity, not mere presence: a second copy that drifts is worse than
//     no copy, because the world reads the published one and the panel reads
//     the repo one. Same rule as the manifest, ten lines down.
//     Written as a TABLE, not as one special case, and that is the fix for the
//     defect the first draft of this very check shipped with: it asserted
//     byte-identity for WISH_IT_BETTER.md — the file that happened to prompt it —
//     and left NOTICE, LICENSE and OFL.txt with only build_site.py's
//     presence-or-FAIL. Presence is not identity. Those three are exactly the
//     files where a silent divergence costs the most: OFL.txt and NOTICE carry
//     the TERMS for bytes this site redistributes, so a stale published copy
//     would state the wrong terms for the artwork and fonts it hands out, and
//     nothing would report it. Every root file the builder copies is listed here;
//     adding a copy there without a row here is the regression this comment exists
//     to make obvious.
if (!isApp) {
  // [published name, tracked repo-root original, why it must ship]. The .txt twins
  // are a SECOND published name for the SAME tracked bytes — extensionless files
  // are typed application/octet-stream by Pages and download rather than open, so
  // the twin is what a human link can point at. Listing them here is what keeps
  // "two names" from becoming "two truths": every copy is compared to the one
  // tracked original, so a twin cannot silently drift from the file it duplicates.
  const rootAssets = [
    ['WISH_IT_BETTER.md', 'WISH_IT_BETTER.md', 'a network whose membership test is "adopt this file" must serve the file under the URL its cards carry; an agent handed a chip gets one URL and nothing else'],
    ['LICENSE', 'LICENSE', 'this site redistributes the project under it, and NOTICE beside it opens by naming it'],
    ['LICENSE.txt', 'LICENSE', 'the extensionless copy downloads instead of opening; this is the one a human link can reach'],
    ['NOTICE', 'NOTICE', 'it withholds the GT-001 artwork from the MIT grant, and that artwork is served from this very artifact — a withholding that does not ship with the bytes protects nobody'],
    ['NOTICE.txt', 'NOTICE', 'the whole force of a NOTICE beside an MIT licence is discovery, and a file that downloads is not discovered'],
    ['OFL.txt', 'OFL.txt', 'gt/index.html embeds OFL-licensed fonts, and the licence must travel with the bytes'],
  ];
  for (const [name, original, why] of rootAssets) {
    if (!entries.has(name)) { bad(`${name} missing from the artifact — ${why}`); continue; }
    const rootPath = path.join(repoRoot, original);
    if (!fs.existsSync(rootPath)) { bad(`${name} is in the artifact but ${original} is not at the repo root — the published copy has no tracked original to be checked against`); continue; }
    const liveBytes = fs.readFileSync(path.join(site, name));
    if (fs.readFileSync(rootPath).equals(liveBytes)) ok(`${name} present and matches ${original} byte-for-byte`);
    else bad(`${name} in the artifact differs from ${original} at the repo root — two sources of truth, and the published copy is the one the world reads`);
  }

  // Byte-identity is not content. An emptied or gutted NOTICE matches an emptied
  // or gutted original perfectly and sweeps green through every check above —
  // which would publish a ZERO-BYTE withholding while the artwork it is supposed
  // to withhold keeps serving 200 from this same artifact. So this one file is
  // asserted on what it SAYS: it must still name every path it exists to carve
  // out. The list is derived from the exclusion itself, not retyped, so adding a
  // fifth face to the withholding without naming it here cannot pass quietly.
  // Two card packages, not one. The raices entry was missing for four commits
  // while this file's closing blanket affirmatively offered a child's paintings
  // under MIT, so the list is kept here rather than in anyone's memory.
  const withheld = [
    'gt-archive-front.jpg', 'gt-archive-back.jpg', 'gt-sleek-front.jpg', 'gt-sleek-back.jpg',
    'raices/card-front.png', 'raices/card-back.png', 'raices-front.png', 'raices-back.png',
  ];
  if (entries.has('NOTICE')) {
    const notice = fs.readFileSync(path.join(site, 'NOTICE'), 'utf8');
    const missing = withheld.filter((f) => !notice.includes(f));
    if (missing.length) bad(`published NOTICE no longer names ${missing.join(', ')} — a carve-out that stops naming what it carves out is a 200 that withholds nothing, and the artwork is still served from this artifact`);
    else if (!/OFL/.test(notice)) bad('published NOTICE no longer mentions the OFL fonts — they are embedded in gt/index.html and may not be distributed under MIT');
    else ok(`NOTICE still names all ${withheld.length} withheld faces and the OFL fonts`);
  }
}

if (!isApp) {
  const wib = 'wish-it-better.json';
  const live = path.join(site, wib);
  if (!entries.has(wib)) {
    bad(`${wib} missing from the artifact — the site URL is what a card's chip carries, so a manifest that exists only in the repo is invisible to every card holder`);
  } else {
    let text = null;
    try {
      text = fs.readFileSync(live, 'utf8');
      const parsed = JSON.parse(text);
      ok(`${wib} present and parses (level ${parsed.level ?? '?'})`);
    } catch (e) {
      // A 200 a crawler cannot read is worse than a 404: the 404 is an honest
      // absence, the unparseable 200 scores as a pass and reports a level.
      bad(`${wib} is in the artifact but does not parse (${e.message})`);
      text = null;
    }
    // Drift is the entire risk of publishing a second copy, so prove there is no
    // second copy: the published bytes must be the git-tracked bytes.
    const root = path.join(repoRoot, wib);
    if (text !== null) {
      if (fs.existsSync(root) && fs.readFileSync(root, 'utf8') === text) ok(`${wib} matches the repo-root original byte-for-byte`);
      else bad(`${wib} in the artifact differs from the repo-root original — two sources of truth, and the published copy is the one the world reads`);

      // The registry badge and the manifest must agree about the level.
      // They said the same thing only because a person typed it twice, in two
      // files, and nothing has ever compared them: build_site.py checks that an
      // entry's fields are PRESENT, never what they say, so an entry claiming
      // L99 builds green. Publishing the manifest is what makes this checkable —
      // the two numbers are now one hop apart on one origin, and a visitor who
      // reads the badge and then the manifest is the first party to see both.
      // Matched on repo URL rather than id, because the id is a registry-side
      // label the manifest has never carried.
      const reg = path.join(repoRoot, 'src', 'site', 'network.json');
      const declared = JSON.parse(text);

      // The manifest is the machine-readable half of the account-free rule below,
      // and it is the ONLY half a crawler reads: nothing traverses the page looking
      // for a mailto. Declaring the issue tracker here publishes the account-gated
      // route as THE route — which is what every manifest on this network did,
      // including KUNAI-360's, whose live page carries a mailto it does not declare.
      // A mailto is account-free but it is not a QUEUE, and it made a human's
      // inbox the precondition for anything happening. A page carrying the
      // wishing well is MORE account-free — no mail client, no address — so it
      // counts, but only if it is PROVEN: the declared page must exist in this
      // artifact and actually carry the marker. A URL alone would be a promise.
      const wc = String(declared.wish_channel || '');
      let wellPage = null;
      if (/^https?:/i.test(wc)) {
        // strip fragment and query FIRST — the channel is a page plus an anchor
        // (…/#wish), and folding the anchor into the path resolves to nothing.
        const bare = wc.split('#')[0].split('?')[0];
        const rel = (bare.replace(/^https?:\/\/[^/]+\//, '').replace(/^vibe-cards\//, '')
                       .replace(/\/$/, '') + '/index.html').replace(/^\//, '');
        const cand = rel === 'index.html' ? 'index.html' : rel;
        if (entries.has(cand) && /data-wish-well[\s=>]/.test(fs.readFileSync(path.join(site, cand), 'utf8'))) {
          wellPage = cand;
        }
      }
      if (/^(mailto|tel|sms):/i.test(wc)) {
        ok(`manifest wish_channel reaches a human without an account`);
      } else if (wellPage) {
        ok(`manifest wish_channel is the wishing well on ${wellPage} — no account, and it queues`);
      } else {
        bad(`manifest wish_channel "${declared.wish_channel}" needs an account — it is the only channel a machine reads, and §1 of the standard requires a wish in under 30 seconds with no account`);
      }

      if (fs.existsSync(reg) && declared.repo) {
        const norm = (u) => String(u).replace(/\/+$/, '').toLowerCase();
        const listed = (JSON.parse(fs.readFileSync(reg, 'utf8')).listed || [])
          .filter((e) => norm(e.repo) === norm(declared.repo));
        // Silence is not agreement: if the seed is not in its own registry, say so
        // rather than passing a comparison that never happened.
        if (!listed.length) bad(`no listed entry has repo ${declared.repo} — the published manifest's level is compared against nothing`);
        for (const e of listed) {
          if (e.level === declared.level) ok(`registry badge and manifest agree on ${e.level} for ${e.id}`);
          else bad(`${e.id} is badged ${e.level} in the registry but the published manifest declares ${declared.level} — the page and the file it links disagree`);
        }
      }

      // `amended` is the compounding ledger — the field L2 reads as proof that a
      // project contributed back — and nothing had ever compared it to the
      // standard it names. This manifest carried two entries while
      // WISH_IT_BETTER.md recorded one in force. `git log -S 'v1.0.2'` puts the
      // extra one in 7f0cb71, whose stat lists five files and not the spec, so
      // "v1.0.2 — origin filled" described a manifest edit and claimed a spec
      // change, on the one file every adopter copies.
      //
      // It survived because §5's definition has two halves — a PR touching
      // WISH_IT_BETTER.md AND adding your project to `amended` — and only the
      // second half leaves a trace in a checkable file. So the half that costs
      // something could be skipped while the half that claims credit was written.
      // This is the join, and it is the same shape as the level check above: two
      // records a person typed separately, never compared until now.
      //
      // Matched on the version token ALONE. The prose after it is a summary and
      // will never be byte-equal to the spec's heading, so demanding more would
      // fail honest entries — and an entry with no parseable version is failed
      // too, because a claim nobody can look up is not auditable. Read from the
      // ARTIFACT copy of the spec rather than the repo root: that is the copy an
      // adopter fetches, and it is already proven byte-identical above.
      const specPath = path.join(site, 'WISH_IT_BETTER.md');
      if (Array.isArray(declared.amended) && fs.existsSync(specPath)) {
        const spec = fs.readFileSync(specPath, 'utf8');
        const inForce = new Set(
          [...spec.matchAll(/^\*\*(v\d+(?:\.\d+)*)\b/gm)].map((m) => m[1]),
        );
        const unbacked = declared.amended.filter((a) => {
          const v = /^\s*(v\d+(?:\.\d+)*)\b/.exec(String(a));
          return !v || !inForce.has(v[1]);
        });
        if (!inForce.size) {
          bad('published WISH_IT_BETTER.md records no amendments in force — every `amended` entry is compared against nothing');
        } else if (unbacked.length) {
          bad(`manifest \`amended\` claims ${unbacked.map((a) => JSON.stringify(String(a).slice(0, 40))).join(', ')} — no such amendment is in force in the published WISH_IT_BETTER.md (${[...inForce].join(', ')}), and \`amended\` is what L2 reads as proof of contributing back`);
        } else {
          ok(`manifest \`amended\` (${declared.amended.length}) all name amendments in force in the published spec (${[...inForce].join(', ')})`);
        }
      }
    }
  }
}

// 8. Every project surface must carry a channel that reaches a human WITHOUT an
//    account.
//
//    §1 of the standard requires a wish "in under 30 seconds with no account" and
//    then, two lines below, offers "at minimum: a GitHub issue template" — which
//    requires one. Both lines were copied forward, and the second one won: the
//    landing page carried three issue links and nothing else, so the single page a
//    VIBE-CARDS-001 chip opens had no route to a human for most of the people
//    holding these cards. Measured before this check existed: 15 links on the
//    landing page, 0 account-free — while /gt/, a project this registry HOLDS below
//    the bar, had one. The held entry did it right and the example did not.
//
//    Derived, not listed: every non-app document in the artifact is a project
//    surface and gets the same rule. App documents exclude themselves by their own
//    content (a <script src> tag), so /studio/ needs no special case and a second
//    app would be covered without editing this.
//
//    mailto/tel/sms only. An arbitrary https:// form may well be account-free, but
//    nothing here can prove that statically, and a check that guesses is a check
//    that waves through the next issue tracker.
//
//    TWO LIMITS, measured, because this check will be copied to other repos and
//    both of them bite there and neither bites here:
//    · It reads index.html documents. Every HTML file this artifact ships is one
//      (3 of 3, checked); a project surface named credits.html would go unchecked.
//    · It reads STATIC markup. A channel installed by a JS bundle is invisible to
//      it — the archive's /av/ well is exactly that: a working account-free queue
//      with zero `mailto:` in the served HTML, which this check would FAIL. That is
//      a false negative, not a defect found. It cannot bite here because these
//      pages ship no JavaScript for content on purpose (see build_site.py), so the
//      markup is the whole surface. Take this to a React app and it will lie.
if (!isApp) {
  const surfaces = [...entries]
    .filter((e) => e === 'index.html' || e.endsWith('/index.html'))
    .sort();
  for (const rel of surfaces) {
    const doc = fs.readFileSync(path.join(site, rel), 'utf8');
    if (/<script src="/.test(doc)) {
      console.log(`  --   ${rel}: app document, not a project surface`);
      continue;
    }
    // A mailto is an account-free ROUTE and a useless QUEUE — no status, no
    // ordering, and a human read before anything can happen. The card pages now
    // post to the wishing well instead (tools/wishing_well.py), which is MORE
    // account-free, not less: no mail client, no address, no app. So the well
    // counts, and it is detected by an explicit marker rather than by sniffing
    // for a URL, because the endpoint is a config value and will move.
    const free = [...doc.matchAll(/href="((?:mailto|tel|sms):[^"]*)"/gi)].map((m) => m[1]);
    // `data-wish-well` is a valueless boolean attribute, which is valid HTML and
    // what the pages emit. An earlier version of this line required `=` and so
    // failed every page that carried the marker correctly.
    const well = /data-wish-well[\s=>]/.test(doc) ? ['wishing-well'] : [];
    free.push(...well);
    if (free.length) ok(`${rel}: ${free.length} account-free wish route(s)`);
    else bad(`${rel} carries no account-free channel — every link on it needs an account. `
      + `This is a page a card's chip opens. shape.wish in network.json: issues are a second `
      + `route, never the only one. Add a mailto:/tel:/sms: route; src/site/gt/index.html is the pattern.`);
  }
}

// 8b. EVERY CARD ROW MUST POINT AT THE PROJECT IT NAMES. A pure local join, and
//     the only link in the card chain that runs on a push.
//
//     Check 10 below compares each row's live final URL against that row's OWN
//     resolves_to and nothing else, so a row that is internally consistent passes
//     no matter whose project it lands on. Reproduced by mutation: rewrite
//     KUNAI-001's chip row to COLLAGE-001's redirector and destination and the
//     sweep goes green at exit 0 with zero FAILs — a listed project's card
//     pointing at a different project entirely, with every gate agreeing.
//
//     WHY IT LIVES OUT HERE AND NOT DOWN THERE WITH THE SWEEP. It fetches
//     nothing; it is a join over one file in this repo. --network-registry is
//     opt-in for a real reason — it reaches hosts this repo does not control, and
//     a deploy a third party's hiccup can block is a coupling, not a check — but
//     that reason does not extend to a check that makes no request. Inside the
//     flag this would fail up to a day AFTER the push that broke it, on a
//     schedule GitHub disables after 60 days of inactivity where a dropped run
//     looks exactly like a green one; and it would sit behind the Node-18 fetch
//     bail, skipped on an older runner for want of a fetch it never makes.
//     pages.yml already triggers on src/site/**, so out here the edit that breaks
//     a card is refused by the deploy that would have published it.
//
//     THE FORWARD JOIN ALONE IS NEARLY WORTHLESS, which is the correction to the
//     remedy as it was first written down. "Compare a row's resolves_to against
//     the url of the listed entry named in its project field" describes a check
//     whose scope the row itself chooses: `project: null` is legal and ordinary —
//     10 of 22 rows carry it today, because the example cards point at pages that
//     are not registry projects — so deleting one word walks the mutation past
//     this join AND past the coverage arm, destination intact. Hence the inverse
//     rule: a row landing on a listed project's site must SAY that project. The
//     pair is what closes it; either alone is an off-switch.
//
//     EXACT EQUALITY, NEVER A PREFIX. Six destinations sit strictly below
//     VIBE-CARDS-001's url — the five example cards and gt-archive. A startsWith
//     comparison is the obvious leniency for making those join, and it would
//     adopt all six and wave through anything pointing at /vibe-cards/anything/.
if (!isApp) {
  const regFile = registryOverride ?? path.join(repoRoot, 'src', 'site', 'network.json');
  if (!fs.existsSync(regFile)) {
    bad(`no registry at ${regFile} — every card row would be compared against nothing`);
  } else {
    const registry = JSON.parse(fs.readFileSync(regFile, 'utf8'));
    const rows = (registry.cards && registry.cards.destinations) || [];
    const listed = registry.listed || [];
    // Scheme and host are case-insensitive per RFC 3986 and the default port is
    // not part of identity; the PATH is case-sensitive on the Pages filesystem,
    // so check 7's whole-string lowercase would make /av/ and /AV/ — two
    // different pages on the same host — compare equal. Same semantics as the
    // sweep's own norm() below, deliberately, so the two halves cannot disagree
    // about whether a row matches.
    const norm = (u) => {
      try {
        const x = new URL(String(u));
        return `${x.protocol.toLowerCase()}//${x.host.toLowerCase()}${x.pathname.replace(/\/+$/, '')}${x.search}`;
      } catch { return String(u).replace(/\/+$/, ''); }
    };
    const name = (c) => `${c.card || c.project || '?'}/${c.surface}`;
    const listedById = new Map(listed.map((e) => [e.id, e]));
    const heldIds = new Set((registry.held || []).map((e) => e.id));
    // Indexed in the normalised form the comparison uses, so "is this some listed
    // project's site?" is answered the same way in both directions.
    const siteOwner = new Map(listed.filter((e) => e.url).map((e) => [norm(e.url), e.id]));

    // EXHAUSTIVE, and this file has learned twice what happens when a partition is
    // not: a row in no bucket reads, in the transcript, exactly like a row that
    // passed. Every row lands in exactly one of these five and the count is
    // asserted, because the fix asserts on 6 of 22 rows and a section printing
    // only ok-lines would read as full coverage.
    const tieable = rows.filter((c) => c.project && listedById.has(c.project) && c.resolves_to);
    const listedNoDest = rows.filter((c) => c.project && listedById.has(c.project) && !c.resolves_to);
    const heldRows = rows.filter((c) => c.project && heldIds.has(c.project));
    const dangling = rows.filter((c) => c.project && !listedById.has(c.project) && !heldIds.has(c.project));
    const noProject = rows.filter((c) => !c.project);
    const accounted = tieable.length + listedNoDest.length + heldRows.length + dangling.length + noProject.length;
    if (accounted !== rows.length) {
      bad(`card tie: ${rows.length} row(s) but ${accounted} accounted for — some row is in no bucket and would be checked by nothing`);
    }
    console.log(`  --   card tie: ${rows.length} row(s) = ${tieable.length} tied + ${listedNoDest.length} listed-but-no-destination + ${heldRows.length} held, exempt (${heldRows.map(name).join(', ') || 'none'}) + ${noProject.length} no project named (${noProject.map(name).join(', ') || 'none'}) + ${dangling.length} dangling`);

    // SELF-HOSTED DESTINATIONS: if a card points into THIS site, the page it
    // points at has to be in the artifact.
    //
    // `project` is legitimately null on the example cards — tierra, raices, nica,
    // sala, lab, manis, aurea, bloom, moku are not network projects and never will
    // be. But the five-way partition above files every one of them under
    // `noProject` and checks their destination against nothing, so ONE field was
    // answering two unrelated questions: *whose project is this row* and *should
    // anyone confirm the destination exists*. That makes the second check
    // switchable by deleting a word — the same hazard the INVERSE loop below was
    // written to close, arriving from the other side.
    //
    // It shipped. bloom-card/qr named https://mrdirno.github.io/vibe-cards/bloom/
    // while the artifact had no bloom/index.html in it, and this file printed
    // "Artifact complete: 95 files, all references resolve." and exited 0. Nothing
    // was lying: check 1 verifies references that pages MAKE, and no page linked
    // to /bloom/ — the only thing pointing there was a QR code printed on a card,
    // which is not a document this tool can crawl. A destination reachable only
    // from ink is exactly the destination nothing else will ever check.
    //
    // Deliberately NOT a sixth bucket: the partition above is asserted exhaustive
    // and a self-hosted bucket would steal founder-card/qr from `tieable` and
    // gt-archive/qr from `heldRows`, trip the count tripwire, and check LESS. This
    // runs over all rows independently, so a row can be tied AND checked to exist.
    //
    // The base URL is derived from the artifact rather than written here as a
    // literal, so a fork or a rename cannot leave this silently checking a host it
    // no longer publishes.
    const manifestPath = path.join(site, 'wish-it-better.json');
    let selfBase = null;
    if (fs.existsSync(manifestPath)) {
      try {
        const declaredRepo = JSON.parse(fs.readFileSync(manifestPath, 'utf8')).repo;
        const normRepo = (u) => String(u).replace(/\/+$/, '').toLowerCase();
        const self = listed.find((e) => e.repo && e.url && normRepo(e.repo) === normRepo(declaredRepo));
        if (self) selfBase = new URL(self.url);
      } catch { /* fall through to the bad() below — a parse failure is not a pass */ }
    }
    if (!selfBase) {
      bad(`card destinations: could not derive this site's own base URL from ${manifestPath} + the registry's listed entries, so no card row pointing into this site was checked to exist`);
    } else {
      const basePath = selfBase.pathname.replace(/\/+$/, '');
      let checked = 0, missing = 0;
      for (const c of rows) {
        if (!c.url) continue;
        let u;
        try { u = new URL(String(c.url)); } catch { continue; }
        // Compare pathname only: a #wish or ?q= row still points at a real page.
        if (u.origin !== selfBase.origin) continue;
        if (u.pathname !== basePath && !u.pathname.startsWith(basePath + '/')) continue;
        const rel = u.pathname.slice(basePath.length).replace(/^\/+|\/+$/g, '');
        // Against the real directory listing, never existsSync — this volume is
        // case-insensitive and Pages is not, so /Bloom/ would pass here and 404
        // live. Same reason the `entries` Set exists at the top of this file.
        const candidates = rel ? [`${rel}/index.html`, rel] : ['index.html'];
        checked++;
        if (!candidates.some((p) => entries.has(p))) {
          missing++;
          bad(`card ${name(c)}: points at ${c.url}, which is this site, but the artifact has no ${candidates[0]} — a printed card would scan straight to a 404`);
        }
      }
      // Summarise what HAPPENED, not what was attempted. The first draft of this
      // line said "all have a page" off `checked` alone, so a run with one FAIL
      // above it still printed a green sentence claiming every row was fine —
      // this file's own rule (count is not coverage) broken by the check written
      // to enforce it.
      if (missing) console.log(`  --   card destinations: ${checked} row(s) point into this site, ${missing} with no page in the artifact`);
      else ok(`card destinations: ${checked} row(s) pointing into this site all have a page in the artifact`);
    }

    // A row naming a project that exists nowhere is a record checked against
    // nothing — the same shape as the sentence-in-prose this whole block replaced.
    for (const c of dangling) {
      bad(`card tie ${name(c)}: project "${c.project}" is in neither listed nor held — this row names a project that does not exist, so nothing can check where it points`);
    }

    // FORWARD: the row says which project it belongs to; its destination must be
    // that project's site.
    for (const c of tieable) {
      const entry = listedById.get(c.project);
      if (!entry.url) {
        bad(`card tie ${name(c)}: listed entry ${c.project} has no url, so this row's destination is tied to nothing`);
        continue;
      }
      if (norm(c.resolves_to) !== norm(entry.url)) {
        bad(`card tie ${name(c)}: this row is a card for ${c.project}, whose site is ${entry.url}, but it lands on ${c.resolves_to} — a card in someone's hand opens a different project than the one this row claims`);
        continue;
      }
      ok(`card tie ${name(c)}: ${c.project} -> ${entry.url}`);
    }

    // INVERSE: whatever the row says, if it lands on a listed project's site then
    // it is a card for that project and must say so. This is the half that makes
    // the forward join mean anything — without it the check is disabled by
    // deleting the field that decides whether the check applies.
    for (const c of rows) {
      if (!c.resolves_to) continue;
      const owner = siteOwner.get(norm(c.resolves_to));
      if (owner && c.project !== owner) {
        bad(`card tie ${name(c)}: lands on ${c.resolves_to}, which is ${owner}'s site, but this row names ${c.project === null || c.project === undefined ? 'no project' : `"${c.project}"`} — a row cannot point at one project and be filed under another`);
      }
    }

    // COUNT IS NOT COVERAGE. Everything above iterates rows, so a project nobody
    // wrote a row for is invisible to it — and on the day the card block shipped,
    // two listed projects had zero rows while a prose field two lines above them
    // recorded having measured their live destinations. The measurement existed;
    // the row did not; nothing swept them.
    //
    // This arm lived inside --network-registry until the tie check gave it a
    // local home. It never needed the flag: it is a join over one file, it can
    // only fail on an edit to that file, and behind the flag it could fire only
    // on a schedule that is forbidden to block a deploy. It does NOT make `card`
    // a listing gate — curation.note concluded that `criteria` governs promotion
    // and `criteria` has no card in it. It asserts something narrower and purely
    // internal: every listed project must have a ROW, including a row whose url
    // is null saying it has no recorded destination. Absence is a fine answer;
    // silence is not, because silence and "swept clean" are the same shape in a
    // transcript. Held entries are exempt — being held is already the record that
    // a part is missing.
    const listedIds = listed.map((p) => p.id);
    const covered = new Set(rows.map((c) => c.project).filter(Boolean));
    const uncovered = listedIds.filter((id) => !covered.has(id));
    console.log(`  --   card coverage: ${listedIds.length - uncovered.length}/${listedIds.length} listed + ${[...heldIds].filter((id) => covered.has(id)).length}/${heldIds.size} held project(s) have a destination row`);
    for (const id of uncovered) {
      bad(`card coverage ${id}: listed, but no row in cards.destinations — not even one recording that it has no known card destination, so nothing here can tell "swept clean" from "never looked"`);
    }
  }
}

// 9. --network-registry: the other half of check 7, across the network.
//    Check 7 proves THIS project's badge and manifest agree. Nothing anywhere
//    ever fetched a LISTED project's published manifest, so a listed project
//    that raises its own level — which its own deploy now correctly publishes —
//    would disagree with the badge here and no gate would notice. This mode
//    fetches each listed entry's manifest at its listed url and compares.
//    Derived, not listed: the urls come from the registry itself.
//    Listed entries only: a held entry declares no level, so there is nothing
//    to cross-check — GT-001 is held precisely for having no manifest, and
//    that absence is its honest state, not a failure for this mode to shout
//    about. Every 200 is proven against a nonsense-path control on the same
//    host, because a host that answers 200 to everything makes the manifest's
//    200 worthless. What this mode does NOT prove: that the level was EARNED
//    (curation's job), or that the site renders (a manifest is one file).
if (netMode) {
  if (typeof fetch !== 'function') {
    bad('--network-registry needs Node 18+ (global fetch)');
  } else {
    const regFile = registryOverride ?? path.join(repoRoot, 'src', 'site', 'network.json');
    const registry = JSON.parse(fs.readFileSync(regFile, 'utf8'));
    const listedEntries = registry.listed || [];
    // Name the registry in the transcript: with --registry in play, an output
    // that does not say which file it read is an output that cannot be audited.
    console.log(`  --   network-registry: ${listedEntries.length} listed manifest(s) from ${regFile}; held entries excluded — no declared level to check`);
    const get = async (url) => {
      try {
        const r = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(15000), headers: { 'user-agent': 'wish-it-better-registry-gate' } });
        return { status: r.status, finalUrl: r.url, text: r.status === 200 ? await r.text() : null };
      } catch (e) {
        return { status: 0, finalUrl: null, text: null, err: e.message };
      }
    };
    // Kept so the origin arm below can compare against the copy a card holder's
    // agent would actually read, without paying for the fetch twice.
    const publishedManifest = new Map();
    for (const e of listedEntries) {
      const base = String(e.url || '').replace(/\/+$/, '');
      if (!/^https?:/i.test(base)) { bad(`net ${e.id}: listed url "${e.url}" is not fetchable`); continue; }
      const murl = `${base}/wish-it-better.json`;
      const [m, control] = await Promise.all([get(murl), get(`${base}/control-404-for-the-registry-gate`)]);
      // A control that could not LOOK must not report "held": answering
      // "proven" on a transport error is the QR-check failure all over again —
      // quietly saying "no drift" when the truth was "I couldn't check".
      if (control.status === 0) { bad(`net ${e.id}: the control request did not answer (${control.err}) — cannot prove the host 404s nonsense, so a 200 on the manifest is unproven this run`); continue; }
      if (control.status === 200) { bad(`net ${e.id}: host answers 200 to a nonsense path — a 200 on the manifest proves nothing`); continue; }
      if (m.status !== 200) { bad(`net ${e.id}: ${murl} returned ${m.status || `no answer (${m.err})`} — the level this registry badges is compared against nothing`); continue; }
      // The listed url is the one a chip carries. A manifest that is only alive
      // via an off-origin redirect means the chip's own origin no longer serves
      // it — the exact class that left KUNAI-001's chip dead: alive somewhere
      // is not alive at the URL in someone's hand. Same-origin path redirects
      // (a /av -> /av/ slash fix) stay legal.
      if (new URL(m.finalUrl).origin !== new URL(murl).origin) {
        bad(`net ${e.id}: ${murl} answers only via an off-origin redirect to ${m.finalUrl} — the listed url itself is not serving this manifest`); continue;
      }
      let declared;
      try { declared = JSON.parse(m.text); } catch (err) {
        // Same rule as check 7: an unparseable 200 scores as a pass and
        // reports a level, which is exactly why it must not.
        bad(`net ${e.id}: ${murl} is 200 but does not parse (${err.message})`); continue;
      }
      if (!String(declared.spec || '').startsWith('wish-it-better/')) {
        bad(`net ${e.id}: published manifest declares spec "${declared.spec}" — not a wish-it-better manifest`);
      } else if (typeof e.level !== 'string' || !e.level) {
        // Two absent levels would otherwise "agree" — a comparison of nothing
        // with nothing must not read as a pass.
        bad(`net ${e.id}: registry entry carries no level to check against`);
      } else if (typeof declared.level !== 'string' || !declared.level) {
        bad(`net ${e.id}: published manifest declares no level — nothing to agree with the ${e.level} badge here`);
      } else if (declared.level !== e.level) {
        bad(`net ${e.id}: badged ${e.level} here but the published manifest declares ${declared.level} — the registry is claiming a level the project no longer does`);
      } else {
        ok(`net ${e.id}: ${murl} 200 (control non-200), level ${declared.level} agrees`);
      }
      publishedManifest.set(e.id, declared);
    }

    // 9b. CRITERION 5 — "Origin declared if it is a spinoff" — which until now was
    //     the ONE criterion in the list with no arm at all, on a network where
    //     every single manifest declared origin: null.
    //
    //     A null there is not a neutral empty field. It is a positive claim that
    //     nothing upstream exists, and an audit of all five projects found real
    //     lineage behind every one of them: a vendored MIT QR generator, a sibling
    //     LISTED project's enclosure geometry adopted verbatim, a licence
    //     inherited from a host repo rather than chosen, this very spec copied
    //     byte-for-byte between two listed repos. The standard's own author was
    //     the loudest offender, which is the shape this class always takes.
    //
    //     THE PART WORTH REMEMBERING, because it says why prose could never have
    //     caught this: the lineage was already written down every time — in a
    //     generator's header comment, in a vendor file's second paragraph, in a
    //     credit printed on the live page. Provenance was never unknown. Only the
    //     one machine-readable field whose entire job is to carry it said nothing,
    //     and a field nothing reads is a field nothing can sweep.
    //
    //     So an entry must SAY which case it is in. A non-empty origin declares
    //     lineage. The literal "none-found" declares a MEASURED absence and must
    //     carry origin_evidence naming what was searched to earn it. A bare null —
    //     the unfilled default — is the single thing that no longer passes, for
    //     the reason it existed: it is indistinguishable from nobody having looked.
    for (const e of listedEntries) {
      const declaredOrigin = e.origin;
      if (declaredOrigin === null || declaredOrigin === undefined) {
        bad(`net ${e.id}: origin is ${declaredOrigin === undefined ? 'absent' : 'null'} — criterion 5 reads that as "not a spinoff, nothing upstream", which is a claim. Declare the lineage, or write "none-found" with origin_evidence naming what was searched`);
      } else if (typeof declaredOrigin !== 'string' || !declaredOrigin.trim()) {
        bad(`net ${e.id}: origin is ${JSON.stringify(declaredOrigin)} — an empty or non-string origin is the null case wearing a different type`);
      } else if (declaredOrigin.trim() === 'none-found') {
        // A measured null is a real and valuable result — but only if it names
        // the search that earned it. Without that it is the bare null again,
        // spelled out, and this arm would have taught the network a new way to
        // say nothing.
        const ev = typeof e.origin_evidence === 'string' ? e.origin_evidence.trim() : '';
        if (!ev) bad(`net ${e.id}: origin "none-found" with no origin_evidence — an absence nobody can audit is not a measurement`);
        else ok(`net ${e.id}: origin measured absent, evidence names what was searched`);
      } else {
        ok(`net ${e.id}: origin declared (${declaredOrigin.trim().slice(0, 60)}${declaredOrigin.trim().length > 60 ? '…' : ''})`);
      }

      // The published manifest is the copy a card holder's agent would read. It
      // may legitimately lag this file — a sibling repo deploys on its own clock
      // — so a MISSING origin there is reported and not failed. What is failed is
      // a CONTRADICTION: two records that disagree about where a thing came from
      // are worse than one record that is silent, because both look authoritative.
      const pub = publishedManifest.get(e.id);
      if (pub && typeof declaredOrigin === 'string' && declaredOrigin.trim() && declaredOrigin.trim() !== 'none-found') {
        // MANY LISTED ENTRIES, ONE PUBLISHED MANIFEST — the case 9c thirty lines
        // below already models and this arm did not. Two entries on this network
        // share one repo, and that repo's deploy stages ONE tracked manifest into
        // /av/ and /collage/, failing closed if a per-surface copy ever differs.
        // So the comparison below is not two records disagreeing; it is one record
        // being asked to be two, and it CANNOT pass for both: whichever origin is
        // published, the other entry reads it as a contradiction and fails. This
        // would not have failed here on a dev's machine — it fails on the 07:17
        // cron in network-sweep.yml, in a repo nobody had open.
        //
        // De-duplicated on manifest CONTENT, not URL. The URLs genuinely differ
        // (…/av/ and …/collage/); it is the bytes that are the same file, and the
        // bytes are what carries the single `origin`. Keying on URL would have
        // looked like the same fix and caught nothing.
        //
        // Reported, not failed, and that is a judgement rather than a dodge: the
        // sharers' repo forbids per-surface manifests by construction, so failing
        // here would red a gate over a state this repo cannot fix, which is the
        // shape of an alarm people learn to ignore. It names both ways out instead.
        const key = JSON.stringify(pub);
        const sharers = listedEntries.filter((o) => {
          const p = publishedManifest.get(o.id);
          return p && JSON.stringify(p) === key;
        });
        const disagree = sharers.some((o) => String(o.origin || '').trim() !== declaredOrigin.trim());
        if (sharers.length > 1 && disagree) {
          console.log(`  --   net ${e.id}: shares one published manifest with ${sharers.filter((o) => o.id !== e.id).map((o) => o.id).join(', ')} — byte-identical copies of a single file, which can carry only ONE origin, while these entries declare different ones. Criterion 5 is unclosable for at least one of them until the registry gives the sharers one agreed origin, or their repo publishes a per-surface manifest`);
        } else if (pub.origin === null || pub.origin === undefined) {
          console.log(`  --   net ${e.id}: published manifest still declares no origin while this registry declares one — the project's own copy has not caught up`);
        } else if (String(pub.origin).trim() !== declaredOrigin.trim()) {
          bad(`net ${e.id}: registry and published manifest give DIFFERENT origins — "${declaredOrigin.trim().slice(0, 40)}…" here vs "${String(pub.origin).trim().slice(0, 40)}…" published`);
        } else {
          // Agreement printed nothing until now, so a cycle that closed an origin
          // left a transcript identical to one where the arm never ran — and this
          // file says elsewhere that silence and "swept clean" are the same shape.
          ok(`net ${e.id}: published manifest declares the same origin as this registry`);
        }
      }
    }

    // 9c. THE OPERAND THAT HAS LEFT THIS LAPTOP.
    //     9b compares two records the claimant wrote, so the honest question —
    //     what is the cheapest change to production this arm would NOT notice? —
    //     has an uncomfortable answer: a project quietly acquiring a new parent,
    //     forking something or vendoring a library, and simply not saying. No
    //     amount of extra local operands fixes that; three local operands do not
    //     compose into one remote one.
    //     There is exactly one upstream fact about lineage this network can read
    //     from OUTSIDE itself, and no edit in this repo can set it: GitHub's own
    //     fork bit. If the API says a listed repo IS a fork while its entry claims
    //     a measured absence, that is a contradiction with an independent witness.
    //     Narrow, but it is the only claim here that is not self-reported.
    //     Repos are de-duplicated: two listed entries share one repo on this
    //     network today, and asking twice would double the rate-limit cost to
    //     learn the same bit.
    const repos = new Map();
    for (const e of listedEntries) {
      const m = /^https?:\/\/github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/*$/i.exec(String(e.repo || ''));
      if (m) {
        const key = `${m[1]}/${m[2]}`;
        if (!repos.has(key)) repos.set(key, []);
        repos.get(key).push(e);
      }
    }
    for (const [slug, ents] of repos) {
      const r = await get(`https://api.github.com/repos/${slug}`);
      // A probe that could not LOOK must not report a verdict. The rate limit is
      // 60/hour unauthenticated and this mode is opt-in, so a 403 here is ordinary
      // and must read as "could not check" — never as "not a fork".
      if (r.status !== 200) {
        console.log(`  --   net fork-witness ${slug}: API answered ${r.status || `nothing (${r.err})`} — could not check, so no verdict either way`);
        continue;
      }
      let api; try { api = JSON.parse(r.text); } catch { console.log(`  --   net fork-witness ${slug}: API 200 did not parse — could not check`); continue; }
      const parent = api.parent && api.parent.full_name;
      if (api.fork !== true) { ok(`net fork-witness ${slug}: GitHub reports fork=false — no upstream repo to declare`); continue; }
      for (const e of ents) {
        const o = typeof e.origin === 'string' ? e.origin.trim() : '';
        if (!o || o === 'none-found') bad(`net ${e.id}: GitHub reports ${slug} IS a fork${parent ? ` of ${parent}` : ''}, but the entry declares ${o === 'none-found' ? 'a measured absence' : 'no origin'} — an independent witness contradicts the record`);
        else ok(`net ${e.id}: ${slug} is a fork${parent ? ` of ${parent}` : ''} and the entry declares an origin`);
      }
    }

    // 10. CARD DESTINATIONS. The other half of the sweep, and the half that has
    //     actually failed in the field: a chip is permanent, so the URL burned
    //     into it can never change, and one of them was dead for weeks with
    //     nothing to notice. It went unnoticed because the only record of that
    //     URL anywhere was a sentence in curation.note, and a sentence cannot be
    //     swept. registry.cards.destinations is that record as data.
    //
    //     THIS IS NOW THE LIVENESS HALF ONLY. Whether a row points at the project
    //     it names is check 8b, which needs no network and therefore runs on every
    //     build instead of once a night. What is left here is the question that
    //     genuinely requires reaching a host: does this URL still land where the
    //     record says it lands. The two are complementary and neither is the
    //     other — 8b would pass a row whose destination is correct and dead, and
    //     this loop passed a KUNAI card pointing at Collage Studio for as long as
    //     the row agreed with itself.
    //
    //     WHY THIS COMPARES THE FINAL URL AND IGNORES THE STATUS CODE. The
    //     obvious check — "does it 200?" — is worthless on the host that carries
    //     the one chip URL we have. persona500.com/c/<slug> is a redirector with
    //     a DEFAULT FALLBACK: an unmapped slug 302s to the vibe-cards site root
    //     and answers a perfectly healthy 200. Measured 2026-08-14, GT-001's slug
    //     and a freshly generated random control were byte-identical to each
    //     other. So a card carrying an unmapped slug passes a status check while
    //     landing its holder on the wrong page. Only the destination discriminates.
    //
    //     Hence the control rule: the control must not land where we expect to
    //     land, must not answer 200 in place, and must not land somewhere still
    //     carrying our own nonsense segment. On GitHub Pages it 404s; on the
    //     redirector it 302s to the fallback.
    //       Check 9 above fails on ANY 200 control, which is right for a manifest
    //     on a file host and WRONG here: this redirector's control legitimately
    //     answers 200, because falling through to a default IS a 200. The two
    //     rules differ on purpose, and an earlier draft of this comment claimed a
    //     parity that does not exist. What both reach for is one idea — a control
    //     that answers the way the real URL does has told you nothing about the
    //     real URL.
    const cardRows = (registry.cards && registry.cards.destinations) || [];
    // THE PARTITION MUST BE EXHAUSTIVE, and this file has now learned that twice.
    // The first draft split rows into "has url AND resolves_to" and "has no url",
    // which is not a partition: a row carrying a url with no measured destination
    // fell into neither and was named NOWHERE, while the tally said "0 unrecorded
    // (none)". A row that vanishes reads, in the transcript, exactly like a row
    // that passed — the precise failure this check exists to end, reproduced
    // inside the check itself. The arithmetic assertion below is a TRIPWIRE, not a
    // proof: as long as the three predicates stay as written it is a tautology and
    // can never fire, which an audit of this file established by enumerating 169
    // (url, resolves_to) combinations. It earns its keep only on the day someone
    // narrows a predicate — that is the day the first draft's hole reopens, and it
    // is the only day this line has anything to say.
    const swept = cardRows.filter((c) => c.url && c.resolves_to);
    const unrecorded = cardRows.filter((c) => !c.url);
    const unswept = cardRows.filter((c) => c.url && !c.resolves_to);
    const name = (c) => `${c.card || c.project || '?'}/${c.surface}`;
    if (swept.length + unrecorded.length + unswept.length !== cardRows.length) {
      bad(`card destinations: ${cardRows.length} row(s) but ${swept.length + unrecorded.length + unswept.length} accounted for — some row is in no bucket and would be checked by nothing`);
    }
    console.log(`  --   card destinations: ${cardRows.length} row(s) = ${swept.length} swept + ${unrecorded.length} unrecorded (${unrecorded.map(name).join(', ') || 'none'}) + ${unswept.length} url-but-no-measured-destination (${unswept.map(name).join(', ') || 'none'})`);
    // The coverage arm — every listed project must have a ROW — used to sit here
    // and now runs in check 8b, on every build. It never needed this flag: it is
    // a join over one repo file and can only break on an edit to that file, so
    // behind the flag it could fire only on a schedule that is deliberately
    // forbidden to block a deploy. What is left below is the half that genuinely
    // fetches, which is the only thing this flag is for.
    const CONTROL_SEG = 'zz-control-for-the-card-sweep';
    const norm = (u) => {
      try {
        const x = new URL(String(u));
        // Scheme and host are case-insensitive per RFC 3986 and the default port
        // is not part of identity; the PATH is case-sensitive, so lowercasing the
        // whole string would make two different pages compare equal.
        return `${x.protocol.toLowerCase()}//${x.host.toLowerCase()}${x.pathname.replace(/\/+$/, '')}${x.search}`;
      } catch { return String(u).replace(/\/+$/, ''); }
    };
    for (const c of swept) {
      const who = name(c);
      if (!/^https?:/i.test(c.url)) { bad(`card ${who}: recorded url "${c.url}" is not fetchable`); continue; }
      // Same-SITE control, with a fixed nonsense segment — fixed and not random
      // because a scheduled gate that fails must be reproducible by hand, and
      // nobody can re-run a random token tomorrow.
      //
      // WHY THE SHAPE OF THE PATH DECIDES SWAP-vs-APPEND, and why "always append"
      // is wrong. With two or more segments the last one is the identifier and
      // the prefix selects the route, so swapping it (/c/<slug>, /vibe-cards/<page>/)
      // asks the right question. With one segment there is no sibling to swap:
      // /vibe-cards/ IS the site, and replacing it hands the control to GitHub
      // Pages' USER-site route — a different server answering a different
      // question ("Site not found", because no mrdirno.github.io user site
      // exists) rather than the project site's own "Page not found". Appending
      // there keeps the control inside the site under test.
      //   And the converse, measured on the live redirector: appending to
      //   /c/KUNAI-001 gives /c/KUNAI-001/<seg>, which 404s without ever reaching
      //   the /c/<slug> route, so the control would pass trivially and an unmapped
      //   slug falling back to the site root would go unnoticed — the exact trap
      //   the paragraph above this loop exists to describe. Neither rule alone works.
      let controls;
      try {
        const u0 = new URL(c.url);
        const trailing = u0.pathname.endsWith('/');
        const segs = u0.pathname.split('/').filter(Boolean);
        const mk = (parts) => {
          const u = new URL(c.url);
          // A control that inherits ?query or #hash can be routed by it, and a
          // redirector keyed on a parameter would send the control to the real
          // destination — failing a healthy card with a message that is untrue.
          u.search = ''; u.hash = '';
          u.pathname = `/${parts.join('/')}${trailing ? '/' : ''}`;
          return u.toString();
        };
        // ONE SEGMENT IS AMBIGUOUS, AND NO SINGLE RULE READS IT CORRECTLY — which
        // is why both controls are fetched instead of choosing. https://host/x/
        // is either a SITE (GitHub Pages project page: the sibling /zz-control/
        // is answered by the user-site route, a different server answering a
        // different question) or an IDENTIFIER (a root-mounted redirector or a
        // link shortener: the child /x/zz-control 404s without ever reaching the
        // slug route, so it passes trivially and an unmapped slug falling through
        // to a default sweeps green). Each rule fails open on the other's shape,
        // and the URL cannot tell you which shape it is. Two probes; either one
        // showing non-discrimination is disqualifying.
        controls = segs.length >= 2
          ? [mk([...segs.slice(0, -1), CONTROL_SEG])]
          : [mk([CONTROL_SEG]), mk([...segs, CONTROL_SEG])];
      } catch (err) { bad(`card ${who}: url "${c.url}" does not parse (${err.message})`); continue; }
      const [r, ...ctls] = await Promise.all([get(c.url), ...controls.map((x) => get(x))]);
      if (r.status === 0) { bad(`card ${who}: ${c.url} did not answer (${r.err}) — a card in someone's hand points here`); continue; }
      // THE PRIMARY FACT FIRST, and it must outrank the control's own troubles:
      // that a card in someone's hand points at a 404 is the single most important
      // sentence this gate can print, and it was unreachable while any control
      // branch ran ahead of it.
      if (r.status !== 200) { bad(`card ${who}: ${c.url} returned ${r.status} — this URL is printed on a card and cannot be changed`); continue; }
      // Three ways a control proves the host is not discriminating. The third —
      // the final URL containing our own nonsense segment — catches the host that
      // DERIVES its destination from the path instead of looking it up (a bare
      // `/c/* -> /:splat` rule with no table at all): it lands somewhere new, so
      // the first two arms miss it, while proving no mapping exists.
      let problem = null;
      for (const [i, ctl] of ctls.entries()) {
        const ctlUrl = controls[i];
        if (ctl.status === 0) { problem = `the control ${ctlUrl} did not answer (${ctl.err}) — cannot prove this host discriminates, so today's result is unproven`; break; }
        if (ctl.status !== 200) continue;
        if (norm(ctl.finalUrl) === norm(ctlUrl)) { problem = `the control ${ctlUrl} answers 200 in place — this host serves 200 to any path, so ${c.url}'s 200 proves nothing`; break; }
        if (norm(ctl.finalUrl) === norm(c.resolves_to)) { problem = `a nonsense sibling reaches ${ctl.finalUrl} too — this host answers the same way for anything, so reaching ${c.resolves_to} proves no mapping exists`; break; }
        if (norm(ctl.finalUrl).includes(CONTROL_SEG)) { problem = `the control ${ctlUrl} lands on ${ctl.finalUrl}, which still carries our own nonsense segment — this host builds a destination out of whatever path it is given rather than looking one up, so ${c.url} resolving proves no mapping exists`; break; }
      }
      if (problem) { bad(`card ${who}: ${problem}`); continue; }
      if (norm(r.finalUrl) !== norm(c.resolves_to)) {
        // Both directions are failures and the second one is why this gate is
        // worth running on a clock. A destination that DIES is the loud case. A
        // destination that quietly comes BACK — because someone served the
        // redirect the ask had been filed for — leaves the registry asserting a
        // death that ended, and nothing here would ever notice the good news.
        // That second direction is only reachable for a row whose recorded
        // resolves_to is where it lands TODAY; a row recording a dead URL as
        // resolves_to:null is in the unswept bucket above, named but not fetched.
        bad(`card ${who}: ${c.url} now lands on ${r.finalUrl}, but this registry records ${c.resolves_to} — either the destination moved, or it was fixed and nobody updated the record`); continue;
      }
      ok(`card ${who}: ${c.url} -> ${c.resolves_to} (${ctls.length} control(s) discriminate: ${controls.map((x, i) => `${x} ${ctls[i].status}`).join(', ')})`);
    }
  }
}

console.log(fail.length ? `\n${fail.length} problem(s) — the deploy would be green over a dead site.`
                        : `\nArtifact complete: ${entries.size} files, all references resolve.`);
process.exit(fail.length ? 1 : 0);
