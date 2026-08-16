# The GESICA deck — design note

A card in this deck is a window into a picture that has no edges.

GESICA is a program that draws pictures from a number. There is no saved image
anywhere. You give it a number, it computes every pixel. Give it the same number
again and you get the same picture again, forever.

A card in this deck prints one small rectangle of one of those pictures. The
number is printed on the card. The two faces are not two pictures — they are the
left half and the right half of one picture, cut in the middle.

Everything below was measured on this machine on 2026-08-16, except where it says
it was not. The parts that were not measured are in §6.

---

## 1. The seam

### The card

| | width | height |
|---|---|---|
| printed (bleed) | 87.5 mm | 55.88 mm |
| finished (trim) | 85.6 mm | 53.98 mm |
| cut away | 0.95 mm per edge | 0.95 mm per edge |

At 600 dpi the repo works in whole pixels: **2066 × 1319** printed,
**2022 × 1275** finished, **22 px** cut from each edge. Those four numbers are in
`tools/intake_card.py` lines 48–54 and nothing may change them.

### The two rectangles

Lay the two *finished* faces side by side. That is one field, 171.2 mm wide and
53.98 mm tall.

- **Front** takes field x from 0 to 85.6 mm.
- **Back** takes field x from 85.6 to 171.2 mm.

They meet at 85.6 mm with nothing between them.

### What happens at the cut

This is the part that sounds like it should fail, and does not.

Each face is *printed* 0.95 mm larger than it is *finished*, on all four sides.
So the front actually prints field x from −0.95 to 86.55 mm, and the back prints
84.65 to 171.15 mm.

The strip from 84.65 to 86.55 mm — 1.9 mm of field — gets printed **twice**, once
on each card, and the guillotine removes one copy of each half. After trimming
that strip appears exactly once, split down the middle at 85.6 mm.

**Nothing is lost at the cut. The overlap is printed twice and cut once.** That is
what bleed has always been; this just applies it across a join instead of against
a card edge.

### Does the code support it

Yes, with no change to the drawing maths.

The shader turns a screen position into a place in the field like this
(`src/pages/ShardsScrollPage.tsx`, lines 46–49):

```
place = uCref + rotate(uRot) · (uv.x · uAsp, uv.y) · uZi
```

`uv` runs −1 to 1 across whatever is being drawn. There is no pan uniform and no
tile uniform, which looks fatal — but it is not, because any sub-rectangle can be
reached by moving the centre and changing the two scale numbers.

For a crop centred at `c` with half-size `h`, in the parent's `uv` units:

```
uRot'  = uRot                                  unchanged
uZi'   = h.y · uZi                             vertical extent
uAsp'  = h.x · uAsp / h.y                      horizontal extent
uCref' = uCref + rotate(uRot) · (c.x · uAsp, c.y) · uZi
```

Four numbers. No shader edit.

**Compute these from the raster, not from the millimetres.** Using 2022, 1275 and
22 px makes `uAsp'` come out as exactly 2066 ÷ 1319, which is the canvas the card
is drawn on, so there is no sub-pixel stretch:

```
pair half-width   = 2022 px      pair half-height = 637.5 px
uAsp_pair = 2022 / 637.5 = 3.171765
h.x = 1033 / 2022  = 0.5108803   h.y = 659.5 / 637.5 = 1.0345098
uAsp_face = 1033 / 659.5 = 1.5663381     (= 2066 / 1319)
c.x = −0.5 for the front, +0.5 for the back;  c.y = 0
```

### It was measured

Two faces rendered at full 2066 × 1319, trimmed, and the two columns that end up
touching were compared. Then the same column was compared against columns
elsewhere in the other face — that is the control, the number you would get if the
crop maths were wrong.

| seed · cell | the join | normal neighbouring columns | wrong-seam control |
|---|---|---|---|
| 1337 · 3 | **8.65** | 10.21 | 86.44 |
| 1011 · 3 | **5.54** | 13.98 | 35.27 |

(Mean colour difference, 0–255 per channel.)

The join is *smaller* than the difference between any two neighbouring columns
inside a face, and about one eighth of the control. The two faces are one picture.
Stitched and viewed, there is no line.

### Three things that could break it — two of them do not

