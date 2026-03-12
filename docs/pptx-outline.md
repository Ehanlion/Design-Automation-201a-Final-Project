# PowerPoint Outline
## EE 201A Final Project: Thermal Resistance Network Solver for 3D/2.5D GPU+HBM

**Authors:** Ethan Owen, Rachel Sarmiento

## Slide 1: Problem + Final v4 Requirements

- Goal: build a thermal resistance network for GPU+HBM packages and solve it with `ngspice`
- Final Project v4 items implemented:
  - `Power_Source = 0 W`
  - GPU/HBM power injected on the **center z-plane**
  - temperatures reported in **Celsius**
  - ambient fixed at **45 C**
- Project focus: **correctness + runtime**

Visuals:
- one screenshot/snippet from the project PDF
- one small package diagram showing GPU + HBM context

## Slide 2: Overall Method

- Parse chiplet/package geometry from the provided XML flow
- Build a **non-uniform voxel mesh**
- Assign conductivity from stackup layers and materials
- Build a voxel RC network
- Export the RC network to a SPICE netlist
- Solve with local `ngspice`

Visuals:
- pipeline diagram:
  parse -> mesh -> materials -> power -> RC netlist -> ngspice -> temperatures

## Slide 3: Meshing Strategy (Required Item)

- We use a **non-uniform mesh**, not a uniform global grid
- Mesh aligns to:
  - chiplet boundaries
  - bonding regions
  - TIM regions
  - heatsink geometry
- Default grid controls:
  - `max_xy = 2.0 mm`
  - `max_z = 0.3 mm`
  - `min_s = 0.001 mm`

Visuals:
- 3D mesh image or package cross-section
- one bullet noting why non-uniform meshing improves accuracy/runtime tradeoff

## Slide 4: Voxel Resistance Calculation (Required Item)

- Each voxel is a thermal node
- Neighboring voxels connect through face conductances
- Face resistance formula:
  - `R_face = d1/(2*k1*A) + d2/(2*k2*A)`
  - `G_face = 1/R_face`
- Top and bottom surfaces connect to ambient with convection resistances

Visuals:
- one equation block
- one two-voxel face diagram labeling `k1`, `k2`, `A`, and half distances

## Slide 5: Power and Boundary Conditions

- GPU power: `270 W`
- HBM stack power: `5 W`
- `Power_Source = 0 W`
- GPU/HBM heat is deposited on the **center z-plane**
- Ambient: `45 C`
- Water-cooled top boundary uses effective `hc` derived from correlation and capped by XML `hc`

Visuals:
- center-plane power injection figure
- top/bottom boundary-condition sketch

## Slide 6: ngspice Solver Flow

- Final implementation uses `ngspice` as the **first-choice solver**
- Exported netlist: `out_therm/thermal_netlist.sp`
- Local binary used:
  - `third_party/ngspice/install/bin/ngspice`
- Runtime improvements added:
  - `.option klu`
  - voltage extraction via `wrdata`
- Matrix CG/SOR kept only as fallback

Visuals:
- screenshot of console output showing:
  - `Solver: voxel RC mesh`
  - `RC netlist exported`
  - `Parsed ... node voltages`

## Slide 7: ngspice Validation

- We checked `ngspice` against the internal matrix solve on the **same voxel network**
- Default 2.5D case agreement:
  - max peak delta: `3.70e-05 C`
  - max average delta: `3.64e-05 C`
- Conclusion:
  - exported netlist and internal matrix assembly are numerically consistent

Visuals:
- tiny comparison table: `ngspice` vs matrix
- optional one-line conclusion callout

## Slide 8: Current Results

- From current runs:
  - `ECTC_2p5D_1GPU_8high_110325_higherHTC`
    - hottest peak: `101.2606 C`
    - GPU peak: `101.2606 C`
    - HBM peak: `93.4960 C`
  - `ECTC_3D_1GPU_8high_110325_higherHTC`
    - hottest peak: `126.4009 C`
    - GPU peak: `126.4009 C`
    - HBM peak: `125.3038 C`
  - `ECTC_3D_1GPU_8high_120125_higherHTC`
    - hottest peak: `122.3400 C`
    - GPU peak: `122.0180 C`
    - HBM peak: `122.3400 C`

Visuals:
- summary table from `out_therm/results.txt`
- one thermal map image

## Slide 9: Correctness vs Golden

- Current golden-compared case:
  - `ECTC_3D_1GPU_8high_110325_higherHTC`
- Metrics:
  - matched boxes: `61/61`
  - peak MAE: `0.271364 C`
  - average MAE: `0.250548 C`
  - peak variance match: `67.32%`
  - average variance match: `97.90%`

Visuals:
- compact golden-comparison table
- optional bar chart for MAE / variance-match metrics

## Slide 10: Runtime and Closing

- Runtime summary lines now reported per run:
  - `total`: wall-clock (`sizing start -> simulation end`)
  - `ngspice`: ngspice subprocess only
  - `placement`: placement algorithm only
  - `config`: sizing + placement (grading FoM)
- Latest measured timings:
  - `ECTC_3D_1GPU_8high_120125_higherHTC` (`11718` nodes):
    - total `30.126 s`, ngspice `28.953 s`, placement `0.011 s`, config `0.023 s`
  - `ECTC_3D_1GPU_8high_110325_higherHTC` (`11718` nodes):
    - total `29.818 s`, ngspice `28.621 s`, placement `0.013 s`, config `0.025 s`
  - `ECTC_2p5D_1GPU_8high_110325_higherHTC` (`20880` nodes):
    - total `97.673 s`, ngspice `95.354 s`, placement `0.503 s`, config `1.014 s`
- Main closing points:
  - non-uniform voxel mesh
  - explicit voxel resistance derivation
  - center-plane v4 power model
  - local `ngspice` used correctly as primary solver
  - fallback solver retained only for robustness

Visuals:
- small runtime table
- final takeaway box
