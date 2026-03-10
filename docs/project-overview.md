# Project Overview

## Goal

Build a thermal resistance network solver for 2.5-D and 3-D GPU + HBM
chiplet systems.  The starter code (`therm.py`) already handles:

- Parsing XML system-description configs (chiplet tree, layers, bonding,
  heatsinks).
- Sizing and placement of chiplets into a 3-D stackup of `Box` objects.
- Generating visualisation plots.

What remains is implementing `simulator_simulate()` — the function that turns
the box stackup into a resistive grid and solves for temperatures.

## Repository Layout

```
.
├── therm.py                    # Main entry point (click CLI)
├── therm_xml_parser.py         # XML config parser for chiplet trees
├── bonding_xml_parser.py       # Bonding definitions parser
├── heatsink_xml_parser.py      # Heatsink definitions parser
├── rearrange.py                # Placement / rearrangement logic
├── docs/anemoi-reference.md    # Reference data extracted from legacy Anemoi simulator
├── configs/thermal-configs/    # Local XML config files
│   ├── sip_hbm_dray_*.xml      # System descriptions (3D, 2.5D variants)
│   ├── heatsink_definitions.xml
│   ├── bonding_definitions.xml
│   └── layer_definitions.xml
├── scripts/                    # Shell scripts to run each configuration
│   ├── run_3D_1GPU_top.sh
│   ├── run_3D_1GPU.sh
│   ├── run_2p5D_1GPU.sh
│   └── run_all.sh
├── docs/                       # Documentation
│   ├── project-overview.md     # This file
│   └── expected-outputs.md     # Detailed output descriptions
├── out_therm/                  # Output directory (plots + results YAML)
├── output/                     # Legacy output YAML files
└── lab-files/                  # Project PDF and reference papers
```

## CLI Arguments

`therm.py` uses the `click` library.  Key options:

| Flag | Purpose |
|------|---------|
| `--therm_conf` | Path to the system description XML |
| `--out_dir` | Output directory for plots and results |
| `--heatsink_conf` | Path to heatsink definitions XML |
| `--bonding_conf` | Path to bonding definitions XML |
| `--heatsink` | Heatsink name (e.g. `heatsink_water_cooled`) |
| `--project_name` | Name used for output file prefixes |
| `--is_repeat` | `False` for first run, `True` for calibration iterations |
| `--hbm_stack_height` | Number of dies per HBM stack (8 or 16) |
| `--system_type` | `3D_1GPU_top`, `3D_1GPU`, or `2p5D_1GPU` |
| `--dummy_si` | Whether 3-D configs include dummy silicon spacers |
| `--tim_cond_list` | TIM conductivity values (W/m·K) |
| `--infill_cond_list` | Infill conductivity values (W/m·K) |
| `--underfill_cond_list` | Underfill conductivity values (W/m·K) |

## Power Assumption: 270 W GPU

The lab PDF specifies 400 W for the GPU. The Piazza course forum clarified that the XML config value (270 W) is the correct value to use:
> "Please use the 270 W values as in therm.py for now."

`GPU_DEFAULT_POWER_W = 270.0` is set at the top of `therm.py` and applied to the chiplet tree before any simulation. The fallback constant `GPU_TOTAL_POWER_W = 270.0` in `thermal_solver.py` is kept consistent.

## Thermal Solver: PySpice Integration

The thermal solve uses **PySpice** as the primary interface, per the course requirement:
> "use Pyspice either as an API call or by dumping out netlist. I don't want how you solve a linear system of equations to be reason why your code is faster or slower!"

**Solver hierarchy** in `thermal_solver.solve_thermal()`:

1. **PySpice box-level resistor network** (primary, `HAS_PYSPICE=True`):
   - Builds a SPICE thermal circuit via `PySpice.Spice.Netlist.Circuit`
   - One thermal node per physical box
   - Interface resistors between z-adjacent boxes (half-cell R formula)
   - Convective boundary resistors at top and bottom surfaces
   - Current sources for power injection
   - Exports netlist to `out_therm/thermal_netlist.sp` (the "dump netlist" path)
   - Attempts ngspice operating-point simulation (API call path)
   - On ngspice failure: extracts conductance matrix from PySpice elements, solves with scipy sparse CG
   - `thermal_solver.py` is preserved and NOT removed

2. **3D voxel finite-difference** (fallback, if PySpice unavailable):
   - Non-uniform grid aligned to box boundaries
   - scipy sparse CG or numpy SOR

**Simulation timing** is excluded from the FoM runtime (sizing + placement only).

## Changes Made to Starter Code

1. **Removed** the entire `thermal_simulators/` directory (legacy Anemoi
   cloud-API code). Useful reference data (conductivity values, voxelization
   logic, solver parameters) was extracted to `docs/anemoi-reference.md`.
2. **Added** `simulator_simulate()` stub function that returns zero-valued
   results for every box, allowing the pipeline to run end-to-end without
   a solver implementation.
3. **Replaced** the bare `return #TODO: Comment out later` after
   `simulator_simulate()` with result-printing and YAML-writing logic.
   The original code exited the `therm()` function immediately after the
   simulation, so no output file was ever written. Now each run produces
   a `<project_name>_results.yaml` in `out_therm/`.
