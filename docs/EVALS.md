# Evals — Card Studio

The [Make It Better](../MAKE_IT_BETTER.md) standard says an eval must be able to fail, must
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

## 5. What is NOT covered

Named explicitly, per E4 — a missing eval is only dangerous when it is unlisted.

- **The print path.** Nothing here puts ink on a card. Geometry is verified against
  vendor tray templates in `src/profiles.json`, but the end-to-end "does it land inside
  the pocket" test is a physical calibration print the user runs (`Calibrate` tab).
- **`pdfwriter.py`.** Hand-rolled PDF generation is exercised only indirectly.
- **Non-Canon printers, and every non-macOS platform.** See the README's platform note.
- **The 3D-printed enclosure.** Geometry is verified in the generator's own checks; fit
  against a specific reader PCB is a test print, and clearances are sub-millimetre.
