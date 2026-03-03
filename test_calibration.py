from convert_calibration_data import convert_calibration_data
from thermal_analysis_gui import calibrate_GPU, calibrate_HBM

def test_calibration():
    # First convert all calibration data to JSON
    convert_calibration_data()
    
    # Test some known calibration points
    test_cases = [
        {
            "system_name": "2p5D_1GPU",
            "HBM_power": 5.0,
            "HTC": 10,
            "TIM_cond": 10,
            "infill_cond": 19,
            "underfill_cond": 19,
            "HBM_stack_height": 8,
            "dummy_Si": False
        },
        {
            "system_name": "3D_1GPU", 
            "HBM_power": 5.0,
            "HTC": 10,
            "TIM_cond": 10,
            "infill_cond": 19,
            "underfill_cond": 19,
            "HBM_stack_height": 8,
            "dummy_Si": True
        }
    ]
    
    print("Testing calibration functions...")
    for case in test_cases:
        print(f"\nTesting case: {case}")
        gpu_result = calibrate_GPU(**case)
        hbm_result = calibrate_HBM(**case)
        print(f"GPU calibration result: {gpu_result}")
        print(f"HBM calibration result: {hbm_result}")

if __name__ == "__main__":
    test_calibration()