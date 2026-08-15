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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SITE = SRC / "site"
WEB = SRC / "web"
MARKER = "<!--FEED-->"
TOKEN = "__CS_SESSION_TOKEN__"


ENTRY_MARKER = "<!--ENTRIES-->"


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
            blocks.append(
                '  <article class="entry">\n'
                f'    <p class="when">{esc(e.get("date", ""))}</p>\n'
                f'    <h3>{esc(e.get("es") or e.get("en"))}</h3>\n'
                + (f'    <p>{esc(e["body_es"])}</p>\n' if e.get("body_es") else "")
                + (f'    <p class="en" lang="en">{esc(e["body_en"])}</p>\n' if e.get("body_en") else "")
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
    note = entry.get("curator_note")
    note_html = f'<p class="note">{esc(note)}</p>' if note else ""
    return f"""      <a class="item" href="{esc(entry.get('url') or entry.get('repo'))}">
        <div class="top"><h3>{esc(entry.get('title'))}</h3><span class="id">{esc(entry.get('id'))}</span></div>
        <p>{esc(entry.get('summary'))}</p>
        {note_html}
        <div class="tags">{tags}</div>
      </a>"""


def held(entry: dict) -> str:
    return (f'      <div class="held"><b>{esc(entry.get("title"))}</b>'
            f'<span>{esc(entry.get("reason"))}</span></div>')


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

    parts = [item(e) for e in listed]

    if not listed:
        parts.append('      <div class="empty">Nothing listed yet.</div>')

    for e in net.get("held", []):
        parts.append(held(e))

    cur = net.get("curation", {})
    if cur.get("last_run"):
        panel = ", ".join(cur.get("panel", []))
        parts.append(f'      <p class="curated">Reviewed {esc(cur["last_run"])}'
                     + (f' · {esc(panel)}' if panel else "") + "</p>")

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
        (outdir / rel).write_bytes(f.read_bytes())
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
    # GT-001 card artwork is embedded in that SAME file — and served again, whole,
    # at /studio/templates/gt-*.jpg — and LICENSE may not grant it either: it was
    # commissioned from Meta AI by the card's owner and is not this project's work.
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