**The bezel does not step at the join.** The shader ends with a rounded-rectangle
mask (line 101). It reads like a black frame that would print a bar down the
middle. It is not: the distance function is zero or negative everywhere inside a
square-cornered box, so the mask is 1 across the whole interior. It only darkens
**the four corners**. Turn it off for cards — the card's own 3.18 mm rounded
corner is the real bezel, and it is cut, not printed.

**The vignette does not step either, but it bends the picture.** Line 103 darkens
toward the edge of whatever is drawn. Both sides of the join sit at the same 0.8,
so there is no step. But each face gets its own bright dome. Measured brightness
across one face, left to right:

```
vignette on    81  86  89  92  94  96  97  98  97  99  96  93  91  92  82  72
vignette off  109 108 107 106 105 105 104 105 103 107 105 104 104 110 104  97
```

With it on, each half looks separately lit. Turn it off. (If the dome is wanted,
move it into field coordinates so one dome spans the pair — two extra uniforms.)

**The anti-aliasing jitter is fine.** It is 0.0007 in `uv` units, which scales with
the crop. Both faces are the same pixel size and the same crop scale, so the
jitter lands identically in field terms. Not a seam problem. At 2066 × 1319 it is
0.72 px across and 0.46 px down — worth tightening to a true half-pixel some day,
but that is sharpness, not continuity.

**One thing genuinely must match: `uTime`.** It shifts the palette. Give the two
faces different values and the colours differ. For cards it is 0. See §2.

### What has to change, and where

Nothing about the geometry. Two things about the shader, both in
`/Volumes/dual/persona500/src/pages/ShardsScrollPage.tsx`:

1. Lines 94–104 — put the bezel and the vignette behind uniforms so a card can
   switch them off and the website keeps them on.
2. Lines 18–105 — move `VS` and `FS` into their own file so the website and the
   card renderer share one copy. Two copies of a shader drift, and the drift shows
   up as a card that no longer matches its own web page.

---

## 2. The seed is the identity

### Two numbers, not one

A GESICA seed produces eight cells, each with its own colour, depth and rotation.
So a piece is addressed by **(seed, cell)** — seed 1011, cell 3.

At time zero, everything the shader consumes is fixed by those two numbers:

| what | how |
|---|---|
| zoom | `t = (sin(phase) + 1) / 2`, then `zoom = 4 · (zoomMax/4)^t` |
| centre | `(anchor.re, anchor.im + 0.03/zoom)` |
| palette drift | `uTime = 0` |
| rotation | `2.39996 · (index + cell)` |

The centre deserves a note. The live page nudges the centre by
`sin(time·0.00003 + seed·2π)`. At time zero that is `sin(seed·2π)`, and for a whole
number seed that is zero — checked at seed 1337, error 1.5 × 10⁻¹⁶. The cosine
term is 1. So the centre is exact and free.

**One number is not seed-derived: `index`.** It is the card's position in the
website's scroll list, not its seed. The site builds seeds 1000, 1001, 1002 … in
order, so `index = seed − 1000` today, by coincidence of construction. Two ways
out, and the deck should start with the first:

- **Keep the deck inside seeds 1000–1499** and compute `index = seed − 1000`. Zero
  changes to the website. This is the slice-1 choice.
- **Make rotation seed-derived** — one line at `ShardsScrollPage.tsx:309` and one
  at `:417`. Frees any seed, but changes how every existing piece looks.

### The rule: a card is GESICA at time zero

The website animates. Zoom breathes on a 9.5-to-105 minute cycle, the palette
drifts, the centre wanders. None of that is recorded anywhere, so a screenshot is
not reproducible.

So the deck fixes it: **a card is the field at time zero.** Everything becomes a
pure function of the seed and the cell.

And time zero is where the live page starts. Load `/gesica` and the first frame
you see is the card. It drifts from there — at worst about 4% of zoom per second
for the fastest cells, far slower for most. So the honest claim is not "the page
shows your card forever". It is: **the page opens on your card, and then it moves.**

### What is printed, and what the chip says

**On the card, back face, inside the safe zone:**

```
SEED 1011 · CELL 3
```

**Card id:** `GESICA-1011-3`

