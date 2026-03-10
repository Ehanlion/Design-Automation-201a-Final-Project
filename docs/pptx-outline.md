# PowerPoint Presentation Outline — EE 201A Final Project
## Thermal Resistance Network Solver for Multi-Chiplet 3D/2.5D Packages

**Authors:** Ethan Owen (905452983), Rachel Sarmiento (506556199)
**Suggested format:** 5 slides, 16:9 widescreen, dark technical theme (navy/white/accent colors)

---

## SLIDE 1 — Title & Problem Statement

**Title:**
> Thermal Resistance Network Solver for GPU + HBM Multi-Chiplet Packages

**Subtitle:**
> EE 201A Final Project — Ethan Owen & Rachel Sarmiento

---

**Left column — Problem context (bullet points):**
- Modern AI/HPC packages stack GPU + HBM dies in 3D or arrange them in 2.5D on a silicon interposer
- Thermal management is critical: HBM reliability degrades above ~85°C; GPU performance throttles above ~100°C
- Goal: compute steady-state temperature maps for 3 configurations and compare packaging strategies

**Right column — Three configurations (diagram or labeled boxes):**
```
Config 1: 3D GPU-on-Top     Config 2: 3D GPU-Bottom     Config 3: 2.5D
─────────────────────       ─────────────────────        ─────────────────────
 [GPU]                        [HBM_l8]                   [GPU] [HBM] [HBM] [HBM]
 [HBM_l8]                     [HBM_l7]                   ───────────────────────
 [HBM_l7]  ← 8-high           ...                             silicon interposer
 ...          HBM stack        [GPU]                   
```

**Key facts box (bottom, accent color):**
- 1 GPU (270 W) + 6 HBM stacks (5 W each = 30 W total) = **300 W total**
- Water-cooled heatsink: h = 7000 W/(m²·K), T_ambient = 45°C
- HBM stack height: 8 die layers per stack

**Suggested visuals:** Include the `*3D.png` render of Config 1 (the colorful 3D oblique view of the stacked chiplets) in the right third of the slide.

---

## SLIDE 2 — Solver Architecture: PySpice Thermal Resistor Network

**Title:**
> PySpice-Based Box-Level Thermal Network (Primary Solver)

---

**Center/main area — Flowchart (left to right):**

```
XML Config ──→ Chiplet Tree ──→ Box Objects ──→ Build Network ──→ PySpice Circuit ──→ Solve ──→ Results
               (hierarchy         (N ≈ 60                          API + netlist      matrix
                parsing)           nodes)        z-adjacency        export            or ngspice
                                                 + power vec
                                                 + conv. BC
```

**Left column — Thermal-to-Electrical Analogy (table):**

| Thermal | Electrical |
|---|---|
| Temperature rise (°C) | Voltage (V) |
| Power injection (W) | Current source (A) |
| Thermal resistance (K/W) | Resistance (Ω) |
| Ambient (45°C) | Ground (0 V) |

**Right column — Network construction steps (numbered):**
1. Parse all boxes into N nodes (one per physical chiplet die)
2. For each z-adjacent pair with x-y overlap:
   - `G = 1 / (h₁/2k₁A + h₂/2k₂A)` — half-cell interface conductance
3. Power injection: GPU node ← 270 A; HBM layers ← 0.5 A each
4. Convective BC: `G_conv = h × A_top` to ground
5. Build `PySpice.Spice.Netlist.Circuit` → export `thermal_netlist.sp`
6. Attempt ngspice `.op`; fall back to `scipy.sparse.linalg.spsolve`

**Bottom callout box (accent color):**
> Satisfies project requirement: *"use PySpice either as an API call or by dumping out netlist"*
> Netlist exported to `out_therm/thermal_netlist.sp` for TA inspection.

**Suggested visuals:**
- Small excerpt of the SPICE netlist (2–3 lines: one Rint, one Rconv, one Ipwr)
- Schematic diagram: 3 nodes in series with current source at GPU node, Rconv to ground at top

---

## SLIDE 3 — Implementation Details: Step-by-Step Pipeline

**Title:**
> End-to-End Pipeline: From XML to Temperature Map

---

