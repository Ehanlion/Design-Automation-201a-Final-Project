#!/usr/bin/env python3

# Minimal test to verify the thermal analysis function works
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_thermal_analysis():
    """Test the thermal analysis function that the GUI calls"""
    print("Testing thermal analysis function...")
    
    try:
        from calibrated_iterations import iterations_gui_safe
        
        # Test the function call with 3D_waferscale
        print("Calling iterations_gui_safe('3D_waferscale')...")
        result = iterations_gui_safe('3D_waferscale')
        
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        if result and isinstance(result, tuple) and len(result) >= 4:
            runtime, gpu_temp, hbm_temp, idle_frac = result
            print(f"\n✓ Analysis successful!")
            print(f"  Runtime: {runtime:.2f} seconds")
            print(f"  GPU Temperature: {gpu_temp:.1f}°C")
            print(f"  HBM Temperature: {hbm_temp:.1f}°C")
            print(f"  GPU Idle Fraction: {idle_frac:.3f}")
            
            # Validate ranges
            if runtime > 0 and 40 <= gpu_temp <= 120 and 40 <= hbm_temp <= 120 and 0 <= idle_frac <= 1:
                print("✓ All values are within expected ranges!")
                return True
            else:
                print("✗ Some values are out of expected ranges")
                return False
        else:
            print("✗ Invalid result format")
            return False
            
    except Exception as e:
        print(f"✗ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_thermal_analysis()
    print(f"\nTest result: {'PASSED' if success else 'FAILED'}")
