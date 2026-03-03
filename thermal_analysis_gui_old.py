# import dash
# from dash import dcc, html, dash_table, Input, Output, State
# from dash.exceptions import PreventUpdate
# import dash_bootstrap_components as dbc
# import plotly.graph_objs as go
# import plotly.express as px
import contextlib
import subprocess
import os
import re
import threading
import time
from datetime import datetime
import pandas as pd
import sys
import traceback
from DeepFlow_llm_dev.run_perf import run_LLM, run_GEMM
import contextlib  

# dedeepyo : 3-Jul-25 : Implementing calibration-informed iterations
from ast import Not
import math

# core:
    # nominal_frequency: 2.82e9
# SRAM-R:
#     bandwidth: 244 TB # Line 79, element 78.
# SRAM-L1:
#     bandwidth: 36 TB # Line 66, element 65.
# SRAM-L2:
#     bandwidth: 14100 GB # source: GTC 2021 # Line 53, element 52.

# Only for 3D wafer-scale
# Assume linear frequency voltage scaling. Assume safe temperature is 80C for the GPU. That is 220 W for the GPU. Peak FLOPs of 312 at 270 W. So 312 * 220 / 270 = 254.22 FLOPs. This corresponds to nominal_flop_rate_per_mcu of 417. Replace in line 20 / index 19 of config yaml.
# With HTC of 20 kW / (m^2 * K), safe temperature of 95 C is attained at 650 W, which is 750 TFLOPs, not considered here. Our peak is 624 TFLOPs.
def GPU_FLOPs_throttled(GPU_peak_temperature, GPU_safe_temperature, GPU_peak_power = 540.0, GPU_average_power = 540.0): # W
    nominal_frequency = 1.41e9 # 1.41e9 # Hz
    GPU_FLOPs_power = 370.0
    register_bandwidth = 122 * 1024 # GB/s # 122 TB
    l1_bandwidth = 18 * 1024 # GB/s # 18 TB
    l2_bandwidth = 7050 # GB/s # 7050 GB
    step_size = 5.0 # W # 5.0, 30.0, 20.0

    if(GPU_peak_temperature > GPU_safe_temperature):
        # Reduce GPU_peak_power by 20W per iteration.
        # Assume linear frequency scaling.
        # Assume quadratic frequency power scaling.
        nominal_frequency *= math.sqrt((GPU_peak_power - step_size) / GPU_FLOPs_power)
        GPU_FLOPs_power = GPU_peak_power - step_size
        # nominal_frequency = 1.67e9 # 1.15e9 # Hz
        # GPU_FLOPs_power = 320.0
    # elif(GPU_peak_power == GPU_average_power):
    #     nominal_frequency = 2.82e9 # 1.41e9 # Hz
    #     GPU_FLOPs_power = 540.0
    else:
        nominal_frequency *= math.sqrt(GPU_peak_power / GPU_FLOPs_power)
        GPU_FLOPs_power = GPU_peak_power
    
    register_bandwidth *= nominal_frequency / 1.41e9
    l1_bandwidth *= nominal_frequency / 1.41e9
    l2_bandwidth *= nominal_frequency / 1.41e9

    return nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth

def calibrate_GPU(system_name = "2p5D_1GPU", HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False): # W # TIM_thickness = 10, 
    # Define slope and intercept for the calibration
    # Assuming trends are linear (they have been observed to be linear in prior experiments).
    temperature_dict = {}
    temperature_dict["2p5D_1GPU"] = {
        5.0 : (0.0719, 47.1),
        5.6 : (0.0719, 47.3),
        6.8024 : (0.0718, 47.8)
    }
    # if(system_name == "3D_1GPU"): # HTC here is TIM_height # HTC 100 means 10 kW / (m^2 * K) cooling, HTC 10 means 7 kW / (m^2 * K) cooling.
    #     if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.144, 49.3),
    #             5.6 : (0.144, 49.6),
    #             6.8024 : (0.144, 50.0)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.17, 49.8),
    #             5.6 : (0.17, 50.1),
    #             6.8024 : (0.17, 50.6)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.142, 49.1),
    #             5.6 : (0.142, 49.4),
    #             6.8024 : (0.142, 49.8)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.151, 49.4),
    #             5.6 : (0.151, 49.6),
    #             6.8024 : (0.151, 50.1)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.107, 48.2),
    #             5.6 : (0.107, 48.3),
    #             6.8024 : (0.107, 48.7)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.131, 48.8),
    #             5.6 : (0.131, 49),
    #             6.8024 : (0.131, 49.4)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.104, 48),
    #             5.6 : (0.104, 48.2),
    #             6.8024 : (0.104, 48.5)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.114, 48.2),
    #             5.6 : (0.114, 48.4),
    #             6.8024 : (0.114, 48.7)
    #         }
            # temperature_dict["3D_1GPU"] = {
            #     5.0 : (0.107, 48.1),
            #     5.6 : (0.107, 48.5),
            #     6.8024 : (0.107, 49.3)
            # }
    
    if(HBM_stack_height == 8):
        #TODO: Below is for 8-high HBM stack, comment out otherwise. 3D_1GPU.
        if(system_name == "3D_1GPU"):
            # if((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.290, 53.60),
            #         5.6 : (0.290, 54.64),
            #         6.8024 : (0.289, 56.80)
            #     }
            # elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.327, 54.63),
            #         5.6 : (0.327, 55.79),
            #         6.8024 : (0.327, 58.13)
            #     }
            # if((HTC == 7) and (TIM_cond == 5) and (infill_cond == 237)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 50.44),
            #         5.6 : (0.184, 51.09),
            #         6.8024 : (0.184, 52.40)
            #     }
            # elif((HTC == 7) and (TIM_cond == 5) and (infill_cond == 1)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.196, 50.77),
            #         5.6 : (0.196, 51.46),
            #         6.8024 : (0.196, 52.86)
            #     }
            # elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.170, 50.04),
            #         5.6 : (0.170, 50.65),
            #         6.8024 : (0.170, 51.86)
            #     }
            # elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.179, 50.25),
            #         5.6 : (0.179, 50.88),
            #         6.8024 : (0.179, 52.15)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 31.28),
            #         5.6 : (0.186, 31.22),
            #         6.8024 : (0.188, 31.11)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.186, 31.00),
            #         5.6 : (0.187, 30.95),
            #         6.8024 : (0.189, 30.84)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 31.28),
            #         5.6 : (0.186, 31.22),
            #         6.8024 : (0.188, 31.11)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.186, 31.00),
            #         5.6 : (0.187, 30.95),
            #         6.8024 : (0.189, 30.84)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.174, 31.88),
            #         5.6 : (0.174, 31.92),
            #         6.8024 : (0.177, 31.79)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.172, 32.18),
            #         5.6 : (0.173, 32.13),
            #         6.8024 : (0.175, 32.03)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.174, 31.88),
            #         5.6 : (0.174, 31.92),
            #         6.8024 : (0.177, 31.79)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.172, 32.18),
            #         5.6 : (0.173, 32.13),
            #         6.8024 : (0.175, 32.03)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.190, 50.63),
            #         5.6 : (0.190, 50.87),
            #         6.8024 : (0.190, 51.33)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 50.53),
            #         5.6 : (0.187, 50.78),
            #         6.8024 : (0.187, 51.22)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.189, 50.47),
            #         5.6 : (0.189, 50.72),
            #         6.8024 : (0.189, 51.16)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.185, 50.50),
            #         5.6 : (0.186, 50.73),
            #         6.8024 : (0.186, 51.17)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.176, 50.22),
            #         5.6 : (0.176, 50.44),
            #         6.8024 : (0.176, 50.85)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 50.10),
            #         5.6 : (0.173, 50.33),
            #         6.8024 : (0.173, 50.74)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.175, 50.07),
            #         5.6 : (0.175, 50.30),
            #         6.8024 : (0.175, 50.71)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.172, 50.09),
            #         5.6 : (0.172, 50.32),
            #         6.8024 : (0.172, 50.72)
            #     }
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.190, 50.63),
            #         5.6 : (0.190, 51.30),
            #         6.8024 : (0.190, 52.62)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 50.53),
            #         5.6 : (0.187, 51.20),
            #         6.8024 : (0.187, 52.52)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.189, 50.47),
            #         5.6 : (0.189, 51.13),
            #         6.8024 : (0.189, 52.47)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.185, 50.50),
            #         5.6 : (0.186, 51.15),
            #         6.8024 : (0.186, 52.47)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.176, 50.22),
            #         5.6 : (0.176, 50.83),
            #         6.8024 : (0.176, 52.07)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 50.10),
            #         5.6 : (0.173, 50.72),
            #         6.8024 : (0.173, 51.95)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.175, 50.07),
            #         5.6 : (0.175, 50.69),
            #         6.8024 : (0.175, 51.93)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.172, 50.09),
            #         5.6 : (0.172, 50.70),
            #         6.8024 : (0.172, 51.93)
            #     }
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.191, 50.59),
                    5.6 : (0.191, 51.27),
                    6.8024 : (0.191, 52.61)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.187, 50.53),
                    5.6 : (0.187, 51.19),
                    6.8024 : (0.187, 52.52)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.190, 50.55),
                    5.6 : (0.190, 51.22),
                    6.8024 : (0.190, 52.55)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.186, 50.50),
                    5.6 : (0.186, 51.16),
                    6.8024 : (0.186, 52.49)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.177, 50.20),
                    5.6 : (0.177, 50.83),
                    6.8024 : (0.177, 52.09)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.174, 50.11),
                    5.6 : (0.174, 50.73),
                    6.8024 : (0.174, 51.97)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.176, 50.15),
                    5.6 : (0.176, 50.77),
                    6.8024 : (0.176, 52.01)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.173, 50.09),
                    5.6 : (0.173, 50.71),
                    6.8024 : (0.173, 51.94)
                }

        #TODO: Below is for 8-high HBM stack, comment out otherwise. For 2p5D_1GPU.
        if(system_name == "2p5D_1GPU"):
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.175, 32.07),
                    5.6 : (0.177, 31.98),
                    6.8024 : (0.180, 31.80)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.173, 31.88),
                    5.6 : (0.175, 31.79),
                    6.8024 : (0.178, 31.61)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.173, 31.97),
                    5.6 : (0.174, 31.88),
                    6.8024 : (0.178, 31.70)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.172, 31.89),
                    5.6 : (0.174, 31.79),
                    6.8024 : (0.177, 31.61)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.161, 32.99),
                    5.6 : (0.163, 32.90),
                    6.8024 : (0.166, 32.74)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.163, 32.49),
                    5.6 : (0.165, 32.41),
                    6.8024 : (0.168, 32.25)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.160, 32.84),
                    5.6 : (0.162, 32.75),
                    6.8024 : (0.166, 32.59)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.161, 32.70),
                    5.6 : (0.163, 32.62),
                    6.8024 : (0.166, 32.45)
                }
    # elif(HBM_stack_height == 12):
    #     #TODO: Below is for 12-high HBM stack, comment out otherwise.
    #     if(system_name == "3D_1GPU"): # HTC here is TIM_height # HTC 100 means 10 kW / (m^2 * K) cooling, HTC 10 means 7 kW / (m^2 * K) cooling.
    #         if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.147, 51.1),
    #                 5.6 : (0.147, 51.5),
    #                 6.8024 : (0.147, 52.1)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 1) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.173, 51.9),
    #                 5.6 : (0.173, 52.3),
    #                 6.8024 : (0.173, 53.0)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.143, 51),
    #                 5.6 : (0.143, 51.3),
    #                 6.8024 : (0.143, 51.9)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.158, 50.7),
    #                 5.6 : (0.159, 51.1),
    #                 6.8024 : (0.159, 51.7)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.107, 48.2),
    #                 5.6 : (0.107, 48.3),
    #                 6.8024 : (0.107, 48.7)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.131, 48.8),
    #                 5.6 : (0.131, 49),
    #                 6.8024 : (0.131, 49.4)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.104, 48),
    #                 5.6 : (0.104, 48.2),
    #                 6.8024 : (0.104, 48.5)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.114, 48.2),
    #                 5.6 : (0.114, 48.4),
    #                 6.8024 : (0.114, 48.7)
    #             }
    elif(HBM_stack_height == 16):
        #TODO: Below is for 16-high HBM stack, comment out otherwise. For 2p5D_1GPU.
        if(system_name == "2p5D_1GPU"):
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.184, 31.28),
                    5.6 : (0.186, 31.22),
                    6.8024 : (0.188, 31.11)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.186, 31.00),
                    5.6 : (0.187, 30.95),
                    6.8024 : (0.189, 30.84)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.184, 31.28),
                    5.6 : (0.186, 31.22),
                    6.8024 : (0.188, 31.11)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.186, 31.00),
                    5.6 : (0.187, 30.95),
                    6.8024 : (0.189, 30.84)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.174, 31.88),
                    5.6 : (0.174, 31.92),
                    6.8024 : (0.177, 31.79)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.172, 32.18),
                    5.6 : (0.173, 32.13),
                    6.8024 : (0.175, 32.03)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.174, 31.88),
                    5.6 : (0.174, 31.92),
                    6.8024 : (0.177, 31.79)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.172, 32.18),
                    5.6 : (0.173, 32.13),
                    6.8024 : (0.175, 32.03)
                }

        #TODO: Below is for 16-high HBM stack, comment out otherwise.
        if(system_name == "3D_1GPU"):
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.193, 55.24),
                    5.6 : (0.193, 55.68),
                    6.8024 : (0.193, 56.49)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.187, 54.89),
                    5.6 : (0.187, 55.33),
                    6.8024 : (0.187, 56.13)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.192, 54.95),
                    5.6 : (0.192, 55.39),
                    6.8024 : (0.192, 56.19)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.186, 54.83),
                    5.6 : (0.186, 55.27),
                    6.8024 : (0.186, 56.06)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.180, 54.40),
                    5.6 : (0.180, 54.81),
                    6.8024 : (0.180, 55.56)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.173, 54.19),
                    5.6 : (0.173, 54.61),
                    6.8024 : (0.173, 55.35)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.178, 54.21),
                    5.6 : (0.178, 54.63),
                    6.8024 : (0.178, 55.38)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.173, 54.11),
                    5.6 : (0.173, 54.51),
                    6.8024 : (0.173, 55.25)
                }
            
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.193, 55.24),
            #         5.6 : (0.193, 55.68),
            #         6.8024 : (0.193, 56.49)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 54.89),
            #         5.6 : (0.187, 55.33),
            #         6.8024 : (0.187, 56.13)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.192, 54.95),
            #         5.6 : (0.192, 55.39),
            #         6.8024 : (0.192, 56.19)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.186, 54.83),
            #         5.6 : (0.186, 55.27),
            #         6.8024 : (0.186, 56.06)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.180, 54.40),
            #         5.6 : (0.180, 54.81),
            #         6.8024 : (0.180, 55.56)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 54.19),
            #         5.6 : (0.173, 54.61),
            #         6.8024 : (0.173, 55.35)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.178, 54.21),
            #         5.6 : (0.178, 54.63),
            #         6.8024 : (0.178, 55.38)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 54.11),
            #         5.6 : (0.173, 54.51),
            #         6.8024 : (0.173, 55.25)
            #     }
            
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.220, 56.52),
            #         5.6 : (0.220, 57.03),
            #         6.8024 : (0.220, 57.95)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.217, 56.34),
            #         5.6 : (0.217, 56.85),
            #         6.8024 : (0.216, 57.80)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.196, 55.13),
            #         5.6 : (0.196, 55.59),
            #         6.8024 : (0.196, 56.40)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.189, 54.93),
            #         5.6 : (0.189, 55.37),
            #         6.8024 : (0.189, 56.17)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.200, 55.34),
            #         5.6 : (0.200, 55.80),
            #         6.8024 : (0.199, 56.73)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.197, 55.31),
            #         5.6 : (0.197, 55.78),
            #         6.8024 : (0.198, 56.51)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.181, 54.32),
            #         5.6 : (0.181, 54.74),
            #         6.8024 : (0.181, 55.49)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.174, 54.15),
            #         5.6 : (0.174, 54.55),
            #         6.8024 : (0.174, 55.24)
            #     }
    
        #     if((HTC == 7) and (TIM_cond == 5) and (infill_cond == 237)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.184, 54.72),
        #             5.6 : (0.184, 55.15),
        #             6.8024 : (0.184, 55.93)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 5) and (infill_cond == 1)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.199, 54.80),
        #             5.6 : (0.199, 55.32),
        #             6.8024 : (0.199, 56.15)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.170, 54.01),
        #             5.6 : (0.170, 54.41),
        #             6.8024 : (0.170, 55.13)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.180, 54.19),
        #             5.6 : (0.180, 54.60),
        #             6.8024 : (0.180, 55.36)
        #         }

    # if(system_name == "3D_1GPU"):
    #     if((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237) and (TIM_thickness == 10)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.168, 49.95),
    #             5.6 : (0.168, 50.55),
    #             6.8024 : (0.168, 51.75)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1) and (TIM_thickness == 10)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.176, 50.05),
    #             5.6 : (0.176, 50.67),
    #             6.8024 : (0.176, 51.91)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (TIM_thickness == 10)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.156, 49.6),
    #             5.6 : (0.156, 50.15),
    #             6.8024 : (0.156, 51.26)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (TIM_thickness == 10)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.161, 49.58),
    #             5.6 : (0.161, 50.14),
    #             6.8024 : (0.161, 51.27)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237) and (TIM_thickness == 20)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.168, 49.95),
    #             5.6 : (0.168, 50.55),
    #             6.8024 : (0.168, 51.75)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1) and (TIM_thickness == 20)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.176, 50.05),
    #             5.6 : (0.176, 50.67),
    #             6.8024 : (0.176, 51.91)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (TIM_thickness == 20)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.156, 49.6),
    #             5.6 : (0.156, 50.15),
    #             6.8024 : (0.156, 51.26)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (TIM_thickness == 20)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.161, 49.58),
    #             5.6 : (0.161, 50.14),
    #             6.8024 : (0.161, 51.27)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237) and (TIM_thickness == 50)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.168, 49.95),
    #             5.6 : (0.168, 50.55),
    #             6.8024 : (0.168, 51.75)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1) and (TIM_thickness == 50)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.176, 50.05),
    #             5.6 : (0.176, 50.67),
    #             6.8024 : (0.176, 51.91)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (TIM_thickness == 50)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.156, 49.6),
    #             5.6 : (0.156, 50.15),
    #             6.8024 : (0.156, 51.26)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (TIM_thickness == 50)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.161, 49.58),
    #             5.6 : (0.161, 50.14),
    #             6.8024 : (0.161, 51.27)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237) and (TIM_thickness == 100)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.168, 49.95),
    #             5.6 : (0.168, 50.55),
    #             6.8024 : (0.168, 51.75)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1) and (TIM_thickness == 100)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.176, 50.05),
    #             5.6 : (0.176, 50.67),
    #             6.8024 : (0.176, 51.91)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (TIM_thickness == 100)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.156, 49.6),
    #             5.6 : (0.156, 50.15),
    #             6.8024 : (0.156, 51.26)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (TIM_thickness == 100)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.161, 49.58),
    #             5.6 : (0.161, 50.14),
    #             6.8024 : (0.161, 51.27)
    #         }
        # elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
        #     temperature_dict["3D_1GPU"] = {
        #         5.0 : (0.107, 48.2),
        #         5.6 : (0.107, 48.3),
        #         6.8024 : (0.107, 48.7)
        #     }
        # elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
        #     temperature_dict["3D_1GPU"] = {
        #         5.0 : (0.131, 48.8),
        #         5.6 : (0.131, 49),
        #         6.8024 : (0.131, 49.4)
        #     }
        # elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
        #     temperature_dict["3D_1GPU"] = {
        #         5.0 : (0.104, 48),
        #         5.6 : (0.104, 48.2),
        #         6.8024 : (0.104, 48.5)
        #     }
        # elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
        #     temperature_dict["3D_1GPU"] = {
        #         5.0 : (0.114, 48.2),
        #         5.6 : (0.114, 48.4),
        #         6.8024 : (0.114, 48.7)
        #     }

    

    temperature_dict["2p5D_waferscale"] = {
        5.0 : (0.0722, 47.1),
        5.6 : (0.0721, 47.4),
        6.8024 : (0.0722, 47.9)
    }
    # temperature_dict["3D_1GPU"] = {
    #     5.0 : (0.107, 48.1),
    #     5.6 : (0.107, 48.5),
    #     6.8024 : (0.107, 49.3)
    # }
    temperature_dict["3D_waferscale"] = {
        5.0 : (0.139, 49.2),
        5.6 : (0.139, 49.7),
        6.8024 : (0.139, 50.7)
    } #TODO: Comment 68 to 72 and uncomment 63 to 67.
    # temperature_dict["3D_waferscale"] = {
    #     5.0 : (0.13, 48.82),
    #     5.6 : (0.13, 49.344),
    #     6.8024 : (0.13, 50.21)
    # }
    if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.139, 49.2),
            5.6 : (0.139, 49.7),
            6.8024 : (0.139, 50.7)
        }
    if((HTC == 20) and (TIM_cond == 1) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.073, 47.2),
            5.6 : (0.073, 47.2),
            6.8024 : (0.073, 47.8)
        }
    if((TIM_cond == 10) and (HTC == 10) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.1214, 48.522),
            5.6 : (0.1214, 48.952),
            6.8024 : (0.1214, 49.812)
        }
    # if((TIM_cond == 100) and (HTC == 10) and (infill_cond == 237)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.121, 48.51),
    #         5.6 : (0.121, 48.94),
    #         6.8024 : (0.121, 49.8)
    #     }
    # if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.1574, 48.972),
    #         5.6 : (0.1574, 49.512),
    #         6.8024 : (0.1574, 50.592)
    #     }
    # if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.1574, 48.972),
    #         5.6 : (0.1574, 49.512),
    #         6.8024 : (0.1574, 50.592)
    #     }
    if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.165, 50.09),
            5.6 : (0.165, 50.404),
            6.8024 : (0.165, 50.904)
        }
    if((infill_cond == 1) and (TIM_cond == 10) and (HTC == 10)):
        # print("I am here.")
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.147, 49.2),
            5.6 : (0.147, 49.7),
            6.8024 : (0.147, 50.7)
        }
    if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 20)):
        # print("I am here.")
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.1049, 47.755),
            5.6 : (0.1049, 48.113),
            6.8024 : (0.1049, 48.862)
        }
    if((infill_cond == 237) and (TIM_cond == 10) and (HTC == 20)):
        # print("I am here.")
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.075, 47.237),
            5.6 : (0.075, 47.504),
            6.8024 : (0.075, 48.25)
        }
