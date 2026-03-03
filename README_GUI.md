# Thermal Analysis GUI

This GUI application provides an interactive interface to run thermal analysis for different system configurations and machine learning models, with real-time visualization of runtime and temperature data.

## Features

### Configuration Options
- **System Type**: 2.5D Waferscale or 3D Waferscale architectures
- **ML Models**: Llama 3.3 70B or Llama 3.1 405B
- **Parallelism Strategies**: Different approaches based on system type
- **HTC Values**: Heat Transfer Coefficient (10 or 20 kW/(m²·K))
- **Network Bandwidth**: 9 options from 450 GB/s to 115,200 GB/s

### Real-time Visualization
- **Runtime Plots**: Interactive charts showing runtime vs iteration
- **Temperature Plots**: Temperature tracking across iterations  
- **Results Tables**: Detailed data tables with iteration metrics
- **Cost Estimation**: Automatic system cost calculation

### Analysis Features
- Live progress monitoring and output logging
- Background process management
- Two-column layout: configuration on left, results on right

## Installation

1. Install the required Python packages:
```bash
pip install -r requirements_gui.txt
```

## Usage

### Option 1: Use the launch script
```bash
./launch_gui.sh
```

### Option 2: Run directly
```bash
python thermal_analysis_gui.py
```

The GUI will be available at: http://localhost:8050

## Features

### System Configuration Options

1. **System Type**:
   - 2.5D Waferscale (`2p5D_waferscale`)
   - 3D Waferscale (`3D_waferscale`)

2. **ML Model**:
   - Llama 3.3 70B
   - Llama 3.1 405B

3. **Parallelism Strategy**:
   - For 3D Waferscale:
     - Strategy 1: kp1=1, kp2=49
     - Strategy 2: kp1=49, kp2=1
     - Strategy 3: kp1=7, kp2=7
   - For 2.5D Waferscale:
     - Strategy 1: kp1=1, kp2=25
     - Strategy 2: kp1=25, kp2=1
     - Strategy 3: kp1=5, kp2=5

4. **HTC (Heat Transfer Coefficient)**:
   - 10 kW/(m²·K) (available for both systems)
   - 20 kW/(m²·K) (only available for 3D Waferscale)

5. **Network Bandwidth**:
   - 450 GB/s
   - 900 GB/s
   - 1800 GB/s
   - 3600 GB/s
   - 7200 GB/s
   - 14400 GB/s
   - 28800 GB/s
   - 57600 GB/s
   - 115200 GB/s

## How it Works

1. **Select Configuration**: Choose your desired system type, ML model, parallelism strategy, HTC value, and network bandwidth.

2. **Run Analysis**: Click the "Run Analysis" button to start the thermal analysis.

3. **View Results**: The GUI will display:
   - System cost calculation
   - Analysis status
   - Progress bar
   - Detailed output log with results

4. **Stop Analysis**: Use the "Stop Analysis" button to halt a running analysis if needed.

## Behind the Scenes

The GUI automatically modifies the following files based on your configuration:

1. **buildRun.sh**: Selects the appropriate ML model parameters
2. **run.sh**: Sets the correct parallelism strategy (kp1, kp2 values)
3. **YAML config files**: Updates network bandwidth settings
4. **calibrated_iterations.py**: Adjusts HTC settings for thermal analysis

## Output

The analysis provides:
- **System Cost**: Calculated using the load_and_test_design.py script
- **Thermal Analysis Results**: Runtime, GPU peak temperatures, HBM peak temperatures, and GPU idle time fractions
- **Detailed Log**: Complete output from the analysis process

## File Dependencies

The GUI requires the following files to be present in the correct locations:
- `calibrated_iterations.py`
- `DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh`
- `DeepFlow_llm_dev/DeepFlow/scripts/run.sh`
- `DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100.yaml`
- `DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100_2p5D.yaml`
- `load_and_test_design.py`
- Various config files in `configs/thermal-configs/`

## Troubleshooting

- Ensure all dependencies are installed: `pip install -r requirements_gui.txt`
- Check that all required files are in their expected locations
- Make sure you're running from the correct directory: `/app/nanocad/projects/deepflow_thermal/DeepFlow/`
- If the GUI doesn't load, check that port 8050 is available

## Notes

- The 20 kW/(m²·K) HTC option is only available for 3D Waferscale systems
- Analysis can take several minutes to complete depending on the configuration
- The GUI will automatically switch between different YAML config files based on the system type selected
