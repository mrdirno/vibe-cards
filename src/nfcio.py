"""NFC card read/write for Card Studio — the chip half of a printed card.

Named `nfcio` and not `nfc` on purpose: `nfcpy` installs a top-level module called
`nfc`, and because Python puts the script directory first on `sys.path` this file
would silently shadow it for anyone who has nfcpy installed. Shadowing a real
package to save four characters is how you get a bug report nobody can reproduce.

Talks to a PC/SC reader through **macOS's own PCSC.framework via ctypes**. That is
the whole dependency story: no pyscard, no libnfc, no install step. macOS ships a
CCID driver that already claims the ACR122U, so `SCardListReaders` finds it with
nothing installed. This keeps the repo's stdlib-only rule intact — see CLAUDE.md.

Scope: NFC Forum **Type 2** tags (NTAG213/215/216, MIFARE Ultralight). Those are
the tags a phone will actually read. MIFARE Classic is deliberately NOT written
here — Apple's Core NFC does not expose MIFARE Classic at all, so a Classic card
can never trigger the phone-tap flow this module exists to serve. Classic cards
still report their UID via read_card(), because a UID is enough for the reader-side
lookup; they just cannot carry a URL a phone will honour.

Everything degrades to a dict with `"ok": False` and a human-readable `"error"`.
No exception escapes into the request path.

RUN IT DIRECTLY — this module is a command-line tool as well as a library, and that
is the point rather than a convenience. Cards exist to be handled by agents and
scripts; the desktop app is a wrapper around this file, not the way in. Anything the
app can do, a command can do, with no server, no session token, and no window:

    python3 nfcio.py status
    python3 nfcio.py read
    python3 nfcio.py write --url https://example.com/c/X-1 --epitaph "vc1|X-1|…"
    python3 nfcio.py open
    python3 nfcio.py watch

Every command prints ONE JSON object to stdout and exits 0 when `ok` is true, 1 when
it is not — so `python3 nfcio.py read | jq -r .url` and `if ! python3 nfcio.py write …`
both behave. Diagnostics go to stderr and never pollute the parse.
"""

from __future__ import annotations

import contextlib
import ctypes
import re
import threading
from ctypes import (POINTER, Structure, byref, c_char_p, c_int32, c_ubyte,
                    c_uint32, c_void_p, create_string_buffer)

# --- PC/SC types -----------------------------------------------------------
# macOS wintypes.h defines LONG as int32_t and DWORD as uint32_t. On Linux
# pcsclite LONG is a native long, so a binding copied from a Linux example
# silently mis-sizes SCARDCONTEXT on a 64-bit Mac and every call returns
# garbage. These widths are macOS's, and this module is macOS-only today.
LONG = c_int32
DWORD = c_uint32
SCARDCONTEXT = LONG
SCARDHANDLE = LONG

PCSC_PATH = "/System/Library/Frameworks/PCSC.framework/PCSC"

SCARD_SCOPE_SYSTEM = 2
SCARD_SHARE_SHARED = 2
SCARD_PROTOCOL_ANY = 3          # T0 | T1
SCARD_LEAVE_CARD = 0
SCARD_S_SUCCESS = 0

# The only two failures a caller needs to tell apart from "broken".
SCARD_E_NO_SMARTCARD = 0x8010000C
SCARD_W_REMOVED_CARD = 0x80100069
SCARD_E_NO_READERS_AVAILABLE = 0x8010002E

_ERRORS = {
    0x8010000C: "no card on the reader",
    0x80100069: "card was removed mid-operation",
    0x8010002E: "no reader connected",
    0x8010000B: "reader is busy in another app",
    0x80100017: "reader was unplugged",
    0x80100066: "card is unresponsive — reseat it",
}


class _IOReq(Structure):
    _fields_ = [("dwProtocol", DWORD), ("cbPciLength", DWORD)]


_lib = None

# --- one reader, one caller at a time ---------------------------------------
# server.py runs a ThreadingHTTPServer, so two browser requests genuinely execute
# at the same time. There is exactly ONE reader and ONE tag on it, and a Type 2
# write is a SEQUENCE of 4-byte page writes: interleaving two of those sequences
# produces a card whose pages come from two different URLs, which still parses as
# valid NDEF and still resolves — to somewhere neither caller asked for. That is
# the silent-wrong-card failure this module exists to prevent, so the hardware is
# serialised here rather than at the HTTP layer: the constraint belongs to the
# reader, and any future caller (CLI, batch job) inherits the protection for free.
#
# The timeout matters as much as the lock. A wedged reader holding the lock
# forever would otherwise pile up threads until the server dies; instead the
# second caller gets a plain "reader is busy" it can show a human.
_HW_LOCK = threading.Lock()
_LOCK_TIMEOUT_S = 10.0      # longer than the slowest real write (~1.5 s at 496 B)
_STATUS_TIMEOUT_S = 0.25    # a poll must never queue behind a write


@contextlib.contextmanager
def _exclusive(timeout: float):
    """Yield True when the reader is ours, False when someone else holds it.
    Never raises, never leaks the lock on an exception in the body."""
    got = _HW_LOCK.acquire(timeout=timeout)
    try:
        yield got
    finally:
        if got:
            _HW_LOCK.release()


def _pcsc():
    """Load PCSC.framework once. Returns None when unavailable rather than
    raising, so a machine with no smartcard stack just reports 'unavailable'
    instead of taking the whole app down at import time."""
    global _lib
    if _lib is not None:
        return _lib or None
    try:
        lib = ctypes.CDLL(PCSC_PATH)
    except OSError:
        _lib = False
        return None
    sigs = [
        ("SCardEstablishContext", [DWORD, c_void_p, c_void_p, POINTER(SCARDCONTEXT)]),
        ("SCardReleaseContext", [SCARDCONTEXT]),
        ("SCardListReaders", [SCARDCONTEXT, c_char_p, c_char_p, POINTER(DWORD)]),
        ("SCardConnect", [SCARDCONTEXT, c_char_p, DWORD, DWORD,
                          POINTER(SCARDHANDLE), POINTER(DWORD)]),
        ("SCardDisconnect", [SCARDHANDLE, DWORD]),
        ("SCardTransmit", [SCARDHANDLE, POINTER(_IOReq), POINTER(c_ubyte), DWORD,
                           POINTER(_IOReq), POINTER(c_ubyte), POINTER(DWORD)]),
    ]
    for name, argtypes in sigs:
        fn = getattr(lib, name)
        fn.argtypes = argtypes
        fn.restype = LONG
    _lib = lib
    return lib


