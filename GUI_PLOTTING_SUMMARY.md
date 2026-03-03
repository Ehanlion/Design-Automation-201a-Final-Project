# GUI Plotting and Visualization Features

## Overview
The Thermal Analysis GUI has been enhanced with comprehensive plotting and tabulation capabilities to visualize runtime results from the `iterations()` function in `calibrated_iterations.py`.

## New Features Added

### 1. Real-time Data Visualization
- **Runtime Plot**: Interactive line plot showing runtime vs iteration number
- **Temperature Plot**: Temperature tracking across iterations
- **Results Table**: Comprehensive data table with all iteration metrics

### 2. Data Parsing and Processing
- **Runtime Data Extraction**: Parses output log to extract runtime information
- **Temperature Data Extraction**: Extracts temperature data from analysis output
- **Cost Data Extraction**: Captures cost information when available
- **Error Handling**: Robust parsing with fallback for missing data

### 3. Interactive GUI Layout
- **Two-Column Design**: 
  - Left: Configuration panel and status
  - Right: Visualization panels (runtime plot, temperature plot, results table)
- **Real-time Updates**: Plots and tables update automatically when analysis completes
- **Responsive Design**: Uses Bootstrap styling for professional appearance

## Technical Implementation

### New Functions Added
```python
def parse_runtime_from_output(output_text)
def create_runtime_plot()
def create_temperature_plot()
def create_results_table()
```

### New Callbacks
- `update_visualizations()`: Updates all plots and tables based on output log

### Updated Components
- Added Plotly graphs for runtime and temperature visualization
- Added Dash DataTable for detailed results
- Updated layout to include visualization panels
- Enhanced status monitoring and progress tracking

### Dependencies
- `plotly`: For interactive plotting
- `pandas`: For data manipulation and table creation
- `dash_table`: For professional data table display

## Data Flow

1. **Analysis Execution**: User runs thermal analysis through GUI
2. **Output Parsing**: System parses console output for runtime/temperature data
3. **Data Storage**: Extracted data stored in global `runtime_data` dictionary
4. **Visualization Update**: Plots and tables automatically refresh with new data
5. **Interactive Display**: Users can interact with plots (zoom, hover, etc.)

## Usage Instructions

1. **Configure Parameters**: Set system type, model, parallelism, HTC, and bandwidth
2. **Run Analysis**: Click "Run Analysis" button
3. **Monitor Progress**: Watch real-time progress in left panel
4. **View Results**: Runtime and temperature plots appear in right panel
5. **Examine Details**: Detailed results table shows all iteration data

## Sample Data Display

### Runtime Plot
- X-axis: Iteration number
- Y-axis: Runtime (seconds)
- Interactive features: hover data, zoom, pan

### Temperature Plot  
- X-axis: Iteration number
- Y-axis: Temperature (°C)
- Shows thermal behavior across iterations

### Results Table
- Columns: Iteration, Runtime (s), Temperature (°C), Cost ($)
- Sortable and searchable
- Professional styling with alternating row colors

## Error Handling

- **No Data Available**: Shows placeholder messages when no data is present
- **Parsing Errors**: Gracefully handles malformed output data
- **Missing Fields**: Fills missing data with None values
- **Plot Failures**: Displays informative error messages

## Integration with calibrated_iterations.py

The GUI automatically extracts runtime data from the output of the `iterations()` function by:
1. Parsing console output for patterns like "Iteration X: Runtime: Y.YY s"
2. Extracting temperature data from thermal simulation results
3. Capturing cost calculations when available
4. Displaying all data in real-time as analysis progresses

## Future Enhancements

Potential improvements for future development:
- Export functionality for plots and data
- Historical data comparison
- Advanced filtering and analysis tools
- Real-time streaming updates during long analyses
- Custom plot configurations and styling options
