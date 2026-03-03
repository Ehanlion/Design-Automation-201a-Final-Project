import contextlib
import subprocess
import os
import re
import threading
import time
from datetime import datetime
import sys
import traceback
import csv
from pathlib import Path
from typing import Dict, Tuple, Optional
from functools import lru_cache
try:
    from DeepFlow_llm_dev.run_perf import run_LLM
except ImportError:
    print("Warning: DeepFlow_llm_dev.run_perf not found")

CURRENT_DEEPFLOW_CONFIG_PATH = None
DEEPFLOW_MODEL_CONFIG_DIR = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config"
DEEPFLOW_MODEL_CONFIG_TARGET = "LLM_thermal.yaml"

def run_deepflow():
    model_config_path = os.path.join(DEEPFLOW_MODEL_CONFIG_DIR, DEEPFLOW_MODEL_CONFIG_TARGET)

    with contextlib.redirect_stdout(None):
        runtime, GPU_time_frac_idle = run_LLM(
            mode="LLM",
            exp_hw_config_path=CURRENT_DEEPFLOW_CONFIG_PATH,
            exp_model_config_path=model_config_path,
            exp_dir="./output",
        )

    return float(runtime), float(GPU_time_frac_idle)

if __name__ == "__main__":
    file_path = 

    global CURRENT_DEEPFLOW_CONFIG_PATH
    CURRENT_DEEPFLOW_CONFIG_PATH = file_path