# Important Gotchas

## `therm.py` programming

You are given a Python program therm.py which calls a function simulator_simulate() which you need to
define. The simulator_simulate() function takes the set of boxes as input. Each box is an instance of Box()
class, having start_x, start_y, start_z, end_x, end_y, end_z coordinates and stackup. The stackup consists
of a list of layers, each of which has a material compositions and thickness. The definition of all layers is
also passed as an argument to simulator_simulate() function. All heatsinks are defined in the
heatsink_definitions.xml and the heatsink we are using is specified using heatsink_water_cooled. You are
allowed to pass more inputs as arguments to the simulator_simulate() function if required.

## `simulator_simulate` signature

The simulator_simulate() function is expected to return a **dictionary** as below.

```py
results = simulator_simulate()
results = {
“Box1” : (peak_temperature_of_box1, average_temperature_of_box1,
thermal_resistance_of_box1_in_x, thermal_resistance_of_box1_in_y,
thermal_resistance_of_box1_in_z),
“Box2” : (peak_temperature_of_box1, average_temperature_of_box1,
thermal_resistance_of_box1_in_x, thermal_resistance_of_box1_in_y,
thermal_resistance_of_box1_in_z),
...
...
...
}
```

## Solver Hierarchy (updated March 2026)

`thermal_solver.solve_thermal()` attempts three solver tiers in order:

1. **Local ngspice subprocess** (`_solve_ngspice_subprocess`):
   - Calls the `ngspice` binary directly via `subprocess.run`.
   - Prefers the project-local binary at
     `third_party/ngspice/install/bin/ngspice` (set up by `setup/setup.sh`).
   - Uses the already-exported PySpice netlist (`out_therm/thermal_netlist.sp`),
     appends a `.control` block that runs `.op` and `print all`, then parses
     stdout for `v(ndN) = ...` lines.
   - Satisfies the "use ngspice locally" requirement from Piazza.

2. **PySpice API** (`_solve_pyspice_ngspice`):
   - Calls `circuit.simulator(temperature=25).operating_point()` via PySpice.
   - Also uses local ngspice under the hood but through PySpice's wrapper.
   - Activated only when the subprocess path fails (ngspice not in PATH, etc.).

3. **Custom RC linear-algebra solver** (`_solve_box_network_matrix`):
   - Assembles the conductance matrix directly from the same network topology
     (identical physics to the ngspice path).
   - Solves with `scipy.sparse.linalg.spsolve` (preferred) or `numpy.linalg.solve`.
   - Used when both ngspice approaches are unavailable.

If PySpice is not importable at all, the entire box-level network path is skipped
and a **3D voxel finite-difference solver** is used instead (scipy CG or numpy SOR).

## Image Generation Gotcha

`endswith()` checks on raw box names fail because of hierarchy prefixes and
`#n` / `_lN` suffixes (e.g. `substrate.HBM_l1#0`). The visualization functions
in `therm.py` use `'hbm' in name_l` (substring) rather than `name_l.endswith(...)`.

Per the Piazza answer: "Yes, you are allowed to modify these visualization functions.
We will check against the numerical output dumped by the code."

## Expected Output Files (per run)

Each call to `python3 therm.py --project_name NAME --out_dir out_therm` produces:

| File | Contents |
|------|----------|
| `out_therm/NAME.png` | 2D top-down placement plot (HBM=blue, GPU=red, interposer=black) |
| `out_therm/NAME3D.png` | 3D oblique view with z-scale exaggeration and color legend |
| `out_therm/NAME_results.yaml` | Per-box results dict (peak_T, avg_T, R_x, R_y, R_z) in YAML |
| `out_therm/NAME_results.txt` | Same data in human-readable Python dict format |
| `out_therm/thermal_netlist.sp` | Exported SPICE netlist (for inspection / grading) |

## Submission Script

`scripts/make_submission_tar.sh` packs **only** the files needed to run:
- `therm.py` and all Python dependencies
- `configs/` (all XML system configs, bonding, heatsink, layer definitions)
- `setup/` (requirements.txt + setup.sh)
- `scripts/` (run_all.sh, run_config*.sh, summarize_all.sh, make_submission_tar.sh)

The tar maintains the `GroupName/` directory structure; untarring creates a
self-contained directory from which `bash scripts/run_all.sh` works directly.
The `output/` directory (legacy YAML vars) is intentionally **not** included.
