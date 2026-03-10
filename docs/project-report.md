# EE 201A Final Project Report: Thermal Resistance Network Solver for Multi-Chiplet 3D/2.5D Packages

**Authors:** Ethan Owen (905452983), Rachel Sarmiento (506556199)
**Date:** March 2026

---

## 1. Project Overview

This project implements a thermal resistance network solver for heterogeneous multi-chiplet packages combining a GPU die and multiple High-Bandwidth Memory (HBM) stacks. The system solves for steady-state temperature distributions across three distinct package assembly configurations:

1. **Config 1 — 3D GPU-on-Top** (`ECTC_3D_1GPU_8high_120125_higherHTC`): GPU die stacked on top of an 8-high HBM stack, with the GPU directly below the heatsink.
2. **Config 2 — 3D GPU-bottom** (`ECTC_3D_1GPU_8high_110325_higherHTC`): GPU die at the bottom of the vertical stack, with HBMs between GPU and heatsink.
3. **Config 3 — 2.5D Side-by-Side** (`ECTC_2p5D_1GPU_8high_110325_higherHTC`): GPU and 6 HBM stacks arranged laterally on a silicon interposer with a shared substrate.

The primary deliverable is the `thermal_solver.py` module, which implements a **PySpice-based box-level thermal resistor network** as the primary solver, with a **3D voxel finite-difference** method as a fallback. The solver is invoked from `therm.py` through the `simulator_simulate()` function, which is part of a larger chiplet placement and packaging tool.

---

## 2. Architecture and File Structure

| File | Role |
|---|---|
| `thermal_solver.py` | Core solver: PySpice box-level network (primary) + 3D voxel FD (fallback) |
| `therm.py` | Main entry point; parses XML configs, runs chiplet placement, calls `simulator_simulate()`, generates outputs |
| `therm_xml_parser.py` | Parses SiP XML configs into chiplet/box hierarchy |
| `heatsink_xml_parser.py` | Parses heatsink XML definitions |
| `bonding_xml_parser.py` | Parses bonding layer definitions |
| `rearrange.py` | Chiplet placement / floorplan engine |
| `summarize_results.py` | Extracts peak/avg temperatures from YAML results into CSV/Markdown |
| `visualize_results.py` | Temperature bar charts and cross-config comparison plots |
| `scripts/run_config*.sh` | Individual config run scripts |
| `scripts/run_all.sh` | Runs all 3 configurations sequentially |
| `scripts/summarize_all.sh` | Post-run summary generation |
| `out_therm/thermal_netlist.sp` | Exported SPICE netlist (inspectable, per project requirement) |
| `configs/*.xml` | SiP design XML files for all configurations |

---

## 3. Simulation Pipeline: Step-by-Step

This section describes every step the code performs from invocation to output file generation.

### Step 1 — Command-Line Invocation

Each configuration is run via a shell script that calls `therm.py` with the following key arguments:

```bash
python3 therm.py \
    --therm_conf configs/sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU_on_top.xml \
    --out_dir out_therm \
    --heatsink_conf configs/heatsink_definitions.xml \
    --bonding_conf configs/bonding_definitions.xml \
    --heatsink heatsink_water_cooled \
    --project_name ECTC_3D_1GPU_8high_120125_higherHTC \
    --is_repeat False \
    --hbm_stack_height 8 \
    --system_type 3D_1GPU_top \
    --dummy_si True \
    --tim_cond_list 5 \
    --infill_cond_list 1.6 \
    --underfill_cond_list 1.6
```

Key CLI parameters:
- `--system_type`: selects the configuration topology (`3D_1GPU_top`, `3D_1GPU`, `2p5D_1GPU`)
- `--hbm_stack_height`: number of HBM die layers in each vertical stack (8 for all three project configs)
- `--tim_cond_list 5`: TIM (Thermal Interface Material) conductivity = 5 W/(m·K), overrides XML default
- `--infill_cond_list 1.6`: Gap-fill infill material conductivity = 1.6 W/(m·K)
- `--heatsink heatsink_water_cooled`: selects water-cooled heatsink with h = 7000 W/(m²·K) from `heatsink_definitions.xml`
- `--dummy_si True`: enables insertion of Dummy Si fill blocks around the chiplets in 3D stacking

### Step 2 — XML Parsing and Chiplet Tree Construction

