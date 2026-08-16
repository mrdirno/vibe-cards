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
# AND ENGLISH IS NOT PYTHON EITHER. `--all` scans .py/.mjs/.js only, but the
# default mode pipes the whole diff plus every untracked file — HTML included —
# so a card page reading "...1.2 mm felt made\nfrom recycled bottles." tripped a
# rule about Python dependencies. Two modes of one gate were reading two
# different corpora, and the workaround had already leaked into an unrelated
# file: tools/intake_card.py carries a docstring line telling authors that no
# sentence there may begin with "from ". A check that makes people write around
# it is a check that will be written around. An import can only live in a .py
# file, so this one reads .py files — the others keep the full corpus, because
# an unsafe subprocess flag, a path join and a network call can all appear in a
# script tag. (Check 1 greps its own source too, and does not skip comments, so
# writing that flag out literally in this comment trips it. It has been written
# around here rather than by loosening the grep, which is the right trade for a
# one-line comment and the wrong one for anything else.)
py_scan() {
  if [ "$MODE" = "--all" ] || ! git rev-parse --git-dir >/dev/null 2>&1; then
    find src tools -type f -name '*.py' ! -path '*/__pycache__/*' 2>/dev/null | sort | xargs cat 2>/dev/null
  else
    git diff HEAD -- 'src/*.py' 'tools/*.py' | grep "^+" | grep -v "^+++"
    git ls-files --others --exclude-standard -- 'src/*.py' 'tools/*.py' \
      | xargs -I{} cat {} 2>/dev/null
  fi
}
THIRD_PARTY=$(py_scan | grep -E '^\+?\s*(import|from) ' \
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
  # A PASS THAT SWALLOWED A NON-RUN IS A FALSE PASS. verify_geometry.py can only
  # decode card QRs where macOS Vision exists; off macOS it prints the marker
  # below and exits 0, which used to arrive here as a plain green tick over every
  # card QR assertion — twenty of them today — that never ran. The log is only
  # ever shown on failure, and only from /FAILED/ onward, so the words "This is
  # NOT a pass" were unreachable from this transcript. Grep for the marker so the
  # tick can never outrun the check.
  if grep -q 'QR-DECODE-DID-NOT-RUN' /tmp/_vc_geom.log; then
    say "  –  6. mm pipeline exact — but NO card QR was decoded on this platform (macOS only); that half is unchecked, not passed"
  else
    pass "6. mm pipeline exact (placement, bleed, calibration, slot fit)"
  fi
  # ECHO THE COVERAGE LINE ON SUCCESS, because the other honesty signal this gate
  # added is one that never fails by design — it reports how many QR-bearing
  # artifacts are bound to a registry row. A registry that quietly loses rows
  # collapses that number while this transcript still prints a green tick, and the
  # log is shown only on failure. The same argument as the grep above; the same
  # answer.
  grep 'QR coverage' /tmp/_vc_geom.log | sed 's/^ *--  */      /' || true
else
  # NAME THE ACTUAL CAUSE. Every failure in this step used to be announced as a
  # geometry regression, which sent whoever hit it to debug a placement pipeline
  # that was fine — the common case on a fresh clone is the QR decoder, not a
  # millimetre.
  if grep -q 'QR decoder builds' /tmp/_vc_geom.log; then
    fail "6. QR DECODER DID NOT BUILD — swiftc tools/qrdecode.swift -o tools/qrdecode (geometry itself is fine)"
  else
    fail "6. GEOMETRY REGRESSION — a placement no longer lands where it was asked to"
  fi
  sed -n '/FAILED/,$p' /tmp/_vc_geom.log | sed 's/^/      /'
fi

# ── the chip ──────────────────────────────────────────────────────────────
# A GATE NOTHING RUNS IS A GATE THAT DOES NOT EXIST, and until this line
# tools/verify_nfc_guard.py was that: the ONLY suite covering the HTTP guard and
# the NFC write path, invoked by no workflow, and not by this script either —
# which printed GATE CLEAR without it. CLAUDE.md says to run it "after any change
# here", so the guard against two live exploits that were actually reproduced
# (a page reading ~/.docker/config.json, any site driving the printer) rested
# entirely on an agent remembering a sentence in a README.
#
# It belongs in the cheap tier and always did: no reader, no network, about a
# second. The suite asserts its own inability to write to a tag, for the reason
# documented at the top of that file — so running it here cannot cost a card.
#
# Deliberately NOT wrapped in a "skip if the module is missing" arm. That is the
# shape that turns a security suite into decoration: it would go green on the
# machine where it could not run, which is the same false pass the geometry step
# above had to grow a grep to kill.
say ""
say "── the chip ─────────────────────────────────────────────────────"
if python3 "$(dirname "$0")/verify_nfc_guard.py" >/tmp/_vc_nfc.log 2>&1; then
  pass "6b. NFC guard suite (page-225 write ceiling, both-directions validation, one-reader lock)"
else
  fail "6b. NFC GUARD SUITE FAILED — the chip write path or the HTTP guard regressed"
  tail -n 40 /tmp/_vc_nfc.log | sed 's/^/      /'
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
# Always build fresh. This used to read `[ -d _site_mobile ] || build`, so an
# existing directory skipped the build and got measured instead — and build()
# writes index.html BEFORE it can refuse, so a REFUSED build still leaves one
# behind. The next run then measured the wreckage of the previous one and passed
# it. Caught exactly that way: with the manifest deleted, this gate printed
# "✓ 8. watertight" off a stale tree. A cache keyed on nothing is not a cache.
rm -rf _site_mobile
if python3 tools/build_site.py _site_mobile >/dev/null 2>&1; then
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

  # 9. The PUBLISHED artifact — checked by the gate a contributor actually runs.
  #
  # This existed only in .github/workflows/pages.yml, so the site was verified by
  # CI and by nothing a person could run. CLAUDE.md calls this script "the
  # mechanical gate" and tells you to clear it before calling anything done; you
  # could clear it green having changed the builder, and learn nothing about
  # whether the site still serves what a card points at. build_site.py's own
  # header already names this failure: "a check that cannot pass gets ignored,
  # and an ignored check is the same as no check with extra steps." The variant
  # here is worse, because this one passes — it just was not asked.
  #
  # Free to add: the block above ALREADY builds the whole site to measure mobile
  # and then deletes it. The artifact was passing through this gate's hands
  # unexamined. Both surfaces are checked, because they are different documents
  # under different rules — the landing page owes a manifest at its well-known
  # path, the studio app owes its backend and script order.
  say ""
  say "── published artifact ───────────────────────────────────────────"
  if node tools/verify_pages_artifact.mjs _site_mobile >/tmp/_vc_pages.log 2>&1 &&
     node tools/verify_pages_artifact.mjs _site_mobile/studio >>/tmp/_vc_pages.log 2>&1; then
    pass "9. published artifact complete (landing + studio; manifest present, parsing, byte-identical)"
  else
    fail "9. PUBLISHED ARTIFACT INCOMPLETE — the deploy would go green over a dead site"
    grep -E "^  FAIL" /tmp/_vc_pages.log | head -8 | sed 's/^/    /'
  fi

  rm -rf _site_mobile
else
  fail "8. could not build the site to measure it"
  # ...and say WHY. The builder refuses with a reason on stderr and this branch
  # threw it away, so a missing manifest surfaced as "could not build the site"
  # under the MOBILE heading — a true sentence pointing at the wrong thing. Same
  # scar build_site.py records in its own main(): stopping the pipeline is only
  # half of it, the gate still has to name what stopped it. Re-run for the
  # message alone; a build that just failed is cheap and this path is rare.
  python3 tools/build_site.py _site_mobile 2>&1 >/dev/null | grep -E "^FAIL" | head -3 | sed 's/^/    /'
  rm -rf _site_mobile
fi

# ── committed tree ────────────────────────────────────────────────────────
#
# 10. Every page the builder publishes must be a page the DEPLOY can build.
#
# Check 9 above says a deploy must not "go green over a dead site", and then
# checks the site it built from the WORKING TREE. The deploy builds from the
# COMMITTED tree. Those are different trees, and the difference is invisible to
# every other check in this file, because an untracked file is a real file: it
# opens, it parses, build_site.py copies it, the artifact verifier finds it, and
# the whole gate goes green over a page that does not exist for anyone else.
#
# It happened. src/site/bloom/index.html was written and never `git add`ed,
# while the two PNGs beside it were added and pushed. So the live directory
# existed and served its own artwork — measured 2026-08-15:
#
#   /vibe-cards/bloom/card-front.png -> 200
#   /vibe-cards/bloom/            -> 404
#
# A printed card whose QR code is ink scanned to a 404 in the same folder as its
# own picture, for as long as nobody looked. That URL is permanent; the page
# behind it was optional right up until it was not.
#
# Scoped to src/site/ on purpose — that is the published surface, where an
# untracked file is a broken promise rather than work in progress. Tripping on
# your own new page is the point, and `git add` clears it in a second.
say ""
say "── committed tree ───────────────────────────────────────────────"
UNTRACKED_SITE=$(git ls-files --others --exclude-standard -- src/site 2>/dev/null)
if [ -z "$UNTRACKED_SITE" ]; then
  pass "10. every published page is committed (the deploy builds the same site this gate just checked)"
else
  fail "10. UNTRACKED PAGE ON THE PUBLISHED SURFACE — this gate can see it, the deploy cannot"
  printf '%s\n' "$UNTRACKED_SITE" | while IFS= read -r f; do
    # Name the URL, not just the path. "src/site/bloom/index.html is untracked"
    # is a fact about git; "/bloom/ will 404" is the thing a card holder meets.
    url=${f#src/site/}; url=${url%index.html}
    printf '      %s\n        → https://mrdirno.github.io/vibe-cards/%s would 404. Fix: git add %s\n' "$f" "$url" "$f"
  done
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
