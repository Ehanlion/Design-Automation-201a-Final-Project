#!/usr/bin/env bash
# Copy a submission tarball into an isolated test sandbox, extract it, and run
# the bundled scripts/run_all.sh from the extracted tree. To avoid keeping two
# ngspice builds on disk at once, this temporarily removes the original
# project's ngspice tree, runs the extracted submission, then reinstalls
# ngspice in the original project afterward.
#
# Usage:
#   ./scripts/test_tar.sh [TAR_PATH|GROUP_DIRNAME]

set -euo pipefail

PIN="1234"
DEFAULT_GROUP="Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT="$ROOT_DIR/_testing"
SOURCE_ARG="${1:-}"

SOURCE_ARG="${SOURCE_ARG//$'\r'/}"

MAIN_PROJECT_ROOT=""
MAIN_PROJECT_INSTALLER=""
MAIN_PROJECT_NGSPICE_ROOT=""
MAIN_PROJECT_NGSPICE_REMOVED=0
EXTRACTED_DIR=""
EXTRACTED_NGSPICE_ROOT=""
EXTRACTED_VENV_DIR=""

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

tar_root_dir() {
  local tar_path="$1"
  local roots
  local root_count

  roots="$(tar -tzf "$tar_path" | awk -F/ 'NF {print $1}' | sed '/^$/d' | sort -u)"
  root_count="$(printf '%s\n' "$roots" | sed '/^$/d' | wc -l | tr -d '[:space:]')"

  [[ "$root_count" == "1" ]] || fail "Expected exactly one top-level directory in tarball, found $root_count."
  printf '%s\n' "$roots" | sed -n '1p'
}

find_main_project_root() {
  local extracted_dir="$1"
  local current

  current="$(cd "$extracted_dir/../.." && pwd)"
  while [[ "$current" != "/" ]]; do
    if [[ -f "$current/setup/install_local_ngspice.sh" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    current="$(dirname "$current")"
  done

  return 1
}

clean_directory_contents() {
  local dir="$1"

  [[ -d "$dir" ]] || return 0
  find "$dir" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
}

remove_ngspice_tree() {
  local path="$1"
  local label="$2"

  [[ -n "$path" ]] || fail "Refusing to remove empty path for $label."
  [[ -d "$path" ]] || return 0

  echo "--- Removing $label ---"
  echo "Path: $path"
  rm -rf "$path"
}

restore_project_ngspice() {
  local exit_code="$1"
  local restore_code=0

  trap - EXIT
  set +e

  if [[ -n "$EXTRACTED_NGSPICE_ROOT" && -d "$EXTRACTED_NGSPICE_ROOT" ]]; then
    echo ""
    remove_ngspice_tree "$EXTRACTED_NGSPICE_ROOT" "extracted submission ngspice tree"
  fi

  if [[ -n "$EXTRACTED_VENV_DIR" && -d "$EXTRACTED_VENV_DIR" ]]; then
    echo "--- Removing extracted submission virtualenv ---"
    echo "Path: $EXTRACTED_VENV_DIR"
    rm -rf "$EXTRACTED_VENV_DIR"
  fi

  if [[ "$MAIN_PROJECT_NGSPICE_REMOVED" -eq 1 ]]; then
    echo ""
    echo "--- Restoring original project ngspice ---"
    echo "Installer: $MAIN_PROJECT_INSTALLER"
    bash "$MAIN_PROJECT_INSTALLER"
    restore_code=$?
    if [[ "$restore_code" -ne 0 ]]; then
      echo "[ERROR] Failed to reinstall ngspice in the original project." >&2
    fi
  fi

  if [[ "$exit_code" -ne 0 ]]; then
    echo ""
    echo "[ERROR] Tar test failed with exit code $exit_code." >&2
    exit "$exit_code"
  fi

  if [[ "$restore_code" -ne 0 ]]; then
    exit "$restore_code"
  fi
}

trap 'restore_project_ngspice "$?"' EXIT

TAR_PATH="$(resolve_tar_path "$SOURCE_ARG")"
COPIED_TAR="$TEST_ROOT/$(basename "$TAR_PATH")"

[[ -f "$TAR_PATH" ]] || fail "Tarball not found: $TAR_PATH"

mkdir -p "$TEST_ROOT"
[[ "$TEST_ROOT" == "$ROOT_DIR/_testing" ]] || fail "Refusing to clean unexpected test directory: $TEST_ROOT"

echo "=== Preparing isolated tar test ==="
echo "Source tar : $TAR_PATH"
echo "Test dir   : $TEST_ROOT"

clean_directory_contents "$TEST_ROOT"
ln -f "$TAR_PATH" "$COPIED_TAR" 2>/dev/null || cp -f "$TAR_PATH" "$COPIED_TAR"
cmp -s "$TAR_PATH" "$COPIED_TAR" || fail "Copied tarball does not match source tarball."

EXTRACTED_ROOT="$(tar_root_dir "$COPIED_TAR")"
EXTRACTED_DIR="$TEST_ROOT/$EXTRACTED_ROOT"
RUN_ALL_SCRIPT="$EXTRACTED_DIR/scripts/run_all.sh"

echo "Copied tar : $COPIED_TAR"
echo "Extracting : $EXTRACTED_ROOT"
tar -xzf "$COPIED_TAR" -C "$TEST_ROOT"

[[ -d "$EXTRACTED_DIR" ]] || fail "Extracted project directory not found: $EXTRACTED_DIR"
[[ -f "$RUN_ALL_SCRIPT" ]] || fail "run_all.sh not found in extracted tarball: $RUN_ALL_SCRIPT"

MAIN_PROJECT_ROOT="$(find_main_project_root "$EXTRACTED_DIR")" || fail "Could not locate the original project root above $EXTRACTED_DIR."
MAIN_PROJECT_INSTALLER="$MAIN_PROJECT_ROOT/setup/install_local_ngspice.sh"
MAIN_PROJECT_NGSPICE_ROOT="$MAIN_PROJECT_ROOT/third_party/ngspice"
EXTRACTED_NGSPICE_ROOT="$EXTRACTED_DIR/third_party/ngspice"
EXTRACTED_VENV_DIR="$EXTRACTED_DIR/.venv"

[[ -f "$MAIN_PROJECT_INSTALLER" ]] || fail "Original ngspice installer not found: $MAIN_PROJECT_INSTALLER"

echo ""
echo "=== Original project detected ==="
echo "Project root : $MAIN_PROJECT_ROOT"
echo "Installer    : $MAIN_PROJECT_INSTALLER"

if [[ -d "$MAIN_PROJECT_NGSPICE_ROOT" ]]; then
  echo ""
  remove_ngspice_tree "$MAIN_PROJECT_NGSPICE_ROOT" "original project ngspice tree"
  MAIN_PROJECT_NGSPICE_REMOVED=1
else
  echo ""
  echo "--- No original project ngspice tree found at $MAIN_PROJECT_NGSPICE_ROOT ---"
fi

echo ""
echo "=== Running extracted submission ==="
(
  cd "$EXTRACTED_DIR"
  bash "$RUN_ALL_SCRIPT"
)

echo ""
echo "=== Isolated tar test completed successfully ==="
