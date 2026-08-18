# The chip — what a card carries, and how to program one

A Vibe Card is a CR-80 card with an NFC tag in it. This file is the whole contract for
the chip half: what goes on it, why it is shaped that way, how to write one, and the
rules a writer must not break.

It is written to be operated from — by a person, or by an agent handed this repo and
nothing else. If something here is not enough to program a card correctly, that is a bug
in this file.

The printing half is the [README](../README.md). The improvement loop is
[WISH_IT_BETTER.md](../WISH_IT_BETTER.md).

---

## 1. The idea in three lines

```
INK      identity, immutable, decade-rated, human-legible   ← the primary record
CHIP r2  identity, plaintext, offline, needs no server      ← the epitaph
CHIP r1  location, disposable, rewritable forever           ← the pointer
```

**The layer you can rewrite carries the thing that changes.** A URL is the part of a card
most likely to stop meaning anything — usernames get freed, domains lapse, hosting paths
move. The card ID printed in ink outlives all of that, and the epitaph on the chip keeps a
machine-readable copy of it that no server gets a vote in.

If a change to this project ever inverts that — identity in the URL, location in the ink —
the change is wrong.

### Why not just a URL?

Because the failure that matters is not a 404. A lapsed name gets taken, and then the tap
**succeeds and lies**: someone else's content, served from the address printed on your
object, to a person or an agent that has no way to notice. Fallbacks only fire on visible
failure, and a lie is not a visible failure.

So the card states what it is, on the card, in plaintext.

---

## 2. What goes on the chip

Two NDEF records, in this order. Order is not stylistic — a phone acts on the first URI
record it finds, so it has to be first.

### Record 1 — URI

An NFC Forum RTD URI record. **This is the only record a phone acts on with no app
installed**, on both iOS (Core NFC) and Android (NDEF dispatch). Anything else — a custom
MIME type, an external type record — requires an app to already be installed and therefore
fails the only test that matters: hand the card to someone and see if it works.

### Record 2 — Text (the epitaph)

An RTD Text record, invisible on a normal tap, carrying identity as pipe-delimited text:

```
vc1|<id>|<title>|<yyyy-mm>|<license>|<tool>
```

