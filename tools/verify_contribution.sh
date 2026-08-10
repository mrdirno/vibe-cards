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
if [ "$MODE" = "--all" ]; then
  SCAN_CMD='cat src/server.py src/pdfwriter.py src/web/app.js'
  say "▸ scanning ENTIRE tree"
elif git rev-parse --git-dir >/dev/null 2>&1; then
  SCAN_CMD='git diff HEAD -- src/ | grep "^+" | grep -v "^+++"'
  say "▸ scanning working tree vs HEAD (use --all for everything)"
else
  SCAN_CMD='cat src/server.py src/pdfwriter.py src/web/app.js'
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
if scan | grep -nE 'urllib\.request|http\.client|requests\.(get|post)|fetch\(["'"'"']https?://|socket\.create_connection'; then
  fail "3. new outbound network call"
else
  pass "3. no new network egress"
fi

# 4. third-party imports. Stdlib-only is a feature: it is why there is no install
#    step. Pillow is the ONE allowed optional dependency — every use is inside a
#    try/except with a working fallback (HAS_PIL), so a machine without it still
#    runs. A second optional dependency needs that same treatment and a README line.
THIRD_PARTY=$(scan | grep -E '^\+?\s*(import|from) ' \
  | grep -vE '(import|from)\s+(__future__|base64|glob|json|os|plistlib|re|secrets|shutil|socket|subprocess|sys|threading|time|traceback|urllib|datetime|http\.server|pathlib|typing|math|struct|zlib|io|hashlib|tempfile|argparse|textwrap|collections|functools|itertools|pdfwriter)\b' \
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
if python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in ('src/server.py','src/pdfwriter.py')]" 2>/dev/null; then
  pass "5a. python parses"
else
  fail "5a. python syntax error"; python3 -c "import ast; ast.parse(open('src/server.py').read())" 2>&1 | tail -3
fi

if command -v node >/dev/null 2>&1; then
  if node --check src/web/app.js 2>/dev/null; then
    pass "5b. app.js parses"
  else
    fail "5b. app.js syntax error"; node --check src/web/app.js 2>&1 | tail -3
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

say ""
if [ "$FAIL" -eq 0 ]; then
  say "GATE CLEAR — now do the human half (SECURITY.md 6-8)."
  say "  6. Does this widen what an unauthenticated request reaches?"
  say "  7. New route? Confirm _guard still covers it."
  say "  8. Security-relevant? Default verdict is REFUTED until an independent"
  say "     pass fails to break it, citing the lines that make it safe."
else
  say "GATE TRIPPED — see the ✗ lines above."
fi
exit "$FAIL"
