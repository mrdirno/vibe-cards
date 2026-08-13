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
    for f in sorted(SITE.iterdir()):
        if f.is_file() and f.name not in {"index.html", "network.json"}:
            (outdir / f.name).write_bytes(f.read_bytes())
            print(f"  asset {f.name}")

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
    if rc or landing_only:
        return rc
    return 0 if assemble_studio(outdir) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
