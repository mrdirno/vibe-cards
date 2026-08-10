# Contributing

This project runs the [Make It Better loop](MAKE_IT_BETTER.md). Contributions are not just
welcome — they are the mechanism. Here is how each kind works.

## I want it to do something it doesn't

**File a wish.** [New wish →](../../issues/new?template=wish.yml)

A wish takes under a minute and needs no reproduction steps. "I wanted to print 10 cards
with different names and had to do it by hand" is a perfect wish. It tells us the shape of
a gap, which is more useful than a proposed solution.

Every wish reaches one of four states — **claimed, shipped, declined with a reason, or
expired**. A declined wish gets an actual explanation; silence is not one of the options.

## I want it to work on my platform

This is the highest-value contribution right now, and the most explicitly wanted.

The app is macOS-only today, and the coupling is narrower than it looks: it is CUPS/`lp`
for printing, `lpstat`/`lpoptions` for discovery, and `open` for the window. The design
surface, the PDF composer, and the geometry model are all platform-neutral.

If you are porting, [open a platform-port issue →](../../issues/new?template=platform-port.yml)
first so two people do not do it twice. Keep the platform seam in one place rather than
threading `if platform == ...` through the composer.

## I found a bug

[Open a bug →](../../issues/new?template=bug.yml). What it did, what you expected, and —
for anything print-related — your printer model and whether the dry run also fails. A dry
run that succeeds while a real print fails is a completely different problem from one
where both fail.

## I found a security issue

**Do not open a public issue.** See [SECURITY.md](SECURITY.md) — use a private advisory.

## I want to send a pull request

1. **Run the gate first:** `./tools/verify_contribution.sh`
   It checks the mechanical things (no shells, no path joins on request data, no new
   dependency, everything parses) so review can be about the actual idea.
2. **Bring an eval, not a claim.** The bar is in [MAKE_IT_BETTER.md §2](MAKE_IT_BETTER.md);
   worked examples are in [docs/EVALS.md](docs/EVALS.md). The short version: describe the
   observation that would have proven you wrong, then show it did not happen. Verify at
   the built artifact, not only the source.
3. **Write the lesson next to the code.** If the obvious fix was wrong, say why in a
   comment where the next person will hit it. That comment is worth more than a changelog
   entry.
4. **Small and causal beats large and sweeping.** A fix at the cause, with an eval, gets
   merged. A refactor without one does not.

### House style

- **Stdlib only.** Pillow is the single optional dependency, always inside a `try/except`
  with a working fallback. This is why there is no install step, and the gate enforces it.
- **One renderer.** The canvas has exactly one draw path (`drawFace()`); the empty state
  and everything else derive from the document in `render()`. Do not add a second place
  that mutates the view.
- **Comments explain *why*, especially why the obvious thing is wrong.** The existing
  comments are the format to match.
- No build step, no bundler, no framework. `index.html` + `app.js` + `styles.css`.

## Forking, and staying in the network

Fork freely — MIT. If your fork becomes its own thing, please set `origin` in your
`make-it-better.json` to point back here. That single field is what lets improvements flow
back along the edge they came from, and it is the whole mechanism behind the network.

If this spec fails you — if you hit a real scar it did not prevent — **amend it**
(MAKE_IT_BETTER.md §5). An amendment must come from something you shipped, not from a
theory, and it should prefer deleting a rule over adding one. Amendments propagate to
every adopter, which is what makes the standard compound rather than merely exist.
