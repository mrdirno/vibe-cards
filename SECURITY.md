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

Explicitly out of scope: an attacker who already has your user account.

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