# Below is for 20 kW / (m^2 * K) cooling.
 # Below is for 10 kW / (m^2 * K) cooling and TIM of 10 W / (m K).
    
    return temperature_dict.get(system_name, {}).get(HBM_power, ())

def calibrate_HBM(system_name = "2p5D_1GPU", HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False): # W
    # Define slope and intercept for the calibration
    # Assuming trends are linear (they have been observed to be linear in prior experiments).

    # print(f"System: {system_name}, HBM_power: {HBM_power}, HTC: {HTC}, TIM_cond: {TIM_cond}, infill_cond: {infill_cond}, underfill_cond: {underfill_cond}, HBM_stack_height: {HBM_stack_height}, dummy_Si: {dummy_Si}")

    temperature_dict = {}
    temperature_dict["2p5D_1GPU"] = {
        5.0 : (0.0697, 47.4),
        5.6 : (0.0697, 47.6),
        6.8024 : (0.0696, 48.2)
    }
    temperature_dict["2p5D_waferscale"] = {
        5.0 : (0.0703, 47.2),
        5.6 : (0.0703, 47.5),
        6.8024 : (0.0702, 48)
    }
    # temperature_dict["3D_1GPU"] = {
    #     5.0 : (0.106, 48.2),
    #     5.6 : (0.106, 48.6),
    #     6.8024 : (0.106, 49.3)
    # }
    # if(system_name == "3D_1GPU"): # HTC here is TIM_height # HTC 100 means 10 kW / (m^2 * K) cooling, HTC 10 means 7 kW / (m^2 * K) cooling.
    #     if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.143, 49.3),
    #             5.6 : (0.143, 49.6),
    #             6.8024 : (0.143, 50.0)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.167, 49.9),
    #             5.6 : (0.167, 50.2),
    #             6.8024 : (0.167, 50.7)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.14, 49.2),
    #             5.6 : (0.14, 49.4),
    #             6.8024 : (0.14, 49.9)
    #         }
    #     elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.149, 49.4),
    #             5.6 : (0.149, 49.6),
    #             6.8024 : (0.149, 50.1)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.106, 48.2),
    #             5.6 : (0.106, 48.4),
    #             6.8024 : (0.106, 48.7)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.129, 48.8),
    #             5.6 : (0.129, 49),
    #             6.8024 : (0.129, 49.4)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.102, 48.1),
    #             5.6 : (0.102, 48.2),
    #             6.8024 : (0.102, 48.5)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.111, 48.2),
    #             5.6 : (0.111, 48.4),
    #             6.8024 : (0.111, 48.7)
    #         }

    if(HBM_stack_height == 8):
        #TODO: Below is for 8-high HBM stack, comment out otherwise. 
        # print("Using 8-high HBM stack calibration.")
        if(system_name == "3D_1GPU"):
            # if((HTC == 7) and (TIM_cond == 5) and (infill_cond == 237)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.183, 50.46),
            #         5.6 : (0.183, 51.11),
            #         6.8024 : (0.183, 52.42)
            #     }
            # elif((HTC == 7) and (TIM_cond == 5) and (infill_cond == 1)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.195, 50.82),
            #         5.6 : (0.195, 51.51),
            #         6.8024 : (0.195, 52.90)
            #     }
            # elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.169, 50.05),
            #         5.6 : (0.169, 50.66),
            #         6.8024 : (0.169, 51.87)
            #     }
            # elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.178, 50.30),
            #         5.6 : (0.178, 50.93),
            #         6.8024 : (0.178, 52.19)
            #     }
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 31.12),
            #         5.6 : (0.188, 31.05),
            #         6.8024 : (0.190, 30.94)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.182, 31.54),
            #         5.6 : (0.183, 31.48),
            #         6.8024 : (0.186, 31.37)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 31.12),
            #         5.6 : (0.188, 31.05),
            #         6.8024 : (0.190, 30.94)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.182, 31.54),
            #         5.6 : (0.183, 31.48),
            #         6.8024 : (0.186, 31.37)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 32.23),
            #         5.6 : (0.175, 32.11),
            #         6.8024 : (0.177, 32.00)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.170, 32.45),
            #         5.6 : (0.171, 32.40),
            #         6.8024 : (0.173, 32.30)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 32.23),
            #         5.6 : (0.175, 32.11),
            #         6.8024 : (0.177, 32.00)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.170, 32.45),
            #         5.6 : (0.171, 32.40),
            #         6.8024 : (0.173, 32.30)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 51.83),
            #         5.6 : (0.184, 52.09),
            #         6.8024 : (0.185, 52.46)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 50.93),
            #         5.6 : (0.184, 51.18),
            #         6.8024 : (0.184, 51.63)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.188, 50.62),
            #         5.6 : (0.188, 50.87),
            #         6.8024 : (0.188, 51.32)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.185, 50.56),
            #         5.6 : (0.184, 50.82),
            #         6.8024 : (0.184, 51.26)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.170, 51.47),
            #         5.6 : (0.171, 51.70),
            #         6.8024 : (0.171, 52.11)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.171, 50.57),
            #         5.6 : (0.171, 50.80),
            #         6.8024 : (0.171, 51.22)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.174, 50.23),
            #         5.6 : (0.174, 50.46),
            #         6.8024 : (0.174, 50.87)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.171, 50.11),
            #         5.6 : (0.171, 50.33),
            #         6.8024 : (0.171, 50.74)
            #     }
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 51.83),
            #         5.6 : (0.185, 52.43),
            #         6.8024 : (0.185, 53.73)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.184, 50.93),
            #         5.6 : (0.184, 51.60),
            #         6.8024 : (0.184, 52.89)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.188, 50.62),
            #         5.6 : (0.188, 51.29),
            #         6.8024 : (0.188, 52.62)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.185, 50.56),
            #         5.6 : (0.184, 51.23),
            #         6.8024 : (0.184, 52.55)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.170, 51.47),
            #         5.6 : (0.171, 52.09),
            #         6.8024 : (0.171, 53.30)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.171, 50.57),
            #         5.6 : (0.171, 51.19),
            #         6.8024 : (0.171, 52.44)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.174, 50.23),
            #         5.6 : (0.174, 50.85),
            #         6.8024 : (0.174, 52.09)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.171, 50.11),
            #         5.6 : (0.171, 50.72),
            #         6.8024 : (0.171, 51.94)
            #     }
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.190, 50.72),
                    5.6 : (0.190, 51.43),
                    6.8024 : (0.191, 52.61)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.187, 50.53),
                    5.6 : (0.187, 51.19),
                    6.8024 : (0.187, 52.53)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.189, 50.57),
                    5.6 : (0.189, 51.23),
                    6.8024 : (0.189, 52.58)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.185, 50.52),
                    5.6 : (0.185, 51.18),
                    6.8024 : (0.185, 52.51)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.176, 50.41),
                    5.6 : (0.176, 51.05),
                    6.8024 : (0.176, 52.30)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.173, 50.18),
                    5.6 : (0.173, 50.80),
                    6.8024 : (0.173, 52.03)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.175, 50.15),
                    5.6 : (0.175, 50.78),
                    6.8024 : (0.175, 52.02)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.172, 50.11),
                    5.6 : (0.172, 50.73),
                    6.8024 : (0.172, 51.95)
                }

        #TODO: Below is for 8-high HBM stack, comment out otherwise. For 2p5D_1GPU.
        if(system_name == "2p5D_1GPU"):
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.173, 31.83),
                    5.6 : (0.175, 31.74),
                    6.8024 : (0.179, 31.55)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.172, 31.89),
                    5.6 : (0.174, 31.80),
                    6.8024 : (0.178, 31.62)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.172, 31.95),
                    5.6 : (0.173, 31.86),
                    6.8024 : (0.177, 31.68)
                }
            if(HTC == 7) and (TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.171, 32.03),
                    5.6 : (0.172, 31.94),
                    6.8024 : (0.176, 31.76)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.161, 32.75),
                    5.6 : (0.163, 32.67),
                    6.8024 : (0.166, 32.50)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.161, 32.70),
                    5.6 : (0.163, 32.61),
                    6.8024 : (0.166, 32.45)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.160, 32.85),
                    5.6 : (0.161, 32.77),
                    6.8024 : (0.165, 32.60)
                }
            if(HTC == 7) and (TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.159, 32.90),
                    5.6 : (0.161, 32.82),
                    6.8024 : (0.164, 32.65)
                }
    # elif(HBM_stack_height == 12):
    #     #TODO: Below is for 12-high HBM stack, comment out otherwise.
    #     if(system_name == "3D_1GPU"): # HTC here is TIM_height # HTC 100 means 10 kW / (m^2 * K) cooling, HTC 10 means 7 kW / (m^2 * K) cooling.
    #         if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.146, 51.2),
    #                 5.6 : (0.146, 51.6),
    #                 6.8024 : (0.146, 52.2)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 1) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.169, 52.1),
    #                 5.6 : (0.169, 52.5),
    #                 6.8024 : (0.169, 53.2)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.142, 51.1),
    #                 5.6 : (0.142, 51.4),
    #                 6.8024 : (0.142, 52)
    #             }
    #         elif((HTC == 10) and (TIM_cond == 10) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.151, 51.3),
    #                 5.6 : (0.151, 51.7),
    #                 6.8024 : (0.151, 52.3)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.106, 48.2),
    #                 5.6 : (0.106, 48.4),
    #                 6.8024 : (0.106, 48.7)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.129, 48.8),
    #                 5.6 : (0.129, 49),
    #                 6.8024 : (0.129, 49.4)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.102, 48.1),
    #                 5.6 : (0.102, 48.2),
    #                 6.8024 : (0.102, 48.5)
    #             }
    #         elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
    #             temperature_dict["3D_1GPU"] = {
    #                 5.0 : (0.111, 48.2),
    #                 5.6 : (0.111, 48.4),
    #                 6.8024 : (0.111, 48.7)
    #             }
    elif(HBM_stack_height == 16):
        #TODO: Below is for 16-high HBM stack, comment out otherwise.
        if(system_name == "3D_1GPU"):
            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.218, 56.93),
            #         5.6 : (0.218, 57.42),
            #         6.8024 : (0.218, 58.31)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.216, 56.37),
            #         5.6 : (0.216, 56.88),
            #         6.8024 : (0.216, 57.83)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.195, 55.15),
            #         5.6 : (0.195, 55.60),
            #         6.8024 : (0.195, 56.42)
            #     }

            # if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.187, 55.08),
            #         5.6 : (0.187, 55.52),
            #         6.8024 : (0.187, 56.32)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.198, 55.76),
            #         5.6 : (0.198, 56.22),
            #         6.8024 : (0.197, 57.12)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.196, 55.36),
            #         5.6 : (0.196, 55.82),
            #         6.8024 : (0.197, 56.56)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.180, 54.33),
            #         5.6 : (0.180, 54.75),
            #         6.8024 : (0.180, 55.50)
            #     }

            # if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
            #     temperature_dict["3D_1GPU"] = {
            #         5.0 : (0.173, 54.26),
            #         5.6 : (0.173, 54.67),
            #         6.8024 : (0.173, 55.37)
            #     }
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.192, 55.80),
                    5.6 : (0.192, 56.24),
                    6.8024 : (0.192, 57.05)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.184, 55.41),
                    5.6 : (0.184, 55.91),
                    6.8024 : (0.184, 56.78)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.191, 54.99),
                    5.6 : (0.191, 55.45),
                    6.8024 : (0.191, 56.25)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.185, 54.89),
                    5.6 : (0.185, 55.32),
                    6.8024 : (0.185, 56.11)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.179, 54.62),
                    5.6 : (0.179, 55.03),
                    6.8024 : (0.179, 55.76)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.171, 54.67),
                    5.6 : (0.171, 55.12),
                    6.8024 : (0.171, 55.93)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.177, 54.29),
                    5.6 : (0.177, 54.70),
                    6.8024 : (0.177, 55.46)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237) and (dummy_Si == True)):
                temperature_dict["3D_1GPU"] = {
                    5.0 : (0.172, 54.19),
                    5.6 : (0.172, 54.59),
                    6.8024 : (0.172, 55.32)
                }

        #     if((HTC == 7) and (TIM_cond == 5) and (infill_cond == 237)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.183, 54.73),
        #             5.6 : (0.183, 55.17),
        #             6.8024 : (0.183, 55.95)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 5) and (infill_cond == 1)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.195, 55.26),
        #             5.6 : (0.195, 55.73),
        #             6.8024 : (0.195, 56.55)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.169, 54.03),
        #             5.6 : (0.169, 54.43),
        #             6.8024 : (0.169, 55.16)
        #         }
        #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1)):
        #         temperature_dict["3D_1GPU"] = {
        #             5.0 : (0.178, 54.32),
        #             5.6 : (0.178, 54.74),
        #             6.8024 : (0.178, 55.49)
        #         }

        #TODO: Below is for 16-high HBM stack, comment out otherwise. For 2p5D_1GPU.
        if(system_name == "2p5D_1GPU"):
            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.187, 31.12),
                    5.6 : (0.188, 31.05),
                    6.8024 : (0.190, 30.94)
                }

            if((TIM_cond == 5) and (infill_cond == 1) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.182, 31.54),
                    5.6 : (0.183, 31.48),
                    6.8024 : (0.186, 31.37)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.187, 31.12),
                    5.6 : (0.188, 31.05),
                    6.8024 : (0.190, 30.94)
                }

            if((TIM_cond == 5) and (infill_cond == 237) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.182, 31.54),
                    5.6 : (0.183, 31.48),
                    6.8024 : (0.186, 31.37)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.173, 32.23),
                    5.6 : (0.175, 32.11),
                    6.8024 : (0.177, 32.00)
                }

            if((TIM_cond == 10) and (infill_cond == 1) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.170, 32.45),
                    5.6 : (0.171, 32.40),
                    6.8024 : (0.173, 32.30)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 1)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.173, 32.23),
                    5.6 : (0.175, 32.11),
                    6.8024 : (0.177, 32.00)
                }

            if((TIM_cond == 10) and (infill_cond == 237) and (underfill_cond == 237)):
                temperature_dict["2p5D_1GPU"] = {
                    5.0 : (0.170, 32.45),
                    5.6 : (0.171, 32.40),
                    6.8024 : (0.173, 32.30)
                }    

    

    # if(system_name == "3D_1GPU"): 
    #     if((HTC == 7) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.167, 50.05),
    #             5.6 : (0.167, 50.65),
    #             6.8024 : (0.167, 51.85)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.173, 50.2),
    #             5.6 : (0.173, 50.82),
    #             6.8024 : (0.173, 52.05)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.155, 49.63),
    #             5.6 : (0.155, 50.19),
    #             6.8024 : (0.155, 51.3)
    #         }
    #     elif((HTC == 7) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.158, 49.66),
    #             5.6 : (0.158, 50.26),
    #             6.8024 : (0.158, 51.35)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.106, 48.2),
    #             5.6 : (0.106, 48.4),
    #             6.8024 : (0.106, 48.7)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 1) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.129, 48.8),
    #             5.6 : (0.129, 49),
    #             6.8024 : (0.129, 49.4)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 237)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.102, 48.1),
    #             5.6 : (0.102, 48.2),
    #             6.8024 : (0.102, 48.5)
    #         }
    #     elif((HTC == 100) and (TIM_cond == 10) and (infill_cond == 1)):
    #         temperature_dict["3D_1GPU"] = {
    #             5.0 : (0.111, 48.2),
    #             5.6 : (0.111, 48.4),
    #             6.8024 : (0.111, 48.7)
    #         }

    

    temperature_dict["3D_waferscale"] = {
        5.0 : (0.138, 49.2),
        5.6 : (0.138, 49.7),
        6.8024 : (0.138, 50.7)
    } #TODO: Uncomment 121 to 125 and comment 126 to 130.
    # temperature_dict["3D_waferscale"] = {
    #     5.0 : (0.1288, 48.864),
    #     5.6 : (0.1288, 49.334),
    #     6.8024 : (0.1288, 50.328)
    # }
    if((HTC == 10) and (TIM_cond == 1) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.138, 49.2),
            5.6 : (0.138, 49.7),
            6.8024 : (0.138, 50.7)
        }
    if((HTC == 20) and (TIM_cond == 1) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.072, 47.2),
            5.6 : (0.072, 47.4),
            6.8024 : (0.072, 47.9)
        }
    if((TIM_cond == 10) and (HTC == 10) and (infill_cond == 237)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.1202, 48.596),
            5.6 : (0.1204, 48.972),
            6.8024 : (0.1202, 49.896)
        }
    # if((TIM_cond == 100) and (HTC == 10) and (infill_cond == 237)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.1196, 48.578),
    #         5.6 : (0.1196, 49.008),
    #         6.8024 : (0.1196, 49.868)
    #     }
    # if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.1526, 49.572),
    #         5.6 : (0.1526, 50.058),
    #         6.8024 : (0.1526, 51.138)
    #     }
    # if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
    #     temperature_dict["3D_waferscale"] = {
    #         5.0 : (0.1526, 49.572),
    #         5.6 : (0.1526, 50.058),
    #         6.8024 : (0.1526, 51.138)
    #     }
    if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 10)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.161, 49.81),
            5.6 : (0.161, 50.262),
            6.8024 : (0.161, 51.476)
        }
    if((infill_cond == 1) and (TIM_cond == 10) and (HTC == 10)):
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.145, 49.15),
            5.6 : (0.145, 49.66),
            6.8024 : (0.145, 50.64)
        }
    if((infill_cond == 1) and (TIM_cond == 1) and (HTC == 20)):
        # print("I am here.")
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.102, 47.805),
            5.6 : (0.102, 48.156),
            6.8024 : (0.102, 48.862)
        }
    if((infill_cond == 237) and (TIM_cond == 10) and (HTC == 20)):
        # print("I am here.")
        temperature_dict["3D_waferscale"] = {
            5.0 : (0.073, 47.525),
            5.6 : (0.073, 47.797),
            6.8024 : (0.073, 48.139)
        }
    # Below is for 20 kW / (m^2 * K) cooling.
