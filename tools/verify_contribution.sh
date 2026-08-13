#!/usr/bin/env bash
# The mechanical half of the SECURITY.md review gate.
#
# It answers the questions a human should not have to re-derive on every PR:
# did this change add a shell, a path join on request data, a network call, or a
# dependency — and does the thing still parse and run. The judgement calls (6)-(8)
# stay human, on purpose.
#
#   ./tools/verify_contribution.sh            # check working tree vs HEAD
#   ./tools/verify_contribution.sh --all      # check the whole tree, not just the diff
#
# Exit 0 = clear to review. Exit 1 = a gate tripped, with the offending line printed.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

FAIL=0
MODE="${1:-diff}"

say()  { printf '%s\n' "$*"; }
pass() { printf '  ✓ %s\n' "$*"; }
fail() { printf '  ✗ %s\n' "$*"; FAIL=1; }

# What are we scanning? On a PR the diff is the honest unit — pre-existing code is
# the maintainer's problem, not the contributor's.
# The file list used to be six hardcoded paths. That is a list which silently
# stops being the tree the moment anyone adds a file — and it did: src/nfcio.py,
# 500 lines that drive a card reader over ctypes and burn bytes onto physical
# objects, was invisible to every mode of this gate. Enumerate the tree instead.
ALL_FILES() { find src tools -type f \( -name '*.py' -o -name '*.mjs' -o -name '*.js' \) \
                ! -path '*/__pycache__/*' 2>/dev/null | sort; }

if [ "$MODE" = "--all" ]; then
  SCAN_CMD='ALL_FILES | xargs cat'
  say "▸ scanning ENTIRE tree"
elif git rev-parse --git-dir >/dev/null 2>&1; then
  # `git diff HEAD` reports tracked changes ONLY, so a brand-new file scanned
  # exactly zero lines and still printed GATE CLEAR. New work is the work most
  # likely to need the gate, so untracked files are appended in full.
  SCAN_CMD='{ git diff HEAD -- src/ tools/ | grep "^+" | grep -v "^+++"; \
              git ls-files --others --exclude-standard -- src/ tools/ | xargs -I{} cat {} 2>/dev/null; }'
  say "▸ scanning working tree vs HEAD, including untracked (use --all for everything)"
else
  SCAN_CMD='ALL_FILES | xargs cat'
  say "▸ not a git repo — scanning entire tree"
fi

scan() { eval "$SCAN_CMD" 2>/dev/null; }

say ""
say "── automated gate (SECURITY.md 1-5) ─────────────────────────────"

# 1. no shell=True — the single highest-value grep in a repo that shells out
if scan | grep -nE 'shell\s*=\s*True'; then
  fail "1. subprocess with shell=True"
else
  pass "1. no shell=True"
fi

# 2. request data joined into a path. `BASE / user_input` discards BASE when the
#    input is absolute — this is the exact bug that leaked ~/.docker/config.json.
#    Comments do not count, and a line may carry an explicit `# gate-ok:` marker,
#    which is not a bypass: it puts a human's justification in the diff where a
#    reviewer reads it.
JOINS=$(scan | grep -vE '^\+?\s*#' | grep -v 'gate-ok:' \
  | grep -nE '(DESIGNS|OUTPUT|SUPPORT|WEB|Path\([^)]*\))\s*/\s*(name|body|payload|route|rel|user|req)' || true)
if [ -n "$JOINS" ]; then
  fail "2. request-derived value joined into a filesystem path — match against a listing instead"
  printf '      %s\n' "$JOINS"
else
  pass "2. no request data joined into a path (marked exceptions excluded)"
fi

# 3. network egress. The app talks to a printer on the LAN and nothing else.
# A marked exception carries `# gate-ok: <why>` on the line, same convention rule 2
# already uses. Test harnesses under tools/ genuinely have to speak HTTP to the
# local server they just started; the marker keeps that visible and reviewed
# rather than quietly widening the pattern for everyone.
if scan | grep -vE '# *gate-ok:' \
        | grep -nE 'urllib\.request|http\.client|requests\.(get|post)|fetch\(["'"'"']https?://|socket\.create_connection'; then
  fail "3. new outbound network call"
else
  pass "3. no new network egress"
fi

