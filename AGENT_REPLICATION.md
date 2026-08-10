# Replicating this project — an exact procedure for a coding agent

Written for Claude Code or any comparable agent, given a bare machine and this repo. It
is the build order that actually worked, with the traps that cost real time called out at
the step where they bite.

**Read this whole file before starting.** Several steps are cheap to do in the right order
and expensive to undo in the wrong one — most importantly, the physical calibration
(step 6) must happen before you commit card stock to a batch.

---

## What you are building

Three things that only matter together:

1. **A printed card.** Artwork placed to sub-millimetre accuracy on a CR-80 PVC card, via
   a desktop inkjet's disc/MP tray.
2. **A readable card.** An RFID chip inside that card, whose ID a USB reader can bind to
   an identity.
3. **An enclosure.** A 3D-printed case so the reader is a device on a desk rather than a
   bare board on a cable.

An agent can complete 1 and 3 unattended. Step 2 needs a human to physically tap a card.

---

## 0. Prerequisites, and how to check them

```bash
sw_vers -productVersion                 # macOS 12+
python3 --version                       # 3.9+; /usr/bin/python3 is fine
ls /Applications/Google\ Chrome.app     # optional, but gives the app its own window
lpstat -p                               # printers CUPS can see
```

Nothing to install. The app is **stdlib-only** by design — that is a constraint the
contribution gate enforces (`tools/verify_contribution.sh`), not an accident. Pillow is
the single optional dependency and every use of it is inside a `try/except` with a working
fallback.

**Hardware, if you are doing the physical half:**

| Item | Note |
|---|---|
| Canon PIXMA TS702a (or TS700-series) | Any printer with a disc/MP tray can work — the geometry is a config, see step 6 |
| 2-card CR-80 PVC tray | The disc-tray-shaped carrier; slot coordinates come from the vendor's template |
| Inkjet-**printable** PVC cards, CR-80, 30 mil | The single most common wrong buy — see the trap below |
| USB RFID reader | 125 kHz and 13.56 MHz are different, incompatible families |
| 3D printer, ≥120 × 90 mm bed | For the enclosure in `hardware/` |

> **Trap — "graphic quality" cards.** Cards sold as *graphic quality* or *premium graphic
> quality* are a **surface grade for dye-sublimation ID printers**, not a coating claim.
> Inkjet ink beads up and wipes off them. The listing must literally say *inkjet
> printable* or *ink receptive coating*. This is the failure the app's Supplies tab exists
> to prevent; it wastes a whole pack before you work it out.

> **Trap — reader frequency.** A 125 kHz reader (EM4100 / EM4200 / TK4100) **cannot see**
> 13.56 MHz cards (NTAG213/215/216, MIFARE) at all, and vice versa. Buy the cards and the
> reader as one decision. A dual-frequency reader reads both and removes the question.

---

## 1. Run the app from source

```bash
cd src
python3 server.py            # prints: Card Studio serving http://127.0.0.1:<port>/
```

It picks a free port, writes it to `~/Library/Application Support/Card Studio/port`, and
opens a Chrome app window. Two environment variables exist for automation:

```bash
CARD_STUDIO_PORT=8791 CARD_STUDIO_NO_BROWSER=1 python3 server.py   # headless, fixed port
```

**Verify it is actually up** — and note that a bare `curl` will now be refused, which is
correct:

```bash
P=8791
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: 127.0.0.1:$P" http://127.0.0.1:$P/   # 200
TOKEN=$(curl -s -H "Host: 127.0.0.1:$P" http://127.0.0.1:$P/ \
        | grep -o 'cs-token" content="[^"]*"' | sed 's/.*content="//;s/"//')
curl -s -H "Host: 127.0.0.1:$P" -H "X-CS-Token: $TOKEN" http://127.0.0.1:$P/api/ping     # {"ok": true}
```

> **Trap — the API refuses you on purpose.** Every `/api/*` call needs the `X-CS-Token`
> header and a loopback `Host`. If you are getting `403`, you are not misconfigured; you
> are being treated exactly like the malicious web page this guards against. Read
> `SECURITY.md` before you consider weakening it.

---

## 2. Build the double-clickable app

```bash
./build_app.sh                  # → ~/Desktop/Card Studio.app
./build_app.sh /Applications    # or install it properly
```

The bundle carries **its own copy of `src/`**, because the source may live on a removable
volume and an app that breaks when a drive is unplugged is not an app.

