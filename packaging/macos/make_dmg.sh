#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="NeuroGame"
APP_DIR="$DIST_DIR/${APP_NAME}.app"
DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"
STAGE_DIR="$DIST_DIR/dmg-stage"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Expected app bundle not found: $APP_DIR"
  exit 1
fi

codesign --force --deep --sign - "$APP_DIR" || true

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$APP_DIR" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create -volname "NeuroGame" -srcfolder "$STAGE_DIR" -ov -format UDZO "$DMG_PATH"
rm -rf "$STAGE_DIR"
echo "DMG created: $DMG_PATH"
