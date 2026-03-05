#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper to summarize all existing *_results.yaml files in out_therm.
# Outputs:
#   - Console table
#   - out_therm/summary.csv
#   - out_therm/summary.md

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RESULTS_DIR="$PROJECT_DIR/out_therm"
CSV="$RESULTS_DIR/summary.csv"
MD="$RESULTS_DIR/summary.md"

python3 "$PROJECT_DIR/summarize_results.py" \
  --results_dir "$RESULTS_DIR" \
  --csv "$CSV" \
  --md "$MD"

echo ""
echo "Wrote $CSV and $MD"
