#!/usr/bin/env python3
"""Assemble the whole published site — landing page AND the studio app.

    python3 tools/build_site.py [outdir]              # default: _site
    python3 tools/build_site.py [outdir] --landing-only

This builds exactly what deploys. It used to build only the landing page while
the GitHub Actions workflow assembled /studio/ with its own shell block — two
places describing one artifact, which had the effect you would predict: running
the verifier locally could NEVER pass, because the studio it looks for was only
ever created in CI. A check that cannot pass gets ignored, and an ignored check is
the same as no check with extra steps.

One command, one artifact, verifiable on a laptop before it is pushed.

The page ships no JavaScript, so the project feed cannot be fetched at runtime.
It is substituted here at build time, into the <!--FEED--> marker.

Everything interpolated is HTML-escaped. Entries come from a JSON file that an
agent panel writes, so it is not hand-authored input.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SITE = SRC / "site"
WEB = SRC / "web"

# The published origin, as one name rather than two literals. It was written out
# twice — once for the frozen-page sweep, once nowhere at all, because the
# per-node manifest emitter below needs to ask "is this listed url inside my own
# site?" and there was nothing to ask. A second literal would have been a second
# truth, and this file's manifest copier says in its own comment why that is the
# thing to avoid.
SITE_ROOT = "https://mrdirno.github.io/vibe-cards/"
MARKER = "<!--FEED-->"
TOKEN = "__CS_SESSION_TOKEN__"

# THE LIMITS ARE MEASURED OFF THIS FILE'S OWN CORPUS, NOT WISHED.
#
# Every number below is the length of a string that ALREADY WORKS on the deployed
# page, so tripping the gate means "you are now denser than the best thing here",
# not "you exceeded a round number somebody liked".
#
#   SUMMARY_MAX 200  — the longest summary in network.json is COLLAGE-001 at 194
#                      characters and it reads fine as the one line under a title.
#                      200 is that, rounded up by six. Nothing needs more; the four
#                      listed summaries measure 95, 128, 194 and 91.
#   NOTE_MAX    300  — VIBE-CARDS-001's curator_note is 122 characters and is the
#                      ONE entry a stranger can already read without clicking:
#                      "Composes card PDFs against per-printer tray geometry and
#                      writes the NFC chip over PC/SC, from the Python standard
#                      library." 300 leaves room for a second sentence at that
#                      density and still refuses the 2,703 / 3,752 / 4,129 /
#                      5,540-character audit essays the other entries carried.
#   MAX_SENTENCES 2  — the good note is one sentence. Two is the allowance for
#                      "what it is" + "why it is at this level".
#   MAX_WORDS_PER_SENTENCE 25 — the plain-language ceiling used by every readability
#                      standard in wide use (plainlanguage.gov, the UK GDS style
#                      guide, Hemingway's "hard to read" threshold). It is the only
#                      number here NOT derived from this corpus, and it is the one
#                      that catches the real failure mode: a 280-character string
#                      that passes the character cap by being a single 46-word
#                      sentence is not readable, it is merely short.
SUMMARY_MAX = 200
NOTE_MAX = 300
MAX_SENTENCES = 2
MAX_WORDS_PER_SENTENCE = 25

# Dotless abbreviations whose full stop does NOT end a sentence. Dotted ones
# (e.g. / i.e. / U.S. / an initial "A.") need no list — sentences() catches any
# token carrying an internal dot, which is what an initialism is.
#
# The months are here because this registry writes dates in prose constantly and
# "Reviewed in Aug. The panel found…" is the exact shape that made the first
# version of this function report two sentences where a reader sees one. "mar" is
# deliberately absent: it is the Spanish word for sea, and the node pages this
# repo publishes are Spanish-first.
ABBREVIATIONS = {
    "etc", "vs", "cf", "approx", "fig", "al", "mr", "mrs", "ms", "dr", "jr",
    "sr", "inc", "ltd", "no",
    "jan", "feb", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov", "dec",
}

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


ENTRY_MARKER = "<!--ENTRIES-->"


# ── THE WAY BACK ─────────────────────────────────────────────────────────────
#
# Three people, three different cards, one complaint, none of them answered by
# what was already on the page:
#
#   "You need a working vibe craft link hopefully all the cards link to the main
#    vibe cards project page presentation"                        — ZARIA-HALO-006
#   "How do you go to main vibe card page?"                — COMPOUND-CRAFT-BOOK-1
#   "Every card should be clickable and takes you to the card presentation page"
#                                                                 — VIBE-CARDS-001
#
# A link home had ALREADY been added to all seventeen pages, and a check in
# verify_pages_artifact.mjs already asserted it was there, and both were green
# while all three people were writing in. Measured at 390x844 on the built site:
#
#     pages whose only link home is below the first screen   18 of 18
#     the worst of them                          /kaze/ at y = 16,683px
#     the two pages that wished for it   /zaria/ 11,946 · /compound-craft/ 10,583
#     smallest tap target             /gt/ at 91x14 px, in 10.5px type
#
# The check asked "does a link exist". A person asks "can I get back". Those are
# not the same question, and eighteen greens is what the gap between them looks
# like. So the bar goes FIRST IN THE BODY, where above-the-fold is a property of
# the document rather than a number that has to keep being re-measured.
#
# HERE, not in seventeen files. This is the only loop every per-card page passes
# through, so this is the only place the bar can be added once and be true of
# page eighteen as well. Editing the pages by hand would be seventeen copies to
# keep in step and a new page silently born without one — the same shape as the
# footer link that was already there and already insufficient.
#
# NO LITERAL COLOURS, and this is the load-bearing part. There is no common
# ground to match: twelve of these pages are pale paper spanning #FAFAF8 to
# #EAE0C8, five are near-black from #08080A to #14100C, and no two share an
# accent. A dark bar is a slab on the twelve; a pale bar is a slab on the five;
# a mid-tone is wrong on both. `color:inherit` over a transparent ground is the
# page's OWN ink on the page's OWN paper — a contrast pair each page already
# chose and checked. The hairline is currentColor at 16%, for the same reason.
#
# NORMAL FLOW, NOT position:fixed. Fixed would sit on top of the six pages that
# open with their own top strip, and would have to win a z-order fight with the
# full-viewport texture layers on the two generated artifacts. First-in-flow
# pushes the page's own heading down instead of covering it, needs no stacking
# context and no JavaScript — and these pages ship no JavaScript on purpose.
WAY_BACK_MARK = "vc-way-back"

# Only the two pages that say lang="es" get Spanish, because the page's own
# declaration is the one signal that cannot drift from what is written on it. A
# second list of "the Spanish ones" kept here would be a second truth, and the
# first thing to go stale when a page is translated.
WAY_BACK_WORDS = {"es": "Todas las tarjetas"}
WAY_BACK_DEFAULT = "All the cards"

WAY_BACK_CSS = """<style>
.vc-way-back{position:relative;display:flex;align-items:center;gap:.55em;
  box-sizing:border-box;width:100%;min-height:48px;
  padding:12px max(16px,env(safe-area-inset-right,0px)) 12px max(16px,env(safe-area-inset-left,0px));
  background:transparent;color:inherit;text-decoration:none;
  font:600 15px/1.2 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
  letter-spacing:.01em}
.vc-way-back::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;
  background:currentColor;opacity:.16}
