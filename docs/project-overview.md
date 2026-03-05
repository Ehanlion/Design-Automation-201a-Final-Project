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
├── thermal_simulators/         # Anemoi cloud-API simulator (legacy)
│   ├── anemoi_sim.py
│   ├── base.py
│   ├── factory.py
│   └── neural_sim.py
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

## Changes Made to Starter Code

1. **Removed** unused `from thermal_simulators.factory import SimulatorFactory`
   import — the underlying `anemoi_sim.py` had a broken placeholder
   (`<paste API key here!>`) causing a `SyntaxError`.
2. **Fixed** the placeholder in `anemoi_sim.py` to be a valid empty string.
3. **Added** `simulator_simulate()` stub function that returns zero-valued
   results for every box, allowing the pipeline to run end-to-end without
   a solver implementation.
4. **Replaced** the bare `return #TODO: Comment out later` after
   `simulator_simulate()` with result-printing and YAML-writing logic.
   The original code exited the `therm()` function immediately after the
   simulation, so no output file was ever written. Now each run produces
   a `<project_name>_results.yaml` in `out_therm/`.