**Chip epitaph** (grammar `vc1|<id>|<title>|<yyyy-mm>|<license>|<tool>`):

```
vc1|GESICA-1011-3|GESICA 1011·3|2026-08|CC-BY-NC-4.0|vibe-cards
```

64 bytes against a 252-byte limit. Nothing about the format resists a numeric id —
`tools/card_ledger.py` reads field 1 as a plain string and keys its rows on the
tag's own serial, so per-seed identities cannot collide.

**URL — QR and chip carry the same one:**

```
https://mrdirno.github.io/vibe-cards/gesica-1011-3/
```

A query string is not available. `intake_card.py` generates the QR itself and
refuses the card unless a face decodes to exactly `SITE_BASE/<slug>/`. So
`/gesica/?seed=1011` cannot pass. **The slug is the seed.** That is a better answer
anyway: one card, one address, no second destination to keep in sync.

That page should run the field live at that seed, so a tap lands *on* the piece
rather than next to it. The engine is one shader and two random number generators
with no dependencies, so the page can carry it. Until then the page links out to
`/gesica`, and the honest downside is that the visitor has to scroll to find their
seed. Fixing that is a small change to the website's scroll list, which is
currently hard-coded to start at 1000.

---

## 3. The character window

### The idea in one line

The character is not drawn on top of the field. **The field is drawn through the
character.**

### How

MAKO's cutouts live in `/Volumes/dual/persona500/docs/mako/output_nobg/` — 4,735
of them, real transparency, about 5% of each image being soft feathered edge
(hair, mostly). That feather is what makes this work, and a hand-cut mask would
not.

Four steps:

1. Draw the field crop for this face. This is the base.
2. Draw the field **again**, into an offscreen buffer — same centre, same
   rotation, **different `uZi`**. Deeper or shallower, your choice. Same picture,
   different depth.
3. Use the cutout's alpha channel as a stencil on that second render.
4. Composite it over the base.

The result is a person-shaped opening showing the same field at another depth.
No outline. No drop shadow. No glow. Nothing that says "an image was placed here".

**The cutout's colours are thrown away — only its shape is used.** That is the
whole difference between a window and a sticker. A sticker brings its own
lighting; a window brings none.

If the face needs to stay readable, add the character's brightness back at low
strength as a second pass. Its colour never comes back.

### The tap-mark box must stay clear

There is a 10.3 mm square on the **front** of every card, at x 68.3–78.6 mm,
y 36.7–47.0 mm. It is where you tap. Card Studio composites a black, white or gold
mark there as a separate layer, over the artwork.

Three rules:

1. **No part of the character silhouette may enter that box.** Position the cutout
   so the box falls on field, not on a shoulder.
2. **The field under the box must be plainly light or plainly dark**, so the mark
   has contrast. `intake_card.py` measures the box's average brightness and picks
   white below 128, black above.
3. **The box must be quiet.** Fine fractal detail under a tap mark reads as dirt.

Proposed gate: average brightness **below 100 or above 156**, and standard
deviation **below 20**.

**Run that gate on the finished 2066 × 1319 image, never on a preview.** Measured
on seed 1011 cell 3: at quarter resolution the box looked perfectly flat, standard
deviation **0.3**. At full resolution the same box is standard deviation **28.5**
with an average of **128.8** — sitting exactly on the white/black decision line and
far too busy. The downsample destroyed the very detail the gate exists to find. A
cheap preview is a pre-filter, not a proof.

Everything else — type, the seed line, the QR — stays inside the 3.95 mm safe zone.

---

## 4. Why this is not Book One

Compound Craft, Book One has one entry fee: **every card leaves behind a reusable
tool, and it carries a 1:1 cutting file** — a template you can put a blade against.
The card is a set of instructions for making a physical object. A GESICA card has
no object and no template. There is nothing on it to cut. Admitting one would not
extend Book One, it would repeal its only rule, and afterwards nobody could say
what Book One was for. These are a separate deck. They share the card format — the
same millimetres, the same tap mark, the same chip, the same intake tool — and
nothing else.

### This deck's entry fee

**Every card must be reproducible from the numbers printed on it.**

Hold the card, read the seed and cell, type them in, get the same picture back.
Nothing on a card may depend on anything the printed numbers do not determine.

