#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  build_mac.sh — builds VideoCheck-Setup.dmg
#  Must be run ON macOS (PyInstaller can't cross-compile).
#
#  Usage:
#    1. Install Python 3.10+ (brew install python) on your build Mac.
#    2. cd installer
#    3. ./build_mac.sh
#  Output: installer/dist/VideoCheck-Setup.dmg
# ─────────────────────────────────────────────────────────────
set -e

cd "$(dirname "$0")"

python3 -m pip install --upgrade pyinstaller

# --add-data "src:dest_inside_bundle" (macOS/Linux use : as separator)
python3 -m PyInstaller \
    --onefile \
    --name VideoCheck-Setup \
    --add-data "../video_check.py:." \
    --add-data "../preinstall.py:." \
    --add-data "../pyproject.toml:." \
    --add-data "../dashboard.html:." \
    --add-data "../Makefile:." \
    --add-data "../src:src" \
    bootstrap.py

APP_BIN="dist/VideoCheck-Setup"
DMG_STAGE="dist/dmg_stage"
DMG_OUT="dist/VideoCheck-Setup.dmg"

rm -rf "$DMG_STAGE" "$DMG_OUT"
mkdir -p "$DMG_STAGE"
cp "$APP_BIN" "$DMG_STAGE/VideoCheck-Setup"
ln -s /Applications "$DMG_STAGE/Applications"

hdiutil create -volname "VideoCheck Setup" \
    -srcfolder "$DMG_STAGE" \
    -ov -format UDZO \
    "$DMG_OUT"

echo ""
echo "  Build complete: $DMG_OUT"
echo "  Give this single file to non-technical users — double-click, run"
echo "  VideoCheck-Setup, done."
echo ""
echo "  Note: since this isn't code-signed / notarized with an Apple"
echo "  Developer ID, Gatekeeper will show a warning on first run. Users"
echo "  will need: right-click -> Open -> Open (once). To remove that"
echo "  warning entirely you'd need an Apple Developer account (\$99/yr)"
echo "  to sign + notarize the binary."