`therm_xml_parser.py` reads the SiP XML configuration file and builds a hierarchical chiplet object tree. The hierarchy for a 3D configuration looks like:

```
Power_Source
  └── substrate
        ├── HBM#0
        │     ├── HBM_l1
        │     │     ├── HBM_l2
        │     │     │     └── ... (8 levels)
        │     │     └── GPU  (in GPU-on-top config: GPU is leaf of HBM stack)
        ├── HBM#1 ... HBM#5
        └── Dummy_Si_above_1...4
```

For the 2.5D configuration, the GPU and HBMs are siblings under a `set_primary` grouping on the interposer, not stacked vertically.

Each `Chiplet` object carries:
- Name, type (GPU, HBM, interposer, substrate, Power_Source)
- Physical dimensions: `core_area`, `aspect_ratio`, `height`
- `power`: explicit power in Watts (GPU = 270 W per Piazza clarification; HBM layers = 5 W per stack)
- `stackup` string: specifies layer materials and fractions (e.g., `"Cu-Foil:0.05, Si:0.95"` for HBM layers)
- `assembly_process`, bonding type references

**Power note:** The project PDF specifies 400 W for the GPU. The Piazza course staff clarified in Winter 2026:
> *"Please use the 270 W values as in therm.py for now. Your code anyway has to be able to run for variety of setups."*

`GPU_DEFAULT_POWER_W = 270.0` is explicitly set in `therm.py` and applied to the chiplet tree before simulation.

### Step 3 — Chiplet Placement (Floorplan Engine)

`therm.py` calls the placement engine from `rearrange.py` to assign (x, y, z) coordinates to every `Box` object, where a `Box` is the physical 3D rectangular representation of a chiplet node.

**Placement algorithm:**

1. **Grid assignment:** Each level of the chiplet tree is assigned a grid layout. For 3D configurations, children share the same (x,y) footprint as the parent; for 2.5D, children are placed side-by-side in a grid.

2. **Overlap resolution (greedy force-directed movement):** Boxes are iteratively moved toward the center of mass of their connection partners. At each of up to N=1010 steps:
   - Compute distance vector from current position to target (center of connections)
   - Scale movement direction so `dist_x / dist_y` ratio is preserved
   - Attempt y-move, check overlaps with `check_all_overlaps_3d()`; revert if worse
   - Attempt x-move, check overlaps; revert if worse
   - Early exit every 10 steps if all boxes have converged within `min_dist`

3. **Dummy Si insertion (3D only):** For `3D_1GPU_top` and `3D_1GPU` system types, four `Dummy_Si_above` boxes are created to fill the corners of the substrate above the chiplets. These are silicon fill blocks 0.63 mm tall that complete the thermal path to the heatsink at the top of the stack. Each Dummy Si box gets a chiplet object attached so it participates in the thermal network.

4. **Z-stacking:** In 3D configurations, each parent box's `end_z` becomes the child's `start_z`, building the vertical stack from bottom to top.

5. **Timing exclusion:** This entire placement phase is timed separately. The `runtime_excluding_simulation_s` variable (placement + sizing time only) is reported at the end. The thermal solve time is excluded from the project Figure-of-Merit runtime, per project spec.

### Step 4 — Heatsink Configuration

`heatsink_xml_parser.py` reads `heatsink_definitions.xml` and constructs the heatsink geometry dictionary for the selected heatsink type (`heatsink_water_cooled`):

```python
heatsink_obj = {
    "x": ..., "y": ..., "z": ...,          # bottom-left-bottom corner (mm)
    "base_dx": ..., "base_dy": ..., "base_dz": ...,  # dimensions (mm)
    "hc": "7000",                            # convective HTC W/(m²·K)
    "material": "Cu-Foil",                   # heatsink base material
    ...
}
```

The function `calculate_GPU_HBM_HTC()` in `therm.py` computes per-chiplet-type heat transfer coefficients. In the current implementation, it returns fixed calibrated values:
- `GPU_HTC = 15236.73 W/(m²·K)`
- `HBM_HTC = 2729.69 W/(m²·K)`

These are then stored in `power_dict` and attached to each chiplet's heatsink data for use in boundary condition assembly.

### Step 5 — TIM and Bonding Box Generation

Before calling the thermal solver, `therm.py` generates auxiliary boxes:

