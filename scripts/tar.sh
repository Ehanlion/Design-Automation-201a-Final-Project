#!/usr/bin/env bash
# Build submission tarball for EE 201A Final Project.
#
# Includes ONLY the files required to run therm.py from scratch:
#   - therm.py and all its Python dependencies
#   - configs/ directory (all XML files needed by therm.py and run scripts)
#   - output/ variable YAML files required by therm_xml_parser.py
#   - setup/ directory (requirements.txt + setup.sh for environment setup)
#   - scripts/ — run_all.sh and run_config*.sh
#
# Slides are optional: place Slides.pptx in lab_files/ or docs/ and it will be
# included automatically.
#
# Usage:
#   ./scripts/tar.sh [GROUP_DIRNAME]
#
# The resulting tarball unpacks to GroupName/ and can be run from inside:
#   cd GroupName
#   bash setup/setup.sh           # (optional: create venv)
#   bash scripts/run_all.sh       # runs all 3 configs
#
# PIN is fixed to 1234 per submission request.

set -euo pipefail

PIN="1234"
GROUP="${1:-Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SUBMIT_DIR="$ROOT_DIR/submission/${GROUP}"
TAR_NAME="${GROUP}_pin${PIN}.tar.gz"

echo "=== Building submission tarball ==="
echo "Group dir : $GROUP"
echo "Staging   : $SUBMIT_DIR"
echo "Tarball   : submission/$TAR_NAME"
echo ""

rm -rf "$SUBMIT_DIR"
mkdir -p "$SUBMIT_DIR"

# ---------------------------------------------------------------------------
# Core Python source files (therm.py + all imported dependencies)
# ---------------------------------------------------------------------------
PY_FILES=(
  therm.py
  thermal_solver.py
  therm_xml_parser.py
  bonding_xml_parser.py
  heatsink_xml_parser.py
  rearrange.py
  visualize_results.py
  convert_golden_output.py
  compare_to_golden.py
  lextab.py
  yacctab.py
)

echo "--- Python source files ---"
for f in "${PY_FILES[@]}"; do
  if [[ -f "$ROOT_DIR/$f" ]]; then
    cp "$ROOT_DIR/$f" "$SUBMIT_DIR/"
    echo "  $f"
  else
    echo "[WARN] Missing expected file: $f" >&2
  fi
done

# ---------------------------------------------------------------------------
# Helper: rsync a directory tree, skipping .pyc / __pycache__ / .pkl
# ---------------------------------------------------------------------------
copy_dir() {
  local label="$1"
  local d="$2"
  shift 2
  local extra_excludes=("$@")
  if [[ -d "$ROOT_DIR/$d" ]]; then
    local rsync_args=(-a --exclude='*.pyc' --exclude='__pycache__' --exclude='*.pkl')
    for excl in "${extra_excludes[@]}"; do
      rsync_args+=(--exclude="$excl")
    done
    rsync "${rsync_args[@]}" "$ROOT_DIR/$d" "$SUBMIT_DIR/"
    echo "  $d/"
  else
    echo "[WARN] Missing expected dir: $d ($label)" >&2
  fi
}

# ---------------------------------------------------------------------------
# configs/ — all XML files needed by therm.py (layers, bonding, heatsink,
#             system configs used by the run scripts)
# output/  — variable YAML files consumed by therm_xml_parser.py
# setup/   — requirements.txt + setup.sh for environment reproducibility
# ---------------------------------------------------------------------------
echo ""
echo "--- Config and setup directories ---"
copy_dir "SPICE/therm configs" "configs"
copy_dir "output variable files" "output"
copy_dir "environment setup"   "setup"
copy_dir "golden reference outputs" "solutions"

# ---------------------------------------------------------------------------
# scripts/ — run scripts included in the submission bundle
# ---------------------------------------------------------------------------
echo ""
echo "--- Run scripts ---"
mkdir -p "$SUBMIT_DIR/scripts"
SCRIPT_FILES=(
  run_all.sh
  run_config1_3D_gpu_top.sh
  run_config2_3D_gpu_bottom.sh
  run_config3_2p5D.sh
)
for f in "${SCRIPT_FILES[@]}"; do
  if [[ -f "$ROOT_DIR/scripts/$f" ]]; then
    cp "$ROOT_DIR/scripts/$f" "$SUBMIT_DIR/scripts/"
    echo "  scripts/$f"
  else
    echo "[WARN] Missing expected script: scripts/$f" >&2
  fi
done

# ---------------------------------------------------------------------------
# Ensure all packaged shell scripts are executable inside the archive
# ---------------------------------------------------------------------------
chmod +x "$SUBMIT_DIR/scripts/"*.sh 2>/dev/null || true
chmod +x "$SUBMIT_DIR/setup/"*.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
# Slides PPTX (optional — warning only if missing)
# ---------------------------------------------------------------------------
echo ""
echo "--- Slides (optional) ---"
SLIDES_ASSET="Slides.pptx"
if [[ -f "$ROOT_DIR/lab_files/$SLIDES_ASSET" ]]; then
  cp "$ROOT_DIR/lab_files/$SLIDES_ASSET" "$SUBMIT_DIR/"
  echo "  $SLIDES_ASSET (from lab_files/)"
elif [[ -f "$ROOT_DIR/docs/$SLIDES_ASSET" ]]; then
  cp "$ROOT_DIR/docs/$SLIDES_ASSET" "$SUBMIT_DIR/"
  echo "  $SLIDES_ASSET (from docs/)"
else
  echo "  [WARN] $SLIDES_ASSET not found — add it before final submission." >&2
fi

# ---------------------------------------------------------------------------
# Create out_therm/ placeholder so the run scripts can find the dir
# ---------------------------------------------------------------------------
mkdir -p "$SUBMIT_DIR/out_therm"

# ---------------------------------------------------------------------------
# Make the extracted tree editable by anyone, while keeping shell entrypoints
# directly runnable after untarring.
# ---------------------------------------------------------------------------
chmod -R a+rwX "$SUBMIT_DIR"
find "$SUBMIT_DIR/scripts" "$SUBMIT_DIR/setup" -type f -name '*.sh' -exec chmod a+rwx {} +

# ---------------------------------------------------------------------------
# Pack tarball — preserves full GroupName/ directory structure on untar
# ---------------------------------------------------------------------------
echo ""
mkdir -p "$ROOT_DIR/submission"
tar -czf "$ROOT_DIR/submission/$TAR_NAME" -C "$ROOT_DIR/submission" "$GROUP"
echo "=== Tarball created: submission/$TAR_NAME ==="
echo ""
echo "Contents (first 80 entries):"
tar -tzf "$ROOT_DIR/submission/$TAR_NAME" | head -80
echo ""
echo "To verify, untar with:"
echo "  tar -xzf submission/$TAR_NAME"
echo "  cd $GROUP && bash scripts/run_all.sh"
