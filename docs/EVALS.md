# Evals — Card Studio

The [Wish It Better](../WISH_IT_BETTER.md) standard says an eval must be able to fail, must
check the artifact a user touches, and must name its own limits. This file is the record
of the evals actually run, not a description of evals that could be run.

Format for every entry: **claim · how it could have failed · what was observed · limits.**

---

## Harnesses

| Harness | What it drives | Where |
|---|---|---|
| Live-exploit curl suite | The real HTTP server, patched vs. unpatched | §1 below |
| Playwright first-run harness | The real app in a real browser, real drop events | §2 below |
| Fresh-user isolation | The app under a clean `HOME` with no personal overlay | §3 below |
| Phone reachability | The shipped page on WebKit and Chromium, panels opened and tapped | §5 below |

There is no mocking anywhere in this list, on purpose. Every harness drives the shipped
server and the shipped page. See E2 in the standard for why.

---

## 1. Security — local server hardening

**Claim.** A local page cannot read files from the user's home directory, and a web page
the user visits cannot make this app do anything.

**How it could have failed.** Any of the four probes below returning `200` with a body.
All four *did* return exploitable results before the fix — that is what motivated it.

**Observed** (patched server, live, both states measured):

| Probe | Before | After |
|---|---|---|
| `GET /api/design/%2FUsers%2F<user>%2F.docker%2Fconfig.json` | `200` + file body | `404` |
| `GET /api/design/..%2F..%2F..%2F..%2F.docker%2Fconfig.json` | `200` + file body | `404` |
| `POST /api/quit` with no token | `200` `{"ok":true}`, server died | `403` |
| `POST /api/quit` with `Origin: https://evil.example.com` | `200` | `403` |
| `GET /` with `Host: evil.example.com` (rebinding) | `200` | `403` |
| Legitimate client: `/api/bootstrap`, `/api/designs`, `/api/ping` | `200` | `200` |

The last row is the control. A guard that also breaks the real client is not a fix.

**Limits.** These probes cover the four routes the audit proved exploitable. They are not
a full fuzz of every endpoint, and no static analysis was run over `pdfwriter.py`. The
`Host` allow-list assumes the server keeps binding to loopback; if that ever changes, this
eval no longer covers the threat it was written for.

---

## 2. First run and the import path

**Claim.** The app opens blank, tells a new user what to do, and the empty-state overlay
does not break the drag-and-drop it is advertising.

**How it could have failed.** The overlay sits *on top of* `#canvasWrap`, which owns the
`dragover`/`drop` handlers. If `pointer-events` were wrong, the panel telling you to drop
a photo would be the thing eating the drop. This is the exact hazard, so it is measured
directly with `elementFromPoint` rather than assumed.

**Observed:**

```
elementsOnBoot (front/back) : 0 / 0        — opens blank
emptyStateVisible           : true
hitTest.centerTarget        : "canvas"     — overlay is transparent to hits
hitTest.centerIsOverlay     : false        — the actual assertion
hitTest.buttonTarget        : "ceChoose"   — buttons still clickable
drop at overlay centre      : 1 element, type "image"
emptyStateAfterDrop         : false        — clears on first content
consoleErrors               : []
```

**Limits.** Drop is dispatched as a synthetic `DragEvent` with a real `File`, not an OS
drag. It exercises the app's handlers and hit-testing; it does not exercise Chrome's own
file-drag plumbing.

---

## 3. Recovery, and not destroying work

**Claim.** Saved cards can be reopened; unsaved work is not silently discarded.

**How it could have failed.** Before this eval, `Save` wrote a file the UI had no way to
read back — the write path existed and the read path did not. The measurement is a round
trip, because only a round trip could have caught it.

**Observed:**

