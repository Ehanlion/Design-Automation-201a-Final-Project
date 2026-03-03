#!/usr/bin/env python3
"""
Simple test script to verify the GUI components work correctly
"""

import os
import sys

def test_file_exists(filepath, description):
    """Test if a file exists"""
    if os.path.exists(filepath):
        print(f"✓ {description}: {filepath}")
        return True
    else:
        print(f"✗ {description}: {filepath} (NOT FOUND)")
        return False

def test_gui_dependencies():
    """Test if GUI dependencies are available"""
    print("Testing GUI Dependencies...")
    
    try:
        import dash
        print("✓ Dash imported successfully")
    except ImportError:
        print("✗ Dash not found. Run: pip install dash")
        return False
    
    try:
        import dash_bootstrap_components
        print("✓ Dash Bootstrap Components imported successfully")
    except ImportError:
        print("✗ Dash Bootstrap Components not found. Run: pip install dash-bootstrap-components")
        return False
    
    return True

def test_required_files():
    """Test if all required files exist"""
    print("\nTesting Required Files...")
    
    base_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow"
    files_to_check = [
        ("calibrated_iterations.py", f"{base_path}/calibrated_iterations.py"),
        ("buildRun.sh", f"{base_path}/DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh"),
        ("run.sh", f"{base_path}/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"),
        ("3D config YAML", f"{base_path}/DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100.yaml"),
        ("2.5D config YAML", f"{base_path}/DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100_2p5D.yaml"),
        ("load_and_test_design.py", f"{base_path}/load_and_test_design.py"),
    ]
    
    all_exist = True
    for description, filepath in files_to_check:
        if not test_file_exists(filepath, description):
            all_exist = False
    
    return all_exist

def main():
    """Main test function"""
    print("Thermal Analysis GUI Test Script")
    print("=" * 40)
    
    # Change to the correct directory
    os.chdir("/app/nanocad/projects/deepflow_thermal/DeepFlow")
    
    # Test dependencies
    deps_ok = test_gui_dependencies()
    
    # Test required files
    files_ok = test_required_files()
    
    print("\n" + "=" * 40)
    if deps_ok and files_ok:
        print("✓ All tests passed! The GUI should work correctly.")
        print("Run: python thermal_analysis_gui.py")
        print("Or: ./launch_gui.sh")
    else:
        print("✗ Some tests failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