.vc-way-back:hover,.vc-way-back:focus-visible{text-decoration:underline;text-underline-offset:4px}
.vc-way-back .vc-arrow{font-size:1.2em;line-height:1}
</style>"""

BODY_RE = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
LANG_RE = re.compile(r"<html\b[^>]*\blang=\"([^\"]+)\"", re.IGNORECASE)


def way_back(depth: int, lang: str) -> str:
    """The bar itself. `depth` is how many directories down from the site root the
    page sits — 1 for zaria/, 2 for lab/universe/ — so the href is computed from
    where the file actually is rather than from a table that can disagree with it."""
    words = WAY_BACK_WORDS.get((lang or "").split("-")[0].lower(), WAY_BACK_DEFAULT)
    return (WAY_BACK_CSS
            + f'\n<a class="{WAY_BACK_MARK}" href="{"../" * max(depth, 1)}">'
            + f'<span class="vc-arrow" aria-hidden="true">&#8592;</span>{words}</a>')


def add_way_back(payload: bytes, depth: int, rel) -> bytes:
    """Put the bar immediately after <body>. Returns the page unchanged if it
    already carries one, so this is safe to run twice.

    A page with no <body> tag is a HARD FAILURE rather than a quiet skip. That is
    the whole lesson of the defect this bar exists to fix: the thing that let a
    wish go unserved for three days was a check that stayed green over a page it
    was not really reaching. A page that silently misses the bar is the same
    failure with a different name."""
    text = payload.decode("utf-8")
    if WAY_BACK_MARK in text:
        return payload
    m = BODY_RE.search(text)
    if not m:
        raise ValueError(
            f"{rel}: no <body> tag, so the way-back bar has nowhere to go. Every page "
            "a card opens needs a link back to the network in its first screen; if this "
            "page is genuinely not one, it does not belong under src/site/.")
    lang = LANG_RE.search(text)
    bar = way_back(depth, lang.group(1) if lang else "")
    return (text[:m.end()] + "\n" + bar + text[m.end():]).encode("utf-8")


def render_node_pages(outdir: Path) -> None:
    """Substitute each node's living entries into its page.

    A card's URL is burned into a chip and handed to a person. It can never
    change — so the page behind it is the only place depth can accumulate, and
    someone who taps the same card next month has to find something that was not
    there before. That makes "add an entry" the most common edit this repo will
    ever take, and it must stay a JSON edit: no new page, no new URL, no
    template surgery.

    Same reason the feed on the landing page is substituted at build time rather
    than fetched: the page ships no JavaScript for content, so it works with
    scripting off, on a bad connection, in a hotel, on someone's mother's phone.

    Spanish leads and English follows because of who holds these cards.
    """
    # SWEEP FROM THE PROMISE, NOT FROM THE DATA. The loop below starts at
    # entries.json, so it can only ever reach a page that already has a living
    # half. The failure runs the other way and the loop is structurally blind to
    # it: a page carrying the marker with NO entries.json beside it is not
    # visited, nothing raises, and the build exits 0. That is not hypothetical —
    # manis, aurea, bloom and moku shipped exactly that way, each printing
    # "tap the card again in a month and there should be something on this page
    # that is not on it today" directly above an empty socket, with the .entry
    # CSS already in the page. The whole living half was wired and never plugged
    # in, for cards that are already in people's hands.
    #
    # The `if not blocks` guard below looks like it covers this and does not: it
    # fires on an entries.json that renders to nothing, which is the FILLED case
    # failing. An author who writes the promise and forgets the data trips no
    # guard at all. So the check has to key on the thing the reader was promised
    # — the marker in the markup — rather than on the file that fulfils it.
    unfilled = [
        p.relative_to(SITE)
        for p in sorted(SITE.rglob("index.html"))
        if ENTRY_MARKER in p.read_text() and not (p.parent / "entries.json").is_file()
    ]
    if unfilled:
        raise SystemExit(
            "FAIL: " + str(len(unfilled)) + " page(s) promise a living half and ship an "
            "empty one: " + ", ".join(str(p) for p in unfilled) + ".\n"
            "FAIL:   Each of these contains " + ENTRY_MARKER + " with no entries.json "
            "beside it, so the reader is told the page will have something new on it "
            "and it never will.\n"
            "FAIL:   FIX: write src/site/<node>/entries.json — {\"node\": \"<id>\", "
            "\"entries\": [{\"date\": \"YYYY-MM\", \"en\": \"title\", \"body_en\": \"...\"}]}, "
            "newest first. src/site/gt/entries.json is the worked example. "
            "If the page should NOT have a log, delete the marker instead."
        )

    # THE OTHER DIRECTION, AND THE ONE THAT SWEEPS GREEN THE WHOLE TIME IT IS WRONG.
    # The check above catches a page that PROMISES a living half and ships an empty
    # one. This one catches the page that never promised anything: a permanent chip
    # points at it, the destination sweep fetches it, it answers 200 on every run,
    # and it can never say anything it did not say the day the card was printed.
    #
    # A STATUS CODE CANNOT SEE THIS. cards.destinations records where each card
    # actually lands, and `verify_pages_artifact.mjs --network-registry` proves those
    # URLs resolve — which is exactly what tierra, raices, nica, sala and lab did, in
    # every sweep, while frozen. The sweep was not broken. It answers "does this URL
    # land" and was read as if it answered "is there any point tapping this card
    # again", which is a different question and the one the network is actually for.
    #
    # SAY WHICH CARDS THESE ARE, because the tempting sentence is wrong. Those five
    # are the EXAMPLE cards: their rows are qr rows, decoded from shipped design
    # files, and card_ledger.py records no physical instance of any of them. The
    # eleven cards that HAVE been printed and programmed are aurea, moku, bloom,
    # aurelia, zaria and the founder card — and every one of those already had its
    # living half. The gap ran the other way from the dramatic version: the pages
    # that could not change were the ones this repo hands a stranger as the worked
    # example of what a card is.
    #
    # SO THE RULE IS: if a card points at a page in THIS site, that page has to be
    # able to change. Off-site destinations live in other repos and are not on disk
    # here; they are counted and named below rather than silently passed, because a
    # check that quietly ignores most of its input reads exactly like one that
    # covered everything. The site root is excluded on purpose — it is the landing
    # page, rebuilt from network.json on every run, so it is never frozen.
    net_path = SITE / "network.json"
    if net_path.is_file():
        site_root = SITE_ROOT
        frozen, offsite, unbuilt, seen = [], set(), set(), set()
        for row in json.loads(net_path.read_text()).get("cards", {}).get("destinations", []):
            dest = row.get("resolves_to")
            if not dest:
                continue                       # a chip row with no recorded URL: nothing to check
            if not dest.startswith(site_root):
                offsite.add(dest)
                continue
            slug = dest[len(site_root):].strip("/")
            if not slug or slug in seen:
                continue                       # the landing page, or a second card to the same node
            seen.add(slug)
            page = SITE / slug / "index.html"
            if not page.is_file():
                unbuilt.add(slug)
            elif ENTRY_MARKER not in page.read_text():
                frozen.append(slug)
        if unbuilt:
            # THIS GATE COMPUTED THE ANSWER AND REFUSED TO FAIL ON IT. `unbuilt` was
            # filled three lines up and then used only to decorate the summary print
            # below, so a card destination with NO PAGE AT ALL was reported as a
            # parenthetical while a card destination with a page that cannot change was
            # a hard FAIL. The lesser fault stopped the build and the greater one did
            # not. Found by mutation: renaming src/site/kaze/ printed
            # "1 not built here: kaze" at exit 0.
            #
            # Off-site rows are already filtered above, so everything reaching here is a
            # path in THIS repo that a card points at and this build does not produce.
            raise SystemExit(
                "FAIL: " + str(len(unbuilt)) + " page(s) a printed card points at do not "
                "exist in this repo: " + ", ".join(sorted(unbuilt)) + ".\n"
                "FAIL:   A chip's URL is burned in. If the page is gone or renamed, every "
                "card carrying it scans to a 404 forever and no redirect can be added, "
                "because nothing in front of that URL is ours to change.\n"
                "FAIL:   FIX: restore src/site/<node>/index.html under its original name. "
                "If the page genuinely moved, the card is dead and its row belongs in "
                "cards.destinations with the new destination recorded and the old one "
                "written down as lost — never quietly repointed."
            )
        if frozen:
            raise SystemExit(
                "FAIL: " + str(len(frozen)) + " page(s) are the destination of a printed card "
                "and can never change: " + ", ".join(sorted(frozen)) + ".\n"
                "FAIL:   A chip's URL is burned in, so the page behind it is the only place "
                "anything new can ever appear. These pages carry no " + ENTRY_MARKER + ", so "
                "someone who taps the card next year finds exactly what they found today.\n"
                "FAIL:   FIX: add a log section with " + ENTRY_MARKER + " to src/site/<node>/"
                "index.html and an entries.json beside it. src/site/gt/ is the worked example.\n"
                "FAIL:   If a card really should point at something static, remove its row from "
                "cards.destinations — but then nothing sweeps that card at all."
            )
        print(f"  living-half gate: {len(seen)} card destination(s) in this site checked, "
              f"{len(offsite)} off-site skipped (other repos, not on disk here)"
              + (f", {len(unbuilt)} not built here: {', '.join(sorted(unbuilt))}" if unbuilt else ""))

    # THE DENSITY GATE HAS TO RUN HERE TOO, AND IT IS A SEPARATE CALL SITE ON
    # PURPOSE. check_entries() below measures curator_note / reason / summary on
    # the REGISTRY entries — the front page. These are node pages: a different
    # renderer, reading a different file, rendering a different set of fields.
    # Nothing connected them, so the fix that landed for the 2,165-character
    # front-page sentence protected the one surface the bug was FOUND on rather
    # than the class of surface it belongs to, and the same audit voice went
    # straight back into body_en. Measured the day this ran: 41 of 82 rendered
    # node strings breached these very limits, worst 828 characters in one
    # 72-word sentence on /gt/.
    #
    # This surface is the WORSE of the two to get wrong. The front page can be
    # relinked; a node page is what a printed chip points at, and a chip URL can
    # never change. The reader who lands here tapped a physical card, which is
    # the least patient arrival there is.
    #
    # Checked BEFORE the render loop, not inside it, because that loop writes
    # each page as it goes — a mid-loop raise would leave half the site built
    # from text this gate had already rejected.
    #
    # Only the four fields the loop below actually renders are measured: the
    # heading (es/en) and the body (body_es/body_en). Anything else in the file,
    # including any _-prefixed key, is where the dense version LIVES, verbatim.
    # That is the whole shape of the fix: nothing is deleted, it moves.
    #
    # SCOPED TO entries.json DELIBERATELY, AND NOT BECAUSE THE REST WAS MISSED.
    # The node pages' own static template prose is not measured here, and the
    # obvious next step — point these same limits at it — is the wrong one. An
    # independent read of all seven pages after this gate landed found 129
    # static paragraphs over 200 characters that would fail these limits, and
    # judged that prose the BEST writing on the site. gt's visitor-facing intro
    # is 650 characters and reads on one pass; "A ring you wear on your head,
    # folded from paper. Pull two opposite corners and the whole thing opens at
    # once." is four sentences and would be rejected here.
    #
    # THE LIMITS ARE A PROXY FOR READABILITY, NOT READABILITY, and the same read
    # caught the proxy failing in BOTH directions on one page: readable prose
    # this gate would reject, and gate-passing prose a stranger cannot follow
    # (zaria's third entry cleared 224 characters, 2 sentences and a 22-word
    # maximum while naming nothing anybody could picture — it had to be rewritten
    # a second time, by a human reading it, not by anything mechanical).
    #
    # So the gate is aimed where the proxy is known to hold: the living-half
    # entries, which are written by agents, on a cadence, into a field whose
    # audit voice has now twice drifted onto a public page. Authored template
    # prose is a person's voice and gets a person's review. Widening this to
    # cover it would trade a real failure it catches for a larger one it would
    # cause, which is how a gate stops being trusted.
    dense, dropped = [], []
    for entries_json in sorted(SITE.rglob("entries.json")):
        if not (entries_json.parent / "index.html").is_file():
            continue
        rel = entries_json.relative_to(SITE)
        for i, e in enumerate(json.loads(entries_json.read_text()).get("entries", [])):
            for field in ("es", "en", "body_es", "body_en"):
                why = too_dense(f"{rel}[{i}].{field}", e.get(field), NOTE_MAX, MAX_SENTENCES)
                if why:
                    dense.append(why)
            # THE RENDERER'S LANGUAGES ARE es AND en, AND SILENCE ABOUT THAT IS THE
            # DANGEROUS PART. Any key it does not know is dropped with no warning and
            # exit 0, so `body_tl` on /sala/ — whose own heading says "the words live
            # here, in all four", in Tagalog, Pangasinan and Kapampangan — would look
            # written, be committed, deploy green and appear nowhere. The four field
            # names are also hard-coded in the density check just above, so a language
            # that became renderable would skip the plain-language gate as well. An
            # underscore prefix is this file's documented "not for the page" marker and
            # stays exempt; a bare language-shaped key is somebody expecting to be read.
            stray = sorted(k for k in e
                           if not k.startswith("_") and k != "date"
                           and k not in ("es", "en", "body_es", "body_en")
                           and re.fullmatch(r"(?:body_)?[a-z]{2,3}(?:-[A-Za-z0-9]+)?", k))
            if stray:
                dropped.append(
                    f"{rel}[{i}] carries {', '.join(stray)}, which this renderer does not read: "
                    "it knows es and en only, so those words would be dropped silently and the "
                    "page would deploy green without them. Rename to _" + stray[0]
                    + " to keep them out of the page on purpose, or teach the renderer the "
                    "language — but teach the density check above it in the same edit")
    if dropped:
        # ITS OWN HEADER, because these two failures want opposite things from the writer
        # and one message cannot ask for both. Too-dense says "write less here"; dropped
        # says "these words reach nobody". Filing the second under the first printed
        # "1 string(s) ... too dense" above a line about a language, followed by a FIX
        # paragraph telling the writer to do what the check was objecting to.
        print("FAIL: " + str(len(dropped)) + " entry field(s) would be dropped without a "
              "word of warning:", file=sys.stderr)
        for why in dropped:
            print("FAIL:   " + why, file=sys.stderr)
        raise SystemExit(1)
    if dense:
        print("FAIL: " + str(len(dense)) + " string(s) a card holder reads are too dense "
              "for the page they land on:", file=sys.stderr)
        for why in dense:
            print("FAIL:   " + why, file=sys.stderr)
        print('FAIL:   FIX: move the long text into a "_audit_<field>" key on the same '
              'entry — this renderer only ever reads date, es, en, body_es and body_en, '
              'so every other key keeps its words and none of them reach the page — and '
              'leave ONE plain sentence in the field itself. Nothing is deleted; it moves.',
              file=sys.stderr)
        raise SystemExit(1)

    for entries_json in sorted(SITE.rglob("entries.json")):
        page = entries_json.parent / "index.html"
        if not page.is_file():
            continue
        data = json.loads(entries_json.read_text())
        rel = page.relative_to(SITE)
        built = outdir / rel
        html = built.read_text()

        blocks = []
        for e in data.get("entries", []):
            # THE LEADING LANGUAGE TAKES THE PRIMARY PARAGRAPH, and it is not always
            # Spanish. `.entry .en` is the SECONDARY style on every page that has it:
            # smaller and set in the muted colour, because on /gt/ English is the
            # translation running under a Spanish entry. Emitting body_en into that
            # class unconditionally is right there and wrong everywhere else — on an
            # English-only page it would render the entry's ONLY text as faded fine
            # print, while `.entry p`, the full-size ink style, went unused. The
            # heading one line up already degrades correctly ("es" or "en"); the body
            # is the half that did not, and nothing catches it because the page still
            # builds, still validates, and just quietly looks like a footnote.
            # WHICH LANGUAGE LEADS IS THE PAGE'S DECISION, AND THE PAGE ALREADY STATES
            # IT. This was `body_es or body_en` — Spanish wins wherever it exists — and
            # the comment above it says "the leading language ... is not always Spanish",
            # which was true only because no page had ever supplied both on an English
            # page. /tierra/ is that page. Its own template comment says "Spanish leads
            # in the entries and English runs underneath, which is the same order the
            # card's own words use", and the second half is FALSE: on tierra-back.png the
            # English line is the large dark ink and the Spanish runs under it, muted and
            # smaller — the same order the four .dicho blocks on the page use. So the old
            # hard-coding would have made the growing half of that card contradict the
            # card, and an agent trusting the comment would have shipped it.
            #
            # `<html lang>` is the page saying which language it is in, in the one place a
            # browser reads. Deriving from it changes nothing anywhere today (/gt/ and
            # /nica/ declare "es" and still lead in Spanish; the eleven English-only
            # nodes have no body_es to reorder) and it makes the one case that was
            # inexpressible expressible, without a new field for a page to disagree with.
            page_lang = "es" if re.search(r'<html lang="es', html) else "en"
            other = "en" if page_lang == "es" else "es"
            lead = e.get(f"body_{page_lang}") or e.get(f"body_{other}")
            second = e.get(f"body_{other}") if e.get(f"body_{page_lang}") else None
            second_lang = other if second else None
            # THE LEAD'S LANGUAGE IS DERIVED FROM THE FIELD THAT SUPPLIED IT, NEVER
            # INHERITED FROM THE PAGE. `lang="en"` one line down was hard-coded and
            # correct — `second` is only ever body_en — and that is exactly what made
            # the pair look symmetrical when only one half was tagged at all. The
            # heading and the lead carried no lang, so they inherited <html lang>,
            # which is right only where the page's declared language happens to equal
            # the language of the field that won. On /gt/ and /nica/ it does. On the
            # other 16 documents in this site it does not — they declare "en", and
            # every one of them ships zero inline lang attributes today.
            #
            # Reproduced before this existed: insert a body_es entry into
            # src/site/tierra/entries.json, build, and the page comes out carrying
            # lang="en" twice and lang="es" nowhere — the Spanish announced as
            # English, with its English translation the only correctly-tagged text on
            # the page. A screen reader then reads "Estamos con vos" with English
            # phonetics. Who holds any of these cards is not recorded anywhere in this
            # repo and is not assumed here; what IS on the page is the promise that the
            # words are there "in both, the way we actually say them", and a language a
            # device cannot identify is not there in the sense that promise means. No
            # gate could see it, because the page builds, validates and looks perfect.
            #
            # Heading and body are derived SEPARATELY. An entry may legitimately carry
            # a Spanish heading over an English body, and one flag for both would
            # mislabel whichever half disagreed.
            #
            # `class="en"` STAYS, AND IT NO LONGER MEANS ENGLISH. It is the secondary
            # style — smaller, muted — defined in all thirteen node pages' own CSS, so
            # renaming it is thirteen edits for a word. The name is historical and now
            # inaccurate on a page that leads in English; the `lang` beside it is
            # derived and is the authority on language. That split is this whole
            # commit's point: a class is a style hook only CSS reads, and tierra
            # already had four paragraphs whose class said "es" while nothing told the
            # reader's device anything at all.
            # AN ABSENT FIELD GETS NO LANGUAGE, because the first draft of this gave it
            # one. `page_lang if e.get(page_lang) else other` reads as a fallback and is
            # really an assertion: an entry carrying NEITHER heading field emitted
            # `<h3 lang="es"></h3>` — an empty heading labelled Spanish, on an English
            # page, by the same commit that removed a hard-coded language. Derive from the
            # field that supplied the text or say nothing.
            head = e.get(page_lang) or e.get(other)
            head_lang = page_lang if e.get(page_lang) else (other if e.get(other) else None)
            lead_lang = page_lang if e.get(f"body_{page_lang}") else other
            if not head and not lead:
                # AN EMPTY ENTRY IS WORSE THAN A MISSING ONE, and it shipped: a dated
                # <article> with an empty <h3> and no body passed the build and all of the
                # deploy gates, at the TOP of the log — the first thing a person who taps
                # the card reads. `if not blocks` below only catches a file with no entries
                # at all, so one blank entry among real ones was invisible to it.
                raise SystemExit(
                    f"FAIL: {rel} entry dated {e.get('date', '(no date)')!r} would render a "
                    "dated block with no heading and no body.\n"
                    "FAIL:   Someone tapping the card reads this first. Give it a heading and "
                    "a body, or remove the entry — an empty one is a worse answer than a "
                    "shorter log."
                )
            langs = "" if head_lang is None else f' lang="{head_lang}"'
            blocks.append(
                '  <article class="entry">\n'
                f'    <p class="when">{esc(e.get("date", ""))}</p>\n'
                f'    <h3{langs}>{esc(head)}</h3>\n'
                + (f'    <p lang="{lead_lang}">{esc(lead)}</p>\n' if lead else "")
                + (f'    <p class="en" lang="{second_lang}">{esc(second)}</p>\n' if second else "")
                + "  </article>"
            )
        out = html.replace(ENTRY_MARKER, "\n".join(blocks))
        out = out.replace("__COUNT__", str(len(data.get("entries", []))))

        if ENTRY_MARKER in out or "__COUNT__" in out:
            raise SystemExit(f"FAIL: {rel} kept a marker — substitution silently no-op'd")
        if not blocks:
            raise SystemExit(f"FAIL: {rel} rendered ZERO entries; the page would ship empty")

        built.write_text(out)
        (outdir / rel.parent / "entries.json").unlink(missing_ok=True)
        print(f"  node {rel.parent}: {len(blocks)} entries")


def assemble_studio(outdir: Path) -> int:
    """Copy the designer to /studio/, as the deploy does.

    The root is the landing page and the app lives one level down, because a card
    handed to a stranger has to open something that explains what they are holding.
    Dropping them into a card editor answers a question nobody asked.
    """
    dest = outdir / "studio"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(WEB.rglob("*")):
        if not f.is_file() or f.name == ".DS_Store":
            continue
        rel = f.relative_to(WEB)
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_bytes(f.read_bytes())
        n += 1

    # Sibling data files. src/profiles.json and src/supplies.json are OUTSIDE
    # src/web/ because the desktop server reads them from there, so publishing
    # src/web alone gives a site that 404s both and dies on boot.
    for name in ("profiles.json", "supplies.json"):
        (dest / name).write_bytes((SRC / name).read_bytes())
        n += 1

    # The only difference between the two builds: which backend answers.
    static = dest / "backend-static.js"
    if not static.is_file():
        print("FAIL: backend-static.js missing — the web build has no backend",
              file=sys.stderr)
        return 0
    static.replace(dest / "backend.js")

    # The session-token placeholder is desktop-only plumbing that server.py fills in
    # at serve time. Left on a static host it is dead text implying a security
    # mechanism the page does not have.
    idx = dest / "index.html"
    html_text = idx.read_text()
    if TOKEN not in html_text:
        print(f"FAIL: {TOKEN} missing from the studio index — either the placeholder "
              "was removed, or a REAL token was committed", file=sys.stderr)
        return 0
    idx.write_text("\n".join(l for l in html_text.split("\n") if TOKEN not in l))
    print(f"  studio/ {n} files")
    return n


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def item(entry: dict) -> str:
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in entry.get("tags", []))
    if entry.get("level"):
        tags = f'<span class="tag">{esc(entry["level"])}</span>' + tags
    if entry.get("license"):
        tags += f'<span class="tag">{esc(entry["license"])}</span>'
    # BOTH GRANTS, OR THE PAGE UNDERSTATES ONE. A project can ship its code under
    # one licence and its artwork or printed models under another, and the entry
    # schema already carries that as `license_design` — but only `license` was
    # ever rendered, so an entry holding MIT + CC-BY-NC-4.0 tagged as plain MIT on
    # the deployed page, with the NonCommercial half appearing nowhere in its
    # 28,603 bytes. The landing page is precisely the surface that tells a stranger
    # what they may reuse, and a renderer that shows one of two grants shows the
    # permissive one. Same failure as the NOTICE carve-out: attribution existed in
    # three places and reduced the grant by not one word.
    #   HONEST ABOUT COVERAGE: no listed entry carries this field today (the one
    # that did moved to `held` in the same commit, and held() renders no tags at
    # all), so this changes zero rendered bytes right now. It is here so the next
    # entry with a second grant cannot repeat it silently.
    if entry.get("license_design"):
        tags += f'<span class="tag">{esc(entry["license_design"])} (design)</span>'
    # THE CURATOR NOTE IS FOLDED AWAY, AND THE SUMMARY IS WHAT A STRANGER SEES.
    # Three people wished for this independently through the well on this very
    # page, within nine hours of each other, and they were right:
    #   "Collapse the long text strings on this page it makes it hard to read."
    #   "You should instead list the cards as a deck instead of long text read outs."
    #   "You hide the details above for each wish it better project it makes it
    #    harder to know what it is in laymen's terms. Are you doing a thought
    #    spill or helping market vibe cards"
    # Measured before the change: 16,754 characters of prose from network.json on
    # one page — KUNAI-001's curator_note alone is 730 words and GT-001's hold
    # reason is 1,017. The notes are the network's integrity record and deleting
    # them would be the level inflation this whole registry exists to prevent, so
    # NOTHING is removed: the audit prose moves behind a disclosure and the plain
    # summary becomes the thing you actually read.
    #
    # <details> and not a script: network.json's own _doc records that this page
    # ships no JavaScript, and that property is worth more than the widget. It
    # also means the fold works with JS off and is keyboard- and screen-reader-
    # operable for free.
    #
    # The card stops being one big <a>. An <a> may not contain a <details> — the
    # markup is invalid and a tap on the disclosure would navigate away instead of
    # opening it — so the anchor now wraps only the part that IS a link and the
    # fold is its sibling inside the bordered <article>. If you re-inline them,
    # you get a card whose "read more" silently sends the reader to another site.
    note = entry.get("curator_note")
    note_html = ""
    if note:
        note_html = (f'\n        <details class="fold"><summary>How this was verified</summary>'
                     f'<p class="note">{esc(note)}</p></details>')
    return f"""      <article class="entry">
        <a class="item" href="{esc(entry.get('url') or entry.get('repo'))}">
        <div class="top"><h3>{esc(entry.get('title'))}</h3><span class="id">{esc(entry.get('id'))}</span></div>
        <p>{esc(entry.get('summary'))}</p>
        <div class="tags">{tags}</div>
        </a>{note_html}
      </article>"""


def held(entry: dict) -> str:
    # Same fold, same reason (see item()). A held entry's `reason` is the longest
    # single string the page renders — GT-001's is 1,017 words — and it is also
    # the most load-bearing, because it is the record of WHY an agent may not
    # close this one on its own. So the lead sentence stays in the open and the
    # rest folds; the split is lossless, lead + rest reconstructs `reason`
    # exactly, and if no sentence break is found early the whole thing is shown
    # unfolded rather than guessed at.
    reason = entry.get("reason") or ""
    cut = reason.find(". ")
    if 0 < cut <= 240:
        lead, rest = reason[:cut + 1], reason[cut + 2:]
        tail = (f'<details class="fold"><summary>Why it is held</summary>'
                f'<span>{esc(rest)}</span></details>')
    else:
        lead, tail = reason, ""
    return (f'      <div class="held"><b>{esc(entry.get("title"))}</b>'
            f'<span>{esc(lead)}</span>{tail}</div>')


def human_date(iso: str) -> str:
    """"2026-08-14" -> "14 August 2026".

    A date is the one thing on the curated line a reader is actually meant to take
    away, and an ISO date is a machine's format: it reads as a version string, not
    as "recently". Written out, it answers the only question the line exists to
    answer — is this list maintained.

    The month names are a tuple rather than strftime("%B") because strftime is
    locale-dependent: the same commit would build "August" on a laptop and "agosto"
    on a machine with LC_TIME set, and the deploy is supposed to be reproducible
    from the same source. Anything that will not parse is passed through untouched —
    a malformed date is a reason to show the raw string, never to fail a build over
    a footer.
    """
    try:
        d = date.fromisoformat(str(iso))
    except (ValueError, TypeError):
        return str(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def sentences(text: str) -> list[str]:
    """Split on real sentence ends only.

    A naive text.split(".") reports "0.038 mm" as two sentences and "e.g." as two
    more, so a gate built on it fires on correct writing and gets switched off
    within the week. Three rules keep it honest:

      1. A terminator ends the string or is followed by whitespace. This alone is
         what protects every decimal in the corpus — the dot in 0.038 is followed
         by a digit, so it is never a candidate.
      2. What follows must LOOK like a new sentence: a capital letter, or an
         opening quote or bracket. This is the rule that fixes "Aug. 2026", which
         the first version of this function reported as two sentences — a digit
         does not start a sentence in this registry's prose, and a lowercase
         letter never does.
      3. The word in front of a full stop must not be an abbreviation: anything
         carrying an internal dot (e.g. / i.e. / U.S.), any single letter (an
         initial, and the tail of "e.g."), or one of the dotless ABBREVIATIONS.

    Where it is unsure it UNDER-splits — "end.)" keeps going and "..." does not
    terminate.

    UNDER-SPLITTING IS NOT FREE, and an earlier version of this docstring claimed
    it was: "an under-split can only over-report length". That is wrong, because
    the WORD CAP fires off the over-reported length. Two fine sentences merged
    into one chunk are measured as a single long sentence and refused. Measured
    against this file's own stated bar — VIBE-CARDS-001's 122-character note plus
    one short second sentence — the first version refused at "28 words; the limit
    is 25" on prose a reader sees as 19 words and 9.

    The cause was rule 2 asking for a capital letter. Two shapes this repo writes
    constantly do not have one: a sentence opening with a NUMBER ("36 strings over
    300 characters...") and one opening with a lowercase FILENAME ("nfcio.py does
    the chip half..."). CLAUDE.md contains both. Neither could ever end the
    sentence before it. `_starts_a_sentence` now admits them, and the decimals
    that shape might have broken — 0.038, 142.918 — are still safe, because the
    word-before-the-dot rule below already refuses to split a token with an
    internal dot.
    """
    s = (text or "").strip()
    out, start = [], 0
    for i, ch in enumerate(s):
        if ch not in ".!?":
            continue
        nxt = s[i + 1:i + 2]
        if nxt and not nxt.isspace():
            continue
        after = s[i + 1:].lstrip()
        if after and not _starts_a_sentence(after):
            continue
        if ch == ".":
            before = s[:i].split()
            word = before[-1].lower() if before else ""
            if len(word) == 1 or "." in word or word in ABBREVIATIONS:
                continue
        out.append(s[start:i + 1].strip())
        start = i + 1
    tail = s[start:].strip()
    if tail:
        out.append(tail)
    return out


def _starts_a_sentence(after: str) -> bool:
    """Could `after` be the beginning of a new sentence?

    A capital or an opening quote/bracket is the obvious yes. The two additions
    are the ones that cost a false refusal: a DIGIT ("36 strings over 300
    characters") and a lowercase token carrying an internal dot, which is how a
    filename looks ("nfcio.py does the chip half"). Both open sentences in this
    repo's own prose; neither is a capital letter.

    A bare lowercase word is still a continuation — "the card. and then" is one
    sentence with a typo, not two — so this stays narrow on purpose.
    """
    if not after:
        return False
    c = after[0]
    if c.isupper() or c in "\"'\u201c\u2018([":
        return True
    if c.isdigit():
        return True
    first = after.split()[0] if after.split() else ""
    return "." in first.rstrip(".,;:")


def too_dense(field: str, text: str, max_chars: int, max_sentences: int | None) -> str | None:
    """Say why `text` is unreadable to a stranger, or None if it is fine.

    Returns the MEASURED number beside the limit, because "too long" is not a
    thing anyone can act on and "4,129 characters against a limit of 300" is.
    """
    t = str(text or "").strip()
    if len(t) > max_chars:
        return f"{field} is {len(t):,} characters; the limit is {max_chars}"
    parts = sentences(t)
    if max_sentences is not None and len(parts) > max_sentences:
        return f"{field} is {len(parts)} sentences; the limit is {max_sentences}"
    for p in parts:
        n = len(p.split())
        if n > MAX_WORDS_PER_SENTENCE:
            clip = p if len(p) <= 70 else p[:70].rsplit(" ", 1)[0] + "…"
            return (f"{field} has a {n}-word sentence; the limit is "
                    f"{MAX_WORDS_PER_SENTENCE} — \"{clip}\"")
    return None


def build(outdir: Path) -> int:
    tpl = (SITE / "index.html").read_text()
    net = json.loads((SITE / "network.json").read_text())

    if MARKER not in tpl:
        print(f"FAIL: {MARKER} not found in src/site/index.html", file=sys.stderr)
        return 1

    listed = net.get("listed", [])

    # A promotion moves an entry from `held` to `listed`, and the two shapes are
    # NOT the same: held() renders only title and reason, item() dereferences nine
    # other fields and reads `reason` not at all. Move an entry across untouched and
    # the build still succeeds — it just emits href="" (which resolves to the current
    # document, so the card links back to this very page) and an empty <p>. A network
    # entry that points at the network is precisely the listing that means nothing,
    # and it was reproduced against this builder before this check existed.
    #
    # Fail here rather than in review. `url` is checked separately from the rest
    # because item() falls back to `repo`, so a missing url is only fatal when repo
    # is missing too — but a listing with neither has nowhere to send a reader.
    required = ("id", "title", "summary", "level", "license", "tags", "curator_note")
    for e in listed:
        missing = [k for k in required if not e.get(k)]
        if not (e.get("url") or e.get("repo")):
            missing.append("url-or-repo")
        if missing:
            print(f"FAIL: listed entry {e.get('id') or e.get('title') or '?'} is missing "
                  f"{', '.join(missing)} — a `held` entry cannot be promoted by moving it "
                  f"across; held() and item() render different fields, and `reason` is "
                  f"dropped on promotion (carry it into curator_note).", file=sys.stderr)
            return 1

    # PRESENT IS NOT THE SAME AS READABLE, so the check above is only half a gate.
    # On 2026-08-15 every field it demands was present and the page still opened
    # with a 2,173-character sentence, because nothing here had ever asked how LONG
    # a string was — only whether it existed.
    #
    # ONE FIELD WAS SERVING TWO AUDIENCES. `curator_note` is at once this network's
    # audit record, where 4,129 characters of method is exactly right, and the text
    # a stranger reads on a public page, where it is fatal. Nobody had to choose
    # which one they were writing for, so nobody did, and the audit voice won every
    # time — it is the one with something to prove.
    #
    # WHAT IS AND IS NOT CHECKED, and this boundary is the whole design: only
    # strings item() and held() actually put in front of a reader. `origin`,
    # `audit`, `note`, `panel` and anything starting with "_" are NOT measured,
    # because density there is CORRECT and a gate that squeezed the record out of
    # this file would be a far worse bug than the one it fixes. Nothing is deleted
    # to satisfy this check; the long text MOVES to a field the page does not
    # render, verbatim, every number and command intact — which is what
    # `curation.note` (31,214 characters, never rendered, never trimmed) already is.
    #
    # It refuses the build rather than truncating, for the reason the repo's own
    # history gives: a silent trim is how you ship a half sentence and never find
    # out. The author is here, at build time, with the text in front of them.
    dense = []
    for e in listed:
        name = e.get("id") or e.get("title") or "?"
        for why in (too_dense("summary", e.get("summary"), SUMMARY_MAX, None),
                    too_dense("curator_note", e.get("curator_note"), NOTE_MAX, MAX_SENTENCES)):
            if why:
                dense.append(f"{name}: {why}")
    for e in net.get("held", []):
        name = e.get("id") or e.get("title") or "?"
        why = too_dense("reason", e.get("reason"), NOTE_MAX, MAX_SENTENCES)
        if why:
            dense.append(f"{name} (held): {why}")
    if dense:
        # EVERY line carries the FAIL: prefix, and that is not cosmetic.
        # tools/verify_contribution.sh - the gate CLAUDE.md tells contributors to
        # clear before calling anything done - surfaces this builder's failures
        # with `... | grep -E "^FAIL" | head -3`. Indented detail lines are
        # filtered out by that grep, so the contributor saw only
        #   FAIL: 1 string(s) that a reader sees are too dense to publish:
        # with nothing naming the entry, the field or the number. That script's
        # own comment records the scar this repeats: "stopping the pipeline is
        # only half of it, the gate still has to name what stopped it."
        print("FAIL: " + str(len(dense)) + " string(s) that a reader sees are too dense "
              "to publish:", file=sys.stderr)
        for line in dense:
            print(f"FAIL:   - {line}", file=sys.stderr)
        print('FAIL:   FIX: move the long text into the entry\'s "audit" field — this builder '
              'never renders it, so the record keeps every word — and leave one plain '
              'sentence in its place. The bar is already in this file: VIBE-CARDS-001\'s '
              'curator_note, 122 characters, "Composes card PDFs against per-printer tray '
              'geometry and writes the NFC chip over PC/SC, from the Python standard '
              'library." It says what the thing IS. It does not describe how it was '
              'checked — that is what the audit field is for.', file=sys.stderr)
        return 1

    parts = [item(e) for e in listed]

    if not listed:
        parts.append('      <div class="empty">Nothing listed yet.</div>')

    for e in net.get("held", []):
        parts.append(held(e))

    cur = net.get("curation", {})
    if cur.get("last_run"):
        # `curation.panel` IS NEVER RENDERED, AND THE FIX IS HERE RATHER THAN IN THE
        # DATA. This line used to be ", ".join(cur["panel"]). panel is APPEND-ONLY:
        # five review passes each added a sentence describing their own method — 165,
        # 200, 491, 720 and 589 characters — and no pass ever replaced one, because
        # none of them was wrong to keep its record. Joined, that is a single
        # 2,173-character sentence, and it sits OUTSIDE the <details> fold item()
        # puts the per-entry notes behind, so it was both the longest string on the
        # page and the only one a reader could not click away. It was the first thing
        # the front page said.
        #
        # A FIELD THAT ONLY EVER GROWS CAN NEVER BE THE THING A READER SEES. That is
        # the whole lesson and it outlives this instance: there is no length at which
        # the join becomes acceptable, because the sixth pass appends a sixth
        # sentence and the page gets worse again — silently, with nobody having
        # written a bad line. Trimming panel would be the wrong fix twice over: it
        # destroys an audit record to solve a rendering problem, and it leaves the
        # join in place to re-break on the next honest append.
        #
        # So the record is untouched and the surface changes. The date, written out
        # for a person, answers the one question this line exists to answer — is
        # this list maintained. An OPTIONAL `curation.panel_note` may carry one
        # plain sentence about the review, and it is a SCALAR: a writer has to
        # replace it, which is exactly the property panel does not have.
        #
        # It is capped rather than refused (unlike the entry gate above) because a
        # footer must never be able to stop a deploy — and the cap prints, because a
        # silent truncation is how you ship half a sentence and never learn.
        note = str(cur.get("panel_note") or "").strip()
        if len(note) > SUMMARY_MAX:
            note = note[:SUMMARY_MAX].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
            print(f"  note: curation.panel_note capped to {SUMMARY_MAX} chars on the page; "
                  f"the full text stays in network.json")
        parts.append(f'      <p class="curated">Reviewed {esc(human_date(cur["last_run"]))}'
                     + (f' · {esc(note)}' if note else "") + "</p>")

    out = tpl.replace(MARKER, "\n".join(parts))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(out)

    # Everything else in src/site/ is an asset the page references, so it ships
    # with the page. Derived from the directory rather than a list here, because a
    # list is a thing that silently stops matching the tree — which is how an image
    # ends up 404ing on a deploy that went green.
    # rglob, not iterdir: iterdir sees FILES ONLY at the top level, so a
    # subdirectory of src/site — a project's own page, say — was silently not
    # copied and 404'd on the live host while the build printed success. Same
    # shape as every other missing-asset failure in this repo: correct locally,
    # dead on deploy, green either way.
    for f in sorted(SITE.rglob("*")):
        if not f.is_file() or f.name == ".DS_Store":
            continue
        rel = f.relative_to(SITE)
        if str(rel) in {"index.html", "network.json"}:
            continue
        (outdir / rel).parent.mkdir(parents=True, exist_ok=True)
        payload = f.read_bytes()
        # Every per-card page gets the way back, at the moment it is copied. See
        # WAY_BACK_MARK above for why it is here and not in seventeen files.
        # render_node_pages() rewrites 13 of these copies afterwards, replacing
        # only ENTRY_MARKER, so it carries the bar through untouched.
        if rel.name == "index.html":
            payload = add_way_back(payload, len(rel.parts) - 1, rel)
        (outdir / rel).write_bytes(payload)
        print(f"  asset {rel}")

    # The manifest, at the one path a machine can guess.
    #
    # This does NOT arrive via the loop above, and the reason is the joke: the
    # network's criterion 4 requires wish-it-better.json at the REPO root, which
    # is outside src/site/, so the rglob that ships every other asset has never
    # seen it. The rule that fixes the file's location is exactly what kept it off
    # the published surface. Measured before this line existed: 200 on the repo,
    # 404 on the site — for the seed project this network holds up as its example,
    # while a same-day 13-lane panel passed criterion 4 by reading the repo root.
    #
    # It has to be here and not only in the repo because `shape.site` is the URL
    # burned into a card's chip, permanently. An agent handed that card gets one
    # URL and nothing else. If the manifest is not under it, the project is
    # undiscoverable to the only visitor this network was built for.
    #
    # Copied from the git-tracked original rather than authored here, so the two
    # paths cannot drift: one source, one derived copy, never two truths. That is
    # the opposite of the archive's credits.json, which exists only at deploy time
    # and so has no history to check the live bytes against.
    manifest = REPO / "wish-it-better.json"
    if not manifest.is_file():
        print("FAIL: wish-it-better.json missing from the repo root — that is "
              "criterion 4 of this network's own registry", file=sys.stderr)
        return 1
    try:
        json.loads(manifest.read_text())
    except json.JSONDecodeError as e:
        # "parsing" is half of criterion 4. A manifest that 200s while failing to
        # parse is worse than one that 404s: a crawler scores the 200 as a pass.
        print(f"FAIL: wish-it-better.json does not parse ({e}) — publishing it "
              "would serve a 200 that no crawler can read", file=sys.stderr)
        return 1
    (outdir / "wish-it-better.json").write_bytes(manifest.read_bytes())
    print("  asset wish-it-better.json (from repo root)")

    # THE SAME MANIFEST, ONE PATH DOWN, FOR EVERY LISTED PROJECT WHOSE PAGE IS
    # INSIDE THIS SITE.
    #
    # The argument is the one four paragraphs up, unchanged, applied to the
    # candidates it was written about but never reached: `shape.site` is the URL
    # burned into a chip, an agent handed that card gets one URL and nothing
    # else, and if the manifest is not under it the project is undiscoverable to
    # the only visitor this network was built for. That reasoning was used to
    # justify copying ONE manifest to ONE path, and stopped there — so criterion
    # 4 was satisfiable only by a project whose url happened to be the artifact
    # root. Measured 2026-08-17 before this block existed:
    # /kaze/wish-it-better.json, /tierra/, /raices/, /nica/, /sala/, /lab/ all
    # 404, against /wish-it-better.json 200 on the same host in the same run.
    #
    # So the bar that reads as a curation policy — "wish-it-better.json at the
    # root, parsing, declaring a level it has earned" — was in practice a
    # property of the BUILDER: any in-site project failed it by construction, no
    # matter what it did. A rule nothing can satisfy is not a standard, it is an
    # accident that looks like one. AV-TOOLKIT-001 and COLLAGE-001 are already
    # listed off one shared containing repo, so the shared-root shape was always
    # admitted; only the manifest path was missing.
    #
    # DERIVED FROM THE REGISTRY ENTRY, NOT AUTHORED HERE, for the reason the
    # root copy states: one source, one derived copy, never two truths. The
    # registry entry is the source of truth for a listed project's identity, and
    # it is the same object the landing page renders and the gate reads — so a
    # manifest that disagreed with the badge could not be produced by this code
    # even deliberately. verify_pages_artifact.mjs compares declared level
    # against badged level and fails on drift; here they are one value read once.
    #
    # wish_channel points at the node page's own #wish anchor rather than the
    # landing page's, because §4's check is that the DECLARED page carries the
    # well marker, and every node page already ships one (the account-free wish
    # route asserted per page in check 8). Pointing them all at the root would
    # have passed the gate while sending a card holder's agent to the wrong page.
    in_site = [e for e in listed if str(e.get("url", "")).startswith(SITE_ROOT)]
    for e in in_site:
        slug = str(e["url"])[len(SITE_ROOT):].strip("/")
        if not slug:
            continue                       # the root entry: already written above
        node_dir = outdir / slug
        if not node_dir.is_dir():
            # A listed url with no page in the artifact is check 9's problem, not
            # this loop's; writing a manifest into a directory nothing serves
            # would invent a 200 for a page that 404s.
            print(f"  (no page for {slug}/ — manifest not emitted)")
            continue

        # A HAND-AUTHORED MANIFEST OUTRANKS A DERIVED ONE, AND THIS ARM IS WHY
        # THE FIRST DRAFT OF THIS BLOCK WAS WRONG.
        #
        # src/site/gt/wish-it-better.json is a tracked file. The asset rglob
        # above already ships it, and the first version of this loop then wrote
        # a derived manifest over the top of it in the same run — the two-truths
        # failure this block's own comment says it exists to avoid, committed by
        # the code that says it. Caught because the build printed the same path
        # twice, one line apart, which is the only reason it was visible at all.
        #
        # Derivation fills a GAP. It does not replace an author. A project that
        # wrote its own manifest may have earned a level, an origin or a spinoff
        # list richer than a registry entry can express, and the registry entry
        # is a summary of the project, not the reverse.
        src_manifest = SITE / slug / "wish-it-better.json"
        if src_manifest.is_file():
            try:
                authored = json.loads(src_manifest.read_text())
            except json.JSONDecodeError as ex:
                print(f"FAIL: {src_manifest} does not parse ({ex}) — it is published "
                      f"at {SITE_ROOT}{slug}/wish-it-better.json, where an unparseable "
                      f"200 scores as a pass", file=sys.stderr)
                return 1
            # The registry badges a level and the manifest declares one. The
            # network gate compares them, but only in its network-fetching mode;
            # a plain build would ship the drift and stay green until someone ran
            # the other mode. Cheap to catch here, at the moment both are in hand.
            if authored.get("level") != e.get("level"):
                print(f"FAIL: {slug} is badged {e.get('level')!r} in network.json but its "
                      f"own {src_manifest.relative_to(REPO)} declares {authored.get('level')!r} "
                      f"— the registry would claim a level the project does not",
                      file=sys.stderr)
                return 1
            print(f"  ({slug}/wish-it-better.json is authored — kept, not derived; "
                  f"level {authored.get('level')} agrees)")
            continue

        # THE LICENCE IS THE FIELD THIS DERIVATION MUST NOT OMIT, AND THE FIRST
        # DRAFT OMITTED IT.
        #
        # WISH_IT_BETTER.md §4 says a machine reads the manifest "and nothing
        # else — it does not traverse your page looking for a better route". So
        # a derived manifest carrying no `license` and a `repo` that falls
        # through to this repository publishes, at the card's own url, a
        # machine-readable record whose only licence pointer is an MIT repo.
        # For manis, aurea and bloom that repo grant is exactly what NOTICE
        # withdrew over thirty files — the same page-says-NC / licence-says-MIT
        # split NOTICE records as already committed once, rebuilt on a new
        # surface by the code that fixed it. Worse than the original, because
        # this one would be generated rather than typed, on every card added.
        #
        # So the entry's licence is carried, and a project with no licence to
        # carry does not get a manifest at all: a missing field would be read as
        # "the repo's", which is the failure above with fewer characters.
        # license_note follows GT-001's hand-authored file, the only prior
        # page-project manifest, which scopes its MIT against NOTICE in prose
        # rather than leaving a bare SPDX id to be over-read.
        if not e.get("license"):
            print(f"FAIL: listed entry {e.get('id')} has no license, so a derived manifest "
                  f"at {SITE_ROOT}{slug}/wish-it-better.json would name only the repo — "
                  f"which a machine reads as this project's grant", file=sys.stderr)
            return 1

        # The page and the registry each state a licence. They are two surfaces
        # describing the same card, which is precisely the shape that produced
        # every entry in NOTICE, so they are compared here rather than trusted
        # to agree. replication is read at the same time and carried into the
        # note, because "MIT" and "you may not reproduce the artwork" are both
        # true of some of these cards and a licence id alone cannot say so.
        page_license, replication = None, None
        page_src = SITE / slug / "index.html"
        if page_src.is_file():
            block = re.search(
                r'<script type="application/json" id="vc-card">(.*?)</script>',
                page_src.read_text(), re.S)
            if block:
                try:
                    vc = json.loads(block.group(1))
                    page_license, replication = vc.get("license"), vc.get("replication")
                except json.JSONDecodeError:
                    pass                   # check 8c fails on this at the artifact
        if page_license is not None and page_license != e.get("license"):
            print(f"FAIL: {slug} is badged {e.get('license')!r} in network.json but its page's "
                  f"#vc-card block declares {page_license!r} — the manifest published at that "
                  f"card's own url would contradict the card", file=sys.stderr)
            return 1

        note = (f"{e['license']} is what src/site/network.json badges for this project and what "
                f"this card's page declares in its #vc-card block. Artwork this project cannot "
                f"grant is named in NOTICE, served at {SITE_ROOT}NOTICE.txt — nothing in this "
                f"manifest enlarges what NOTICE withholds.")
        if replication:
            note += (f" This card declares replication {replication!r}: "
                     + {"open": "it may be reproduced, including commercially.",
                        "noncommercial": "it may be reproduced, but not sold.",
                        "withheld": "reproduction is not offered — ask the owner."}
                     .get(replication, "see the card's page."))

        derived = {
            "spec": "wish-it-better/1.0",
            "level": e.get("level"),
            "project": e.get("id"),
            "summary": e.get("summary"),
            "license": e.get("license"),
            "license_note": note,
            # The PAGE, with no fragment. The first draft appended "#wish", and
            # `grep -c 'id="wish"'` over every card page returns 0 — the anchor
            # does not exist anywhere in this site. §4's check is that the
            # declared page carries the wishing-well marker, which every card
            # page does; a fragment naming nothing would have passed that check
            # while sending a card holder's agent to the top of the page and
            # calling it the wish route.
            "wish_channel": f"{SITE_ROOT}{slug}/",
            "origin": e.get("origin"),
            "spinoffs": [],
            "evals": "docs/EVALS.md",
            # host_repo before repo, because a page-project inside this site
            # carries the FORMER on purpose. verify_pages_artifact.mjs joins
            # listed[] to the artifact-root manifest on `repo` and fails any
            # entry whose level differs — the root declares L1, every card here
            # is L0 — so GT-001, the one precedent, uses `host_repo` to stay out
            # of a comparison that does not apply to it. Reading only `repo`
            # here would have silently defaulted those entries to this repo.
            "repo": e.get("repo") or e.get("host_repo") or "https://github.com/mrdirno/vibe-cards",
            "_derived": ("Generated by tools/build_site.py from this project's entry in "
                         "src/site/network.json, which is the same object the landing page "
                         "renders and the registry gate reads. Edit the entry, not this file: "
                         "a hand-edit here would be a second truth, and the level below is "
                         "compared against the badge on the landing page."),
        }
        (node_dir / "wish-it-better.json").write_text(
            json.dumps(derived, indent=2, ensure_ascii=False) + "\n")
        print(f"  asset {slug}/wish-it-better.json (derived from listed[{e.get('id')}])")
    print(f"  per-node manifests: {len(in_site)} in-site listed entr"
          f"{'y' if len(in_site) == 1 else 'ies'}")

    # OFL.txt, for exactly the reason above, one class over — and it recurred the
    # same day the comment above was written, which is why it gets its own lines
    # instead of a wider glob.
    #
    # gt/index.html embeds two SIL OFL 1.1 typefaces as base64 data: URIs. That is
    # redistribution, and subsetting them to Latin is modification, so the licence
    # has to travel WITH the fonts. The in-page notice says "full text in OFL.txt
    # at the repo root" — and measured right after it shipped, OFL.txt was 200 on
    # the repo and 404 on the site, byte-identical in status to a nonsense control.
    # A card holder is not a repo visitor. They tap a chip, get one URL, and every
    # obligation this project owes them has to be reachable from under it.
    #
    # The trap worth naming: this obligation was CREATED by a privacy fix. Linking
    # the fonts made them someone else's to ship; self-hosting made them ours. A
    # change that moves a file across a licence boundary inherits the licence, and
    # nothing in the gate could see that, because the gate checks references that
    # resolve and this was a reference to a file no page links.
    ofl = REPO / "OFL.txt"
    if not ofl.is_file():
        print("FAIL: OFL.txt missing from the repo root while gt/index.html embeds "
              "OFL-licensed fonts — the licence must ship with the bytes",
              file=sys.stderr)
        return 1
    (outdir / "OFL.txt").write_bytes(ofl.read_bytes())
    print("  asset OFL.txt (from repo root)")

    # WISH_IT_BETTER.md, and at this point it stops being an anecdote and becomes
    # a class, so it is written down as one: the manifest above ships because a
    # card holder cannot go to the repo; OFL.txt ships because a card holder
    # cannot go to the repo; and the document that DEFINES this network shipped
    # nowhere at all. Measured against a same-host 404 control before this line
    # existed: /WISH_IT_BETTER.md 404, /wish-it-better.md 404, /spec/ 404, and the
    # artifact carried zero .md files of any name — while the landing page's "The
    # standard" link pointed at github.com/mrdirno/vibe-cards/blob/main/…, the one
    # surface this project does not control and cannot edit the day someone asks.
    #
    # The rule was already written, twice, and applied to everything except the
    # rule itself. A network whose entire membership test is "adopt this file"
    # owes the file at the URL it hands out — and the visitor that most needs it
    # is the one the comment above names: an agent handed a chip gets ONE URL and
    # nothing else. It could reach this network's manifest and its font licence
    # from under that URL, and could not reach the standard both of them serve.
    #
    # Shipped as the raw bytes copied from the git-tracked original — one source,
    # one derived copy, never two truths, exactly as the manifest is. What is NOT
    # claimed here: that a browser renders it nicely. That was written as an open
    # question and is now MEASURED, from this very deploy:
    #
    #   /WISH_IT_BETTER.md -> 200, content-type: text/markdown; charset=utf-8
    #   sha256 of the served bytes == sha256 of the repo file (control: 404)
    #
    # The first version of this note called it "the first .md that has ever existed
    # on this host, which is why it could not be measured before". That was false
    # and it was a search failure, not a fact: one sibling probed
    # (nested-resonance-memory-archive) ships no .md, and "the two I tried are 404"
    # became "none exists". mrdirno.github.io/kunai-360/README.md answers 200 — a
    # project THIS REGISTRY LISTS, on the same host, all along. The measurement
    # below stands on its own; the excuse for not having taken it earlier does not.
    #
    # text/markdown is not a type browsers agree on — some render it as text, some
    # download it — and the reader this project actually has is a phone woken by a
    # chip, where a download is not a document. So the landing page's "The
    # standard" link deliberately still points at the rendered blob: the machine
    # half is closed (an agent handed only the card URL can now GET the standard
    # from under it, byte-identical), and the human half needs an HTML rendering,
    # not a repointed href. Repointing it on the strength of "probably renders"
    # would trade a working link for an unverified one.
    spec = REPO / "WISH_IT_BETTER.md"
    if not spec.is_file():
        print("FAIL: WISH_IT_BETTER.md missing from the repo root — L0's first "
              "clause is this file's presence and the registry lists this project "
              "at L1", file=sys.stderr)
        return 1
    (outdir / "WISH_IT_BETTER.md").write_bytes(spec.read_bytes())
    print("  asset WISH_IT_BETTER.md (from repo root)")

    # LICENSE and NOTICE, for the reason the OFL block above gives, applied to the
    # material that block does not cover. The fonts embedded in gt/index.html ship
    # their licence with their bytes because embedding is redistribution. The
    # GT-001 card artwork is served whole at /studio/templates/gt-*.jpg, and
    # LICENSE may not grant it either: it was commissioned from Meta AI by the
    # card's owner and is not this project's work. (Until 2026-08-15 that artwork
    # was ALSO embedded in gt/index.html, and this sentence said so; the page now
    # references those JPGs instead. The licence reasoning is untouched by that —
    # the bytes are still handed out from this host, which is the whole reason
    # NOTICE has to reach the SITE and not only the repo. What changed is 1.14 MB
    # a card holder was paying to receive the same picture twice.)
    # ("the one thing in this tree LICENSE may not grant" is what this sentence
    # said for one commit, with the fonts named four lines above it — the same
    # blanket reflex NOTICE itself had to be corrected for, in the same hour.)
    # NOTICE withholds it. A withholding that lives
    # only in the repo protects nobody at the surface where the bytes are actually
    # handed out, which is the identical failure the two blocks above fix.
    #
    # LICENSE ships beside it because NOTICE's first sentence is "LICENSE grants
    # MIT over this project": publishing the exception without the rule leaves a
    # reader on this host holding half a sentence. Measured before these lines:
    # /LICENSE 404 and /NOTICE 404 against a same-host control, while all four
    # gt-*.jpg answered 200.
    # Each ships TWICE, under two names, and that is not redundancy — it is the
    # only way to serve both readers on a host whose Content-Type we cannot set.
    # GitHub Pages types an extensionless file as application/octet-stream, which
    # every browser DOWNLOADS. Measured on this very site: /NOTICE and /LICENSE
    # came back application/octet-stream while /OFL.txt came back text/plain. So
    # the well-known extensionless path stays (a machine guesses /NOTICE, and
    # `curl` does not care what the type is), and a .txt twin exists for the human
    # who follows a link — because the whole force of a NOTICE beside an MIT
    # licence is DISCOVERY, and a file that downloads instead of opening is not
    # discovered. Both are written from ONE source: the tracked repo-root file,
    # never authored here, and verify_pages_artifact.mjs asserts every copy
    # byte-identical to it, so two names still means one truth.
    #
    # The same commit that added these refused to repoint the standard's link
    # because text/markdown might download. Shipping two files that certainly do,
    # and linking one of them, was that rule applied to someone else's file and
    # not to its author's own — which is the bug this paragraph exists to stop
    # recurring.
    for name, why in (("LICENSE", "the grant"), ("NOTICE", "what the grant excludes")):
        f = REPO / name
        if not f.is_file():
            print(f"FAIL: {name} missing from the repo root — the site redistributes "
                  f"third-party artwork and cannot publish it without {why}",
                  file=sys.stderr)
            return 1
        payload = f.read_bytes()
        (outdir / name).write_bytes(payload)
        (outdir / f"{name}.txt").write_bytes(payload)
        print(f"  asset {name} + {name}.txt (from repo root)")

    # A marker left in the output means the substitution silently no-op'd.
    if MARKER in out:
        print("FAIL: marker survived substitution", file=sys.stderr)
        return 1
    print(f"built {outdir/'index.html'}: {len(listed)} listed, {len(net.get('held', []))} held")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    landing_only = "--landing-only" in argv
    outdir = Path(args[0] if args else "_site")

    rc = build(outdir)
    # Stop on a failed build instead of carrying on. build() reports its refusals by
    # returning 1 and writing nothing, so every later step is operating on a file that
    # does not exist — render_node_pages() then dies on `out/gt/index.html` with a
    # FileNotFoundError traceback that buries the actual FAIL line above it. The exit
    # code came out right only because the crash happened to be non-zero; the diagnosis
    # did not. A gate that reports a failure has to also stop the pipeline.
    if rc:
        return rc
    render_node_pages(outdir)
    if landing_only:
        return rc
    return 0 if assemble_studio(outdir) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