def _errname(rv: int) -> str:
    rv &= 0xFFFFFFFF
    return _ERRORS.get(rv, f"PC/SC error 0x{rv:08X}")


# --- chip identification ---------------------------------------------------
# The Capability Container at page 3 is the honest identifier. GET_VERSION
# (0x60) is richer but has to be tunnelled through a PN532 passthrough APDU
# that not every reader/tag pair answers, and a card that does not answer it
# is not a card we should refuse to write. CC byte 2 * 8 == usable NDEF bytes.
_CC_CHIPS = {
    0x12: ("NTAG213", 144),
    0x3E: ("NTAG215", 496),
    0x6D: ("NTAG216", 872),
    0x06: ("MIFARE Ultralight", 48),
}

# ATR bytes 13..14 carry the PC/SC standard card name for contactless tags.
# The last page that holds USER DATA on the largest tag we support (NTAG216).
# Above it sit the dynamic lock bytes, the OTP/config pages and the password
# pages — writing there is IRREVERSIBLE and can permanently brick a tag.
#
# This ceiling exists because the capacity check alone is not a bound: capacity
# is computed from the card's OWN capability-container byte, and a tag formatted
# by another app (or crafted) can claim `E1 10 FF 00` = 2040 bytes. Trusting that
# number walks the write loop straight through the data area and into the config
# pages. The card does not get a vote on where we are allowed to write.
_MAX_DATA_PAGE = 225

# Per-chip ceilings, keyed by the storage byte GET_VERSION returns.
#   name, last user-data page, usable NDEF bytes
#
# A SINGLE ceiling of 225 is NOT a safety check, and believing it was is the bug this
# table replaces. 225 is NTAG216's last user page. Apply it to a physical NTAG213 —
# whose user area ends at page 39 — and pages 40-44 are fair game: dynamic lock bytes,
# CFG0, CFG1, PWD, PACK. That is a bricked tag and a password nobody knows, from a
# ceiling that was supposed to prevent exactly this.
#
# It cannot be fixed from the capability container either, because the CC is the field
# an attacker (or a careless formatting app) forges: a real NTAG213 carrying an NTAG216
# CC asks for 872 bytes and every CC-derived check waves it through. The card cannot be
# the source of truth about how big the card is.
_VERSION_STORAGE = {
    0x0F: ("NTAG213", 39, 144),
    0x11: ("NTAG215", 129, 496),
    0x13: ("NTAG216", 225, 872),
}

# Used when the chip will not identify itself. The SMALLEST NTAG, deliberately: an
# unidentified tag gets the most cautious ceiling, so the failure mode is "your URL did
# not fit" instead of "your tag is permanently ruined." Under-writing is recoverable.
_UNIDENTIFIED_LAST_PAGE = 39
_UNIDENTIFIED_CAPACITY = 144

_ATR_TYPE2 = "0003"      # MIFARE Ultralight / NTAG — NFC Forum Type 2
_ATR_CLASSIC_1K = "0001"
_ATR_CLASSIC_4K = "0002"

URI_PREFIXES = [
    (0x04, "https://"), (0x03, "http://"), (0x02, "https://www."),
    (0x01, "http://www."), (0x05, "tel:"), (0x06, "mailto:"),
]