# Below is for 10 kW / (m^2 * K) cooling and TIM of 10 W / (m K).

    return temperature_dict.get(system_name, {}).get(HBM_power, ())

def predict_temperature(system_name = "2p5D_1GPU", GPU_power = 540.0, HBM_power = 5.0):
    if(system_name == "3D_waferscale"):
        a = 0.065
        b = 0.813
        c = 45.0
        d = 0.064
        e = 0.822
        f = 45.0
        return a * GPU_power + b * HBM_power + c, d * GPU_power + e * HBM_power + f
    else:
        raise NotImplementedError(f"System {system_name} is not defined for temperature prediction.")

def step(system_name = "2p5D_1GPU", GPU_power = 270.0, HBM_power = 5.0, HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False):
    slope, intercept = calibrate_HBM(system_name = system_name, HBM_power = HBM_power, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)
    HBM_peak_temperature = slope * GPU_power + intercept
    slope, intercept = calibrate_GPU(system_name = system_name, HBM_power = HBM_power, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si)
    GPU_peak_temperature = slope * GPU_power + intercept
    # GPU_peak_temperature, HBM_peak_temperature = predict_temperature(system_name = system_name, GPU_power = GPU_power, HBM_power = HBM_power) #TODO: Only used for 20 kW / (m^2 * K). Comment for 10 kW / (m^2 * K) cooling.
    return GPU_peak_temperature, HBM_peak_temperature

def iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 1, infill_cond = 237, underfill_cond = 1, HBM_stack_height = 8, dummy_Si = False):
    HBM_bandwidth_reference = 7944 # 1986 # GB/s # 1986 for 2.5D, 7944 for 3D
    GPU_safe_temperature = 95 # dedeepyo : 29-Jul-25
    HBM_size = 80 # GB

    # if system_name == "2p5D_1GPU" or system_name == "2p5D_waferscale":
    #     HBM_bandwidth_reference = 1986
    #     file_name = "testing_thermal_A100_2p5D.yaml" # testing_thermal_A100_2p5D.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name.
        # file_name = "testing_thermal_A100_1GPU.yaml"
    if system_name == "3D_waferscale":
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100.yaml" # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. # testing_thermal_A100_1GPU.yaml for 1 GPU.
        # file_name = "testing_thermal_A100_1GPU.yaml"

    if(system_name == "2p5D_1GPU"):
        HBM_bandwidth_reference = 3972 if HBM_stack_height == 16 else 1986 if HBM_stack_height == 8 else 0 # 1986, 3972
        HBM_size = 80 if HBM_stack_height == 8 else 160 if HBM_stack_height == 16 else 0 # 80, 160 GB
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"

    if(system_name == "3D_1GPU"):
        HBM_bandwidth_reference = 7944 if HBM_stack_height == 8 else 15888 if HBM_stack_height == 16 else 0 # 15888, 7944 #TODO: Update for 8-high vs 16-high.
        HBM_size = 80 if HBM_stack_height == 8 else 160 if HBM_stack_height == 16 else 0 # 80, 160 GB
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
        # HBM_bandwidth_reference = 11916 # 2 cases, BW 7944 or 11916. #TODO: Only if 12-high HBM.
        # file_name = "testing_thermal_A100_3D_1GPU_ECTC_12stack.yaml" #TODO: Only if 12-high HBM.

    GPU_power = 370.0 # 270.0 # W # GPU_power is actually GPU_averaged_power, not peak power.
    HBM_power = 5.0 # W # For 12-high HBM stack, the thermal simulation is fed the correct power but it is marked as 5, 5.6, 6.8024 here for ease.
    GPU_FLOPs_power = GPU_power

    GPU_power_list = []
    HBM_power_list = []
    GPU_power_list.append(GPU_power)
    HBM_power_list.append(HBM_power)

    results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si) # 237 is the default value for infill_cond.
    GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
    
    GPU_peak_temperature_list = [GPU_peak_temperature]
    HBM_peak_temperature_list = [HBM_peak_temperature]
    GPU_time_frac_idle_list = []
    
    current_GPU_peak_temperature = GPU_peak_temperature
    current_HBM_peak_temperature = HBM_peak_temperature
    
    old_GPU_peak_temperature = -10.00 # 0
    old_HBM_peak_temperature = -10.00 # 0
    old_GPU_min_peak_temperature = -10.00 # 0
    old_HBM_min_peak_temperature = -10.00 # 0

    GPU_count_sqrt = 1 # 7 #TODO: Update everytime.
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    # run_file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    # with open(run_file_path, "r") as f:
    #     content = f.read()

    # content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    # content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    # new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    # with open(run_file_path, "w") as f:
    #     f.write(new_content)

    runtimes = []
    # file_path = "÷/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    with open(file_path, "r") as f:
        lines = f.readlines()

    parts = lines[23].split("size:")
    lines[23] = f"{parts[0]}size: {HBM_size} GB\n" # HBM size
    # print(f"lines[92]: {lines[92].rstrip()}")

    old_old_GPU_peak_temperature = -20.00
    old_old_HBM_peak_temperature = -20.00

    nominal_frequency = 1.41e9 # 2.82e9
    GPU_FLOPs_power = GPU_power
    i = 0
    reti = (-1)
    HBM_bandwidth = HBM_bandwidth_reference
    while((abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 0.1) or (current_GPU_peak_temperature > GPU_safe_temperature)):
        nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth = GPU_FLOPs_throttled(GPU_peak_temperature = current_GPU_peak_temperature, GPU_safe_temperature = GPU_safe_temperature, GPU_peak_power = GPU_FLOPs_power, GPU_average_power = GPU_power) # 80C / 95C is the safe temperature for the GPU.
        if(i == 0):
            nominal_frequency = 1.41e9 # 2.82e9
            GPU_FLOPs_power = 370.0
        HBM_bandwidth, HBM_latency, HBM_power_Watt = HBM_throttled_performance(bandwidth = HBM_bandwidth_reference, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth = 7944 for 3D, 1986 for 2.5D
        # HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = HBM_bandwidth_reference, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        nominal_frequency /= 1e9 # Convert to GHz
        HBM_latency *= 1e9
        # print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [9, 24, 32]:
            if "operating_frequency:" in lines[idx]:
                # print(lines[idx].rstrip())
                # tech params: core:
                parts = lines[idx].split("operating_frequency:")
                lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
            elif "bandwidth:" in lines[idx]:
                # print(f"HBM_bandwidth: {lines[idx].rstrip()}")
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
            elif "latency:" in lines[idx]:
                # HBM latency
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        # print(lines[33])
        # print(lines[78])
        if "bandwidth:" in lines[43]:
            # print(f"l2_bandwidth: {lines[52].rstrip()}")
            parts = lines[43].split("bandwidth:")
            lines[43] = f"{parts[0]}bandwidth: {math.ceil(l2_bandwidth)} GB\n"
        if "bandwidth:" in lines[55]:
            # print(f"l1_bandwidth: {lines[65].rstrip()}")
            parts = lines[55].split("bandwidth:")
            lines[55] = f"{parts[0]}bandwidth: {math.ceil(l1_bandwidth)} GB\n"
        if "bandwidth:" in lines[67]:
            # print(f"register_bandwidth: {lines[78].rstrip()}")
            parts = lines[67].split("bandwidth:")
            lines[67] = f"{parts[0]}bandwidth: {math.ceil(register_bandwidth)} GB\n"
            # print(lines[78])

        with open(file_path, "w") as f:
            f.writelines(lines)

        # with open(file_path, "r") as f:
        #     lines = f.readlines()
        # print(f"{lines[21].rstrip()} and {lines[33].rstrip()} and {lines[40].rstrip()}")

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        scripts_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts"
        base_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow"
        buildRun_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh"

        # try:
        #     # print("Starting DeepFlow run...")
        #     deepflow_result = subprocess.run([buildRun_path], cwd = scripts_dir, capture_output = True, text = True) # , env = os.environ.copy())
        #     # print(f"DeepFlow run completed with return code {deepflow_result.returncode}")
        #     if deepflow_result.returncode == 0:
        #         a = deepflow_result.stdout.split()
        #         runtimes.append(float(a[0]))
        #         GPU_time_frac_idle = float(a[1])
        #         GPU_time_frac_idle_list.append(GPU_time_frac_idle)
        #     else:
        #         print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #         # print(deepflow_result.stderr)
        #         return None, None, None, None
        # except subprocess.TimeoutExpired:
        #     return None, None, None, None
        # except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        #     return None, None, None, None
        # except Exception as e:
        #     # print("Error: File found and not timed out, still failed {}".format(e))
        #     return None, None, None, None
        #     # print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #     # print(deepflow_result.stderr)
        # # DeepFlow ran.

        # print("Starting DeepFlow run...")
        # suppress prints for the next line          
        target = "LLM_thermal.yaml"
        # target = "LLM_thermal.yaml"
        if target == "GEMM_thermal.yaml":
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_GEMM(mode="GEMM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        else:    
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_LLM(mode="LLM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        runtimes.append(float(runtime))

        num_layers = 32 #llama 2 7b
        GPU_time_frac_idle = GPU_time_frac_idle * num_layers
        GPU_time_frac_idle_list.append(GPU_time_frac_idle)

        # print(f"operating_frequency = {nominal_frequency:.2f} GHz")
        print(f"Iteration {i}: Runtime = {runtime:.2f} s, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")

        GPU_power_throttled = GPU_throttling(GPU_power = GPU_FLOPs_power, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        GPU_power = GPU_power_throttled # power in W
        # print(f"GPU_power throttled to {GPU_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        HBM_power = HBM_power_Watt # power in W
        old_old_GPU_peak_temperature = old_GPU_peak_temperature
        old_old_HBM_peak_temperature = old_HBM_peak_temperature
        old_GPU_peak_temperature = current_GPU_peak_temperature
        old_HBM_peak_temperature = current_HBM_peak_temperature

        GPU_power_list.append(GPU_power)
        HBM_power_list.append(HBM_power)

        # print(f"GPU_power = {GPU_power}, HBM_power = {HBM_power}")
        results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = dummy_Si) # 237 is the default value for infill_cond.
        GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
        
        GPU_peak_temperature_list.append(GPU_peak_temperature)
        HBM_peak_temperature_list.append(HBM_peak_temperature)
        current_GPU_peak_temperature = GPU_peak_temperature
        current_HBM_peak_temperature = HBM_peak_temperature
        
        # print(f"Iteration {i}: GPU_peak_temperature = {current_GPU_peak_temperature:.2f} C, HBM_peak_temperature = {current_HBM_peak_temperature:.2f} C, GPU_power = {GPU_power:.2f} W, HBM_power = {HBM_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        i += 1
        if i > 100: # 101 iterations
            print("Reached maximum iterations. Exiting.") # dedeepyo : 25-Jul-25
            break
        if current_GPU_peak_temperature == old_old_GPU_peak_temperature:
            print("No change in temperatures. Exiting.") # dedeepyo : 25-Jul-25
            if len(runtimes) > 1:
                if runtimes[-1] < runtimes[-2]:
                    reti = -2
            break

    # print(f"Runtimes: {runtimes}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")
    # print(f"GPU Power : {GPU_power_list}")
    # print(f"HBM Power : {HBM_power_list}")
    # print(f"GPU_power: {GPU_power} W")
    # print(runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti])
    return runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti], nominal_frequency, HBM_bandwidth

def calibrate_iterations(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 1, infill_cond = 237, HBM_stack_height = 8):
    HBM_bandwidth_reference = 7944 # 1986 # GB/s # 1986 for 2.5D, 7944 for 3D
    GPU_safe_temperature = 200 # 95 # dedeepyo : 29-Jul-25 # Set to 45C for calibration, 95C for normal run.

    if system_name == "2p5D_1GPU" or system_name == "2p5D_waferscale":
        HBM_bandwidth_reference = 1986
        file_name = "testing_thermal_A100_2p5D.yaml" # testing_thermal_A100_2p5D.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name.
        # file_name = "testing_thermal_A100_1GPU.yaml"
    elif system_name == "3D_waferscale":
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100.yaml" # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. # testing_thermal_A100_1GPU.yaml for 1 GPU.
        # file_name = "testing_thermal_A100_1GPU.yaml"

    if(system_name == "3D_1GPU"):
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
        # HBM_bandwidth_reference = 11916 # 2 cases, BW 7944 or 11916. #TODO: Only if 12-high HBM.
        # file_name = "testing_thermal_A100_3D_1GPU_ECTC_12stack.yaml" #TODO: Only if 12-high HBM.

    GPU_power = 370.0 # 270.0 # W # GPU_power is actually GPU_averaged_power, not peak power.
    HBM_power = 5.0 # W # For 12-high HBM stack, the thermal simulation is fed the correct power but it is marked as 5, 5.6, 6.8024 here for ease.
    GPU_FLOPs_power = GPU_power

    GPU_power_list = []
    HBM_power_list = []
    GPU_power_list.append(GPU_power)
    HBM_power_list.append(HBM_power)

    results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, HBM_stack_height = HBM_stack_height) # 237 is the default value for infill_cond.
    GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
    
    GPU_peak_temperature_list = [GPU_peak_temperature]
    HBM_peak_temperature_list = [HBM_peak_temperature]
    GPU_time_frac_idle_list = []
    
    current_GPU_peak_temperature = GPU_peak_temperature
    current_HBM_peak_temperature = HBM_peak_temperature
    
    old_GPU_peak_temperature = -10.00 # 0
    old_HBM_peak_temperature = -10.00 # 0
    old_GPU_min_peak_temperature = -10.00 # 0
    old_HBM_min_peak_temperature = -10.00 # 0

    GPU_count_sqrt = 1 # 7 #TODO: Update everytime.
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    # run_file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    # with open(run_file_path, "r") as f:
    #     content = f.read()

    # content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    # content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    # new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    # with open(run_file_path, "w") as f:
    #     f.write(new_content)

    # runtimes = []
    # file_path = "÷/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    with open(file_path, "r") as f:
        lines = f.readlines()

    # print(f"lines[92]: {lines[92].rstrip()}")

    old_old_GPU_peak_temperature = -20.00
    old_old_HBM_peak_temperature = -20.00

    nominal_frequency = 1.41e9 # 2.82e9
    GPU_FLOPs_power = GPU_power
    i = 0
    reti = (-1)
    runtimes = {}
    GPU_time_frac_idle_dict = {}

    while(GPU_FLOPs_power > 42): # While GPU_FLOPs_power is greater than idle power of 42W.
    # while((abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 0.1) or (current_GPU_peak_temperature > GPU_safe_temperature)):
        nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth = GPU_FLOPs_throttled(GPU_peak_temperature = current_GPU_peak_temperature, GPU_safe_temperature = GPU_safe_temperature, GPU_peak_power = GPU_FLOPs_power, GPU_average_power = GPU_power) # 80C / 95C is the safe temperature for the GPU.
        if(i == 0):
            nominal_frequency = 1.41e9 # 2.82e9
            GPU_FLOPs_power = 370.0
        HBM_bandwidth, HBM_latency, HBM_power_Watt = HBM_throttled_performance(bandwidth = HBM_bandwidth_reference, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth = 7944 for 3D, 1986 for 2.5D
        # HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = HBM_bandwidth_reference, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        nominal_frequency /= 1e9 # Convert to GHz
        HBM_latency *= 1e9
        # print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [9, 24, 32]:
            if "operating_frequency:" in lines[idx]:
                # print(lines[idx].rstrip())
                # tech params: core:
                parts = lines[idx].split("operating_frequency:")
                lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
            elif "bandwidth:" in lines[idx]:
                # print(f"HBM_bandwidth: {lines[idx].rstrip()}")
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
            elif "latency:" in lines[idx]:
                # HB latency
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        # print(lines[33])
        # print(lines[78])
        if "bandwidth:" in lines[43]:
            # print(f"l2_bandwidth: {lines[52].rstrip()}")
            parts = lines[43].split("bandwidth:")
            lines[43] = f"{parts[0]}bandwidth: {math.ceil(l2_bandwidth)} GB\n"
        if "bandwidth:" in lines[55]:
            # print(f"l1_bandwidth: {lines[65].rstrip()}")
            parts = lines[55].split("bandwidth:")
            lines[55] = f"{parts[0]}bandwidth: {math.ceil(l1_bandwidth)} GB\n"
        if "bandwidth:" in lines[67]:
            # print(f"register_bandwidth: {lines[78].rstrip()}")
            parts = lines[67].split("bandwidth:")
            lines[67] = f"{parts[0]}bandwidth: {math.ceil(register_bandwidth)} GB\n"
            # print(lines[78])

        with open(file_path, "w") as f:
            f.writelines(lines)

        # with open(file_path, "r") as f:
        #     lines = f.readlines()
        # print(f"{lines[21].rstrip()} and {lines[33].rstrip()} and {lines[40].rstrip()}")

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        scripts_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts"
        base_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow"
        buildRun_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh"

        # try:
        #     # print("Starting DeepFlow run...")
        #     deepflow_result = subprocess.run([buildRun_path], cwd = scripts_dir, capture_output = True, text = True) # , env = os.environ.copy())
        #     # print(f"DeepFlow run completed with return code {deepflow_result.returncode}")
        #     if deepflow_result.returncode == 0:
        #         a = deepflow_result.stdout.split()
        #         runtimes.append(float(a[0]))
        #         GPU_time_frac_idle = float(a[1])
        #         GPU_time_frac_idle_list.append(GPU_time_frac_idle)
        #     else:
        #         print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #         # print(deepflow_result.stderr)
        #         return None, None, None, None
        # except subprocess.TimeoutExpired:
        #     return None, None, None, None
        # except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        #     return None, None, None, None
        # except Exception as e:
        #     # print("Error: File found and not timed out, still failed {}".format(e))
        #     return None, None, None, None
        #     # print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #     # print(deepflow_result.stderr)
        # # DeepFlow ran.

        from DeepFlow_llm_dev.run_perf import run_LLM, run_GEMM
        # print("Starting DeepFlow run...")
        # suppress prints for the next line
        import contextlib    
        target = "LLM_thermal.yaml"
        # target = "LLM_thermal.yaml"
        if target == "GEMM_thermal.yaml":
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_GEMM(mode="GEMM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        else:    
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_LLM(mode="LLM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        runtimes.append(float(runtime))

        num_layers = 32 #llama 2 7b
        GPU_time_frac_idle = GPU_time_frac_idle * num_layers
        GPU_time_frac_idle_list.append(GPU_time_frac_idle)

        # print(f"Iteration {i}: Runtime = {runtime:.2f} s, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")

        # GPU_power_throttled = GPU_throttling(GPU_power = GPU_FLOPs_power, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        # GPU_power = GPU_power_throttled # power in W
        # # print(f"GPU_power throttled to {GPU_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        # HBM_power = HBM_power_Watt # power in W
        # old_old_GPU_peak_temperature = old_GPU_peak_temperature
        # old_old_HBM_peak_temperature = old_HBM_peak_temperature
        # old_GPU_peak_temperature = current_GPU_peak_temperature
        # old_HBM_peak_temperature = current_HBM_peak_temperature

        # GPU_power_list.append(GPU_power)
        # HBM_power_list.append(HBM_power)

        # # print(f"GPU_power = {GPU_power}, HBM_power = {HBM_power}")
        # results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, HBM_stack_height = HBM_stack_height) # 237 is the default value for infill_cond.
        # GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
        
        # GPU_peak_temperature_list.append(GPU_peak_temperature)
        # HBM_peak_temperature_list.append(HBM_peak_temperature)
        # current_GPU_peak_temperature = GPU_peak_temperature
        # current_HBM_peak_temperature = HBM_peak_temperature
        
        # print(f"Iteration {i}: GPU_peak_temperature = {current_GPU_peak_temperature:.2f} C, HBM_peak_temperature = {current_HBM_peak_temperature:.2f} C, GPU_power = {GPU_power:.2f} W, HBM_power = {HBM_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        # i += 1
        # if i > 100: # 101 iterations
        #     print("Reached maximum iterations. Exiting.") # dedeepyo : 25-Jul-25
        #     break
        # if current_GPU_peak_temperature == old_old_GPU_peak_temperature:
        #     print("No change in temperatures. Exiting.") # dedeepyo : 25-Jul-25
        #     if len(runtimes) > 1:
        #         if runtimes[-1] < runtimes[-2]:
        #             reti = -2
        #     break

    # print(f"Runtimes: {runtimes}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")
    # print(f"GPU Power : {GPU_power_list}")
    # print(f"HBM Power : {HBM_power_list}")
    # print(f"GPU_power: {GPU_power} W")
    # print(runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti])
    return runtimes, GPU_time_frac_idle_list
    # return runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti]

def iterations_lookup(system_name = "2p5D_1GPU", HTC = 10, TIM_cond = 1, infill_cond = 237, HBM_stack_height = 8):
    HBM_bandwidth_reference = 7944 # 1986 # GB/s # 1986 for 2.5D, 7944 for 3D
    GPU_safe_temperature = 95 # dedeepyo : 29-Jul-25

    if system_name == "2p5D_1GPU" or system_name == "2p5D_waferscale":
        HBM_bandwidth_reference = 1986
        file_name = "testing_thermal_A100_2p5D.yaml" # testing_thermal_A100_2p5D.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name.
        # file_name = "testing_thermal_A100_1GPU.yaml"
    elif system_name == "3D_waferscale":
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100.yaml" # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. # testing_thermal_A100_1GPU.yaml for 1 GPU.
        # file_name = "testing_thermal_A100_1GPU.yaml"

    if(system_name == "3D_1GPU"):
        HBM_bandwidth_reference = 7944
        file_name = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
        # HBM_bandwidth_reference = 11916 # 2 cases, BW 7944 or 11916. #TODO: Only if 12-high HBM.
        # file_name = "testing_thermal_A100_3D_1GPU_ECTC_12stack.yaml" #TODO: Only if 12-high HBM.

    GPU_power = 370.0 # 270.0 # W # GPU_power is actually GPU_averaged_power, not peak power.
    HBM_power = 5.0 # W # For 12-high HBM stack, the thermal simulation is fed the correct power but it is marked as 5, 5.6, 6.8024 here for ease.
    GPU_FLOPs_power = GPU_power

    GPU_power_list = []
    HBM_power_list = []
    GPU_power_list.append(GPU_power)
    HBM_power_list.append(HBM_power)

    results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, HBM_stack_height = HBM_stack_height) # 237 is the default value for infill_cond.
    GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
    
    GPU_peak_temperature_list = [GPU_peak_temperature]
    HBM_peak_temperature_list = [HBM_peak_temperature]
    GPU_time_frac_idle_list = []
    
    current_GPU_peak_temperature = GPU_peak_temperature
    current_HBM_peak_temperature = HBM_peak_temperature
    
    old_GPU_peak_temperature = -10.00 # 0
    old_HBM_peak_temperature = -10.00 # 0
    old_GPU_min_peak_temperature = -10.00 # 0
    old_HBM_min_peak_temperature = -10.00 # 0

    GPU_count_sqrt = 1 # 7 #TODO: Update everytime.
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    # run_file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    # with open(run_file_path, "r") as f:
    #     content = f.read()

    # content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    # content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    # new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    # with open(run_file_path, "w") as f:
    #     f.write(new_content)

    runtimes = []
    # file_path = "÷/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/" + file_name # testing_thermal_A100_2p5D.yaml # testing_thermal_A100.yaml # dedeepyo : 10-Jul-25 : Update everytime we change system_name. 
    with open(file_path, "r") as f:
        lines = f.readlines()

    # print(f"lines[92]: {lines[92].rstrip()}")

    old_old_GPU_peak_temperature = -20.00
    old_old_HBM_peak_temperature = -20.00

    nominal_frequency = 1.41e9 # 2.82e9
    GPU_FLOPs_power = GPU_power
    i = 0
    reti = (-1)
    while((abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 0.1) or (current_GPU_peak_temperature > GPU_safe_temperature)):
        nominal_frequency, GPU_FLOPs_power, register_bandwidth, l1_bandwidth, l2_bandwidth = GPU_FLOPs_throttled(GPU_peak_temperature = current_GPU_peak_temperature, GPU_safe_temperature = GPU_safe_temperature, GPU_peak_power = GPU_FLOPs_power, GPU_average_power = GPU_power) # 80C / 95C is the safe temperature for the GPU.
        if(i == 0):
            nominal_frequency = 1.41e9 # 2.82e9
            GPU_FLOPs_power = 370.0
        HBM_bandwidth, HBM_latency, HBM_power_Watt = HBM_throttled_performance(bandwidth = HBM_bandwidth_reference, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth = 7944 for 3D, 1986 for 2.5D
        # HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = HBM_bandwidth_reference, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        nominal_frequency /= 1e9 # Convert to GHz
        HBM_latency *= 1e9
        # print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [9, 24, 32]:
            if "operating_frequency:" in lines[idx]:
                # print(lines[idx].rstrip())
                # tech params: core:
                parts = lines[idx].split("operating_frequency:")
                lines[idx] = f"{parts[0]}operating_frequency: {nominal_frequency:.2f}e9\n"
            elif "bandwidth:" in lines[idx]:
                # print(f"HBM_bandwidth: {lines[idx].rstrip()}")
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {math.ceil(HBM_bandwidth)} GB\n"
            elif "latency:" in lines[idx]:
                # HB latency
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        # print(lines[33])
        # print(lines[78])
        if "bandwidth:" in lines[43]:
            # print(f"l2_bandwidth: {lines[52].rstrip()}")
            parts = lines[43].split("bandwidth:")
            lines[43] = f"{parts[0]}bandwidth: {math.ceil(l2_bandwidth)} GB\n"
        if "bandwidth:" in lines[55]:
            # print(f"l1_bandwidth: {lines[65].rstrip()}")
            parts = lines[55].split("bandwidth:")
            lines[55] = f"{parts[0]}bandwidth: {math.ceil(l1_bandwidth)} GB\n"
        if "bandwidth:" in lines[67]:
            # print(f"register_bandwidth: {lines[78].rstrip()}")
            parts = lines[67].split("bandwidth:")
            lines[67] = f"{parts[0]}bandwidth: {math.ceil(register_bandwidth)} GB\n"
            # print(lines[78])

        with open(file_path, "w") as f:
            f.writelines(lines)

        # with open(file_path, "r") as f:
        #     lines = f.readlines()
        # print(f"{lines[21].rstrip()} and {lines[33].rstrip()} and {lines[40].rstrip()}")

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        scripts_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts"
        base_dir = "/app/nanocad/projects/deepflow_thermal/DeepFlow"
        buildRun_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh"

        # try:
        #     # print("Starting DeepFlow run...")
        #     deepflow_result = subprocess.run([buildRun_path], cwd = scripts_dir, capture_output = True, text = True) # , env = os.environ.copy())
        #     # print(f"DeepFlow run completed with return code {deepflow_result.returncode}")
        #     if deepflow_result.returncode == 0:
        #         a = deepflow_result.stdout.split()
        #         runtimes.append(float(a[0]))
        #         GPU_time_frac_idle = float(a[1])
        #         GPU_time_frac_idle_list.append(GPU_time_frac_idle)
        #     else:
        #         print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #         # print(deepflow_result.stderr)
        #         return None, None, None, None
        # except subprocess.TimeoutExpired:
        #     return None, None, None, None
        # except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        #     return None, None, None, None
        # except Exception as e:
        #     # print("Error: File found and not timed out, still failed {}".format(e))
        #     return None, None, None, None
        #     # print(f"Error: Command failed with return code {deepflow_result.returncode}")
        #     # print(deepflow_result.stderr)
        # # DeepFlow ran.

        from DeepFlow_llm_dev.run_perf import run_LLM, run_GEMM
        # print("Starting DeepFlow run...")
        # suppress prints for the next line
        import contextlib    
        target = "LLM_thermal.yaml"
        # target = "LLM_thermal.yaml"
        if target == "GEMM_thermal.yaml":
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_GEMM(mode="GEMM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        else:    
            with contextlib.redirect_stdout(None):
                runtime, GPU_time_frac_idle = run_LLM(mode="LLM", exp_hw_config_path=file_path, exp_model_config_path="/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config/"+target, exp_dir="./output")
        runtimes.append(float(runtime))

        num_layers = 32 #llama 2 7b
        GPU_time_frac_idle = GPU_time_frac_idle * num_layers
        GPU_time_frac_idle_list.append(GPU_time_frac_idle)

        print(f"Iteration {i}: Runtime = {runtime:.2f} s, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")

        GPU_power_throttled = GPU_throttling(GPU_power = GPU_FLOPs_power, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        GPU_power = GPU_power_throttled # power in W
        # print(f"GPU_power throttled to {GPU_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        HBM_power = HBM_power_Watt # power in W
        old_old_GPU_peak_temperature = old_GPU_peak_temperature
        old_old_HBM_peak_temperature = old_HBM_peak_temperature
        old_GPU_peak_temperature = current_GPU_peak_temperature
        old_HBM_peak_temperature = current_HBM_peak_temperature

        GPU_power_list.append(GPU_power)
        HBM_power_list.append(HBM_power)

        # print(f"GPU_power = {GPU_power}, HBM_power = {HBM_power}")
        results = step(GPU_power = GPU_power, HBM_power = HBM_power, system_name = system_name, HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond, HBM_stack_height = HBM_stack_height) # 237 is the default value for infill_cond.
        GPU_peak_temperature, HBM_peak_temperature = results # 0.00, 0.00 # 
        
        GPU_peak_temperature_list.append(GPU_peak_temperature)
        HBM_peak_temperature_list.append(HBM_peak_temperature)
        current_GPU_peak_temperature = GPU_peak_temperature
        current_HBM_peak_temperature = HBM_peak_temperature
        
        # print(f"Iteration {i}: GPU_peak_temperature = {current_GPU_peak_temperature:.2f} C, HBM_peak_temperature = {current_HBM_peak_temperature:.2f} C, GPU_power = {GPU_power:.2f} W, HBM_power = {HBM_power:.2f} W, GPU_time_frac_idle = {GPU_time_frac_idle:.2f}")
        i += 1
        if i > 100: # 101 iterations
            print("Reached maximum iterations. Exiting.") # dedeepyo : 25-Jul-25
            break
        if current_GPU_peak_temperature == old_old_GPU_peak_temperature:
            print("No change in temperatures. Exiting.") # dedeepyo : 25-Jul-25
            if len(runtimes) > 1:
                if runtimes[-1] < runtimes[-2]:
                    reti = -2
            break

    # print(f"Runtimes: {runtimes}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")
    # print(f"GPU Power : {GPU_power_list}")
    # print(f"HBM Power : {HBM_power_list}")
    # print(f"GPU_power: {GPU_power} W")
    # print(runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti])
    return runtimes[reti], GPU_peak_temperature_list[reti], HBM_peak_temperature_list[reti], GPU_time_frac_idle_list[reti]

def GPU_throttling(GPU_power = 275, GPU_time_frac_idle = 0.2, GPU_idle_power = 47):
  GPU_power_throttled = GPU_power * (1 - GPU_time_frac_idle) + GPU_idle_power * GPU_time_frac_idle
  return GPU_power_throttled

def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74): # Trip points 85 C and 95 C or 75 C and 85 C
    HBM_power_Watt = 5.0 # W
    trip1 = 85 # 75, 85
    trip2 = 95 # 85, 95
    if(((HBM_peak_temperature > (trip1 - 1))) and (HBM_peak_temperature < (trip2 + 1))):
        if((trip1 == 75) and (trip2 == 85)):
            bandwidth *= (2.28 - 0.018 * HBM_peak_temperature) # Linear interpolation between (75, 0.912) and (85, 0.732)
        elif((trip1 == 85) and (trip2 == 95)):
            bandwidth *= (2.442 - 0.018 * HBM_peak_temperature) # Linear interpolation between (85, 0.912) and (95, 0.732)
    elif(HBM_peak_temperature >= (trip2 + 1)):
        bandwidth *= 0.732 # At 95C and above, bandwidth is 73.2% of nominal
    if((HBM_peak_temperature > trip2)):
        # bandwidth *= 0.732
        latency *= 1.714
        HBM_power_Watt = 6.8024 # W
    elif((HBM_peak_temperature > trip1) and (HBM_peak_temperature <= trip2)):
        # bandwidth *= 0.912
        latency *= 1.238
        HBM_power_Watt = 5.6 # W
    
    return int(bandwidth), latency, HBM_power_Watt

# def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74):
#     HBM_power_Watt = 5.0 # W
#     if((HBM_peak_temperature > 85)):
#         bandwidth *= 0.732
#         latency *= 1.714
#         HBM_power_Watt = 6.8024 # W
#     elif((HBM_peak_temperature > 75) and (HBM_peak_temperature <= 85)):
#         bandwidth *= 0.912
#         latency *= 1.238
#         HBM_power_Watt = 5.6 # W

#     return bandwidth, latency, HBM_power_Watt

def HBM_throttled_power(bandwidth_throttled, HBM_power, bandwidth_reference = 1986, HBM_peak_temperature = 74):
    refresh_energy = 0.12 * HBM_power
    non_refresh_energy = HBM_power - refresh_energy
    if(bandwidth_throttled < bandwidth_reference):
        non_refresh_energy *= (bandwidth_throttled / bandwidth_reference)
    if(HBM_peak_temperature > 85):
        refresh_energy *= 4.004
    elif(HBM_peak_temperature > 75 and HBM_peak_temperature <= 85):
        refresh_energy *= 2.0
    return refresh_energy + non_refresh_energy

# def main():
#     # run_iter = iterations(system_name = "3D_waferscale") # 3D_1GPU, 3D_waferscale, 2p5D_waferscale, 2p5D_1GPU  # Change system_name as needed
#     # print(run_iter)
#     run_safe_iter = iterations_gui_safe(system_name = "3D_waferscale")
#     print(run_safe_iter)

# def iterations_gui_safe(system_name = "3D_waferscale"):
#     """
#     GUI-safe wrapper for iterations() function that handles all possible errors
#     and provides sensible fallback values for the thermal analysis GUI.
#     """
#     try:
#         # Call the main iterations function
#         result = iterations(system_name = system_name)
#         # print(f"Result from iterations: {result}")
        
#         # Check if result is None (subprocess failed) or invalid
#         # if result is None or (isinstance(result, tuple) and any(x is None for x in result)):
#         #     # print("iterations() returned None values, using fallbacks")
#         #     result = (None, None, None, None)

#         return result
#     except subprocess.SubprocessError as e:
#         # print(f"Subprocess error in iterations_gui_safe: {e}")
#         return None, None, None, None
#     except subprocess.TimeoutExpired as e:
#         # print(f"Timeout error in iterations_gui_safe: {e}")
#         return None, None, None, None
#     except (OSError, FileNotFoundError) as e:
#         # print(f"File system error in iterations_gui_safe: {e}")
#         return None, None, None, None
#     except Exception as e:
#         # print(f"Unexpected error in iterations_gui_safe: {e}")
#         return None, None, None, None

# dedeepyo : 3-Jul-25

# Initialize the Dash app
# app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# # Define the layout
# app.layout = dbc.Container([
#     dbc.Row([
#         dbc.Col([
#             html.H1("Thermal-aware Performance Analysis GUI", className="text-center mb-4"),
#             html.Hr(),
#         ])
#     ]),
    
#     dbc.Row([
#         # Left Column - Configuration
#         dbc.Col([
#             # Configuration Section
#             dbc.Card([
#                 dbc.CardHeader("System Configuration"),
#                 dbc.CardBody([
#                     # System Type
#                     dbc.Row([
#                         dbc.Col([
#                             html.Label("System Type:", className="fw-bold"),
#                             dcc.Dropdown(
#                                 id='system-dropdown',
#                                 options=[
#                                     {'label': '2.5D Waferscale', 'value': '2p5D_waferscale'},
#                                     {'label': '3D Waferscale', 'value': '3D_waferscale'}
#                                 ],
#                                 value='3D_waferscale',
#                                 clearable=False
#                             )
#                         ], width=6),
                        
#                         # ML Model
#                         dbc.Col([
#                             html.Label("ML Model:", className="fw-bold"),
#                             dcc.Dropdown(
#                                 id='model-dropdown',
#                                 options=[
#                                     {'label': 'Llama 3.3 70B', 'value': 'llama_3_3_70b'},
#                                     {'label': 'Llama 3.1 405B', 'value': 'llama_3_1_405b'}
#                                 ],
#                                 value='llama_3_3_70b',
#                                 clearable=False
#                             )
#                         ], width=6)
#                     ], className="mb-3"),
                    
#                     # Parallelism Strategy
#                     dbc.Row([
#                         dbc.Col([
#                             html.Label("Parallelism Strategy:", className="fw-bold"),
#                             dcc.Dropdown(
#                                 id='parallelism-dropdown',
#                                 value='strategy_1',
#                                 clearable=False
#                             )
#                         ], width=6),
                        
#                         # HTC Value
#                         dbc.Col([
#                             html.Label("HTC Value:", className="fw-bold"),
#                             dcc.Dropdown(
#                                 id='htc-dropdown',
#                                 options=[
#                                     {'label': '10 kW/(m²·K)', 'value': '10'},
#                                     {'label': '20 kW/(m²·K)', 'value': '20'}
#                                 ],
#                                 value='10',
#                                 clearable=False
#                             )
#                         ], width=6)
#                     ], className="mb-3"),
                    
#                     # Network Bandwidth
#                     dbc.Row([
#                         dbc.Col([
#                             html.Label("Network Bandwidth:", className="fw-bold"),
#                             dcc.Dropdown(
#                                 id='bandwidth-dropdown',
#                                 options=[
#                                     {'label': '450 GB/s', 'value': '450'},
#                                     {'label': '900 GB/s', 'value': '900'},
#                                     {'label': '1800 GB/s', 'value': '1800'},
#                                     {'label': '3600 GB/s', 'value': '3600'},
#                                     {'label': '7200 GB/s', 'value': '7200'},
#                                     {'label': '14400 GB/s', 'value': '14400'},
#                                     {'label': '28800 GB/s', 'value': '28800'},
#                                     {'label': '57600 GB/s', 'value': '57600'},
#                                     {'label': '115200 GB/s', 'value': '115200'}
#                                 ],
#                                 value='14400',
#                                 clearable=False
#                             )
#                         ], width=12)
#                     ])
#                 ])
#             ], className="mb-4"),
            
#             # Control Buttons
#             dbc.Row([
#                 dbc.Col([
#                     dbc.Button("Run Analysis", id="run-button", color="primary", size="lg", className="me-2"),
#                     dbc.Button("Bandwidth Sweep", id="sweep-button", color="info", size="lg", className="me-2"),
#                     dbc.Button("Dual HTC Sweep", id="dual-htc-sweep-button", color="warning", size="lg", className="me-2"),
#                     dbc.Button("Dual TIM_cond Sweep", id="dual-tim-cond-sweep-button", color="warning", size="lg", className="me-2"),
#                     dbc.Button("Dual Infill_cond Sweep", id="dual-infill-cond-sweep-button", color="warning", size="lg", className="me-2"),
#                     dbc.Button("Stop Analysis", id="stop-button", color="danger", size="lg", disabled=True),
#                 ], className="text-center")
#             ], className="mb-4"),
            
#             # System Cost and Status
#             dbc.Card([
#                 dbc.CardHeader("Analysis Status"),
#                 dbc.CardBody([
#                     dbc.Row([
#                         dbc.Col([
#                             html.H5("System Cost:", className="fw-bold"),
#                             html.H4(id="system-cost", children="Not calculated", className="text-primary")
#                         ], width=6),
                        
#                         dbc.Col([
#                             html.H5("Status:", className="fw-bold"),
#                             html.H4(id="status", children="Ready", className="text-success")
#                         ], width=6)
#                     ], className="mb-3"),
                    
#                     dbc.Progress(id="progress-bar", value=0, className="mb-3"),
                    
#                     html.H6("Output Log:", className="fw-bold"),
#                     html.Div(
#                         id="output-log",
#                         style={
#                             'height': '200px',
#                             'overflow-y': 'scroll',
#                             'border': '1px solid #ddd',
#                             'padding': '10px',
#                             'background-color': '#f8f9fa',
#                             'font-family': 'monospace',
#                             'font-size': '12px'
#                         },
#                         children="Analysis results will appear here..."
#                     )
#                 ])
#             ])
#         ], width=6),
        
#         # Right Column - Results Visualization
#         dbc.Col([
#             # Runtime Plot
#             dbc.Card([
#                 dbc.CardHeader("Runtime Analysis"),
#                 dbc.CardBody([
#                     dcc.Graph(id="runtime-plot", style={'height': '400px'})
#                 ])
#             ], className="mb-4"),
            
#             # Temperature Plots
#             dbc.Card([
#                 dbc.CardHeader("Temperature Analysis"),
#                 dbc.CardBody([
#                     dcc.Graph(id="temperature-plot", style={'height': '400px'})
#                 ])
#             ], className="mb-4"),
            
#             # Results Table
#             dbc.Card([
#                 dbc.CardHeader("Detailed Results"),
#                 dbc.CardBody([
#                     html.Div(id="results-table")
#                 ])
#             ])
#         ], width=6)
#     ])
# ], fluid=True)

# Global variable to track running process
running_process = None

# Global variables to store runtime data
runtime_data = {
    'iterations': [],
    'runtimes': [],
    'temperatures': [],
    'costs': []
}

# Global variables to store bandwidth sweep data
bandwidth_sweep_data = {
    'bandwidths': [],
    'runtimes': [],
    'gpu_temperatures': [],
    'hbm_temperatures': [],
    'idle_fractions': []
}

# Global variables to store dual HTC bandwidth sweep data
dual_htc_sweep_data = {
    'bandwidths': [],
    'htc_10': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    },
    'htc_20': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    }
}

# Global variables to store dual TIM_cond bandwidth sweep data
dual_TIM_cond_sweep_data = {
    'bandwidths': [],
    'TIM_cond_1': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    },
    'TIM_cond_10': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    }
}

# Global variables to store dual infill_cond bandwidth sweep data
dual_infill_cond_sweep_data = {
    'bandwidths': [],
    'infill_cond_237': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    },
    'infill_cond_1': {
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    }
}

