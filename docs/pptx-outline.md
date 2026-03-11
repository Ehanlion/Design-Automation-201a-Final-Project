# PowerPoint Outline (v4-Focused)
## EE 201A Final Project: Thermal Solver for 3D/2.5D GPU+HBM

**Authors:** Ethan Owen, Rachel Sarmiento

## Slide 1: v4 Requirements + What Changed

- Final Project v4 updates we implemented:
  1. `Power_Source` power set to **0 W**
  2. Added golden reference flow (`golden_output.txt` -> converted results)
  3. GPU/HBM power modeled on **center z-plane** of each die/tier
- Ambient temperature fixed at **45 C**
- Temperatures reported in **Celsius**

Visuals:
- Screenshot of v4 requirement snippet (power-source + center-plane text)
- Small diagram showing old full-volume vs new center-plane injection

## Slide 2: Meshing + Voxel Resistance Method (Required in Report)

- Meshing approach: **non-uniform voxel grid**
  - aligned to chiplet/bonding/TIM/heatsink boundaries
- Material assignment:
  - layer-stackup conductivity mapped per voxel z-slice
- Resistance/conductance model:
  - half-cell face resistance, `G = 1/R`
  - top/bottom boundary convection to ambient

Visuals:
- One exploded 3D mesh view
- One equation block for `R_face` and `G_face`

## Slide 3: Solver Flow + Runtime Criterion

- Driver: `therm.py`
- Main solve path for v4 outputs:
  - voxel RC solve with center-plane power assignment
- Tuned runtime/accuracy settings (reference case):
  - grid: `max_xy=3.0 mm`, `max_z=0.5 mm`
  - effective convection: `hc_eff = hc_raw * (5400/7000)`
- Runtime reported as two numbers:
  1. placement/sizing runtime (grading runtime focus)
  2. simulation runtime (reported separately)

Visuals:
- Pipeline block diagram:
  parse -> place -> mesh/material -> power map -> solve -> outputs
- Runtime table with two rows (pre-sim vs sim)

## Slide 4: Correctness Metrics vs Golden (v4 grading focus)

- Compare against `solutions/golden_output_results.txt`
- Report:
  - peak/avg MAE
  - peak/avg RMSE
  - max absolute error
  - **variance match ratio** (our variance / golden variance)
- Why variance is shown:
  - v4 grading emphasizes closeness of result variance to NGSpice/golden

Visuals:
- Metric table for reference case `ECTC_3D_1GPU_8high_110325_higherHTC`
- Optional histogram/boxplot comparing golden vs ours

## Slide 5: Current Results + Next Tuning Steps

- Current reference-case summary (from `out_therm/golden_comparison.csv`)
  - matched boxes: 61/61
  - peak MAE: 0.39 C
  - avg MAE: 0.43 C
  - peak/avg RMSE: 0.50 C / 0.54 C
  - simulation runtime: ~0.08 s
- Confirmed constraints:
  - no hardcoded golden outputs
  - no interposer insertion beyond config-defined geometry
- Planned tuning:
  1. convection boundary calibration
  2. material parameter sensitivity
  3. grid refinement/runtime trade-off

Visuals:
- Final summary table + one short “next actions” list