| Field | Meaning | Example |
|---|---|---|
| `vc1` | format version — bump if the field list changes | `vc1` |
| `id` | the ID printed on the card face, exactly | `RFID-CASE-001` |
| `title` | what the thing is, in plain words | `RFID Reader Enclosure` |
| `yyyy-mm` | when the card was made | `2026-08` |
| `license` | an [SPDX identifier](https://spdx.org/licenses/) | `MIT` |
| `tool` | what made it, so it can be remade | `vibe-cards` |

Pipe-delimited, not JSON, for two reasons: braces and quotes cost bytes a 144-byte tag does
not have, and a person reading a hex dump in 2035 can still parse a line of pipes.

**The last field is the TOOL, not the host.** That is deliberate — it means the epitaph is
byte-identical before and after you re-point the URL. The pointer moves; the identity does
not.

**There is no author field, and this is not an oversight.** A card can end up carrying a
name that belongs to a child, a client, or someone who never agreed to be indexed — and the
archive layers that make cards durable (Wayback, Software Heritage, DOI) are engineered to
have *no delete*. A name written into a machine-readable surface cannot be withdrawn later.
Put the dedication in ink on the card face if you want it there; keep attribution out of the
bytes. If you fork this and add an author field, understand you are making that permanent
for whoever's name goes in it.

---

## 3. The URL

```
<base>/c/<ID>
```

> **Not implemented yet — you must supply `<base>` yourself.** There is no configuration
> key, no default, and no setting for it in the app today; the surface that will own it is
> item #0 in the [roadmap](ROADMAP.md). Until it exists, pass a full URL you chose. Do not
> copy `example.com` out of the worked example below onto a real card — an agent following
> an earlier draft of this file would have done exactly that.

`<base>` is **configuration, never a constant in the source.** Two reasons, and the second
is the one people miss:

1. You will move hosts eventually and every already-printed card has to survive it.
2. If `<base>` is hardcoded, then everyone who forks this repo ships cards pointing at
   *our* host. Their cards, our domain, forever. A fork must resolve to the forker.

Same rule the printer profiles follow: a new home is a **config entry, never new code**.

There is nothing magic about `/c/`. It is short, and short matters — see the byte budget.

### What the page should serve

Whatever the project wants. A build recipe, a gallery page, a spec sheet, an artwork, a
single paragraph. The chip layer is identical either way, which is exactly why this is left
open: the part that is standardised is the part that must never change, and the page is the
part that should differ every time.

---

## 4. Byte budget

Usable NDEF capacity, which is less than the raw chip size:

| Chip | Usable | Notes |
|---|---|---|
| NTAG213 | 144 B | the common cheap inlay — plan for this one |
| NTAG215 | 496 B | comfortable |
| NTAG216 | 872 B | roomy |
| MIFARE Ultralight | 48 B | URI only; an epitaph will not fit |
| MIFARE Classic | — | **cannot be read by an iPhone at all.** Core NFC does not expose it. Not usable for cards meant to be tapped. |

Overhead: 2 bytes TLV + 4 record header + 1 URI prefix byte + 1 terminator, padded to
4-byte pages. A Text record costs 7 bytes plus its text.

Worked example. Do not trust this table — reproduce it, the command is right here:

```bash
cd src && python3 -c "import nfcio; print(len(nfcio.encode_message(
  'https://example.com/c/RFID-CASE-001',
  'vc1|RFID-CASE-001|RFID Reader Enclosure|2026-08|MIT|vibe-cards')))"
```

```
url      https://example.com/c/RFID-CASE-001
epitaph  vc1|RFID-CASE-001|RFID Reader Enclosure|2026-08|MIT|vibe-cards

         104 bytes  →  40 free on NTAG213, 392 free on NTAG215
```

An earlier draft of this file printed 112/32/384 here. Those numbers were copied from a
different card's measurement instead of being re-run for these strings, under a sentence
claiming they were measured. If a number in a document cannot be regenerated by a command
printed next to it, treat it as decoration.

**Leave headroom.** Free space on the tag is the migration budget for the next URL. A card
written to exactly capacity has silently lost the ability to be re-pointed, which is the one
cure available when a host dies. Aim to leave at least 16 bytes on a 144-byte tag.

The URI prefix table is what makes this fit at all: `https://` is stored as a single byte
`0x04`, and `https://www.` as `0x02`. Always take the **longest** matching prefix — taking
the first match instead wastes four bytes on every `www` URL, which is the difference
between fitting and not on a 144-byte tag.

---

## 5. Programming a card

### From the command line — the primary interface

Cards are programmed by agents and scripts far more often than by a person clicking, so
this is the way in. **No server, no session token, no window, no install.**

```bash
cd src
python3 nfcio.py status                          # reader present? card on it?
python3 nfcio.py read                            # everything on the card
python3 nfcio.py write --url https://example.com/c/BENCH-001 \
                       --epitaph "vc1|BENCH-001|Bench Lamp|2026-08|MIT|vibe-cards"
python3 nfcio.py open                            # open the card's address in a browser
python3 nfcio.py open --print-only               # resolve it without opening anything
python3 nfcio.py watch                           # one JSON line per card ARRIVAL
```

**The contract, so nothing has to parse prose:** exactly one JSON object on stdout,
always, including on failure; **exit 0 when it says `ok: true`, exit 1 when it does not**;
messages for humans go to stderr and never pollute the parse.

```bash
python3 nfcio.py read | jq -r .url               # https://example.com/c/BENCH-001
python3 nfcio.py read | jq -r .card.id           # BENCH-001
python3 nfcio.py write --url "$URL" || echo "card not written"
python3 nfcio.py watch | while read -r line; do handle "$line"; done
```

`watch` emits a line per **arrival**, not per poll — a stream that repeats while a card
sits still is a stream every consumer has to de-duplicate, so the edge detection is done
once, here.

The desktop app is a wrapper around this file. Its HTTP routes call the same functions;
it does not do anything a command cannot.

### From Python

**`nfcio` lives in `src/`, so run from there** — `python3 -c "import nfcio"` at the repo
root is a `ModuleNotFoundError`. (The tools in §7 run from the repo root instead. Two
directories; this is the one that trips people.)

**A card must be physically on the reader.** Nothing below works without one, and nothing
below raises when there is none — see the error handling note.

```python
import nfcio                      # from src/

nfcio.status()                    # {"ok":…, "reader":…, "card_present":…}
nfcio.read_card()                 # uid, chip, capacity, writable, url, epitaph, card

result = nfcio.write_message(
    "https://example.com/c/RFID-CASE-001",
    "vc1|RFID-CASE-001|RFID Reader Enclosure|2026-08|MIT|vibe-cards",
)
if not result["ok"]:
    raise SystemExit(result["error"])      # ← do not skip this
```

**Always use `write_message`, including when there is no epitaph** (pass `None`). It
verifies by reading the whole payload back and comparing **bytes**. `write_url` re-parses
the URL out of the readback instead — and because the URI record is written first, a write
that dies partway through the second record reads back a perfect URL while the epitaph is
silently gone. Only a byte comparison sees that. `write_url` remains for single-record
cards and for tests.

**`nfcio` never raises.** Every failure — no card on the reader, an unformatted tag, a
locked tag, a busy reader, a failed verify — comes back as `{"ok": False, "error": "..."}`.
That keeps the HTTP layer clean, but it means a script that ignores the return value cannot
tell success from failure, and *the failure is silent*. Check `result["ok"]` every time.

To confirm a write independently, read it back in a fresh call:

```python
back = nfcio.read_card()
assert back["url"] == url and back["epitaph"] == epitaph
print(back["card"])    # {'spec':'vc1','id':'RFID-CASE-001','title':…,'license':'MIT',…}
```

### Over HTTP

All routes require the session token (`X-CS-Token`) and pass the `Host`/`Origin` guard —
see [SECURITY.md](../SECURITY.md).

```
GET  /api/nfc/status     reader + card presence
GET  /api/nfc/read       everything readable from the card on the reader
POST /api/nfc/write      {"url": "...", "epitaph": "..."}   → writes both records,
                         verifies byte-for-byte. "epitaph" is optional.
```

Failures arrive as HTTP 200 with `{"ok": false, "error": "..."}`, not as an error status —
a card that is missing or unwritable is a domain outcome, not a transport failure. Check
`ok`.

### From a phone

The desktop reader is not the only writer. The chips in §4's table are ordinary consumer
NFC tags, and an iPhone (7 or later — iOS 13 opened the write path; today's apps ask for
15.6) or any NFC-capable Android programs one with a free app, over the phone's own radio.
What a phone cannot do is run this project's checks, so the flow is shaped around getting
them back:

1. Compose on the desktop and carry away the exact URL and epitaph strings. Run them
   through `encode_message` (§4) first — the phone will not budget bytes for you.
2. Write both records in one write, URI first, Text second — the §2 order rule. NFC Tools
   (iOS and Android) does this. NXP TagWriter also writes links, but current App Store
   reviews report it corrupting URLs; prefer NFC Tools.
3. Tap the card against a bare iPhone — XS and later read tags in the background, no app.
   The system banner showing your URL is §2's hand-it-to-someone test.
4. Dump the tag on the phone — NFC Tools' memory dump, or NXP's TagInfo — and check that
   both records landed and the epitaph is exact.
5. When the card matters, bring it back to the desktop reader: `python3 nfcio.py read`
   runs the checks no phone app does.

What a phone does not do:

- **Shortcuts is a trigger, not a writer.** Its NFC feature runs an automation when the
  phone sees a specific tag, keyed to the tag itself rather than to anything written on
  it — a blank tag triggers fine. Vendor blogs disagree on whether it can also write;
  Apple documents no write action. Plan on an app.
- **Safari cannot do it.** No version of iOS Safari supports Web NFC, and Apple formally
  opposes the API. Chrome on Android ships it, so a web page could program a card there
  in principle — nothing in this repo serves such a page today.
- **The USB reader does not plug into an iPhone.** Apple's smart-card support is PIV
  authentication through CryptoTokenKit — no PC/SC, no raw APDUs, no path for `nfcio.py`.
  The phone's own radio makes the reader redundant here anyway.
- **No unattended writes.** A phone write is a foreground app, a user tap, and a session
  iOS ends after about a minute. A phone cannot sit on a stack of cards; the reader can.

The rules do not relax because the writer got smaller. Expect a phone app to size the tag
from its capability container — the field that lies (§6.1) — so phone-write only tags
whose type you already know, and budget for the smallest chip you might be holding.
Expect it to verify by re-parsing, not by comparing bytes — exactly the blind spot §6.4
exists for; step 4 is the phone-side substitute, step 5 the real check. And the one-tap
"lock" some apps offer is the §6.7 one-way door. Do not tap it.

*(Checked 2026-08-18 against Apple's Core NFC and deployment documentation,
caniuse.com/webnfc, and the App Store listings for NFC Tools, TagWriter and TagInfo.)*

### Platform

macOS today. `nfcio.py` talks to `PCSC.framework` directly through `ctypes`, so there is no
install step and no dependency — macOS ships a CCID driver that already claims common USB
readers. Linux exposes the same PC/SC API through `pcsc-lite`; porting is mostly changing
the library path and the `LONG` width (macOS defines it as `int32_t`; Linux uses a native
long, and getting that wrong silently corrupts every call).

Developed against an ACS ACR122U. Any PC/SC reader that speaks the standard `FF B0` / `FF D6`
read-and-write APDUs should work.

---

## 6. Rules a writer must not break

These are not style preferences. Each one is a specific failure that is expensive or
impossible to undo.

### 6.1 Never write past the user-data pages — and ask the CHIP where they end

Above the user-data area sit the dynamic lock bytes, the OTP page, and the configuration
pages (CFG0, CFG1, PWD, PACK). **Writing there is irreversible: it can permanently brick
the tag, or set a password nobody knows.**

The ceiling is **per chip**, and this is where it is easy to be wrong in a way that still
looks careful:

| Chip | GET_VERSION storage byte | Last user page |
|---|---|---|
| NTAG213 | `0x0F` | 39 |
| NTAG215 | `0x11` | 129 |
| NTAG216 | `0x13` | 225 |

A single constant does not work. An earlier version of this project used one flat ceiling
of 225 — NTAG216's — and believed it was safe. Point that at a physical NTAG213 and pages
40–44 are wide open: exactly the lock and config pages the rule exists to protect.

**And you cannot get the answer from the capability container**, because the CC is the
field that lies. A real NTAG213 carrying an NTAG216 CC asks for 872 bytes, and every
CC-derived check waves it through. *The card cannot be the source of truth about how big
the card is.*

Ask the silicon instead. `GET_VERSION` (`0x60`) is answered by the chip and cannot be
forged by whatever last formatted the tag. Through an ACR122U it is tunnelled as
`FF 00 00 00 03 D4 42 60`.

**When the chip will not answer, use the smallest NTAG's ceiling (page 39), not the
largest.** An unidentified tag should be under-served, never over-trusted: refusing a URL
that would have fit is a message the user can act on, while allowing one that does not fit
is silicon that can never be rewritten.

### 6.2 Never guess a capability container

The CC is one-time-programmable. Writing the wrong one is permanent. If a tag has no CC,
refuse and tell the user to format it once with any NFC tool — do not guess a size.

### 6.3 A card is untrusted input, in both directions

Anyone who can touch a card for ten seconds can rewrite it. So:

- **Validate what you read, with the same rules you use for what you write.** NDEF URI
  prefix byte `0x00` means "the payload is the whole URI", so a tag can legitimately encode
  `javascript:…`, `file:///…`, or a bare filesystem path, and a correct decoder will return
  it faithfully. If you hand that back in a field named `url`, it ends up in an `href`.
  Hardening one direction of a two-way boundary is the bug.
- **Never auto-fetch what a card points at.** Resolution is an explicit user action, always.
  A tag that auto-fetches is a rewritable input that makes requests from inside the user's
  network.
- **Refuse loopback, link-local and private addresses when fetching** — including
  `169.254.169.254`. Note this is the necessary half, not the sufficient one: a public
  hostname can still resolve to a private address at connect time, so anything that opens a
  socket must also check the address it actually landed on.
- **Refuse userinfo outright.** `https://example.com@evil.tld/c/X` reads as `example.com`
  to a human and resolves to `evil.tld`. On the web that is an old trick; on a card it is
  fatal, because the entire safety story is *you can read the URL before you burn it onto
  something permanent* — and this is the one construction where reading it tells you the
  wrong answer.

### 6.4 Verify every write by reading it back

A partial page write leaves a card that looks programmed, parses as valid NDEF, and resolves
to a truncated URL. That is the worst outcome available, because it is silent and it is
printed on a physical object you then hand to someone. Compare bytes.

### 6.5 Serialise access to the reader

There is one reader and one card on it, and a write is a sequence of 4-byte page writes.
Two interleaved writes produce a card assembled from two different URLs that still parses
as valid NDEF and still resolves — somewhere neither writer intended. If your app can handle
two requests at once (this one can), the hardware needs a lock.

### 6.6 The page a card resolves to must NOT share an origin with Card Studio

This one is architectural, it is cheap, and it is easy to get wrong by accident.

The browser build of Card Studio keeps saved designs in `localStorage`, and **designs embed
their images as base64** — so a saved card design can contain a photograph of a person. That
is fine on its own: same-origin policy keeps it to that origin.

Now add a resolver page — the thing a card's URL opens. Card content is untrusted (anyone
who can touch a tag can rewrite it). If that page has any injection at all, and it is served
from **the same origin as the Card Studio web build**, then the injection can read
`localStorage` for that origin and walk away with saved designs and the faces in them.