def parse_analysis_results(results):
    """Parse results from the thermal analysis and populate runtime_data"""
    global runtime_data
    
    # Reset data
    runtime_data = {
        'iterations': [1],  # Single iteration for now
        'runtimes': [],
        'temperatures': [],
        'costs': []
    }
    
    if results and isinstance(results, tuple) and len(results) >= 3:
        runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
        runtime_data['runtimes'].append(runtime)
        runtime_data['temperatures'].append(gpu_temp)  # Use GPU temperature
        # Could also add HBM temperature if needed
    
    return runtime_data

def parse_runtime_from_output(output_text):
    """Parse runtime data from the analysis output"""
    global runtime_data
    
    # Reset data
    runtime_data = {
        'iterations': [],
        'runtimes': [],
        'temperatures': [],
        'costs': []
    }
    
    lines = output_text.split('\n')
    for line in lines:
        # Look for iteration results in the output
        if 'Iteration' in line and 'Runtime:' in line:
            try:
                # Extract iteration number
                iter_part = line.split('Iteration')[1].split(':')[0].strip()
                iteration = int(iter_part)
                
                # Extract runtime (looking for patterns like "Runtime: X.XX s")
                runtime_part = line.split('Runtime:')[1].split('s')[0].strip()
                runtime = float(runtime_part)
                
                runtime_data['iterations'].append(iteration)
                runtime_data['runtimes'].append(runtime)
                
            except (ValueError, IndexError):
                continue
        
        # Look for temperature data
        elif 'Temperature:' in line or 'Max temp:' in line:
            try:
                if 'Temperature:' in line:
                    temp_part = line.split('Temperature:')[1].split('°C')[0].strip()
                elif 'Max temp:' in line:
                    temp_part = line.split('Max temp:')[1].split('°C')[0].strip()
                else:
                    continue
                    
                temperature = float(temp_part)
                if len(runtime_data['temperatures']) < len(runtime_data['iterations']):
                    runtime_data['temperatures'].append(temperature)
                    
            except (ValueError, IndexError):
                continue
                
        # Look for cost data  
        elif 'Cost:' in line:
            try:
                cost_part = line.split('Cost:')[1].split('$')[0].strip()
                cost = float(cost_part)
                if len(runtime_data['costs']) < len(runtime_data['iterations']):
                    runtime_data['costs'].append(cost)
                    
            except (ValueError, IndexError):
                continue
    
    return runtime_data