class _Session:
    """One connect/transmit/disconnect cycle. Context manager so a removed card
    can never leak a handle — PC/SC handles are a finite OS resource and a leaked
    one makes the *next* scan fail with a sharing violation, which reads as a
    hardware fault and is not."""

    def __init__(self):
        self.lib = _pcsc()
        self.ctx = SCARDCONTEXT()
        self.card = SCARDHANDLE()
        self.pci = None
        self.reader = None
        self.error = None
        self._ctx_ok = False
        self._card_ok = False

    def __enter__(self):
        if self.lib is None:
            self.error = "PC/SC is unavailable on this machine"
            return self
        rv = self.lib.SCardEstablishContext(SCARD_SCOPE_SYSTEM, None, None, byref(self.ctx))
        if rv != SCARD_S_SUCCESS:
            self.error = _errname(rv)
            return self
        self._ctx_ok = True

        n = DWORD(0)
        rv = self.lib.SCardListReaders(self.ctx, None, None, byref(n))
        if rv != SCARD_S_SUCCESS or not n.value:
            self.error = _errname(rv) if rv != SCARD_S_SUCCESS else "no reader connected"
            return self
        buf = create_string_buffer(n.value)
        if self.lib.SCardListReaders(self.ctx, None, buf, byref(n)) != SCARD_S_SUCCESS:
            self.error = "could not list readers"
            return self
        names = [r for r in buf.raw.split(b"\x00") if r]
        if not names:
            self.error = "no reader connected"
            return self
        self.reader = names[0].decode(errors="replace")

        proto = DWORD()
        rv = self.lib.SCardConnect(self.ctx, names[0], SCARD_SHARE_SHARED,
                                   SCARD_PROTOCOL_ANY, byref(self.card), byref(proto))
        if rv != SCARD_S_SUCCESS:
            self.error = _errname(rv)
            return self
        self._card_ok = True
        self.pci = _IOReq(proto.value, ctypes.sizeof(_IOReq))
        return self

    def __exit__(self, *exc):
        if self._card_ok:
            self.lib.SCardDisconnect(self.card, SCARD_LEAVE_CARD)
        if self._ctx_ok:
            self.lib.SCardReleaseContext(self.ctx)
        return False

    def apdu(self, data: list[int], expect: int = 258):
        """Send one APDU. Returns (body, sw) with sw as an int, or (None, None)."""
        if not self._card_ok:
            return None, None
        send = (c_ubyte * len(data))(*data)
        recv = (c_ubyte * expect)()
        rlen = DWORD(expect)
        rv = self.lib.SCardTransmit(self.card, byref(self.pci), send, len(data),
                                    None, recv, byref(rlen))
        if rv != SCARD_S_SUCCESS or rlen.value < 2:
            return None, None
        raw = bytes(recv[:rlen.value])
        return raw[:-2], (raw[-2] << 8) | raw[-1]

    # Type 2 READ returns exactly 16 bytes (4 pages). Asking for 32 makes the
    # ACR122U answer with an error rather than two reads — a length of 0x10 is
    # not a preference, it is the protocol.
    def read_pages(self, page: int):
        body, sw = self.apdu([0xFF, 0xB0, 0x00, page, 0x10])
        return body if sw == 0x9000 else None

    def write_page(self, page: int, four: bytes):
        if len(four) != 4:
            raise ValueError("a Type 2 page is exactly 4 bytes")
        _, sw = self.apdu([0xFF, 0xD6, 0x00, page, 0x04] + list(four))
        return sw == 0x9000

    def uid(self):
        body, sw = self.apdu([0xFF, 0xCA, 0x00, 0x00, 0x00])
        return body if sw == 0x9000 else None

    def identify(self):
        """Ask the CHIP what it is. Returns (name, last_user_page, capacity).

        GET_VERSION (0x60) is answered by the silicon, so unlike the capability
        container it cannot be forged by whatever last formatted the tag. It has to be
        tunnelled through the reader's direct-transmit pseudo-APDU
        (FF 00 00 00 Lc / D4 42 = InCommunicateThru), which not every reader and tag
        pair supports — hence the fallback rather than a hard requirement.

        When the chip will not answer, we return the SMALLEST NTAG's limits. That
        deliberately under-serves a big tag: a 496-byte NTAG215 that stays quiet gets
        treated as 144 bytes and a long URL is refused. That is the correct trade. The
        cost of guessing too small is a message the user can act on; the cost of
        guessing too large is silicon that can never be rewritten.
        """
        body, sw = self.apdu([0xFF, 0x00, 0x00, 0x00, 0x03, 0xD4, 0x42, 0x60])
        if sw == 0x9000 and body and len(body) >= 10 and body[0] == 0xD5:
            version = body[3:]
            if len(version) >= 7:
                known = _VERSION_STORAGE.get(version[6])
                if known:
                    return known
        return (None, _UNIDENTIFIED_LAST_PAGE, _UNIDENTIFIED_CAPACITY)


# --- NDEF ------------------------------------------------------------------

def encode_uri(url: str) -> bytes:
    """URL -> the exact bytes that live from page 4 onward.

    Layout is TLV(0x03) { NDEF record } TLV(0xFE). The prefix table is the whole
    reason a URL costs one byte instead of eight: 0x04 stands in for "https://".
    """
    # LONGEST matching prefix wins, and the comparison must be against the prefix
    # we have already chosen — not against the remainder. Comparing to the
    # remainder (the earlier form of this loop) silently kept the FIRST match:
    # URI_PREFIXES lists "https://" before "https://www.", so every www URL was
    # stored with the 8-byte prefix instead of the 12-byte one and carried four
    # redundant bytes. Round-trips stayed correct, which is exactly why it
    # survived — the only symptom is a URL that no longer fits an NTAG213's
    # 144 bytes when it should have. Track the chosen length explicitly.
    prefix_code, rest, chosen = 0x00, url, 0
    for code, text in URI_PREFIXES:
        if url.startswith(text) and len(text) > chosen:
            prefix_code, rest, chosen = code, url[len(text):], len(text)
    payload = bytes([prefix_code]) + rest.encode("utf-8")

    # Short-record form caps payload at 255. Our URLs are far below that, but a
    # silent truncation here would write a card that reads as valid and points
    # somewhere else, so the long form is implemented rather than assumed away.
    if len(payload) < 256:
        record = bytes([0xD1, 0x01, len(payload), 0x55]) + payload
    else:
        record = (bytes([0xC1, 0x01]) + len(payload).to_bytes(4, "big")
                  + bytes([0x55]) + payload)

    if len(record) < 255:
        tlv = bytes([0x03, len(record)]) + record + b"\xFE"
    else:
        tlv = bytes([0x03, 0xFF]) + len(record).to_bytes(2, "big") + record + b"\xFE"
    # Pad to a whole number of 4-byte pages; writes are page-granular.
    if len(tlv) % 4:
        tlv += b"\x00" * (4 - len(tlv) % 4)
    return tlv


def encode_message(url: str, epitaph: str | None = None) -> bytes:
    """Build the TLV for a card: a URI record, and optionally a Text epitaph.

    Why two records instead of one. The URI is the only record a phone acts on with
    no app installed, so it has to be there and it has to be first. But a URL is the
    part of a card most likely to stop meaning anything: usernames get freed,
    domains lapse, Pages paths move. The failure mode that matters is not a 404 —
    it is that someone else takes the name and the tap then **succeeds and lies**,
    serving their content from the address printed on our object. A fallback only
    fires on visible failure, and a lie is not a visible failure.

    So the second record carries identity in plaintext, on the card, where no server
    gets a vote:

        vc1|<id>|<title>|<yyyy-mm>|<license>|<tool>

    Pipe-delimited because it has to be readable by both a person squinting at a
    hex dump in 2035 and a `split('|')` — and because a JSON blob costs braces and
    quotes we do not have the bytes for. The last field is the TOOL, not the host,
    so the epitaph stays byte-identical when the pointer is re-pointed. There is no
    author field, deliberately: see the child-author rule. Attribution is local.

    Record headers: 0x91 = MB set, ME clear, short record, well-known type (first of
    several). 0x51 = ME set (last). A lone URI record uses 0xD1 = MB and ME both set,
    which is what encode_uri emits and why it stays a separate function.
    """
    uri = encode_uri(url)
    # encode_uri returns a whole TLV; we need just its record bytes to re-wrap.
    # Strip the 0x03/len header and the 0xFE terminator + padding it added.
    rec1 = _records_from_tlv(uri)
    if not rec1:
        raise ValueError("could not build the URI record")
    if not epitaph:
        return uri

    text = epitaph.encode("utf-8")
    lang = b"en"
    payload = bytes([len(lang)]) + lang + text     # status byte: UTF-8, lang len
    if len(payload) > 255:
        raise ValueError("epitaph too long for a short record")
    rec2 = bytes([0x51, 0x01, len(payload), 0x54]) + payload

    # rec1 currently has MB+ME (0xD1). It is no longer last, so clear ME.
    rec1 = bytes([(rec1[0] & ~0x40) & 0xFF]) + rec1[1:]
    body = rec1 + rec2

    if len(body) < 255:
        tlv = bytes([0x03, len(body)]) + body + b"\xFE"
    else:
        tlv = bytes([0x03, 0xFF]) + len(body).to_bytes(2, "big") + body + b"\xFE"
    if len(tlv) % 4:
        tlv += b"\x00" * (4 - len(tlv) % 4)
    return tlv


