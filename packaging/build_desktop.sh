#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_PATH="$ROOT_DIR/packaging/neurogame.spec"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

cd "$ROOT_DIR"

echo "[1/4] Installing packaging dependency (PyInstaller)..."
python -m pip install --upgrade pyinstaller

echo "[2/4] Building desktop executable..."
python -m PyInstaller --noconfirm --clean "$SPEC_PATH"

echo "[3/4] Preparing release archive..."
mkdir -p "$DIST_DIR"
PLATFORM_TAG="$(python - <<'PY'
import platform
print(f"{platform.system().lower()}-{platform.machine().lower()}")
PY
)"
ARCHIVE_BASENAME="neurogame-${PLATFORM_TAG}"

if [[ -f "$DIST_DIR/NeuroGame" ]]; then
  ARCHIVE_PATH="$DIST_DIR/${ARCHIVE_BASENAME}.zip"
  rm -f "$ARCHIVE_PATH"
  (cd "$DIST_DIR" && zip -q -r "$(basename "$ARCHIVE_PATH")" "NeuroGame")
elif [[ -f "$DIST_DIR/NeuroGame.exe" ]]; then
  ARCHIVE_PATH="$DIST_DIR/${ARCHIVE_BASENAME}.zip"
  rm -f "$ARCHIVE_PATH"
  (cd "$DIST_DIR" && zip -q -r "$(basename "$ARCHIVE_PATH")" "NeuroGame.exe")
else
  echo "Build output not found in $DIST_DIR."
  exit 1
fi

echo "[4/4] Done."
echo "Executable: $DIST_DIR/NeuroGame (or NeuroGame.exe)"
echo "Archive: $ARCHIVE_PATH"
echo
echo "To run built app:"
echo "  $DIST_DIR/NeuroGame"

