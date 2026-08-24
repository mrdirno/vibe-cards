#!/usr/bin/env python3
"""Mint a founder game card — the replicable start of a founder's page on the network.

A founder card is a page inside src/site/<slug>/ that a founder's chip carries: a
hero title, a one-line tagline, a PLAY/BUILD link to the game as they build it, and
the same no-account Wish It Better box every other card on this network uses. It is
NOT a parametric deck card — it ships no generative-engine code and never touches the
OpenRouter key. The engine that makes a founder's sprites lives server-side behind a
founder-tier quota (FOUNDER_PLAYBOOK.md); only the output images ever reach the page.

    python3 tools/new_founder_card.py --slug pico-racer \\
        --title "Pico Racer" --founder "Ada" \\
        --game-url https://example.com/pico-racer \\
        --tagline "A one-thumb racer you build one corner at a time"

What it writes into src/site/<slug>/:
    index.html            the card page, house style copied from leviathan/
    entries.json          the living log (one opening entry), <!--ENTRIES--> beside it
    wish-it-better.json   L0 manifest, wish_channel = the page (no account)
    AUTHORSHIP.md         credits the founder

Then it PRINTS the network.json `listed` entry to add (paste it into the `listed`
array in src/site/network.json). Pass --register to append it in place instead — that
rewrites the whole file, so it is opt-in and refuses if the id is already listed.

Determinism: the card id and every derived string come from --slug alone; a re-run
with the same slug produces byte-identical files. The only clock touch is the log
entry's month (--date overrides it), and the tool refuses to overwrite an existing
folder anyway (pass --force), so a normal re-run regenerates nothing.

Standard library only. No Pillow, no network, no third-party import.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "src" / "site"
NETWORK = SITE / "network.json"

HOST_REPO = "https://github.com/mrdirno/vibe-cards"
PAGES_BASE = "https://mrdirno.github.io/vibe-cards"

# The wishing well: deliberate egress, insert-only under RLS. Copied verbatim from
# every card on this network so a founder's wishes land in the same vibe_card_wishes
# queue the operator already reads. The anon key is publishable by design — the table
# only accepts inserts, never reads.
WISH_URL = "https://fxjucjvfmklbpapretzr.supabase.co/rest/v1/vibe_card_wishes"
WISH_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ4anVjanZmbWtsYnBhcHJldHpyIiwicm9sZSI6"
            "ImFub24iLCJpYXQiOjE3Njg2OTQwNzUsImV4cCI6MjA4NDI3MDA3NX0."
            "UVQm1A4okSvej0UJLiKetiFuB4H9Prjv4rYcnGYVBYs")

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def die(msg: str) -> "NoReturn":
    print("FAIL: " + msg, file=sys.stderr)
    raise SystemExit(1)


def card_id(slug: str) -> str:
    """The slug, uppercased — e.g. pico-racer -> PICO-RACER. Derived from the slug
    alone so it is stable across re-runs. A founder card carries no numeric suffix,
    which keeps it out of the numbered deck's id space (LEVIATHAN-010, GESICA-013);
    the "Founder game" tag is what marks the lane."""
    return slug.upper()


def esc(s: str) -> str:
    """Minimal HTML entity escape for text dropped into the page."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def jesc(s: str) -> str:
    """Escape a string for safe inclusion inside a single-quoted JS string literal
    (the wish script's card_id)."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_index_html(slug, title, founder, tagline, game_url, cid, date):
    play_block = ""
    if game_url:
        play_block = (
            f'    <a class="btn" href="{esc(game_url)}">Play / build it</a>\n')
    # og:image is deliberately omitted: a founder card ships with no rendered face
    # yet, so pointing og:image at a card-front.png that does not exist would give a
    # broken preview. Add it when the founder has art.
    url = f"{PAGES_BASE}/{slug}/"
    lede = tagline or f"A game by {founder}, growing one build at a time."
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>{esc(title)}</title>
<meta name="description" content="{esc(lede)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(lede)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Vibe Cards">

<script type="application/json" id="vc-card">
{{
  "spec":        "vc1",
  "id":          "{cid}",
  "title":       "{jesc(title)}",
  "date":        "{date}",
  "license":     "MIT",
  "replication": "open",
  "tool":        "vibe-cards",
  "url":         "{url}",
  "provenance":  "A founder game card. The card is an address for a game its founder is building; the page links to the live game. No face is machine-generated on the card itself. Sprites, when the founder makes them, come from the server-side engine behind a founder-tier quota and are never generated on this page."
}}
</script>

<style>
/* Founder game card — house style copied verbatim from src/site/leviathan/ so a
   founder's page reads as one of the family. Dark faces, one accent, 44px tap
   targets (verify_mobile.mjs floors every tap target there). No generative-engine
   code lives here by law: the engine and the OpenRouter key stay server-side, and
   only output images ever reach a page. */
*{{box-sizing:border-box}}
:root{{--ink:#f2f2f4;--dim:#9aa0ad;--line:#2a2d36;--bg:#101219;--panel:#171a23;--pop:#e08aa8}}
html,body{{margin:0;padding:0}}
body{{background:var(--bg);color:var(--ink);
     font:17px/1.65 ui-rounded,"Avenir Next","Segoe UI",system-ui,sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:28px 20px 80px}}
h1{{font-size:clamp(30px,7vw,46px);line-height:1.08;margin:.2em 0 .15em;letter-spacing:-.02em}}
h2{{font-size:clamp(20px,4.2vw,26px);margin:2.2em 0 .4em}}
p{{margin:.7em 0}}
a{{color:var(--pop)}}
.kicker{{font:600 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.14em;
        text-transform:uppercase;color:var(--dim)}}
.lede{{font-size:clamp(18px,3.4vw,21px);color:var(--dim)}}
.btn{{display:inline-block;border:1px solid var(--pop);border-radius:999px;
     padding:14px 20px;min-height:44px;background:var(--pop);color:#101219;text-decoration:none;
     font:600 15px/1 ui-rounded,system-ui,sans-serif;margin:4px 6px 6px 0}}
.btn.ghost{{background:transparent;color:var(--pop)}}
.well{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px;margin:2.4em 0 0}}
.well textarea{{width:100%;min-height:84px;border:1px solid var(--line);border-radius:10px;
               padding:10px;font:inherit;font-size:16px;background:#0c0e14;color:var(--ink);resize:vertical}}
.send{{margin-top:9px;border:0;border-radius:999px;background:var(--pop);color:#101219;
      padding:14px 22px;min-height:44px;font:600 15px/1 ui-rounded,system-ui,sans-serif;cursor:pointer}}
.fine{{font-size:13px;color:var(--dim)}}
footer{{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);font-size:14px;color:var(--dim)}}
.wrap p a:not(.btn){{display:inline-block;padding:8px 0;margin:-8px 0}}
.wrap footer p a:not(.btn){{padding:11px 0;margin:0}}
</style>
</head>
<body>
<div class="wrap">

  <p class="kicker">Vibe Cards · Founder game</p>
  <h1>{esc(title)}</h1>
  <p class="lede">{esc(lede)}</p>
  <p>Made by {esc(founder)}. This card is the game's front door — the address stays the
     same while the game behind it grows.</p>

  <h2>Play it</h2>
  <p>The card links to the game. As {esc(founder)} builds it, the link points at the
     latest version — the card never has to be reprinted.</p>
  <p>
{play_block}    <a class="btn ghost" href="../">See the other cards</a>
  </p>

  <h2>The log</h2>
  <!--ENTRIES-->

  <section class="well">
    <h2 style="margin-top:0">Want it better?</h2>
    <p>What would you change about this game, or want to see in it next?</p>
    <label for="texto" style="position:absolute;left:-9999px">Your wish</label>
    <textarea id="texto" placeholder="I&#39;d love it if&hellip;"></textarea>
    <button class="send" id="mandar" type="button" data-wish-well>Send my wish</button>
    <p id="dicho" hidden style="font-weight:700"></p>
    <p class="fine">No account, no email, nothing to sign up for.</p>
  </section>

  <footer>
    <p><a href="../">All the cards</a> &middot;
       <a href="../studio/">Card Studio</a></p>
    <p>{cid} &middot; MIT</p>
  </footer>
</div>

<script>
/* The wishing well. Deliberate egress, insert-only under RLS. */
(function () {{
  var W = "{WISH_URL}",  // gate-ok: the wishing well, insert-only under RLS
      K = "{WISH_KEY}";
  var t = document.getElementById('texto'), b = document.getElementById('mandar'),
      s = document.getElementById('dicho');
  if (!t || !b) return;
  var L = b.textContent;
  b.addEventListener('click', function () {{
    var v = (t.value || '').trim();
    if (v.length < 2) {{ t.focus(); if (s) {{ s.textContent = "Type your wish first."; s.hidden = false; }} return; }}
    b.disabled = true; b.textContent = 'Sending…';
    fetch(W, {{ method: 'POST',                                                   // gate-ok: same well, see above
      headers: {{ 'apikey': K, 'Authorization': 'Bearer ' + K,
                 'Content-Type': 'application/json', 'Prefer': 'return=minimal' }},
      body: JSON.stringify({{ card_id: '{jesc(cid)}', wish: v, kind: 'improve',
                             lang: 'en', page_url: location.href }}) }})
    .then(function (r) {{ if (!r.ok) throw 0;
      t.value = ''; b.textContent = L; b.disabled = false;
      s.textContent = 'Got it. Thank you — we read every one.'; s.hidden = false; }})
    .catch(function () {{ b.textContent = L; b.disabled = false;
      s.textContent = "That didn't send. Try again."; s.hidden = false; }});
  }});
}})();
</script>
</body>
</html>
"""