def _records_from_tlv(tlv: bytes) -> bytes:
    """Pull the record bytes back out of a TLV built by encode_uri."""
    if len(tlv) < 3 or tlv[0] != 0x03:
        return b""
    if tlv[1] == 0xFF:
        n, start = int.from_bytes(tlv[2:4], "big"), 4
    else:
        n, start = tlv[1], 2
    return tlv[start:start + n]


def decode_message(blob: bytes) -> dict:
    """Read both records back. Returns {"url": str|None, "epitaph": str|None}.

    The epitaph is returned RAW and is never treated as a URL or interpolated
    anywhere — it is a stranger's text on a rewritable tag, same as everything else
    a card carries.
    """
    out = {"url": decode_uri(blob), "epitaph": None}
    body = _records_from_tlv(blob)
    # Walk records looking for a Text record. Short-record form only, which is all
    # encode_message emits; anything else is left alone rather than half-parsed.
    i = 0
    while i + 4 <= len(body):
        hdr = body[i]
        short, type_len = bool(hdr & 0x10), body[i + 1]
        if not short:
            break
        plen = body[i + 2]
        tstart = i + 3
        pstart = tstart + type_len
        if pstart + plen > len(body):
            break
        if body[tstart:pstart] == b"T" and plen >= 1:
            payload = body[pstart:pstart + plen]
            lang_len = payload[0] & 0x3F
            try:
                out["epitaph"] = payload[1 + lang_len:].decode("utf-8")
            except UnicodeDecodeError:
                out["epitaph"] = None
        i = pstart + plen
        if hdr & 0x40:      # ME — last record
            break
    return out


def decode_uri(blob: bytes):
    """Inverse of encode_uri. Returns a URL, or None when the bytes do not carry
    a WHOLE one. Never returns a partial URL.

    Every slice below is length-checked before it is used, and that is the entire
    point of this function. Python slicing silently returns short — `b"abc"[0:99]`
    is `b"abc"`, not an error — so the natural way to write a parser here reads a
    declared length of 200, gets 90 bytes, and decodes them into a URL that looks
    completely legitimate. On a card that means `https://example.com/projects/kun`
    instead of `.../card`: it parses, it resolves, it goes somewhere else, and
    nothing anywhere reports a problem. A truncated read is indistinguishable from
    a short URL unless the lengths are checked, so they are checked, and any
    shortfall returns None rather than a guess.

    The 0xFE terminator is required for the same reason: it is the only evidence
    that the writer finished. A half-written card — interrupted mid-write, or
    written by something that crashed — has a valid TLV header, valid record
    bytes, and no terminator. Without this check it reads back as a good card.
    """
    if len(blob) < 4 or blob[0] != 0x03:
        return None

    # TLV length: 1-byte form, or the 3-byte 0xFF form for records >= 255 B.
    if blob[1] == 0xFF:
        if len(blob) < 4:
            return None
        rec_len, rec_start = int.from_bytes(blob[2:4], "big"), 4
    else:
        rec_len, rec_start = blob[1], 2
    rec_end = rec_start + rec_len
    if rec_len < 4 or len(blob) < rec_end:
        return None                      # declared longer than what we actually read
    rec = blob[rec_start:rec_end]

    # The terminator must be present at the position the TLV length points to.
    # Trailing padding to a page boundary is normal, so scan the remainder rather
    # than demanding it sit at exactly rec_end.
    if 0xFE not in blob[rec_end:rec_end + 4]:
        return None

    tnf, type_len = rec[0] & 0x07, rec[1]
    short = bool(rec[0] & 0x10)
    if tnf != 0x01:                      # well-known type
        return None
    if short:
        plen, off = rec[2], 3
    else:
        if len(rec) < 6:
            return None
        plen, off = int.from_bytes(rec[2:6], "big"), 6
    if len(rec) < off + type_len:
        return None
    if rec[off:off + type_len] != b"U":  # URI record
        return None

    start = off + type_len
    if plen < 1 or len(rec) < start + plen:
        return None                      # payload declared longer than the record
    payload = rec[start:start + plen]
    prefix = dict(URI_PREFIXES).get(payload[0], "")
    try:
        return prefix + payload[1:].decode("utf-8")
    except UnicodeDecodeError:
        # "replace" here would hand back a URL containing U+FFFD that still looks
        # printable in a UI. Undecodable bytes mean this is not our record.
        return None


# --- public API ------------------------------------------------------------

def status() -> dict:
    """Is there a reader, and is a card sitting on it? Cheap enough to poll."""
    lib = _pcsc()
    if lib is None:
        return {"ok": False, "available": False, "error": "PC/SC unavailable (macOS only)"}
    with _exclusive(_STATUS_TIMEOUT_S) as mine:
        if not mine:
            # A poll that blocks behind a 1.5 s write makes the status pill lie
            # about latency and stacks threads. "Busy" IS the honest answer.
            return {"ok": True, "available": True, "busy": True,
                    "card_present": None, "error": None}
        return _status_locked()


