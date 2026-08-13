# Roadmap — and what this framework transfers to

Vibe Cards is one project. **Wish It Better** is the part meant to outlive it: a portable
standard for building small tools that get measurably better on a loop, in public, with
the history as the proof.

This file says what is next for the cards, and — more usefully — what the framework
transfers to, because that transfer is the whole point.

---

## Near-term, Vibe Cards

Ranked by what actually unblocks people, not by what is fun to build.

> **Shipped since this file was written:** reading and writing the chip. A card is no
> longer just printed — Card Studio programs the NFC tag inside it and verifies the write
> by reading it back. macOS only for now (it talks to `PCSC.framework` directly through
> `ctypes`, so there is still no install step). Type 2 tags: NTAG213/215/216 and MIFARE
> Ultralight. See `src/nfcio.py` and `tools/verify_nfc_guard.py`.

| | What | Why it matters |
|---|---|---|
| **0** | **The projects surface** | A card is a project, made physical. The manifest graph in [`WISH_IT_BETTER.md`](../WISH_IT_BETTER.md) §4 is already walkable by anyone — `origin` and `spinoffs` are edges, and nobody has to maintain a directory. What is missing is the thing that walks it: browse the projects you know about, and write one onto a card. This is the feature the cards were always for. |
| **0.5** | **A stock picker** | Seven card stocks ship in `src/web/textures/` with a registry that records each one's measured luminance and the ink colour that clears contrast against it. The founder template uses one; nothing lets you *choose* one yet. A stock should be a config entry, the way a printer is — pick it from a list, and the template's text colour follows the registry instead of being retyped. Adding an eighth stock should be a file and a row, never a code change. |
| **1** | **Linux / Windows port** | The single most requested thing before it is even released. The platform coupling is narrow: CUPS/`lp` for printing, `lpstat`/`lpoptions` for discovery, `open` for the window. The design surface, PDF composer and geometry model are already neutral. The chip layer adds one more: `nfcio.py` is macOS PC/SC today, and `pcsc-lite` speaks the same API on Linux. [Claim it →](../../issues/new?template=platform-port.yml) |
| **2** | **More tray + printer profiles** | A new printer is a `profiles.json` entry, never new code. Every profile someone contributes makes the project work for a whole class of hardware. |
| **3** | **Batch from CSV, end to end** | Print 50 named cards without touching the designer 50 times. The batch surface exists; the loop around it is thin. |
| **4** | **Dual-frequency reader support** | 125 kHz and 13.56 MHz are incompatible families and the choice traps people. Supporting both removes the single most expensive wrong purchase. |
| **5** | **Enclosure variants** | The generator is parametric. Other reader boards are constants, not mesh surgery. |

## Near-term, the framework

- **First amendment.** `WISH_IT_BETTER.md` §5 is live but unused — v1.0 is the seed. The
  first adopter who hits a real scar the spec did not prevent upgrades it for everyone.
  That first amendment is the moment the standard starts compounding instead of just
  existing.
- **Agent review of incoming wishes.** Every request gets read carefully and organised —
  triaged against the eval bar, checked against the security gate, routed. The gate
  (`tools/verify_contribution.sh`) is the mechanical half and already runs; the review
  loop around it is the next build.
- **A crawler for the network graph.** `wish-it-better.json` carries `origin` and
  `spinoffs`. Those edges are walkable *today* by anyone — nobody has to maintain a
  directory. Someone should render it.

---

## Isomorphic transfer — where this pattern goes next

The five stages behind Vibe Cards are not about cards:

```
a physical thing you already own
  + a printed part that makes it usable
  + a local app that removes the tedious step
  + evals that could have failed
  + a public loop that improves it without you
```

Swap the nouns and the structure holds. Candidates, in rough order of how ready they are:

**AV and field trades.** Site surveys, rack elevations, cable schedules, gear checklists —
the documents a working AV tech assembles by hand, in the trade's own vocabulary. The
strongest candidate because the constraint is already known: *ticking beats typing*. If
the task is a list, build a list; never answer a narrative task with a twelve-field form.
And never compete with whoever already owns and numbers the document — scope to what you
*send* them.

**Other desk peripherals.** RFID was the first reader; the pattern is the same for
sensors, SDRs, cameras, scanners. Off-the-shelf board, printed enclosure, small local app
that removes the tedious step, evals, loop.

**Internal think-tank tools.** Build the same shape for a team, keep it private, and still
adopt the standard — then choose, later and separately, whether to contribute anything
back. Adoption and contribution are deliberately two different decisions. `wish-it-better.json`
with `origin: null` and a private repo is a completely valid L0.

**Anything with a physical irreversible step.** The most transferable idea in this repo is
not the code — it is that the two irreversible actions (printing on PVC, printing the
enclosure) each have a cheap rehearsal immediately before them: dry run, calibration print,
single test print. Any project with a costly commit step can copy that ordering directly.

---

## What would make the network real

Not more projects — **more amendments**. A network of forks is a fan-out; a network where
one project's scar upgrades every other project's standard is a flywheel. The mechanism is
already written down (`WISH_IT_BETTER.md` §5) and deliberately strict:

- An amendment must come from something **shipped**, never from a theory.
- It must name the **concrete scar** the current spec allowed.
- It should prefer **deleting** a rule to adding one — a spec that only grows becomes a
  spec nobody reads, and an unread rule enforces nothing.

That is the whole ask. Build something small, hold it to the eval bar, and when the
standard fails you, say so in a pull request.
