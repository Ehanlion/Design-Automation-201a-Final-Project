# EE 201A Final Project - Thermal Resistance Networks for 2.5D/3D ICs

UCLA EE 201A -- VLSI Design Automation -- Winter 2026

## Project Summary

This project extracts thermal resistance networks from 2.5D and 3D integrated circuit package descriptions (GPU + 6 HBM chiplets). The starter code parses system XML configs, builds a chiplet hierarchy, performs floorplanning, and generates a 3D box stackup. The core task is implementing `simulator_simulate()` in `therm.py` to:

1. Divide the 3D system into a grid of thermal resistance cells
2. Calculate thermal resistance along X, Y, and Z for each cell
3. Solve the resistance network (using PiSPICE or a custom solver) to extract the temperature map
4. Return peak/average temperatures and thermal resistances per box

## Quick Start

```bash
# Set up virtual environment and install dependencies
./setup/setup.sh

# Activate the environment
source .venv/bin/activate

# Run all three test configurations
./scripts/run_all.sh

# Or run individually
./scripts/run_config1_3D_gpu_top.sh
./scripts/run_config2_3D_gpu_bottom.sh
./scripts/run_config3_2p5D.sh
```

`setup/setup.sh` also installs a **project-local ngspice** build at:
`third_party/ngspice/install/bin/ngspice`

If you need to override the binary path explicitly, set:
```bash
export EE201A_NGSPICE_BIN=/absolute/path/to/ngspice
```

See `docs/RUNNING_GUIDE.md` for detailed test commands, argument descriptions, and file documentation.

## Repository Structure

```
therm.py                    # Main script + simulator_simulate() stub (OUR CODE HERE)
therm_xml_parser.py         # XML parser: Chiplet, Layer, Assembly classes
rearrange.py                # Box class, overlap checking, placement utilities
bonding_xml_parser.py       # Bonding definitions parser
heatsink_xml_parser.py      # Heatsink definitions parser
configs/                    # XML system descriptions and material definitions
output/                     # Variable definitions (power, area, HBM count)
thermal_simulators/         # Simulator framework (Anemoi reference, not used locally)
lab_files/                  # Project spec PDF and reference papers
setup/
├── setup.sh                # Creates .venv and installs all dependencies
└── requirements.txt        # Python package requirements
scripts/
├── run_config1_3D_gpu_top.sh
├── run_config2_3D_gpu_bottom.sh
├── run_config3_2p5D.sh
└── run_all.sh
docs/
└── RUNNING_GUIDE.md        # Detailed running instructions and file descriptions
out_therm/                  # Output directory for plots (generated at runtime)
```

## Three Test Configurations

| Config | System Type | XML Config File | Dummy Si |
|--------|-------------|-----------------|----------|
| 1 | 3D, GPU on top | `sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU_on_top.xml` | Yes |
| 2 | 3D, GPU on bottom | `sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU.xml` | Yes |
| 3 | 2.5D | `sip_hbm_dray062325_1gpu_6hbm_2p5D.xml` | No |

## Key Parameters

- GPU power: **270 W** (per Piazza course-staff clarification — NOT the 400 W from the lab PDF; see `lab_files/lab-gotchas.md`)
- HBM power: 5 W per stack
- Heatsink: Water-cooled
- HBM stack height: 8 dies

## Thermal Solver

The solver uses **PySpice** as the primary interface for building and solving the resistor network, per the project requirement:

> "use Pyspice either as an API call or by dumping out netlist. I don't want how you solve a linear system of equations to be reason why your code is faster or slower!" — course staff (Piazza)

Solver hierarchy (in priority order):
1. **PySpice box-level resistor network** (primary): Builds a SPICE thermal circuit via `PySpice.Spice.Netlist.Circuit` (one thermal node per box), exports netlist to `out_therm/thermal_netlist.sp`, and runs ngspice using the project-local binary (`third_party/ngspice/install/bin/ngspice`) when available. Falls back to direct matrix solve from the same PySpice network topology only if ngspice is unavailable.
2. **3D voxel finite-difference** (fallback if PySpice import fails): scipy sparse CG or numpy SOR.

The simulation is excluded from the figure-of-merit runtime. Only sizing + placement time is measured.
