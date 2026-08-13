#!/usr/bin/env python3
"""Card Studio — local application server.

Serves the designer UI to a browser on 127.0.0.1 and owns everything the
browser cannot do: querying CUPS, writing exact-geometry PDFs, and handing
jobs to `lp`.

Stdlib only. The browser rasterises each card face at print DPI and posts the
raster here; this process never re-scales it — it only places it at exact
millimetre coordinates on an exact-size page. Scaling anywhere in that chain
is how ink misses a card, so there is exactly one place geometry is decided:
pdfwriter.build_pdf().
"""

from __future__ import annotations

import base64
import json
import os
import plistlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfwriter  # noqa: E402  (local, sits beside this file)
import nfcio  # noqa: E402  (local; stdlib ctypes only, no reader required to import)

SRC = Path(__file__).resolve().parent
WEB = SRC / "web"
SUPPORT = Path.home() / "Library" / "Application Support" / "Card Studio"
DESIGNS = SUPPORT / "designs"
OUTPUT = SUPPORT / "output"
SETTINGS_PATH = SUPPORT / "settings.json"

# The browser must check in or we assume its window is gone and exit. Long
# enough to ride out a laptop sleep or a long print dialog.
HEARTBEAT_TIMEOUT_S = 90.0

MM_PER_IN = 25.4

# PIL is optional: it is only needed for the lossless-PNG print path. The
# browser sends JPEG by default, which pdfwriter embeds with no decode at all.
try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ──────────────────────────────────────────────────────────────────────────
# settings (calibration lives here — it is per-machine, not per-design)
# ──────────────────────────────────────────────────────────────────────────

def load_profiles() -> dict:
    return json.loads((SRC / "profiles.json").read_text())


def load_supplies() -> dict:
    """The buying guide, with the user's personal layer merged over it.

    supplies.json ships generic on purpose — which reader you own and which card
    stock you actually bought is one person's kit, not the project's. That lives
    in my_supplies.json under Application Support: never committed, never shipped,
    and it turns a generic buying guide into YOUR kit. Amazon links get the
    Associates tag appended only when one is configured, so the default build
    ships plain links."""
    data = json.loads((SRC / "supplies.json").read_text())

    mine = {}
    personal = SUPPORT / "my_supplies.json"
    if personal.exists():
        try:
            mine = json.loads(personal.read_text())
        except json.JSONDecodeError:
            # A hand-edited overlay with a stray comma must not take the app down;
            # the guide is still fully usable without it.
            data["personal_error"] = f"{personal.name} is not valid JSON — personal layer ignored."

    if mine.get("your_reader"):
        data["your_reader"] = mine["your_reader"]
    owned = mine.get("owned") or {}
    overrides = mine.get("items") or {}
    for item in data.get("items", []):
        if item["id"] in owned:
            item["owned"] = owned[item["id"]]
        for key, val in (overrides.get(item["id"]) or {}).items():
            item[key] = val

    # The tag can come from the personal overlay, which lives outside the repo. That
    # matters because this repo is public and MIT: a tag committed to supplies.json
    # would ship in every fork, quietly earning for whoever published it rather than
    # for the person who did the forking.
    if mine.get("affiliate", {}).get("amazon_tag"):
        data.setdefault("affiliate", {})["amazon_tag"] = mine["affiliate"]["amazon_tag"]

    tag = (data.get("affiliate") or {}).get("amazon_tag") or ""
    if tag:
        for item in data.get("items", []):
            for link in item.get("links", []):
                if "amazon." in link["url"]:
                    link["url"] += ("&" if "?" in link["url"] else "?") + "tag=" + tag
        data["affiliate"]["active"] = True
    return data


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_settings(patch: dict) -> dict:
    cur = load_settings()
    cur.update(patch)
    SUPPORT.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(cur, indent=2))
    return cur


def effective_profiles() -> dict:
    """profiles.json with any per-machine calibration merged in."""
    data = load_profiles()
    saved = load_settings().get("calibration", {})
    for key, prof in data["profiles"].items():
        if key in saved:
            prof["calibration"] = {
                "dx": float(saved[key].get("dx", 0.0)),
                "dy": float(saved[key].get("dy", 0.0)),
            }
    return data


# ──────────────────────────────────────────────────────────────────────────
# CUPS
# ──────────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out: {' '.join(cmd)}"


def list_printers() -> dict:
    rc, out, err = _run(["lpstat", "-p", "-d"])
    printers, default = [], None
    for line in out.splitlines():
        # "is idle" / "is disabled" but also "now printing job-N" — matching only
        # the "is <word>" form silently dropped any printer that was busy, which
        # emptied the device picker exactly when a job was running.
        m = re.match(r"printer (\S+) (?:is (\w+)|(now printing))", line)
        if m:
            printers.append({"name": m.group(1), "state": m.group(2) or "printing"})
        m = re.match(r"system default destination: (\S+)", line)
        if m:
            default = m.group(1)
    return {"printers": printers, "default": default, "error": err.strip() or None}