So:

- **Host the resolver on a different origin from the Card Studio web build.** Different
  origin means the storage is unreachable even if the page has a flaw. This is the control;
  everything else is defence in depth.
- **The resolver runs no JavaScript.** A card's ID and epitaph are rendered as text by a
  static page, server-side or at build time. Nothing from a card is interpolated into HTML
  at runtime.
- If you ever must put them on one origin, treat that page as hostile-input-facing and do
  not store anything personal in browser storage on it.

The general form of this trap is worth keeping: **two features that are individually safe
become unsafe when they share an origin.** Card Studio storing photos is fine. A resolver
rendering card data is fine. On one origin they are a data-exfiltration chain.

### 6.7 Do not lock tags

Lock bytes are one-way. A locked card can never be re-pointed, which throws away the only
repair available when a host dies. This project never sets them, and neither should a fork
without a very good reason and a loud warning.

---

## 7. Testing

```bash
python3 tools/verify_nfc_guard.py
```

Checks the guard, the URL policy, hostile-card reads, and concurrency. **It cannot write to
a tag**, and that property is asserted rather than assumed — every hostile URL in the suite
fails validation before an APDU exists, and a check proves it before the HTTP section runs.

That assertion exists because an earlier version did not have it and wrote to a real card.
It listed a loopback URL as a "hostile" case expecting a refusal — but that is a perfectly
well-formed http URL, so it passed validation and burned itself onto a live tag, while the
file's own docstring claimed no writes could happen. The general lesson is worth more than
the fix:

