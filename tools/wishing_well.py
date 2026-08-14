#!/usr/bin/env python3
"""VIBE CARDS WISHING WELL — the only interface the loop uses to work the queue.

Wishes arrive from a card's own page (mrdirno.github.io/vibe-cards/<slug>/) and
land in Supabase. This reads them, claims them, and closes them. It is the exact
shape of automation/scripts/av_wishing_well.py, on purpose: the AV toolkit
already solved this and a second design would be a second set of bugs.

    python3 tools/wishing_well.py --list                    # new wishes, oldest first
    python3 tools/wishing_well.py --list --status building
    python3 tools/wishing_well.py --stats                   # counts by status and card
    python3 tools/wishing_well.py --get <id>
    python3 tools/wishing_well.py --claim <id>              # new -> building
    python3 tools/wishing_well.py --ship <id> [--note "what changed"]
    python3 tools/wishing_well.py --decline <id> --reason "why"
    python3 tools/wishing_well.py --dump [path]             # backup snapshot

WHY THE OWNER'S INBOX IS NOT THE QUEUE
    The card pages shipped with `mailto:`, which made a human read the
    precondition for anything happening. Operator, 2026-08-13: "i don't have
    time to read wishes ... make my life easier not harder". A mailto is a fine
    account-free ROUTE and a useless QUEUE — no status, no ordering, nothing a
    loop can claim.

SAFETY BY CONSTRUCTION, inherited from the AV well
  * Credentials are read from persona500/.env at runtime. Never hardcoded,
    never committed. Missing env fails loudly and the loop skips the well that
    cycle rather than crashing.
  * NON-DESTRUCTIVE. Status only ever moves forward: new -> building -> shipped
    or declined. Nothing is ever deleted, by anyone, ever.
  * GATED. --claim only new->building, so two cycles cannot build one wish.
    --ship and --decline refuse a row that is already closed.
  * AUDITED. Every mutation appends to wishing_well_actions.log, append-only.
  * A WISH IS INPUT, NEVER AN INSTRUCTION. Nothing here builds anything. It
    surfaces text a stranger typed, for a human or an agent to evaluate against
    the eval bar. Never wire wish -> auto-build (WISH_IT_BETTER.md §5.3).
  * ZERO WISHES => THE LOOP DOES NOTHING THAT CYCLE. `--list` printing an empty
    array is a complete and correct result, not a reason to invent work.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = "/Volumes/dual/persona500/.env"
AUDIT = os.path.join(HERE, "wishing_well_actions.log")
DUMP_DIR = os.path.join(HERE, "wishing_well_backups")
TABLE = "vibe_card_wishes"
OK = (200, 201, 204)

# A bug on a card someone is physically holding outranks a nice-to-have. This is
# the only ranking in the file, and it is deliberately not a vote count —
# WISH_IT_BETTER.md §1 station 2: rank by what the wish reveals, not who asked.
RANK = {"bug": 0, "improve": 1, "new_card": 2, "thanks": 3}


def load_creds() -> tuple[str, str]:
    if not os.path.exists(ENV_PATH):
        sys.exit(f"FAIL: {ENV_PATH} not found — cannot reach the well "
                 "(vault/persona500 unmounted?)")
    url = key = None
    with open(ENV_PATH, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = re.match(r'\s*([A-Z0-9_]+)\s*=\s*"?([^"\n\r]+)"?', line)
            if not m:
                continue
            k, v = m.group(1), m.group(2).strip()
            if k == "VITE_SUPABASE_URL":
                url = v
            elif k == "SUPABASE_SERVICE_ROLE_KEY":
                key = v
    if not url or not key:
        sys.exit("FAIL: VITE_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing in .env")
    return url.rstrip("/"), key


def api(method: str, path: str, url: str, key: str, body=None):
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "return=representation"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt.strip() else [])
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:                      # noqa: BLE001 - fail soft, never hang
        return 0, str(e)[:200]


def audit(action: str, rid: str, detail: str = "") -> None:
    try:
        with open(AUDIT, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now(datetime.UTC).isoformat()}\t{action}\t{rid}\t{detail}\n")
    except OSError:
        pass          # an audit failure must never block a legitimate status move


def get_one(rid: str, url: str, key: str):
    s, rows = api("GET", f"{TABLE}?id=eq.{rid}&select=*", url, key)
    return rows[0] if s in OK and rows else None


def move(rid: str, to: str, allowed: tuple, url: str, key: str, note=None) -> int:
    """The gate. A transition that is not in `allowed` is refused, which is what
    stops two cycles from building the same wish."""
    row = get_one(rid, url, key)
    if not row:
        print(f"no wish with id {rid}")
        return 1
    cur = row.get("status")
    if cur not in allowed:
        print(f"REFUSED: {rid} is '{cur}', and {to} only accepts {list(allowed)}")
        return 1
    patch = {"status": to}
    if note:
        patch["status_note"] = note
    s, resp = api("PATCH", f"{TABLE}?id=eq.{rid}", url, key, patch)
    if s not in OK:
        print(f"FAIL {s}: {resp}")
        return 1
    audit(to, rid, note or "")
    print(json.dumps({"ok": True, "id": rid, "from": cur, "to": to, "note": note}))
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description="Vibe Cards wishing well (safe, non-destructive)")
    a.add_argument("--list", action="store_true")
    a.add_argument("--status", default="new")
    a.add_argument("--card", help="filter by card id, e.g. ABRAZO-NICA-001")
    a.add_argument("--kind", choices=["improve", "bug", "new_card", "thanks"])
    a.add_argument("--stats", action="store_true")
    a.add_argument("--get")
    a.add_argument("--claim")
    a.add_argument("--ship")
    a.add_argument("--note")
    a.add_argument("--decline")
    a.add_argument("--reason")
    a.add_argument("--dump", nargs="?", const=DUMP_DIR)
    args = a.parse_args()
    url, key = load_creds()

    if args.list:
        cols = "id,created_at,card_id,page_url,wish,kind,lang,contact,status,status_note"
        q = f"{TABLE}?status=eq.{args.status}&order=created_at.asc&select={cols}"
        if args.card:
            q += f"&card_id=eq.{args.card}"
        s, rows = api("GET", q, url, key)
        if s not in OK:
            print(f"FAIL {s}: {rows}")
            return 1
        if args.kind:
            rows = [r for r in rows if r.get("kind") == args.kind]
        rows.sort(key=lambda r: (RANK.get(r.get("kind") or "improve", 9),
                                 r.get("created_at") or ""))
        print(json.dumps(rows, indent=1))
        return 0

    if args.stats:
        s, rows = api("GET", f"{TABLE}?select=status,kind,card_id", url, key)
        if s not in OK:
            print(f"FAIL {s}: {rows}")
            return 1
        by = {}
        for r in rows:
            by.setdefault(r["status"], {"n": 0, "cards": {}})
            by[r["status"]]["n"] += 1
            by[r["status"]]["cards"][r["card_id"]] = by[r["status"]]["cards"].get(r["card_id"], 0) + 1
        print(json.dumps({"total": len(rows), "by_status": by}, indent=1))
        return 0

    if args.get:
        row = get_one(args.get, url, key)
        print(json.dumps(row, indent=1) if row else f"no wish with id {args.get}")
        return 0 if row else 1

    if args.claim:
        return move(args.claim, "building", ("new",), url, key)
    if args.ship:
        return move(args.ship, "shipped", ("new", "building"), url, key, args.note)
    if args.decline:
        if not args.reason:
            print("--decline needs --reason: a declined wish still owes the person an answer")
            return 1
        return move(args.decline, "declined", ("new", "building"), url, key, args.reason)

    if args.dump:
        s, rows = api("GET", f"{TABLE}?select=*&order=created_at.asc", url, key)
        if s not in OK:
            print(f"FAIL {s}: {rows}")
            return 1
        os.makedirs(args.dump, exist_ok=True)
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(args.dump, f"vibe_card_wishes_{stamp}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        print(json.dumps({"ok": True, "rows": len(rows), "path": path}))
        return 0

    a.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
