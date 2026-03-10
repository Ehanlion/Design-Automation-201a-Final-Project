#!/usr/bin/env bash
# Build submission tarball with code dependencies + Report/Slides.
# Usage: ./scripts/make_submission_tar.sh
# PIN is fixed to 1234 per submission request.

set -euo pipefail

PIN="1234"
GROUP="${1:-Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SUBMIT_DIR="$ROOT_DIR/submission/${GROUP}"
TAR_NAME="${GROUP}_pin${PIN}.tar.gz"

echo "Creating submission directory: $SUBMIT_DIR"
rm -rf "$SUBMIT_DIR"
mkdir -p "$SUBMIT_DIR"

# Core python files
PY_FILES=(
  therm.py
  thermal_solver.py
  therm_xml_parser.py
  bonding_xml_parser.py
  heatsink_xml_parser.py
  rearrange.py
  visualize_results.py
  summarize_results.py
  README.md
)

for f in "${PY_FILES[@]}"; do
  if [[ -f "$ROOT_DIR/$f" ]]; then
    cp "$ROOT_DIR/$f" "$SUBMIT_DIR/"
  else
    echo "[WARN] Missing expected file: $f" >&2
  fi
done

# Required supporting dirs (structure preserved)
copy_dir() {
  local d="$1"
  if [[ -d "$ROOT_DIR/$d" ]]; then
    rsync -a --exclude='*.pyc' --exclude='__pycache__' "$ROOT_DIR/$d" "$SUBMIT_DIR/"
  else
    echo "[WARN] Missing expected dir: $d" >&2
  fi
}

for d in configs setup output; do
  copy_dir "$d"
done

# Only the run scripts + summarize script from scripts/
mkdir -p "$SUBMIT_DIR/scripts"
for f in run_all.sh run_config1_3D_gpu_top.sh run_config2_3D_gpu_bottom.sh run_config3_2p5D.sh summarize_all.sh; do
  if [[ -f "$ROOT_DIR/scripts/$f" ]]; then
    cp "$ROOT_DIR/scripts/$f" "$SUBMIT_DIR/scripts/"
  else
    echo "[WARN] Missing expected script: scripts/$f" >&2
  fi
done

# Pull report/slides from lab_files if present; place beside therm.py
for asset in Report.pdf Slides.pptx; do
  if [[ -f "$ROOT_DIR/lab_files/$asset" ]]; then
    cp "$ROOT_DIR/lab_files/$asset" "$SUBMIT_DIR/"
  else
    echo "[WARN] $asset not found in lab_files/. Add it before rerunning." >&2
  fi
done

mkdir -p "$ROOT_DIR/submission"
tar -czf "$ROOT_DIR/submission/$TAR_NAME" -C "$ROOT_DIR/submission" "$GROUP"
echo "Tarball created: submission/$TAR_NAME"