def build_entries_json(cid, founder, date):
    return json.dumps({
        "node": cid,
        "entries": [
            {
                "date": date,
                "en": "The card is minted; the game begins",
                "body_en": (f"{founder} claimed this card as the front door to their "
                            "game. The address is fixed; the game behind it grows from "
                            "here."),
            }
        ],
    }, indent=2, ensure_ascii=False) + "\n"


def build_wish_json(cid, title, founder, tagline, game_url):
    summary = tagline or f"A founder game by {founder}."
    obj = {
        "spec": "wish-it-better/1.0",
        "project": cid,
        "summary": summary,
        "level": "L0",
        "license": "MIT",
        "wish_channel": f"{PAGES_BASE}/{card_slug_from_id(cid)}/",
        "origin": None,
        "host_repo": HOST_REPO,
        "founder": founder,
        "game": game_url or None,
    }
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build_authorship_md(cid, founder):
    return (f"# AUTHORSHIP — {cid}\n\n"
            "Recorded at intake from the package's #vc-card block.\n\n"
            f"- Commissioned by: {founder}\n"
            f"- Made by: {founder}\n"
            "- Generated with: hand-authored card page; game assets, if any, come from "
            "the server-side engine behind a founder-tier quota (never generated on the "
            "page)\n"
            "- Depicts a real person: no\n"
            f"- Intent: the front door to {founder}'s game on the Vibe Cards network\n")


