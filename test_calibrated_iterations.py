from calibrated_iterations import *

def debug_thermal_analysis_run():
    try:
        system_type = "3D_waferscale"  # Example system type, can be changed as needed
        # Run the analysis with timeout
        print("Running thermal analysis with system type:", system_type)

        # For now, let's return mock data to test the GUI functionality
        # Mock results for testing
        runtime = 12.34  # seconds
        gpu_temp = 85.2  # Celsius
        hbm_temp = 82.1  # Celsius  
        idle_frac = 0.15  # fraction
        results = (runtime, gpu_temp, hbm_temp, idle_frac)

        # TODO: Replace with actual iterations call once build environment is ready
        results = iterations(system_name = system_type)
        # print("Thermal analysis completed with results:", results)

        return "Analysis completed successfully", results
    
    except Exception as e:
        print("Error during thermal analysis run:", str(e))
        raise e

def main():
    print("Starting thermal analysis run...")
    try:
        result_message, results = debug_thermal_analysis_run()
        print(result_message)
        print("Results:", results)
    except Exception as e:
        print("Error during thermal analysis run:", str(e))

if __name__ == "__main__":
    main()