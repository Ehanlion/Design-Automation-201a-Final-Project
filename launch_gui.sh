#!/bin/bash

# Thermal Analysis GUI Setup and Launch Script
echo "Setting up Thermal Analysis GUI..."

# Install required Python packages
echo "Installing required Python packages..."
pip install -r requirements_gui.txt

# Launch the GUI application
echo "Launching Thermal Analysis GUI..."
echo "The GUI will be available at: http://localhost:8050"
echo "Press Ctrl+C to stop the application"

python thermal_analysis_gui.py