def create_runtime_plot():
    """Create runtime vs iteration plot"""
    if not runtime_data['iterations']:
        return go.Figure().add_annotation(
            text="No runtime data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add runtime line
    fig.add_trace(go.Scatter(
        x=runtime_data['iterations'],
        y=runtime_data['runtimes'],
        mode='lines+markers',
        name='Runtime (days)',
        line=dict(color='blue', width=2),
        marker=dict(size=8)
    ))
    
    fig.update_layout(
        title='Runtime vs Iteration',
        xaxis_title='Iteration',
        yaxis_title='Runtime (days)',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_temperature_plot():
    """Create temperature vs iteration plot"""
    if not runtime_data['temperatures']:
        return go.Figure().add_annotation(
            text="No temperature data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add temperature line
    fig.add_trace(go.Scatter(
        x=runtime_data['iterations'][:len(runtime_data['temperatures'])],
        y=runtime_data['temperatures'],
        mode='lines+markers',
        name='Temperature (°C)',
        line=dict(color='red', width=2),
        marker=dict(size=8)
    ))
    
    fig.update_layout(
        title='Temperature vs Iteration',
        xaxis_title='Iteration',
        yaxis_title='Temperature (°C)',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_results_table():
    """Create a table showing detailed results"""
    if not runtime_data['iterations']:
        return html.Div("No data available for table display")
    
    # Create DataFrame
    df_data = {
        'Iteration': runtime_data['iterations'],
        'Runtime (days)': runtime_data['runtimes']
    }
    
    # Add temperature data if available
    if runtime_data['temperatures']:
        temp_data = runtime_data['temperatures'] + [None] * (len(runtime_data['iterations']) - len(runtime_data['temperatures']))
        df_data['Temperature (°C)'] = temp_data[:len(runtime_data['iterations'])]
    
    # Add cost data if available
    if runtime_data['costs']:
        cost_data = runtime_data['costs'] + [None] * (len(runtime_data['iterations']) - len(runtime_data['costs']))
        df_data['Cost ($)'] = cost_data[:len(runtime_data['iterations'])]
    
    df = pd.DataFrame(df_data)
    
    # Create Dash DataTable
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        style_data={'backgroundColor': 'rgb(248, 248, 248)'}
    )

def create_bandwidth_sweep_runtime_plot():
    """Create runtime vs bandwidth plot for sweep analysis"""
    if not bandwidth_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No bandwidth sweep data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add runtime line
    fig.add_trace(go.Scatter(
        x=bandwidth_sweep_data['bandwidths'],
        y=bandwidth_sweep_data['runtimes'],
        mode='lines+markers',
        name='Runtime (days)',
        line=dict(color='blue', width=2),
        marker=dict(size=8)
    ))
    
    fig.update_layout(
        title='Runtime vs Network Bandwidth',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Runtime (days)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_bandwidth_sweep_temperature_plot():
    """Create temperature vs bandwidth plot for sweep analysis"""
    if not bandwidth_sweep_data['gpu_temperatures']:
        return go.Figure().add_annotation(
            text="No bandwidth sweep temperature data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add GPU temperature line
    fig.add_trace(go.Scatter(
        x=bandwidth_sweep_data['bandwidths'],
        y=bandwidth_sweep_data['gpu_temperatures'],
        mode='lines+markers',
        name='GPU Temperature (°C)',
        line=dict(color='red', width=2),
        marker=dict(size=8)
    ))
    
    # Add HBM temperature line if available
    if bandwidth_sweep_data['hbm_temperatures']:
        fig.add_trace(go.Scatter(
            x=bandwidth_sweep_data['bandwidths'],
            y=bandwidth_sweep_data['hbm_temperatures'],
            mode='lines+markers',
            name='HBM Temperature (°C)',
            line=dict(color='orange', width=2),
            marker=dict(size=8)
        ))
    
    fig.update_layout(
        title='Peak Temperature vs Network Bandwidth',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Temperature (°C)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_bandwidth_sweep_table():
    """Create a table showing detailed bandwidth sweep results"""
    if not bandwidth_sweep_data['bandwidths']:
        return html.Div("No bandwidth sweep data available for table display")
    
    # Create DataFrame
    df_data = {
        'Bandwidth (GB/s)': bandwidth_sweep_data['bandwidths'],
        'Runtime (days)': bandwidth_sweep_data['runtimes'],
        'GPU Temp (°C)': bandwidth_sweep_data['gpu_temperatures']
    }
    
    # Add HBM temperature data if available
    if bandwidth_sweep_data['hbm_temperatures']:
        df_data['HBM Temp (°C)'] = bandwidth_sweep_data['hbm_temperatures']
    
    # Add idle fraction data if available
    if bandwidth_sweep_data['idle_fractions']:
        df_data['GPU Idle Fraction'] = bandwidth_sweep_data['idle_fractions']
    
    df = pd.DataFrame(df_data)
    
    # Create Dash DataTable
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        style_data={'backgroundColor': 'rgb(248, 248, 248)'}
    )

def create_dual_htc_runtime_plot():
    """Create runtime vs bandwidth plot for dual HTC analysis"""
    if not dual_htc_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual HTC sweep data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add HTC 10 runtime line
    if dual_htc_sweep_data['htc_10']['runtimes']:
        # Filter out None values
        valid_data_10 = [(bw, rt) for bw, rt in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_10']['runtimes']) if rt is not None]
        if valid_data_10:
            bandwidths_10, runtimes_10 = zip(*valid_data_10)
            fig.add_trace(go.Scatter(
                x=bandwidths_10,
                y=runtimes_10,
                mode='lines+markers',
                name='HTC 10 kW/(m²·K)',
                line=dict(color='blue', width=2),
                marker=dict(size=8)
            ))
    
    # Add HTC 20 runtime line
    if dual_htc_sweep_data['htc_20']['runtimes']:
        # Filter out None values
        valid_data_20 = [(bw, rt) for bw, rt in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_20']['runtimes']) if rt is not None]
        if valid_data_20:
            bandwidths_20, runtimes_20 = zip(*valid_data_20)
            fig.add_trace(go.Scatter(
                x=bandwidths_20,
                y=runtimes_20,
                mode='lines+markers',
                name='HTC 20 kW/(m²·K)',
                line=dict(color='green', width=2),
                marker=dict(size=8)
            ))
    
    fig.update_layout(
        title='Runtime vs Network Bandwidth (Dual HTC Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Runtime (days)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_htc_temperature_plot():
    """Create temperature vs bandwidth plot for dual HTC analysis"""
    if not dual_htc_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual HTC sweep temperature data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add HTC 10 GPU temperature line
    if dual_htc_sweep_data['htc_10']['gpu_temperatures']:
        # Filter out None values
        valid_data_10 = [(bw, temp) for bw, temp in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_10']['gpu_temperatures']) if temp is not None]
        if valid_data_10:
            bandwidths_10, temps_10 = zip(*valid_data_10)
            fig.add_trace(go.Scatter(
                x=bandwidths_10,
                y=temps_10,
                mode='lines+markers',
                name='GPU Temp - HTC 10 kW/(m²·K)',
                line=dict(color='red', width=2),
                marker=dict(size=8)
            ))
    
    # Add HTC 20 GPU temperature line
    if dual_htc_sweep_data['htc_20']['gpu_temperatures']:
        # Filter out None values
        valid_data_20 = [(bw, temp) for bw, temp in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_20']['gpu_temperatures']) if temp is not None]
        if valid_data_20:
            bandwidths_20, temps_20 = zip(*valid_data_20)
            fig.add_trace(go.Scatter(
                x=bandwidths_20,
                y=temps_20,
                mode='lines+markers',
                name='GPU Temp - HTC 20 kW/(m²·K)',
                line=dict(color='darkred', width=2),
                marker=dict(size=8)
            ))
    
    # Add HTC 10 HBM temperature line if available
    if dual_htc_sweep_data['htc_10']['hbm_temperatures']:
        valid_data_10_hbm = [(bw, temp) for bw, temp in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_10']['hbm_temperatures']) if temp is not None]
        if valid_data_10_hbm:
            bandwidths_10_hbm, temps_10_hbm = zip(*valid_data_10_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_10_hbm,
                y=temps_10_hbm,
                mode='lines+markers',
                name='HBM Temp - HTC 10 kW/(m²·K)',
                line=dict(color='orange', width=2, dash='dash'),
                marker=dict(size=6)
            ))
    
    # Add HTC 20 HBM temperature line if available
    if dual_htc_sweep_data['htc_20']['hbm_temperatures']:
        valid_data_20_hbm = [(bw, temp) for bw, temp in zip(dual_htc_sweep_data['bandwidths'], dual_htc_sweep_data['htc_20']['hbm_temperatures']) if temp is not None]
        if valid_data_20_hbm:
            bandwidths_20_hbm, temps_20_hbm = zip(*valid_data_20_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_20_hbm,
                y=temps_20_hbm,
                mode='lines+markers',
                name='HBM Temp - HTC 20 kW/(m²·K)',
                line=dict(color='darkorange', width=2, dash='dash'),
                marker=dict(size=6)
            ))
    
    fig.update_layout(
        title='Peak Temperature vs Network Bandwidth (Dual HTC Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Temperature (°C)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_htc_table():
    """Create a table showing detailed dual HTC bandwidth sweep results"""
    if not dual_htc_sweep_data['bandwidths']:
        return html.Div("No dual HTC sweep data available for table display")
    
    # Create DataFrame with dual HTC results
    df_data = {
        'Bandwidth (GB/s)': dual_htc_sweep_data['bandwidths']
    }
    
    # Add HTC 10 data
    if dual_htc_sweep_data['htc_10']['runtimes']:
        df_data['Runtime HTC 10 (days)'] = dual_htc_sweep_data['htc_10']['runtimes']
    if dual_htc_sweep_data['htc_10']['gpu_temperatures']:
        df_data['GPU Temp HTC 10 (°C)'] = dual_htc_sweep_data['htc_10']['gpu_temperatures']
    if dual_htc_sweep_data['htc_10']['hbm_temperatures']:
        df_data['HBM Temp HTC 10 (°C)'] = dual_htc_sweep_data['htc_10']['hbm_temperatures']
    
    # Add HTC 20 data
    if dual_htc_sweep_data['htc_20']['runtimes']:
        df_data['Runtime HTC 20 (days)'] = dual_htc_sweep_data['htc_20']['runtimes']
    if dual_htc_sweep_data['htc_20']['gpu_temperatures']:
        df_data['GPU Temp HTC 20 (°C)'] = dual_htc_sweep_data['htc_20']['gpu_temperatures']
    if dual_htc_sweep_data['htc_20']['hbm_temperatures']:
        df_data['HBM Temp HTC 20 (°C)'] = dual_htc_sweep_data['htc_20']['hbm_temperatures']
    
    df = pd.DataFrame(df_data)
    
    # Create Dash DataTable
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        style_data={'backgroundColor': 'rgb(248, 248, 248)'}
    )

def create_dual_TIM_cond_runtime_plot():
    """Create runtime vs bandwidth plot for dual TIM_cond analysis"""
    if not dual_TIM_cond_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual TIM_cond sweep data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()

    # Add TIM_cond 1 runtime line
    if dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes']:
        # Filter out None values
        valid_data_1 = [(bw, rt) for bw, rt in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes']) if rt is not None]
        if valid_data_1:
            bandwidths_1, runtimes_1 = zip(*valid_data_1)
            fig.add_trace(go.Scatter(
                x=bandwidths_1,
                y=runtimes_1,
                mode='lines+markers',
                name='TIM_cond 1 W/(m·K)',
                line=dict(color='blue', width=2),
                marker=dict(size=8)
            ))

    # Add TIM_cond_10 runtime line
    if dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes']:
        # Filter out None values
        valid_data_10 = [(bw, rt) for bw, rt in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes']) if rt is not None]
        if valid_data_10:
            bandwidths_10, runtimes_10 = zip(*valid_data_10)
            fig.add_trace(go.Scatter(
                x=bandwidths_10,
                y=runtimes_10,
                mode='lines+markers',
                name='TIM_cond 10 W/(m·K)',
                line=dict(color='green', width=2),
                marker=dict(size=8)
            ))
    
    fig.update_layout(
        title='Runtime vs Network Bandwidth (Dual TIM_cond Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Runtime (days)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_TIM_cond_temperature_plot():
    """Create temperature vs bandwidth plot for dual TIM_cond analysis"""
    if not dual_TIM_cond_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual TIM_cond sweep temperature data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add TIM_cond_1 GPU temperature line
    if dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures']:
        # Filter out None values
        valid_data_1 = [(bw, temp) for bw, temp in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures']) if temp is not None]
        if valid_data_1:
            bandwidths_1, temps_1 = zip(*valid_data_1)
            fig.add_trace(go.Scatter(
                x=bandwidths_1,
                y=temps_1,
                mode='lines+markers',
                name='GPU Temp - TIM_cond 1 W/(m·K)',
                line=dict(color='red', width=2),
                marker=dict(size=8)
            ))

    # Add TIM_cond_10 GPU temperature line
    if dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures']:
        # Filter out None values
        valid_data_10 = [(bw, temp) for bw, temp in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures']) if temp is not None]
        if valid_data_10:
            bandwidths_10, temps_10 = zip(*valid_data_10)
            fig.add_trace(go.Scatter(
                x=bandwidths_10,
                y=temps_10,
                mode='lines+markers',
                name='GPU Temp - TIM_cond 10 W/(m·K)',
                line=dict(color='darkred', width=2),
                marker=dict(size=8)
            ))
    
    # Add TIM_cond_1 HBM temperature line if available
    if dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures']:
        valid_data_1_hbm = [(bw, temp) for bw, temp in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures']) if temp is not None]
        if valid_data_1_hbm:
            bandwidths_1_hbm, temps_1_hbm = zip(*valid_data_1_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_1_hbm,
                y=temps_1_hbm,
                mode='lines+markers',
                name='HBM Temp - TIM_cond 1 W/(m·K)',
                line=dict(color='orange', width=2, dash='dash'),
                marker=dict(size=6)
            ))

    # Add TIM_cond_10 HBM temperature line if available
    if dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures']:
        valid_data_10_hbm = [(bw, temp) for bw, temp in zip(dual_TIM_cond_sweep_data['bandwidths'], dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures']) if temp is not None]
        if valid_data_10_hbm:
            bandwidths_10_hbm, temps_10_hbm = zip(*valid_data_10_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_10_hbm,
                y=temps_10_hbm,
                mode='lines+markers',
                name='HBM Temp - TIM_cond 10 W/(m·K)',
                line=dict(color='darkorange', width=2, dash='dash'),
                marker=dict(size=6)
            ))
    
    fig.update_layout(
        title='Peak Temperature vs Network Bandwidth (Dual TIM_cond Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Temperature (°C)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_TIM_cond_table():
    """Create a table showing detailed dual TIM_cond bandwidth sweep results"""
    if not dual_TIM_cond_sweep_data['bandwidths']:
        return html.Div("No dual TIM_cond sweep data available for table display")

    # Create DataFrame with dual TIM_cond results
    df_data = {
        'Bandwidth (GB/s)': dual_TIM_cond_sweep_data['bandwidths']
    }

    # Add TIM_cond 1 data
    if dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes']:
        df_data['Runtime TIM_cond 1 (days)'] = dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes']
    if dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures']:
        df_data['GPU Temp TIM_cond 1 (°C)'] = dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures']
    if dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures']:
        df_data['HBM Temp TIM_cond 1 (°C)'] = dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures']

    # Add TIM_cond 10 data
    if dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes']:
        df_data['Runtime TIM_cond 10 (days)'] = dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes']
    if dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures']:
        df_data['GPU Temp TIM_cond 10 (°C)'] = dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures']
    if dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures']:
        df_data['HBM Temp TIM_cond 10 (°C)'] = dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures']

    df = pd.DataFrame(df_data)
    
    # Create Dash DataTable
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        style_data={'backgroundColor': 'rgb(248, 248, 248)'}
    )

def create_dual_infill_cond_runtime_plot():
    """Create runtime vs bandwidth plot for dual infill_cond analysis"""
    if not dual_infill_cond_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual infill_cond sweep data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()

    # Add infill_cond 237 runtime line
    if dual_infill_cond_sweep_data['infill_cond_237']['runtimes']:
        # Filter out None values
        valid_data_237 = [(bw, rt) for bw, rt in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_237']['runtimes']) if rt is not None]
        if valid_data_237:
            bandwidths_237, runtimes_237 = zip(*valid_data_237)
            fig.add_trace(go.Scatter(
                x=bandwidths_237,
                y=runtimes_237,
                mode='lines+markers',
                name='infill_cond 237 W/(m·K)',
                line=dict(color='blue', width=2),
                marker=dict(size=8)
            ))

    # Add infill_cond 1 runtime line
    if dual_infill_cond_sweep_data['infill_cond_1']['runtimes']:
        # Filter out None values
        valid_data_1 = [(bw, rt) for bw, rt in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_1']['runtimes']) if rt is not None]
        if valid_data_1:
            bandwidths_1, runtimes_1 = zip(*valid_data_1)
            fig.add_trace(go.Scatter(
                x=bandwidths_1,
                y=runtimes_1,
                mode='lines+markers',
                name='infill_cond 1 W/(m·K)',
                line=dict(color='green', width=2),
                marker=dict(size=8)
            ))
    
    fig.update_layout(
        title='Runtime vs Network Bandwidth (Dual infill_cond Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Runtime (days)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_infill_cond_temperature_plot():
    """Create temperature vs bandwidth plot for dual infill_cond analysis"""
    if not dual_infill_cond_sweep_data['bandwidths']:
        return go.Figure().add_annotation(
            text="No dual infill_cond sweep temperature data available",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font_size=16
        )
    
    fig = go.Figure()
    
    # Add infill_cond_237 GPU temperature line
    if dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures']:
        # Filter out None values
        valid_data_237 = [(bw, temp) for bw, temp in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures']) if temp is not None]
        if valid_data_237:
            bandwidths_237, temps_237 = zip(*valid_data_237)
            fig.add_trace(go.Scatter(
                x=bandwidths_237,
                y=temps_237,
                mode='lines+markers',
                name='GPU Temp - infill_cond 237 W/(m·K)',
                line=dict(color='red', width=2),
                marker=dict(size=8)
            ))

    # Add infill_cond_1 GPU temperature line
    if dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures']:
        # Filter out None values
        valid_data_1 = [(bw, temp) for bw, temp in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures']) if temp is not None]
        if valid_data_1:
            bandwidths_1, temps_1 = zip(*valid_data_1)
            fig.add_trace(go.Scatter(
                x=bandwidths_1,
                y=temps_1,
                mode='lines+markers',
                name='GPU Temp - infill_cond 1 W/(m·K)',
                line=dict(color='darkred', width=2),
                marker=dict(size=8)
            ))
    
    # Add infill_cond_237 HBM temperature line if available
    if dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures']:
        valid_data_237_hbm = [(bw, temp) for bw, temp in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures']) if temp is not None]
        if valid_data_237_hbm:
            bandwidths_237_hbm, temps_237_hbm = zip(*valid_data_237_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_237_hbm,
                y=temps_237_hbm,
                mode='lines+markers',
                name='HBM Temp - infill_cond 237 W/(m·K)',
                line=dict(color='orange', width=2, dash='dash'),
                marker=dict(size=6)
            ))

    # Add infill_cond_1 HBM temperature line if available
    if dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures']:
        valid_data_1_hbm = [(bw, temp) for bw, temp in zip(dual_infill_cond_sweep_data['bandwidths'], dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures']) if temp is not None]
        if valid_data_1_hbm:
            bandwidths_1_hbm, temps_1_hbm = zip(*valid_data_1_hbm)
            fig.add_trace(go.Scatter(
                x=bandwidths_1_hbm,
                y=temps_1_hbm,
                mode='lines+markers',
                name='HBM Temp - infill_cond 1 W/(m·K)',
                line=dict(color='darkorange', width=2, dash='dash'),
                marker=dict(size=6)
            ))
    
    fig.update_layout(
        title='Peak Temperature vs Network Bandwidth (Dual infill_cond Comparison)',
        xaxis_title='Network Bandwidth (GB/s)',
        yaxis_title='Temperature (°C)',
        xaxis_type='log',
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig

def create_dual_infill_cond_table():
    """Create a table showing detailed dual infill_cond bandwidth sweep results"""
    if not dual_infill_cond_sweep_data['bandwidths']:
        return html.Div("No dual infill_cond sweep data available for table display")

    # Create DataFrame with dual infill_cond results
    df_data = {
        'Bandwidth (GB/s)': dual_infill_cond_sweep_data['bandwidths']
    }

    # Add infill_cond 237 data
    if dual_infill_cond_sweep_data['infill_cond_237']['runtimes']:
        df_data['Runtime infill_cond 237 (days)'] = dual_infill_cond_sweep_data['infill_cond_237']['runtimes']
    if dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures']:
        df_data['GPU Temp infill_cond 237 (°C)'] = dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures']
    if dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures']:
        df_data['HBM Temp infill_cond 237 (°C)'] = dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures']

    # Add infill_cond 1 data
    if dual_infill_cond_sweep_data['infill_cond_1']['runtimes']:
        df_data['Runtime infill_cond 1 (days)'] = dual_infill_cond_sweep_data['infill_cond_1']['runtimes']
    if dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures']:
        df_data['GPU Temp infill_cond 1 (°C)'] = dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures']
    if dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures']:
        df_data['HBM Temp infill_cond 1 (°C)'] = dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures']

    df = pd.DataFrame(df_data)
    
    # Create Dash DataTable
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_cell={'textAlign': 'center'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        style_data={'backgroundColor': 'rgb(248, 248, 248)'}
    )

def run_bandwidth_sweep(system_type, model_type, parallelism_strategy, htc_value):
    """Run thermal analysis across all bandwidth values"""
    global bandwidth_sweep_data
    
    # Reset sweep data
    bandwidth_sweep_data = {
        'bandwidths': [],
        'runtimes': [],
        'gpu_temperatures': [],
        'hbm_temperatures': [],
        'idle_fractions': []
    }
    
    # Define all bandwidth values to sweep
    bandwidth_values = ['450', '900', '1800', '3600', '7200', '14400', '28800', '57600', '115200']
    
    results_summary = ""
    
    for bandwidth in bandwidth_values:
        try:
            # Run analysis for this bandwidth
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, htc_value, bandwidth, TIM_cond = 1, infill_cond = 1)
            
            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                # Store results
                bandwidth_sweep_data['bandwidths'].append(int(bandwidth))
                bandwidth_sweep_data['runtimes'].append(runtime)
                bandwidth_sweep_data['gpu_temperatures'].append(gpu_temp)
                bandwidth_sweep_data['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    bandwidth_sweep_data['idle_fractions'].append(idle_frac)
                
                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                
        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
    
    return "Bandwidth sweep completed", results_summary

def run_dual_htc_bandwidth_sweep(system_type, model_type, parallelism_strategy):
    """Run thermal analysis across all bandwidth values for both HTC values (10 and 20)"""
    global dual_htc_sweep_data
    
    # Only run for 3D_waferscale as 2p5D doesn't support HTC 20
    if system_type != '3D_waferscale':
        return "Dual HTC sweep only available for 3D Waferscale systems", "Error: 2.5D systems only support HTC 10 kW/(m²·K)"
    
    # Reset dual HTC sweep data
    dual_htc_sweep_data = {
        'bandwidths': [],
        'htc_10': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        },
        'htc_20': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        }
    }
    
    # Define all bandwidth values to sweep
    bandwidth_values = ['450', '900', '1800', '3600', '7200', '14400', '28800', '57600', '115200']
    
    results_summary = "Dual HTC Bandwidth Sweep Results:\n"
    results_summary += "=" * 50 + "\n\n"
    
    # Store bandwidth values once
    dual_htc_sweep_data['bandwidths'] = [int(bw) for bw in bandwidth_values]
    
    # Sweep for HTC 10 kW/(m²·K)
    results_summary += "HTC 10 kW/(m²·K) Results:\n"
    results_summary += "-" * 30 + "\n"
    
    for bandwidth in bandwidth_values:
        try:
            # Run analysis for HTC 10
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '10', bandwidth, TIM_cond = 1, infill_cond = 1)
            
            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                # Store HTC 10 results
                dual_htc_sweep_data['htc_10']['runtimes'].append(runtime)
                dual_htc_sweep_data['htc_10']['gpu_temperatures'].append(gpu_temp)
                dual_htc_sweep_data['htc_10']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_htc_sweep_data['htc_10']['idle_fractions'].append(idle_frac)
                
                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_htc_sweep_data['htc_10']['runtimes'].append(None)
                dual_htc_sweep_data['htc_10']['gpu_temperatures'].append(None)
                dual_htc_sweep_data['htc_10']['hbm_temperatures'].append(None)
                
        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_htc_sweep_data['htc_10']['runtimes'].append(None)
            dual_htc_sweep_data['htc_10']['gpu_temperatures'].append(None)
            dual_htc_sweep_data['htc_10']['hbm_temperatures'].append(None)

        try:
            # print(f"Running HTC 20 analysis for bandwidth {bandwidth} GB/s...")
            # Run analysis for HTC 20
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '20', bandwidth, TIM_cond = 1, infill_cond = 1)
            
            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                # Store HTC 20 results
                dual_htc_sweep_data['htc_20']['runtimes'].append(runtime)
                dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(gpu_temp)
                dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_htc_sweep_data['htc_20']['idle_fractions'].append(idle_frac)
                
                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_htc_sweep_data['htc_20']['runtimes'].append(None)
                dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(None)
                dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(None)
                
        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_htc_sweep_data['htc_20']['runtimes'].append(None)
            dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(None)
            dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(None)
    
    results_summary += "\nHTC 20 kW/(m²·K) Results:\n"
    results_summary += "-" * 30 + "\n"
    
    # print("Finished HTC 10 sweep, now starting HTC 20 sweep...\n")

    # Sweep for HTC 20 kW/(m²·K)
    # for bandwidth in bandwidth_values:
        # try:
        #     # print(f"Running HTC 20 analysis for bandwidth {bandwidth} GB/s...")
        #     # Run analysis for HTC 20
        #     status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '20', bandwidth)
            
        #     if results and isinstance(results, tuple) and len(results) >= 3:
        #         runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
        #         idle_frac = results[3] if len(results) >= 4 else None
                
        #         # Store HTC 20 results
        #         dual_htc_sweep_data['htc_20']['runtimes'].append(runtime)
        #         dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(gpu_temp)
        #         dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(hbm_temp)
        #         if idle_frac is not None:
        #             dual_htc_sweep_data['htc_20']['idle_fractions'].append(idle_frac)
                
        #         results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
        #             bandwidth, runtime, gpu_temp, hbm_temp)
        #     else:
        #         results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
        #         # Add None values to maintain array alignment
        #         dual_htc_sweep_data['htc_20']['runtimes'].append(None)
        #         dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(None)
        #         dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(None)
                
        # except Exception as e:
        #     results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
        #     # Add None values to maintain array alignment
        #     dual_htc_sweep_data['htc_20']['runtimes'].append(None)
        #     dual_htc_sweep_data['htc_20']['gpu_temperatures'].append(None)
        #     dual_htc_sweep_data['htc_20']['hbm_temperatures'].append(None)
    
    return "Dual HTC bandwidth sweep completed", results_summary

def run_dual_TIM_cond_bandwidth_sweep(system_type, model_type, parallelism_strategy):
    """Run thermal analysis across all bandwidth values for both TIM_cond values (1 and 10)"""
    global dual_TIM_cond_sweep_data

    # Only run for 3D_waferscale as 2p5D doesn't support TIM_cond 10
    if system_type != '3D_waferscale':
        return "Dual TIM_cond sweep only available for 3D Waferscale systems", "Error: 2.5D systems only support TIM_cond 1 kW/(m·K)"

    # Reset dual TIM_cond sweep data
    dual_TIM_cond_sweep_data = {
        'bandwidths': [],
        'TIM_cond_1': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        },
        'TIM_cond_10': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        }
    }
    
    # Define all bandwidth values to sweep
    bandwidth_values = ['450', '900', '1800', '3600', '7200', '14400', '28800', '57600', '115200']

    results_summary = "Dual TIM_cond Bandwidth Sweep Results:\n"
    results_summary += "=" * 50 + "\n\n"
    
    # Store bandwidth values once
    dual_TIM_cond_sweep_data['bandwidths'] = [int(bw) for bw in bandwidth_values]

    # Sweep for TIM_cond 1 kW/(m·K)
    results_summary += "TIM_cond 1 kW/(m·K) Results:\n"
    results_summary += "-" * 30 + "\n"
    
    for bandwidth in bandwidth_values:
        try:
            # Run analysis for TIM_cond 1
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '10', bandwidth, TIM_cond = 1, infill_cond = 1)

            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                # Store TIM_cond 1 results
                dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes'].append(runtime)
                dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures'].append(gpu_temp)
                dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_TIM_cond_sweep_data['TIM_cond_1']['idle_fractions'].append(idle_frac)

                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes'].append(None)
                dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures'].append(None)
                dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures'].append(None)

        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_TIM_cond_sweep_data['TIM_cond_1']['runtimes'].append(None)
            dual_TIM_cond_sweep_data['TIM_cond_1']['gpu_temperatures'].append(None)
            dual_TIM_cond_sweep_data['TIM_cond_1']['hbm_temperatures'].append(None)

        try:
            # print(f"Running TIM_cond 10 analysis for bandwidth {bandwidth} GB/s...")
            # Run analysis for TIM_cond 10
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '10', bandwidth, TIM_cond = 10, infill_cond = 1)
            
            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None
                
                # Store TIM_cond 10 results
                dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes'].append(runtime)
                dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures'].append(gpu_temp)
                dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_TIM_cond_sweep_data['TIM_cond_10']['idle_fractions'].append(idle_frac)

                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes'].append(None)
                dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures'].append(None)
                dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures'].append(None)

        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_TIM_cond_sweep_data['TIM_cond_10']['runtimes'].append(None)
            dual_TIM_cond_sweep_data['TIM_cond_10']['gpu_temperatures'].append(None)
            dual_TIM_cond_sweep_data['TIM_cond_10']['hbm_temperatures'].append(None)

    results_summary += "\nTIM_cond 10 kW/(m·K) Results:\n"
    results_summary += "-" * 30 + "\n"
    
    return "Dual TIM_cond bandwidth sweep completed", results_summary

def run_dual_infill_cond_bandwidth_sweep(system_type, model_type, parallelism_strategy):
    """Run thermal analysis across all bandwidth values for both infill_cond values (237 and 1)"""
    global dual_infill_cond_sweep_data

    # Only run for 3D_waferscale as 2p5D doesn't support infill_cond 1
    if system_type != '3D_waferscale':
        return "Dual infill_cond sweep only available for 3D Waferscale systems", "Error: 2.5D systems only support infill_cond 237 kW/(m·K)"

    # Reset dual infill_cond sweep data
    dual_infill_cond_sweep_data = {
        'bandwidths': [],
        'infill_cond_237': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        },
        'infill_cond_1': {
            'runtimes': [],
            'gpu_temperatures': [],
            'hbm_temperatures': [],
            'idle_fractions': []
        }
    }
    
    # Define all bandwidth values to sweep
    bandwidth_values = ['450', '900', '1800', '3600', '7200', '14400', '28800', '57600', '115200']

    results_summary = "Dual infill_cond Bandwidth Sweep Results:\n"
    results_summary += "=" * 50 + "\n\n"
    
    # Store bandwidth values once
    dual_infill_cond_sweep_data['bandwidths'] = [int(bw) for bw in bandwidth_values]

    # Sweep for infill_cond 237 kW/(m·K)
    results_summary += "infill_cond 237 kW/(m·K) Results:\n"
    results_summary += "-" * 30 + "\n"
    
    for bandwidth in bandwidth_values:
        try:
            # Run analysis for infill_cond 237
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '10', bandwidth, TIM_cond = 1, infill_cond = 1)

            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None

                # Store infill_cond 237 results
                dual_infill_cond_sweep_data['infill_cond_237']['runtimes'].append(runtime)
                dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures'].append(gpu_temp)
                dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_infill_cond_sweep_data['infill_cond_237']['idle_fractions'].append(idle_frac)

                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_infill_cond_sweep_data['infill_cond_237']['runtimes'].append(None)
                dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures'].append(None)
                dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures'].append(None)

        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_infill_cond_sweep_data['infill_cond_237']['runtimes'].append(None)
            dual_infill_cond_sweep_data['infill_cond_237']['gpu_temperatures'].append(None)
            dual_infill_cond_sweep_data['infill_cond_237']['hbm_temperatures'].append(None)

        try:
            # print(f"Running infill_cond 1 analysis for bandwidth {bandwidth} GB/s...")
            # Run analysis for infill_cond 1
            status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, '10', bandwidth, TIM_cond = 1, infill_cond = 1)

            if results and isinstance(results, tuple) and len(results) >= 3:
                runtime, gpu_temp, hbm_temp = results[0], results[1], results[2]
                idle_frac = results[3] if len(results) >= 4 else None

                # Store infill_cond 1 results
                dual_infill_cond_sweep_data['infill_cond_1']['runtimes'].append(runtime)
                dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures'].append(gpu_temp)
                dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures'].append(hbm_temp)
                if idle_frac is not None:
                    dual_infill_cond_sweep_data['infill_cond_1']['idle_fractions'].append(idle_frac)

                results_summary += "Bandwidth {}: Runtime={:.2f} days, GPU={:.1f}°C, HBM={:.1f}°C\n".format(
                    bandwidth, runtime, gpu_temp, hbm_temp)
            else:
                results_summary += "Bandwidth {}: Analysis failed\n".format(bandwidth)
                # Add None values to maintain array alignment
                dual_infill_cond_sweep_data['infill_cond_1']['runtimes'].append(None)
                dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures'].append(None)
                dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures'].append(None)

        except Exception as e:
            results_summary += "Bandwidth {}: Error - {}\n".format(bandwidth, str(e))
            # Add None values to maintain array alignment
            dual_infill_cond_sweep_data['infill_cond_1']['runtimes'].append(None)
            dual_infill_cond_sweep_data['infill_cond_1']['gpu_temperatures'].append(None)
            dual_infill_cond_sweep_data['infill_cond_1']['hbm_temperatures'].append(None)

    results_summary += "\ninfill_cond 1 kW/(m·K) Results:\n"
    results_summary += "-" * 30 + "\n"

    return "Dual infill_cond bandwidth sweep completed", results_summary

# def calculate_system_cost(system_type, model_type):
#     """Calculate estimated system cost based on configuration"""
#     base_costs = {
#         '3D_waferscale': {
#             'llama_3_3_70b': 45000,
#             'llama_3_1_405b': 85000
#         },
#         '2p5D_waferscale': {
#             'llama_3_3_70b': 35000,
#             'llama_3_1_405b': 65000
#         }
#     }
    
#     try:
#         return f"${base_costs[system_type][model_type]:,}"
#     except KeyError:
#         return "Cost calculation unavailable"

# Callback to update parallelism options based on system type
# @app.callback(
#     Output('parallelism-dropdown', 'options'),
#     Output('parallelism-dropdown', 'value'),
#     Input('system-dropdown', 'value')
# )
# def update_parallelism_options(system_type):
#     if system_type == '3D_waferscale':
#         options = [
#             {'label': 'Strategy 1 (kp1=1, kp2=49)', 'value': 'strategy_1'},
#             {'label': 'Strategy 2 (kp1=49, kp2=1)', 'value': 'strategy_2'},
#             {'label': 'Strategy 3 (kp1=7, kp2=7)', 'value': 'strategy_3'}
#         ]
#     else:  # 2p5D_waferscale
#         options = [
#             {'label': 'Strategy 1 (kp1=1, kp2=25)', 'value': 'strategy_1'},
#             {'label': 'Strategy 2 (kp1=25, kp2=1)', 'value': 'strategy_2'},
#             {'label': 'Strategy 3 (kp1=5, kp2=5)', 'value': 'strategy_3'}
#         ]
#     return options, 'strategy_1'

# # Callback to disable HTC 20 for 2p5D
# @app.callback(
#     Output('htc-dropdown', 'options'),
#     Output('htc-dropdown', 'value'),
#     Input('system-dropdown', 'value'),
#     State('htc-dropdown', 'value')
# )
# def update_htc_options(system_type, current_htc):
    if system_type == '2p5D_waferscale':
        options = [{'label': '10 kW/(m²·K)', 'value': '10'}]
        value = '10'
    else:  # 3D_waferscale
        options = [
            {'label': '10 kW/(m²·K)', 'value': '10'},
            {'label': '20 kW/(m²·K)', 'value': '20'}
        ]
        value = current_htc if current_htc in ['10', '20'] else '10'
    return options, value

def get_frequency_for_bandwidth(bandwidth):
    """Convert bandwidth to frequency value"""
    bandwidth_to_frequency = {
        '450': '4.2e9',
        '900': '12.48e9',
        '1800': '40e9',
        '3600': '120e9',
        '7200': '400e9',
        '14400': '1480e9',
        '28800': '6600e9',
        '57600': '45750e9',
        '115200': '3230000e9'
    }
    return bandwidth_to_frequency.get(bandwidth, '12.48e9')

def modify_buildrun_sh(model_type):
    """Modify buildRun.sh to select the correct model parameters"""
    file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/buildRun.sh"
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        if model_type == 'llama_3_3_70b':
            # Uncomment Llama 3.3 70B lines (lines 5-13)
            # Comment Llama 3.1 405B lines (lines 27-35)
            for i, line in enumerate(lines):
                if i >= 4 and i <= 12:  # Lines 5-13 (0-indexed 4-12)
                    if line.strip().startswith('#'):
                        line = line.replace('# ', '', 1)  # Remove '# '
                        lines[i] = line
                elif i >= 26 and i <= 34:  # Lines 27-35 (0-indexed 26-34)
                    if not line.strip().startswith('#'):
                        lines[i] = '# ' + line
            
            
        elif model_type == 'llama_3_1_405b':
            # Comment Llama 3.3 70B lines and uncomment Llama 3.1 405B lines
            for i, line in enumerate(lines):
                if i >= 4 and i <= 12:  # Lines 5-13 (0-indexed 4-12)
                    if not line.strip().startswith('#'):
                        lines[i] = '# ' + line
                elif i >= 26 and i <= 34:  # Lines 27-35 (0-indexed 26-34)
                    if line.strip().startswith('#'):
                        line = line.replace('# ', '', 1)  # Remove '# '
                        lines[i] = line
        
        with open(file_path, 'w') as f:
            f.writelines(lines)

    except Exception as e:
        print("Error modifying buildRun.sh: {}".format(e))
        raise

def modify_run_sh(system_type, parallelism_strategy):
    """Modify run.sh to set correct parallelism parameters"""
    file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Get kp1 and kp2 values based on system and strategy
    if system_type == '3D_waferscale':
        strategies = {
            'strategy_1': (1, 49),
            'strategy_2': (49, 1),
            'strategy_3': (7, 7)
        }
        kp1, kp2 = strategies[parallelism_strategy]

        # Use line 23 for 3D_waferscale, comment line 24
        for i in [21, 23, 24]:
            line = lines[i]
            if not line.strip().startswith('#'):
                lines[i] = '# ' + line
        
        line = lines[22]
        line = re.sub(r"--kp1\s+\d+", "--kp1 {}".format(kp1), line)
        line = re.sub(r"--kp2\s+\d+", "--kp2 {}".format(kp2), line)
        if line.strip().startswith('#'):
            line = line.replace('# ', '', 1)
        
        lines[22] = line

    elif system_type == '2p5D_waferscale':  # 2p5D_waferscale
        strategies = {
            'strategy_1': (1, 25),
            'strategy_2': (25, 1),
            'strategy_3': (5, 5)
        }
        kp1, kp2 = strategies[parallelism_strategy]

        # Use line 24 for 2p5D_waferscale, comment line 23
        for i in [21, 22, 24]:
            line = lines[i]
            if not line.strip().startswith('#'):
                lines[i] = '# ' + line
        
        line = lines[23]
        line = re.sub(r"--kp1\s+\d+", "--kp1 {}".format(kp1), line)
        line = re.sub(r"--kp2\s+\d+", "--kp2 {}".format(kp2), line)
        if line.strip().startswith('#'):
            line = line.replace('# ', '', 1)

        lines[23] = line
    
    with open(file_path, 'w') as f:
        f.writelines(lines)

# def modify_run_sh(system_type, parallelism_strategy):
#     """Modify run.sh to set correct parallelism parameters"""
#     file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/scripts/run.sh"
    
#     with open(file_path, 'r') as f:
#         content = f.read()
    
#     # Get kp1 and kp2 values based on system and strategy
#     if system_type == '3D_waferscale':
#         strategies = {
#             'strategy_1': (1, 49),
#             'strategy_2': (49, 1),
#             'strategy_3': (7, 7)
#         }
#         # Use line 23 for 3D_waferscale, comment line 24
#         content = re.sub(r'#.*python3.*testing_thermal_A100\.yaml.*--kp1 \d+ --kp2 \d+', 
#                         lambda m: m.group(0).replace('#', '').strip(), content)
#         content = re.sub(r'python3.*testing_thermal_A100_2p5D\.yaml.*--kp1 \d+ --kp2 \d+', 
#                         lambda m: '    # ' + m.group(0), content)
#     elif system_type == '2p5D_waferscale':  # 2p5D_waferscale
#         strategies = {
#             'strategy_1': (1, 25),
#             'strategy_2': (25, 1),
#             'strategy_3': (5, 5)
#         }
#         # Use line 24 for 2p5D_waferscale, comment line 23
#         content = re.sub(r'python3.*testing_thermal_A100\.yaml.*--kp1 \d+ --kp2 \d+', 
#                         lambda m: '    # ' + m.group(0), content)
#         content = re.sub(r'#.*python3.*testing_thermal_A100_2p5D\.yaml.*--kp1 \d+ --kp2 \d+', 
#                         lambda m: m.group(0).replace('#', '').strip(), content)
    
#     kp1, kp2 = strategies[parallelism_strategy]
    
#     # Update kp1 and kp2 values in the active line
#     if system_type == '3D_waferscale':
#         content = re.sub(r'(python3.*testing_thermal_A100\.yaml.*--kp1) \d+ (--kp2) \d+', 
#                         r'\1 {} \2 {}'.format(kp1, kp2), content)
#     elif system_type == '2p5D_waferscale':
#         content = re.sub(r'(python3.*testing_thermal_A100_2p5D\.yaml.*--kp1) \d+ (--kp2) \d+', 
#                         r'\1 {} \2 {}'.format(kp1, kp2), content)
    
#     with open(file_path, 'w') as f:
#         f.write(content)

def modify_yaml_bandwidth(system_type, bandwidth):
    """Modify the YAML file to set network bandwidth"""
    if system_type == '3D_waferscale':
        file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100.yaml"
    elif system_type == '2p5D_waferscale':
        file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/DeepFlow/configs/new-configs/testing_thermal_A100_2p5D.yaml"
    
    frequency = get_frequency_for_bandwidth(bandwidth)
    nominal_frequency = float(frequency) / 1e9
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Update the nominal_frequency in network.intra_node section
    line = lines[92]
    parts = line.split("nominal_frequency:")
    line = "{}nominal_frequency: {:.2f}e9\n".format(parts[0], nominal_frequency)
    lines[92] = line

    with open(file_path, 'w') as f:
        f.writelines(lines)

# def modify_calibrated_iterations(htc_value, system_type):
#     """Modify calibrated_iterations.py for HTC value"""
    
#     file_path = "/app/nanocad/projects/deepflow_thermal/DeepFlow/calibrated_iterations.py"
#     try:
#         with open(file_path, 'r') as f:
#             lines = f.readlines()
        
#         # For 20 kW/(m²·K), we need to use the predict_temperature function
#         # and modify the temperature dictionaries accordingly
#         # This is a simplified approach - in practice, you would need to identify
#         # the exact lines to modify based on the actual file structure
        
#         # Only modify for 3D_waferscale with 20 kW/(m²·K)
#         if htc_value == '20' and system_type == '3D_waferscale':
#             modified = False
#             for i, line in enumerate(lines):
#                 if i >= 38 and i <= 42:
#                     if not line.strip().startswith('#'):
#                         lines[i] = '# ' + line
#                         modified = True
#                 elif i >= 43 and i <= 47:
#                     if line.strip().startswith('#'):
#                         lines[i] = line.replace('# ', '', 1)
#                         modified = True
#                 elif i >= 74 and i <= 78:
#                     if not line.strip().startswith('#'):
#                         lines[i] = '# ' + line
#                         modified = True
#                 elif i >= 79 and i <= 83:
#                     if line.strip().startswith('#'):
#                         lines[i] = line.replace('# ', '', 1)
#                         modified = True
#                 # else:
#                 #     continue
            
#             if modified:
#                 with open(file_path, 'w') as f:
#                     f.writelines(lines)
        
#         else:
#             modified = False
#             for i, line in enumerate(lines):
#                 if i >= 38 and i <= 42:
#                     if line.strip().startswith('#'):
#                         lines[i] = line.replace('# ', '', 1)
#                         modified = True
#                 elif i >= 43 and i <= 47:
#                     if not line.strip().startswith('#'):
#                         lines[i] = '# ' + line
#                         modified = True
#                 elif i >= 74 and i <= 78:
#                     if line.strip().startswith('#'):
#                         lines[i] = line.replace('# ', '', 1)
#                         modified = True
#                 elif i >= 79 and i <= 83:
#                     if not line.strip().startswith('#'):
#                         lines[i] = '# ' + line
#                         modified = True
#                 # else:
#                 #     continue
            
#             if modified:
#                 with open(file_path, 'w') as f:
#                     f.writelines(lines)
                
#     except Exception as e:
#         print("Error modifying calibrated_iterations.py: {}".format(e))
#         raise

# def get_system_cost(system_type):
#     """Calculate system cost using load_and_test_design.py"""
#     try:
#         if system_type == '2p5D_waferscale':
#             cmd = [
#                 'python', 'load_and_test_design.py',
#                 'configs/thermal-configs/io_definitions.xml',
#                 'configs/thermal-configs/layer_definitions.xml',
#                 'configs/thermal-configs/wafer_process_definitions.xml',
#                 'configs/thermal-configs/assembly_process_definitions.xml',
#                 'configs/thermal-configs/test_definitions.xml',
#                 'configs/thermal-configs/netlist.xml',
#                 'configs/thermal-configs/sip_hbm_dray050925_1gpu_6hbm_5x5.xml',
#                 'output/output_vars2.yaml'
#             ]
#         else:  # 3D_waferscale
#             cmd = [
#                 'python', 'load_and_test_design.py',
#                 'configs/thermal-configs/io_definitions.xml',
#                 'configs/thermal-configs/layer_definitions.xml',
#                 'configs/thermal-configs/wafer_process_definitions.xml',
#                 'configs/thermal-configs/assembly_process_definitions.xml',
#                 'configs/thermal-configs/test_definitions.xml',
#                 'configs/thermal-configs/netlist.xml',
#                 'configs/thermal-configs/sip_hbm_dray061925_1GPU_6HBM_7x7_3D.xml',
#                 'output/output_vars2.yaml'
#             ]
        
#         os.chdir('/app/nanocad/projects/deepflow_thermal/DeepFlow')
#         result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        
#         if result.returncode == 0:
#             # Extract the cost value from output
#             cost_value = result.stdout.decode('utf-8').strip()
#             formatted_cost = "{:.2f}".format(float(cost_value))
#             return formatted_cost
#         else:
#             return "Error: {}".format(result.stderr.decode('utf-8'))
            
#     except Exception as e:
#         return "Error calculating cost: {}".format(str(e))

# def run_thermal_analysis(system_type, model_type, parallelism_strategy, htc_value, bandwidth, TIM_cond, infill_cond):
#     """Run the complete thermal analysis"""
#     global running_process
    
#     try:
#         # Make all necessary modifications
#         modify_buildrun_sh(model_type)
#         modify_run_sh(system_type, parallelism_strategy)
#         modify_yaml_bandwidth(system_type, bandwidth)
#         # modify_calibrated_iterations(htc_value, system_type)
        
#         # Use the GUI-safe version of iterations that handles subprocess errors
#         # print("We are in directory:", os.getcwd())
#         # results = iterations_gui_safe(system_name = system_type)
#         # from calibrated_iterations import iterations
#         results = iterations(system_name = system_type, HTC = int(htc_value), TIM_cond = TIM_cond, infill_cond = infill_cond)
#         print(results)
#         return "Analysis completed successfully", results
        
#     except Exception as e:
#         print("Error in run_thermal_analysis:", str(e))
#         traceback.print_exc()
#         return "Error: {}".format(str(e)), None

# # Main callback for running analysis
# @app.callback(
#     [Output('system-cost', 'children'),
#      Output('status', 'children'),
#      Output('status', 'className'),
#      Output('output-log', 'children'),
#      Output('progress-bar', 'value'),
#      Output('run-button', 'disabled'),
#      Output('stop-button', 'disabled')],
#     [Input('run-button', 'n_clicks'),
#      Input('sweep-button', 'n_clicks'),
#      Input('dual-htc-sweep-button', 'n_clicks'),
#      Input('dual-tim-cond-sweep-button', 'n_clicks'),
#      Input('dual-infill-cond-sweep-button', 'n_clicks'),
#      Input('stop-button', 'n_clicks')],
#     [State('system-dropdown', 'value'),
#      State('model-dropdown', 'value'),
#      State('parallelism-dropdown', 'value'),
#      State('htc-dropdown', 'value'),
#      State('bandwidth-dropdown', 'value')]
# )
# def handle_analysis(run_clicks, sweep_clicks, dual_htc_clicks, dual_TIM_cond_clicks, dual_infill_cond_clicks, stop_clicks, system_type, model_type, parallelism_strategy, htc_value, bandwidth):
#     global running_process
    
#     ctx = dash.callback_context
#     if not ctx.triggered:
#         return "Not calculated", "Ready", "text-success", "Analysis results will appear here...", 0, False, True
    
#     button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
#     if button_id == 'stop-button':
#         if running_process:
#             running_process.terminate()
#             running_process = None
#         return "Not calculated", "Stopped", "text-warning", "Analysis stopped by user", 0, False, True
    
#     if button_id == 'sweep-button' and sweep_clicks:
#         # Start bandwidth sweep analysis
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         log_content = "[{}] Starting bandwidth sweep analysis...\n".format(timestamp)
#         log_content += "System: {}\n".format(system_type)
#         log_content += "Model: {}\n".format(model_type)
#         log_content += "Parallelism: {}\n".format(parallelism_strategy)
#         log_content += "HTC: {} kW/(m²·K)\n".format(htc_value)
#         log_content += "Sweeping bandwidths: 450, 900, 1800, 3600, 7200, 14400, 28800, 57600, 115200 GB/s\n\n"
        
#         try:
#             # Calculate system cost first
#             log_content += "Calculating system cost...\n"
#             cost = get_system_cost(system_type)
#             log_content += "System cost: {}\n\n".format(cost)
            
#             # Run bandwidth sweep
#             log_content += "Running bandwidth sweep analysis...\n"
#             status_msg, sweep_results = run_bandwidth_sweep(system_type, model_type, parallelism_strategy, htc_value)
            
#             log_content += sweep_results
#             log_content += "\nBandwidth sweep completed successfully!\n"
            
#             return cost, "Sweep Completed", "text-success", log_content, 100, False, True
            
#         except Exception as e:
#             error_msg = "Error: {}".format(str(e))
#             log_content += error_msg
#             return "Error", "Failed", "text-danger", log_content, 0, False, True
    
#     if button_id == 'dual-htc-sweep-button' and dual_htc_clicks:
#         # Start dual HTC bandwidth sweep analysis
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         log_content = "[{}] Starting dual HTC bandwidth sweep analysis...\n".format(timestamp)
#         log_content += "System: {}\n".format(system_type)
#         log_content += "Model: {}\n".format(model_type)
#         log_content += "Parallelism: {}\n".format(parallelism_strategy)
#         log_content += "Comparing HTC: 10 kW/(m²·K) vs 20 kW/(m²·K)\n"
#         log_content += "Sweeping bandwidths: 450, 900, 1800, 3600, 7200, 14400, 28800, 57600, 115200 GB/s\n\n"
        
#         try:
#             # Check if system supports dual HTC
#             if system_type != '3D_waferscale':
#                 log_content += "Error: Dual HTC sweep only available for 3D Waferscale systems\n"
#                 log_content += "2.5D systems only support HTC 10 kW/(m²·K)\n"
#                 return "Not supported", "Failed", "text-danger", log_content, 0, False, True
            
#             # Calculate system cost first
#             log_content += "Calculating system cost...\n"
#             cost = get_system_cost(system_type)
#             log_content += "System cost: {}\n\n".format(cost)
            
#             # Run dual HTC bandwidth sweep
#             log_content += "Running dual HTC bandwidth sweep analysis...\n"
#             status_msg, sweep_results = run_dual_htc_bandwidth_sweep(system_type, model_type, parallelism_strategy)
            
#             log_content += sweep_results
#             log_content += "\nDual HTC bandwidth sweep completed successfully!\n"
            
#             return cost, "Dual HTC Sweep Completed", "text-success", log_content, 100, False, True
            
#         except Exception as e:
#             error_msg = "Error: {}".format(str(e))
#             log_content += error_msg
#             return "Error", "Failed", "text-danger", log_content, 0, False, True
        
#     if button_id == 'dual-tim-cond-sweep-button' and dual_TIM_cond_clicks:
#         # Start dual TIM_cond sweep analysis
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         log_content = "[{}] Starting dual TIM_cond sweep analysis...\n".format(timestamp)
#         # print(system_type)
#         log_content += "System: {}\n".format(system_type)
#         log_content += "Model: {}\n".format(model_type)
#         log_content += "Parallelism: {}\n".format(parallelism_strategy)
#         log_content += "Comparing TIM_cond: 1 W/(m·K) vs 10 W/(m·K)\n"
#         log_content += "Sweeping bandwidths: 450, 900, 1800, 3600, 7200, 14400, 28800, 57600, 115200 GB/s\n\n"
        
#         try:
#             # Check if system supports dual TIM_cond
#             if system_type != '3D_waferscale':
#                 log_content += "Error: Dual TIM_cond sweep only available for 3D Waferscale systems\n"
#                 log_content += "2.5D systems only support TIM_cond 1 W/(m·K)\n"
#                 return "Not supported", "Failed", "text-danger", log_content, 0, False, True
            
#             # Calculate system cost first
#             log_content += "Calculating system cost...\n"
#             cost = get_system_cost(system_type)
#             log_content += "System cost: {}\n\n".format(cost)

#             # Run dual TIM_cond sweep
#             log_content += "Running dual TIM_cond sweep analysis...\n"
#             status_msg, sweep_results = run_dual_TIM_cond_bandwidth_sweep(system_type, model_type, parallelism_strategy)
            
#             log_content += sweep_results
#             log_content += "\nDual TIM_cond sweep completed successfully!\n"

#             return cost, "Dual TIM_cond Sweep Completed", "text-success", log_content, 100, False, True
            
#         except Exception as e:
#             error_msg = "Error: {}".format(str(e))
#             log_content += error_msg
#             return "Error", "Failed", "text-danger", log_content, 0, False, True

#     if button_id == 'dual-infill-cond-sweep-button' and dual_infill_cond_clicks:
#         # Start dual infill_cond sweep analysis
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         log_content = "[{}] Starting dual infill_cond sweep analysis...\n".format(timestamp)
#         # print(system_type)
#         log_content += "System: {}\n".format(system_type)
#         log_content += "Model: {}\n".format(model_type)
#         log_content += "Parallelism: {}\n".format(parallelism_strategy)
#         log_content += "Comparing infill_cond: 237 W/(m·K) vs 1 W/(m·K)\n"
#         log_content += "Sweeping bandwidths: 450, 900, 1800, 3600, 7200, 14400, 28800, 57600, 115200 GB/s\n\n"
        
#         try:
#             # Check if system supports dual infill_cond
#             if system_type != '3D_waferscale':
#                 log_content += "Error: Dual infill_cond sweep only available for 3D Waferscale systems\n"
#                 log_content += "2.5D systems only support infill_cond 237 W/(m·K)\n"
#                 return "Not supported", "Failed", "text-danger", log_content, 0, False, True
            
#             # Calculate system cost first
#             log_content += "Calculating system cost...\n"
#             cost = get_system_cost(system_type)
#             log_content += "System cost: {}\n\n".format(cost)

#             # Run dual infill_cond sweep
#             log_content += "Running dual infill_cond sweep analysis...\n"
#             status_msg, sweep_results = run_dual_infill_cond_bandwidth_sweep(system_type, model_type, parallelism_strategy)

#             log_content += sweep_results
#             log_content += "\nDual infill_cond sweep completed successfully!\n"

#             return cost, "Dual infill_cond Sweep Completed", "text-success", log_content, 100, False, True

#         except Exception as e:
#             error_msg = "Error: {}".format(str(e))
#             log_content += error_msg
#             return "Error", "Failed", "text-danger", log_content, 0, False, True
    
#     if button_id == 'run-button' and run_clicks:
#         # Start single analysis
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         log_content = "[{}] Starting analysis...\n".format(timestamp)
#         log_content += "System: {}\n".format(system_type)
#         log_content += "Model: {}\n".format(model_type)
#         log_content += "Parallelism: {}\n".format(parallelism_strategy)
#         log_content += "HTC: {} kW/(m²·K)\n".format(htc_value)
#         log_content += "Bandwidth: {} GB/s\n\n".format(bandwidth)
        
#         try:
#             # Calculate system cost first
#             log_content += "Calculating system cost...\n"
#             cost = get_system_cost(system_type)
#             log_content += "System cost: {}\n\n".format(cost)
            
#             # Run thermal analysis
#             log_content += "Running thermal analysis...\n"
#             status_msg, results = run_thermal_analysis(system_type, model_type, parallelism_strategy, htc_value, bandwidth, TIM_cond = 1, infill_cond = 1)
            
#             if results:
#                 # Parse and store results
#                 parse_analysis_results(results)
                
#                 log_content += "Analysis completed successfully!\n"
#                 if isinstance(results, tuple) and len(results) >= 4:
#                     runtime, gpu_temp, hbm_temp, idle_frac = results
#                     log_content += "Runtime: {:.2f} days\n".format(runtime)
#                     log_content += "GPU Temperature: {:.1f}°C\n".format(gpu_temp)
#                     log_content += "HBM Temperature: {:.1f}°C\n".format(hbm_temp)
#                     log_content += "GPU Idle Fraction: {:.2f}\n".format(idle_frac)
#                 else:
#                     log_content += "Results: {}\n".format(results)
#             else:
#                 log_content += "Analysis failed: {}\n".format(status_msg)
            
#             return cost, "Completed", "text-success", log_content, 100, False, True
            
#         except Exception as e:
#             error_msg = "Error: {}".format(str(e))
#             log_content += error_msg
#             return "Error", "Failed", "text-danger", log_content, 0, False, True
    
#     return "Not calculated", "Ready", "text-success", "Analysis results will appear here...", 0, False, True

# # Callback to update plots and table based on output log
# @app.callback(
#     [Output('runtime-plot', 'figure'),
#      Output('temperature-plot', 'figure'),
#      Output('results-table', 'children')],
#     [Input('output-log', 'children')]
# )
# def update_visualizations(output_log):
#     """Update plots and table when new output is available"""
#     if not output_log or output_log == "Analysis results will appear here...":
#         empty_fig = go.Figure().add_annotation(
#             text="No data available",
#             x=0.5, y=0.5,
#             xref="paper", yref="paper",
#             showarrow=False,
#             font_size=16
#         )
#         return empty_fig, empty_fig, html.Div("No data available")
    
#     # Check if this is a dual HTC bandwidth sweep analysis
#     if "dual htc" in str(output_log).lower() and "bandwidth sweep" in str(output_log).lower():
#         # Use dual HTC sweep plots and table
#         runtime_fig = create_dual_htc_runtime_plot()
#         temp_fig = create_dual_htc_temperature_plot()
#         results_table = create_dual_htc_table()
#     # Check if this is a dual infill_cond bandwidth sweep analysis
#     elif "dual infill_cond" in str(output_log).lower() and "bandwidth sweep" in str(output_log).lower():
#         # Use dual infill_cond sweep plots and table
#         runtime_fig = create_dual_infill_cond_runtime_plot()
#         temp_fig = create_dual_infill_cond_temperature_plot()
#         results_table = create_dual_infill_cond_table()
#     # Check if this is a dual TIM_cond bandwidth sweep analysis
#     elif "dual tim_cond" in str(output_log).lower() and "bandwidth sweep" in str(output_log).lower():
#         # Use dual TIM_cond sweep plots and table
#         runtime_fig = create_dual_TIM_cond_runtime_plot()
#         temp_fig = create_dual_TIM_cond_temperature_plot()
#         results_table = create_dual_TIM_cond_table()
#     # Check if this is a regular bandwidth sweep analysis
#     elif "bandwidth sweep" in str(output_log).lower():
#         # Use bandwidth sweep plots and table
#         runtime_fig = create_bandwidth_sweep_runtime_plot()
#         temp_fig = create_bandwidth_sweep_temperature_plot()
#         results_table = create_bandwidth_sweep_table()
#     else:
#         # Parse runtime data from output for single analysis
#         parse_runtime_from_output(str(output_log))
        
#         # Create regular plots
#         runtime_fig = create_runtime_plot()
#         temp_fig = create_temperature_plot()
#         results_table = create_results_table()
    
#     return runtime_fig, temp_fig, results_table

if __name__ == '__main__':
    # for TIM_thickness in [10]: # [100]: # [10, 100]
    #     for TIM_cond in [1, 10]:
    #         for infill_cond in [1, 237]:
    #             run_iter = iterations(system_name = '3D_1GPU', HTC = TIM_thickness, TIM_cond = TIM_cond, infill_cond = infill_cond)
    #             HTC = 7 if TIM_thickness == 10 else 10
    #             print("HTC: {}, TIM_cond: {}, infill_cond: {}, Results: {}".format(HTC, TIM_cond, infill_cond, run_iter))
                # exit(0)
    # for HTC in [7]: # [100]: # [10, 100]
    #     for TIM_cond in [1, 10]:
    #         for infill_cond in [1, 237]:
    #             run_iter = iterations(system_name = '3D_1GPU', HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond)
    #             # HTC = 7 if TIM_thickness == 10 else 10
    #             print("HTC: {}, TIM_cond: {}, infill_cond: {}, Results: {}".format(HTC, TIM_cond, infill_cond, run_iter))
    # x_axis = ["Epoxy infill & TIM 5 W/mK", "AlN infill & TIM 5 W/mK", "Epoxy infill & TIM 10 W/mK", "AlN infill & TIM 10 W/mK"]
    # y_axis = []
    # for HTC in [7]: # [100]: # [10, 100]
    #     for TIM_cond in [5, 10]:
    #         for infill_cond in [1, 237]:
    #             run_iter = iterations(system_name = '3D_1GPU', HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond)
    #             y_axis.append(run_iter[0])
    #             # HTC = 7 if TIM_thickness == 10 else 10
    #             print("HTC: {}, TIM_cond: {}, infill_cond: {}, Results: {}".format(HTC, TIM_cond, infill_cond, run_iter))
    
    # print(x_axis)
    # print(y_axis)

    system_name = "3D_1GPU" # "2p5D_1GPU", "3D_1GPU"
    
    # Delete the test_output.txt file if it exists
    if os.path.exists("test_output.txt"):
        os.remove("test_output.txt")

    x_axis = ["TIM 5 W/(m K) & epoxy infill & epoxy underfill", "TIM 5 W/(m K) & epoxy infill & AlN underfill", "TIM 5 W/(m K) & AlN infill & epoxy underfill", "TIM 5 W/(m K) & AlN infill & AlN underfill", "TIM 10 W/(m K) & epoxy infill & epoxy underfill", "TIM 10 W/(m K) & epoxy infill & AlN underfill", "TIM 10 W/(m K) & AlN infill & epoxy underfill", "TIM 10 W/(m K) & AlN infill & AlN underfill"]
    y_axis = []
    f = open("test_output.txt", "w")
    f.write(str(x_axis) + "\n")

    for HBM_stack_height in [8, 16]: # [8, 16]:
        y_axis = []
        f.write("HBM stack height: {}\n".format(HBM_stack_height))
        for TIM_cond in [5, 10]:
            for infill_cond in [1, 237]:
                for underfill_cond in [1, 237]:
                    run_iter = iterations(system_name = system_name, HTC = 7, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = True)
                    y_axis.append(run_iter[0])
                    # HTC = 7 if TIM_thickness == 10 else 10
                    print("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}\n".format(TIM_cond, infill_cond, underfill_cond, run_iter))
                    f.write("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}\n".format(TIM_cond, infill_cond, underfill_cond, run_iter))
        
        f.write(str(y_axis) + "\n")
        
    f.close()

    # y_axis = []
    # f = open("test_output.txt", "w")
    # f.write(str(x_axis) + "\n")

    # for HBM_stack_height in [8, 16]:
    #     for TIM_cond in [5, 10]:
    #         for infill_cond in [1, 237]:
    #             for underfill_cond in [1, 237]:
    #                 run_iter = iterations(system_name = "3D_1GPU", HTC = 7, TIM_cond = TIM_cond, infill_cond = infill_cond, underfill_cond = underfill_cond, HBM_stack_height = HBM_stack_height, dummy_Si = True)
    #                 y_axis.append(run_iter[0])
    #                 # HTC = 7 if TIM_thickness == 10 else 10
    #                 print("TIM_cond: {}, infill_cond: {}, underfill_cond: {}, Results: {}".format(TIM_cond, infill_cond, underfill_cond, run_iter))
        
    #     f.write(str(y_axis) + "\n")
        
    # f.close()

    # for HTC in [10, 20]:
    #     for TIM_cond in [1, 10]:
    #         for infill_cond in [1, 237]:
    #             run_iter = iterations(system_name = '3D_waferscale', HTC = HTC, TIM_cond = TIM_cond, infill_cond = infill_cond)
    #             print("HTC: {}, TIM_cond: {}, infill_cond: {}, Results: {}".format(HTC, TIM_cond, infill_cond, run_iter))
    # run_iter = iterations(system_name = '3D_waferscale', HTC = 20, TIM_cond = 10, infill_cond = 237)
    # print(run_iter)
    # run_iter = iterations(system_name = '3D_waferscale', HTC = 20, TIM_cond = 10, infill_cond = 237)
    # print(run_iter)
    # app.run(debug=True, host='0.0.0.0', port=8052)
