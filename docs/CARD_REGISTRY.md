# Card registry — which numbers are taken, and which one is next

Every card carries an ID printed on its face. This file says what those IDs are and which
number the next card gets, because until now that answer only existed by reading fourteen
pages and counting.

**The next card is 015.** Slots 001 through 014 are full and there are no gaps.

---

## Read this before assigning a number

There are **two different numbering habits** in the IDs below, and mistaking one for the
other is how a number gets used twice.

**A sequence number.** `MANIS-CUIRASS-001` through `KAZE-KIRI-007`, then `REXI-008`,
`KELIBRO-009`, `LEVIATHAN-010` (formerly `FIELD-ORGANISM-010`), `BIFURCATA-011`,
`PANGEA-012` and `GESICA-013`. These
count *cards*, in the order they were made. This is the sequence the
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
| 010 | `LEVIATHAN-010` | Leviathan | `/leviathan/` | Parametric — grown from six numbers at persona500.com/leviathan (formerly FIELD ORGANISM, renamed 2026-08-23; the printed fo| address is frozen) |
| 011 | `BIFURCATA-011` | Bifurcata | `/bifurcata/` | Parametric — a world number; the engine's own `#w=` address |
| 012 | `PANGEA-012` | Pangea | `/pangea/` | Parametric — one world number paints a landscape plate |
| 013 | `GESICA-013` | Gesica | `/gesica/` | Parametric — the engine the deck is named after, frozen at time zero |
| 014 | `9AM-SYNC-CALL-014` | 9AM Sync Call | `/9am-sync-call/` | a comedy Bay-Area song made physical |
| **015** | — | **free** | — | **the next card** |

**Book One has seven cards shipped, and it is not closed.** Its own manifest plans
seventy-two and keeps the unbuilt ones in an archived design file described, correctly, as
"a map of where the book could go, not a promise". Only shipped cards are listed anywhere
that counts.

Its entry fee is specific and is the only rule it calls non-negotiable: **every card leaves
behind one reusable tool and names the earlier cards whose tools it uses.** A card that
inherits nothing and leaves nothing does not belong in it.

Cards 008 through 013 continue the *sequence* without joining the *book*. None is a craft
card, none pays that entry fee, and all sit outside the band every book card shares. So
the sequence number is a card's position in the whole project, and the book is a curated
subset of it. Numbering a card does not enrol it in anything — which is worth stating plainly,
because the book's own id rule says the number in a card_id is "its position in the book",
and cards 008 and 009 were the first two that made that sentence untrue. Cards 009 to 013
are the parametric deck (`docs/GESICA_DECK.md` §4): each is reproducible from the numbers
printed on it, and that rule, not a cutting file, is their entry fee.

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

## Every page's numbers are gated against this file

`tools/build_site.py::check_counts` re-derives the sequence and Book One totals from THIS
table on every build, sweeps every page under `src/site/`, and refuses to publish when they
disagree — each stated count sits in a `<span data-count="sequence|book-one|book-one-range">`
it verifies. A number directly before the word "cards" in visible prose, outside such a
span, fails the build outright. "Seven cards so far" sat on the live page for two cards'
worth of time and was reported twice in one night (wishes 2a895681, 598ae99c); the gate
then read only the landing page, and a third report (2026-08-18 — up top, the first count
met still read seven while nine cards exist) found the book page hand-carrying five counts
it never swept and `/aurelia/` still saying "the other four cards" two cards after that
stopped being true. A hand-carried number is a number that rots, so when a card lands here, the
build breaks until the pages say so. The landing page and `/compound-craft/` must each
state both totals (`REQUIRED_COUNTS` in the gate). Not swept, on purpose: comments and
`<style>`/`<script>` bodies (measurement records are history, not claims), and attribute
text — a count inside a `meta description` still rots by hand.

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

## Adding card 014

1. Take the ID `<NAME>-014`.
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
