# Golden Comparison Summary

Focused on the grading-relevant correctness metrics only: distance from golden and variance match.

## Metric Definitions

| Metric | Calculation | Ideal |
| --- | --- | --- |
| Matched boxes | Shared box names after normalization | `61/61` |
| Peak MAE (C) | `mean_i(abs(result_peak_i - golden_peak_i))` | `0.000000` |
| Average MAE (C) | `mean_i(abs(result_avg_i - golden_avg_i))` | `0.000000` |
| Peak variance match (%) | `100 * min(var(result_peak)/var(golden_peak), var(golden_peak)/var(result_peak))` | `100.00%` |
| Average variance match (%) | `100 * min(var(result_avg)/var(golden_avg), var(golden_avg)/var(result_avg))` | `100.00%` |

## Overview

- Golden box count: `61`
- Compared case count: `1`
- Skipped case count: `2`

## Compared Cases

### Case 1: `ECTC_3D_1GPU_8high_110325_higherHTC_results.txt`

| Metric | Result | Ideal | Notes |
| --- | --- | --- | --- |
| Matched boxes | `61/61` | `61/61` | Same box count and normalized box names matched |
| Peak MAE (C) | `0.271364` | `0.000000` | Lower is better |
| Average MAE (C) | `0.250548` | `0.000000` | Lower is better |
| Peak variance match (%) | `67.32%` | `100.00%` | `var(result_peak)=0.683685`, `var(golden_peak)=0.460271` |
| Average variance match (%) | `97.90%` | `100.00%` | `var(result_avg)=0.652491`, `var(golden_avg)=0.638761` |

## Skipped Files

These files were excluded from the compared metrics.

- `ECTC_2p5D_1GPU_8high_110325_higherHTC_results.txt`: boxes=57 (expected 61)
- `ECTC_3D_1GPU_8high_120125_higherHTC_results.txt`: box names differ after normalization (common=2, expected=61)