def _status_locked() -> dict:
    with _Session() as s:
        if s.reader is None:
            return {"ok": False, "available": True, "reader": None,
                    "card_present": False, "error": s.error or "no reader connected"}
        if s.error:
            # A reader with no card is the normal idle state, not a failure.
            idle = "no card" in s.error
            return {"ok": idle, "available": True, "reader": s.reader,
                    "card_present": False, "error": None if idle else s.error}
        return {"ok": True, "available": True, "reader": s.reader, "card_present": True}


def read_card() -> dict:
    """Everything we can learn from the card currently on the reader."""
    with _exclusive(_LOCK_TIMEOUT_S) as mine:
        if not mine:
            return {"ok": False, "busy": True,
                    "error": "reader is busy with another operation — try again"}
        return _read_card_locked()


def _read_card_locked() -> dict:
    with _Session() as s:
        if s.error:
            return {"ok": False, "error": s.error, "reader": s.reader}
        uid = s.uid()
        out = {
            "ok": True,
            "reader": s.reader,
            "uid": uid.hex().upper() if uid else None,
            "uid_bytes": len(uid) if uid else 0,
            "chip": None,
            "type2": False,
            "ndef_formatted": False,
            "capacity": None,
            "writable": False,
            "locked": False,
            "url": None,
        }
        head = s.read_pages(0)
        if head is None or len(head) < 16:
            # Type 2 page reads fail on MIFARE Classic, which needs sector auth.
            # That is an identification result, not an error.
            out["chip"] = "MIFARE Classic (or non-Type-2)"
            out["note"] = ("this chip cannot carry a URL that an iPhone will read — "
                           "Core NFC does not expose MIFARE Classic")
            return out

        out["type2"] = True
        cc = head[12:16]
        out["cc"] = cc.hex().upper()
        # Static lock bytes live at page 2 bytes 2-3. Non-zero means some pages
        # are permanently frozen; we surface it rather than discovering it as a
        # mysterious write failure halfway through a card.
        lock = head[10:12]
        out["locked"] = lock != b"\x00\x00"
        if cc[0] == 0xE1:
            out["ndef_formatted"] = True
            name, cap = _CC_CHIPS.get(cc[2], (None, cc[2] * 8))
            out["chip"] = name or f"Type 2 tag ({cap} B)"
            out["capacity"] = cap
            out["writable"] = (cc[3] & 0x0F) == 0 and not out["locked"]
        else:
            out["chip"] = "Type 2 tag (unformatted)"
            out["capacity"] = None
            out["writable"] = not out["locked"]

        # Walk the NDEF area only as far as the declared length.
        blob = s.read_pages(4)
        if blob:
            # Work out how many bytes the TLV claims, then keep reading until we
            # have them. The 0xFF form (records >= 255 B) must be handled here and
            # not skipped: excluding it meant a long URL was decoded from only the
            # first 16 bytes ever read, which is precisely the truncation
            # decode_uri now refuses — so the card reported "unreadable" when the
            # data was there and merely unfetched.
            need = 0
            if blob[0] == 0x03:
                if blob[1] == 0xFF and len(blob) >= 4:
                    need = 4 + int.from_bytes(blob[2:4], "big") + 1
                elif blob[1] not in (0x00, 0xFF):
                    need = 2 + blob[1] + 1
            page = 8
            while need and len(blob) < need and page <= _MAX_DATA_PAGE:
                more = s.read_pages(page)
                if not more:
                    break
                blob += more
                page += 4
            # WHAT A CARD SAYS IS UNTRUSTED INPUT. Ten seconds of physical access
            # is enough to rewrite a tag, so the bytes coming back are a stranger's
            # bytes, and decode_uri is a faithful decoder — not a validator. NDEF
            # prefix byte 0x00 means "no prefix, the payload is the whole URI", so
            # a tag can legitimately encode `javascript:alert(1)`, `file:///etc/passwd`
            # or a bare `/tmp/` path, and the decoder will correctly return them.
            #
            # Handing that back in a field called `url` is how it ends up in an
            # href. The write path already refuses these; the read path must too, or
            # the hardening is one-sided — which it was until this line existed.
            # Same policy object, both directions.
            # decode_message, not decode_uri — otherwise the epitaph is written by
            # write_message and then unreadable by every exposed call, which makes
            # "verify the card afterwards" impossible for anyone using this module.
            message = decode_message(blob)
            decoded = message["url"]
            out["epitaph"] = message["epitaph"]
            if message["epitaph"]:
                # Split for convenience, but keep the raw string: this is text from a
                # rewritable tag, so a caller must be able to see exactly what is on it
                # rather than only our interpretation of it.
                parts = message["epitaph"].split("|")
                if len(parts) >= 6 and parts[0].startswith("vc"):
                    out["card"] = {"spec": parts[0], "id": parts[1], "title": parts[2],
                                   "date": parts[3], "license": parts[4], "tool": parts[5]}
            out["empty"] = blob[0] == 0x03 and blob[1] == 0x00
            if decoded is None:
                out["url"] = None
            else:
                verdict = classify_url(decoded)
                if verdict["ok"]:
                    out["url"] = decoded
                    out["url_warnings"] = verdict["warnings"]
                else:
                    # Never in `url`. A caller that only knows about `url` sees
                    # nothing, which is the safe default; a caller that wants to
                    # show the human what is actually on the tag must ask for the
                    # raw field by name and handle it as text.
                    out["url"] = None
                    out["url_raw"] = decoded
                    out["url_unsafe"] = verdict["error"]
            # An NDEF area that declares content we could not fully read, or that
            # fails to decode, is reported rather than silently shown as blank.
            if out["url"] is None and not out["empty"] and blob[0] == 0x03:
                out["unreadable"] = True
                out["note"] = ("this tag carries an NDEF record this tool could not read "
                               "as a whole URL — it may be half-written; rewriting it is safe")
        return out


_SAFE_URL = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{1,900}$")


