#!/usr/bin/env python3
"""Adversarial check on the NFC routes — run it, do not read the guard and assume.

SECURITY.md's rule 4 is "prove it with a reproduction, not a reading", and its
corollary is the part people skip: **keep a legitimate-client control**. A guard
that returns 403 to everything passes an attack suite and ships a broken app. So
this script asserts both directions — every attack is refused AND the real client
still works — and fails if either half stops being true.

Why the NFC routes get their own harness rather than a line in the general one:
/api/nfc/write is the only route in this app whose effect leaves the machine.
Bytes go onto a physical tag that a person then carries away and hands to someone
else. There is no revocation, no redeploy, no patch — the card is just wrong,
forever, in someone's pocket. That asymmetry earns a dedicated, maintained test.

    python3 tools/verify_nfc_guard.py            # no reader needed
    python3 tools/verify_nfc_guard.py --verbose

Exit 0 = every case behaved. Exit 1 = a case regressed; the report names which.

NOTE ON HARDWARE: this never writes a tag, and that property is enforced rather
than hoped for. Every URL in HOSTILE_URLS fails `_SAFE_URL` — wrong scheme, a
space, a control character, or over-length — so `write_url` returns before any
APDU exists. A guard test asserts exactly that before the HTTP section runs.

That assertion exists because the first version of this file did not have it and
DID write to the operator's tag. It included `http://127.0.0.1:1/api/quit` as a
"hostile" case, expecting a refusal. But that string is a perfectly well-formed
http URL: it passed validation, reached the reader, and burned itself onto a live
NTAG215 — while the file's own docstring claimed no writes could happen. The
lesson generalises past this repo: **a test that asserts a refusal will perform
the action whenever the refusal is the thing that is broken.** Any suite whose
negative cases have side effects must make the side effect impossible, not
unlikely. Hence the pure-policy section below, which tests the loopback rule with
no server and no reader in the loop at all.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error  # gate-ok: drives the loopback server this file starts
import urllib.request  # gate-ok: drives the loopback server this file starts
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

VERBOSE = False


def log(*a):
    if VERBOSE:
        print("   ", *a)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(port, path, *, token=None, host=None, origin=None, body=None, method=None):
    """Returns (status, text). Never raises on an HTTP error status — a 403 IS
    the result we are testing for, so it must not arrive as an exception."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,  # gate-ok: 127.0.0.1 only, test harness
                                 method=method or ("POST" if data else "GET"))
    req.add_header("Host", host if host is not None else f"127.0.0.1:{port}")
    if token is not None:
        req.add_header("X-CS-Token", token)
    if origin is not None:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # gate-ok: loopback test harness
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # connection refused, timeout — a real failure
        return 0, f"{type(e).__name__}: {e}"


class Server:
    """Starts server.py on a port nobody else holds.

    The port is chosen by binding :0 and reading it back rather than picking a
    'probably free' number. An earlier version of this check hardcoded 8799,
    silently bound to a DIFFERENT process that already owned it, and reported
    that process's 404s as our guard working. Every assertion was against the
    wrong server. Never hardcode the port.
    """

    def __init__(self):
        self.port = free_port()
        self.proc = None
        self.fixture = None
        self.support = None

    def __enter__(self):
        env = dict(os.environ, CARD_STUDIO_PORT=str(self.port), CARD_STUDIO_NO_BROWSER="1")
        # Refused writes are journaled too. A random port isolates requests, not
        # the operator's settings or append-only chip history. Redirect every
        # support path before main() creates directories or serves a request.
        self.fixture = tempfile.TemporaryDirectory(prefix="card-studio-nfc-guard-")
        self.support = Path(self.fixture.name)
        launch = """
from pathlib import Path
import sys
import server  # noqa: E402 (local module, cwd is this repository's src)
server.SUPPORT = Path(sys.argv[1])
server.DESIGNS = server.SUPPORT / 'designs'
server.OUTPUT = server.SUPPORT / 'output'
server.SETTINGS_PATH = server.SUPPORT / 'settings.json'
server.CHIP_WRITES = server.SUPPORT / 'chip_writes.jsonl'
raise SystemExit(server.main())
"""
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-c", launch, str(self.support)], cwd=SRC, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            deadline = time.time() + 20
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise SystemExit("server.py exited on startup:\n" + (self.proc.stdout.read() or ""))
                status, _ = request(self.port, "/")
                if status:
                    return self
                time.sleep(0.25)
            raise SystemExit("server.py never became reachable")
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *exc):
        # Kill by the PID we own. `pkill -f "python3 server.py"` would match the
        # operator's real running app — and can match the killing shell itself.
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.proc and self.proc.stdout:
            self.proc.stdout.close()
        if self.fixture:
            self.fixture.cleanup()
        return False

    def token(self) -> str:
        status, html = request(self.port, "/")
        if status != 200:
            raise SystemExit(f"index did not load (status {status})")
        m = re.search(r'name="cs-token"[^>]*content="([^"]+)"', html)
        if not m:
            raise SystemExit("no cs-token meta in index.html — token plumbing changed")
        tok = m.group(1)
        if tok == "__CS_SESSION_TOKEN__":
            raise SystemExit("token placeholder was not substituted — the app would be unusable")
        return tok


