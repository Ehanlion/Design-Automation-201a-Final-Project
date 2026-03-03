"""
Example usage of the calibration CSV reader.
This shows how to load calibration data once and use it multiple times.
"""

from calibration_csv_reader import CalibrationData


# ============================================================================
# Basic usage: Load once, use multiple times
# ============================================================================

# Step 1: Create and load the calibration data (do this once at the start)
calibration_data = CalibrationData()
calibration_data.load_from_csv("calibration_data.csv")

print(f"Loaded {len(calibration_data)} calibration configurations")


# ============================================================================
# Example: Use calibration data in a loop/iteration
# ============================================================================

def run_thermal_analysis_with_calibration(
    system_name,
    HBM_power,
    HTC,
    TIM_cond,
    infill_cond,
    underfill_cond,
    HBM_stack_height,
    dummy_Si,
    calibration_data: CalibrationData
):
    """
    Run thermal analysis using calibration data if available.
    
    Args:
        All the system configuration parameters
        calibration_data: Pre-loaded CalibrationData instance
    """
    # Check if we have calibration data for this configuration
    calib = calibration_data.get_calibration(
        system_name=system_name,
        HBM_power=HBM_power,
        HTC=HTC,
        TIM_cond=TIM_cond,
        infill_cond=infill_cond,
        underfill_cond=underfill_cond,
        HBM_stack_height=HBM_stack_height,
        dummy_Si=dummy_Si
    )
    
    if calib:
        print(f"Using calibration data for {system_name}:")
        print(f"  GPU: slope={calib['calibrate_GPU_slope']}, intercept={calib['calibrate_GPU_intercept']}")
        print(f"  HBM: slope={calib['calibrate_HBM_slope']}, intercept={calib['calibrate_HBM_intercept']}")
        
        # Use the calibration values in your thermal analysis
        # For example, apply calibration to temperature predictions:
        # calibrated_temp = original_temp * slope + intercept
        
        return calib
    else:
        print(f"No calibration data found for configuration: {system_name}")
        return None


# Example: Iterate over multiple configurations
configurations = [
    {
        "system_name": "2p5D_1GPU",
        "HBM_power": 5.0,
        "HTC": 7.0,
        "TIM_cond": 50.0,
        "infill_cond": 19.0,
        "underfill_cond": 19.0,
        "HBM_stack_height": 8,
        "dummy_Si": False
    },
    {
        "system_name": "2p5D_1GPU",
        "HBM_power": 5.6,
        "HTC": 7.0,
        "TIM_cond": 50.0,
        "infill_cond": 19.0,
        "underfill_cond": 19.0,
        "HBM_stack_height": 8,
        "dummy_Si": False
    }
]

print("\n" + "="*60)
print("Example: Iterating over configurations")
print("="*60)

for config in configurations:
    calib = run_thermal_analysis_with_calibration(
        calibration_data=calibration_data,
        **config
    )
    if calib:
        # Use calibration values in your calculations
        pass


# ============================================================================
# Example: Check if configuration exists before running simulation
# ============================================================================

def should_run_simulation(
    system_name,
    HBM_power,
    HTC,
    TIM_cond,
    infill_cond,
    underfill_cond,
    HBM_stack_height,
    dummy_Si,
    calibration_data: CalibrationData
):
    """
    Check if we already have calibration data for this configuration.
    If yes, we might skip the simulation or use cached results.
    """
    exists = calibration_data.has_configuration(
        system_name=system_name,
        HBM_power=HBM_power,
        HTC=HTC,
        TIM_cond=TIM_cond,
        infill_cond=infill_cond,
        underfill_cond=underfill_cond,
        HBM_stack_height=HBM_stack_height,
        dummy_Si=dummy_Si
    )
    
    return exists


# ============================================================================
# Example: Get all available configurations
# ============================================================================

print("\n" + "="*60)
print("All available configurations:")
print("="*60)

all_configs = calibration_data.get_all_configurations()
for key, values in all_configs.items():
    system_name, hbm_power, htc, tim_cond, infill_cond, underfill_cond, hbm_stack, dummy_si = key
    print(f"\nSystem: {system_name}")
    print(f"  HBM_power: {hbm_power}W, HTC: {htc}W/(m²K)")
    print(f"  TIM: {tim_cond}, Infill: {infill_cond}, Underfill: {underfill_cond}")
    print(f"  Stack height: {hbm_stack}, Dummy_Si: {dummy_si}")
    print(f"  GPU calibration: slope={values['calibrate_GPU_slope']}, intercept={values['calibrate_GPU_intercept']}")
    print(f"  HBM calibration: slope={values['calibrate_HBM_slope']}, intercept={values['calibrate_HBM_intercept']}")


# ============================================================================
# Example: Filter configurations by certain criteria
# ============================================================================

def filter_configurations_by_tim_cond(calibration_data: CalibrationData, tim_cond: float):
    """Get all configurations with a specific TIM conductivity."""
    matching = {}
    for key, values in calibration_data.get_all_configurations().items():
        system_name, hbm_power, htc, tim, infill, underfill, hbm_stack, dummy_si = key
        if tim == tim_cond:
            matching[key] = values
    return matching


print("\n" + "="*60)
print("Configurations with TIM_cond = 50.0:")
print("="*60)

matching_configs = filter_configurations_by_tim_cond(calibration_data, 50.0)
for key, values in matching_configs.items():
    print(f"Key: {key}")


# ============================================================================
# Example: Integration in a class or module
# ============================================================================

class ThermalAnalyzer:
    """
    Example class that uses calibration data.
    """
    
    def __init__(self, calibration_csv_path: str = "calibration_data.csv"):
        """Initialize with calibration data."""
        self.calibration_data = CalibrationData()
        self.calibration_data.load_from_csv(calibration_csv_path)
        print(f"ThermalAnalyzer initialized with {len(self.calibration_data)} configurations")
    
    def analyze_with_calibration(self, system_config):
        """Perform thermal analysis using calibration if available."""
        calib = self.calibration_data.get_calibration(**system_config)
        if calib:
            # Use calibration in analysis
            return {
                "calibration_applied": True,
                "gpu_slope": calib['calibrate_GPU_slope'],
                "gpu_intercept": calib['calibrate_GPU_intercept'],
                "hbm_slope": calib['calibrate_HBM_slope'],
                "hbm_intercept": calib['calibrate_HBM_intercept']
            }
        else:
            return {"calibration_applied": False}


# Example usage of the class
analyzer = ThermalAnalyzer("calibration_data.csv")

config = {
    "system_name": "2p5D_1GPU",
    "HBM_power": 5.0,
    "HTC": 7.0,
    "TIM_cond": 50.0,
    "infill_cond": 19.0,
    "underfill_cond": 19.0,
    "HBM_stack_height": 8,
    "dummy_Si": False
}

result = analyzer.analyze_with_calibration(config)
print("\n" + "="*60)
print("Class-based usage result:")
print("="*60)
print(result)