# 4. third-party imports. Stdlib-only is a feature: it is why there is no install
#    step. Pillow is the ONE allowed optional dependency — every use is inside a
#    try/except with a working fallback (HAS_PIL), so a machine without it still
#    runs. A second optional dependency needs that same treatment and a README line.
# JS module syntax is not a Python import. The scan concatenates .py AND .mjs, so
# `import { readdirSync } from 'fs'` tripped a rule about Python dependencies —
# a false positive that would hit anyone who adds a node tool, and the kind that
# teaches people to ignore the gate. Distinguished by the quoted specifier, which
# Python's `from X import Y` never has.
THIRD_PARTY=$(scan | grep -E '^\+?\s*(import|from) ' \
  | grep -vE "^\+?\s*import\s.*\sfrom\s+['\"]" | grep -vE "^\+?\s*import\s+['\"]" \
  | grep -vE '(import|from)\s+(__future__|base64|glob|json|os|plistlib|re|secrets|shutil|socket|subprocess|sys|threading|time|traceback|urllib|datetime|http\.server|pathlib|typing|math|struct|zlib|io|hashlib|tempfile|argparse|textwrap|collections|functools|itertools|contextlib|ctypes|ipaddress|importlib|pdfwriter|nfcio)\b' \
  | grep -vE '^\+?\s*#' | grep -vE 'from PIL import' | grep -vE '# *noqa' || true)
if [ -n "$THIRD_PARTY" ]; then
  fail "4. non-stdlib import added (Pillow is the only allowed optional dep):"
  printf '      %s\n' "$THIRD_PARTY"
else
  pass "4. stdlib-only preserved (Pillow optional, guarded)"
fi

# 5. it has to parse.
say ""
say "── syntax ───────────────────────────────────────────────────────"
# Every .py under src/, not a two-name tuple. A syntax error in an unlisted file
# cleared this gate and only surfaced when server.py imported it — on the user's
# machine, as an app that will not start.
if python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('src/*.py')]" 2>/dev/null; then
  pass "5a. python parses"
else
  fail "5a. python syntax error"; python3 -c "import ast; ast.parse(open('src/server.py').read())" 2>&1 | tail -3
fi

if command -v node >/dev/null 2>&1; then
  JS_BAD=""
  for f in src/web/app.js src/web/backend.js src/web/backend-static.js src/web/pdf.js; do
    node --check "$f" 2>/dev/null || JS_BAD="$JS_BAD $f"
  done
  if [ -z "$JS_BAD" ]; then
    pass "5b. all frontend JS parses"
  else
    fail "5b. syntax error in:$JS_BAD"; for f in $JS_BAD; do node --check "$f" 2>&1 | tail -2; done
  fi

  # ONE renderer. The web build shares app.js with the desktop; a second copy is
  # the failure this whole architecture exists to prevent, so it is checked
  # rather than trusted.
  if [ "$(git ls-files 2>/dev/null | grep -cE '(^|/)app\.js$')" = "1" ] || ! git rev-parse --git-dir >/dev/null 2>&1; then
    pass "5d. exactly one app.js (no forked renderer)"
  else
    fail "5d. more than one app.js is tracked — the renderer has been forked"
  fi

  # The JS PDF composer must agree with pdfwriter.py or the web build misplaces ink.
  if node tools/pdf_parity.mjs >/dev/null 2>&1; then
    pass "5e. PDF geometry parity with pdfwriter.py"
  else
    fail "5e. PDF geometry DIVERGED from pdfwriter.py"; node tools/pdf_parity.mjs 2>&1 | tail -6
  fi
else
  say "  – 5b. node not installed, skipped app.js parse (NOT a pass)"
fi

# The token placeholder must survive: a real token committed here is a leaked secret,
# and a missing placeholder means the UI can never authenticate.
if grep -q '__CS_SESSION_TOKEN__' src/web/index.html; then
  pass "5c. session-token placeholder intact"
else
  fail "5c. index.html lost __CS_SESSION_TOKEN__ (UI cannot authenticate, or a real token was committed)"
fi

# ── geometry ──────────────────────────────────────────────────────────────
# A card is 85.6 x 53.98 mm and nothing in this project may scale it. Measured by
# building real PDFs and reading the placements back out, not by inspecting the
# composer. Cards cost stock: a geometry regression is only ever discovered on
# paper unless something checks it here.
say ""
say "── geometry ─────────────────────────────────────────────────────"
if python3 "$(dirname "$0")/verify_geometry.py" >/tmp/_vc_geom.log 2>&1; then
  pass "6. mm pipeline exact (placement, bleed, calibration, slot fit)"
else
  fail "6. GEOMETRY REGRESSION — a placement no longer lands where it was asked to"
  sed -n '/FAILED/,$p' /tmp/_vc_geom.log | sed 's/^/      /'
fi

