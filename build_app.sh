#!/usr/bin/env bash
# Build "Card Studio.app" — a self-contained double-clickable macOS bundle.
#
# Self-contained on purpose: the source may live on an external volume, and an
# app that referenced it would break whenever that drive was unplugged. The
# bundle carries its own copy of everything it runs.
#
#   ./build_app.sh                 → builds to ~/Desktop/Card Studio.app
#   ./build_app.sh /Applications   → builds there instead

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${1:-$HOME/Desktop}"
APP="$DEST_DIR/Card Studio.app"
CONTENTS="$APP/Contents"
VERSION="1.0.0"

echo "▸ building $APP"

# ── icon ─────────────────────────────────────────────────────────────────
if [ ! -f "$SRC_DIR/src/assets/AppIcon.icns" ]; then
  echo "▸ generating icon"
  PY="$(command -v python3)"
  "$PY" "$SRC_DIR/src/make_icon.py" || echo "  (icon generation failed — bundle will use the default icon)"
fi

# ── bundle skeleton ──────────────────────────────────────────────────────
rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>                 <string>Card Studio</string>
  <key>CFBundleDisplayName</key>          <string>Card Studio</string>
  <key>CFBundleIdentifier</key>           <string>com.persona500.cardstudio</string>
  <key>CFBundleExecutable</key>           <string>CardStudio</string>
  <key>CFBundleIconFile</key>             <string>AppIcon</string>
  <key>CFBundlePackageType</key>          <string>APPL</string>
  <key>CFBundleShortVersionString</key>   <string>$VERSION</string>
  <key>CFBundleVersion</key>              <string>$VERSION</string>
  <key>LSMinimumSystemVersion</key>       <string>12.0</string>
  <key>NSHighResolutionCapable</key>      <true/>
  <key>LSApplicationCategoryType</key>    <string>public.app-category.graphics-design</string>
  <key>NSHumanReadableCopyright</key>     <string>Persona 500 LLC</string>
</dict>
</plist>
PLIST

# ── payload ──────────────────────────────────────────────────────────────
cp -R "$SRC_DIR/src/." "$CONTENTS/Resources/app/"
rm -rf "$CONTENTS/Resources/app/assets/AppIcon.iconset" \
       "$CONTENTS/Resources/app/__pycache__" 2>/dev/null || true

if [ -f "$SRC_DIR/src/assets/AppIcon.icns" ]; then
  cp "$SRC_DIR/src/assets/AppIcon.icns" "$CONTENTS/Resources/AppIcon.icns"
fi

# ── launcher ─────────────────────────────────────────────────────────────
cat > "$CONTENTS/MacOS/CardStudio" <<'LAUNCHER'
#!/bin/bash
# Card Studio launcher. Finds a usable python3, then hands off to the app
# server, which opens the UI window itself.

HERE="$(cd "$(dirname "$0")/../Resources/app" && pwd)"
SUPPORT="$HOME/Library/Application Support/Card Studio"
mkdir -p "$SUPPORT"
LOG="$SUPPORT/launch.log"

# Already running? Re-open its window instead of starting a second server.
PORTFILE="$SUPPORT/port"
if [ -f "$PORTFILE" ]; then
  PORT="$(cat "$PORTFILE")"
  if curl -sf -m 1 "http://127.0.0.1:$PORT/api/ping" >/dev/null 2>&1; then
    # Focus the existing app window. `open <url>` would hand it to the default
    # browser instead, which reads as the app doing nothing.
    if [ -d "/Applications/Google Chrome.app" ]; then
      open -na "/Applications/Google Chrome.app" --args \
        "--app=http://127.0.0.1:$PORT/" "--user-data-dir=$SUPPORT/browser" \
        --no-first-run --no-default-browser-check
    else
      open "http://127.0.0.1:$PORT/"
    fi
    exit 0
  fi
fi

PY=""
for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)" /usr/bin/python3; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
  osascript -e 'display alert "Card Studio needs Python 3" message "No python3 was found. Install the Xcode Command Line Tools (xcode-select --install) or Homebrew python, then reopen Card Studio." as critical'
  exit 1
fi

cd "$HERE" || exit 1
exec "$PY" server.py >>"$LOG" 2>&1
LAUNCHER

chmod +x "$CONTENTS/MacOS/CardStudio"

# Refresh the Finder's icon cache — otherwise a rebuilt bundle keeps the
# generic icon until the next login.
touch "$APP"
/usr/bin/touch "$CONTENTS/Info.plist"

echo "✓ built: $APP"
[ -f "$CONTENTS/Resources/AppIcon.icns" ] && echo "✓ icon:  $(du -h "$CONTENTS/Resources/AppIcon.icns" | cut -f1)"
echo "  double-click it, or:  open -a \"$APP\""
