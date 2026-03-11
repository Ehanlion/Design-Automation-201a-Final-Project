#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "  Running all 3 test configurations"
echo "========================================"

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