#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SETUP_SCRIPT="$PROJECT_DIR/setup/setup.sh"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
NGSPICE_BIN="$PROJECT_DIR/third_party/ngspice/install/bin/ngspice"

venv_ready() {
    [ -x "$VENV_PYTHON" ] || return 1
    "$VENV_PYTHON" - <<'PY' >/dev/null 2>&1
import click
import matplotlib
import numpy
import seaborn
import sklearn
import yaml
from sortedcontainers import SortedList
PY
}

ngspice_ready() {
    [ -x "$NGSPICE_BIN" ] || return 1
    "$NGSPICE_BIN" --version >/dev/null 2>&1
}

echo ""
echo "========================================"
echo "  Running all 3 test configurations"
echo "========================================"
echo ""

NEEDS_SETUP=0
if venv_ready; then
    echo "Environment check: .venv is ready."
else
    echo "Environment check: .venv missing or incomplete."
    NEEDS_SETUP=1
fi

if ngspice_ready; then
    echo "Environment check: local ngspice is ready."
else
    echo "Environment check: local ngspice missing or not working."
    NEEDS_SETUP=1
fi

if [ "$NEEDS_SETUP" -eq 1 ]; then
    echo ""
    echo "--- Bootstrapping environment via setup/setup.sh ---"
    bash "$SETUP_SCRIPT"
fi

if ! venv_ready; then
    echo "ERROR: .venv is still unavailable after setup. Please check $SETUP_SCRIPT."
    exit 1
fi

if ! ngspice_ready; then
    echo "ERROR: local ngspice is still unavailable after setup. Please check setup/install_local_ngspice.sh."
    exit 1
fi

source "$VENV_DIR/bin/activate"
export EE201A_NGSPICE_BIN="$NGSPICE_BIN"

echo ""
"$SCRIPT_DIR/run_config1_3D_gpu_top.sh"

echo ""
echo "----------------------------------------"
echo ""

"$SCRIPT_DIR/run_config2_3D_gpu_bottom.sh"

echo ""
echo "----------------------------------------"
echo ""

"$SCRIPT_DIR/run_config3_2p5D.sh"

echo ""
echo "========================================"
echo "  All 3 configurations completed"
echo "========================================"

echo ""
echo "========================================"
echo "  Summarizing all results"
echo "========================================"

"$SCRIPT_DIR/summarize_all.sh"

echo ""
echo "========================================"
echo "  All results summarized"
echo "========================================"

echo ""
echo "========================================"
echo "  Comparing results to golden reference"
echo "========================================"

python3 "$PROJECT_DIR/convert_golden_output.py" \
  --input "$PROJECT_DIR/solutions/golden_output.txt" \
  --output "$PROJECT_DIR/solutions/golden_output_results.txt"

python3 "$PROJECT_DIR/compare_to_golden.py" \
  --golden "$PROJECT_DIR/solutions/golden_output_results.txt" \
  --results_dir "$PROJECT_DIR/out_therm" \
  --csv "$PROJECT_DIR/out_therm/golden_comparison.csv" \
  --summary_txt "$PROJECT_DIR/out_therm/golden_comparison_summary.txt" \
  --summary_md "$PROJECT_DIR/out_therm/golden_comparison_summary.md"

echo ""
echo "========================================"
echo "  Golden comparison complete"
echo "========================================"
