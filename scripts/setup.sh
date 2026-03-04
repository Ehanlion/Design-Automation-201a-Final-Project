#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== EE 201A Final Project Setup ==="
echo "Project directory: $PROJECT_DIR"

cd "$PROJECT_DIR"

echo ""
echo "--- Checking Python version ---"
python3 --version

echo ""
echo "--- Installing required Python packages ---"
pip3 install --user click seaborn scikit-learn sortedcontainers 2>&1 | tail -5

echo ""
echo "--- Verifying imports ---"
python3 -c "
import click, seaborn, sklearn, yaml, numpy, matplotlib
from sortedcontainers import SortedList
print('All required packages available.')
"

echo ""
echo "--- Creating output directory ---"
mkdir -p out_therm

echo ""
echo "--- Verifying config files ---"
CONFIGS="$PROJECT_DIR/configs/thermal-configs"
REQUIRED_FILES=(
    "$CONFIGS/assembly_process_definitions.xml"
    "$CONFIGS/bonding_definitions.xml"
    "$CONFIGS/heatsink_definitions.xml"
    "$CONFIGS/layer_definitions.xml"
    "$CONFIGS/netlist.xml"
    "$CONFIGS/sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU_on_top.xml"
    "$CONFIGS/sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU.xml"
    "$CONFIGS/sip_hbm_dray062325_1gpu_6hbm_2p5D.xml"
    "$PROJECT_DIR/output/output_vars2.yaml"
)

ALL_OK=true
for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$f" ]; then
        echo "  MISSING: $f"
        ALL_OK=false
    fi
done

if $ALL_OK; then
    echo "All required config files present."
else
    echo "ERROR: Some config files are missing. Check your project directory."
    exit 1
fi

echo ""
echo "=== Setup complete. Ready to run test configurations. ==="
echo "  ./scripts/run_config1_3D_gpu_top.sh"
echo "  ./scripts/run_config2_3D_gpu_bottom.sh"
echo "  ./scripts/run_config3_2p5D.sh"
echo "  ./scripts/run_all.sh"