def _as_ip(host: str):
    """Parse a host as an IP address the way the NETWORK STACK will, not the way it
    looks. Returns an ip_address, or None if it is genuinely a name.

    `ipaddress.ip_address` only accepts the dotted-quad spelling, but connect() does
    not: `127.1`, `2130706433` and `0x7f.0.0.1` are all accepted by inet_aton and all
    reach 127.0.0.1. A loopback check built on ip_address alone therefore refuses
    `http://127.0.0.1/` and cheerfully allows `http://127.1/` — the same destination,
    spelled differently. Any blocklist that parses more strictly than the resolver is
    not a blocklist.

    inet_aton is used for exactly that reason: it is the same permissive legacy parser,
    so we classify what will actually be dialled.
    """
    import ipaddress
    import socket

    h = host.strip("[]")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    # IPv6 with a zone id, e.g. fe80::1%en0
    if "%" in h:
        try:
            return ipaddress.ip_address(h.split("%", 1)[0])
        except ValueError:
            pass
    try:
        return ipaddress.ip_address(socket.inet_aton(h))
    except (OSError, ValueError):
        return None


def classify_url(url: str) -> dict:
    """Decide what may be written, and what the human should be warned about.

    PURE — no hardware, no network, no DNS. That is deliberate: the policy is the
    part worth testing exhaustively, and a policy you can only exercise by burning
    a real tag is a policy that stops being tested. Everything hostile is refused
    here, before any APDU exists.

    Returns {"ok": bool, "error": str|None, "warnings": [str], "host": str|None}.

    On the loopback question — this is a judgement call, so the reasoning is here
    rather than in a commit message. A card carrying `http://127.0.0.1/...` is
    *meaningless to a phone*: the phone resolves its own loopback, not the Mac's.
    The tempting move is to refuse it outright. We do not, because the same check
    would refuse `http://192.168.1.50/` — and tagging the 3D printer on your desk
    is a real thing makers want a card for. Refusing a legitimate use to block a
    payload that is inert on the device that reads it is a bad trade.

    So loopback and private ranges are WARNED, not refused. The actual danger is
    not writing such a URL, it is *following* one: a card is an attacker-writable
    input, and anything that auto-fetches what a card points at turns a rewritten
    tag into SSRF against the local machine. That defence belongs at the fetch,
    where it is enforced separately and where it IS a hard refusal — see
    `fetch_allowed()`. Write-side: inform. Fetch-side: refuse.
    """
    import ipaddress
    import urllib.parse

    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "no url given", "warnings": [], "host": None}
    if not _SAFE_URL.match(url):
        # Refuse rather than escape: the byte string goes onto a physical card,
        # and a card is not something you can quietly re-deploy.
        return {"ok": False, "warnings": [], "host": None,
                "error": "url must be http(s) and free of spaces and control characters"}

    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError as exc:
        return {"ok": False, "error": f"unparseable url ({exc})", "warnings": [], "host": None}
    if not host:
        return {"ok": False, "error": "url has no host", "warnings": [], "host": None}

    # Userinfo is a pure spoofing vector here and has no legitimate use on a card,
    # so it is REFUSED rather than warned about.
    #
    #     https://example.com@attacker.example/c/CARD-001
    #
    # A person reads that left to right and stops at the first thing shaped like a
    # domain. The authority is everything after the '@', so it resolves to
    # attacker.example. On the open web this is an old trick; on a card it is worse,
    # because the entire safety story of this feature is "you can see the URL before
    # you burn it onto something permanent" — and this is the one construction where
    # looking at it tells you the wrong answer. Nothing legitimate needs credentials
    # in a URL that gets printed on a physical object and handed to a stranger.
    if parts.username is not None or parts.password is not None or "@" in (parts.netloc or ""):
        return {"ok": False, "warnings": [], "host": host,
                "error": ("url contains an '@' before the host. A reader would see "
                          f"the text before it, but this address actually resolves to "
                          f"'{host}'. Refusing — put credentials nowhere near a card.")}

    warnings = []
    # _as_ip, not ipaddress.ip_address — the same permissive parser fetch_allowed uses.
    # Using the strict one here made `http://127.1/` warn about nothing on the write
    # side while being refused on the fetch side: one host, two verdicts, because two
    # different parsers were asked. The policy has to speak with one voice.
    ip = _as_ip(host)
    if ip is None:
        if host in {"localhost", "localhost.localdomain"}:
            warnings.append("points at localhost — it will resolve on whatever device "
                            "reads the card, not on this Mac, so a phone will find nothing")
        elif host.endswith(".local"):
            warnings.append("points at an mDNS .local name — only resolves on this network")
    if ip is not None:
        if ip.is_loopback:
            warnings.append("points at loopback — it will resolve on whatever device reads "
                            "the card, not on this Mac, so a phone will find nothing")
        elif ip.is_link_local:
            warnings.append("points at a link-local address — it will not resolve off this machine")
        elif ip.is_private:
            warnings.append("points at a private address — only resolves on your local network, "
                            "not for anyone you hand the card to")

    return {"ok": True, "error": None, "warnings": warnings, "host": host}


# Hosts an automatic or semi-automatic fetch must never reach. This is the HARD
# refusal the write path deliberately does not make. A card's URL is untrusted
# input by construction — anyone with ten seconds of physical access can rewrite
# the tag — so following one has to be treated as following a stranger's link.
def fetch_allowed(url: str) -> dict:
    """May the app itself fetch this URL? Pure; no network, no DNS resolution.

    DNS rebinding is NOT solved here and cannot be: a public name can resolve to
    127.0.0.1 at connect time. Any caller that actually opens a socket must also
    check the address it landed on. This function rejects the literal cases, which
    is the necessary half, not the sufficient one.
    """
    import ipaddress
    import urllib.parse

    import socket

    verdict = classify_url(url)
    if not verdict["ok"]:
        return verdict
    host = verdict["host"]
    blocked = None
    try:
        ip = _as_ip(host)
        if ip is None:
            raise ValueError("not an address")
        if ip.is_loopback:
            blocked = "loopback"
        elif ip.is_link_local:
            blocked = "link-local (includes cloud metadata endpoints)"
        elif ip.is_private:
            blocked = "a private network address"
        elif ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            blocked = "a reserved address"
    except ValueError:
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            blocked = "localhost"
    if blocked:
        return {"ok": False, "host": host, "warnings": [],
                "error": f"refusing to fetch {blocked} on behalf of a card — a tag is "
                         f"rewritable by anyone who can touch it, so following it into "
                         f"this machine's own network is not something a card gets to ask for"}
    return {"ok": True, "error": None, "warnings": verdict["warnings"], "host": host}