def printer_capabilities(name: str) -> dict:
    """Read the driver's real option list so the UI never offers a media the
    printer cannot accept."""
    rc, out, _ = _run(["lpoptions", "-p", name, "-l"])
    caps: dict[str, dict] = {}
    for line in out.splitlines():
        m = re.match(r"([^/]+)/([^:]*):\s*(.*)", line)
        if not m:
            continue
        key, label, values = m.group(1), m.group(2).strip(), m.group(3).split()
        caps[key] = {
            "label": label,
            "values": [v.lstrip("*") for v in values],
            "default": next((v.lstrip("*") for v in values if v.startswith("*")), None),
        }
    return caps


def queue_status(name: str) -> dict:
    rc, out, _ = _run(["lpstat", "-o", name])
    jobs = [l for l in out.splitlines() if l.strip()]
    rc2, out2, _ = _run(["lpstat", "-p", name])
    return {"jobs": jobs, "state": out2.strip()}


# ──────────────────────────────────────────────────────────────────────────
# print pipeline
# ──────────────────────────────────────────────────────────────────────────

def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    m = re.match(r"data:image/(png|jpeg|jpg);base64,(.*)$", data_url, re.S)
    if not m:
        raise ValueError("expected a base64 png/jpeg data URL")
    fmt = "png" if m.group(1) == "png" else "jpeg"
    return base64.b64decode(m.group(2)), fmt


def compose_pdf(payload: dict) -> Path:
    """Turn a print payload from the browser into an exact-geometry PDF.

    payload = {
      page_mm: {w,h},
      dx, dy,                        # calibration nudge, mm, applied to every placement
      placements: [ {image: dataURL, x_mm, y_mm, w_mm, h_mm, rotate_deg} ],
      name: "..."                    # used for the output filename
    }
    """
    page = payload["page_mm"]
    dx = float(payload.get("dx", 0.0))
    dy = float(payload.get("dy", 0.0))

    images = []
    for p in payload["placements"]:
        data, fmt = _decode_data_url(p["image"])
        images.append({
            "data": data,
            "format": fmt,
            "x_mm": float(p["x_mm"]) + dx,
            "y_mm": float(p["y_mm"]) + dy,
            "w_mm": float(p["w_mm"]),
            "h_mm": float(p["h_mm"]),
            "rotate_deg": int(p.get("rotate_deg", 0)),
        })

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", payload.get("name") or "cards")[:60]
    out = OUTPUT / f"{safe}-{stamp}.pdf"

    pdfwriter.build_pdf(
        str(out),
        float(page["w"]),
        float(page["h"]),
        images,
        title=f"Card Studio — {safe}",
    )
    return out


def _known_printer(printer: str) -> str:
    """A printer name CUPS actually reports, or ValueError.

    `printer` reaches an argv and a filesystem path. A name like `../../etc/x`
    walks out of /etc/cups/ppd, and one starting with `-` becomes a flag rather
    than a value. Neither is escapable in general — but the set of real printers
    is small and knowable, so match against it and refuse everything else.
    """
    names = {p.get("name") for p in (list_printers().get("printers") or [])}
    if printer in names:
        return printer
    raise ValueError(f"unknown printer: {printer!r}")


def dry_run(pdf: Path, printer: str, options: dict) -> dict:
    """Render the job through the real CUPS filter chain WITHOUT printing.

    This is the cheap insurance: the printer accepts a PDF only after CUPS
    converts it to URF raster, and a MediaBox that does not exactly match the
    page is silently cropped rather than reported. Rasterising here and reading
    the URF header back tells us the true output geometry before any PVC is at
    risk.
    """
    printer = _known_printer(printer)
    ppd = Path("/etc/cups/ppd") / f"{printer}.ppd"
    cmd = ["cupsfilter", "-m", "image/urf"]
    if ppd.exists():
        cmd += ["-p", str(ppd)]
    for k, v in options.items():
        if v not in (None, "", False):
            cmd += ["-o", f"{k}={v}"]
    cmd.append(str(pdf))

    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "command": " ".join(cmd)}

    raster = p.stdout
    out = {"ok": False, "command": " ".join(cmd), "bytes": len(raster),
           "stderr": p.stderr.decode(errors="replace")[-2000:]}
    if p.returncode != 0 or not raster:
        out["error"] = f"cupsfilter exited {p.returncode}"
        return out

    idx = raster.find(b"UNIRAST")
    if idx < 0:
        out["error"] = "no URF header in the rendered raster"
        return out
    # URF layout from "UNIRAST": 8-byte magic, uint32 page count, then the
    # 32-byte page header — bpp at +0, width/height/resolution at +12/+16/+20.
    import struct
    try:
        bpp = raster[idx + 12]
        w, h, dpi = struct.unpack(">III", raster[idx + 24: idx + 36])
    except (struct.error, IndexError) as exc:
        out["error"] = f"could not parse URF header: {exc}"
        return out

    out.update({"ok": True, "width_px": w, "height_px": h, "dpi": dpi, "bpp": bpp,
                "width_mm": round(w / dpi * MM_PER_IN, 3),
                "height_mm": round(h / dpi * MM_PER_IN, 3)})
    return out


