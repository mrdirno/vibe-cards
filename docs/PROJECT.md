# Vibe Cards — what this is, where it came from, and where it goes

This is the context document. If you are picking this project up — human or agent — read
this first, then [`CARDS.md`](CARDS.md) for the chip contract and
[`WISH_IT_BETTER.md`](../WISH_IT_BETTER.md) for how work gets accepted.

---

## 1. The one-line version

**A Vibe Card is a project, made physical.** A printed CR-80 card with an NFC tag in it,
carrying an identity that never changes and an address that can. Tap it with any phone and
it opens the project. Put it on a reader and an agent can read it, rewrite it, and act on
it — with no app, no account, and no server.

**Card Studio** is the tool that prints them, programs them, and browses the network they
form.

---

## 2. Inception — the actual story, because it explains every design decision

Someone asked for a small object to be 3D-printed. It got designed, printed, and then —
because the design lived in a parametric generator that would be forgotten in a month — a
trading-card-style spec card was printed for it: name, stats, a silhouette of the part, a
mount diagram, an ID in the corner.

**The card was not made to publish anything. It was made so its own maker could find his
way back to the generator later.**

The card stock had an RFID tag in it. The tag was blank.

That is the whole project: a physical object that clearly *should* point at something,
pointing at nothing. Everything below is downstream of taking that seriously.

Three consequences, and none of them are obvious until you sit with that story:

- **The primary user is the maker, not an audience.** The first job of a card is to get
  *you* back to the thing that regenerates the object. Sharing it with someone else is the
  same primitive aimed outward — not a different feature.
- **The card outlives its URL.** A PVC card is good for a decade. Usernames get freed,
  domains lapse, hosting paths move. Design for the day the address stops answering.
- **The page is not the point, and it is not our business.** A generator project serves a
  build recipe. An art piece serves the piece. Both are correct. We standardise the chip,
  which must never change; the page is where people should build freely.

---

## 3. How it is put together

```
INK      identity, immutable, decade-rated, human-legible   ← primary record
CHIP r2  identity, plaintext, offline, needs no server      ← the epitaph
CHIP r1  location, disposable, rewritable forever           ← the pointer
```

**The layer you can rewrite carries the thing that changes.** If a future change inverts
that — identity in the URL, location in the ink — the change is wrong.

### Why two records instead of one URL

Because the failure that matters is not a 404. A lapsed name gets taken by someone else,
and then the tap **succeeds and lies**: their content, served from the address printed on
your object, to a person or an agent with no way to notice. Fallbacks only fire on visible
failure, and a lie is not a visible failure.

So the chip carries a second record — plain text, no server involved:

```
vc1|<id>|<title>|<yyyy-mm>|<SPDX license>|<tool>
```

The last field is the **tool**, not the host, so the identity is byte-identical before and
after you re-point the address. There is deliberately **no author field** — see §7.

Full byte budgets, the irreversible-page rules, and the security model:
[`CARDS.md`](CARDS.md).

---

## 4. Repo → card → site

```
   a project                      github repo, PRIVATE by default
       │                          + wish-it-better.json at its root
       │
   card printed  ─────────────▶   CR-80 + NFC tag, id printed in ink
       │                          chip: identity + address
       │
   published  ────────────────▶   a standardized project page
       │
   shared  ───────────────────▶   joins the network: origin/spinoffs edges
                                  become walkable by anyone
```

### The three verbs — three levels of commitment

| Verb | What happens | Who decides |
|---|---|---|
| **create** | the project exists, repo is **private**, nothing is exposed | an agent may do this unasked |
| **publish** | the project page goes live | the owner, explicitly |
| **share** | it joins the Wish It Better network | the owner, explicitly |

**The default rung is the safe one, and you cannot skip a rung by accident.** That is what
makes it safe to let an agent create things on your behalf: the worst case is a private
repo you did not want, which costs nothing. Publishing has no undo — an hour of public is
cloned, forked and archived, and the archive layers that make projects durable are built
to have no delete.

Cards are about real things, and very often about real people: a client's install, a gift,
a prototype, something made with your kid. **Public is never inferred. It is instructed.**

---

## 5. The network

A project joins by committing `wish-it-better.json` at its root:

```json
{
  "spec": "wish-it-better/1.0",
  "level": "L0",
  "project": "vibe-cards",
  "wish_channel": "https://mrdirno.github.io/vibe-cards/#wish",
  "origin": null,
  "spinoffs": [],
  "evals": "docs/EVALS.md",
  "amended": []
}
```

`wish_channel` must be a route that needs **no account**. This example read
`issues/new?template=wish.yml` until 2026-08-17, and every manifest on the network copied
it — which is how a standard whose first rule is "no login" ended up account-gated
everywhere. An example is what gets copied, so the example is the rule. The URL above is
the wishing well on this project's own page: one box, no fields, and a queue rather than
someone's inbox. The level reads `L0` for the same reason: it is what this project has
earned as of 2026-08-19 (it declared `L1` from its second commit with nothing measured
under it), and a copied `L1` is how a badge stops meaning anything.

