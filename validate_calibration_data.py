"""
Validation script for thermal calibration data migration.
This script verifies the integrity and correctness of the migrated calibration data.
"""

import json
import sys
from typing import Dict, List, Tuple
from dray_ECTC4 import ThermalCalibrationStore, CalibrationKey, CalibrationData

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass

def validate_value_ranges(key: str, data: dict) -> List[str]:
    """Validate that values are within expected ranges"""
    errors = []
    
    # Parse key components
    components = key.split('_')
    if len(components) != 7:
        errors.append(f"Invalid key format: {key}")
        return errors
    
    # Known valid ranges
    valid_systems = {"2p5D_1GPU", "3D_1GPU", "2p5D_waferscale", "3D_waferscale"}
    valid_stack_heights = {8, 12, 16}
    valid_htc = {7, 10, 20, 50, 100}
    valid_tim_cond = {1, 5, 10, 50, 100}
    valid_fill_cond = {1, 19, 237}
    valid_power_values = {5.0, 5.6, 6.8024, 9.0, 9.4, 10.1218}

    # System name validation
    system_name = components[0]
    if system_name not in valid_systems:
        errors.append(f"Invalid system name: {system_name}")
    
    # Stack height validation
    try:
        stack_height = int(components[1])
        if stack_height not in valid_stack_heights:
            errors.append(f"Invalid stack height: {stack_height}")
    except ValueError:
        errors.append(f"Invalid stack height format: {components[1]}")

    # HTC validation
    try:
        htc = int(components[2])
        if htc not in valid_htc:
            errors.append(f"Invalid HTC value: {htc}")
    except ValueError:
        errors.append(f"Invalid HTC format: {components[2]}")

    # TIM conductivity validation
    try:
        tim_cond = int(components[3])
        if tim_cond not in valid_tim_cond:
            errors.append(f"Invalid TIM conductivity: {tim_cond}")
    except ValueError:
        errors.append(f"Invalid TIM conductivity format: {components[3]}")

    # Fill conductivity validation
    try:
        fill_cond = int(components[4])
        if fill_cond not in valid_fill_cond:
            errors.append(f"Invalid fill conductivity: {fill_cond}")
    except ValueError:
        errors.append(f"Invalid fill conductivity format: {components[4]}")

    # Value range validation
    for cal_type in ['gpu_calibration', 'hbm_calibration']:
        if cal_type not in data:
            errors.append(f"Missing {cal_type} in data")
            continue
            
        for power_str, (slope, intercept) in data[cal_type].items():
            try:
                power = float(power_str)
                if power not in valid_power_values:
                    errors.append(f"Invalid power value {power} in {cal_type}")
                
                # Validate slope and intercept ranges based on empirical data
                if not (0.05 < slope < 0.5):
                    errors.append(f"Suspicious slope value {slope} in {cal_type} for power {power}")
                if not (25 < intercept < 60):
                    errors.append(f"Suspicious intercept value {intercept} in {cal_type} for power {power}")
            except ValueError:
                errors.append(f"Invalid power value format: {power_str}")

    return errors

def validate_data_structure(data: dict) -> List[str]:
    """Validate the structure of the calibration data"""
    errors = []
    
    for key, entry in data.items():
        # Check basic structure
        if not isinstance(entry, dict):
            errors.append(f"Invalid entry type for key {key}")
            continue
            
        # Check calibration data presence
        for cal_type in ['gpu_calibration', 'hbm_calibration']:
            if cal_type not in entry:
                errors.append(f"Missing {cal_type} in entry {key}")
                continue
                
            if not isinstance(entry[cal_type], dict):
                errors.append(f"Invalid {cal_type} type in entry {key}")
                continue
                
            # Check calibration data format
            for power, values in entry[cal_type].items():
                if not isinstance(values, list) or len(values) != 2:
                    errors.append(f"Invalid calibration format for {cal_type} power {power} in {key}")
                    continue
                    
                try:
                    float(power)
                    float(values[0])
                    float(values[1])
                except ValueError:
                    errors.append(f"Invalid numeric value in {cal_type} power {power} in {key}")

    return errors

def validate_data_consistency(data: dict) -> List[str]:
    """Validate consistency of calibration data across configurations"""
    errors = []
    
    # Group configurations by system type
    system_configs: Dict[str, Dict[str, dict]] = {}
    for key, entry in data.items():
        system = key.split('_')[0]
        if system not in system_configs:
            system_configs[system] = {}
        system_configs[system][key] = entry
    
    # Check consistency within each system type
    for system, configs in system_configs.items():
        power_values = set()
        for key, entry in configs.items():
            # Collect all power values
            gpu_powers = set(float(p) for p in entry['gpu_calibration'].keys())
            hbm_powers = set(float(p) for p in entry['hbm_calibration'].keys())
            
            # Check if GPU and HBM calibrations have the same power values
            if gpu_powers != hbm_powers:
                errors.append(f"Mismatched power values between GPU and HBM calibration in {key}")
            
            # Add to overall power values
            if not power_values:
                power_values = gpu_powers
            elif power_values != gpu_powers:
                errors.append(f"Inconsistent power values in {key} compared to other {system} configurations")
    
    return errors

def validate_calibration_data(json_file: str = 'dray_ECTC4.json') -> bool:
    """Main validation function"""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_file} not found")
        return False
    except json.JSONDecodeError:
        print(f"Error: {json_file} contains invalid JSON")
        return False

    all_errors = []

    # Validate data structure
    structure_errors = validate_data_structure(data)
    if structure_errors:
        all_errors.extend(["Data Structure Errors:"] + structure_errors)

    # Validate value ranges
    range_errors = []
    for key, entry in data.items():
        errors = validate_value_ranges(key, entry)
        range_errors.extend([f"{key}: {error}" for error in errors])
    if range_errors:
        all_errors.extend(["Value Range Errors:"] + range_errors)

    # Validate data consistency
    consistency_errors = validate_data_consistency(data)
    if consistency_errors:
        all_errors.extend(["Data Consistency Errors:"] + consistency_errors)

    # Print validation results
    if all_errors:
        print("Validation Failed!")
        print("\n".join(all_errors))
        return False
    else:
        print("Validation Successful!")
        print(f"Verified {len(data)} configurations")
        return True

def main():
    """Main entry point"""
    success = validate_calibration_data()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()