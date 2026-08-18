# Vibe Cards — agent brief

You are working in **Vibe Cards**: an app that prints CR-80 RFID/ID cards on a desktop
inkjet, a 3D-printable enclosure for the card reader, and the **Wish It Better** framework
that networks projects like this one.

This file is the entry point. Read it fully before your first edit — it is short, and
every line in it is something that cost someone real time.

## Run it

```bash
cd src && python3 server.py          # opens the UI; prints its port
./build_app.sh                       # → ~/Desktop/Card Studio.app
```

No install step. **Python 3 stdlib only** — Pillow is the one optional dependency and every
use of it sits inside a `try/except` with a working fallback. `tools/verify_contribution.sh`
enforces this; do not add a dependency to save yourself twenty lines.

For automation:

```bash
CARD_STUDIO_PORT=8791 CARD_STUDIO_NO_BROWSER=1 python3 server.py
```

## Security first — read this before touching `src/server.py`

This app serves HTTP on `127.0.0.1` and shells out to the printing system. **Loopback is
not a security boundary.** An audit of an earlier version reproduced two live exploits:
it served `~/.docker/config.json` to any web page, and any site the user visited could
kill the app or drive their printer.

Four rules. Breaking any one of them reopens a hole that was already exploited once:

1. **`Host` allow-list AND a per-run token.** The `Host` check stops DNS rebinding; the
   token stops blind CSRF. They defend *different* attacks — neither alone is enough.
   Both live in `Handler._guard`, which every route inherits. If you add a `do_*` method,
   call `_guard` first.
2. **Never join request data into a filesystem path.** `BASE / user_input` silently
   discards `BASE` when the input is absolute — that is exactly how the file read
   happened. Match against a real listing instead (`list_designs()`). A genuinely
   necessary exception must carry an inline `# gate-ok: <why>` so review sees it.
3. **Never interpolate request data into a directive language** — shell, IPP, SQL,
   template. Validate against the grammar and refuse (`_ipp_keyword`, `_known_printer`).
   Do not try to escape.
4. **Prove it with a reproduction, not a reading.** "Looks guarded" is not evidence. Run
   the exploit before and after, and keep a legitimate-client control — a guard that also
   breaks the real client is not a fix.

Full threat model and the review gate: [`SECURITY.md`](SECURITY.md).

## Traps that will cost you an hour each

- **`grep` is blind on `src/web/app.js`.** It uses NUL bytes as cache-key delimiters, so
  `file` calls it `data` and **plain `grep` prints nothing at all** — not "Binary file
  matches", nothing. A search for a symbol that is definitely there returns zero hits and
  reads as "this feature does not exist." Use `grep -a`, or read it with Python.
- **The built app is a *copy* of `src/`.** Editing `src/` does not change
  `Card Studio.app`. Rebuild, then verify against the bundle path.
- **A running instance makes `open -a` a no-op**, so a freshly rebuilt bundle keeps
  serving the old code. Kill the old server *by PID* (`ps -Eww -o pid=,command=`), delete
  `~/Library/Application Support/Card Studio/port`, then relaunch. Confirm a new
  `Card Studio serving …` line in `launch.log` before believing anything.
- **Do not `pkill -f "python3 server.py"` from an agent shell** — the pattern can match
  your own shell's command line and kill it.
- **Someone else is probably editing this repo right now.** The owner works this project
  from two terminals at once, and other agent sessions run against the same checkout. So
  the working tree is not yours, and it changes *while you are in it*. On 2026-08-17 a
  whole card family — `src/site/rexi/`, `src/site/kelibro/`, nine card images and their
  `app.js` templates — appeared mid-cycle, between one `git status` and the next.
  **The fix is structural: give each session its own worktree.** One repository, one
  history, separate working directory *and separate index* — so two sessions cannot
  collide at all, rather than agreeing not to.

  ```bash
  git worktree add ../vibe-cards-b -b session-b     # second terminal works here
  git worktree list
  ```

  Everything below is what you need when you are nonetheless sharing one tree, and it is
  written from getting it wrong:

  - **`git add` does not scope a commit. `git commit -- <paths>` does.** This is the one
    that bites. Staging your file is not the same as committing only your file: a bare
    `git commit` commits *the entire index*, including whatever the other session already
    staged. On 2026-08-17 a careful `git add CLAUDE.md` was followed by a bare
    `git commit`, and 51 of the other terminal's files went out under a commit message
    about something else — pushed before that session had chosen to ship them. Nothing was
    lost, but the record is wrong and cannot be repaired without a force-push that would
    race the live peer.
  - **Read `git diff --cached --name-only` before every commit, and count it.** It is the
    only thing that shows what you are actually about to ship. `git status` invites you to
    read the column you expected rather than the one that is there.
  - **`git add -A` and `git add .` are never right here.** They sweep the other session's
    files into your staging area, and then the rule above ships them.
  - **`git stash` takes the other session's tracked edits too**, and `stash pop` hands them
    back unstaged — which silently un-stages deletions someone had already `git rm`'d. That
    happened the same day: three deleted files quietly came back to life in the index, and
    a plain `git commit` would have shipped a change that undid itself. If you need a clean
    tree to compare against, build from `git show HEAD:<path>` or a scratch clone instead.
