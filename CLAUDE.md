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
- **Personal data is not in this repo, by design.** The owner's reader and purchases live
  in `~/Library/Application Support/Card Studio/my_supplies.json` and merge at runtime.
  Never move that content into `src/supplies.json`.

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
src/web/app.js    the entire frontend, one file, ONE renderer (drawFace) — no framework
src/profiles.json tray + page geometry; a new printer is a CONFIG, never new code
hardware/         the printable reader enclosure + its parametric generator
```

House style: comments explain **why**, especially why the obvious thing is wrong. Match
the existing ones. One renderer — do not add a second place that mutates the view. A new
printer or tray is a profile entry, not a branch in the composer.

## Rebuilding the whole thing from scratch

[`AGENT_REPLICATION.md`](AGENT_REPLICATION.md) — the exact order that worked, including
which two steps are physically irreversible (printing on PVC, printing the enclosure) and
the cheap rehearsal that goes immediately before each.