# Canon support codes worth translating in-app. The printer only ever shows
# "Check the printer." plus a number, and the number is the whole diagnosis —
# 1857 cost a round of SNMP spelunking to find, which is exactly the kind of
# thing this panel exists to prevent.
# Canon's own wording, verified against ij.manual.canon for the TS700 series.
#
# The output-tray codes are the trap and the reason MP-tray printing feels
# broken: the printer wants the output tray in OPPOSITE positions at two
# different moments. It must be pulled OUT to initialise (1857/1851/1259), then
# pushed back IN before the multi-purpose tray goes on (1850/1855). Chasing one
# code at a time just flips you into the other.
CANON_CODES = {
    "1857": ("Output tray is pushed in — needed OUT to initialise",
             "Pull the paper output tray fully out, then press OK. This is the first "
             "stage: the printer needs it open to initialise before it asks for the tray."),
    "1851": ("Output tray is pushed in",
             "Pull the paper output tray fully out, extend the paper support, then press OK."),
    "1259": ("Output tray is not pulled out fully",
             "Pull the paper output tray fully forward until it stops, extend the paper "
             "support, then press OK."),
    "1850": ("Output tray is pulled out — needed IN for the MP tray",
             "Retract the paper output support and push the output tray in until it stops, "
             "aligned with the operation panel. Seat the multi-purpose tray on its guide, "
             "then press OK. This is the second stage — the opposite of 1857."),
    "1855": ("Output tray is pulled out — needed IN for the MP tray",
             "Push the output tray in until it stops and realign it with the operation panel, "
             "re-seat the multi-purpose tray on its guide, then press OK."),
    "1300": ("Paper jam feeding from the rear tray",
             "Slowly pull the jammed sheet or tray out from the output slot or rear tray, "
             "holding it with both hands so it does not tear. Then reload and press OK. "
             "If it will not come out, power-cycle the printer — it often ejects on restart."),
    "2114": ("Paper settings do not match the rear tray",
             "Press OK and either print with the current settings, change the paper in the "
             "rear tray to match, or cancel and fix the job's paper settings."),
    "1003": ("No paper in the cassette, or loaded incorrectly",
             "Load paper in the cassette, align the paper guides to the paper edges, and set "
             "the paper information on the printer."),
}


def _device_host() -> str | None:
    """Resolve the printer's hostname so we can talk to the device directly.

    The CUPS queue is a dnssd:// URI with no host in it, so the name has to be
    resolved through Bonjour. Everything that depends on this degrades to None
    rather than failing the whole status call.
    """
    rc, out, _ = _run(["ippfind", "--name", "Canon", "-x", "echo", "{}", ";"], timeout=8)
    for line in out.splitlines():
        m = re.match(r"ipps?://([^:/]+)", line.strip())
        if m:
            return m.group(1)
    # Bonjour fallback: dns-sd never exits on its own, so it is time-boxed.
    rc, out, _ = _run(["bash", "-c",
                       'timeout 5 dns-sd -L "Canon TS700 series" _ipps._tcp local 2>/dev/null'], timeout=10)
    m = re.search(r"can be reached at ([^:\s]+)", out)
    return m.group(1).rstrip(".") if m else None


def _snmp(host: str, oid: str) -> str | None:
    rc, out, _ = _run(["snmpget", "-v1", "-c", "public", "-t", "2", "-r", "0", host, oid], timeout=8)
    if rc != 0:
        return None
    m = re.search(r'(?:STRING|INTEGER|Hex-STRING):\s*"?([^"\n]*)"?', out)
    return m.group(1).strip() if m else None


