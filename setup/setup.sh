#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

echo "=== EE 201A Final Project - Environment Setup ==="
echo "Project:      $PROJECT_DIR"
echo "Virtual env:  $VENV_DIR"
echo "Requirements: $REQUIREMENTS"
echo ""

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "Using $PYTHON_VERSION"
echo ""

# --system-site-packages lets the venv inherit large packages already
# installed system-wide (numpy, matplotlib, etc.) to avoid disk quota issues
# on SEASnet shared servers.
if [ ! -d "$VENV_DIR" ]; then
    echo "--- Creating virtual environment (with system site-packages) ---"
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "Created .venv at $VENV_DIR"
else
    echo "--- Virtual environment already exists at $VENV_DIR ---"
fi

echo ""
echo "--- Activating virtual environment ---"
source "$VENV_DIR/bin/activate"
echo "Active Python: $(which python3)"
echo ""

echo "--- Installing requirements ---"
pip install -r "$REQUIREMENTS" 2>&1 | grep -v "already satisfied" || true
echo ""

echo "--- Verifying all imports ---"
python3 -c "
import click
import matplotlib
import numpy
import seaborn
import sklearn
import yaml
from sortedcontainers import SortedList
print('All packages imported successfully.')
"
echo ""

mkdir -p "$PROJECT_DIR/out_therm"

echo "=== Setup complete ==="
echo ""
echo "To activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run test configurations:"
echo "  ./scripts/run_config1_3D_gpu_top.sh"
echo "  ./scripts/run_config2_3D_gpu_bottom.sh"
echo "  ./scripts/run_config3_2p5D.sh"
echo "  ./scripts/run_all.sh"
