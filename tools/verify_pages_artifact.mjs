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
    const listedEntries = JSON.parse(fs.readFileSync(regFile, 'utf8')).listed || [];
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
    }
  }
}

console.log(fail.length ? `\n${fail.length} problem(s) — the deploy would be green over a dead site.`
                        : `\nArtifact complete: ${entries.size} files, all references resolve.`);
process.exit(fail.length ? 1 : 0);
