# EE 201A Final Project Report: Thermal Resistance Network Solver

## 1. Project Overview

This project implements a 3D thermal resistance network solver for multi-chiplet
packages with GPU and HBM stacks. The solver computes steady-state temperature
distributions for three package configurations:

1. **Config 1 (3D GPU-on-top)**: GPU stacked on top of an 8-high HBM stack
2. **Config 2 (3D GPU-bottom)**: GPU below HBM stacks
3. **Config 3 (2.5D)**: GPU and HBMs side-by-side on an interposer

## 2. Solver Architecture

### 2.1 Approach: 3D Finite-Difference Method

The solver discretizes the 3D package geometry into a non-uniform grid and solves
the steady-state heat conduction equation:

  ∇·(k∇T) + q = 0

where k is thermal conductivity (W/(m·K)), T is temperature (°C), and q is
volumetric heat generation (W/mm³).

### 2.2 Non-Uniform Grid Construction

Grid edges are placed at every box, bonding, TIM, and heatsink boundary to
ensure material interfaces align with cell boundaries. Large cells are
subdivided to a maximum of 2mm in XY and 0.3mm in Z. Minimum cell size is
0.001mm to avoid degenerate cells.

### 2.3 Layer-by-Layer Conductivity Assignment

Rather than assigning a single average conductivity per box, the solver
computes per-voxel conductivity by walking through each box's layer stackup.
For each z-cell overlapping a box, the `_retrieve_conductivity()` function
determines which material layers span that voxel and computes a
thickness-weighted average:

```
k_voxel = Σ (overlap_fraction_i × k_i)
```

This captures the thermal effects of composite stackups (e.g., Cu-Foil:0.05,
Si:0.95 in HBM layers) at each z-level.

### 2.4 Material Property Sources

Conductivities are sourced from `layer_definitions.xml` and the Anemoi
reference data:

| Material | k (W/(m·K)) | Usage |
|---|---|---|
| Si | 105 | Active layers, interposer |
| Cu-Foil | 400 | Metal layers, heatsink |
| TIM0p5 | 5.0 (from CLI) | TIM between chiplets and heatsink |
| Epoxy, Silver filled | 1.6 | Underfill, bonding fill |
| Infill_material | 1.6 (from CLI) | Gap fill between chiplets |
| Air | 0.025 | Empty space outside package |
| FR-4 | 0.1 | Organic substrate |

CLI parameters `--tim_cond_list`, `--infill_cond_list`, and `--underfill_cond_list`
override default conductivities at runtime.

### 2.5 Power Distribution

Power is distributed volumetrically to active components:

| Component | Power |
|---|---|
| GPU | 400 W (per project spec) |
| Each HBM stack | 5 W (per project spec) |
| Total (6 stacks) | 430 W |

Power density q (W/mm³) is computed by dividing each component's power budget
by its volume, then assigned to all grid cells within that component.

### 2.6 Boundary Conditions

- **Top (z_max)**: Convective cooling through the heatsink to ambient.
  Conductance per cell: G_top = 1 / (dz/(2·k·A) + 1/(h·A))
  where h = 7000 W/(m²·K) (water cooling) and T_ambient = 45°C.

- **Bottom (z_min)**: Natural convection to ambient.
  h_bottom = 10 W/(m²·K), T_ambient = 45°C.

- **Lateral (x, y boundaries)**: Adiabatic (zero heat flux).

### 2.7 Sparse Matrix Assembly and Solver

The discretized system Ax = b is assembled as a sparse CSR matrix where:
- A is the thermal conductance matrix (symmetric positive definite)
- x is the temperature vector
- b contains heat source terms and boundary condition contributions

The solver uses **Conjugate Gradient (CG)** with a **Jacobi (diagonal)
preconditioner**, which provides excellent performance for this SPD system.
A numpy-based SOR fallback is available when scipy is not installed.

**Performance note**: CG with Jacobi preconditioner provides a ~186x speedup
over scipy's `spsolve` direct solver on the SEASnet server (scipy 1.5.4),
reducing solve time from ~19s to ~0.1s for 9000-cell grids.

## 3. Implementation Files

| File | Purpose |
|---|---|
| `thermal_solver.py` | Core 3D FD solver (grid, materials, power, assembly, CG solve) |
| `therm.py` | Main entry point; `simulator_simulate()` delegates to thermal_solver |
| `visualize_results.py` | Temperature bar charts and cross-config comparison plots |
| `summarize_results.py` | Extracts peak/avg temperatures into CSV/Markdown tables |
| `scripts/run_all.sh` | Runs all 3 configurations sequentially |
| `scripts/run_config*.sh` | Individual config run scripts |
| `scripts/summarize_all.sh` | Generates summary from all result YAML files |