**Full-width timeline / pipeline (horizontal, 6 steps with icons):**

**Step 1 — XML Parsing**
- `therm_xml_parser.py` reads SiP XML → builds `Chiplet` object hierarchy
- Each chiplet: dimensions, `stackup` string (layer materials), power, bonding type
- 3D config: GPU is a leaf child of HBM stack root

**Step 2 — Chiplet Placement**
- `rearrange.py` assigns (x, y, z) to every box
- Overlap resolution: greedy force-directed iteration (max 1010 steps per level)
- Dummy Si fill: 4 corner blocks added to complete thermal path to heatsink
- **Timed separately** from simulation (placement time = Figure of Merit)

**Step 3 — Material Properties**
- Conductivities from `layer_definitions.xml`; composites parsed as fraction-weighted average
- CLI overrides: TIM=5 W/(m·K), infill=1.6 W/(m·K)
- Key: k_eff = Σ(fᵢ × kᵢ) / Σ(fᵢ) for stackup strings like `"Cu-Foil:0.05, Si:0.95"`

**Step 4 — Network Assembly**
- `_build_box_network_data()`: scans all box pairs for z-adjacency
- Builds G_pairs list (conductances), P_vec (power), G_conv (boundary)
- TIM boxes (0.01 mm, k=5) and bonding boxes inserted between stacked dies

**Step 5 — PySpice Solve**
- Primary: ngspice `.op` analysis → node voltages = temperature rise
- Fallback: assemble conductance matrix A, solve A·T = b with `spsolve`
- Matrix size: ~60×60 for box-level (solves in < 0.01 s)

**Step 6 — Output Generation**
- `*_results.txt`: Python dict of `(peak_T, avg_T, Rx, Ry, Rz)` per box
- `*_results.yaml`: full structured output
- `thermal_netlist.sp`: exported SPICE netlist
- `*.png` / `*3D.png`: 2D placement + 3D oblique visualization

**Bottom note (small):**
- 3D visualization bug fix: z-scale = `(xy_span × 0.25) / z_span`; color by substring match (Image Generation Gotcha)
- Runtime reporting: placement time and simulation time reported separately

---

## SLIDE 4 — Results and Comparison

**Title:**
> Simulation Results: Temperature Map Across All Three Configurations

---

**Top section — Results summary table (large, centered):**

| Configuration | GPU Peak (°C) | HBM Peak (°C) | System Hottest (°C) | # Nodes |
|---|---|---|---|---|
| 3D GPU-on-Top (Config 1) | 106.8 | 107.2 | 109.1 | 61 |
| 3D GPU-Bottom (Config 2) | 109.3 | 109.0 | 111.2 | 61 |
| **2.5D Side-by-Side (Config 3)** | **81.4** | **80.8** | **82.1** | **57** |

**Left column — Key finding bullets:**
- 2.5D is **~27°C cooler** than 3D — larger heatsink footprint reduces convective resistance
- GPU-on-top ~2°C cooler than GPU-bottom — highest-power die closest to heatsink is thermally optimal
- HBM layer gradient across 8-die stack: only ~0.3°C total — silicon is an efficient conductor vertically
- Hottest node is always `Power_Source` (package-level root) due to high convective lumped resistance

**Right column — Thermal resistance breakdown (mini table):**

| Box (Config 1) | R_z (K/W) | Note |
|---|---|---|
| GPU | 0.000240 | Very thin, large area |
| HBM_l1..l7 | 0.00890 | Per 8-high layer |
| HBM#0 stack root | 0.00577 | Full stack R_z |
| Power_Source | 0.00244 | Package root |

**Bottom section — Analysis (2 columns):**

*3D configurations:*
- Vertical stack thermal resistance ≈ sum of TIM + bonding layers
- Heat path: GPU → TIM → HBM stack → heatsink (in GPU-bottom: 8 die layers of thermal resistance in series)
- All components thermally coupled — HBM and GPU reach similar temperatures

*2.5D configuration:*
- Each chiplet has independent direct path to heatsink
- Larger combined footprint: total convective resistance R_conv = 1/(h×A_total) much smaller
- GPU 0.6°C above HBM average — minimal lateral coupling through interposer

