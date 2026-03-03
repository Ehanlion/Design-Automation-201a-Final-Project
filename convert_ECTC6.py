import json

def parse_temperature_dict(file_content):
    data = {}
    current_system = None
    current_conditions = {}
    
    # Helper function to extract tuple values from string
    def extract_values(line):
        if ":" not in line:
            return None, None
        power = float(line.split(":")[0].strip())
        tuple_str = line.split(":")[-1].strip()
        if not tuple_str.startswith("(") or not tuple_str.endswith(")"):
            return None, None
        values = tuple_str[1:-1].split(",")
        if len(values) != 2:
            return None, None
        return power, {"slope": float(values[0]), "intercept": float(values[1])}

    for line in file_content.split("\n"):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith("#") or "if(" not in line:
            continue

        # Extract condition check
        if "if(" in line:
            condition_str = line[line.index("if(") + 3:line.index(")")]
            conditions = {}
            
            # Parse conditions
            for cond in condition_str.split("and"):
                cond = cond.strip()
                if "==" in cond:
                    key, value = cond.split("==")
                    key = key.strip()
                    value = value.strip()
                    try:
                        value = eval(value)  # Convert string values to proper types
                    except:
                        value = value.strip()
                    conditions[key] = value
            
            # Create a key for these conditions
            condition_key = "_".join(f"{k}_{v}" for k, v in sorted(conditions.items()))
            current_conditions = conditions

        # Look for temperature dictionary assignments
        if 'temperature_dict["' in line:
            system = line[line.index('"') + 1:line.rindex('"')]
            current_system = system
            if current_system not in data:
                data[current_system] = {}
            if current_conditions:
                data[current_system][condition_key] = {
                    "conditions": current_conditions,
                    "values": {}
                }

        # Extract power values and their corresponding tuples
        if current_system and ":" in line and "(" in line and ")" in line:
            power, values = extract_values(line)
            if power is not None and current_conditions:
                data[current_system][condition_key]["values"][str(power)] = values

    return data

# Read the original file
with open("dray_ECTC6.txt", "r") as f:
    content = f.read()

# Parse the data
calibration_data = parse_temperature_dict(content)

# Write to JSON file
with open("dray_ECTC6.json", "w") as f:
    json.dump(calibration_data, f, indent=2)

print("Conversion completed. Data saved to dray_ECTC6.json")