- **Personal data is not in this repo, by design.** The owner's reader and purchases live
  in `~/Library/Application Support/Card Studio/my_supplies.json` and merge at runtime.
  Never move that content into `src/supplies.json`. The same rule covers the card ledger
  below: the tool is shared, the inventory is not.

## Which physical cards exist

The repo describes card **designs**. A printed, programmed card is an **instance**, and
until `tools/card_ledger.py` there was nowhere that recorded one — a card that had been
shredded and a card that was never made looked identical, which is to say invisible. Two
questions need this file: which chips are out there carrying which project (so you know
what to reprogram when a URL moves), and which ones have been pulled.

```bash
python3 tools/card_ledger.py --list
python3 tools/card_ledger.py --record                     # the card on the reader
python3 tools/card_ledger.py --retire --reason "misprint" # the card on the reader
python3 src/nfcio.py erase                                # blank a card before binning it
```

Data lives at `~/Library/Application Support/Card Studio/cards.json`, with an append-only
`cards_actions.log` beside it. **A retired row is never deleted** — deleting it puts the
ledger back in the state that made it necessary.

## How work gets accepted here

This project runs the [Wish It Better loop](WISH_IT_BETTER.md). Before you call anything
done:

```bash
./tools/verify_contribution.sh      # the mechanical gate
```

Then bring an **eval**, not a claim. The bar is §2 of `WISH_IT_BETTER.md`; worked examples
with real numbers are in [`docs/EVALS.md`](docs/EVALS.md). In short:

- **E1** Write the observation that would have proven you wrong — *before* the fix.
- **E2** Verify at the artifact a user touches (built app, rendered page), not the source.
- **E3** Report the denominator and name what was excluded. Count is not coverage.
- **E4** State any sampling, truncation, or top-N. A silent cap reads as full coverage.
- **E5** Security- or data-relevant? Default verdict is *refuted* until an independent
  pass fails to break it.
- **L** Write the lesson next to the code it belongs to, not in a changelog.

## Architecture, in one breath

```
src/server.py     stdlib HTTP server on 127.0.0.1 — API, printing, CUPS; the guard lives here
src/pdfwriter.py  hand-rolled PDF composer (exact page geometry is the whole trick)
src/nfcio.py      the chip half — NFC read/write over PC/SC via ctypes; no dependency
src/web/app.js    the entire frontend, one file, ONE renderer (drawFace) — no framework
src/profiles.json tray + page geometry; a new printer is a CONFIG, never new code
hardware/         the printable reader enclosure + its parametric generator
```

## The chip

A card is printed **and** programmed. [`docs/CARDS.md`](docs/CARDS.md) is the full contract —
read it before touching `src/nfcio.py` or the `/api/nfc/*` routes. It is written so an agent
handed only this repo can program a card correctly; if it is not sufficient for that, fix it.

The four things that will cost you a card, a tag, or a user:

1. **Page 225 is the last user-data page.** Above it are the lock and configuration pages,
   and writing there is irreversible — it bricks the tag. Do not derive that ceiling from
   the card's own capability byte; a mis-formatted tag can claim a capacity it does not
   have. The card does not get a vote on where you may write.
2. **A card is untrusted input in BOTH directions.** Ten seconds of physical access rewrites
   any unlocked tag. Validate what you *read* with the same policy you use for what you
   *write* — an NDEF URI record can legitimately carry `javascript:` or a bare filesystem
   path, and a faithful decoder will hand it straight back. Nothing auto-fetches a card.
3. **Verify writes by comparing bytes, not by re-parsing.** The URI record is written first,
   so a write that dies partway through still reads back a perfect URL while the second
   record is silently gone.
4. **One reader, one lock.** `server.py` is a `ThreadingHTTPServer`; two interleaved writes
   produce a card assembled from two different URLs that still parses as valid NDEF.

Run `python3 tools/verify_nfc_guard.py` after any change here. It cannot write to a tag —
that property is asserted in the suite, for a reason documented at the top of the file.

## Trace what you built on, and say so

Before a project is listed, submitted, or called finished, work out what it
actually came from and name it — the forks, the specs, the posts, the person who
answered the question, the model that wrote the first draft. `origin` in the
manifest covers a fork. It does not cover the rest, and the rest is most of it.