NFC_ROUTES = ["/api/nfc/status", "/api/nfc/read"]

# Payloads that must never reach a tag. Each is (label, url, why-it-matters).
HOSTILE_URLS = [
    ("javascript: scheme", "javascript:alert(1)",
     "a tapped card that runs script in whatever opens it"),
    ("file: scheme", "file:///etc/passwd",
     "a card that points a reader app at the local filesystem"),
    ("data: scheme", "data:text/html,<script>alert(1)</script>",
     "inline payload smuggled onto a physical object"),
    ("no scheme", "example.com/x",
     "would silently become a relative reference when opened"),
    ("empty", "", "a card that resolves to nothing but reads as programmed"),
    ("whitespace only", "   ", "same, but survives a naive truthiness check"),
    ("embedded space", "https://a.co/ evil", "splits differently across parsers"),
    ("embedded newline", "https://a.co/\nX", "record smuggling"),
    ("embedded CR", "https://a.co/\rX", "record smuggling"),
    ("NUL byte", "https://a.co/\x00X", "truncates in C, not in Python"),
    ("over-length", "https://a.co/" + "x" * 2000,
     "past the 900-char validator bound and past any tag's capacity"),
]

# Loopback deliberately does NOT appear above. `http://127.0.0.1/x` is a valid
# http URL and writing one is allowed on purpose (see nfcio.classify_url — the
# same rule that would block it would block tagging your own 3D printer). It is
# WARNED at write and REFUSED at fetch, and both halves are checked in the pure
# policy section, which cannot touch hardware.

# (url, must_be_writable, must_be_fetchable, label)
POLICY_CASES = [
    ("https://example.com/projects/card", True, True, "ordinary public https"),
    ("http://example.com/x", True, True, "ordinary public http"),
    ("http://127.0.0.1:8080/api/quit", True, False, "loopback v4"),
    ("http://[::1]:8080/x", True, False, "loopback v6"),
    ("http://localhost:8080/x", True, False, "localhost by name"),
    ("http://192.168.1.50/", True, False, "private LAN (a real maker use case)"),
    ("http://10.0.0.5/", True, False, "private 10/8"),
    ("http://172.16.4.4/", True, False, "private 172.16/12"),
    ("http://169.254.169.254/latest/meta-data/", True, False, "cloud metadata endpoint"),
    ("http://0.0.0.0/", True, False, "unspecified"),
    ("javascript:alert(1)", False, False, "not http at all"),
    ("https://a.co/\nX", False, False, "control character"),
    # Userinfo spoofing. A human reads left-to-right and stops at the first
    # domain-shaped token; the authority is what follows the '@'. Refused, not
    # warned — the whole safety story is "you can read the URL before you burn it".
    ("https://example.com@evil.tld/c/K-1", False, False, "userinfo spoof (looks like ours)"),
    ("https://user:pw@evil.tld/x", False, False, "userinfo with password"),
    # Loopback spelled the ways inet_aton accepts but ipaddress.ip_address does not.
    # All three dial 127.0.0.1. A blocklist that parses more strictly than the
    # resolver is not a blocklist — these were all ALLOWED until an audit found them.
    ("http://127.1/x", True, False, "loopback short form 127.1"),
    ("http://2130706433/x", True, False, "loopback as a bare integer"),
    ("http://0x7f.0.0.1/x", True, False, "loopback in hex"),
    ("http://0177.0.0.1/x", True, False, "loopback in octal"),
]