```
cleanOnBoot        : true          — a blank card is not "unsaved work"
dirtyAfterEdit     : true
cleanAfterSave     : true
savedElements      : 6
afterWipe          : 0             — document destroyed in memory
elementsAfterOpen  : 6             — recovered from disk
nameAfterOpen      : "HarnessCard"
cleanAfterOpen     : true
template-on-busy   : prompted, work preserved when declined
```

**Limits.** The overwrite prompt and the close-window prompt are driven by auto-accepting
dialogs; a human misreading the prompt is not modelled. Image-heavy documents are not
size-tested — a very large embedded photo may make the dirty-check snapshot expensive.

---

## 4. Fresh user — no personal data ships

**Claim.** A stranger who clones this repo gets a working app with none of the author's
hardware, purchases, or scanned card IDs in it.

**How it could have failed.** The Supplies tab used to ship one person's reader, their
purchase, and evidence derived from their scanned card UIDs. The measurement runs the
server under an isolated `HOME` so the personal overlay cannot possibly be found.

**Observed:**

```
your_reader panel  : ABSENT   (renders 0 .sup-reader elements)
owned card block   : ABSENT   (renders 0 .sup-card.is-owned)
supply cards       : 5 render normally
consoleErrors      : []
grep for personal markers in shipped supplies.json : NONE
```

The same server, with the author's real `HOME`, renders both — so the feature works and
the data is simply not in the repo.

**Limits.** The marker grep is a fixed keyword list (reader model, owner name, machine
paths). It would not catch a personal detail phrased in a way nobody thought to search
for. This is E3 in the standard: the check is real, and its denominator is a word list.

---

## 5. Reachability on a phone — the control you can actually use

**Claim.** Every control the studio offers a phone can be reached with a finger: the
empty state's template button lands you on the picker, both topbar panels open inside the
screen, and the Send button that files a wish receives the tap.

**How it could have failed.** It did fail, in the only way that counts — reported from a
phone, twice inside two hours, the second time after nothing had changed. Per §1 of the
standard the queue itself stays private, so what is published here is the defect and the
fix, measured; the reports are what pointed at them.

`tools/verify_mobile.mjs` reported /studio/ watertight at all four widths throughout. It
was not wrong; it measures the page **at rest**, and both defects live in state it never
enters. A panel is only wrong once it is opened.

**Observed** — `tools/verify_phone_reach.mjs`, both engines, four widths, before and
after. The "before" column is the shipped code at `96b231b`:

| | Before | After |
|---|---|---|
| `#templateSel` after tapping *Start from a template* | `0×0`, no sheet raised | `272×23`, Card sheet up, picker pinged |
| `#wishPop` at 390px | `L-186 R134` — 186px off the left | `L0 R390 T594 B788` |
| `#openMenu` at 390px | `L-62 R198` | `L0 R390 T734 B788` |
| `#wishSend` under `elementFromPoint` | — | `wishSend` |
| findings, 2 engines × 4 widths | **24** | **0** |

Three separate causes, and the third only appeared because the fix was measured rather
than looked at:

1. On a phone `#templateSel` sits inside the left rail's Card block, and that rail is a
   sheet that is down by default — `display:none`, so `focus()` landed on nothing,
   `showPicker()` threw `InvalidStateError`, and the `.is-pinged` fallback animated a
   border with no pixels behind it. WebKit has no `showPicker()` at all, which is the
   engine the report came from.
2. Both popovers are `position:absolute; right:0` inside a wrapper the width of their own
   button — correct against a desktop bar pinned to the right edge, and 186px off the
   screen against a phone action row that is not.
3. Pinning them to the bottom put `#wishSend` **under the dock**, and then under a raised
   rail's scrim: on screen, correctly sized, and untappable. The tap that submits a wish
   would instead have dismissed it and discarded what was typed.

**Limits.** The harness taps four controls, not every control — it proves the two that
were reported and the one that shares their geometry, and says nothing about the rest of
the app's phone surface. It cannot see the on-screen keyboard: `--kb` is asserted only by
the CSS reading `visualViewport`, never by a real keyboard being raised. `elementFromPoint`
tests one point, the centre, so an element covered at its edges reads as reachable. And
this is E3 in the standard — the denominator is the list of controls someone thought to
name, which is exactly how the two in it went unnoticed until a person on a phone said so.