**Suggested visuals:**
- Bar chart comparing GPU and HBM peak temps for all 3 configs
- Include one `*3D.png` figure showing the 2.5D layout (GPU + HBMs side by side)

---

## SLIDE 5 — Conclusions, Design Choices, and Future Work

**Title:**
> Conclusions, Algorithm Choices, and Next Steps

---

**Left column — Key design decisions (with rationale):**

**Decision 1: PySpice Box-Level Network**
- N ≈ 60 nodes vs. thousands for voxel mesh
- Produces human-readable SPICE netlist for TA verification
- < 0.01 s solve time; satisfies project requirement for PySpice use

**Decision 2: Half-Cell Interface Conductance**
- `G = 1/(h₁/2k₁A + h₂/2k₂A)` prevents double-counting box thermal resistance at shared interfaces
- Each box's thermal resistance is split equally between its two interfaces

**Decision 3: GPU Power = 270 W (not 400 W)**
- Piazza course-staff clarification: *"Please use the 270 W values as in therm.py"*
- XML configs carry `core_power=270`; `GPU_DEFAULT_POWER_W = 270.0` set explicitly in code

**Decision 4: Dynamic Z-Scaling in 3D Visualization**
- IC packages: 30–80 mm lateral, sub-mm vertical → flat without scaling
- Fix: `z_scale = (xy_span × 0.25) / z_span` makes stack visible in plots

**Decision 5: Timing Separation**
- Project FoM: placement + sizing time only (not SPICE solve)
- `runtime_excluding_simulation_s` is the reported metric

---

**Center column — Conclusions (summary bullets):**

- Successfully implemented PySpice thermal resistor network satisfying project requirements
- 2.5D integration offers **27°C thermal advantage** over 3D stacking at equivalent power
- GPU-on-top is the best 3D arrangement (2°C cooler than GPU-bottom)
- Solver is fast: box-level network solves in < 0.01 s; full pipeline runs in seconds
- All three outputs validated: `*_results.txt`, `*_results.yaml`, `thermal_netlist.sp`, `*.png`

---

**Right column — Future Work (bullet list):**

1. **Lateral (XY) conductance:** Add resistors between side-by-side chiplets on same substrate level for more accurate 2.5D lateral spreading
2. **Bonding layer accuracy:** Model micro-bump fill fraction and pitch instead of bulk material k
3. **Transient analysis:** Time-domain simulation to capture thermal throttling and power transients
4. **Adaptive meshing:** Voxel FD path with refinement near heat sources and TIM layers
5. **Multi-package extension:** Board-level thermal model including PCB spreading resistance

---

**Bottom banner (full width, accent color):**

> **Output Files Available:** `out_therm/thermal_netlist.sp` · `*_results.txt` · `*_results.yaml` · `*3D.png`
> **Run:** `bash scripts/run_all.sh` → results in `out_therm/`

---

## Design Notes for PowerPoint Formatting

**Recommended slide layout:** 16:9 widescreen

**Color scheme:**
- Background: dark navy (#1a1a2e) or white
- Primary accent: UCLA blue (#2774AE) or electric blue (#0097ff)
- GPU highlight: red (#e63946)
- HBM highlight: royal blue (#4361ee)
- Table headers: dark gray (#2d2d2d) on white, or inverted for dark theme

**Fonts:**
- Title: Bold sans-serif (Calibri Bold or Montserrat Bold), 28–32pt
- Body text: Regular sans-serif (Calibri or Roboto), 16–18pt
- Code/netlist: Monospace (Consolas or Courier New), 11–13pt

**Suggested images to include:**
- Slide 1: `out_therm/ECTC_3D_1GPU_8high_120125_higherHTC3D.png` — 3D oblique view of 3D config
- Slide 2: Hand-drawn or tool-generated circuit diagram (3 nodes, Rconv, Ipwr)
- Slide 4: `out_therm/ECTC_2p5D_1GPU_8high_110325_higherHTC3D.png` — 2.5D layout view
- Slide 4: Bar chart (can be generated from `summary.csv` data)
- Slide 5: The SPICE netlist excerpt (code block screenshot)

**Slide timing suggestion:** ~2–3 minutes per slide for a 12–15 minute presentation