> **Trap — the bundle is a copy.** Editing `src/` does not change the built app. If you
> "fixed" something and the app still misbehaves, you are looking at the old copy. Rebuild,
> then verify against the bundle path, not the source path. (This is eval rule **E2**:
> verify at the artifact the user touches.)

---

## 3. Verify the UI without a human

Playwright drives the real page. There is no mocking — the harness talks to the running
server.

```js
// see docs/EVALS.md §2 for the assertions that matter
await page.goto(`http://127.0.0.1:${PORT}/`);
await page.waitForSelector('#canvasEmpty');            // opens blank, with guidance
const hit = await page.evaluate(() => {                // the overlay must not eat drops
  const b = document.querySelector('#canvasEmpty').getBoundingClientRect();
  const el = document.elementFromPoint(b.left + b.width/2, b.top + b.height/2);
  return { isOverlay: !!el.closest('#canvasEmpty') };  // must be false
});
```

> **Trap — `grep` is blind on `app.js`.** That file uses NUL bytes as cache-key delimiters,
> so `file` reports it as `data` and **plain `grep` prints nothing at all** — not "Binary
> file matches", nothing. A search for a symbol that is definitely there returns zero hits
> and reads as "this feature does not exist." Use `grep -a`, or read it with Python.

---

## 4. Print geometry — how the cards land where they land

The MP tray prints a **120 × 120 mm page** with ~0.1 mm margin. The two card slots sit at
measured positions inside that square; `src/profiles.json` carries the coordinates and
cites the three independent vendor artifacts they were derived from (they agree to within
0.0005 mm, which is itself the evidence they were measured rather than idealised).

```
design (mm) → 600 dpi raster → exact-geometry PDF → lp → CUPS → URF → printer
```

**Adapting to a different printer or tray** is a config change, not a code change: add a
profile to `profiles.json` with your page size and slot centres. Do not hardcode a second
geometry in the composer.

---

## 5. Dry-run before any card is at risk

The app can push a job through the real CUPS filter chain **without printing**, and read
the resulting URF header back to confirm the true output geometry. Use it. A MediaBox that
does not exactly match the page is silently cropped rather than reported — the dry run is
the only thing that tells you before the PVC does.

---

## 6. Calibrate — on paper, before PVC

Print the calibration page on **plain paper**, hold it against the physical tray, and
enter the offsets in the Calibrate tab.

> **Trap — trays vary by SKU.** A different vendor's tray can shift the slots by ~1 mm,
> which is the difference between a centred card and artwork off the edge. Re-run
> calibration whenever the tray changes. Calibration is stored per machine in
> `~/Library/Application Support/Card Studio/settings.json`, not in the repo.

---

## 7. Print the cards

Both tray pockets must be loaded every print, even for a single card. One photo fills the
card and both slots print it; two photos give you a front and a back.

**After printing:** 90 seconds before touching the face, 24–48 hours before laminating.
Lay cards flat in a single layer — stacked wet cards transfer ink to the back of the next.

---

## 8. The reader enclosure

`hardware/rfid-reader-case/` holds two printable halves and the generator that produced
them. See that directory's README for print orientation and the snap-fit tolerance note.

```bash
python3 hardware/rfid-reader-case/gen_rfid_reader_case_v7.py   # regenerate the STLs
```

> **Trap — sub-millimetre snap clearances.** The tongue-and-groove seal is a near-zero-
> clearance press fit at the shipped smoothing value. Expect to tune it for your printer;
> print the halves once before printing a batch.

---

## 9. Bind a card to an identity (needs a human)

Most 125 kHz cards are **read-only** — you do not write an ID to them, you read whatever
ID they shipped with and bind that. The flow is *scan, then register*: tap the card, and
the reader (a USB HID keyboard-emulation device) types the ID; store that ID against the
identity you want. No writer hardware is required, which is why read-only cards are fine.

---

## 10. Before you call it done

```bash
./tools/verify_contribution.sh --all    # the mechanical review gate
```

Then the human half in `SECURITY.md` §6–8, and the eval checklist in
`WISH_IT_BETTER.md` §2. If you shipped a change, write down what it taught, next to the
code it taught you about — that is station 5, and skipping it is what turns a loop back
into an event.

---

## Order of operations, condensed

```
prerequisites → run from source → build bundle → automated UI verify
   → geometry profile → DRY RUN → calibrate on PAPER → print PVC
   → print enclosure → bind card (human) → verify gate → log the lesson
```

The two irreversible steps are **printing on PVC** and **printing the enclosure**. Both
have a cheap rehearsal immediately before them (dry run, calibration print, single test
print). Do not skip a rehearsal to save a minute; that is the whole reason the order is
this way.
