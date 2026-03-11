# EE 201A Final Project Report
## Thermal Resistance Network Solver for 3D/2.5D GPU+HBM Packages

**Authors:** Ethan Owen (905452983), Rachel Sarmiento (506556199)  
**Date:** March 11, 2026

## 1. Project Scope and Final v4 Alignment

This project builds a thermal resistance network for GPU+HBM packages and solves that network with a local `ngspice` installation, as required by **Final Project v4** and the Piazza clarifications.

The final implementation reflects the following v4 updates:

1. `Power_Source` is modeled as **0 W**.
2. GPU and HBM heat is injected on the **center z-plane** of each powered die/tier.
3. The thermal network is exported as a **SPICE netlist** and solved with **local `ngspice`** first.
4. All temperatures are reported in **degrees Celsius** with **ambient = 45 C**.

## 2. Required Report Items and Where They Are Addressed

The project PDF asks the report/slides to state the approach used, whether uniform or non-uniform meshing was used, and how voxel resistances were calculated.

This report covers those items directly:

1. **Approach used**: Sections 3 and 4.
2. **Uniform or non-uniform meshing**: Section 3.1.
3. **How voxel resistances were calculated**: Section 3.2.
4. **Ambient temperature and temperature units**: Section 3.4.
5. **Correctness and runtime reporting**: Sections 5 and 6.

## 3. Thermal Modeling Method

### 3.1 Meshing strategy

We use a **non-uniform 3D voxel mesh**.

- Mesh lines are aligned to the geometric boundaries of:
  - chiplet boxes
  - bonding boxes
  - TIM boxes
  - heatsink base
- Additional subdivision is applied to keep cell sizes bounded while preserving boundary alignment.
- Current default controls in `thermal_solver.py` are:
  - `max_xy = 2.0 mm`
  - `max_z = 0.3 mm`
  - `min_s = 0.001 mm`

This gives a mesh that is finer near important package boundaries without forcing a globally uniform discretization.

### 3.2 Voxel resistance / conductance calculation

Each voxel becomes a thermal node in the RC network.

Neighboring voxels are connected by conductances derived from half-cell series thermal resistances. For a face-normal direction:

`R_face = d1 / (2*k1*A) + d2 / (2*k2*A)`

and

`G_face = 1 / R_face`

where:

- `d1`, `d2` are the two half-cell distances to the shared face
- `k1`, `k2` are the thermal conductivities on the two sides
- `A` is the shared face area

This is computed independently for `x`, `y`, and `z`, so anisotropic effective conductivity across stacked layers is preserved.

### 3.3 Material and boundary modeling

Material assignment is derived from the package stackup and heatsink definitions.

- Layer stackups are mapped into per-voxel conductivity values.
- The top boundary is connected to ambient through a convection resistance.
- The bottom boundary is also connected to ambient through a convection resistance.
- For water-cooled cases, we estimate an effective top-side convection coefficient from a forced-convection correlation and cap it by the XML-provided `hc`.

### 3.4 Power and temperature assumptions

- **Ambient temperature:** `45 C`
- **Temperature unit:** Celsius throughout
- **GPU power:** `270 W`
- **HBM stack power:** `5 W` per stack
- **Power_Source:** `0 W`

For Final Project v4, GPU and HBM power is deposited on the **center z-plane** of each powered die or HBM tier. If the center plane lies on a voxel boundary, the power is split across the two adjacent slices.

## 4. Solver Flow and ngspice Usage

### 4.1 Primary solver path

For final-project runs, `therm.py` calls the voxel solver path with center-plane power enabled. The flow is:

1. Build the non-uniform voxel mesh.
2. Assign materials and power.
3. Assemble the voxel RC network.
4. Export the network to `out_therm/thermal_netlist.sp`.
5. Solve the netlist with the project-local binary:
   `third_party/ngspice/install/bin/ngspice`
6. Convert node voltages back into temperatures.

This now makes `ngspice` the **first-choice solver**, which was the main project requirement.

### 4.2 Implementation details that make ngspice practical

The final code uses several measures to keep the `ngspice` path robust on the actual project meshes:

