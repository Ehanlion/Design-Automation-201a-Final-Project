from DeepFlow_llm_dev.run_perf import run_LLM
import os

if __name__ == "__main__":
    CURRENT_DEEPFLOW_CONFIG_PATH = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/hardware-config/testing_thermal_A100_3D_1GPU_ECTC.yaml"
    DEEPFLOW_MODEL_CONFIG_DIR = "/app/nanocad/projects/deepflow_thermal/DeepFlow/DeepFlow_llm_dev/configs/model-config"
    DEEPFLOW_MODEL_CONFIG_TARGET = "LLM_thermal.yaml"

    model_config_path = os.path.join(DEEPFLOW_MODEL_CONFIG_DIR, DEEPFLOW_MODEL_CONFIG_TARGET)

    runtime, GPU_time_frac_idle = run_LLM(
                mode="LLM",
                exp_hw_config_path=CURRENT_DEEPFLOW_CONFIG_PATH,
                exp_model_config_path=model_config_path,
                exp_dir="./output",
            )

    print(f"Runtime: {runtime}, GPU_time_frac_idle: {GPU_time_frac_idle}")