#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$PROJECT_DIR/out_therm"

if [ ! -d "$OUT_DIR" ]; then
    echo "No out_therm directory found at: $OUT_DIR"
    exit 0
fi

echo "Cleaning generated files in: $OUT_DIR"
echo "Preserving:"
echo "  - $OUT_DIR/archive/**"
echo "  - Archive files (*.zip, *.tar, *.tar.gz, *.tgz, *.gz, *.bz2, *.xz, *.7z, *.rar)"

find "$OUT_DIR" -mindepth 1 \
    -type f \
    ! -path "$OUT_DIR/archive/*" \
    ! -name '*.zip' ! -name '*.tar' ! -name '*.tar.gz' ! -name '*.tgz' ! -name '*.gz' \
    ! -name '*.bz2' ! -name '*.xz' ! -name '*.7z' ! -name '*.rar' \
    -print -delete

echo "Done."