def write_url(url: str, verify: bool = True) -> dict:
    """Write a URL to the card on the reader, then read it back and compare.

    Verification is not optional politeness. A partial page write leaves a card
    that looks programmed, scans as valid NDEF, and resolves to a truncated URL —
    the worst failure mode available, because it is silent and it is printed on
    a physical object you then hand to someone.
    """
    url = (url or "").strip()
    verdict = classify_url(url)
    if not verdict["ok"]:
        return {"ok": False, "error": verdict["error"]}
    warnings = verdict["warnings"]

    with _exclusive(_LOCK_TIMEOUT_S) as mine:
        if not mine:
            # Refusing is the ONLY safe answer here. A queued write would burn
            # pages onto whatever tag happens to be present when it finally runs,
            # which may not be the tag the user was looking at when they clicked.
            return {"ok": False, "busy": True,
                    "error": "reader is busy with another operation — nothing was written"}
        return _write_url_locked(url, verify, warnings)


def write_message(url: str, epitaph: str | None = None, verify: bool = True) -> dict:
    """Write a URI record plus an optional plaintext epitaph, and verify the WHOLE
    message byte-for-byte.

    The verification is deliberately stricter than write_url's. Checking only that
    `decode_uri(readback) == url` passes while the epitaph is silently truncated or
    missing — the URI record sits first, so it reads back perfectly even when the
    write died partway through the second record. That is the exact failure this
    two-record design exists to prevent: a card that looks programmed, resolves
    correctly today, and has lost the identity that was supposed to outlive the URL.
    So the comparison is over the full byte string, not over a parse of its first half.
    """
    url = (url or "").strip()
    verdict = classify_url(url)
    if not verdict["ok"]:
        return {"ok": False, "error": verdict["error"]}
    try:
        payload = encode_message(url, epitaph)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    with _exclusive(_LOCK_TIMEOUT_S) as mine:
        if not mine:
            return {"ok": False, "busy": True,
                    "error": "reader is busy with another operation — nothing was written"}
        return _write_payload_locked(payload, url, epitaph, verify, verdict["warnings"])


def _write_payload_locked(payload: bytes, url: str, epitaph, verify: bool,
                          warnings: list) -> dict:
    with _Session() as s:
        if s.error:
            return {"ok": False, "error": s.error, "reader": s.reader}
        head = s.read_pages(0)
        if head is None or len(head) < 16:
            return {"ok": False, "error": (
                "this card is not an NFC Forum Type 2 tag (likely MIFARE Classic). "
                "Phones cannot open a URL from it — use NTAG213/215/216.")}
        if head[10:12] != b"\x00\x00":
            return {"ok": False, "error": "card is locked read-only"}
        cc = head[12:16]
        if cc[0] != 0xE1:
            return {"ok": False, "error": (
                "card has no NDEF capability container and this tool will not guess "
                "one — the CC is one-time-programmable.")}
        # Ask the SILICON, then take the smaller of what it says and what the CC claims.
        # The chip's own answer is the ceiling; the CC can only ever make us more
        # cautious, never less.
        chip_name, last_user_page, chip_capacity = s.identify()
        cc_capacity = _CC_CHIPS.get(cc[2], (None, cc[2] * 8))[1]
        capacity = min(chip_capacity, cc_capacity) if cc_capacity else chip_capacity

        if capacity and len(payload) > capacity:
            hint = "" if chip_name else (
                " (this tag would not identify itself, so it is being treated as the "
                "smallest NTAG — a shorter url will fit)")
            return {"ok": False, "error":
                    f"message needs {len(payload)} B but this chip holds {capacity} B{hint}"}

        pages = [payload[i:i + 4] for i in range(0, len(payload), 4)]
        last_page = 4 + len(pages) - 1
        if last_page > last_user_page:
            return {"ok": False, "error":
                    f"refusing to write: this needs pages 4..{last_page}, but "
                    f"{chip_name or 'an unidentified tag'} ends its user data at page "
                    f"{last_user_page}. Above it are the lock and configuration pages, "
                    f"and writing those cannot be undone."}

        for i, four in enumerate(pages):
            if not s.write_page(4 + i, four):
                return {"ok": False, "written_pages": i,
                        "error": f"write failed at page {4 + i} ({i} of {len(pages)} "
                                 f"written) — card is half-programmed, rewrite it"}

        result = {"ok": True, "url": url, "epitaph": epitaph, "bytes": len(payload),
                  "pages": len(pages), "reader": s.reader, "warnings": warnings,
                  "uid": (s.uid() or b"").hex().upper() or None,
                  "free": (capacity - len(payload)) if capacity else None}
        if verify:
            back = b""
            page = 4
            while len(back) < len(payload) and page <= _MAX_DATA_PAGE:
                more = s.read_pages(page)
                if not more:
                    break
                back += more
                page += 4
            back = back[:len(payload)]
            result["verified"] = back == payload
            if not result["verified"]:
                result["ok"] = False
                got = decode_message(back)
                result["error"] = (
                    "verify failed — the card does not read back the bytes we wrote. "
                    f"url={got.get('url')!r} epitaph={got.get('epitaph')!r}")
        return result


