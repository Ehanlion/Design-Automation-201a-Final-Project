# PowerPoint Outline (5 Slides)
## EE 201A Final Project: Thermal Solver for 3D/2.5D GPU+HBM

**Authors:** Ethan Owen, Rachel Sarmiento

## Slide 1: Problem + Scope

- Goal: compare thermal behavior for 3 package styles:
  - `3D_1GPU_top`
  - `3D_1GPU`
  - `2p5D_1GPU`
- Inputs: XML hierarchy + materials + power + heatsink setup
- Output target: steady-state per-box temperatures and resistances
- Constraint from course: use PySpice/netlist flow

Visuals:
- One 3D package render
- One simple configuration diagram (3D vs 2.5D)

## Slide 2: What We Use (Stack + Scripts)

- `therm.py` (driver)
- `thermal_solver.py` (solver logic)
- `PySpice` (circuit/netlist API)
- Local `ngspice` (project-installed):
  - `third_party/ngspice/install/bin/ngspice`
- Setup:
  - `setup/setup.sh`
  - `setup/install_local_ngspice.sh`
- Run scripts:
  - `scripts/run_config*.sh`
  - `scripts/run_all.sh`
  - `scripts/summarize_all.sh`

Visual:
- Architecture block diagram (parsing -> placement -> solver -> outputs)

## Slide 3: Algorithm Choices + Solver Order

- Primary model: box-level thermal resistor network
  - 1 box = 1 node
  - interface conductance from half-cell resistance formula
  - power -> current source; ambient -> ground
- Solver hierarchy:
  1. local ngspice subprocess (primary)
  2. PySpice API ngspice-subprocess mode
  3. custom matrix solve from same network
  4. voxel FD only if PySpice import fails
- Why this design:
  - satisfies PySpice requirement
  - reproducible on lab machines
  - robust fallback behavior

Visual:
- Thermal-electrical analogy table + mini circuit snippet

## Slide 4: End-to-End Flow + Outputs

Pipeline:
1. parse XML + materials
2. place boxes + add TIM/bonding
3. build PySpice circuit
4. export `out_therm/thermal_netlist.sp`
5. solve (local ngspice first)
6. emit result files + plots

Outputs to show:
- `out_therm/<project>.png`
- `out_therm/<project>3D.png`
- `out_therm/<project>_results.txt`
- `out_therm/<project>_results.yaml`
- `out_therm/summary.csv`, `out_therm/summary.md`

Visual:
- one results table + one netlist excerpt

## Slide 5: Results Summary + Practical Usage

- Key comparison findings (GPU/HBM peak trends across 3 configs)
- Runtime note:
  - placement/sizing runtime reported separately from simulation runtime
- Practical usage:
  - `./setup/setup.sh`
  - `source .venv/bin/activate`
  - `./scripts/run_all.sh`
  - `./scripts/summarize_all.sh`
- Reproducibility:
  - local ngspice install in repo
  - same scripts generate all deliverables

Visual:
- bar chart + concise “how to run” command box

