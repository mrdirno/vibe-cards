#!/usr/bin/env python3
"""Render the landing page from src/site/index.html + src/site/network.json.

    python3 tools/build_site.py [outdir]      # default: _site

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
SITE = REPO / "src" / "site"
MARKER = "<!--FEED-->"


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

    # A marker left in the output means the substitution silently no-op'd.
    if MARKER in out:
        print("FAIL: marker survived substitution", file=sys.stderr)
        return 1
    print(f"built {outdir/'index.html'}: {len(listed)} listed, {len(net.get('held', []))} held")
    return 0


if __name__ == "__main__":
    raise SystemExit(build(Path(sys.argv[1] if len(sys.argv) > 1 else "_site")))