# ── print path ────────────────────────────────────────────────────────────
# Three separate failures lived here, and every geometry check passed through all
# of them, because they were all INSIDE the image rather than in the placement.
# The pixels themselves need a browser, so the real proof is
# `tools/verify_print_export.py` run against an exported PDF (see
# docs/PRINT_GEOMETRY.md). What is cheap here is the wiring that made each
# possible in the first place.
say ""
say "── print path ───────────────────────────────────────────────────"
python3 - <<'PYGATE'
import re, sys, pathlib
s = pathlib.Path("src/web/app.js").read_text(errors="replace")

def body(name):
    i = s.index(name); d, j = 0, i
    while True:
        if s[j] == "{": d += 1
        elif s[j] == "}":
            d -= 1
            if d == 0: return s[i:j]
        j += 1

bad = []

# 7a. The preview must not promise ink the export does not lay down. The frame
#     was drawn on the design canvas and nowhere else for weeks.
if "drawBezel" not in body("function rasterise"):
    bad.append("7a. rasterise() no longer paints the frame — the preview will show a "
               "white border the printed card does not have")

# 7b. The calibration target must be frameless BY CONSTRUCTION. It renders through
#     the same rasteriser, and a frame over it paints out the low ticks and the
#     corner L — the exact marks the card tells you to read. Measured: a 1.885 mm
#     frame moved the first visible ink to 4.91 mm from the edge, so the reading
#     would have been ~5 mm wrong, costing a card AND the calibration.
if not re.search(r"rasterise\(f, S\.doc\.card, dpi, null, 0, null\)", s):
    bad.append("7b. the calibration target is no longer rendered with an explicit "
               "null frame — its registration marks can be painted over")

# 7c. What the printer cannot reach is read FROM the printer. The old constants
#     were calipered off a card whose artwork carried its own white border, so a
#     measurement error became a printing instruction on every card.
if re.search(r"DEVICE_MARGIN_[XY]\s*=\s*(1\.885|2\.02)\b", s):
    bad.append("7c. DEVICE_MARGIN is back to the fitted 1.885/2.02 — those came from "
               "artwork white, not from the printer (which reports 0.1 mm)")
if "adoptDeviceMargins" not in s:
    bad.append("7c. the app no longer adopts the printer's reported margins")

# 7d. Bleed has to reach the elements. Growing only the background made bleed a
#     no-op for a full-card image, which is the default shape of every image added.
if "bledElement" not in body("function rasterise"):
    bad.append("7d. bleed no longer grows edge-touching fills — enabling bleed will "
               "dirty the tray and produce an identical card")

for b in bad:
    print("  " + b)
sys.exit(1 if bad else 0)
PYGATE
if [ $? -eq 0 ]; then
  pass "7. print path wired (frame exported, calibration frameless, margins from device, bleed reaches elements)"
else
  fail "7. print path REGRESSED — see above and docs/PRINT_GEOMETRY.md"
fi

# ── mobile ────────────────────────────────────────────────────────────────
# Every page here is reached by tapping a printed card, so a phone is not one of
# the targets — it is the only one. This measures a REAL emulated touch device
# rather than a narrow desktop window, because the fixes hang off
# `pointer: coarse` and a resized desktop would never match them.
#
# Playwright is optional and is NOT a dependency of this project; without it the
# gate prints SKIPPED, and SKIPPED is not a pass.
say ""
say "── mobile ───────────────────────────────────────────────────────"
if [ -d _site_mobile ] || python3 tools/build_site.py _site_mobile >/dev/null 2>&1; then
  if node tools/verify_mobile.mjs >/tmp/_vc_mobile.log 2>&1; then
    if grep -q "SKIPPED" /tmp/_vc_mobile.log; then
      say "  – 8. playwright absent, mobile gate skipped (NOT a pass)"
    else
      pass "8. watertight at 320/360/390/430 px (no overflow, taps >= 44 px)"
    fi
  else
    fail "8. MOBILE REGRESSION"
    grep -E "^  - " /tmp/_vc_mobile.log | head -8 | sed 's/^/    /'
  fi
  rm -rf _site_mobile
else
  fail "8. could not build the site to measure it"
fi

say ""
if [ "$FAIL" -eq 0 ]; then
  say "GATE CLEAR — now do the human half (SECURITY.md 7-9)."
  say "  7. Does this widen what an unauthenticated request reaches?"
  say "  8. New route? Confirm _guard still covers it."
  say "  9. Security-relevant? Default verdict is REFUTED until an independent"
  say "     pass fails to break it, citing the lines that make it safe."
else
  say "GATE TRIPPED — see the ✗ lines above."
fi
exit "$FAIL"
