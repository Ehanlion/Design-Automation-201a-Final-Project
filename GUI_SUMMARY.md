# Thermal Analysis GUI - Complete Package

## Files Created

1. **thermal_analysis_gui.py** - Main GUI application
2. **requirements_gui.txt** - Python package dependencies
3. **launch_gui.sh** - Launch script for easy startup
4. **README_GUI.md** - Comprehensive documentation
5. **test_gui.py** - Test script to verify setup

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements_gui.txt
   ```

2. **Launch the GUI:**
   ```bash
   ./launch_gui.sh
   ```
   Or:
   ```bash
   python thermal_analysis_gui.py
   ```

3. **Access the GUI:**
   Open your web browser and go to: http://localhost:8050

## GUI Features

### Configuration Options
- **System Type**: 2.5D Waferscale, 3D Waferscale
- **ML Model**: Llama 3.3 70B, Llama 3.1 405B
- **Parallelism**: 3 strategies per system type
- **HTC**: 10 kW/(m²·K), 20 kW/(m²·K) (3D only)
- **Network Bandwidth**: 9 options from 450 GB/s to 115200 GB/s

### Outputs
- **System Cost**: Calculated via load_and_test_design.py
- **Thermal Analysis**: Runtime, temperatures, GPU utilization
- **Status Updates**: Real-time progress and logs

## How It Works

The GUI automatically modifies configuration files based on user selections:

1. **buildRun.sh**: Switches between Llama model parameters
2. **run.sh**: Sets parallelism strategy (kp1, kp2 values)
3. **YAML configs**: Updates network bandwidth frequency
4. **calibrated_iterations.py**: Adjusts for HTC settings

Then executes:
1. System cost calculation
2. Thermal analysis via calibrated_iterations.py

## File Modifications

### buildRun.sh
- **Llama 3.3 70B**: Uncomments lines 5-13, comments lines 27-35
- **Llama 3.1 405B**: Comments lines 5-13, uncomments lines 27-35

### run.sh
- **3D Waferscale**: Uses line 23, modifies kp1/kp2 values
- **2.5D Waferscale**: Uses line 24, modifies kp1/kp2 values

### YAML Files
- Updates `nominal_frequency` in `network.intra_node` section
- Maps bandwidth to frequency values

### calibrated_iterations.py
- **20 kW/(m²·K)**: Uses predict_temperature function
- **10 kW/(m²·K)**: Uses calibration functions (default)

## System Cost Commands

The GUI executes these commands for cost calculation:

**2.5D Waferscale:**
```bash
python load_and_test_design.py configs/thermal-configs/io_definitions.xml configs/thermal-configs/layer_definitions.xml configs/thermal-configs/wafer_process_definitions.xml configs/thermal-configs/assembly_process_definitions.xml configs/thermal-configs/test_definitions.xml configs/thermal-configs/netlist.xml configs/thermal-configs/sip_hbm_dray050925_1gpu_6hbm_5x5.xml output/output_vars2.yaml
```

**3D Waferscale:**
```bash
python load_and_test_design.py configs/thermal-configs/io_definitions.xml configs/thermal-configs/layer_definitions.xml configs/thermal-configs/wafer_process_definitions.xml configs/thermal-configs/assembly_process_definitions.xml configs/thermal-configs/test_definitions.xml configs/thermal-configs/netlist.xml configs/thermal-configs/sip_hbm_dray061925_1GPU_6HBM_7x7_3D.xml output/output_vars2.yaml
```

## Testing

Run the test script to verify everything is set up correctly:
```bash
python test_gui.py
```

## Dependencies

- dash>=2.14.0
- dash-bootstrap-components>=1.5.0
- plotly>=5.15.0

## Usage Notes

- GUI runs on port 8050 by default
- Analysis can take several minutes
- All file modifications are automatic
- Results include both cost and thermal analysis
- Stop button available for long-running analyses

## Architecture

The GUI is built using Dash (Flask-based) with Bootstrap styling. It provides:
- Reactive dropdowns that update based on selections
- Real-time status updates
- Progress tracking
- Comprehensive error handling
- Automatic file configuration management

This creates a complete thermal analysis workflow with an intuitive web interface.
