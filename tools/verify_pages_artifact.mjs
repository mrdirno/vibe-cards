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
        if (pub.origin === null || pub.origin === undefined) {
          console.log(`  --   net ${e.id}: published manifest still declares no origin while this registry declares one — the project's own copy has not caught up`);
        } else if (String(pub.origin).trim() !== declaredOrigin.trim()) {
          bad(`net ${e.id}: registry and published manifest give DIFFERENT origins — "${declaredOrigin.trim().slice(0, 40)}…" here vs "${String(pub.origin).trim().slice(0, 40)}…" published`);
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
    // COUNT IS NOT COVERAGE. Everything above iterates rows, so a project nobody
    // wrote a row for is invisible to it — and on the day this block shipped, two
    // listed projects had zero rows while a prose field two lines above them
    // recorded having measured their live destinations. The measurement existed;
    // the row did not; nothing swept them.
    //
    // WHAT THIS DOES AND DOES NOT ASSERT, because the distinction is load-bearing
    // and the first draft of this comment got it wrong. It does NOT make `card`
    // a listing gate — this registry's own curation note concluded that `criteria`
    // governs promotion and `criteria` has five items, none of them a card. It
    // asserts something narrower and purely internal: every listed project must
    // have a ROW, including a row whose url is null saying it has no recorded
    // destination. Absence is a fine answer; silence is not, because silence and
    // "swept clean" are the same shape in a transcript. Held entries are exempt:
    // being held is already the record that a part is missing.
    const listedIds = (registry.listed || []).map((p) => p.id);
    const heldIds = (registry.held || []).map((p) => p.id);
    const covered = new Set(cardRows.map((c) => c.project).filter(Boolean));
    const uncovered = listedIds.filter((id) => !covered.has(id));
    console.log(`  --   card coverage: ${listedIds.length - uncovered.length}/${listedIds.length} listed + ${heldIds.filter((id) => covered.has(id)).length}/${heldIds.length} held project(s) have a destination row`);
    for (const id of uncovered) {
      bad(`card coverage ${id}: listed, but no row in cards.destinations — not even one recording that it has no known card destination, so nothing here can tell "swept clean" from "never looked"`);
    }
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
