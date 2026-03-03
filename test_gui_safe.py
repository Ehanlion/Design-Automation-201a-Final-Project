#!/usr/bin/env python3

# Simple test script to verify iterations_gui_safe function works
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calibrated_iterations import iterations_gui_safe

def test_gui_safe_function():
    print("Testing iterations_gui_safe function...")
    
    # Test 3D waferscale
    print("\nTesting 3D_waferscale:")
    result_3d = iterations_gui_safe('3D_waferscale')
    print(f"Result: {result_3d}")
    print(f"Type: {type(result_3d)}")
    
    if result_3d and isinstance(result_3d, tuple) and len(result_3d) == 4:
        runtime, gpu_temp, hbm_temp, idle_frac = result_3d
        print(f"  Runtime: {runtime} seconds")
        print(f"  GPU Temperature: {gpu_temp}°C")
        print(f"  HBM Temperature: {hbm_temp}°C")
        print(f"  GPU Idle Fraction: {idle_frac}")
        print("✓ 3D_waferscale test PASSED")
    else:
        print("✗ 3D_waferscale test FAILED")
    
    # Test 2p5D waferscale
    print("\nTesting 2p5D_waferscale:")
    result_2p5d = iterations_gui_safe('2p5D_waferscale')
    print(f"Result: {result_2p5d}")
    
    if result_2p5d and isinstance(result_2p5d, tuple) and len(result_2p5d) == 4:
        runtime, gpu_temp, hbm_temp, idle_frac = result_2p5d
        print(f"  Runtime: {runtime} seconds")
        print(f"  GPU Temperature: {gpu_temp}°C")
        print(f"  HBM Temperature: {hbm_temp}°C")
        print(f"  GPU Idle Fraction: {idle_frac}")
        print("✓ 2p5D_waferscale test PASSED")
    else:
        print("✗ 2p5D_waferscale test FAILED")

if __name__ == "__main__":
    test_gui_safe_function()