## 4. Results

### 4.1 Temperature Summary

| Configuration | GPU Peak (°C) | HBM Peak (°C) | Hottest Box |
|---|---|---|---|
| Config 1: 3D GPU-on-top | 136.2 | 136.4 | HBM#5_l8 |
| Config 2: 3D GPU-bottom | 139.0 | 137.3 | GPU |
| Config 3: 2.5D | 105.0 | 92.6 | GPU |

### 4.2 Analysis

**Config 1 (3D GPU-on-top)**: The GPU sits on top of the HBM stack, directly
below the heatsink. The heatsink covers a 25.5×32.4mm area. With 430W total
power and h=7000, the convective ΔT alone is ~74°C (T_min ≈ 119°C). The
relatively uniform temperatures (~134-136°C across all components) indicate
efficient vertical heat conduction through the Cu-foil heatsink.

**Config 2 (3D GPU-bottom)**: The GPU is below the HBM stacks, farther from
the heatsink. This results in a slightly higher GPU peak (139°C vs 136°C in
Config 1) because heat must travel through additional layers to reach the
heatsink.

**Config 3 (2.5D)**: The GPU and HBMs are side-by-side on an interposer. The
larger heatsink area (41.4×35.2mm = 1457mm²) significantly reduces the
convective resistance, lowering the GPU peak to 105°C and HBM peaks to ~93°C.
This demonstrates the thermal advantage of 2.5D integration for spreading
heat over a larger area.

### 4.3 Thermal Coupling

In 3D configurations, the tight vertical stacking creates strong thermal
coupling between GPU and HBM components. All components reach similar
temperatures because the dominant thermal resistance is at the heatsink-to-
ambient interface, not between components.

In 2.5D, lateral separation creates distinct thermal zones. The GPU runs ~12°C
hotter than HBMs, confirming the thermal isolation benefit of lateral spacing.

## 5. Design Decisions and Trade-offs

### 5.1 Non-Uniform vs. Uniform Grid

A non-uniform grid was chosen to accurately capture material interfaces
without excessive cell counts. Grid edges align with every box boundary,
ensuring no material averaging across interfaces.

### 5.2 CG vs. Direct Solver

The Conjugate Gradient solver was selected over scipy's direct solver
(`spsolve`) after profiling revealed extremely poor performance of the direct
solver on the SEASnet scipy 1.5.4 installation. CG with Jacobi
preconditioning converges in ~0.1s for typical grids (9000-12000 cells).

### 5.3 Infill Material Strategy

The gap fill between chiplets uses the CLI-specified conductivity (1.6 W/(m·K)
from `--infill_cond_list`). The infill is applied only within the lateral
extent of the active chiplets, not across the entire domain, to avoid
artificial heat spreading paths.

### 5.4 Power Model

The solver assigns power only to active GPU and HBM leaf components, matching
the Anemoi reference where Power_Source power = 0. The total power budget is
400W (GPU) + 30W (6×5W HBMs) = 430W.

## 6. Potential Improvements

1. **Thermal isolators**: Embedding low-k materials (aerogel, air gaps)
   between GPU and HBM regions in the heatsink could reduce HBM temperatures.

2. **Finer grid resolution**: Adaptive mesh refinement near heat sources
   and material interfaces would improve accuracy.

3. **Transient analysis**: Extending to time-dependent thermal analysis
   would capture dynamic throttling behavior.

4. **Bonding layer detail**: More accurate modeling of micro-bump arrays
   (using bonding ratio calculations) would improve inter-chiplet thermal
   resistance accuracy.

## 7. Running the Code

```bash
# Run all configurations
bash scripts/run_all.sh

# Run individual configs
bash scripts/run_config1_3D_gpu_top.sh
bash scripts/run_config2_3D_gpu_bottom.sh
bash scripts/run_config3_2p5D.sh

# Summarize results
bash scripts/summarize_all.sh

# Generate visualizations
python3 visualize_results.py --results_dir out_therm
```

## 8. Output Files

All outputs are written to `out_therm/`:

- `*_results.yaml`: Per-box temperature and resistance results
- `*_temp_chart.png`: Temperature bar charts per configuration
- `temperature_comparison.png`: Cross-configuration comparison
- `summary.csv`, `summary.md`: Tabular summaries
- `post.png`, `post3D.png`: Chiplet placement plots
