#!/bin/bash
cd /app/nanocad/projects/deepflow_thermal/DeepFlow
echo "Starting Thermal Analysis GUI..."
echo "Python executable: /app/nanocad/projects/deepflow_thermal/DeepFlow/deepflow/bin/python"
echo "GUI file: thermal_analysis_gui.py"
echo "Working directory: $(pwd)"
echo "=================================="

/app/nanocad/projects/deepflow_thermal/DeepFlow/deepflow/bin/python thermal_analysis_gui.py
