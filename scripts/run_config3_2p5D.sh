#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIGS="$PROJECT_DIR/configs"

cd "$PROJECT_DIR"
mkdir -p out_therm

echo "=== Config 3: 2.5D (2p5D_1GPU) ==="
echo ""

python3 therm.py \
    --therm_conf "$CONFIGS/sip_hbm_dray062325_1gpu_6hbm_2p5D.xml" \
    --out_dir out_therm \
    --heatsink_conf "$CONFIGS/heatsink_definitions.xml" \
    --bonding_conf "$CONFIGS/bonding_definitions.xml" \
    --heatsink heatsink_water_cooled \
    --project_name ECTC_2p5D_1GPU_8high_110325_higherHTC \
    --is_repeat False \
    --hbm_stack_height 8 \
    --system_type 2p5D_1GPU \
    --dummy_si False \
    --tim_cond_list 5 \
    --infill_cond_list 1.6 \
    --underfill_cond_list 1.6

echo ""
echo "=== Config 3 complete ==="
