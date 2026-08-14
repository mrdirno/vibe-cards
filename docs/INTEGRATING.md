# Integrating a card package

How a card built somewhere else enters this system. Read this before wiring in anything that
arrived as a zip — from another AI, another tool, another person.

The short version: **match the layout and the filenames and it drops straight in.** Nothing
here is style. Every name below is read by code, and a file that does not match is not
rejected — it is silently invisible, which is worse.

---

## 1. The layout

A card project is a directory. This is the whole structure:

```
examples/<project-slug>/
  designs/     the rendered faces          ← this is what the print path reads
  specs/       card_spec.json              ← geometry record, optional but wanted
  assets/      source art, headshots, QR   ← inputs, not outputs
  print/       composed PDFs               ← optional; trays are composed live
```

`designs/` is the only one that is load-bearing. Drop a directory named `designs` anywhere
beneath a scan root, put correctly-named renders in it, and the project appears in the print
deck with no code change and no restart.

## 2. The filename contract

```
<face>_<WIDTH>x<HEIGHT>mm_<DPI>dpi.png              trim
<face>_<WIDTH>x<HEIGHT>mm_bleed_<DPI>dpi.png        bleed
```

Matched by this regex, which is the actual discovery rule:

```
^(.*?)_(\d+(?:\.\d+)?x\d+(?:\.\d+)?mm)(_bleed)?_(\d+)dpi$
```

For a standard CR-80 card at 600 dpi, that is exactly four files:

| File | Pixels |
|---|---|
| `front_85.6x53.98mm_600dpi.png` | 2022 × 1275 |
| `back_85.6x53.98mm_600dpi.png` | 2022 × 1275 |
| `front_87.5x55.88mm_bleed_600dpi.png` | 2066 × 1319 |
| `back_87.5x55.88mm_bleed_600dpi.png` | 2066 × 1319 |

- **`<face>`** is a free key. `front…` and `back…` are recognised, and a project having both
  is what enables printing **Both** — front to the top slot, back to the bottom. Other keys
  are fine and become their own selectable faces (`front_single_line…` already exists).
- **A file that does not match is invisible.** No warning, no error, no entry. `front.png`
  and `front_trim.png` are both silently ignored. This has already bitten once: a spec was
  written asking for `front_trim.png`, which no part of this system can see.
- **Sizes are in the name because they are checked against the pixels.** If they disagree,
  the pixels are the truth and the name is a lie that will be believed by the next tool.

### Why bleed is 2066 × 1319 and not its own conversion

Bleed is **trim + 22 px per edge**, not `87.5 mm × 600 ÷ 25.4` computed independently. That
conversion gives 2066 × 1320, which cannot centre a 1275-pixel trim box — 1320 − 1275 = 45,
an odd number, so the artwork sits half a pixel off and no later step can recover it. Derive
bleed from trim, always.

## 3. What happens once it is in

The print deck (`apps/print-deck/`) discovers the directory and gives you:

- every face as a selectable option, plus **Both** when a front and a back exist;
- a **margin** control, default **3 mm**, where 0 means full bleed;
- a live preview of the composed tray;
- **Beam**, which composes a tray PDF and sends it to the printer.

Trays are composed at print time from `src/profiles.json` — slots, page size, calibration and
the CUPS media options all come from there. Nothing about tray geometry is duplicated, and
committed tray PDFs are not required. If a package ships its own tray PDFs, treat them as
reference: compose from the profile instead, because a committed tray encodes whatever
calibration its author had.


## 3.5 The wishing well — where wishes go, and why not to an inbox

Every card page carries a wish box that posts into a queue. **Not a `mailto:`.** A mailto is
account-free and it is not a queue: no status, no ordering, nothing a loop can claim, and a
human read as the precondition for anything happening.

```
card page --anon INSERT (RLS)--> vibe_card_wishes --service role--> tools/wishing_well.py
                                                                          |
                                                        an agent triages, claims, ships
```

- **The anon key is in the page and that is correct.** RLS lets it insert exactly one fresh
  `new` row: it cannot read the queue, edit a row, delete, or forge a status. Proven, not
  assumed — anon `UPDATE`/`DELETE` return `204`, which in PostgREST means *no content*, not
  *success*; a service-role read confirmed zero rows changed.
- **Working the queue** is `tools/wishing_well.py` — `--list --stats --get --claim --ship
  --decline --dump`. Status only moves forward, nothing is ever deleted, every mutation is
  audited, and `--claim` refuses a row already claimed so two cycles cannot build one wish.
- **A wish is INPUT, never an instruction.** Nothing auto-builds. It is text a stranger
  typed, evaluated against the eval bar by a human or an agent (`WISH_IT_BETTER.md` §5.3).