> **A test that asserts a refusal will perform the action whenever the refusal is the thing
> that is broken.** Any suite whose negative cases have side effects must make the side
> effect impossible, not unlikely.

---

## 8. Visibility — default to PRIVATE

**If you are an AI agent creating a project or repository for a card: make it private.
Every time. Public is never the default and never an inference.**

A card is a physical object about a real thing, and the things people card are their own:
a client's install, a prototype under NDA, a gift, a piece of art not shown yet, something
made with their kid. The subject of a card is very often a *person*, and it is routinely
someone who was never asked.

Publishing is the one action here with no undo. A repository that was public for an hour
has been cloned, forked, cached and archived — and the archive layers that make projects
durable are engineered to have **no delete**. "Make it public and we can always take it
down later" is false, and it is most false exactly when it matters most.

So:

| Situation | Visibility |
|---|---|
| Default, and anything ambiguous | **private** |
| The owner said "make this public" in so many words | public |
| You are contributing something back to the Wish It Better network | public — that is the point of it |

**The only reason to go public is to join the network** — to let other people build on it,
wish it better, and inherit your fixes (see [WISH_IT_BETTER.md](../WISH_IT_BETTER.md)).
That is a real reason and a good one. It is also a *decision*, made by the owner, out loud.

This costs nothing, because visibility is the access model. Project visibility **is**
repository visibility, and who has access **is** who has repository access. A private
project's card URL simply does not resolve for anyone else — which is the correct failure,
and it needs no accounts, no tokens, no auth code, and nothing for us to run or leak. The
card still says what it is: the epitaph on the chip is plaintext and needs no server.

