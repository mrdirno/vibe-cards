# Security

Card Studio runs a small HTTP server on your machine and shells out to the printing
system. That is a real attack surface, and this document says exactly what is guarded,
what is not, and how contributions touching it get reviewed.

## Reporting a vulnerability

Open a **private security advisory** on the repository (Security → Report a vulnerability).
Please do not open a public issue for anything exploitable.

Include: the endpoint or file, a reproduction (a `curl` line is ideal), and what an
attacker gains. A working reproduction is worth more than a severity rating — see the
project's eval bar (`docs/EVALS.md` §1) for the standard the fix will be held to.

## Threat model

The realistic attackers, in order of how likely they are to matter:

1. **A web page the user visits.** It cannot read cross-origin responses, but it *can*
   send requests to `127.0.0.1` on a guessed port. Left open, that means printing to your
   printer, killing the app, or writing to its settings.
2. **DNS rebinding.** An attacker serves `evil.tld`, re-points it at `127.0.0.1`, and
   their page becomes **same-origin** with the app — which lifts the read restriction in
   (1) entirely.
3. **Another local process or user account.** `127.0.0.1` is reachable by everything on
   the machine. Loopback is not an isolation boundary.

4. **A card itself.** Since the app gained NFC read/write, a tag is an input — and an
   unlocked tag is rewritable by anyone who can touch it for ten seconds. A card handed to
   you, left on a desk, or embedded in an object in public is a stranger's data arriving on
   a physical object that looks trustworthy because you can hold it.

Explicitly out of scope: an attacker who already has your user account.

### The card as an attack surface

Two properties make this different from the rest of the app, and both cut in a direction
that is easy to get backwards.

**Writing leaves the machine and cannot be undone.** `/api/nfc/write` is the only route
here whose effect is a physical object someone else ends up holding. There is no redeploy
and no patch — the card is simply wrong, in someone's pocket, until it is found and
rewritten. So the URL is passed through verbatim (never normalised, never "helpfully"
completed), verification is forced on and compares **bytes** rather than re-parsing, and
the write refuses anything that is not plain `http(s)`.

**Reading is the direction people forget to guard.** An NDEF URI record with prefix byte
`0x00` means "the payload is the whole URI", so a tag can carry `javascript:…`,
`file:///…`, `data:…`, or a bare filesystem path — and a *correct* decoder returns it
faithfully. Handing that back in a field named `url` is how it reaches an `href`. The read
path therefore runs the same policy object as the write path. This was a real defect in
this repo: `write_url` refused `javascript:` while `read_card` returned it. **Hardening one
direction of a two-way boundary is the bug.**

Three rules follow, and they are enforced in `src/nfcio.py`:

| Rule | Why |
|---|---|
| Nothing auto-fetches what a card points at | otherwise a rewritten tag makes requests from inside the user's network — resolution is always an explicit user action |
| Fetching refuses loopback, link-local, private and reserved addresses | including `169.254.169.254`. Necessary, not sufficient: a public name can still resolve to a private address at connect time, so any socket-opening caller must re-check what it landed on |
| Userinfo (`https://good.example@evil.tld/`) is refused outright | it reads as one host and resolves to another, and the entire safety story of a card is that you can read the URL before you burn it onto something permanent |

Writing to loopback or a private address is **warned, not refused** — the same rule that
blocks `127.0.0.1` would block `192.168.1.50`, and tagging your own printer is legitimate.
Inform at write; refuse at fetch.

### Origin separation for anything that resolves a card

The browser build stores saved designs in `localStorage`, and designs embed their images as
base64 — so that storage can hold a photograph of a person (`src/web/backend-static.js`,
where the comment at the setter says exactly this).

A page that *resolves* a card renders untrusted input, because a tag is rewritable by anyone
who can touch it. If such a page shares an origin with the Card Studio web build, then any
injection on it can read that origin's `localStorage` and exfiltrate saved designs.

**Therefore: a card resolver must be served from a different origin than the Card Studio web
build, and must run no JavaScript.** Neither feature is unsafe alone — storing designs is
fine, rendering card data is fine — they are only unsafe *co-located*. Same-origin policy is
the actual control here, so the deployment decision is the security decision.

Full contract, byte budget and the irreversible-page rules: [`docs/CARDS.md`](docs/CARDS.md).
Adversarial suite: `python3 tools/verify_nfc_guard.py`.

## What is guarded, and where

| Guard | Stops | Implementation |
|---|---|---|
| `Host` allow-list | DNS rebinding | `server.py` → `Handler._guard` |
| `Origin` check | Cross-origin drive-by | `server.py` → `Handler._guard` |
| Per-run session token on every `/api/*` | Blind CSRF | minted in `server.py` (`SESSION_TOKEN`), served once into `index.html`, sent as `X-CS-Token` |
| Design reads matched against the real listing | Arbitrary file read | `server.py` → `/api/design/` route |
| Printer names matched against CUPS output | Argument injection, `.ppd` path traversal | `server.py` → `_known_printer` |
| IPP keyword validation | ipptool directive injection | `server.py` → `_ipp_keyword` |
| Static serving confined to `web/` | Path traversal | `server.py` → `_static` |

Two of these deserve a note, because they are the mistakes that are easy to reintroduce:

- **`DESIGNS / name` silently discards `DESIGNS` when `name` is absolute.** That is
  standard `pathlib` behaviour and it turned a "load my card" route into "read any JSON
  file on this machine." Never join user input into a path — match it against a listing.
- **A token alone does not stop rebinding, and a `Host` check alone does not stop CSRF.**
  They defend different attacks. Removing either one reopens a hole the other never
  covered.

## Known limitations

- The session token lives in the served HTML. Anything that can already read that page
  can act as the app. The `Host` guard is what keeps that page unreachable from outside.
- The server trusts the local filesystem — a user who edits their own `settings.json` or
  `my_supplies.json` is trusting themselves.
- `pdfwriter.py` parses image data supplied by the user. It has not been fuzzed.

## The review gate for contributions

Any pull request touching `server.py`, the print path, or file handling goes through this
gate before merge. It is deliberately mechanical — a checklist beats a judgement call.

**Automated (run `tools/verify_contribution.sh`):**

1. No new `subprocess` call with `shell=True`.
2. No new interpolation of a request value into a path, an argv, or a directive string.
3. No new network egress (this app talks to the printer and nothing else).
4. No new third-party dependency (the app is stdlib-only by design).
5. Python and JavaScript both parse; the first-run harness still passes.

**Human, for anything the script cannot decide:**

6. Does the change widen what an unauthenticated request can reach? If yes, it needs a
   live reproduction showing it does not.
7. Does it add a route? Every route inherits `_guard` automatically — confirm it was not
   bypassed with a new `do_*` handler.
8. Per eval bar **E5**: for security-relevant changes the default verdict is *refuted*.
   An independent pass must try to break the claim and fail, citing the lines that make
   it safe.

A contribution that cannot clear (6)–(8) is not rejected — it is held, with the specific
reproduction it needs written into the PR. That is the difference between a gate and a
wall.
