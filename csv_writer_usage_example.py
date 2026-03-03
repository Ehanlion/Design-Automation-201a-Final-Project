"""
Example code showing how to replace the file writing at line 1606 in therm.py
with CSV writing functionality.

This file shows the exact code to use as a replacement for the file writing logic.
"""

# ============================================================================
# CODE TO REPLACE LINES 1606-1608 IN therm.py
# ============================================================================

# Instead of:
# f.write(f"\nif((TIM_cond == {TIM_cond}) and (infill_cond == {infill_cond_mark}) and (underfill_cond == {underfill_cond_mark})):\n")
# interpolate_and_report(data, col2_values, f)
# f.close()

# Use this:

from calibration_csv_writer import write_calibration_to_csv, extract_calibration_from_interpolate

# Extract calibration values from the data
calibration_dict = extract_calibration_from_interpolate(data, col2_values)

# Strategy: Use the calibration values from the first HBM_power value
# (You can modify this to use last value, average, or another strategy)
if col2_values and len(col2_values) > 0:
    # Use first HBM_power value for calibration
    representative_hbm_power = col2_values[0]
    
    if representative_hbm_power in calibration_dict:
        gpu_slope, gpu_intercept = calibration_dict[representative_hbm_power]['GPU']
        hbm_slope, hbm_intercept = calibration_dict[representative_hbm_power]['HBM']
        
        # Get HTC value from heatsink configuration
        # Assuming hc is available from heatsinks[0].get_hc()
        # If not directly available, you may need to extract it differently
        try:
            hc_value = heatsinks[0].get_hc() if heatsinks and len(heatsinks) > 0 else 7.0
        except:
            hc_value = 7.0  # Default fallback
        
        # Get system_name from project_name or determine from config
        system_name = project_name  # or extract from therm_conf if needed
        
        # Determine dummy_Si based on your system configuration
        # This may need to be extracted from your chiplet tree or config
        dummy_Si = False  # Set based on your system configuration
        
        # Write to CSV
        write_calibration_to_csv(
            system_name=system_name,
            HBM_power=representative_hbm_power,
            HTC=hc_value,
            TIM_cond=TIM_cond,
            infill_cond=infill_cond,
            underfill_cond=underfill_cond,
            HBM_stack_height=hbm_stack_height,
            dummy_Si=dummy_Si,
            calibrate_GPU_slope=gpu_slope,
            calibrate_GPU_intercept=gpu_intercept,
            calibrate_HBM_slope=hbm_slope,
            calibrate_HBM_intercept=hbm_intercept
        )


# ============================================================================
# ALTERNATIVE: If you want to write one row per HBM_power value
# ============================================================================

# If you want to create one CSV row per HBM_power value instead:
"""
from calibration_csv_writer import write_calibration_to_csv, extract_calibration_from_interpolate

calibration_dict = extract_calibration_from_interpolate(data, col2_values)

# Get HTC and system_name (same as above)
try:
    hc_value = heatsinks[0].get_hc() if heatsinks and len(heatsinks) > 0 else 7.0
except:
    hc_value = 7.0

system_name = project_name
dummy_Si = False

# Write one row per HBM_power value
for hbm_power in col2_values:
    if hbm_power in calibration_dict:
        gpu_slope, gpu_intercept = calibration_dict[hbm_power]['GPU']
        hbm_slope, hbm_intercept = calibration_dict[hbm_power]['HBM']
        
        write_calibration_to_csv(
            system_name=system_name,
            HBM_power=hbm_power,
            HTC=hc_value,
            TIM_cond=TIM_cond,
            infill_cond=infill_cond,
            underfill_cond=underfill_cond,
            HBM_stack_height=hbm_stack_height,
            dummy_Si=dummy_Si,
            calibrate_GPU_slope=gpu_slope,
            calibrate_GPU_intercept=gpu_intercept,
            calibrate_HBM_slope=hbm_slope,
            calibrate_HBM_intercept=hbm_intercept
        )
"""