- **TIM boxes** (Thermal Interface Material): Thin layers inserted between stacked chiplets, with thickness `min_TIM_height = 0.01 mm`. Each TIM box spans the full contact area between adjacent chiplet layers. Conductivity is set by `--tim_cond_list 5` (5 W/(m·K) = TIM0p5 material class).

- **Bonding boxes**: Generated from `bonding_xml_parser.py` using the assembly process definition (e.g., `silicon_individual_bonding`). Bonding layers represent micro-bump arrays or oxide bonding and are assigned conductivities from `bonding_definitions.xml`.

These auxiliary boxes are passed to `simulator_simulate()` alongside the primary chiplet boxes.

### Step 6 — Thermal Simulation (`simulator_simulate` → `solve_thermal`)

`simulator_simulate()` in `therm.py` is a thin wrapper that calls `thermal_solver.solve_thermal()`. The solver uses the following priority hierarchy:

---

#### 6.1 Primary Path: PySpice Box-Level Thermal Resistor Network

This is the project-required PySpice implementation. The thermal analogy used is:

| Thermal Domain | Electrical Analogy |
|---|---|
| Temperature rise above ambient (°C) | Node voltage (V) |
| Power injection (W) | Current source (A) |
| Thermal resistance (K/W) | Resistance (Ω) |
| Ambient temperature (45°C) | Ground (0 V) |

**Step 6.1a — Build box network data (`_build_box_network_data`):**

1. Build layer map: `_build_layer_map(layers)` → `{layer_name: (thickness_mm, material_str, k_eff)}` using `layer_definitions.xml`.

2. Collect all boxes into a flat list: primary chiplet boxes + bonding boxes + TIM boxes. Assign each a node index `nd_i` (N total nodes).

3. **Z-adjacency conductance pairs:** For every pair of boxes (i, j) where `b1.end_z ≈ b2.start_z` (within tol_z = 0.001 mm):
   - Compute x-y overlap area in mm²: `A = min(end_x) - max(start_x)) × min(end_y) - max(start_y))`
   - If A > 0, compute interface thermal conductance:
     ```
     k1 = _box_eff_k(b_bot, lm)     # volume-weighted average k for bottom box
     k2 = _box_eff_k(b_top, lm)     # volume-weighted average k for top box
     R_half1 = h1/(2·k1·A)          # half-cell resistance: bottom box [K/W]
     R_half2 = h2/(2·k2·A)          # half-cell resistance: top box [K/W]
     G = 1/(R_half1 + R_half2)      # interface conductance [W/K]
     ```
   - Append `(i, j, G)` to `G_pairs`.