# What a HOSTILE CARD can carry. NDEF prefix byte 0x00 means "payload is the whole
# URI", so a tag can encode any string at all — and anyone who can touch the card
# for ten seconds can put it there. decode_uri is a faithful decoder, so it will
# return these correctly; the job of read_card is to keep them out of a field named
# `url` that a UI would put in an href.
HOSTILE_CARD_PAYLOADS = [
    "javascript:alert(1)",
    "file:///etc/passwd",
    "data:text/html,<script>alert(1)</script>",
    "/tmp/",
    "../../etc/passwd",
    "https://example.com@evil.tld/c/K-1",
]

NON_STRINGS = [("integer", 123), ("null", None), ("list", ["https://a.co"]),
               ("object", {"href": "https://a.co"}), ("bool", True)]


def main() -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    failures = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if detail:
            log(detail)
        if not ok:
            failures.append(f"{name} — {detail}")

    # ---- 0. pure policy — no server, no reader, no possibility of a write ----
    sys.path.insert(0, str(SRC))
    import nfcio

    print("URL POLICY — pure, no hardware. write-side warns, fetch-side refuses:")
    for url, writable, fetchable, label in POLICY_CASES:
        w = nfcio.classify_url(url)
        f = nfcio.fetch_allowed(url)
        ok = (w["ok"] is writable) and (f["ok"] is fetchable)
        check(f"{label}: write={w['ok']} fetch={f['ok']}", ok,
              f"{url!r} expected write={writable} fetch={fetchable}; "
              f"error={w['error'] or f['error']}")
    # A URL that is writable-but-not-fetchable must SAY why, or the UI has nothing
    # honest to show and the user learns nothing from the refusal.
    quiet = [u for u, wr, fe, _ in POLICY_CASES
             if wr and not fe and not nfcio.classify_url(u)["warnings"]]
    check("every write-allowed-but-fetch-blocked url carries a warning", not quiet,
          f"silent: {quiet}")

    # ---- 0-. the two-record contract ----------------------------------------
    # This section exists because an audit found the two-record format documented in
    # docs/CARDS.md §2 had ZERO callers and ZERO tests — a published contract that
    # nothing exercised. All of it is pure: no reader, no server, no writes.
    print("TWO-RECORD FORMAT — pure, no hardware:")

    MSG = [
        ("https://example.com/c/RFID-CASE-001",
         "vc1|RFID-CASE-001|RFID Reader Enclosure|2026-08|MIT|vibe-cards"),
        ("https://a.co/c/X-1", "vc1|X-1|x|2026-08|MIT|vibe-cards"),
        ("https://www.example.com/c/LONG-1", "vc1|LONG-1|" + "t" * 90 + "|2026-08|MIT|vibe-cards"),
        ("https://example.com/c/NOEPI-1", None),          # URI record alone
    ]
    for url, epi in MSG:
        blob = nfcio.encode_message(url, epi)
        got = nfcio.decode_message(blob)
        ok = got["url"] == url and got["epitaph"] == epi
        check(f"round-trips {('url+epitaph' if epi else 'url only')}: {url[:34]}", ok,
              f"url={got['url']!r} epitaph={got['epitaph']!r} bytes={len(blob)}")

    # The byte budget printed in docs/CARDS.md §4 must be REPRODUCIBLE, because a
    # capacity table that drifts from the encoder is worse than no table — it is
    # relied on to decide whether a URL fits a 144-byte tag. An earlier draft of that
    # section published numbers copied from a different card's measurement.
    doc_bytes = len(nfcio.encode_message(MSG[0][0], MSG[0][1]))
    check(f"docs/CARDS.md byte budget still reads {doc_bytes} B", doc_bytes == 104,
          f"encoder says {doc_bytes}; the doc's table and this check must agree")

    # A truncated epitaph must NOT pass as a good read. This is the failure the
    # byte-comparison verify exists to catch: the URI record is first, so it survives
    # intact while the second record is cut off.
    full = nfcio.encode_message(MSG[0][0], MSG[0][1])
    truncated = full[:len(full) - 12]
    t = nfcio.decode_message(truncated)
    check("a truncated epitaph does not read back as complete",
          t["epitaph"] != MSG[0][1],
          f"truncated blob still yielded epitaph={t['epitaph']!r}")

    # Per-chip write ceilings. A single flat ceiling of 225 (NTAG216's) applied to a
    # physical NTAG213 leaves pages 40-44 — lock bytes, CFG0, CFG1, PWD, PACK —
    # writable. That is an irreversible brick, so the table is asserted here.
    expected = {0x0F: ("NTAG213", 39, 144), 0x11: ("NTAG215", 129, 496),
                0x13: ("NTAG216", 225, 872)}
    check("per-chip page ceilings match the NTAG datasheets",
          nfcio._VERSION_STORAGE == expected,
          f"got {nfcio._VERSION_STORAGE}")
    check("an unidentified tag falls back to the SMALLEST ceiling, not the largest",
          nfcio._UNIDENTIFIED_LAST_PAGE == 39 and nfcio._UNIDENTIFIED_CAPACITY == 144,
          f"fallback is page {nfcio._UNIDENTIFIED_LAST_PAGE}, {nfcio._UNIDENTIFIED_CAPACITY} B")

    # ---- 0a. reading a hostile card -----------------------------------------
    # The read path is hardened with the SAME policy object as the write path.
    # It was not, once: write refused javascript: while read handed it straight
    # back in `url`. Hardening one direction of a two-way boundary is the bug.
    print("\nHOSTILE CARD READ — a tag is untrusted input; these must never reach `url`:")

    def fake_tag(text, prefix=0x00):
        payload = bytes([prefix]) + text.encode()
        rec = bytes([0xD1, 0x01, len(payload), 0x55]) + payload
        return bytes([0x03, len(rec)]) + rec + b"\xFE"

    for text in HOSTILE_CARD_PAYLOADS:
        decoded = nfcio.decode_uri(fake_tag(text))
        # decode_uri SHOULD return it faithfully — it is a decoder, not a filter.
        faithful = decoded == text
        blocked = not nfcio.classify_url(decoded or "")["ok"]
        check(f"card carrying {text[:34]!r} is decoded but refused", faithful and blocked,
              f"decoded={decoded!r} blocked={blocked}")

    good = nfcio.decode_uri(fake_tag("example.com/projects/card", prefix=0x04))
    check("a legitimate card still decodes and passes",
          good == "https://example.com/projects/card" and nfcio.classify_url(good)["ok"],
          f"decoded={good!r}")

    # ---- 0b. the side-effect guard ------------------------------------------
    # Proves the HTTP section cannot write, instead of assuming it.
    leaky = [u for _, u, _ in HOSTILE_URLS if nfcio.classify_url(u)["ok"]]
    check("no HOSTILE_URLS case can reach the reader", not leaky,
          f"these would be WRITTEN to a live tag: {leaky}")
    if leaky:
        print("\nAborting before the HTTP section — a negative case would burn a real tag.")
        return 1

    with Server() as srv:
        port, tok = srv.port, srv.token()
        print(f"\nserver on 127.0.0.1:{port}  (pid {srv.proc.pid})\n")

        # ---- 1. legitimate client control -------------------------------
        # Runs FIRST and deliberately so. If this section fails, the attack
        # results below are meaningless: refusing everyone is not security.
        print("LEGITIMATE CLIENT — the control. These MUST succeed:")
        for route in NFC_ROUTES:
            status, text = request(port, route, token=tok)
            ok = status == 200
            payload = {}
            if ok:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    ok = False
            # A reader-less machine legitimately answers ok:false with an error
            # string. What we require is a 200 carrying a JSON object — proof the
            # route ran, not proof that hardware is attached.
            ok = ok and isinstance(payload, dict)
            check(f"{route} answers the real client", ok, f"status={status} body={text[:160]}")

        # ---- 2. the guard ------------------------------------------------
        print("\nGUARD — these MUST be refused (403):")
        attacks = [
            ("no token", dict(token=None)),
            ("wrong token", dict(token="x" * 43)),
            ("empty token", dict(token="")),
            ("DNS-rebind Host", dict(token=tok, host="evil.example.com")),
            ("Host with no port", dict(token=tok, host="127.0.0.1")),
            ("Host uppercase LOCALHOST", dict(token=tok, host=f"LOCALHOST:{port}")),
            ("Host trailing dot", dict(token=tok, host=f"127.0.0.1.:{port}")),
            ("cross-origin", dict(token=tok, origin="https://evil.example.com")),
            ("null origin", dict(token=tok, origin="null")),
        ]
        for label, kw in attacks:
            for route in NFC_ROUTES:
                status, text = request(port, route, **kw)
                check(f"{label} -> {route}", status == 403, f"status={status} body={text[:120]}")

        # CSRF on the write route is the one that would burn a physical tag.
        status, text = request(port, "/api/nfc/write", body={"url": "https://evil.example.com/"})
        check("un-tokened POST to /api/nfc/write", status == 403,
              f"status={status} body={text[:120]}")

        # ---- 3. write validation ----------------------------------------
        print("\nWRITE VALIDATION — authorized caller, hostile payloads. These MUST refuse:")
        for label, url, why in HOSTILE_URLS:
            status, text = request(port, "/api/nfc/write", token=tok, body={"url": url})
            refused = False
            try:
                refused = json.loads(text).get("ok") is False
            except json.JSONDecodeError:
                pass
            check(f"refuses {label}", status == 200 and refused,
                  f"({why}) status={status} body={text[:140]}")

        for label, value in NON_STRINGS:
            status, text = request(port, "/api/nfc/write", token=tok, body={"url": value})
            refused = status == 400 or (status == 200 and '"ok": false' in text.replace("'", '"'))
            check(f"refuses non-string url ({label})", refused,
                  f"status={status} body={text[:140]}")

        # A missing key must not become a write of the string "None".
        status, text = request(port, "/api/nfc/write", token=tok, body={})
        check("refuses missing url key", status in (200, 400) and '"ok": true' not in text,
              f"status={status} body={text[:140]}")

        # Exercise the real journaling path. An absent fixture file means the
        # launch override regressed; never silently fall back to the live ledger.
        journal = srv.support / "chip_writes.jsonl"
        recorded = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
        check("all refused HTTP writes stay in the temporary journal",
              len(recorded) == len(HOSTILE_URLS)
              and all(row.get("ok") is False and row.get("via") == "http" for row in recorded),
              f"fixture records={len(recorded)}, expected={len(HOSTILE_URLS)}")

        # ---- 4. no crash under concurrency -------------------------------
        # ThreadingHTTPServer means these genuinely overlap. The lock in nfcio
        # must serialise them; nothing may hang or 500.
        print("\nCONCURRENCY — overlapping reads must serialise, not crash:")
        import threading
        results = []
        threads = [threading.Thread(target=lambda: results.append(
            request(port, "/api/nfc/read", token=tok))) for _ in range(6)]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=40)
        elapsed = time.time() - t0
        ok = len(results) == 6 and all(s == 200 for s, _ in results)
        check(f"6 overlapping reads all answered in {elapsed:.1f}s", ok,
              f"statuses={[s for s, _ in results]}")

    check("temporary support fixture is removed after shutdown", not srv.support.exists())

    print()
    if failures:
        print(f"FAILED — {len(failures)} case(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All NFC guard cases behaved (attacks refused, real client served).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