This is an agent's job specifically, because an agent is the one participant that
can reconstruct the lineage and has no instinct to. Silence about provenance is a
claim of originality, and it is usually a false one.

Credit how the person asked to be credited, including not at all. Do not add a
name to a public surface that nobody asked you to add.

## If you are an agent making a repo for a card: PRIVATE, every time

**Default to private. Public is never an inference — only ever an instruction.**

Cards are about real things and very often about real people: a client's install, a gift,
a prototype, something someone made with their kid. Publishing has no undo — an hour of
public is cloned, forked, cached and archived, and archives are built to have no delete.

The only reason to go public is to contribute to the [Wish It Better
network](WISH_IT_BETTER.md) so others can build on it. That is a good reason, and it is the
owner's call to make out loud — not yours to infer from enthusiasm.

It costs nothing, because visibility *is* the access model: a private project's card URL
just does not resolve for anyone else. Correct failure, no auth to build. The checklist to
run before anything goes public is [`docs/CARDS.md`](docs/CARDS.md) §8.

**The refusal binds on a real person; a synthetic face gets declared instead.** No name,
photograph or likeness of a real, identifiable person who did not agree — absolute, checked
before publication and never after, because the archives have no delete and a child cannot
consent. A face that belongs to nobody is not that — but **the test is who it depicts, never
how it was made.** An illustration, a sculpt and a generated render are three of the oldest
ways to make a portrait *of a real person*, so a render that resembles a real, identifiable
person is that person's likeness however it was made, and the refusal applies to it
unchanged. The exemption is only for a face no real person can be recognised in. When it is
genuinely nobody, declare it on the card page's provenance section and in the package's
`#vc-card` provenance field: you cannot tell by looking, which makes an undeclared synthetic
face and an undeclared real one the same artifact to the next agent reading this repo. Ask
whether there is a real person who could be harmed, not whether there is a face. (Amended
2026-08-15, after the old wording flagged an arriving package's editorial render of a model
who does not exist. Corrected within the hour: the first draft exempted "an AI-generated
model, an illustration, a sculpt" as a class, which keys the carve-out on the medium and
would have permitted a generated likeness of a real, identifiable person — the exact harm
the rule exists to prevent.)

## Anything a stranger can see is written for a stranger

Short sentences. Concrete nouns. No internal vocabulary. If 99 people out of 100 would not
follow it on one read, it is not finished.

On 2026-08-15 the front page of the network site opened with a single 2,165-character
sentence. Five review passes had each **appended** a description of their own method to
`curation.panel` in `src/site/network.json` — 165, 200, 491, 720 and 589 characters.
Nothing ever replaced anything. `tools/build_site.py` joins that list with `", "` into one
`<p class="curated">`, and that paragraph sits outside the `<details>` fold the per-entry
notes were put behind, so it was the first thing a visitor read.

Two mechanisms produced it, and both outlive this instance:

- **An append-only field was rendered to a person.** `panel` only grows. A field that only
  grows must never be the thing a reader sees.
- **One field served two audiences.** `curator_note` is at once this project's audit record,
  where density is correct and valuable, and the text on a public page, where density is
  fatal. Nobody had to choose which one they were writing for, so nobody did. Keep the split
  explicit: the dense version goes in an `audit` field the builder does not render (as
  `curation.note` already is), the plain version goes in the field the page renders.

Operator, same day: *"the payload delivery mechanism should be as good as the content being
delivered so it reaches the most people and gives it a fighting chance for propagation or
people wanting to share it."* Nobody shares a wall of text. A page that is not read does not
travel, which makes this a distribution problem rather than a matter of taste.

The standard is already in the file — `listed[0].curator_note`, 122 characters:

> Composes card PDFs against per-printer tray geometry and writes the NFC chip over PC/SC,
> from the Python standard library.

One sentence, real things named, and not a word about the process by which it was checked.
Measured the same day, the rest of the registry: 36 strings over 300 characters, 73,351
characters of prose in an 87,457-byte file — 84% prose.

Density is still right in code comments, audit fields, internal docs and commit messages.
This is a rule about audience, not about writing less. Nothing is deleted either: the audit
text moves to a field the page does not render, verbatim, every number and command intact.

House style: comments explain **why**, especially why the obvious thing is wrong. Match
the existing ones. One renderer — do not add a second place that mutates the view. A new
printer or tray is a profile entry, not a branch in the composer.

## Rebuilding the whole thing from scratch

[`AGENT_REPLICATION.md`](AGENT_REPLICATION.md) — the exact order that worked, including
which two steps are physically irreversible (printing on PVC, printing the enclosure) and
the cheap rehearsal that goes immediately before each.
