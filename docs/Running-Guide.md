# EE 201A Final Project - Running Guide

## Overview

This project implements a thermal resistance network extraction tool for 2.5D/3D integrated circuits with GPU and HBM chiplets. The main script (`therm.py`) takes a system description XML config and produces a 3D stackup of boxes representing the chip package. Your task is to implement `simulator_simulate()` in `therm.py` to build a thermal resistance grid from these boxes and solve for temperature.

---

## Prerequisites

Run on SEASnet server `eeapps.seas.ucla.edu`.

**Quick setup** (recommended):
```bash
./setup/setup.sh          # creates .venv and installs all dependencies
source .venv/bin/activate  # activate for current shell
```

**Manual setup** (alternative):
```bash
pip3 install --user click seaborn scikit-learn sortedcontainers
```
The following are already available on SEASnet: `numpy`, `matplotlib`, `PyYAML`.

---

## Test Commands

All commands are run from the project root directory. The config paths below use local copies (the `/app/nanocad/...` paths in the project spec reference the same files).

### Configuration 1: 3D with GPU on Top (3D_1GPU_top)

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

### Configuration 2: 3D with GPU on Bottom (3D_1GPU)

```bash
python3 therm.py \
  --therm_conf configs/sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU.xml \
  --out_dir out_therm \
  --heatsink_conf configs/heatsink_definitions.xml \
  --bonding_conf configs/bonding_definitions.xml \
  --heatsink heatsink_water_cooled \
  --project_name ECTC_3D_1GPU_8high_110325_higherHTC \
  --is_repeat False \
  --hbm_stack_height 8 \
  --system_type 3D_1GPU \
  --dummy_si True \
  --tim_cond_list 5 \
  --infill_cond_list 1.6 \
  --underfill_cond_list 1.6
```

### Configuration 3: 2.5D (2p5D_1GPU)

```bash
python3 therm.py \
  --therm_conf configs/sip_hbm_dray062325_1gpu_6hbm_2p5D.xml \
  --out_dir out_therm \
  --heatsink_conf configs/heatsink_definitions.xml \
  --bonding_conf configs/bonding_definitions.xml \
  --heatsink heatsink_water_cooled \
  --project_name ECTC_2p5D_1GPU_8high_110325_higherHTC \
  --is_repeat False \
  --hbm_stack_height 8 \
  --system_type 2p5D_1GPU \
  --dummy_si False \
  --tim_cond_list 5 \
  --infill_cond_list 1.6 \
  --underfill_cond_list 1.6
```

---

## Command-Line Arguments

| Argument | Description |
|---|---|
| `--therm_conf` | System description XML file (defines chiplet hierarchy) |
| `--out_dir` | Output directory for generated plots and results |
| `--heatsink_conf` | Heatsink definitions XML file |
| `--bonding_conf` | Bonding definitions XML file |
| `--heatsink` | Heatsink name to use (e.g., `heatsink_water_cooled`) |
| `--project_name` | Project identifier for output naming |
| `--is_repeat` | Whether this is a repeated run with different power values |
| `--hbm_stack_height` | Number of DRAM dies per HBM stack (e.g., 8) |
| `--system_type` | Package type: `3D_1GPU_top`, `3D_1GPU`, or `2p5D_1GPU` |
| `--dummy_si` | Whether 3D package includes dummy silicon fill |
| `--tim_cond_list` | TIM thermal conductivity in W/(m*K) |
| `--infill_cond_list` | Infill thermal conductivity in W/(m*K) |
| `--underfill_cond_list` | Underfill thermal conductivity in W/(m*K) |

---

## How the Code Works (Execution Flow)

1. **Parse system config** (`therm_xml_parser.py`): Reads the XML chiplet hierarchy, assembly processes, layer definitions, and connection netlist. Builds a tree of `Chiplet` objects.

2. **Size fake chiplets** (`therm.py`): Recursively determines dimensions for "set" (fake) chiplets based on their children.

3. **Place chiplets** (`therm.py`): Uses a grid-based floorplanning approach to assign (x, y, z) coordinates to each chiplet. Resolves overlaps with iterative greedy movement.

4. **Create bonding layers** (`therm.py`): Adds bonding material boxes between parent-child chiplets (Cu pillars, BGA balls).

5. **Create TIM layers** (`therm.py`): Adds Thermal Interface Material boxes between chiplets and the heatsink.

6. **Create heatsink** (`therm.py`): Generates heatsink geometry from definitions.

7. **Call `simulator_simulate()`** (`therm.py`): **This is what you implement.** Takes all boxes, bonding, TIM, and heatsink data. Must return a dict mapping box names to temperature/resistance tuples.

---

## Your Task: Implement `simulator_simulate()`

The stub is at the top of `therm.py`. It receives:
- `boxes`: List of `Box` objects with coordinates, dimensions, power, and stackup
- `bonding_box_list`: Bonding layer boxes
- `TIM_boxes`: TIM layer boxes
- `heatsink_obj`: Heatsink geometry dict
- `layers`: Layer material/thickness definitions

Must return:

```python
results = {
    "BoxName": (peak_temperature, average_temperature, R_x, R_y, R_z),
    ...
}
```

**Approach**: Divide the 3D system into a uniform grid, calculate thermal resistance of each cell in X/Y/Z directions based on material conductivity, and solve the resulting resistance network (feed to PiSPICE or write your own solver). GPU power = 400W, each HBM = 5W.

---

## Key Power Assumptions

- **GPU power**: **270 W** — The lab PDF says 400 W, but the Piazza course forum clarified that the XML config value (270 W) is correct: *"Please use the 270 W values as in therm.py for now."* `GPU_DEFAULT_POWER_W = 270.0` in `therm.py` enforces this at runtime, overriding the chiplet tree before any simulation runs.
- **HBM power**: 5 W per stack
- **Power source efficiency**: 90% (backside power delivery loss accounted for)

## Thermal Solver

The simulation uses **PySpice** as the primary solver interface:

1. **PySpice box-level circuit** (primary): `PySpice.Spice.Netlist.Circuit` is used to build a thermal resistor network with one node per physical box. The netlist is exported to `out_therm/thermal_netlist.sp`. ngspice is tried first; if unavailable the conductance matrix is extracted from the same PySpice circuit and solved with scipy/numpy.
2. **3D voxel FD** (fallback): Used only if PySpice import fails entirely.

The simulation time is **excluded** from the project figure-of-merit runtime. Only chiplet sizing + placement time counts.