That rule does the same work Book One's cutting file does. A sticker album is a
set of pictures somebody liked. This is a set of coordinates anybody can revisit.
The card is not a copy of the artwork — it is an address for it, and the artwork
is regenerated on demand at the other end.

What the rule forbids, concretely:

- No retouching. No paint, no repair, no cloning out an ugly patch.
- No colour grade after the fact.
- No hand-chosen frame from an animation. Time is zero or the card is not
  reproducible.
- No image file promoted to the source of truth. The generator is the source; the
  PNG is an artifact of it and can always be thrown away.

What the rule permits, because it does not break reproducibility:

- **Choosing which seeds to print.** Looking at four thousand candidates and
  printing the twelve best is curation, not retouching. The printed numbers still
  regenerate them exactly.

Everything about the deck follows from that one rule. Cards can be added forever
without a meeting, because the only question is ever: does it regenerate.

---

## 5. The three coming-soon cards

One card each for GESICA, MAKO and LOCO. They announce the tools, and they are the
honest test of the whole idea.

**If a GESICA card cannot be made beautiful by GESICA, we stop.** No photograph, no
typography rescue, no gradient behind the title. The tool makes its own card or
the deck does not exist.

### GESICA — the field is the card

- **Front.** One field crop at a curated seed and cell. It runs off all four
  edges. The word GESICA small, in the safe zone. The tap mark in a quiet region.
- **Back.** The same field, continuing across the join. The seed line. The QR.
  And one sentence, in plain words:

  > Every pixel here was computed from the number on this card. Nothing was saved.

Nothing else on either face. This card carries no artwork that is not the field
itself. It is the load-bearing card of the deck.

### MAKO — the casting card

MAKO's real achievement is not the drawing. It is the casting: **641 male, 631
female, 312 androgynous** across 1,584 prompts; **49 distinct ethnicity labels**,
with 19–31 of them inside every single style folder; six age brackets present
everywhere. That machinery is measured and real.

- **Front.** One character as a window cut into the field, per §3.
- **Back.** The field continues, and it carries those numbers. Not a description
  of a pipeline — the counts. That is the claim, and it is checkable.

The card should say the true thing about the tool: MAKO is a casting director that
happens to render.

### LOCO — the card that cannot be made from stock

LOCO renders the characters locally, free, in about 45 seconds. It also has a
measured wall: **every one of 4,152 prompts is longer than the model's 77-token
limit**, a median of 29.4% survives the cut, and the art-style words are in the
part that gets thrown away. That is why the local characters all look like one
house style.

And it has an honest gap: **the generator has never sent a seed**, so none of the
2,085 existing local characters can be made again.

So this card cannot use an existing character. It has to generate a new one with a
recorded seed — the first reproducible LOCO character there has ever been. That is
this card's entry fee, and it is one line at the call site in `mako_loco.ts`.

- **Front.** The new character, as a window in the field.
- **Back.** The field, the character seed, the model, the step count, and:

  > This character can be made again. The 2,085 before it cannot.

---

## 6. What is unknown

Named plainly, not designed around.

**Nothing has been printed.** Every number in this note was measured on screen.
Fine fractal filigree at 600 dpi on PVC, against inkjet dot gain, is untested. It
may fill in and turn to mud. This is the largest unknown in the document.

**Ink load.** Some seeds are very dark — one face measured 43.8% near-black. That
is a lot of ink on a plastic card, and PVC needs a high quality setting already.
Whether those faces dry, scuff or bronze is unknown.

**Colour.** The save path writes 8-bit sRGB with no colour profile and no
resolution tag. GESICA's palette is a saturated cosine ramp through a film
tonemap. How much of the electric blue and acid green survives a CMYK inkjet has
not been measured. Expect movement.

**The physical flip.** The field is proven continuous in the file. It is not proven
continuous *to a person holding the card*. Flipping about the vertical axis puts
the back's left edge against the front's right edge; flipping about the horizontal
axis puts it upside down. The deck must state which flip it means, and only a
printed card settles it.

**Opening the site at a seed.** The website's scroll list is hard-coded to start at
1000 and stops after 500. Reading a seed from the address is a small change that
has not been made or tested.

