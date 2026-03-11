# EE 201A Final Project Report (v4 Alignment)
## Thermal Resistance Network Solver for 3D/2.5D GPU+HBM Packages

**Authors:** Ethan Owen (905452983), Rachel Sarmiento (506556199)  
**Date:** March 2026

## 1. Project v4 Requirement Updates Incorporated

This submission was updated to match **Final Project v4**:

1. **Power_Source power set to 0 W**
   - Implemented in `therm.py` by forcing `Power_Source` to `0.0` and omitting it from `power_dict`.
   - Backside conversion-loss injection is disabled for v4 behavior.
2. **Golden reference integrated**
   - `solutions/golden_output.txt` is converted to `solutions/golden_output_results.txt`.
   - `compare_to_golden.py` computes per-box correctness metrics against the golden case.
3. **GPU/HBM power distribution changed**
   - Power is deposited in the **center z-plane** of each GPU/HBM die/tier (per v4 figure).
   - Implemented in `thermal_solver.py` voxel power assignment.

## 2. Required Reporting Items (from v4) and Where Addressed

1. **Ambient temperature**: fixed at **45 C** (`thermal_solver.py`, `AMBIENT_TEMP_C = 45.0`).
2. **Temperature units**: all reported temperatures are in **degrees Celsius**.
3. **Approach/meshing/resistance method**: Sections 3 and 4 below.
4. **Correctness + runtime grading focus**: Sections 5 and 6 below.

## 3. Thermal Modeling Approach

### 3.1 Meshing strategy

- We use a **non-uniform voxel grid** aligned to geometric boundaries of:
  - chiplet boxes
  - bonding boxes
  - TIM boxes
  - heatsink base
- Grid is generated from sorted boundary edges and subdivided with resolution limits (`build_grid` in `thermal_solver.py`).
- Current defaults:
  - `max_xy = 2.0 mm`
  - `max_z = 0.3 mm`
  - `min_s = 0.001 mm`

### 3.2 Voxel thermal resistance model

For each voxel, conductance links in `x/y/z` are built from half-cell series resistances:

- `R_face = dx/(2*k1*A) + dx/(2*k2*A)` (similarly for `y`, `z`)
- `G_face = 1/R_face`

Boundary conditions:

- Top boundary uses convection via heatsink `hc`.
- For water-cooled cases, effective `hc` is estimated algorithmically from
  forced-convection Nusselt correlation (`Nu_L`) with water properties near 45 C.
  - Laminar branch uses the constant-heat-flux average plate form.
  - XML `hc` is treated as an upper bound (no manual scaling factors).
- Bottom boundary uses `H_BOTTOM`.
- Ambient reference is 45 C.

### 3.3 Power model (v4)

- `Power_Source`: **0 W**.
- GPU + HBM tiers:
  - total box power preserved
  - distributed only to the **center z-plane** voxel slice(s) inside each powered box
  - if center lies on a grid boundary, both adjacent slices are used

This follows the v4 requirement image showing a center-plane heat source rather than full-volume source.

## 4. Solver Path

- For v4 runs, `simulator_simulate()` calls `solve_thermal(..., force_voxel=True, use_center_plane_power=True)`.
- This enforces the mesh-resolved model needed for center-plane power injection.
- PySpice/netlist path remains in code as an alternate solver path, but v4 output generation is based on the voxel RC system for this power model.

## 5. Correctness Evaluation vs Golden Output

### 5.1 Metric definitions used

Compared per box:

- Peak temperature MAE / RMSE / max-abs error
- Average temperature MAE / RMSE / max-abs error
- Percentage scores (`100%` = perfect):
  - `peak_mae_pct`, `peak_rmse_pct`, `peak_max_abs_pct`
  - `avg_mae_pct`, `avg_rmse_pct`, `avg_max_abs_pct`
  - Variance percentage (requested): `var(golden)/var(ours) * 100`
  - Symmetric variance match percentage: `min(var(golden)/var(ours), var(ours)/var(golden)) * 100`

The percentage metrics keep the same correctness information while making comparison easier to read.

### 5.2 Current reference-case numbers

Reference case: `ECTC_3D_1GPU_8high_110325_higherHTC`  
Source: `out_therm/golden_comparison.csv`

- Matched boxes: `61/61`
- Peak MAE: `0.2714 C`
- Avg MAE: `0.2505 C`
- Peak RMSE: `0.3547 C`
- Avg RMSE: `0.3844 C`
- Peak MAE score: `71.43%`
- Avg MAE score: `76.13%`
- Peak RMSE score: `65.67%`
- Avg RMSE score: `67.53%`
- Peak max-abs score: `36.06%`
- Avg max-abs score: `34.69%`
- Peak variance `%` (`var(golden)/var(ours)*100`): `67.32%`
- Avg variance `%` (`var(golden)/var(ours)*100`): `97.90%`

These are produced algorithmically by the solver and comparison scripts; no output values are hardcoded from golden.

## 6. Runtime Reporting (v4 grading criterion)

Runtime is split into:

1. **Placement/sizing runtime** (reported as total runtime excluding simulation)
2. **Thermal simulation runtime** (reported separately)

This matches the requested grading emphasis on runtime while keeping solver time explicit.
For `ECTC_3D_1GPU_8high_110325_higherHTC`, current simulation runtime is about `12.6 s`
with the physics-only solver settings above.

## 7. Reproducible Flow

```bash
./setup/setup.sh
source .venv/bin/activate
bash scripts/run_config2_3D_gpu_bottom.sh
python3 convert_golden_output.py
python3 compare_to_golden.py \
  --golden solutions/golden_output_results.txt \
  --results_dir out_therm \
  --csv out_therm/golden_comparison.csv
```

## 8. Deliverables Produced

Per run:

- `out_therm/<project>.png`
- `out_therm/<project>3D.png`
- `out_therm/<project>_results.txt`
- `out_therm/<project>_results.yaml`

Comparison outputs:

- `solutions/golden_output_results.txt`
- `out_therm/golden_comparison.csv`
