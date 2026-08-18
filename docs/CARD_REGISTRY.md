# Card registry — which numbers are taken, and which one is next

Every card carries an ID printed on its face. This file says what those IDs are and which
number the next card gets, because until now that answer only existed by reading fourteen
pages and counting.

**The next card is 010.** Slots 001 through 009 are full and there are no gaps.

---

## Read this before assigning a number

There are **two different numbering habits** in the IDs below, and mistaking one for the
other is how a number gets used twice.

**A sequence number.** `MANIS-CUIRASS-001` through `KAZE-KIRI-007`, then `REXI-008` and
`KELIBRO-009`. These count *cards*, in the order they were made. This is the sequence the
next card continues.

**A series number.** `ABRAZO-NICA-001`, `TIERRA-TRAZO-001`, `GT-001` and others also end in
`001`, but they are the first card of *their own family*, not the first card overall. Six
different cards currently end in `001`. That is correct and is not a collision — but a
script that sorts by the last three digits will report one, so do not write that script.

If you are numbering a new card in the main sequence, take the next free sequence number.
If you are starting a new family, `-001` of that family is yours.

---

## The sequence

| # | ID | Card | Page | What it is |
|---|---|---|---|---|
| 001 | `MANIS-CUIRASS-001` | Manis Cuirass | `/manis/` | Craft — Compound Craft, Book One |
| 002 | `AUREA-LATTICE-002` | Aurea Lattice | `/aurea/` | Craft — Book One |
| 003 | `MOKU-003` | Mokume Photonic Lattice | `/moku/` | Craft — Book One |
| 004 | `CARPAL-BLOOM-004` | Carpal Bloom | `/bloom/` | Craft — Book One |
| 005 | `AURELIA-CORONA-005` | Aurelia Kresling Corona | `/aurelia/` | Craft — Book One |
| 006 | `ZARIA-HALO-006` | Zaria Solar Bloom Halo | `/zaria/` | Craft — Book One |
| 007 | `KAZE-KIRI-007` | Kaze-Kiri Wind-Cut Collar | `/kaze/` | Craft — Book One |
| 008 | `REXI-008` | Rexi's Vibe Tag | `/rexi/` | Pet tag — a demo other people copy |
| 009 | `KELIBRO-009` | Kelibro | `/kelibro/` | Parametric — the deck's first printed card |
| **010** | — | **free** | — | **the next card** |

**Book One is cards 001–007 and it is closed at seven.** Its page says so, and its entry fee
is specific: every card in it must leave a reusable tool behind. Cards 008 and 009 continue
the *sequence* without joining the *book* — a pet tag and a deck card are not craft cards.
So the sequence number is a card's position in the whole project, and a book is a curated
subset of it. Numbering a card does not enrol it in anything.

## Cards outside the sequence

Each is the first of its own family. None of them occupies a sequence slot.

| ID | Card | Page | What it is |
|---|---|---|---|
| `VIBE-CARDS-001` | The founder card | `/` | The project's own card |
| `GT-001` | Guatemala | `/gt/` | Place card |
| `BUILD-LAB-001` | Build Lab | `/lab/` | Workshop card |
| `TRES-RAICES-001` | Tres Raíces, Una Flor | `/raices/` | Gift card |
| `TIERRA-TRAZO-001` | Tierra y Trazo | `/tierra/` | Gift card |
| `ABRAZO-NICA-001` | Abrazo Nica | `/nica/` | Gift card |
| `ASIN-SALA-001` | Asin at Sala | `/sala/` | Gift card |

---

## Where a card's identity actually lives

The ID above is not stored in this file. Each card page carries its own record, and that
record is what the code reads:

```
src/site/<slug>/index.html  →  <script type="application/json" id="vc-card">
```

Its fields are `spec, id, title, date, license, replication, tool, url`, and optionally
`provenance` and `authorship`. This table is generated from those blocks, so **if the two
ever disagree, the page is right and this file is stale.** Regenerate it rather than editing
a row by hand.

Three published pages carry no `vc-card` block at all — `/gt/`, `/compound-craft/` and
`/deck/`. The last two are not cards, so that is correct. `/gt/` is a card and the missing
block is a real gap: nothing on that page states its own licence in a form a machine reads,
and Card Studio cannot offer its address when the card is loaded.

## Adding card 010

1. Take the ID `<NAME>-010`.
2. Build the package. `tools/intake_card.py` wires an arriving one in.
3. Give it a page at `src/site/<slug>/` with a `vc-card` block carrying that ID.
4. Add a `cards.destinations` row in `src/site/network.json`.
5. Add its figure **and its pager dot** to the gallery in `src/site/index.html`. Both are
   hand-written and nothing checks that they exist — a card with no figure is invisible and
   every gate still passes. `/lab/` is the live proof.
6. Add its template pair to `TEMPLATES` in `src/web/app.js`, with `url` and `epitaph`
   matching the page's `vc-card` block, so the Chip panel can offer the right address.
   That file contains NUL bytes: plain `grep` finds nothing in it. Use `grep -a`.
7. Add the row above.
