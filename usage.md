# Usage (Quick)

```bash
git clone <your-repo-url>
cd final_project

# 1) Setup (creates .venv, installs Python deps, builds local ngspice)
./setup/setup.sh
source .venv/bin/activate

# 2) Run tests from submission space
cd submission/Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project
./scripts/run_all.sh

# Optional: run individually
./scripts/run_config1_3D_gpu_top.sh
./scripts/run_config2_3D_gpu_bottom.sh
./scripts/run_config3_2p5D.sh

# Optional: summarize
./scripts/summarize_all.sh
```

Outputs are written under:

- `submission/Owen-Ethan_905452983_palatics_Sarmiento-Rachel_506556199_rsarmiento_Project/out_therm/`