def printer_status(printer: str) -> dict:
    """Everything needed to answer 'why is nothing printing?' in one call."""
    out: dict = {"printer": printer}

    rc, txt, _ = _run(["lpstat", "-p", printer])
    out["queue_line"] = txt.strip()
    out["queue_enabled"] = "disabled" not in txt

    rc, txt, _ = _run(["lpstat", "-W", "not-completed", "-o", printer])
    jobs = [l for l in txt.splitlines() if l.strip()]
    out["pending_jobs"] = len(jobs)
    out["jobs"] = jobs[:10]

    host = _device_host()
    out["host"] = host
    if not host:
        out["reachable"] = False
        return out

    # Device console text and the support code behind "Check the printer."
    lcd = _snmp(host, "1.3.6.1.2.1.43.16.5.1.2.1.1")
    out["lcd"] = lcd
    out["reachable"] = lcd is not None

    rc, txt, _ = _run(["snmpwalk", "-v1", "-c", "public", "-t", "2", "-r", "0",
                       host, "1.3.6.1.2.1.43.18.1.1.8"], timeout=10)
    alerts, code = [], None
    for line in txt.splitlines():
        m = re.search(r'STRING:\s*"([^"]*)"', line)
        if not m:
            continue
        alerts.append(m.group(1))
        c = re.search(r"(\d{4})", m.group(1))
        if c and not code:
            code = c.group(1)
    out["alerts"] = alerts
    out["support_code"] = code
    if code:
        title, fix = CANON_CODES.get(code, (None, None))
        out["support_title"] = title
        out["support_fix"] = fix
        out["support_url"] = (
            "https://ij.manual.canon/ij/webmanual/ErrorCode/TS700%20series/EN/ERR/" + code + ".html")

    # Ink, so a failed card print is never a mystery low-ink cartridge
    rc, txt, _ = _run(["snmpwalk", "-v1", "-c", "public", "-t", "2", "-r", "0",
                       host, "1.3.6.1.2.1.43.11.1.1.9"], timeout=10)
    levels = [int(m.group(1)) for m in re.finditer(r"INTEGER:\s*(-?\d+)", txt)]
    rc, txt, _ = _run(["snmpwalk", "-v1", "-c", "public", "-t", "2", "-r", "0",
                       host, "1.3.6.1.2.1.43.11.1.1.6"], timeout=10)
    names = [m.group(1) for m in re.finditer(r'STRING:\s*"([^"]*)"', txt)]
    out["ink"] = [{"name": n, "level": l} for n, l in zip(names, levels)]
    return out


_IPP_KEYWORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _ipp_keyword(value, fallback: str) -> str:
    """An IPP keyword, or the fallback. Never the caller's raw string."""
    v = (value or "").strip()
    return v if _IPP_KEYWORD_RE.match(v) else fallback


