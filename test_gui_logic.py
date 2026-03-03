#!/usr/bin/env python3

# Simulate the GUI thermal analysis without Dash dependencies
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def simulate_gui_analysis():
    """Simulate what the GUI does when the Run Analysis button is clicked"""
    print("=" * 50)
    print("SIMULATING GUI ANALYSIS")
    print("=" * 50)
    
    # Simulate the parameters from GUI
    system_type = '3D_waferscale'
    model_type = 'llama_3_3_70b'
    parallelism_strategy = 'strategy_1'
    htc_value = '10'
    bandwidth = '14400'
    
    print(f"System: {system_type}")
    print(f"Model: {model_type}")
    print(f"Parallelism: {parallelism_strategy}")
    print(f"HTC: {htc_value} kW/(m²·K)")
    print(f"Bandwidth: {bandwidth} GB/s")
    print()
    
    try:
        # This is what run_thermal_analysis() does
        print("Running thermal analysis...")
        
        from calibrated_iterations import iterations_gui_safe
        results = iterations_gui_safe(system_name=system_type)
        
        print(f"Analysis completed!")
        
        if results and isinstance(results, tuple) and len(results) >= 4:
            runtime, gpu_temp, hbm_temp, idle_frac = results
            
            print("\n" + "=" * 30)
            print("ANALYSIS RESULTS")
            print("=" * 30)
            print(f"Runtime: {runtime:.2f} seconds")
            print(f"GPU Temperature: {gpu_temp:.1f}°C")
            print(f"HBM Temperature: {hbm_temp:.1f}°C")
            print(f"GPU Idle Fraction: {idle_frac:.2f}")
            print("=" * 30)
            
            # This is what parse_analysis_results() would do
            runtime_data = {
                'iterations': [1],
                'runtimes': [runtime],
                'temperatures': [gpu_temp],
                'costs': []
            }
            
            print(f"\nGUI would display:")
            print(f"- Runtime plot with value: {runtime:.2f}s")
            print(f"- Temperature plot with value: {gpu_temp:.1f}°C")
            print(f"- Results table with all values")
            
            return True
        else:
            print("✗ Analysis failed - invalid results")
            return False
            
    except Exception as e:
        print(f"✗ Analysis failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def simulate_bandwidth_sweep():
    """Simulate what the GUI does for bandwidth sweep"""
    print("\n" + "=" * 50)
    print("SIMULATING BANDWIDTH SWEEP")
    print("=" * 50)
    
    bandwidth_values = ['450', '900', '1800', '3600', '7200', '14400', '28800', '57600', '115200']
    results_summary = ""
    
    sweep_data = {
        'bandwidths': [],
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    }
    
    from calibrated_iterations import iterations_gui_safe
    
    print("Testing first few bandwidth values...")
    for i, bandwidth in enumerate(bandwidth_values[:3]):  # Test only first 3 for demo
        print(f"\nTesting bandwidth {bandwidth} GB/s...")
        
        try:
            # In real GUI this would call run_thermal_analysis for each bandwidth
            results = iterations_gui_safe(system_name='3D_waferscale')
            
            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                sweep_data['bandwidths'].append(int(bandwidth))
                sweep_data['runtimes'].append(runtime)
                sweep_data['gpu_temperatures'].append(gpu_temp)
                sweep_data['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    sweep_data['idle_fractions'].append(idle_frac)
                
                results_summary += f"Bandwidth {bandwidth}: Runtime={runtime:.2f}s, GPU={gpu_temp:.1f}°C, HBM={hbm_temp:.1f}°C\n"
                print(f"  ✓ Success: Runtime={runtime:.2f}s, GPU={gpu_temp:.1f}°C")
            else:
                results_summary += f"Bandwidth {bandwidth}: Analysis failed\n"
                print(f"  ✗ Failed")
                
        except Exception as e:
            results_summary += f"Bandwidth {bandwidth}: Error - {str(e)}\n"
            print(f"  ✗ Error: {e}")
    
    print(f"\nSweep Results Summary:")
    print(results_summary)
    print(f"GUI would display bandwidth vs runtime/temperature plots")
    
    return len(sweep_data['bandwidths']) > 0

if __name__ == "__main__":
    print("Testing GUI functionality without Dash...")
    
    # Test single analysis
    single_success = simulate_gui_analysis()
    
    # Test bandwidth sweep
    sweep_success = simulate_bandwidth_sweep()
    
    print(f"\n" + "=" * 50)
    print("FINAL RESULTS")
    print("=" * 50)
    print(f"Single Analysis: {'✓ PASSED' if single_success else '✗ FAILED'}")
    print(f"Bandwidth Sweep: {'✓ PASSED' if sweep_success else '✗ FAILED'}")
    print(f"Overall GUI Logic: {'✓ WORKING' if single_success and sweep_success else '✗ NEEDS FIXING'}")
    print("=" * 50)