---

## 6. The level — L1 was declared, L0 was earned

**Claim.** The level this project declares in `wish-it-better.json` is one it has earned
under §3 of the standard. Until 2026-08-19 that declaration was `L1`: L0 plus *every shipped
change carries an eval meeting §2* plus *wishes reach a terminal state*.

**How it could have failed.** Written before the ledger was read: if every commit shipped
since `L1` was declared carried a written failing condition (E1) and a check at the artifact
(E2) — or added a gate that fails on regression of that change — then `L1` stands and no
file changes. One commit without one falsifies *every*; the count only sets the size of
the miss. `L1` was declared in `d2fbaac` (2026-08-09), the repository's second commit,
with nothing measured under it.

**What was observed.** The terminal-state clause holds: `tools/wishing_well.py --stats` on
2026-08-19 shows VIBE-CARDS-001 at 19 shipped + 7 declined, 0 new, 0 building. The eval
clause does not. All **179** commits in `d2fbaac..d02631d` were read in full — message and
diffstat, six readers against one written rubric, no sampling — and classified:

| Class | Rule | Count |
|---|---|---|
| EVAL | the message states a failing condition / before-state AND a check at the artifact or a measured after-state; or states E1 and the diff adds a check that fails on regression of this change | **113** |
| MEASURED | a number, before/after or at-artifact check, but no written failing condition; or the only check is at the source | **45** |
| NONE | the message only describes what changed (or is subject-only) and the diff adds no check that can fail for it | **21** |

66 of 179 (37%) are below the bar. Two have no body at all (`9adbf8b`, a one-line CSS
change; `9c5ee6d`, one manifest field). This file — the one the manifest names under
`evals` — had last been touched on 2026-08-17 (`b3eef58`) when the ledger was read, and no
shipped change in between had added to it;
the repository has had zero pull requests, so the §2 PR checklist has gated nothing; and
the per-card manifests under `src/site/*/wish-it-better.json` already said *"shipped changes
here do not carry an eval meeting section 2"* about pages that live in this same ledger.

So the manifest now declares `L0`, the registry badges `L0`, and the sentence that did the
inflating is quoted in the manifest's own `_note` rather than deleted. This is the mirror
of the KUNAI-001 correction of 2026-08-14, which stayed at L0 because *an eval is not a
queue*; here a queue is not an eval.

The 66 non-EVAL commits, newest first, so the reading can be disputed commit by commit:

| Commit | Class | Body chars | Subject | Why |
|---|---|---|---|---|
| `9adbf8b` | NONE | 80 | The rainbow now arcs under the strip, not over the note a first visit is reading | Subject-only; one-line change in the garden page; no before/after, no measurement, no check. |
| `c3597fa` | NONE | 671 | The landing page now hands a visitor the finished thing, not just the source | Describes the strip and the IndexNow key; 'releases/latest resolves' is a claim; nothing measured or checked at the page. |
| `50223e4` | NONE | 559 | The chip doc now answers the phone question instead of leaving it to memory | Doc section added; 'checked against sources' is an unfalsifiable claim; no failing condition, no artifact check. |
| `8847291` | MEASURED | 648 | Every text box a phone touches now meets the 16px iOS stops zooming at | 16px threshold and cause (820px-scoped floor lost the cascade) named; only check is 'desktop computes value-identical'; no written falsifier, no… |
| `00c8755` | MEASURED | 558 | The book page said 'there is no card 008' after card 008 shipped | Before-state written (page said no card 008; /rexi/ and /kelibro/ live, images 200); after-state of the changed page not verified, no check added. |
| `fb1a0e7` | MEASURED | 449 | The gate said clear while the deploy would 404: an IGNORED file on the published | Failing condition named (gate clear while CI deploy 404s the ignored SVG); file force-added, no after check at the deploy, the gate fix is only a… |
| `193e74a` | MEASURED | 279 | The garden hums when asked to, off until tapped, appended after the bundle it ne | Only a source-level check: 180 inserted lines, minified bundle byte-untouched; no failing condition, nothing checked at the rendered page. |
| `83ab734` | NONE | 268 | Three tunes where one looped, and the arrival announced where the wish was made | Describes the SONGS array rotation and one entries row; no number, no before/after, no check. |
| `14351db` | MEASURED | 344 | A 1916 marimba record, public domain and said so, instead of no music at all | PD status verified at the Internet Archive item, 2.0MB mono noted; no failing condition and no check of the page's player. |
| `ba70d21` | NONE | 371 | The cutting file the page warned about is now the file the page hands you | Describes the download link, folded prose and linked faders; no measurement, no check. |
| `4c63394` | MEASURED | 236 | First read is the short story; the depth is one tap away | Before/after measured (visible prose 12,715 -> 5,395 chars, nothing deleted); no written failing condition; measured at source, not the rendered page. |
| `97ac2f2` | MEASURED | 459 | A 155-second export on the main thread reads as a dead page | Before-state measured (155-second export on the main thread); after design (~35ms slices) described, no after measurement, no check. |
| `6b10aac` | MEASURED | 413 | The tray never got a phone layout: 528 fixed pixels in a 390px window, half past | Before-state measured (528 fixed px in a 390px window); fit-to-container described, nothing measured after, no check. |
| `ea4794c` | MEASURED | 642 | Book One is not closed at seven — I read the shipped count as the total | Doc before-state wrong ('closed at seven') with the contradicting fact (manifest says 72, 7 shipped); no verification at any artifact, no check. |
| `fcfc039` | MEASURED | 425 | The tap mark ran its bottom edge through the address line | Overlap measured off the export (mark 42.98+8mm vs line at 50.75mm); new position 40.8 'clears it' by arithmetic, not re-measured on the new export. |
| `9908da0` | NONE | 1206 | A card family appeared between one git status and the next | Narrates the incident behind a CLAUDE.md note; no falsifier for the note, no check; the commit itself sweeps 51 files under a scar message. |
| `17cd99c` | MEASURED | 2506 | Three forms asked thirteen questions before anyone would read a sentence | Before-state counted (13 questions, 12 required) but no after verification at the artifact: issue chooser/textarea route never checked, no gate added. |
| `b3eef58` | NONE | 936 | The eval that proved the fix published the report it came from | Removes two quoted wishes from docs/EVALS.md; no failing condition, no measurement, no check that can fail. |
| `2e811e8` | MEASURED | 2954 | A manifest that measures its own repository is false on arrival | Refutations of the old manifests are written with numbers and size 8-12KB→~2.3KB, but new manifests never verified at the artifact or gate; no… |
| `38b8d5b` | MEASURED | 3311 | A carve-out written only in the file humans read is half a carve-out | Before-states measured (grep NOTICE=0, one LICENSE, no CC link), CC text sha256-checked, but 12 rendered #vc-card blocks never verified at the… |
| `66b65c5` | NONE | 1614 | Design note: GESICA as two faces of one picture | Design note; 'measurement' is a prose derivation: no number, no rendered check, no failing condition. Exclusions named (KELIBRO unmeasured,… |
| `6f43de0` | MEASURED | 1659 | Thirteen entries and none on the camioneta, the one object every holder of this  | Rendered bodies 180/179 chars vs 300 cap, 14 entries, 107 files, gates run; only failing condition is the pre-existing cap, no falsifier written… |
| `760e61c` | MEASURED | 1489 | The tap mark's colour was decided by squinting at a PNG | Measured 107.0/255 on card 006 matching the hand reading; disagreement reported, not a written falsifier; no before-state number ('squinting');… |
| `f599e31` | MEASURED | 2243 | The card reported blank kept its address, because the erase that could not find  | Failing condition written (5 headers: 3 bytes written/0 zeroed, reported ok) but untested on hardware by choice; evidence is source branch logic only. |
| `adccc98` | MEASURED | 1903 | A shredded card and a card that was never made looked exactly the same | Before counted (one UID in repo, in prose); four rows recorded, chips 'verified blank'; no falsifier written for the ledger itself; only generic… |
| `7c87b80` | MEASURED | 1413 | The package ships a list to check itself against, and the list describes a packa | Hash reconcile 7/5/1 (45,607 vs 57,979 bytes), curl exit 6 on frozen host; finding recorded as an entry, but no falsifier or render check for the… |
| `1967718` | NONE | 292 | The book group listed card 04 before card 03 | States the dropdown read 01 02 04 03 and moves entries; no after-state, no number, no check; pure reorder (27 lines moved). |
| `4a2f914` | MEASURED | 2595 | One card printed two numbers for itself, and one of them belonged to another car | Before observed on the face (03 over ID 002, 002 already AUREA's); after asserted ('all say 004', re-intaken, QR decodes); number/back fixes… |
| `cfb613f` | MEASURED | 958 | The chip was programmed and the page it points at did not exist | Tap 404d before; rejected clone counted (25 mantle mentions); after only a generic gate count (91 files resolve), no check that /aurea/ resolves,… |
| `1b7d0d4` | MEASURED | 1991 | The carve-out asked how the picture was made, and portraits of real people have  | Names the hole (generated likeness of a real person slipped the old wording); 4/4 surfaces fixed; docs-only, no refuter, no artifact check, no gate. |
| `6b0deb0` | NONE | 659 | The card was printable for twenty minutes and the dropdown that everyone opens d | Describes the two missing TEMPLATES entries and adds them; no check that the dropdown now shows Manis, no number, no gate added. |
| `8d33880` | MEASURED | 1635 | The archive had recorded the money that arrives and not the childhood it does no | Built _site/gt/index.html checked (renders both, __COUNT__=13, entries.json inlined); no failing condition written for the content or the build. |
| `33cc113` | MEASURED | 2523 | The carve-out re-granted OFL fonts under MIT in the one sentence written to stop | States the over-grant (OFL clause 5 quoted), corrects 'higher resolution' to same-resolution; README gains licence section; no refuter, gate or… |
| `f515cf1` | MEASURED | 1280 | The page's own date field has no slot for the count the archive is about | Rebuilt page checked for title, four proper nouns, node line 10->11; failure mode only implied (source edit proves nothing), no written refuter… |
| `0c6a226` | MEASURED | 2050 | Two of the four projects had already written down where they came from, in files | Provenance sharpened from first-commit order and a served credits.json; 171-package lockfile and bundle checked; no written refuter, no gate, page… |
| `b75471d` | MEASURED | 1146 | The tap mark was missing from five card fronts, and existing cards can get it wi | Per-face luminance measured (255.0 to 86.6) to pick mark colour, but no falsifier, no check of mark position on rendered/printed output; reprint… |
| `ecfc3b3` | MEASURED | 1107 | Write down what the pages actually do, with the gate behind each claim | Doc of measurements (0 subresources, 44px at 4 widths; 11 to 0 after fixing method) but no failing condition for the doc itself and no check added |
| `111611d` | NONE | 458 | The standard says a wish form beats a mailto, and the gate can prove it | Doc-only amendment describing an admissible channel; no measurement, no RED, no check added in this commit (gate lives in 224445f4) |
| `cff9ad2` | MEASURED | 1211 | Four packages in, the numbers say the spec was asking for the wrong thing | Doc-only defect table with denominators (0/4 PNGs, 4/4 placeholder QR); no failing condition for this change, no check added |
| `9371b2e` | MEASURED | 817 | Name the two places this new check would lie | Comment-only limits of the check, with one live measurement (0 mailto/markers at /av/, 3 of 3 index.html); no failing condition, no check |
| `8368ba1` | MEASURED | 2192 | The umbrella: name the shape, list KUNAI, put a wish button on the pages | At-artifact checks (5 criteria, chip URL 404, API vs gh mismatch) but no written falsifier; builder FAILs added yet message never names them |
| `3899a90` | MEASURED | 2023 | GT-001 gets a destination: /gt/ goes live | After-state at page: faces/fonts load, 0 overflow, no network request; iterdir bug reasoned not reproduced; no RED, no check added |
| `6d82d63` | MEASURED | 1500 | One command builds the site; stop the dots stealing the deck's width | 390px iframe check with numbers (deck 350px, 0 overflow) but no RED reproduced, local verifier run not reported; builder FAILs unnamed in msg |
| `aad7e50` | MEASURED | 1066 | Verified product links, and the frequency question a card game turns on | ASINs fetched and confirmed (at-artifact check) but no failing condition written, no numbers beyond identifiers, no check added |
| `2473813` | NONE | 1260 | App icon: the Card Studio mark, squared and given a small-size master | Design rationale with size parameters (16/32/64px, 20% inset); qualitative 'does not survive 16px', no measurement at built icon, no check |
| `3d31df7` | MEASURED | 1197 | Bleed: print past the card edge so no bare PVC shows | Before-state observed on print 2 (inset, bare PVC); PPD 0.2835pt and 2.0mm cap derived; no bleed print verified after, no failing condition written. |
| `7a40de6` | MEASURED | 1504 | Swipeable deck on the splash; margin controls; Place card template | 'Every element clears the measured margin, checked' is a template-geometry check; no before-state or falsifier; swipe/JS-off claims unverified. |
| `51989e4` | MEASURED | 864 | The margin follows the card's curve, like it does on a real card | Before/after value only (1.6mm by eye -> 1.295 derived from measured 1.885); nothing checked at the rendered card; no failing condition. |
| `38cbdea` | NONE | 554 | Show the unprintable margin in the tray preview too | Describes the change (tray preview now draws the bezel via shared drawBezel); no number, no check, no verification. |
| `72345ea` | MEASURED | 405 | GT-001: record that neither variant can be scanned | At-artifact check stated (QR ~20 modules, fails to decode at 1x/4x/8x) but it is a registry note; no written failing condition for the change. |
| `fe5b880` | MEASURED | 863 | Drop the marketing phrase; hold GT-001 with its reason | Carries QR measurements (~20 modules, fails at 1x/4x/8x, 13.5mm vs 17.2mm floor); no falsifier for the hold/phrase change; nothing re-verified. |
| `4981616` | MEASURED | 1063 | Show the margin as white card stock; make the preset selectable | Cites the measured 1.885/2.020mm margins (inherited); the red->white rendering and preset loader are unverified; no failing condition. |
| `73fc6a5` | NONE | 1004 | Card hovers face up; globe goes big behind it | Only chosen parameters (9deg, 7s, 360px vs 180px, 8deg); no measurement, no at-page check; make_globe.py adds no check that can fail. |
| `a3ec93f` | NONE | 1476 | Show the unprintable bezel; submit projects; trace lineage | Describes the red bezel band, project form, lineage text; the 'about 1 mm' figure was a guess (next commit says so); no check, no verification. |
| `6326a9e` | NONE | 1118 | The mission, the fork, and a way to send a card back | Page copy and an issue template; no number, no check, no verification stated. |
| `df3f0a5` | MEASURED | 1142 | Render the card as a card: white bezel, CR-80 corners, alpha | Inspected the artwork at the artifact (pure black to last pixel, no JPEG ringing) to rule out a cause; composite result not verified on the page;… |
| `e3b926c` | NONE | 466 | Ship globe.webp — the page referenced a file the repo did not have | Names the miss (page referenced a globe not in the repo) and ships the file; no verification the page now loads it; no check added. |
| `1cfa405` | MEASURED | 1400 | A real globe over the card, rendered rather than faked | Only measured figure is the 95 KB asset plus an observed jitter; no falsifier, nothing checked at the page; the webp was not even in this commit. |
| `f0908ca` | NONE | 1003 | Splash: the card lying flat with a globe turning above it | Design parameters only (64deg, twelve divs); build_site copies the dir but adds no check that fails; no verification stated. |
| `019f2a3` | MEASURED | 586 | Ship founder.png — the template referenced a file the repo did not have | RED stated (template pointed at untracked founder.png); control run (HEIC + loose PNG still refused) but only on the gitignore rule; render not… |
| `b9a2aaa` | MEASURED | 1474 | Mobile layout, a founder-card template, and a choosable icon | Icon chosen by rendering all six at 16/32/64/128 (at-artifact); one media query counted before; mobile layout never verified on a phone; no… |
| `b70d95f` | NONE | 678 | Add the PC/SC reader to the buying guide; keep the affiliate tag out of the repo | Supplies entry and an env-style tag source; no number, no check, no verification. |
| `6b31510` | MEASURED | 858 | Panel review: one listed, two held | At-artifact checks (license byte-identical to canonical GPL-3.0; GitHub spdx_id NOASSERTION) but no failing condition written for the verdicts. |
| `d12e144` | MEASURED | 775 | Tighten the landing copy; render the network from a curated manifest | Before/after word count (~640 -> 242); build_site.py FAILs on a surviving marker, but message never says what would be wrong; rendered page not… |
| `9c9fe43` | NONE | 1255 | Credit the author, document how it was built, add the transfer roadmap | Credits and docs; the audit figures (20 agents, 1.33M tokens) are content, not a measurement of this change; no check. |
| `9c5ee6d` | NONE | 94 | Point the wish channel at the live repo | Subject only; one manifest field changed; no check. |

**Limits.** This is a *reading*, not a gate: the rubric is written above and six readers
applied it, but a reader can mis-class a commit, and the table is here so anyone can
re-read one and say so. Commit messages were the unit because §5 names git history as the
ledger; an eval that lived only in a ship note on the well, in a comment, or in someone's
head was not counted, and that is the standard's rule rather than this file's. The "before"
verdict was a keyword grep over the 30 newest commits (a cap, named at the time); an
adversarial reader then read all 30 bodies and confirmed it; the 179 were read before this
entry was written. Nothing here measures whether the 113 EVAL commits' evals were *good* —
only that each wrote down what would have proven it wrong and checked the artifact.

**The way back.** Write-discipline, not tooling (§1.3 of the standard: no new tooling for a
behavioural problem). From the commit that carries this entry on, every shipped change says
in its message what would have proven it wrong and what was checked at the artifact. The
level moves back to `L1` when a re-read of the ledger since that commit finds no shipped
change without one — and not before.

---

## 7. What is NOT covered

Named explicitly, per E4 — a missing eval is only dangerous when it is unlisted.

- **The print path.** Nothing here puts ink on a card. Geometry is verified against
  vendor tray templates in `src/profiles.json`, but the end-to-end "does it land inside
  the pocket" test is a physical calibration print the user runs (`Calibrate` tab).
- **`pdfwriter.py`.** Hand-rolled PDF generation is exercised only indirectly.
- **Non-Canon printers, and every non-macOS platform.** See the README's platform note.
- **The 3D-printed enclosure.** The generator's only self-check is that each half comes out as
  a closed mesh, and a wall carved clean through by the surface relief still passes it — that is
  what happened to the v7 top half, and `hardware/rfid-reader-case/README.md` documents it with
  the measurements. Nothing here verifies the geometry, no version has ever been printed, and
  clearances are sub-millimetre.
