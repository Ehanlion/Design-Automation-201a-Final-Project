#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIGS="$PROJECT_DIR/configs/thermal-configs"

cd "$PROJECT_DIR"
mkdir -p out_therm

echo "=== Config 2: 3D with GPU on Bottom (3D_1GPU) ==="
echo ""

python3 therm.py \
    --therm_conf "$CONFIGS/sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU.xml" \
    --out_dir out_therm \
    --heatsink_conf "$CONFIGS/heatsink_definitions.xml" \
    --bonding_conf "$CONFIGS/bonding_definitions.xml" \
    --heatsink heatsink_water_cooled \
    --project_name ECTC_3D_1GPU_8high_110325_higherHTC \
    --is_repeat False \
    --hbm_stack_height 8 \
    --system_type 3D_1GPU \
    --dummy_si True \
    --tim_cond_list 5 \
    --infill_cond_list 1.6 \
    --underfill_cond_list 1.6

echo ""
echo "=== Config 2 complete ==="
