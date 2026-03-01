#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

cd "$ROOT_DIR"

echo "[1/4] Installing packaging dependency (PyInstaller)..."
python -m pip install --upgrade pyinstaller

echo "[2/4] Building desktop executable..."
if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* ]]; then
  ADD_DATA_SEP=";"
else
  ADD_DATA_SEP=":"
fi
ASSETS_DIR="$ROOT_DIR/game/assets"
ADD_DATA_ARGS=()
if [[ -d "$ROOT_DIR/data" ]]; then
  ADD_DATA_ARGS+=(--add-data "$ROOT_DIR/data${ADD_DATA_SEP}data")
else
  echo "Warning: optional data directory not found, skipping: $ROOT_DIR/data"
fi
if [[ -d "$ASSETS_DIR" ]]; then
  ADD_DATA_ARGS+=(--add-data "$ASSETS_DIR${ADD_DATA_SEP}game/assets")
else
  echo "Required assets directory not found: $ASSETS_DIR"
  exit 1
fi
if [[ "$OSTYPE" == "darwin"* ]]; then
  python -m PyInstaller --noconfirm --clean --windowed --name NeuroGame \
    "${ADD_DATA_ARGS[@]}" \
    "$ROOT_DIR/main.py"
else
  python -m PyInstaller --noconfirm --clean --onefile --windowed --name NeuroGame \
    "${ADD_DATA_ARGS[@]}" \
    "$ROOT_DIR/main.py"
fi

echo "[3/4] Preparing release archive..."
mkdir -p "$DIST_DIR"
PLATFORM_TAG="$(python - <<'PY'
import platform
print(f"{platform.system().lower()}-{platform.machine().lower()}")
PY
)"
ARCHIVE_BASENAME="neurogame-${PLATFORM_TAG}"

if [[ -d "$DIST_DIR/NeuroGame.app" ]]; then
  ARCHIVE_PATH="$DIST_DIR/${ARCHIVE_BASENAME}.zip"
  rm -f "$ARCHIVE_PATH"
  (cd "$DIST_DIR" && zip -q -r "$(basename "$ARCHIVE_PATH")" "NeuroGame.app")
elif [[ -f "$DIST_DIR/NeuroGame" ]]; then
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
