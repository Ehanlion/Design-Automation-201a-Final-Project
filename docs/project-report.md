# EE 201A Final Project Report
## Thermal Resistance Network Solver for 3D/2.5D GPU+HBM Packages

**Authors:** Ethan Owen (905452983), Rachel Sarmiento (506556199)  
**Date:** March 2026

## 1. What Is Implemented

We implemented a thermal solver flow for the three required package configurations:

1. `3D_1GPU_top` (`ECTC_3D_1GPU_8high_120125_higherHTC`)
2. `3D_1GPU` (`ECTC_3D_1GPU_8high_110325_higherHTC`)
3. `2p5D_1GPU` (`ECTC_2p5D_1GPU_8high_110325_higherHTC`)

The solver uses a **PySpice box-level thermal network** as the primary model and now uses **project-local ngspice** by default.

## 2. Tools and Runtime Stack

- Core entry point: `therm.py`
- Main solver implementation: `thermal_solver.py`
- Required SPICE interface: `PySpice`
- Local simulator backend: `ngspice` built into `third_party/ngspice/install`
- Setup/install scripts:
  - `setup/setup.sh`
  - `setup/install_local_ngspice.sh`
- Run scripts:
  - `scripts/run_config1_3D_gpu_top.sh`
  - `scripts/run_config2_3D_gpu_bottom.sh`
  - `scripts/run_config3_2p5D.sh`
  - `scripts/run_all.sh`
  - `scripts/summarize_all.sh`

## 3. Solver Choices and Why

### 3.1 Primary model: box-level PySpice network

Each physical box (chiplet/bonding/TIM) is one thermal node.

Thermal-electrical analogy:
- Temperature rise above ambient ↔ voltage
- Power (W) ↔ current source
- Thermal resistance (K/W) ↔ electrical resistance (ohms)
- Ambient boundary ↔ ground

This was chosen because it directly satisfies the course requirement to use PySpice and export a netlist.

### 3.2 Solver hierarchy (actual execution order)

`solve_thermal()` attempts:

1. **Local ngspice subprocess** (primary execution path)
   - Runs exported netlist via `third_party/ngspice/install/bin/ngspice` when available.
2. **PySpice API path** (`circuit.simulator(...)`) using ngspice-subprocess mode.
3. **Custom RC matrix solve** from the same network data (scipy/numpy fallback).
4. If PySpice import fails entirely: **3D voxel finite-difference fallback**.

This preserves identical physics while ensuring the run completes even if ngspice is unavailable.

### 3.3 Algorithmic details

- Interface conductance between stacked boxes uses half-cell series resistance:
  - `R_iface = h1/(2*k1*A) + h2/(2*k2*A)`, `G = 1/R_iface`
- Power uses explicit `box.power` when present.
- Top/bottom convection converted to conductance-to-ambient.
- Matrix fallback builds `A*T = b` from the same `G_pairs`, `P_vec`, and `G_conv`.

## 4. End-to-End Flow

1. Parse XML config hierarchy and materials.
2. Build/place 3D box geometry (`rearrange.py`, `therm.py`).
3. Generate bonding/TIM helper boxes.
4. Build PySpice thermal circuit in `thermal_solver.py`.
5. Export netlist to `out_therm/thermal_netlist.sp`.
6. Solve using local ngspice first, then fallbacks if needed.
7. Write results/plots and summaries.

## 5. Local ngspice Integration

### 5.1 Installation path

`setup/install_local_ngspice.sh` downloads and builds ngspice source locally into:

- `third_party/ngspice/install/bin/ngspice`

No system-wide install is required.

### 5.2 Discovery and use

`thermal_solver.py` now:
- Prefers `third_party/ngspice/install/bin/ngspice`
- Accepts override via `EE201A_NGSPICE_BIN`
- Sets environment so PySpice can use local ngspice library/binary paths

## 6. Scripting Usage

Primary run script flow:

1. `./setup/setup.sh`
2. `source .venv/bin/activate`
3. `./scripts/run_all.sh`
4. `./scripts/summarize_all.sh`

Individual config scripts remain available for isolated runs.

## 7. Outputs Produced

Per configuration run:

- `out_therm/<project>.png`
- `out_therm/<project>3D.png`
- `out_therm/<project>_results.txt`
- `out_therm/<project>_results.yaml`
- `out_therm/thermal_netlist.sp`

Aggregate summaries:

- `out_therm/summary.csv`
- `out_therm/summary.md`

## 8. Key Project Decisions

1. **PySpice kept as required front-end**; no replacement with a pure custom-only solver.
2. **Local ngspice provisioning** added for reproducibility on lab machines.
3. **GPU power uses 270 W** (course clarification), not 400 W from older text.
4. **Simulation runtime separated from placement/sizing runtime** per project guidance.

## 9. Validation Notes

- Netlist export verified each run.
- Local ngspice subprocess path verified to parse all expected node voltages.
- Fallbacks retained and functional for robustness.

