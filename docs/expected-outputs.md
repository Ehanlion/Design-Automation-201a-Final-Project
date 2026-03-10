# Expected Outputs

This document describes the files and data produced when running each of the
three starter configurations from the Final Project PDF.

---

## How to Run

```bash
# Individual configurations
bash scripts/run_3D_1GPU_top.sh   # Config 1
bash scripts/run_3D_1GPU.sh       # Config 2
bash scripts/run_2p5D_1GPU.sh     # Config 3

# Or run all three at once
bash scripts/run_all.sh
```

All scripts use **local** config files under `configs/thermal-configs/` (no
dependency on `/app/nanocad/...`).

---

## Output Directory: `out_therm/`

Each run produces:

| File | Description |
|------|-------------|
| `post.png` | 2-D placement plot of chiplets on the substrate. |
| `post3D.png` | 3-D visualisation of the full box stackup. |
| `<project_name>_results.yaml` | Per-box results dictionary (YAML). |

### Results YAML Format

The YAML file contains a dictionary keyed by box name.  Each value is a tuple:

```
BoxName:
- peak_temperature   (°C)
- average_temperature (°C)
- thermal_resistance_x (K/W)
- thermal_resistance_y (K/W)
- thermal_resistance_z (K/W)
```

Until `simulator_simulate()` is implemented with a real solver, all values
will be `0.0` (the stub returns placeholder zeros).

---

## Configuration Details

### Config 1 — `3D_1GPU_top` (GPU on top of HBM stack)

- **Script:** `scripts/run_3D_1GPU_top.sh`
- **Thermal config:** `sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU_on_top.xml`
- **Project name:** `ECTC_3D_1GPU_8high_120125_higherHTC`
- **System type:** `3D_1GPU_top`
- **HBM stack height:** 8
- **Dummy Si:** True
- **TIM conductivity:** 5 W/(m·K)
- **Infill conductivity:** 1.6 W/(m·K)
- **Underfill conductivity:** 1.6 W/(m·K)
- **Expected box count:** 61 boxes, 8 bonding boxes, 1 TIM box
- **Key boxes:** Power_Source, substrate, 6x HBM stacks (each 8 layers deep),
  4x Dummy_Si_above, 1x GPU (placed on top of HBM#0's stack)

### Config 2 — `3D_1GPU` (GPU below HBMs)

- **Script:** `scripts/run_3D_1GPU.sh`
- **Thermal config:** `sip_hbm_dray_062325_1GPU_6HBM_3D_single_GPU.xml`
- **Project name:** `ECTC_3D_1GPU_8high_110325_higherHTC`
- **System type:** `3D_1GPU`
- **HBM stack height:** 8
- **Dummy Si:** True
- **TIM conductivity:** 5 W/(m·K)
- **Infill conductivity:** 1.6 W/(m·K)
- **Underfill conductivity:** 1.6 W/(m·K)
- **Expected box count:** 61 boxes, 8 bonding boxes, 1 TIM box
- **Key boxes:** Power_Source, substrate, GPU, 6x HBM stacks (each 8 layers),
  4x Dummy_Si_above

### Config 3 — `2p5D_1GPU` (2.5-D interposer)

- **Script:** `scripts/run_2p5D_1GPU.sh`
- **Thermal config:** `sip_hbm_dray062325_1gpu_6hbm_2p5D.xml`
- **Project name:** `ECTC_2p5D_1GPU_8high_110325_higherHTC`
- **System type:** `2p5D_1GPU`
- **HBM stack height:** 8
- **Dummy Si:** False
- **TIM conductivity:** 5 W/(m·K)
- **Infill conductivity:** 1.6 W/(m·K)
- **Underfill conductivity:** 1.6 W/(m·K)
- **Expected box count:** 57 boxes, 8 bonding boxes, 1 TIM box
- **Key boxes:** Power_Source, substrate, set_primary (interposer group), GPU,
  6x HBM stacks (each 8 layers). No Dummy_Si boxes (dummy_si=False).

---

## What Students Must Implement

The function `simulator_simulate()` at the top of `therm.py` is currently a
stub that returns zeros.  Students need to replace it with code that:

1. **Divides** the 3-D box stackup into a grid of small uniform (or
   non-uniform) cells.
2. **Computes** the thermal resistance (R_x, R_y, R_z) of each cell using
   material conductivities from `layers` and cell geometry.
3. **Feeds** the resistance network into PiSPICE or a custom RC solver.
4. **Extracts** peak and average temperatures per box from the solver output.
5. **Returns** the results dictionary in the format shown above.

Power assumptions (from the project PDF):
- GPU power: **400 W**
- Each HBM: **5 W**

---

## Gotchas and Notes

- The `thermal_simulators/` directory (legacy Anemoi cloud-API code) has been
  removed. Reference data was extracted to `docs/anemoi-reference.md`.
- The `is_repeat` flag should be `False` for initial runs.  When set to `True`
  the code skips `simulator_simulate()` and enters the iterative calibration
  loop instead.
- Plot files (`post.png`, `post3D.png`) are overwritten by each run — only the
  last configuration's plots persist.
- The `configs/thermal-configs/layer_definitions.xml` file must exist locally;
  it is hardcoded at line ~1497 of `therm.py`.
- The original code had a bare `return` immediately after calling
  `simulator_simulate()` (tagged `#TODO: Comment out later`), which caused the
  function to exit before writing any results file. This was replaced with
  result-printing and YAML-writing logic followed by the `return`.
