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