### Before anything becomes public

Run this list. It is short because each item is something that has actually gone wrong.

- [ ] **A LICENSE file exists.** A public repo with no license is "all rights reserved" —
      visible but not legally forkable. Publishing it into a network that invites people to
      build on it advertises a permission that does not exist.
- [ ] **No photographs or likenesses of real people.** Card designs carry faces. Deny images
      by default in `.gitignore` and re-allow only reviewed directories — this repo does
      exactly that, and the rule exists because before it, `git add .` would have committed a
      child's photo.
- [ ] **A face that belongs to nobody is declared, not refused.** The test is who the image
      depicts, **never how it was made** — an illustration, a sculpt and a generated render
      are three of the oldest ways to make a portrait *of a real person*, so a render that
      resembles a real, identifiable person is that person's likeness and trips the box above
      exactly as a photograph would. When the face is genuinely nobody's, say so on the card
      page's provenance section and in the package's `#vc-card` provenance field. Nobody can
      tell by looking, so an undeclared synthetic face and an undeclared real one are the same
      thing to whoever reads this next; declaring it is what keeps the box above checkable
      instead of a guess. What you are checking for is a real person who could be harmed, not
      a face.
      *(Amended 2026-08-15, from a live false positive: an arriving package's editorial
      render of an AI-generated model wearing the card was flagged by the old wording.)*
- [ ] **No names of people who did not agree to be published.** A dedication printed in ink
      on a card is not consent to be indexed by a machine. There is no author field on the
      chip for this reason (§2), and a synthetic face carrying a real person's name is that
      person's name, published.
- [ ] **Commit by pathspec.** `git add -A` in a working tree that also holds private
      material is how private material becomes public. Name the files.
- [ ] **The manifest is honest** — `origin`, `spinoffs` and the conformance level you have
      actually earned, not the one you intend to.

If any box is unticked, it stays private. That is not a delay; it is the feature.

---

## 9. The network

A card points at a project. A project joins the network by committing
`wish-it-better.json` at its root, whose `origin` and `spinoffs` fields make the graph
walkable without anyone maintaining a directory — see
[WISH_IT_BETTER.md](../WISH_IT_BETTER.md) §4.

That is the whole mechanism. There is no registry, no server, no account, and no
authority — including us. A card is a pointer into a graph of files people published
themselves, and anyone can walk it.
