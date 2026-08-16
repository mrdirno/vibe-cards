#!/usr/bin/env python3
"""What physical cards exist, and which ones are gone.

    python3 tools/card_ledger.py --list
    python3 tools/card_ledger.py --record [--note "..."]      # the card on the reader
    python3 tools/card_ledger.py --retire --reason "..."      # the card on the reader
    python3 tools/card_ledger.py --retire --uid 04F2... --card-id AUREA-LATTICE-002 \
                                 --reason "misprint" [--title "..."]

Prints one JSON object on stdout. Exit 0 on ok, 1 on refusal.

WHY IT EXISTS. This project could design a card, print it, program it and publish
its page, and at no point did anything write down that the card EXISTED. There
was one tag UID in the whole repository and it was inside a prose evidence
string in network.json — an anecdote, not a record. So there was no way to ask
the two questions that come up the moment you have more than a handful of cards:
which chips are out there carrying which project, and which ones have been
pulled. A card that was shredded and a card that was never made looked exactly
the same, which is to say: invisible.

That matters more than an inventory usually would, because a card is a pointer
someone else is holding. If a URL has to move, the answer to "which cards do I
have to reprogram" is this file. If a card is destroyed, the answer to "is that
UID still out there" is this file. Neither question can be answered by the
repository, because the repository describes DESIGNS and a card is an INSTANCE.

THE DATA DOES NOT LIVE IN THE REPO, and that is on purpose. It is a list of
objects the owner physically possesses, so it sits beside my_supplies.json in
Application Support, exactly like the owner's reader and purchases do. The tool
is shared; the inventory is not. Do not move the contents into src/.

A RETIRED ROW IS NEVER DELETED. Deleting it would put the ledger back in the
state that made it necessary — unable to tell a destroyed card from one that was
never made. Retiring sets a status and a reason and keeps everything else.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUPPORT = Path.home() / "Library" / "Application Support" / "Card Studio"
LEDGER = SUPPORT / "cards.json"
AUDIT = SUPPORT / "cards_actions.log"
SPEC = "vibe-card-ledger/1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    if not LEDGER.exists():
        return {"spec": SPEC, "cards": []}
    try:
        d = json.loads(LEDGER.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(json.dumps(
            {"ok": False, "error": f"{LEDGER} is not valid JSON: {exc}"}))
    d.setdefault("cards", [])
    return d


def save(d: dict) -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    # Write beside and rename, so a crash mid-write cannot leave a truncated
    # ledger where a complete one used to be.
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, LEDGER)


def audit(line: str) -> None:
    try:
        SUPPORT.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a") as fh:
            fh.write(f"{now()}  {line}\n")
    except OSError:
        pass          # an audit failure must never block a real status move


def read_chip() -> dict:
    """Ask nfcio for whatever is on the reader. Never raises."""
    try:
        r = subprocess.run([sys.executable, str(REPO / "src" / "nfcio.py"), "read"],
                           capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"could not read the reader: {exc}"}


def find(cards: list, uid: str):
    for c in cards:
        if c.get("uid") == uid:
            return c
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="card_ledger.py",
                                 description="What physical cards exist, and which are gone.")
    ap.add_argument("--list", action="store_true", help="print every card on record")
    ap.add_argument("--record", action="store_true",
                    help="add or refresh the card currently on the reader")
    ap.add_argument("--retire", action="store_true", help="mark a card retired")
    ap.add_argument("--uid", help="act on this uid instead of the card on the reader")
    ap.add_argument("--card-id", help="which card it is, when the chip cannot say")
    ap.add_argument("--title")
    ap.add_argument("--note")
    ap.add_argument("--reason", help="why it was retired")
    a = ap.parse_args(argv)

    d = load()
    cards = d["cards"]

    if a.list or not (a.record or a.retire):
        live = [c for c in cards if c.get("status") == "live"]
        print(json.dumps({"ok": True, "path": str(LEDGER), "total": len(cards),
                          "live": len(live), "retired": len(cards) - len(live),
                          "cards": cards}, indent=1))
        return 0

    uid = (a.uid or "").upper() or None
    chip = {}
    if not uid:
        chip = read_chip()
        if not chip.get("ok"):
            print(json.dumps({"ok": False, "error": chip.get("error")
                              or "no card on the reader — put one on it, or pass --uid"}))
            return 1
        uid = chip.get("uid")
    if not uid:
        print(json.dumps({"ok": False, "error": "no uid"}))
        return 1

    row = find(cards, uid)

    if a.record:
        # The chip is the source of truth for what a card SAYS. A blank chip is
        # recordable — a card can be printed before it is programmed — but then
        # the identity has to be given, because nothing on the tag can supply it.
        ident = a.card_id or (chip.get("epitaph") or "|").split("|")[1:2]
        ident = a.card_id or (ident[0] if ident and ident[0] else None)
        if not ident:
            print(json.dumps({"ok": False, "uid": uid, "error":
                              "the chip carries no identity and none was given — "
                              "pass --card-id"}))
            return 1
        new = {
            "uid": uid,
            "card_id": ident,
            "title": a.title or (chip.get("epitaph") or "||").split("|")[2:3] or [None],
            "url": chip.get("url"),
            "chip": chip.get("chip"),
            "status": "live",
            "first_seen": (row or {}).get("first_seen") or now(),
            "updated": now(),
        }
        if isinstance(new["title"], list):
            new["title"] = new["title"][0] if new["title"] else None
        if a.note:
            new["note"] = a.note
        if row:
            row.update(new)
        else:
            cards.append(new)
        save(d)
        audit(f"record {uid} {ident}")
        print(json.dumps({"ok": True, "action": "record", "card": find(cards, uid)}, indent=1))
        return 0

    # --retire
    if not a.reason:
        print(json.dumps({"ok": False, "error": "--retire needs --reason"}))
        return 1
    if not row:
        # A card can be retired that was never recorded — this ledger did not
        # exist for most of the cards already printed. Recording it AS retired
        # is more honest than refusing: the card was real either way.
        ident = a.card_id or (chip.get("epitaph") or "|").split("|")[1:2]
        ident = a.card_id or (ident[0] if ident and ident[0] else None)
        if not ident:
            print(json.dumps({"ok": False, "uid": uid, "error":
                              "not on record and the chip carries no identity — "
                              "pass --card-id"}))
            return 1
        row = {"uid": uid, "card_id": ident, "title": a.title,
               "first_seen": now(), "note": "added at retirement; predates this ledger"}
        cards.append(row)
    row["status"] = "retired"
    row["retired_reason"] = a.reason
    row["retired_at"] = now()
    row["updated"] = now()
    if a.title:
        row["title"] = a.title
    row["chip_blank_at_retirement"] = bool(chip.get("empty")) if chip else None
    save(d)
    audit(f"retire {uid} {row['card_id']} — {a.reason}")
    print(json.dumps({"ok": True, "action": "retire", "card": row}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