**Rendering inside intake.** These renders used a standalone script with specific
graphics flags. `tools/intake_card.py` launches its browser with none, and
screenshots page elements. Whether a live WebGL canvas captures correctly there is
untested. The safe route is to render the two PNGs first and let intake screenshot
plain `<img>` tags — which also avoids the tool's refusal on multiple embedded
images, since the QR will be marked `data-vc-qr`.

**The character window is designed, not built.** No composite exists. The alpha
stencil and the second-depth render are described here and have never been run.

**The 25% pass rate is soft.** 9 of 36 candidates passed all four gates — but that
survey ran at quarter resolution, and §3 shows the tap-box column of it is wrong.
The brightness and darkness gates transfer; the tap gate does not. The real pass
rate is unmeasured and will be lower.

**Deep zoom in print.** The engine caps zoom at 10,000 with a comment saying the
cap protects against 32-bit maths breaking down. A printed card asks for more
spatial detail than a screen does. Whether the deepest seeds go blocky on paper is
unmeasured.

---

## The first buildable slice

One session. Ends with two image files on screen that are provably one picture.

**It does not touch this repo.** No intake, no slug, no page, no chip, no printing.
Those come after somebody has looked at the join and agreed it is invisible.

**1.** Create `/Volumes/dual/persona500/src/lib/gesicaField.ts`.
Move — do not retype — three things out of
`/Volumes/dual/persona500/src/pages/ShardsScrollPage.tsx`: the random number
generator at lines 10–16, the `ANCHORS` list at lines 227–236, and the state
derivation at lines 238–260. Export `deriveShardStates(seed, count = 8)`.
Add `fieldUniforms(seed, cell, index, timeMs)` returning exactly the numbers the
render loop sets at lines 299–312.
*Retyping is the main risk in this whole slice. There are two different random
number generators involved and they are easy to confuse.*

**2.** Create `/Volumes/dual/persona500/src/lib/gesicaShader.ts`.
Move `VS` and `FS` out of `ShardsScrollPage.tsx` lines 18–105. Put the bezel
(line 101) and the vignette (line 103) behind two uniforms, `uBezel` and `uVig`,
using `mix()`. Change nothing else in the text.

**3.** Edit `ShardsScrollPage.tsx`. Import from both new files, delete the moved
code, and set `uBezel = 1.0` and `uVig = 1.0` at both places uniforms are set —
the live loop near line 299 and `captureCell` near line 409.
Load `/gesica` and confirm it looks exactly as before.
*This step must change nothing a visitor can see. If the site looks different, the
move was wrong.*

**4.** Create `/Volumes/dual/persona500/automation/scripts/gesica_card_faces.mjs`.
Takes `--seed`, `--cell`, `--out`. Renders both faces at 2066 × 1319 with
`uBezel = 0`, `uVig = 0`, `uTime = 0`, `uIter = 1000`, using:

```
uRot'  = uRot
uZi'   = (659.5 / 637.5) · uZi
uAsp'  = 1033 / 659.5
uCref' = uCref + rotate(uRot) · (∓0.5 · (2022/637.5) · uZi, 0)
```

Minus for the front, plus for the back. Writes `front.png` and `back.png`.

**5.** Add `--check` to that same script. Trim 22 px from each edge, then print
three numbers: the difference at the join, the difference between normal
neighbouring columns, and the wrong-seam control. **Refuse to write the files if
the join is larger than the neighbouring-column figure.** Reference values:
join 5.54, neighbours 13.98, control 35.27.

**6.** Add `--gate` to the same script. On the finished front, measure the tap box
at x 68.3–78.6 mm, y 36.7–47.0 mm and print its average brightness and standard
deviation. Pass needs average below 100 or above 156, and standard deviation below
20. **Full resolution only.**

**7.** Run steps 4–6 across seeds 1000–1019, cells 0–7. That is 160 candidates;
about a quarter survive the brightness checks, so budget roughly 40 full-size
renders. Stop at the first that passes everything.

**8.** Stitch the two trimmed faces side by side and look at the join.

That is the session. What you have at the end is two files and a decision: either
the join is invisible and the deck is real, or it is not and this note was wrong.