def _boot_margins(profiles: dict, printer: str) -> dict:
    """device_margins for the profile the app opens with.

    Bootstrap must never fail on this — a printer that is asleep or off the
    network is normal, and the client keeps its fallback. But the first version
    of this caught everything and returned {}, so when it reached into the wrong
    level of the profiles file and raised TypeError, the result was
    indistinguishable from "the printer did not answer". It looked like a
    hardware condition and it was a typo.

    So the failure REASON travels with the empty answer. A silent fallback that
    cannot tell a bug from an offline device will hide the bug every time, and
    the bug is the one you can fix.
    """
    if not printer:
        return {"error": "no printer selected"}
    try:
        key = profiles.get("default_profile")
        table = profiles.get("profiles") or {}
        prof = table.get(key) or next(iter(table.values()))
        got = device_margins(prof["page_mm"])
        return got or {"error": "printer did not report margins for this media"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def device_margins(page_mm: dict) -> dict:
    """Ask the printer what it cannot reach, for THIS media size.

    The app used to carry 1.885 x 2.02 mm as "the unprintable margin", derived by
    calipering a printed card. That measurement cannot separate the printer's
    limit from white the ARTWORK already contained, and in this case it was almost
    entirely the artwork: the two calipered cards carry 1.91 and 1.99 mm of white
    inside their own raster, while a full-bleed card on the same tray carries
    0.00. The fitted number then became a printing instruction.

    The device answers this question directly and for free. `media-col-database`
    lists every media size with its four margins in hundredths of a millimetre;
    for this tray's 120 x 120 it reports 10, 10, 10, 10 — 0.1 mm all round.

    Ask the thing that knows. A caliper measures the OUTCOME of a pipeline and
    cannot attribute it; the printer reports its own limit.

    Returns {} when the printer cannot be reached, and the caller keeps its
    fallback — a missing answer must not silently become 0.
    """
    host = _device_host()
    if not host:
        return {}

    x = int(round(float(page_mm["w"]) * 100))
    y = int(round(float(page_mm["h"]) * 100))

    # No caller data reaches the test file: x and y are ints, and everything else
    # is a literal. See validate_tray for why that matters here.
    test = """{
  OPERATION Get-Printer-Attributes
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR language attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR keyword requested-attributes media-col-database
}
"""
    tmp = SUPPORT / ".margins.test"
    tmp.write_text(test)
    rc, out, err = _run(["ipptool", "-tv", f"ipp://{host}:631/ipp/print", str(tmp)], timeout=20)
    tmp.unlink(missing_ok=True)
    if rc != 0 or not out:
        return {}

    # Every entry for our media size. A size usually appears twice — bordered and
    # borderless — and the SMALLEST margins are the ones a borderless job gets,
    # which is what this app asks for.
    best = None
    for m in re.finditer(
            r"media-size=\{x-dimension=(\d+)\s+y-dimension=(\d+)\}"
            r"\s*media-bottom-margin=(\d+)"
            r"\s*media-left-margin=(\d+)"
            r"\s*media-right-margin=(\d+)"
            r"\s*media-top-margin=(\d+)", out):
        mx, my, b, l, r, t = (int(g) for g in m.groups())
        if abs(mx - x) > 50 or abs(my - y) > 50:      # 0.5 mm of slack on the match
            continue
        cand = {"left": l / 100, "right": r / 100, "top": t / 100, "bottom": b / 100}
        if best is None or max(cand.values()) < max(best.values()):
            best = cand
    if best is None:
        return {}
    return {**best,
            "x": max(best["left"], best["right"]),
            "y": max(best["top"], best["bottom"]),
            "source": f"printer, media {x/100:g}x{y/100:g} mm (IPP media-col-database)"}


def validate_tray(printer: str, page_mm: dict, options: dict) -> dict:
    """Ask the printer whether it accepts this exact job — without printing it.

    IPP Validate-Job is the only honest answer to "is the tray actually
    selected?": it puts the real media-col on the wire and the device says yes
    or no. Costs no ink, no card, no paper.
    """
    host = _device_host()
    if not host:
        return {"ok": False, "error": "could not find the printer on the network"}

    x = int(round(float(page_mm["w"]) * 100))
    y = int(round(float(page_mm["h"]) * 100))
    # x/y are coerced to int, so they cannot carry syntax. These two are strings
    # interpolated into an ipptool test file, which is a DIRECTIVE LANGUAGE — a
    # value containing a newline writes new ATTR/OPERATION lines into the job.
    # IPP keywords are lowercase alphanumerics with - and _; anything else is not
    # a keyword we should be sending, so refuse rather than escape.
    source = _ipp_keyword(options.get("InputSlot"), "disc")
    mtype = _ipp_keyword(options.get("MediaType"), "disc")
    quality = {"Draft": 3, "Normal": 4, "High": 5}.get(options.get("cupsPrintQuality"), 5)

    test = f"""{{
  OPERATION Validate-Job
  GROUP operation-attributes-tag
  ATTR charset attributes-charset utf-8
  ATTR language attributes-natural-language en
  ATTR uri printer-uri $uri
  ATTR name requesting-user-name $user
  ATTR mimeMediaType document-format image/urf
  GROUP job-attributes-tag
  ATTR integer copies 1
  ATTR keyword print-color-mode color
  ATTR enum print-quality {quality}
  ATTR collection media-col {{
    MEMBER collection media-size {{
      MEMBER integer x-dimension {x}
      MEMBER integer y-dimension {y}
    }}
    MEMBER keyword media-source {source}
    MEMBER keyword media-type {mtype}
  }}
  STATUS successful-ok
}}
"""
    tmp = SUPPORT / ".validate.test"
    tmp.write_text(test)
    rc, out, err = _run(["ipptool", "-tv", f"ipp://{host}:631/ipp/print", str(tmp)], timeout=25)
    tmp.unlink(missing_ok=True)

    m = re.search(r"status-code\s*=\s*(\S+)", out)
    status = m.group(1) if m else None
    return {
        "ok": status == "successful-ok",
        "status": status,
        "host": host,
        "sent": {"media-size": f"{x}x{y} (1/100 mm)", "media-source": source,
                 "media-type": mtype, "print-quality": quality},
        "detail": (out or err)[-1200:],
    }


def reset_printer(printer: str) -> dict:
    """Clear the queue and put it back to its idle default.

    Cancelling first matters: a job left stuck at the tray handshake keeps the
    device in an alert state, and re-enabling underneath it just re-runs the
    same failure.
    """
    steps = []
    rc, o, e = _run(["cancel", "-a", printer], timeout=20)
    steps.append({"step": "cancel all jobs", "ok": rc == 0, "detail": (e or o).strip()})
    time.sleep(1.5)
    rc, o, e = _run(["cupsenable", printer], timeout=15)
    steps.append({"step": "enable queue", "ok": rc == 0, "detail": (e or o).strip()})
    time.sleep(1.5)
    return {"ok": all(s["ok"] for s in steps), "steps": steps, "status": printer_status(printer)}


def enable_queue(printer: str) -> dict:
    """A backend failure leaves the CUPS queue disabled, and a disabled queue
    accepts jobs then silently does nothing — the most common 'I pressed print
    and nothing happened'."""
    rc, out, err = _run(["cupsenable", printer])
    return {"ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()}


def send_to_printer(pdf: Path, printer: str, options: dict, copies: int = 1) -> dict:
    printer = _known_printer(printer)
    cmd = ["lp", "-d", printer, "-n", str(max(1, min(99, int(copies))))]
    for k, v in options.items():
        if v in (None, "", False):
            continue
        cmd += ["-o", f"{k}={v}"]
    cmd.append(str(pdf))
    rc, out, err = _run(cmd, timeout=60)
    job = None
    m = re.search(r"request id is (\S+)", out)
    if m:
        job = m.group(1)
    return {
        "ok": rc == 0,
        "job": job,
        "command": " ".join(cmd),
        "stdout": out.strip(),
        "stderr": err.strip(),
    }


# ──────────────────────────────────────────────────────────────────────────
# designs on disk
# ──────────────────────────────────────────────────────────────────────────

def list_designs() -> list[dict]:
    DESIGNS.mkdir(parents=True, exist_ok=True)
    items = []
    for f in sorted(DESIGNS.glob("*.card.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            doc = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        items.append({
            "file": f.name,
            "name": doc.get("name") or f.stem.replace(".card", ""),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return items


def _design_path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9 ._-]+", "_", name).strip() or "Untitled"
    return DESIGNS / f"{safe}.card.json"


# ──────────────────────────────────────────────────────────────────────────
# HTTP
# ──────────────────────────────────────────────────────────────────────────

class State:
    last_beat = time.time()
    quit_requested = False


# A localhost bind is NOT a security boundary, and treating it as one is the
# classic desktop-app hole:
#   * every other process and every other user account on the machine can reach
#     127.0.0.1, so "local" is not "mine";
#   * any web page the user visits can POST to 127.0.0.1 on a guessed port
#     (drive-by CSRF) — it cannot read the reply, but it can make things happen;
#   * DNS rebinding defeats even that. An attacker serves evil.tld, re-points it
#     at 127.0.0.1, and their page becomes SAME-ORIGIN with this server — at
#     which point it can read every response too.
# Two independent guards, because they stop different attacks:
#   HOST allow-list  → kills DNS rebinding (a rebound request carries the
#                      attacker's hostname in Host, never 127.0.0.1).
#   PER-RUN TOKEN    → kills blind CSRF (an attacker can send a request but
#                      cannot know a secret minted this run and never sent
#                      cross-origin).
# The token is regenerated every launch and only ever leaves via index.html,
# which the Host guard already protects.
SESSION_TOKEN = secrets.token_urlsafe(32)
TOKEN_PLACEHOLDER = "__CS_SESSION_TOKEN__"


def _allowed_hosts(port: int) -> set:
    return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "CardStudio/1.0"

    def log_message(self, fmt, *args):  # quiet; this is a desktop app, not a web server
        pass

    # ---- helpers ----------------------------------------------------------

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    # ---- request guard ----------------------------------------------------

    def _guard(self, route: str) -> bool:
        """Reject anything that is not this app's own window talking to itself.
        Returns True to continue; on False it has already answered 403."""
        port = self.server.server_address[1]
        host = (self.headers.get("Host") or "").strip()
        if host not in _allowed_hosts(port):
            # DNS rebinding, or a proxy — either way not our window.
            self._json({"error": "bad host"}, 403)
            return False

        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in _allowed_hosts(port)}:
            self._json({"error": "cross-origin request refused"}, 403)
            return False

        # Static assets carry no privilege; the API does.
        if route.startswith("/api/"):
            sent = self.headers.get("X-CS-Token") or ""
            if not secrets.compare_digest(sent, SESSION_TOKEN):
                self._json({"error": "bad or missing session token"}, 403)
                return False
        return True

    def _static(self, rel: str):
        path = (WEB / rel).resolve()  # gate-ok: contained by the check on the next line
        if not str(path).startswith(str(WEB.resolve())) or not path.is_file():
            self.send_error(404)
            return
        if rel == "index.html":
            # The one place the session token is handed out. Everything after
            # this point must present it.
            html = path.read_text().replace(TOKEN_PLACEHOLDER, SESSION_TOKEN)
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES[".html"])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- routes -----------------------------------------------------------

    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if not self._guard(route):
            return
        if route == "/":
            return self._static("index.html")
        if route == "/api/bootstrap":
            State.last_beat = time.time()
            profiles = effective_profiles()
            pr = list_printers()
            chosen = load_settings().get("printer") or pr.get("default")
            caps = printer_capabilities(chosen) if chosen else {}
            return self._json({
                "profiles": profiles,
                "printers": pr,
                "printer": chosen,
                "capabilities": caps,
                "settings": load_settings(),
                "designs": list_designs(),
                "paths": {"designs": str(DESIGNS), "output": str(OUTPUT)},
                "pil": HAS_PIL,
                "supplies": load_supplies(),
                # What the printer says it cannot reach, so the app never has to
                # infer it from a printed card again. {} means the printer did not
                # answer, and the client keeps its own conservative fallback —
                # a missing answer must not read as "no margin".
                "device_margins": _boot_margins(profiles, chosen),
            })
        if route == "/api/ping":
            State.last_beat = time.time()
            return self._json({"ok": True})
        if route == "/api/designs":
            return self._json({"designs": list_designs()})
        if route == "/api/queue":
            name = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("printer", [""])[0]
            return self._json(queue_status(name))
        if route.startswith("/api/design/"):
            name = urllib.parse.unquote(route[len("/api/design/"):])
            # `DESIGNS / name` accepts an ABSOLUTE path and silently discards the
            # left operand, so the raw name could name any file on disk — and the
            # designs dir is exactly where a home directory full of JSON
            # credentials is one `..` away. Match against the real listing rather
            # than trying to out-sanitise pathlib.
            known = {d["file"] for d in list_designs()}
            if name not in known:
                return self._json({"error": "not found"}, 404)
            p = (DESIGNS / name).resolve()  # gate-ok: name matched against list_designs() above
            if p.parent != DESIGNS.resolve() or not p.is_file():
                return self._json({"error": "not found"}, 404)
            try:
                return self._json(json.loads(p.read_text()))
            except (json.JSONDecodeError, OSError):
                return self._json({"error": "design file is unreadable"}, 500)

        # ---- NFC (the chip half of a printed card) ------------------------
        # Both are reads. They are still behind _guard's token check because
        # /api/ is privileged wholesale — a page that could poll the reader
        # learns when a card is present, and card UIDs are used as identifiers
        # elsewhere in this app.
        # These two carry their own try/except because do_GET, unlike do_POST
        # (:843), has no blanket handler. An exception here does not become a 500 —
        # it propagates into socketserver, which closes the socket with no status
        # line at all, so the browser's fetch() REJECTS and backend.js never gets
        # to read an error message. The UI would show nothing rather than a
        # problem. nfcio is written not to raise, but "written not to raise" is a
        # claim about today's code; a missing PCSC symbol still surfaces as an
        # AttributeError from _pcsc(), and hardware makes new failure modes.
        if route in ("/api/nfc/status", "/api/nfc/read"):
            try:
                return self._json(nfcio.status() if route.endswith("status")
                                  else nfcio.read_card())
            except Exception as exc:
                return self._json({"ok": False, "error": f"reader failed: {exc}"}, 200)

        return self._static(route.lstrip("/"))

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if not self._guard(route):
            return
        State.last_beat = time.time()
        try:
            if route == "/api/print":
                body = self._body()
                pdf = compose_pdf(body)
                printer = body.get("printer") or list_printers().get("default")
                if not printer:
                    return self._json({"ok": False, "error": "no printer available"}, 400)
                res = send_to_printer(pdf, printer, body.get("options") or {}, body.get("copies", 1))
                res["pdf"] = str(pdf)
                return self._json(res)

            if route == "/api/dryrun":
                body = self._body()
                pdf = compose_pdf(body)
                printer = body.get("printer") or list_printers().get("default")
                res = dry_run(pdf, printer, body.get("options") or {})
                res["pdf"] = str(pdf)
                return self._json(res)

            if route == "/api/enable-queue":
                return self._json(enable_queue(self._body()["printer"]))

            if route == "/api/validate-tray":
                body = self._body()
                return self._json(validate_tray(
                    body.get("printer") or list_printers().get("default"),
                    body["page_mm"], body.get("options") or {}))

            if route == "/api/printer-status":
                body = self._body()
                return self._json(printer_status(body.get("printer") or list_printers().get("default")))

            if route == "/api/reset-printer":
                body = self._body()
                return self._json(reset_printer(body.get("printer") or list_printers().get("default")))

            if route == "/api/pdf":
                body = self._body()
                pdf = compose_pdf(body)
                if body.get("reveal"):
                    _run(["open", "-R", str(pdf)])
                elif body.get("open", True):
                    _run(["open", str(pdf)])
                return self._json({"ok": True, "pdf": str(pdf)})

            if route == "/api/save-design":
                body = self._body()
                doc = body["design"]
                p = _design_path(doc.get("name") or "Untitled")
                DESIGNS.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(doc, indent=2))
                return self._json({"ok": True, "file": p.name, "designs": list_designs()})

            if route == "/api/delete-design":
                body = self._body()
                # Same rule as the read route: match the request against the real
                # listing rather than joining it into a path. The old
                # `p.parent == DESIGNS` check did hold, but "never join request
                # data into a path" is only a usable rule if it has no exceptions
                # to remember.
                name = body.get("file") or ""
                if name in {d["file"] for d in list_designs()}:
                    p = (DESIGNS / name).resolve()  # gate-ok: name matched against list_designs() above
                    if p.is_file() and p.parent == DESIGNS.resolve():
                        p.unlink()
                return self._json({"ok": True, "designs": list_designs()})

            if route == "/api/settings":
                return self._json({"ok": True, "settings": save_settings(self._body())})

            if route == "/api/calibration":
                body = self._body()
                cal = load_settings().get("calibration", {})
                cal[body["profile"]] = {"dx": float(body["dx"]), "dy": float(body["dy"])}
                save_settings({"calibration": cal})
                return self._json({"ok": True, "profiles": effective_profiles()})

            if route == "/api/printer":
                body = self._body()
                save_settings({"printer": body["printer"]})
                return self._json({"ok": True, "capabilities": printer_capabilities(body["printer"])})

            if route == "/api/reveal":
                _run(["open", str(OUTPUT if self._body().get("what") == "output" else DESIGNS)])
                return self._json({"ok": True})

            if route == "/api/nfc/write":
                # The only route in this app whose effect is IRREVERSIBLE OUTSIDE
                # THE MACHINE: it burns bytes onto a physical tag that is then
                # handed to a human. Two consequences shape the handling here.
                #
                # 1. The URL is never assembled server-side. Whatever the user
                #    read on screen is exactly what is transmitted and exactly
                #    what is written — no normalising, no appending a tracking
                #    parameter, no "helpfully" adding https://. A card that says
                #    one thing and resolves to another is the failure this whole
                #    feature has to be incapable of, so the string is passed
                #    through verbatim and nfcio refuses anything that is not
                #    plain http(s).
                # 2. Verification is forced on. write_url(verify=False) exists
                #    for tests; over HTTP a caller does not get to skip the
                #    read-back, because an unverified write is indistinguishable
                #    from a half-written card until someone taps it.
                body = self._body()
                url = body.get("url")
                if not isinstance(url, str):
                    return self._json({"ok": False, "error": "url must be a string"}, 400)
                epitaph = body.get("epitaph")
                if epitaph is not None and not isinstance(epitaph, str):
                    return self._json({"ok": False, "error": "epitaph must be a string"}, 400)
                # write_message, not write_url, even when there is no epitaph. Its
                # verification compares the WHOLE payload byte-for-byte, where
                # write_url's only re-parses the URL back out — and a re-parse cannot
                # see a second record that was truncated or never written, because the
                # URI record comes first and reads back perfectly either way. The
                # documented guarantee is the byte comparison, so the route that the
                # documentation describes has to be the one that performs it.
                return self._json(nfcio.write_message(url, epitaph, verify=True))

            if route == "/api/nfc/open":
                # Hand the card's address to the user's browser. This is NOT the
                # auto-fetch that SECURITY.md forbids: nothing here requests the URL,
                # parses a response, or renders anything. The browser navigates, with
                # its own sandbox and a visible address bar — the same thing a phone
                # does with this card and no app installed.
                #
                # THE URL IS NOT ACCEPTED FROM THE CLIENT. The server re-reads the tag
                # and opens what is actually on it. If the caller supplied it, a page
                # holding the session token could open any address it liked through
                # this route; reading the card removes that entirely — the worst a
                # caller can do is open the card the user is already holding.
                card = nfcio.read_card()
                if not card.get("ok") or not card.get("url"):
                    return self._json({"ok": False, "error": card.get("url_unsafe")
                                       or card.get("error") or "no address on this card"})
                url = card["url"]
                # Same predicate that governs fetching. A card is attacker-writable, so
                # loopback, link-local and private addresses are refused here too: the
                # browser would carry the user's cookies to whatever answered.
                verdict = nfcio.fetch_allowed(url)
                if not verdict["ok"]:
                    return self._json({"ok": False, "url": url, "error": verdict["error"]})
                # argv list, never a shell string, and the scheme is already proven
                # http(s) — so `open` reaches the browser and cannot launch anything else.
                rc, _, err = _run(["open", url])
                if rc != 0:
                    return self._json({"ok": False, "url": url, "error": err or "could not open"})
                return self._json({"ok": True, "url": url})

            if route == "/api/quit":
                State.quit_requested = True
                return self._json({"ok": True})

            return self._json({"error": "unknown route"}, 404)

        except Exception as exc:  # surface the real failure in the UI, never a silent no-op
            import traceback
            return self._json({"ok": False, "error": str(exc), "trace": traceback.format_exc()}, 500)


