#!/usr/bin/env python3
"""
Test script to debug the iterations function call
"""
import os
import sys
sys.path.append('/app/nanocad/projects/deepflow_thermal/DeepFlow')

print("Testing iterations function...")
print("Current working directory:", os.getcwd())

try:
    # Change to the correct directory
    os.chdir('/app/nanocad/projects/deepflow_thermal/DeepFlow')
    print("Changed directory to:", os.getcwd())
    
    # Try to import
    from calibrated_iterations import iterations
    print("Successfully imported iterations function")
    
    # Try to call the function
    print("Calling iterations with system_name='3D_waferscale'...")
    result = iterations(system_name='3D_waferscale')
    print("Function call successful!")
    print("Result:", result)
    
except ImportError as e:
    print("Import error:", e)
    import traceback
    traceback.print_exc()
except Exception as e:
    print("Runtime error:", e)
    import traceback
    traceback.print_exc()