- direct invocation of the project-local `ngspice` binary
- KLU enabled in the exported netlist via `.option klu`
- voltage extraction through `wrdata` files instead of huge stdout dumps
- configurable timeout through `EE201A_NGSPICE_TIMEOUT_S`

### 4.3 Fallback behavior

If `ngspice` is unavailable or fails, the code falls back to the existing matrix-based solver:

- SciPy sparse CG with Jacobi preconditioner
- NumPy SOR if SciPy is unavailable

This fallback uses the **same voxel-network physics**, so it is a backend change, not a model change.

### 4.4 Validation of ngspice correctness

We explicitly validated that the `ngspice` solution and the internal matrix fallback agree on the **same voxel network**.

For the default 2.5D case mesh:

- maximum peak-temperature difference: `3.70e-05 C`
- maximum average-temperature difference: `3.64e-05 C`

This confirms that the exported RC netlist is consistent with the internally assembled linear system.

## 5. Results and Correctness

### 5.1 Current run summary

From the current `out_therm/summary.md` results:

| Project | Hottest box | Peak temp (C) | GPU peak (C) | HBM peak (C) | Box count |
| --- | --- | --- | --- | --- | --- |
| `ECTC_2p5D_1GPU_8high_110325_higherHTC` | `Power_Source.substrate.set_primary.GPU` | `101.2606` | `101.2606` | `93.4960` | `57` |
| `ECTC_3D_1GPU_8high_110325_higherHTC` | `Power_Source.substrate.GPU` | `126.4009` | `126.4009` | `125.3038` | `61` |
| `ECTC_3D_1GPU_8high_120125_higherHTC` | `Power_Source.substrate.HBM#1` | `122.3400` | `122.0180` | `122.3400` | `61` |

### 5.2 Golden comparison case

The current golden comparison is available for the matching 3D reference case:

`ECTC_3D_1GPU_8high_110325_higherHTC`

From `out_therm/golden_comparison_summary.md`:

- matched boxes: `61/61`
- peak MAE: `0.271364 C`
- average MAE: `0.250548 C`
- peak variance match: `67.32%`
- average variance match: `97.90%`

These are the grading-relevant correctness metrics currently available from the provided golden flow.

## 6. Runtime Reporting

We report runtime in two parts:

1. **placement/sizing runtime**
2. **thermal solve runtime**

This separation makes it easier to see both algorithmic overhead and the actual RC solve cost.

Recent verified `ngspice` solve times on the current code:

- `ECTC_2p5D_1GPU_8high_110325_higherHTC`
  - mesh size: `20880` nodes
  - `ngspice` solve time: about `92.31 s`
- `ECTC_3D_1GPU_8high_120125_higherHTC`
  - mesh size: `11718` nodes
  - `ngspice` solve time: about `30.31 s`

We also verified that enabling KLU materially improves `ngspice` runtime on intermediate meshes while preserving the same temperatures.

## 7. Reproducible Flow

```bash
./setup/setup.sh
source .venv/bin/activate

bash scripts/run_config1_3D_gpu_top.sh
bash scripts/run_config2_3D_gpu_bottom.sh
bash scripts/run_config3_2p5D.sh

python3 convert_golden_output.py
python3 compare_to_golden.py \
  --golden solutions/golden_output_results.txt \
  --results_dir out_therm \
  --csv out_therm/golden_comparison.csv
```

## 8. Deliverables Produced

For each run:

- `out_therm/<project>.png`
- `out_therm/<project>3D.png`
- `out_therm/<project>_results.txt`
- `out_therm/<project>_results.yaml`

Netlist / solver artifact:

- `out_therm/thermal_netlist.sp`

Golden-comparison outputs:

- `solutions/golden_output_results.txt`
- `out_therm/golden_comparison.csv`
- `out_therm/golden_comparison_summary.md`

## 9. Main Final Takeaway

The final submission now satisfies the key project requirement that the **meshed thermal RC network be solved with local `ngspice`**. The solver uses a non-uniform voxel mesh, center-plane GPU/HBM power deposition, exported SPICE netlists, and validated fallback behavior. The `ngspice` and matrix solutions agree to within about `1e-5` to `1e-4 C`, so the netlist generation and solver integration are numerically consistent.