def watchdog(httpd):
    """Exit when the UI window goes away, so the app has a real lifecycle
    instead of leaking a server every launch."""
    while True:
        time.sleep(3)
        if State.quit_requested or (time.time() - State.last_beat) > HEARTBEAT_TIMEOUT_S:
            httpd.shutdown()
            return


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def open_ui(url: str) -> None:
    """Prefer a chromeless Chrome app window with its own profile — it makes
    this feel like an app rather than a tab, and an isolated profile means it
    never collides with the operator's live browser session."""
    chrome = Path("/Applications/Google Chrome.app")
    if chrome.exists():
        profile = SUPPORT / "browser"
        profile.mkdir(parents=True, exist_ok=True)
        rc, _, _ = _run([
            "open", "-na", str(chrome), "--args",
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1500,960",
        ])
        if rc == 0:
            return
    _run(["open", url])


def main() -> int:
    for d in (SUPPORT, DESIGNS, OUTPUT):
        d.mkdir(parents=True, exist_ok=True)

    port = int(os.environ.get("CARD_STUDIO_PORT") or free_port())
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Card Studio serving {url}", flush=True)

    # The launcher reads this to re-open an already-running instance instead of
    # starting a second server on a second port.
    portfile = SUPPORT / "port"
    portfile.write_text(str(port))

    threading.Thread(target=watchdog, args=(httpd,), daemon=True).start()
    if os.environ.get("CARD_STUDIO_NO_BROWSER") != "1":
        threading.Timer(0.4, open_ui, args=(url,)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if portfile.exists() and portfile.read_text().strip() == str(port):
            portfile.unlink()
    print("Card Studio stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
