# Instructions for Final Project

Hello, this project was created by Ethan Owen and Rachel Sarmiento for EE201A (Design Automation). The following is a guide on how to run our solution code using our provided scripting tools. Thank you.

The following is the project structure:
```txt
configs/
out_therm/ 
output/
scripts/
solutions/
third_party/
therm.py
thermal_solver.py
(other py files)
```

Please untar the given file before progressing further.

Please do not modify the script files or the tested execution flow may not occur. As the files stand, they have been tested and should work as is. 

Then, enter the scripts directory and execute the run script (if not executable, run chmod as well)
```bash
cd scripts/
chmod +x run_all.sh
./run_all.sh
```

The `run_all.sh` script will do the following:
- Check to see if a local `.venv` virtual environment exists 
- Check to see if a local install of `pyspice` or (`ngspice`) is present
- Install missing dependancies from above

If a dependancy is missing it will be installed in the project root. The virtual environment is called `.venv` and the `pyspice` install is built in the `third_party/` directory. 

**Important**: If the `run_all.sh` script find missing dependancies, this can take 5 ish minutes to install prior to the execution of the scripts. This is a one-time cost and is not paid a second time upon subsequent re-runs of the `run_all.sh` script unless the `.venv` or `third_party/` directories have been removed.

Once the `run_all.sh` script starts, it will execute each config in order:
- Config 1: ECTC_3D_1GPU_8high_110325
- Config 2: ECTC_3D_1GPU_8high_110325
- Config 3: ECTC_2p5D_1GPU_8high_110325

Then all results will be found in the `out_therm` directory as follows:
1. `.yaml` file for each config, by config name
2. `.txt` file, dumping the dict contents, by config name
3. `.png` file, for 3d image, by config name
4. `.png` file, for flat image, by config name
5. `results.txt` file containing thermal properties AND a comparison between config 1 and the golden results provided in piazza.
6. `thermal_netlist.sp`, thermal netlist file from running the run script, ignore this
6. In total there should be 14 files total after running