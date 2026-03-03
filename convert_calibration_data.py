import json

def convert_calibration_data():
    """Convert thermal calibration data from code to JSON format."""
    calibration_data = {
        "2p5D_1GPU": {},
        "3D_1GPU": {},
        "2p5D_WS": {},
        "3D_WS": {},
    }

    # Base conditions for each configuration
    configurations = {
        "2p5D_1GPU": {
            "TIM_cond": [5, 10, 50],
            "infill_cond": [1, 19, 237],
            "underfill_cond": [1, 19, 237],
            "HTC": [7, 10],
            "HBM_stack_height": [8, 16],
            "dummy_Si": [True, False]
        },
        "3D_1GPU": {
            "TIM_cond": [5, 10, 50],
            "infill_cond": [1, 19, 237], 
            "underfill_cond": [1, 19, 237],
            "HTC": [7, 10],
            "HBM_stack_height": [8, 16],
            "dummy_Si": [True]
        }
    }

    for system in configurations:
        configs = configurations[system]
        for TIM_cond in configs["TIM_cond"]:
            for infill_cond in configs["infill_cond"]:
                for underfill_cond in configs["underfill_cond"]:
                    for HTC in configs["HTC"]:
                        for HBM_stack_height in configs["HBM_stack_height"]:
                            for dummy_Si in configs["dummy_Si"]:
                                key = f"{system}_{TIM_cond}_{infill_cond}_{underfill_cond}_{HTC}_{HBM_stack_height}_{dummy_Si}"
                                calibration_data[system][key] = {
                                    "conditions": {
                                        "TIM_cond": TIM_cond,
                                        "infill_cond": infill_cond,
                                        "underfill_cond": underfill_cond,
                                        "HTC": HTC,
                                        "HBM_stack_height": HBM_stack_height,
                                        "dummy_Si": dummy_Si
                                    },
                                    "HBM_power_map": {
                                        "5.0": {"slope": 0.0, "intercept": 0.0},
                                        "5.6": {"slope": 0.0, "intercept": 0.0},
                                        "6.8024": {"slope": 0.0, "intercept": 0.0}
                                    }
                                }

    # Load calibration data from existing files
    calibration_files = [
        "dray_ECTC6.txt",
        "dray_ECTC3.txt",
        "dray_techcon.txt"
    ]

    for file in calibration_files:
        try:
            with open(file, 'r') as f:
                lines = f.readlines()
                current_system = None
                current_conditions = {}
                
                for line in lines:
                    if "system_name ==" in line:
                        current_system = line.split('"')[1]
                    elif "TIM_cond ==" in line or "infill_cond ==" in line or "underfill_cond ==" in line:
                        cond_name = line.split("==")[0].strip()
                        cond_value = float(line.split("==")[1].strip())
                        current_conditions[cond_name] = cond_value
                    elif "temperature_dict[" in line and "{" in line:
                        power_data = {}
                        power_lines = []
                        while "}" not in line:
                            if ":" in line:
                                power, values = line.split(":")
                                power = float(power.strip())
                                slope, intercept = eval(values.strip().rstrip(","))
                                power_data[str(power)] = {"slope": slope, "intercept": intercept}
                            line = next(lines)
                            power_lines.append(line)
                        
                        key = f"{current_system}_{current_conditions['TIM_cond']}_{current_conditions['infill_cond']}_{current_conditions['underfill_cond']}"
                        if current_system in calibration_data:
                            if key in calibration_data[current_system]:
                                calibration_data[current_system][key]["HBM_power_map"] = power_data
        except FileNotFoundError:
            print(f"Warning: {file} not found")

    # Save to JSON file
    with open('dray_calibration.json', 'w') as f:
        json.dump(calibration_data, f, indent=2)

if __name__ == "__main__":
    convert_calibration_data()