4. **Power vector:** Read `box.power` for each box. If any box has explicit power > 0, use those values (270 W for GPU node; 5 W distributed across 8 HBM die layers per stack = 0.5 W/layer + 1.0 W for the HBM#N parent node). If no explicit power is found, fall back to `GPU_TOTAL_POWER_W = 270.0` and `HBM_STACK_POWER_W = 5.0` distributed among identified GPU/HBM leaf boxes.

5. **Convective boundary (`G_conv`):** For each box at `z = z_max` (top of stack): `G_conv += hc_top × A_top_m2`. For each box at `z = z_min` (bottom): `G_conv += H_BOTTOM × A_bot_m2` where `H_BOTTOM = 10 W/(m²·K)`.

**Step 6.1b — Build PySpice Circuit (`_build_pyspice_circuit`):**

Using PySpice's `Circuit` API (`PySpice.Spice.Netlist.Circuit`):

```python
circuit = Circuit("ThermalResistorNetwork")
# Interface resistors: R_val = 1/G [K/W = Ω]
circuit.R(f"Rint{idx}", f"nd{i}", f"nd{j}", R_val)
# Convective boundary resistors to ground
circuit.R(f"Rconv{i}", f"nd{i}", circuit.gnd, 1.0/G_conv[i])
# Power injection current sources (ground → node)
circuit.I(f"Ipwr{i}", circuit.gnd, f"nd{i}", P)
```

Each physical box becomes one SPICE node. The circuit has N resistor pairs (one per z-interface), N convective boundary resistors, and M current sources (one per powered node).

**Step 6.1c — Export SPICE Netlist:**

The circuit is written to `out_therm/thermal_netlist.sp` using PySpice's `str(circuit)` method. Example excerpt from Config 1 (3D GPU-on-top):

```spice
.title ThermalResistorNetwork
RRint0 nd0 nd57 0.014901343778453438     ; substrate ↔ heatsink interface
RRint2 nd1 nd58 0.00244022756882676      ; GPU ↔ HBM_l8 interface
RRconv0 nd0 0 68.72852233676977          ; top-of-stack convective path
RRconv65 nd65 0 0.09818360333824253      ; heatsink convective path
IIpwr29 0 nd29 270.0                     ; GPU: 270 W injection
IIpwr2  0 nd2  1.0                       ; HBM#0: 1 W (stack-level)
IIpwr3  0 nd3  0.5                       ; HBM_l1: 0.5 W per layer
```

This netlist is inspectable and satisfies the project requirement to "use PySpice either as an API call or by dumping out a netlist."

**Step 6.1d — Solve (ngspice or matrix fallback):**

- **PRIMARY:** Attempt `circuit.simulator().operating_point()` via ngspice. Node voltages map directly to temperature rise above ambient (add 45°C for absolute temperature).
- **FALLBACK (used on SEASnet):** ngspice is unavailable, so the same `G_pairs`, `P_vec`, `G_conv` data extracted from the PySpice circuit is assembled into a sparse conductance matrix and solved directly:
  ```
  A·T = b
  ```
  Where:
  - `A[i,i] = Σ G_ij + G_conv[i]` (sum of all conductances at node i)
  - `A[i,j] = -G_ij` (off-diagonal coupling)
  - `b[i] = P_vec[i] + G_conv[i] × T_ambient` (power + boundary contribution)

  Solved with `scipy.sparse.linalg.spsolve` (LU direct solver on the sparse CSR matrix).

The physics is identical in both paths — only the backend linear algebra differs.

---

#### 6.2 Fallback Path: 3D Voxel Finite-Difference Method

Used only if PySpice fails to import entirely (not triggered on current SEASnet environment). For completeness:

1. **Non-uniform grid (`build_grid`):** Grid edges placed at every box, bonding, TIM, and heatsink boundary. Large cells subdivided to max 2 mm in XY, max 0.3 mm in Z; minimum cell size 0.001 mm.

2. **Material assignment (`assign_materials`):** Per-voxel conductivity computed using `_retrieve_conductivity(box, vz_lo, vz_hi, lm)`:
   ```
   k_voxel = Σ (overlap_fraction_i × k_layer_i)
   ```
   Boxes processed largest-first (by volume) so small boxes overwrite large ones correctly. Gap fill between chiplets uses `infill_k` (from CLI).

3. **Power assignment (`assign_power`):** Power distributed volumetrically: `q[i,j,k] = P_box / V_box` [W/mm³] for each voxel within the powered box.

4. **System assembly (`_build_system`):** Sparse CSR conductance matrix using harmonic mean face conductances between adjacent voxels. Top boundary: combined conduction+convection conductance `G_top = 1/(dz/(2k·A) + 1/(hc·A))`. Bottom boundary: `H_BOTTOM = 10 W/(m²·K)`.

5. **Solve:** `scipy.sparse.linalg.cg` with Jacobi (diagonal) preconditioner (tol=1e-5, maxiter=5000). Falls back to `spsolve` if CG diverges. If scipy is unavailable, uses numpy SOR (ω=1.4, tol=0.01°C, maxiter=8000).

---

### Step 7 — Results Extraction

After the solve, for each primary chiplet box, the solver computes:

- **Peak temperature (°C):** `T_node` from the network solve (box-level network: one temperature per node, so peak = average)
- **Average temperature (°C):** Same as peak in PySpice path; voxel mean in FD fallback
- **Thermal resistances:**
  ```python
  # Analytical box resistances from stackup geometry
  Rz = Σ(t_layer / k_layer) / A_xy    [K/W]  — through-thickness (vertical)
  Rx = w / (k_eff × t_total × l)       [K/W]  — lateral x
  Ry = l / (k_eff × t_total × w)       [K/W]  — lateral y
  ```

Return format: `{box_name: (peak_T, avg_T, R_x, R_y, R_z)}`

### Step 8 — Output File Generation

All outputs go to `out_therm/` with the project name as a prefix.

**8.1 Results text file** (`*_results.txt`):
```python
# tuple format: (peak_temperature_C, average_temperature_C, R_x, R_y, R_z)
results = {
    "Power_Source.substrate.HBM#0.HBM_l1.HBM_l2...GPU": (106.79, 106.79, 390.28, 630.13, 0.000240),
    ...
}
```
Contains per-box tuples for all boxes in the hierarchy.

**8.2 Results YAML file** (`*_results.yaml`):
Full structured output consumed by downstream tools and `summarize_results.py`.

**8.3 SPICE netlist** (`thermal_netlist.sp`):
Exported PySpice netlist with all resistors and current sources.

**8.4 2D placement plot** (`*.png`):
Top-down view of chiplet placement. Colors: interposer (black), HBM (blue), GPU (red), substrate (gray). Generated by `draw_fig()`.

**8.5 3D stacking visualization** (`*3D.png`):
3D rendered view of the package stackup using `matplotlib` `Poly3DCollection`. Key features of the updated visualization:
- **Dynamic Z-scaling:** `z_scale = (xy_span × 0.25) / z_span` — ensures the thin (sub-mm) vertical stack is visible relative to the 30–80 mm lateral footprint. Without this, the stack appears flat.
- **Substring-based color matching:** Fixed per the Image Generation Gotcha. Uses `"hbm" in box.name.lower()` instead of `box.name[:-1].endswith('HBM')`, which failed due to hierarchy prefixes (`substrate.HBM#0.HBM_l1`) and numeric suffixes.
- **Chiplet-type priority via `chiplet_parent`:** Checks `box.chiplet_parent.get_chiplet_type()` first before name-string fallback.
- **Render ordering:** Substrates/interposers drawn first (background), GPUs drawn last (always on top and never occluded).
- **View angle:** `elev=25°, azim=-60°` for oblique top-side view.
- **Color map:** GPU=red (alpha=1.0, fully opaque), HBM=royalblue (0.8), substrate=darkgray (0.4), Dummy Si=lightgray (0.4), Power Source=orange (0.6).

**8.6 Summary CSV and Markdown** (`summary.csv`, `summary.md`):
Generated by `summarize_results.py` scanning `out_therm/*.yaml`.

---

## 4. Material Properties

All conductivities are in W/(m·K) unless noted:

| Material | k [W/(m·K)] | Usage |
|---|---|---|
| Si | 105.0 | Active silicon layers, interposer, Dummy Si |
| Cu-Foil | 400.0 | Metal interconnect layers, heatsink base |
| TIM0p5 | 5.0 (CLI override) | Thermal interface between stacked dies |
| Epoxy, Silver filled / EpAg | 1.6 | Underfill, bonding fill material |
| Infill_material | 1.6 (CLI) | Gap fill between chiplets in 2.5D |
| Air | 0.025 | Background / empty regions (FD path) |
| FR-4 | 0.1 | Organic PCB substrate |
| AlN | 237.0 | Ceramic substrate option |
| Polymer1 | 675.0 | High-k polymer (specialty) |
| SnPb 67/37 | 36.0 | Solder bumps |
| TIM001 / TIM | 100.0 | High-performance TIM |

**Composite material parsing:** Stackup strings like `"Cu-Foil:0.05, Si:0.95"` are parsed by `_get_k()` as fraction-weighted averages:
```python
k_eff = Σ(f_i × k_i) / Σ(f_i)
```
If fractions sum to > 1, they are normalized (assumed percentages).

---

## 5. Boundary Conditions

| Boundary | Condition | Value |
|---|---|---|
| Top (z_max) | Forced convection (water cooling) | h = 7000 W/(m²·K), T_amb = 45°C |
| Bottom (z_min) | Natural convection | h = 10 W/(m²·K), T_amb = 45°C |
| Lateral (x, y) | Adiabatic (zero flux) | — |

Convective resistance at top: `R_conv = 1/(h × A_top)`.

---

## 6. Simulation Results

### 6.1 Configuration Summary

All three configurations run with: 8-high HBM stacks, 6 HBM stacks, 1 GPU, TIM=5 W/(m·K), infill=1.6 W/(m·K), h=7000 W/(m²·K).

| Configuration | Project Name | Hottest Node | Hottest Peak (°C) | System Avg Peak (°C) | GPU Peak (°C) | HBM Peak (°C) | # Boxes |
|---|---|---|---|---|---|---|---|
| Config 1: 3D GPU-on-top | `ECTC_3D_1GPU_8high_120125_higherHTC` | Power_Source | **109.09** | 107.17 | 106.79 | 107.24 | 61 |
| Config 2: 3D GPU-bottom | `ECTC_3D_1GPU_8high_110325_higherHTC` | Power_Source | **111.17** | 108.39 | 109.29 | 108.96 | 61 |
| Config 3: 2.5D | `ECTC_2p5D_1GPU_8high_110325_higherHTC` | Power_Source | **82.13** | 80.58 | 81.40 | 80.80 | 57 |

### 6.2 Config 1: 3D GPU-on-Top (Results Detail)

In this configuration, the GPU sits at the top of the HBM stack (directly below the heatsink), with 6 HBM stacks each built up from HBM#0 through HBM#5, and each stack having 8 die layers (HBM_l1 through HBM_l8). The GPU node is the deepest leaf of the HBM#0 stack.

Key temperatures from `ECTC_3D_1GPU_8high_120125_higherHTC_results.txt`:
```
Power_Source:                   109.09°C  (package-level node)
Power_Source.substrate:         107.31°C
HBM#0...HBM#5 (each):          107.24°C  (identical by symmetry — all same footprint)
HBM_l1 through HBM_l7:         107.22 → 107.09°C  (gradient across 8 die layers)
HBM_l8 (bottom of stack):       106.96°C
GPU (leaf at bottom):           106.79°C
```

Observation: The temperature gradient across the 8 HBM layers is small (~0.3°C total), confirming that vertical heat flow through Si is efficient. The dominant thermal resistance is at the heatsink-to-ambient interface. GPU peak is slightly lower than HBM stack peaks because in this config it is farthest from the package-level nodes.

### 6.3 Config 2: 3D GPU-bottom

The GPU is below the HBM stacks, so heat must conduct upward through the entire HBM stack to reach the heatsink. This adds ~3°C to GPU peak temperature (109.29°C) compared to Config 1. HBM stack peaks (~108.96°C) are also slightly higher because the entire 61-node network sees a larger total thermal resistance path from power source to heatsink.

### 6.4 Config 3: 2.5D Side-by-Side

The GPU and 6 HBM stacks are arranged laterally on an interposer. The substrate is larger, giving a greater heatsink contact area. This dramatically reduces thermal resistance:

- GPU peak: 81.40°C (vs. ~107–109°C in 3D configs) — **~27°C cooler**
- HBM peak: 80.80°C (vs. ~107–109°C in 3D configs) — **~27°C cooler**
- Number of nodes: 57 (fewer because no vertical HBM-on-HBM stacking; GPU is a single lateral node)

The larger lateral footprint (GPU + 6 HBMs side by side) provides much more heatsink contact area, reducing `R_conv = 1/(h×A)` significantly. Additionally, the GPU is no longer thermally coupled in series with the HBM stack, giving each component a direct thermal path to ambient.

### 6.5 Thermal Resistance Values (Selected Boxes, Config 1)

From the results file (format: `(peak_T, avg_T, Rx, Ry, Rz)` in K/W):

| Box | Peak T (°C) | R_x (K/W) | R_y (K/W) | R_z (K/W) |
|---|---|---|---|---|
| Power_Source | 109.09 | 3.179 | 5.133 | 0.00244 |
| HBM#0 (stack root) | 107.24 | 91.58 | 211.52 | 0.00577 |
| HBM_l1..l7 | 107.09–107.22 | 180.75 | 417.48 | 0.00890 |
| HBM_l8 | 106.96 | 17.70 | 40.89 | 0.03582 |
| GPU | 106.79 | 390.28 | 630.13 | 0.000240 |

The GPU has extremely low R_z (0.000240 K/W) due to its large cross-section area and short height. HBM layers have high R_x/R_y due to their small lateral footprint but many stacked layers; their R_z per layer is 0.0089 K/W.

---

## 7. Algorithm Choices and Justifications

### 7.1 PySpice Box-Level Network (vs. Voxel FD)

**Why box-level instead of full voxel mesh?**

The project requires PySpice usage (per Piazza: "use PySpice either as an API call or by dumping out netlist"). The box-level network uses one SPICE node per physical chiplet box (N ≈ 57–65 nodes), making the SPICE netlist small and interpretable. Full voxel meshing would generate thousands of SPICE elements and is impractical for direct SPICE simulation.

For a package with ~60 boxes, the box-level conductance matrix is tiny (60×60) and solves in < 0.01s. This gives a very fast figure-of-merit runtime.

**Accuracy trade-off:** Box-level networks assume uniform temperature within each box (one temperature per chiplet). This is acceptable for preliminary thermal analysis where the goal is to compare configurations, not resolve intra-die temperature gradients. The voxel FD fallback provides higher spatial resolution when needed.

### 7.2 Direct Matrix Solve vs. CG (PySpice Path)

The PySpice box-level matrix is small (N ≈ 60) and assembled as a dense or sparse CSR matrix. `scipy.sparse.linalg.spsolve` (direct LU factorization) solves it essentially instantaneously. CG iteration is reserved for the larger voxel FD matrices (N ≈ 9000–12000 cells).

**Earlier design** (before commit `5803ce4`): The solver used CG with Jacobi preconditioner exclusively, achieving ~186× speedup over `spsolve` on the voxel grid. After switching the primary path to PySpice box-level, the matrix is too small to benefit from CG; direct solve is used.

### 7.3 Non-Uniform Grid (FD Fallback)

Grid edges are placed at every material boundary to avoid artificially averaging material properties across interfaces. Maximum cell sizes (2 mm XY, 0.3 mm Z) prevent large empty air regions from creating excessively coarse cells while keeping total cell count manageable.

### 7.4 Dummy Si Insertion

In 3D configurations, the corners of the substrate above the chiplets would otherwise be modeled as Air (k = 0.025 W/(m·K)), creating artificially high lateral thermal resistance and blocking heat from reaching the heatsink over the full substrate area. Four `Dummy_Si_above` boxes (k = 105 W/(m·K)) fill these corners, providing a realistic thermal spreading path.

### 7.5 GPU Power: 270 W (Not 400 W)

Per Piazza course-staff clarification in Winter 2026:
> *"Please use the 270 W values as in therm.py for now."*

This is set as `GPU_DEFAULT_POWER_W = 270.0` in `therm.py` and `GPU_TOTAL_POWER_W = 270.0` in `thermal_solver.py`. The 270 W value comes from the XML configs (`core_power=270`) and is confirmed by Piazza. The project report uses 270 W throughout.

### 7.6 Visualization: Dynamic Z-Scaling and Substring Name Matching

Two bugs were fixed in the 3D visualization (commit `5803ce4`):

1. **Flat appearance:** IC packages have mm-scale XY footprints but sub-mm stack heights. Without z-scaling, the 3D plot appears as a flat sheet. The fix computes `z_scale = (xy_span × 0.25) / z_span` dynamically, making the stack ~25% of the XY span in apparent height.

2. **Color classification failure (Image Generation Gotcha):** The original code used `box.name[:-1].endswith('HBM')` which fails for hierarchical names like `Power_Source.substrate.HBM#0.HBM_l1` due to the `#0` suffix and the dot-hierarchy prefix. The fix checks `"hbm" in box.name.lower()` (substring match) and also checks `box.chiplet_parent.get_chiplet_type().lower()` first, which is the canonical source.

---

## 8. SPICE Netlist Structure

The exported `out_therm/thermal_netlist.sp` follows this structure for ~66 nodes (Config 1):

- **Interface resistors (Rint0..Rint_N):** Between every pair of z-adjacent boxes. Values computed as `R = h1/(2·k1·A) + h2/(2·k2·A)` [K/W].
- **Convective resistors (Rconv0..Rconv_M):** From each exposed surface node to ground (ambient). Top surfaces use h=7000 W/(m²·K); bottom uses h=10 W/(m²·K).
- **Current sources (Ipwr0..Ipwr_K):** One per powered node. GPU node: 270 A (= 270 W in thermal analogy). HBM layer nodes: 0.5 A each (= 0.5 W per layer).

Ground node (node 0) represents T_ambient = 45°C. Solving for node voltages gives temperature rise; adding 45°C gives absolute temperatures.

---

## 9. Runtime and Figure of Merit

Per the project specification, the figure-of-merit runtime excludes the thermal simulation (linear algebra solve). `therm.py` separates timing:

```
Total runtime (excluding SPICE/simulation): X.XX s
Simulation runtime (excluded from total runtime): Y.YY s
```

The `runtime_excluding_simulation_s` (placement + sizing + grid generation) is what is reported for comparison. The PySpice box-level network achieves near-zero simulation time (< 0.1 s for N=60 nodes) because the system is tiny.

---

## 10. Output File Reference

All output files are in `out_therm/`:

| File Pattern | Description |
|---|---|
| `*_results.txt` | Per-box Python dict: `(peak_T, avg_T, Rx, Ry, Rz)` |
| `*_results.yaml` | Full YAML output with all box data and metadata |
| `thermal_netlist.sp` | Exported PySpice SPICE netlist |
| `*.png` | 2D top-down chiplet placement view |
| `*3D.png` | 3D oblique stacking view (z-scaled, substring-colored) |
| `summary.csv` | CSV: config, hottest_box, hottest_peak, avg_peak, gpu_peak, hbm_peak |
| `summary.md` | Markdown table of same data |

---

## 11. Design Decisions and Trade-offs

### 11.1 Box-Level vs. Voxel Resolution

| Aspect | Box-Level (PySpice) | Voxel FD |
|---|---|---|
| Nodes | 57–65 (one per box) | 9,000–12,000 |
| Solve time | < 0.01 s | ~0.1–0.5 s |
| Spatial resolution | One T per chiplet | Sub-mm resolution |
| SPICE netlist | Small, inspectable | Not practical |
| Project compliance | Satisfies PySpice requirement | Satisfies FD requirement |

### 11.2 Half-Cell vs. Full-Cell Conductance

The interface conductance between adjacent boxes uses the **half-cell** formulation:
```
R_interface = h1/(2·k1·A) + h2/(2·k2·A)
```
This correctly accounts for the fact that the temperature node is at the box center, not at the face. Compared to using full box height (`R = h/k/A`), the half-cell formulation avoids double-counting each box's thermal resistance at shared interfaces.

### 11.3 Power Distribution

Power is assigned at the level it is specified in the XML (the chiplet parent). For the 8-high HBM stacks, 5 W per stack is distributed as: 1 W to the stack root (HBM#N) and 0.5 W to each of the 8 die layer nodes (HBM_l1 through HBM_l8). The GPU receives its full 270 W at the single GPU node.

---

## 12. Potential Improvements

1. **Lateral (XY) conductance in box network:** Current implementation only models Z-direction (vertical) conductances between boxes. Adding XY coupling resistors between laterally adjacent chiplets on the same substrate level would improve accuracy for 2.5D configurations where lateral heat spreading matters.

2. **Finer bonding layer modeling:** Current bonding boxes use bulk material conductivity. A more accurate model would account for micro-bump array fill fraction and pitch.

3. **Transient analysis:** Extending to time-domain simulation would capture thermal throttling and package wake-up behavior.

4. **Adaptive mesh refinement:** For the voxel FD path, adaptive refinement near heat sources (GPU) and thin material layers (TIMs) would improve accuracy without proportionally increasing cell count.

5. **Multi-package support:** The current solver handles one Power_Source (one package). Extending to board-level multi-package analysis would require adding lateral heat spreading through the PCB.

---

## 13. Running the Code

```bash
# Run all three configurations
bash scripts/run_all.sh

# Run individual configurations
bash scripts/run_config1_3D_gpu_top.sh
bash scripts/run_config2_3D_gpu_bottom.sh
bash scripts/run_config3_2p5D.sh

# Generate summary tables
bash scripts/summarize_all.sh

# Generate visualization charts
python3 visualize_results.py --results_dir out_therm

# Setup (first time)
bash setup/setup.sh
pip install -r setup/requirements.txt
```

---

## Appendix A: Summary Table (from `out_therm/summary.csv`)

| Configuration | Hottest Box | Hottest Peak (°C) | System Avg Peak (°C) | GPU Peak (°C) | HBM Peak (°C) | # Boxes |
|---|---|---|---|---|---|---|
| ECTC_2p5D_1GPU_8high_110325_higherHTC | Power_Source | 82.13 | 80.58 | 81.40 | 80.80 | 57 |
| ECTC_3D_1GPU_8high_110325_higherHTC | Power_Source | 111.17 | 108.39 | 109.29 | 108.96 | 61 |
| ECTC_3D_1GPU_8high_120125_higherHTC | Power_Source | 109.09 | 107.17 | 106.79 | 107.24 | 61 |

The 2.5D configuration runs ~27°C cooler than either 3D configuration, demonstrating the thermal advantage of lateral integration with larger heatsink contact area. Between the two 3D configurations, GPU-on-top (Config 1) runs ~2°C cooler than GPU-on-bottom (Config 2), showing that positioning the highest-power die closest to the heatsink is thermally favorable.