`origin` and `spinoffs` are edges. **A crawler can walk them and render the whole network
without anyone maintaining a directory** — there is no registry, no server, and no
authority, including us. A card is that graph's physical entry point.

Conformance is declared, not granted: **L0** adopting · **L1** looping (every change
carries an eval; wishes reach a terminal state) · **L2** networked (spinoffs declare their
origin, and you have contributed at least one amendment back).

The compounding mechanism is the **amendment clause** — an adopter who hits a real scar
amends the standard, and every other adopter inherits the fix. An amendment must come from
something shipped, never from a theory, and it should prefer *deleting* a rule to adding
one. That is what makes the standard improve rather than merely spread.

---

## 6. What is actually built, as of 2026-08

**Shipped and verified on hardware** (ACS ACR122U, NTAG213/215/216):

- `src/nfcio.py` — read, write, NDEF encode/decode, read-back verification, per-chip write
  ceilings, hardware serialisation. **Python 3 stdlib only**, talking to macOS
  `PCSC.framework` through `ctypes`. No install step, no dependency.
- **A command line** — `python3 nfcio.py status|read|write|open|watch`. One JSON object on
  stdout, exit 0/1 on `ok`. `watch` emits one line per card *arrival*. This is the primary
  interface; the app is a wrapper on it.
- **Three HTTP routes** behind the app's `Host` + session-token guard.
- **A Chip panel** in Card Studio that polls the reader, shows what a card carries, writes
  and verifies, and opens the address when a card is set down.
- `tools/verify_nfc_guard.py` — 74 adversarial cases, and structurally incapable of
  writing to a tag.

**Not built yet:** the projects browser, the standardized page generator, and the login
that lets an owner see a private project's page.

---

## 7. The rules that are not negotiable

Each one exists because of a specific failure, most of them found the hard way here.

1. **Never write past the user-data pages, and ask the chip where they end.** Above the
   data area are lock bytes, OTP and config pages; writing there bricks the tag
   permanently. The ceiling is per-chip, and it cannot be read from the tag's capability
   container — that is the field a forged tag lies about. Ask `GET_VERSION`; when it will
   not answer, use the *smallest* chip's ceiling, never the largest.
2. **A card is untrusted input in both directions.** Ten seconds of physical access
   rewrites any unlocked tag. Validate what you *read* with the same policy object you use
   for what you *write* — hardening one direction of a two-way boundary is the bug.
3. **Nothing auto-*fetches* what a card points at.** Auto-*opening* it in the user's
   browser is fine — that is what a phone already does — but the app never requests,
   parses or renders a card's target. Loopback, link-local and private addresses are
   refused either way.
4. **Verify writes by comparing bytes, not by re-parsing.** The URI record is written
   first, so a write that dies partway through still reads back a perfect URL while the
   identity record is silently gone.
5. **No author on any machine-readable surface.** A card can carry the name and face of a
   client, a friend, or a child. A dedication printed in ink is not consent to be indexed
   by a machine, and machine-readable provenance cannot be withdrawn later. Attribution
   stays local.
6. **Default private.** See §4.

---

## 8. Roadmap

Ranked by what unblocks people, not by what is fun.

| | What | Why it matters |
|---|---|---|
| **1** | **The projects surface** | Browse the projects you know about and write one onto a card. The graph is already walkable; nothing walks it yet. This is what the cards were always for. |
| **2** | **Standardized project pages** | A project that passes its checks gets a page, generated from its manifest, so a card has somewhere real to land. |
| **3** | **Owner sign-in for private projects** | So a scanned card takes its owner to their project while telling a stranger nothing — including whether it exists. |
| **4** | **Linux / Windows** | The platform coupling is narrow: CUPS for printing, `pcsc-lite` speaks the same API `nfcio.py` already uses. |
| **5** | **More tray + printer profiles** | A new printer is a `profiles.json` entry, never new code. |
| **6** | **Batch from CSV, end to end** | Print and program 50 cards without touching the designer 50 times. |
| **7** | **Dual-frequency readers** | 125 kHz and 13.56 MHz are incompatible families, and the choice traps people into the wrong purchase. |
| **8** | **QR fiducials for AR** | Cards already carry a printed ID. A fiducial costs nothing now and makes "hold your phone over the card and see the object above it" possible later. |

---

## 9. Wish it better

This project runs the [Wish It Better loop](../WISH_IT_BETTER.md). The whole point is that
you do not have to be sitting at the machine — or be us — to improve it.

**[Open a wish →](https://mrdirno.github.io/vibe-cards/#wish)** — one box, no account,
no sign-in. Same box for a project you want listed and for a card you made.

Before you call anything done:

```bash
./tools/verify_contribution.sh      # the mechanical gate
python3 tools/verify_nfc_guard.py   # if you touched the chip layer
```

Then bring an **eval**, not a claim — the bar is `WISH_IT_BETTER.md` §2, with worked
examples in [`EVALS.md`](EVALS.md). In short: write the observation that would have proven
you wrong *before* the fix; verify at the artifact a user touches, not the source you
edited; report the denominator; name any cap; and for anything security-relevant assume
you are wrong until an independent pass fails to break you.

And if the standard itself fails you — say so in a pull request. That is the part that
compounds.