def card_slug_from_id(cid: str) -> str:
    return cid.lower()


def listed_entry(slug, title, founder, tagline, game_url, cid):
    """The network.json `listed` entry — the row build_site.py renders onto the
    landing page. Matches the shape of the existing entries (id/title/summary/
    host_repo/url/level/license/tags/origin/curator_note/audit). curator_note is the
    plain sentence the page shows; audit carries the dense record the page does not."""
    summary = tagline or f"A game by {founder}, behind one permanent card address."
    game_line = (f" The card links to the game at {game_url}."
                 if game_url else " The game link is added once the founder has a URL.")
    return {
        "id": cid,
        "title": title,
        "summary": summary,
        "host_repo": HOST_REPO,
        "url": f"{PAGES_BASE}/{slug}/",
        "level": "L0",
        "license": "MIT",
        "tags": ["Founder game"],
        "origin": (f"Not a fork and not a repository of its own. /{slug}/ is a page "
                   "inside mrdirno/vibe-cards, published on that repo's Pages surface, "
                   "and its MIT is inherited from the parent repo."),
        "curator_note": summary,
        "audit": (f"Minted by tools/new_founder_card.py for founder {founder!r}."
                  + game_line +
                  " L0: a page at the url a card carries, with a no-account wish "
                  "channel and an MIT grant inherited from the repo. It ships no "
                  "generative-engine code — the founder's sprite generation runs "
                  "server-side behind a founder-tier quota (FOUNDER_PLAYBOOK.md) and "
                  "only output images ever reach the page."),
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description="Mint a founder game card into src/site/<slug>/.")
    ap.add_argument("--slug", required=True,
                    help="lowercase-hyphen folder name, e.g. pico-racer")
    ap.add_argument("--title", required=True, help='the game title, e.g. "Pico Racer"')
    ap.add_argument("--founder", required=True, help="who is building it (credited)")
    ap.add_argument("--game-url", default="", help="link the card points at (optional)")
    ap.add_argument("--tagline", default="", help="one line under the title (optional)")
    ap.add_argument("--date", default="",
                    help="log entry month, YYYY-MM (default: this month)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing folder")
    ap.add_argument("--register", action="store_true",
                    help="append the entry to network.json in place (rewrites the file)")
    args = ap.parse_args(argv)

    slug = args.slug.strip().lower()
    if not SLUG_RE.match(slug):
        die(f"--slug {args.slug!r} must be lowercase letters/digits joined by single "
            "hyphens, e.g. pico-racer")
    date = args.date or datetime.date.today().strftime("%Y-%m")
    if not re.match(r"^\d{4}-\d{2}$", date):
        die(f"--date {date!r} must be YYYY-MM")

    cid = card_id(slug)
    outdir = SITE / slug
    if outdir.exists() and not args.force:
        die(f"src/site/{slug}/ already exists — pass --force to overwrite. "
            "(The tool is idempotent by refusal, so a re-run never clobbers.)")

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(
        build_index_html(slug, args.title, args.founder, args.tagline,
                         args.game_url, cid, date))
    (outdir / "entries.json").write_text(
        build_entries_json(cid, args.founder, date))
    (outdir / "wish-it-better.json").write_text(
        build_wish_json(cid, args.title, args.founder, args.tagline, args.game_url))
    (outdir / "AUTHORSHIP.md").write_text(
        build_authorship_md(cid, args.founder))

    entry = listed_entry(slug, args.title, args.founder, args.tagline,
                         args.game_url, cid)

    print(f"OK  wrote src/site/{slug}/  (id {cid})")
    for f in ("index.html", "entries.json", "wish-it-better.json", "AUTHORSHIP.md"):
        print(f"      src/site/{slug}/{f}")

    if args.register:
        net = json.loads(NETWORK.read_text())
        if any(e.get("id") == cid for e in net.get("listed", [])):
            die(f"{cid} is already in network.json listed — nothing appended.")
        net.setdefault("listed", []).append(entry)
        # ensure_ascii=True matches the file's existing \u-escaped style; indent=1
        # matches its formatting. This rewrites the whole file — under a shared tree,
        # read `git diff` after and commit by pathspec.
        NETWORK.write_text(json.dumps(net, indent=1, ensure_ascii=True) + "\n")
        print(f"OK  appended {cid} to src/site/network.json listed[]  "
              f"({len(net['listed'])} listed)")
    else:
        print("\nAdd this to the `listed` array in src/site/network.json "
              "(or re-run with --register):\n")
        print(json.dumps(entry, indent=1, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
