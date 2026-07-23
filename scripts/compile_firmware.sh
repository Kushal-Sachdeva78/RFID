#!/usr/bin/env bash
# Compile Main.ino for the ESP32 DevKit V1 without moving the sketch.
#
# arduino-cli requires a sketch's .ino to sit in a folder of the same base name
# (Main/Main.ino). Rather than move the tracked Main.ino from the repo root
# (which would break the README link and external references), this script
# copies it into build/Main/Main.ino and compiles that copy.
#
# Prerequisites (run once, or let CI do it):
#   arduino-cli core install esp32:esp32
#   arduino-cli lib install "MFRC522" "Adafruit GFX Library" "Adafruit ILI9341"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKETCH_SRC="$REPO_ROOT/Main.ino"
BUILD_DIR="$REPO_ROOT/build/Main"
FQBN="esp32:esp32:esp32doit-devkit-v1"

CLI="${ARDUINO_CLI:-arduino-cli}"
if ! command -v "$CLI" >/dev/null 2>&1; then
  # Fall back to the default winget install location on Windows.
  CLI="/c/Program Files/Arduino CLI/arduino-cli.exe"
fi

mkdir -p "$BUILD_DIR"
cp "$SKETCH_SRC" "$BUILD_DIR/Main.ino"

echo "Compiling Main.ino for $FQBN ..."
"$CLI" compile --fqbn "$FQBN" "$BUILD_DIR" --warnings all
