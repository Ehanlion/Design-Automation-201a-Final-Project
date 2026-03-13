#!/usr/bin/env bash
# Copy a submission tarball into the class handin directory and verify it.
#
# Usage:
#   ./scripts/submit.sh [TAR_PATH|GROUP_DIRNAME] [TARGET_DIR]

set -euo pipefail

PIN="1234"
DEFAULT_GROUP="Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project"
DEFAULT_TARGET_DIR="/w/class.1/ee/ee201o/ee201ot2/submission/project/"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_ARG="${1:-}"
TARGET_DIR="${2:-$DEFAULT_TARGET_DIR}"

SOURCE_ARG="${SOURCE_ARG//$'\r'/}"
TARGET_DIR="${TARGET_DIR//$'\r'/}"

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

resolve_tar_path() {
  local arg="$1"

  if [[ -z "$arg" ]]; then
    echo "$ROOT_DIR/submission/${DEFAULT_GROUP}_pin${PIN}.tar.gz"
    return
  fi

  if [[ "$arg" == *.tar.gz ]]; then
    if [[ -f "$arg" ]]; then
      echo "$arg"
    else
      echo "$ROOT_DIR/$arg"
    fi
    return
  fi

  echo "$ROOT_DIR/submission/${arg}_pin${PIN}.tar.gz"
}

TAR_PATH="$(resolve_tar_path "$SOURCE_ARG")"
DEST_PATH="$TARGET_DIR/$(basename "$TAR_PATH")"

[[ -f "$TAR_PATH" ]] || fail "Tarball not found: $TAR_PATH"
[[ -d "$TARGET_DIR" ]] || fail "Submission directory does not exist: $TARGET_DIR"
[[ -x "$TARGET_DIR" ]] || fail "Submission directory is not searchable: $TARGET_DIR"
[[ -w "$TARGET_DIR" ]] || fail "Submission directory is not writable: $TARGET_DIR"

echo "=== Submitting tarball ==="
echo "Source : $TAR_PATH"
echo "Target : $DEST_PATH"

cp -f "$TAR_PATH" "$DEST_PATH"

[[ -f "$DEST_PATH" ]] || fail "Copied file is not visible in target directory: $DEST_PATH"
cmp -s "$TAR_PATH" "$DEST_PATH" || fail "Copied file does not match source tarball."
tar -tzf "$DEST_PATH" >/dev/null || fail "Copied tarball is not readable as a valid .tar.gz archive."

echo "=== Submission verified ==="
echo "Copied file exists in the class submission directory and matches the source tarball."