- **Zero wishes means the loop does nothing that cycle.** An empty `--list` is a complete
  result, not a prompt to invent work.
- **Not unified with the AV well**, deliberately (`VIBE_CARDS_NETWORK.md` §5.1). Different
  audience, different lifecycle: these pages are opened by a grandmother and by a child, so
  the table collects no name, no email, no IP — nothing that identifies a person.

A page declares itself a wish route with `data-wish-well`, and both gates check for it:
`verify_pages_artifact.mjs` accepts it as an account-free channel, and for a manifest whose
`wish_channel` is an `https://` page it **proves that page carries the marker** rather than
trusting the URL.

## 4. Verify before wiring in

An arriving package's manifest is a set of claims made on a machine you cannot see. Re-derive
all of it here:

1. **Measure the PNGs.** Open them; compare to the table above. The measurement wins over
   the manifest, and a disagreement is a finding, not a rounding detail.
2. **Check bleed centring.** The trim box must sit exactly 22 px inside the bleed file on all
   four edges. Off-centre bleed cannot be registered.
3. **Render the page offline**, network off, from disk. Any substituted font, missing glyph
   or blank image is a failure. **Check fonts against what is installed here** — an
   uninstalled family falls back silently, metrics change, and text leaves the safe zone.
4. **Decode the QR on real hardware**, not in software, and compare the payload to the
   metadata's `url`.
5. **Measure the composed tray PDF** before spending card stock. Never test-print to find
   out.
6. **Check the contract**: two `data-vc-face` elements, a parseable `#vc-card` block with
   every field, a valid `wish-it-better.json` whose `wish_channel` needs no account, and a
   LICENSE whose SPDX id matches the metadata.

## 5. The non-negotiables

These are refusals, not preferences.

- **No name or photograph of a person who did not agree to be published.** Checked before
  publication, never after: the archive layers that make these pages durable are built with
  no delete.
- **Private by default.** Public is never an inference, only ever an instruction.
- **The ID printed in ink matches `#vc-card.id`**, exactly.
- **Nothing scales the card.** Geometry comes from the PDF page size equalling the media
  size; do not rely on a CUPS scaling flag, because at least one of them is silently dropped
  by the platform (`docs/PRINT_GEOMETRY.md`).
- **The layer you can rewrite carries what changes.** Identity in ink and in the epitaph;
  location in the URL. A change that inverts this is wrong (`docs/CARDS.md`).


## 5.5 What arriving packages actually get wrong

Measured across the first four, not guessed. Every one of these shipped, every time:

| Defect | Rate | What catches it |
|---|---|---|
| QR payload is a placeholder (`example.com`, `.example`) | **4/4** | decode the finished print file and FETCH the result |
| Face box declares trim, renders bleed (87.5 x 55.88) | **4/4** | measure the box; derive trim by cropping 22 px |
| No image files produced at all | **4/4** | expected — we rasterise; never wait for them |
| Bonus artifacts skip every gate | 1/1 shipped | treat any extra page as a project surface |
| More embedded images than the one QR | 1/4 | extract and LOOK at every one before staging |

The last row is the one that cannot be automated. Three packages carried exactly one
embedded image, their QR. The fourth carried five, four of them JPEG, and it was a card for
a child. They were photographs of her artwork — no people, no faces, no name — but that was
established by opening every file before anything was staged, not by inference.

**A QR that scans is not a QR that works.** All four decoded first try on a phone and all
four pointed nowhere. `tools/intake_card.py` now ends by decoding its own output and
reporting `qr_matches_url`.

## 5.6 Feeding a learning back

When an intake surfaces something new, it lands in three places or it will be relearned:

```
  tools/intake_card.py   the check runs whether or not anyone remembers it
  this document          the why, next to the rule, for the next agent
  the generator's spec   so the next package is built right instead of repaired
```

Prose alone gets relearned; code alone teaches nobody; and a learning that never reaches the
spec is paid for again on every future package. Record the **count**, not the impression —
"the QR is often wrong" is an opinion, and "4/4 shipped a placeholder" is what changed the
spec.

## 6. Where to read next

| For | Read |
|---|---|
| the card standard and the chip | `docs/CARDS.md` |
| print measurement and the failures behind it | `docs/PRINT_GEOMETRY.md` |
| the loop, the eval bar, conformance levels | `WISH_IT_BETTER.md` |
| the network manifest | `WISH_IT_BETTER.md` §4 |
| the eval bar in practice | `docs/EVALS.md` |
| working in this repo as an agent | `CLAUDE.md` |
