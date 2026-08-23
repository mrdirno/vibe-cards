/**
 * CROSS-PAGE FRAGMENTS RESOLVE — the gate.
 *
 *   node tools/verify_fragments.mjs [site-dir]        # default: _site
 *
 * verify_pages_artifact.mjs checks that every href's PATH exists in the artifact and
 * says, in its own words, "the fragment is the browser's business". It is — until one
 * page deletes a section and another page keeps linking to it. On 2026-08-23 the deck's
 * #panel-fo section left with the LEVIATHAN engine (deck RING 3) while ../leviathan/
 * kept a button pointing at it: the path resolved, the deploy stayed green, and the
 * button landed a visitor at the top of a page that had nothing for them. A fragment is
 * a promise about the TARGET document, and only the build holds both documents at once.
 *
 * WHAT IT CHECKS: every href in every .html document that carries a #fragment and
 * resolves to a document IN THIS SITE (the same page, or a relative path) must name an
 * element that exists there — id="…" or <a name="…">. External URLs are not ours to
 * check. A bare "#" (a script hook) and "#top" (every browser honours it without an
 * element) are exempt, and the exemption is written here so it is a choice, not a hole.
 * E3: the summary prints the denominator — documents read, links checked, exemptions.
 * KNOWN LIMIT, named (E4): ids assigned by script at runtime are invisible here, the
 * same way they are invisible to a crawler.
 */

import fs from 'node:fs';
import path from 'node:path';

const site = path.resolve(process.argv[2] || '_site');
if (!fs.existsSync(site)) {
  console.error(`FAIL: ${site} does not exist — build first (python3 tools/build_site.py)`);
  process.exit(2);
}

const docs = [];
(function walk(dir, prefix = '') {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${e.name}` : e.name;
    if (e.isDirectory()) walk(path.join(dir, e.name), rel);
    else if (e.name.endsWith('.html')) docs.push(rel);
  }
})(site);
docs.sort();

// MARKUP ONLY. The first run of this gate passed the exact dead link it was written
// for: the deck's RING 2 change log — an HTML comment — says `id="panel-fo"` in prose,
// so the deleted section was "found". A comment, a <script> body and a <style> block
// are not places a fragment can land, and a gate that reads them measures the page's
// diary instead of its body. (Found by running the gate on the build that still had
// the dead link, E1 — the observation that had to fail, and did not.)
const text = new Map();
const read = (rel) => {
  if (!text.has(rel)) {
    text.set(rel, fs.readFileSync(path.join(site, rel), 'utf8')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/<script\b[\s\S]*?<\/script>/gi, '')
      .replace(/<style\b[\s\S]*?<\/style>/gi, ''));
  }
  return text.get(rel);
};
const anchors = new Map();
const anchorsOf = (rel) => {
  if (!anchors.has(rel)) {
    const set = new Set();
    const doc = read(rel);
    for (const m of doc.matchAll(/(?<![\w-])id\s*=\s*("([^"]*)"|'([^']*)')/gi)) set.add(m[2] ?? m[3]);
    for (const m of doc.matchAll(/<a\b[^>]*\bname\s*=\s*("([^"]*)"|'([^']*)')/gi)) set.add(m[2] ?? m[3]);
    anchors.set(rel, set);
  }
  return anchors.get(rel);
};

const EXEMPT = new Set(['', 'top']);
let checked = 0, exempt = 0, offsite = 0;
const misses = [];
const docSet = new Set(docs);

for (const rel of docs) {
  const dir = path.posix.dirname(rel) === '.' ? '' : path.posix.dirname(rel);
  const doc = read(rel);
  for (const m of doc.matchAll(/(?<![\w-])href\s*=\s*("([^"]*)"|'([^']*)')/gi)) {
    const raw = (m[2] ?? m[3]).trim();
    const hash = raw.indexOf('#');
    if (hash < 0) continue;
    if (/^(https?:|data:|mailto:|tel:|sms:|javascript:|\/\/)/i.test(raw)) { offsite++; continue; }
    let frag = raw.slice(hash + 1);
    try { frag = decodeURIComponent(frag); } catch { /* keep raw */ }
    if (EXEMPT.has(frag)) { exempt++; continue; }
    const p = raw.slice(0, hash).replace(/\?.*$/, '');
    let target;
    if (!p) target = rel;
    else {
      target = path.posix.normalize(path.posix.join(dir, p));
      if (target === '.' || target === './') target = 'index.html';
      if (!docSet.has(target) && docSet.has(path.posix.join(target, 'index.html'))) {
        target = path.posix.join(target, 'index.html');
      }
      if (!docSet.has(target)) continue;   /* a missing PATH is the artifact gate's finding, not this one's */
    }
    checked++;
    if (!anchorsOf(target).has(frag)) misses.push(`${rel}: href="${raw}" — ${target} has no id or name "${frag}"`);
  }
}

console.log(`fragments: ${checked} link(s) checked across ${docs.length} document(s) · ${exempt} exempt (# / #top) · ${offsite} off-site left to their owners`);
for (const miss of misses) console.log('FAIL: ' + miss);
if (misses.length) {
  console.log(`FAIL: ${misses.length} fragment link(s) name an element the target page does not have.`);
  console.log('FAIL:   FIX: point the href at an id that exists, or restore the section it promised.');
  process.exit(1);
}
console.log('ok: every in-site fragment resolves');
