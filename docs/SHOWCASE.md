# What these pages actually do

A vibe card is a printed object with a chip in it. Tap it and a page opens. This is what is
on the other side of that tap, and the constraints every one of them is built under.

Everything below is measured on the built artifact, not described from intent.

---

## The constraints first, because they are what makes the rest interesting

Any of these pages would be easy with a framework, a CDN and a login. None of them have one.

| | |
|---|---|
| **External subresources** | **zero.** No CDN script, no remote font, no hosted image. Measured across every page. |
| **Renders offline** | open the file from disk with the network off and it is complete. |
| **Account required** | none, anywhere — not to read, not to interact, not to send a wish. |
| **Horizontal overflow** | zero at 320, 360, 390 and 430 px. Enforced by `tools/verify_mobile.mjs`. |
| **Tap targets** | ≥ 44 px on the short side, checked at every width. |
| **Content without JS** | the landing deck swipes on CSS scroll-snap alone; the script only lights the dots and adds arrows a mouse needs. |

The pages are reached one way — someone taps a card with their phone. There is no desktop
entry point and no search traffic, so "mobile friendly" is not a nice-to-have here, it is the
only mode that exists.

## The surfaces

| Page | Weight | What it is |
|---|---|---|
| `/` | 24 KB | Landing. A swipeable deck of real cards, and a wish box. |
| `/studio/` | 22 KB + app | Card Studio: design both faces, program the chip, print. In the browser. |
| `/nica/` `/sala/` `/tierra/` `/raices/` `/lab/` | 13–14 KB | One page per card. |
| `/gt/` | 67 KB + 2 faces | The Guatemala node: a living archive in Spanish, thirteen entries. Weighed 1.5 MB until 2026-08-15 — a table of weights with no row for the heaviest page is how that lasted. |
| `/raices/garden/` | 5.4 MB | A pocket garden built from a child's own painted artwork. |
| `/lab/universe/` | 198 KB | A build lab — *Chief Engineer: you.* |

### The card, in your hand, on the page

Every card page shows the physical object and lets you **turn it over**. CSS 3D, one
`rotateY(180deg)`, `backface-visibility` doing the work — no library, and it degrades to two
stacked images if the script never runs. Tapping a picture of a card to flip it is the
smallest possible bridge between the thing in your pocket and the thing on the screen, and it
is the first thing every visitor does.

### Two worlds, built for two children

**`/raices/garden/`** — a niece's paper daisies and ladybugs, photographed, and turned into
three worlds she can move through: Philippines, Nicaragua, Guatemala. *"You made these
flowers. Now they have a whole universe."*

**`/lab/universe/`** — a nephew's blueprint lab. Blocks placed, bricks high, goals scored,
an inventory, and an **ENTER LAB** door. *"This is your lab. No rules. Just build."*

Both are self-contained single files. Both were authored as artifacts and adopted rather than
rebuilt — and both needed the same two corrections before they could ship, which is the
useful part to know: **neither had a wish route, and both had controls under the 44 px touch
floor.** Both were fixed *by rule* — a stylesheet and an appended element outside the
framework's root — so regenerating the artifact cannot silently undo them.

### The wishing well

Every page takes a wish. Write it, press one button, done — no account, no email address, no
mail client, nothing to sign up for. It lands in a queue that gets worked, not in somebody's
inbox.

The anon key ships in the page, and that is correct: row-level security permits exactly one
fresh `new` row and nothing else — it cannot read the queue, edit a row, delete, or forge a
status. That was **tested rather than assumed**, and the test is worth repeating because it
nearly lied: anon `UPDATE` and `DELETE` both return `204`, which in PostgREST means *no
content*, **not** *success*. A privileged read was needed to confirm zero rows had actually
changed.

### Card Studio, in a browser tab

`/studio/` is the whole tool: lay out both faces at true CR-80 geometry, compose a
print-exact PDF, program the NFC chip, and print onto a card tray. One renderer, no
framework, Python standard library on the server side.

## What is enforced, and by what

Nothing above is a promise; each line has a gate behind it.

```
tools/verify_pages_artifact.mjs   every reference resolves · no external subresource
                                  · no root-absolute path · every project surface
                                  carries an account-free wish route · a declared
                                  wish channel must PROVE its page has the well
tools/verify_mobile.mjs           320/360/390/430 px · zero overflow · 44 px targets
                                  · re-checked with the root font size bumped
tools/verify_geometry.py          the card is 85.6 × 53.98 mm and nothing scales it
tools/verify_nfc_guard.py         the chip path, and it cannot touch hardware
tools/intake_card.py              decodes a finished print file and refuses to
                                  report an unverified QR as verified
```

## The one number that matters most

A QR that scans is not a QR that works. Of the card packages built for this network so far,
**five out of five** shipped a technically perfect QR — correct size, correct quiet zone,
decoded first try on a phone — pointing at a placeholder domain. The check that catches it is
not "is there a QR" but "decode the finished print file and **fetch what comes back**."

That is the shape of most of the work here: the artifact renders beautifully long before it
is correct, so every claim gets measured on the thing a person actually touches.