def _write_url_locked(url: str, verify: bool, warnings: list) -> dict:
    payload = encode_uri(url)
    with _Session() as s:
        if s.error:
            return {"ok": False, "error": s.error, "reader": s.reader}
        head = s.read_pages(0)
        if head is None or len(head) < 16:
            return {"ok": False, "error": (
                "this card is not an NFC Forum Type 2 tag (likely MIFARE Classic). "
                "Phones cannot open a URL from it — use NTAG213/215/216.")}
        cc = head[12:16]
        if head[10:12] != b"\x00\x00":
            return {"ok": False, "error": "card is locked read-only"}

        # Same rule as _write_payload_locked: the chip's own GET_VERSION answer is the
        # ceiling, the CC can only lower it. Never the other way round.
        chip_name, last_user_page, chip_capacity = s.identify()
        if cc[0] == 0xE1:
            cc_capacity = _CC_CHIPS.get(cc[2], (None, cc[2] * 8))[1]
            capacity = min(chip_capacity, cc_capacity) if cc_capacity else chip_capacity
        else:
            capacity = None
        if cc[0] != 0xE1:
            # A factory-blank Type 2 tag has no CC. Write the NTAG215 CC only if
            # we can tell the size; guessing here would brick the card, because
            # the CC is one-time-programmable on NTAG.
            return {"ok": False, "error": (
                "card has no NDEF capability container and this tool will not guess "
                "one — the CC is one-time-programmable. Format it once with any NFC "
                "writer app, then this tool can rewrite the URL forever.")}
        if capacity and len(payload) > capacity:
            return {"ok": False, "error":
                    f"url needs {len(payload)} B but this chip holds {capacity} B"}

        pages = [payload[i:i + 4] for i in range(0, len(payload), 4)]
        # The last line of defence, independent of anything the card claimed about
        # itself. If this ever trips, a capacity check above was wrong — and the
        # cost of being wrong here is a permanently bricked tag, so it is checked
        # before the loop rather than trusted to be unreachable.
        last_page = 4 + len(pages) - 1
        if last_page > last_user_page:
            return {"ok": False, "error": (
                f"refusing to write: this url needs pages 4..{last_page}, but "
                f"{chip_name or 'an unidentified tag'} ends its user data at page "
                f"{last_user_page}. Above it are the lock and configuration pages, and "
                f"writing those cannot be undone.")}

        written = 0
        for i, four in enumerate(pages):
            if not s.write_page(4 + i, four):
                return {"ok": False, "error": f"write failed at page {4 + i} "
                                              f"({written} of {len(pages)} pages written) — "
                                              f"card may be half-programmed, rewrite it",
                        "written_pages": written}
            written += 1

        result = {"ok": True, "url": url, "bytes": len(payload),
                  "pages": written, "reader": s.reader,
                  "warnings": warnings,
                  "uid": (s.uid() or b"").hex().upper() or None}
        if verify:
            back = s.read_pages(4)
            if back and len(payload) > 16:
                page = 8
                while len(back) < len(payload) and page < 220:
                    more = s.read_pages(page)
                    if not more:
                        break
                    back += more
                    page += 4
            got = decode_uri(back or b"")
            result["verified"] = got == url
            result["read_back"] = got
            if not result["verified"]:
                result["ok"] = False
                result["error"] = f"verify failed — card reads back {got!r}, expected {url!r}"
        return result


# --- command line ----------------------------------------------------------
# The agent-facing surface. A card is a thing an automation programs, reads and acts
# on far more often than a person clicks at, so the command line is the primary
# interface and the HTTP API is the app's adapter onto it — not the other way round.
#
# Contract, so a caller never has to parse prose:
#   * exactly one JSON object on stdout, always, including on failure
#   * exit 0 when that object has ok:true, exit 1 otherwise
#   * nothing else on stdout, ever; messages for humans go to stderr

def _cli(argv=None) -> int:
    import argparse
    import json
    import subprocess
    import sys

    ap = argparse.ArgumentParser(
        prog="nfcio.py",
        description="Read and program NFC cards. Prints one JSON object; exits 0 on ok.")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status", help="is a reader connected, is a card on it")
    sub.add_parser("read", help="everything readable from the card on the reader")

    w = sub.add_parser("write", help="write a url (and optional identity) to the card")
    w.add_argument("--url", required=True)
    w.add_argument("--epitaph", default=None,
                   help="vc1|<id>|<title>|<yyyy-mm>|<license>|<tool>")
    w.add_argument("--no-verify", action="store_true",
                   help="skip the read-back check (tests only — never for a real card)")

    o = sub.add_parser("open", help="open the card's address in the default browser")
    o.add_argument("--print-only", action="store_true",
                   help="resolve and print the url without opening anything")

    wa = sub.add_parser("watch", help="print one JSON line per card arrival, forever")
    wa.add_argument("--interval", type=float, default=1.0)

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 2

    def emit(obj):
        print(json.dumps(obj))
        return 0 if obj.get("ok") else 1

    if a.cmd == "status":
        return emit(status())
    if a.cmd == "read":
        return emit(read_card())
    if a.cmd == "write":
        return emit(write_message(a.url, a.epitaph, verify=not a.no_verify))

    if a.cmd == "open":
        card = read_card()
        if not card.get("ok") or not card.get("url"):
            return emit({"ok": False, "error": card.get("url_unsafe") or card.get("error")
                         or "no address on this card"})
        url = card["url"]
        verdict = fetch_allowed(url)
        if not verdict["ok"]:
            return emit({"ok": False, "url": url, "error": verdict["error"]})
        if a.print_only:
            return emit({"ok": True, "url": url, "opened": False})
        # argv list, never a shell string; the scheme is already proven http(s) by
        # fetch_allowed, so this reaches a browser and cannot launch anything else.
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        try:
            rc = subprocess.run([opener, url], capture_output=True, timeout=15).returncode
        except (OSError, subprocess.SubprocessError) as exc:
            return emit({"ok": False, "url": url, "error": f"could not open: {exc}"})
        return emit({"ok": rc == 0, "url": url, "opened": rc == 0})

    if a.cmd == "watch":
        # One line per ARRIVAL, not per poll — a stream that repeats itself while a
        # card sits still is a stream a consumer has to de-duplicate, which means
        # every consumer reimplements the same edge detection. Do it once, here.
        import time
        seen = None
        try:
            while True:
                st = status()
                if st.get("card_present"):
                    card = read_card()
                    key = (card.get("uid"), card.get("url"))
                    if card.get("ok") and key != seen:
                        seen = key
                        print(json.dumps(card), flush=True)
                elif not st.get("busy"):
                    seen = None          # lifted — re-arm for the next arrival
                time.sleep(a.interval)
        except KeyboardInterrupt:
            return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
